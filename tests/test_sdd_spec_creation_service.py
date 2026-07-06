from __future__ import annotations

from pathlib import Path

from backend.app.application.services.sdd_spec_creation_service import (
    SddSpecCreationService,
)
from backend.app.application.services.sdd_spec_target_service import (
    SpecIntakeMediaItemInput,
    SpecIntakeValidationInput,
    SpecTargetInput,
)


def test_new_spec_creation_dry_run_text_only_and_no_writes(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    service = SddSpecCreationService(projects_root=tmp_path / "projects")

    result = service.dry_run_new_spec(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(mode="new_spec", spec_id="favorites"),
            title_seed="Favorites",
            intake_items=(SpecIntakeMediaItemInput(kind="text", text="Favorites"),),
        )
    )

    assert result.status == "dry-run"
    assert "specs/favorites/spec.md" in result.target_files
    assert result.intake_plan is not None
    assert result.intake_plan.status == "dry-run"
    assert not (project / "specs/favorites").exists()


def test_new_spec_creation_dry_run_blocks_collision_and_missing_intake(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    (project / "specs/favorites").mkdir(parents=True)
    service = SddSpecCreationService(projects_root=tmp_path / "projects")

    collision = service.dry_run_new_spec(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(mode="new_spec", spec_id="favorites"),
            title_seed="Favorites",
            intake_items=(SpecIntakeMediaItemInput(kind="text", text="Favorites"),),
        )
    )
    missing_intake = service.dry_run_new_spec(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(mode="new_spec", spec_id="empty"),
            title_seed="Empty",
            intake_items=(),
        )
    )

    assert [error.code for error in collision.validation_errors] == [
        "spec_slug_collision"
    ]
    assert [error.code for error in missing_intake.validation_errors] == [
        "missing_intake"
    ]
    assert not (project / "specs/empty").exists()


def _write_project(tmp_path: Path) -> Path:
    project = tmp_path / "projects/demo"
    project.mkdir(parents=True)
    (project / "codex-bridge.yaml").write_text("sdd:\n  standard: workbench-sdd/v1\n")
    return project
