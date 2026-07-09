#!/usr/bin/env python3
"""Adopt workbench-sdd/v1 in the SAT Catalogo Ropa workspace.

The command is dry-run by default. Use --apply to write missing SAT-owned SDD
metadata, diagram sidecars, traceability, and generated .sdd indexes.
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
    SddStandardService,
)


SAT_STANDARD_ID = "workbench-sdd/v1"
DEFAULT_SAT_WORKSPACE = Path("/home/batata/Projects/sat-catalogo-ropa")


@dataclass(frozen=True, slots=True)
class AdoptionOperation:
    target: str
    action: str
    detail: str


@dataclass(frozen=True, slots=True)
class AdoptionReport:
    workspace: str
    applied: bool
    status: str
    operations: tuple[AdoptionOperation, ...]
    next_actions: tuple[str, ...]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safely adopt workbench-sdd/v1 in the SAT workspace."
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=DEFAULT_SAT_WORKSPACE,
        help="SAT workspace root. Defaults to /home/batata/Projects/sat-catalogo-ropa.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write missing adoption artifacts. Default is dry-run.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    workspace = args.workspace.expanduser().resolve()
    report = adopt_sat_workspace(workspace, apply=args.apply)
    emit(report, json_output=args.json_output)
    return 1 if report.status == "blocked" else 0


def adopt_sat_workspace(workspace: Path, *, apply: bool) -> AdoptionReport:
    operations: list[AdoptionOperation] = []
    if not workspace.is_dir():
        return AdoptionReport(
            workspace=str(workspace),
            applied=apply,
            status="blocked",
            operations=(
                AdoptionOperation(
                    str(workspace),
                    "blocked",
                    "Workspace directory does not exist.",
                ),
            ),
            next_actions=("Provide the SAT workspace path.",),
        )
    manifest_path = workspace / "codex-bridge.yaml"
    if not manifest_path.is_file():
        return AdoptionReport(
            workspace=str(workspace),
            applied=apply,
            status="blocked",
            operations=(
                AdoptionOperation(
                    "codex-bridge.yaml",
                    "blocked",
                    "SAT manifest is required before adoption.",
                ),
            ),
            next_actions=("Create codex-bridge.yaml before adopting SDD.",),
        )

    _plan_manifest(workspace, apply=apply, operations=operations)
    _plan_static_files(workspace, apply=apply, operations=operations)
    _plan_diagram_sidecars(workspace, apply=apply, operations=operations)
    _plan_traceability(workspace, apply=apply, operations=operations)
    _plan_spec_metadata(workspace, apply=apply, operations=operations)
    if apply:
        _generate_indexes(workspace, operations=operations)
    else:
        operations.append(
            AdoptionOperation(
                ".sdd/*.yaml",
                "would_generate",
                "Generated indexes will be refreshed after --apply writes metadata.",
            )
        )

    blocked = tuple(
        operation for operation in operations if operation.action == "blocked"
    )
    return AdoptionReport(
        workspace=str(workspace),
        applied=apply,
        status="blocked" if blocked else "applied" if apply else "dry-run",
        operations=tuple(operations),
        next_actions=_next_actions(operations, apply=apply),
    )


def _plan_manifest(
    workspace: Path,
    *,
    apply: bool,
    operations: list[AdoptionOperation],
) -> None:
    manifest_path = workspace / "codex-bridge.yaml"
    current = manifest_path.read_text(encoding="utf-8")
    updated = _updated_manifest_text(current)
    if updated == current:
        operations.append(
            AdoptionOperation(
                "codex-bridge.yaml",
                "exists",
                "SAT manifest already declares workbench-sdd/v1 adoption fields.",
            )
        )
        return
    operations.append(
        AdoptionOperation(
            "codex-bridge.yaml",
            "updated" if apply else "would_update",
            "Add standard, roots, protected baselines, and SAT context_rules.",
        )
    )
    if apply:
        manifest_path.write_text(updated, encoding="utf-8")


def _updated_manifest_text(text: str) -> str:
    lines = text.splitlines()
    try:
        sdd_index = next(index for index, line in enumerate(lines) if line == "sdd:")
    except StopIteration:
        insert_at = _first_top_level_after_header(lines)
        block = ["sdd:", *_sdd_adoption_lines()]
        return "\n".join([*lines[:insert_at], *block, *lines[insert_at:]]) + "\n"
    next_top_level = len(lines)
    for index in range(sdd_index + 1, len(lines)):
        line = lines[index]
        if line and not line.startswith(" ") and not line.startswith("\t"):
            next_top_level = index
            break
    existing_block = lines[sdd_index + 1 : next_top_level]
    additions = [
        line
        for key, line in _sdd_adoption_key_lines()
        if not _sdd_block_has_key(existing_block, key)
    ]
    if not additions:
        return text if text.endswith("\n") else text + "\n"
    updated = [*lines[:next_top_level], *additions, *lines[next_top_level:]]
    return "\n".join(updated) + "\n"


def _first_top_level_after_header(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        if line and not line.startswith(" ") and line not in {"kind:", "version:"}:
            return index
    return len(lines)


def _sdd_adoption_key_lines() -> tuple[tuple[str, str], ...]:
    return (
        ("standard", "  standard: workbench-sdd/v1"),
        ("project_type", "  project_type: flutter_app"),
        ("domain_root", "  domain_root: domain"),
        ("data_root", "  data_root: data"),
        ("generated_index_root", "  generated_index_root: .sdd"),
        (
            "protected_baseline",
            "  protected_baseline:\n"
            "    - architecture/components.mmd\n"
            "    - architecture/data-flow.mmd\n"
            "    - architecture/erd.mmd",
        ),
        (
            "context_rules",
            "  context_rules:\n"
            "    domains:\n"
            "      catalogo:\n"
            "        modules:\n"
            "          - mobile_app/lib\n"
            "          - backend/app\n"
            "        preferred_context:\n"
            "          - specs/001-sat-sdd-onboarding/spec.md\n"
            "          - architecture/components.mmd\n"
            "    candidate_limits:\n"
            "      related_specs: 5\n"
            "      related_diagrams: 3",
        ),
    )


def _sdd_adoption_lines() -> tuple[str, ...]:
    lines: list[str] = []
    for _key, value in _sdd_adoption_key_lines():
        lines.extend(value.splitlines())
    return tuple(lines)


def _sdd_block_has_key(block: list[str], key: str) -> bool:
    return any(line.startswith(f"  {key}:") for line in block)


def _plan_static_files(
    workspace: Path,
    *,
    apply: bool,
    operations: list[AdoptionOperation],
) -> None:
    static_files = {
        "architecture/overview.md": _architecture_overview(),
        "domain/glossary.md": _domain_glossary(),
        "data/persistence-model.md": _persistence_model(),
    }
    for relative_path, content in static_files.items():
        _write_missing_file(
            workspace,
            relative_path,
            content,
            apply=apply,
            operations=operations,
        )


def _plan_diagram_sidecars(
    workspace: Path,
    *,
    apply: bool,
    operations: list[AdoptionOperation],
) -> None:
    for diagram_path in sorted(workspace.glob("architecture/*.mmd")):
        relative = diagram_path.relative_to(workspace).as_posix()
        diagram_type = _diagram_type(relative, diagram_path)
        content = _diagram_metadata(
            diagram_id=diagram_path.stem,
            diagram_type=diagram_type,
            scope="baseline",
            source=relative,
        )
        _write_missing_file(
            workspace,
            diagram_path.with_suffix(".yaml").relative_to(workspace).as_posix(),
            content,
            apply=apply,
            operations=operations,
        )
    for diagram_path in sorted(workspace.glob("specs/*/diagrams/*.mmd")):
        relative = diagram_path.relative_to(workspace).as_posix()
        content = _diagram_metadata(
            diagram_id=diagram_path.stem,
            diagram_type=_diagram_type(relative, diagram_path),
            scope="feature",
            source=relative,
        )
        _write_missing_file(
            workspace,
            diagram_path.with_suffix(".yaml").relative_to(workspace).as_posix(),
            content,
            apply=apply,
            operations=operations,
        )


def _diagram_type(relative: str, path: Path) -> str:
    name = path.stem.lower()
    first_line = path.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
    directive = first_line[0].strip() if first_line else ""
    if "erd" in name or directive.startswith("erDiagram"):
        return "entity-relationship"
    if "sequence" in name or directive.startswith("sequenceDiagram"):
        return "sequence"
    if "component" in name:
        return "components"
    if "data-flow" in name:
        return "system-context"
    if relative.startswith("architecture/"):
        return "system-context"
    return "sequence"


def _plan_traceability(
    workspace: Path,
    *,
    apply: bool,
    operations: list[AdoptionOperation],
) -> None:
    for spec_path in sorted(workspace.glob("specs/*/spec.md")):
        spec_dir = spec_path.parent
        relative_path = (
            (spec_dir / "traceability.yaml").relative_to(workspace).as_posix()
        )
        content = _traceability_yaml(spec_dir.name)
        _write_missing_file(
            workspace,
            relative_path,
            content,
            apply=apply,
            operations=operations,
        )


def _plan_spec_metadata(
    workspace: Path,
    *,
    apply: bool,
    operations: list[AdoptionOperation],
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
                AdoptionOperation(
                    relative_path,
                    "blocked",
                    f"Metadata refresh failed: {exc}",
                )
            )
            continue
        if result.blocked:
            operations.append(
                AdoptionOperation(
                    relative_path,
                    "blocked",
                    "; ".join(result.blocked),
                )
            )
            continue
        if apply and result.written:
            operations.append(
                AdoptionOperation(
                    relative_path,
                    "updated" if metadata_existed else "created",
                    "Refresh generated spec metadata, source digests, task summary, and diagram summary.",
                )
            )
        elif not apply and result.would_write:
            operations.append(
                AdoptionOperation(
                    relative_path,
                    "would_update" if metadata_existed else "would_create",
                    "Refresh generated spec metadata, source digests, task summary, and diagram summary.",
                )
            )
        else:
            operations.append(
                AdoptionOperation(
                    relative_path,
                    "exists",
                    "Spec metadata is already fresh.",
                )
            )


def _write_missing_file(
    workspace: Path,
    relative_path: str,
    content: str,
    *,
    apply: bool,
    operations: list[AdoptionOperation],
) -> None:
    if _unsafe_relative_path(relative_path):
        operations.append(
            AdoptionOperation(relative_path, "blocked", "Unsafe adoption target path.")
        )
        return
    target = (workspace / relative_path).resolve()
    if not _is_relative_to(target, workspace):
        operations.append(
            AdoptionOperation(relative_path, "blocked", "Target escapes workspace.")
        )
        return
    if target.exists():
        operations.append(
            AdoptionOperation(relative_path, "exists", "Existing file preserved.")
        )
        return
    operations.append(
        AdoptionOperation(
            relative_path,
            "created" if apply else "would_create",
            "Create missing SAT SDD adoption artifact.",
        )
    )
    if apply:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _generate_indexes(workspace: Path, *, operations: list[AdoptionOperation]) -> None:
    try:
        standard = SddStandardService().load(SAT_STANDARD_ID)
        status = SddIndexService().ensure_indexes(
            workspace,
            standard=standard,
            auto_regenerate=True,
            allow_degraded=False,
        )
    except Exception as exc:  # noqa: BLE001 - script reports adoption blockers.
        operations.append(
            AdoptionOperation(
                ".sdd/*.yaml",
                "blocked",
                f"Index generation failed: {exc}",
            )
        )
        return
    operations.append(
        AdoptionOperation(
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


def _traceability_yaml(spec_id: str) -> str:
    return (
        f"spec_id: {spec_id}\n"
        "requirements:\n"
        "  FR-001:\n"
        "    acceptance_criteria:\n"
        "      - AC-001\n"
        "    tasks:\n"
        "      - T001\n"
        "    diagrams:\n"
        f"      - specs/{spec_id}/diagrams/feedback-sequence.mmd\n"
    )


def _architecture_overview() -> str:
    return (
        "# Architecture Overview\n\n"
        "SAT Catalogo Ropa is a Flutter catalog app with a local/catalog domain, "
        "checkout preparation, staff administration, loyalty parameters, and "
        "Codex Bridge feedback/workbench integration.\n\n"
        "Baseline diagrams live in `architecture/` and feature-local impact "
        "diagrams live under `specs/<feature>/diagrams/`.\n"
    )


def _domain_glossary() -> str:
    return (
        "# Domain Glossary\n\n"
        "- Product: SAT clothing item shown in the catalog.\n"
        "- Cart: shopper-selected products, quantities, totals, and points.\n"
        "- Checkout preview: prepared order summary before WhatsApp handoff.\n"
        "- Staff account: internal SAT user with role-protected access.\n"
        "- Loyalty rule: SAT-owned point and promotion configuration.\n"
    )


def _persistence_model() -> str:
    return (
        "# Persistence Model\n\n"
        "Persistent SAT concepts are described by `architecture/erd.mmd`: products, "
        "categories, sizes, customers, carts, orders, staff accounts, and loyalty "
        "settings. The app must not replace these project-owned concepts with "
        "Workbench-generated content.\n"
    )


def _next_actions(
    operations: list[AdoptionOperation],
    *,
    apply: bool,
) -> tuple[str, ...]:
    if any(operation.action == "blocked" for operation in operations):
        return ("Resolve blocked adoption operations and rerun.",)
    if not apply:
        return ("Review dry-run output, then rerun with --apply.",)
    return (
        "Run codex_bridge_sdd_doctor.py against SAT.",
        "Run SAT-focused Workbench/SDD tests.",
    )


def emit(report: AdoptionReport, *, json_output: bool) -> None:
    payload = {
        "kind": "codex.sddSatAdoptionReport",
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
