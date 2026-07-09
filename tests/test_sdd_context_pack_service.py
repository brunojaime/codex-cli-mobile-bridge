from __future__ import annotations

import os
import textwrap
from pathlib import Path

from backend.app.application.services.sdd_context_pack_service import (
    CONTEXT_PACK_PRESETS,
    SddContextPackService,
)
from backend.app.application.services.sdd_index_service import SddIndexService
from backend.app.application.services.sdd_standard_service import SddStandardService


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_STANDARDS = ROOT / "tests/fixtures/sdd_standards"


def test_new_feature_context_pack_regenerates_missing_indexes(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_context_project(project)

    pack = _service().build_pack(
        project,
        standard=_standard(),
        preset="new-feature",
        query="checkout",
    )

    assert pack.status == "ready"
    assert pack.index_status == "regenerated"
    assert "codex-bridge.yaml" in pack.required_files
    assert "standard_payload" in pack.required_files
    assert ".sdd/context-index.yaml" in pack.required_files
    assert "scan_every_full_spec_body" in pack.blocked_reads


def test_context_rules_project_override_limits_candidates(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_context_project(project, related_specs=6, related_diagrams=4, limits=(2, 1))

    pack = _service().build_pack(
        project,
        standard=_standard(),
        preset="new-feature",
        query="checkout",
    )

    assert pack.status == "ready"
    assert len(pack.related_specs) == 2
    assert len(pack.related_diagrams) == 1
    assert any(
        "related_specs=2 related_diagrams=1" in item for item in pack.routing_decisions
    )


def test_context_pack_uses_default_limits_and_deterministic_ranking(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_context_project(project, related_specs=7, related_diagrams=5)

    first = _service().build_pack(
        project,
        standard=_standard(),
        preset="new-feature",
        query="checkout",
    )
    second = _service().build_pack(
        project,
        standard=_standard(),
        preset="new-feature",
        query="checkout",
    )

    assert len(first.related_specs) == 5
    assert len(first.related_diagrams) == 3
    assert [item.path for item in first.related_specs] == [
        item.path for item in second.related_specs
    ]
    assert [item.path for item in first.related_specs] == sorted(
        item.path for item in first.related_specs
    )


def test_all_context_pack_presets_return_required_files(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_context_project(project)
    selected_spec = "specs/001-demo/spec.md"
    selected_diagram = "specs/001-demo/diagrams/sequence.mmd"
    selected_by_preset = {
        "modify-existing-feature": selected_spec,
        "implementation-from-spec": selected_spec,
        "diagram-update": selected_diagram,
        "bugfix": "backend/app/application/services/example.py",
    }

    for preset in CONTEXT_PACK_PRESETS:
        pack = _service().build_pack(
            project,
            standard=_standard(),
            preset=preset,
            selected_artifact=selected_by_preset.get(preset),
            query="checkout",
        )
        assert pack.status == "ready", preset
        assert pack.required_files, preset
        assert "codex-bridge.yaml" in pack.required_files
        assert "standard_payload" in pack.required_files


def test_stale_index_hard_fails_when_regeneration_disabled(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_context_project(project)
    standard = _standard()
    SddIndexService().ensure_indexes(project, standard=standard, auto_regenerate=True)
    spec_path = project / "specs/001-demo/spec.md"
    spec_path.write_text(spec_path.read_text() + "\nChanged.\n")
    os.utime(spec_path, None)

    pack = _service().build_pack(
        project,
        standard=standard,
        preset="new-feature",
        auto_regenerate_indexes=False,
    )

    assert pack.status == "blocked"
    assert pack.index_status == "stale"
    assert "fallback_to_all_specs_when_indexes_unavailable" in pack.blocked_reads


def test_failed_index_regeneration_returns_degraded_pack(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_context_project(project)
    (project / ".sdd").write_text("not a directory\n")

    pack = _service().build_pack(
        project,
        standard=_standard(),
        preset="new-feature",
        allow_degraded=True,
    )

    assert pack.status == "degraded"
    assert pack.mode == "degraded"
    assert pack.index_status == "failed"
    assert pack.related_specs == ()
    assert "scan_every_full_spec_body" in pack.blocked_reads


def test_context_pack_does_not_fallback_to_full_spec_body(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_context_project(project)
    marker = "SECRET_FULL_BODY_MARKER"
    (project / "specs/001-demo/spec.md").write_text(
        "# Demo Spec\n\n" + ("x" * 9000) + marker + "\n"
    )

    pack = _service().build_pack(
        project,
        standard=_standard(),
        preset="new-feature",
        query=marker,
    )

    spec_index = (project / ".sdd/spec-index.yaml").read_text()
    assert pack.status == "ready"
    assert marker not in spec_index
    assert all(marker not in item.reason for item in pack.related_specs)
    assert "scan_every_full_spec_body" in pack.blocked_reads


def test_context_pack_reuses_fresh_indexes(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_context_project(project)
    standard = _standard()
    SddIndexService().ensure_indexes(project, standard=standard, auto_regenerate=True)

    pack = _service().build_pack(
        project,
        standard=standard,
        preset="new-feature",
        auto_regenerate_indexes=False,
    )

    assert pack.status == "ready"
    assert pack.index_status == "fresh"


def _service() -> SddContextPackService:
    return SddContextPackService()


def _standard():
    return SddStandardService(standards_root=FIXTURE_STANDARDS).load("workbench-sdd/v1")


def _write_context_project(
    project: Path,
    *,
    related_specs: int = 1,
    related_diagrams: int = 1,
    limits: tuple[int, int] = (5, 3),
) -> None:
    (project / ".specify/memory").mkdir(parents=True)
    (project / "architecture").mkdir(parents=True)
    (project / "specs/001-demo/diagrams").mkdir(parents=True)
    (project / "architecture/overview.md").write_text("# Architecture Overview\n")
    (project / "domain").mkdir()
    (project / "data").mkdir()
    (project / "domain/glossary.md").write_text("# Domain Glossary\n")
    (project / "data/persistence-model.md").write_text("# Persistence Model\n")
    (project / "codex-bridge.yaml").write_text(
        textwrap.dedent(
            f"""\
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
              context_rules:
                domains:
                  workbench:
                    modules:
                      - backend/app/application/services
                    preferred_context:
                      - specs/001-demo/spec.md
                candidate_limits:
                  related_specs: {limits[0]}
                  related_diagrams: {limits[1]}
            """
        )
    )
    (project / ".specify/memory/constitution.md").write_text("# Constitution\n")
    (project / "architecture/components.mmd").write_text("flowchart LR\nA --> B\n")
    for index in range(related_specs):
        spec_id = f"{index + 1:03d}-demo" if index else "001-demo"
        spec_dir = project / "specs" / spec_id
        (spec_dir / "diagrams").mkdir(parents=True, exist_ok=True)
        (spec_dir / "spec.md").write_text(
            textwrap.dedent(
                f"""\
                ---
                status: draft
                ---

                # Checkout Spec {index + 1}

                checkout indexed summary {index + 1}
                """
            )
        )
        (spec_dir / "plan.md").write_text(f"# Checkout Plan {index + 1}\n")
        (spec_dir / "tasks.md").write_text(f"# Checkout Tasks {index + 1}\n")
        if index < related_diagrams:
            (spec_dir / "diagrams/sequence.mmd").write_text(
                "sequenceDiagram\nA->>B: checkout\n"
            )
