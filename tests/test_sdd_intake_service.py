from __future__ import annotations

import json
from pathlib import Path

from backend.app.api.schemas import SddIntakeDryRunResponse, SddIntakeRequest
from backend.app.application.services.sdd_intake_service import SddIntakeService
from backend.app.application.services.sdd_spec_target_service import (
    AUDIO_MAX_BYTES,
    IMAGE_MAX_BYTES,
    IMAGE_SEQUENCE_MAX_FRAMES,
    SCREENSHOT_BATCH_MAX_IMAGES,
    SpecIntakeMediaItemInput,
    SpecIntakeValidationInput,
    SpecTargetInput,
)

FIXTURES = Path(__file__).parent / "fixtures/sdd_intake"


def test_intake_request_schema_accepts_camel_aliases() -> None:
    request = SddIntakeRequest(
        workspacePath="/tmp/demo",
        specTarget={"mode": "new_spec"},
        titleSeed="Favorites",
        jobId="job-1",
        items=[
            {
                "kind": "image_sequence",
                "frameCount": 2,
                "audioTrackCount": 1,
                "timelineMs": [0, 100],
            }
        ],
    )

    assert request.workspace_path == "/tmp/demo"
    assert request.spec_target.mode == "new_spec"
    assert request.items[0].frame_count == 2
    assert request.items[0].timeline_ms == [0, 100]
    assert request.job_id == "job-1"


def test_intake_dry_run_plans_all_supported_media_without_writes(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path, spec_id="001-existing")
    for relative_path in (
        "uploads/audio.mp3",
        "uploads/screen.png",
        "uploads/crop.webp",
        "uploads/marked.jpg",
        "uploads/shot-1.png",
        "uploads/shot-2.png",
        "uploads/frame-1.png",
        "uploads/frame-2.png",
        "uploads/narration.m4a",
    ):
        path = project / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative_path.encode())
    service = _service(tmp_path)

    result = service.dry_run_storage(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(
                mode="existing_spec",
                spec_id="001-existing",
                artifact="auto",
            ),
            intake_items=(
                SpecIntakeMediaItemInput(kind="text", text="Add note"),
                SpecIntakeMediaItemInput(
                    kind="audio",
                    mime_type="audio/mpeg",
                    byte_size=2048,
                    duration_ms=5000,
                    filename="note.mp3",
                    sha256="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    payload_ref="uploads/audio.mp3",
                ),
                SpecIntakeMediaItemInput(
                    kind="image",
                    mime_type="image/png",
                    byte_size=1024,
                    filename="screen.png",
                    payload_ref="uploads/screen.png",
                ),
                SpecIntakeMediaItemInput(
                    kind="crop",
                    mime_type="image/webp",
                    byte_size=512,
                    filename="crop.webp",
                    source_ref="screen.png",
                    payload_ref="uploads/crop.webp",
                    region={"x": 1, "y": 2, "width": 3, "height": 4},
                ),
                SpecIntakeMediaItemInput(
                    kind="marked_region",
                    mime_type="image/jpeg",
                    byte_size=600,
                    filename="marked.jpg",
                    source_ref="screen.png",
                    payload_ref="uploads/marked.jpg",
                    region={"x": 1, "y": 2, "width": 30, "height": 40},
                ),
                SpecIntakeMediaItemInput(
                    kind="screenshot_batch",
                    image_count=2,
                    references=("uploads/shot-1.png", "uploads/shot-2.png"),
                ),
                SpecIntakeMediaItemInput(
                    kind="image_sequence",
                    frame_count=2,
                    audio_track_count=1,
                    timeline_ms=(0, 100),
                    references=(
                        "uploads/frame-1.png",
                        "uploads/frame-2.png",
                        "uploads/narration.m4a",
                    ),
                ),
            ),
        ),
        job_id="job 01",
    )

    payload = result.to_payload()
    response = SddIntakeDryRunResponse(**payload)
    target_paths = [item.target_path for item in result.would_create]

    assert response.status == "dry-run"
    assert response.retention_hours == 24
    assert result.staging_root == ".codex-bridge/sdd-intake/job-01"
    assert "specs/001-existing/intake/jobs/job-01/original-request.md" in target_paths
    assert "specs/001-existing/intake/jobs/job-01/media/audio-002.mp3" in target_paths
    assert "specs/001-existing/intake/jobs/job-01/transcript.md" in target_paths
    assert "specs/001-existing/intake/jobs/job-01/media/image-003.png" in target_paths
    assert "specs/001-existing/intake/jobs/job-01/media/crop-004.webp" in target_paths
    assert "specs/001-existing/intake/jobs/job-01/media/marked-005.jpg" in target_paths
    assert (
        "specs/001-existing/intake/jobs/job-01/media/screenshot-001.png" in target_paths
    )
    assert "specs/001-existing/intake/jobs/job-01/media/frame-001.png" in target_paths
    assert "specs/001-existing/intake/jobs/job-01/media/narration.m4a" in target_paths
    assert "specs/001-existing/intake/jobs/job-01/timeline.yaml" in target_paths
    assert result.blocked == ()
    assert result.rejected_media == ()
    assert not (project / "specs/001-existing/intake").exists()


def test_intake_dry_run_accepts_formal_supported_shape_fixture(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path, spec_id="001-existing")
    for relative_path in (
        "media/request.mp3",
        "media/screen.png",
        "media/screen-crop.png",
        "media/screen-marked.webp",
        "media/shot-1.png",
        "media/shot-2.png",
        "media/frame-1.png",
        "media/frame-2.png",
        "media/frame-3.png",
        "media/narration.m4a",
    ):
        path = project / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative_path.encode())
    service = _service(tmp_path)

    result = service.dry_run_storage(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(
                mode="existing_spec",
                spec_id="001-existing",
            ),
            intake_items=_fixture_items("supported_shapes.json"),
        )
    )

    assert result.status == "dry-run"
    assert result.rejected_media == ()
    assert any(item.sha256 for item in result.would_create)
    assert not (project / "specs/001-existing/intake").exists()


