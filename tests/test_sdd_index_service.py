from __future__ import annotations

import os
import textwrap
from pathlib import Path

from backend.app.application.services.sdd_index_service import (
    INDEX_FILENAMES,
    SddIndexService,
)
from backend.app.application.services.sdd_standard_service import SddStandardService
from backend.app.application.services.sdd_validation_service import (
    SddPreflightValidationService,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_STANDARDS = ROOT / "tests/fixtures/sdd_standards"


def test_index_generation_creates_all_indexes_and_then_reports_fresh(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_index_project(project)
    standard = _standard()
    service = SddIndexService()

    generated = service.ensure_indexes(
        project,
        standard=standard,
        auto_regenerate=True,
    )
    fresh = service.ensure_indexes(
        project,
        standard=standard,
        auto_regenerate=False,
    )

    assert generated.state == "regenerated"
    assert generated.generated == INDEX_FILENAMES
    assert fresh.state == "fresh"
    for filename in INDEX_FILENAMES:
        assert (project / ".sdd" / filename).is_file()
    context_index = (project / ".sdd/context-index.yaml").read_text()
    assert "index_status: regenerated" in context_index
    assert "read_policy: prefix_only_no_full_spec_body" in context_index


def test_missing_index_regenerates_when_allowed(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_index_project(project)
    standard = _standard()
    service = SddIndexService()
    service.ensure_indexes(project, standard=standard, auto_regenerate=True)
    (project / ".sdd/spec-index.yaml").unlink()

    status = service.ensure_indexes(project, standard=standard, auto_regenerate=True)

    assert status.state == "regenerated"
    assert status.missing == ("spec-index.yaml",)
    assert (project / ".sdd/spec-index.yaml").is_file()


def test_stale_index_reports_hard_failure_when_regeneration_disabled(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_index_project(project)
    standard = _standard()
    service = SddIndexService()
    service.ensure_indexes(project, standard=standard, auto_regenerate=True)
    spec_path = project / "specs/001-demo/spec.md"
    spec_path.write_text(spec_path.read_text() + "\nChanged requirement.\n")
    os.utime(spec_path, None)

    status = service.ensure_indexes(project, standard=standard, auto_regenerate=False)

    assert status.state == "stale"
    assert status.mode == "hard_failure"
    assert set(status.stale) == set(INDEX_FILENAMES)
    assert "must not read all specs" in status.detail


def test_stale_index_regenerates_when_allowed(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_index_project(project)
    standard = _standard()
    service = SddIndexService()
    service.ensure_indexes(project, standard=standard, auto_regenerate=True)
    spec_path = project / "specs/001-demo/spec.md"
    spec_path.write_text(spec_path.read_text() + "\nChanged requirement.\n")
    os.utime(spec_path, None)

    status = service.ensure_indexes(project, standard=standard, auto_regenerate=True)

    assert status.state == "regenerated"
    assert set(status.stale) == set(INDEX_FILENAMES)


def test_missing_index_hard_fails_when_regeneration_disabled(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_index_project(project)

    status = SddIndexService().ensure_indexes(
        project,
        standard=_standard(),
        auto_regenerate=False,
    )

    assert status.state == "missing"
    assert status.mode == "hard_failure"
    assert set(status.missing) == set(INDEX_FILENAMES)


def test_regeneration_failure_returns_degraded_mode(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_index_project(project)
    (project / ".sdd").write_text("not a directory\n")

    status = SddIndexService().ensure_indexes(
        project,
        standard=_standard(),
        auto_regenerate=True,
        allow_degraded=True,
    )

    assert status.state == "failed"
    assert status.mode == "degraded"
    assert "degraded mode forbids all-spec fallback" in status.detail


def test_spec_index_uses_prefix_only_and_does_not_capture_full_body(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_index_project(project)
    marker = "SECRET_FULL_BODY_MARKER"
    (project / "specs/001-demo/spec.md").write_text(
        "# Demo Spec\n\n" + ("x" * 9000) + marker + "\n"
    )

    status = SddIndexService().ensure_indexes(
        project,
        standard=_standard(),
        auto_regenerate=True,
    )

    spec_index = (project / ".sdd/spec-index.yaml").read_text()
    assert status.state == "regenerated"
    assert marker not in spec_index
    assert "read_policy: prefix_only_no_full_spec_body" in spec_index


def test_validator_reports_missing_index_status_and_historical_metadata_warning(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_index_project(project)
    service = SddPreflightValidationService(
        standard_service=SddStandardService(standards_root=FIXTURE_STANDARDS)
    )

    checks = service.validate_workspace(project)
    by_name = {check.name: check for check in checks}

    assert by_name["index_status"].status == "warn"
    assert "index_status=missing" in by_name["index_status"].detail
    assert by_name["diagram_metadata"].status == "warn"
    assert "diagram metadata sidecar(s) missing" in by_name["diagram_metadata"].detail


def _standard():
    return SddStandardService(standards_root=FIXTURE_STANDARDS).load("workbench-sdd/v1")


def _write_index_project(project: Path) -> None:
    (project / ".specify/memory").mkdir(parents=True)
    (project / "architecture").mkdir(parents=True)
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
        )
    )
    (project / ".specify/memory/constitution.md").write_text("# Constitution\n")
    (project / "architecture/components.mmd").write_text("flowchart LR\nA --> B\n")
    (project / "specs/001-demo/spec.md").write_text(
        textwrap.dedent(
            """\
            ---
            status: draft
            ---

            # Demo Spec

            First summary sentence for index generation.
            """
        )
    )
    (project / "specs/001-demo/plan.md").write_text("# Demo Plan\n")
    (project / "specs/001-demo/tasks.md").write_text("# Demo Tasks\n")
    (project / "specs/001-demo/diagrams/sequence.mmd").write_text(
        "sequenceDiagram\nA->>B: hi\n"
    )
