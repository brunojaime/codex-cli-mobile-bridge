from __future__ import annotations

import json
from pathlib import Path

from backend.app.application.services.project_factory_generator_service import (
    ProjectFactoryGeneratedFile,
    ProjectFactoryGenerationResult,
)
from backend.app.application.services.project_factory_init_service import (
    ProjectFactoryInitService,
)
from backend.app.application.services.project_factory_job_runner import (
    ProjectFactoryJobRunner,
    ProjectFactoryProcessResult,
    ProjectFactoryRunnerContext,
)
from backend.app.application.services.project_factory_manifest_service import (
    ProjectFactoryManifestInput,
    ProjectFactoryManifestService,
)
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.project_factory_init import (
    INIT_PHASE_ORDER,
    ProjectFactoryInitBlocker,
    ProjectFactoryInitCommandEvidence,
    ProjectFactoryInitPhaseName,
    ProjectFactoryInitPhaseStatus,
    ProjectFactoryInitRemoteResource,
    ProjectFactoryInitRemoteResourceType,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.persistence.in_memory_chat_repository import (
    InMemoryChatRepository,
)


def test_context_pack_writes_ready_json_markdown_attaches_chat_and_persists(
    tmp_path: Path,
) -> None:
    repository = _chat_repository(tmp_path)
    repository.save_session(_session(tmp_path))
    service = _service(tmp_path, repository=repository)
    job = _ready_job(service)

    completed = service.run_llm_context_pack_phase(job.id)
    workspace = Path(completed.relationships.generated_workspace_path or "")
    init_result = workspace / ".codex/factory/init-result.json"
    markdown_path = workspace / ".codex/factory/llm-start-context.md"
    payload = json.loads(init_result.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")

    assert payload["kind"] == "codex.projectFactoryInitResult"
    assert payload["draftId"] == "draft-1"
    assert payload["initJobId"] == job.id
    assert payload["chatSessionId"] == "chat-1"
    assert payload["sourceApp"] == "clinica-norte"
    assert payload["workspacePath"] == str(workspace)
    assert payload["readyForBusinessLlm"] is True
    assert payload["blockedWithContext"] is False
    assert payload["resources"]["github"]["repoUrl"] == (
        "https://github.com/owner/clinica-norte"
    )
    assert payload["resources"]["cloudflarePreview"]["previewUrl"] == (
        "https://preview.nienfos.com/clinica-norte"
    )
    assert payload["resources"]["cloudflarePreview"]["apiBaseUrl"] == (
        "https://preview.nienfos.com/clinica-norte/api"
    )
    assert payload["resources"]["androidPreviewRelease"]["releaseTag"] == (
        "android-preview-v0.1.0-build.1"
    )
    assert payload["resources"]["bridgeInstallable"]["sourceApp"] == "clinica-norte"
    assert "Do not recreate GitHub, Cloudflare Worker/route/D1" in markdown
    assert "mock, demo, localhost, placeholder" in markdown.lower()
    phase = completed.phase(ProjectFactoryInitPhaseName.LLM_CONTEXT_PACK)
    assert phase.status == ProjectFactoryInitPhaseStatus.COMPLETED
    assert completed.context_pack is not None
    assert completed.context_pack.attached_to_chat is True
    assert completed.context_pack.attached_message_id
    messages = repository.list_messages("chat-1")
    assert len(messages) == 1
    assert messages[0].dedupe_key == f"project-factory-init-context-pack:{job.id}"
    assert "Deterministic Init Context" in messages[0].content

    reloaded = ProjectFactoryInitService(
        state_root=tmp_path / "state",
        settings=_settings(tmp_path),
        chat_repository=repository,
    )
    persisted = reloaded.get_job(job.id)
    assert persisted is not None
    assert persisted.context_pack is not None
    assert persisted.context_pack.content_sha256 == completed.context_pack.content_sha256


def test_context_pack_rerun_keeps_hash_and_chat_attachment_idempotent(
    tmp_path: Path,
) -> None:
    repository = _chat_repository(tmp_path)
    repository.save_session(_session(tmp_path))
    service = _service(tmp_path, repository=repository)
    job = _ready_job(service)

    first = service.run_llm_context_pack_phase(job.id)
    second = service.run_llm_context_pack_phase(job.id)

    assert first.context_pack is not None
    assert second.context_pack is not None
    assert second.context_pack.content_sha256 == first.context_pack.content_sha256
    assert second.context_pack.attached_message_id == first.context_pack.attached_message_id
    assert len(repository.list_messages("chat-1")) == 1


def test_context_pack_blocked_json_markdown_includes_retry_actions(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    job = _ready_job(service)
    blocked = service.block_phase(
        job.id,
        ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_PROVISION.value,
        blocker=ProjectFactoryInitBlocker(
            code="cloudflare_d1_access_missing",
            message="D1 access missing.",
            phase=ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_PROVISION,
            next_action="Run wrangler login and grant D1 access.",
            command=("wrangler", "login"),
        ),
        context_available=True,
    )

    completed = service.run_llm_context_pack_phase(blocked.id)
    workspace = Path(completed.relationships.generated_workspace_path or "")
    payload = json.loads(
        (workspace / ".codex/factory/init-result.json").read_text(encoding="utf-8")
    )
    markdown = (workspace / ".codex/factory/llm-start-context.md").read_text(
        encoding="utf-8"
    )

    assert payload["readyForBusinessLlm"] is False
    assert payload["blockedWithContext"] is True
    assert payload["blockers"][0]["code"] == "cloudflare_d1_access_missing"
    assert payload["blockers"][0]["command"] == ["wrangler", "login"]
    assert "blocked_with_context" in markdown
    assert "wrangler login" in markdown
    assert "None." not in markdown


def test_context_pack_redacts_secrets_from_json_markdown_and_state(
    tmp_path: Path,
) -> None:
    secret = "super-secret-token"
    service = _service(tmp_path, command_env={"GH_TOKEN": secret})
    job = _ready_job(service, secret=secret)

    completed = service.run_llm_context_pack_phase(job.id)
    workspace = Path(completed.relationships.generated_workspace_path or "")
    init_text = (workspace / ".codex/factory/init-result.json").read_text(
        encoding="utf-8"
    )
    markdown = (workspace / ".codex/factory/llm-start-context.md").read_text(
        encoding="utf-8"
    )
    state = json.dumps(completed.to_payload())

    assert secret not in init_text
    assert secret not in markdown
    assert secret not in state
    assert "[redacted]" in init_text


def test_business_prompts_consume_context_pack_without_recreating_setup(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    job = _ready_job(service)
    completed = service.run_llm_context_pack_phase(job.id)
    workspace = Path(completed.relationships.generated_workspace_path or "")
    process_runner = _PromptCaptureRunner()
    runner = ProjectFactoryJobRunner(
        generator_service=_ReusableProjectGenerator(workspace),
        process_runner=process_runner,
    )

    runner.run(_runner_context(tmp_path), event_sink=lambda event: None)

    generator_prompt = process_runner.calls[1][-1]
    reviewer_prompt = process_runner.calls[2][-1]
    assert "Initialized deterministic baseline" in generator_prompt
    assert ".codex/factory/init-result.json" in generator_prompt
    assert "https://preview.nienfos.com/clinica-norte/api" in generator_prompt
    assert "Do not recreate GitHub, Cloudflare Worker/route/D1" in generator_prompt
    assert "Initial git commit, GitHub publish/push status" not in generator_prompt
    assert "Initialized deterministic baseline" in reviewer_prompt
    assert "Do not recreate GitHub, Cloudflare Worker/route/D1" in reviewer_prompt


def _service(
    tmp_path: Path,
    *,
    repository: InMemoryChatRepository | None = None,
    command_env: dict[str, str] | None = None,
) -> ProjectFactoryInitService:
    return ProjectFactoryInitService(
        state_root=tmp_path / "state",
        settings=_settings(tmp_path),
        chat_repository=repository,
        command_env=command_env,
    )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        projects_root=str(tmp_path / "projects"),
        project_factory_state_dir=str(tmp_path / "state"),
        preview_base_domain="preview.nienfos.com",
        api_base_url="https://bridge.test",
        installable_apps_registration_token="bridge-secret-token",
    )


def _chat_repository(tmp_path: Path) -> InMemoryChatRepository:
    return InMemoryChatRepository(projects_root=str(tmp_path / "projects"))


def _session(tmp_path: Path) -> ChatSession:
    return ChatSession(
        id="chat-1",
        title="New Project",
        workspace_path=str(tmp_path / "projects/clinica-norte"),
        workspace_name="clinica-norte",
    )


def _ready_job(
    service: ProjectFactoryInitService,
    *,
    secret: str | None = None,
):
    job = service.start_or_resume(
        draft_id="draft-1",
        chat_session_id="chat-1",
        project_name="Clinica Norte",
        slug="clinica-norte",
        frontend_strategy="flutter",
    )
    job = service.run_frontend_baseline_phase(job.id)
    for phase in INIT_PHASE_ORDER:
        if phase in {
            ProjectFactoryInitPhaseName.FLUTTER_OR_STRATEGY_BASELINE,
            ProjectFactoryInitPhaseName.LLM_CONTEXT_PACK,
        }:
            continue
        evidence = ()
        if secret and phase == ProjectFactoryInitPhaseName.GITHUB_REPOSITORY:
            evidence = (
                ProjectFactoryInitCommandEvidence(
                    argv=("gh", "repo", "view"),
                    stdout_summary=f"repo ok {secret}",
                    stderr_summary=f"stderr {secret}",
                    redacted_env_keys=("GH_TOKEN",),
                ),
            )
        job = service.complete_phase(
            job.id,
            phase.value,
            message=f"{phase.value} completed.",
            command_evidence=evidence,
        )
    for resource in _remote_resources(secret=secret):
        job = service.record_remote_resource(job.id, resource=resource)
    return job


def _remote_resources(
    *,
    secret: str | None = None,
) -> tuple[ProjectFactoryInitRemoteResource, ...]:
    return (
        ProjectFactoryInitRemoteResource(
            type=ProjectFactoryInitRemoteResourceType.GITHUB_REPOSITORY,
            identifier="owner/clinica-norte",
            display_name="owner/clinica-norte",
            url="https://github.com/owner/clinica-norte",
            provider="github",
            status="ready",
            metadata={"token": secret} if secret else {},
        ),
        ProjectFactoryInitRemoteResource(
            type=ProjectFactoryInitRemoteResourceType.GITHUB_BRANCH,
            identifier="main",
            display_name="main",
            provider="github",
            status="pushed",
        ),
        ProjectFactoryInitRemoteResource(
            type=ProjectFactoryInitRemoteResourceType.PREVIEW_URL,
            identifier="clinica-norte-preview",
            display_name="Preview URL",
            url="https://preview.nienfos.com/clinica-norte",
            provider="cloudflare",
            status="smoke_passed",
        ),
        ProjectFactoryInitRemoteResource(
            type=ProjectFactoryInitRemoteResourceType.API_BASE_URL,
            identifier="clinica-norte-api",
            display_name="Preview API",
            url="https://preview.nienfos.com/clinica-norte/api",
            provider="cloudflare",
            status="smoke_passed",
        ),
        ProjectFactoryInitRemoteResource(
            type=ProjectFactoryInitRemoteResourceType.CLOUDFLARE_WORKER,
            identifier="nienfos-preview-runtime",
            display_name="nienfos-preview-runtime",
            provider="cloudflare",
            status="verified",
        ),
        ProjectFactoryInitRemoteResource(
            type=ProjectFactoryInitRemoteResourceType.CLOUDFLARE_ROUTE,
            identifier="preview.nienfos.com/clinica-norte*",
            display_name="preview route",
            provider="cloudflare",
            status="verified",
        ),
        ProjectFactoryInitRemoteResource(
            type=ProjectFactoryInitRemoteResourceType.CLOUDFLARE_D1_DATABASE,
            identifier="d1-clinica-norte",
            display_name="nienfos-preview",
            provider="cloudflare",
            status="migrated",
        ),
        ProjectFactoryInitRemoteResource(
            type=ProjectFactoryInitRemoteResourceType.GITHUB_RELEASE,
            identifier="android-preview-v0.1.0-build.1",
            display_name="android-preview-v0.1.0-build.1",
            url="https://github.com/owner/clinica-norte/releases/tag/android-preview-v0.1.0-build.1",
            provider="github",
            status="prerelease_verified",
            metadata={"apkSha256": "a" * 64, "asset": {"name": "clinica-norte.apk"}},
        ),
        ProjectFactoryInitRemoteResource(
            type=ProjectFactoryInitRemoteResourceType.BRIDGE_INSTALLABLE_APP,
            identifier="clinica-norte",
            display_name="Clinica Norte Preview",
            url="https://bridge.test/app-updates/clinica-norte/apk/clinica-norte.apk",
            provider="codex-mobile-bridge",
            status="available",
            metadata={
                "sourceApp": "clinica-norte",
                "releaseChannel": "prerelease",
                "mockOrDemo": False,
            },
        ),
    )


class _PromptCaptureRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, *, argv, cwd, env, timeout_seconds):
        del cwd, env, timeout_seconds
        self.calls.append(tuple(argv))
        return ProjectFactoryProcessResult(returncode=0, stdout="ok", stderr="")


class _ReusableProjectGenerator:
    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path

    def generate(self, manifest_plan, *, reference_assets=(), project_assets=()):
        del manifest_plan, reference_assets, project_assets
        return ProjectFactoryGenerationResult(
            ok=True,
            status="ready",
            target_path=str(self.project_path),
            generated_files=(
                ProjectFactoryGeneratedFile(path=".codex/project.yaml", size_bytes=0),
            ),
            git_status="existing",
            message="Existing project foundation verified.",
        )


def _runner_context(tmp_path: Path) -> ProjectFactoryRunnerContext:
    plan = ProjectFactoryManifestService(projects_root=tmp_path / "projects").plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
        )
    )
    return ProjectFactoryRunnerContext(
        draft_id="draft-1",
        manifest_plan=plan,
        reference_assets=(),
        generator_runs=1,
        reviewer_runs=1,
        codex_command="fake-codex",
        timeout_seconds=1,
    )
