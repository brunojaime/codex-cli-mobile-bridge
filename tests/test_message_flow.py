from __future__ import annotations

import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.infrastructure.config.settings import Settings


def build_test_client() -> TestClient:
    settings = Settings(
        codex_command="python3 tests/fixtures/fake_codex.py",
        codex_use_exec=False,
        projects_root="..",
        chat_store_backend="memory",
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
    )
    app = create_app(settings)
    return TestClient(app)


def build_session_client() -> TestClient:
    settings = Settings(
        codex_command="python3 tests/fixtures/fake_codex_session.py",
        codex_use_exec=True,
        projects_root="..",
        chat_store_backend="memory",
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
    )
    app = create_app(settings)
    return TestClient(app)


def build_audio_client() -> TestClient:
    settings = Settings(
        codex_command="python3 tests/fixtures/fake_codex.py",
        codex_use_exec=False,
        projects_root="..",
        chat_store_backend="memory",
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
        audio_transcription_backend="command",
        audio_transcription_command="python3 tests/fixtures/fake_transcriber.py {filename} {file}",
    )
    app = create_app(settings)
    return TestClient(app)


def build_slow_audio_clients() -> tuple[TestClient, TestClient]:
    settings = Settings(
        codex_command="python3 tests/fixtures/fake_codex.py",
        codex_use_exec=False,
        projects_root="..",
        chat_store_backend="memory",
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
        audio_transcription_backend="command",
        audio_transcription_command=(
            "python3 tests/fixtures/fake_transcriber.py --sleep 0.4 {filename} {file}"
        ),
    )
    app = create_app(settings)
    return TestClient(app), TestClient(app)


def build_image_client() -> TestClient:
    settings = Settings(
        codex_command="python3 tests/fixtures/fake_codex_session.py",
        codex_use_exec=True,
        projects_root="..",
        chat_store_backend="memory",
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
    )
    app = create_app(settings)
    return TestClient(app)


def build_multi_attachment_client() -> TestClient:
    settings = Settings(
        codex_command="python3 tests/fixtures/fake_codex_session.py",
        codex_use_exec=True,
        projects_root="..",
        chat_store_backend="memory",
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
        audio_transcription_backend="command",
        audio_transcription_command="python3 tests/fixtures/fake_transcriber.py {filename} {file}",
    )
    app = create_app(settings)
    return TestClient(app)


