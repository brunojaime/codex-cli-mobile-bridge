from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

loaded_scripts = sys.modules.get("scripts")
loaded_scripts_path = getattr(loaded_scripts, "__file__", "") if loaded_scripts else ""
if loaded_scripts_path and not loaded_scripts_path.startswith(str(ROOT / "scripts")):
    del sys.modules["scripts"]

from scripts.codex_bridge_sdd_sat_adopt import (  # noqa: E402
    AdoptionOperation,
    _write_missing_file,
    adopt_sat_workspace,
)


def test_sat_adoption_dry_run_is_non_mutating(tmp_path: Path) -> None:
    project = tmp_path / "sat-catalogo-ropa"
    _write_sat_workspace(project)

    report = adopt_sat_workspace(project, apply=False)

    assert report.status == "dry-run"
    actions = {operation.action for operation in report.operations}
    assert {"would_update", "would_create", "would_generate"} <= actions
    assert "standard: workbench-sdd/v1" not in _read(project / "codex-bridge.yaml")
    assert not (project / "domain/glossary.md").exists()
    assert not (project / "architecture/components.yaml").exists()
    assert not (project / ".sdd/spec-index.yaml").exists()


def test_sat_adoption_apply_writes_metadata_indexes_and_passes_strict_doctor(
    tmp_path: Path,
) -> None:
    project = tmp_path / "sat-catalogo-ropa"
    _write_sat_workspace(project)

    report = adopt_sat_workspace(project, apply=True)

    assert report.status == "applied"
    manifest = _read(project / "codex-bridge.yaml")
    assert "standard: workbench-sdd/v1" in manifest
    assert "project_type: flutter_app" in manifest
    assert "catalogo:" in manifest
    assert "architecture/components.mmd" in manifest
    assert _read(project / "domain/glossary.md").startswith("# Domain Glossary")
    assert _read(project / "data/persistence-model.md").startswith(
        "# Persistence Model"
    )
    baseline_sidecar = _read(project / "architecture/components.yaml")
    assert "diagram_type: components" in baseline_sidecar
    assert "source: architecture/components.mmd" in baseline_sidecar
    assert "change_policy: baseline_impact_required" in baseline_sidecar
    feature_sidecar = _read(
        project / "specs/001-sat-sdd-onboarding/diagrams/feedback-sequence.yaml"
    )
    assert "diagram_type: sequence" in feature_sidecar
    assert (
        "source: specs/001-sat-sdd-onboarding/diagrams/feedback-sequence.mmd"
        in feature_sidecar
    )
    assert "change_policy:" not in feature_sidecar
    assert (project / "specs/001-sat-sdd-onboarding/traceability.yaml").is_file()
    assert (project / ".sdd/spec-index.yaml").is_file()
    assert (project / ".sdd/diagram-index.yaml").is_file()
    assert (project / ".sdd/module-index.yaml").is_file()
    assert (project / ".sdd/context-index.yaml").is_file()

    doctor = _doctor(project, tmp_path, "--strict")

    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    payload = json.loads(doctor.stdout)
    assert payload["status"] == "pass"
    assert payload["warnings"] == []
    assert payload["index_status"]["state"] == "fresh"


def test_sat_adoption_preserves_existing_project_owned_files(tmp_path: Path) -> None:
    project = tmp_path / "sat-catalogo-ropa"
    _write_sat_workspace(project)
    custom_glossary = "# Domain Glossary\n\nSAT custom content.\n"
    (project / "domain").mkdir()
    (project / "domain/glossary.md").write_text(custom_glossary, encoding="utf-8")

    report = adopt_sat_workspace(project, apply=True)

    assert report.status == "applied"
    assert _read(project / "domain/glossary.md") == custom_glossary
    glossary_operation = _operation(report.operations, "domain/glossary.md")
    assert glossary_operation.action == "exists"
    assert glossary_operation.detail == "Existing file preserved."


