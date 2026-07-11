from __future__ import annotations

import json
from pathlib import Path

from backend.app.application.services.project_factory_init_service import (
    ProjectFactoryInitService,
)
from backend.app.domain.entities.project_factory_init import (
    ProjectFactoryInitPhaseName,
    ProjectFactoryInitPhaseStatus,
)
from backend.app.infrastructure.config.settings import Settings


def test_frontend_baseline_generates_and_verifies_flutter_contracts(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    job = _job(service)

    completed = service.run_frontend_baseline_phase(job.id)

    project = tmp_path / "projects/clinica-norte"
    assert (project / "apps/mobile/pubspec.yaml").is_file()
    assert (project / "apps/mobile/android/app/src/main/AndroidManifest.xml").is_file()
    assert (project / "apps/mobile/web/index.html").is_file()
    phase = completed.phase(ProjectFactoryInitPhaseName.FLUTTER_OR_STRATEGY_BASELINE)
    assert phase.status == ProjectFactoryInitPhaseStatus.COMPLETED
    assert phase.command_evidence[0].argv[:2] == (
        "project-factory-generator",
        "generate",
    )
    artifacts = {artifact.kind: artifact for artifact in phase.artifacts}
    assert artifacts["frontend_baseline"].metadata["status"] == "generated"
    assert artifacts["workbench_sdd_metadata"].metadata["sourceApp"] == "clinica-norte"
    feedback = artifacts["feedback_updater_wiring"].metadata
    assert feedback["feedbackTemplate"] is True
    assert feedback["appUpdater"] is True
    assert feedback["bridgeWorkbench"] is True
    assert feedback["bridgeUrlSeparatedFromBusinessApi"] is True
    runtime = artifacts["preview_runtime_guardrails"].metadata
    assert runtime["apiBaseUrl"] == "https://preview.nienfos.com/clinica-norte/api"
    assert runtime["apiRuntime"] == "cloudflare_preview"
    assert runtime["dataPersistence"] == "cloudflare_d1"
    assert completed.relationships.generated_workspace_path == str(project)
    assert completed.relationships.workbench_scope_id == f"workspace:{project}"
    assert completed.phase(
        ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE
    ).status == ProjectFactoryInitPhaseStatus.QUEUED
    assert completed.phase(
        ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION
    ).status == ProjectFactoryInitPhaseStatus.QUEUED


def test_frontend_baseline_existing_workspace_is_verified_idempotently(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    job = _job(service)
    first = service.run_frontend_baseline_phase(job.id)

    second = service.run_frontend_baseline_phase(first.id)

    phase = second.phase(ProjectFactoryInitPhaseName.FLUTTER_OR_STRATEGY_BASELINE)
    assert phase.status == ProjectFactoryInitPhaseStatus.COMPLETED
    assert phase.command_evidence[0].argv[:2] == (
        "project-factory-generator",
        "verify-existing",
    )
    assert phase.artifacts[0].metadata["status"] == "verified_existing"


def test_frontend_baseline_blocks_missing_flutter_baseline(tmp_path: Path) -> None:
    project = tmp_path / "projects/clinica-norte"
    project.mkdir(parents=True)
    service = _service(tmp_path)
    job = _job(service, workspace_path=project)

    blocked = service.run_frontend_baseline_phase(job.id)

    phase = blocked.phase(ProjectFactoryInitPhaseName.FLUTTER_OR_STRATEGY_BASELINE)
    assert phase.status == ProjectFactoryInitPhaseStatus.BLOCKED
    assert phase.blockers[0].code == "frontend_baseline_missing"
    assert "apps/mobile/pubspec.yaml" in phase.blockers[0].message
    assert phase.blockers[0].command == (
        "project-factory",
        "init",
        "baseline",
        "repair",
    )


def test_frontend_baseline_blocks_mock_or_local_preview_runtime(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    job = _job(service)
    first = service.run_frontend_baseline_phase(job.id)
    runtime_path = Path(first.relationships.generated_workspace_path or "") / (
        "release/preview-runtime.json"
    )
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    runtime["apiBaseUrl"] = "http://localhost:8000"
    runtime_path.write_text(json.dumps(runtime), encoding="utf-8")

    blocked = service.run_frontend_baseline_phase(job.id)

    phase = blocked.phase(ProjectFactoryInitPhaseName.FLUTTER_OR_STRATEGY_BASELINE)
    assert phase.status == ProjectFactoryInitPhaseStatus.BLOCKED
    assert phase.blockers[0].code in {
        "preview_runtime_contract_invalid",
        "preview_runtime_mock_or_local_blocked",
    }
    assert "preview runtime" in phase.blockers[0].message.lower()


def test_frontend_baseline_svelte_skips_android_and_installable_phases(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    job = _job(service, frontend_strategy="svelte")

    completed = service.run_frontend_baseline_phase(job.id)

    project = tmp_path / "projects/clinica-norte"
    assert (project / "apps/web/package.json").is_file()
    assert not (project / "apps/mobile/pubspec.yaml").exists()
    assert completed.phase(
        ProjectFactoryInitPhaseName.FLUTTER_OR_STRATEGY_BASELINE
    ).status == ProjectFactoryInitPhaseStatus.COMPLETED
    assert completed.phase(
        ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE
    ).status == ProjectFactoryInitPhaseStatus.SKIPPED
    assert completed.phase(
        ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION
    ).status == ProjectFactoryInitPhaseStatus.SKIPPED
    capabilities = next(
        artifact
        for artifact in completed.phase(
            ProjectFactoryInitPhaseName.FLUTTER_OR_STRATEGY_BASELINE
        ).artifacts
        if artifact.kind == "frontend_strategy_capabilities"
    )
    assert capabilities.metadata["supportsAndroidPreviewApk"] is False
    assert capabilities.metadata["supportsBridgeInstallableApp"] is False


def test_frontend_baseline_persists_after_reload(tmp_path: Path) -> None:
    service = _service(tmp_path)
    job = _job(service)
    completed = service.run_frontend_baseline_phase(job.id)

    reloaded = ProjectFactoryInitService(
        state_root=tmp_path / "state",
        settings=_settings(tmp_path),
    )
    loaded = reloaded.get_job(completed.id)

    assert loaded is not None
    phase = loaded.phase(ProjectFactoryInitPhaseName.FLUTTER_OR_STRATEGY_BASELINE)
    assert phase.status == ProjectFactoryInitPhaseStatus.COMPLETED
    assert loaded.relationships.workbench_scope_id == (
        f"workspace:{tmp_path / 'projects/clinica-norte'}"
    )
    assert any(
        artifact.kind == "feedback_updater_wiring" for artifact in phase.artifacts
    )


def _service(tmp_path: Path) -> ProjectFactoryInitService:
    return ProjectFactoryInitService(
        state_root=tmp_path / "state",
        settings=_settings(tmp_path),
    )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        projects_root=str(tmp_path / "projects"),
        project_factory_state_dir=str(tmp_path / "state"),
        preview_base_domain="preview.nienfos.com",
    )


def _job(
    service: ProjectFactoryInitService,
    *,
    frontend_strategy: str = "flutter",
    workspace_path: Path | None = None,
):
    return service.start_or_resume(
        draft_id=f"draft-{frontend_strategy}",
        project_name="Clinica Norte",
        slug="clinica-norte",
        frontend_strategy=frontend_strategy,
        workspace_path=str(workspace_path) if workspace_path is not None else None,
    )
