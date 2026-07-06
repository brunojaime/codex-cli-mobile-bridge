from __future__ import annotations

import os
import textwrap
from pathlib import Path

from backend.app.application.services.sdd_index_service import SddIndexService
from backend.app.application.services.sdd_llm_instruction_service import (
    SddLlmInstructionService,
)
from backend.app.application.services.sdd_standard_service import SddStandardService


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_STANDARDS = ROOT / "tests/fixtures/sdd_standards"


def test_llm_prompt_requires_standard_context_pack_and_blocked_reads(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_project(project, related_specs=2, related_diagrams=2)

    result = _service().build_prompt(
        project,
        preset="new-feature",
        query="checkout",
    )

    assert result.status == "ready"
    assert result.context_pack is not None
    assert result.context_pack.index_status == "regenerated"
    assert "standard_payload: workbench-sdd/v1" in result.prompt
    assert "standard_payload_source:" in result.prompt
    assert "Canonical in-repo artifact:" in result.prompt
    assert "context_pack_preset: new-feature" in result.prompt
    assert "index_status: regenerated" in result.prompt
    assert "- codex-bridge.yaml" in result.prompt
    assert "- .specify/memory/constitution.md" in result.prompt
    assert "- .sdd/context-index.yaml" in result.prompt
    assert "Related specs:" in result.prompt
    assert "Related diagrams:" in result.prompt
    assert "Routing decisions:" in result.prompt
    assert "Next actions:" in result.prompt
    assert "Do not read all specs" in result.prompt
    assert "Do not scan every full spec body as fallback." in result.prompt
    assert "scan_every_full_spec_body" in result.prompt


def test_llm_prompt_blocks_unknown_standard_before_context_routing(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_project(project, standard_id="workbench-sdd/v9")

    result = _service().build_prompt(project, preset="new-feature")

    assert result.status == "blocked"
    assert result.context_pack is None
    assert result.error is not None
    assert "Unsupported SDD standard version 'workbench-sdd/v9'" in result.error
    assert "Workbench SDD action blocked." in result.prompt
    assert "Do not proceed with implementation or broad file reads" in result.prompt


def test_llm_prompt_surfaces_invalid_preset_as_blocked_workflow(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_project(project)

    result = _service().build_prompt(project, preset="unsupported-workflow")

    assert result.status == "blocked"
    assert result.context_pack is not None
    assert result.context_pack.index_status == "not_checked"
    assert "Unsupported context pack preset: unsupported-workflow" in result.prompt
    assert "fallback_to_all_specs_when_indexes_unavailable" in result.prompt


def test_llm_prompt_surfaces_stale_index_hard_failure_without_broad_fallback(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_project(project)
    standard = _standard()
    SddIndexService().ensure_indexes(project, standard=standard, auto_regenerate=True)
    spec_path = project / "specs/001-demo/spec.md"
    spec_path.write_text(spec_path.read_text() + "\nChanged after index.\n")
    os.utime(spec_path, None)

    result = _service().build_prompt(
        project,
        preset="new-feature",
        auto_regenerate_indexes=False,
    )

    assert result.status == "blocked"
    assert result.context_pack is not None
    assert result.context_pack.index_status == "stale"
    assert "index_status: stale" in result.prompt
    assert "context_pack_mode: hard_failure" in result.prompt
    assert "auto-regeneration is disabled" in result.prompt
    assert "fallback_to_all_specs_when_indexes_unavailable" in result.prompt
    assert "Do not read all specs" in result.prompt


def test_llm_prompt_surfaces_degraded_index_mode(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(project)
    (project / ".sdd").write_text("not a directory\n")

    result = _service().build_prompt(
        project,
        preset="new-feature",
        allow_degraded=True,
    )

    assert result.status == "degraded"
    assert result.context_pack is not None
    assert result.context_pack.related_specs == ()
    assert result.context_pack.related_diagrams == ()
    assert "context_pack_status: degraded" in result.prompt
    assert "context_pack_mode: degraded" in result.prompt
    assert "index_status: failed" in result.prompt
    assert "Index regeneration failed" in result.prompt
    assert "Regenerate .sdd indexes before related-candidate routing." in result.prompt
    assert "Do not scan every full spec body as fallback." in result.prompt


def test_llm_prompt_preserves_project_context_rules_and_protected_baselines(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_project(project, protected_baselines=("architecture/components.mmd",))

    result = _service().build_prompt(
        project,
        preset="architecture-change",
        query="components",
    )

    assert result.status == "ready"
    assert "Baseline protection:" in result.prompt
    assert "- architecture/components.mmd" in result.prompt
    assert "Protect baseline architecture, domain, and data artifacts." in result.prompt
    assert "Do not edit protected baseline diagrams" in result.prompt
    assert "Project-owned rules:" in result.prompt
    assert "sdd.context_rules overrides" in result.prompt
    assert "Workbench default -> project profile -> project overrides" in result.prompt


def test_llm_prompt_blocks_invalid_context_rules_override(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(project, invalid_context_rules=True)

    result = _service().build_prompt(project, preset="new-feature")

    assert result.status == "blocked"
    assert result.context_pack is not None
    assert "Unsupported sdd.context_rules key(s): disable_safety" in result.prompt
    assert "Fix the blocking condition before building a context pack." in result.prompt
    assert "Do not read all specs" in result.prompt


def test_llm_prompt_does_not_expose_full_spec_body_fallback(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(project)
    marker = "SECRET_FULL_BODY_MARKER"
    (project / "specs/001-demo/spec.md").write_text(
        "# Demo Spec\n\n" + ("x" * 9000) + marker + "\n",
        encoding="utf-8",
    )

    result = _service().build_prompt(
        project,
        preset="new-feature",
        query=marker,
    )

    spec_index = (project / ".sdd/spec-index.yaml").read_text(encoding="utf-8")
    assert result.status == "ready"
    assert marker not in result.prompt
    assert marker not in spec_index
    assert "scan_every_full_spec_body" in result.prompt
    assert "Do not scan every full spec body as fallback." in result.prompt


def _service() -> SddLlmInstructionService:
    return SddLlmInstructionService(
        standard_service=SddStandardService(standards_root=FIXTURE_STANDARDS),
    )


def _standard():
    return SddStandardService(standards_root=FIXTURE_STANDARDS).load("workbench-sdd/v1")


def _write_project(
    project: Path,
    *,
    standard_id: str = "workbench-sdd/v1",
    related_specs: int = 1,
    related_diagrams: int = 1,
    protected_baselines: tuple[str, ...] = ("architecture/components.mmd",),
    invalid_context_rules: bool = False,
) -> None:
    (project / ".specify/memory").mkdir(parents=True)
    (project / "architecture").mkdir(parents=True)
    (project / "domain").mkdir()
    (project / "data").mkdir()
    (project / "specs/001-demo/diagrams").mkdir(parents=True)
    (project / "architecture/overview.md").write_text(
        "# Architecture Overview\n",
        encoding="utf-8",
    )
    (project / "architecture/components.mmd").write_text(
        "flowchart LR\nA --> B\n",
        encoding="utf-8",
    )
    (project / "domain/glossary.md").write_text(
        "# Domain Glossary\n",
        encoding="utf-8",
    )
    (project / "data/persistence-model.md").write_text(
        "# Persistence Model\n",
        encoding="utf-8",
    )
    (project / ".specify/memory/constitution.md").write_text(
        "# Constitution\n",
        encoding="utf-8",
    )
    protected_lines = (
        "\n".join(f"    - {path}" for path in protected_baselines)
        or "    - architecture/components.mmd"
    )
    extra_context_rules = "    disable_safety: true\n" if invalid_context_rules else ""
    (project / "codex-bridge.yaml").write_text(
        textwrap.dedent(
            f"""\
            kind: codex.bridge.project
            version: 1
            sdd:
              required: true
              standard: {standard_id}
              project_type: bridge_backend
              constitution: .specify/memory/constitution.md
              specs: specs
              architecture: architecture
              domain_root: domain
              data_root: data
              generated_index_root: .sdd
              protected_baseline:
            {protected_lines}
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
            {extra_context_rules}\
            """
        ),
        encoding="utf-8",
    )
    for index in range(related_specs):
        spec_id = "001-demo" if index == 0 else f"{index + 1:03d}-demo"
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
            ),
            encoding="utf-8",
        )
        (spec_dir / "plan.md").write_text(
            f"# Checkout Plan {index + 1}\n",
            encoding="utf-8",
        )
        (spec_dir / "tasks.md").write_text(
            f"# Checkout Tasks {index + 1}\n",
            encoding="utf-8",
        )
        (spec_dir / "traceability.yaml").write_text(
            f"spec_id: {spec_id}\n",
            encoding="utf-8",
        )
        if index < related_diagrams:
            (spec_dir / "diagrams/sequence.mmd").write_text(
                "sequenceDiagram\nA->>B: checkout\n",
                encoding="utf-8",
            )
            (spec_dir / "diagrams/sequence.yaml").write_text(
                textwrap.dedent(
                    """\
                    diagram_id: sequence
                    diagram_type: sequence
                    scope: feature
                    status: draft
                    owner: project
                    source: sequence.mmd
                    """
                ),
                encoding="utf-8",
            )
