from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest
import yaml

import backend.app.application.services.project_scaffold_providers as provider_module
from backend.app.application.services.domain_factory_service import DomainFactoryService
from backend.app.application.services.project_scaffold_service import (
    ProjectScaffoldService,
    ScaffoldDraftInput,
    ScaffoldCommandResult,
    ScaffoldError,
)
from backend.app.domain.entities.agent_configuration import AgentId
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.project_scaffold import (
    AwsReadinessMode,
    CloudflareMode,
    ScaffoldLifecycleState,
)
from backend.app.infrastructure.persistence.in_memory_chat_repository import (
    InMemoryChatRepository,
)


def _service(tmp_path: Path) -> ProjectScaffoldService:
    projects = tmp_path / "projects"
    projects.mkdir()
    return ProjectScaffoldService(
        projects_root=projects,
        state_root=tmp_path / "state",
        execute_commands=False,
        allow_remote_writes=False,
    )


def _run(
    service: ProjectScaffoldService,
    *,
    name: str = "Composable",
    preset: str = "expo-sveltekit-fastapi",
    github_mode: str = "disabled",
    cloudflare: CloudflareMode = CloudflareMode.GENERATE_ONLY,
    aws: AwsReadinessMode = AwsReadinessMode.TERRAFORM_READY,
):
    draft = service.create_draft(
        ScaffoldDraftInput(
            name=name,
            stack_preset=preset,
            github_mode=github_mode,
            cloudflare_mode=cloudflare,
            aws_mode=aws,
        )
    )
    service.confirm_draft(draft.id, draft.contract_hash)
    job = service.start_or_resume(draft.id)
    return draft, service.run(job.id)


def test_scaffold_intake_contract_is_minimal_and_explicit(tmp_path: Path) -> None:
    service = _service(tmp_path)

    draft = service.create_draft(
        ScaffoldDraftInput(
            name="Neutral",
            github_mode="disabled",
            cloudflare_mode=CloudflareMode.DISABLED,
        )
    )

    payload = draft.to_payload()
    assert payload["creationMode"] == "scaffold"
    assert set(payload["request"]) == {
        "name",
        "slug",
        "stackPreset",
        "mobileProvider",
        "webProvider",
        "apiProvider",
        "cloudflareMode",
        "awsReadinessMode",
        "githubOwner",
        "githubVisibility",
        "githubMode",
        "previewProtected",
        "initialAdminEmail",
    }
    forbidden_questions = {
        "businessType",
        "entities",
        "roles",
        "workflows",
        "screens",
        "navigation",
        "colors",
        "logo",
        "ux",
    }
    assert forbidden_questions.isdisjoint(payload["request"])
    assert payload["contractPreview"]["publishAndroid"] is False
    assert payload["contractPreview"]["startDomainFactory"] is False
    assert payload["manifest"]["infrastructure"]["web_edge"]["d1"] is False


