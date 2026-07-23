from __future__ import annotations

from pathlib import Path

import pytest

import backend.app.application.services.project_factory_init_service as init_service_module
from backend.app.application.services.project_factory_init_service import (
    INIT_PHASES,
    ProjectFactoryInitCommandResult,
    ProjectFactoryInitConflictError,
    ProjectFactoryInitService,
    SubprocessProjectFactoryInitCommandRunner,
)
from backend.app.domain.entities.agent_configuration import AgentId, AgentType
from backend.app.domain.entities.chat_message import (
    ChatMessage,
    ChatMessageAuthorType,
    ChatMessageRole,
    ChatMessageStatus,
)
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.project_factory_init import (
    ProjectFactoryInitArtifact,
    ProjectFactoryInitBlocker,
    ProjectFactoryInitCommandEvidence,
    ProjectFactoryInitContextPack,
    ProjectFactoryInitCompletionState,
    ProjectFactoryInitPhaseName,
    ProjectFactoryInitPhaseStatus,
    ProjectFactoryInitRemoteResource,
    ProjectFactoryInitRemoteResourceType,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.persistence.in_memory_chat_repository import (
    InMemoryChatRepository,
)
from backend.app.application.services.project_factory_job_runner import (
    _VisualUxSkillContext,
)


def test_subprocess_runner_uses_devnull_stdin_for_noninteractive_exec(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 12345
        returncode = 0

        def communicate(self, *, timeout: float | None = None) -> tuple[str, str]:
            captured["communicate_timeout"] = timeout
            return "ok", ""

    def fake_popen(argv: list[str], **kwargs: object) -> FakeProcess:
        captured["argv"] = argv
        captured.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(init_service_module.subprocess, "Popen", fake_popen)

    result = SubprocessProjectFactoryInitCommandRunner().run(
        ("codex", "exec", "Read `.codex/factory/prompts/ux-generator.md`."),
        cwd=tmp_path,
        timeout_seconds=30,
    )

    assert result.exit_code == 0
    assert captured["stdin"] == init_service_module.subprocess.DEVNULL
    assert captured["stdout"] == init_service_module.subprocess.PIPE
    assert captured["stderr"] == init_service_module.subprocess.PIPE
    assert captured["text"] is True
    assert captured["start_new_session"] is True
    assert captured["communicate_timeout"] == 30


def test_init_service_creates_idempotent_draft_chat_job(tmp_path: Path) -> None:
    service = ProjectFactoryInitService(state_root=tmp_path)

    job = service.start_or_resume(
        draft_id="draft-1",
        chat_session_id="chat-1",
        workspace_path="/workspace",
    )
    resumed = service.start_or_resume(
        draft_id="draft-1",
        chat_session_id="chat-1",
        workspace_path="/workspace",
    )

    assert resumed.id == job.id
    assert resumed.relationships.chat_session_id == "chat-1"
    assert resumed.relationships.generated_workspace_path == "/workspace"
    assert [phase.name.value for phase in resumed.phases] == list(INIT_PHASES)
    assert all(
        phase.status == ProjectFactoryInitPhaseStatus.QUEUED for phase in resumed.phases
    )
    payload = service.to_response_payload(resumed)
    assert payload["status"] == "queued"
    assert payload["currentPhase"] == "init_preflight"
    assert payload["readyForBusinessLlm"] is False
    assert payload["canContinueWithBlockedContext"] is False


def test_init_service_phase_completion_is_idempotent_and_persisted(
    tmp_path: Path,
) -> None:
    service = ProjectFactoryInitService(state_root=tmp_path)
    job = service.start_or_resume(draft_id="draft-1")

    running = service.begin_phase(job.id, "init_preflight", message="Checking tools.")
    completed = service.complete_phase(
        running.id,
        "init_preflight",
        message="Tools ready.",
        artifacts=(
            ProjectFactoryInitArtifact(
                kind="report",
                path=".codex/factory/init-preflight.json",
                metadata={"description": "preflight report"},
                sha256="abc",
            ),
        ),
        command_evidence=(
            ProjectFactoryInitCommandEvidence(
                argv=("gh", "auth", "status"),
                cwd="/tmp/project",
                exit_code=0,
                stdout_summary="ok",
                stderr_summary="",
                started_at="2026-07-11T00:00:00Z",
                completed_at="2026-07-11T00:00:01Z",
            ),
        ),
    )
    completed_again = service.complete_phase(
        completed.id,
        "init_preflight",
        message="Should not duplicate.",
    )

    completed_payload = service.to_response_payload(completed_again)
    assert completed_payload["status"] == "resumable"
    assert completed_payload["currentPhase"] == "draft_and_slug"
    phase = completed_again.phases[0]
    assert phase.status == ProjectFactoryInitPhaseStatus.COMPLETED
    assert phase.message == "Tools ready."
    assert len(phase.artifacts) == 1
    assert len(phase.command_evidence) == 1

    reloaded = ProjectFactoryInitService(state_root=tmp_path)
    loaded = reloaded.get_job(completed.id)
    assert loaded is not None
    assert reloaded.to_response_payload(loaded)["currentPhase"] == "draft_and_slug"
    assert loaded.phases[0].command_evidence[0].argv == ("gh", "auth", "status")


def test_init_service_run_pipeline_generates_workspace_ux_and_blocked_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command_runner = _FakeInitCommandRunner(ux_complete_after=2)
    repository = InMemoryChatRepository(projects_root=str(tmp_path))
    repository.save_session(
        ChatSession(
            id="chat-1",
            title="Clinica Norte",
            workspace_path=str(tmp_path / "clinica-norte"),
            workspace_name="clinica-norte",
        )
    )
    monkeypatch.setenv(
        "VISUAL_UX_POLISH_SKILL_PATH",
        str(_visual_ux_skill_fixture(tmp_path)),
    )
    service = ProjectFactoryInitService(
        state_root=tmp_path / ".state",
        command_runner=command_runner,
        chat_repository=repository,
        settings=Settings(
            projects_root=str(tmp_path),
            project_factory_state_dir=str(tmp_path / ".state"),
            chat_store_backend="memory",
            audio_transcription_backend="disabled",
            speech_synthesis_backend="disabled",
            codex_command="fake-codex",
        ),
    )
    job = service.start_or_resume(
        draft_id="draft-1",
        chat_session_id="chat-1",
        project_name="Clinica Norte",
        slug="clinica-norte",
        frontend_strategy="flutter",
    )

    waiting = service.run_pipeline(job.id)
    _write_domain_brief(tmp_path / "clinica-norte")
    completed = service.run_pipeline(waiting.id)

    workspace = tmp_path / "clinica-norte"
    assert completed.relationships.generated_workspace_path == str(workspace)
    assert (workspace / ".codex/factory/init-result.json").is_file()
    assert (workspace / ".codex/factory/llm-start-context.md").is_file()
    assert (
        completed.phase(ProjectFactoryInitPhaseName.FLUTTER_OR_STRATEGY_BASELINE).status
        == ProjectFactoryInitPhaseStatus.COMPLETED
    )
    assert (
        completed.phase(ProjectFactoryInitPhaseName.UX_GENERATOR).status
        == ProjectFactoryInitPhaseStatus.COMPLETED
    )
    assert (
        completed.phase(ProjectFactoryInitPhaseName.UX_REVIEWER).status
        == ProjectFactoryInitPhaseStatus.COMPLETED
    )
    assert command_runner.ux_generator_calls == 2
    assert command_runner.ux_reviewer_calls == 2
    ux_commands = [
        command
        for command in command_runner.commands
        if command and ".codex/factory/prompts/ux-" in command[-1]
    ]
    assert len(ux_commands) == 4
    assert all(len(command[-1]) < 500 for command in ux_commands)
    assert all("Read and follow the full automatic UX prompt" in command[-1] for command in ux_commands)
    assert all("Automatic New Project UX Generator" not in command[-1] for command in ux_commands)
    assert (
        workspace / ".codex/ux/evidence-index.json"
    ).is_file()
    ux_messages = [
        message for message in repository.list_messages("chat-1")
        if message.agent_label in {"UX Generator", "UX Reviewer"}
    ]
    assert [message.agent_label for message in ux_messages] == [
        "UX Generator",
        "UX Reviewer",
        "UX Generator",
        "UX Reviewer",
    ]
    assert all(message.run_id == completed.id for message in ux_messages)
    assert "UX Generator pass 1" in ux_messages[0].content
    assert "UX Reviewer pass 2" in ux_messages[-1].content
    assert (
        completed.phase(ProjectFactoryInitPhaseName.LOCAL_GIT_COMMIT).status
        == ProjectFactoryInitPhaseStatus.COMPLETED
    )
    assert (
        completed.phase(ProjectFactoryInitPhaseName.GITHUB_REPOSITORY).status
        == ProjectFactoryInitPhaseStatus.BLOCKED
    )
    assert (
        completed.phase(ProjectFactoryInitPhaseName.LLM_CONTEXT_PACK).status
        == ProjectFactoryInitPhaseStatus.COMPLETED
    )
    assert (
        completed.completion_state
        == ProjectFactoryInitCompletionState.BLOCKED_WITH_CONTEXT
    )
    phase_names = [phase.name for phase in completed.phases]
    assert phase_names.index(ProjectFactoryInitPhaseName.UX_REVIEWER) < phase_names.index(
        ProjectFactoryInitPhaseName.LOCAL_VALIDATION
    )


def test_init_service_waits_for_domain_brief_before_automatic_ux(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command_runner = _FakeInitCommandRunner()
    monkeypatch.setenv(
        "VISUAL_UX_POLISH_SKILL_PATH",
        str(_visual_ux_skill_fixture(tmp_path)),
    )
    service = ProjectFactoryInitService(
        state_root=tmp_path / ".state",
        command_runner=command_runner,
        settings=Settings(
            projects_root=str(tmp_path),
            project_factory_state_dir=str(tmp_path / ".state"),
            chat_store_backend="memory",
            audio_transcription_backend="disabled",
            speech_synthesis_backend="disabled",
            codex_command="fake-codex",
        ),
    )
    job = service.start_or_resume(
        draft_id="draft-1",
        chat_session_id="chat-1",
        project_name="Clinica Norte",
        slug="clinica-norte",
        frontend_strategy="flutter",
    )

    waiting = service.run_pipeline(job.id)

    assert service.to_response_payload(waiting)["status"] == "waiting_for_domain_brief"
    assert service.to_response_payload(waiting)["currentPhase"] == "ux_generator"
    generator = waiting.phase(ProjectFactoryInitPhaseName.UX_GENERATOR)
    reviewer = waiting.phase(ProjectFactoryInitPhaseName.UX_REVIEWER)
    assert (
        generator.status
        == ProjectFactoryInitPhaseStatus.QUEUED_WAITING_FOR_DOMAIN_BRIEF
    )
    assert (
        reviewer.status
        == ProjectFactoryInitPhaseStatus.QUEUED_WAITING_FOR_DOMAIN_BRIEF
    )
    assert "queued_waiting_for_domain_brief" in generator.message
    assert command_runner.ux_generator_calls == 0
    assert command_runner.ux_reviewer_calls == 0
    assert (
        waiting.phase(ProjectFactoryInitPhaseName.LOCAL_VALIDATION).status
        == ProjectFactoryInitPhaseStatus.QUEUED
    )


def test_init_service_runs_automatic_ux_after_domain_brief_before_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command_runner = _FakeInitCommandRunner(ux_complete_after=1)
    monkeypatch.setenv(
        "VISUAL_UX_POLISH_SKILL_PATH",
        str(_visual_ux_skill_fixture(tmp_path)),
    )
    service = ProjectFactoryInitService(
        state_root=tmp_path / ".state",
        command_runner=command_runner,
        settings=Settings(
            projects_root=str(tmp_path),
            project_factory_state_dir=str(tmp_path / ".state"),
            chat_store_backend="memory",
            audio_transcription_backend="disabled",
            speech_synthesis_backend="disabled",
            codex_command="fake-codex",
        ),
    )
    job = service.start_or_resume(
        draft_id="draft-1",
        chat_session_id="chat-1",
        project_name="Clinica Norte",
        slug="clinica-norte",
        frontend_strategy="flutter",
    )
    waiting = service.run_pipeline(job.id)
    _write_domain_brief(tmp_path / "clinica-norte")

    completed = service.run_pipeline(waiting.id)

    assert command_runner.ux_generator_calls == 1
    assert command_runner.ux_reviewer_calls == 1
    assert (
        completed.phase(ProjectFactoryInitPhaseName.UX_REVIEWER).status
        == ProjectFactoryInitPhaseStatus.COMPLETED
    )
    assert (
        completed.phase(ProjectFactoryInitPhaseName.LOCAL_VALIDATION).status
        == ProjectFactoryInitPhaseStatus.COMPLETED
    )
    assert (
        completed.phase(ProjectFactoryInitPhaseName.UX_REVIEWER).completed_at
        <= completed.phase(ProjectFactoryInitPhaseName.LOCAL_VALIDATION).completed_at
    )


def test_init_service_uses_approved_project_factory_chat_as_ux_domain_brief(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command_runner = _FakeInitCommandRunner(ux_complete_after=1)
    repository = InMemoryChatRepository(projects_root=str(tmp_path))
    repository.save_session(
        ChatSession(
            id="chat-1",
            title="Puerto",
            workspace_path=str(tmp_path / "prueba-22"),
            workspace_name="prueba-22",
        )
    )
    _save_chat_message(
        repository,
        session_id="chat-1",
        role=ChatMessageRole.USER,
        agent_id=AgentId.USER,
        content=(
            "este proyecto es del puerto. admin y empleado cargan datos del excel; "
            "usuarios ven los datos."
        ),
    )
    _save_chat_message(
        repository,
        session_id="chat-1",
        role=ChatMessageRole.ASSISTANT,
        agent_id=AgentId.GENERATOR,
        content=(
            "**Contrato Aprobado: prueba-22**\n\nApp operativa para el puerto con "
            "Admin, Empleado y Usuario. Datos reales persistentes, sin mock/demo."
        ),
    )
    _save_chat_message(
        repository,
        session_id="chat-1",
        role=ChatMessageRole.ASSISTANT,
        agent_id=AgentId.GENERATOR,
        content="PROJECT_FACTORY_READY_FOR_BUILD",
    )
    monkeypatch.setenv(
        "VISUAL_UX_POLISH_SKILL_PATH",
        str(_visual_ux_skill_fixture(tmp_path)),
    )
    service = ProjectFactoryInitService(
        state_root=tmp_path / ".state",
        command_runner=command_runner,
        chat_repository=repository,
        settings=Settings(
            projects_root=str(tmp_path),
            project_factory_state_dir=str(tmp_path / ".state"),
            chat_store_backend="memory",
            audio_transcription_backend="disabled",
            speech_synthesis_backend="disabled",
            codex_command="fake-codex",
        ),
    )
    job = service.start_or_resume(
        draft_id="draft-1",
        chat_session_id="chat-1",
        project_name="prueba-22",
        slug="prueba-22",
        frontend_strategy="flutter",
    )

    completed = service.run_pipeline(job.id)

    workspace = tmp_path / "prueba-22"
    assert command_runner.ux_generator_calls == 1
    assert command_runner.ux_reviewer_calls == 1
    assert (
        completed.phase(ProjectFactoryInitPhaseName.UX_REVIEWER).status
        == ProjectFactoryInitPhaseStatus.COMPLETED
    )
    domain_brief = (workspace / ".codex/ux/domain-brief.md").read_text(
        encoding="utf-8"
    )
    assert "Approved Project Factory Domain Brief" in domain_brief
    assert "proyecto es del puerto" in domain_brief
    assert "Contrato Aprobado: prueba-22" in domain_brief
    prompt = (workspace / ".codex/factory/prompts/ux-generator.md").read_text(
        encoding="utf-8"
    )
    assert "Read `.codex/ux/domain-brief.md`" in prompt
    assert "proyecto es del puerto" in prompt


def test_init_service_automatic_ux_uses_configured_codex_exec_args(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command_runner = _FakeInitCommandRunner(ux_complete_after=1)
    monkeypatch.setenv(
        "VISUAL_UX_POLISH_SKILL_PATH",
        str(_visual_ux_skill_fixture(tmp_path)),
    )
    service = ProjectFactoryInitService(
        state_root=tmp_path / ".state",
        command_runner=command_runner,
        settings=Settings(
            projects_root=str(tmp_path),
            project_factory_state_dir=str(tmp_path / ".state"),
            chat_store_backend="memory",
            audio_transcription_backend="disabled",
            speech_synthesis_backend="disabled",
            codex_command="fake-codex",
            codex_exec_args=(
                "--skip-git-repo-check --color never "
                "--dangerously-bypass-approvals-and-sandbox"
            ),
        ),
    )
    job = service.start_or_resume(
        draft_id="draft-1",
        chat_session_id="chat-1",
        project_name="Clinica Norte",
        slug="clinica-norte",
        frontend_strategy="flutter",
    )
    waiting = service.run_pipeline(job.id)
    _write_domain_brief(tmp_path / "clinica-norte")

    service.run_pipeline(waiting.id)

    ux_command = next(
        command
        for command in command_runner.commands
        if command and ".codex/factory/prompts/ux-generator.md" in command[-1]
    )
    assert "--dangerously-bypass-approvals-and-sandbox" in ux_command


def test_init_service_automatic_ux_blocks_sandbox_text_even_with_zero_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command_runner = _FakeInitCommandRunner(sandbox_blocked_ux=True)
    monkeypatch.setenv(
        "VISUAL_UX_POLISH_SKILL_PATH",
        str(_visual_ux_skill_fixture(tmp_path)),
    )
    service = ProjectFactoryInitService(
        state_root=tmp_path / ".state",
        command_runner=command_runner,
        settings=Settings(
            projects_root=str(tmp_path),
            project_factory_state_dir=str(tmp_path / ".state"),
            chat_store_backend="memory",
            audio_transcription_backend="disabled",
            speech_synthesis_backend="disabled",
            codex_command="fake-codex",
        ),
    )
    job = service.start_or_resume(
        draft_id="draft-1",
        chat_session_id="chat-1",
        project_name="Clinica Norte",
        slug="clinica-norte",
        frontend_strategy="flutter",
    )
    waiting = service.run_pipeline(job.id)
    _write_domain_brief(tmp_path / "clinica-norte")

    blocked = service.run_pipeline(waiting.id)

    generator = blocked.phase(ProjectFactoryInitPhaseName.UX_GENERATOR)
    assert generator.status == ProjectFactoryInitPhaseStatus.BLOCKED
    assert generator.blockers[0].code == "automatic_ux_generator_failed"
    assert "bwrap: loopback" in generator.blockers[0].message
    fallback_report = (
        tmp_path / "clinica-norte" / ".codex/ux/ux-generator-report.md"
    )
    assert fallback_report.is_file()
    assert "bwrap: loopback" in fallback_report.read_text(encoding="utf-8")
    assert command_runner.ux_generator_calls == 1
    assert command_runner.ux_reviewer_calls == 0
    assert (
        blocked.phase(ProjectFactoryInitPhaseName.LOCAL_VALIDATION).status
        == ProjectFactoryInitPhaseStatus.QUEUED
    )


def test_init_service_automatic_ux_blocks_when_reviewer_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command_runner = _FakeInitCommandRunner(fail_ux_reviewer=True)
    monkeypatch.setenv(
        "VISUAL_UX_POLISH_SKILL_PATH",
        str(_visual_ux_skill_fixture(tmp_path)),
    )
    service = ProjectFactoryInitService(
        state_root=tmp_path / ".state",
        command_runner=command_runner,
        settings=Settings(
            projects_root=str(tmp_path),
            project_factory_state_dir=str(tmp_path / ".state"),
            chat_store_backend="memory",
            audio_transcription_backend="disabled",
            speech_synthesis_backend="disabled",
            codex_command="fake-codex",
        ),
    )
    job = service.start_or_resume(
        draft_id="draft-1",
        chat_session_id="chat-1",
        project_name="Clinica Norte",
        slug="clinica-norte",
        frontend_strategy="flutter",
    )
    job = service.run_frontend_baseline_phase(job.id)
    _write_domain_brief(tmp_path / "clinica-norte")

    blocked = service.run_automatic_ux_phases(job.id)

    assert (
        blocked.phase(ProjectFactoryInitPhaseName.UX_GENERATOR).status
        == ProjectFactoryInitPhaseStatus.COMPLETED
    )
    reviewer = blocked.phase(ProjectFactoryInitPhaseName.UX_REVIEWER)
    assert reviewer.status == ProjectFactoryInitPhaseStatus.BLOCKED
    assert reviewer.blockers[0].code == "automatic_ux_reviewer_failed"
    assert "reviewer failed" in reviewer.blockers[0].message.lower()


def test_init_service_blocked_with_context_and_remote_context_payload(
    tmp_path: Path,
) -> None:
    service = ProjectFactoryInitService(state_root=tmp_path)
    job = service.start_or_resume(draft_id="draft-1", chat_session_id="chat-1")
    service.complete_phase(job.id, "init_preflight")

    blocked = service.block_phase(
        job.id,
        "draft_and_slug",
        blocker=ProjectFactoryInitBlocker(
            code="cloudflare_credentials",
            message="Missing Cloudflare token.",
            phase=ProjectFactoryInitPhaseName.DRAFT_AND_SLUG,
            next_action="Set CLOUDFLARE_API_TOKEN and rerun deterministic init.",
            command=("export", "CLOUDFLARE_API_TOKEN=..."),
        ),
        context_available=True,
    )
    with_resource = service.record_remote_resource(
        blocked.id,
        resource=ProjectFactoryInitRemoteResource(
            type=ProjectFactoryInitRemoteResourceType.GITHUB_REPOSITORY,
            identifier="owner/app",
            display_name="owner/app",
            url="https://github.com/owner/app",
            provider="github",
            status="ready",
            metadata={"branch": "main"},
        ),
    )
    with_context = service.attach_context_pack(
        with_resource.id,
        context_pack=ProjectFactoryInitContextPack(
            init_result_path=".codex/factory/init-result.json",
            llm_start_context_path=".codex/factory/llm-start-context.md",
            content_sha256="hash",
            attached_to_chat=True,
        ),
    )

    payload = service.to_response_payload(with_context)
    assert payload["status"] == "blocked_with_context"
    assert payload["canContinueWithBlockedContext"] is True
    assert payload["retryAvailable"] is True
    assert payload["blockers"][0]["code"] == "cloudflare_credentials"
    assert payload["remoteResources"][0]["url"] == "https://github.com/owner/app"
    assert payload["contextPack"]["attachedSessionId"] == "chat-1"


def test_init_service_queues_retry_for_any_blocked_phase(tmp_path: Path) -> None:
    service = ProjectFactoryInitService(state_root=tmp_path)
    job = service.start_or_resume(draft_id="draft-1")
    service.complete_phase(job.id, "init_preflight")
    blocked = service.block_phase(
        job.id,
        "cloudflare_preview_deploy",
        blocker=ProjectFactoryInitBlocker(
            code="cloudflare_token_missing",
            message="Cloudflare token missing.",
            phase=ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_DEPLOY,
            next_action="Configure CLOUDFLARE_API_TOKEN.",
        ),
        context_available=True,
    )

    payload = service.to_response_payload(blocked)
    assert payload["status"] == "blocked_with_context"
    assert payload["currentPhase"] == "cloudflare_preview_deploy"
    assert payload["retryAvailable"] is True

    queued = service.queue_retry(blocked.id)
    retry_phase = queued.phase(ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_DEPLOY)

    assert retry_phase.status == ProjectFactoryInitPhaseStatus.QUEUED
    assert retry_phase.blockers == ()
    assert service.to_response_payload(queued)["status"] == "resumable"
    assert service.to_response_payload(queued)["retryAvailable"] is False


def test_init_service_queues_retry_for_failed_phase(tmp_path: Path) -> None:
    service = ProjectFactoryInitService(state_root=tmp_path)
    job = service.start_or_resume(draft_id="draft-1")
    service.complete_phase(job.id, "init_preflight")
    failed = service.fail_phase(
        job.id,
        "ux_generator",
        message="Deterministic init pipeline failed: [Errno 7] Argument list too long",
    )

    payload = service.to_response_payload(failed)
    assert payload["status"] == "failed"
    assert payload["currentPhase"] == "ux_generator"
    assert payload["retryAvailable"] is True

    queued = service.queue_retry(failed.id)
    retry_phase = queued.phase(ProjectFactoryInitPhaseName.UX_GENERATOR)

    assert retry_phase.status == ProjectFactoryInitPhaseStatus.QUEUED
    assert retry_phase.message == ""
    assert service.to_response_payload(queued)["status"] == "resumable"
    assert service.to_response_payload(queued)["retryAvailable"] is False


def test_init_service_recovers_running_job_as_resumable(tmp_path: Path) -> None:
    service = ProjectFactoryInitService(state_root=tmp_path)
    job = service.start_or_resume(draft_id="draft-1")
    service.begin_phase(job.id, "init_preflight")

    reloaded = ProjectFactoryInitService(state_root=tmp_path)
    loaded = reloaded.get_job(job.id)

    assert loaded is not None
    payload = reloaded.to_response_payload(loaded)
    assert payload["status"] == "queued"
    assert payload["currentPhase"] == "init_preflight"


def test_init_service_rejects_unknown_phase(tmp_path: Path) -> None:
    service = ProjectFactoryInitService(state_root=tmp_path)
    job = service.start_or_resume(draft_id="draft-1")

    with pytest.raises(ProjectFactoryInitConflictError):
        service.begin_phase(job.id, "not_a_phase")


def test_init_service_passes_large_automatic_ux_prompt_by_file_not_argv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    huge_skill_context = "# Huge visual UX context\n" + ("large-context\n" * 25_000)
    monkeypatch.setattr(
        init_service_module,
        "_load_visual_ux_skill_context",
        lambda _path: _VisualUxSkillContext(
            skill_path=tmp_path / "visual-ux-polish" / "SKILL.md",
            prompt_section=huge_skill_context,
        ),
    )
    command_runner = _FakeInitCommandRunner(ux_complete_after=1)
    repository = InMemoryChatRepository(projects_root=str(tmp_path))
    repository.save_session(
        ChatSession(
            id="chat-large-ux",
            title="Clinica Norte",
            workspace_path=str(tmp_path / "clinica-norte"),
            workspace_name="clinica-norte",
        )
    )
    service = ProjectFactoryInitService(
        state_root=tmp_path / ".state",
        command_runner=command_runner,
        chat_repository=repository,
        settings=Settings(
            projects_root=str(tmp_path),
            project_factory_state_dir=str(tmp_path / ".state"),
            chat_store_backend="memory",
            audio_transcription_backend="disabled",
            speech_synthesis_backend="disabled",
            codex_command="fake-codex",
        ),
    )
    job = service.start_or_resume(
        draft_id="draft-large-ux",
        chat_session_id="chat-large-ux",
        project_name="Clinica Norte",
        slug="clinica-norte",
        frontend_strategy="flutter",
    )

    waiting = service.run_pipeline(job.id)
    _write_domain_brief(tmp_path / "clinica-norte")
    completed = service.run_pipeline(waiting.id)

    workspace = tmp_path / "clinica-norte"
    prompt_path = workspace / ".codex/factory/prompts/ux-generator.md"
    assert prompt_path.stat().st_size > 200_000
    ux_commands = [
        command
        for command in command_runner.commands
        if command and ".codex/factory/prompts/ux-" in command[-1]
    ]
    assert ux_commands
    assert all(len(command[-1]) < 500 for command in ux_commands)
    assert all("large-context" not in command[-1] for command in ux_commands)
    assert all("--output-last-message" in command for command in ux_commands)
    assert any(
        str(workspace / ".codex/ux/ux-generator-report.md") in command
        for command in ux_commands
    )
    assert any(
        str(workspace / ".codex/ux/ux-reviewer-report.md") in command
        for command in ux_commands
    )
    assert command_runner.ux_generator_calls == 1
    assert command_runner.ux_reviewer_calls == 1
    assert (
        completed.phase(ProjectFactoryInitPhaseName.UX_GENERATOR).status
        == ProjectFactoryInitPhaseStatus.COMPLETED
    )


def _write_domain_brief(workspace: Path) -> Path:
    brief_path = workspace / "specs/019-domain-factory/intake/original-brief.md"
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(
        "# Original Domain Brief\n\nClinica Norte needs appointments and patient workflows.\n",
        encoding="utf-8",
    )
    state_path = workspace / ".codex/factory/domain-factory-state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        '{\n'
        '  "modeStatus": "implementation_ready",\n'
        '  "briefPath": "specs/019-domain-factory/intake/original-brief.md"\n'
        '}\n',
        encoding="utf-8",
    )
    return brief_path


def _save_chat_message(
    repository: InMemoryChatRepository,
    *,
    session_id: str,
    role: ChatMessageRole,
    agent_id: AgentId,
    content: str,
) -> None:
    repository.save_message(
        ChatMessage(
            id=f"message-{len(repository.list_messages(session_id)) + 1}",
            session_id=session_id,
            role=role,
            author_type=(
                ChatMessageAuthorType.HUMAN
                if role == ChatMessageRole.USER
                else ChatMessageAuthorType.ASSISTANT
            ),
            agent_id=agent_id,
            agent_type=(
                AgentType.HUMAN
                if agent_id == AgentId.USER
                else AgentType.GENERATOR
            ),
            agent_label=None if agent_id == AgentId.USER else "Project Factory",
            content=content,
            status=ChatMessageStatus.COMPLETED,
        )
    )


class _FakeInitCommandRunner:
    def __init__(
        self,
        *,
        ux_complete_after: int = 1,
        fail_ux_reviewer: bool = False,
        sandbox_blocked_ux: bool = False,
    ) -> None:
        self.ux_complete_after = ux_complete_after
        self.fail_ux_reviewer = fail_ux_reviewer
        self.sandbox_blocked_ux = sandbox_blocked_ux
        self.ux_generator_calls = 0
        self.ux_reviewer_calls = 0
        self.commands: list[tuple[str, ...]] = []

    def run(
        self,
        argv: tuple[str, ...],
        *,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: float = 0,
    ):
        del timeout_seconds
        self.commands.append(argv)
        cwd_path = Path(cwd or ".")
        prompt = argv[-1] if argv else ""
        if ".codex/factory/prompts/" in prompt:
            marker = ".codex/factory/prompts/"
            relative = marker + prompt.split(marker, 1)[1].split("`", 1)[0]
            prompt_path = cwd_path / relative
            if prompt_path.exists():
                prompt = prompt_path.read_text(encoding="utf-8")
        if "Automatic New Project UX Generator" in prompt:
            self.ux_generator_calls += 1
            if self.sandbox_blocked_ux:
                return ProjectFactoryInitCommandResult(
                    argv=argv,
                    cwd=str(cwd_path),
                    exit_code=0,
                    stdout=(
                        "I could not execute the UX prompt because the workspace "
                        "tools are blocked before file reads run.\n"
                        "bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted\n"
                        "The filesystem is also configured as read-only, so I cannot "
                        "write the requested `.codex/ux/` evidence."
                    ),
                    env=env,
                )
            ux_dir = cwd_path / ".codex/ux"
            ux_dir.mkdir(parents=True, exist_ok=True)
            (ux_dir / "ux-generator-report.md").write_text(
                f"# UX generator report\n\npass {self.ux_generator_calls}\n",
                encoding="utf-8",
            )
            return ProjectFactoryInitCommandResult(
                argv=argv,
                cwd=str(cwd_path),
                exit_code=0,
                stdout="UX generator ok",
                env=env,
            )
        if "Automatic New Project UX Reviewer" in prompt:
            self.ux_reviewer_calls += 1
            if self.fail_ux_reviewer:
                return ProjectFactoryInitCommandResult(
                    argv=argv,
                    cwd=str(cwd_path),
                    exit_code=1,
                    stderr="reviewer failed",
                    env=env,
                )
            status = (
                "complete"
                if self.ux_reviewer_calls >= self.ux_complete_after
                else "continue"
            )
            ux_dir = cwd_path / ".codex/ux"
            ux_dir.mkdir(parents=True, exist_ok=True)
            (ux_dir / "ux-reviewer-report.md").write_text(
                "# UX reviewer report\n\n"
                + f"status: {status}\nrelease_gate: pass\n",
                encoding="utf-8",
            )
            return ProjectFactoryInitCommandResult(
                argv=argv,
                cwd=str(cwd_path),
                exit_code=0,
                stdout=f"status: {status}\nrelease_gate: pass",
                env=env,
            )
        stdout = "true" if argv[:2] == ("git", "rev-parse") else "ok"
        return ProjectFactoryInitCommandResult(
            argv=argv,
            cwd=str(cwd_path),
            exit_code=0,
            stdout=stdout,
            env=env,
        )


def _visual_ux_skill_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "skills/visual-ux-polish"
    references = root / "references"
    references.mkdir(parents=True)
    root.joinpath("SKILL.md").write_text(
        "# Visual UX Polish\n\nUse this skill for professional UX polish.\n",
        encoding="utf-8",
    )
    for relative_path in (
        "visual-quality-checklist.md",
        "product-category-playbooks.md",
        "visual-validation-protocol.md",
        "accessibility-performance-polish.md",
    ):
        references.joinpath(relative_path).write_text(
            f"# {relative_path}\n\nFixture reference.\n",
            encoding="utf-8",
        )
    return root / "SKILL.md"
