from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

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


def test_new_spec_apply_creates_text_only_spec_from_dry_run_plan(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    service = SddSpecCreationService(projects_root=tmp_path / "projects")
    request = _text_request(project, spec_id="favorites")

    dry_run = service.dry_run_new_spec(request)
    result = service.apply_new_spec(request)

    assert result.status == "applied"
    assert result.dry_run.target_files == dry_run.target_files
    assert result.created == (
        "specs/favorites",
        "specs/favorites/intake/",
        "specs/favorites/diagrams/",
        "specs/favorites/metadata.yaml",
        "specs/favorites/spec.md",
        "specs/favorites/plan.md",
        "specs/favorites/tasks.md",
        "specs/favorites/traceability.yaml",
        "specs/favorites/intake/original-request.md",
        "specs/favorites/intake/retention.json",
    )
    assert result.post_apply_refresh["metadata_status"] == "written"
    assert result.post_apply_refresh["traceability_status"] == "written"
    assert result.post_apply_refresh["metadata_refresh"]["status"] == "updated"
    assert result.post_apply_refresh["metadata_refresh"]["task_summary"] == {
        "total": 1,
        "completed": 0,
        "pending": 1,
    }
    assert result.post_apply_refresh["index_status"] == "regenerated"
    assert "spec-index.yaml" in result.post_apply_refresh["generated_indexes"]
    assert (project / ".sdd/spec-index.yaml").is_file()
    assert "source_digests" in (project / "specs/favorites/metadata.yaml").read_text()
    assert "favorites" in (project / ".sdd/spec-index.yaml").read_text()
    assert (project / "specs/favorites/spec.md").is_file()
    assert "# Product Favorites" in (project / "specs/favorites/spec.md").read_text()
    assert (
        "Users save favorite products."
        in (project / "specs/favorites/intake/original-request.md").read_text()
    )
    assert not (tmp_path / "outside-created").exists()


def test_new_spec_apply_api_returns_machine_testable_created_output(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    client = _client(tmp_path / "projects")

    response = client.post(
        "/sdd/specs/apply",
        json={
            "workspacePath": str(project),
            "specTarget": {"mode": "new_spec", "specId": "favorites"},
            "titleSeed": "Product favorites",
            "intakeItems": [{"kind": "text", "text": "Users save favorite products."}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "codex.sddSpecApply"
    assert payload["status"] == "applied"
    assert "specs/favorites/spec.md" in payload["created"]
    assert payload["metadata_result"]["title"] == "Product Favorites"
    assert payload["intake_references"] == [
        "specs/favorites/intake/original-request.md"
    ]
    assert payload["post_apply_refresh"]["metadata_status"] == "written"
    assert payload["post_apply_refresh"]["metadata_refresh"]["status"] == "updated"
    assert payload["post_apply_refresh"]["index_status"] == "regenerated"
    assert "spec-index.yaml" in payload["post_apply_refresh"]["generated_indexes"]
    assert payload["dry_run"]["status"] == "dry-run"


def test_new_spec_apply_blocks_pre_existing_collision_and_is_idempotent(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    service = SddSpecCreationService(projects_root=tmp_path / "projects")
    request = _text_request(project, spec_id="favorites")

    first = service.apply_new_spec(request)
    second = service.apply_new_spec(request)

    assert first.status == "applied"
    assert second.status == "blocked"
    assert "spec_slug_collision" in second.blocked[0]
    assert (project / "specs/favorites/spec.md").read_text().count(
        "# Product Favorites"
    ) == 1


def test_new_spec_apply_blocks_unsafe_path_and_invalid_media_without_writes(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    service = SddSpecCreationService(projects_root=tmp_path / "projects")

    unsafe = service.apply_new_spec(
        SpecIntakeValidationInput(
            workspace_path=str(tmp_path / "outside"),
            spec_target=SpecTargetInput(mode="new_spec", spec_id="unsafe"),
            title_seed="Unsafe",
            intake_items=(SpecIntakeMediaItemInput(kind="text", text="Unsafe"),),
        )
    )
    missing_payload = service.apply_new_spec(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(mode="new_spec", spec_id="audio-backed"),
            title_seed="Audio backed",
            intake_items=(
                SpecIntakeMediaItemInput(
                    kind="audio",
                    mime_type="audio/mpeg",
                    byte_size=100,
                    duration_ms=100,
                ),
            ),
        )
    )

    assert unsafe.status == "blocked"
    assert "unsafe_workspace_path" in unsafe.blocked[0]
    assert missing_payload.status == "blocked"
    assert "requires payload_ref" in missing_payload.blocked[0]
    assert not (project / "specs/audio-backed").exists()
    assert not (tmp_path / "outside/specs/unsafe").exists()


def test_new_spec_apply_persists_media_payloads_from_valid_refs(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    audio = project / "uploads/audio.m4a"
    audio.parent.mkdir()
    audio.write_bytes(b"audio-bytes")
    service = SddSpecCreationService(projects_root=tmp_path / "projects")

    result = service.apply_new_spec(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(mode="new_spec", spec_id="audio-backed"),
            title_seed="Audio backed",
            intake_items=(
                SpecIntakeMediaItemInput(kind="text", text="Audio backed request"),
                SpecIntakeMediaItemInput(
                    kind="audio",
                    mime_type="audio/m4a",
                    byte_size=audio.stat().st_size,
                    filename="audio.m4a",
                    sha256=_sha(audio),
                    duration_ms=100,
                    payload_ref="uploads/audio.m4a",
                ),
            ),
        )
    )

    assert result.status == "applied"
    assert "specs/audio-backed/intake/media/audio-002.m4a" in result.created
    assert "specs/audio-backed/intake/retention.json" in result.created
    assert (
        project / "specs/audio-backed/intake/media/audio-002.m4a"
    ).read_bytes() == b"audio-bytes"
    assert "Run transcription" in result.next_actions[1]


def test_new_spec_apply_audio_transcript_fixture_persists_transcript(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    audio = project / "fixtures/audio/favorites.m4a"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"audio-transcript-fixture")
    service = SddSpecCreationService(projects_root=tmp_path / "projects")

    result = service.apply_new_spec(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(mode="new_spec", spec_id="audio-transcript"),
            title_seed="Audio transcript",
            intake_items=(
                SpecIntakeMediaItemInput(
                    kind="audio",
                    mime_type="audio/m4a",
                    byte_size=audio.stat().st_size,
                    filename="favorites.m4a",
                    sha256=_sha(audio),
                    duration_ms=1200,
                    payload_ref="fixtures/audio/favorites.m4a",
                    transcript=(
                        "El usuario quiere guardar prendas favoritas y verlas "
                        "en una lista dedicada."
                    ),
                ),
            ),
        )
    )

    assert result.status == "applied"
    transcript = (project / "specs/audio-transcript/intake/transcript.md").read_text(
        encoding="utf-8"
    )
    assert "guardar prendas favoritas" in transcript
    assert "Transcription has not been generated" not in transcript
    assert "Run transcription" not in " ".join(result.next_actions)
    assert (
        project / "specs/audio-transcript/intake/media/audio-001.m4a"
    ).read_bytes() == b"audio-transcript-fixture"


def test_new_spec_apply_failed_transcription_fixture_does_not_invent_content(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    audio = project / "fixtures/audio/failed.m4a"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"audio-without-transcript")
    service = SddSpecCreationService(projects_root=tmp_path / "projects")

    result = service.apply_new_spec(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(
                mode="new_spec",
                spec_id="failed-transcription",
            ),
            title_seed="Failed transcription",
            intake_items=(
                SpecIntakeMediaItemInput(
                    kind="audio",
                    mime_type="audio/m4a",
                    byte_size=audio.stat().st_size,
                    filename="failed.m4a",
                    sha256=_sha(audio),
                    duration_ms=1200,
                    payload_ref="fixtures/audio/failed.m4a",
                ),
            ),
        )
    )

    assert result.status == "applied"
    transcript = (
        project / "specs/failed-transcription/intake/transcript.md"
    ).read_text(encoding="utf-8")
    spec_text = (project / "specs/failed-transcription/spec.md").read_text(
        encoding="utf-8"
    )
    assert "Transcription has not been generated yet" in transcript
    assert "guardar prendas favoritas" not in transcript
    assert "guardar prendas favoritas" not in spec_text
    assert "Transcription has not been generated yet" not in spec_text
    assert any("Run transcription" in action for action in result.next_actions)


def test_new_spec_apply_no_partial_writes_when_dry_run_fails(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    service = SddSpecCreationService(projects_root=tmp_path / "projects")

    result = service.apply_new_spec(
        SpecIntakeValidationInput(
            workspace_path=str(project),
            spec_target=SpecTargetInput(mode="new_spec", spec_id="empty"),
            title_seed="Empty",
            intake_items=(),
        )
    )

    assert result.status == "blocked"
    assert "missing_intake" in result.blocked[0]
    assert result.post_apply_refresh["metadata_refresh"]["status"] == "not_run"
    assert result.post_apply_refresh["index_status"] == "not_run"
    assert not (project / "specs/empty").exists()


def _text_request(project: Path, *, spec_id: str) -> SpecIntakeValidationInput:
    return SpecIntakeValidationInput(
        workspace_path=str(project),
        spec_target=SpecTargetInput(mode="new_spec", spec_id=spec_id),
        title_seed="Product favorites",
        intake_items=(
            SpecIntakeMediaItemInput(
                kind="text",
                text="Users save favorite products.",
            ),
        ),
    )


def _client(projects_root: Path) -> TestClient:
    settings = Settings(
        codex_command="python3 tests/fixtures/fake_codex.py",
        codex_use_exec=False,
        projects_root=str(projects_root),
        chat_store_backend="memory",
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
        audio_transcription_backend="disabled",
        speech_synthesis_backend="disabled",
        feedback_source_workspace_aliases="",
    )
    return TestClient(create_app(settings))


def _write_project(tmp_path: Path) -> Path:
    project = tmp_path / "projects/demo"
    project.mkdir(parents=True)
    (project / "codex-bridge.yaml").write_text("sdd:\n  standard: workbench-sdd/v1\n")
    return project


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
