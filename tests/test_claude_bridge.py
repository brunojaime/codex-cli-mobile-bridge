import json
import shlex
import sys
import time
from pathlib import Path

import pytest

from backend.app.application.services.message_service import MessageService
from backend.app.domain.entities.agent_configuration import AgentConfiguration, AgentId
from backend.app.domain.entities.chat_message import (
    ChatMessage,
    ChatMessageRole,
    ChatMessageStatus,
    ChatMessageAuthorType,
)
from backend.app.domain.entities.codex_options import CodexRunOptions
from backend.app.domain.entities.job import JobStatus
from backend.app.infrastructure.execution.local_provider import LocalExecutionProvider
from backend.app.infrastructure.persistence.in_memory_chat_repository import (
    InMemoryChatRepository,
)
from backend.app.infrastructure.transcription.disabled_transcriber import (
    DisabledAudioTranscriber,
)


def provider(**kwargs):
    fixture = Path(__file__).parent / "fixtures" / "fake_claude.py"
    return LocalExecutionProvider(
        command="unused-codex",
        claude_command=(f"{shlex.quote(sys.executable)} {shlex.quote(str(fixture))}"),
        **kwargs,
    )


def wait(p, job):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if p.get_status(job).is_terminal:
            return p.get_snapshot(job)
        time.sleep(0.01)
    pytest.fail("Job did not finish")


def test_claude_protocol_resume_images_and_watch(tmp_path):
    p = provider()
    image = tmp_path / "image.png"
    image.write_bytes(b"test-image")
    job = p.execute(
        "hello",
        model="claude:sonnet",
        image_paths=[str(image)],
        provider_session_id="claude:existing",
        workdir=str(tmp_path),
    )
    snapshots = []
    p.watch_job(job, snapshots.append)
    result = wait(p, job)
    assert result.status == JobStatus.COMPLETED
    assert result.provider_session_id == "claude:existing"
    output = json.loads(result.response)
    assert output["argv"][-2:] == ["--resume", "existing"]
    assert "sonnet" in output["argv"]
    assert output["argv"][output["argv"].index("--effort") + 1] == "medium"
    assert "--dangerously-skip-permissions" not in output["argv"]
    assert (
        output["payload"]["message"]["content"][1]["source"]["media_type"]
        == "image/png"
    )
    assert any(s.latest_activity == "Claude: Read" for s in snapshots)


@pytest.mark.parametrize(
    "prompt", ["ERROR_FIXTURE", "MISSING_RESULT_FIXTURE", "DENIED_FIXTURE"]
)
def test_claude_failure_is_not_success(prompt):
    p = provider()
    assert wait(p, p.execute(prompt, model="claude:sonnet")).status == JobStatus.FAILED


def test_claude_rejects_codex_options_and_foreign_resume():
    p = provider()
    result = wait(
        p, p.execute("hello", model="claude:sonnet", provider_session_id="codex-id")
    )
    assert "--resume" not in json.loads(result.response)["argv"]
    failed = wait(
        p,
        p.execute(
            "hello",
            model="claude:sonnet",
            codex_options=CodexRunOptions(
                config_overrides=('sandbox_mode="workspace-write"',)
            ),
        ),
    )
    assert failed.status == JobStatus.FAILED
    assert "cannot reproduce" in failed.error


def test_claude_timeout_and_cancellation():
    p = provider(timeout_seconds=1)
    assert (
        wait(p, p.execute("SLEEP_FIXTURE", model="claude:sonnet")).phase == "Timed out"
    )
    job = p.execute("SLEEP_FIXTURE", model="claude:sonnet")
    assert p.cancel_job(job)
    assert wait(p, job).status == JobStatus.CANCELLED


def test_serial_claude_turns_resume_predecessor():
    p = provider()
    first = p.execute("one", model="claude:sonnet", serial_key="chat")
    second = p.execute("two", model="claude:sonnet", serial_key="chat")
    assert wait(p, first).status == JobStatus.COMPLETED
    result = wait(p, second)
    assert result.status == JobStatus.COMPLETED
    assert json.loads(result.response)["argv"][-2:] == ["--resume", "fixture-session"]


