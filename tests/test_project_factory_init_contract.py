from __future__ import annotations

from backend.app.domain.entities.project_factory_init import (
    INIT_PHASE_IDEMPOTENCY_RULES,
    INIT_PHASE_ORDER,
    ProjectFactoryInitArtifact,
    ProjectFactoryInitBlocker,
    ProjectFactoryInitCommandEvidence,
    ProjectFactoryInitCompletionState,
    ProjectFactoryInitContextPack,
    ProjectFactoryInitIdempotencyRule,
    ProjectFactoryInitJob,
    ProjectFactoryInitPhase,
    ProjectFactoryInitPhaseName,
    ProjectFactoryInitPhaseStatus,
    ProjectFactoryInitRelationships,
    ProjectFactoryInitRemoteResource,
    ProjectFactoryInitRemoteResourceType,
    derive_init_completion_state,
)


def test_init_phase_order_is_stable_and_complete() -> None:
    assert [phase.value for phase in INIT_PHASE_ORDER] == [
        "init_preflight",
        "draft_and_slug",
        "baseline_scaffold",
        "flutter_or_strategy_baseline",
        "local_validation",
        "local_git_commit",
        "github_repository",
        "cloudflare_preview_provision",
        "cloudflare_preview_deploy",
        "preview_smoke",
        "android_preview_release",
        "bridge_installable_registration",
        "workbench_and_feedback_verification",
        "llm_context_pack",
    ]
    assert set(INIT_PHASE_IDEMPOTENCY_RULES) == set(INIT_PHASE_ORDER)
    assert (
        INIT_PHASE_IDEMPOTENCY_RULES[ProjectFactoryInitPhaseName.INIT_PREFLIGHT]
        == ProjectFactoryInitIdempotencyRule.READ_ONLY_PREFLIGHT
    )
    assert (
        INIT_PHASE_IDEMPOTENCY_RULES[ProjectFactoryInitPhaseName.LLM_CONTEXT_PACK]
        == ProjectFactoryInitIdempotencyRule.CONTEXT_REBUILD_FROM_STATE
    )


def test_new_init_job_links_draft_chat_job_and_workbench_scope() -> None:
    job = ProjectFactoryInitJob.new(
        id="pf-init-1",
        draft_id="pf-draft-1",
        chat_session_id="session-1",
        project_name="Clinica Norte",
        slug="clinica-norte",
        frontend_strategy="flutter",
    )

    assert job.completion_state == ProjectFactoryInitCompletionState.RESUMABLE
    assert job.relationships == ProjectFactoryInitRelationships(
        draft_id="pf-draft-1",
        chat_session_id="session-1",
        init_job_id="pf-init-1",
    )
    assert [phase.name for phase in job.phases] == list(INIT_PHASE_ORDER)
    assert job.phase(ProjectFactoryInitPhaseName.GITHUB_REPOSITORY).idempotency == (
        ProjectFactoryInitIdempotencyRule.CREATE_OR_VERIFY
    )


