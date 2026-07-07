from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

loaded_scripts = sys.modules.get("scripts")
loaded_scripts_path = getattr(loaded_scripts, "__file__", "") if loaded_scripts else ""
if loaded_scripts_path and not loaded_scripts_path.startswith(str(ROOT / "scripts")):
    del sys.modules["scripts"]

from backend.app.application.services.sdd_standard_service import parse_simple_yaml  # noqa: E402
from scripts.codex_bridge_sdd_backfill import backfill_workspace  # noqa: E402


def test_sdd_backfill_dry_run_is_non_mutating(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_backfillable_project(project)

    report = backfill_workspace(project, apply=False)

    assert report.status == "dry-run"
    assert any(operation.action == "would_create" for operation in report.operations)
    assert any(operation.action == "would_generate" for operation in report.operations)
    assert not (project / "architecture/components.yaml").exists()
    assert not (project / "specs/001-demo/traceability.yaml").exists()
    assert not (project / ".sdd/spec-index.yaml").exists()


def test_sdd_backfill_apply_creates_metadata_and_enables_strict_doctor(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_backfillable_project(project)

    report = backfill_workspace(project, apply=True)

    assert report.status == "applied"
    assert "diagram_type: sequence" in _read(project / "architecture/runtime.yaml")
    assert "change_policy: baseline_impact_required" in _read(
        project / "architecture/runtime.yaml"
    )
    assert "diagram_type: data-impact" in _read(
        project / "specs/001-demo/diagrams/data.yaml"
    )
    assert "spec_id: 001-demo" in _read(project / "specs/001-demo/traceability.yaml")
    assert (project / ".sdd/spec-index.yaml").is_file()

    doctor = _doctor(project, tmp_path, "--strict")

    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    payload = json.loads(doctor.stdout)
    assert payload["status"] == "pass"
    assert payload["warnings"] == []
    assert payload["index_status"]["state"] == "fresh"


def test_phase12_documentation_and_traceability_are_complete() -> None:
    tasks = _read(ROOT / "specs/003-workbench-sdd-standard/tasks.md")
    traceability = parse_simple_yaml(
        _read(ROOT / "specs/003-workbench-sdd-standard/traceability.yaml")
    )
    docs = _read(ROOT / "docs/workbench-sdd-adoption.md")

    for task_id in ("T084", "T085", "T086", "T087", "T088", "T089", "T090"):
        assert f"- [x] {task_id} " in tasks
    assert "- [x] T095 " in tasks
    iterations = traceability["implementation"]["iterations"]
    phase12 = iterations["adoption-documentation-pass-001"]
    assert set(phase12["completed_tasks"]) == {
        "T084",
        "T085",
        "T086",
        "T087",
        "T088",
        "T089",
        "T090",
        "T095",
    }
    assert phase12["evidence"]
    for required_text in (
        "Workbench owns the process contract",
        "Feature Workflow",
        "Context Packs",
        "Diagram Governance",
        "Version Resolution",
        "SAT is an example, not a template for every domain",
    ):
        assert required_text in docs


def _write_backfillable_project(project: Path) -> None:
    (project / ".specify/memory").mkdir(parents=True)
    (project / "architecture").mkdir()
    (project / "domain").mkdir()
    (project / "data").mkdir()
    (project / "specs/001-demo/diagrams").mkdir(parents=True)
    (project / "codex-bridge.yaml").write_text(
        textwrap.dedent(
            """\
            kind: codex.bridge.project
            version: 1
            sdd:
              required: true
              standard: workbench-sdd/v1
              project_type: bridge_backend
              constitution: .specify/memory/constitution.md
              specs: specs
              architecture: architecture
              domain_root: domain
              data_root: data
              generated_index_root: .sdd
              protected_baseline:
                - architecture/components.mmd
                - architecture/runtime.mmd
              context_rules:
                domains:
                  workbench:
                    modules:
                      - backend/app/application/services
                    preferred_context:
                      - specs/001-demo/spec.md
                candidate_limits:
                  related_specs: 5
                  related_diagrams: 3
            """
        ),
        encoding="utf-8",
    )
    (project / ".specify/memory/constitution.md").write_text(
        "# Constitution\n", encoding="utf-8"
    )
    (project / "architecture/overview.md").write_text(
        "# Architecture Overview\n", encoding="utf-8"
    )
    (project / "domain/glossary.md").write_text("# Domain Glossary\n", encoding="utf-8")
    (project / "data/persistence-model.md").write_text(
        "# Persistence Model\n", encoding="utf-8"
    )
    (project / "architecture/components.mmd").write_text(
        "flowchart LR\nA --> B\n", encoding="utf-8"
    )
    (project / "architecture/runtime.mmd").write_text(
        "sequenceDiagram\nA->>B: call\n", encoding="utf-8"
    )
    (project / "specs/001-demo/spec.md").write_text("# Demo Spec\n", encoding="utf-8")
    (project / "specs/001-demo/plan.md").write_text("# Demo Plan\n", encoding="utf-8")
    (project / "specs/001-demo/tasks.md").write_text(
        "# Demo Tasks\n\n- [ ] T001\n", encoding="utf-8"
    )
    (project / "specs/001-demo/diagrams/data.mmd").write_text(
        "erDiagram\nA ||--o{ B : owns\n", encoding="utf-8"
    )


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


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")
