from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
    assert (project / "specs/001-product-foundation/tree.json").is_file()
    assert (
        project / "specs/001-product-foundation/plans/01-foundation/plan.md"
    ).is_file()
    assert (
        project / "specs/001-product-foundation/tasks/plan-1-task-1/task.md"
    ).is_file()
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
    assert (project / "scripts/validate_preview_release_profiles.sh").is_file()
    assert (project / "scripts/finalize_local_commit.sh").is_file()
    assert (project / "scripts/publish_project.sh").is_file()
    assert (project / "scripts/apply_cloudflare_preview.sh").is_file()
    assert (project / "scripts/smoke_preview_api.sh").is_file()
    assert (project / "scripts/publish_android_preview_release.sh").is_file()
    assert (project / "scripts/publish_android_release.sh").is_file()
    assert (project / "scripts/validate_initial_preview_release.sh").is_file()
    assert (project / "scripts/register_installable_app.sh").is_file()
    assert (project / "scripts/build_web_preview.sh").is_file()
    assert (project / "scripts/validate_web_preview.sh").is_file()
    assert (project / "scripts/deploy_web_preview.sh").is_file()
    assert (project / "deploy/web-preview/web-preview-manifest.yaml").is_file()
    assert (project / "deploy/web-preview/wrangler.toml.example").is_file()
    assert (project / "deploy/web-preview/worker/src/index.js").is_file()
    assert (project / ".github/workflows/android-release.yml").is_file()
    assert (project / ".github/workflows/android-preview-release.yml").is_file()
    assert (project / "codex-bridge.yaml").is_file()
    assert (project / "docs/workbench.md").is_file()
    assert (project / "release/runtime-profiles.md").is_file()
    assert (project / "release/preview-runtime.json").is_file()
    assert (project / "release/release-contracts.yaml").is_file()
    assert (project / "release/aws-domain-delegation-runbook.md").is_file()
    assert (project / "release/email-provider-runbook.md").is_file()
    assert (project / "release/dns-cloudflare-troubleshooting.md").is_file()
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
    assert "tree.json" in metadata
    assert "total: 11" in metadata
    assert "completed: 7" in metadata
    assert "pending: 4" in metadata
    assert "architecture/components.mmd" in metadata
    assert "architecture/entity-relationship.mmd" in metadata
    tree = json.loads(
        (project / "specs/001-product-foundation/tree.json").read_text(
            encoding="utf-8",
        ),
    )
    assert tree["plans"][0]["status"] == "in_progress"
    statuses = [task["status"] for task in tree["plans"][0]["tasks"]]
    assert statuses.count("done") == 7
    assert statuses.count("planned") == 4
    assert tree["plans"][0]["tasks"][0]["file"] == "tasks/plan-1-task-1/task.md"
    assert "SEED_ADMIN_PASSWORD" in (project / "AGENTS.md").read_text(
        encoding="utf-8",
    )
    api_client = (project / "apps/mobile/lib/src/api_client.dart").read_text(
        encoding="utf-8"
    )
    screens = (project / "apps/mobile/lib/src/screens.dart").read_text(
        encoding="utf-8"
    )
    session = (
        project / "apps/mobile/lib/src/session_controller.dart"
    ).read_text(encoding="utf-8")
    main = (project / "apps/mobile/lib/main.dart").read_text(encoding="utf-8")
    pubspec = (project / "apps/mobile/pubspec.yaml").read_text(encoding="utf-8")
    assert "acceptPreviewInvite" in api_client
    assert "'/invites/accept'" in api_client
    assert "Invite token or link" not in screens
    assert "Aceptar invitación al Preview" in screens
    assert "Crear contraseña" in screens
    assert "Repetir contraseña" in screens
    assert "Aceptar invitación" in screens
    assert "Create password" not in screens
    assert "Repeat password" not in screens
    assert "Activate account" not in screens
    assert "label: 'Workbench'" not in screens
    assert "CodexBridgeDevModeWrapper" in main
    assert "DeveloperFeedbackTemplate" in main
    assert "CODEX DEV" not in screens
    assert "CODEX_BRIDGE_WORKBENCH_URL" in main
    assert "CODEX_APP_UPDATER_ENABLED" in main
    assert "CODEX_APP_UPDATER_BRIDGE_URL" in main
    assert "workbenchBridgeUrl: apiBaseUrl" not in main
    assert "codex_developer_feedback_template:" in pubspec
    assert "ref: codex-developer-feedback-template-v0.4.7" in pubspec
    assert "codex_app_updater:" in pubspec
    assert "ref: 374f0e3180dc8d80214dcaa4374073d8e4ab1340" in pubspec
    assert "codex_bridge_workbench:" in pubspec
    android_manifest = (
        project / "apps/mobile/android/app/src/main/AndroidManifest.xml"
    ).read_text(encoding="utf-8")
    assert 'android:label="Clinica Norte"' in android_manifest
    assert "Generated Preview" not in android_manifest
    assert 'android:icon="@drawable/app_icon"' in android_manifest
    assert 'android:networkSecurityConfig="@xml/network_security_config"' in (
        android_manifest
    )
    app_icon = (
        project / "apps/mobile/android/app/src/main/res/drawable/app_icon.xml"
    ).read_text(encoding="utf-8")
    assert "<vector" in app_icon
    assert "@mipmap/ic_launcher" not in app_icon
    brand_logo = (project / "assets/brand/logo.svg").read_text(encoding="utf-8")
    mobile_icon_source = (
        project / "apps/mobile/assets/brand/app_icon_source.svg"
    ).read_text(encoding="utf-8")
    assert "Clinica Norte logo" in brand_logo
    assert "CN" in brand_logo
    assert brand_logo == mobile_icon_source
    network_security = (
        project / "apps/mobile/android/app/src/main/res/xml/network_security_config.xml"
    ).read_text(encoding="utf-8")
    assert 'cleartextTrafficPermitted="true"' in network_security
    assert "tail0302c4.ts.net" in network_security
    assert "isPreviewRuntime" in session
    manifest = (project / ".codex/project.yaml").read_text(encoding="utf-8")
    assert "runtime_profiles:" in manifest
    assert "APP_RUNTIME_PROFILE" in manifest
    assert "strong_reference_contract:" in manifest
    assert "generic_material_shell_forbidden_when_references_exist: true" in manifest
    assert "workbench_visibility:" in manifest
    web_preview_manifest = (
        project / "deploy/web-preview/web-preview-manifest.yaml"
    ).read_text(encoding="utf-8")
    assert "source_app: clinica-norte" in web_preview_manifest
    assert 'stable_url: "https://preview.nienfos.com/clinica-norte"' in (
        web_preview_manifest
    )
    assert "api_runtime: cloudflare_preview" in web_preview_manifest
    assert "CLOUDFLARE_API_TOKEN:" not in web_preview_manifest
    assert "runtime_profile=mock" not in web_preview_manifest
    deploy_script = (project / "scripts/deploy_web_preview.sh").read_text(
        encoding="utf-8",
    )
    assert "--plan|--apply" in deploy_script
    assert "CONFIRM_APPLY=true is required" in deploy_script
    assert "EXPECTED_PLAN_HASH is required" in deploy_script
    web_preview_readme = (project / "deploy/web-preview/README.md").read_text(
        encoding="utf-8",
    )
    assert "Bridge deploy flow" in web_preview_readme
    assert "WEB_PREVIEW_APPLY_ENABLED=true" in web_preview_readme
    bridge_config = (project / "codex-bridge.yaml").read_text(encoding="utf-8")
    assert "sourceApp: clinica-norte" in bridge_config
    assert "workbench-sdd/v1" in bridge_config
    assert "Nienfoadmin1994" not in _read_all_text(project)


def test_generator_uses_readable_android_label_for_slug_like_project_name(
    tmp_path: Path,
) -> None:
    manifest_plan = ProjectFactoryManifestService(
        projects_root=tmp_path,
    ).plan_manifest(
        ProjectFactoryManifestInput(
            name="prueba-24",
            business_type="operations",
            primary_goal="Gestionar operaciones",
        )
    )

    ProjectFactoryGeneratorService().generate(manifest_plan)

    manifest = (
        tmp_path
        / "prueba-24/apps/mobile/android/app/src/main/AndroidManifest.xml"
    ).read_text(encoding="utf-8")
    assert 'android:label="Prueba 24"' in manifest
    assert "prueba-24" not in manifest
    assert "Generated Preview" not in manifest


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
    assert "APP_RUNTIME_PROFILE=preview" in env_example
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
    assert "/admin/business-records" in content
    assert "/notifications" in content
    assert "flutter test --dart-define=API_BASE_URL=" in content
    assert "validate_release_profiles.sh" in content
    assert "trap cleanup EXIT" in content