def test_init_job_payload_roundtrip_preserves_contract_details() -> None:
    blocker = ProjectFactoryInitBlocker(
        code="missing_gh_auth",
        message="GitHub CLI is not authenticated.",
        phase=ProjectFactoryInitPhaseName.GITHUB_REPOSITORY,
        next_action="Run gh auth login.",
        command=("gh", "auth", "login"),
    )
    evidence = ProjectFactoryInitCommandEvidence(
        argv=("gh", "repo", "view", "owner/clinica-norte"),
        cwd="/home/batata/Projects/clinica-norte",
        exit_code=1,
        stderr_summary="not found",
        redacted_env_keys=("GH_TOKEN",),
    )
    artifact = ProjectFactoryInitArtifact(
        kind="init_result",
        path=".codex/factory/init-result.json",
        sha256="abc123",
    )
    blocked_phase = ProjectFactoryInitPhase(
        name=ProjectFactoryInitPhaseName.GITHUB_REPOSITORY,
        status=ProjectFactoryInitPhaseStatus.BLOCKED,
        message="GitHub repository is blocked.",
        command_evidence=(evidence,),
        blockers=(blocker,),
        artifacts=(artifact,),
    )
    job = ProjectFactoryInitJob.new(
        id="pf-init-1",
        draft_id="pf-draft-1",
        project_name="Clinica Norte",
        slug="clinica-norte",
        frontend_strategy="flutter",
    ).with_phase(blocked_phase)
    job = ProjectFactoryInitJob(
        id=job.id,
        relationships=ProjectFactoryInitRelationships(
            draft_id="pf-draft-1",
            chat_session_id="session-1",
            init_job_id="pf-init-1",
            generated_workspace_path="/home/batata/Projects/clinica-norte",
            workbench_scope_id="workspace:/home/batata/Projects/clinica-norte",
            first_chat_message_id="message-1",
        ),
        created_at=job.created_at,
        updated_at=job.updated_at,
        project_name=job.project_name,
        slug=job.slug,
        frontend_strategy=job.frontend_strategy,
        phases=job.phases,
        remote_resources=(
            ProjectFactoryInitRemoteResource(
                type=ProjectFactoryInitRemoteResourceType.GITHUB_REPOSITORY,
                identifier="owner/clinica-norte",
                display_name="owner/clinica-norte",
                url="https://github.com/owner/clinica-norte",
                provider="github",
                status="blocked",
            ),
            ProjectFactoryInitRemoteResource(
                type=ProjectFactoryInitRemoteResourceType.API_BASE_URL,
                identifier="https://preview.nienfos.com/clinica-norte/api",
                display_name="Preview API",
                url="https://preview.nienfos.com/clinica-norte/api",
                status="planned",
            ),
        ),
        context_pack=ProjectFactoryInitContextPack(
            init_result_path=".codex/factory/init-result.json",
            llm_start_context_path=".codex/factory/llm-start-context.md",
            content_sha256="def456",
            attached_to_chat=True,
            attached_message_id="message-1",
        ),
    ).with_derived_completion_state()

    restored = ProjectFactoryInitJob.from_payload(job.to_payload())

    assert restored.to_payload() == job.to_payload()
    assert restored.completion_state == (
        ProjectFactoryInitCompletionState.BLOCKED_WITH_CONTEXT
    )
    github_phase = restored.phase(ProjectFactoryInitPhaseName.GITHUB_REPOSITORY)
    assert github_phase.blockers[0].next_action == "Run gh auth login."
    assert github_phase.command_evidence[0].redacted_env_keys == ("GH_TOKEN",)
    assert restored.remote_resources[0].url == (
        "https://github.com/owner/clinica-norte"
    )
    assert restored.context_pack is not None
    assert restored.context_pack.attached_to_chat is True


def test_completion_state_derivation_prioritizes_terminal_outcomes() -> None:
    completed = tuple(
        ProjectFactoryInitPhase(
            name=phase,
            status=ProjectFactoryInitPhaseStatus.COMPLETED,
        )
        for phase in INIT_PHASE_ORDER
    )
    assert derive_init_completion_state(completed) == (
        ProjectFactoryInitCompletionState.READY
    )

    blocked = (
        ProjectFactoryInitPhase(
            name=ProjectFactoryInitPhaseName.INIT_PREFLIGHT,
            status=ProjectFactoryInitPhaseStatus.BLOCKED,
        ),
        *completed[1:],
    )
    assert derive_init_completion_state(blocked) == (
        ProjectFactoryInitCompletionState.BLOCKED_WITH_CONTEXT
    )

    failed = (
        ProjectFactoryInitPhase(
            name=ProjectFactoryInitPhaseName.INIT_PREFLIGHT,
            status=ProjectFactoryInitPhaseStatus.FAILED,
        ),
        *blocked[1:],
    )
    assert derive_init_completion_state(failed) == (
        ProjectFactoryInitCompletionState.FAILED
    )

    cancelled = (
        ProjectFactoryInitPhase(
            name=ProjectFactoryInitPhaseName.INIT_PREFLIGHT,
            status=ProjectFactoryInitPhaseStatus.CANCELLED,
        ),
        *failed[1:],
    )
    assert derive_init_completion_state(cancelled) == (
        ProjectFactoryInitCompletionState.CANCELLED
    )

    resumable = (
        ProjectFactoryInitPhase(
            name=ProjectFactoryInitPhaseName.INIT_PREFLIGHT,
            status=ProjectFactoryInitPhaseStatus.COMPLETED,
        ),
        ProjectFactoryInitPhase(
            name=ProjectFactoryInitPhaseName.DRAFT_AND_SLUG,
            status=ProjectFactoryInitPhaseStatus.QUEUED,
        ),
    )
    assert derive_init_completion_state(resumable) == (
        ProjectFactoryInitCompletionState.RESUMABLE
    )
