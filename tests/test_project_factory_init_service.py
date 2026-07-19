from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.application.services.project_factory_init_service import (
    INIT_PHASES,
    ProjectFactoryInitConflictError,
    ProjectFactoryInitService,
)
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


def test_init_service_run_pipeline_generates_workspace_and_blocked_context(
    tmp_path: Path,
) -> None:
    service = ProjectFactoryInitService(
        state_root=tmp_path / ".state",
        settings=Settings(
            projects_root=str(tmp_path),
            project_factory_state_dir=str(tmp_path / ".state"),
            chat_store_backend="memory",
            audio_transcription_backend="disabled",
            speech_synthesis_backend="disabled",
        ),
    )
    job = service.start_or_resume(
        draft_id="draft-1",
        chat_session_id="chat-1",
        project_name="Clinica Norte",
        slug="clinica-norte",
        frontend_strategy="flutter",
    )

    completed = service.run_pipeline(job.id)

    workspace = tmp_path / "clinica-norte"
    assert completed.relationships.generated_workspace_path == str(workspace)
    assert (workspace / ".codex/factory/init-result.json").is_file()
    assert (workspace / ".codex/factory/llm-start-context.md").is_file()
    assert (
        completed.phase(ProjectFactoryInitPhaseName.FLUTTER_OR_STRATEGY_BASELINE).status
        == ProjectFactoryInitPhaseStatus.COMPLETED
    )
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