def test_sat_adoption_blocks_unsafe_targets_without_writing(tmp_path: Path) -> None:
    operations: list[AdoptionOperation] = []

    _write_missing_file(
        tmp_path,
        "../escape.md",
        "nope\n",
        apply=True,
        operations=operations,
    )

    assert operations == [
        AdoptionOperation("../escape.md", "blocked", "Unsafe adoption target path.")
    ]
    assert not (tmp_path.parent / "escape.md").exists()


def test_sdd_doctor_remains_read_only_before_sat_adoption(tmp_path: Path) -> None:
    project = tmp_path / "sat-catalogo-ropa"
    _write_sat_workspace(project)
    adopted_manifest = _read(project / "codex-bridge.yaml").replace(
        "  required: true\n",
        "  required: true\n  standard: workbench-sdd/v1\n",
    )
    (project / "codex-bridge.yaml").write_text(adopted_manifest, encoding="utf-8")

    doctor = _doctor(project, tmp_path)

    assert doctor.returncode == 0
    assert not (project / "architecture/components.yaml").exists()
    assert not (project / ".sdd/spec-index.yaml").exists()
    payload = json.loads(doctor.stdout)
    assert payload["status"] == "warn"
    assert any(check["name"] == "diagram_metadata" for check in payload["warnings"])
    assert payload["index_status"]["state"] == "missing"


def _doctor(
    project: Path,
    projects_root: Path,
    *extra_args: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "scripts/codex_bridge_sdd_doctor.py",
            "--workspace",
            str(project),
            "--projects-root",
            str(projects_root),
            "--json",
            *extra_args,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _write_sat_workspace(project: Path) -> None:
    (project / ".specify/memory").mkdir(parents=True)
    (project / "architecture").mkdir()
    (project / "specs/001-sat-sdd-onboarding/diagrams").mkdir(parents=True)
    (project / "codex-bridge.yaml").write_text(
        textwrap.dedent(
            """\
            kind: codex.bridge.project
            version: 1
            project:
              id: sat-catalogo-ropa
              name: SAT Catalogo Ropa
            sdd:
              required: true
              devModeFlag: CODEX_BRIDGE_DEV_MODE
              constitution: .specify/memory/constitution.md
              specs: specs
              architecture: architecture
              diagramsSourceOfTruth: mmd
              renderedDiagramCache: .codex-bridge/cache/diagrams
            """
        ),
        encoding="utf-8",
    )
    (project / ".specify/memory/constitution.md").write_text(
        "# Constitution\n\nSAT project governance.\n",
        encoding="utf-8",
    )
    (project / "architecture/components.mmd").write_text(
        "flowchart LR\nApp --> Catalog\n",
        encoding="utf-8",
    )
    (project / "architecture/data-flow.mmd").write_text(
        "flowchart TD\nCatalog --> Cart\n",
        encoding="utf-8",
    )
    (project / "architecture/erd.mmd").write_text(
        "erDiagram\nPRODUCT ||--o{ ORDER : appears_in\n",
        encoding="utf-8",
    )
    (project / "specs/001-sat-sdd-onboarding/spec.md").write_text(
        textwrap.dedent(
            """\
            # SAT Catalog Domain

            ## Intent

            SAT Catalogo Ropa documents product catalog, cart, checkout, staff,
            and loyalty behavior.
            """
        ),
        encoding="utf-8",
    )
    (project / "specs/001-sat-sdd-onboarding/plan.md").write_text(
        "# Plan\n\nSAT SDD onboarding plan.\n",
        encoding="utf-8",
    )
    (project / "specs/001-sat-sdd-onboarding/tasks.md").write_text(
        "# Tasks\n\n- [status: done] Document SAT catalog behavior.\n",
        encoding="utf-8",
    )
    (
        project / "specs/001-sat-sdd-onboarding/diagrams/feedback-sequence.mmd"
    ).write_text(
        "sequenceDiagram\nUser->>App: feedback\n",
        encoding="utf-8",
    )


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _operation(
    operations: tuple[AdoptionOperation, ...],
    target: str,
) -> AdoptionOperation:
    for operation in operations:
        if operation.target == target:
            return operation
    raise AssertionError(f"Missing operation for {target}")
