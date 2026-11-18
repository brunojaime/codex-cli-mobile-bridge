"""Regression tests for Claude auto permissions, runtime evidence and history isolation."""
import asyncio
import json
import shlex
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.application.services.message_service import MessageService
from backend.app.domain.ai_runtime import AiRuntimePolicy
from backend.app.domain.entities.agent_configuration import AgentId, AgentType, AgentTriggerSource
from backend.app.domain.entities.chat_message import (
    ChatMessage,
    ChatMessageAuthorType,
    ChatMessageRole,
    ChatMessageStatus,
)
from backend.app.domain.entities.codex_options import CodexRunOptions
from backend.app.domain.entities.job import JobConversationKind, JobStatus
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.execution import claude_evidence
from backend.app.infrastructure.execution.agent_cli import AgentCli, run_process
from backend.app.infrastructure.execution.local_provider import LocalExecutionProvider
from backend.app.infrastructure.persistence.in_memory_chat_repository import (
    InMemoryChatRepository,
)
from backend.app.infrastructure.transcription.disabled_transcriber import (
    DisabledAudioTranscriber,
)

FIXTURE = Path(__file__).parent / "fixtures" / "fake_claude.py"
POLICY = AiRuntimePolicy("claude", "claude-opus-5-5")


def provider(mode="auto"):
    return LocalExecutionProvider(
        command="unused-codex",
        claude_command=f"{shlex.quote(sys.executable)} {shlex.quote(str(FIXTURE))}",
        claude_permission_mode=mode,
        ai_policy=POLICY,
    )


def wait(p, job):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if p.get_status(job).is_terminal:
            return p.get_snapshot(job)
        time.sleep(0.01)
    pytest.fail("Job did not finish")


def test_settings_accept_auto_and_reject_bypass():
    assert Settings(_env_file=None, claude_permission_mode="auto").claude_permission_mode == "auto"
    with pytest.raises(ValueError):
        Settings(_env_file=None, claude_permission_mode="bypassPermissions")


def test_chat_applies_auto_and_records_cli_evidence():
    p = provider()
    snapshots = []
    job = p.execute("hello", model="gpt-5.4")
    p.watch_job(job, snapshots.append)
    result = wait(p, job)
    assert result.status == JobStatus.COMPLETED
    argv = json.loads(result.response)["argv"]
    assert argv[argv.index("--permission-mode") + 1] == "auto"
    assert argv[argv.index("--model") + 1] == "claude-opus-5-5"
    evidence = claude_evidence.latest()["chat"]
    assert evidence["permission_mode"] == "auto"
    assert evidence["model"] == "claude-opus-5-5"


def test_readonly_overrides_auto_and_is_still_verified():
    p = provider()
    result = wait(p, p.execute("triage", codex_options=CodexRunOptions(
        config_overrides=('sandbox_mode="read-only"',))))
    assert result.status == JobStatus.COMPLETED
    argv = json.loads(result.response)["argv"]
    # The restricted mode wins over the configured default; the CLI uses the last flag.
    assert claude_evidence.requested_flag(argv, "--permission-mode") == "dontAsk"
    assert claude_evidence.latest()["chat"]["permission_mode"] == "dontAsk"


@pytest.mark.parametrize("prompt,needle", [
    ("MODE_MISMATCH_FIXTURE", "permission mode"),
    ("MODEL_MISMATCH_FIXTURE", "reported model"),
    ("NO_INIT_FIXTURE", "not verified"),
])
def test_chat_fails_closed_when_cli_reports_another_runtime(prompt, needle):
    p = provider()
    result = wait(p, p.execute(prompt))
    assert result.status == JobStatus.FAILED
    assert needle in result.error


def _cli_script(tmp_path, init):
    events = ([init] if init else []) + [{"type": "result", "result": "done", "permission_denials": []}]
    script = tmp_path / "fake_cli.py"
    script.write_text(f"import json; print(json.dumps({events!r}))")
    return script


@pytest.mark.parametrize("init,ok", [
    ({"type": "system", "subtype": "init", "model": "claude-opus-5-5", "permissionMode": "auto"}, True),
    ({"type": "system", "subtype": "init", "model": "claude-opus-5-5", "permissionMode": "default"}, False),
    (None, False),
])
def test_secondary_cli_applies_and_verifies_auto(tmp_path, init, ok):
    cli = AgentCli(POLICY, permission_mode="auto")
    argv = cli.argv(prompt="task")
    assert "--verbose" in argv
    assert claude_evidence.requested_flag(argv, "--permission-mode") == "auto"
    # Run a fixture with the same flags, so verification compares against them.
    fake = (sys.executable, str(_cli_script(tmp_path, init)), *argv[1:])
    result = run_process(argv=fake, cwd=tmp_path, env={}, timeout_seconds=10)
    assert (result.returncode == 0) is ok
    if ok:
        assert result.stdout == "done"
        assert claude_evidence.latest()["agent_cli"]["permission_mode"] == "auto"


def test_container_wires_auto_into_chat_and_secondary_cli():
    from backend.app.container import _agent_cli, _build_execution_provider
    settings = Settings(_env_file=None, ai_provider="claude", ai_model="claude-opus-5-5",
                        claude_permission_mode="auto")
    assert _build_execution_provider(settings)._claude_permission_mode == "auto"
    assert claude_evidence.requested_flag(_agent_cli(settings).argv(prompt="x"), "--permission-mode") == "auto"