def test_expo_sveltekit_fastapi_scaffold_generates_neutral_baseline(tmp_path: Path) -> None:
    service = _service(tmp_path)

    draft, job = _run(service)

    workspace = Path(job.workspace_path)
    assert job.lifecycle_state is ScaffoldLifecycleState.SCAFFOLD_BLOCKED_WITH_CONTEXT
    assert (workspace / "apps/mobile/app/index.tsx").is_file()
    assert (workspace / "apps/web/src/routes/+page.svelte").is_file()
    assert (workspace / "services/api/app/main.py").is_file()
    requirements_lock = (workspace / "services/api/requirements.lock").read_text(
        encoding="utf-8"
    )
    assert "pydantic-core==" in requirements_lock
    assert all(
        "==" in line
        for line in requirements_lock.splitlines()
        if line.strip()
    )
    assert "pip install --no-cache-dir --no-deps" in (
        workspace / "services/api/Dockerfile"
    ).read_text(encoding="utf-8")
    assert (workspace / "contracts/openapi.yaml").is_file()
    runtime_schema = json.loads(
        (workspace / "contracts/runtime.schema.json").read_text(encoding="utf-8")
    )
    assert runtime_schema["properties"]["runtime_profile"]["enum"] == [
        "preview",
        "staging",
        "real",
        "mock",
    ]
    assert "scaffold" not in runtime_schema["properties"]["runtime_profile"]["enum"]
    assert (workspace / "packages/codex-bridge-react-native/src/index.ts").is_file()
    bridge_adapter = (
        workspace / "packages/codex-bridge-react-native/src/index.ts"
    ).read_text(encoding="utf-8")
    assert "FeedbackStorage" in bridge_adapter
    assert "captureFeedback" in bridge_adapter
    assert "audio?()" in bridge_adapter
    assert "releaseWhenComplete" in bridge_adapter
    assert "workbenchDeepLink" in bridge_adapter
    assert "/sdd/workbench/view?workspace_path=" in bridge_adapter
    assert "/workbench/${" not in bridge_adapter
    assert "verifyChecksum" in bridge_adapter
    assert "AndroidInstaller" in bridge_adapter
    assert "crypto.subtle" not in bridge_adapter
    signing_plugin = (
        workspace / "apps/mobile/plugins/with-preview-signing.js"
    ).read_text(encoding="utf-8")
    assert "signingConfigs.release" in signing_plugin
    release_workflow = (
        workspace / ".github/workflows/android-preview-release.yml"
    ).read_text(encoding="utf-8")
    assert isinstance(yaml.safe_load(release_workflow), dict)
    assert "assembleRelease" in release_workflow
    assert "ANDROID_KEYSTORE_BASE64" in release_workflow
    assert "gh release create" in release_workflow
    assert "API_BASE_URL must be a real HTTPS endpoint" in release_workflow
    assert "local or placeholder API is forbidden" in release_workflow
    assert "apksigner" in release_workflow
    assert "aapt" in release_workflow
    assert "Android Debug" in release_workflow
    assert "sha256sum" in release_workflow
    assert release_workflow.index("apksigner") < release_workflow.index(
        "gh release create"
    )
    validation_workflow = yaml.safe_load(
        (workspace / ".github/workflows/scaffold-validation.yml").read_text()
    )
    validation_steps = validation_workflow["jobs"]["targets"]["steps"]
    assert any(item.get("uses") == "actions/setup-node@v4" for item in validation_steps)
    assert any(item.get("uses") == "actions/setup-python@v5" for item in validation_steps)
    assert any(item.get("run") == "npm ci" for item in validation_steps)
    assert any("pytest" in item.get("run", "") for item in validation_steps)
    manifest = yaml.safe_load((workspace / ".codex/project.yaml").read_text())
    assert manifest["schema_version"] == 2
    assert manifest["creation"]["mode"] == "scaffold"
    assert manifest["targets"]["mobile"]["provider"] == "react_native_expo"
    assert manifest["targets"]["web"]["provider"] == "sveltekit"
    assert manifest["targets"]["api"]["provider"] == "fastapi"
    assert manifest["lifecycle"] == {
        "state": "scaffold_blocked_with_context",
        "next_action": "retry_scaffold",
    }
    result = json.loads(
        (workspace / ".codex/factory/scaffold-result.json").read_text()
    )
    assert result["android"] == {
        "installableRegistered": False,
        "publishDuringScaffold": False,
    }
    assert result["cloudflare"]["d1"] is False
    assert any(
        item["code"] == "local_validation_not_executed"
        for item in result["blockers"]
    )
    api_plan = next(
        item
        for item in job.provider_results
        if item["target_kind"] == "api"
        and item["provider_id"] == "fastapi"
        and item["commands"]
    )
    assert ["python3", "-m", "venv", ".venv"] in api_plan["commands"]
    assert [".venv/bin/python", "-m", "pytest", "-q"] in api_plan["commands"]
    assert ["python3", "-m", "pytest", "-q"] not in api_plan["commands"]
    assert draft.contract_hash


