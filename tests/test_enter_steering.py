"""Enter steers the running turn: Claude stream input, persistence and fallback."""

import json
import shlex
import sys
import time
from pathlib import Path

import pytest

from backend.app.domain.entities.agent_configuration import AgentId
from backend.app.domain.entities.chat_message import (
    ChatMessageAuthorType,
    ChatMessageReasonCode,
    ChatMessageRole,
)
from backend.app.domain.entities.job import JobStatus
from backend.app.infrastructure.execution.local_provider import LocalExecutionProvider


def steer_provider():
    fixture = Path(__file__).parent / "fixtures" / "fake_claude_steer.py"
    return LocalExecutionProvider(
        command="unused-codex",
        claude_command=f"{shlex.quote(sys.executable)} {shlex.quote(str(fixture))}",
    )


def wait_until(predicate, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    pytest.fail("condition not reached")


def wait_done(provider, job_id):
    wait_until(lambda: provider.get_status(job_id).is_terminal)
    return provider.get_snapshot(job_id)


def start_claude(provider, prompt, tmp_path):
    job_id = provider.execute(prompt, model="claude:sonnet", workdir=str(tmp_path))
    wait_until(lambda: job_id in provider._claude_steerers)
    return job_id


def test_claude_takes_the_instruction_mid_turn_without_stopping(tmp_path):
    provider = steer_provider()
    job_id = start_claude(provider, "hacé la tarea", tmp_path)

    assert provider.steer_job(job_id, "  usá pytest -q  ") is True

    snapshot = wait_done(provider, job_id)
    assert snapshot.status == JobStatus.COMPLETED
    # Same process, same turn: the answer already includes the instruction.
    assert snapshot.response == "tomé en cuenta: usá pytest -q"
    steer = [a for a in snapshot.activities if a["kind"] == "steer"]
    assert [a["title"] for a in steer] == ["usá pytest -q"]


def test_late_instruction_is_answered_as_continuation_before_finishing(tmp_path):
    provider = steer_provider()
    job_id = start_claude(provider, "LATE tarea", tmp_path)

    assert provider.steer_job(job_id, "agregá un resumen") is True

    snapshot = wait_done(provider, job_id)
    assert snapshot.status == JobStatus.COMPLETED
    # The job waited for the continuation and kept both answers.
    assert snapshot.response == "primera respuesta\n\ncontinuación: agregá un resumen"
    usage = [a for a in snapshot.activities if a["kind"] == "usage"]
    assert usage and json.loads(usage[0]["detail"])["input_tokens"] == 17


def test_finished_claude_job_refuses_steering(tmp_path):
    provider = steer_provider()
    job_id = start_claude(provider, "hacé la tarea", tmp_path)
    provider.steer_job(job_id, "seguí")
    wait_done(provider, job_id)
    assert job_id not in provider._claude_steerers
    assert provider.steer_job(job_id, "tarde") is False


def test_closed_claude_input_is_not_accepted(tmp_path):
    provider = steer_provider()
    job_id = start_claude(provider, "hacé la tarea", tmp_path)
    process = provider._processes[job_id]
    process.stdin.close()
    assert provider.steer_job(job_id, "no entra") is False
    provider.cancel_job(job_id)


class _Quality:
    def __init__(self):
        self.sources = []

    def chat_intake_context(self, *, workspace, source_ref, text):
        self.sources.append((workspace, source_ref, text))
        return "Acceptance intake for this human message. Source ID: source-x."

    def feedback_validation_context(self, workspace):
        return None


def _service(tmp_path, provider):
    from backend.app.application.services.message_service import MessageService
    from backend.app.domain.entities.agent_configuration import AgentConfiguration
    from backend.app.infrastructure.persistence.in_memory_chat_repository import (
        InMemoryChatRepository,
    )
    from backend.app.infrastructure.transcription.disabled_transcriber import (
        DisabledAudioTranscriber,
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    repository = InMemoryChatRepository(projects_root=str(tmp_path))
    quality = _Quality()
    service = MessageService(
        repository=repository,
        execution_provider=provider,
        default_workspace_path=str(workspace),
        audio_transcriber=DisabledAudioTranscriber(),
        quality_service=quality,
    )
    session = service.create_session(workspace_path=str(workspace))
    config = AgentConfiguration.default()
    config.agents[AgentId.GENERATOR].model = "claude:sonnet"
    service.update_agent_configuration(session_id=session.id, configuration=config)
    return service, repository, quality, session


def test_service_steers_running_claude_turn_and_persists_the_message(tmp_path):
    provider = steer_provider()
    service, repository, quality, session = _service(tmp_path, provider)
    job = service.submit_message("hacé la tarea", session_id=session.id)
    wait_until(lambda: job.id in provider._claude_steerers)

    steered = service.steer_job(job.id, "  cambiá a SQLite ", client_submission_id="sub-1")

    assert steered is not None
    assert steered.content == "cambiá a SQLite"
    assert steered.run_id == job.run_id
    assert steered.role == ChatMessageRole.USER
    assert steered.author_type == ChatMessageAuthorType.HUMAN
    assert steered.reason_code == ChatMessageReasonCode.STEERED_INTO_RUNNING_TURN
    # Same job: no new turn was queued and nothing was cancelled.
    assert [j.id for j in repository.list_jobs_for_session(session.id)] == [job.id]
    snapshot = wait_done(provider, job.id)
    assert snapshot.status == JobStatus.COMPLETED
    assert snapshot.response.startswith("tomé en cuenta: cambiá a SQLite\n\nAcceptance intake")
    # The timeline shows what the person wrote, not the internal intake.
    assert [a["title"] for a in snapshot.activities if a["kind"] == "steer"] == ["cambiá a SQLite"]
    steer_source = [s for s in quality.sources if ":steer:" in s[1]]
    assert steer_source == [
        (session.workspace_path, f"chat:{session.id}:run:{job.run_id}:steer:{steered.id}", "cambiá a SQLite")
    ]
    # The message survives a reload of the conversation, once.
    stored = [m for m in repository.list_messages(session.id) if m.id == steered.id]
    assert len(stored) == 1
    # A retried submission returns the same message without injecting it again.
    assert service.steer_job(job.id, "cambiá a SQLite", client_submission_id="sub-1").id == steered.id
    # The run's request stays the original message, not the steering.
    latest = service._latest_user_message_for_run(session.id, run_id=job.run_id)
    assert latest.content == "hacé la tarea"


def test_service_does_not_persist_when_the_agent_cannot_take_it(tmp_path):
    provider = steer_provider()
    service, repository, _, session = _service(tmp_path, provider)
    job = service.submit_message("hacé la tarea", session_id=session.id)
    wait_until(lambda: job.id in provider._claude_steerers)
    provider._processes[job.id].stdin.close()
    before = len(repository.list_messages(session.id))
    assert service.steer_job(job.id, "hola") is None
    assert len(repository.list_messages(session.id)) == before
    provider.cancel_job(job.id)


def test_native_commands_are_never_steered(tmp_path):
    provider = steer_provider()
    service, _, _, session = _service(tmp_path, provider)
    job = service.submit_message("hacé la tarea", session_id=session.id)
    wait_until(lambda: job.id in provider._claude_steerers)
    assert service.steer_job(job.id, "/compact") is None
    assert not [a for a in provider.get_snapshot(job.id).activities if a["kind"] == "steer"]
    provider.cancel_job(job.id)
