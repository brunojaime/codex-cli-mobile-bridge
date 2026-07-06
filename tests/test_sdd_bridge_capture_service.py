from __future__ import annotations

import base64
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.application.services.feedback_queue_service import FeedbackQueueItem
from backend.app.application.services.sdd_bridge_capture_service import (
    SddBridgeCaptureService,
)
from backend.app.application.services.sdd_codex_job_service import SddCodexJobService
from backend.app.application.services.sdd_spec_target_service import SpecTargetInput
from backend.app.infrastructure.config.settings import Settings
from backend.app.main import create_app


def test_bridge_capture_none_preserves_feedback_behavior(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    item = _feedback_item(tmp_path, "feedback-1", comment="Keep as feedback")
    service = SddBridgeCaptureService(projects_root=tmp_path / "projects")

    result = service.dry_run_capture(
        workspace_path=str(project),
        spec_target=SpecTargetInput(mode="none"),
        feedback_items=(item,),
    )

    assert result.status == "feedback-only"
    assert result.intake_items == ()
    assert result.staged_media == ()
    assert not (project / ".codex-bridge/sdd-media").exists()


def test_bridge_capture_converts_screenshot_bounds_to_marked_region(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    item = _feedback_item(
        tmp_path,
        "feedback-bounds",
        comment="Use selected area",
        screenshot=b"image",
        selection_bounds={"left": 1, "top": 2, "width": 30, "height": 40},
    )
    service = SddBridgeCaptureService(projects_root=tmp_path / "projects")

    result = service.dry_run_capture(
        workspace_path=str(project),
        spec_target=SpecTargetInput(mode="new_spec", spec_id="capture-bounds"),
        feedback_items=(item,),
    )

    assert result.status == "dry-run"
    assert [item.kind for item in result.intake_items] == [
        "text",
        "image",
        "marked_region",
    ]
    marked = result.intake_items[2]
    assert marked.region == {"x": 1.0, "y": 2.0, "width": 30.0, "height": 40.0}
    assert marked.source_ref == result.intake_items[1].payload_ref


def test_bridge_capture_multi_capture_uses_deterministic_batch_order(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    first = _feedback_item(tmp_path, "feedback-1", screenshot=b"first")
    second = _feedback_item(tmp_path, "feedback-2", screenshot=b"second")
    service = SddBridgeCaptureService(projects_root=tmp_path / "projects")

    result = service.dry_run_capture(
        workspace_path=str(project),
        spec_target=SpecTargetInput(mode="new_spec", spec_id="capture-batch"),
        feedback_items=(first, second),
    )

    batch = next(
        item for item in result.intake_items if item.kind == "screenshot_batch"
    )
    assert batch.image_count == 2
    assert tuple(batch.references) == tuple(
        media["staged_path"] for media in result.staged_media
    )


def test_bridge_capture_screenshot_audio_sequence_preserves_order(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    first = _feedback_item(tmp_path, "feedback-1", screenshot=b"first")
    second = _feedback_item(
        tmp_path,
        "feedback-2",
        screenshot=b"second",
        audio=b"voice",
        audio_duration_ms=1500,
    )
    service = SddBridgeCaptureService(projects_root=tmp_path / "projects")

    result = service.dry_run_capture(
        workspace_path=str(project),
        spec_target=SpecTargetInput(mode="new_spec", spec_id="capture-sequence"),
        feedback_items=(first, second),
    )

    sequence = next(
        item for item in result.intake_items if item.kind == "image_sequence"
    )
    assert sequence.frame_count == 2
    assert sequence.audio_track_count == 1
    assert sequence.timeline_ms == (0, 1000)
    assert sequence.references[-1].endswith("feedback-2.m4a")


def test_bridge_capture_new_spec_dry_run_then_apply_reuses_staged_media(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    item = _feedback_item(
        tmp_path, "feedback-new", comment="Create export", screenshot=b"image"
    )
    service = SddBridgeCaptureService(projects_root=tmp_path / "projects")

    dry_run = service.dry_run_capture(
        workspace_path=str(project),
        spec_target=SpecTargetInput(mode="new_spec", spec_id="capture-export"),
        feedback_items=(item,),
    )
    applied = service.apply_capture(
        workspace_path=str(project),
        spec_target=SpecTargetInput(mode="new_spec", spec_id="capture-export"),
        feedback_items=(item,),
    )

    assert dry_run.status == "dry-run"
    assert applied.status == "applied"
    assert (project / "specs/capture-export/spec.md").is_file()
    assert (
        project / "specs/capture-export/intake/media/image-002.png"
    ).read_bytes() == b"image"


def test_bridge_capture_existing_spec_apply_queues_codex_job(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path, spec_id="001-existing")
    item = _feedback_item(tmp_path, "feedback-existing", comment="Update tasks")
    service = SddBridgeCaptureService(
        projects_root=tmp_path / "projects",
        codex_job_service=SddCodexJobService(projects_root=tmp_path / "projects"),
    )

    result = service.apply_capture(
        workspace_path=str(project),
        spec_target=SpecTargetInput(
            mode="existing_spec",
            spec_id="001-existing",
            artifact="tasks",
        ),
        feedback_items=(item,),
    )

    assert result.status == "queued"
    assert result.apply_result is not None
    assert result.apply_result["job"]["status"] == "queued"
    assert (
        not (project / "specs/001-existing/tasks.md").read_text().startswith("Update")
    )


def test_bridge_capture_invalid_target_blocks_without_writes(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    item = _feedback_item(tmp_path, "feedback-invalid", comment="Update missing")
    service = SddBridgeCaptureService(projects_root=tmp_path / "projects")

    result = service.dry_run_capture(
        workspace_path=str(project),
        spec_target=SpecTargetInput(
            mode="existing_spec",
            spec_id="999-missing",
            artifact="tasks",
        ),
        feedback_items=(item,),
    )

    assert result.status == "blocked"
    assert result.dry_run is not None
    assert "target_spec_not_found" in " ".join(result.blocked)


def test_bridge_capture_api_runs_dry_run_from_feedback_queue(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    client = _client(tmp_path, projects_root=tmp_path / "projects")

    queued = client.post(
        "/feedback-queue",
        json={
            "id": "feedback-api",
            "sourceApp": "sat-catalogo-ropa",
            "sourceDisplayName": "SAT Catalogo Ropa",
            "comment": "Create spec from selected card",
            "screenshotPngBase64": base64.b64encode(b"image").decode("ascii"),
            "selectionBounds": {"left": 3, "top": 4, "width": 50, "height": 60},
        },
    )
    assert queued.status_code == 201

    response = client.post(
        "/sdd/bridge-captures/dry-run",
        json={
            "workspacePath": str(project),
            "specTarget": {"mode": "new_spec", "specId": "capture-api"},
            "feedbackItemIds": ["feedback-api"],
            "jobId": "capture-api-job",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "dry-run"
    assert payload["target_mode"] == "new_spec"
    assert payload["feedback_item_ids"] == ["feedback-api"]
    assert [item["kind"] for item in payload["intake_items"]] == [
        "text",
        "image",
        "marked_region",
    ]
    assert payload["dry_run"]["spec_id"] == "capture-api"
    assert not (project / "specs/capture-api").exists()


def test_feedback_queue_preserves_old_payload_without_spec_target(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path, projects_root=tmp_path / "projects")

    queued = client.post(
        "/feedback-queue",
        json={
            "id": "feedback-old",
            "sourceApp": "sat-catalogo-ropa",
            "comment": "Old payload",
            "screenshotPngBase64": base64.b64encode(b"image").decode("ascii"),
        },
    )

    assert queued.status_code == 201
    assert queued.json()["spec_target"] == {}


def test_bridge_capture_uses_embedded_new_spec_target(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    client = _client(tmp_path, projects_root=tmp_path / "projects")
    queued = client.post(
        "/feedback-queue",
        json={
            "id": "feedback-embedded-new",
            "sourceApp": "sat-catalogo-ropa",
            "comment": "Create embedded spec",
            "screenshotPngBase64": base64.b64encode(b"image").decode("ascii"),
            "specTarget": {
                "mode": "new_spec",
                "specId": "embedded-new",
                "artifact": "auto",
            },
        },
    )
    assert queued.status_code == 201
    assert queued.json()["spec_target"]["mode"] == "new_spec"

    response = client.post(
        "/sdd/bridge-captures/apply",
        json={
            "workspacePath": str(project),
            "feedbackItemIds": ["feedback-embedded-new"],
            "jobId": "embedded-new-job",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "applied"
    assert payload["target_mode"] == "new_spec"
    assert (project / "specs/embedded-new/spec.md").is_file()


def test_bridge_capture_blocks_request_embedded_target_conflict(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    client = _client(tmp_path, projects_root=tmp_path / "projects")
    queued = client.post(
        "/feedback-queue",
        json={
            "id": "feedback-conflict",
            "sourceApp": "sat-catalogo-ropa",
            "comment": "Conflict",
            "screenshotPngBase64": base64.b64encode(b"image").decode("ascii"),
            "specTarget": {
                "mode": "new_spec",
                "specId": "embedded-target",
                "artifact": "tasks",
            },
        },
    )
    assert queued.status_code == 201

    response = client.post(
        "/sdd/bridge-captures/dry-run",
        json={
            "workspacePath": str(project),
            "specTarget": {
                "mode": "new_spec",
                "specId": "ui-target",
                "artifact": "tasks",
            },
            "feedbackItemIds": ["feedback-conflict"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert "spec_target_conflict" in " ".join(payload["blocked"])
    assert not (project / ".codex-bridge/sdd-media").exists()
    assert not (project / "specs/ui-target").exists()


def test_bridge_capture_uses_embedded_existing_spec_target_for_job(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path, spec_id="001-existing")
    client = _client(tmp_path, projects_root=tmp_path / "projects")
    queued = client.post(
        "/feedback-queue",
        json={
            "id": "feedback-embedded-existing",
            "sourceApp": "sat-catalogo-ropa",
            "comment": "Update existing tasks",
            "screenshotPngBase64": base64.b64encode(b"image").decode("ascii"),
            "specTarget": {
                "mode": "existing_spec",
                "specId": "001-existing",
                "artifact": "tasks",
            },
        },
    )
    assert queued.status_code == 201

    response = client.post(
        "/sdd/bridge-captures/apply",
        json={
            "workspacePath": str(project),
            "feedbackItemIds": ["feedback-embedded-existing"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["apply_result"]["job"]["status"] == "queued"
    assert (
        not (project / "specs/001-existing/tasks.md")
        .read_text()
        .startswith("Update existing")
    )


def _feedback_item(
    tmp_path: Path,
    item_id: str,
    *,
    comment: str = "Feedback",
    screenshot: bytes | None = None,
    audio: bytes | None = None,
    audio_duration_ms: int | None = None,
    selection_bounds: dict[str, float] | None = None,
) -> FeedbackQueueItem:
    root = tmp_path / "feedback"
    root.mkdir(exist_ok=True)
    screenshot_file = None
    if screenshot is not None:
        path = root / f"{item_id}.png"
        path.write_bytes(screenshot)
        screenshot_file = str(path)
    audio_file = None
    if audio is not None:
        path = root / f"{item_id}.m4a"
        path.write_bytes(audio)
        audio_file = str(path)
    return FeedbackQueueItem(
        id=item_id,
        source_app="sat-catalogo-ropa",
        source_display_name="SAT Catalogo Ropa",
        comment=comment,
        created_at="2026-07-06T00:00:00Z",
        screenshot_file=screenshot_file,
        screenshot_mime_type="image/png",
        selection_bounds=selection_bounds or {},
        audio_file=audio_file,
        audio_mime_type="audio/mp4" if audio_file else None,
        audio_duration_ms=audio_duration_ms,
        audio_byte_length=len(audio) if audio is not None else None,
    )


def _write_project(
    tmp_path: Path,
    *,
    spec_id: str | None = None,
) -> Path:
    project = tmp_path / "projects/demo"
    project.mkdir(parents=True)
    (project / "codex-bridge.yaml").write_text("sdd:\n  standard: workbench-sdd/v1\n")
    if spec_id is not None:
        spec_root = project / "specs" / spec_id
        spec_root.mkdir(parents=True)
        (spec_root / "spec.md").write_text("# Existing\n")
        (spec_root / "plan.md").write_text("# Plan\n")
        (spec_root / "tasks.md").write_text("- [ ] Existing\n")
        (spec_root / "traceability.yaml").write_text("requirements: {}\n")
    return project


def _client(tmp_path: Path, *, projects_root: Path) -> TestClient:
    settings = Settings(
        codex_command="python3 tests/fixtures/fake_codex_session.py",
        codex_use_exec=True,
        projects_root=str(projects_root),
        chat_store_backend="memory",
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
        audio_transcription_backend="disabled",
        speech_synthesis_backend="disabled",
        feedback_queue_path=str(tmp_path / "feedback_queue.json"),
        feedback_image_dir=str(tmp_path / "feedback_images"),
        feedback_audio_dir=str(tmp_path / "feedback_audio"),
    )
    return TestClient(create_app(settings))
