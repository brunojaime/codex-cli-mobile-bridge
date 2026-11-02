from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.app.api.message_outbox_routes import build_message_outbox_router
from backend.app.application.services.message_outbox_service import (
    MessageOutboxService,
    OutboxConflict,
)
from backend.app.domain.entities.job import Job


def wait_for(queue, identifier, states=("accepted",), timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        receipt = queue.get(identifier)
        if receipt["state"] in states:
            return receipt
        time.sleep(0.01)
    raise AssertionError(queue.get(identifier))


class FakeService:
    def __init__(self):
        self.jobs = {}
        self.calls = []
        self.lock = threading.Lock()
        self.fail = False

    def submit_message(
        self, message, *, session_id=None, client_submission_id, **kwargs
    ):
        if self.fail:
            raise RuntimeError("ambiguous provider failure")
        with self.lock:
            self.calls.append((session_id, message))
            job = Job(
                id=str(uuid4()), session_id=session_id or "new-chat", message=message
            )
            self.jobs[client_submission_id] = job
            return job

    def find_client_submission(self, identifier):
        return self.jobs.get(identifier)

    def _ensure_accepting_new_jobs(self):
        pass

    @staticmethod
    def _build_audio_display_message(*, message, transcript):
        return f"{message}\n{transcript}"

    @staticmethod
    def _build_audio_execution_message(*, message, transcript):
        return transcript


class Transcriber:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.failed = False
        self.calls = 0

    def transcribe(self, path, **kwargs):
        self.calls += 1
        self.started.set()
        assert self.release.wait(5)
        if self.failed:
            raise ValueError("transcription failed")
        return Path(path).read_bytes().decode()


def payload(session="a", message="hello", kind="text"):
    return {
        "kind": kind,
        "session_id": session,
        "conversation_key": session,
        "message": message,
        "filename": "note.wav",
    }


@pytest.fixture
def setup_queue(tmp_path):
    service, transcriber = FakeService(), Transcriber()
    queue = MessageOutboxService(
        database_path=str(tmp_path / "intake.db"),
        message_service=service,
        transcriber=transcriber,
    )
    yield queue, service, transcriber
    transcriber.release.set()
    queue.close()


def test_twenty_mixed_turns_keep_order_and_other_project_progresses(setup_queue):
    queue, service, transcriber = setup_queue
    queue.accept("audio-0", payload(message="0", kind="audio"), b"spoken-0")
    assert transcriber.started.wait(1)
    # First audio is still transcribing; all 19 later turns are durable.
    for i in range(1, 20):
        queue.accept(
            f"turn-{i}",
            payload(message=str(i), kind="audio" if i % 2 == 0 else "text"),
            str(i).encode() if i % 2 == 0 else None,
        )
    queue.accept("other-project", payload(session="b", message="independent"), None)
    wait_for(queue, "other-project")
    assert service.calls == [("b", "independent")]
    transcriber.release.set()
    wait_for(queue, "turn-19")
    assert [
        text.splitlines()[0] for session, text in service.calls if session == "a"
    ] == [str(i) for i in range(20)]


def test_duplicate_receipt_is_idempotent_before_and_after_completion(setup_queue):
    queue, service, transcriber = setup_queue
    data = payload(kind="audio")
    queue.accept("same-id", data, b"audio")
    assert transcriber.started.wait(1)
    for _ in range(5):
        assert queue.accept("same-id", data, b"audio")["state"] == "transcribing"
    with pytest.raises(OutboxConflict):
        queue.accept("same-id", data, b"different")
    transcriber.release.set()
    accepted = wait_for(queue, "same-id")
    assert queue.accept("same-id", data, b"audio") == accepted
    assert len(service.calls) == 1
    assert transcriber.calls == 1


def test_failure_holds_lane_until_retry_or_discard(setup_queue):
    queue, service, transcriber = setup_queue
    transcriber.failed = True
    transcriber.release.set()
    queue.accept("bad", payload(kind="audio"), b"audio")
    wait_for(queue, "bad", ("failed",))
    queue.accept("following", payload(message="later"), None)
    assert queue.get("following")["state"] == "queued"
    assert not service.calls
    transcriber.failed = False
    queue.retry("bad")
    wait_for(queue, "following")
    assert len(service.calls) == 2
    transcriber.failed = True
    queue.accept("bad-again", payload(kind="audio"), b"audio")
    wait_for(queue, "bad-again", ("failed",))
    queue.accept("after-discard", payload(message="final"), None)
    queue.discard("bad-again")
    wait_for(queue, "after-discard")


def test_restart_recovers_transcription_and_accepted_receipt(tmp_path):
    path = str(tmp_path / "queue.db")
    service, transcriber = FakeService(), Transcriber()
    transcriber.release.set()
    queue = MessageOutboxService(
        database_path=path, message_service=service, transcriber=transcriber
    )
    queue.accept("done", payload(), None)
    accepted = wait_for(queue, "done")
    # Simulate persisted stages at process death without a running worker.
    with queue._lock:
        for identifier, state in [
            ("interrupted-audio", "transcribing"),
            ("unknown", "submitting"),
        ]:
            queue._db.execute(
                "INSERT INTO message_intake(id,lane,fingerprint,payload,audio,state) VALUES(?,?,?,?,?,?)",
                (
                    identifier,
                    identifier,
                    "hash",
                    json.dumps(payload(kind="audio")),
                    b"restored",
                    state,
                ),
            )
        queue._db.commit()
    queue.close()
    restored = MessageOutboxService(
        database_path=path, message_service=service, transcriber=transcriber
    )
    try:
        assert restored.get("done") == accepted
        assert restored.get("unknown")["state"] == "uncertain"
        with pytest.raises(OutboxConflict):
            restored.retry("unknown")
        restored.wake()
        wait_for(restored, "interrupted-audio")
        assert len(service.calls) == 2
    finally:
        restored.close()


def test_crash_between_turn_save_and_receipt_commit_reconciles_without_repeat(tmp_path):
    service, transcriber = FakeService(), Transcriber()
    path = str(tmp_path / "queue.db")
    queue = MessageOutboxService(
        database_path=path, message_service=service, transcriber=transcriber
    )
    queue.accept("saved-turn", payload(), None)
    receipt = wait_for(queue, "saved-turn")
    with queue._lock:
        queue._db.execute(
            "UPDATE message_intake SET state='submitting',result=NULL WHERE id='saved-turn'"
        )
        queue._db.commit()
    queue.close()
    restored = MessageOutboxService(
        database_path=path, message_service=service, transcriber=transcriber
    )
    try:
        assert restored.get("saved-turn") == receipt
        assert len(service.calls) == 1
    finally:
        restored.close()


def test_http_accepts_before_transcription_and_legacy_endpoint_is_independent(
    setup_queue,
):
    queue, service, transcriber = setup_queue
    container = SimpleNamespace(
        message_outbox_service=queue,
        settings=SimpleNamespace(audio_max_upload_bytes=64),
    )

    async def validate(*args, **kwargs):
        return None

    app = FastAPI()
    app.include_router(build_message_outbox_router(lambda: container, validate))
    with TestClient(app) as client:
        identifier = "mobile-submission-123"
        response = client.post(
            f"/message-outbox/{identifier}",
            data={"payload_json": json.dumps(payload(kind="audio"))},
            files={"audio": ("note.wav", b"spoken", "audio/wav")},
        )
        assert response.status_code == 202
        assert transcriber.started.wait(1)
        assert (
            client.get(f"/message-outbox/{identifier}").json()["state"]
            == "transcribing"
        )
        assert (
            client.post(
                "/message-outbox/mobile-submission-large",
                data={"payload_json": json.dumps(payload(kind="audio"))},
                files={"audio": ("note.wav", b"x" * 65, "audio/wav")},
            ).status_code
            == 413
        )
        assert (
            client.post(
                "/message-outbox/mobile-submission-empty",
                data={"payload_json": json.dumps(payload(message=""))},
            ).status_code
            == 422
        )
        assert client.get("/message-outbox/missing").status_code == 404
        transcriber.release.set()
        receipt = wait_for(queue, identifier)
        replay = client.post(
            f"/message-outbox/{identifier}",
            data={"payload_json": json.dumps(payload(kind="audio"))},
            files={"audio": ("note.wav", b"spoken", "audio/wav")},
        )
        assert replay.json() == receipt
        assert len(service.calls) == 1


def test_real_message_service_persists_submission_marker_and_options(tmp_path):
    from backend.app.application.services.message_service import MessageService
    from backend.app.infrastructure.execution.local_provider import (
        LocalExecutionProvider,
    )
    from backend.app.infrastructure.persistence.sqlite_chat_repository import (
        SqliteChatRepository,
    )
    from backend.app.infrastructure.transcription.disabled_transcriber import (
        DisabledAudioTranscriber,
    )
    from backend.app.domain.entities.codex_options import CodexRunOptions

    repository = SqliteChatRepository(
        database_path=str(tmp_path / "chat.db"), projects_root=str(tmp_path.parent)
    )
    provider = LocalExecutionProvider(
        command=f"python3 {Path('tests/fixtures/fake_codex.py').resolve()}",
        use_exec_mode=False,
        workdir=str(tmp_path),
        timeout_seconds=5,
    )
    service = MessageService(
        repository=repository,
        execution_provider=provider,
        default_workspace_path=str(tmp_path),
        audio_transcriber=DisabledAudioTranscriber(),
    )
    session = service.create_session(title="test", workspace_path=str(tmp_path))
    job = service.submit_message(
        "hello from queue",
        session_id=session.id,
        client_submission_id="real-client-submission",
        codex_options=CodexRunOptions(search_enabled=True),
    )
    assert service.find_client_submission("real-client-submission").id == job.id
    # Open the saved repository again to verify the marker is durable.
    restored_repository = SqliteChatRepository(
        database_path=str(tmp_path / "chat.db"), projects_root=str(tmp_path.parent)
    )
    assert (
        restored_repository.get_message(job.user_message_id).content
        == "hello from queue"
    )
    assert service.find_client_submission("another-submission") is None


def test_app_routes_use_real_message_service_and_compatible_legacy_endpoint(tmp_path):
    from backend.app.api.routes import get_container
    from backend.app.infrastructure.config.settings import Settings
    from backend.app.main import create_app

    project = tmp_path / "project"
    project.mkdir()
    settings = Settings(
        chat_store_backend="memory",
        bridge_environment="dev",
        dev_pipeline_enabled=False,
        projects_root=str(tmp_path),
        codex_workdir=str(project),
        codex_command=f"python3 {Path('tests/fixtures/fake_codex.py').resolve()}",
        codex_use_exec=False,
        audio_transcription_backend="disabled",
        speech_synthesis_backend="disabled",
        execution_timeout_seconds=5,
    )
    app = create_app(settings)
    container = app.dependency_overrides[get_container]()
    transcriber = Transcriber()
    container.audio_transcriber = transcriber
    with TestClient(app) as client:
        session = client.post(
            "/sessions", json={"workspace_path": str(project)}
        ).json()["id"]
        data = payload(session=session, kind="audio")
        data["workspace_path"] = str(project)
        identifier = "real-audio-submission-123"
        response = client.post(
            f"/api/v1/message-outbox/{identifier}",
            data={"payload_json": json.dumps(data)},
            files={"audio": ("voice.wav", b"real flow transcript", "audio/wav")},
        )
        assert response.status_code == 202
        assert transcriber.started.wait(1)
        assert container.message_service.find_client_submission(identifier) is None
        transcriber.release.set()
        receipt = wait_for(container.message_outbox_service, identifier)
        job = container.message_service.find_client_submission(identifier)
        assert receipt["job"]["job_id"] == job.id
        assert job.session_id == session
        assert "real flow transcript" in job.message
        assert (
            client.post(
                "/message", json={"session_id": session, "message": "legacy text"}
            ).status_code
            == 202
        )
        assert client.get(f"/message-outbox/{identifier}").json() == receipt


def test_ambiguous_submission_with_unavailable_repository_stops_without_repeat(
    setup_queue,
):
    queue, service, _ = setup_queue

    def unavailable_lookup(_):
        raise RuntimeError("repository unavailable")

    def interrupted_submission(*args, **kwargs):
        service.find_client_submission = unavailable_lookup
        raise RuntimeError("connection lost during provider submission")

    service.submit_message = interrupted_submission
    queue.accept("ambiguous-delivery", payload(), None)
    wait_for(queue, "ambiguous-delivery", ("uncertain",))
    with pytest.raises(OutboxConflict):
        queue.retry("ambiguous-delivery")
    assert service.calls == []
