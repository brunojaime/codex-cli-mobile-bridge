from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app.application.services.project_factory_generator_service import (
    ProjectFactoryGeneratorError,
    ProjectFactoryGeneratorService,
)
from backend.app.application.services.project_factory_manifest_service import (
    ProjectFactoryManifestInput,
    ProjectFactoryManifestService,
)


def test_generator_writes_foundation_and_rolls_no_secrets(tmp_path: Path) -> None:
    manifest_plan = ProjectFactoryManifestService(
        projects_root=tmp_path,
    ).plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
        )
    )

    result = ProjectFactoryGeneratorService().generate(manifest_plan)

    project = tmp_path / "clinica-norte"
    assert result.ok is True
    assert result.status == "ready"
    assert result.target_path == str(project)
    assert (project / ".codex/project.yaml").is_file()
    assert (project / "specs/001-product-foundation/spec.md").is_file()
    assert (project / ".sdd/spec-index.yaml").is_file()
    assert (project / ".sdd/diagram-index.yaml").is_file()
    assert (project / "architecture/components.mmd").is_file()
    assert (project / "architecture/components.yaml").is_file()
    assert (project / "architecture/classes.mmd").is_file()
    assert (project / "architecture/classes.yaml").is_file()
    assert (project / "architecture/entity-relationship.mmd").is_file()
    assert (project / "architecture/entity-relationship.yaml").is_file()
    assert (project / "architecture/deployment.mmd").is_file()
    assert (project / "architecture/deployment.yaml").is_file()
    assert (project / "scripts/validate_generated_project.sh").is_file()
    assert (project / "scripts/validate_publication_ready.sh").is_file()
    assert (project / "scripts/validate_release_profiles.sh").is_file()
    assert (project / "scripts/finalize_local_commit.sh").is_file()
    assert (project / "scripts/publish_project.sh").is_file()
    assert (project / "scripts/register_installable_app.sh").is_file()
    assert (project / ".github/workflows/android-release.yml").is_file()
    assert (project / "codex-bridge.yaml").is_file()
    assert (project / "docs/workbench.md").is_file()
    assert (project / "release/runtime-profiles.md").is_file()
    assert (project / "release/release-contracts.yaml").is_file()
    assert (project / "apps/mobile/.gitkeep").is_file()
    assert (project / "backend/.gitkeep").is_file()
    assert result.git_status == "initialized_committed"
    assert _git(["log", "--oneline", "-1"], project).stdout
    assert "Initial Project Factory baseline" in _git(
        ["log", "--format=%s", "-1"],
        project,
    ).stdout
    assert _git(["status", "--porcelain"], project).stdout == ""
    metadata = (
        project / "specs/001-product-foundation/metadata.yaml"
    ).read_text(encoding="utf-8")
    assert "architecture/components.mmd" in metadata
    assert "architecture/entity-relationship.mmd" in metadata
    assert "SEED_ADMIN_PASSWORD" in (project / "AGENTS.md").read_text(
        encoding="utf-8",
    )
    manifest = (project / ".codex/project.yaml").read_text(encoding="utf-8")
    assert "runtime_profiles:" in manifest
    assert "APP_RUNTIME_PROFILE" in manifest
    assert "strong_reference_contract:" in manifest
    assert "generic_material_shell_forbidden_when_references_exist: true" in manifest
    assert "workbench_visibility:" in manifest
    bridge_config = (project / "codex-bridge.yaml").read_text(encoding="utf-8")
    assert "sourceApp: clinica-norte" in bridge_config
    assert "workbench-sdd/v1" in bridge_config
    assert "Nienfoadmin1994" not in _read_all_text(project)


