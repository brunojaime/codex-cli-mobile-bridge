from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.application.services.sdd_media_upload_service import (
    SddMediaUploadService,
)
from backend.app.application.services.sdd_spec_creation_service import (
    SddSpecCreationService,
)
from backend.app.application.services.sdd_spec_target_service import (
    SpecIntakeMediaItemInput,
    SpecIntakeValidationInput,
    SpecTargetInput,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.main import create_app


def test_sdd_media_upload_stages_image_with_metadata(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    content = b"\x89PNG\r\nimage"
    service = SddMediaUploadService(projects_root=tmp_path / "projects")

    result = service.stage_image(
        workspace_path=str(project),
        filename="screen.png",
        mime_type="image/png",
        content=content,
    )

    assert result.status == "staged"
    assert result.intake_item is not None
    assert result.intake_item["kind"] == "image"
    assert result.intake_item["sha256"] == hashlib.sha256(content).hexdigest()
    assert result.staged_path is not None
    assert (project / result.staged_path).read_bytes() == content
    assert result.metadata_path is not None
    assert (project / result.metadata_path).is_file()
    metadata = json.loads((project / result.metadata_path).read_text())
    assert metadata["lifecycle"] == "staged"


def test_sdd_media_upload_stages_crop_with_source_metadata(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    service = SddMediaUploadService(projects_root=tmp_path / "projects")
    source = service.stage_image(
        workspace_path=str(project),
        filename="screen.png",
        mime_type="image/png",
        content=b"source-image",
    )
    assert source.staged_path is not None

    crop = service.stage_crop(
        workspace_path=str(project),
        filename="screen-crop.png",
        mime_type="image/png",
        content=b"cropped-image",
        source_ref=source.staged_path,
        region={"x": 2, "y": 3, "width": 20, "height": 10},
    )

    assert crop.status == "staged"
    assert crop.intake_item is not None
    assert crop.intake_item["kind"] == "crop"
    assert crop.intake_item["source_ref"] == source.staged_path
    assert crop.intake_item["region"] == {"x": 2, "y": 3, "width": 20, "height": 10}
    assert crop.staged_path is not None
    assert (project / crop.staged_path).read_bytes() == b"cropped-image"
    assert crop.metadata_path is not None
    metadata = json.loads((project / crop.metadata_path).read_text())
    assert metadata["media_kind"] == "crop"
    assert metadata["source_ref"] == source.staged_path
    assert metadata["region"]["width"] == 20


def test_sdd_media_upload_rejects_invalid_crop_source_or_region(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    service = SddMediaUploadService(projects_root=tmp_path / "projects")
    source = service.stage_image(
        workspace_path=str(project),
        filename="screen.png",
        mime_type="image/png",
        content=b"source-image",
    )
    assert source.staged_path is not None
    deleted = service.delete_staged_media(
        workspace_path=str(project),
        staged_path=source.staged_path,
    )
    assert deleted.status == "deleted"

    missing_parent = service.stage_crop(
        workspace_path=str(project),
        filename="screen-crop.png",
        mime_type="image/png",
        content=b"cropped-image",
        region={"x": 2, "y": 3, "width": 20, "height": 10},
    )
    deleted_parent = service.stage_crop(
        workspace_path=str(project),
        filename="screen-crop.png",
        mime_type="image/png",
        content=b"cropped-image",
        source_ref=source.staged_path,
        region={"x": 2, "y": 3, "width": 20, "height": 10},
    )
    live_source = service.stage_image(
        workspace_path=str(project),
        filename="screen-2.png",
        mime_type="image/png",
        content=b"source-image-2",
    )
    assert live_source.staged_path is not None
    invalid_region = service.stage_crop(
        workspace_path=str(project),
        filename="screen-crop.png",
        mime_type="image/png",
        content=b"cropped-image",
        source_ref=live_source.staged_path,
        region={"x": 2, "y": 3, "width": 0, "height": 10},
    )

    assert missing_parent.status == "blocked"
    assert "crop source_ref is required" in missing_parent.blocked[0]
    assert deleted_parent.status == "blocked"
    assert "staged media file does not exist" in deleted_parent.blocked[0]
    assert invalid_region.status == "blocked"
    assert "invalid_crop_region_width" in invalid_region.blocked


def test_sdd_media_upload_rejects_unsafe_or_invalid_media(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    service = SddMediaUploadService(projects_root=tmp_path / "projects")

    unsupported = service.stage_image(
        workspace_path=str(project),
        filename="screen.gif",
        mime_type="image/gif",
        content=b"gif",
    )
    mismatch = service.stage_image(
        workspace_path=str(project),
        filename="screen.png",
        mime_type="image/png",
        content=b"png",
        sha256="0" * 64,
    )
    oversized = service.stage_image(
        workspace_path=str(project),
        filename="large.png",
        mime_type="image/png",
        content=b"x" * (10 * 1024 * 1024 + 1),
    )

    assert unsupported.status == "blocked"
    assert "unsupported_image_extension" in unsupported.blocked
    assert "unsupported_image_mime_type" in unsupported.blocked
    assert mismatch.status == "blocked"
    assert "sha256 mismatch" in mismatch.blocked
    assert oversized.status == "blocked"
    assert oversized.staged_path is None


def test_sdd_media_upload_blocks_duplicate_without_overwrite(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    service = SddMediaUploadService(projects_root=tmp_path / "projects")

    first = service.stage_image(
        workspace_path=str(project),
        filename="screen.png",
        mime_type="image/png",
        content=b"same",
    )
    second = service.stage_image(
        workspace_path=str(project),
        filename="screen.png",
        mime_type="image/png",
        content=b"same",
    )

    assert first.status == "staged"
    assert second.status == "blocked"
    assert "would overwrite existing staged media" in second.blocked[0]
    assert first.staged_path is not None
    assert (project / first.staged_path).read_bytes() == b"same"


def test_sdd_media_upload_is_consumed_by_new_spec_apply(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    upload = SddMediaUploadService(projects_root=tmp_path / "projects").stage_image(
        workspace_path=str(project),
        filename="screen.png",
        mime_type="image/png",
        content=b"image",
    )
    assert upload.intake_item is not None
    service = SddSpecCreationService(projects_root=tmp_path / "projects")

    result = service.apply_new_spec(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(mode="new_spec", spec_id="image-spec"),
            intake_items=(
                SpecIntakeMediaItemInput(kind="text", text="Use screenshot"),
                SpecIntakeMediaItemInput(**upload.intake_item),
            ),
        )
    )

    assert result.status == "applied"
    assert "specs/image-spec/intake/media/image-002.png" in result.created
    assert (
        project / "specs/image-spec/intake/media/image-002.png"
    ).read_bytes() == b"image"
    assert "Run visual extraction" in " ".join(result.next_actions)
    assert upload.staged_path is not None
    delete = SddMediaUploadService(
        projects_root=tmp_path / "projects"
    ).delete_staged_media(
        workspace_path=str(project),
        staged_path=upload.staged_path,
    )
    assert delete.status == "blocked"
    assert delete.lifecycle == "consumed"
    assert "consumed" in delete.blocked[0]


def test_sdd_media_upload_crop_is_consumed_by_new_spec_apply(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    upload_service = SddMediaUploadService(projects_root=tmp_path / "projects")
    source = upload_service.stage_image(
        workspace_path=str(project),
        filename="screen.png",
        mime_type="image/png",
        content=b"image",
    )
    assert source.intake_item is not None
    assert source.staged_path is not None
    crop = upload_service.stage_crop(
        workspace_path=str(project),
        filename="screen-crop.png",
        mime_type="image/png",
        content=b"crop",
        source_ref=source.staged_path,
        region={"x": 1, "y": 2, "width": 3, "height": 4},
    )
    assert crop.intake_item is not None
    assert crop.staged_path is not None
    service = SddSpecCreationService(projects_root=tmp_path / "projects")

    result = service.apply_new_spec(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(mode="new_spec", spec_id="crop-spec"),
            intake_items=(
                SpecIntakeMediaItemInput(kind="text", text="Use cropped screenshot"),
                SpecIntakeMediaItemInput(**source.intake_item),
                SpecIntakeMediaItemInput(**crop.intake_item),
            ),
        )
    )

    assert result.status == "applied"
    assert "specs/crop-spec/intake/media/crop-003.png" in result.created
    assert (
        project / "specs/crop-spec/intake/media/crop-003.png"
    ).read_bytes() == b"crop"
    retention = json.loads(
        (project / "specs/crop-spec/intake/retention.json").read_text()
    )
    crop_artifact = next(
        artifact for artifact in retention["artifacts"] if artifact["kind"] == "crop"
    )
    assert crop_artifact["metadata"]["region"] == {
        "x": 1,
        "y": 2,
        "width": 3,
        "height": 4,
    }
    delete_crop = upload_service.delete_staged_media(
        workspace_path=str(project),
        staged_path=crop.staged_path,
    )
    assert delete_crop.status == "blocked"
    assert delete_crop.lifecycle == "consumed"


def test_sdd_media_upload_deletes_unconsumed_staged_file_and_sidecar(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    service = SddMediaUploadService(projects_root=tmp_path / "projects")
    upload = service.stage_image(
        workspace_path=str(project),
        filename="screen.png",
        mime_type="image/png",
        content=b"image",
    )
    assert upload.staged_path is not None
    assert upload.metadata_path is not None

    delete = service.delete_staged_media(
        workspace_path=str(project),
        staged_path=upload.staged_path,
    )

    assert delete.status == "deleted"
    assert upload.staged_path in delete.deleted
    assert upload.metadata_path in delete.deleted
    assert not (project / upload.staged_path).exists()
    assert not (project / upload.metadata_path).exists()


def test_sdd_media_upload_rejects_unsafe_delete_path(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    service = SddMediaUploadService(projects_root=tmp_path / "projects")

    delete = service.delete_staged_media(
        workspace_path=str(project),
        staged_path="../outside.png",
    )

    assert delete.status == "blocked"
    assert "unsafe staged media path" in delete.blocked[0]


def test_sdd_media_upload_cleanup_dry_run_and_apply(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    service = SddMediaUploadService(projects_root=tmp_path / "projects")
    old_upload = service.stage_image(
        workspace_path=str(project),
        filename="old.png",
        mime_type="image/png",
        content=b"old",
    )
    fresh_upload = service.stage_image(
        workspace_path=str(project),
        filename="fresh.png",
        mime_type="image/png",
        content=b"fresh",
    )
    assert old_upload.metadata_path is not None
    assert old_upload.staged_path is not None
    assert fresh_upload.staged_path is not None
    old_metadata_path = project / old_upload.metadata_path
    old_metadata = json.loads(old_metadata_path.read_text())
    old_metadata["created_at"] = (
        (datetime.now(UTC) - timedelta(hours=48)).isoformat().replace("+00:00", "Z")
    )
    old_metadata_path.write_text(json.dumps(old_metadata))

    dry_run = service.cleanup_staged_media(workspace_path=str(project), dry_run=True)
    applied = service.cleanup_staged_media(workspace_path=str(project), dry_run=False)

    assert dry_run.status == "dry-run"
    assert old_upload.staged_path in dry_run.would_delete
    assert fresh_upload.staged_path not in dry_run.would_delete
    assert applied.status == "applied"
    assert old_upload.staged_path in applied.deleted
    assert not (project / old_upload.staged_path).exists()
    assert (project / fresh_upload.staged_path).exists()


def test_sdd_media_upload_stages_and_rejects_audio(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    content = b"audio"
    service = SddMediaUploadService(projects_root=tmp_path / "projects")

    staged = service.stage_audio(
        workspace_path=str(project),
        filename="note.m4a",
        mime_type="audio/mp4",
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
        duration_ms=12_000,
    )
    unsupported = service.stage_audio(
        workspace_path=str(project),
        filename="note.ogg",
        mime_type="audio/ogg",
        content=b"audio",
        duration_ms=12_000,
    )
    missing_duration = service.stage_audio(
        workspace_path=str(project),
        filename="note.m4a",
        mime_type="audio/mp4",
        content=b"other",
    )

    assert staged.status == "staged"
    assert staged.intake_item is not None
    assert staged.intake_item["kind"] == "audio"
    assert staged.intake_item["duration_ms"] == 12_000
    assert "Run transcription" in " ".join(staged.next_actions)
    assert unsupported.status == "blocked"
    assert "unsupported_audio_extension" in unsupported.blocked
    assert "unsupported_audio_mime_type" in unsupported.blocked
    assert missing_duration.status == "blocked"
    assert "missing_audio_duration" in missing_duration.blocked


def test_sdd_media_upload_api_returns_intake_item(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    client = TestClient(
        create_app(
            Settings(
                projects_root=str(tmp_path / "projects"),
                chat_store_backend="memory",
                audio_transcription_backend="disabled",
                speech_synthesis_backend="disabled",
            )
        )
    )

    response = client.post(
        "/sdd/specs/intake/media",
        data={
            "workspace_path": str(project),
            "kind": "image",
            "mime_type": "image/png",
        },
        files={"media": ("screen.png", b"image", "image/png")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "staged"
    assert payload["intake_item"]["kind"] == "image"
    assert payload["intake_item"]["payload_ref"].startswith(".codex-bridge/sdd-media/")


def test_sdd_media_upload_api_returns_crop_intake_item(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    client = TestClient(
        create_app(
            Settings(
                projects_root=str(tmp_path / "projects"),
                chat_store_backend="memory",
                audio_transcription_backend="disabled",
                speech_synthesis_backend="disabled",
            )
        )
    )
    source_response = client.post(
        "/sdd/specs/intake/media",
        data={
            "workspace_path": str(project),
            "kind": "image",
            "mime_type": "image/png",
        },
        files={"media": ("screen.png", b"image", "image/png")},
    )
    source_ref = source_response.json()["staged_path"]

    crop_response = client.post(
        "/sdd/specs/intake/media",
        data={
            "workspace_path": str(project),
            "kind": "crop",
            "mime_type": "image/png",
            "source_ref": source_ref,
            "region": json.dumps({"x": 1, "y": 2, "width": 3, "height": 4}),
        },
        files={"media": ("screen-crop.png", b"crop", "image/png")},
    )

    assert crop_response.status_code == 200
    payload = crop_response.json()
    assert payload["status"] == "staged"
    assert payload["intake_item"]["kind"] == "crop"
    assert payload["intake_item"]["source_ref"] == source_ref
    assert payload["intake_item"]["region"] == {"x": 1, "y": 2, "width": 3, "height": 4}


def test_sdd_media_upload_api_deletes_staged_media(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    client = TestClient(
        create_app(
            Settings(
                projects_root=str(tmp_path / "projects"),
                chat_store_backend="memory",
                audio_transcription_backend="disabled",
                speech_synthesis_backend="disabled",
            )
        )
    )
    upload_response = client.post(
        "/sdd/specs/intake/media",
        data={
            "workspace_path": str(project),
            "kind": "audio",
            "mime_type": "audio/mp4",
            "duration_ms": "1000",
        },
        files={"media": ("note.m4a", b"audio", "audio/mp4")},
    )
    staged_path = upload_response.json()["staged_path"]

    delete_response = client.post(
        "/sdd/specs/intake/media/delete",
        json={"workspacePath": str(project), "stagedPath": staged_path},
    )

    assert delete_response.status_code == 200
    payload = delete_response.json()
    assert payload["status"] == "deleted"
    assert staged_path in payload["deleted"]


def _write_project(tmp_path: Path) -> Path:
    project = tmp_path / "projects/demo"
    project.mkdir(parents=True)
    (project / "codex-bridge.yaml").write_text("sdd:\n  standard: workbench-sdd/v1\n")
    return project
