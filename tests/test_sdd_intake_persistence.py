from __future__ import annotations

import hashlib
from pathlib import Path

from backend.app.application.services.sdd_intake_service import SddIntakeService
from backend.app.application.services.sdd_media_upload_service import (
    SddMediaUploadService,
)
from backend.app.application.services.sdd_spec_target_service import (
    IMAGE_MAX_BYTES,
    SpecIntakeMediaItemInput,
    SpecIntakeValidationInput,
    SpecTargetInput,
)


def test_intake_persistence_writes_text_audio_image_and_retention_manifest(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    audio = _write_payload(project, "uploads/audio.m4a", b"audio-bytes")
    image = _write_payload(project, "uploads/image.png", b"image-bytes")
    service = SddIntakeService(projects_root=tmp_path / "projects")

    result = service.persist_storage(
        _request(
            project,
            (
                SpecIntakeMediaItemInput(kind="text", text="Create favorites"),
                SpecIntakeMediaItemInput(
                    kind="audio",
                    mime_type="audio/m4a",
                    byte_size=audio.stat().st_size,
                    filename="audio.m4a",
                    sha256=_sha(audio),
                    duration_ms=1000,
                    payload_ref="uploads/audio.m4a",
                ),
                SpecIntakeMediaItemInput(
                    kind="image",
                    mime_type="image/png",
                    byte_size=image.stat().st_size,
                    filename="image.png",
                    sha256=_sha(image),
                    payload_ref="uploads/image.png",
                ),
            ),
        ),
        job_id="job-media",
    )

    assert result.status == "applied"
    assert {artifact.target_path for artifact in result.persisted} >= {
        "specs/001-demo/intake/jobs/job-media/original-request.md",
        "specs/001-demo/intake/jobs/job-media/media/audio-002.m4a",
        "specs/001-demo/intake/jobs/job-media/transcript.md",
        "specs/001-demo/intake/jobs/job-media/media/image-003.png",
    }
    assert (
        result.retention_manifest_path
        == "specs/001-demo/intake/jobs/job-media/retention.json"
    )
    assert (
        project / "specs/001-demo/intake/jobs/job-media/media/audio-002.m4a"
    ).read_bytes() == b"audio-bytes"
    assert (
        "Transcription has not been generated yet"
        in (project / "specs/001-demo/intake/jobs/job-media/transcript.md").read_text()
    )
    assert "Run transcription" in result.next_actions[0]


def test_intake_persistence_writes_crop_region_batch_and_sequence_order(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    for path, payload in {
        "uploads/source.png": b"source",
        "uploads/crop.png": b"crop",
        "uploads/marked.png": b"marked",
        "uploads/shot-1.png": b"shot1",
        "uploads/shot-2.png": b"shot2",
        "uploads/frame-1.png": b"frame1",
        "uploads/frame-2.png": b"frame2",
        "uploads/narration.m4a": b"voice",
    }.items():
        _write_payload(project, path, payload)
    service = SddIntakeService(projects_root=tmp_path / "projects")

    result = service.persist_storage(
        _request(
            project,
            (
                SpecIntakeMediaItemInput(
                    kind="image",
                    mime_type="image/png",
                    byte_size=6,
                    filename="source.png",
                    payload_ref="uploads/source.png",
                ),
                SpecIntakeMediaItemInput(
                    kind="crop",
                    mime_type="image/png",
                    byte_size=4,
                    filename="crop.png",
                    source_ref="source.png",
                    payload_ref="uploads/crop.png",
                    region={"x": 1, "y": 2, "width": 3, "height": 4},
                ),
                SpecIntakeMediaItemInput(
                    kind="marked_region",
                    mime_type="image/png",
                    byte_size=6,
                    filename="marked.png",
                    source_ref="source.png",
                    payload_ref="uploads/marked.png",
                    region={"x": 5, "y": 6, "width": 7, "height": 8},
                ),
                SpecIntakeMediaItemInput(
                    kind="screenshot_batch",
                    image_count=2,
                    byte_size=5,
                    references=("uploads/shot-1.png", "uploads/shot-2.png"),
                ),
                SpecIntakeMediaItemInput(
                    kind="image_sequence",
                    frame_count=2,
                    audio_track_count=1,
                    timeline_ms=(0, 500),
                    references=(
                        "uploads/frame-1.png",
                        "uploads/frame-2.png",
                        "uploads/narration.m4a",
                    ),
                ),
            ),
        ),
        job_id="job-complex",
    )

    assert result.status == "applied"
    assert (
        project / "specs/001-demo/intake/jobs/job-complex/media/crop-002.png"
    ).read_bytes() == b"crop"
    assert (
        project / "specs/001-demo/intake/jobs/job-complex/media/marked-003.png"
    ).read_bytes() == b"marked"
    assert (
        project / "specs/001-demo/intake/jobs/job-complex/media/screenshot-001.png"
    ).read_bytes() == b"shot1"
    assert (
        project / "specs/001-demo/intake/jobs/job-complex/media/frame-001.png"
    ).read_bytes() == b"frame1"
    timeline = (
        project / "specs/001-demo/intake/jobs/job-complex/timeline.yaml"
    ).read_text()
    assert "  - 0\n  - 500" in timeline
    assert "uploads/narration.m4a" in timeline
    crop_metadata = next(
        artifact.metadata for artifact in result.persisted if artifact.kind == "crop"
    )
    sequence_metadata = next(
        artifact.metadata
        for artifact in result.persisted
        if artifact.kind == "sequence_manifest"
    )
    assert crop_metadata["region"] == {"x": 1, "y": 2, "width": 3, "height": 4}
    assert sequence_metadata["timeline_ms"] == [0, 500]


def test_intake_persistence_accepts_structured_staged_media_refs(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    upload_service = SddMediaUploadService(projects_root=tmp_path / "projects")
    source = upload_service.stage_image(
        workspace_path=str(project),
        filename="source.png",
        mime_type="image/png",
        content=b"source",
    )
    crop = upload_service.stage_image(
        workspace_path=str(project),
        filename="crop.png",
        mime_type="image/png",
        content=b"crop",
    )
    marked = upload_service.stage_image(
        workspace_path=str(project),
        filename="marked.png",
        mime_type="image/png",
        content=b"marked",
    )
    shot1 = upload_service.stage_image(
        workspace_path=str(project),
        filename="shot-1.png",
        mime_type="image/png",
        content=b"shot1",
    )
    shot2 = upload_service.stage_image(
        workspace_path=str(project),
        filename="shot-2.png",
        mime_type="image/png",
        content=b"shot2",
    )
    frame1 = upload_service.stage_image(
        workspace_path=str(project),
        filename="frame-1.png",
        mime_type="image/png",
        content=b"frame1",
    )
    frame2 = upload_service.stage_image(
        workspace_path=str(project),
        filename="frame-2.png",
        mime_type="image/png",
        content=b"frame2",
    )
    audio = upload_service.stage_audio(
        workspace_path=str(project),
        filename="narration.m4a",
        mime_type="audio/mp4",
        content=b"voice",
        duration_ms=800,
    )
    staged = (source, crop, marked, shot1, shot2, frame1, frame2, audio)
    assert all(item.staged_path is not None for item in staged)
    service = SddIntakeService(projects_root=tmp_path / "projects")

    result = service.persist_storage(
        _request(
            project,
            (
                SpecIntakeMediaItemInput(kind="text", text="Use structured media"),
                SpecIntakeMediaItemInput(
                    kind="image",
                    mime_type="image/png",
                    byte_size=6,
                    filename="source.png",
                    payload_ref=source.staged_path,
                ),
                SpecIntakeMediaItemInput(
                    kind="crop",
                    mime_type="image/png",
                    byte_size=4,
                    filename="crop.png",
                    source_ref=source.staged_path,
                    payload_ref=crop.staged_path,
                    region={"x": 1, "y": 2, "width": 3, "height": 4},
                ),
                SpecIntakeMediaItemInput(
                    kind="marked_region",
                    mime_type="image/png",
                    byte_size=6,
                    filename="marked.png",
                    source_ref=source.staged_path,
                    payload_ref=marked.staged_path,
                    region={"x": 5, "y": 6, "width": 7, "height": 8},
                ),
                SpecIntakeMediaItemInput(
                    kind="screenshot_batch",
                    image_count=2,
                    references=(shot1.staged_path or "", shot2.staged_path or ""),
                ),
                SpecIntakeMediaItemInput(
                    kind="image_sequence",
                    frame_count=2,
                    audio_track_count=1,
                    timeline_ms=(0, 800),
                    references=(
                        frame1.staged_path or "",
                        frame2.staged_path or "",
                        audio.staged_path or "",
                    ),
                ),
            ),
        ),
        job_id="job-structured",
    )

    assert result.status == "applied"
    assert (
        project / "specs/001-demo/intake/jobs/job-structured/media/crop-003.png"
    ).read_bytes() == b"crop"
    assert (
        project / "specs/001-demo/intake/jobs/job-structured/media/screenshot-001.png"
    ).read_bytes() == b"shot1"
    assert (
        project / "specs/001-demo/intake/jobs/job-structured/media/narration.m4a"
    ).read_bytes() == b"voice"
    assert any(
        artifact.metadata.get("source_ref") == source.staged_path
        for artifact in result.persisted
        if artifact.kind == "crop"
    )


def test_intake_dry_run_blocks_deleted_and_duplicate_structured_refs(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    upload_service = SddMediaUploadService(projects_root=tmp_path / "projects")
    image = upload_service.stage_image(
        workspace_path=str(project),
        filename="screen.png",
        mime_type="image/png",
        content=b"image",
    )
    assert image.staged_path is not None
    upload_service.delete_staged_media(
        workspace_path=str(project),
        staged_path=image.staged_path,
    )
    service = SddIntakeService(projects_root=tmp_path / "projects")

    deleted = service.dry_run_storage(
        _request(
            project,
            (
                SpecIntakeMediaItemInput(
                    kind="image",
                    mime_type="image/png",
                    byte_size=5,
                    filename="screen.png",
                    payload_ref=image.staged_path,
                ),
            ),
        )
    )
    duplicate = service.dry_run_storage(
        _request(
            project,
            (
                SpecIntakeMediaItemInput(
                    kind="screenshot_batch",
                    image_count=2,
                    references=("uploads/missing.png", "uploads/missing.png"),
                ),
            ),
        )
    )

    assert deleted.status == "blocked"
    assert "does not resolve" in deleted.blocked[0]
    assert duplicate.status == "blocked"
    assert any("duplicate media reference" in item for item in duplicate.blocked)


def test_intake_persistence_blocks_sha_mismatch_and_cleans_partial_writes(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    audio = _write_payload(project, "uploads/audio.m4a", b"audio-bytes")
    service = SddIntakeService(projects_root=tmp_path / "projects")

    result = service.persist_storage(
        _request(
            project,
            (
                SpecIntakeMediaItemInput(kind="text", text="Create favorites"),
                SpecIntakeMediaItemInput(
                    kind="audio",
                    mime_type="audio/m4a",
                    byte_size=audio.stat().st_size,
                    filename="audio.m4a",
                    sha256="0" * 64,
                    duration_ms=1000,
                    payload_ref="uploads/audio.m4a",
                ),
            ),
        ),
        job_id="job-bad-sha",
    )

    assert result.status == "blocked"
    assert "sha256 mismatch" in result.blocked[0]
    assert not (
        project / "specs/001-demo/intake/jobs/job-bad-sha/original-request.md"
    ).exists()
    assert result.cleanup


def test_intake_persistence_blocks_limits_format_duplicates_collisions_and_escape(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside")
    _write_payload(project, "uploads/image.png", b"image")
    (project / "specs/001-demo/intake/jobs/job-collision").mkdir(parents=True)
    (
        project / "specs/001-demo/intake/jobs/job-collision/original-request.md"
    ).write_text("exists")
    service = SddIntakeService(projects_root=tmp_path / "projects")

    collision = service.persist_storage(
        _request(project, (SpecIntakeMediaItemInput(kind="text", text="New"),)),
        job_id="job-collision",
    )
    unsupported = service.persist_storage(
        _request(
            project,
            (
                SpecIntakeMediaItemInput(
                    kind="image",
                    mime_type="image/gif",
                    byte_size=10,
                    filename="bad.gif",
                    payload_ref="uploads/image.png",
                ),
            ),
        )
    )
    oversized = service.persist_storage(
        _request(
            project,
            (
                SpecIntakeMediaItemInput(
                    kind="image",
                    mime_type="image/png",
                    byte_size=IMAGE_MAX_BYTES + 1,
                    filename="too-large.png",
                    payload_ref="uploads/image.png",
                ),
            ),
        )
    )
    duplicate = service.persist_storage(
        _request(
            project,
            (
                SpecIntakeMediaItemInput(
                    kind="image",
                    mime_type="image/png",
                    byte_size=5,
                    filename="image.png",
                    payload_ref="uploads/image.png",
                ),
                SpecIntakeMediaItemInput(
                    kind="image",
                    mime_type="image/png",
                    byte_size=5,
                    filename="image.png",
                    payload_ref="uploads/image.png",
                ),
            ),
        )
    )
    escaped = service.persist_storage(
        _request(
            project,
            (
                SpecIntakeMediaItemInput(
                    kind="image",
                    mime_type="image/png",
                    byte_size=outside.stat().st_size,
                    filename="outside.png",
                    payload_ref=str(outside),
                ),
            ),
        ),
        job_id="job-escape",
    )

    assert collision.status == "blocked"
    assert "would overwrite" in collision.blocked[0]
    assert unsupported.status == "blocked"
    assert "unsupported_image_format" in unsupported.blocked[0]
    assert oversized.status == "blocked"
    assert "media_image_too_large" in oversized.blocked[0]
    assert duplicate.status == "blocked"
    assert "duplicate_media_item" in duplicate.blocked[0]
    assert escaped.status == "blocked"
    assert "escapes workspace" in escaped.blocked[0]
    assert not (
        project / "specs/001-demo/intake/jobs/job-escape/media/outside-001.png"
    ).exists()


def _request(
    project: Path,
    items: tuple[SpecIntakeMediaItemInput, ...],
) -> SpecIntakeValidationInput:
    return SpecIntakeValidationInput(
        workspace_path=str(project),
        spec_target=SpecTargetInput(mode="existing_spec", spec_id="001-demo"),
        intake_items=items,
    )


def _write_project(tmp_path: Path) -> Path:
    project = tmp_path / "projects/demo"
    spec_root = project / "specs/001-demo"
    spec_root.mkdir(parents=True)
    (project / "codex-bridge.yaml").write_text("sdd:\n  standard: workbench-sdd/v1\n")
    (spec_root / "spec.md").write_text("# Demo\n")
    (spec_root / "tasks.md").write_text("- [ ] Existing\n")
    return project


def _write_payload(project: Path, relative_path: str, content: bytes) -> Path:
    path = project / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