def test_intake_dry_run_uses_staging_for_new_spec_without_persistence(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    service = _service(tmp_path)

    result = service.dry_run_storage(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(mode="new_spec", spec_id="favorites"),
            title_seed="Favorites",
            intake_items=(SpecIntakeMediaItemInput(kind="text", text="Favorites"),),
        ),
        job_id="../unsafe job",
    )

    assert result.status == "dry-run"
    assert result.target_root == "specs/favorites/intake"
    assert result.staging_root == ".codex-bridge/sdd-intake/unsafe-job"
    assert result.would_create[0].staging_path.endswith(
        "specs/favorites/intake/original-request.md"
    )
    assert not (project / "specs/favorites").exists()


def test_intake_dry_run_blocks_validation_errors_and_rejected_media(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    service = _service(tmp_path)

    result = service.dry_run_storage(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(
                mode="existing_spec",
                spec_id="999-missing",
            ),
            intake_items=(
                SpecIntakeMediaItemInput(
                    kind="audio",
                    mime_type="audio/ogg",
                    byte_size=AUDIO_MAX_BYTES + 1,
                    duration_ms=600_001,
                ),
                SpecIntakeMediaItemInput(
                    kind="image",
                    mime_type="image/gif",
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

    assert result.status == "blocked"
    assert result.would_create == ()
    assert result.blocked[0].startswith("spec_target.spec_id: target_spec_not_found")
    assert [error.code for error in result.rejected_media] == [
        "unsupported_audio_format",
        "media_audio_too_large",
        "media_audio_duration_too_large",
        "unsupported_image_format",
        "media_image_too_large",
        "media_image_count_too_large",
        "media_frame_count_too_large",
        "media_audio_track_count_too_large",
    ]
    assert not (project / "specs/999-missing").exists()


def test_intake_dry_run_rejects_formal_invalid_media_fixture(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path, spec_id="001-existing")
    service = _service(tmp_path)

    result = service.dry_run_storage(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(
                mode="existing_spec",
                spec_id="001-existing",
            ),
            intake_items=_fixture_items("invalid_media.json"),
        )
    )

    codes = [error.code for error in result.rejected_media]
    assert result.status == "blocked"
    assert codes == [
        "invalid_sha256",
        "unsupported_audio_format",
        "media_audio_too_large",
        "media_audio_duration_too_large",
        "unsupported_image_format",
        "media_image_too_large",
        "invalid_region",
        "missing_media_reference",
        "media_audio_track_count_too_large",
        "invalid_timeline_order",
        "duplicate_media_item",
    ]


def test_intake_dry_run_blocks_duplicate_planned_paths(tmp_path: Path) -> None:
    project = _write_project(tmp_path, spec_id="001-existing")
    service = _service(tmp_path)

    result = service.dry_run_storage(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(
                mode="existing_spec",
                spec_id="001-existing",
            ),
            intake_items=(
                SpecIntakeMediaItemInput(kind="text", text="first"),
                SpecIntakeMediaItemInput(kind="text", text="second"),
            ),
        )
    )

    assert result.status == "blocked"
    assert result.blocked == (
        "duplicate planned intake artifact: specs/001-existing/intake/jobs/dry-run/original-request.md",
    )


def test_intake_dry_run_is_deterministic_and_detects_existing_outputs(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path, spec_id="001-existing")
    existing = project / "specs/001-existing/intake/jobs/same/media"
    existing.mkdir(parents=True)
    (existing / "image-001.png").write_text("already there")
    upload = project / "uploads/image.png"
    upload.parent.mkdir(parents=True)
    upload.write_bytes(b"image")
    service = _service(tmp_path)
    request = SpecIntakeValidationInput(
        workspace_path=str(project),
        spec_target=SpecTargetInput(
            mode="existing_spec",
            spec_id="001-existing",
        ),
        intake_items=(
            SpecIntakeMediaItemInput(
                kind="image",
                mime_type="image/png",
                byte_size=100,
                payload_ref="uploads/image.png",
            ),
        ),
    )

    first = service.dry_run_storage(request, job_id="same")
    second = service.dry_run_storage(request, job_id="same")

    assert first.to_payload() == second.to_payload()
    assert first.status == "blocked"
    assert first.existing == (
        "specs/001-existing/intake/jobs/same/media/image-001.png",
    )
    assert first.blocked == (
        "would overwrite existing intake artifact: specs/001-existing/intake/jobs/same/media/image-001.png",
    )


def _service(tmp_path: Path) -> SddIntakeService:
    return SddIntakeService(projects_root=tmp_path / "projects")


def _fixture_items(name: str) -> tuple[SpecIntakeMediaItemInput, ...]:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return tuple(SpecIntakeMediaItemInput(**item) for item in payload["items"])


def _write_project(tmp_path: Path, *, spec_id: str | None = None) -> Path:
    project = tmp_path / "projects/demo"
    project.mkdir(parents=True)
    (project / "codex-bridge.yaml").write_text("sdd:\n  standard: workbench-sdd/v1\n")
    if spec_id is not None:
        spec_root = project / "specs" / spec_id
        spec_root.mkdir(parents=True)
        (spec_root / "spec.md").write_text("# Existing\n")
    return project
