from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import NamedTemporaryFile
from typing import Any

import yaml

from backend.app.application.services.cloudflare_preview_service import (
    CloudflareClient,
    CloudflareLookupResult,
    CloudflareProvisioningPlanner,
    HttpCloudflareClient,
)
from backend.app.infrastructure.config.settings import Settings


_SOURCE_APP_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$")
_INVITE_UPSERT_SQL = """
INSERT INTO preview_invites (
  invite_id,
  token_sha256,
  source_app,
  app_slug,
  single_use,
  created_at,
  expires_at,
  used_at,
  revoked_at
) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, NULL, ?8)
ON CONFLICT(invite_id) DO UPDATE SET
  token_sha256 = excluded.token_sha256,
  source_app = excluded.source_app,
  app_slug = excluded.app_slug,
  single_use = excluded.single_use,
  created_at = excluded.created_at,
  expires_at = excluded.expires_at,
  revoked_at = excluded.revoked_at
"""


class WebPreviewError(RuntimeError):
    def __init__(self, *, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class WebPreviewPlanInput:
    project_path: str | None = None
    manifest_path: str | None = None
    source_app: str | None = None


@dataclass(frozen=True, slots=True)
class WebPreviewDeployInput(WebPreviewPlanInput):
    confirm_apply: bool = False
    expected_plan_hash: str | None = None


class WebPreviewDeployService:
    def __init__(
        self,
        *,
        settings: Settings,
        client: CloudflareClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._state_root = Path(settings.web_preview_state_dir).expanduser().resolve()
        self._preview_state_dir = self._state_root / "previews"
        self._invite_state_dir = self._state_root / "invites"
        self._preview_state_dir.mkdir(parents=True, exist_ok=True)
        self._invite_state_dir.mkdir(parents=True, exist_ok=True)

    def plan(self, request: WebPreviewPlanInput) -> dict[str, Any]:
        manifest_path, project_path, manifest = self._load_manifest(request)
        source_app = str(manifest.get("source_app") or request.source_app or "").strip()
        if not source_app:
            raise WebPreviewError(
                code="invalid_manifest",
                message="web preview manifest must include source_app",
            )
        if not _SOURCE_APP_RE.fullmatch(source_app):
            raise WebPreviewError(
                code="invalid_source_app",
                message="source_app must be a safe lowercase slug.",
            )
        if request.source_app and request.source_app != source_app:
            raise WebPreviewError(
                code="source_app_mismatch",
                message="requested source_app does not match manifest source_app",
            )
        planner = CloudflareProvisioningPlanner(settings=self._settings)
        cloudflare_plan = planner.plan_for_manifest(manifest)
        preview_id = _preview_id(source_app)
        plan_hash = _plan_hash(manifest, cloudflare_plan)
        health_path = str(cloudflare_plan.get("health_path") or "/__preview/health")
        preview_url = str(manifest.get("stable_url") or "")
        payload = {
            "kind": "codex.webPreview",
            "version": 1,
            "preview_id": preview_id,
            "source_app": source_app,
            "project_path": str(project_path),
            "manifest_path": str(manifest_path),
            "status": "planned",
            "preview_url": preview_url,
            "health_url": f"{preview_url.rstrip('/')}{health_path}",
            "plan_hash": plan_hash,
            "planned_resources": cloudflare_plan["resources"],
            "applied_resources": [],
            "error": None,
            "logs": [
                {
                    "level": "info",
                    "message": "Preview deploy plan created in dry-run mode.",
                },
            ],
            "created_at": _now_iso(),
            "completed_at": None,
        }
        self._persist_preview(payload)
        return payload

    def deploy(self, request: WebPreviewDeployInput) -> dict[str, Any]:
        planned = self.plan(
            WebPreviewPlanInput(
                project_path=request.project_path,
                manifest_path=request.manifest_path,
                source_app=request.source_app,
            )
        )
        if not self._settings.web_preview_apply_enabled:
            raise WebPreviewError(
                code="apply_disabled",
                message="WEB_PREVIEW_APPLY_ENABLED must be true before apply.",
                status_code=403,
            )
        if not request.confirm_apply:
            raise WebPreviewError(
                code="dry_run_required",
                message="Set confirm_apply=true after reviewing the dry-run plan.",
                status_code=400,
            )
        if not request.expected_plan_hash:
            raise WebPreviewError(
                code="plan_hash_required",
                message="expected_plan_hash is required for apply.",
                status_code=400,
            )
        if request.expected_plan_hash != planned["plan_hash"]:
            raise WebPreviewError(
                code="plan_hash_mismatch",
                message="expected_plan_hash does not match the current plan.",
                status_code=409,
            )
        self._assert_cloudflare_apply_configured()
        manifest_path, project_path, manifest = self._load_manifest(request)
        state = {
            **planned,
            "status": "applying",
            "logs": [
                *planned["logs"],
                {"level": "info", "message": "Apply gate passed; validating artifact."},
            ],
        }
        self._persist_preview(state)
        try:
            self._validate_project_for_apply(project_path, manifest)
            applied = CloudflarePreviewProvisioner(
                settings=self._settings,
                client=self._cloudflare_client(),
            ).apply(
                manifest=manifest,
                project_path=project_path,
            )
            state = {
                **state,
                "status": "active",
                "applied_resources": applied,
                "completed_at": _now_iso(),
                "logs": [
                    *state["logs"],
                    {
                        "level": "info",
                        "message": "Cloudflare preview resources applied.",
                    },
                ],
            }
            self._persist_preview(state)
            invite_sync_summary = self.sync_invites_for_preview(
                str(state["preview_id"]),
            )
            state = {
                **state,
                "invite_sync_summary": invite_sync_summary,
                "logs": [
                    *state["logs"],
                    {
                        "level": "info",
                        "message": (
                            "Invite sync completed: "
                            f"{invite_sync_summary['synced']} synced, "
                            f"{invite_sync_summary['failed']} failed, "
                            f"{invite_sync_summary['not_deployed']} not deployed."
                        ),
                    },
                ],
            }
        except Exception as exc:
            error = _safe_error(
                exc,
                secrets=(
                    self._settings.cloudflare_api_token,
                    self._settings.cloudflare_dns_api_token,
                ),
            )
            state = {
                **state,
                "status": "failed",
                "error": error,
                "completed_at": _now_iso(),
                "logs": [
                    *state["logs"],
                    {
                        "level": "error",
                        "message": error,
                    },
                ],
            }
        self._persist_preview(state)
        if state["status"] == "failed":
            raise WebPreviewError(
                code="deploy_failed",
                message=str(state["error"]),
                status_code=500,
            )
        return state

    def sync_invite(self, invite: dict[str, Any]) -> dict[str, Any]:
        preview = self.get_preview(str(invite.get("preview_id") or ""))
        if preview is None or preview.get("status") != "active":
            return {
                "sync_status": "not_deployed",
                "synced_at": None,
                "sync_error": None,
            }
        try:
            context = self._d1_sync_context(preview)
            result = self._cloudflare_client().execute_d1_sql(
                account_id=context["account_id"],
                database_id=context["database_id"],
                sql=_INVITE_UPSERT_SQL,
                params=_invite_sync_params(invite),
            )
            _raise_if_failed(result, "d1_invite_sync_failed")
            return {
                "sync_status": "synced",
                "synced_at": _now_iso(),
                "sync_error": None,
            }
        except Exception as exc:
            return {
                "sync_status": "failed",
                "synced_at": invite.get("synced_at"),
                "sync_error": _safe_error(
                    exc,
                    secrets=(
                        self._settings.cloudflare_api_token,
                        self._settings.cloudflare_dns_api_token,
                    ),
                ),
            }

    def sync_invites_for_preview(
        self,
        preview_id: str,
        *,
        invite_id: str | None = None,
    ) -> dict[str, Any]:
        summary = {
            "preview_id": preview_id,
            "total": 0,
            "synced": 0,
            "failed": 0,
            "not_deployed": 0,
            "pending": 0,
            "updated_at": _now_iso(),
        }
        for path in sorted(self._invite_state_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if payload.get("preview_id") != preview_id:
                continue
            if invite_id and payload.get("invite_id") != invite_id:
                continue
            summary["total"] += 1
            sync = self.sync_invite(payload)
            payload.update(sync)
            _atomic_write_json(path, payload)
            status = str(sync.get("sync_status") or "pending")
            if status in summary:
                summary[status] += 1
            else:
                summary["pending"] += 1
        return summary

    def get_preview(self, preview_id: str) -> dict[str, Any] | None:
        path = self._preview_state_dir / f"{_safe_id(preview_id)}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_previews(self, *, limit: int = 50) -> tuple[dict[str, Any], ...]:
        previews = []
        for path in self._preview_state_dir.glob("*.json"):
            try:
                previews.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        previews.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return tuple(previews[: max(1, min(limit, 200))])

    def _load_manifest(
        self,
        request: WebPreviewPlanInput,
    ) -> tuple[Path, Path, dict[str, Any]]:
        if request.manifest_path:
            manifest_path = Path(request.manifest_path).expanduser().resolve()
            project_path = (
                Path(request.project_path).expanduser().resolve()
                if request.project_path
                else manifest_path.parents[2]
            )
        elif request.project_path:
            project_path = Path(request.project_path).expanduser().resolve()
            manifest_path = project_path / "deploy/web-preview/web-preview-manifest.yaml"
        else:
            raise WebPreviewError(
                code="manifest_required",
                message="project_path or manifest_path is required.",
            )
        if not manifest_path.is_file():
            raise WebPreviewError(
                code="manifest_not_found",
                message="web preview manifest was not found.",
                status_code=404,
            )
        if not manifest_path.is_relative_to(project_path):
            raise WebPreviewError(
                code="manifest_outside_project",
                message="web preview manifest must be inside project_path.",
            )
        payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise WebPreviewError(
                code="invalid_manifest",
                message="web preview manifest must be a YAML object.",
            )
        return manifest_path, project_path, payload

    def _assert_cloudflare_apply_configured(self) -> None:
        missing = [
            name
            for name, value in (
                ("CLOUDFLARE_API_TOKEN", self._settings.cloudflare_api_token),
                ("CLOUDFLARE_DNS_API_TOKEN", self._settings.cloudflare_dns_api_token),
                ("CLOUDFLARE_ACCOUNT_ID", self._settings.cloudflare_account_id),
                ("CLOUDFLARE_ZONE_ID", self._settings.cloudflare_zone_id),
            )
            if not (value or "").strip()
        ]
        if missing:
            raise WebPreviewError(
                code="cloudflare_configuration_missing",
                message=f"Missing required Cloudflare configuration: {', '.join(missing)}",
                status_code=503,
            )

    def _validate_project_for_apply(
        self,
        project_path: Path,
        manifest: dict[str, Any],
    ) -> None:
        script = project_path / "scripts/validate_web_preview.sh"
        if not script.is_file():
            raise WebPreviewError(
                code="validation_script_missing",
                message="scripts/validate_web_preview.sh is missing.",
            )
        build = manifest.get("build")
        output_dir = (
            build.get("output_dir")
            if isinstance(build, dict)
            else None
        )
        if not output_dir:
            raise WebPreviewError(
                code="build_output_missing",
                message="web preview manifest build.output_dir is missing.",
            )
        env = {
            **os.environ,
            "REQUIRE_WEB_BUILD_OUTPUT": "true",
            "APP_RUNTIME_PROFILE": "real",
            "API_RUNTIME": "cloudflare_preview",
            "API_BASE_URL": str(
                manifest.get("runtime", {}).get("api_base_url")
                if isinstance(manifest.get("runtime"), dict)
                else "https://preview.nienfos.com"
            ),
            "APP_SLUG": str(manifest.get("source_app") or ""),
        }
        completed = subprocess.run(
            [str(script)],
            cwd=project_path,
            text=True,
            capture_output=True,
            check=False,
            shell=False,
            timeout=120,
            env=env,
        )
        if completed.returncode != 0:
            raise WebPreviewError(
                code="preview_validation_failed",
                message=_safe_error_text(completed.stderr or completed.stdout),
            )

    def _cloudflare_client(self) -> CloudflareClient:
        return self._client or HttpCloudflareClient(
            api_token=self._settings.cloudflare_api_token or "",
            dns_api_token=self._settings.cloudflare_dns_api_token,
            base_url=self._settings.cloudflare_api_base_url,
            timeout_seconds=self._settings.cloudflare_timeout_seconds,
        )

    def _persist_preview(self, payload: dict[str, Any]) -> None:
        preview_id = _safe_id(str(payload["preview_id"]))
        _atomic_write_json(self._preview_state_dir / f"{preview_id}.json", payload)

    def _d1_sync_context(self, preview: dict[str, Any]) -> dict[str, str]:
        account_id = (self._settings.cloudflare_account_id or "").strip()
        if not account_id:
            raise RuntimeError("cloudflare_account_id_missing")
        database_id = ""
        for resource in preview.get("applied_resources") or ():
            if isinstance(resource, dict) and resource.get("kind") == "d1_database":
                database_id = str(resource.get("database_id") or "").strip()
                break
        if not database_id:
            raise RuntimeError("d1_database_id_missing")
        return {
            "account_id": account_id,
            "database_id": database_id,
        }


class CloudflarePreviewProvisioner:
    def __init__(self, *, settings: Settings, client: CloudflareClient) -> None:
        self._settings = settings
        self._client = client

    def apply(self, *, manifest: dict[str, Any], project_path: Path) -> list[dict[str, Any]]:
        cloudflare = _expect_mapping(manifest, "cloudflare")
        resources = _expect_mapping(cloudflare, "resources")
        account_id = self._settings.cloudflare_account_id or ""
        zone_id = self._settings.cloudflare_zone_id or ""
        source_app = str(manifest.get("source_app") or "")
        base_domain = str(cloudflare.get("base_domain") or "preview.nienfos.com")
        worker_name = str(resources.get("worker_name") or "nienfos-preview-runtime")
        pages_project = str(resources.get("pages_project") or "nienfos-preview-web")
        d1_database = str(resources.get("d1_database") or "nienfos-preview")
        r2_bucket = resources.get("r2_bucket")
        access = manifest.get("access") if isinstance(manifest.get("access"), dict) else {}
        migrations_dir = str(access.get("migrations_dir") or "")
        applied = [
            self._ensure_dns_record(
                zone_id=zone_id,
                name=f"{base_domain}",
                target=f"{worker_name}.workers.dev",
            ),
            self._ensure_worker(
                account_id=account_id,
                worker_name=worker_name,
                script_path=project_path / "deploy/web-preview/worker/src/index.js",
            ),
        ]
        d1_resource = self._ensure_d1(account_id=account_id, database_name=d1_database)
        applied.append(d1_resource)
        if migrations_dir:
            applied.extend(
                self._apply_d1_migrations(
                    account_id=account_id,
                    database_name=d1_database,
                    database_id=str(d1_resource.get("database_id") or ""),
                    migrations_dir=project_path / migrations_dir,
                )
            )
        applied.extend(
            [
                self._ensure_pages_project(account_id=account_id, name=pages_project),
                {
                    "kind": "route",
                    "name": f"{base_domain}/{source_app}",
                    "status": "planned_external",
                    "detail": "Stable route is served by the shared preview Worker/Pages routing.",
                },
            ]
        )
        if r2_bucket:
            applied.append(
                {
                    "kind": "r2_bucket",
                    "name": str(r2_bucket),
                    "status": "skipped",
                    "detail": "R2 apply is gated for a later persistent-assets slice.",
                }
            )
        else:
            applied.append(
                {
                    "kind": "r2_bucket",
                    "name": None,
                    "status": "skipped",
                    "detail": "R2 disabled for this preview manifest.",
                }
            )
        return applied

    def _ensure_dns_record(
        self,
        *,
        zone_id: str,
        name: str,
        target: str,
    ) -> dict[str, Any]:
        existing = self._client.list_dns_records(
            zone_id=zone_id,
            name=name,
            record_type="CNAME",
        )
        _raise_if_failed(existing, "dns_list_failed")
        records = _cloudflare_result_list(existing.payload)
        if records:
            return {"kind": "dns_record", "name": name, "status": "existing"}
        created = self._client.create_dns_record(
            zone_id=zone_id,
            payload={
                "type": "CNAME",
                "name": name,
                "content": target,
                "proxied": True,
            },
        )
        _raise_if_failed(created, "dns_create_failed")
        return {"kind": "dns_record", "name": name, "status": "created"}

    def _ensure_worker(
        self,
        *,
        account_id: str,
        worker_name: str,
        script_path: Path,
    ) -> dict[str, Any]:
        existing = self._client.get_worker_script(
            account_id=account_id,
            script_name=worker_name,
        )
        if existing.ok:
            return {"kind": "worker_script", "name": worker_name, "status": "existing"}
        if existing.status_code not in (404, None):
            _raise_if_failed(existing, "worker_lookup_failed")
        if not script_path.is_file():
            raise RuntimeError("worker script source is missing")
        deployed = self._client.deploy_worker_script(
            account_id=account_id,
            script_name=worker_name,
            script_content=script_path.read_text(encoding="utf-8"),
        )
        _raise_if_failed(deployed, "worker_deploy_failed")
        return {"kind": "worker_script", "name": worker_name, "status": "created"}

    def _ensure_d1(self, *, account_id: str, database_name: str) -> dict[str, Any]:
        existing = self._client.list_d1_databases(account_id)
        _raise_if_failed(existing, "d1_list_failed")
        for item in _cloudflare_result_list(existing.payload):
            if isinstance(item, dict) and item.get("name") == database_name:
                return {
                    "kind": "d1_database",
                    "name": database_name,
                    "status": "existing",
                    "database_id": _d1_database_id(item),
                }
        created = self._client.create_d1_database(
            account_id=account_id,
            name=database_name,
        )
        _raise_if_failed(created, "d1_create_failed")
        return {
            "kind": "d1_database",
            "name": database_name,
            "status": "created",
            "database_id": _d1_database_id(_cloudflare_result(created.payload)),
        }

    def _apply_d1_migrations(
        self,
        *,
        account_id: str,
        database_name: str,
        database_id: str,
        migrations_dir: Path,
    ) -> list[dict[str, Any]]:
        if not database_id:
            raise RuntimeError("d1_database_id_missing")
        if not migrations_dir.is_dir():
            raise RuntimeError("d1_migrations_missing")
        applied: list[dict[str, Any]] = []
        for migration in sorted(migrations_dir.glob("*.sql")):
            result = self._client.execute_d1_sql(
                account_id=account_id,
                database_id=database_id,
                sql=migration.read_text(encoding="utf-8"),
            )
            _raise_if_failed(result, "d1_migration_failed")
            applied.append(
                {
                    "kind": "d1_migration",
                    "name": migration.name,
                    "database": database_name,
                    "status": "applied",
                }
            )
        if not applied:
            raise RuntimeError("d1_migrations_missing")
        return applied

    def _ensure_pages_project(self, *, account_id: str, name: str) -> dict[str, Any]:
        existing = self._client.get_pages_project(
            account_id=account_id,
            project_name=name,
        )
        if existing.ok:
            return {"kind": "pages_project", "name": name, "status": "existing"}
        if existing.status_code not in (404, None):
            _raise_if_failed(existing, "pages_lookup_failed")
        created = self._client.create_pages_project(account_id=account_id, name=name)
        _raise_if_failed(created, "pages_create_failed")
        return {"kind": "pages_project", "name": name, "status": "created"}


def _preview_id(source_app: str) -> str:
    return f"wp-{_safe_id(source_app)}"


def _safe_id(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in value)
    return safe.strip("-") or "preview"


def _plan_hash(manifest: dict[str, Any], cloudflare_plan: dict[str, Any]) -> str:
    material = {
        "source_app": manifest.get("source_app"),
        "stable_url": manifest.get("stable_url"),
        "runtime": manifest.get("runtime"),
        "cloudflare": manifest.get("cloudflare"),
        "resources": cloudflare_plan.get("resources"),
        "runtime_type": cloudflare_plan.get("runtime_type"),
        "health_path": cloudflare_plan.get("health_path"),
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as tmp:
        json.dump(payload, tmp, indent=2, sort_keys=True)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _expect_mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise RuntimeError(f"manifest {key} must be an object")
    return value


def _cloudflare_result_list(payload: dict[str, Any] | list[Any] | None) -> list[Any]:
    if isinstance(payload, dict):
        result = payload.get("result")
        return result if isinstance(result, list) else []
    return payload if isinstance(payload, list) else []


def _cloudflare_result(payload: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    result = payload.get("result")
    return result if isinstance(result, dict) else {}


def _d1_database_id(payload: dict[str, Any]) -> str:
    for key in ("uuid", "id", "database_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _invite_sync_params(invite: dict[str, Any]) -> list[Any]:
    return [
        str(invite.get("invite_id") or ""),
        str(invite.get("token_sha256") or ""),
        str(invite.get("source_app") or ""),
        str(invite.get("app_slug") or invite.get("source_app") or ""),
        1 if invite.get("single_use", True) else 0,
        str(invite.get("created_at") or ""),
        str(invite.get("expires_at") or ""),
        invite.get("revoked_at"),
    ]


def _raise_if_failed(result: CloudflareLookupResult, code: str) -> None:
    if result.ok:
        return
    raise RuntimeError(f"{code}: {_safe_error_text(result.error or 'Cloudflare request failed')}")


def _safe_error(
    exc: Exception,
    *,
    secrets: tuple[str | None, ...] = (),
) -> str:
    return _safe_error_text(str(exc), secrets=secrets)


def _safe_error_text(
    value: str,
    *,
    secrets: tuple[str | None, ...] = (),
) -> str:
    redacted = value.replace("Bearer ", "Bearer [redacted] ")
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[redacted]")
    for marker in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_DNS_API_TOKEN"):
        redacted = redacted.replace(marker, marker)
    return redacted[:1000]
