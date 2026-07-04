#!/usr/bin/env python3
"""Validate the mandatory Codex Bridge SDD contract for a workspace."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.application.services.sdd_project_service import (  # noqa: E402
    SddProject,
    SddProjectService,
    SddWorkspacePathError,
)


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    status: str
    detail: str


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
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures.",
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

    checks = build_checks(project)
    emit(project, checks, json_output=args.json_output)
    has_failure = any(check.status == "fail" for check in checks)
    has_warning = any(check.status == "warn" for check in checks)
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


def build_checks(project: SddProject) -> list[Check]:
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
        checks.append(Check("diagrams", "fail", "Missing architecture or spec diagrams"))

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
    return checks


def _presence_check(name: str, file_value: object | None, expected: str) -> Check:
    if file_value is None:
        return Check(name, "fail", f"Missing {expected}")
    return Check(name, "pass", expected)


def emit(project: SddProject, checks: list[Check], *, json_output: bool) -> None:
    if json_output:
        print(
            json.dumps(
                {
                    "workspace": project.workspace_path,
                    "ok": all(check.status != "fail" for check in checks),
                    "checks": [asdict(check) for check in checks],
                },
                indent=2,
            )
        )
        return
    print(f"Workspace: {project.workspace_path}")
    for check in checks:
        print(f"[{check.status}] {check.name}: {check.detail}")


if __name__ == "__main__":
    raise SystemExit(main())
