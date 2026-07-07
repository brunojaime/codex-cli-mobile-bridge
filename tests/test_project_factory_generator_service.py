from __future__ import annotations

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
    assert (project / "apps/mobile/.gitkeep").is_file()
    assert (project / "backend/.gitkeep").is_file()
    metadata = (
        project / "specs/001-product-foundation/metadata.yaml"
    ).read_text(encoding="utf-8")
    assert "architecture/components.mmd" in metadata
    assert "architecture/entity-relationship.mmd" in metadata
    assert "SEED_ADMIN_PASSWORD" in (project / "AGENTS.md").read_text(
        encoding="utf-8",
    )
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
    assert "trap cleanup EXIT" in content


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
    assert "No notifications" in screens
    assert "Nienfoadmin1994" not in _read_all_text(project)


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
