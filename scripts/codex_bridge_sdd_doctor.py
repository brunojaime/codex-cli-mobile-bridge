#!/usr/bin/env python3
"""Validate the mandatory Codex Bridge SDD contract for a workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.application.services.sdd_project_service import (  # noqa: E402
    SddProject,
    SddProjectService,
    SddWorkspacePathError,
)
from backend.app.application.services.sdd_standard_service import (  # noqa: E402
    SddStandardService,
    parse_simple_yaml,
)
from backend.app.application.services.sdd_validation_service import (  # noqa: E402
    SddPreflightValidationService,
)
from backend.app.application.services.sdd_llm_instruction_service import (  # noqa: E402
    SddLlmInstructionService,
)
from backend.app.application.services.sdd_workbench_view_service import (  # noqa: E402
    SddWorkbenchViewService,
)


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    status: str
    detail: str
    next_actions: tuple[str, ...] = ()
    data: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class DoctorReport:
    workspace: str
    status: str
    ok: bool
    strict: bool
    checks: list[Check]
    next_actions: tuple[str, ...]
    index_status: dict[str, object] | None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a workspace's mandatory Codex Bridge SDD files. "
            "The command is read-only."
        )
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace root to inspect. Defaults to the current directory.",
    )
    parser.add_argument(
        "--projects-root",
        type=Path,
        default=Path(os.environ.get("PROJECTS_ROOT", str(Path.cwd().parent))),
        help="Allowed projects root. Defaults to PROJECTS_ROOT or cwd parent.",
    )
    parser.add_argument(
        "--workspace-aliases",
        default=os.environ.get("FEEDBACK_SOURCE_WORKSPACE_ALIASES", ""),
        help="Comma-separated sourceApp:/workspace/path aliases.",
    )
    parser.add_argument(
        "--standards-root",
        type=Path,
        default=None,
        help="Override Workbench SDD standards root. Intended for tests.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures.",
    )
    parser.add_argument(
        "--context-preset",
        default="sdd-audit",
        help="Context-pack preset used for doctor readiness checks.",
    )
    parser.add_argument(
        "--selected-artifact",
        default=None,
        help="Optional selected artifact for context-pack readiness checks.",
    )
    parser.add_argument(
        "--query",
        default="",
        help="Optional query used for context-pack readiness checks.",
    )
    parser.add_argument(
        "--regenerate-indexes",
        action="store_true",
        help="Allow doctor readiness checks to regenerate .sdd indexes.",
    )
    args = parser.parse_args()

    service = SddProjectService(
        projects_root=str(args.projects_root),
        workspace_aliases=parse_workspace_aliases(args.workspace_aliases),
    )
    try:
        project = service.get_project(str(args.workspace.expanduser().resolve()))
    except SddWorkspacePathError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    checks = build_checks(
        project,
        workspace=args.workspace.expanduser().resolve(),
        standards_root=args.standards_root,
        context_preset=args.context_preset,
        selected_artifact=args.selected_artifact,
        query=args.query,
        regenerate_indexes=args.regenerate_indexes,
    )
    report = build_report(project, checks, strict=args.strict)
    emit(report, json_output=args.json_output)
    has_failure = any(check.status == "fail" for check in report.checks)
    has_warning = any(check.status in {"warn", "degraded"} for check in report.checks)
    return 1 if has_failure or (args.strict and has_warning) else 0


def parse_workspace_aliases(raw_value: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for raw_entry in raw_value.split(","):
        entry = raw_entry.strip()
        if not entry or ":" not in entry:
            continue
        source_app, workspace_path = entry.split(":", 1)
        if source_app.strip() and workspace_path.strip():
            aliases[source_app.strip()] = workspace_path.strip()
    return aliases


def build_checks(
    project: SddProject,
    *,
    workspace: Path,
    standards_root: Path | None = None,
    context_preset: str = "sdd-audit",
    selected_artifact: str | None = None,
    query: str = "",
    regenerate_indexes: bool = False,
) -> list[Check]:
    checks = [
        _presence_check("manifest", project.manifest, "codex-bridge.yaml"),
        _presence_check(
            "constitution",
            project.constitution,
            ".specify/memory/constitution.md",
        ),
    ]
    if project.specs:
        checks.append(Check("specs", "pass", f"{len(project.specs)} spec(s)"))
    else:
        checks.append(Check("specs", "fail", "Missing specs/<feature>/spec.md"))

    diagram_count = len(project.architecture_diagrams) + sum(
        len(spec.diagrams) for spec in project.specs
    )
    if diagram_count:
        checks.append(Check("diagrams", "pass", f"{diagram_count} .mmd diagram(s)"))
    else:
        checks.append(
            Check("diagrams", "fail", "Missing architecture or spec diagrams")
        )

    for spec in project.specs:
        for filename in ("spec.md", "plan.md", "tasks.md"):
            status = "fail" if filename in spec.missing else "pass"
            checks.append(
                Check(
                    f"spec:{spec.id}:{filename}",
                    status,
                    f"{spec.path}/{filename}",
                )
            )
        if not spec.diagrams:
            checks.append(
                Check(
                    f"spec:{spec.id}:diagrams",
                    "warn",
                    f"{spec.path}/diagrams/*.mmd is empty",
                )
            )
    oversized = [
        file_value.path
        for file_value in (
            [project.manifest, project.constitution]
            + list(project.architecture_diagrams)
            + [
                file_value
                for spec in project.specs
                for file_value in (
                    spec.spec,
                    spec.plan,
                    spec.tasks,
                    *spec.diagrams,
                )
            ]
        )
        if file_value is not None and file_value.error == "file_too_large"
    ]
    for path in oversized:
        checks.append(Check("file_size", "fail", f"{path} exceeds size limit"))
    standard_service = SddStandardService(standards_root=standards_root)
    preflight = SddPreflightValidationService(standard_service=standard_service)
    checks.extend(
        Check(check.name, check.status, check.detail)
        for check in preflight.validate_workspace(workspace)
    )
    checks.extend(
        _readiness_checks(
            project,
            workspace=workspace,
            standard_service=standard_service,
            preflight=preflight,
            context_preset=context_preset,
            selected_artifact=selected_artifact,
            query=query,
            regenerate_indexes=regenerate_indexes,
        )
    )
    return checks


def build_report(
    project: SddProject, checks: list[Check], *, strict: bool
) -> DoctorReport:
    has_failure = any(check.status == "fail" for check in checks)
    has_warning = any(check.status in {"warn", "degraded"} for check in checks)
    status = "fail" if has_failure else "warn" if has_warning else "pass"
    return DoctorReport(
        workspace=project.workspace_path,
        status=status,
        ok=not has_failure,
        strict=strict,
        checks=checks,
        next_actions=_report_next_actions(checks),
        index_status=_index_status_payload(checks),
    )


def _readiness_checks(
    project: SddProject,
    *,
    workspace: Path,
    standard_service: SddStandardService,
    preflight: SddPreflightValidationService,
    context_preset: str,
    selected_artifact: str | None,
    query: str,
    regenerate_indexes: bool,
) -> list[Check]:
    standard_id = _declared_standard_id(workspace)
    if standard_id is None:
        return [
            Check(
                "context_pack",
                "skipped",
                "Context-pack readiness skipped because sdd.standard is not declared.",
                next_actions=(
                    "Declare sdd.standard: workbench-sdd/v1 to enable context routing.",
                ),
            ),
            Check(
                "llm_instructions",
                "skipped",
                "LLM instruction readiness skipped because sdd.standard is not declared.",
                next_actions=(
                    "Declare sdd.standard: workbench-sdd/v1 to enable Codex actions.",
                ),
            ),
            Check(
                "workbench_view",
                "skipped",
                "Workbench view readiness skipped because sdd.standard is not declared.",
                next_actions=(
                    "Adopt workbench-sdd/v1 before relying on Workbench SDD automation.",
                ),
            ),
        ]
    llm_service = SddLlmInstructionService(standard_service=standard_service)
    instruction = llm_service.build_prompt(
        workspace,
        preset=context_preset,
        selected_artifact=selected_artifact,
        query=query,
        auto_regenerate_indexes=regenerate_indexes,
        allow_degraded=True,
    )
    context_pack = instruction.context_pack
    checks: list[Check] = []
    if context_pack is None:
        checks.append(
            Check(
                "context_pack",
                "fail",
                instruction.error or "Context pack unavailable.",
                next_actions=(
                    "Fix standard or manifest blockers before routing context.",
                ),
                data={"preset": context_preset, "index_status": "not_checked"},
            )
        )
        checks.append(
            Check(
                "llm_instructions",
                "fail",
                instruction.error or "LLM instructions unavailable.",
                next_actions=(
                    "Fix standard or manifest blockers before launching Codex.",
                ),
            )
        )
    else:
        action_status = _doctor_status_from_action(
            context_pack.status,
            context_pack.index_status,
        )
        checks.append(
            Check(
                "context_pack",
                action_status,
                "context_pack_status="
                f"{context_pack.status} mode={context_pack.mode} "
                f"index_status={context_pack.index_status}; "
                + "; ".join(context_pack.routing_decisions or ("ready",)),
                next_actions=context_pack.next_actions,
                data={
                    "preset": context_pack.preset,
                    "status": context_pack.status,
                    "mode": context_pack.mode,
                    "index_status": context_pack.index_status,
                    "required_files": list(context_pack.required_files),
                    "blocked_reads": list(context_pack.blocked_reads),
                    "related_specs": [
                        {
                            "path": candidate.path,
                            "rank": candidate.rank,
                            "reason": candidate.reason,
                        }
                        for candidate in context_pack.related_specs
                    ],
                    "related_diagrams": [
                        {
                            "path": candidate.path,
                            "rank": candidate.rank,
                            "reason": candidate.reason,
                        }
                        for candidate in context_pack.related_diagrams
                    ],
                },
            )
        )
        checks.append(
            Check(
                "llm_instructions",
                action_status,
                f"llm_instruction_status={instruction.status}; "
                "prompt includes manifest, standard, constitution, context pack, "
                "blocked reads, routing decisions, and next actions.",
                next_actions=context_pack.next_actions,
                data={
                    "status": instruction.status,
                    "prompt_length": len(instruction.prompt),
                    "no_broad_read_guard": "scan_every_full_spec_body"
                    in instruction.prompt,
                },
            )
        )
    view_service = SddWorkbenchViewService(
        validation_service=preflight,
        llm_instruction_service=llm_service,
    )
    view = view_service.build_view(
        workspace=workspace,
        project=project,
        preset=context_preset,
        selected_artifact=selected_artifact,
        query=query,
        auto_regenerate_indexes=regenerate_indexes,
        allow_degraded=True,
    )
    view_status = _status_from_view(view)
    checks.append(
        Check(
            "workbench_view",
            view_status,
            "Workbench view readiness: "
            f"health={view.health.status} "
            f"standards={view.standards_compliance.status} "
            f"context={view.context_preview.status} "
            f"feature_specs={len(view.feature_specs)} "
            f"baselines={len(view.baselines)} "
            f"traceability_rows={len(view.traceability_matrix)} "
            f"impact_items={len(view.impact_queue)}.",
            next_actions=view.health.next_actions + view.context_preview.next_actions,
            data={
                "health_status": view.health.status,
                "standards_status": view.standards_compliance.status,
                "context_status": view.context_preview.status,
                "index_status": view.context_preview.index_status,
                "feature_spec_count": len(view.feature_specs),
                "baseline_count": len(view.baselines),
                "traceability_row_count": len(view.traceability_matrix),
                "impact_queue_count": len(view.impact_queue),
            },
        )
    )
    checks.extend(_traceability_checks(project, workspace))
    checks.append(_spec_intake_readiness_check(project, workspace))
    return checks


def _spec_intake_readiness_check(project: SddProject, workspace: Path) -> Check:
    data: dict[str, object] = {
        "metadata": {
            "missing": [],
            "malformed": [],
            "stale": [],
        },
        "intake_manifests": [],
        "missing_intake_artifacts": [],
        "media_policy_violations": [],
        "staged_media_warnings": [],
        "job_state_warnings": [],
    }
    warnings: list[str] = []
    failures: list[str] = []

    for spec in project.specs:
        metadata = spec.metadata
        if metadata.metadata_status == "missing":
            item = {"spec_id": spec.id, "path": f"{spec.path}/metadata.yaml"}
            data["metadata"]["missing"].append(item)  # type: ignore[index, union-attr]
            warnings.append(f"{spec.id}: metadata.yaml is missing")
        elif metadata.metadata_status == "malformed":
            item = {
                "spec_id": spec.id,
                "path": f"{spec.path}/metadata.yaml",
                "warnings": list(metadata.metadata_warnings),
            }
            data["metadata"]["malformed"].append(item)  # type: ignore[index, union-attr]
            failures.append(f"{spec.id}: metadata.yaml is malformed")
        elif metadata.metadata_status == "stale":
            item = {
                "spec_id": spec.id,
                "path": f"{spec.path}/metadata.yaml",
                "stale_paths": list(metadata.metadata_stale_paths),
            }
            data["metadata"]["stale"].append(item)  # type: ignore[index, union-attr]
            warnings.append(f"{spec.id}: metadata.yaml source digests are stale")

    _inspect_intake_retention(
        workspace,
        data=data,
        warnings=warnings,
        failures=failures,
    )
    _inspect_staged_media(
        workspace,
        data=data,
        warnings=warnings,
        failures=failures,
    )
    _inspect_job_statuses(
        workspace,
        data=data,
        warnings=warnings,
        failures=failures,
    )

    if failures:
        return Check(
            "spec_intake_readiness",
            "fail",
            "; ".join(failures[:5]),
            next_actions=(
                "Fix spec-intake metadata, media, retention, or job-state blockers before write flows.",
            ),
            data=data,
        )
    if warnings:
        return Check(
            "spec_intake_readiness",
            "warn",
            "; ".join(warnings[:5]),
            next_actions=(
                "Refresh metadata, clean stale staged media, or resolve failed jobs before final readiness.",
            ),
            data=data,
        )
    return Check(
        "spec_intake_readiness",
        "pass",
        "Spec-intake metadata, retention manifests, staged media, and job states are ready.",
        data=data,
    )


def _inspect_intake_retention(
    workspace: Path,
    *,
    data: dict[str, object],
    warnings: list[str],
    failures: list[str],
) -> None:
    for retention_path in sorted(workspace.glob("specs/*/intake/**/retention.json")):
        rel_retention = retention_path.relative_to(workspace).as_posix()
        manifest_record: dict[str, object] = {
            "path": rel_retention,
            "status": "pass",
            "artifact_count": 0,
        }
        data["intake_manifests"].append(manifest_record)  # type: ignore[union-attr]
        try:
            manifest = json.loads(retention_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - doctor should report detail.
            manifest_record["status"] = "fail"
            failures.append(f"{rel_retention}: retention manifest is invalid JSON")
            data["media_policy_violations"].append(  # type: ignore[union-attr]
                {
                    "path": rel_retention,
                    "code": "invalid_retention_json",
                    "detail": str(exc),
                }
            )
            continue
        if not isinstance(manifest, dict):
            manifest_record["status"] = "fail"
            failures.append(f"{rel_retention}: retention manifest must be an object")
            continue
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list):
            manifest_record["status"] = "fail"
            failures.append(f"{rel_retention}: retention artifacts must be a list")
            data["media_policy_violations"].append(  # type: ignore[union-attr]
                {
                    "path": rel_retention,
                    "code": "invalid_retention_artifacts",
                }
            )
            continue
        manifest_record["artifact_count"] = len(artifacts)
        for index, artifact in enumerate(artifacts):
            if not isinstance(artifact, dict):
                manifest_record["status"] = "fail"
                failures.append(f"{rel_retention}: artifact {index} must be an object")
                continue
            target_path = artifact.get("target_path")
            if not isinstance(target_path, str) or not target_path.strip():
                manifest_record["status"] = "fail"
                failures.append(
                    f"{rel_retention}: artifact {index} missing target_path"
                )
                continue
            artifact_error = _validate_intake_artifact(
                workspace,
                retention_path=retention_path,
                artifact=artifact,
            )
            if artifact_error:
                manifest_record["status"] = "fail"
                failures.append(artifact_error["detail"])
                code = str(artifact_error.get("code", "invalid_intake_artifact"))
                bucket = (
                    "missing_intake_artifacts"
                    if code == "missing_intake_artifact"
                    else "media_policy_violations"
                )
                data[bucket].append(artifact_error)  # type: ignore[index, union-attr]


def _validate_intake_artifact(
    workspace: Path,
    *,
    retention_path: Path,
    artifact: dict[str, object],
) -> dict[str, object] | None:
    target_path = str(artifact.get("target_path") or "")
    relative = Path(target_path)
    retention_root = retention_path.parent
    if relative.is_absolute() or ".." in relative.parts:
        return {
            "path": retention_path.relative_to(workspace).as_posix(),
            "target_path": target_path,
            "code": "unsafe_intake_artifact_path",
            "detail": f"{target_path}: intake artifact path is unsafe",
        }
    resolved = (workspace / relative).resolve()
    if not _is_relative_to(resolved, workspace):
        return {
            "path": retention_path.relative_to(workspace).as_posix(),
            "target_path": target_path,
            "code": "unsafe_intake_artifact_path",
            "detail": f"{target_path}: intake artifact escapes workspace",
        }
    if not _is_relative_to(resolved, retention_root):
        return {
            "path": retention_path.relative_to(workspace).as_posix(),
            "target_path": target_path,
            "code": "intake_artifact_outside_manifest_root",
            "detail": f"{target_path}: intake artifact is outside its intake root",
        }
    if not resolved.is_file():
        return {
            "path": retention_path.relative_to(workspace).as_posix(),
            "target_path": target_path,
            "code": "missing_intake_artifact",
            "detail": f"{target_path}: retention artifact is missing",
        }
    expected_size = artifact.get("byte_size")
    if isinstance(expected_size, int) and resolved.stat().st_size != expected_size:
        return {
            "path": retention_path.relative_to(workspace).as_posix(),
            "target_path": target_path,
            "code": "intake_artifact_size_mismatch",
            "detail": f"{target_path}: byte_size does not match retention manifest",
        }
    expected_sha = artifact.get("sha256")
    if isinstance(expected_sha, str) and expected_sha.strip():
        actual_sha = hashlib.sha256(resolved.read_bytes()).hexdigest()
        if actual_sha.lower() != expected_sha.lower():
            return {
                "path": retention_path.relative_to(workspace).as_posix(),
                "target_path": target_path,
                "code": "intake_artifact_sha_mismatch",
                "detail": f"{target_path}: sha256 does not match retention manifest",
            }
    return None


def _inspect_staged_media(
    workspace: Path,
    *,
    data: dict[str, object],
    warnings: list[str],
    failures: list[str],
) -> None:
    media_root = workspace / ".codex-bridge/sdd-media"
    if not media_root.is_dir():
        return
    now = datetime.now(UTC)
    for metadata_path in sorted(media_root.glob("*.json")):
        rel_metadata = metadata_path.relative_to(workspace).as_posix()
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - doctor should report detail.
            failures.append(f"{rel_metadata}: staged media sidecar is invalid JSON")
            data["media_policy_violations"].append(  # type: ignore[union-attr]
                {
                    "path": rel_metadata,
                    "code": "invalid_staged_media_json",
                    "detail": str(exc),
                }
            )
            continue
        if not isinstance(metadata, dict):
            failures.append(f"{rel_metadata}: staged media sidecar must be an object")
            data["media_policy_violations"].append(  # type: ignore[union-attr]
                {
                    "path": rel_metadata,
                    "code": "invalid_staged_media_sidecar",
                }
            )
            continue
        _validate_staged_media_sidecar(
            workspace,
            metadata_path=metadata_path,
            metadata=metadata,
            now=now,
            data=data,
            warnings=warnings,
            failures=failures,
        )


def _validate_staged_media_sidecar(
    workspace: Path,
    *,
    metadata_path: Path,
    metadata: dict[str, object],
    now: datetime,
    data: dict[str, object],
    warnings: list[str],
    failures: list[str],
) -> None:
    rel_metadata = metadata_path.relative_to(workspace).as_posix()
    lifecycle = str(metadata.get("lifecycle") or "staged")
    media_kind = str(metadata.get("media_kind") or "")
    if lifecycle not in {"staged", "consumed", "deleted"}:
        failures.append(f"{rel_metadata}: unsupported staged media lifecycle")
        data["media_policy_violations"].append(  # type: ignore[union-attr]
            {
                "path": rel_metadata,
                "code": "unsupported_staged_media_lifecycle",
                "lifecycle": lifecycle,
            }
        )
    if media_kind not in {"image", "crop", "audio"}:
        failures.append(f"{rel_metadata}: unsupported staged media kind")
        data["media_policy_violations"].append(  # type: ignore[union-attr]
            {
                "path": rel_metadata,
                "code": "unsupported_staged_media_kind",
                "media_kind": media_kind,
            }
        )
    staged_path = metadata.get("staged_path")
    if not isinstance(staged_path, str) or not staged_path.strip():
        failures.append(f"{rel_metadata}: staged_path is missing")
        data["media_policy_violations"].append(  # type: ignore[union-attr]
            {"path": rel_metadata, "code": "missing_staged_path"}
        )
        return
    resolved = _safe_workspace_path(workspace, staged_path)
    if resolved is None:
        failures.append(f"{rel_metadata}: staged_path is unsafe")
        data["media_policy_violations"].append(  # type: ignore[union-attr]
            {
                "path": rel_metadata,
                "code": "unsafe_staged_path",
                "staged_path": staged_path,
            }
        )
        return
    if lifecycle == "deleted":
        if resolved.exists():
            warnings.append(f"{staged_path}: deleted staged media file still exists")
            data["staged_media_warnings"].append(  # type: ignore[union-attr]
                {
                    "path": rel_metadata,
                    "staged_path": staged_path,
                    "code": "deleted_media_file_still_exists",
                }
            )
        return
    if not resolved.is_file():
        failures.append(f"{staged_path}: staged media file is missing")
        data["media_policy_violations"].append(  # type: ignore[union-attr]
            {
                "path": rel_metadata,
                "staged_path": staged_path,
                "code": "missing_staged_media_file",
            }
        )
        return
    expected_size = metadata.get("byte_size")
    if isinstance(expected_size, int) and resolved.stat().st_size != expected_size:
        failures.append(f"{staged_path}: staged media byte_size mismatch")
        data["media_policy_violations"].append(  # type: ignore[union-attr]
            {
                "path": rel_metadata,
                "staged_path": staged_path,
                "code": "staged_media_size_mismatch",
            }
        )
    expected_sha = metadata.get("sha256")
    if isinstance(expected_sha, str) and expected_sha.strip():
        actual_sha = hashlib.sha256(resolved.read_bytes()).hexdigest()
        if actual_sha.lower() != expected_sha.lower():
            failures.append(f"{staged_path}: staged media sha256 mismatch")
            data["media_policy_violations"].append(  # type: ignore[union-attr]
                {
                    "path": rel_metadata,
                    "staged_path": staged_path,
                    "code": "staged_media_sha_mismatch",
                }
            )
    if lifecycle == "consumed":
        consumed_path = metadata.get("consumed_path")
        if not isinstance(consumed_path, str) or not consumed_path.strip():
            failures.append(f"{rel_metadata}: consumed media missing consumed_path")
            data["media_policy_violations"].append(  # type: ignore[union-attr]
                {"path": rel_metadata, "code": "missing_consumed_path"}
            )
        elif _safe_workspace_path(workspace, consumed_path) is None:
            failures.append(f"{rel_metadata}: consumed_path is unsafe")
            data["media_policy_violations"].append(  # type: ignore[union-attr]
                {
                    "path": rel_metadata,
                    "code": "unsafe_consumed_path",
                    "consumed_path": consumed_path,
                }
            )
        return
    retention = metadata.get("retention")
    retention_hours = 24
    if isinstance(retention, dict) and isinstance(retention.get("hours"), int):
        retention_hours = int(retention["hours"])
    created_at = _parse_datetime(str(metadata.get("created_at") or ""))
    if created_at is None or created_at <= now - timedelta(hours=retention_hours):
        warnings.append(f"{staged_path}: staged media is cleanup-eligible")
        data["staged_media_warnings"].append(  # type: ignore[union-attr]
            {
                "path": rel_metadata,
                "staged_path": staged_path,
                "code": "cleanup_eligible_staged_media",
                "retention_hours": retention_hours,
            }
        )


def _inspect_job_statuses(
    workspace: Path,
    *,
    data: dict[str, object],
    warnings: list[str],
    failures: list[str],
) -> None:
    jobs_root = workspace / ".codex-bridge/sdd-jobs"
    if not jobs_root.is_dir():
        return
    for status_path in sorted(
        {
            *jobs_root.glob("*/job-status.json"),
            *jobs_root.glob("*/status.json"),
        }
    ):
        rel_status = status_path.relative_to(workspace).as_posix()
        try:
            payload = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - doctor should report detail.
            failures.append(f"{rel_status}: job status is invalid JSON")
            data["media_policy_violations"].append(  # type: ignore[union-attr]
                {
                    "path": rel_status,
                    "code": "invalid_job_status_json",
                    "detail": str(exc),
                }
            )
            continue
        if not isinstance(payload, dict):
            failures.append(f"{rel_status}: job status must be an object")
            continue
        status = str(payload.get("status") or payload.get("state") or "unknown")
        if status in {"failed", "timed_out", "blocked", "cancelled"}:
            warnings.append(f"{rel_status}: job is {status}")
            data["job_state_warnings"].append(  # type: ignore[union-attr]
                {
                    "path": rel_status,
                    "job_id": status_path.parent.name,
                    "status": status,
                    "next_actions": payload.get("next_actions", []),
                }
            )


def _safe_workspace_path(workspace: Path, relative_path: str) -> Path | None:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    resolved = (workspace / relative).resolve()
    if not _is_relative_to(resolved, workspace):
        return None
    return resolved


def _parse_datetime(value: str) -> datetime | None:
    if not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _declared_standard_id(workspace: Path) -> str | None:
    try:
        payload = parse_simple_yaml(
            (workspace / "codex-bridge.yaml").read_text(encoding="utf-8")
        )
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    sdd = payload.get("sdd")
    if not isinstance(sdd, dict):
        return None
    standard = sdd.get("standard")
    return standard if isinstance(standard, str) and standard.strip() else None


def _traceability_checks(project: SddProject, workspace: Path) -> list[Check]:
    checks: list[Check] = []
    for spec in project.specs:
        path = workspace / spec.path / "traceability.yaml"
        if not path.is_file():
            checks.append(
                Check(
                    f"traceability:{spec.id}",
                    "warn",
                    f"Missing {spec.path}/traceability.yaml",
                    next_actions=("Add traceability.yaml for this feature spec.",),
                )
            )
            continue
        try:
            payload = parse_simple_yaml(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - script should report validation detail.
            checks.append(
                Check(
                    f"traceability:{spec.id}",
                    "warn",
                    f"{path.relative_to(workspace)} is not valid supported YAML: {exc}",
                    next_actions=("Fix traceability YAML syntax.",),
                )
            )
            continue
        requirements = (
            payload.get("requirements") if isinstance(payload, dict) else None
        )
        if not isinstance(requirements, dict) or not requirements:
            checks.append(
                Check(
                    f"traceability:{spec.id}",
                    "warn",
                    f"{spec.path}/traceability.yaml has no requirements mapping.",
                    next_actions=(
                        "Link requirements to acceptance criteria, tasks, and diagrams.",
                    ),
                )
            )
            continue
        missing: list[str] = []
        for requirement_id, raw_requirement in requirements.items():
            if not isinstance(raw_requirement, dict):
                missing.append(f"{requirement_id}: requirement mapping")
                continue
            for key in ("acceptance_criteria", "tasks"):
                if not isinstance(raw_requirement.get(key), list):
                    missing.append(f"{requirement_id}: {key}")
        if missing:
            checks.append(
                Check(
                    f"traceability:{spec.id}",
                    "warn",
                    f"Missing traceability links: {', '.join(missing)}",
                    next_actions=("Complete requirement-to-task traceability links.",),
                )
            )
        else:
            checks.append(
                Check(
                    f"traceability:{spec.id}",
                    "pass",
                    f"{len(requirements)} requirement(s) linked.",
                )
            )
    return checks


def _presence_check(name: str, file_value: object | None, expected: str) -> Check:
    if file_value is None:
        return Check(name, "fail", f"Missing {expected}")
    return Check(name, "pass", expected)


def emit(report: DoctorReport, *, json_output: bool) -> None:
    if json_output:
        print(
            json.dumps(
                {
                    "kind": "codex.sddDoctorReport",
                    "version": 2,
                    "workspace": report.workspace,
                    "status": report.status,
                    "ok": report.ok,
                    "strict": report.strict,
                    "summary": _summary(report.checks),
                    "index_status": report.index_status,
                    "next_actions": list(report.next_actions),
                    "warnings": _checks_with_status(report.checks, "warn"),
                    "errors": _checks_with_status(report.checks, "fail"),
                    "skipped": _checks_with_status(report.checks, "skipped"),
                    "degraded": _checks_with_status(report.checks, "degraded"),
                    "checks": [check_to_json(check) for check in report.checks],
                },
                indent=2,
            )
        )
        return
    print(f"Workspace: {report.workspace}")
    print(f"Status: {report.status}")
    for check in report.checks:
        print(f"[{check.status}] {check.name}: {check.detail}")
        for next_action in check.next_actions:
            print(f"  next: {next_action}")


def check_to_json(check: Check) -> dict[str, object]:
    payload = asdict(check)
    payload["next_actions"] = list(check.next_actions)
    if payload["data"] is None:
        payload["data"] = {}
    return payload


def _doctor_status_from_action(status: str, index_status: str) -> str:
    if status == "ready":
        return "pass"
    if status == "degraded":
        return "degraded"
    if index_status in {"missing", "stale", "failed"}:
        return "warn"
    return "fail"


def _status_from_view(view: object) -> str:
    health = view.health.status
    context = view.context_preview.status
    if health == "fail":
        return "fail"
    if context == "degraded":
        return "degraded"
    if health == "warn" or context == "blocked":
        return "warn"
    return "pass"


def _summary(checks: list[Check]) -> dict[str, int]:
    return {
        "total": len(checks),
        "pass": sum(1 for check in checks if check.status == "pass"),
        "warn": sum(1 for check in checks if check.status == "warn"),
        "fail": sum(1 for check in checks if check.status == "fail"),
        "skipped": sum(1 for check in checks if check.status == "skipped"),
        "degraded": sum(1 for check in checks if check.status == "degraded"),
    }


def _checks_with_status(checks: list[Check], status: str) -> list[dict[str, object]]:
    return [check_to_json(check) for check in checks if check.status == status]


def _report_next_actions(checks: list[Check]) -> tuple[str, ...]:
    actions: list[str] = []
    for check in checks:
        actions.extend(check.next_actions)
    if any(check.status == "fail" for check in checks):
        actions.append("Fix failing SDD checks before write or Codex action flows.")
    elif any(check.status in {"warn", "degraded"} for check in checks):
        actions.append("Review warnings before relying on full Workbench automation.")
    return tuple(dict.fromkeys(action for action in actions if action))


def _index_status_payload(checks: list[Check]) -> dict[str, object] | None:
    for check in checks:
        if check.name == "context_pack" and check.data:
            return {
                "state": check.data.get("index_status"),
                "source": "context_pack",
            }
    for check in checks:
        if check.name == "index_status":
            state = "unknown"
            mode = "unknown"
            for token in check.detail.replace(";", " ").split():
                if token.startswith("index_status="):
                    state = token.partition("=")[2]
                if token.startswith("mode="):
                    mode = token.partition("=")[2]
            return {"state": state, "mode": mode, "source": "validation"}
    return None


if __name__ == "__main__":
    raise SystemExit(main())