def wait_for_job(client: TestClient, job_id: str, *, timeout_seconds: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout_seconds
    payload: dict | None = None

    while time.monotonic() < deadline:
        response = client.get(f"/response/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.05)

    raise AssertionError(f"Job {job_id} did not finish in time: {payload}")


def wait_for_session(
    client: TestClient,
    session_id: str,
    *,
    predicate,
    timeout_seconds: float = 5.0,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    payload: dict | None = None

    while time.monotonic() < deadline:
        response = client.get(f"/sessions/{session_id}")
        assert response.status_code == 200
        payload = response.json()
        if predicate(payload):
            return payload
        time.sleep(0.05)

    raise AssertionError(f"Session {session_id} did not reach expected state: {payload}")


def build_docx_bytes(*paragraphs: str) -> bytes:
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {paragraphs}
  </w:body>
</w:document>
""".format(
        paragraphs="".join(
            f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>" for paragraph in paragraphs
        )
    )

    with TemporaryDirectory() as temp_dir:
        archive_path = Path(temp_dir) / "sample.docx"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("[Content_Types].xml", "")
            archive.writestr("word/document.xml", document_xml)
        return archive_path.read_bytes()


def test_message_flow_returns_completed_response() -> None:
    client = build_test_client()

    create_response = client.post("/message", json={"message": "hello from test"})

    assert create_response.status_code == 202
    job_id = create_response.json()["job_id"]

    payload = wait_for_job(client, job_id)

    assert payload["status"] == "completed"
    assert payload["response"] == "Codex response: hello from test"


def test_message_flow_returns_failed_response() -> None:
    client = build_test_client()

    create_response = client.post("/message", json={"message": "fail:boom"})

    assert create_response.status_code == 202
    job_id = create_response.json()["job_id"]

    payload = wait_for_job(client, job_id)

    assert payload["status"] == "failed"
    assert payload["error"] == "boom"


def test_session_message_flow_reuses_provider_session() -> None:
    client = build_session_client()

    first_response = client.post("/message", json={"message": "first prompt"})
    assert first_response.status_code == 202
    first_job = wait_for_job(client, first_response.json()["job_id"])

    session_id = first_job["session_id"]
    session_detail = client.get(f"/sessions/{session_id}")
    assert session_detail.status_code == 200
    provider_session_id = session_detail.json()["provider_session_id"]
    assert provider_session_id is not None
    assert session_detail.json()["messages"][1]["content"].startswith("new:")

    second_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "second prompt"},
    )
    assert second_response.status_code == 202

    second_job = wait_for_job(client, second_response.json()["job_id"])
    assert second_job["provider_session_id"] == provider_session_id

    updated_session = client.get(f"/sessions/{session_id}")
    payload = updated_session.json()
    assert payload["provider_session_id"] == provider_session_id
    assert len(payload["messages"]) == 4
    assert payload["messages"][3]["content"] == f"resume:{provider_session_id}:second prompt"

    sessions_response = client.get("/sessions")
    assert sessions_response.status_code == 200
    sessions = sessions_response.json()
    assert len(sessions) == 1
    assert sessions[0]["id"] == session_id


def test_session_message_flow_serializes_overlapping_turns() -> None:
    client = build_session_client()

    first_response = client.post("/message", json={"message": "sleep:0.3:first prompt"})
    assert first_response.status_code == 202
    session_id = first_response.json()["session_id"]

    second_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "second prompt"},
    )
    assert second_response.status_code == 202

    first_job = wait_for_job(client, first_response.json()["job_id"])
    second_job = wait_for_job(client, second_response.json()["job_id"])

    assert first_job["provider_session_id"] is not None
    assert second_job["provider_session_id"] == first_job["provider_session_id"]

    updated_session = client.get(f"/sessions/{session_id}")
    payload = updated_session.json()
    assert payload["provider_session_id"] == first_job["provider_session_id"]
    assert len(payload["messages"]) == 4
    assert payload["messages"][1]["content"] == f"new:{first_job['provider_session_id']}:first prompt"
    assert payload["messages"][3]["content"] == f"resume:{first_job['provider_session_id']}:second prompt"


def test_auto_mode_chains_primary_and_reviewer_codex_turns() -> None:
    client = build_session_client()

    session_response = client.post(
        "/sessions",
        json={"title": "Auto mode"},
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    auto_mode_response = client.put(
        f"/sessions/{session_id}/auto-mode",
        json={
            "enabled": True,
            "max_turns": 1,
            "reviewer_prompt": "Write the next implementation prompt for the generator Codex.",
        },
    )
    assert auto_mode_response.status_code == 200
    assert auto_mode_response.json()["auto_mode_enabled"] is True
    assert auto_mode_response.json()["auto_max_turns"] == 1

    message_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "Build the first version"},
    )
    assert message_response.status_code == 202
    primary_job = wait_for_job(client, message_response.json()["job_id"])
    assert primary_job["conversation_kind"] == "primary"

    session_payload = wait_for_session(
        client,
        session_id,
        predicate=lambda payload: (
            len(payload["messages"]) >= 4
            and payload["auto_turn_index"] == 1
            and payload["messages"][2]["author_type"] == "reviewer_codex"
            and payload["messages"][2]["status"] == "completed"
            and payload["messages"][3]["job_status"] == "completed"
        ),
    )

    assert session_payload["provider_session_id"] is not None
    assert session_payload["reviewer_provider_session_id"] is not None
    assert (
        session_payload["provider_session_id"]
        != session_payload["reviewer_provider_session_id"]
    )
    assert session_payload["messages"][0]["author_type"] == "human"
    assert session_payload["messages"][1]["author_type"] == "assistant"
    assert session_payload["messages"][2]["role"] == "user"
    assert session_payload["messages"][3]["role"] == "assistant"


def test_workspaces_endpoint_and_session_workspace_binding() -> None:
    client = build_session_client()

    workspaces_response = client.get("/workspaces")
    assert workspaces_response.status_code == 200
    workspaces = workspaces_response.json()
    assert any(workspace["name"] == "cli-codex-project" for workspace in workspaces)

    target_workspace = next(
        workspace for workspace in workspaces if workspace["name"] == "cli-codex-project"
    )
    create_response = client.post(
        "/sessions",
        json={"title": "Fixtures chat", "workspace_path": target_workspace["path"]},
    )
    assert create_response.status_code == 201
    payload = create_response.json()
    assert payload["workspace_name"] == "cli-codex-project"
    assert payload["workspace_path"] == target_workspace["path"]


def test_job_response_exposes_phase_metadata() -> None:
    client = build_session_client()

    create_response = client.post("/message", json={"message": "phase check"})
    assert create_response.status_code == 202

    payload = wait_for_job(client, create_response.json()["job_id"])
    assert payload["status"] == "completed"
    assert payload["phase"] == "Completed"
    assert payload["latest_activity"] == "Codex returned a final response."
    assert payload["elapsed_seconds"] >= 0

    session_detail = client.get(f"/sessions/{payload['session_id']}")
    assert session_detail.status_code == 200
    assistant_message = session_detail.json()["messages"][1]
    assert assistant_message["job_status"] == "completed"
    assert assistant_message["job_phase"] == "Completed"
    assert assistant_message["job_elapsed_seconds"] >= 0


def test_sqlite_chat_store_persists_sessions_across_app_restarts() -> None:
    with TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "chat-store.sqlite3"
        settings = Settings(
            codex_command="python3 tests/fixtures/fake_codex_session.py",
            codex_use_exec=True,
            projects_root="..",
            chat_store_backend="sqlite",
            chat_store_path=str(database_path),
            execution_timeout_seconds=10,
            poll_interval_seconds=0,
        )

        first_client = TestClient(create_app(settings))
        try:
            create_response = first_client.post("/message", json={"message": "persist me"})
            assert create_response.status_code == 202
            initial_job = wait_for_job(first_client, create_response.json()["job_id"])
            session_id = initial_job["session_id"]
        finally:
            first_client.close()

        restarted_client = TestClient(create_app(settings))
        try:
            sessions_response = restarted_client.get("/sessions")
            assert sessions_response.status_code == 200
            sessions = sessions_response.json()
            assert len(sessions) == 1
            assert sessions[0]["id"] == session_id
            assert sessions[0]["last_message_preview"].startswith("new:")

            session_detail = restarted_client.get(f"/sessions/{session_id}")
            assert session_detail.status_code == 200
            payload = session_detail.json()
            assert len(payload["messages"]) == 2
            assert payload["messages"][1]["status"] == "completed"
            assert payload["messages"][1]["job_status"] == "completed"
            assert payload["messages"][1]["content"].endswith(":persist me")
        finally:
            restarted_client.close()


def test_health_endpoint_exposes_audio_transcription_status() -> None:
    client = build_test_client()

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["audio_transcription_backend"] == "auto"
    assert payload["audio_transcription_resolved_backend"] == "faster_whisper"
    assert payload["audio_transcription_ready"] is True
    assert payload["audio_transcription_detail"] == "Local faster-whisper model: small"


def test_audio_message_flow_transcribes_then_submits_prompt() -> None:
    client = build_audio_client()

    create_response = client.post(
        "/message/audio",
        files={"audio": ("voice-note.m4a", b"fake audio bytes", "audio/mp4")},
    )

    assert create_response.status_code == 202
    assert create_response.json()["transcript"] == "Transcribed audio from voice-note.m4a"

    job_id = create_response.json()["job_id"]
    payload = wait_for_job(client, job_id)

    assert payload["status"] == "completed"
    assert payload["message"] == "Transcribed audio from voice-note.m4a"
    assert payload["response"] == "Codex response: Transcribed audio from voice-note.m4a"


def test_audio_message_flow_accepts_whatsapp_style_audio_uploads() -> None:
    client = build_audio_client()

    create_response = client.post(
        "/message/audio",
        files={"audio": ("PTT-20260322-WA0001.ogg", b"fake whatsapp audio", "audio/ogg")},
    )

    assert create_response.status_code == 202
    assert create_response.json()["transcript"] == "Transcribed audio from PTT-20260322-WA0001.ogg"

    job_id = create_response.json()["job_id"]
    payload = wait_for_job(client, job_id)

    assert payload["status"] == "completed"
    assert payload["message"] == "Transcribed audio from PTT-20260322-WA0001.ogg"
    assert payload["response"] == "Codex response: Transcribed audio from PTT-20260322-WA0001.ogg"


def test_audio_transcription_does_not_block_other_requests() -> None:
    upload_client, read_client = build_slow_audio_clients()
    upload_started = threading.Event()
    upload_finished = threading.Event()

    def submit_audio() -> None:
        upload_started.set()
        response = upload_client.post(
            "/message/audio",
            files={"audio": ("voice-note.m4a", b"fake audio bytes", "audio/mp4")},
        )
        assert response.status_code == 202
        upload_finished.set()

    worker = threading.Thread(target=submit_audio, daemon=True)
    worker.start()

    assert upload_started.wait(timeout=1)
    time.sleep(0.05)

    started_at = time.monotonic()
    sessions_response = read_client.get("/sessions")
    elapsed = time.monotonic() - started_at

    assert sessions_response.status_code == 200
    assert elapsed < 0.25

    worker.join(timeout=2)
    assert upload_finished.is_set()


def test_document_message_flow_transcribes_audio_documents() -> None:
    client = build_audio_client()

    create_response = client.post(
        "/message/document",
        data={"message": "Summarize this audio"},
        files={"document": ("PTT-20260322-WA0001.ogg", b"fake whatsapp audio", "audio/ogg")},
    )

    assert create_response.status_code == 202
    payload = create_response.json()
    assert payload["document_kind"] == "audio"
    assert payload["attached_document_name"] == "PTT-20260322-WA0001.ogg"
    assert payload["transcript"] == "Transcribed audio from PTT-20260322-WA0001.ogg"

    job = wait_for_job(client, payload["job_id"])

    assert job["status"] == "completed"
    assert job["message"] == (
        "Summarize this audio\n\n[Attached audio document: PTT-20260322-WA0001.ogg]"
    )
    assert "Document kind: audio" in job["response"]
    assert "Transcript:\nTranscribed audio from PTT-20260322-WA0001.ogg" in job["response"]


def test_document_message_flow_reads_text_documents() -> None:
    client = build_test_client()

    create_response = client.post(
        "/message/document",
        data={"message": "Extract action items"},
        files={"document": ("notes.txt", b"Line one\nLine two\nLine three", "text/plain")},
    )

    assert create_response.status_code == 202
    payload = create_response.json()
    assert payload["document_kind"] == "text"
    assert payload["attached_document_name"] == "notes.txt"
    assert payload["extracted_text_preview"] == "Line one Line two Line three"

    job = wait_for_job(client, payload["job_id"])

    assert job["status"] == "completed"
    assert job["message"] == "Extract action items\n\n[Attached text document: notes.txt]"
    assert "Document name: notes.txt" in job["response"]
    assert "Extracted document text:\nLine one\nLine two\nLine three" in job["response"]


def test_document_message_flow_reads_docx_documents() -> None:
    client = build_test_client()
    docx_bytes = build_docx_bytes("First paragraph", "Second paragraph")

    create_response = client.post(
        "/message/document",
        data={"message": "Summarize this docx"},
        files={
            "document": (
                "notes.docx",
                docx_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert create_response.status_code == 202
    payload = create_response.json()
    assert payload["document_kind"] == "docx"
    assert payload["attached_document_name"] == "notes.docx"
    assert payload["extracted_text_preview"] == "First paragraph Second paragraph"

    job = wait_for_job(client, payload["job_id"])

    assert job["status"] == "completed"
    assert "Document name: notes.docx" in job["response"]
    assert "First paragraph" in job["response"]
    assert "Second paragraph" in job["response"]


def test_document_message_flow_rejects_unsupported_documents() -> None:
    client = build_test_client()

    create_response = client.post(
        "/message/document",
        files={"document": ("payload.bin", b"\x00\x01\x02", "application/octet-stream")},
    )

    assert create_response.status_code == 415
    assert "Unsupported document type" in create_response.json()["detail"]


def test_image_message_flow_attaches_image_to_codex_cli() -> None:
    client = build_image_client()

    create_response = client.post(
        "/message/image",
        data={"message": "What does this show?"},
        files={"image": ("diagram.png", b"fake image bytes", "image/png")},
    )

    assert create_response.status_code == 202
    assert create_response.json()["attached_image_name"] == "diagram.png"

    payload = wait_for_job(client, create_response.json()["job_id"])

    assert payload["status"] == "completed"
    assert payload["message"] == "What does this show?"
    assert "[images: " in payload["response"]
    assert ".png]" in payload["response"]


def test_image_message_flow_uses_default_prompt_when_message_is_blank() -> None:
    client = build_image_client()

    create_response = client.post(
        "/message/image",
        data={"message": "   "},
        files={"image": ("diagram.png", b"fake image bytes", "image/png")},
    )

    assert create_response.status_code == 202

    payload = wait_for_job(client, create_response.json()["job_id"])

    assert payload["status"] == "completed"
    assert payload["message"] == "Please analyze the attached image."
    assert "[images: " in payload["response"]
    assert ".png]" in payload["response"]


def test_attachment_batch_flow_combines_image_text_and_audio_inputs() -> None:
    client = build_multi_attachment_client()

    create_response = client.post(
        "/message/attachments",
        data={"message": "Compare everything in this batch"},
        files=[
            ("attachments", ("diagram.png", b"fake image bytes", "image/png")),
            ("attachments", ("notes.txt", b"Alpha line\nBeta line", "text/plain")),
            ("attachments", ("voice.ogg", b"fake audio bytes", "audio/ogg")),
        ],
    )

    assert create_response.status_code == 202
    payload = wait_for_job(client, create_response.json()["job_id"])

    assert payload["status"] == "completed"
    assert payload["message"] == (
        "Compare everything in this batch\n\n"
        "[Attached files]\n"
        "- image: diagram.png\n"
        "- text: notes.txt\n"
        "- audio: voice.ogg"
    )
    assert "[images: " in payload["response"]
    assert ".png]" in payload["response"]
    assert "Document name: notes.txt" in payload["response"]
    assert "Extracted document text:\nAlpha line\nBeta line" in payload["response"]
    assert "Document name: voice.ogg" in payload["response"]
    assert "Transcript:\nTranscribed audio from voice.ogg" in payload["response"]
