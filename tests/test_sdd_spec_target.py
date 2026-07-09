from __future__ import annotations

from pathlib import Path

from backend.app.api.schemas import (
    SpecIntakeValidationRequest,
    SpecIntakeValidationResponse,
)
from backend.app.application.services.sdd_spec_target_service import (
    AUDIO_MAX_BYTES,
    IMAGE_MAX_BYTES,
    IMAGE_SEQUENCE_MAX_FRAMES,
    SCREENSHOT_BATCH_MAX_IMAGES,
    TEXT_MAX_BYTES,
    SddSpecTargetValidationService,
    SpecIntakeMediaItemInput,
    SpecIntakeValidationInput,
    SpecTargetInput,
)


def test_spec_target_schemas_accept_snake_and_camel_aliases() -> None:
    request = SpecIntakeValidationRequest(
        workspacePath="/tmp/project",
        specTarget={
            "mode": "existing_spec",
            "specId": "001-demo",
            "artifact": "diagram",
        },
        intakeItems=[
            {
                "kind": "crop",
                "mimeType": "image/png",
                "byteSize": 1024,
                "sourceRef": "media/original.png",
                "region": {"x": 1, "y": 2, "width": 3, "height": 4},
            }
        ],
        titleSeed="Demo",
    )

    assert request.spec_target.spec_id == "001-demo"
    assert request.spec_target.artifact == "diagram"
    assert request.intake_items[0].mime_type == "image/png"
    assert request.intake_items[0].byte_size == 1024
    assert request.intake_items[0].source_ref == "media/original.png"


def test_valid_none_target_keeps_feedback_non_scm(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    service = _service(tmp_path)

    result = service.validate(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(mode="none"),
            intake_items=(_text_item("ordinary feedback"),),
        )
    )

    assert result.ok is True
    assert result.status == "valid"
    assert result.mode == "none"
    assert result.spec_id is None
    assert result.artifact == "auto"
    assert result.spec_root is None
    assert result.errors == ()


def test_valid_new_spec_allows_requested_slug_without_writes(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    service = _service(tmp_path)

    result = service.validate(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(
                mode="new_spec",
                spec_id="favorites-products",
            ),
            title_seed="Product favorites",
            intake_items=(_text_item("Add product favorites"),),
        )
    )

    assert result.ok is True
    assert result.spec_root == str(project / "specs/favorites-products")
    assert not (project / "specs/favorites-products").exists()


def test_valid_existing_spec_resolves_alias_and_artifact(tmp_path: Path) -> None:
    project = _write_project(tmp_path, spec_id="001-existing")
    service = SddSpecTargetValidationService(
        projects_root=tmp_path / "projects",
        workspace_aliases={"sat": str(project)},
    )

    result = service.validate(
        SpecIntakeValidationInput(
            workspace_path="sat",
            spec_target=SpecTargetInput(
                mode="existing_spec",
                spec_id="001-existing",
                artifact="tasks",
            ),
            intake_items=(_image_item(),),
        )
    )

    assert result.ok is True
    assert result.workspace_path == str(project)
    assert result.spec_root == str(project / "specs/001-existing")
    assert result.artifact == "tasks"


def test_invalid_target_combinations_are_deterministic(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    service = _service(tmp_path)
    request = SpecIntakeValidationInput(
        workspace_path=str(project),
        spec_target=SpecTargetInput(
            mode="none",
            spec_id="001-demo",
            artifact="tasks",
        ),
        intake_items=(),
    )

    first = service.validate(request)
    second = service.validate(request)

    assert first.to_payload() == second.to_payload()
    assert _codes(first) == [
        "invalid_target_combination",
        "invalid_target_combination",
        "missing_intake",
    ]
    response = SpecIntakeValidationResponse(**first.to_payload())
    assert response.status == "blocked"
    assert response.errors[0].field == "spec_target.spec_id"


def test_new_spec_rejects_artifact_missing_title_source_and_slug_collision(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path, spec_id="001-existing")
    service = _service(tmp_path)

    result = service.validate(
        SpecIntakeValidationInput(
            workspace_path=str(tmp_path / "projects/demo"),
            spec_target=SpecTargetInput(
                mode="new_spec",
                spec_id="001-existing",
                artifact="plan",
            ),
            intake_items=(SpecIntakeMediaItemInput(kind="audio", transcript=""),),
        )
    )

    assert _codes(result) == [
        "invalid_target_combination",
        "missing_title_source",
        "spec_slug_collision",
        "unsupported_audio_format",
        "missing_media_size",
        "missing_audio_duration",
    ]
    assert not (tmp_path / "projects/demo/specs/001-existing/intake").exists()


def test_existing_spec_rejects_missing_invalid_and_unknown_spec_id(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    service = _service(tmp_path)

    missing = service.validate(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(mode="existing_spec"),
            intake_items=(_text_item("edit spec"),),
        )
    )
    invalid = service.validate(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(
                mode="existing_spec",
                spec_id="../outside",
            ),
            intake_items=(_text_item("edit spec"),),
        )
    )
    unknown = service.validate(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(
                mode="existing_spec",
                spec_id="999-missing",
            ),
            intake_items=(_text_item("edit spec"),),
        )
    )

    assert _codes(missing) == ["missing_spec_id"]
    assert _codes(invalid) == ["invalid_spec_id"]
    assert invalid.spec_root is None
    assert _codes(unknown) == ["target_spec_not_found"]