def _service(tmp_path, captured):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    repo = InMemoryChatRepository(projects_root=str(tmp_path))
    p = provider()
    p.execute = lambda message, **kwargs: captured.append(message) or f"job-{len(captured)}"
    service = MessageService(repository=repo, execution_provider=p,
        default_workspace_path=str(workspace), audio_transcriber=DisabledAudioTranscriber())
    session = service.create_session(workspace_path=str(workspace))
    for index, (role, agent, text) in enumerate([
        (ChatMessageRole.USER, AgentId.USER, "Keep the blue button"),
        (ChatMessageRole.ASSISTANT, AgentId.GENERATOR, "Generator says it is done"),
    ]):
        repo.save_message(ChatMessage(id=f"m{index}", session_id=session.id, role=role,
            author_type=ChatMessageAuthorType.HUMAN if role == ChatMessageRole.USER
            else ChatMessageAuthorType.ASSISTANT, agent_id=agent, content=text,
            status=ChatMessageStatus.COMPLETED))
    return service, session


def _start(service, session, kind, agent_id, agent_type, *, user_message_id=None):
    return service._start_job(session=session, display_message="x",
        execution_message="REQUEST", image_paths=None, cleanup_paths=None,
        user_message_id=user_message_id, assistant_message_id=None,
        provider_session_id="codex-thread", model=None, codex_options=None,
        serial_key="k", conversation_kind=kind, agent_id=agent_id, agent_type=agent_type,
        trigger_source=AgentTriggerSource.USER, run_id=None)


@pytest.mark.parametrize("kind,agent_id,agent_type", [
    (JobConversationKind.REVIEWER, AgentId.REVIEWER, AgentType.REVIEWER),
    (JobConversationKind.SUMMARY, AgentId.SUMMARY, AgentType.SUMMARY),
    (JobConversationKind.SPECIALIST, AgentId.QA, AgentType.QA),
    (JobConversationKind.SPECIALIST, AgentId.SENIOR_ENGINEER, AgentType.SENIOR_ENGINEER),
])
def test_independent_roles_never_receive_transferred_history(tmp_path, kind, agent_id, agent_type):
    captured = []
    service, session = _service(tmp_path, captured)
    _start(service, session, kind, agent_id, agent_type)
    assert captured == ["REQUEST"]


def test_owner_history_excludes_current_request_and_is_not_stored_for_retry(tmp_path):
    captured = []
    service, session = _service(tmp_path, captured)
    job = _start(service, session, JobConversationKind.PRIMARY, AgentId.GENERATOR,
                 AgentType.GENERATOR, user_message_id="m0")
    assert "<bridge_history>" in captured[0] and "Generator says it is done" in captured[0]
    assert "Keep the blue button" not in captured[0]
    # Retries rebuild history from the stored request instead of nesting it.
    assert job.execution_message == "REQUEST"
    session_retry = service._start_job(session=session, display_message="x",
        execution_message=job.execution_message, image_paths=None, cleanup_paths=None,
        user_message_id="m0", assistant_message_id=None, provider_session_id=None,
        model=None, codex_options=None, serial_key="k",
        conversation_kind=JobConversationKind.PRIMARY, agent_id=AgentId.GENERATOR,
        agent_type=AgentType.GENERATOR, trigger_source=AgentTriggerSource.USER, run_id=None)
    assert captured[1].count("<bridge_history>") == 1
    assert session_retry.execution_message == "REQUEST"


def test_lambda_applies_policy_and_refuses_claude():
    from backend.app.infrastructure.execution.lambda_provider import LambdaExecutionProvider
    pinned = LambdaExecutionProvider(endpoint="http://127.0.0.1:9",
        ai_policy=AiRuntimePolicy("codex", "gpt-5.4"))
    assert pinned.resolve_model("claude-opus-5-5") == "gpt-5.4"
    with pytest.raises(ValueError):
        LambdaExecutionProvider(endpoint="http://127.0.0.1:9").execute("x", model="claude-opus-5-5")


def test_claude_mcp_selection_never_invokes_codex_and_runtime_reports_mode(monkeypatch):
    from fastapi import HTTPException
    from backend.app.api import routes

    def forbidden(*args, **kwargs):
        raise AssertionError("codex mcp list must not run under Claude")

    monkeypatch.setattr(routes, "inspect_codex_mcp_server_selection", forbidden)
    container = SimpleNamespace(settings=Settings(_env_file=None, ai_provider="claude",
        ai_model="claude-opus-5-5", claude_permission_mode="auto"))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(routes._validate_codex_options(
            CodexRunOptions(mcp_server_ids=("github",)), container=container))
    assert exc.value.status_code == 422
    status = asyncio.run(routes.ai_runtime(container))
    assert status["permission_mode"] == "auto"
    assert isinstance(status["verified_runs"], dict)


@pytest.mark.parametrize("raw", [
    '```json\n{"status": "continue", "next_agent_id": "qa", "instruction": "Test it"}\n```',
    'Decision:\n{"status": "continue", "next_agent_id": "qa", "instruction": "Test it"}',
])
def test_supervisor_decision_tolerates_provider_fencing(tmp_path, raw):
    service, _ = _service(tmp_path, [])
    decision = service._parse_supervisor_decision(raw)
    assert decision is not None and decision.next_agent_id == AgentId.QA
    assert service._parse_supervisor_decision('```json\n{"status": "maybe"}\n```') is None


def test_internal_title_and_summary_jobs_get_no_tools_only_under_claude(tmp_path):
    from backend.app.infrastructure.execution.claude_options import translate_options
    service, _ = _service(tmp_path, [])
    args, _ = translate_options(service._text_only_options(None), workdir=None)
    assert args[args.index("--tools") + 1] == ""
    assert claude_evidence.requested_flag(args, "--permission-mode") == "dontAsk"
    codex = MessageService(repository=InMemoryChatRepository(projects_root=str(tmp_path)),
        execution_provider=LocalExecutionProvider(command="codex"),
        default_workspace_path=str(tmp_path), audio_transcriber=DisabledAudioTranscriber())
    assert codex._text_only_options("gpt-5.4") is None