def test_generator_writes_fastapi_backend_v1_and_compileall_passes(
    tmp_path: Path,
) -> None:
    manifest_plan = ProjectFactoryManifestService(
        projects_root=tmp_path,
    ).plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
        )
    )

    ProjectFactoryGeneratorService().generate(manifest_plan)

    project = tmp_path / "clinica-norte"
    backend = project / "backend"
    assert (backend / "pyproject.toml").is_file()
    assert (backend / ".env.example").is_file()
    assert (backend / "README.md").is_file()
    assert (backend / "app/main.py").is_file()
    assert (backend / "app/security.py").is_file()
    assert (backend / "app/routers/auth.py").is_file()
    assert (backend / "app/routers/admin.py").is_file()
    assert (backend / "app/routers/notifications.py").is_file()
    assert (backend / "tests/test_backend.py").is_file()

    env_example = (backend / ".env.example").read_text(encoding="utf-8")
    assert "APP_RUNTIME_PROFILE=real" in env_example
    assert "APP_RELEASE_TAG=" in env_example
    assert "SECRET_KEY=" in env_example
    assert "ADMIN_INITIAL_PASSWORD=" in env_example
    assert "Nienfoadmin1994" not in _read_all_text(project)
    security = (backend / "app/security.py").read_text(encoding="utf-8")
    assert "hashlib.pbkdf2_hmac" in security
    assert "shell=True" not in security
    auth = (backend / "app/routers/auth.py").read_text(encoding="utf-8")
    assert '@router.post("/login")' in auth
    assert '@router.get("/me")' in auth
    notifications = (backend / "app/routers/notifications.py").read_text(
        encoding="utf-8",
    )
    assert '@router.get("")' in notifications
    app_updates = (backend / "app/routers/app_updates.py").read_text(
        encoding="utf-8",
    )
    assert '@router.get("/current")' in app_updates
    assert "mock_or_demo" in app_updates

    completed = subprocess.run(
        [sys.executable, "-m", "compileall", str(backend)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_generator_writes_executable_e2e_validation_script(tmp_path: Path) -> None:
    manifest_plan = ProjectFactoryManifestService(
        projects_root=tmp_path,
    ).plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
        )
    )

    ProjectFactoryGeneratorService().generate(manifest_plan)

    script = tmp_path / "clinica-norte/scripts/validate_generated_project.sh"
    assert script.is_file()
    assert script.stat().st_mode & stat.S_IXUSR
    content = script.read_text(encoding="utf-8")
    assert "DATABASE_URL" in content
    assert "SECRET_KEY" in content
    assert "ADMIN_EMAIL" in content
    assert "ADMIN_INITIAL_PASSWORD" in content
    assert "python -m pytest" in content
    assert "python -m uvicorn app.main:app" in content
    assert "/auth/login" in content
    assert "/auth/me" in content
    assert "/admin/roles" in content
    assert "/admin/domains" in content
    assert "/notifications" in content
    assert "flutter test --dart-define=API_BASE_URL=" in content
    assert "validate_release_profiles.sh" in content
    assert "trap cleanup EXIT" in content


def test_generator_writes_executable_publish_script(tmp_path: Path) -> None:
    manifest_plan = ProjectFactoryManifestService(
        projects_root=tmp_path,
    ).plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
        )
    )

    ProjectFactoryGeneratorService().generate(manifest_plan)

    script = tmp_path / "clinica-norte/scripts/publish_project.sh"
    assert script.is_file()
    assert script.stat().st_mode & stat.S_IXUSR
    content = script.read_text(encoding="utf-8")
    assert "gh repo create" in content
    assert "git push -u origin" in content
    assert "GITHUB_OWNER" in content
    assert "INITIAL_COMMIT_MESSAGE" in content
    assert "published: https://github.com/$REPO" in content

    finalize_script = tmp_path / "clinica-norte/scripts/finalize_local_commit.sh"
    assert finalize_script.is_file()
    assert finalize_script.stat().st_mode & stat.S_IXUSR
    finalize_content = finalize_script.read_text(encoding="utf-8")
    assert "git add -A" in finalize_content
    assert "Finalize Project Factory output" in finalize_content

    validation_script = tmp_path / "clinica-norte/scripts/validate_publication_ready.sh"
    assert validation_script.is_file()
    assert validation_script.stat().st_mode & stat.S_IXUSR
    validation_content = validation_script.read_text(encoding="utf-8")
    assert "origin remote is not configured" in validation_content
    assert "local HEAD is not pushed" in validation_content
    assert "GitHub release $expected_tag has no APK asset" in validation_content
    assert "validate_release_profiles.sh" in validation_content

    release_profile_script = tmp_path / "clinica-norte/scripts/validate_release_profiles.sh"
    assert release_profile_script.is_file()
    assert release_profile_script.stat().st_mode & stat.S_IXUSR
    release_profile_content = release_profile_script.read_text(encoding="utf-8")
    assert "APP_RUNTIME_PROFILE" in release_profile_content
    assert "android-mock-" in release_profile_content
    assert "productive android-v* tags cannot use" in release_profile_content
    assert "API_BASE_URL" in release_profile_content
    assert "codex-bridge.yaml" in release_profile_content


