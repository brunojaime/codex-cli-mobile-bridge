from __future__ import annotations

import textwrap
from pathlib import Path

from backend.app.application.services.sdd_metadata_refresh_service import (
    SddMetadataRefreshService,
)
from backend.app.application.services.sdd_project_service import SddProjectService


def test_metadata_refresh_preview_generates_title_description_and_digests_read_only(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    service = SddMetadataRefreshService(projects_root=tmp_path / "projects")

    result = service.preview_spec_metadata(project, "001-demo")

    assert result.status == "preview"
    assert result.mode == "preview"
    assert result.title == "Checkout Favorites"
    assert result.description == "Users can save favorite products from checkout."
    assert result.task_summary.to_payload() == {
        "total": 3,
        "completed": 1,
        "pending": 2,
    }
    assert result.diagram_summary.total == 1
    assert result.diagram_summary.diagrams[0]["diagram_type"] == "sequence"
    assert result.source_digests.keys() >= {
        "spec.md",
        "plan.md",
        "tasks.md",
        "traceability.yaml",
        "diagrams/sequence.mmd",
        "diagrams/sequence.yaml",
    }
    assert result.would_write is True
    assert result.written is False
    assert not (project / "specs/001-demo/metadata.yaml").exists()


def test_metadata_refresh_apply_writes_metadata_and_is_idempotent(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    service = SddMetadataRefreshService(projects_root=tmp_path / "projects")

    first = service.refresh_spec_metadata(project, "001-demo")
    first_text = (project / "specs/001-demo/metadata.yaml").read_text()
    second = service.refresh_spec_metadata(project, "001-demo")

    assert first.status == "updated"
    assert first.written is True
    assert "source_digests" in first.changed_fields
    assert "tasks" in first.changed_fields
    assert "diagrams" in first.changed_fields
    assert second.status == "unchanged"
    assert second.written is False
    assert (project / "specs/001-demo/metadata.yaml").read_text() == first_text


def test_metadata_refresh_preserves_pinned_title_and_description(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path, metadata=True, pinned=True)
    service = SddMetadataRefreshService(projects_root=tmp_path / "projects")

    result = service.refresh_spec_metadata(project, "001-demo")
    metadata_text = (project / "specs/001-demo/metadata.yaml").read_text()

    assert result.title == "Pinned Title"
    assert result.description == "Pinned description."
    assert result.proposed_title == "Checkout Favorites"
    assert (
        result.proposed_description == "Users can save favorite products from checkout."
    )
    assert result.pinned_fields == ("title", "description")
    assert result.skipped_fields == ("title", "description")
    assert "title: Pinned Title" in metadata_text
    assert "description: Pinned description." in metadata_text
    assert "user_pinned_title: true" in metadata_text
    assert "user_pinned_description: true" in metadata_text


def test_metadata_refresh_reports_stale_paths_and_project_reader_sees_fresh_after_apply(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path, metadata=True)
    service = SddMetadataRefreshService(projects_root=tmp_path / "projects")
    tasks_path = project / "specs/001-demo/tasks.md"
    tasks_path.write_text("- [x] T001 Done\n- [x] T002 Done\n")

    preview = service.preview_spec_metadata(project, "001-demo")
    refreshed = service.refresh_spec_metadata(project, "001-demo")
    metadata = SddProjectService(
        projects_root=str(tmp_path / "projects")
    ).get_spec_metadata(
        str(project),
        "001-demo",
    )

    assert preview.stale_paths == ("tasks.md",)
    assert refreshed.task_summary.to_payload() == {
        "total": 2,
        "completed": 2,
        "pending": 0,
    }
    assert metadata.metadata_status == "present"
    assert metadata.metadata_stale_paths == ()


def _write_project(
    tmp_path: Path,
    *,
    metadata: bool = False,
    pinned: bool = False,
) -> Path:
    project = tmp_path / "projects/demo"
    spec_root = project / "specs/001-demo"
    (spec_root / "diagrams").mkdir(parents=True)
    (project / "codex-bridge.yaml").write_text("sdd:\n  standard: workbench-sdd/v1\n")
    (spec_root / "spec.md").write_text(
        textwrap.dedent(
            """\
            ---
            id: 001-demo
            ---

            # Checkout Favorites

            Users can save favorite products from checkout.
            """
        )
    )
    (spec_root / "plan.md").write_text("# Plan\n")
    (spec_root / "tasks.md").write_text(
        "- [x] T001 Done\n- [ ] T002 Pending\n- [ ] T003 Pending\n"
    )
    (spec_root / "traceability.yaml").write_text("requirements: {}\n")
    (spec_root / "diagrams/sequence.mmd").write_text(
        "sequenceDiagram\nUser->>System: save favorite\n"
    )
    (spec_root / "diagrams/sequence.yaml").write_text(
        textwrap.dedent(
            """\
            diagram_id: sequence
            diagram_type: sequence
            scope: feature
            status: draft
            owner: project
            source: sequence.mmd
            """
        )
    )
    if metadata:
        service = SddMetadataRefreshService(projects_root=tmp_path / "projects")
        service.refresh_spec_metadata(project, "001-demo")
        if pinned:
            metadata_path = spec_root / "metadata.yaml"
            metadata_path.write_text(
                metadata_path.read_text()
                .replace("title: Checkout Favorites", "title: Pinned Title")
                .replace(
                    "description: Users can save favorite products from checkout.",
                    "description: Pinned description.",
                )
                .replace("user_pinned_title: false", "user_pinned_title: true")
                .replace(
                    "user_pinned_description: false",
                    "user_pinned_description: true",
                )
            )
    return project
