from __future__ import annotations

import textwrap
from pathlib import Path

from backend.app.application.services.sdd_spec_creation_service import (
    SddSpecCreationService,
)
from backend.app.application.services.sdd_spec_edit_service import SddSpecEditService
from backend.app.application.services.sdd_spec_target_service import (
    SpecIntakeMediaItemInput,
    SpecIntakeValidationInput,
    SpecTargetInput,
)


def test_new_spec_dry_run_plans_target_files_metadata_and_intake(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    service = SddSpecCreationService(projects_root=tmp_path / "projects")

    result = service.dry_run_new_spec(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(mode="new_spec", spec_id="favorites"),
            title_seed="Product favorites",
            intake_items=(
                SpecIntakeMediaItemInput(
                    kind="text",
                    text="Users can save products as favorites.",
                ),
            ),
        ),
        job_id="new-1",
    )

    assert result.status == "dry-run"
    assert result.spec_id == "favorites"
    assert result.spec_root == "specs/favorites"
    assert result.metadata_proposal is not None
    assert result.metadata_proposal.title == "Product Favorites"
    assert (
        result.metadata_proposal.description == "Users can save products as favorites."
    )
    assert result.target_files == (
        "specs/favorites/metadata.yaml",
        "specs/favorites/spec.md",
        "specs/favorites/plan.md",
        "specs/favorites/tasks.md",
        "specs/favorites/traceability.yaml",
        "specs/favorites/intake/",
        "specs/favorites/diagrams/",
    )
    assert "refresh .sdd indexes after apply" in result.metadata_refresh_plan
    assert result.intake_plan is not None
    assert result.intake_plan.status == "dry-run"
    assert not (project / "specs/favorites").exists()


def test_new_spec_dry_run_generates_deterministic_title_and_collision_slug(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    (project / "specs/favorites").mkdir(parents=True)
    service = SddSpecCreationService(projects_root=tmp_path / "projects")
    request = SpecIntakeValidationInput(
        workspace_path=str(project),
        spec_target=SpecTargetInput(mode="new_spec"),
        intake_items=(
            SpecIntakeMediaItemInput(
                kind="text",
                text="favorites",
            ),
        ),
    )

    first = service.dry_run_new_spec(request)
    second = service.dry_run_new_spec(request)

    assert first.to_payload() == second.to_payload()
    assert first.status == "dry-run"
    assert first.spec_id == "favorites-2"
    assert first.metadata_proposal is not None
    assert first.metadata_proposal.generated_title is True


def test_new_spec_dry_run_blocks_requested_slug_collision(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    (project / "specs/favorites").mkdir(parents=True)
    service = SddSpecCreationService(projects_root=tmp_path / "projects")

    result = service.dry_run_new_spec(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(mode="new_spec", spec_id="favorites"),
            title_seed="Favorites",
            intake_items=(SpecIntakeMediaItemInput(kind="text", text="Favorites"),),
        )
    )

    assert result.status == "blocked"
    assert [error.code for error in result.validation_errors] == ["spec_slug_collision"]
    assert not (project / "specs/favorites/intake").exists()


def test_existing_spec_edit_dry_run_plans_selected_artifact_and_pinned_metadata(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path, spec_id="001-existing", metadata=True)
    service = SddSpecEditService(projects_root=tmp_path / "projects")

    result = service.dry_run_existing_spec_edit(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(
                mode="existing_spec",
                spec_id="001-existing",
                artifact="tasks",
            ),
            intake_items=(
                SpecIntakeMediaItemInput(
                    kind="text",
                    text="Update task list for favorites implementation.",
                ),
            ),
        )
    )

    assert result.status == "dry-run"
    assert result.intended_artifact_updates == (
        "specs/001-existing/tasks.md",
        "specs/001-existing/metadata.yaml",
    )
    assert result.metadata_proposal is not None
    assert result.metadata_proposal.title == "Pinned Existing Title"
    assert result.metadata_proposal.preserve_pinned_title is True
    assert result.metadata_proposal.preserve_pinned_description is True
    assert "preserve pinned title/description fields" in result.metadata_refresh_plan
    assert (project / "specs/001-existing/tasks.md").read_text() == "- [ ] Existing\n"


def test_existing_spec_edit_dry_run_blocks_invalid_target_and_missing_artifact(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path, spec_id="001-existing", include_plan=False)
    service = SddSpecEditService(projects_root=tmp_path / "projects")

    invalid = service.dry_run_existing_spec_edit(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(
                mode="existing_spec",
                spec_id="999-missing",
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

    assert invalid.status == "blocked"
    assert [error.code for error in invalid.validation_errors] == [
        "target_spec_not_found"
    ]
    assert missing_artifact.status == "blocked"
    assert missing_artifact.conflicts == ("specs/001-existing/plan.md",)
    assert not (project / "specs/999-missing").exists()


def _write_project(
    tmp_path: Path,
    *,
    spec_id: str | None = None,
    metadata: bool = False,
    include_plan: bool = True,
) -> Path:
    project = tmp_path / "projects/demo"
    project.mkdir(parents=True)
    (project / "codex-bridge.yaml").write_text("sdd:\n  standard: workbench-sdd/v1\n")
    if spec_id is None:
        return project
    spec_root = project / "specs" / spec_id
    (spec_root / "diagrams").mkdir(parents=True)
    (spec_root / "spec.md").write_text("# Existing Spec\n\nCurrent description.\n")
    if include_plan:
        (spec_root / "plan.md").write_text("# Plan\n")
    (spec_root / "tasks.md").write_text("- [ ] Existing\n")
    (spec_root / "traceability.yaml").write_text("requirements: {}\n")
    (spec_root / "diagrams/sequence.mmd").write_text("sequenceDiagram\nA->>B: hi\n")
    if metadata:
        (spec_root / "metadata.yaml").write_text(
            textwrap.dedent(
                """\
                title: Pinned Existing Title
                description: Pinned existing description.
                status: draft
                generated:
                  title: false
                  description: false
                  user_pinned_title: true
                  user_pinned_description: true
                tasks:
                  total: 1
                  completed: 0
                  pending: 1
                """
            )
        )
    return project