def test_generated_release_profile_script_enforces_real_and_mock_contracts(
    tmp_path: Path,
) -> None:
    manifest_plan = ProjectFactoryManifestService(
        projects_root=tmp_path,
    ).plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
        )
    )

    ProjectFactoryGeneratorService().generate(manifest_plan)

    project = tmp_path / "clinica-norte"
    script = project / "scripts/validate_release_profiles.sh"

    real = subprocess.run(
        [str(script)],
        cwd=project,
        env={
            **os.environ,
            "APP_RELEASE_TAG": "android-v0.1.0-build.1",
            "APP_RUNTIME_PROFILE": "real",
            "API_BASE_URL": "https://api.validation.invalid",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert real.returncode == 0, real.stdout + real.stderr
    assert "profile=real" in real.stdout

    mock = subprocess.run(
        [str(script)],
        cwd=project,
        env={
            **os.environ,
            "APP_RELEASE_TAG": "android-mock-v0.1.0-build.1",
            "APP_RUNTIME_PROFILE": "mock",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert mock.returncode == 0, mock.stdout + mock.stderr
    assert "profile=mock" in mock.stdout

    bad_productive = subprocess.run(
        [str(script)],
        cwd=project,
        env={
            **os.environ,
            "APP_RELEASE_TAG": "android-v0.1.0-build.1",
            "APP_RUNTIME_PROFILE": "mock",
            "API_BASE_URL": "https://api.validation.invalid",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert bad_productive.returncode != 0
    assert "productive android-v* tags cannot use APP_RUNTIME_PROFILE=mock" in (
        bad_productive.stdout + bad_productive.stderr
    )


def test_generated_android_release_workflow_defaults_to_real_runtime(
    tmp_path: Path,
) -> None:
    manifest_plan = ProjectFactoryManifestService(
        projects_root=tmp_path,
    ).plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
        )
    )

    ProjectFactoryGeneratorService().generate(manifest_plan)

    workflow = (
        tmp_path / "clinica-norte/.github/workflows/android-release.yml"
    ).read_text(encoding="utf-8")
    assert 'default: "real"' in workflow
    assert "APP_RUNTIME_PROFILE:" in workflow
    assert "github.event.inputs.runtime_profile" in workflow
    assert "|| 'real'" in workflow
    assert "android-mock-v*" in workflow
    assert 'LOCAL_DATA_MODE: "false"' in workflow
    assert 'args+=(--dart-define=APP_RUNTIME_PROFILE="$APP_RUNTIME_PROFILE")' in workflow
    assert 'args+=(--dart-define=API_BASE_URL="$API_BASE_URL")' in workflow


def test_generated_contract_docs_have_coherent_minimum_content(
    tmp_path: Path,
) -> None:
    manifest_plan = ProjectFactoryManifestService(
        projects_root=tmp_path,
    ).plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
        )
    )

    ProjectFactoryGeneratorService().generate(manifest_plan)

    project = tmp_path / "clinica-norte"
    contracts = (project / "release/release-contracts.yaml").read_text(
        encoding="utf-8"
    )
    runtime_doc = (project / "release/runtime-profiles.md").read_text(
        encoding="utf-8"
    )
    bridge = (project / "codex-bridge.yaml").read_text(encoding="utf-8")
    workbench = (project / "docs/workbench.md").read_text(encoding="utf-8")

    assert "runtime_profiles:" in contracts
    assert "productive_release:" in contracts
    assert "mock_release:" in contracts
    assert "codex_mobile_catalog:" in contracts
    assert "scripts/register_installable_app.sh" in contracts
    assert "APP_RUNTIME_PROFILE=real" in runtime_doc
    assert "android-mock-vX.Y.Z-build.N" in runtime_doc
    assert "sourceApp: clinica-norte" in bridge
    assert "workbench-sdd/v1" in bridge
    assert "APP_RUNTIME_PROFILE=real" in workbench
    assert "hidden or disabled" in " ".join(workbench.split())


def test_generated_project_registers_installable_app_contract(
    tmp_path: Path,
) -> None:
    manifest_plan = ProjectFactoryManifestService(
        projects_root=tmp_path,
    ).plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
        )
    )

    ProjectFactoryGeneratorService().generate(manifest_plan)

    project = tmp_path / "clinica-norte"
    script = project / "scripts/register_installable_app.sh"
    assert script.is_file()
    assert script.stat().st_mode & stat.S_IXUSR
    content = script.read_text(encoding="utf-8")
    assert 'SOURCE_APP="${SOURCE_APP:-clinica-norte}"' in content
    assert 'DISPLAY_NAME="${DISPLAY_NAME:-Clinica Norte}"' in content
    assert 'BRIDGE_URL="${BRIDGE_URL:-http://127.0.0.1:8000}"' in content
    assert 'POST "$BRIDGE_URL/installable-apps"' in content
    assert 'installable-apps/$SOURCE_APP' in content
    assert "REQUIRE_INSTALLABLE_APK" in content

    readme = (project / "README.md").read_text(encoding="utf-8")
    assert "scripts/register_installable_app.sh" in readme
    assert "/installable-apps/{sourceApp}" in readme


