from __future__ import annotations

import json
from pathlib import Path

from backend.app.application.services.domain_factory_service import (
    DomainFactoryService,
)
from backend.app.application.services.message_service import MessageService
from backend.app.main import create_app
from backend.app.domain.entities.agent_configuration import AgentId
from backend.app.domain.entities.codex_options import CodexRunOptions
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.job import JobStatus
from backend.app.infrastructure.execution.base import ExecutionProvider
from backend.app.infrastructure.persistence.in_memory_chat_repository import (
    InMemoryChatRepository,
)
from backend.app.infrastructure.transcription.disabled_transcriber import (
    DisabledAudioTranscriber,
)


def test_start_domain_factory_configures_current_session_and_writes_sdd(
    tmp_path: Path,
) -> None:
    workspace = _baseline_workspace(tmp_path)
    repository = _repository(tmp_path)
    session = _session(workspace)
    repository.save_session(session)
    service = DomainFactoryService(
        projects_root=tmp_path / "projects",
        chat_repository=repository,
    )

    result = service.start(session_id=session.id)

    assert result.status == "ready"
    assert result.session.id == session.id
    assert result.session.workspace_path == str(workspace)
    assert result.context.source_app == "clinica-norte"
    assert result.context.api_url == "https://preview.nienfos.com/clinica-norte/api"
    assert result.state_path == ".codex/factory/domain-factory-state.json"
    assert result.spec_root is not None

    updated = repository.get_session(session.id)
    assert updated is not None
    configuration = updated.agent_configuration.normalized()
    generator = configuration.agents[AgentId.GENERATOR]
    reviewer = configuration.agents[AgentId.REVIEWER]
    assert generator.label == "Domain Factory"
    assert reviewer.label == "Domain Reviewer"
    assert generator.enabled is True
    assert reviewer.enabled is True
    assert "not creating a new project" in generator.prompt
    assert "Owner/admin must retain access" in generator.prompt
    assert "mock/demo/local/placeholder data" in generator.prompt
    assert "did not recreate New Project baseline infrastructure" in reviewer.prompt

    messages = repository.list_messages(session.id)
    assert len(messages) == 1
    assert messages[0].dedupe_key == f"domain-factory:start:{session.id}:{workspace}"
    assert "Domain Factory mode is active" in messages[0].content
    assert "Send the business/domain brief here" in messages[0].content

    state = json.loads(
        (workspace / ".codex/factory/domain-factory-state.json").read_text(
            encoding="utf-8"
        )
    )
    assert state["sessionId"] == session.id
    assert state["sourceApp"] == "clinica-norte"
    assert state["modeStatus"] == "intake"
    assert state["guardrails"]["mockDemoRequiresExplicitUserRequest"] is True
    assert state["releaseGuardrails"]["mustNotOverwriteBuild"] == 1
    assert state["rolePermissionModel"]["owner"]["allAccess"] is True
    assert state["rolePermissionModel"]["admin"]["allAccess"] is True

    spec_root = workspace / result.spec_root
    assert (spec_root / "spec.md").exists()
    assert (spec_root / "plan.md").exists()
    assert (spec_root / "tasks.md").exists()
    assert (spec_root / "traceability.yaml").exists()
    intake_contract = json.loads(
        (spec_root / "intake/domain-intake-contract.json").read_text(encoding="utf-8")
    )
    assert "project name or slug" in intake_contract["baselineFieldsToAvoid"]
    assert "business outcome" in intake_contract["intakeFields"]
    assert intake_contract["rolePermissionModel"]["owner"]["permissions"] == ["*"]
    assert (
        intake_contract["pairedWorkflow"]["reviewerFeedbackBecomesNextGeneratorPrompt"]
        is True
    )
    release_guardrails = json.loads(
        (spec_root / "release-guardrails.json").read_text(encoding="utf-8")
    )
    assert release_guardrails["realPreviewOnly"] is True
    assert release_guardrails["mustNotOverwriteBuild"] == 1
    assert "bridgeRegistryPayload" in release_guardrails["requiredEvidenceFields"]
    for diagram in (
        "entity-relationship.mmd",
        "class.mmd",
        "sequence.mmd",
        "component.mmd",
        "deployment.mmd",
    ):
        assert (spec_root / "diagrams" / diagram).exists()