def test_generator_writes_svelte_web_strategy_without_android_overpromise(
    tmp_path: Path,
) -> None:
    manifest_plan = ProjectFactoryManifestService(
        projects_root=tmp_path,
    ).plan_manifest(
        ProjectFactoryManifestInput(
            name="Portal Clientes",
            business_type="services",
            primary_goal="Clientes consultan estados",
            platforms=("web",),
            frontend_strategy="svelte",
        )
    )

    result = ProjectFactoryGeneratorService().generate(manifest_plan)

    project = tmp_path / "portal-clientes"
    assert result.ok is True
    assert (project / "apps/web/package.json").is_file()
    assert (project / "apps/web/package-lock.json").is_file()
    assert (project / "apps/web/src/config.ts").is_file()
    assert (project / "apps/web/test/preview-config.test.mjs").is_file()
    assert not (project / "apps/mobile/pubspec.yaml").exists()
    assert not (project / ".github/workflows/android-preview-release.yml").exists()
    assert not (project / "scripts/publish_android_preview_release.sh").exists()
    assert not (project / "scripts/register_installable_app.sh").exists()

    runtime = json.loads(
        (project / "release/preview-runtime.json").read_text(encoding="utf-8")
    )
    assert runtime["frontendStrategy"] == "svelte"
    assert runtime["installableAndroid"] is False
    assert runtime["bridgeRegistrationRequired"] is False
    assert runtime["releaseChannel"] == "prerelease"
    assert "releaseTagPattern" not in runtime

    manifest = (project / ".codex/project.yaml").read_text(encoding="utf-8")
    assert "frontend_strategy: svelte" in manifest
    assert "source_root: apps/web" in manifest
    assert "env: VITE_APP_RUNTIME_PROFILE" in manifest
    assert "api_runtime_env: VITE_API_RUNTIME" in manifest
    assert "preview_api_env: VITE_API_BASE_URL" in manifest
    assert "android-preview-v" not in manifest
    assert "android-mock-v" not in manifest
    assert "android-v" not in manifest
    assert "env: APP_RUNTIME_PROFILE" not in manifest
    assert "APP_RUNTIME_PROFILE=preview" not in manifest
    assert "APK assets and release metadata are required" not in manifest

    preview_manifest = (
        project / "deploy/web-preview/web-preview-manifest.yaml"
    ).read_text(encoding="utf-8")
    assert "frontend_strategy: svelte" in preview_manifest
    assert "svelte_project: apps/web" in preview_manifest
    assert "installable_android: false" in preview_manifest

    config = (project / "apps/web/src/config.ts").read_text(encoding="utf-8")
    assert "https://preview.nienfos.com/portal-clientes/api" in config
    assert "localhost" in config
    assert "throw new Error" in config

    package_json = json.loads(
        (project / "apps/web/package.json").read_text(encoding="utf-8")
    )
    assert package_json["scripts"]["validate:preview"] == (
        "node test/preview-config.test.mjs --preview"
    )
    build_script = (project / "scripts/build_web_preview.sh").read_text(
        encoding="utf-8"
    )
    validation_script = (
        project / "scripts/validate_generated_project.sh"
    ).read_text(encoding="utf-8")
    assert "npm ci" in build_script
    assert "npm install" not in build_script
    assert "npm ci" in validation_script
    assert "npm install" not in validation_script

    release_files = {
        "release/preview-signing-policy.json": (
            project / "release/preview-signing-policy.json"
        ).read_text(encoding="utf-8"),
        "release/android-preview-signing.md": (
            project / "release/android-preview-signing.md"
        ).read_text(encoding="utf-8"),
        "release/promotion-contract.json": (
            project / "release/promotion-contract.json"
        ).read_text(encoding="utf-8"),
        "release/release-contracts.yaml": (
            project / "release/release-contracts.yaml"
        ).read_text(encoding="utf-8"),
        "release/release-output-template.md": (
            project / "release/release-output-template.md"
        ).read_text(encoding="utf-8"),
        "release/runtime-profiles.md": (
            project / "release/runtime-profiles.md"
        ).read_text(encoding="utf-8"),
        "release/play-store-checklist.md": (
            project / "release/play-store-checklist.md"
        ).read_text(encoding="utf-8"),
        "release/app-store-checklist.md": (
            project / "release/app-store-checklist.md"
        ).read_text(encoding="utf-8"),
    }
    for path, content in release_files.items():
        assert "android-preview-v" not in content, path
        assert "android-v" not in content, path
        assert ".apk" not in content.lower(), path
        assert "bridge_preview_registration" not in content, path
        assert "production_signing_key" not in content, path
        assert "Play Store readiness" not in content, path
        assert "App Store readiness" not in content, path
    contracts = release_files["release/release-contracts.yaml"]
    assert "env: VITE_APP_RUNTIME_PROFILE" in contracts
    assert "api_runtime_env: VITE_API_RUNTIME" in contracts
    assert "preview_api_env: VITE_API_BASE_URL" in contracts
    assert "env: APP_RUNTIME_PROFILE" not in contracts
    assert "web_preview_ready: false" in release_files[
        "release/release-output-template.md"
    ]
    assert "installable_android: false" in release_files[
        "release/release-output-template.md"
    ]
    scanned_files = [
        project / "README.md",
        *sorted((project / "specs/001-product-foundation").glob("*.md")),
        project / "specs/001-product-foundation/tree.json",
        *sorted((project / "architecture").glob("*.mmd")),
        *sorted((project / "release").glob("*.md")),
        project / ".codex/project.yaml",
    ]
    forbidden_terms = (
        "Flutter iOS/Android/Web",
        "Flutter mobile v1",
        "Flutter Mobile App",
        "Flutter Web App",
        "Installed Mobile App",
        "App Store / Play Store",
        "android-preview-v",
        "android-mock-v",
        "android-v",
        ".apk",
        "scripts/register_installable_app.sh",
        "Bridge installable",
        "Play Store readiness",
        "App Store readiness",
        "ready for Play Store",
        "ready for App Store",
    )
    for scanned_file in scanned_files:
        content = scanned_file.read_text(encoding="utf-8")
        for term in forbidden_terms:
            assert term not in content, f"{term!r} found in {scanned_file}"
        assert "APP_RUNTIME_PROFILE=preview" not in content.replace(
            "VITE_APP_RUNTIME_PROFILE=preview",
            "",
        ), scanned_file

    final_gate = (
        project / "scripts/validate_initial_preview_release.sh"
    ).read_text(encoding="utf-8")
    assert "scripts/smoke_web_preview.sh" in final_gate
    assert "scripts/smoke_preview_api.sh" in final_gate
    assert final_gate.index("scripts/smoke_web_preview.sh") < final_gate.index(
        "web_preview_ready: true"
    )
    assert final_gate.index("scripts/smoke_preview_api.sh") < final_gate.index(
        "web_preview_ready: true"
    )