def test_generated_flutter_mock_seed_selector_is_mock_profile_only(
    tmp_path: Path,
) -> None:
    manifest_plan = ProjectFactoryManifestService(
        projects_root=tmp_path,
    ).plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
        )
    )

    ProjectFactoryGeneratorService().generate(manifest_plan)

    mobile = tmp_path / "clinica-norte/apps/mobile"
    main = (mobile / "lib/main.dart").read_text(encoding="utf-8")
    config = (mobile / "lib/src/config.dart").read_text(encoding="utf-8")
    session = (mobile / "lib/src/session_controller.dart").read_text(
        encoding="utf-8"
    )
    screens = (mobile / "lib/src/screens.dart").read_text(encoding="utf-8")

    assert "defaultValue: 'real'" in main
    assert "config.isMock" in main
    assert "MockProjectApiClient" in main
    assert "runtimeProfile == 'mock'" in config
    assert "bool get isMockRuntime" in session
    assert "if (widget.controller.isMockRuntime)" in screens
    assert "Enter demo as role" in screens


def test_generator_writes_flutter_mobile_v1_template(tmp_path: Path) -> None:
    manifest_plan = ProjectFactoryManifestService(
        projects_root=tmp_path,
    ).plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
        )
    )

    ProjectFactoryGeneratorService().generate(manifest_plan)

    project = tmp_path / "clinica-norte"
    mobile = project / "apps/mobile"
    assert (mobile / "pubspec.yaml").is_file()
    assert (mobile / "README.md").is_file()
    assert (mobile / "lib/main.dart").is_file()
    assert (mobile / "lib/src/config.dart").is_file()
    assert (mobile / "lib/src/models.dart").is_file()
    assert (mobile / "lib/src/api_client.dart").is_file()
    assert (mobile / "lib/src/mock_api_client.dart").is_file()
    assert (mobile / "lib/src/session_controller.dart").is_file()
    assert (mobile / "lib/src/screens.dart").is_file()
    assert (mobile / "test/config_test.dart").is_file()
    assert (mobile / "test/api_client_test.dart").is_file()
    assert (mobile / "test/session_controller_test.dart").is_file()

    pubspec = (mobile / "pubspec.yaml").read_text(encoding="utf-8")
    assert "name: clinica_norte" in pubspec
    assert "http: ^1.2.2" in pubspec
    readme = (mobile / "README.md").read_text(encoding="utf-8")
    assert "--dart-define=API_BASE_URL=" in readme
    main = (mobile / "lib/main.dart").read_text(encoding="utf-8")
    assert "String.fromEnvironment('API_BASE_URL')" in main
    assert "APP_RUNTIME_PROFILE" in main
    assert "MockProjectApiClient" in main
    api_client = (mobile / "lib/src/api_client.dart").read_text(encoding="utf-8")
    assert "/health" in api_client
    assert "/auth/register" in api_client
    assert "/auth/login" in api_client
    assert "/auth/me" in api_client
    assert "/auth/logout" in api_client
    assert "/admin/users" in api_client
    assert "/admin/roles" in api_client
    assert "/admin/domains" in api_client
    assert "/notifications" in api_client
    screens = (mobile / "lib/src/screens.dart").read_text(encoding="utf-8")
    assert "user.canAccessAdmin" in screens
    assert "Enter demo as role" in screens
    assert "No notifications" in screens
    mock_api = (mobile / "lib/src/mock_api_client.dart").read_text(encoding="utf-8")
    assert "seedRoles" in mock_api
    assert "employee" in mock_api
    assert "Nienfoadmin1994" not in _read_all_text(project)


