#!/usr/bin/env python3
"""Backfill missing Workbench SDD metadata for an adopted workspace.

The command is dry-run by default. Use --apply to create missing diagram
sidecars, missing feature traceability files, and regenerated .sdd indexes.
Existing project-owned files are preserved.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.application.services.sdd_index_service import SddIndexService  # noqa: E402
from backend.app.application.services.sdd_metadata_refresh_service import (  # noqa: E402
    SddMetadataRefreshService,
)
from backend.app.application.services.sdd_standard_service import (  # noqa: E402
    SddStandardError,
    SddStandardService,
    parse_simple_yaml,
)


@dataclass(frozen=True, slots=True)
class BackfillOperation:
    target: str
    action: str
    detail: str


@dataclass(frozen=True, slots=True)
class BackfillReport:
    workspace: str
    applied: bool
    status: str
    operations: tuple[BackfillOperation, ...]
    next_actions: tuple[str, ...]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safely backfill missing Workbench SDD metadata."
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace root. Defaults to the current directory.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write missing backfill artifacts. Default is dry-run.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    report = backfill_workspace(args.workspace.expanduser().resolve(), apply=args.apply)
    emit(report, json_output=args.json_output)
    return 1 if report.status == "blocked" else 0


def backfill_workspace(workspace: Path, *, apply: bool) -> BackfillReport:
    operations: list[BackfillOperation] = []
    standard_id, standard_error = _declared_standard_id(workspace)
    if standard_error is not None:
        return _blocked_report(workspace, apply, standard_error)
    if standard_id is None:
        return _blocked_report(
            workspace,
            apply,
            "codex-bridge.yaml must declare sdd.standard before SDD backfill.",
        )

    _plan_diagram_sidecars(workspace, apply=apply, operations=operations)
    _plan_traceability(workspace, apply=apply, operations=operations)
    _plan_spec_metadata(workspace, apply=apply, operations=operations)
    if apply:
        _generate_indexes(workspace, standard_id, operations=operations)
    else:
        operations.append(
            BackfillOperation(
                ".sdd/*.yaml",
                "would_generate",
                "Generated indexes will be refreshed after --apply writes metadata.",
            )
        )

    blocked = tuple(
        operation for operation in operations if operation.action == "blocked"
    )
    return BackfillReport(
        workspace=str(workspace),
        applied=apply,
        status="blocked" if blocked else "applied" if apply else "dry-run",
        operations=tuple(operations),
        next_actions=_next_actions(operations, apply=apply),
    )


def _blocked_report(workspace: Path, apply: bool, detail: str) -> BackfillReport:
    return BackfillReport(
        workspace=str(workspace),
        applied=apply,
        status="blocked",
        operations=(BackfillOperation("codex-bridge.yaml", "blocked", detail),),
        next_actions=("Fix the manifest blocker and rerun SDD backfill.",),
    )


def _declared_standard_id(workspace: Path) -> tuple[str | None, str | None]:
    manifest_path = workspace / "codex-bridge.yaml"
    if not manifest_path.is_file():
        return None, "Missing codex-bridge.yaml."
    try:
        payload = parse_simple_yaml(manifest_path.read_text(encoding="utf-8"))
    except SddStandardError as exc:
        return None, f"codex-bridge.yaml is not valid supported YAML: {exc}"
    if not isinstance(payload, dict):
        return None, "codex-bridge.yaml must contain a mapping."
    sdd = payload.get("sdd")
    if not isinstance(sdd, dict):
        return None, None
    standard = sdd.get("standard")
    if not isinstance(standard, str) or not standard.strip():
        return None, None
    return standard.strip(), None


def _plan_diagram_sidecars(
    workspace: Path,
    *,
    apply: bool,
    operations: list[BackfillOperation],
) -> None:
    for diagram_path in _diagram_paths(workspace):
        relative = diagram_path.relative_to(workspace).as_posix()
        scope = "baseline" if relative.startswith("architecture/") else "feature"
        content = _diagram_metadata(
            diagram_id=diagram_path.stem,
            diagram_type=_diagram_type(relative, diagram_path),
            scope=scope,
            source=relative,
        )
        _write_missing_file(
            workspace,
            diagram_path.with_suffix(".yaml").relative_to(workspace).as_posix(),
            content,
            apply=apply,
            operations=operations,
            detail="Create missing diagram metadata sidecar.",
        )


def _plan_traceability(
    workspace: Path,
    *,
    apply: bool,
    operations: list[BackfillOperation],
) -> None:
    for spec_path in sorted(workspace.glob("specs/*/spec.md")):
        spec_dir = spec_path.parent
        relative_path = (
            (spec_dir / "traceability.yaml").relative_to(workspace).as_posix()
        )
        content = _traceability_yaml(
            spec_id=spec_dir.name,
            diagrams=tuple(
                diagram.relative_to(workspace).as_posix()
                for diagram in sorted((spec_dir / "diagrams").glob("*.mmd"))
            ),
        )
        _write_missing_file(
            workspace,
            relative_path,
            content,
            apply=apply,
            operations=operations,
            detail="Create missing feature traceability links.",
        )


def _plan_spec_metadata(
    workspace: Path,
    *,
    apply: bool,
    operations: list[BackfillOperation],
) -> None:
    service = SddMetadataRefreshService(projects_root=workspace.parent)
    for spec_path in sorted(workspace.glob("specs/*/spec.md")):
        spec_id = spec_path.parent.name
        relative_path = f"specs/{spec_id}/metadata.yaml"
        metadata_existed = (workspace / relative_path).is_file()
        try:
            result = (
                service.refresh_spec_metadata(workspace, spec_id)
                if apply
                else service.preview_spec_metadata(workspace, spec_id)
            )
        except Exception as exc:  # noqa: BLE001 - script reports blockers.
            operations.append(
                BackfillOperation(
                    relative_path,
                    "blocked",
                    f"Metadata refresh failed: {exc}",
                )
            )
            continue
        if result.blocked:
            operations.append(
                BackfillOperation(
                    relative_path,
                    "blocked",
                    "; ".join(result.blocked),
                )
            )
            continue
        if apply and result.written:
            operations.append(
                BackfillOperation(
                    relative_path,
                    "updated" if metadata_existed else "created",
                    "Refresh generated spec metadata, source digests, task summary, and diagram summary.",
                )
            )
        elif not apply and result.would_write:
            operations.append(
                BackfillOperation(
                    relative_path,
                    "would_update" if metadata_existed else "would_create",
                    "Refresh generated spec metadata, source digests, task summary, and diagram summary.",
                )
            )
        else:
            operations.append(
                BackfillOperation(
                    relative_path,
                    "exists",
                    "Spec metadata is already fresh.",
                )
            )


def _diagram_paths(workspace: Path) -> tuple[Path, ...]:
    paths = [
        *workspace.glob("architecture/*.mmd"),
        *workspace.glob("specs/*/diagrams/*.mmd"),
    ]
    return tuple(
        sorted(
            {
                path.resolve()
                for path in paths
                if path.is_file() and _is_relative_to(path.resolve(), workspace)
            },
            key=lambda item: item.as_posix(),
        )
    )


def _diagram_type(relative: str, path: Path) -> str:
    name = path.stem.lower()
    directive = _first_nonempty_line(path)
    baseline = relative.startswith("architecture/")
    if directive.startswith("sequenceDiagram") or "sequence" in name:
        return "sequence"
    if directive.startswith("classDiagram") or "class" in name:
        return "domain-model" if baseline else "domain-impact"
    if directive.startswith("erDiagram") or "entity" in name or "erd" in name:
        return "entity-relationship" if baseline else "data-impact"
    if "deployment" in name:
        return "deployment" if baseline else "component-impact"
    if "component" in name:
        return "components" if baseline else "component-impact"
    return "system-context" if baseline else "component-impact"


def _first_nonempty_line(path: Path) -> str:
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _diagram_metadata(
    *,
    diagram_id: str,
    diagram_type: str,
    scope: str,
    source: str,
) -> str:
    change_policy = (
        "change_policy: baseline_impact_required\n" if scope == "baseline" else ""
    )
    return (
        f"diagram_id: {diagram_id}\n"
        f"diagram_type: {diagram_type}\n"
        f"scope: {scope}\n"
        "status: draft\n"
        "owner: project\n"
        f"source: {source}\n"
        f"{change_policy}"
    )


def _traceability_yaml(*, spec_id: str, diagrams: tuple[str, ...]) -> str:
    lines = [
        f"spec_id: {spec_id}",
        "requirements:",
        "  FR-001:",
        "    acceptance_criteria:",
        "      - AC-001",
        "    tasks:",
        "      - T001",
    ]
    if diagrams:
        lines.extend(["    diagrams:", f"      - {diagrams[0]}"])
    return "\n".join(lines) + "\n"


def _write_missing_file(
    workspace: Path,
    relative_path: str,
    content: str,
    *,
    apply: bool,
    operations: list[BackfillOperation],
    detail: str,
) -> None:
    if _unsafe_relative_path(relative_path):
        operations.append(
            BackfillOperation(relative_path, "blocked", "Unsafe backfill target path.")
        )
        return
    target = (workspace / relative_path).resolve()
    if not _is_relative_to(target, workspace):
        operations.append(
            BackfillOperation(relative_path, "blocked", "Target escapes workspace.")
        )
        return
    if target.exists():
        operations.append(
            BackfillOperation(relative_path, "exists", "Existing file preserved.")
        )
        return
    operations.append(
        BackfillOperation(
            relative_path,
            "created" if apply else "would_create",
            detail,
        )
    )
    if apply:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _generate_indexes(
    workspace: Path,
    standard_id: str,
    *,
    operations: list[BackfillOperation],
) -> None:
    try:
        standard = SddStandardService().load(standard_id)
        status = SddIndexService().ensure_indexes(
            workspace,
            standard=standard,
            auto_regenerate=True,
            allow_degraded=False,
        )
    except Exception as exc:  # noqa: BLE001 - script reports backfill blockers.
        operations.append(
            BackfillOperation(
                ".sdd/*.yaml",
                "blocked",
                f"Index generation failed: {exc}",
            )
        )
        return
    operations.append(
        BackfillOperation(
            ".sdd/*.yaml",
            "generated",
            f"index_status={status.state}; generated={','.join(status.generated)}",
        )
    )


def _unsafe_relative_path(relative_path: str) -> bool:
    path = Path(relative_path)
    return path.is_absolute() or ".." in path.parts or not relative_path.strip()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _next_actions(
    operations: list[BackfillOperation],
    *,
    apply: bool,
) -> tuple[str, ...]:
    if any(operation.action == "blocked" for operation in operations):
        return ("Resolve blocked backfill operations and rerun.",)
    if not apply:
        return ("Review dry-run output, then rerun with --apply.",)
    return ("Run codex_bridge_sdd_doctor.py --json --strict.",)


def emit(report: BackfillReport, *, json_output: bool) -> None:
    payload = {
        "kind": "codex.sddBackfillReport",
        "version": 1,
        "workspace": report.workspace,
        "applied": report.applied,
        "status": report.status,
        "operations": [asdict(operation) for operation in report.operations],
        "next_actions": list(report.next_actions),
    }
    if json_output:
        print(json.dumps(payload, indent=2))
        return
    print(f"Workspace: {report.workspace}")
    print(f"Status: {report.status}")
    for operation in report.operations:
        print(f"[{operation.action}] {operation.target}: {operation.detail}")
    for action in report.next_actions:
        print(f"next: {action}")


if __name__ == "__main__":
    raise SystemExit(main())
