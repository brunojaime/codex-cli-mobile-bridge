from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from backend.app.application.services.project_factory_generator_service import (
    ProjectFactoryGeneratorService,
)
from backend.app.application.services.project_factory_init_service import (
    INIT_PHASES,
    ProjectFactoryInitService,
)
from backend.app.application.services.project_factory_manifest_service import (
    ProjectFactoryManifestInput,
    ProjectFactoryManifestService,
)
from backend.app.domain.entities.project_factory_init import (
    INIT_PHASE_ORDER,
    ProjectFactoryInitBlocker,
    ProjectFactoryInitPhaseName,
    ProjectFactoryInitPhaseStatus,
    ProjectFactoryInitRemoteResource,
    ProjectFactoryInitRemoteResourceType,
)
from backend.app.infrastructure.config.settings import Settings


def test_init_state_transitions_recovery_and_phase_ordering(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    job = service.start_or_resume(
        draft_id="draft-1",
        chat_session_id="chat-1",
        project_name="Clinica Norte",
        slug="clinica-norte",
    )

    assert INIT_PHASES == tuple(phase.value for phase in INIT_PHASE_ORDER)
    assert service.to_response_payload(job)["status"] == "queued"
    assert service.to_response_payload(job)["currentPhase"] == "init_preflight"

    running = service.begin_phase(job.id, "init_preflight", message="checking")
    assert service.to_response_payload(running)["status"] == "running"
    completed = service.complete_phase(running.id, "init_preflight")
    assert service.to_response_payload(completed)["currentPhase"] == "draft_and_slug"

    service.begin_phase(completed.id, "github_repository", message="will recover")
    reloaded = _service(tmp_path)
    recovered = reloaded.get_job(job.id)
    assert recovered is not None
    assert recovered.phase(ProjectFactoryInitPhaseName.GITHUB_REPOSITORY).status == (
        ProjectFactoryInitPhaseStatus.QUEUED
    )
    assert reloaded.to_response_payload(recovered)["status"] == "resumable"

    blocked = reloaded.block_phase(
        recovered.id,
        ProjectFactoryInitPhaseName.GITHUB_REPOSITORY.value,
        blocker=ProjectFactoryInitBlocker(
            code="github_owner_missing",
            message="GitHub owner is required.",
            phase=ProjectFactoryInitPhaseName.GITHUB_REPOSITORY,
            next_action="Set PROJECT_FACTORY_GITHUB_OWNER.",
            command=("export", "PROJECT_FACTORY_GITHUB_OWNER=owner"),
        ),
        context_available=True,
    )
    blocked_payload = reloaded.to_response_payload(blocked)
    assert blocked_payload["status"] == "blocked_with_context"
    assert blocked_payload["readyForBusinessLlm"] is False
    assert blocked_payload["blockers"][0]["command"] == [
        "export",
        "PROJECT_FACTORY_GITHUB_OWNER=owner",
    ]

    failed = _service(tmp_path / "failed").start_or_resume(draft_id="failed")
    failed = _service(tmp_path / "failed").fail_phase(
        failed.id,
        "init_preflight",
        message="tool failure",
    )
    assert failed.completion_state.value == "failed"

    cancelled_service = _service(tmp_path / "cancelled")
    cancelled = cancelled_service.start_or_resume(draft_id="cancelled")
    cancelled = cancelled_service.cancel(cancelled.id)
    assert cancelled.completion_state.value == "cancelled"


def test_ready_context_requires_no_blockers_even_when_context_pack_exists(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    job = service.start_or_resume(
        draft_id="draft-1",
        project_name="Clinica Norte",
        slug="clinica-norte",
    )
    job = service.run_frontend_baseline_phase(job.id)
    for phase in INIT_PHASE_ORDER:
        if phase in {
            ProjectFactoryInitPhaseName.FLUTTER_OR_STRATEGY_BASELINE,
            ProjectFactoryInitPhaseName.GITHUB_REPOSITORY,
            ProjectFactoryInitPhaseName.LLM_CONTEXT_PACK,
        }:
            continue
        job = service.complete_phase(job.id, phase.value)
    job = service.block_phase(
        job.id,
        ProjectFactoryInitPhaseName.GITHUB_REPOSITORY.value,
        blocker=ProjectFactoryInitBlocker(
            code="github_push_failed",
            message="Push failed.",
            phase=ProjectFactoryInitPhaseName.GITHUB_REPOSITORY,
            next_action="Run git push -u origin main.",
            command=("git", "push", "-u", "origin", "main"),
        ),
        context_available=True,
    )

    completed = service.run_llm_context_pack_phase(job.id)
    payload = json.loads(
        (
            Path(completed.relationships.generated_workspace_path or "")
            / ".codex/factory/init-result.json"
        ).read_text(encoding="utf-8")
    )

    assert completed.completion_state.value == "blocked_with_context"
    assert payload["readyForBusinessLlm"] is False
    assert payload["blockedWithContext"] is True
    assert payload["blockers"][0]["code"] == "github_push_failed"


def test_release_guardrails_keep_preview_real_and_reject_regressions(
    tmp_path: Path,
) -> None:
    manifest_plan = ProjectFactoryManifestService(projects_root=tmp_path).plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
        )
    )
    ProjectFactoryGeneratorService().generate(manifest_plan)
    project = tmp_path / "clinica-norte"
    runtime = json.loads(
        (project / "release/preview-runtime.json").read_text(encoding="utf-8")
    )

    assert runtime["apiBaseUrl"] == "https://preview.nienfos.com/clinica-norte/api"
    assert runtime["runtimeProfile"] == "preview"
    assert runtime["apiRuntime"] == "cloudflare_preview"
    assert runtime["releaseChannel"] == "prerelease"
    assert runtime["releaseTagPattern"] == "android-preview-v*"
    assert runtime["productionReady"] is False
    assert runtime["mockOrDemo"] is False
    assert "localhost" not in json.dumps(runtime).lower()
    assert "placeholder" not in json.dumps(runtime).lower()

    good = subprocess.run(
        [str(project / "scripts/validate_release_profiles.sh")],
        cwd=project,
        env={
            **os.environ,
            "APP_RELEASE_TAG": "android-preview-v0.1.0-build.1",
            "APP_RUNTIME_PROFILE": "preview",
            "API_RUNTIME": "cloudflare_preview",
            "API_BASE_URL": "https://preview.nienfos.com/clinica-norte/api",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert good.returncode == 0, good.stdout + good.stderr

    bad = subprocess.run(
        [str(project / "scripts/validate_release_profiles.sh")],
        cwd=project,
        env={
            **os.environ,
            "APP_RELEASE_TAG": "android-preview-v0.1.0-build.1",
            "APP_RUNTIME_PROFILE": "preview",
            "API_RUNTIME": "cloudflare_preview",
            "API_BASE_URL": "http://127.0.0.1:8000",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert bad.returncode != 0
    assert "preview releases require API_BASE_URL" in bad.stdout + bad.stderr


def test_context_pack_preserves_release_and_bridge_evidence_without_secrets(
    tmp_path: Path,
) -> None:
    secret = "secret-token"
    service = _service(tmp_path, command_env={"GH_TOKEN": secret})
    job = service.start_or_resume(
        draft_id="draft-1",
        project_name="Clinica Norte",
        slug="clinica-norte",
    )
    job = service.run_frontend_baseline_phase(job.id)
    for phase in INIT_PHASE_ORDER:
        if phase in {
            ProjectFactoryInitPhaseName.FLUTTER_OR_STRATEGY_BASELINE,
            ProjectFactoryInitPhaseName.LLM_CONTEXT_PACK,
        }:
            continue
        job = service.complete_phase(job.id, phase.value)
    for resource in (
        ProjectFactoryInitRemoteResource(
            type=ProjectFactoryInitRemoteResourceType.GITHUB_RELEASE,
            identifier="android-preview-v0.1.0-build.1",
            display_name="android-preview-v0.1.0-build.1",
            provider="github",
            status="prerelease_verified",
            metadata={"token": secret, "apkSha256": "a" * 64},
        ),
        ProjectFactoryInitRemoteResource(
            type=ProjectFactoryInitRemoteResourceType.BRIDGE_INSTALLABLE_APP,
            identifier="clinica-norte",
            display_name="Clinica Norte Preview",
            provider="codex-mobile-bridge",
            status="available",
            metadata={
                "releaseChannel": "prerelease",
                "productionReady": False,
                "mockOrDemo": False,
            },
        ),
    ):
        job = service.record_remote_resource(job.id, resource=resource)

    completed = service.run_llm_context_pack_phase(job.id)
    state = json.dumps(completed.to_payload())
    payload = json.loads(
        (
            Path(completed.relationships.generated_workspace_path or "")
            / ".codex/factory/init-result.json"
        ).read_text(encoding="utf-8")
    )

    assert secret not in state
    assert secret not in json.dumps(payload)
    assert payload["resources"]["androidPreviewRelease"]["releaseTag"] == (
        "android-preview-v0.1.0-build.1"
    )
    assert payload["resources"]["bridgeInstallable"]["status"] == "available"


def _service(
    tmp_path: Path,
    *,
    command_env: dict[str, str] | None = None,
) -> ProjectFactoryInitService:
    return ProjectFactoryInitService(
        state_root=tmp_path / "state",
        settings=Settings(
            projects_root=str(tmp_path / "projects"),
            project_factory_state_dir=str(tmp_path / "state"),
            preview_base_domain="preview.nienfos.com",
        ),
        command_env=command_env,
    )