def test_switch_preserves_chat_and_transfers_context_both_directions(tmp_path):
    p = provider()
    repo = InMemoryChatRepository(projects_root=str(tmp_path))
    tmp_path = tmp_path / "workspace"
    tmp_path.mkdir()
    service = MessageService(
        repository=repo,
        execution_provider=p,
        default_workspace_path=str(tmp_path),
        audio_transcriber=DisabledAudioTranscriber(),
    )
    session = service.create_session(workspace_path=str(tmp_path))
    session.agent_configuration.agents[
        AgentId.GENERATOR
    ].provider_session_id = "codex-old"
    repo.save_session(session)
    repo.save_message(
        ChatMessage(
            id="old",
            session_id=session.id,
            role=ChatMessageRole.USER,
            author_type=ChatMessageAuthorType.HUMAN,
            content="Keep the blue button",
            status=ChatMessageStatus.COMPLETED,
        )
    )
    config = AgentConfiguration.default()
    config.agents[AgentId.GENERATOR].model = "claude:sonnet"
    config.agents[AgentId.GENERATOR].provider_session_id = "untrusted-ui-id"
    switched = service.update_agent_configuration(
        session_id=session.id, configuration=config
    )
    assert (
        switched.agent_configuration.agents[AgentId.GENERATOR].provider_session_id
        is None
    )
    job = service.submit_message("Continue", session_id=session.id)
    result = wait(p, job.id)
    assert result.status == JobStatus.COMPLETED
    prompt = json.loads(result.response)["payload"]["message"]["content"][0]["text"]
    assert "Keep the blue button" in prompt
    assert "<bridge_history>" in prompt
    service.get_job(job.id)
    session = repo.get_session(session.id)
    # Terminal processing is asynchronous; isolate the next configuration change.
    session.active_agent_run_id = None
    repo.save_session(session)
    config = AgentConfiguration.default()
    switched = service.update_agent_configuration(
        session_id=session.id, configuration=config
    )
    assert (
        switched.agent_configuration.agents[AgentId.GENERATOR].provider_session_id
        is None
    )
    # Polling a completed Claude job after switching must not restore its ID.
    service.get_job(job.id)
    assert (
        repo.get_session(session.id)
        .agent_configuration.agents[AgentId.GENERATOR]
        .provider_session_id
        is None
    )
    captured = []
    p.execute = lambda message, **kwargs: (
        captured.append((message, kwargs)) or "capture"
    )
    service.submit_message("Back to Codex", session_id=session.id)
    assert "Keep the blue button" in captured[0][0]
    assert captured[0][1]["provider_session_id"] is None