def test_rejects_bridge_workbench_target_conflict(tmp_path: Path) -> None:
    project = _write_project(tmp_path, spec_id="001-existing")
    service = _service(tmp_path)

    result = service.validate(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(
                mode="existing_spec",
                spec_id="001-existing",
                artifact="spec",
            ),
            workbench_spec_target=SpecTargetInput(
                mode="existing_spec",
                spec_id="001-existing",
                artifact="spec",
            ),
            bridge_spec_target=SpecTargetInput(
                mode="existing_spec",
                spec_id="001-existing",
                artifact="tasks",
            ),
            intake_items=(_text_item("edit spec"),),
        )
    )

    assert _codes(result) == ["target_conflict", "target_conflict"]
    assert result.to_payload()["next_actions"] == [
        "Fix validation errors before creating jobs or writing files."
    ]


def test_rejects_unsafe_workspace_paths(tmp_path: Path) -> None:
    service = _service(tmp_path)

    result = service.validate(
        SpecIntakeValidationInput(
            workspace_path=str(tmp_path / "outside"),
            spec_target=SpecTargetInput(mode="none"),
            intake_items=(_text_item("feedback"),),
        )
    )

    assert _codes(result) == ["unsafe_workspace_path"]
    assert result.workspace_path is None


def test_rejects_media_size_and_count_limit_violations(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    service = _service(tmp_path)

    result = service.validate(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(mode="none"),
            intake_items=(
                SpecIntakeMediaItemInput(kind="text", byte_size=TEXT_MAX_BYTES + 1),
                SpecIntakeMediaItemInput(
                    kind="audio",
                    mime_type="audio/wav",
                    byte_size=AUDIO_MAX_BYTES + 1,
                    duration_ms=600_001,
                ),
                SpecIntakeMediaItemInput(
                    kind="image",
                    mime_type="image/png",
                    byte_size=IMAGE_MAX_BYTES + 1,
                ),
                SpecIntakeMediaItemInput(
                    kind="screenshot_batch",
                    image_count=SCREENSHOT_BATCH_MAX_IMAGES + 1,
                ),
                SpecIntakeMediaItemInput(
                    kind="image_sequence",
                    frame_count=IMAGE_SEQUENCE_MAX_FRAMES + 1,
                    audio_track_count=2,
                ),
            ),
        )
    )

    assert _codes(result) == [
        "media_text_too_large",
        "media_audio_too_large",
        "media_audio_duration_too_large",
        "media_image_too_large",
        "media_image_count_too_large",
        "media_frame_count_too_large",
        "media_audio_track_count_too_large",
    ]


def test_rejects_media_formats_and_missing_crop_metadata(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    service = _service(tmp_path)

    result = service.validate(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(mode="none"),
            intake_items=(
                SpecIntakeMediaItemInput(
                    kind="audio",
                    mime_type="audio/ogg",
                    byte_size=100,
                    duration_ms=1000,
                ),
                SpecIntakeMediaItemInput(
                    kind="image",
                    mime_type="image/gif",
                    byte_size=100,
                ),
                SpecIntakeMediaItemInput(
                    kind="crop",
                    mime_type="image/png",
                    byte_size=100,
                ),
                SpecIntakeMediaItemInput(
                    kind="marked_region",
                    filename="marked.webp",
                    byte_size=100,
                    source_ref="media/original.webp",
                    region={"x": 0, "y": 0, "width": 0, "height": 10},
                ),
            ),
        )
    )

    assert _codes(result) == [
        "unsupported_audio_format",
        "unsupported_image_format",
        "missing_source_ref",
        "missing_region",
        "invalid_region",
        "missing_media_reference",
    ]


def test_rejects_unsupported_artifact_and_media_kind(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    service = _service(tmp_path)

    result = service.validate(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(
                mode="existing_spec", spec_id="x", artifact="adr"
            ),
            intake_items=(SpecIntakeMediaItemInput(kind="video"),),
        )
    )

    assert _codes(result) == [
        "unsupported_artifact_target",
        "target_spec_not_found",
        "unsupported_media_kind",
    ]


def _service(tmp_path: Path) -> SddSpecTargetValidationService:
    return SddSpecTargetValidationService(projects_root=tmp_path / "projects")


def _write_project(tmp_path: Path, *, spec_id: str | None = None) -> Path:
    project = tmp_path / "projects/demo"
    project.mkdir(parents=True)
    (project / "codex-bridge.yaml").write_text("sdd:\n  standard: workbench-sdd/v1\n")
    if spec_id is not None:
        spec_root = project / "specs" / spec_id
        spec_root.mkdir(parents=True)
        (spec_root / "spec.md").write_text("# Existing\n")
    return project


def _text_item(text: str) -> SpecIntakeMediaItemInput:
    return SpecIntakeMediaItemInput(kind="text", text=text)


def _image_item() -> SpecIntakeMediaItemInput:
    return SpecIntakeMediaItemInput(
        kind="image",
        mime_type="image/png",
        byte_size=1024,
    )


def _codes(result: object) -> list[str]:
    return [error.code for error in result.errors]