def test_generated_svelte_project_npm_preview_contract_smoke(
    tmp_path: Path,
) -> None:
    if shutil.which("npm") is None:
        pytest.skip("npm is required for generated Svelte smoke validation")
    manifest_plan = ProjectFactoryManifestService(
        projects_root=tmp_path,
    ).plan_manifest(
        ProjectFactoryManifestInput(
            name="Portal Clientes",
            business_type="services",
            primary_goal="Clientes consultan estados",
            platforms=("web",),
            frontend_strategy="svelte",
        )
    )
    ProjectFactoryGeneratorService().generate(manifest_plan)

    web_dir = tmp_path / "portal-clientes/apps/web"
    install = subprocess.run(
        ["npm", "ci"],
        cwd=web_dir,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert install.returncode == 0, install.stdout + install.stderr
    test = subprocess.run(
        ["npm", "test"],
        cwd=web_dir,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert test.returncode == 0, test.stdout + test.stderr
    validate = subprocess.run(
        ["npm", "run", "validate:preview"],
        cwd=web_dir,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert validate.returncode == 0, validate.stdout + validate.stderr
    build = subprocess.run(
        ["npm", "run", "build"],
        cwd=web_dir,
        env={
            **os.environ,
            "VITE_APP_RUNTIME_PROFILE": "preview",
            "VITE_API_RUNTIME": "cloudflare_preview",
            "VITE_API_BASE_URL": (
                "https://preview.nienfos.com/portal-clientes/api"
            ),
        },
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert build.returncode == 0, build.stdout + build.stderr


def test_generator_keeps_flutter_release_files_android_capable(
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
    runtime = json.loads(
        (project / "release/preview-runtime.json").read_text(encoding="utf-8")
    )
    assert runtime["frontendStrategy"] == "flutter"
    assert runtime["releaseTagPattern"] == "android-preview-v*"
    assert runtime["installableAndroid"] is True
    assert runtime["bridgeRegistrationRequired"] is True
    assert runtime["bridge"]["requiresApkUrl"] is True
    assert (project / "scripts/register_installable_app.sh").is_file()
    assert (project / "scripts/publish_android_preview_release.sh").is_file()


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
    assert "gh variable set API_BASE_URL" in content
    assert "https://preview.nienfos.com/$PROJECT_SLUG/api" in content
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
    assert "validate_initial_preview_release.sh" in validation_content
    assert "initial preview release ready" in (
        tmp_path / "clinica-norte/scripts/validate_initial_preview_release.sh"
    ).read_text(encoding="utf-8")

    web_build = (tmp_path / "clinica-norte/scripts/build_web_preview.sh").read_text(
        encoding="utf-8"
    )
    assert 'CODEX_BRIDGE_DEV_MODE="${CODEX_BRIDGE_DEV_MODE:-false}"' in web_build

    android_preview = (
        tmp_path / "clinica-norte/.github/workflows/android-preview-release.yml"
    ).read_text(encoding="utf-8")
    assert (
        '--dart-define=CODEX_BRIDGE_DEV_MODE="${{ vars.CODEX_BRIDGE_DEV_MODE '
        "|| 'true' }}\""
    ) in android_preview
    assert "--dart-define=CODEX_BRIDGE_WORKBENCH_URL=" in android_preview
    assert "flutter build apk --release --target=lib/main_preview.dart" in (
        android_preview
    )
    assert "vars.CODEX_APP_UPDATER_ENABLED || 'true'" in android_preview

    android_preview_script = tmp_path / "clinica-norte/scripts/publish_android_preview_release.sh"
    assert android_preview_script.is_file()
    assert android_preview_script.stat().st_mode & stat.S_IXUSR
    android_preview_content = android_preview_script.read_text(encoding="utf-8")
    smoke_preview_content = (
        tmp_path / "clinica-norte/scripts/smoke_preview_api.sh"
    ).read_text(encoding="utf-8")
    assert "flutter is required to create the missing Android platform" in (
        android_preview_content
    )
    assert "preview_health_ready" in smoke_preview_content
    assert "health.get(\"assets_bound\") is True" in smoke_preview_content
    assert "for delay in (0.5, 1.0, 2.0, 3.0, 5.0, 8.0)" in (
        smoke_preview_content
    )
    assert 'PREVIEW_ORIGIN="https://preview.nienfos.com/$SOURCE_APP"' in (
        smoke_preview_content
    )
    assert 'PREVIEW_API_BASE_URL="$PREVIEW_ORIGIN/api"' in smoke_preview_content
    assert "export PREVIEW_API_BASE_URL" in smoke_preview_content
    assert "expected_url=https://preview.nienfos.com/{source_app}/api/admin/bootstrap" in (
        smoke_preview_content
    )
    assert "does not accept POST" in smoke_preview_content
    assert "android-preview-v${version//+/-build.}" in android_preview_content
    assert "scripts/smoke_preview_api.sh" in android_preview_content
    assert "scripts/load_bridge_env.sh" in android_preview_content
    assert "scripts/github_repo_access.sh" in android_preview_content
    assert "bridge_env_load_preview_signing" in android_preview_content
    assert "APP_RUNTIME_PROFILE=preview" in android_preview_content
    assert 'ANDROID_PREVIEW_RELEASE_MODE="${ANDROID_PREVIEW_RELEASE_MODE:-bridge_local}"' in android_preview_content
    assert "--github-actions" in android_preview_content
    assert "flutter build apk" in android_preview_content
    assert "--target=lib/main_preview.dart" in android_preview_content
    assert "ensure_flutter_android_platform" in android_preview_content
    assert "flutter create --platforms=android ." in android_preview_content
    assert "flutter create did not produce a complete Android v2 platform" in (
        android_preview_content
    )
    assert "rm -f apps/mobile/analysis_options.yaml" in android_preview_content
    assert "rm -f apps/mobile/test/widget_test.dart" in android_preview_content
    assert "patch_flutter_android_release_signing" in android_preview_content
    assert 'signingConfig = signingConfigs.getByName("release")' in (
        android_preview_content
    )
    assert "preview_release_blocking_git_status" in android_preview_content
    assert '"?? specs/"*"-domain-factory-"*) continue' in android_preview_content
    assert "gh release create" in android_preview_content
    assert "gh release upload" in android_preview_content
    assert "gh run list" in android_preview_content
    assert "DEBUG_PREVIEW_SIGNING" not in android_preview_content
    assert "https://preview.nienfos.com/$SOURCE_APP/api" in android_preview_content
    assert "--dart-define=CODEX_APP_UPDATER_ENABLED=true" in android_preview_content
    assert '--dart-define=CODEX_APP_UPDATER_BRIDGE_URL="${BRIDGE_PUBLIC_URL:-${BRIDGE_URL:-}}"' in android_preview_content
    assert "BRIDGE_REGISTRATION_URL or BRIDGE_URL is required" in android_preview_content
    assert 'BRIDGE_URL="$bridge_registration_url"' in android_preview_content
    assert '"$HOME/.local/share/android-sdk"' in android_preview_content
    assert '[[ -d "$sdk_root/build-tools" ]] || continue' in android_preview_content
    assert "git push origin \"$tag\"" in android_preview_content
    assert android_preview_content.index(
        "Preview APK must not be signed with Android debug certificate"
    ) < android_preview_content.index('git push origin "$tag"')
    assert android_preview_content.index('"$apksigner" verify') < android_preview_content.index(
        'git push origin "$tag"'
    )
    assert "GitHub Actions Android preview workflow failed before producing" in (
        android_preview_content
    )
    register_script_content = (
        tmp_path / "clinica-norte/scripts/register_installable_app.sh"
    ).read_text(encoding="utf-8")
    assert 'BRIDGE_REGISTRATION_URL="${BRIDGE_REGISTRATION_URL:-}"' in (
        register_script_content
    )
    assert 'BRIDGE_URL="$BRIDGE_REGISTRATION_URL"' in register_script_content
    assert "BRIDGE_URL or BRIDGE_REGISTRATION_URL is required" in (
        register_script_content
    )
    env_loader_content = (
        tmp_path / "clinica-norte/scripts/load_bridge_env.sh"
    ).read_text(encoding="utf-8")
    assert '"$key" != PREVIEW_ADMIN_*' in env_loader_content
    gitignore_content = (tmp_path / "clinica-norte/.gitignore").read_text(
        encoding="utf-8"
    )
    assert "apps/mobile/.flutter-plugins-dependencies" in gitignore_content
    assert "apps/mobile/android/local.properties" in gitignore_content
    assert ".codex/factory/" in gitignore_content
    assert ".generated-validation/" in gitignore_content
    assert "backend/.venv/" in gitignore_content
    assert "backend/*.egg-info/" in gitignore_content
    initial_preview_validation = (
        tmp_path / "clinica-norte/scripts/validate_initial_preview_release.sh"
    ).read_text(encoding="utf-8")
    workflow_content = (
        tmp_path / "clinica-norte/.github/workflows/android-preview-release.yml"
    ).read_text(encoding="utf-8")
    assert "certificate SHA-256 digest/ { print $NF; exit }" in (
        initial_preview_validation
    )
    assert "certificate SHA-256 digest/ { print $NF; exit }" in workflow_content
    assert "certificate SHA-256 digest/ { print $2; exit }" not in (
        initial_preview_validation
    )
    assert "certificate SHA-256 digest/ { print $2; exit }" not in workflow_content

    android_release_script = tmp_path / "clinica-norte/scripts/publish_android_release.sh"
    assert android_release_script.is_file()
    assert android_release_script.stat().st_mode & stat.S_IXUSR
    android_release_content = android_release_script.read_text(encoding="utf-8")
    assert "apps/mobile/android is required" in android_release_content
    assert "API_BASE_URL is required for a real Android release" in android_release_content
    assert "GitHub Actions variable API_BASE_URL is not configured" in (
        android_release_content
    )
    assert "real Android release cannot use APP_RUNTIME_PROFILE=mock" in android_release_content
    assert "git push origin \"$tag\"" in android_release_content
    assert "GitHub release $tag did not expose an APK asset" in android_release_content

    release_profile_script = tmp_path / "clinica-norte/scripts/validate_release_profiles.sh"
    assert release_profile_script.is_file()
    assert release_profile_script.stat().st_mode & stat.S_IXUSR
    release_profile_content = release_profile_script.read_text(encoding="utf-8")
    assert "APP_RUNTIME_PROFILE" in release_profile_content
    assert "android-preview-v*" in release_profile_content
    assert "APP_RUNTIME_PROFILE=preview" in release_profile_content
    assert "android-mock-" in release_profile_content
    assert "productive android-v* tags cannot use" in release_profile_content
    assert "API_BASE_URL" in release_profile_content
    assert "codex-bridge.yaml" in release_profile_content
    preview_profile_script = (
        tmp_path / "clinica-norte/scripts/validate_preview_release_profiles.sh"
    )
    assert preview_profile_script.is_file()
    assert preview_profile_script.stat().st_mode & stat.S_IXUSR
    preview_profile_content = preview_profile_script.read_text(encoding="utf-8")
    assert "release/preview-runtime.json" in preview_profile_content
    assert "release/preview-signing-policy.json" in preview_profile_content
    assert "debugPreview signing policy is forbidden" in preview_profile_content
    assert "deploy/web-preview/web-preview-manifest.yaml" in preview_profile_content
    assert "scripts/validate_release_profiles.sh" in preview_profile_content

    d1_apply_script = tmp_path / "clinica-norte/scripts/apply_preview_d1_migrations.sh"
    assert d1_apply_script.is_file()
    assert d1_apply_script.stat().st_mode & stat.S_IXUSR
    d1_apply_content = d1_apply_script.read_text(encoding="utf-8")
    assert "wrangler d1 execute" in d1_apply_content
    assert "codex:d1:add-column" in (
        tmp_path
        / "clinica-norte/deploy/web-preview/d1/migrations/0003_preview_schema_evolution.sql"
    ).read_text(encoding="utf-8")
    assert "scripts/apply_preview_d1_migrations.sh" in (
        tmp_path / "clinica-norte/scripts/apply_cloudflare_preview.sh"
    ).read_text(encoding="utf-8")


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

    preview = subprocess.run(
        [str(script)],
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
    assert preview.returncode == 0, preview.stdout + preview.stderr
    assert "profile=preview" in preview.stdout

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


def test_generated_release_profile_script_rejects_bad_preview_contracts(
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
    cases = [
        (
            {
                "APP_RELEASE_TAG": "android-preview-v0.1.0-build.1",
                "APP_RUNTIME_PROFILE": "mock",
                "API_RUNTIME": "cloudflare_preview",
                "API_BASE_URL": "https://preview.nienfos.com/clinica-norte/api",
            },
            "android-preview-v* tags require APP_RUNTIME_PROFILE=preview",
        ),
        (
            {
                "APP_RELEASE_TAG": "android-preview-v0.1.0-build.1",
                "APP_RUNTIME_PROFILE": "preview",
                "API_RUNTIME": "cloudflare_preview",
                "API_BASE_URL": "http://127.0.0.1:8000",
            },
            "preview releases require API_BASE_URL=https://preview.nienfos.com/<slug>/api",
        ),
        (
            {
                "APP_RELEASE_TAG": "android-preview-v0.1.0-build.1",
                "APP_RUNTIME_PROFILE": "preview",
                "API_RUNTIME": "cloudflare_preview",
                "API_BASE_URL": "https://placeholder.invalid/api",
            },
            "preview releases require API_BASE_URL=https://preview.nienfos.com/<slug>/api",
        ),
        (
            {
                "APP_RELEASE_TAG": "android-preview-v0.1.0-build.1",
                "APP_RUNTIME_PROFILE": "preview",
                "API_RUNTIME": "cloudflare_preview",
                "API_BASE_URL": "https://preview.nienfos.com/clinica-norte/api",
                "LOCAL_DATA_MODE": "true",
            },
            "preview releases cannot use LOCAL_DATA_MODE=true",
        ),
    ]
    for env_overrides, expected in cases:
        completed = subprocess.run(
            [str(script)],
            cwd=project,
            env={**os.environ, **env_overrides},
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode != 0
        assert expected in completed.stdout + completed.stderr


def test_generated_android_preview_release_blocks_wrong_api_before_git_or_network(
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
    (project / "apps/mobile/android").mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["scripts/publish_android_preview_release.sh", "--push", "--watch"],
        cwd=project,
        env={
            **os.environ,
            "APP_RUNTIME_PROFILE": "preview",
            "API_RUNTIME": "cloudflare_preview",
            "API_BASE_URL": "https://example.com/clinica-norte/api",
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    output = completed.stdout + completed.stderr
    assert (
        "initial preview API must be https://preview.nienfos.com/clinica-norte/api"
        in output
    )
    assert "not inside a git repository" not in output
    assert not _git(["tag"], project).stdout.strip()


def test_generated_initial_preview_validation_flutter_has_no_optional_bypasses(
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

    script = (
        tmp_path / "clinica-norte/scripts/validate_initial_preview_release.sh"
    ).read_text(encoding="utf-8")
    forbidden_bypasses = [
        "RUN_BACKEND_TESTS",
        "RUN_FLUTTER_ANALYZE",
        "RUN_FLUTTER_TESTS",
        "RUN_LOCAL_APK_BUILD",
        "RUN_APKSIGNER_VERIFY",
        "RUN_INVITE_E2E",
        "SKIP_GITHUB_WORKFLOW_CHECK",
    ]
    for bypass in forbidden_bypasses:
        assert bypass not in script
    assert "release/initial-preview-validation-report.json" in script


def test_generated_preview_api_smoke_retries_until_assets_bound(
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

    smoke_script = (
        tmp_path / "clinica-norte/scripts/smoke_preview_api.sh"
    ).read_text(encoding="utf-8")
    python_source = smoke_script.split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]

    class Handler(BaseHTTPRequestHandler):
        health_calls = 0

        def _write(self, status: int, payload: dict[str, object]) -> None:
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                type(self).health_calls += 1
                self._write(
                    200,
                    {
                        "runtime": "cloudflare_preview",
                        "source_app": "clinica-norte",
                        "d1_bound": True,
                        "assets_bound": type(self).health_calls >= 2,
                    },
                )
                return
            if self.path == "/auth/me":
                self._write(200, {"sourceApp": "clinica-norte"})
                return
            if self.path == "/business/records":
                self._write(
                    200,
                    {
                        "records": [
                            {
                                "sourceApp": "clinica-norte",
                                "appSlug": "clinica-norte",
                            }
                        ]
                    },
                )
                return
            if self.path == "/notifications":
                self._write(200, {"notifications": []})
                return
            if self.path == "/app-updates/current":
                self._write(
                    200,
                    {"releaseChannel": "prerelease", "mockOrDemo": False},
                )
                return
            self._write(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path == "/auth/login":
                self._write(200, {"access_token": "token"})
                return
            if self.path == "/business/records":
                self._write(
                    201,
                    {"sourceApp": "clinica-norte", "appSlug": "clinica-norte"},
                )
                return
            self._write(404, {"error": "not found"})

        def log_message(self, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                python_source,
                f"http://127.0.0.1:{server.server_port}",
                "clinica-norte",
                "test-agent",
            ],
            env={
                **os.environ,
                "PREVIEW_ADMIN_EMAIL": "admin@example.test",
                "PREVIEW_ADMIN_PASSWORD": "password",
                "PREVIEW_ADMIN_BOOTSTRAP_TOKEN": "",
            },
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "preview api smoke passed" in completed.stdout
    assert Handler.health_calls == 2


def test_android_preview_release_ignores_domain_factory_specs_dirty_state(
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
    domain_spec = project / "specs/019-domain-factory-abc123/spec.md"
    domain_spec.parent.mkdir(parents=True)
    domain_spec.write_text("# Domain Factory draft\n", encoding="utf-8")
    assert "?? specs/019-domain-factory-abc123/" in _git(
        ["status", "--porcelain"],
        project,
    ).stdout

    publish_script = (
        project / "scripts/publish_android_preview_release.sh"
    ).read_text(encoding="utf-8")
    function_source = _extract_shell_function(
        publish_script,
        "preview_release_blocking_git_status",
    )
    completed = subprocess.run(
        [
            "bash",
            "-c",
            f"{function_source}\npreview_release_blocking_git_status",
        ],
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""


def test_android_preview_release_ignores_gradle_kotlin_dirty_state(
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
    kotlin_state = project / "apps/mobile/android/.kotlin/build-history.bin"
    kotlin_state.parent.mkdir(parents=True)
    kotlin_state.write_text("gradle kotlin state\n", encoding="utf-8")

    assert (project / "apps/mobile/android/.gitignore").read_text(
        encoding="utf-8",
    ).splitlines() == ["upload-keystore.jks", "key.properties", ".kotlin/"]
    assert ".kotlin" not in _git(["status", "--porcelain"], project).stdout

    publish_script = (
        project / "scripts/publish_android_preview_release.sh"
    ).read_text(encoding="utf-8")
    function_source = _extract_shell_function(
        publish_script,
        "preview_release_blocking_git_status",
    )
    completed = subprocess.run(
        [
            "bash",
            "-c",
            f"{function_source}\npreview_release_blocking_git_status",
        ],
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""


def test_generated_initial_preview_validation_runs_all_flutter_checks(
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
    _git(
        ["remote", "add", "origin", "https://github.com/acme/clinica-norte.git"],
        project,
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    command_log, bridge_root = _write_initial_preview_gate_fakes(
        project,
        fake_bin,
        tmp_path,
    )
    _git(["add", "scripts/smoke_preview_api.sh"], project)
    _git(["add", "scripts/smoke_web_preview.sh"], project)
    _git(["add", "scripts/final_readiness_audit.sh"], project)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.test",
            "-c",
            "user.name=Test",
            "commit",
            "-m",
            "Install fake validation hooks",
        ],
        cwd=project,
        text=True,
        capture_output=True,
        check=True,
    )

    fixed_timestamp = "2026-07-10T00:00:00Z"
    seed_report = tmp_path / "seed-initial-preview-validation-report.json"
    seed = subprocess.run(
        ["scripts/validate_initial_preview_release.sh"],
        cwd=project,
        env=_initial_preview_env(
            {
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "COMMAND_LOG": str(command_log),
                "CODEX_MOBILE_BRIDGE_ROOT": str(bridge_root),
                "CHECK_TIMESTAMP": fixed_timestamp,
                "CHECK_REPORT_JSON": str(seed_report),
            }
        ),
        text=True,
        capture_output=True,
        check=False,
    )
    assert seed.returncode == 0, seed.stdout + seed.stderr
    shutil.copyfile(
        seed_report,
        project / "release/initial-preview-validation-report.json",
    )
    _git(["add", "release/initial-preview-validation-report.json"], project)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.test",
            "-c",
            "user.name=Test",
            "commit",
            "-m",
            "Commit initial preview validation report",
        ],
        cwd=project,
        text=True,
        capture_output=True,
        check=True,
    )

    completed = subprocess.run(
        ["scripts/validate_initial_preview_release.sh"],
        cwd=project,
        env=_initial_preview_env(
            {
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "COMMAND_LOG": str(command_log),
                "CODEX_MOBILE_BRIDGE_ROOT": str(bridge_root),
                "CHECK_TIMESTAMP": fixed_timestamp,
            }
        ),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(
        (project / "release/initial-preview-validation-report.json").read_text(
            encoding="utf-8",
        )
    )
    statuses = {item["name"]: item["status"] for item in report["checks"]}
    mandatory = [
        "backend tests",
        "Flutter analyze",
        "Flutter tests",
        "APK local build",
        "apksigner verify",
        "D1 migration apply",
        "Cloudflare preview health",
        "web preview smoke",
        "API preview smoke",
        "Factory invite validation",
        "GitHub Android release workflow",
        "GitHub release asset exists",
        "Bridge registration real",
        "APK SHA256",
        "final readiness audit",
        "clean git status",
        "validate_initial_preview_release.sh",
    ]
    for check_name in mandatory:
        assert statuses[check_name] == "passed"
    assert "skipped_with_reason" not in statuses.values()
    assert _git(["status", "--porcelain"], project).stdout == ""
    log = command_log.read_text(encoding="utf-8")
    assert "backend tests" in log
    assert "flutter analyze" in log
    assert "flutter test" in log
    assert "flutter build apk" in log
    assert "apksigner verify" in log
    assert "wrangler" in log
    assert "invite e2e" in log


@pytest.mark.parametrize(
    "apksigner_certificate_output",
    [
        (
            "Signer #1 certificate SHA-256 digest: "
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
            "Signer #1 certificate DN: CN=Clinica Norte Preview Upload"
        ),
        (
            "V2 Signer: certificate SHA-256 digest: "
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
            "V2 Signer: certificate DN: CN=Clinica Norte Preview Upload"
        ),
    ],
)
def test_generated_initial_preview_validation_parses_apksigner_sha_formats(
    tmp_path: Path,
    apksigner_certificate_output: str,
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
    _git(["remote", "add", "origin", "https://github.com/acme/clinica-norte.git"], project)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    command_log, bridge_root = _write_initial_preview_gate_fakes(
        project,
        fake_bin,
        tmp_path,
        apksigner_certificate_output=apksigner_certificate_output,
    )
    _git(["add", "scripts/smoke_preview_api.sh"], project)
    _git(["add", "scripts/smoke_web_preview.sh"], project)
    _git(["add", "scripts/final_readiness_audit.sh"], project)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.test",
            "-c",
            "user.name=Test",
            "commit",
            "-m",
            "Install fake validation hooks",
        ],
        cwd=project,
        text=True,
        capture_output=True,
        check=True,
    )

    report_path = tmp_path / "apksigner-format-report.json"
    completed = subprocess.run(
        ["scripts/validate_initial_preview_release.sh"],
        cwd=project,
        env=_initial_preview_env(
            {
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "COMMAND_LOG": str(command_log),
                "CODEX_MOBILE_BRIDGE_ROOT": str(bridge_root),
                "CHECK_TIMESTAMP": "2026-07-10T00:00:00Z",
                "CHECK_REPORT_JSON": str(report_path),
            }
        ),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    signer_check = next(
        item
        for item in report["checks"]
        if item["name"] == "apksigner signer SHA256"
    )
    assert signer_check["status"] == "passed"
    assert (
        signer_check["detail"]
        == "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    )


def test_generated_initial_preview_validation_fails_when_report_dirties_git(
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
    _git(["remote", "add", "origin", "https://github.com/acme/clinica-norte.git"], project)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    command_log, bridge_root = _write_initial_preview_gate_fakes(
        project,
        fake_bin,
        tmp_path,
    )
    _git(["add", "scripts/smoke_preview_api.sh"], project)
    _git(["add", "scripts/smoke_web_preview.sh"], project)
    _git(["add", "scripts/final_readiness_audit.sh"], project)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.test",
            "-c",
            "user.name=Test",
            "commit",
            "-m",
            "Install fake validation hooks",
        ],
        cwd=project,
        text=True,
        capture_output=True,
        check=True,
    )

    completed = subprocess.run(
        ["scripts/validate_initial_preview_release.sh"],
        cwd=project,
        env=_initial_preview_env(
            {
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "COMMAND_LOG": str(command_log),
                "CODEX_MOBILE_BRIDGE_ROOT": str(bridge_root),
                "CHECK_TIMESTAMP": "2026-07-10T00:00:00Z",
            }
        ),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    report_path = project / "release/initial-preview-validation-report.json"
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    statuses = {item["name"]: item["status"] for item in report["checks"]}
    assert statuses["clean git status"] == "failed"
    assert statuses["validate_initial_preview_release.sh"] == "failed"
    assert "?? release/initial-preview-validation-report.json" in _git(
        ["status", "--porcelain"],
        project,
    ).stdout
    assert "one or more required checks failed" in completed.stdout + completed.stderr


def test_generated_initial_preview_validation_reports_failed_flutter_check(
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
    _git(["remote", "add", "origin", "https://github.com/acme/clinica-norte.git"], project)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    command_log, bridge_root = _write_initial_preview_gate_fakes(
        project,
        fake_bin,
        tmp_path,
    )

    completed = subprocess.run(
        ["scripts/validate_initial_preview_release.sh"],
        cwd=project,
        env=_initial_preview_env(
            {
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "COMMAND_LOG": str(command_log),
                "CODEX_MOBILE_BRIDGE_ROOT": str(bridge_root),
                "FAIL_FLUTTER_ANALYZE": "true",
            }
        ),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    report = json.loads(
        (project / "release/initial-preview-validation-report.json").read_text(
            encoding="utf-8",
        )
    )
    statuses = {item["name"]: item["status"] for item in report["checks"]}
    assert statuses["Flutter analyze"] == "failed"
    assert statuses["validate_initial_preview_release.sh"] == "failed"
    assert "one or more required checks failed" in completed.stdout + completed.stderr


def test_generated_initial_preview_validation_rejects_bad_bridge_registration(
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
    _git(["remote", "add", "origin", "https://github.com/acme/clinica-norte.git"], project)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    command_log, bridge_root = _write_initial_preview_gate_fakes(
        project,
        fake_bin,
        tmp_path,
    )
    fake_curl = fake_bin / "curl"
    cases = [
        (
            {
                "releaseChannel": "stable",
                "releaseTagPattern": "android-preview-v*",
                "previewUrl": "https://preview.nienfos.com/clinica-norte",
                "runtimeProfile": "preview",
                "productionReady": False,
                "mockOrDemo": False,
            },
            "Bridge registration is not prerelease channel",
        ),
        (
            {
                "releaseChannel": "prerelease",
                "releaseTagPattern": "android-v*",
                "previewUrl": "https://preview.nienfos.com/clinica-norte",
                "runtimeProfile": "preview",
                "productionReady": False,
                "mockOrDemo": False,
            },
            "Bridge registration does not use android-preview-v*",
        ),
        (
            {
                "releaseChannel": "prerelease",
                "releaseTagPattern": "android-preview-v*",
                "previewUrl": "https://preview.nienfos.com/clinica-norte",
                "runtimeProfile": "preview",
                "productionReady": True,
                "mockOrDemo": False,
            },
            "Bridge registration productionReady must be false",
        ),
        (
            {
                "releaseChannel": "prerelease",
                "releaseTagPattern": "android-preview-v*",
                "previewUrl": "https://preview.nienfos.com/clinica-norte",
                "runtimeProfile": "preview",
                "productionReady": False,
                "mockOrDemo": True,
            },
            "Bridge registration mockOrDemo must be false",
        ),
    ]
    for payload, expected in cases:
        detail = {
            "sourceApp": "clinica-norte",
            "available": True,
            "releaseTag": "android-preview-v0.1.0-build.1",
            "apkUrl": "https://bridge/apk",
            "sha256": "0" * 64,
            "latestBuild": {"releaseTag": "android-preview-v0.1.0-build.1"},
            **payload,
        }
        fake_curl.write_text(
            "#!/usr/bin/env bash\n"
            "cat <<'JSON'\n"
            f"{json.dumps(detail)}\n"
            "JSON\n",
            encoding="utf-8",
        )
        fake_curl.chmod(0o755)

        completed = subprocess.run(
            ["scripts/validate_initial_preview_release.sh"],
            cwd=project,
            env=_initial_preview_env(
                {
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "COMMAND_LOG": str(command_log),
                    "CODEX_MOBILE_BRIDGE_ROOT": str(bridge_root),
                }
            ),
            text=True,
            capture_output=True,
            check=False,
        )

        assert completed.returncode != 0
        assert expected in completed.stdout + completed.stderr


def test_generated_initial_preview_validation_checks_expected_apk_sha256(
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
    _git(["remote", "add", "origin", "https://github.com/acme/clinica-norte.git"], project)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    command_log, bridge_root = _write_initial_preview_gate_fakes(
        project,
        fake_bin,
        tmp_path,
    )
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        "#!/usr/bin/env bash\n"
        "args=\"$*\"\n"
        "if [[ \"$args\" == *'https://bridge.test/apk'* ]]; then\n"
        "  out=/tmp/project-factory-preview.apk\n"
        "  while [[ $# -gt 0 ]]; do\n"
        "    if [[ \"$1\" == '-o' ]]; then out=\"$2\"; shift 2; else shift; fi\n"
        "  done\n"
        "  printf 'real-apk-bytes' > \"$out\"\n"
        "  exit 0\n"
        "fi\n"
        "cat <<'JSON'\n"
        '{"sourceApp":"clinica-norte","releaseChannel":"prerelease",'
        '"releaseTagPattern":"android-preview-v*",'
        '"releaseTag":"android-preview-v0.1.0-build.1","available":true,'
        '"previewUrl":"https://preview.nienfos.com/clinica-norte",'
        '"runtimeProfile":"preview","productionReady":false,'
        '"mockOrDemo":false,"apkUrl":"https://bridge.test/apk",'
        '"sha256":"' + ("0" * 64) + '","latestBuild":{"releaseTag":"android-preview-v0.1.0-build.1"}}\n'
        "JSON\n",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)

    completed = subprocess.run(
        ["scripts/validate_initial_preview_release.sh"],
        cwd=project,
        env=_initial_preview_env(
            {
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "COMMAND_LOG": str(command_log),
                "CODEX_MOBILE_BRIDGE_ROOT": str(bridge_root),
                "EXPECTED_SHA256": "0" * 64,
            }
        ),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "Preview APK checksum does not match EXPECTED_SHA256" in (
        completed.stdout + completed.stderr
    )
    assert "verifying preview APK bytes with EXPECTED_SHA256 via download" in (
        completed.stdout + completed.stderr
    )


def test_generated_preview_release_shell_and_workflow_syntax(tmp_path: Path) -> None:
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
    scripts = [
        "scripts/apply_cloudflare_preview.sh",
        "scripts/smoke_preview_api.sh",
        "scripts/publish_android_preview_release.sh",
        "scripts/register_installable_app.sh",
        "scripts/validate_initial_preview_release.sh",
        "scripts/validate_publication_ready.sh",
        "scripts/validate_release_profiles.sh",
        "scripts/validate_preview_release_profiles.sh",
    ]
    for script in scripts:
        completed = subprocess.run(
            ["bash", "-n", script],
            cwd=project,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr

    yaml = pytest.importorskip("yaml")
    for workflow in [
        ".github/workflows/android-preview-release.yml",
        ".github/workflows/android-release.yml",
    ]:
        payload = yaml.safe_load((project / workflow).read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        assert "jobs" in payload


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
    preview_workflow = (
        tmp_path / "clinica-norte/.github/workflows/android-preview-release.yml"
    ).read_text(encoding="utf-8")
    assert 'default: "real"' in workflow
    assert "APP_RUNTIME_PROFILE:" in workflow
    assert "github.event.inputs.runtime_profile" in workflow
    assert "|| 'real'" in workflow
    assert "android-mock-v*" in workflow
    assert 'LOCAL_DATA_MODE: "false"' in workflow
    assert 'args+=(--dart-define=APP_RUNTIME_PROFILE="$APP_RUNTIME_PROFILE")' in workflow
    assert 'args+=(--dart-define=API_BASE_URL="$API_BASE_URL")' in workflow
    assert '"android-preview-v*"' in preview_workflow
    assert "APP_RUNTIME_PROFILE: preview" in preview_workflow
    assert "API_RUNTIME: cloudflare_preview" in preview_workflow
    assert '--dart-define=API_BASE_URL="$API_BASE_URL"' in preview_workflow
    assert "prerelease: true" in preview_workflow


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
    preview_runtime = json.loads(
        (project / "release/preview-runtime.json").read_text(encoding="utf-8")
    )
    promotion = json.loads(
        (project / "release/promotion-contract.json").read_text(encoding="utf-8")
    )
    cost_posture = json.loads(
        (project / "release/cloudflare-cost-posture.json").read_text(encoding="utf-8")
    )
    signing_policy = json.loads(
        (project / "release/preview-signing-policy.json").read_text(
            encoding="utf-8"
        )
    )
    runtime_doc = (project / "release/runtime-profiles.md").read_text(
        encoding="utf-8"
    )
    promotion_doc = (project / "release/promotion-runbook.md").read_text(
        encoding="utf-8"
    )
    signing_doc = (project / "release/android-preview-signing.md").read_text(
        encoding="utf-8"
    )
    operations_doc = (project / "release/preview-operations-runbook.md").read_text(
        encoding="utf-8"
    )
    false_ready_doc = (project / "release/false-readiness-runbook.md").read_text(
        encoding="utf-8"
    )
    aws_doc = (project / "release/aws-domain-delegation-runbook.md").read_text(
        encoding="utf-8"
    )
    email_doc = (project / "release/email-provider-runbook.md").read_text(
        encoding="utf-8"
    )
    dns_doc = (project / "release/dns-cloudflare-troubleshooting.md").read_text(
        encoding="utf-8"
    )
    bridge = (project / "codex-bridge.yaml").read_text(encoding="utf-8")
    workbench = (project / "docs/workbench.md").read_text(encoding="utf-8")

    assert "runtime_profiles:" in contracts
    assert "initial_preview_release:" in contracts
    assert "productive_release:" in contracts
    assert "mock_release:" in contracts
    assert "opt_in: true" in contracts
    assert "required: false" in contracts
    assert "codex_mobile_catalog:" in contracts
    assert "scripts/register_installable_app.sh" in contracts
    assert "web_preview:" in contracts
    assert "scripts/validate_web_preview.sh" in contracts
    assert "preview_to_production_promotion:" in contracts
    assert "release/promotion-contract.json" in contracts
    assert "cloudflare_cost_posture:" in contracts
    assert "scripts/validate_cloudflare_cost_posture.sh" in contracts
    assert "https://preview.nienfos.com/clinica-norte/api" in contracts
    assert preview_runtime["sourceApp"] == "clinica-norte"
    assert preview_runtime["previewUrl"] == "https://preview.nienfos.com/clinica-norte"
    assert preview_runtime["apiBaseUrl"] == (
        "https://preview.nienfos.com/clinica-norte/api"
    )
    assert preview_runtime["runtimeProfile"] == "preview"
    assert preview_runtime["apiRuntime"] == "cloudflare_preview"
    assert preview_runtime["releaseChannel"] == "prerelease"
    assert preview_runtime["releaseTagPattern"] == "android-preview-v*"
    assert preview_runtime["productionReady"] is False
    assert preview_runtime["mockOrDemo"] is False
    assert promotion["initialPreview"]["productionReady"] is False
    assert promotion["initialPreview"]["tagPattern"] == "android-preview-v*"
    assert promotion["productionPromotion"]["tagPattern"] == "android-v*"
    assert promotion["productionPromotion"]["runtimeProfile"] == "real"
    assert promotion["mockDemo"]["tagPatterns"] == [
        "android-mock-v*",
        "android-local-v*",
    ]
    assert cost_posture["policy"] == "free_compatible"
    assert cost_posture["paidResourcesAllowed"] is False
    assert all(item["paid"] is False for item in cost_posture["resources"])
    assert signing_policy["defaultSigningMode"] == "preview"
    assert "debugPreview" not in signing_policy
    assert signing_policy["productionReady"] is False
    assert signing_policy["mockOrDemo"] is False
    assert "APP_RUNTIME_PROFILE=real" in runtime_doc
    assert "APP_RUNTIME_PROFILE=preview" in runtime_doc
    assert "android-preview-vX.Y.Z-build.N" in runtime_doc
    assert "android-mock-vX.Y.Z-build.N" in runtime_doc
    assert "Mock/demo releases are never part of the default initial release" in (
        runtime_doc
    )
    assert "android-v<version>" in promotion_doc
    assert "Never reuse preview or mock APKs for production" in promotion_doc
    assert "productionReady=false" in signing_doc
    assert "release/preview-signing-policy.json" in signing_doc
    assert "Debug signing is forbidden" in signing_doc
    assert "scripts/validate_cloudflare_cost_posture.sh" in operations_doc
    assert "aws route53domains get-domain-detail" in aws_doc
    assert "AutoRenew" in aws_doc
    assert "WEB_PREVIEW_EMAIL_PROVIDER=cloudflare_email" in email_doc
    assert "deploy/cloudflare-email-endpoint" in email_doc
    assert "wrangler secret put EMAIL_ENDPOINT_TOKEN" in email_doc
    assert "Cloudflare Workers Free can host this endpoint" in email_doc
    assert "Native Cloudflare Email" in email_doc
    assert "Service sending to arbitrary invite recipients requires Workers Paid" in (
        " ".join(email_doc.split())
    )
    assert "Amazon SES SMTP profile" in email_doc
    assert "email-smtp.us-east-1.amazonaws.com" in email_doc
    assert "Request SES production access" in email_doc
    assert "WEB_PREVIEW_SMTP_IMPLICIT_TLS=false" in email_doc
    assert "manual_delivery_required=true" in email_doc
    assert "CLOUDFLARE_DNS_API_TOKEN" in dns_doc
    assert "dig +trace preview.nienfos.com" in dns_doc
    assert "False Readiness Examples" in false_ready_doc
    assert "sourceApp: clinica-norte" in bridge
    assert "workbench-sdd/v1" in bridge
    assert "APP_RUNTIME_PROFILE=real" in workbench
    assert "no `Workbench` item" in workbench
    assert "Bridge-owned entry point" in workbench


def test_generated_cloudflare_cost_posture_script_blocks_paid_resources(
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
    script = project / "scripts/validate_cloudflare_cost_posture.sh"
    assert script.is_file()
    assert script.stat().st_mode & stat.S_IXUSR
    assert "scripts/validate_cloudflare_cost_posture.sh" in (
        project / "scripts/apply_cloudflare_preview.sh"
    ).read_text(encoding="utf-8")
    apply_script = (project / "scripts/apply_cloudflare_preview.sh").read_text(
        encoding="utf-8"
    )
    assert '"active"' in apply_script
    assert "cloudflare preview recovery" in apply_script

    completed = subprocess.run(
        ["scripts/validate_cloudflare_cost_posture.sh"],
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "cloudflare cost posture ok" in completed.stdout

    report_path = project / "release/cloudflare-cost-posture.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["paidResourcesAllowed"] = True
    report["resources"].append({"type": "r2", "name": "paid-assets", "paid": True})
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    blocked = subprocess.run(
        ["scripts/validate_cloudflare_cost_posture.sh"],
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
    )
    assert blocked.returncode != 0
    assert "CLOUDFLARE_PAID_RESOURCES_CONFIRMED=true" in blocked.stderr

    confirmed = subprocess.run(
        ["scripts/validate_cloudflare_cost_posture.sh"],
        cwd=project,
        env={
            **os.environ,
            "CLOUDFLARE_PAID_RESOURCES_CONFIRMED": "true",
            "CLOUDFLARE_PAID_RESOURCES_REASON": "operator accepted R2 preview cost",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert confirmed.returncode == 0, confirmed.stdout + confirmed.stderr


def test_generated_business_records_d1_migration_is_app_scoped_and_idempotent(
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
    assert not (
        project / "deploy/web-preview/d1/migrations/0002_domain_entities.sql"
    ).exists()
    sql = (
        project / "deploy/web-preview/d1/migrations/0002_business_records.sql"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS preview_business_record_events" in sql
    assert "source_app TEXT NOT NULL" in sql
    assert "app_slug TEXT NOT NULL" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_preview_business_record_events_app_record" in sql
    assert "preview_domain_" not in sql


def test_generated_project_has_no_stale_domain_contract(
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
    generated_text = _read_all_text(project)
    stale_patterns = [
        "preview_domain_",
        "handlePreviewDomain",
        "0002_domain_entities",
        "domain CRUD",
        "domain-management",
        "domain management",
        "/api/domain",
        "/admin/domains",
        "/domains",
        "domain_name",
        "adminDomain",
        "adminDomains",
        "Domain Management",
        "Domain features",
        "domain UX",
        "domain-specific resources",
        "domain-specific workflows",
        "api --> domain",
        "domain --> db",
        "domain[",
    ]
    for pattern in stale_patterns:
        assert pattern not in generated_text
    assert "preview_business_records" in generated_text
    assert "business_records" in generated_text
    assert "business-records" in generated_text
    components = (project / "architecture/components.mmd").read_text(
        encoding="utf-8"
    )
    assert "businessRecords[Business Records]" in components
    assert "api --> businessRecords" in components
    assert "businessRecords --> db" in components


def test_generated_apply_preview_d1_migrations_blocks_and_reapplies_safely(
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
    blocked = subprocess.run(
        ["scripts/apply_preview_d1_migrations.sh"],
        cwd=project,
        env={
            **os.environ,
            "CODEX_MOBILE_BRIDGE_ROOT": str(tmp_path / "empty-bridge-root"),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert blocked.returncode == 2
    assert "PREVIEW_D1_DATABASE" in blocked.stderr

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "wrangler-calls.log"
    fake_wrangler = fake_bin / "wrangler"
    fake_wrangler.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$WRANGLER_CALLS\"\n"
        "if [[ \"$*\" == *'--json'* ]]; then printf '[]\\n'; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_wrangler.chmod(0o755)

    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "WRANGLER_CALLS": str(calls),
        "PREVIEW_D1_DATABASE": "preview-db",
        "WRANGLER_AUTH_READY": "true",
        "CODEX_MOBILE_BRIDGE_ROOT": str(tmp_path / "empty-bridge-root"),
    }
    first = subprocess.run(
        ["scripts/apply_preview_d1_migrations.sh"],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    second = subprocess.run(
        ["scripts/apply_preview_d1_migrations.sh"],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    lines = calls.read_text(encoding="utf-8").splitlines()
    assert any("--command PRAGMA table_info(preview_invites)" in line for line in lines)
    assert any("ALTER TABLE preview_invites ADD COLUMN email TEXT" in line for line in lines)
    assert any(line.startswith("d1 execute preview-db --remote --file") for line in lines)
    assert any("0001_preview_invites.sql" in line for line in lines)
    assert any("0002_business_records.sql" in line for line in lines)
    assert not any("0002_domain_entities.sql" in line for line in lines)


def test_generated_preview_signing_policy_blocks_debug_without_metadata(
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
    policy = json.loads(
        (project / "release/preview-signing-policy.json").read_text(
            encoding="utf-8"
        )
    )
    assert policy["defaultSigningMode"] == "preview"
    assert "debugPreview" not in policy

    validator = (project / "scripts/validate_preview_release_profiles.sh").read_text(
        encoding="utf-8"
    )
    assert "DEBUG_PREVIEW_SIGNING" not in validator

    accepted = subprocess.run(
        ["scripts/validate_preview_release_profiles.sh"],
        cwd=project,
        env={
            **os.environ,
            "APP_RELEASE_TAG": "android-preview-v0.1.0-build.1",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr


def test_generated_preview_signing_policy_rejects_explicit_debug_preview(
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
    policy_path = project / "release/preview-signing-policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["debugPreview"] = {"enabled": True}
    policy_path.write_text(json.dumps(policy, indent=2), encoding="utf-8")

    rejected = subprocess.run(
        ["scripts/validate_preview_release_profiles.sh"],
        cwd=project,
        env={
            **os.environ,
            "APP_RELEASE_TAG": "android-preview-v0.1.0-build.1",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode != 0
    assert "debugPreview signing policy is forbidden" in rejected.stderr

    wrong_tag = subprocess.run(
        ["scripts/validate_preview_release_profiles.sh"],
        cwd=project,
        env={
            **os.environ,
            "APP_RELEASE_TAG": "android-v0.1.0-build.1",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert wrong_tag.returncode != 0
    assert "debugPreview signing policy is forbidden" in wrong_tag.stderr


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
    assert "RUNTIME_CONTRACT=\"$ROOT_DIR/release/preview-runtime.json\"" in content
    assert "RT_SOURCE_APP" in content
    assert 'SOURCE_APP="${SOURCE_APP:-${RT_SOURCE_APP:-clinica-norte}}"' in content
    assert (
        'DISPLAY_NAME="${DISPLAY_NAME:-${RT_DISPLAY_NAME:-Clinica Norte Preview}}"'
        in content
    )
    assert 'BRIDGE_URL="${BRIDGE_URL:-}"' in content
    assert 'BRIDGE_PUBLIC_URL="${BRIDGE_PUBLIC_URL:-}"' in content
    assert 'BRIDGE_PUBLIC_URL="${BRIDGE_PUBLIC_URL:-$BRIDGE_URL}"' in content
    assert 'bridge_detail_headers+=(-H "Host: $public_host")' in content
    assert (
        'bridge_detail_headers+=(-H "X-Forwarded-Proto: $public_scheme")'
        in content
    )
    assert "BRIDGE_REGISTRATION_TOKEN" in content
    assert (
        'RELEASE_TAG_PATTERN="${RELEASE_TAG_PATTERN:-${RT_RELEASE_TAG_PATTERN:-android-preview-v*}}"'
        in content
    )
    assert 'RELEASE_CHANNEL="${RELEASE_CHANNEL:-${RT_RELEASE_CHANNEL:-prerelease}}"' in content
    assert (
        'PREVIEW_URL="${PREVIEW_URL:-${RT_PREVIEW_URL:-https://preview.nienfos.com/clinica-norte}}"'
        in content
    )
    assert 'RUNTIME_PROFILE="${RUNTIME_PROFILE:-${RT_RUNTIME_PROFILE:-preview}}"' in content
    assert (
        'PRODUCTION_READY="${PRODUCTION_READY:-${RT_PRODUCTION_READY:-false}}"'
        in content
    )
    assert 'MOCK_OR_DEMO="${MOCK_OR_DEMO:-${RT_MOCK_OR_DEMO:-false}}"' in content
    assert '"previewUrl": os.environ["PREVIEW_URL"]' in content
    assert '"productionReady": os.environ.get("PRODUCTION_READY"' in content
    assert '"mockOrDemo": os.environ.get("MOCK_OR_DEMO"' in content
    assert "--dry-run" in content
    assert "gh release view" in content
    assert 'POST "$BRIDGE_URL/installable-apps"' in content
    assert 'Authorization: Bearer $BRIDGE_REGISTRATION_TOKEN' in content
    assert 'installable-apps/$SOURCE_APP' in content
    assert "curl -fsSI" in content
    assert "apk_proxy_deadline" in content
    assert 'local_apk_url="$BRIDGE_URL${apk_url#"$BRIDGE_PUBLIC_URL"}"' in content
    assert "Bridge APK proxy verified through local bridge transport" in content
    assert "REQUIRE_INSTALLABLE_APK" in content

    readme = (project / "README.md").read_text(encoding="utf-8")
    assert "scripts/register_installable_app.sh" in readme
    assert "BRIDGE_REGISTRATION_TOKEN=<token>" in readme
    assert "/installable-apps/{sourceApp}" in readme


def test_generated_register_installable_app_script_dry_run_uses_release_asset(
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
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_fake_github_access_tools(fake_bin)

    completed = subprocess.run(
        ["scripts/register_installable_app.sh", "--dry-run"],
        cwd=project,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "BRIDGE_URL": "http://bridge.test",
            "BRIDGE_REGISTRATION_TOKEN": "token",
                "GITHUB_REPO": "brunojaime/clinica-norte",
                "APP_RELEASE_TAG": "android-preview-v0.1.0-build.1",
                "LATEST_ASSET_NAME": "clinica-norte.apk",
                "CODEX_MOBILE_BRIDGE_ROOT": str(tmp_path / "empty-bridge-root"),
            },
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert '"sourceApp": "clinica-norte"' in completed.stdout
    assert '"latestAssetName": "clinica-norte.apk"' in completed.stdout
    assert '"previewUrl": "https://preview.nienfos.com/clinica-norte"' in (
        completed.stdout
    )
    assert '"runtimeProfile": "preview"' in completed.stdout
    assert '"productionReady": false' in completed.stdout
    assert '"mockOrDemo": false' in completed.stdout
    assert "dry-run: release and asset were verified" in completed.stdout


def test_generated_register_installable_app_script_posts_preview_metadata(
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
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_fake_github_access_tools(fake_bin)
    curl_calls = tmp_path / "curl-calls.txt"
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$CURL_CALLS_FILE\"\n"
        "args=\"$*\"\n"
        "if [[ \"$args\" == *'https://bridge.test/apk'* ]]; then\n"
        "  echo 'Could not resolve host: bridge.test' >&2\n"
        "  exit 6\n"
        "fi\n"
        "if [[ \"$args\" == *'http://localhost:8000/apk'* ]]; then\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$args\" == *'-I'* ]]; then exit 0; fi\n"
        "if [[ \"$args\" == *'/installable-apps/clinica-norte'* ]]; then\n"
        "  cat <<'JSON'\n"
        '{"sourceApp":"clinica-norte","displayName":"Clinica Norte Preview",'
        '"releaseChannel":"prerelease","releaseTagPattern":"android-preview-v*",'
        '"releaseTag":"android-preview-v0.1.0-build.1","available":true,'
        '"latestAssetName":"clinica-norte.apk",'
        '"previewUrl":"https://preview.nienfos.com/clinica-norte",'
        '"runtimeProfile":"preview","productionReady":false,'
        '"mockOrDemo":false,"apkUrl":"https://bridge.test/apk",'
        '"sha256":"' + ("0" * 64) + '","latestBuild":{"releaseTag":"android-preview-v0.1.0-build.1"},'
        '"installStatusHint":"available"}\n'
        "JSON\n"
        "  exit 0\n"
        "fi\n"
        "cat <<'JSON'\n"
        '{"sourceApp":"clinica-norte","displayName":"Clinica Norte Preview"}\n'
        "JSON\n",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)

    completed = subprocess.run(
        ["scripts/register_installable_app.sh"],
        cwd=project,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "BRIDGE_URL": "http://localhost:8000",
                "BRIDGE_PUBLIC_URL": "https://bridge.test",
                "BRIDGE_REGISTRATION_TOKEN": "token",
                "GITHUB_REPO": "brunojaime/clinica-norte",
                "APP_RELEASE_TAG": "android-preview-v0.1.0-build.1",
                "CODEX_MOBILE_BRIDGE_ROOT": str(tmp_path / "empty-bridge-root"),
                "CURL_CALLS_FILE": str(curl_calls),
            },
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "registered installable app: clinica-norte -> Clinica Norte Preview" in (
        completed.stdout
    )
    assert "apk url: https://bridge.test/apk" in completed.stdout
    assert (
        "Bridge APK proxy verified through local bridge transport for public APK URL: "
        "https://bridge.test/apk"
    ) in completed.stdout
    calls = curl_calls.read_text(encoding="utf-8")
    assert "Host: bridge.test" in calls
    assert "X-Forwarded-Proto: https" in calls
    assert "http://localhost:8000/apk" in calls
    assert "https://bridge.test/apk" not in calls


def test_generator_refreshes_managed_factory_scripts(
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
    service = ProjectFactoryGeneratorService()
    service.generate(manifest_plan)

    project = tmp_path / "clinica-norte"
    script = project / "scripts/register_installable_app.sh"
    script.write_text("#!/usr/bin/env bash\necho stale\n", encoding="utf-8")
    script.chmod(0o644)
    existing_plan = ProjectFactoryManifestService(
        projects_root=tmp_path,
    ).plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
        ),
        allow_existing=True,
    )

    result = service.refresh_managed_files(
        existing_plan,
        relative_paths=("scripts/register_installable_app.sh",),
    )

    assert [item.path for item in result.generated_files] == [
        "scripts/register_installable_app.sh"
    ]
    content = script.read_text(encoding="utf-8")
    assert "apk_proxy_deadline" in content
    assert "echo stale" not in content
    assert script.stat().st_mode & stat.S_IXUSR


def test_generated_register_installable_app_script_retries_apk_proxy_fallback(
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
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_fake_github_access_tools(fake_bin)
    curl_calls = tmp_path / "curl-calls.txt"
    fallback_attempts = tmp_path / "fallback-attempts.txt"
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$CURL_CALLS_FILE\"\n"
        "args=\"$*\"\n"
        "if [[ \"$args\" == *'https://bridge.test/apk'* ]]; then\n"
        "  echo 'Could not resolve host: bridge.test' >&2\n"
        "  exit 6\n"
        "fi\n"
        "if [[ \"$args\" == *'http://localhost:8000/apk'* ]]; then\n"
        "  count=0\n"
        "  [[ -f \"$FALLBACK_ATTEMPTS_FILE\" ]] && count=\"$(cat \"$FALLBACK_ATTEMPTS_FILE\")\"\n"
        "  count=$((count + 1))\n"
        "  printf '%s' \"$count\" > \"$FALLBACK_ATTEMPTS_FILE\"\n"
        "  if [[ \"$count\" -lt 2 ]]; then\n"
        "    echo 'The requested URL returned error: 404' >&2\n"
        "    exit 22\n"
        "  fi\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$args\" == *'-I'* ]]; then exit 0; fi\n"
        "if [[ \"$args\" == *'/installable-apps/clinica-norte'* ]]; then\n"
        "  cat <<'JSON'\n"
        '{"sourceApp":"clinica-norte","displayName":"Clinica Norte Preview",'
        '"releaseChannel":"prerelease","releaseTagPattern":"android-preview-v*",'
        '"releaseTag":"android-preview-v0.1.0-build.1","available":true,'
        '"latestAssetName":"clinica-norte.apk",'
        '"previewUrl":"https://preview.nienfos.com/clinica-norte",'
        '"runtimeProfile":"preview","productionReady":false,'
        '"mockOrDemo":false,"apkUrl":"https://bridge.test/apk",'
        '"sha256":"' + ("1" * 64) + '","latestBuild":{"releaseTag":"android-preview-v0.1.0-build.1"},'
        '"installStatusHint":"available"}\n'
        "JSON\n"
        "  exit 0\n"
        "fi\n"
        "cat <<'JSON'\n"
        '{"sourceApp":"clinica-norte","displayName":"Clinica Norte Preview"}\n'
        "JSON\n",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)

    completed = subprocess.run(
        ["scripts/register_installable_app.sh"],
        cwd=project,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "BRIDGE_URL": "http://localhost:8000",
            "BRIDGE_PUBLIC_URL": "https://bridge.test",
            "BRIDGE_REGISTRATION_TOKEN": "token",
            "GITHUB_REPO": "brunojaime/clinica-norte",
            "APP_RELEASE_TAG": "android-preview-v0.1.0-build.1",
            "BRIDGE_APK_PROXY_TIMEOUT_SECONDS": "5",
            "BRIDGE_APK_PROXY_POLL_SECONDS": "0",
            "CODEX_MOBILE_BRIDGE_ROOT": str(tmp_path / "empty-bridge-root"),
            "CURL_CALLS_FILE": str(curl_calls),
            "FALLBACK_ATTEMPTS_FILE": str(fallback_attempts),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert fallback_attempts.read_text(encoding="utf-8") == "2"
    assert (
        "Bridge APK proxy verified through local bridge transport for public APK URL: "
        "https://bridge.test/apk"
    ) in completed.stdout


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

    assert "defaultValue: 'preview'" in main
    assert "API_RUNTIME" in main
    assert "APP_SLUG" in main
    assert "config.isMock" in main
    assert "MockProjectApiClient" in main
    assert "runtimeProfile == 'mock'" in config
    assert "runtimeProfile != 'preview'" in config
    assert "apiRuntime == 'cloudflare_preview'" in config
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
    assert (mobile / "lib/main_preview.dart").is_file()
    assert (mobile / "lib/src/config.dart").is_file()
    assert (mobile / "lib/src/models.dart").is_file()
    assert (mobile / "lib/src/api_client.dart").is_file()
    assert (mobile / "lib/src/mock_api_client.dart").is_file()
    assert (mobile / "lib/src/session_controller.dart").is_file()
    assert (mobile / "lib/src/screens.dart").is_file()
    assert (mobile / "web/index.html").is_file()
    assert (mobile / "web/manifest.json").is_file()
    assert (mobile / "test/config_test.dart").is_file()
    assert (mobile / "test/api_client_test.dart").is_file()
    assert (mobile / "test/session_controller_test.dart").is_file()

    pubspec = (mobile / "pubspec.yaml").read_text(encoding="utf-8")
    assert "name: clinica_norte" in pubspec
    assert "http: ^1.2.2" in pubspec
    assert "codex_developer_feedback_template:" in pubspec
    assert "ref: codex-developer-feedback-template-v0.4.7" in pubspec
    assert "codex_app_updater:" in pubspec
    assert "ref: 374f0e3180dc8d80214dcaa4374073d8e4ab1340" in pubspec
    assert "codex_bridge_workbench:" in pubspec
    android_manifest = (
        mobile / "android/app/src/main/AndroidManifest.xml"
    ).read_text(encoding="utf-8")
    assert 'android:networkSecurityConfig="@xml/network_security_config"' in (
        android_manifest
    )
    android_gitignore = (mobile / "android/.gitignore").read_text(encoding="utf-8")
    assert ".kotlin/" in android_gitignore
    assert (mobile / "android/app/src/main/res/xml/network_security_config.xml").is_file()
    readme = (mobile / "README.md").read_text(encoding="utf-8")
    assert "--dart-define=API_BASE_URL=" in readme
    main = (mobile / "lib/main.dart").read_text(encoding="utf-8")
    assert "String.fromEnvironment('API_BASE_URL')" in main
    assert "CODEX_BRIDGE_WORKBENCH_URL" in main
    assert "CODEX_APP_UPDATER_ENABLED" in main
    assert "CodexBridgeDevModeWrapper" in main
    assert "DeveloperFeedbackTemplate" in main
    assert "APP_RUNTIME_PROFILE" in main
    assert "MockProjectApiClient" in main
    preview_main = (mobile / "lib/main_preview.dart").read_text(encoding="utf-8")
    assert "ProjectApiClient" in preview_main
    assert "MockProjectApiClient" not in preview_main
    assert "mock_api_client" not in preview_main
    assert "Enter demo as role" not in preview_main
    assert "seedRoles" not in preview_main
    assert "mock://local" not in preview_main
    assert "CODEX_APP_UPDATER_ENABLED" in preview_main
    assert "CodexAppUpdater" in preview_main
    api_client = (mobile / "lib/src/api_client.dart").read_text(encoding="utf-8")
    assert "/health" in api_client
    assert "/auth/register" in api_client
    assert "/auth/login" in api_client
    assert "/auth/me" in api_client
    assert "/auth/logout" in api_client
    assert "/admin/users" in api_client
    assert "/admin/roles" in api_client
    assert "/admin/business-records" in api_client
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
    assert "Preview screenshots" in report
    assert "No visual reference assets were attached" in report
    tokens = (project / "design/tokens.yaml").read_text(encoding="utf-8")
    assert "derived_from_visual_references" in tokens


def test_generated_web_preview_bundle_is_validable_locally(tmp_path: Path) -> None:
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
    build_script = project / "scripts/build_web_preview.sh"
    validate_script = project / "scripts/validate_web_preview.sh"
    worker = project / "deploy/web-preview/worker/src/index.js"
    worker_harness = project / "deploy/web-preview/worker/local_preview_test.mjs"
    wrangler = project / "deploy/web-preview/wrangler.toml.example"
    manifest = project / "deploy/web-preview/web-preview-manifest.yaml"
    d1_migration = project / "deploy/web-preview/d1/migrations/0001_preview_invites.sql"
    assert build_script.stat().st_mode & stat.S_IXUSR
    assert validate_script.stat().st_mode & stat.S_IXUSR
    assert "flutter build web" in build_script.read_text(encoding="utf-8")
    assert '--base-href "/$APP_SLUG/"' in build_script.read_text(encoding="utf-8")
    assert "APP_RUNTIME_PROFILE" in build_script.read_text(encoding="utf-8")
    worker_text = worker.read_text(encoding="utf-8")
    assert "/__preview/health" in worker_text
    assert "/api/health" in worker_text
    assert "function isPublicPreviewHealthRoute" in worker_text
    assert "function stripLeadingSlug" in worker_text
    assert "sluglessPath === '/api/health'" in worker_text
    assert worker_text.index("isPublicPreviewHealthRoute(request, url, assetPath)") < (
        worker_text.index("const access = await requireAccess(env, request, url)")
    )
    assert "/api/auth/login" in worker_text
    assert "/api/invites/accept" in worker_text
    assert "handlePreviewInviteAccept" in worker_text
    assert "invite_password_setup" in worker_text
    assert "/api/admin/bootstrap" in worker_text
    assert "/api/app-updates/current" in worker_text
    assert "/api/business/records" in worker_text
    assert "/api/domain/" not in worker_text
    assert "handlePreviewBusinessRecords" in worker_text
    assert "handlePreviewDomain" not in worker_text
    assert "preview_domain_" not in worker_text
    assert "/api/notifications" in worker_text
    assert "ASSETS.fetch" in worker_text
    assert "pathname === '/index.html' ? '/' : pathname" in worker_text
    assert "assetUrl.search = '';" in worker_text
    assert "WEB_PREVIEW_INVITE_SECRET" in worker_text
    assert "PREVIEW_DB" in worker_text
    assert "recordAuditEvent" in worker_text
    assert "login_succeeded" in worker_text
    assert "invite_access_granted" in worker_text
    assert "used_invite_token" in worker_text
    assert "revoked_invite_token" in worker_text
    assert "missing_invite_token" in worker_text
    assert "/__preview/access" in worker_text
    assert "asset_not_found" in worker_text
    assert "content-security-policy" in worker_text
    assert (
        "connect-src 'self' https://preview.nienfos.com https://www.gstatic.com "
        "https://fonts.gstatic.com"
    ) in worker_text
    assert "serveSpa" in worker_text
    assert worker_harness.is_file()
    assert "PREVIEW_DB" in wrangler.read_text(encoding="utf-8")
    assert 'binding = "ASSETS"' in wrangler.read_text(encoding="utf-8")
    assert "WEB_PREVIEW_INVITE_SECRET" in wrangler.read_text(encoding="utf-8")
    migration_text = d1_migration.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS preview_invites" in migration_text
    assert "CREATE TABLE IF NOT EXISTS preview_apps" in migration_text
    assert "CREATE TABLE IF NOT EXISTS preview_builds" in migration_text
    assert "CREATE TABLE IF NOT EXISTS preview_tenants" in migration_text
    assert "CREATE TABLE IF NOT EXISTS preview_users" in migration_text
    assert "CREATE TABLE IF NOT EXISTS preview_roles" in migration_text
    assert "CREATE TABLE IF NOT EXISTS preview_admin_invites" in migration_text
    assert "CREATE TABLE IF NOT EXISTS preview_sessions" in migration_text
    assert "CREATE TABLE IF NOT EXISTS preview_audit_events" in migration_text
    assert "CREATE TABLE IF NOT EXISTS preview_app_updates" in migration_text
    assert "CREATE TABLE IF NOT EXISTS preview_business_records" in migration_text
    assert "preview_domain_" not in migration_text
    assert "CREATE TABLE IF NOT EXISTS preview_assets" in migration_text
    assert "CREATE TABLE IF NOT EXISTS preview_events" in migration_text
    assert "CREATE TABLE IF NOT EXISTS preview_notifications" in migration_text
    assert "CREATE INDEX IF NOT EXISTS idx_preview_apps_slug" in migration_text
    assert "CREATE INDEX IF NOT EXISTS idx_preview_builds_app_created" in migration_text
    assert "CREATE INDEX IF NOT EXISTS idx_preview_tenants_app" in migration_text
    assert "CREATE INDEX IF NOT EXISTS idx_preview_roles_app_name" in migration_text
    assert "CREATE INDEX IF NOT EXISTS idx_preview_admin_invites_app_email" in migration_text
    assert "CREATE INDEX IF NOT EXISTS idx_preview_assets_app_type" in migration_text
    assert "CREATE INDEX IF NOT EXISTS idx_preview_events_app_type" in migration_text
    assert "token_sha256" in migration_text
    assert "used_at" in migration_text
    assert "revoked_at" in migration_text
    if shutil.which("node"):
        completed = subprocess.run(
            ["node", "deploy/web-preview/worker/local_preview_test.mjs"],
            cwd=project,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert "worker local preview harness passed" in completed.stdout

    yaml = pytest.importorskip("yaml")
    payload = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    assert payload["source_app"] == "clinica-norte"
    assert payload["stable_url"] == "https://preview.nienfos.com/clinica-norte"
    assert payload["runtime"]["type"] == "cloudflare_worker_assets"
    assert payload["runtime"]["default_profile"] == "preview"
    assert payload["runtime"]["api_runtime"] == "cloudflare_preview"
    assert payload["runtime"]["api_base_url"] == (
        "https://preview.nienfos.com/clinica-norte/api"
    )
    assert payload["runtime"]["health_path"] == "/api/health"
    assert payload["runtime"]["asset_binding"] == "ASSETS"
    assert payload["first_release"]["mode"] == "preview"
    assert payload["first_release"]["android_tag_pattern"] == "android-preview-v*"
    assert payload["first_release"]["data_persistence"] == "cloudflare_d1"
    assert payload["access"]["mode"] == "invite_token"
    assert payload["access"]["single_use"] is True
    assert payload["access"]["d1_binding"] == "PREVIEW_DB"
    assert payload["access"]["migrations_dir"] == "deploy/web-preview/d1/migrations"
    assert payload["access"]["required_worker_secrets"] == [
        "WEB_PREVIEW_INVITE_SECRET"
    ]
    assert payload["access"]["access_path"] == "/__preview/access"
    assert payload["build"]["asset_entrypoint"] == "index.html"
    assert "flutter_bootstrap.js" in payload["build"]["required_files"]
    assert payload["cloudflare"]["resources"]["worker_name"] == (
        "nienfos-preview-runtime"
    )
    assert payload["cloudflare"]["resources"]["d1_database"] == "nienfos-preview"
    assert "/clinica-norte/__preview/health" in payload["expected_routes"]
    assert "/clinica-norte/__preview/access" in payload["expected_routes"]
    assert "/clinica-norte/api/health" in payload["expected_routes"]
    assert "/clinica-norte/api/auth/login" in payload["expected_routes"]
    assert "/clinica-norte/api/app-updates/current" in payload["expected_routes"]
    assert payload["preview_api_v1"]["base_url"] == (
        "https://preview.nienfos.com/clinica-norte/api"
    )


def test_generated_web_preview_validation_accepts_real_and_blocks_mock(
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
    real = subprocess.run(
        ["scripts/validate_web_preview.sh"],
        cwd=project,
        env={
            **os.environ,
            "API_BASE_URL": "https://preview.nienfos.com/clinica-norte/api",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert real.returncode == 0, real.stdout + real.stderr
    assert "web preview validation completed" in real.stdout
    build_output = project / "build/web-preview/clinica-norte"
    (build_output / "assets").mkdir(parents=True)
    (build_output / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (build_output / "manifest.json").write_text("{}", encoding="utf-8")
    (build_output / "flutter_bootstrap.js").write_text("void 0;", encoding="utf-8")
    strict = subprocess.run(
        ["scripts/validate_web_preview.sh"],
        cwd=project,
        env={
            **os.environ,
            "API_BASE_URL": "https://preview.nienfos.com/clinica-norte/api",
            "REQUIRE_WEB_BUILD_OUTPUT": "true",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert strict.returncode == 0, strict.stdout + strict.stderr

    mock = subprocess.run(
        ["scripts/validate_web_preview.sh"],
        cwd=project,
        env={
            **os.environ,
            "API_BASE_URL": "https://preview.nienfos.com/clinica-norte/api",
            "APP_RUNTIME_PROFILE": "mock",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert mock.returncode != 0
    assert "mock web preview validation requires ALLOW_MOCK_WEB_PREVIEW=true" in (
        mock.stderr
    )


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


def _initial_preview_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {
        **os.environ,
        "APP_RUNTIME_PROFILE": "preview",
        "API_RUNTIME": "cloudflare_preview",
        "API_BASE_URL": "https://preview.nienfos.com/clinica-norte/api",
        "APP_RELEASE_TAG": "android-preview-v0.1.0-build.1",
        "APP_ANDROID_PREVIEW_RELEASE_TAG": "android-preview-v0.1.0-build.1",
        "BRIDGE_URL": "https://bridge.test",
        "INSTALLABLE_APPS_REGISTRATION_TOKEN": "token",
        "PREVIEW_ADMIN_PASSWORD": "preview-password",
        "PREVIEW_ADMIN_BOOTSTRAP_TOKEN": "bootstrap-token",
        "PREVIEW_D1_DATABASE": "nienfos-preview",
        "CLOUDFLARE_D1_DATABASE": "nienfos-preview",
        "CODEX_MOBILE_BRIDGE_ROOT": "/tmp/project-factory-test-no-env",
        "WRANGLER_AUTH_READY": "true",
    }
    if extra:
        env.update(extra)
    return env


def _write_fake_github_access_tools(
    fake_bin: Path,
    *,
    release_asset: str = "clinica-norte.apk",
) -> None:
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$1 $2\" == \"repo view\" ]]; then exit 0; fi\n"
        "if [[ \"$1 $2\" == \"workflow view\" ]]; then exit 0; fi\n"
        "if [[ \"$1 $2\" == \"release view\" ]]; then\n"
        f"  printf '{release_asset}\\n'\n"
        "  exit 0\n"
        "fi\n"
        "exit 2\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    real_git = shutil.which("git") or "/usr/bin/git"
    fake_git = fake_bin / "git"
    fake_git.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$1\" == \"ls-remote\" ]]; then printf 'abc123\\tHEAD\\n'; exit 0; fi\n"
        f"exec {real_git} \"$@\"\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)


def _write_initial_preview_gate_fakes(
    project: Path,
    fake_bin: Path,
    tmp_path: Path,
    *,
    apksigner_certificate_output: str | None = None,
) -> tuple[Path, Path]:
    command_log = tmp_path / "initial-preview-commands.log"
    bridge_root = tmp_path / "bridge-root"
    secrets = bridge_root / "secrets"
    secrets.mkdir(parents=True, exist_ok=True)
    (secrets / "clinica-norte-preview-upload-keystore.jks").write_bytes(
        b"existing-preview-keystore"
    )
    (secrets / "clinica-norte-preview-signing.env").write_text(
        "\n".join(
            [
                "ANDROID_KEY_ALIAS=preview",
                "ANDROID_STORE_PASSWORD=store-password",
                "ANDROID_KEY_PASSWORD=key-password",
                "ANDROID_STORE_TYPE=JKS",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write_fake_github_access_tools(fake_bin)
    real_python = sys.executable
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$1 $2 $3 $4\" == '-m pytest tests -q' ]]; then\n"
        "  printf 'backend tests\\n' >> \"$COMMAND_LOG\"\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1\" == '-' && \"${2:-}\" == 'https://bridge.test' ]]; then\n"
        "  printf 'invite e2e\\n' >> \"$COMMAND_LOG\"\n"
        "  cat >/dev/null\n"
        "  exit 0\n"
        "fi\n"
        f"exec {real_python} \"$@\"\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    fake_flutter = fake_bin / "flutter"
    fake_flutter.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'flutter %s\\n' \"$*\" >> \"$COMMAND_LOG\"\n"
        "if [[ \"$1\" == 'analyze' && \"${FAIL_FLUTTER_ANALYZE:-false}\" == 'true' ]]; then\n"
        "  printf 'flutter analyze failed by test\\n' >&2\n"
        "  exit 7\n"
        "fi\n"
        "if [[ \"$1 $2\" == 'build apk' ]]; then\n"
        "  mkdir -p build/app/outputs/flutter-apk\n"
        "  printf 'preview-apk' > build/app/outputs/flutter-apk/app-release.apk\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_flutter.chmod(0o755)

    if apksigner_certificate_output is None:
        apksigner_certificate_output = (
            "V2 Signer: certificate SHA-256 digest: "
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
            "V2 Signer: certificate DN: CN=Clinica Norte Preview Upload"
        )
    fake_apksigner = fake_bin / "apksigner"
    fake_apksigner.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'apksigner %s\\n' \"$*\" >> \"$COMMAND_LOG\"\n"
        "if [[ \"${FAIL_APKSIGNER:-false}\" == 'true' ]]; then\n"
        "  printf 'apksigner failed by test\\n' >&2\n"
        "  exit 9\n"
        "fi\n"
        "cat <<'OUT'\n"
        "Verifies\n"
        "Verified using v1 scheme (JAR signing): true\n"
        f"{apksigner_certificate_output.rstrip()}\n"
        "OUT\n",
        encoding="utf-8",
    )
    fake_apksigner.chmod(0o755)

    fake_wrangler = fake_bin / "wrangler"
    fake_wrangler.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'wrangler %s\\n' \"$*\" >> \"$COMMAND_LOG\"\n"
        "if [[ \"$*\" == *'PRAGMA table_info'* ]]; then\n"
        "  cat <<'JSON'\n"
        '{"result":[{"results":[{"name":"id"},{"name":"email"},{"name":"role"},{"name":"sha256"},{"name":"used_at"}]}]}\n'
        "JSON\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_wrangler.chmod(0o755)

    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'curl %s\\n' \"$*\" >> \"$COMMAND_LOG\"\n"
        "if [[ \"$*\" == *'https://bridge.test/apk'* ]]; then\n"
        "  out=/tmp/project-factory-preview.apk\n"
        "  while [[ $# -gt 0 ]]; do\n"
        "    if [[ \"$1\" == '-o' ]]; then out=\"$2\"; shift 2; else shift; fi\n"
        "  done\n"
        "  printf 'preview-apk' > \"$out\"\n"
        "  exit 0\n"
        "fi\n"
        "cat <<'JSON'\n"
        '{"sourceApp":"clinica-norte","releaseChannel":"prerelease",'
        '"releaseTagPattern":"android-preview-v*",'
        '"releaseTag":"android-preview-v0.1.0-build.1","available":true,'
        '"previewUrl":"https://preview.nienfos.com/clinica-norte",'
        '"runtimeProfile":"preview","productionReady":false,'
        '"mockOrDemo":false,"apkUrl":"https://bridge.test/apk",'
        '"sha256":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",'
        '"latestBuild":{"releaseTag":"android-preview-v0.1.0-build.1"},'
        '"releaseMetadata":{"initialPreviewRelease":true,'
        '"releaseTagPattern":"android-preview-v*"}}\n'
        "JSON\n",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)

    for script_name in [
        "scripts/smoke_preview_api.sh",
        "scripts/smoke_web_preview.sh",
        "scripts/final_readiness_audit.sh",
    ]:
        script = project / script_name
        script.write_text(
            "#!/usr/bin/env bash\n"
            f"printf '{script_name}\\n' >> \"$COMMAND_LOG\"\n"
            "exit 0\n",
            encoding="utf-8",
        )
        script.chmod(0o755)

    return command_log, bridge_root


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


def _extract_shell_function(script: str, name: str) -> str:
    lines = script.splitlines()
    start = next(
        index for index, line in enumerate(lines) if line.startswith(f"{name}()")
    )
    selected: list[str] = []
    depth = 0
    for line in lines[start:]:
        selected.append(line)
        depth += line.count("{")
        depth -= line.count("}")
        if selected and depth == 0:
            return "\n".join(selected)
    raise AssertionError(f"shell function not closed: {name}")
