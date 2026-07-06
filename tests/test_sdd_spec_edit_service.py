from __future__ import annotations

from pathlib import Path

from backend.app.application.services.sdd_spec_edit_service import SddSpecEditService
from backend.app.application.services.sdd_spec_target_service import (
    SpecIntakeMediaItemInput,
    SpecIntakeValidationInput,
    SpecTargetInput,
)


def test_existing_spec_edit_dry_run_targets_selected_artifact_without_writes(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path, spec_id="001-existing")
    service = SddSpecEditService(projects_root=tmp_path / "projects")

    result = service.dry_run_existing_spec_edit(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(
                mode="existing_spec",
                spec_id="001-existing",
                artifact="spec",
            ),
            intake_items=(SpecIntakeMediaItemInput(kind="text", text="Edit spec"),),
        )
    )

    assert result.status == "dry-run"
    assert result.intended_artifact_updates == (
        "specs/001-existing/spec.md",
        "specs/001-existing/metadata.yaml",
    )
    assert (project / "specs/001-existing/spec.md").read_text() == "# Existing\n"


def test_existing_spec_edit_dry_run_covers_spec_plan_tasks_and_diagram_targets(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path, spec_id="001-existing", include_diagram=True)
    service = SddSpecEditService(projects_root=tmp_path / "projects")

    expected = {
        "spec": (
            "specs/001-existing/spec.md",
            "specs/001-existing/metadata.yaml",
        ),
        "plan": (
            "specs/001-existing/plan.md",
            "specs/001-existing/metadata.yaml",
        ),
        "tasks": (
            "specs/001-existing/tasks.md",
            "specs/001-existing/metadata.yaml",
        ),
        "diagram": (
            "specs/001-existing/diagrams/sequence.mmd",
            "specs/001-existing/metadata.yaml",
        ),
    }

    for artifact, intended_updates in expected.items():
        result = service.dry_run_existing_spec_edit(
            SpecIntakeValidationInput(
                workspace_path=str(project),
                spec_target=SpecTargetInput(
                    mode="existing_spec",
                    spec_id="001-existing",
                    artifact=artifact,
                ),
                intake_items=(
                    SpecIntakeMediaItemInput(kind="text", text=f"Edit {artifact}"),
                ),
            )
        )

        assert result.status == "dry-run"
        assert result.selected_artifact == artifact
        assert result.intended_artifact_updates == intended_updates
        assert result.conflicts == ()


def test_existing_spec_edit_dry_run_blocks_invalid_targets_and_artifacts(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path, spec_id="001-existing", include_plan=False)
    service = SddSpecEditService(projects_root=tmp_path / "projects")

    traversal = service.dry_run_existing_spec_edit(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(mode="existing_spec", spec_id="../outside"),
            intake_items=(SpecIntakeMediaItemInput(kind="text", text="Edit"),),
        )
    )
    unsupported = service.dry_run_existing_spec_edit(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(
                mode="existing_spec",
                spec_id="001-existing",
                artifact="adr",
            ),
            intake_items=(SpecIntakeMediaItemInput(kind="text", text="Edit"),),
        )
    )
    missing_artifact = service.dry_run_existing_spec_edit(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(
                mode="existing_spec",
                spec_id="001-existing",
                artifact="plan",
            ),
            intake_items=(SpecIntakeMediaItemInput(kind="text", text="Edit"),),
        )
    )

    assert [error.code for error in traversal.validation_errors] == ["invalid_spec_id"]
    assert [error.code for error in unsupported.validation_errors] == [
        "unsupported_artifact_target"
    ]
    assert missing_artifact.conflicts == ("specs/001-existing/plan.md",)
    assert not (project / "specs/001-existing/plan.md").exists()


def test_existing_spec_edit_apply_blocks_codex_required_content_without_writes(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path, spec_id="001-existing")
    service = SddSpecEditService(projects_root=tmp_path / "projects")
    request = SpecIntakeValidationInput(
        workspace_path=str(project),
        spec_target=SpecTargetInput(
            mode="existing_spec",
            spec_id="001-existing",
            artifact="tasks",
        ),
        intake_items=(SpecIntakeMediaItemInput(kind="text", text="Update tasks"),),
    )

    before = (project / "specs/001-existing/tasks.md").read_text()
    result = service.apply_existing_spec_edit(request)

    assert result.status == "blocked"
    assert result.dry_run.status == "dry-run"
    assert result.existing == (
        "specs/001-existing/tasks.md",
        "specs/001-existing/metadata.yaml",
    )
    assert result.created == ()
    assert result.updated == ()
    assert result.blocked == (
        "existing-spec edit apply requires Codex CLI synthesis for content changes",
    )
    assert result.next_actions == (
        "Run the Codex CLI orchestration phase before applying existing-spec edits.",
    )
    assert (project / "specs/001-existing/tasks.md").read_text() == before


def test_existing_spec_edit_apply_preserves_dry_run_blockers_and_no_writes(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path, spec_id="001-existing", include_plan=False)
    service = SddSpecEditService(projects_root=tmp_path / "projects")

    result = service.apply_existing_spec_edit(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(
                mode="existing_spec",
                spec_id="001-existing",
                artifact="plan",
            ),
            intake_items=(SpecIntakeMediaItemInput(kind="text", text="Edit"),),
        )
    )

    assert result.status == "blocked"
    assert result.dry_run.status == "blocked"
    assert result.conflicts == ("specs/001-existing/plan.md",)
    assert result.blocked == ("conflict: specs/001-existing/plan.md",)
    assert result.next_actions == ("Fix dry-run blockers before applying spec edit.",)
    assert not (project / "specs/001-existing/plan.md").exists()


def _write_project(
    tmp_path: Path,
    *,
    spec_id: str,
    include_plan: bool = True,
    include_diagram: bool = False,
) -> Path:
    project = tmp_path / "projects/demo"
    spec_root = project / "specs" / spec_id
    spec_root.mkdir(parents=True)
    (project / "codex-bridge.yaml").write_text("sdd:\n  standard: workbench-sdd/v1\n")
    (spec_root / "spec.md").write_text("# Existing\n")
    if include_plan:
        (spec_root / "plan.md").write_text("# Plan\n")
    (spec_root / "tasks.md").write_text("- [ ] Existing\n")
    if include_diagram:
        (spec_root / "diagrams").mkdir()
        (spec_root / "diagrams/sequence.mmd").write_text(
            "sequenceDiagram\nA->>B: edit\n"
        )
    return project