def test_flutter_runtime_reads_logical_environment_without_scaffold_profile(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    _, job = _run(
        service,
        preset="flutter-sveltekit-go",
        cloudflare=CloudflareMode.DISABLED,
        aws=AwsReadinessMode.NONE,
    )
    main = Path(job.workspace_path, "apps/mobile/lib/main.dart").read_text(
        encoding="utf-8"
    )

    assert "String.fromEnvironment('SOURCE_APP'" in main
    assert "String.fromEnvironment('APP_RUNTIME_PROFILE'" in main
    assert "String.fromEnvironment('API_BASE_URL'" in main
    assert "defaultValue: 'preview'" in main
    assert "defaultValue: 'scaffold'" not in main


def test_go_provider_is_real_go_and_emits_no_fastapi_files(tmp_path: Path) -> None:
    service = _service(tmp_path)

    _, job = _run(service, preset="expo-sveltekit-go")

    workspace = Path(job.workspace_path)
    assert job.lifecycle_state is ScaffoldLifecycleState.SCAFFOLD_BLOCKED_WITH_CONTEXT
    assert (workspace / "services/api/go.mod").is_file()
    assert (workspace / "services/api/cmd/server/main.go").is_file()
    assert not (workspace / "services/api/app/main.py").exists()
    commands = json.dumps(job.to_payload()["providerResults"])
    assert "go test ./..." not in commands  # commands are structured argv
    assert '"go", "test", "./..."' in commands
    assert "pytest" not in commands


def test_flutter_sveltekit_go_matrix_uses_independent_targets(tmp_path: Path) -> None:
    service = _service(tmp_path)

    _, job = _run(service, preset="flutter-sveltekit-go")

    workspace = Path(job.workspace_path)
    assert job.lifecycle_state is ScaffoldLifecycleState.SCAFFOLD_BLOCKED_WITH_CONTEXT
    assert (workspace / "apps/mobile/pubspec.yaml").is_file()
    assert (workspace / "apps/web/package.json").is_file()
    assert (workspace / "services/api/go.mod").is_file()
    assert not (workspace / "services/api/app/main.py").exists()
    commands = json.dumps(job.to_payload()["providerResults"])
    assert '"--platforms=android,ios"' in commands
    workflow = (workspace / ".github/workflows/scaffold-validation.yml").read_text()
    assert "subosito/flutter-action@v2" in workflow
    assert "actions/setup-node@v4" in workflow
    assert "actions/setup-go@v5" in workflow
    build_script = (workspace / "scripts/build_targets.sh").read_text()
    assert "flutter build apk --debug" in build_script
    assert "flutter build web" not in build_script.split("apps/mobile")[1].split(")")[0]


def test_flutter_web_is_independent_from_react_native_mobile(tmp_path: Path) -> None:
    service = _service(tmp_path)
    draft = service.create_draft(
        ScaffoldDraftInput(
            name="Mixed Flutter Web",
            stack_preset=None,
            mobile_provider="react_native_expo",
            web_provider="flutter_web",
            api_provider="none",
            github_mode="disabled",
            cloudflare_mode=CloudflareMode.GENERATE_ONLY,
        )
    )
    service.confirm_draft(draft.id, draft.contract_hash)

    job = service.run(service.start_or_resume(draft.id).id)
    workspace = Path(job.workspace_path)

    assert job.lifecycle_state is ScaffoldLifecycleState.SCAFFOLD_BLOCKED_WITH_CONTEXT
    assert (workspace / "apps/mobile/package.json").is_file()
    assert (workspace / "apps/web/pubspec.yaml").is_file()
    cloudflare = (workspace / "infra/cloudflare/wrangler.toml").read_text()
    assert 'directory = "../../apps/web/build/web"' in cloudflare
    assets_path = workspace / "infra/cloudflare" / "../../apps/web/build/web"
    assert assets_path.resolve() == (workspace / "apps/web/build/web").resolve()


def test_numeric_slugs_generate_valid_mobile_package_identifiers(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _, expo_job = _run(
        service,
        name="123 Technical",
        cloudflare=CloudflareMode.DISABLED,
        aws=AwsReadinessMode.NONE,
    )
    flutter_draft = service.create_draft(
        ScaffoldDraftInput(
            name="456 Technical",
            stack_preset=None,
            mobile_provider="flutter",
            web_provider="none",
            api_provider="none",
            github_mode="disabled",
            cloudflare_mode=CloudflareMode.DISABLED,
        )
    )
    service.confirm_draft(flutter_draft.id, flutter_draft.contract_hash)
    flutter_job = service.run(service.start_or_resume(flutter_draft.id).id)

    expo_app = json.loads(
        Path(expo_job.workspace_path, "apps/mobile/app.json").read_text()
    )
    flutter_pubspec = yaml.safe_load(
        Path(flutter_job.workspace_path, "apps/mobile/pubspec.yaml").read_text()
    )

    assert expo_app["expo"]["android"]["package"] == "com.nienfos.app123technical"
    assert flutter_pubspec["name"] == "app_456_technical"


def test_web_only_scaffold_has_no_mobile_or_android_claim(tmp_path: Path) -> None:
    service = _service(tmp_path)

    _, job = _run(service, preset="sveltekit-go-web-only")

    workspace = Path(job.workspace_path)
    assert not (workspace / "apps/mobile").exists()
    assert (workspace / "apps/web").is_dir()
    assert job.result is not None
    assert job.result["android"]["publishDuringScaffold"] is False
    assert job.result["android"]["installableRegistered"] is False


def test_generate_only_and_terraform_ready_have_no_remote_or_apply_commands(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)

    _, job = _run(service)

    workspace = Path(job.workspace_path)
    cloudflare = job.phase("cloudflare_scaffold")
    aws = job.phase("aws_readiness")
    assert cloudflare.status == "completed"
    assert cloudflare.evidence[0]["mode"] == "generate_only"
    assert "remoteWrite" not in cloudflare.evidence[0]
    assert aws.evidence[0]["resourcesCreated"] == 0
    assert aws.evidence[0]["terraformApply"] is False
    assert "resource \"" not in (workspace / "infra/aws/main.tf").read_text()
    assert "terraform apply" not in json.dumps(aws.to_payload()).lower()


def test_post_commit_infrastructure_evidence_is_tracked_and_workspace_is_clean(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    service = ProjectScaffoldService(
        projects_root=projects,
        state_root=tmp_path / "state",
        execute_commands=True,
        allow_remote_writes=False,
    )
    draft = service.create_draft(
        ScaffoldDraftInput(
            name="Clean Infra Evidence",
            stack_preset=None,
            mobile_provider="none",
            web_provider="none",
            api_provider="none",
            github_mode="disabled",
            cloudflare_mode=CloudflareMode.GENERATE_ONLY,
            aws_mode=AwsReadinessMode.ARCHITECTURE_DOCS_ONLY,
        )
    )
    service.confirm_draft(draft.id, draft.contract_hash)

    job = service.run(service.start_or_resume(draft.id).id)
    workspace = Path(job.workspace_path)

    assert job.lifecycle_state is ScaffoldLifecycleState.SCAFFOLD_READY
    status = subprocess.run(
        ("git", "status", "--porcelain"),
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    tracked = subprocess.run(
        ("git", "ls-files"),
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert status.stdout == ""
    assert "infra/cloudflare/wrangler.toml" in tracked
    assert "infra/aws/architecture-decisions.md" in tracked


def test_remote_blocker_preserves_local_scaffold_and_restart_recovery(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)

    draft, job = _run(service, name="Needs GitHub", github_mode="create_or_verify")

    assert job.lifecycle_state is ScaffoldLifecycleState.SCAFFOLD_BLOCKED_WITH_CONTEXT
    assert Path(job.workspace_path, "apps/mobile/app/index.tsx").is_file()
    assert any(item["code"] == "github_owner_missing" for item in job.to_payload()["blockers"])
    restored = ProjectScaffoldService(
        projects_root=tmp_path / "projects",
        state_root=tmp_path / "state",
        execute_commands=False,
        allow_remote_writes=False,
    )
    recovered = restored.get_job(job.id)
    assert recovered is not None
    assert recovered.lifecycle_state is ScaffoldLifecycleState.SCAFFOLD_BLOCKED_WITH_CONTEXT
    assert restored.start_or_resume(draft.id).id == job.id


def test_requested_remote_writes_are_not_reported_ready_when_disabled(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    draft = service.create_draft(
        ScaffoldDraftInput(
            name="Remote Pending",
            github_owner="owner",
            github_mode="create_or_verify",
            cloudflare_mode=CloudflareMode.PROVISION_SCAFFOLD,
            aws_mode=AwsReadinessMode.NONE,
        )
    )
    service.confirm_draft(draft.id, draft.contract_hash)

    job = service.run(service.start_or_resume(draft.id).id)
    codes = {item["code"] for item in job.to_payload()["blockers"]}

    assert job.lifecycle_state is ScaffoldLifecycleState.SCAFFOLD_BLOCKED_WITH_CONTEXT
    assert "github_remote_write_not_executed" in codes
    assert "cloudflare_remote_write_not_executed" in codes
    assert Path(job.workspace_path, ".codex/factory/scaffold-context.md").is_file()


def test_start_product_is_explicit_idempotent_and_reuses_workspace(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    service = ProjectScaffoldService(
        projects_root=projects,
        state_root=tmp_path / "state",
        command_runner=_ArtifactRunner(),
        execute_commands=True,
        allow_remote_writes=False,
    )
    draft = service.create_draft(
        ScaffoldDraftInput(
            name="Composable",
            stack_preset=None,
            mobile_provider="none",
            web_provider="none",
            api_provider="none",
            github_mode="disabled",
            cloudflare_mode=CloudflareMode.DISABLED,
            aws_mode=AwsReadinessMode.NONE,
        )
    )
    service.confirm_draft(draft.id, draft.contract_hash)
    job = service.run(service.start_or_resume(draft.id).id)
    assert job.lifecycle_state is ScaffoldLifecycleState.SCAFFOLD_READY

    started = service.start_product(job.id, session_id="session-1")
    repeated = service.start_product(job.id, session_id="session-1")

    assert started.lifecycle_state is ScaffoldLifecycleState.SCAFFOLD_READY
    assert repeated.domain_factory_relationship == started.domain_factory_relationship
    assert started.domain_factory_relationship["status"] == "domain_intake"
    assert started.domain_factory_relationship["workspacePath"] == job.workspace_path
    assert all(started.domain_factory_relationship["reuse"].values())
    assert started.to_payload()["canStartProduct"] is False
    assert started.result["startProductAvailable"] is False
    manifest = yaml.safe_load(
        Path(job.workspace_path, ".codex/project.yaml").read_text(encoding="utf-8")
    )
    assert manifest["creation"]["mode"] == "scaffold"
    assert manifest["lifecycle"]["state"] == "domain_intake"

    rolled_back = service.rollback_product_start(
        job.id,
        session_id="session-1",
    )
    restored_manifest = yaml.safe_load(
        Path(job.workspace_path, ".codex/project.yaml").read_text(encoding="utf-8")
    )
    assert rolled_back.domain_factory_relationship is None
    assert rolled_back.result["startProductAvailable"] is True
    assert restored_manifest["lifecycle"] == {
        "state": "scaffold_ready",
        "next_action": "start_product",
    }


def test_start_product_rejects_non_terminal_scaffold(tmp_path: Path) -> None:
    service = _service(tmp_path)
    draft = service.create_draft(
        ScaffoldDraftInput(name="Not Ready", github_mode="disabled")
    )
    service.confirm_draft(draft.id, draft.contract_hash)
    job = service.start_or_resume(draft.id)

    with pytest.raises(ScaffoldError, match="scaffold_ready"):
        service.start_product(job.id, session_id="session-too-early")


def test_start_product_rejects_blocked_scaffold_without_starting_domain(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    _, job = _run(service)
    assert job.lifecycle_state is ScaffoldLifecycleState.SCAFFOLD_BLOCKED_WITH_CONTEXT
    assert job.to_payload()["canStartProduct"] is False
    assert job.result is not None
    assert job.result["startProductAvailable"] is False
    manifest = yaml.safe_load(
        Path(job.workspace_path, ".codex/project.yaml").read_text(encoding="utf-8")
    )
    assert manifest["lifecycle"]["next_action"] == "retry_scaffold"

    with pytest.raises(ScaffoldError, match="scaffold_ready"):
        service.start_product(job.id, session_id="blocked-session")


def test_domain_factory_consumes_v2_scaffold_context_without_v1_preview(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    scaffold = ProjectScaffoldService(
        projects_root=projects,
        state_root=tmp_path / "state",
        execute_commands=True,
        allow_remote_writes=False,
    )
    draft = scaffold.create_draft(
        ScaffoldDraftInput(
            name="Composable",
            stack_preset=None,
            mobile_provider="none",
            web_provider="none",
            api_provider="none",
            github_mode="disabled",
            cloudflare_mode=CloudflareMode.DISABLED,
            aws_mode=AwsReadinessMode.NONE,
        )
    )
    scaffold.confirm_draft(draft.id, draft.contract_hash)
    job = scaffold.run(scaffold.start_or_resume(draft.id).id)
    assert job.lifecycle_state is ScaffoldLifecycleState.SCAFFOLD_READY
    repository = InMemoryChatRepository(projects_root=str(tmp_path / "projects"))
    session = ChatSession(
        id="scaffold-session",
        title="Composable",
        workspace_path=job.workspace_path,
        workspace_name=Path(job.workspace_path).name,
    )
    repository.save_session(session)
    domain = DomainFactoryService(
        projects_root=tmp_path / "projects",
        chat_repository=repository,
    )

    context = domain.build_context(session_id=session.id)
    started = domain.start(session_id=session.id)

    assert context.creation_mode == "scaffold"
    assert context.source_app == "composable"
    assert context.preview_url is None
    assert context.api_url is None
    assert context.blockers == ()
    assert context.scaffold_result["pendingProduct"]
    assert started.status == "ready"
    configured = repository.get_session(session.id)
    assert configured is not None
    prompt = configured.agent_configuration.normalized().agents[AgentId.GENERATOR].prompt
    assert "intentionally has no product foundation" in prompt
    assert "selected target providers" in prompt
    assert "Scaffold did not publish or register an APK" in prompt


def test_domain_factory_direct_entry_rejects_blocked_scaffold_context(
    tmp_path: Path,
) -> None:
    scaffold = _service(tmp_path)
    _, job = _run(scaffold)
    assert job.lifecycle_state is ScaffoldLifecycleState.SCAFFOLD_BLOCKED_WITH_CONTEXT
    repository = InMemoryChatRepository(projects_root=str(tmp_path / "projects"))
    session = ChatSession(
        id="blocked-scaffold-session",
        title="Blocked composable",
        workspace_path=job.workspace_path,
        workspace_name=Path(job.workspace_path).name,
    )
    repository.save_session(session)
    domain = DomainFactoryService(
        projects_root=tmp_path / "projects",
        chat_repository=repository,
    )

    context = domain.build_context(session_id=session.id)
    started = domain.start(session_id=session.id)

    assert {item.code for item in context.blockers} == {"scaffold_not_terminal"}
    assert started.status == "blocked"
    unchanged = repository.get_session(session.id)
    assert unchanged is not None
    assert unchanged.agent_profile_id != "domain-factory"


class _RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv, *, cwd, env=None, timeout_seconds=0):
        del env, timeout_seconds
        command = tuple(argv)
        self.calls.append(command)
        return ScaffoldCommandResult(
            command=command,
            exit_code=0,
            stdout=(
                "https://example.invalid/scaffold"
                if command[:2] == ("wrangler", "deploy")
                else ""
            ),
        )


class _ArtifactRunner(_RecordingRunner):
    def run(self, argv, *, cwd, env=None, timeout_seconds=0):
        del env, timeout_seconds
        command = tuple(argv)
        self.calls.append(command)
        if command[:2] == ("npm", "install"):
            (cwd / "package-lock.json").write_text("{}\n", encoding="utf-8")
        if command[:3] == ("npm", "run", "prebuild:android"):
            gradlew = cwd / "android/gradlew"
            gradlew.parent.mkdir(parents=True, exist_ok=True)
            gradlew.write_text("#!/usr/bin/env sh\n", encoding="utf-8")
        if command and command[0] == "./android/gradlew":
            apk = cwd / "android/app/build/outputs/apk/debug/app-debug.apk"
            apk.parent.mkdir(parents=True, exist_ok=True)
            apk.write_bytes(b"normalized-debug-apk")
        if command[:3] == ("npm", "run", "build") and cwd.name == "web":
            (cwd / ".svelte-kit/cloudflare").mkdir(parents=True, exist_ok=True)
        if command[:2] == ("git", "init"):
            (cwd / ".git").mkdir(parents=True, exist_ok=True)
        if command[:3] == ("gh", "repo", "view"):
            return ScaffoldCommandResult(command=command, exit_code=1, stderr="not found")
        return ScaffoldCommandResult(
            command=command,
            exit_code=0,
            stdout=(
                "https://example.invalid/scaffold"
                if command[:2] == ("wrangler", "deploy")
                else ""
            ),
        )


class _FailOnceArtifactRunner(_ArtifactRunner):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    def run(self, argv, *, cwd, env=None, timeout_seconds=0):
        command = tuple(argv)
        if command[:2] == ("npm", "install") and not self.failed:
            self.failed = True
            self.calls.append(command)
            return ScaffoldCommandResult(
                command=command,
                exit_code=1,
                stderr="temporary package registry failure",
            )
        return super().run(
            argv,
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
        )


class _FailValidationOnceRunner(_ArtifactRunner):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    def run(self, argv, *, cwd, env=None, timeout_seconds=0):
        command = tuple(argv)
        if command[:2] == ("npm", "ci") and not self.failed:
            self.failed = True
            self.calls.append(command)
            return ScaffoldCommandResult(
                command=command,
                exit_code=1,
                stderr="temporary validation failure",
            )
        return super().run(
            argv,
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
        )


def test_full_expo_sveltekit_fastapi_e2e_with_remote_fakes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provider_module.shutil,
        "which",
        lambda name: f"/fake-tools/{name}",
    )
    monkeypatch.setattr(provider_module, "_tool_version", lambda _: "99.0.0")
    projects = tmp_path / "projects"
    projects.mkdir()
    runner = _ArtifactRunner()
    service = ProjectScaffoldService(
        projects_root=projects,
        state_root=tmp_path / "state",
        command_runner=runner,
        execute_commands=True,
        allow_remote_writes=True,
    )
    draft = service.create_draft(
        ScaffoldDraftInput(
            name="Complete Fake E2E",
            github_owner="owner",
            github_mode="create_or_verify",
            cloudflare_mode=CloudflareMode.PROVISION_SCAFFOLD,
            aws_mode=AwsReadinessMode.ARCHITECTURE_DOCS_ONLY,
        )
    )
    service.confirm_draft(draft.id, draft.contract_hash)

    job = service.run(service.start_or_resume(draft.id).id)

    assert job.lifecycle_state is ScaffoldLifecycleState.SCAFFOLD_READY
    assert job.to_payload()["blockers"] == []
    assert {item["kind"] for item in job.resources} == {
        "cloudflare_scaffold",
        "github_repository",
        "workbench_scope",
    }
    assert all(
        item["status"] == "locally_verified"
        for item in job.provider_results
        if item["target_kind"] in {"mobile", "web", "api"}
        and item["commands"]
        and item["status"] != "prepared"
    )
    assert job.result["workbench"]["ownedBy"] == "codex_mobile_bridge"
    assert job.result["cloudflare"]["d1"] is False
    assert Path(job.workspace_path, ".codex/factory/scaffold-context.md").is_file()


def test_cloudflare_provision_is_project_scoped_and_idempotent(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    runner = _ArtifactRunner()
    service = ProjectScaffoldService(
        projects_root=projects,
        state_root=tmp_path / "state",
        command_runner=runner,
        execute_commands=True,
        allow_remote_writes=True,
    )
    draft = service.create_draft(
        ScaffoldDraftInput(
            name="Infra Only",
            stack_preset=None,
            mobile_provider="none",
            web_provider="none",
            api_provider="none",
            github_mode="disabled",
            cloudflare_mode=CloudflareMode.PROVISION_SCAFFOLD,
            aws_mode=AwsReadinessMode.NONE,
        )
    )
    service.confirm_draft(draft.id, draft.contract_hash)
    first = service.run(service.start_or_resume(draft.id).id)
    second = service.run(first.id)

    deploys = [call for call in runner.calls if call[:2] == ("wrangler", "deploy")]
    assert deploys == [
        (
            "wrangler",
            "deploy",
            "--config",
            "infra/cloudflare/wrangler.toml",
        )
    ]
    assert first.result is not None
    assert first.result["cloudflare"]["d1"] is False
    assert second.resources == first.resources


def test_protected_scaffold_never_falls_back_to_public_cloudflare_deploy(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    runner = _ArtifactRunner()
    service = ProjectScaffoldService(
        projects_root=projects,
        state_root=tmp_path / "state",
        command_runner=runner,
        execute_commands=True,
        allow_remote_writes=True,
    )
    draft = service.create_draft(
        ScaffoldDraftInput(
            name="Protected Neutral",
            stack_preset=None,
            mobile_provider="none",
            web_provider="none",
            api_provider="none",
            github_mode="disabled",
            cloudflare_mode=CloudflareMode.PROVISION_SCAFFOLD,
            preview_protected=True,
            initial_admin_email="owner@example.org",
        )
    )
    service.confirm_draft(draft.id, draft.contract_hash)

    job = service.run(service.start_or_resume(draft.id).id)

    assert job.lifecycle_state is ScaffoldLifecycleState.SCAFFOLD_BLOCKED_WITH_CONTEXT
    assert any(
        item["code"] == "protected_preview_access_not_configured"
        for item in job.to_payload()["blockers"]
    )
    assert not any(call[:2] == ("wrangler", "deploy") for call in runner.calls)
    assert {item["kind"] for item in job.resources} == {"workbench_scope"}


def test_failed_bootstrap_blocks_validation_and_remote_effects_then_retry_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_module.shutil, "which", lambda name: f"/fake/{name}")
    monkeypatch.setattr(provider_module, "_tool_version", lambda _: "99.0.0")
    projects = tmp_path / "projects"
    projects.mkdir()
    runner = _FailOnceArtifactRunner()
    service = ProjectScaffoldService(
        projects_root=projects,
        state_root=tmp_path / "state",
        command_runner=runner,
        execute_commands=True,
        allow_remote_writes=True,
    )
    draft = service.create_draft(
        ScaffoldDraftInput(
            name="Retryable",
            github_owner="owner",
            github_mode="create_or_verify",
            cloudflare_mode=CloudflareMode.PROVISION_SCAFFOLD,
            aws_mode=AwsReadinessMode.ARCHITECTURE_DOCS_ONLY,
        )
    )
    service.confirm_draft(draft.id, draft.contract_hash)

    failed = service.run(service.start_or_resume(draft.id).id)

    assert failed.phase("target_bootstrap").status == "blocked"
    assert failed.phase("target_validation").status == "blocked"
    assert failed.phase("local_git_commit").status == "blocked"
    assert failed.phase("github_repository").status == "blocked"
    assert failed.phase("cloudflare_scaffold").status == "blocked"
    assert not any(call[:3] == ("gh", "repo", "create") for call in runner.calls)
    assert not any(call[:2] == ("wrangler", "deploy") for call in runner.calls)
    assert failed.result is not None

    reset = service.retry(failed.id)
    assert reset.result is None
    assert reset.phase("target_bootstrap").status == "queued"
    assert reset.phase("scaffold_context_pack").status == "queued"

    recovered = service.run(reset.id)

    assert recovered.lifecycle_state is ScaffoldLifecycleState.SCAFFOLD_READY
    assert recovered.result is not None
    assert recovered.result["status"] == "scaffold_ready"
    assert len(
        [call for call in runner.calls if call[:2] == ("wrangler", "deploy")]
    ) == 1
    assert {item["kind"] for item in recovered.resources} == {
        "cloudflare_scaffold",
        "github_repository",
        "workbench_scope",
    }


def test_retry_refuses_to_overwrite_changed_provider_generated_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_module.shutil, "which", lambda name: f"/fake/{name}")
    monkeypatch.setattr(provider_module, "_tool_version", lambda _: "99.0.0")
    projects = tmp_path / "projects"
    projects.mkdir()
    runner = _FailValidationOnceRunner()
    service = ProjectScaffoldService(
        projects_root=projects,
        state_root=tmp_path / "state",
        command_runner=runner,
        execute_commands=True,
        allow_remote_writes=True,
    )
    draft = service.create_draft(
        ScaffoldDraftInput(
            name="Preserve Generated Change",
            github_owner="owner",
            github_mode="create_or_verify",
            cloudflare_mode=CloudflareMode.PROVISION_SCAFFOLD,
            aws_mode=AwsReadinessMode.NONE,
        )
    )
    service.confirm_draft(draft.id, draft.contract_hash)
    failed = service.run(service.start_or_resume(draft.id).id)
    assert failed.phase("target_bootstrap").status == "completed"
    assert failed.phase("target_validation").status == "blocked"
    gradlew = Path(failed.workspace_path, "apps/mobile/android/gradlew")
    gradlew.write_text("user-reviewed-change\n", encoding="utf-8")
    expo_ci_before = runner.calls.count(("npm", "ci"))

    retried = service.run(service.retry(failed.id).id)

    assert gradlew.read_text(encoding="utf-8") == "user-reviewed-change\n"
    assert retried.phase("target_validation").status == "blocked"
    assert any(
        item["code"] == "provider_generated_file_changed"
        for item in retried.to_payload()["blockers"]
    )
    assert runner.calls.count(("npm", "ci")) == expo_ci_before
    assert not any(call[:2] == ("wrangler", "deploy") for call in runner.calls)


def test_cancelled_job_persists_and_retry_clears_cancellation(tmp_path: Path) -> None:
    service = _service(tmp_path)
    draft = service.create_draft(
        ScaffoldDraftInput(
            name="Persistent Cancellation",
            github_mode="disabled",
            cloudflare_mode=CloudflareMode.DISABLED,
            aws_mode=AwsReadinessMode.NONE,
        )
    )
    service.confirm_draft(draft.id, draft.contract_hash)
    cancelled = service.cancel(service.start_or_resume(draft.id).id)

    assert cancelled.to_payload()["canRetry"] is True
    assert all(phase.status == "cancelled" for phase in cancelled.phases)

    restored = ProjectScaffoldService(
        projects_root=tmp_path / "projects",
        state_root=tmp_path / "state",
        execute_commands=False,
        allow_remote_writes=False,
    )
    persisted = restored.get_job(cancelled.id)
    assert persisted is not None
    assert persisted.cancelled is True
    assert all(phase.status == "cancelled" for phase in persisted.phases)

    reset = restored.retry(cancelled.id)
    assert reset.cancelled is False
    assert all(phase.status == "queued" for phase in reset.phases)
    completed = restored.run(reset.id)
    assert completed.result is not None
    assert completed.lifecycle_state is ScaffoldLifecycleState.SCAFFOLD_BLOCKED_WITH_CONTEXT


def test_preflight_rejects_unrelated_v2_workspace_before_any_remote_effect(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    runner = _RecordingRunner()
    service = ProjectScaffoldService(
        projects_root=projects,
        state_root=tmp_path / "state",
        command_runner=runner,
        execute_commands=True,
        allow_remote_writes=True,
    )
    draft = service.create_draft(
        ScaffoldDraftInput(
            name="Collision",
            github_owner="owner",
            github_mode="create_or_verify",
            cloudflare_mode=CloudflareMode.PROVISION_SCAFFOLD,
        )
    )
    service.confirm_draft(draft.id, draft.contract_hash)
    workspace = projects / "collision"
    (workspace / ".codex").mkdir(parents=True)
    manifest_path = workspace / ".codex/project.yaml"
    original_manifest = (
        "schema_version: 2\ncreation:\n  mode: product\n"
        "project:\n  slug: collision\n"
    )
    manifest_path.write_text(original_manifest, encoding="utf-8")

    job = service.run(service.start_or_resume(draft.id).id)

    assert job.phase("scaffold_preflight").status == "blocked"
    assert any(
        item["code"] == "target_conflict" for item in job.to_payload()["blockers"]
    )
    assert runner.calls == []
    assert manifest_path.read_text(encoding="utf-8") == original_manifest
    assert job.result is not None
    assert job.result["workspaceUntouched"] is True
    assert job.result["manifestPath"] is None
    assert not (workspace / ".codex/factory").exists()


def test_preflight_rejects_manifest_parent_symlink_without_external_write(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    runner = _RecordingRunner()
    service = ProjectScaffoldService(
        projects_root=projects,
        state_root=tmp_path / "state",
        command_runner=runner,
        execute_commands=True,
        allow_remote_writes=True,
    )
    draft = service.create_draft(
        ScaffoldDraftInput(
            name="Linked Collision",
            github_owner="owner",
            github_mode="create_or_verify",
            cloudflare_mode=CloudflareMode.PROVISION_SCAFFOLD,
        )
    )
    service.confirm_draft(draft.id, draft.contract_hash)
    external = tmp_path / "external-codex"
    external.mkdir()
    external_manifest = external / "project.yaml"
    original = yaml.safe_dump(draft.manifest, sort_keys=False)
    external_manifest.write_text(original, encoding="utf-8")
    workspace = projects / "linked-collision"
    workspace.mkdir()
    (workspace / ".codex").symlink_to(external, target_is_directory=True)

    job = service.run(service.start_or_resume(draft.id).id)

    assert job.phase("scaffold_preflight").status == "blocked"
    assert any(
        item["code"] == "unsafe_workspace_symlink"
        for item in job.to_payload()["blockers"]
    )
    assert runner.calls == []
    assert external_manifest.read_text(encoding="utf-8") == original
    assert sorted(path.name for path in external.iterdir()) == ["project.yaml"]


def test_existing_github_repository_never_pushes_to_unapproved_origin(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()

    class _WrongOriginRunner(_RecordingRunner):
        def run(self, argv, *, cwd, env=None, timeout_seconds=0):
            command = tuple(argv)
            if command[:2] == ("git", "init"):
                (cwd / ".git").mkdir(parents=True, exist_ok=True)
            if command == ("git", "remote", "get-url", "origin"):
                self.calls.append(command)
                return ScaffoldCommandResult(
                    command=command,
                    exit_code=0,
                    stdout="git@github.com:someone-else/wrong.git\n",
                )
            return super().run(
                argv, cwd=cwd, env=env, timeout_seconds=timeout_seconds
            )

    runner = _WrongOriginRunner()
    service = ProjectScaffoldService(
        projects_root=projects,
        state_root=tmp_path / "state",
        command_runner=runner,
        execute_commands=True,
        allow_remote_writes=True,
    )
    draft = service.create_draft(
        ScaffoldDraftInput(
            name="Approved",
            stack_preset=None,
            mobile_provider="none",
            web_provider="none",
            api_provider="none",
            github_owner="approved-owner",
            github_mode="create_or_verify",
            cloudflare_mode=CloudflareMode.DISABLED,
            aws_mode=AwsReadinessMode.NONE,
        )
    )
    service.confirm_draft(draft.id, draft.contract_hash)

    job = service.run(service.start_or_resume(draft.id).id)

    assert job.phase("github_repository").status == "blocked"
    assert any(
        item["code"] == "github_origin_mismatch"
        for item in job.to_payload()["blockers"]
    )
    assert not any(call[:2] == ("git", "push") for call in runner.calls)
