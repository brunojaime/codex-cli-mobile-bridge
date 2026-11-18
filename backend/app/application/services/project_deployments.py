"""Read deployment evidence; never infer a deployment from a branch or build."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import fcntl
import os
from tempfile import NamedTemporaryFile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class DeploymentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=200)
    environment: Literal["dev", "qa", "prod"]
    status: Literal["published", "deploying", "failed", "disabled", "expired"]
    deployed_at: datetime
    release: str | None = Field(default=None, min_length=1, max_length=200)
    commit: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{40,64}$")

    @field_validator("deployed_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("Deployment timestamps need a timezone")
        return value.astimezone(timezone.utc)


class DeploymentManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1]
    deployments: list[DeploymentRecord] = Field(max_length=1000)


class IndexedProject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_path: str
    deployments: list[DeploymentRecord] = Field(default_factory=list, max_length=1000)
    errors: list[str] = Field(default_factory=list)


class DeploymentIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1]
    observed_at: datetime
    projects: list[IndexedProject] = Field(max_length=2000)


def read_deployment_index(path):
    if path is None:
        return {}, []
    try:
        with Path(path).open("rb") as stream:
            content = stream.read(16 * 1024 * 1024 + 1)
        if len(content) > 16 * 1024 * 1024:
            raise ValueError("Index too large")
        index = DeploymentIndex.model_validate_json(content)
        if index.observed_at.tzinfo is None:
            raise ValueError("Index needs a timezone")
        stale = (datetime.now(timezone.utc) - index.observed_at).total_seconds() > 3600
        return {p.workspace_path: p for p in index.projects}, (
            ["La sincronización de deploys externos está desactualizada."]
            if stale
            else []
        )
    except FileNotFoundError:
        return {}, []
    except (ValueError, OSError):
        return {}, ["No se pudo consultar el índice de deploys externos."]


def comparison(environments):
    current = [env["current"] for env in environments]
    present = [item for item in current if item]
    if len(present) < 2:
        return "insufficient"
    # Known disagreement is conclusive even when a third environment lacks
    # source identity. Unknown metadata must never conceal that disagreement.
    for key in ("commit", "release"):
        if len({item[key] for item in present if item.get(key)}) > 1:
            return "different"
    # Compare immutable source identities when available. Never compare a commit
    # to a tag, or call two missing versions the same release.
    keys = [
        key for key in ("commit", "release") if all(item.get(key) for item in present)
    ]
    if not keys:
        return "unknown"
    if any(len({item[key] for item in present}) > 1 for key in keys):
        return "different"
    return "same" if len(present) == 3 else "partial_same"


def deployment_overview(
    coordinator, previews=None, workspace_path=None, *, index_path=None
):
    workspaces = coordinator.messages.list_workspaces()
    if workspace_path is not None:
        workspaces = [w for w in workspaces if w.path == workspace_path]
        if not workspaces:
            raise KeyError(workspace_path)
    projects = []
    indexed, index_errors = read_deployment_index(index_path)
    preview_error = False
    try:
        preview_rows = previews.list_previews(limit=None) if previews else ()
    except (OSError, ValueError):
        preview_rows = ()
        preview_error = True
    with coordinator.ledger() as db:
        receipts = db.execute(
            "SELECT id,workspace,receipt,updated_at FROM work_tasks "
            "WHERE status='completed' AND receipt IS NOT NULL"
        ).fetchall()
    for workspace in sorted(workspaces, key=lambda w: (w.name.casefold(), w.path)):
        records = []
        errors = [
            *index_errors,
            *(["No se pudieron leer los previews."] if preview_error else []),
        ]
        external = indexed.get(workspace.path)
        if external:
            records.extend(
                {**r.model_dump(mode="json"), "source": "provider"}
                for r in external.deployments
            )
            errors.extend(external.errors)
        manifest_path = Path(workspace.path) / ".codex" / "deployments.json"
        try:
            # Fixed allowlisted file, bounded read, no arbitrary file discovery.
            with manifest_path.open("rb") as stream:
                content = stream.read(1024 * 1024 + 1)
            if len(content) > 1024 * 1024:
                raise ValueError("Manifest too large")
            manifest = DeploymentManifest.model_validate_json(content)
            for record in manifest.deployments:
                records.append({**record.model_dump(mode="json"), "source": "manifest"})
        except FileNotFoundError:
            pass
        except (OSError, ValueError, ValidationError):
            errors.append("No se pudo leer el registro de deploys del proyecto.")
        for row in receipts:
            if row["workspace"] != workspace.path:
                continue
            try:
                receipt = json.loads(row["receipt"])
                record = DeploymentRecord(
                    id=f"work:{row['id']}",
                    environment=receipt["environment"],
                    status="published",
                    deployed_at=row["updated_at"],
                    commit=receipt.get("commit"),
                    release=receipt.get("release"),
                )
                records.append({**record.model_dump(mode="json"), "source": "delivery"})
            except (KeyError, TypeError, ValueError):
                errors.append("Hay una entrega cuyo comprobante no se pudo leer.")
        for preview in preview_rows:
            if preview.get("project_path") != workspace.path:
                continue
            status = {
                "active": "published",
                "applying": "deploying",
                "failed": "failed",
                "disabled": "disabled",
                "expired": "expired",
            }.get(preview.get("status"))
            if status is None:  # A plan is not a deployment.
                continue
            try:
                record = DeploymentRecord(
                    id=f"preview:{preview['preview_id']}",
                    environment="dev",
                    status=status,
                    deployed_at=(
                        preview.get("updated_at")
                        if status in {"disabled", "expired"}
                        else preview.get("completed_at") or preview["updated_at"]
                    ),
                )
                # A preview plan hash identifies configuration, not its release.
                records.append({**record.model_dump(mode="json"), "source": "preview"})
            except (KeyError, TypeError, ValueError):
                errors.append("Hay un preview cuyo comprobante no se pudo leer.")
        records.sort(
            key=lambda r: datetime.fromisoformat(r["deployed_at"]), reverse=True
        )
        environments = []
        for name in ("dev", "qa", "prod"):
            history = [r for r in records if r["environment"] == name]
            # Failed attempts don't replace the last published release. Explicit
            # deactivation/expiry does remove it.
            current = next(
                (
                    r
                    for r in history
                    if r["status"] in {"published", "disabled", "expired"}
                ),
                None,
            )
            if current and current["status"] != "published":
                current = None
            environments.append(
                {
                    "name": name,
                    "current": current,
                    "latest": history[0] if history else None,
                    "history": history,
                }
            )
        projects.append(
            {
                "name": workspace.name,
                "workspace_path": workspace.path,
                "environments": environments,
                "comparison": "unknown" if errors else comparison(environments),
                "errors": list(dict.fromkeys(errors)),
            }
        )
    return {"projects": projects, "observed_at": datetime.now(timezone.utc).isoformat()}


def record_deployment(project: Path, record: DeploymentRecord):
    directory = project.resolve(strict=True) / ".codex"
    directory.mkdir(exist_ok=True)
    target = directory / "deployments.json"
    with (directory / "deployments.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        manifest = (
            DeploymentManifest.model_validate_json(target.read_bytes())
            if target.exists()
            else DeploymentManifest(version=1, deployments=[])
        )
        for saved in manifest.deployments:
            if saved.id == record.id:
                if saved != record:
                    raise ValueError(
                        "Ese ID ya identifica otro comprobante; usá un ID nuevo para cada evento."
                    )
                return
        manifest.deployments.append(record)
        manifest.deployments = manifest.deployments[-1000:]
        temporary = None
        try:
            with NamedTemporaryFile(mode="w", dir=directory, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(manifest.model_dump(mode="json"), stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