def test_start_domain_factory_accepts_block_empty_lists_in_project_yaml(
    tmp_path: Path,
) -> None:
    workspace = _baseline_workspace(tmp_path)
    (workspace / ".codex/project.yaml").write_text(
        """
schema_version: 1
name: Clinica Norte
slug: clinica-norte
visual_references:
  uploaded_images:
    []
  reference_assets:
    []
asset_depot:
  project_assets:
    []
admin:
  initial_invites:
    emails:
      []
runtime_profiles:
  preview:
    api_base_url: "https://preview.nienfos.com/clinica-norte/api"
""".lstrip(),
        encoding="utf-8",
    )
    repository = _repository(tmp_path)
    session = _session(workspace)
    repository.save_session(session)
    service = DomainFactoryService(
        projects_root=tmp_path / "projects",
        chat_repository=repository,
    )

    result = service.start(session_id=session.id)

    assert result.status == "ready"
    assert result.context.source_app == "clinica-norte"
    assert result.context.api_url == "https://preview.nienfos.com/clinica-norte/api"


def test_domain_factory_chat_message_creates_contract_preview_without_codex_run(
    tmp_path: Path,
) -> None:
    workspace = _baseline_workspace(tmp_path)
    repository = _repository(tmp_path)
    execution_provider = _CountingExecutionProvider()
    message_service = MessageService(
        repository=repository,
        execution_provider=execution_provider,
        default_workspace_path=str(tmp_path / "projects"),
        audio_transcriber=DisabledAudioTranscriber(),
    )
    domain_factory = DomainFactoryService(
        projects_root=tmp_path / "projects",
        chat_repository=repository,
    )
    message_service.set_domain_factory_service(domain_factory)
    session = _session(workspace)
    repository.save_session(session)
    domain_factory.start(session_id=session.id)

    job = message_service.submit_message(
        "Restaurant customers order dishes by WhatsApp. Roles: admin, employee, customer.",
        session_id=session.id,
    )

    assert job.status == JobStatus.COMPLETED
    assert execution_provider.execute_count == 0
    state = json.loads(
        (workspace / ".codex/factory/domain-factory-state.json").read_text(
            encoding="utf-8"
        )
    )
    assert state["modeStatus"] == "implementation_ready"
    spec_root = workspace / state["specRoot"]
    assert (spec_root / "intake/original-brief.md").exists()
    assert (spec_root / "contract-preview.json").exists()
    messages = repository.list_messages(session.id)
    assert [message.role.value for message in messages] == [
        "assistant",
        "user",
        "assistant",
    ]
    assert all(message.status.value == "completed" for message in messages)
    assert "Domain Factory contract preview is ready" in messages[-1].content