def test_generator_writes_visual_reference_contract(tmp_path: Path) -> None:
    manifest_plan = ProjectFactoryManifestService(
        projects_root=tmp_path,
    ).plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
            visual_reference_paths=("references/images/dashboard.png",),
        )
    )

    ProjectFactoryGeneratorService().generate(manifest_plan)

    project = tmp_path / "clinica-norte"
    analysis = (project / "docs/research/visual-reference-analysis.md").read_text(
        encoding="utf-8",
    )
    assert "Every attached visual reference must be analyzed" in analysis
    assert "generic Scaffold/AppBar/ListView shell is a failed" in analysis
    components = (project / "design/reference-components.md").read_text(
        encoding="utf-8",
    )
    assert "inventory item card" in components
    report = (project / "design/visual-validation-report.md").read_text(
        encoding="utf-8",
    )
    assert "screenshots/previews" in report
    tokens = (project / "design/tokens.yaml").read_text(encoding="utf-8")
    assert "derived_from_visual_references" in tokens


def test_generated_flutter_mobile_tests_pass_when_flutter_is_available(
    tmp_path: Path,
) -> None:
    if shutil.which("flutter") is None:
        pytest.skip("flutter is not installed")
    manifest_plan = ProjectFactoryManifestService(
        projects_root=tmp_path,
    ).plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
        )
    )

    ProjectFactoryGeneratorService().generate(manifest_plan)

    completed = subprocess.run(
        ["flutter", "test"],
        cwd=tmp_path / "clinica-norte/apps/mobile",
        text=True,
        capture_output=True,
        check=False,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_generator_rejects_invalid_plan_and_existing_target(tmp_path: Path) -> None:
    service = ProjectFactoryManifestService(projects_root=tmp_path)
    invalid = service.plan_manifest(
        ProjectFactoryManifestInput(name="", business_type="", primary_goal="")
    )
    with pytest.raises(ProjectFactoryGeneratorError):
        ProjectFactoryGeneratorService().generate(invalid)

    valid = service.plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
        )
    )
    (tmp_path / "clinica-norte").mkdir()
    with pytest.raises(ProjectFactoryGeneratorError):
        ProjectFactoryGeneratorService().generate(valid)


def _read_all_text(project: Path) -> str:
    chunks: list[str] = []
    for path in project.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )
