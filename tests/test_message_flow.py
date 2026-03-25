from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

from fastapi.testclient import TestClient
import pytest

from backend.app.application.services.message_service import MessageService
from backend.app.api.routes import get_container
from backend.app.domain.entities.agent_configuration import (
    AgentConfiguration,
    AgentDisplayMode,
    AgentId,
    AgentPreset,
    AgentTriggerSource,
    AgentType,
    AgentVisibilityMode,
)
from backend.app.domain.entities.agent_profile import AgentProfile
from backend.app.domain.entities.chat_message import (
    can_launch_reserved_follow_up,
    ChatMessage,
    ChatMessageAuthorType,
    ChatMessageReasonCode,
    MessageRecoveryAction,
    ChatMessageRole,
    ChatMessageStatus,
)
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.job import JobConversationKind, JobStatus
from backend.app.infrastructure.execution.base import ExecutionProvider, ExecutionSnapshot
from backend.app.infrastructure.persistence.in_memory_chat_repository import InMemoryChatRepository
from backend.app.infrastructure.persistence.sqlite_chat_repository import SqliteChatRepository
from backend.app.infrastructure.transcription.disabled_transcriber import DisabledAudioTranscriber
from backend.app.main import create_app
from backend.app.infrastructure.config.settings import Settings
from backend.app.domain.repositories.chat_repository import PersistenceDataError


def build_test_client() -> TestClient:
    settings = Settings(
        codex_command="python3 tests/fixtures/fake_codex.py",
        codex_use_exec=False,
        projects_root="..",
        chat_store_backend="memory",
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
        audio_transcription_backend="auto",
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
        audio_transcription_backend="auto",
    )
    app = create_app(settings)
    return TestClient(app)


def build_session_client_with_container():
    settings = Settings(
        codex_command="python3 tests/fixtures/fake_codex_session.py",
        codex_use_exec=True,
        projects_root="..",
        chat_store_backend="memory",
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
        audio_transcription_backend="auto",
    )
    app = create_app(settings)
    container = app.dependency_overrides[get_container]()
    return TestClient(app), container


def build_sqlite_session_client_with_container(
    database_path: str,
) -> tuple[TestClient, object]:
    settings = Settings(
        codex_command="python3 tests/fixtures/fake_codex_session.py",
        codex_use_exec=True,
        projects_root="..",
        chat_store_backend="sqlite",
        chat_store_path=database_path,
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
        audio_transcription_backend="auto",
    )
    app = create_app(settings)
    container = app.dependency_overrides[get_container]()
    return TestClient(app), container


class _ControlledExecutionProvider(ExecutionProvider):
    def __init__(self) -> None:
        self._snapshots: dict[str, ExecutionSnapshot] = {}
        self._job_counter = 0
        self._lock = threading.RLock()

    def execute(
        self,
        message: str,
        *,
        image_paths: list[str] | None = None,
        cleanup_paths: list[str] | None = None,
        provider_session_id: str | None = None,
        serial_key: str | None = None,
        submission_token: str | None = None,
        workdir: str | None = None,
    ) -> str:
        with self._lock:
            self._job_counter += 1
            job_id = f"job-{self._job_counter}"
            self._snapshots[job_id] = ExecutionSnapshot(
                job_id=job_id,
                status=JobStatus.PENDING,
                provider_session_id=provider_session_id or f"thread-{job_id}",
                phase="Queued",
                latest_activity="Controlled provider queued the job.",
            )
            return job_id

    def finish_job(
        self,
        job_id: str,
        *,
        status: JobStatus,
        response: str | None = None,
        error: str | None = None,
        phase: str | None = None,
        latest_activity: str | None = None,
    ) -> None:
        with self._lock:
            current = self._snapshots[job_id]
            self._snapshots[job_id] = ExecutionSnapshot(
                job_id=job_id,
                status=status,
                response=response,
                error=error,
                provider_session_id=current.provider_session_id,
                phase=phase or (
                    "Completed"
                    if status == JobStatus.COMPLETED
                    else "Cancelled"
                    if status == JobStatus.CANCELLED
                    else "Failed"
                ),
                latest_activity=latest_activity or (
                    "Controlled provider completed the job."
                    if status == JobStatus.COMPLETED
                    else "Controlled provider cancelled the job."
                    if status == JobStatus.CANCELLED
                    else "Controlled provider failed the job."
                ),
            )

    def complete_job(self, job_id: str, *, response: str) -> None:
        self.finish_job(job_id, status=JobStatus.COMPLETED, response=response)

    def fail_job(self, job_id: str, *, error: str) -> None:
        self.finish_job(job_id, status=JobStatus.FAILED, error=error)

    def get_status(self, job_id: str) -> JobStatus:
        with self._lock:
            return self._snapshots[job_id].status

    def get_result(self, job_id: str) -> str | None:
        with self._lock:
            return self._snapshots[job_id].response

    def get_error(self, job_id: str) -> str | None:
        with self._lock:
            return self._snapshots[job_id].error

    def has_job(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._snapshots

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            current = self._snapshots.get(job_id)
            if current is None or current.status.is_terminal:
                return False
        self.finish_job(job_id, status=JobStatus.CANCELLED, error="Cancelled by user.")
        return True

    def get_snapshot(self, job_id: str) -> ExecutionSnapshot:
        with self._lock:
            return self._snapshots[job_id]

    def watch_job(self, job_id: str, on_change) -> None:
        return None

    def get_provider_session_id(self, job_id: str) -> str | None:
        with self._lock:
            return self._snapshots[job_id].provider_session_id

    def get_phase(self, job_id: str) -> str | None:
        with self._lock:
            return self._snapshots[job_id].phase

    def get_latest_activity(self, job_id: str) -> str | None:
        with self._lock:
            return self._snapshots[job_id].latest_activity


class _WatchedControlledExecutionProvider(_ControlledExecutionProvider):
    def __init__(self) -> None:
        super().__init__()
        self._subscribers: dict[str, list] = {}

    def _notify(self, job_id: str) -> None:
        with self._lock:
            listeners = list(self._subscribers.get(job_id, ()))
            snapshot = self._snapshots[job_id]
        for listener in listeners:
            listener(snapshot)

    def watch_job(self, job_id: str, on_change):
        with self._lock:
            self._subscribers.setdefault(job_id, []).append(on_change)
            snapshot = self._snapshots.get(job_id)

        if snapshot is not None:
            on_change(snapshot)

        def unsubscribe() -> None:
            with self._lock:
                listeners = self._subscribers.get(job_id)
                if listeners is None:
                    return
                try:
                    listeners.remove(on_change)
                except ValueError:
                    return
                if not listeners:
                    self._subscribers.pop(job_id, None)

        return unsubscribe

    def complete_job_with_notification_gate(
        self,
        job_id: str,
        *,
        response: str,
        ready_event: threading.Event,
        release_event: threading.Event,
    ) -> None:
        super().complete_job(job_id, response=response)
        ready_event.set()
        release_event.wait(timeout=1)
        self._notify(job_id)

    def complete_job(self, job_id: str, *, response: str) -> None:
        super().complete_job(job_id, response=response)
        self._notify(job_id)

    def fail_job(self, job_id: str, *, error: str) -> None:
        super().fail_job(job_id, error=error)
        self._notify(job_id)

    def cancel_job(self, job_id: str) -> bool:
        cancelled = super().cancel_job(job_id)
        if cancelled:
            self._notify(job_id)
        return cancelled


class _BarrierLaunchMessageService(MessageService):
    def __init__(
        self,
        *,
        barrier_agent_id: AgentId,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._barrier_agent_id = barrier_agent_id
        self._follow_up_barrier = threading.Barrier(2)

    def _launch_reserved_follow_up(
        self,
        *,
        session: ChatSession,
        message: ChatMessage,
        display_message: str,
        execution_message: str,
        user_message_id: str | None,
        conversation_kind: JobConversationKind,
        agent_id: AgentId,
        agent_type: AgentType,
        trigger_source: AgentTriggerSource,
        run_id: str,
    ) -> None:
        if not can_launch_reserved_follow_up(message):
            return
        if agent_id == self._barrier_agent_id:
            try:
                self._follow_up_barrier.wait(timeout=0.2)
            except threading.BrokenBarrierError:
                pass
        super()._launch_reserved_follow_up(
            session=session,
            message=message,
            display_message=display_message,
            execution_message=execution_message,
            user_message_id=user_message_id,
            conversation_kind=conversation_kind,
            agent_id=agent_id,
            agent_type=agent_type,
            trigger_source=trigger_source,
            run_id=run_id,
        )


def _build_controlled_message_service(
    projects_root: str,
    *,
    barrier_agent_id: AgentId,
) -> tuple[_BarrierLaunchMessageService, _ControlledExecutionProvider, InMemoryChatRepository]:
    repository = InMemoryChatRepository(projects_root=projects_root)
    provider = _ControlledExecutionProvider()
    service = _BarrierLaunchMessageService(
        repository=repository,
        execution_provider=provider,
        default_workspace_path=projects_root,
        audio_transcriber=DisabledAudioTranscriber(),
        barrier_agent_id=barrier_agent_id,
    )
    return service, provider, repository


def _build_watched_controlled_message_service(
    projects_root: str,
    *,
    barrier_agent_id: AgentId,
) -> tuple[_BarrierLaunchMessageService, _WatchedControlledExecutionProvider, InMemoryChatRepository]:
    repository = InMemoryChatRepository(projects_root=projects_root)
    provider = _WatchedControlledExecutionProvider()
    service = _BarrierLaunchMessageService(
        repository=repository,
        execution_provider=provider,
        default_workspace_path=projects_root,
        audio_transcriber=DisabledAudioTranscriber(),
        barrier_agent_id=barrier_agent_id,
    )
    return service, provider, repository


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
        audio_transcription_backend="auto",
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


def wait_for_repository_session(
    repository,
    session_id: str,
    *,
    predicate,
    timeout_seconds: float = 5.0,
):
    deadline = time.monotonic() + timeout_seconds
    last_state: tuple[object | None, list[object], dict[str, object]] | None = None

    while time.monotonic() < deadline:
        session = repository.get_session(session_id)
        messages = repository.list_messages(session_id)
        jobs_by_id = {
            message.job_id: repository.get_job(message.job_id)
            for message in messages
            if getattr(message, "job_id", None)
        }
        last_state = (session, messages, jobs_by_id)
        if predicate(session, messages, jobs_by_id):
            return session, messages, jobs_by_id
        time.sleep(0.05)

    raise AssertionError(
        f"Session {session_id} did not reach expected repository state: {last_state}"
    )


def run_concurrent_get_job(service: MessageService, job_id: str, *, workers: int = 2) -> None:
    errors: list[Exception] = []
    start_barrier = threading.Barrier(workers)

    def worker() -> None:
        try:
            start_barrier.wait(timeout=1)
            service.get_job(job_id)
        except threading.BrokenBarrierError as exc:
            errors.append(exc)
        except Exception as exc:  # pragma: no cover - surfaced via assertion
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, daemon=True)
        for _ in range(workers)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []


def wait_for_background_terminal_convergence(
    service: MessageService,
    repository,
    *,
    session_id: str,
    job_id: str,
    expected_status: JobStatus,
    timeout_seconds: float = 5.0,
):
    deadline = time.monotonic() + timeout_seconds
    last_state: tuple[object | None, list[object], object | None] | None = None

    while time.monotonic() < deadline:
        session = repository.get_session(session_id)
        messages = repository.list_messages(session_id)
        job = repository.get_job(job_id)
        last_state = (session, messages, job)
        if (
            session is not None
            and job is not None
            and job.status == expected_status
            and job.auto_chain_processed is True
            and session.active_agent_run_id is None
            and service._job_monitor_unsubscribes == {}
            and service._terminal_job_locks == {}
        ):
            return session, messages, job
        time.sleep(0.05)

    raise AssertionError(
        f"Job {job_id} did not converge in the background: {last_state}"
    )


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


def list_agent_profiles(client: TestClient) -> list[dict]:
    response = client.get("/agent-profiles")
    assert response.status_code == 200
    return response.json()


def build_agent_configuration_payload(
    *,
    preset: str = "triad",
    display_mode: str = "show_all",
    reviewer_enabled: bool = True,
    summary_enabled: bool = True,
    reviewer_visibility: str = "collapsed",
) -> dict:
    return {
        "preset": preset,
        "display_mode": display_mode,
        "agents": [
            {
                "agent_id": "generator",
                "agent_type": "generator",
                "enabled": True,
                "label": "Generator",
                "prompt": "You are the primary builder Codex.",
                "visibility": "visible",
                "max_turns": 2,
            },
            {
                "agent_id": "reviewer",
                "agent_type": "reviewer",
                "enabled": reviewer_enabled,
                "label": "Reviewer",
                "prompt": "Return the next implementation prompt for the generator.",
                "visibility": reviewer_visibility,
                "max_turns": 1,
            },
            {
                "agent_id": "summary",
                "agent_type": "summary",
                "enabled": summary_enabled,
                "label": "Summary",
                "prompt": "Summarize the run for the user.",
                "visibility": "visible",
                "max_turns": 1,
            },
        ],
    }


def build_supervisor_configuration_payload(
    *,
    supervisor_member_ids: list[str] | None = None,
) -> dict:
    selected_members = supervisor_member_ids or ["qa", "ux", "senior_engineer"]

    def specialist_enabled(agent_id: str) -> bool:
        return agent_id in selected_members

    return {
        "preset": "supervisor",
        "display_mode": "collapse_specialists",
        "supervisor_member_ids": selected_members,
        "agents": [
            {
                "agent_id": "generator",
                "agent_type": "generator",
                "enabled": False,
                "label": "Generator",
                "prompt": "You are the primary builder Codex.",
                "visibility": "visible",
                "max_turns": 0,
            },
            {
                "agent_id": "reviewer",
                "agent_type": "reviewer",
                "enabled": False,
                "label": "Reviewer",
                "prompt": "Return the next implementation prompt for the generator.",
                "visibility": "collapsed",
                "max_turns": 0,
            },
            {
                "agent_id": "summary",
                "agent_type": "summary",
                "enabled": False,
                "label": "Summary",
                "prompt": "Summarize the run for the user.",
                "visibility": "visible",
                "max_turns": 0,
            },
            {
                "agent_id": "supervisor",
                "agent_type": "supervisor",
                "enabled": True,
                "label": "Supervisor",
                "prompt": (
                    "You are the Supervisor Codex. Own the project plan, decide "
                    "which specialist should act next, and keep the work moving."
                ),
                "visibility": "visible",
                "max_turns": 4,
            },
            {
                "agent_id": "qa",
                "agent_type": "qa",
                "enabled": specialist_enabled("qa"),
                "label": "QA",
                "prompt": "You are QA Codex. Validate correctness and risk.",
                "visibility": "collapsed",
                "max_turns": 2 if specialist_enabled("qa") else 0,
            },
            {
                "agent_id": "ux",
                "agent_type": "ux",
                "enabled": specialist_enabled("ux"),
                "label": "UX",
                "prompt": "You are UX Codex. Review flow and usability.",
                "visibility": "collapsed",
                "max_turns": 2 if specialist_enabled("ux") else 0,
            },
            {
                "agent_id": "senior_engineer",
                "agent_type": "senior_engineer",
                "enabled": specialist_enabled("senior_engineer"),
                "label": "Senior Engineer",
                "prompt": "You are Senior Engineer Codex. Review architecture and risk.",
                "visibility": "collapsed",
                "max_turns": 2 if specialist_enabled("senior_engineer") else 0,
            },
        ],
    }


def build_agent_configuration_domain(
    *,
    preset: str = "triad",
    display_mode: str = "show_all",
    reviewer_enabled: bool = True,
    summary_enabled: bool = True,
    reviewer_visibility: str = "collapsed",
) -> AgentConfiguration:
    payload = build_agent_configuration_payload(
        preset=preset,
        display_mode=display_mode,
        reviewer_enabled=reviewer_enabled,
        summary_enabled=summary_enabled,
        reviewer_visibility=reviewer_visibility,
    )
    return AgentConfiguration.from_dict(
        {
            "preset": payload["preset"],
            "display_mode": payload["display_mode"],
            "agents": {
                agent["agent_id"]: agent
                for agent in payload["agents"]
            },
        }
    )
def test_message_flow_returns_completed_response() -> None:
    client = build_test_client()

    create_response = client.post("/message", json={"message": "hello from test"})

    assert create_response.status_code == 202
    accepted_payload = create_response.json()
    assert accepted_payload["agent_id"] == "generator"
    assert accepted_payload["agent_type"] == "generator"
    job_id = accepted_payload["job_id"]

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


def test_session_message_flow_serializes_three_overlapping_turns() -> None:
    client = build_session_client()

    first_response = client.post("/message", json={"message": "sleep:0.3:first prompt"})
    assert first_response.status_code == 202
    session_id = first_response.json()["session_id"]

    second_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "second prompt"},
    )
    third_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "third prompt"},
    )
    assert second_response.status_code == 202
    assert third_response.status_code == 202

    first_job = wait_for_job(client, first_response.json()["job_id"])
    second_job = wait_for_job(client, second_response.json()["job_id"])
    third_job = wait_for_job(client, third_response.json()["job_id"])

    assert second_job["provider_session_id"] == first_job["provider_session_id"]
    assert third_job["provider_session_id"] == first_job["provider_session_id"]

    payload = client.get(f"/sessions/{session_id}").json()
    assert len(payload["messages"]) == 6
    assert payload["messages"][1]["content"] == f"new:{first_job['provider_session_id']}:first prompt"
    assert payload["messages"][3]["content"] == f"resume:{first_job['provider_session_id']}:second prompt"
    assert payload["messages"][5]["content"] == f"resume:{first_job['provider_session_id']}:third prompt"


def test_supervisor_preset_routes_work_through_selected_specialists() -> None:
    client = build_session_client()

    seed_response = client.post("/message", json={"message": "seed session"})
    assert seed_response.status_code == 202
    seed_job = wait_for_job(client, seed_response.json()["job_id"])
    session_id = seed_job["session_id"]

    config_response = client.put(
        f"/sessions/{session_id}/agents",
        json=build_supervisor_configuration_payload(),
    )
    assert config_response.status_code == 200
    assert config_response.json()["agent_configuration"]["preset"] == "supervisor"

    create_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "Plan and run the supervisor workflow."},
    )
    assert create_response.status_code == 202
    assert create_response.json()["agent_id"] == "supervisor"

    payload = wait_for_session(
        client,
        session_id,
        predicate=lambda session_payload: (
            session_payload["active_agent_run_id"] is None
            and any(message["agent_id"] == "qa" for message in session_payload["messages"])
            and any(
                message["agent_id"] == "senior_engineer"
                for message in session_payload["messages"]
            )
            and any(
                message["agent_id"] == "supervisor"
                and "Next agent: qa" in message["content"]
                for message in session_payload["messages"]
            )
        ),
    )

    messages = payload["messages"]
    assert any(message["agent_id"] == "supervisor" for message in messages)
    assert any(message["agent_id"] == "senior_engineer" for message in messages)
    assert any(message["agent_id"] == "qa" for message in messages)
    assert all(message["agent_id"] != "ux" for message in messages[2:])


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
    assert auto_mode_response.json()["reviewer_state"] == "idle"

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
    assert session_payload["reviewer_state"] == "completed"
    assert session_payload["messages"][0]["author_type"] == "human"
    assert session_payload["messages"][1]["author_type"] == "assistant"
    assert session_payload["messages"][2]["role"] == "user"
    assert session_payload["messages"][3]["role"] == "assistant"

    summaries = client.get("/sessions")
    assert summaries.status_code == 200
    summary_payload = next(
        item for item in summaries.json() if item["id"] == session_id
    )
    assert summary_payload["reviewer_state"] == "completed"


def test_auto_mode_configuration_isolated_per_chat() -> None:
    client = build_session_client()

    first_session = client.post("/sessions", json={"title": "Auto A"})
    second_session = client.post("/sessions", json={"title": "Auto B"})
    assert first_session.status_code == 201
    assert second_session.status_code == 201
    first_session_id = first_session.json()["id"]
    second_session_id = second_session.json()["id"]

    auto_mode_response = client.put(
        f"/sessions/{first_session_id}/auto-mode",
        json={
            "enabled": True,
            "max_turns": 1,
            "reviewer_prompt": "Review only in chat A",
        },
    )
    assert auto_mode_response.status_code == 200
    assert auto_mode_response.json()["auto_mode_enabled"] is True

    first_payload = client.get(f"/sessions/{first_session_id}").json()
    second_payload = client.get(f"/sessions/{second_session_id}").json()

    assert first_payload["auto_mode_enabled"] is True
    assert first_payload["agent_configuration"]["preset"] == "review"
    assert second_payload["auto_mode_enabled"] is False
    assert second_payload["agent_configuration"]["preset"] == "solo"


def test_agent_configuration_isolated_per_chat_sessions() -> None:
    client = build_session_client()

    first_session = client.post("/sessions", json={"title": "Configured chat"})
    second_session = client.post("/sessions", json={"title": "Default chat"})
    assert first_session.status_code == 201
    assert second_session.status_code == 201
    first_session_id = first_session.json()["id"]
    second_session_id = second_session.json()["id"]

    config_response = client.put(
        f"/sessions/{first_session_id}/agents",
        json=build_agent_configuration_payload(
            preset="triad",
            display_mode="summary_only",
            reviewer_visibility="hidden",
        ),
    )
    assert config_response.status_code == 200

    default_session_message = client.post(
        f"/sessions/{second_session_id}/messages",
        json={"message": "Only the generator should answer here"},
    )
    assert default_session_message.status_code == 202
    wait_for_job(client, default_session_message.json()["job_id"])

    second_payload = client.get(f"/sessions/{second_session_id}").json()
    assert second_payload["agent_configuration"]["preset"] == "solo"
    assert len(second_payload["messages"]) == 2
    assert all(
        message["agent_id"] != "reviewer" and message["agent_id"] != "summary"
        for message in second_payload["messages"]
    )

    first_payload = client.get(f"/sessions/{first_session_id}").json()
    assert first_payload["agent_configuration"]["preset"] == "triad"
    assert first_payload["agent_configuration"]["display_mode"] == "summary_only"


def test_agent_configuration_route_rejects_invalid_payload() -> None:
    client = build_session_client()
    session_response = client.post("/sessions", json={"title": "Agents"})
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    invalid_payload = build_agent_configuration_payload()
    invalid_payload["agents"] = invalid_payload["agents"][:2]

    response = client.put(f"/sessions/{session_id}/agents", json=invalid_payload)

    assert response.status_code == 422

    blank_prompt_payload = build_agent_configuration_payload()
    blank_prompt_payload["agents"][1]["prompt"] = "   "
    response = client.put(f"/sessions/{session_id}/agents", json=blank_prompt_payload)
    assert response.status_code == 422


def test_agent_configuration_from_dict_rejects_malformed_payloads() -> None:
    with pytest.raises(ValueError):
        AgentConfiguration.from_dict(
            {
                "preset": "triad",
                "display_mode": "show_all",
                "agents": {
                    "generator": {
                        "agent_id": "generator",
                        "agent_type": "generator",
                        "enabled": "true",
                        "label": "Generator",
                        "prompt": "Build things",
                        "visibility": "visible",
                        "max_turns": 2,
                    }
                },
            }
        )

    with pytest.raises(ValueError):
        AgentConfiguration.from_dict(
            {
                "preset": "triad",
                "display_mode": "show_all",
                "agents": {
                    "generator": {
                        "agent_id": "generator",
                        "agent_type": "generator",
                        "enabled": True,
                        "label": "Generator",
                        "prompt": "Build things",
                        "visibility": "visible",
                        "max_turns": 2,
                    },
                    "reviewer": {
                        "agent_id": "reviewer",
                        "agent_type": "reviewer",
                        "enabled": False,
                        "label": "Reviewer",
                        "prompt": "Review things",
                        "visibility": "collapsed",
                        "max_turns": 1,
                    },
                    "summary": {
                        "agent_id": "summary",
                        "agent_type": "summary",
                        "enabled": False,
                        "label": "Summary",
                        "prompt": "Summarize things",
                        "visibility": "visible",
                        "max_turns": 1,
                    },
                    "rogue": {},
                },
            }
        )


def test_agent_chain_persists_agent_configuration_and_message_metadata() -> None:
    client = build_session_client()
    session_response = client.post("/sessions", json={"title": "Triad"})
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    config_response = client.put(
        f"/sessions/{session_id}/agents",
        json=build_agent_configuration_payload(display_mode="summary_only"),
    )
    assert config_response.status_code == 200
    assert config_response.json()["agent_configuration"]["display_mode"] == "summary_only"

    message_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "Implement the first draft"},
    )
    assert message_response.status_code == 202
    primary_job = wait_for_job(client, message_response.json()["job_id"])
    run_id = primary_job["run_id"]
    assert run_id is not None

    session_payload = wait_for_session(
        client,
        session_id,
        predicate=lambda payload: (
            len(payload["messages"]) >= 5
            and payload["messages"][-1]["agent_id"] == "summary"
            and payload["messages"][-1]["job_status"] == "completed"
        ),
    )

    messages = session_payload["messages"]
    assert messages[0]["agent_id"] == "user"
    assert messages[0]["agent_type"] == "human"
    assert messages[0]["trigger_source"] == "user"
    assert messages[1]["agent_id"] == "generator"
    assert messages[2]["agent_id"] == "reviewer"
    assert messages[2]["visibility"] == "collapsed"
    assert messages[-1]["agent_id"] == "summary"
    assert messages[-1]["agent_type"] == "summary"
    assert all(message["run_id"] == run_id for message in messages if message["run_id"] is not None)


def test_duplicate_session_reads_do_not_duplicate_agent_follow_ups() -> None:
    client = build_session_client()
    session_response = client.post("/sessions", json={"title": "Idempotent"})
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    config_response = client.put(
        f"/sessions/{session_id}/agents",
        json=build_agent_configuration_payload(
            preset="review",
            summary_enabled=False,
        ),
    )
    assert config_response.status_code == 200

    message_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "Build the idempotent flow"},
    )
    assert message_response.status_code == 202
    primary_job = wait_for_job(client, message_response.json()["job_id"])
    run_id = primary_job["run_id"]

    wait_for_session(
        client,
        session_id,
        predicate=lambda payload: (
            len(payload["messages"]) == 4
            and payload["messages"][2]["agent_id"] == "reviewer"
            and payload["messages"][3]["agent_id"] == "generator"
            and payload["messages"][3]["job_status"] == "completed"
        ),
    )

    for _ in range(4):
        session_detail = client.get(f"/sessions/{session_id}")
        assert session_detail.status_code == 200

    final_payload = client.get(f"/sessions/{session_id}").json()
    assert len(final_payload["messages"]) == 4
    reviewer_messages = [
        message
        for message in final_payload["messages"]
        if message["run_id"] == run_id and message["agent_id"] == "reviewer"
    ]
    assert len(reviewer_messages) == 1


def test_stale_run_id_does_not_schedule_follow_ups_after_new_user_turn() -> None:
    client = build_session_client()
    session_response = client.post("/sessions", json={"title": "Interrupted"})
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    config_response = client.put(
        f"/sessions/{session_id}/agents",
        json=build_agent_configuration_payload(
            preset="review",
            summary_enabled=False,
        ),
    )
    assert config_response.status_code == 200

    first_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "sleep:0.3:first run"},
    )
    assert first_response.status_code == 202

    second_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "second run"},
    )
    assert second_response.status_code == 202

    first_job = wait_for_job(client, first_response.json()["job_id"])
    second_job = wait_for_job(client, second_response.json()["job_id"])

    session_payload = wait_for_session(
        client,
        session_id,
        predicate=lambda payload: any(
            message["run_id"] == second_job["run_id"] and message["agent_id"] == "reviewer"
            for message in payload["messages"]
        ),
    )

    assert not any(
        message["run_id"] == first_job["run_id"] and message["agent_id"] == "reviewer"
        for message in session_payload["messages"]
    )
    assert any(
        message["run_id"] == second_job["run_id"] and message["agent_id"] == "reviewer"
        for message in session_payload["messages"]
    )


def test_summary_runs_directly_when_reviewer_is_disabled() -> None:
    client = build_session_client()
    session_response = client.post("/sessions", json={"title": "Summary only"})
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    config_response = client.put(
        f"/sessions/{session_id}/agents",
        json=build_agent_configuration_payload(
            preset="triad",
            reviewer_enabled=False,
            summary_enabled=True,
        ),
    )
    assert config_response.status_code == 200

    message_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "Summarize directly"},
    )
    assert message_response.status_code == 202

    session_payload = wait_for_session(
        client,
        session_id,
        predicate=lambda payload: (
            any(message["agent_id"] == "summary" for message in payload["messages"])
            and not any(message["agent_id"] == "reviewer" for message in payload["messages"])
        ),
    )

    assert session_payload["agent_configuration"]["preset"] == "triad"
    assert session_payload["messages"][-1]["agent_id"] == "summary"
    assert all(message["agent_id"] != "reviewer" for message in session_payload["messages"])


def test_agent_endpoint_round_trip_drives_full_triad_chain_and_persists_final_state() -> None:
    client = build_session_client()
    session_response = client.post("/sessions", json={"title": "Full triad"})
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    config_response = client.put(
        f"/sessions/{session_id}/agents",
        json=build_agent_configuration_payload(
            preset="triad",
            display_mode="summary_only",
            reviewer_visibility="hidden",
        ),
    )
    assert config_response.status_code == 200
    assert config_response.json()["agent_configuration"]["display_mode"] == "summary_only"

    message_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "Ship the triad flow"},
    )
    assert message_response.status_code == 202
    first_job = wait_for_job(client, message_response.json()["job_id"])

    session_payload = wait_for_session(
        client,
        session_id,
        predicate=lambda payload: (
            payload["active_agent_run_id"] is None
            and any(message["agent_id"] == "summary" for message in payload["messages"])
        ),
    )

    sessions_payload = client.get("/sessions")
    assert sessions_payload.status_code == 200
    summary_entry = next(
        session for session in sessions_payload.json() if session["id"] == session_id
    )

    assert summary_entry["agent_configuration"]["display_mode"] == "summary_only"
    assert summary_entry["active_agent_run_id"] is None
    assert summary_entry["has_pending_messages"] is False
    assert any(
        message["run_id"] == first_job["run_id"] and message["agent_id"] == "reviewer"
        for message in session_payload["messages"]
    )
    assert any(
        message["run_id"] == first_job["run_id"]
        and message["agent_id"] == "reviewer"
        and message["visibility"] == "hidden"
        for message in session_payload["messages"]
    )
    assert session_payload["messages"][-1]["agent_id"] == "summary"
    assert session_payload["messages"][-1]["job_status"] == "completed"


def test_full_triad_chain_completes_without_client_polling() -> None:
    client, container = build_session_client_with_container()
    session_response = client.post("/sessions", json={"title": "Background triad"})
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    config_response = client.put(
        f"/sessions/{session_id}/agents",
        json=build_agent_configuration_payload(
            preset="triad",
            display_mode="summary_only",
            reviewer_visibility="hidden",
        ),
    )
    assert config_response.status_code == 200

    message_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "Keep the agent chain moving in the background."},
    )
    assert message_response.status_code == 202
    first_job_id = message_response.json()["job_id"]

    repository = container.message_service._repository
    session, messages, jobs_by_id = wait_for_repository_session(
        repository,
        session_id,
        predicate=lambda current_session, current_messages, current_jobs: (
            current_session is not None
            and current_session.active_agent_run_id is None
            and any(
                message.agent_id == AgentId.REVIEWER
                and message.status == ChatMessageStatus.COMPLETED
                for message in current_messages
            )
            and any(
                message.agent_id == AgentId.SUMMARY
                and message.status == ChatMessageStatus.COMPLETED
                for message in current_messages
            )
            and first_job_id in current_jobs
            and current_jobs[first_job_id] is not None
            and current_jobs[first_job_id].auto_chain_processed is True
        ),
    )

    assert session is not None
    assert session.active_agent_run_id is None
    assert any(
        message.agent_id == AgentId.REVIEWER
        and message.status == ChatMessageStatus.COMPLETED
        for message in messages
    )
    assert any(
        message.agent_id == AgentId.SUMMARY
        and message.status == ChatMessageStatus.COMPLETED
        for message in messages
    )
    assert jobs_by_id[first_job_id] is not None
    assert jobs_by_id[first_job_id].auto_chain_processed is True


def test_concurrent_terminal_processing_does_not_duplicate_reviewer_follow_up() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        service, provider, repository = _build_controlled_message_service(
            temp_dir,
            barrier_agent_id=AgentId.REVIEWER,
        )

        session = service.create_session(workspace_path=str(workspace))
        configuration = session.agent_configuration.normalized()
        configuration.preset = AgentPreset.REVIEW
        configuration.agents[AgentId.GENERATOR].max_turns = 2
        configuration.agents[AgentId.REVIEWER].enabled = True
        configuration.agents[AgentId.REVIEWER].max_turns = 1
        configuration.agents[AgentId.SUMMARY].enabled = False
        service.update_agent_configuration(session_id=session.id, configuration=configuration)

        initial_job = service.submit_message(
            "Build the initial implementation.",
            session_id=session.id,
        )
        provider.complete_job(initial_job.id, response="Initial generator response.")

        run_concurrent_get_job(service, initial_job.id)

        messages = repository.list_messages(session.id)
        reviewer_messages = [
            message
            for message in messages
            if message.run_id == initial_job.run_id and message.agent_id == AgentId.REVIEWER
        ]

        assert len(reviewer_messages) == 1
        assert reviewer_messages[0].job_id is not None
        assert len(repository._jobs) == 2


def test_concurrent_terminal_processing_does_not_duplicate_generator_follow_up() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        service, provider, repository = _build_controlled_message_service(
            temp_dir,
            barrier_agent_id=AgentId.GENERATOR,
        )

        session = service.create_session(workspace_path=str(workspace))
        configuration = session.agent_configuration.normalized()
        configuration.preset = AgentPreset.REVIEW
        configuration.agents[AgentId.GENERATOR].max_turns = 2
        configuration.agents[AgentId.REVIEWER].enabled = True
        configuration.agents[AgentId.REVIEWER].max_turns = 1
        configuration.agents[AgentId.SUMMARY].enabled = False
        service.update_agent_configuration(session_id=session.id, configuration=configuration)

        initial_job = service.submit_message(
            "Build the initial implementation.",
            session_id=session.id,
        )
        provider.complete_job(initial_job.id, response="Initial generator response.")
        service.get_job(initial_job.id)

        reviewer_message = next(
            message
            for message in repository.list_messages(session.id)
            if message.run_id == initial_job.run_id and message.agent_id == AgentId.REVIEWER
        )
        assert reviewer_message.job_id is not None

        provider.complete_job(
            reviewer_message.job_id,
            response="Follow up with a stricter implementation pass.",
        )
        run_concurrent_get_job(service, reviewer_message.job_id)

        messages = repository.list_messages(session.id)
        generator_follow_ups = [
            message
            for message in messages
            if message.run_id == initial_job.run_id
            and message.agent_id == AgentId.GENERATOR
            and message.trigger_source == AgentTriggerSource.REVIEWER
        ]

        assert len(generator_follow_ups) == 1
        assert generator_follow_ups[0].job_id is not None
        assert len(repository._jobs) == 3


def test_concurrent_terminal_processing_does_not_duplicate_summary_follow_up() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        service, provider, repository = _build_controlled_message_service(
            temp_dir,
            barrier_agent_id=AgentId.SUMMARY,
        )

        session = service.create_session(workspace_path=str(workspace))
        configuration = session.agent_configuration.normalized()
        configuration.preset = AgentPreset.TRIAD
        configuration.agents[AgentId.GENERATOR].max_turns = 1
        configuration.agents[AgentId.REVIEWER].enabled = False
        configuration.agents[AgentId.REVIEWER].max_turns = 0
        configuration.agents[AgentId.SUMMARY].enabled = True
        configuration.agents[AgentId.SUMMARY].max_turns = 1
        service.update_agent_configuration(session_id=session.id, configuration=configuration)

        initial_job = service.submit_message(
            "Generate the first pass and summarize it.",
            session_id=session.id,
        )
        provider.complete_job(initial_job.id, response="Initial generator response.")

        run_concurrent_get_job(service, initial_job.id)

        messages = repository.list_messages(session.id)
        summary_messages = [
            message
            for message in messages
            if message.run_id == initial_job.run_id and message.agent_id == AgentId.SUMMARY
        ]

        assert len(summary_messages) == 1
        assert summary_messages[0].job_id is not None
        assert len(repository._jobs) == 2


def test_terminal_job_lock_bookkeeping_is_cleaned_up_after_processing() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        service, provider, repository = _build_controlled_message_service(
            temp_dir,
            barrier_agent_id=AgentId.REVIEWER,
        )

        session = service.create_session(workspace_path=str(workspace))
        configuration = session.agent_configuration.normalized()
        configuration.preset = AgentPreset.REVIEW
        configuration.agents[AgentId.GENERATOR].max_turns = 2
        configuration.agents[AgentId.REVIEWER].enabled = True
        configuration.agents[AgentId.REVIEWER].max_turns = 1
        configuration.agents[AgentId.SUMMARY].enabled = False
        service.update_agent_configuration(session_id=session.id, configuration=configuration)

        initial_job = service.submit_message(
            "Build the initial implementation.",
            session_id=session.id,
        )
        provider.complete_job(initial_job.id, response="Initial generator response.")
        run_concurrent_get_job(service, initial_job.id)
        assert service._terminal_job_locks == {}

        reviewer_message = next(
            message
            for message in repository.list_messages(session.id)
            if message.run_id == initial_job.run_id and message.agent_id == AgentId.REVIEWER
        )
        assert reviewer_message.job_id is not None

        provider.complete_job(
            reviewer_message.job_id,
            response="Follow up with a stricter implementation pass.",
        )
        run_concurrent_get_job(service, reviewer_message.job_id)
        assert service._terminal_job_locks == {}


def test_watcher_callback_and_get_job_race_do_not_duplicate_follow_up() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        service, provider, repository = _build_watched_controlled_message_service(
            temp_dir,
            barrier_agent_id=AgentId.REVIEWER,
        )

        session = service.create_session(workspace_path=str(workspace))
        configuration = session.agent_configuration.normalized()
        configuration.preset = AgentPreset.REVIEW
        configuration.agents[AgentId.GENERATOR].max_turns = 2
        configuration.agents[AgentId.REVIEWER].enabled = True
        configuration.agents[AgentId.REVIEWER].max_turns = 1
        configuration.agents[AgentId.SUMMARY].enabled = False
        service.update_agent_configuration(session_id=session.id, configuration=configuration)

        initial_job = service.submit_message(
            "Build the initial implementation.",
            session_id=session.id,
        )

        ready_event = threading.Event()
        release_event = threading.Event()
        watcher_thread = threading.Thread(
            target=provider.complete_job_with_notification_gate,
            kwargs={
                "job_id": initial_job.id,
                "response": "Initial generator response.",
                "ready_event": ready_event,
                "release_event": release_event,
            },
            daemon=True,
        )
        watcher_thread.start()

        assert ready_event.wait(timeout=1)
        poll_thread = threading.Thread(
            target=service.get_job,
            args=(initial_job.id,),
            daemon=True,
        )
        poll_thread.start()
        release_event.set()

        watcher_thread.join(timeout=2)
        poll_thread.join(timeout=2)

        assert not watcher_thread.is_alive()
        assert not poll_thread.is_alive()

        messages = repository.list_messages(session.id)
        reviewer_messages = [
            message
            for message in messages
            if message.run_id == initial_job.run_id and message.agent_id == AgentId.REVIEWER
        ]

        assert len(reviewer_messages) == 1
        assert reviewer_messages[0].job_id is not None
        assert len(repository._jobs) == 2
        assert service._terminal_job_locks == {}


def test_sqlite_triad_chain_completes_without_client_polling() -> None:
    with TemporaryDirectory() as temp_dir:
        database_path = str(Path(temp_dir) / "chat.sqlite3")
        client, container = build_sqlite_session_client_with_container(database_path)

        try:
            session_response = client.post("/sessions", json={"title": "SQLite background triad"})
            assert session_response.status_code == 201
            session_id = session_response.json()["id"]

            config_response = client.put(
                f"/sessions/{session_id}/agents",
                json=build_agent_configuration_payload(
                    preset="triad",
                    display_mode="summary_only",
                    reviewer_visibility="hidden",
                ),
            )
            assert config_response.status_code == 200

            message_response = client.post(
                f"/sessions/{session_id}/messages",
                json={"message": "Keep the SQLite-backed chain moving in the background."},
            )
            assert message_response.status_code == 202
            first_job_id = message_response.json()["job_id"]

            repository = container.message_service._repository
            session, messages, jobs_by_id = wait_for_repository_session(
                repository,
                session_id,
                predicate=lambda current_session, current_messages, current_jobs: (
                    current_session is not None
                    and current_session.active_agent_run_id is None
                    and any(
                        message.agent_id == AgentId.REVIEWER
                        and message.status == ChatMessageStatus.COMPLETED
                        for message in current_messages
                    )
                    and any(
                        message.agent_id == AgentId.SUMMARY
                        and message.status == ChatMessageStatus.COMPLETED
                        for message in current_messages
                    )
                    and first_job_id in current_jobs
                    and current_jobs[first_job_id] is not None
                    and current_jobs[first_job_id].auto_chain_processed is True
                ),
            )

            final_response = client.get(f"/sessions/{session_id}")
            assert final_response.status_code == 200
            payload = final_response.json()

            assert session is not None
            assert session.active_agent_run_id is None
            assert payload["active_agent_run_id"] is None
            assert payload["messages"][-1]["agent_id"] == "summary"
            assert payload["messages"][-1]["job_status"] == "completed"
            assert any(
                message.agent_id == AgentId.REVIEWER
                and message.status == ChatMessageStatus.COMPLETED
                for message in messages
            )
            assert any(
                message.agent_id == AgentId.SUMMARY
                and message.status == ChatMessageStatus.COMPLETED
                for message in messages
            )
            assert jobs_by_id[first_job_id] is not None
            assert jobs_by_id[first_job_id].auto_chain_processed is True
        finally:
            client.close()


def test_failed_job_converges_in_background_without_polling_or_follow_ups() -> None:
    client, container = build_session_client_with_container()

    try:
        session_response = client.post("/sessions", json={"title": "Background failure"})
        assert session_response.status_code == 201
        session_id = session_response.json()["id"]

        config_response = client.put(
            f"/sessions/{session_id}/agents",
            json=build_agent_configuration_payload(
                preset="triad",
                display_mode="summary_only",
                reviewer_visibility="hidden",
            ),
        )
        assert config_response.status_code == 200

        service = container.message_service
        job = service.submit_message(
            "Trigger a background failure.",
            session_id=session_id,
            execution_message="fail:background boom",
        )
        job_id = job.id

        repository = service._repository
        session, messages, job = wait_for_background_terminal_convergence(
            service,
            repository,
            session_id=session_id,
            job_id=job_id,
            expected_status=JobStatus.FAILED,
        )

        final_response = client.get(f"/sessions/{session_id}")
        assert final_response.status_code == 200
        payload = final_response.json()

        assert session.active_agent_run_id is None
        assert job.auto_chain_processed is True
        assert payload["messages"][-1]["status"] == "failed"
        assert "background boom" in payload["messages"][-1]["content"]
        assert len(messages) == 2
        assert all(
            message.agent_id not in {AgentId.REVIEWER, AgentId.SUMMARY}
            for message in messages
        )
        assert service._job_monitor_unsubscribes == {}
        assert service._terminal_job_locks == {}
    finally:
        client.close()


def test_cancelled_job_converges_in_background_without_polling_or_follow_ups() -> None:
    client, container = build_session_client_with_container()

    try:
        session_response = client.post("/sessions", json={"title": "Background cancellation"})
        assert session_response.status_code == 201
        session_id = session_response.json()["id"]

        config_response = client.put(
            f"/sessions/{session_id}/agents",
            json=build_agent_configuration_payload(
                preset="triad",
                display_mode="summary_only",
                reviewer_visibility="hidden",
            ),
        )
        assert config_response.status_code == 200

        message_response = client.post(
            f"/sessions/{session_id}/messages",
            json={"message": "sleep:0.4:background cancellation"},
        )
        assert message_response.status_code == 202
        job_id = message_response.json()["job_id"]

        provider = container.message_service._execution_provider
        deadline = time.monotonic() + 2
        cancelled = False
        while time.monotonic() < deadline:
            if provider.cancel_job(job_id):
                cancelled = True
                break
            time.sleep(0.02)
        assert cancelled is True

        service = container.message_service
        repository = service._repository
        session, messages, job = wait_for_background_terminal_convergence(
            service,
            repository,
            session_id=session_id,
            job_id=job_id,
            expected_status=JobStatus.CANCELLED,
        )

        final_response = client.get(f"/sessions/{session_id}")
        assert final_response.status_code == 200
        payload = final_response.json()

        assert session.active_agent_run_id is None
        assert job.auto_chain_processed is True
        assert payload["messages"][-1]["status"] == "cancelled"
        assert "Cancelled by user." in payload["messages"][-1]["content"]
        assert len(messages) == 2
        assert all(
            message.agent_id not in {AgentId.REVIEWER, AgentId.SUMMARY}
            for message in messages
        )
        assert service._job_monitor_unsubscribes == {}
        assert service._terminal_job_locks == {}
    finally:
        client.close()


def test_failed_reviewer_follow_up_converges_in_background_without_downstream_handoffs() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        service, provider, repository = _build_watched_controlled_message_service(
            temp_dir,
            barrier_agent_id=AgentId.SUPERVISOR,
        )

        session = service.create_session(workspace_path=str(workspace))
        configuration = session.agent_configuration.normalized()
        configuration.preset = AgentPreset.TRIAD
        configuration.agents[AgentId.GENERATOR].max_turns = 2
        configuration.agents[AgentId.REVIEWER].enabled = True
        configuration.agents[AgentId.REVIEWER].max_turns = 1
        configuration.agents[AgentId.SUMMARY].enabled = True
        configuration.agents[AgentId.SUMMARY].max_turns = 1
        service.update_agent_configuration(session_id=session.id, configuration=configuration)

        initial_job = service.submit_message(
            "Build the initial implementation.",
            session_id=session.id,
        )
        provider.complete_job(initial_job.id, response="Initial generator response.")

        _, messages, _ = wait_for_repository_session(
            repository,
            session.id,
            predicate=lambda current_session, current_messages, current_jobs: (
                current_session is not None
                and any(
                    message.run_id == initial_job.run_id
                    and message.agent_id == AgentId.REVIEWER
                    and message.job_id is not None
                    for message in current_messages
                )
                and current_jobs.get(initial_job.id) is not None
                and current_jobs[initial_job.id].auto_chain_processed is True
            ),
        )
        reviewer_message = next(
            message
            for message in messages
            if message.run_id == initial_job.run_id and message.agent_id == AgentId.REVIEWER
        )
        assert reviewer_message.job_id is not None

        provider.fail_job(reviewer_message.job_id, error="Reviewer follow-up failed.")
        session, messages, reviewer_job = wait_for_background_terminal_convergence(
            service,
            repository,
            session_id=session.id,
            job_id=reviewer_message.job_id,
            expected_status=JobStatus.FAILED,
        )

        assert session.active_agent_run_id is None
        assert reviewer_job.auto_chain_processed is True
        assert any(
            message.id == reviewer_message.id
            and message.status == ChatMessageStatus.FAILED
            and "Reviewer follow-up failed." in message.content
            for message in messages
        )
        assert not any(
            message.run_id == initial_job.run_id
            and message.agent_id == AgentId.GENERATOR
            and message.trigger_source == AgentTriggerSource.REVIEWER
            for message in messages
        )
        assert not any(
            message.run_id == initial_job.run_id and message.agent_id == AgentId.SUMMARY
            for message in messages
        )
        assert service._job_monitor_unsubscribes == {}
        assert service._terminal_job_locks == {}


def test_cancelled_reviewer_follow_up_converges_in_background_without_downstream_handoffs() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        service, provider, repository = _build_watched_controlled_message_service(
            temp_dir,
            barrier_agent_id=AgentId.SUPERVISOR,
        )

        session = service.create_session(workspace_path=str(workspace))
        configuration = session.agent_configuration.normalized()
        configuration.preset = AgentPreset.TRIAD
        configuration.agents[AgentId.GENERATOR].max_turns = 2
        configuration.agents[AgentId.REVIEWER].enabled = True
        configuration.agents[AgentId.REVIEWER].max_turns = 1
        configuration.agents[AgentId.SUMMARY].enabled = True
        configuration.agents[AgentId.SUMMARY].max_turns = 1
        service.update_agent_configuration(session_id=session.id, configuration=configuration)

        initial_job = service.submit_message(
            "Build the initial implementation.",
            session_id=session.id,
        )
        provider.complete_job(initial_job.id, response="Initial generator response.")

        _, messages, _ = wait_for_repository_session(
            repository,
            session.id,
            predicate=lambda current_session, current_messages, current_jobs: (
                current_session is not None
                and any(
                    message.run_id == initial_job.run_id
                    and message.agent_id == AgentId.REVIEWER
                    and message.job_id is not None
                    for message in current_messages
                )
                and current_jobs.get(initial_job.id) is not None
                and current_jobs[initial_job.id].auto_chain_processed is True
            ),
        )
        reviewer_message = next(
            message
            for message in messages
            if message.run_id == initial_job.run_id and message.agent_id == AgentId.REVIEWER
        )
        assert reviewer_message.job_id is not None

        assert provider.cancel_job(reviewer_message.job_id) is True
        session, messages, reviewer_job = wait_for_background_terminal_convergence(
            service,
            repository,
            session_id=session.id,
            job_id=reviewer_message.job_id,
            expected_status=JobStatus.CANCELLED,
        )

        assert session.active_agent_run_id is None
        assert reviewer_job.auto_chain_processed is True
        assert any(
            message.id == reviewer_message.id
            and message.status == ChatMessageStatus.CANCELLED
            and "Cancelled by user." in message.content
            for message in messages
        )
        assert not any(
            message.run_id == initial_job.run_id
            and message.agent_id == AgentId.GENERATOR
            and message.trigger_source == AgentTriggerSource.REVIEWER
            for message in messages
        )
        assert not any(
            message.run_id == initial_job.run_id and message.agent_id == AgentId.SUMMARY
            for message in messages
        )
        assert service._job_monitor_unsubscribes == {}
        assert service._terminal_job_locks == {}


def test_failed_supervisor_specialist_follow_up_converges_in_background() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        service, provider, repository = _build_watched_controlled_message_service(
            temp_dir,
            barrier_agent_id=AgentId.REVIEWER,
        )

        session = service.create_session(workspace_path=str(workspace))
        configuration = AgentConfiguration.default().normalized()
        configuration.preset = AgentPreset.SUPERVISOR
        configuration.supervisor_member_ids = (AgentId.QA,)
        configuration.agents[AgentId.SUPERVISOR].enabled = True
        configuration.agents[AgentId.SUPERVISOR].max_turns = 2
        configuration.agents[AgentId.QA].enabled = True
        configuration.agents[AgentId.QA].max_turns = 1
        configuration.agents[AgentId.UX].enabled = False
        configuration.agents[AgentId.UX].max_turns = 0
        configuration.agents[AgentId.SENIOR_ENGINEER].enabled = False
        configuration.agents[AgentId.SENIOR_ENGINEER].max_turns = 0
        service.update_agent_configuration(session_id=session.id, configuration=configuration)

        initial_job = service.submit_message(
            "Plan the release work.",
            session_id=session.id,
        )
        provider.complete_job(
            initial_job.id,
            response=json.dumps(
                {
                    "status": "continue",
                    "plan": [
                        "Assess release readiness",
                        "Run QA verification",
                    ],
                    "next_agent_id": "qa",
                    "instruction": "Validate the release and report blockers.",
                    "user_response": "QA verification is next.",
                }
            ),
        )

        _, messages, _ = wait_for_repository_session(
            repository,
            session.id,
            predicate=lambda current_session, current_messages, current_jobs: (
                current_session is not None
                and any(
                    message.run_id == initial_job.run_id
                    and message.agent_id == AgentId.QA
                    and message.job_id is not None
                    for message in current_messages
                )
                and current_jobs.get(initial_job.id) is not None
                and current_jobs[initial_job.id].auto_chain_processed is True
            ),
        )
        qa_message = next(
            message
            for message in messages
            if message.run_id == initial_job.run_id and message.agent_id == AgentId.QA
        )
        assert qa_message.job_id is not None

        provider.fail_job(qa_message.job_id, error="QA specialist follow-up failed.")
        session, messages, qa_job = wait_for_background_terminal_convergence(
            service,
            repository,
            session_id=session.id,
            job_id=qa_message.job_id,
            expected_status=JobStatus.FAILED,
        )

        supervisor_messages = [
            message
            for message in messages
            if message.run_id == initial_job.run_id and message.agent_id == AgentId.SUPERVISOR
        ]

        assert session.active_agent_run_id is None
        assert session.active_agent_turn_index == 1
        assert qa_job.auto_chain_processed is True
        assert len(supervisor_messages) == 1
        assert any(
            message.id == qa_message.id
            and message.status == ChatMessageStatus.FAILED
            and "QA specialist follow-up failed." in message.content
            for message in messages
        )
        assert service._job_monitor_unsubscribes == {}
        assert service._terminal_job_locks == {}


def test_sqlite_legacy_auto_mode_rows_migrate_into_agent_configuration() -> None:
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
            session_response = first_client.post("/sessions", json={"title": "Legacy"})
            assert session_response.status_code == 201
            session_id = session_response.json()["id"]
            auto_mode_response = first_client.put(
                f"/sessions/{session_id}/auto-mode",
                json={
                    "enabled": True,
                    "max_turns": 1,
                    "reviewer_prompt": "Legacy reviewer prompt",
                },
            )
            assert auto_mode_response.status_code == 200
        finally:
            first_client.close()

        import sqlite3

        with sqlite3.connect(database_path) as connection:
            connection.execute(
                "UPDATE sessions SET agent_configuration_json = NULL WHERE id = ?",
                (session_id,),
            )
            connection.commit()

        restarted_client = TestClient(create_app(settings))
        try:
            session_detail = restarted_client.get(f"/sessions/{session_id}")
            assert session_detail.status_code == 200
            payload = session_detail.json()
            reviewer = next(
                agent
                for agent in payload["agent_configuration"]["agents"]
                if agent["agent_id"] == "reviewer"
            )
            summary = next(
                agent
                for agent in payload["agent_configuration"]["agents"]
                if agent["agent_id"] == "summary"
            )
            assert reviewer["enabled"] is True
            assert reviewer["prompt"] == "Legacy reviewer prompt"
            assert summary["enabled"] is False
        finally:
            restarted_client.close()


def test_sqlite_repository_migrates_legacy_schema_and_rows() -> None:
    import sqlite3

    with TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "legacy-chat-store.sqlite3"
        with sqlite3.connect(database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    workspace_path TEXT NOT NULL,
                    workspace_name TEXT NOT NULL,
                    provider_session_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    job_id TEXT
                );

                CREATE TABLE jobs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    user_message_id TEXT,
                    assistant_message_id TEXT,
                    provider_session_id TEXT,
                    status TEXT NOT NULL,
                    response TEXT,
                    error TEXT,
                    phase TEXT,
                    latest_activity TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                );
                """
            )
            connection.execute(
                """
                INSERT INTO sessions (
                    id,
                    title,
                    workspace_path,
                    workspace_name,
                    provider_session_id,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy-session",
                    "Legacy session",
                    "/workspace/legacy",
                    "legacy",
                    "provider-1",
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO messages (
                    id,
                    session_id,
                    role,
                    content,
                    status,
                    created_at,
                    updated_at,
                    job_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy-assistant",
                    "legacy-session",
                    "assistant",
                    "Legacy assistant response",
                    "completed",
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                    None,
                ),
            )
            connection.commit()

        repository = SqliteChatRepository(
            database_path=str(database_path),
            projects_root="..",
        )

        with sqlite3.connect(database_path) as connection:
            session_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(sessions)")
            }
            message_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(messages)")
            }
            job_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(jobs)")
            }
            user_version = connection.execute("PRAGMA user_version").fetchone()[0]

        assert "agent_configuration_json" in session_columns
        assert "active_agent_run_id" in session_columns
        assert "reason_code" in message_columns
        assert "submission_token" in message_columns
        assert "conversation_kind" in job_columns
        assert "submission_token" in job_columns
        assert user_version >= 1

        session = repository.get_session("legacy-session")
        assert session is not None
        assert session.agent_configuration.agents[AgentId.GENERATOR].enabled is True
        assert session.agent_configuration.agents[AgentId.REVIEWER].enabled is False
        assert session.agent_configuration.agents[AgentId.SUMMARY].enabled is False

        legacy_message = repository.get_message("legacy-assistant")
        assert legacy_message is not None
        assert legacy_message.author_type == ChatMessageAuthorType.ASSISTANT
        assert legacy_message.agent_id == AgentId.GENERATOR
        assert legacy_message.agent_type == AgentType.GENERATOR
        assert legacy_message.reason_code is None

        repository.save_message(
            ChatMessage(
                id="migrated-new-reason",
                session_id="legacy-session",
                role=ChatMessageRole.ASSISTANT,
                author_type=ChatMessageAuthorType.ASSISTANT,
                content="Recovered",
                status=ChatMessageStatus.CANCELLED,
                reason_code=ChatMessageReasonCode.MANUAL_CANCEL_REQUESTED,
            )
        )
        saved_message = repository.get_message("migrated-new-reason")
        assert saved_message is not None
        assert (
            saved_message.reason_code
            == ChatMessageReasonCode.MANUAL_CANCEL_REQUESTED
        )


def test_sqlite_repository_partial_upgrade_migrates_duplicate_dedupe_keys_safely() -> None:
    import sqlite3

    with TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "partial-chat-store.sqlite3"
        with sqlite3.connect(database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    workspace_path TEXT NOT NULL,
                    workspace_name TEXT NOT NULL,
                    provider_session_id TEXT,
                    reviewer_provider_session_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    author_type TEXT NOT NULL DEFAULT 'human',
                    agent_id TEXT NOT NULL DEFAULT 'generator',
                    agent_type TEXT NOT NULL DEFAULT 'generator',
                    visibility TEXT NOT NULL DEFAULT 'visible',
                    trigger_source TEXT NOT NULL DEFAULT 'system',
                    dedupe_key TEXT,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    job_id TEXT
                );

                CREATE TABLE jobs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            connection.execute(
                """
                INSERT INTO sessions (
                    id,
                    title,
                    workspace_path,
                    workspace_name,
                    provider_session_id,
                    reviewer_provider_session_id,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "partial-session",
                    "Partial",
                    "/workspace/partial",
                    "partial",
                    None,
                    None,
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
            for message_id in ("duplicate-1", "duplicate-2"):
                connection.execute(
                    """
                    INSERT INTO messages (
                        id,
                        session_id,
                        role,
                        author_type,
                        agent_id,
                        agent_type,
                        visibility,
                        trigger_source,
                        dedupe_key,
                        content,
                        status,
                        created_at,
                        updated_at,
                        job_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message_id,
                        "partial-session",
                        "user",
                        "not-valid",
                        "bad-agent",
                        "bad-type",
                        "not-visible",
                        "not-trigger",
                        "run:partial:reviewer:1",
                        f"legacy {message_id}",
                        "reserved",
                        "2026-01-01T00:00:00+00:00",
                        "2026-01-01T00:00:00+00:00",
                        None,
                    ),
                )
            connection.commit()

        repository = SqliteChatRepository(
            database_path=str(database_path),
            projects_root="..",
        )

        messages = repository.list_messages("partial-session")
        assert len(messages) == 2
        assert messages[0].agent_id == AgentId.USER
        assert messages[0].agent_type == AgentType.HUMAN
        assert messages[0].visibility == AgentVisibilityMode.VISIBLE
        assert messages[0].trigger_source == AgentTriggerSource.USER

        dedupe_values = {message.id: message.dedupe_key for message in messages}
        assert list(dedupe_values.values()).count("run:partial:reviewer:1") == 1
        assert list(dedupe_values.values()).count(None) == 1

        reserved = repository.reserve_message(
            ChatMessage(
                id="new-duplicate-attempt",
                session_id="partial-session",
                role=ChatMessageRole.USER,
                author_type=ChatMessageAuthorType.REVIEWER_CODEX,
                content="duplicate",
                status=ChatMessageStatus.RESERVED,
                agent_id=AgentId.REVIEWER,
                dedupe_key="run:partial:reviewer:1",
            )
        )
        assert reserved.id == "duplicate-1"

        with sqlite3.connect(database_path) as connection:
            index_names = {
                row[1] for row in connection.execute("PRAGMA index_list(messages)")
            }
            user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        assert "idx_messages_dedupe_key" in index_names
        assert user_version >= 1


def test_sqlite_repository_reports_malformed_historical_rows_with_structured_errors() -> None:
    import sqlite3

    with TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "malformed-chat-store.sqlite3"
        with sqlite3.connect(database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    workspace_path TEXT NOT NULL,
                    workspace_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    job_id TEXT
                );

                CREATE TABLE jobs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            connection.execute(
                """
                INSERT INTO sessions (
                    id,
                    title,
                    workspace_path,
                    workspace_name,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "malformed-session",
                    "Malformed",
                    "/workspace/malformed",
                    "malformed",
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO messages (
                    id,
                    session_id,
                    role,
                    content,
                    status,
                    created_at,
                    updated_at,
                    job_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "bad-message",
                    "malformed-session",
                    "not-a-role",
                    "broken",
                    "completed",
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                    None,
                ),
            )
            connection.commit()

        repository = SqliteChatRepository(
            database_path=str(database_path),
            projects_root="..",
        )

        issues = repository.validate_integrity()
        assert len(issues) == 1
        issue = issues[0]
        assert issue.table == "messages"
        assert issue.row_id == "bad-message"
        assert issue.field == "role"
        assert issue.code == "invalid_role"

        with pytest.raises(PersistenceDataError) as exc:
            repository.get_message("bad-message")
        assert exc.value.table == "messages"
        assert exc.value.row_id == "bad-message"
        assert exc.value.field == "role"
        assert exc.value.code == "invalid_role"


def test_persistence_integrity_debug_endpoint_reports_malformed_rows() -> None:
    import sqlite3

    with TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "malformed-debug-chat-store.sqlite3"
        with sqlite3.connect(database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    workspace_path TEXT NOT NULL,
                    workspace_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    job_id TEXT
                );

                CREATE TABLE jobs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            connection.execute(
                """
                INSERT INTO sessions (
                    id,
                    title,
                    workspace_path,
                    workspace_name,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "debug-session",
                    "Debug",
                    "/workspace/debug",
                    "debug",
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO messages (
                    id,
                    session_id,
                    role,
                    content,
                    status,
                    created_at,
                    updated_at,
                    job_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "debug-bad-status",
                    "debug-session",
                    "assistant",
                    "broken",
                    "not-a-status",
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                    None,
                ),
            )
            connection.commit()

        settings = Settings(
            codex_command="python3 tests/fixtures/fake_codex_session.py",
            codex_use_exec=True,
            projects_root="..",
            chat_store_backend="sqlite",
            chat_store_path=str(database_path),
            execution_timeout_seconds=10,
            poll_interval_seconds=0,
            audio_transcription_backend="auto",
        )
        client = TestClient(create_app(settings))
        try:
            response = client.get("/debug/persistence/integrity")
            assert response.status_code == 200
            payload = response.json()
            assert payload["backend"] == "sqlite"
            assert payload["is_healthy"] is False
            assert payload["issues"] == [
                {
                    "table": "messages",
                    "row_id": "debug-bad-status",
                    "field": "status",
                    "code": "invalid_status",
                    "detail": "Unexpected status value: not-a-status",
                }
            ]
        finally:
            client.close()


def test_session_api_fails_fast_with_structured_persistence_error() -> None:
    import sqlite3

    with TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "malformed-api-chat-store.sqlite3"
        with sqlite3.connect(database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    workspace_path TEXT NOT NULL,
                    workspace_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    job_id TEXT
                );

                CREATE TABLE jobs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            connection.execute(
                """
                INSERT INTO sessions (
                    id,
                    title,
                    workspace_path,
                    workspace_name,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "api-session",
                    "API",
                    "/workspace/api",
                    "api",
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO messages (
                    id,
                    session_id,
                    role,
                    content,
                    status,
                    created_at,
                    updated_at,
                    job_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "api-bad-message",
                    "api-session",
                    "assistant",
                    "broken",
                    "bad-status",
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                    None,
                ),
            )
            connection.commit()

        settings = Settings(
            codex_command="python3 tests/fixtures/fake_codex_session.py",
            codex_use_exec=True,
            projects_root="..",
            chat_store_backend="sqlite",
            chat_store_path=str(database_path),
            execution_timeout_seconds=10,
            poll_interval_seconds=0,
            audio_transcription_backend="auto",
        )
        client = TestClient(create_app(settings), raise_server_exceptions=False)
        try:
            response = client.get("/sessions/api-session")
            assert response.status_code == 500
            assert response.json() == {
                "detail": {
                    "error": "persistence_data_error",
                    "table": "messages",
                    "row_id": "api-bad-message",
                    "field": "status",
                    "code": "invalid_status",
                    "message": "Unexpected status value: bad-status",
                }
            }
        finally:
            client.close()


def test_sqlite_repository_reports_integrity_check_failures_distinctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TemporaryDirectory() as temp_dir:
        repository = SqliteChatRepository(
            database_path=str(Path(temp_dir) / "integrity-check.sqlite3"),
            projects_root="..",
        )
        monkeypatch.setattr(
            repository,
            "_execute_integrity_check",
            lambda _connection: [
                "*** in database main *** On tree page 3 cell 0: invalid page number 999",
            ],
        )

        issues = repository.validate_integrity()
        assert len(issues) == 1
        issue = issues[0]
        assert issue.table == "database"
        assert issue.row_id is None
        assert issue.field is None
        assert issue.code == "sqlite_integrity_check_failed"
        assert (
            issue.detail
            == "*** in database main *** On tree page 3 cell 0: invalid page number 999"
        )


def test_persistence_integrity_debug_endpoint_reports_low_level_sqlite_issues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TemporaryDirectory() as temp_dir:
        settings = Settings(
            codex_command="python3 tests/fixtures/fake_codex_session.py",
            codex_use_exec=True,
            projects_root="..",
            chat_store_backend="sqlite",
            chat_store_path=str(Path(temp_dir) / "integrity-debug.sqlite3"),
            execution_timeout_seconds=10,
            poll_interval_seconds=0,
            audio_transcription_backend="auto",
        )
        app = create_app(settings)
        container = app.dependency_overrides[get_container]()
        monkeypatch.setattr(
            container.message_service._repository,
            "_execute_integrity_check",
            lambda _connection: ["database disk image is malformed"],
        )
        client = TestClient(app)
        try:
            response = client.get("/debug/persistence/integrity")
            assert response.status_code == 200
            assert response.json() == {
                "backend": "sqlite",
                "is_healthy": False,
                "issues": [
                    {
                        "table": "database",
                        "row_id": None,
                        "field": None,
                        "code": "sqlite_integrity_check_failed",
                        "detail": "database disk image is malformed",
                    }
                ],
            }
        finally:
            client.close()


def test_api_returns_structured_sqlite_database_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sqlite3

    settings = Settings(
        codex_command="python3 tests/fixtures/fake_codex_session.py",
        codex_use_exec=True,
        projects_root="..",
        chat_store_backend="sqlite",
        chat_store_path=":memory:",
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
        audio_transcription_backend="auto",
    )
    app = create_app(settings)
    container = app.dependency_overrides[get_container]()
    monkeypatch.setattr(
        container.message_service._repository,
        "get_session",
        lambda _session_id: (_ for _ in ()).throw(
            sqlite3.DatabaseError("database disk image is malformed")
        ),
    )
    client = TestClient(app, raise_server_exceptions=False)
    try:
        response = client.get("/sessions/any-session")
        assert response.status_code == 500
        assert response.json() == {
            "detail": {
                "error": "sqlite_database_error",
                "code": "sqlite_database_error",
                "message": "database disk image is malformed",
            }
        }
    finally:
        client.close()


def test_app_starts_in_degraded_mode_when_sqlite_store_fails_to_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sqlite3

    original_init = SqliteChatRepository.__init__

    def failing_init(self, *, database_path: str, projects_root: str) -> None:
        raise sqlite3.DatabaseError("unable to open database file")

    monkeypatch.setattr(SqliteChatRepository, "__init__", failing_init)
    settings = Settings(
        codex_command="python3 tests/fixtures/fake_codex_session.py",
        codex_use_exec=True,
        projects_root="..",
        chat_store_backend="sqlite",
        chat_store_path="/definitely/missing/chat-store.sqlite3",
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
        audio_transcription_backend="auto",
    )
    client = TestClient(create_app(settings), raise_server_exceptions=False)
    try:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["persistence_available"] is False
        assert health.json()["persistence_error_code"] == "sqlite_database_error"
        assert "unable to open database file" in health.json()["persistence_error_detail"]

        integrity = client.get("/debug/persistence/integrity")
        assert integrity.status_code == 200
        assert integrity.json() == {
            "backend": "sqlite",
            "is_healthy": False,
            "issues": [
                {
                    "table": "database",
                    "row_id": None,
                    "field": None,
                    "code": "sqlite_database_error",
                    "detail": "unable to open database file",
                }
            ],
        }

        sessions = client.get("/sessions")
        assert sessions.status_code == 503
        assert sessions.json() == {
            "detail": {
                "error": "persistence_unavailable",
                "table": "database",
                "row_id": None,
                "field": None,
                "code": "sqlite_database_error",
                "message": "unable to open database file",
            }
        }
    finally:
        monkeypatch.setattr(SqliteChatRepository, "__init__", original_init)
        client.close()


def test_app_reports_generic_startup_migration_failures_structurally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_init = SqliteChatRepository.__init__

    def failing_init(self, *, database_path: str, projects_root: str) -> None:
        raise RuntimeError("migration exploded")

    monkeypatch.setattr(SqliteChatRepository, "__init__", failing_init)
    settings = Settings(
        codex_command="python3 tests/fixtures/fake_codex_session.py",
        codex_use_exec=True,
        projects_root="..",
        chat_store_backend="sqlite",
        chat_store_path="/tmp/migration-exploded.sqlite3",
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
        audio_transcription_backend="auto",
    )
    client = TestClient(create_app(settings), raise_server_exceptions=False)
    try:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["persistence_available"] is False
        assert health.json()["persistence_error_code"] == "persistence_startup_failure"
        assert "migration exploded" in health.json()["persistence_error_detail"]
    finally:
        monkeypatch.setattr(SqliteChatRepository, "__init__", original_init)
        client.close()


def test_sqlite_invalid_agent_configuration_rows_fall_back_to_safe_defaults() -> None:
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
            audio_transcription_backend="auto",
        )

        first_client = TestClient(create_app(settings))
        try:
            session_response = first_client.post("/sessions", json={"title": "Broken config"})
            assert session_response.status_code == 201
            session_id = session_response.json()["id"]
        finally:
            first_client.close()

        import sqlite3

        with sqlite3.connect(database_path) as connection:
            connection.execute(
                """
                UPDATE sessions
                SET agent_configuration_json = ?
                WHERE id = ?
                """,
                (
                    '{"preset":"triad","display_mode":"show_all","agents":{"generator":{"agent_id":"generator","agent_type":"generator","enabled":"yes"}}}',
                    session_id,
                ),
            )
            connection.commit()

        restarted_client = TestClient(create_app(settings))
        try:
            session_detail = restarted_client.get(f"/sessions/{session_id}")
            assert session_detail.status_code == 200
            payload = session_detail.json()
            generator = next(
                agent
                for agent in payload["agent_configuration"]["agents"]
                if agent["agent_id"] == AgentId.GENERATOR.value
            )
            reviewer = next(
                agent
                for agent in payload["agent_configuration"]["agents"]
                if agent["agent_id"] == AgentId.REVIEWER.value
            )
            summary = next(
                agent
                for agent in payload["agent_configuration"]["agents"]
                if agent["agent_id"] == AgentId.SUMMARY.value
            )
            assert payload["agent_configuration"]["preset"] == "solo"
            assert generator["enabled"] is True
            assert reviewer["enabled"] is False
            assert summary["enabled"] is False
        finally:
            restarted_client.close()


def test_sqlite_repository_reserve_message_reuses_existing_dedupe_key() -> None:
    with TemporaryDirectory() as temp_dir:
        repository = SqliteChatRepository(
            database_path=str(Path(temp_dir) / "chat-store.sqlite3"),
            projects_root="..",
        )
        session = ChatSession(
            id="session-1",
            title="Repo",
            workspace_path="/workspace/repo",
            workspace_name="Repo",
        )
        repository.save_session(session)

        first_message = ChatMessage(
            id="message-1",
            session_id=session.id,
            role=ChatMessageRole.USER,
            author_type=ChatMessageAuthorType.REVIEWER_CODEX,
            content="reserved",
            status=ChatMessageStatus.RESERVED,
            agent_id=AgentId.REVIEWER,
            dedupe_key="run:1:reviewer:1",
        )
        second_message = ChatMessage(
            id="message-2",
            session_id=session.id,
            role=ChatMessageRole.USER,
            author_type=ChatMessageAuthorType.REVIEWER_CODEX,
            content="duplicate",
            status=ChatMessageStatus.RESERVED,
            agent_id=AgentId.REVIEWER,
            dedupe_key="run:1:reviewer:1",
        )

        reserved_first = repository.reserve_message(first_message)
        reserved_second = repository.reserve_message(second_message)

        assert reserved_first.id == "message-1"
        assert reserved_second.id == "message-1"
        assert len(repository.list_messages(session.id)) == 1
        persisted_message = repository.list_messages(session.id)[0]
        assert persisted_message.status == ChatMessageStatus.RESERVED
        assert persisted_message.job_id is None


def test_chat_message_recovery_metadata_rejects_invalid_combinations() -> None:
    message = ChatMessage(
        id="invalid-lineage",
        session_id="session-1",
        role=ChatMessageRole.ASSISTANT,
        author_type=ChatMessageAuthorType.ASSISTANT,
        content="broken",
        status=ChatMessageStatus.CANCELLED,
        recovery_action=MessageRecoveryAction.CANCEL,
        recovered_from_message_id="older",
    )
    with pytest.raises(ValueError):
        message.validate_recovery_metadata()

    retry_message = ChatMessage(
        id="retry-lineage",
        session_id="session-1",
        role=ChatMessageRole.ASSISTANT,
        author_type=ChatMessageAuthorType.ASSISTANT,
        content="broken",
        status=ChatMessageStatus.PENDING,
        recovery_action=MessageRecoveryAction.RETRY,
    )
    with pytest.raises(ValueError):
        retry_message.validate_recovery_metadata()


def test_session_read_recovers_reserved_reviewer_follow_up_idempotently() -> None:
    client, container = build_session_client_with_container()
    try:
        session_response = client.post("/sessions", json={"title": "Recover reviewer"})
        assert session_response.status_code == 201
        session_id = session_response.json()["id"]

        message_response = client.post(
            f"/sessions/{session_id}/messages",
            json={"message": "Ship the recovery path"},
        )
        assert message_response.status_code == 202
        primary_job = wait_for_job(client, message_response.json()["job_id"])
        run_id = primary_job["run_id"]
        assert run_id is not None

        repository = container.message_service._repository
        session = repository.get_session(session_id)
        assert session is not None
        session.agent_configuration = build_agent_configuration_domain(
            preset="review",
            reviewer_enabled=True,
            summary_enabled=False,
        )
        session.agent_configuration.agents[AgentId.GENERATOR].max_turns = 1
        session.active_agent_run_id = run_id
        session.touch()
        repository.save_session(session)

        reviewer_definition = session.agent_configuration.agents[AgentId.REVIEWER]
        reviewer_placeholder = ChatMessage(
            id="reserved-reviewer",
            session_id=session_id,
            role=ChatMessageRole.USER,
            author_type=ChatMessageAuthorType.REVIEWER_CODEX,
            content="",
            status=ChatMessageStatus.RESERVED,
            agent_id=AgentId.REVIEWER,
            agent_label=reviewer_definition.label,
            visibility=reviewer_definition.visibility,
            trigger_source=AgentTriggerSource.GENERATOR,
            run_id=run_id,
            dedupe_key=f"run:{run_id}:reviewer:1",
        )
        repository.reserve_message(reviewer_placeholder)

        session_payload = wait_for_session(
            client,
            session_id,
            predicate=lambda payload: any(
                message["id"] == "reserved-reviewer"
                and message["status"] == "completed"
                and message["job_id"] is not None
                for message in payload["messages"]
            )
            and payload["active_agent_run_id"] is None,
        )

        for _ in range(3):
            response = client.get(f"/sessions/{session_id}")
            assert response.status_code == 200

        final_payload = client.get(f"/sessions/{session_id}").json()
        recovered_messages = [
            message
            for message in final_payload["messages"]
            if message["id"] == "reserved-reviewer"
        ]
        assert len(recovered_messages) == 1
        assert recovered_messages[0]["status"] == "completed"
        assert recovered_messages[0]["job_id"] is not None
        assert any(
            message["id"] == "reserved-reviewer"
            for message in session_payload["messages"]
        )
    finally:
        client.close()


def test_session_read_cancels_orphaned_reserved_follow_up_with_reason_code() -> None:
    client, container = build_session_client_with_container()
    try:
        session_response = client.post("/sessions", json={"title": "Orphaned reviewer"})
        assert session_response.status_code == 201
        session_id = session_response.json()["id"]

        repository = container.message_service._repository
        session = repository.get_session(session_id)
        assert session is not None
        session.active_agent_run_id = "run-active"
        session.touch()
        repository.save_session(session)

        repository.reserve_message(
            ChatMessage(
                id="orphaned-reviewer",
                session_id=session_id,
                role=ChatMessageRole.USER,
                author_type=ChatMessageAuthorType.REVIEWER_CODEX,
                content="",
                status=ChatMessageStatus.RESERVED,
                agent_id=AgentId.REVIEWER,
                trigger_source=AgentTriggerSource.GENERATOR,
                run_id="run-stale",
                dedupe_key="run:run-stale:reviewer:1",
            )
        )

        payload = client.get(f"/sessions/{session_id}")
        assert payload.status_code == 200
        message = next(
            item
            for item in payload.json()["messages"]
            if item["id"] == "orphaned-reviewer"
        )
        assert message["status"] == "cancelled"
        assert (
            message["reason_code"]
            == ChatMessageReasonCode.ORPHANED_FOLLOW_UP_CANCELLED.value
        )
    finally:
        client.close()


def test_session_read_attaches_submission_pending_follow_up_without_resubmitting() -> None:
    client, container = build_session_client_with_container()
    try:
        session_response = client.post("/sessions", json={"title": "Attach submitted"})
        assert session_response.status_code == 201
        session_id = session_response.json()["id"]

        message_response = client.post(
            f"/sessions/{session_id}/messages",
            json={"message": "Ship the attach path"},
        )
        assert message_response.status_code == 202
        primary_job = wait_for_job(client, message_response.json()["job_id"])
        run_id = primary_job["run_id"]
        assert run_id is not None

        service = container.message_service
        repository = service._repository
        session = repository.get_session(session_id)
        assert session is not None
        session.agent_configuration = build_agent_configuration_domain(
            preset="review",
            reviewer_enabled=True,
            summary_enabled=False,
        )
        session.agent_configuration.agents[AgentId.GENERATOR].max_turns = 1
        session.active_agent_run_id = run_id
        session.touch()
        repository.save_session(session)

        reviewer_definition = session.agent_configuration.agents[AgentId.REVIEWER]
        reviewer_placeholder = ChatMessage(
            id="submitted-reviewer",
            session_id=session_id,
            role=ChatMessageRole.USER,
            author_type=ChatMessageAuthorType.REVIEWER_CODEX,
            content="",
            status=ChatMessageStatus.SUBMISSION_PENDING,
            agent_id=AgentId.REVIEWER,
            agent_label=reviewer_definition.label,
            visibility=reviewer_definition.visibility,
            trigger_source=AgentTriggerSource.GENERATOR,
            run_id=run_id,
            dedupe_key=f"run:{run_id}:reviewer:1",
            submission_token=f"submission:{run_id}:reviewer:1",
        )
        repository.reserve_message(reviewer_placeholder)

        original_execute = service._execution_provider.execute
        primary_response = primary_job["response"]
        orphan_job_id = original_execute(
            service._build_reviewer_execution_message(
                reviewer_prompt=reviewer_definition.prompt,
                primary_response=primary_response,
            ),
            provider_session_id=None,
            serial_key=service._serial_key_for_agent(session_id, AgentId.REVIEWER),
            submission_token=reviewer_placeholder.submission_token,
            workdir=session.workspace_path,
        )
        service._execution_provider.execute = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("recovery should not resubmit an already-submitted follow-up")
        )

        session_payload = wait_for_session(
            client,
            session_id,
            predicate=lambda payload: any(
                message["id"] == "submitted-reviewer"
                and message["status"] == "completed"
                and message["job_id"] == orphan_job_id
                for message in payload["messages"]
            )
            and payload["active_agent_run_id"] is None,
        )

        recovered_message = next(
            message
            for message in session_payload["messages"]
            if message["id"] == "submitted-reviewer"
        )
        assert recovered_message["submission_token"] == reviewer_placeholder.submission_token
        assert recovered_message["job_id"] == orphan_job_id

        for _ in range(3):
            response = client.get(f"/sessions/{session_id}")
            assert response.status_code == 200
            repeated_message = next(
                message
                for message in response.json()["messages"]
                if message["id"] == "submitted-reviewer"
            )
            assert repeated_message["job_id"] == orphan_job_id
    finally:
        client.close()


def test_submission_pending_without_provider_lookup_becomes_submission_unknown() -> None:
    client, container = build_session_client_with_container()
    try:
        session_response = client.post("/sessions", json={"title": "Unknown submission"})
        assert session_response.status_code == 201
        session_id = session_response.json()["id"]

        repository = container.message_service._repository
        session = repository.get_session(session_id)
        assert session is not None
        session.agent_configuration = build_agent_configuration_domain(
            preset="review",
            reviewer_enabled=True,
            summary_enabled=False,
        )
        session.active_agent_run_id = "run-submission-unknown"
        session.touch()
        repository.save_session(session)

        repository.reserve_message(
            ChatMessage(
                id="unknown-reviewer",
                session_id=session_id,
                role=ChatMessageRole.USER,
                author_type=ChatMessageAuthorType.REVIEWER_CODEX,
                content="",
                status=ChatMessageStatus.SUBMISSION_PENDING,
                agent_id=AgentId.REVIEWER,
                trigger_source=AgentTriggerSource.GENERATOR,
                run_id="run-submission-unknown",
                dedupe_key="run:run-submission-unknown:reviewer:1",
                submission_token="submission:unknown",
            )
        )

        provider = container.message_service._execution_provider
        provider.supports_submission_lookup = lambda: False
        provider.execute = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("submission_unknown recovery must not resubmit blindly")
        )

        session_payload = wait_for_session(
            client,
            session_id,
            predicate=lambda payload: any(
                message["id"] == "unknown-reviewer"
                and message["status"] == "submission_unknown"
                for message in payload["messages"]
            )
            and payload["active_agent_run_id"] is None,
        )

        unknown_message = next(
            message
            for message in session_payload["messages"]
            if message["id"] == "unknown-reviewer"
        )
        assert unknown_message["job_id"] is None
        assert unknown_message["submission_token"] == "submission:unknown"
        assert (
            unknown_message["reason_code"]
            == ChatMessageReasonCode.SUBMISSION_OUTCOME_UNKNOWN.value
        )
        assert "Automatic recovery stopped" in unknown_message["content"]

        for _ in range(2):
            response = client.get(f"/sessions/{session_id}")
            assert response.status_code == 200
            repeated_message = next(
                message
                for message in response.json()["messages"]
                if message["id"] == "unknown-reviewer"
            )
            assert repeated_message["status"] == "submission_unknown"
            assert repeated_message["job_id"] is None
    finally:
        client.close()


def test_submission_unknown_retry_creates_a_new_follow_up_attempt() -> None:
    client, container = build_session_client_with_container()
    try:
        session_response = client.post("/sessions", json={"title": "Manual retry"})
        assert session_response.status_code == 201
        session_id = session_response.json()["id"]

        message_response = client.post(
            f"/sessions/{session_id}/messages",
            json={"message": "Recover this follow-up"},
        )
        assert message_response.status_code == 202
        primary_job = wait_for_job(client, message_response.json()["job_id"])
        run_id = primary_job["run_id"]
        assert run_id is not None

        repository = container.message_service._repository
        session = repository.get_session(session_id)
        assert session is not None
        session.agent_configuration = build_agent_configuration_domain(
            preset="review",
            reviewer_enabled=True,
            summary_enabled=False,
        )
        session.agent_configuration.agents[AgentId.GENERATOR].max_turns = 1
        session.touch()
        repository.save_session(session)

        unknown_message = ChatMessage(
            id="unknown-retry-reviewer",
            session_id=session_id,
            role=ChatMessageRole.USER,
            author_type=ChatMessageAuthorType.REVIEWER_CODEX,
            content="Automatic recovery stopped to avoid duplicate execution.",
            status=ChatMessageStatus.SUBMISSION_UNKNOWN,
            agent_id=AgentId.REVIEWER,
            agent_label="Reviewer",
            trigger_source=AgentTriggerSource.GENERATOR,
            run_id=run_id,
            dedupe_key=f"run:{run_id}:reviewer:1",
            submission_token=f"submission:{run_id}:reviewer:1",
        )
        repository.save_message(unknown_message)

        recovery_response = client.post(
            f"/sessions/{session_id}/messages/{unknown_message.id}/recovery",
            json={"action": "retry"},
        )
        assert recovery_response.status_code == 200

        session_payload = wait_for_session(
            client,
            session_id,
            predicate=lambda payload: any(
                message.get("recovered_from_message_id") == unknown_message.id
                and message["status"] == "completed"
                for message in payload["messages"]
            ),
        )

        old_message = next(
            message
            for message in session_payload["messages"]
            if message["id"] == unknown_message.id
        )
        new_message = next(
            message
            for message in session_payload["messages"]
            if message.get("recovered_from_message_id") == unknown_message.id
        )

        assert old_message["status"] == "cancelled"
        assert (
            old_message["reason_code"]
            == ChatMessageReasonCode.MANUAL_RETRY_REQUESTED.value
        )
        assert old_message["recovery_action"] == MessageRecoveryAction.RETRY.value
        assert old_message["recovered_from_message_id"] is None
        assert old_message["superseded_by_message_id"] == new_message["id"]
        assert new_message["id"] != old_message["id"]
        assert new_message["dedupe_key"] != old_message["dedupe_key"] if "dedupe_key" in new_message else True
        assert new_message["recovered_from_message_id"] == unknown_message.id
        assert (
            new_message["reason_code"]
            == ChatMessageReasonCode.MANUAL_RETRY_REQUESTED.value
        )
        assert new_message["superseded_by_message_id"] is None
        assert new_message["job_id"] is not None
        assert new_message["submission_token"] != old_message["submission_token"]
    finally:
        client.close()


def test_submission_unknown_cancel_marks_message_terminal_without_retry() -> None:
    client, container = build_session_client_with_container()
    try:
        session_response = client.post("/sessions", json={"title": "Manual cancel"})
        assert session_response.status_code == 201
        session_id = session_response.json()["id"]

        repository = container.message_service._repository
        session = repository.get_session(session_id)
        assert session is not None
        session.active_agent_run_id = "run-manual-cancel"
        session.touch()
        repository.save_session(session)
        unknown_message = ChatMessage(
            id="unknown-cancel-reviewer",
            session_id=session_id,
            role=ChatMessageRole.USER,
            author_type=ChatMessageAuthorType.REVIEWER_CODEX,
            content="Automatic recovery stopped to avoid duplicate execution.",
            status=ChatMessageStatus.SUBMISSION_UNKNOWN,
            agent_id=AgentId.REVIEWER,
            trigger_source=AgentTriggerSource.GENERATOR,
            run_id="run-manual-cancel",
            dedupe_key="run:run-manual-cancel:reviewer:1",
            submission_token="submission:manual-cancel",
        )
        repository.save_message(unknown_message)

        response = client.post(
            f"/sessions/{session_id}/messages/{unknown_message.id}/recovery",
            json={"action": "cancel"},
        )
        assert response.status_code == 200
        payload = response.json()
        message = next(
            item for item in payload["messages"] if item["id"] == unknown_message.id
        )
        assert message["status"] == "cancelled"
        assert (
            message["reason_code"]
            == ChatMessageReasonCode.MANUAL_CANCEL_REQUESTED.value
        )
        assert message["recovery_action"] == MessageRecoveryAction.CANCEL.value
        assert message["recovered_from_message_id"] is None
        assert message["superseded_by_message_id"] is None
        assert message["job_id"] is None
        persisted_session = repository.get_session(session_id)
        assert persisted_session is not None
        assert persisted_session.active_agent_run_id is None
    finally:
        client.close()


def test_submission_unknown_retry_survives_sqlite_restart() -> None:
    with TemporaryDirectory() as temp_dir:
        database_path = str(Path(temp_dir) / "recovery-restart.sqlite3")

        first_client, first_container = build_sqlite_session_client_with_container(
            database_path
        )
        try:
            session_response = first_client.post("/sessions", json={"title": "Restart retry"})
            assert session_response.status_code == 201
            session_id = session_response.json()["id"]

            message_response = first_client.post(
                f"/sessions/{session_id}/messages",
                json={"message": "Recover after restart"},
            )
            assert message_response.status_code == 202
            primary_job = wait_for_job(first_client, message_response.json()["job_id"])
            run_id = primary_job["run_id"]
            assert run_id is not None

            repository = first_container.message_service._repository
            session = repository.get_session(session_id)
            assert session is not None
            session.agent_configuration = build_agent_configuration_domain(
                preset="review",
                reviewer_enabled=True,
                summary_enabled=False,
            )
            session.agent_configuration.agents[AgentId.GENERATOR].max_turns = 1
            session.touch()
            repository.save_session(session)

            repository.save_message(
                ChatMessage(
                    id="restart-unknown-reviewer",
                    session_id=session_id,
                    role=ChatMessageRole.USER,
                    author_type=ChatMessageAuthorType.REVIEWER_CODEX,
                    content="Automatic recovery stopped to avoid duplicate execution.",
                    status=ChatMessageStatus.SUBMISSION_UNKNOWN,
                    agent_id=AgentId.REVIEWER,
                    agent_label="Reviewer",
                    trigger_source=AgentTriggerSource.GENERATOR,
                    run_id=run_id,
                    dedupe_key=f"run:{run_id}:reviewer:1",
                    submission_token=f"submission:{run_id}:reviewer:1",
                )
            )
        finally:
            first_client.close()

        restarted_client, _ = build_sqlite_session_client_with_container(database_path)
        try:
            recovery_response = restarted_client.post(
                f"/sessions/{session_id}/messages/restart-unknown-reviewer/recovery",
                json={"action": "retry"},
            )
            assert recovery_response.status_code == 200

            session_payload = wait_for_session(
                restarted_client,
                session_id,
                predicate=lambda payload: any(
                    message.get("recovered_from_message_id")
                    == "restart-unknown-reviewer"
                    and message["status"] == "completed"
                    for message in payload["messages"]
                ),
            )

            old_message = next(
                message
                for message in session_payload["messages"]
                if message["id"] == "restart-unknown-reviewer"
            )
            new_message = next(
                message
                for message in session_payload["messages"]
                if message.get("recovered_from_message_id")
                == "restart-unknown-reviewer"
            )
            assert old_message["status"] == "cancelled"
            assert old_message["superseded_by_message_id"] == new_message["id"]
            assert (
                old_message["reason_code"]
                == ChatMessageReasonCode.MANUAL_RETRY_REQUESTED.value
            )
            assert new_message["job_id"] is not None
            assert (
                new_message["reason_code"]
                == ChatMessageReasonCode.MANUAL_RETRY_REQUESTED.value
            )
            assert (
                new_message["recovered_from_message_id"]
                == "restart-unknown-reviewer"
            )
        finally:
            restarted_client.close()


def test_submission_unknown_recovery_rejects_invalid_transitions() -> None:
    client, container = build_session_client_with_container()
    try:
        session_response = client.post("/sessions", json={"title": "Invalid recovery"})
        assert session_response.status_code == 201
        session_id = session_response.json()["id"]

        repository = container.message_service._repository
        session = repository.get_session(session_id)
        assert session is not None

        completed_message = ChatMessage(
            id="not-unknown",
            session_id=session_id,
            role=ChatMessageRole.ASSISTANT,
            author_type=ChatMessageAuthorType.ASSISTANT,
            content="done",
            status=ChatMessageStatus.COMPLETED,
        )
        repository.save_message(completed_message)

        invalid_status_response = client.post(
            f"/sessions/{session_id}/messages/{completed_message.id}/recovery",
            json={"action": "retry"},
        )
        assert invalid_status_response.status_code == 409

        blocked_message = ChatMessage(
            id="blocked-unknown",
            session_id=session_id,
            role=ChatMessageRole.USER,
            author_type=ChatMessageAuthorType.REVIEWER_CODEX,
            content="Automatic recovery stopped to avoid duplicate execution.",
            status=ChatMessageStatus.SUBMISSION_UNKNOWN,
            agent_id=AgentId.REVIEWER,
            trigger_source=AgentTriggerSource.GENERATOR,
            run_id="run-blocked",
            submission_token="submission:blocked",
        )
        repository.save_message(blocked_message)
        session.active_agent_run_id = "run-other"
        session.touch()
        repository.save_session(session)

        blocked_response = client.post(
            f"/sessions/{session_id}/messages/{blocked_message.id}/recovery",
            json={"action": "retry"},
        )
        assert blocked_response.status_code == 409

        blocked_message.sync(
            status=ChatMessageStatus.CANCELLED,
            recovery_action=MessageRecoveryAction.CANCEL,
        )
        repository.save_message(blocked_message)

        repeat_response = client.post(
            f"/sessions/{session_id}/messages/{blocked_message.id}/recovery",
            json={"action": "cancel"},
        )
        assert repeat_response.status_code == 409
    finally:
        client.close()


def test_new_user_turn_cancels_reserved_follow_up_from_superseded_run() -> None:
    client, container = build_session_client_with_container()
    try:
        session_response = client.post("/sessions", json={"title": "Superseded"})
        assert session_response.status_code == 201
        session_id = session_response.json()["id"]

        repository = container.message_service._repository
        session = repository.get_session(session_id)
        assert session is not None
        session.active_agent_run_id = "run-old"
        session.touch()
        repository.save_session(session)

        repository.reserve_message(
            ChatMessage(
                id="reserved-old-reviewer",
                session_id=session_id,
                role=ChatMessageRole.USER,
                author_type=ChatMessageAuthorType.REVIEWER_CODEX,
                content="",
                status=ChatMessageStatus.RESERVED,
                agent_id=AgentId.REVIEWER,
                trigger_source=AgentTriggerSource.GENERATOR,
                run_id="run-old",
                dedupe_key="run:run-old:reviewer:1",
            )
        )

        message_response = client.post(
            f"/sessions/{session_id}/messages",
            json={"message": "Start the newer run"},
        )
        assert message_response.status_code == 202
        new_job = wait_for_job(client, message_response.json()["job_id"])

        session_payload = client.get(f"/sessions/{session_id}")
        assert session_payload.status_code == 200
        payload = session_payload.json()

        old_reserved = next(
            message
            for message in payload["messages"]
            if message["id"] == "reserved-old-reviewer"
        )
        assert old_reserved["status"] == "cancelled"
        assert (
            old_reserved["reason_code"]
            == ChatMessageReasonCode.SUPERSEDED_BY_NEWER_RUN.value
        )
        assert old_reserved["job_id"] is None
        assert "Superseded by a newer user turn" in old_reserved["content"]
        assert all(
            not (
                message["run_id"] == "run-old"
                and message["agent_id"] == "reviewer"
                and message["job_id"] is not None
            )
            for message in payload["messages"]
        )
        assert any(
            message["run_id"] == new_job["run_id"] and message["agent_id"] == "generator"
            for message in payload["messages"]
        )

        for _ in range(2):
            response = client.get(f"/sessions/{session_id}")
            assert response.status_code == 200
            repeated_payload = response.json()
            repeated_old_reserved = next(
                message
                for message in repeated_payload["messages"]
                if message["id"] == "reserved-old-reviewer"
            )
            assert repeated_old_reserved["status"] == "cancelled"
            assert repeated_old_reserved["job_id"] is None
    finally:
        client.close()


def test_terminal_follow_up_reason_code_marks_run_completion_path() -> None:
    client, container = build_session_client_with_container()
    try:
        session_response = client.post("/sessions", json={"title": "Terminal follow-up"})
        assert session_response.status_code == 201
        session_id = session_response.json()["id"]

        message_response = client.post(
            f"/sessions/{session_id}/messages",
            json={"message": "Trigger the run"},
        )
        assert message_response.status_code == 202
        primary_job = wait_for_job(client, message_response.json()["job_id"])
        run_id = primary_job["run_id"]
        assert run_id is not None

        repository = container.message_service._repository
        session = repository.get_session(session_id)
        assert session is not None
        session.agent_configuration = build_agent_configuration_domain(
            preset="review",
            reviewer_enabled=False,
            summary_enabled=False,
        )
        session.active_agent_run_id = run_id
        session.touch()
        repository.save_session(session)

        repository.reserve_message(
            ChatMessage(
                id="disabled-reviewer",
                session_id=session_id,
                role=ChatMessageRole.USER,
                author_type=ChatMessageAuthorType.REVIEWER_CODEX,
                content="",
                status=ChatMessageStatus.RESERVED,
                agent_id=AgentId.REVIEWER,
                trigger_source=AgentTriggerSource.GENERATOR,
                run_id=run_id,
                dedupe_key=f"run:{run_id}:reviewer:1",
            )
        )

        payload = wait_for_session(
            client,
            session_id,
            predicate=lambda response_payload: any(
                message["id"] == "disabled-reviewer"
                and message["status"] == "cancelled"
                for message in response_payload["messages"]
            )
            and response_payload["active_agent_run_id"] is None,
        )
        terminal_message = next(
            item
            for item in payload["messages"]
            if item["id"] == "disabled-reviewer"
        )
        assert (
            terminal_message["reason_code"]
            == ChatMessageReasonCode.FOLLOW_UP_TERMINAL_COMPLETED_RUN.value
        )
    finally:
        client.close()


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


def test_audio_messages_from_different_sessions_stay_isolated_under_overlap() -> None:
    first_client, second_client = build_slow_audio_clients()

    first_session = first_client.post("/sessions", json={"title": "Audio A"})
    second_session = first_client.post("/sessions", json={"title": "Audio B"})
    assert first_session.status_code == 201
    assert second_session.status_code == 201
    first_session_id = first_session.json()["id"]
    second_session_id = second_session.json()["id"]

    accepted_responses: dict[str, object] = {}
    finished_at: dict[str, float] = {}
    started_at = time.monotonic()

    def submit_audio(
        client: TestClient,
        *,
        key: str,
        session_id: str,
        filename: str,
    ) -> None:
        accepted_responses[key] = client.post(
            "/message/audio",
            data={"session_id": session_id},
            files={"audio": (filename, b"fake audio bytes", "audio/mp4")},
        )
        finished_at[key] = time.monotonic()

    first_worker = threading.Thread(
        target=submit_audio,
        kwargs={
            "client": first_client,
            "key": "first",
            "session_id": first_session_id,
            "filename": "voice-a.m4a",
        },
        daemon=True,
    )
    second_worker = threading.Thread(
        target=submit_audio,
        kwargs={
            "client": second_client,
            "key": "second",
            "session_id": second_session_id,
            "filename": "voice-b.m4a",
        },
        daemon=True,
    )
    first_worker.start()
    time.sleep(0.05)
    second_worker.start()
    first_worker.join(timeout=5)
    second_worker.join(timeout=5)
    elapsed_seconds = time.monotonic() - started_at

    assert "first" in accepted_responses
    assert "second" in accepted_responses
    assert accepted_responses["first"].status_code == 202
    assert accepted_responses["second"].status_code == 202
    assert elapsed_seconds < 0.75
    assert abs(finished_at["first"] - finished_at["second"]) < 0.35

    first_job = wait_for_job(first_client, accepted_responses["first"].json()["job_id"])
    second_job = wait_for_job(second_client, accepted_responses["second"].json()["job_id"])
    assert first_job["session_id"] == first_session_id
    assert second_job["session_id"] == second_session_id
    assert first_job["message"] == "Transcribed audio from voice-a.m4a"
    assert second_job["message"] == "Transcribed audio from voice-b.m4a"

    first_payload = first_client.get(f"/sessions/{first_session_id}").json()
    second_payload = second_client.get(f"/sessions/{second_session_id}").json()
    assert len(first_payload["messages"]) == 2
    assert len(second_payload["messages"]) == 2
    assert first_payload["messages"][0]["content"] == "Transcribed audio from voice-a.m4a"
    assert second_payload["messages"][0]["content"] == "Transcribed audio from voice-b.m4a"


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


def test_agent_creator_profile_can_seed_a_new_chat_for_agent_design() -> None:
    client = build_session_client()

    profiles = list_agent_profiles(client)
    agent_creator = next(
        profile for profile in profiles if profile["id"] == "agent_creator"
    )

    session_response = client.post(
        "/sessions",
        json={
            "agent_profile_id": agent_creator["id"],
        },
    )
    assert session_response.status_code == 201
    session_payload = session_response.json()

    assert session_payload["agent_profile_name"] == "Agent Creator"
    assert session_payload["agent_profile_color"] == agent_creator["color_hex"]
    assert session_payload["agent_configuration"]["agents"][0]["label"] == "Agent Creator"
    assert (
        session_payload["agent_configuration"]["agents"][0]["prompt"]
        == agent_creator["prompt"]
    )

    create_message_response = client.post(
        "/message",
        json={
            "session_id": session_payload["id"],
            "message": "Create an agent that reviews pull requests for API regressions.",
        },
    )
    assert create_message_response.status_code == 202

    job_payload = wait_for_job(client, create_message_response.json()["job_id"])

    assert job_payload["status"] == "completed"
    assert "Agent Creator Codex" in job_payload["response"]
    assert "Create an agent that reviews pull requests" in job_payload["response"]


def test_builtin_registry_includes_supervisor_and_specialist_profiles() -> None:
    client = build_session_client()

    profiles = list_agent_profiles(client)
    by_id = {profile["id"]: profile for profile in profiles}

    assert {
        "default",
        "agent_creator",
        "supervisor",
        "qa",
        "ux",
        "senior_engineer",
    }.issubset(by_id)
    assert by_id["supervisor"]["configuration"]["preset"] == "supervisor"
    assert by_id["supervisor"]["configuration"]["supervisor_member_ids"] == [
        "qa",
        "ux",
        "senior_engineer",
    ]
    assert "Supervisor Codex" in by_id["supervisor"]["prompt"]
    assert by_id["qa"]["configuration"]["preset"] == "solo"
    assert "QA Codex" in by_id["qa"]["prompt"]


def test_corrupt_reserved_builtin_profile_id_is_hidden_from_listing_and_export() -> None:
    with TemporaryDirectory() as temp_dir:
        database_path = str(Path(temp_dir) / "reserved-builtin-profile.sqlite3")
        client, container = build_sqlite_session_client_with_container(database_path)
        try:
            repository = container.message_service._repository
            corrupt_profile = AgentProfile(
                id="default",
                name="Corrupt Default",
                description="Should never shadow the builtin default profile.",
                color_hex="#224466",
                prompt="You are a corrupt shadow profile.",
                configuration=AgentConfiguration.default(),
            ).normalized()
            repository.save_agent_profile(corrupt_profile)

            listed_profiles = list_agent_profiles(client)
            listed_default = next(profile for profile in listed_profiles if profile["id"] == "default")
            assert listed_default["name"] == "Generator"
            assert all(profile["name"] != "Corrupt Default" for profile in listed_profiles)

            export_response = client.get("/agent-profiles/export")
            assert export_response.status_code == 200
            exported_profiles = export_response.json()
            assert exported_profiles == []

            resolved_profile = container.message_service.get_agent_profile("default")
            assert resolved_profile.name == "Generator"

            issues = repository.validate_integrity()
            assert len(issues) == 1
            issue = issues[0]
            assert issue.table == "agent_profiles"
            assert issue.row_id == "default"
            assert issue.field == "id"
            assert issue.code == "reserved_builtin_id"
            assert (
                issue.detail
                == "Agent profile id default is reserved for a builtin profile "
                "and cannot be stored in persistence."
            )
        finally:
            client.close()


def test_supervisor_profile_preserves_selected_specialists_when_applied() -> None:
    client = build_session_client()
    configuration = build_supervisor_configuration_payload(
        supervisor_member_ids=["qa", "senior_engineer"],
    )
    for agent in configuration["agents"]:
        if agent["agent_id"] == "supervisor":
            agent["label"] = "Delivery Supervisor"
        elif agent["agent_id"] == "qa":
            agent["label"] = "Release QA"
        elif agent["agent_id"] == "senior_engineer":
            agent["label"] = "Principal Engineer"

    create_profile_response = client.post(
        "/agent-profiles",
        json={
            "name": "Delivery Supervisor",
            "description": "Plans and delegates to specialists.",
            "color_hex": "#43C6DB",
            "configuration": configuration,
        },
    )
    assert create_profile_response.status_code == 201
    profile = create_profile_response.json()

    assert profile["prompt"] == configuration["agents"][3]["prompt"]
    assert profile["configuration"]["preset"] == "supervisor"
    assert profile["configuration"]["supervisor_member_ids"] == [
        "qa",
        "senior_engineer",
    ]

    session_response = client.post(
        "/sessions",
        json={"agent_profile_id": profile["id"]},
    )
    assert session_response.status_code == 201
    session_payload = session_response.json()

    assert session_payload["agent_profile_name"] == "Delivery Supervisor"
    assert session_payload["agent_configuration"]["preset"] == "supervisor"
    assert session_payload["agent_configuration"]["supervisor_member_ids"] == [
        "qa",
        "senior_engineer",
    ]

    agents_by_id = {
        agent["agent_id"]: agent
        for agent in session_payload["agent_configuration"]["agents"]
    }
    assert agents_by_id["supervisor"]["enabled"] is True
    assert agents_by_id["supervisor"]["label"] == "Delivery Supervisor"
    assert agents_by_id["qa"]["enabled"] is True
    assert agents_by_id["qa"]["label"] == "Release QA"
    assert agents_by_id["ux"]["enabled"] is False
    assert agents_by_id["senior_engineer"]["enabled"] is True
    assert agents_by_id["senior_engineer"]["label"] == "Principal Engineer"


def test_sqlite_supervisor_profile_survives_restart_with_supervisor_members_intact() -> None:
    with TemporaryDirectory() as temp_dir:
        database_path = str(Path(temp_dir) / "supervisor-profile.sqlite3")
        create_client, _ = build_sqlite_session_client_with_container(database_path)
        try:
            configuration = build_supervisor_configuration_payload(
                supervisor_member_ids=["qa", "ux"],
            )
            create_profile_response = create_client.post(
                "/agent-profiles",
                json={
                    "name": "Persistent Supervisor",
                    "description": "Persists supervisor routing across restarts.",
                    "color_hex": "#43C6DB",
                    "configuration": configuration,
                },
            )
            assert create_profile_response.status_code == 201
            created_profile = create_profile_response.json()
        finally:
            create_client.close()

        restart_client, restart_container = build_sqlite_session_client_with_container(database_path)
        try:
            listed_profiles = list_agent_profiles(restart_client)
            restarted_profile = next(
                profile for profile in listed_profiles if profile["id"] == created_profile["id"]
            )
            assert restarted_profile["configuration"]["preset"] == "supervisor"
            assert restarted_profile["configuration"]["supervisor_member_ids"] == [
                "qa",
                "ux",
            ]

            session_response = restart_client.post("/sessions", json={})
            assert session_response.status_code == 201
            session_id = session_response.json()["id"]

            apply_response = restart_client.put(
                f"/sessions/{session_id}/agent-profile",
                json={"profile_id": created_profile["id"]},
            )
            assert apply_response.status_code == 200
            payload = apply_response.json()

            assert payload["agent_configuration"]["preset"] == "supervisor"
            assert payload["agent_configuration"]["supervisor_member_ids"] == [
                "qa",
                "ux",
            ]
            agents_by_id = {
                agent["agent_id"]: agent
                for agent in payload["agent_configuration"]["agents"]
            }
            assert agents_by_id["supervisor"]["enabled"] is True
            assert agents_by_id["qa"]["enabled"] is True
            assert agents_by_id["ux"]["enabled"] is True
            assert agents_by_id["senior_engineer"]["enabled"] is False

            issues = restart_container.message_service.validate_persistence_integrity()
            assert issues == []
        finally:
            restart_client.close()


def test_custom_agent_profile_can_be_created_and_used_for_a_new_chat() -> None:
    client = build_session_client()
    configuration = build_agent_configuration_payload(
        preset="review",
        display_mode="collapse_specialists",
        reviewer_enabled=True,
        summary_enabled=False,
    )
    configuration["agents"][0]["label"] = "API Guardian"
    configuration["agents"][0]["prompt"] = (
        "You are API Guardian Codex. Focus on backend API changes, regressions, "
        "edge cases, contract drift, and missing validation."
    )
    configuration["agents"][1]["label"] = "Risk Reviewer"
    configuration["agents"][1]["prompt"] = (
        "Review the backend changes and return the next implementation prompt."
    )

    create_profile_response = client.post(
        "/agent-profiles",
        json={
            "name": "API Guardian",
            "description": "Reviews backend API changes for regressions and gaps.",
            "color_hex": "#C96BFF",
            "configuration": configuration,
        },
    )
    assert create_profile_response.status_code == 201
    created_profile = create_profile_response.json()

    session_response = client.post(
        "/sessions",
        json={
            "agent_profile_id": created_profile["id"],
        },
    )
    assert session_response.status_code == 201
    session_payload = session_response.json()

    assert session_payload["agent_profile_id"] == created_profile["id"]
    assert session_payload["agent_profile_name"] == "API Guardian"
    assert session_payload["agent_profile_color"] == "#C96BFF"
    assert session_payload["agent_configuration"]["agents"][0]["label"] == "API Guardian"
    assert session_payload["agent_configuration"]["preset"] == "review"
    assert session_payload["agent_configuration"]["display_mode"] == "collapse_specialists"
    assert session_payload["agent_configuration"]["agents"][1]["label"] == "Risk Reviewer"
    assert session_payload["agent_configuration"]["agents"][2]["enabled"] is False

    create_message_response = client.post(
        "/message",
        json={
            "session_id": session_payload["id"],
            "message": "Review the current API layer for backwards compatibility risks.",
        },
    )
    assert create_message_response.status_code == 202

    job_payload = wait_for_job(client, create_message_response.json()["job_id"])

    assert job_payload["status"] == "completed"
    assert "API Guardian Codex" in job_payload["response"]
    assert "backwards compatibility risks" in job_payload["response"]


def test_agent_profile_can_be_applied_to_an_existing_session() -> None:
    client = build_session_client()
    configuration = build_agent_configuration_payload(
        preset="triad",
        display_mode="summary_only",
        reviewer_enabled=True,
        summary_enabled=True,
        reviewer_visibility="hidden",
    )
    configuration["agents"][0]["label"] = "Docs Pilot"
    configuration["agents"][0]["prompt"] = (
        "You are Docs Pilot Codex. Improve documentation structure, examples, onboarding, and clarity."
    )
    configuration["agents"][1]["label"] = "Docs Reviewer"
    configuration["agents"][1]["max_turns"] = 2
    configuration["agents"][2]["label"] = "Release Summary"
    configuration["agents"][2]["max_turns"] = 2

    create_profile_response = client.post(
        "/agent-profiles",
        json={
            "name": "Docs Pilot",
            "description": "Shapes technical docs and onboarding flows.",
            "color_hex": "#FF8A5B",
            "configuration": configuration,
        },
    )
    assert create_profile_response.status_code == 201
    profile = create_profile_response.json()

    session_response = client.post(
        "/sessions",
        json={},
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    apply_response = client.put(
        f"/sessions/{session_id}/agent-profile",
        json={"profile_id": profile["id"]},
    )
    assert apply_response.status_code == 200
    session_payload = apply_response.json()

    assert session_payload["agent_profile_id"] == profile["id"]
    assert session_payload["agent_profile_name"] == "Docs Pilot"
    assert session_payload["agent_profile_color"] == "#FF8A5B"
    assert session_payload["agent_configuration"]["preset"] == "triad"
    assert session_payload["agent_configuration"]["display_mode"] == "summary_only"
    assert session_payload["agent_configuration"]["agents"][0]["prompt"] == profile["prompt"]
    assert session_payload["agent_configuration"]["agents"][1]["label"] == "Docs Reviewer"
    assert session_payload["agent_configuration"]["agents"][1]["max_turns"] == 2
    assert session_payload["agent_configuration"]["agents"][2]["label"] == "Release Summary"
    assert session_payload["agent_configuration"]["agents"][2]["max_turns"] == 2


def test_applying_agent_profile_is_rejected_while_run_is_in_flight() -> None:
    client = build_session_client()
    create_profile_response = client.post(
        "/agent-profiles",
        json={
            "name": "Busy Switch",
            "description": "Used to test profile switching races.",
            "color_hex": "#4FA3FF",
            "configuration": build_agent_configuration_payload(
                preset="review",
                display_mode="collapse_specialists",
                reviewer_enabled=True,
                summary_enabled=False,
            ),
        },
    )
    assert create_profile_response.status_code == 201
    profile_id = create_profile_response.json()["id"]

    session_response = client.post("/sessions", json={"title": "Profile race"})
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    message_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "sleep:0.3:profile switch race"},
    )
    assert message_response.status_code == 202

    apply_response = client.put(
        f"/sessions/{session_id}/agent-profile",
        json={"profile_id": profile_id},
    )
    assert apply_response.status_code == 409
    assert "while work is in flight" in apply_response.json()["detail"]

    session_payload = client.get(f"/sessions/{session_id}").json()
    assert session_payload["agent_profile_id"] == "default"
    assert session_payload["agent_profile_name"] == "Generator"
    assert session_payload["agent_configuration"]["preset"] == "solo"

    wait_for_job(client, message_response.json()["job_id"])

    completed_payload = client.get(f"/sessions/{session_id}").json()
    assert completed_payload["agent_profile_id"] == "default"
    assert completed_payload["agent_configuration"]["preset"] == "solo"
    assert "profile switch race" in completed_payload["messages"][1]["content"]


def test_updating_agent_configuration_is_rejected_while_run_is_in_flight() -> None:
    client = build_session_client()
    session_response = client.post("/sessions", json={"title": "Config race"})
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    message_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "sleep:0.3:config switch race"},
    )
    assert message_response.status_code == 202

    update_response = client.put(
        f"/sessions/{session_id}/agents",
        json=build_agent_configuration_payload(
            preset="review",
            display_mode="collapse_specialists",
            reviewer_enabled=True,
            summary_enabled=False,
        ),
    )
    assert update_response.status_code == 409
    assert "while work is in flight" in update_response.json()["detail"]

    session_payload = client.get(f"/sessions/{session_id}").json()
    assert session_payload["agent_configuration"]["preset"] == "solo"
    assert session_payload["auto_mode_enabled"] is False

    wait_for_job(client, message_response.json()["job_id"])

    completed_payload = client.get(f"/sessions/{session_id}").json()
    assert completed_payload["agent_configuration"]["preset"] == "solo"
    assert "config switch race" in completed_payload["messages"][1]["content"]


def test_updating_auto_mode_is_rejected_while_run_is_in_flight() -> None:
    client = build_session_client()
    session_response = client.post("/sessions", json={"title": "Auto race"})
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    message_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "sleep:0.3:auto mode race"},
    )
    assert message_response.status_code == 202

    auto_mode_response = client.put(
        f"/sessions/{session_id}/auto-mode",
        json={
            "enabled": True,
            "max_turns": 1,
            "reviewer_prompt": "Review the active run.",
        },
    )
    assert auto_mode_response.status_code == 409
    assert "while work is in flight" in auto_mode_response.json()["detail"]

    session_payload = client.get(f"/sessions/{session_id}").json()
    assert session_payload["auto_mode_enabled"] is False
    assert session_payload["agent_configuration"]["preset"] == "solo"

    wait_for_job(client, message_response.json()["job_id"])

    completed_payload = client.get(f"/sessions/{session_id}").json()
    assert completed_payload["auto_mode_enabled"] is False
    assert completed_payload["agent_configuration"]["preset"] == "solo"


def test_profile_and_configuration_updates_succeed_after_run_completes() -> None:
    client = build_session_client()
    create_profile_response = client.post(
        "/agent-profiles",
        json={
            "name": "Post Run Switch",
            "description": "Applied after the active run completes.",
            "color_hex": "#4FA3FF",
            "configuration": build_agent_configuration_payload(
                preset="review",
                display_mode="collapse_specialists",
                reviewer_enabled=True,
                summary_enabled=False,
            ),
        },
    )
    assert create_profile_response.status_code == 201
    profile_id = create_profile_response.json()["id"]

    session_response = client.post("/sessions", json={"title": "Reconfig after run"})
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    message_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "sleep:0.3:finish before reconfiguring"},
    )
    assert message_response.status_code == 202
    wait_for_session(
        client,
        session_id,
        predicate=lambda payload: payload["active_agent_run_id"] is None
        and len(payload["messages"]) >= 2
        and payload["messages"][1]["status"] == "completed",
    )

    apply_response = client.put(
        f"/sessions/{session_id}/agent-profile",
        json={"profile_id": profile_id},
    )
    assert apply_response.status_code == 200
    applied_payload = apply_response.json()
    assert applied_payload["agent_profile_id"] == profile_id
    assert applied_payload["agent_configuration"]["preset"] == "review"

    update_response = client.put(
        f"/sessions/{session_id}/agents",
        json=build_agent_configuration_payload(
            preset="triad",
            display_mode="summary_only",
            reviewer_enabled=True,
            summary_enabled=True,
        ),
    )
    assert update_response.status_code == 200
    updated_payload = update_response.json()
    assert updated_payload["agent_configuration"]["preset"] == "triad"
    assert updated_payload["agent_configuration"]["display_mode"] == "summary_only"


def test_reviewer_runs_again_when_multiple_review_turns_are_configured() -> None:
    client = build_session_client()

    session_response = client.post("/sessions", json={"title": "Reviewer loop"})
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    configuration = build_agent_configuration_payload(
        preset="review",
        display_mode="show_all",
        reviewer_enabled=True,
        summary_enabled=False,
    )
    configuration["agents"][0]["max_turns"] = 3
    configuration["agents"][1]["max_turns"] = 2

    config_response = client.put(
        f"/sessions/{session_id}/agents",
        json=configuration,
    )
    assert config_response.status_code == 200

    message_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "Keep iterating until the reviewer has acted twice."},
    )
    assert message_response.status_code == 202

    payload = wait_for_session(
        client,
        session_id,
        predicate=lambda session_payload: session_payload["active_agent_run_id"] is None
        and len(
            [
                message
                for message in session_payload["messages"]
                if message["agent_id"] == "reviewer"
                and message["status"] == "completed"
            ]
        )
        == 2
        and len(
            [
                message
                for message in session_payload["messages"]
                if message["agent_id"] == "generator"
                and message["status"] == "completed"
            ]
        )
        == 3,
    )

    completed_reviewers = [
        message
        for message in payload["messages"]
        if message["agent_id"] == "reviewer" and message["status"] == "completed"
    ]
    completed_generators = [
        message
        for message in payload["messages"]
        if message["agent_id"] == "generator" and message["status"] == "completed"
    ]

    assert len(completed_reviewers) == 2
    assert len(completed_generators) == 3
    assert payload["active_agent_turn_index"] == 2


def test_legacy_prompt_only_agent_profile_hydrates_default_configuration() -> None:
    client, container = build_session_client_with_container()
    repository = container.message_service._repository
    repository.save_agent_profile(
        container.message_service.create_agent_profile(
            name="temp",
            description="temp",
            color_hex="#112233",
            configuration=AgentConfiguration.default(),
        )
    )
    legacy_profile = repository.list_agent_profiles()[0]
    legacy_profile.name = "Legacy Analyst"
    legacy_profile.description = "Prompt-only profile from an older server."
    legacy_profile.color_hex = "#224466"
    legacy_profile.prompt = "You are Legacy Analyst Codex. Analyze older systems carefully."
    legacy_profile.configuration = None
    repository.save_agent_profile(legacy_profile)

    session_response = client.post(
        "/sessions",
        json={"agent_profile_id": legacy_profile.id},
    )
    assert session_response.status_code == 201
    payload = session_response.json()

    assert payload["agent_profile_name"] == "Legacy Analyst"
    assert payload["agent_configuration"]["preset"] == "solo"
    assert payload["agent_configuration"]["agents"][0]["label"] == "Legacy Analyst"
    assert (
        payload["agent_configuration"]["agents"][0]["prompt"]
        == "You are Legacy Analyst Codex. Analyze older systems carefully."
    )
    assert payload["agent_configuration"]["agents"][1]["enabled"] is False
    assert payload["agent_configuration"]["agents"][2]["enabled"] is False


def test_applying_profile_clears_provider_session_ids_from_reused_configuration() -> None:
    client, container = build_session_client_with_container()
    configuration = AgentConfiguration.default()
    configuration.preset = AgentPreset.TRIAD
    configuration.display_mode = AgentDisplayMode.SUMMARY_ONLY
    configuration.agents[AgentId.GENERATOR].label = "Pack Generator"
    configuration.agents[AgentId.GENERATOR].prompt = "You are Pack Generator."
    configuration.agents[AgentId.GENERATOR].provider_session_id = "generator-thread-old"
    configuration.agents[AgentId.REVIEWER].enabled = True
    configuration.agents[AgentId.REVIEWER].provider_session_id = "reviewer-thread-old"
    configuration.agents[AgentId.SUMMARY].enabled = True
    configuration.agents[AgentId.SUMMARY].provider_session_id = "summary-thread-old"
    profile = container.message_service.create_agent_profile(
        name="Reusable Pack",
        description="Stores a full triad pack.",
        color_hex="#1188AA",
        configuration=configuration,
    )

    session_response = client.post("/sessions", json={})
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    apply_response = client.put(
        f"/sessions/{session_id}/agent-profile",
        json={"profile_id": profile.id},
    )
    assert apply_response.status_code == 200
    payload = apply_response.json()

    generator = payload["agent_configuration"]["agents"][0]
    reviewer = payload["agent_configuration"]["agents"][1]
    summary = payload["agent_configuration"]["agents"][2]

    assert generator["provider_session_id"] is None
    assert reviewer["provider_session_id"] is None
    assert summary["provider_session_id"] is None
    assert payload["provider_session_id"] is None
    assert payload["reviewer_provider_session_id"] is None
    assert payload["agent_configuration"]["preset"] == "triad"
    assert payload["agent_configuration"]["display_mode"] == "summary_only"


def test_agent_profiles_can_be_exported_and_imported_as_json_packs() -> None:
    source_client = build_session_client()
    configuration = build_agent_configuration_payload(
        preset="review",
        display_mode="collapse_specialists",
        reviewer_enabled=True,
        summary_enabled=False,
    )
    configuration["agents"][0]["label"] = "Portable Pack"
    configuration["agents"][0]["prompt"] = "You are Portable Pack Codex."
    configuration["agents"][1]["label"] = "Portable Reviewer"
    create_response = source_client.post(
        "/agent-profiles",
        json={
            "name": "Portable Pack",
            "description": "Moves between servers.",
            "color_hex": "#55AAEE",
            "configuration": configuration,
        },
    )
    assert create_response.status_code == 201

    export_response = source_client.get("/agent-profiles/export")
    assert export_response.status_code == 200
    exported_profiles = export_response.json()
    assert len(exported_profiles) == 1
    assert exported_profiles[0]["name"] == "Portable Pack"
    assert exported_profiles[0]["configuration"]["preset"] == "review"

    destination_client = build_session_client()
    import_response = destination_client.post(
        "/agent-profiles/import",
        json={"profiles": exported_profiles},
    )
    assert import_response.status_code == 200
    imported_profiles = import_response.json()
    assert imported_profiles[0]["name"] == "Portable Pack"
    assert imported_profiles[0]["configuration"]["agents"][1]["label"] == "Portable Reviewer"


def test_import_rejects_builtin_agent_profile_ids() -> None:
    client = build_session_client()

    import_response = client.post(
        "/agent-profiles/import",
        json={
            "profiles": [
                {
                    "id": "default",
                    "name": "Generator",
                    "description": "Should not overwrite built-ins.",
                    "color_hex": "#55D6BE",
                    "prompt": "You are the primary implementation Codex.",
                    "configuration": build_agent_configuration_payload(
                        preset="solo",
                        reviewer_enabled=False,
                        summary_enabled=False,
                    ),
                    "is_builtin": False,
                }
            ]
        },
    )

    assert import_response.status_code == 422
    assert "immutable" in import_response.json()["detail"]