def test_default_claude_applies_to_new_chats_and_all_agents(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    repository = InMemoryChatRepository(projects_root=str(tmp_path))
    service = MessageService(
        repository=repository,
        execution_provider=provider(),
        default_workspace_path=str(workspace),
        audio_transcriber=DisabledAudioTranscriber(),
        default_agent_model="claude:sonnet",
    )
    session = service.create_session(title="New chat", workspace_path=str(workspace))
    assert all(
        a.model == "claude:sonnet" for a in session.agent_configuration.agents.values()
    )
    assert service._title_generation_model == "claude:sonnet"
    # Users can still explicitly switch a chat back to Codex.
    configuration = session.agent_configuration.normalized()
    configuration.agents[AgentId.GENERATOR].model = None
    service.update_agent_configuration(
        session_id=session.id, configuration=configuration
    )
    assert (
        service._model_for_agent(repository.get_session(session.id), AgentId.GENERATOR)
        is None
    )


@pytest.mark.parametrize("hint", [None, "gpt-5.4", "claude:sonnet"])
def test_backend_policy_pins_every_execution(hint):
    from backend.app.domain.ai_runtime import AiRuntimePolicy
    p = provider(ai_policy=AiRuntimePolicy("claude", "claude-opus-5-5"))
    result = wait(p, p.execute("background task", model=hint, provider_session_id="old-codex"))
    assert result.status == JobStatus.COMPLETED
    argv = json.loads(result.response)["argv"]
    assert argv[argv.index("--model") + 1] == "claude-opus-5-5"
    assert "--resume" not in argv


def test_backend_policy_overrides_all_saved_agent_models(tmp_path):
    from backend.app.domain.ai_runtime import AiRuntimePolicy
    repo = InMemoryChatRepository(projects_root=str(tmp_path))
    service = MessageService(repository=repo,
        execution_provider=provider(ai_policy=AiRuntimePolicy("claude", "claude-opus-5-5")),
        default_workspace_path=str(tmp_path), audio_transcriber=DisabledAudioTranscriber())
    workspace = tmp_path / "project"
    workspace.mkdir()
    session = service.create_session(title="Pinned backend", workspace_path=str(workspace))
    config = session.agent_configuration.normalized()
    for agent in config.agents.values():
        agent.model = "gpt-5.4"
        agent.provider_session_id = "old-codex"
    service.update_agent_configuration(session_id=session.id, configuration=config)
    saved = repo.get_session(session.id)
    assert all(a.model == "claude-opus-5-5" for a in saved.agent_configuration.agents.values())
    assert all(service._model_for_agent(saved, a) == "claude-opus-5-5" for a in saved.agent_configuration.agents)


def test_claude_readonly_and_no_tools_translation():
    p = provider()
    result = wait(p, p.execute("triage", model="claude-opus-5-5",
        codex_options=CodexRunOptions(config_overrides=('sandbox_mode="read-only"', 'approval_policy="never"'))))
    assert result.status == JobStatus.COMPLETED
    argv = json.loads(result.response)["argv"]
    assert argv[argv.index("--tools") + 1] == "Read,Glob,Grep"
    assert "--safe-mode" in argv and "--restricted" in argv and "--strict-mcp-config" in argv
    from backend.app.infrastructure.execution.claude_options import translate_options
    args, _ = translate_options(CodexRunOptions(config_overrides=(
        'features.shell_tool=false', 'features.apps=false', 'sandbox_mode="read-only"')), workdir=None)
    assert args[args.index("--tools") + 1] == ""


@pytest.mark.parametrize("options", [CodexRunOptions(profile="legacy"),
    CodexRunOptions(mcp_server_ids=("legacy-mcp",)),
    CodexRunOptions(config_overrides=('features.shell_tool=true', 'features.apps=false'))])
def test_claude_incompatible_options_fail_closed(options):
    from backend.app.infrastructure.execution.claude_options import translate_options
    with pytest.raises(ValueError):
        translate_options(options, workdir=None)


def test_sync_cli_routes_and_normalizes_native_failure(tmp_path):
    from backend.app.domain.ai_runtime import AiRuntimePolicy
    from backend.app.infrastructure.execution.agent_cli import AgentCli, run_process
    cli = AgentCli(AiRuntimePolicy("claude", "claude-opus-5-5"))
    argv = cli.argv(prompt_path=tmp_path / "task.md")
    assert argv[0] == "claude" and "--append-system-prompt-file" in argv
    assert argv[argv.index("--effort") + 1] == "medium"
    script = tmp_path / "fake.py"
    script.write_text('import json; print(json.dumps({"type":"result","result":"denied","permission_denials":[{"tool_name":"Write"}]}))')
    result = run_process(argv=(sys.executable, str(script), "--print", "--output-format", "json"),
        cwd=tmp_path, env={}, timeout_seconds=5)
    assert result.returncode != 0
    assert "permissions denied" in result.stderr


def test_runtime_policy_rejects_mismatched_config():
    from backend.app.domain.ai_runtime import AiRuntimePolicy
    with pytest.raises(ValueError):
        AiRuntimePolicy("claude", "gpt-5.4")


def test_runtime_and_legacy_mcp_install_do_not_select_codex():
    import asyncio
    from types import SimpleNamespace
    from fastapi import HTTPException
    from backend.app.api.routes import ai_runtime, install_codex_mcp_app
    from backend.app.infrastructure.config.settings import Settings
    container = SimpleNamespace(settings=Settings(_env_file=None,
        ai_provider="claude", ai_model="claude-opus-5-5", ai_effort="medium"))
    status = asyncio.run(ai_runtime(container))
    assert status["backend_owned"] and status["provider"] == "claude"
    with pytest.raises(HTTPException) as exc:
        asyncio.run(install_codex_mcp_app("any-app", container))
    assert exc.value.status_code == 422

@pytest.mark.parametrize("restricted", [False, True])
def test_auto_permission_mode_preserves_readonly_policy(tmp_path, restricted):
    from backend.app.infrastructure.config.settings import Settings

    settings = Settings(_env_file=None, claude_permission_mode="auto")
    p = provider(claude_permission_mode=settings.claude_permission_mode)
    options = CodexRunOptions(config_overrides=('sandbox_mode="read-only"',)) if restricted else None
    result = wait(p, p.execute("hello", model="claude:sonnet",
                              workdir=str(tmp_path), codex_options=options))
    assert result.status == JobStatus.COMPLETED
    argv = json.loads(result.response)["argv"]
    assert argv.count("--permission-mode") == 1
    assert argv[argv.index("--permission-mode") + 1] == ("dontAsk" if restricted else "auto")
    assert "--dangerously-skip-permissions" not in argv
    if restricted:
        assert argv[argv.index("--tools") + 1] == "Read,Glob,Grep"