def test_start_domain_factory_blocks_without_baseline_context(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "projects" / "missing-baseline"
    workspace.mkdir(parents=True)
    repository = _repository(tmp_path)
    session = _session(workspace)
    repository.save_session(session)
    service = DomainFactoryService(
        projects_root=tmp_path / "projects",
        chat_repository=repository,
    )

    result = service.start(session_id=session.id)

    assert result.status == "blocked"
    assert result.spec_root is None
    assert result.state_path is None
    assert {blocker.code for blocker in result.context.blockers} == {
        "missing_bridge_manifest",
        "missing_init_result",
        "missing_llm_start_context",
        "missing_preview_runtime",
        "missing_project_manifest",
        "missing_runtime_profile",
        "missing_api_runtime",
        "missing_preview_api_url",
    }
    updated = repository.get_session(session.id)
    assert updated is not None
    assert (
        updated.agent_configuration.normalized().agents[AgentId.GENERATOR].label
        == "Generator"
    )
    messages = repository.list_messages(session.id)
    assert len(messages) == 1
    assert "could not start yet" in messages[0].content
    assert "missing_init_result" in messages[0].content


def test_domain_factory_blocks_each_missing_critical_baseline_file(
    tmp_path: Path,
) -> None:
    expected_codes = {
        "codex-bridge.yaml": "missing_bridge_manifest",
        ".codex/factory/init-result.json": "missing_init_result",
        ".codex/factory/llm-start-context.md": "missing_llm_start_context",
        "release/preview-runtime.json": "missing_preview_runtime",
        ".codex/project.yaml": "missing_project_manifest",
    }
    for relative_path, expected_code in expected_codes.items():
        workspace = _baseline_workspace(tmp_path / relative_path.replace("/", "_"))
        (workspace / relative_path).unlink()
        repository = _repository(workspace.parent.parent)
        session = _session(workspace)
        repository.save_session(session)
        service = DomainFactoryService(
            projects_root=workspace.parent,
            chat_repository=repository,
        )

        result = service.start(session_id=session.id)

        assert result.status == "blocked"
        assert expected_code in {blocker.code for blocker in result.context.blockers}


def test_domain_factory_blocks_missing_runtime_values_without_fabricating_urls(
    tmp_path: Path,
) -> None:
    workspace = _baseline_workspace(tmp_path)
    (workspace / "release/preview-runtime.json").write_text("{}", encoding="utf-8")
    init_result = json.loads(
        (workspace / ".codex/factory/init-result.json").read_text(encoding="utf-8")
    )
    init_result["resources"]["cloudflarePreview"] = {}
    (workspace / ".codex/factory/init-result.json").write_text(
        json.dumps(init_result),
        encoding="utf-8",
    )
    repository = _repository(tmp_path)
    session = _session(workspace)
    repository.save_session(session)
    service = DomainFactoryService(
        projects_root=tmp_path / "projects",
        chat_repository=repository,
    )

    result = service.start(session_id=session.id)

    assert result.status == "blocked"
    assert result.context.api_url is None
    assert result.context.preview_url is None
    assert {
        "invalid_preview_runtime",
        "missing_runtime_profile",
        "missing_api_runtime",
        "missing_preview_api_url",
    }.issubset({blocker.code for blocker in result.context.blockers})


def test_domain_factory_blocks_invalid_runtime_and_api_url(
    tmp_path: Path,
) -> None:
    workspace = _baseline_workspace(tmp_path)
    (workspace / "release/preview-runtime.json").write_text(
        json.dumps(
            {
                "sourceApp": "clinica-norte",
                "previewUrl": "https://preview.nienfos.com/clinica-norte",
                "apiBaseUrl": "http://localhost:8000/api",
                "runtimeProfile": "demo",
                "apiRuntime": "local",
            }
        ),
        encoding="utf-8",
    )
    init_result = json.loads(
        (workspace / ".codex/factory/init-result.json").read_text(encoding="utf-8")
    )
    init_result["resources"]["cloudflarePreview"]["apiBaseUrl"] = (
        "http://localhost:8000/api"
    )
    (workspace / ".codex/factory/init-result.json").write_text(
        json.dumps(init_result),
        encoding="utf-8",
    )
    repository = _repository(tmp_path)
    session = _session(workspace)
    repository.save_session(session)
    service = DomainFactoryService(
        projects_root=tmp_path / "projects",
        chat_repository=repository,
    )

    result = service.start(session_id=session.id)

    assert result.status == "blocked"
    assert {
        "invalid_runtime_profile",
        "invalid_api_runtime",
        "invalid_preview_api_url",
    }.issubset({blocker.code for blocker in result.context.blockers})


def test_domain_factory_rejects_workspace_outside_projects_root(
    tmp_path: Path,
) -> None:
    workspace = _baseline_workspace(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    repository = _repository(tmp_path)
    session = _session(workspace)
    repository.save_session(session)
    service = DomainFactoryService(
        projects_root=tmp_path / "projects",
        chat_repository=repository,
    )

    try:
        service.start(session_id=session.id, workspace_path=str(outside))
    except ValueError as exc:
        assert "under PROJECTS_ROOT" in str(exc)
    else:
        raise AssertionError("Expected workspace validation to fail.")


def test_domain_factory_route_registered_on_root_and_api_v1() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}

    assert "/sessions/{session_id}/domain-factory/start" in paths
    assert "/api/v1/sessions/{session_id}/domain-factory/start" in paths
    assert "/sessions/{session_id}/domain-factory/intake" in paths
    assert "/sessions/{session_id}/domain-factory/implementation/confirm" in paths
    assert "/sessions/{session_id}/domain-factory/release-evidence" in paths


def test_domain_factory_persists_intake_media_and_contract_preview(
    tmp_path: Path,
) -> None:
    workspace = _baseline_workspace(tmp_path)
    repository = _repository(tmp_path)
    session = _session(workspace)
    repository.save_session(session)
    service = DomainFactoryService(
        projects_root=tmp_path / "projects",
        chat_repository=repository,
    )
    start = service.start(session_id=session.id)

    result = service.submit_intake(
        session_id=session.id,
        brief=(
            "Clinic staff and patients need appointments, payments, reports, "
            "inventory and a blue mobile dashboard."
        ),
        media_references=(
            {
                "id": "asset-1",
                "role": "visual_reference",
                "filename": "clinic-home.png",
                "assetId": "asset-1",
                "mimeType": "image/png",
                "sha256": "abc123",
                "path": "intake/assets/clinic-home.png",
            },
        ),
    )

    assert result.status == "implementation_ready"
    assert result.spec_root == start.spec_root
    spec_root = workspace / result.spec_root
    brief = (spec_root / "intake/original-brief.md").read_text(encoding="utf-8")
    media = json.loads(
        (spec_root / "intake/media-references.json").read_text(encoding="utf-8")
    )
    contract = json.loads(
        (spec_root / "contract-preview.json").read_text(encoding="utf-8")
    )
    assert "Clinic staff and patients" in brief
    assert media["items"][0]["assetId"] == "asset-1"
    assert contract["roles"]["owner"]["allAccess"] is True
    assert contract["roles"]["admin"]["permissions"] == ["*"]
    assert "patient" in contract["roles"]["domain"][0]["id"] or {
        role["id"] for role in contract["roles"]["domain"]
    } >= {"staff", "patient"}
    assert "appointment" in contract["entities"]
    assert contract["baselineFieldsAsked"] == []
    assert contract["releaseTarget"]["apiUrl"] == (
        "https://preview.nienfos.com/clinica-norte/api"
    )
    state = json.loads(
        (workspace / ".codex/factory/domain-factory-state.json").read_text(
            encoding="utf-8"
        )
    )
    assert state["modeStatus"] == "implementation_ready"
    assert state["contractPreviewPath"] == f"{result.spec_root}/contract-preview.json"
    messages = repository.list_messages(session.id)
    assert any(
        "Domain Factory contract preview is ready" in item.content for item in messages
    )


def test_domain_factory_confirm_implementation_writes_paired_workflow_evidence(
    tmp_path: Path,
) -> None:
    workspace = _baseline_workspace(tmp_path)
    repository = _repository(tmp_path)
    session = _session(workspace)
    repository.save_session(session)
    service = DomainFactoryService(
        projects_root=tmp_path / "projects",
        chat_repository=repository,
    )
    service.start(session_id=session.id)
    service.submit_intake(session_id=session.id, brief="Customers place orders.")

    result = service.confirm_implementation(session_id=session.id)

    assert result.status == "implementing"
    workflow = json.loads(
        (workspace / result.workflow_evidence_path).read_text(encoding="utf-8")
    )
    assert workflow["mode"] == "generator_reviewer_paired"
    assert workflow["reviewerFeedbackBecomesNextGeneratorPrompt"] is True
    updated = repository.get_session(session.id)
    assert updated is not None
    configuration = updated.agent_configuration.normalized()
    assert configuration.agents[AgentId.GENERATOR].enabled is True
    assert configuration.agents[AgentId.REVIEWER].enabled is True
    assert configuration.preset.value == "review"


def test_domain_factory_completion_evidence_blocks_until_required_files_exist(
    tmp_path: Path,
) -> None:
    workspace = _baseline_workspace(tmp_path)
    repository = _repository(tmp_path)
    session = _session(workspace)
    repository.save_session(session)
    service = DomainFactoryService(
        projects_root=tmp_path / "projects",
        chat_repository=repository,
    )
    start = service.start(session_id=session.id)

    blocked = service.validate_completion_evidence(session_id=session.id)

    assert blocked["canCompleteTasks"] is False
    assert blocked["missingEvidence"] == ["implementation", "validation", "release"]
    spec_root = workspace / start.spec_root
    for filename in (
        "implementation-evidence.json",
        "validation-evidence.json",
        "release-evidence.json",
    ):
        (spec_root / filename).write_text('{"ok": true}\n', encoding="utf-8")

    ready = service.validate_completion_evidence(session_id=session.id)

    assert ready["canCompleteTasks"] is True
    assert ready["missingEvidence"] == []


def test_domain_factory_release_evidence_validator_enforces_real_preview_release(
    tmp_path: Path,
) -> None:
    service = DomainFactoryService(
        projects_root=tmp_path / "projects",
        chat_repository=_repository(tmp_path),
    )

    invalid = service.validate_release_evidence(
        source_app="clinica-norte",
        evidence={
            "build": 1,
            "runtimeProfile": "demo",
            "apiRuntime": "local",
            "apiUrl": "http://localhost:8000/api",
            "commit": "abc",
        },
        initial_build=1,
    )
    assert invalid["ok"] is False
    assert {
        "release_build_not_incremented",
        "invalid_release_runtime_profile",
        "invalid_release_api_runtime",
        "invalid_release_api_url",
        "forbidden_release_default",
        "missing_release_evidence_field",
        "updater_previous_build_missing_new_build",
        "updater_new_build_has_pending_self_update",
    }.issubset({error["code"] for error in invalid["errors"]})

    valid = service.validate_release_evidence(
        source_app="clinica-norte",
        evidence={
            "build": 2,
            "runtimeProfile": "preview",
            "apiRuntime": "cloudflare_preview",
            "apiUrl": "https://preview.nienfos.com/clinica-norte/api",
            "commit": "abc",
            "tag": "android-preview-v0.1.1-build.2",
            "releaseUrl": "https://github.com/acme/clinica/releases/tag/android-preview-v0.1.1-build.2",
            "apkUrl": "https://github.com/acme/clinica/releases/download/android-preview-v0.1.1-build.2/app.apk",
            "sha256": "f" * 64,
            "previewUrl": "https://preview.nienfos.com/clinica-norte",
            "smokeResults": "passed",
            "bridgeRegistryPayload": "registered",
            "rollbackPointer": "android-preview-v0.1.0-build.1",
            "updaterVerification": {
                "previousBuildSeesNewBuild": True,
                "newBuildHasPendingSelfUpdate": False,
            },
        },
        initial_build=1,
    )
    assert valid["ok"] is True
    assert valid["errors"] == []


def test_domain_factory_persists_valid_release_evidence_and_state(
    tmp_path: Path,
) -> None:
    workspace = _baseline_workspace(tmp_path)
    repository = _repository(tmp_path)
    session = _session(workspace)
    repository.save_session(session)
    service = DomainFactoryService(
        projects_root=tmp_path / "projects",
        chat_repository=repository,
    )
    start = service.start(session_id=session.id)

    evidence = {
        "build": 2,
        "runtimeProfile": "preview",
        "apiRuntime": "cloudflare_preview",
        "apiUrl": "https://preview.nienfos.com/clinica-norte/api",
        "commit": "def456",
        "tag": "android-preview-v0.1.1-build.2",
        "releaseUrl": "https://github.com/acme/clinica/releases/tag/android-preview-v0.1.1-build.2",
        "apkUrl": "https://github.com/acme/clinica/releases/download/android-preview-v0.1.1-build.2/app.apk",
        "sha256": "f" * 64,
        "previewUrl": "https://preview.nienfos.com/clinica-norte",
        "smokeResults": {"status": "passed"},
        "bridgeRegistryPayload": {"source_app": "clinica-norte", "build": 2},
        "rollbackPointer": "android-preview-v0.1.0-build.1",
        "updaterVerification": {
            "previousBuildSeesNewBuild": True,
            "newBuildHasPendingSelfUpdate": False,
        },
    }

    result = service.persist_release_evidence(
        session_id=session.id,
        evidence=evidence,
        initial_build=1,
    )

    assert result["ok"] is True
    assert result["status"] == "ready"
    assert result["releaseEvidencePath"] == f"{start.spec_root}/release-evidence.json"
    release = json.loads(
        (workspace / result["releaseEvidencePath"]).read_text(encoding="utf-8")
    )
    assert release["evidence"]["commit"] == "def456"
    assert release["updaterVerification"]["previousBuildSeesNewBuild"] is True
    assert release["updaterVerification"]["newBuildHasPendingSelfUpdate"] is False
    state = json.loads(
        (workspace / ".codex/factory/domain-factory-state.json").read_text(
            encoding="utf-8"
        )
    )
    assert state["modeStatus"] == "release_evidence_ready"
    assert state["releaseEvidencePath"] == result["releaseEvidencePath"]
    completion = service.validate_completion_evidence(session_id=session.id)
    assert completion["missingEvidence"] == ["implementation", "validation"]


def _repository(tmp_path: Path) -> InMemoryChatRepository:
    return InMemoryChatRepository(projects_root=str(tmp_path / "projects"))


class _CountingExecutionProvider(ExecutionProvider):
    def __init__(self) -> None:
        self.execute_count = 0

    def execute(
        self,
        message: str,
        *,
        image_paths: list[str] | None = None,
        cleanup_paths: list[str] | None = None,
        provider_session_id: str | None = None,
        model: str | None = None,
        codex_options: CodexRunOptions | None = None,
        serial_key: str | None = None,
        submission_token: str | None = None,
        workdir: str | None = None,
    ) -> str:
        self.execute_count += 1
        return f"job-{self.execute_count}"

    def get_status(self, job_id: str) -> JobStatus:
        return JobStatus.COMPLETED

    def get_result(self, job_id: str) -> str | None:
        return "completed"

    def get_error(self, job_id: str) -> str | None:
        return None

    def get_provider_session_id(self, job_id: str) -> str | None:
        return None

    def get_phase(self, job_id: str) -> str | None:
        return "Completed"

    def get_latest_activity(self, job_id: str) -> str | None:
        return "Completed"


def _session(workspace: Path) -> ChatSession:
    return ChatSession(
        id="session-1",
        title="Clinica Norte",
        workspace_path=str(workspace),
        workspace_name=workspace.name,
    )


def _baseline_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "projects" / "clinica-norte"
    (workspace / ".codex/factory").mkdir(parents=True)
    (workspace / ".codex").mkdir(exist_ok=True)
    (workspace / "release").mkdir()
    (workspace / "specs/001-baseline").mkdir(parents=True)
    (workspace / "codex-bridge.yaml").write_text(
        "source_app: clinica-norte\ndisplay_name: Clinica Norte\n",
        encoding="utf-8",
    )
    (workspace / ".codex/project.yaml").write_text(
        "source_app: clinica-norte\nname: Clinica Norte\n",
        encoding="utf-8",
    )
    (workspace / "release/preview-runtime.json").write_text(
        json.dumps(
            {
                "sourceApp": "clinica-norte",
                "previewUrl": "https://preview.nienfos.com/clinica-norte",
                "apiBaseUrl": "https://preview.nienfos.com/clinica-norte/api",
                "runtimeProfile": "preview",
                "apiRuntime": "cloudflare_preview",
            }
        ),
        encoding="utf-8",
    )
    (workspace / ".codex/factory/init-result.json").write_text(
        json.dumps(
            {
                "kind": "codex.projectFactoryInitResult",
                "sourceApp": "clinica-norte",
                "displayName": "Clinica Norte",
                "workspacePath": str(workspace),
                "readyForBusinessLlm": True,
                "blockedWithContext": False,
                "baselineCommit": "abc123",
                "resources": {
                    "cloudflarePreview": {
                        "previewUrl": "https://preview.nienfos.com/clinica-norte",
                        "apiBaseUrl": "https://preview.nienfos.com/clinica-norte/api",
                    },
                    "androidPreviewRelease": {
                        "releaseTag": "android-preview-v0.1.0-build.1",
                        "buildNumber": 1,
                    },
                    "bridgeInstallable": {"sourceApp": "clinica-norte"},
                },
            }
        ),
        encoding="utf-8",
    )
    (workspace / ".codex/factory/llm-start-context.md").write_text(
        "# Deterministic Init Context\n\nDo not recreate GitHub or Cloudflare.",
        encoding="utf-8",
    )
    (workspace / "specs/001-baseline/spec.md").write_text(
        "# Baseline\n\nInitialized deterministic baseline.",
        encoding="utf-8",
    )
    return workspace
