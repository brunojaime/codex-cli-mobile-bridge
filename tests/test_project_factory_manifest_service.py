from __future__ import annotations

from pathlib import Path

from backend.app.application.services.project_factory_manifest_service import (
    DEFAULT_CREATION_GENERATOR_RUNS,
    DEFAULT_CREATION_REVIEWER_RUNS,
    ProjectFactoryManifestInput,
    ProjectFactoryManifestService,
)


def test_valid_manifest_includes_required_product_defaults(tmp_path: Path) -> None:
    service = ProjectFactoryManifestService(projects_root=tmp_path)

    result = service.plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="Turnos medicos",
            primary_goal="Pacientes reservan turnos",
            visual_reference_paths=("assets/reference/uploaded/home.png",),
        )
    )

    assert result.ok is True
    assert result.status == "valid"
    assert result.target_path == str(tmp_path / "clinica-norte")
    assert result.manifest_path == str(tmp_path / "clinica-norte/.codex/project.yaml")

    manifest = result.manifest
    assert manifest["name"] == "Clinica Norte"
    assert manifest["slug"] == "clinica-norte"
    assert manifest["business_type"] == "turnos_medicos"
    assert manifest["platforms"] == {"ios": True, "android": True, "web": True}
    assert manifest["frontend"]["framework"] == "flutter"
    assert manifest["frontend"]["mobile_template"] == (
        "flutter-auth-admin-notifications-v1"
    )
    assert manifest["backend"]["framework"] == "fastapi"
    assert manifest["backend"]["template"] == "fastapi-auth-rbac-admin-notifications-v1"
    assert manifest["auth"]["required"] is True
    assert manifest["auth"]["google_login"] is True
    assert manifest["auth"]["google_credentials_status"] == "pending_credentials"
    assert manifest["access_control"]["model"] == "rbac"
    assert manifest["access_control"]["owner_has_all_permissions"] is True
    assert manifest["admin"]["domain_management"] is True
    assert manifest["notifications"]["channels"] == ["in_app", "push", "email"]
    assert manifest["sdd"]["required_artifacts"] == [
        "spec.md",
        "plan.md",
        "tasks.md",
        "metadata.yaml",
    ]


def test_creation_workflow_defaults_to_ten_generator_and_ten_reviewer_runs(
    tmp_path: Path,
) -> None:
    service = ProjectFactoryManifestService(projects_root=tmp_path)

    result = service.plan_manifest(
        ProjectFactoryManifestInput(
            name="Catalogo Autos",
            business_type="autos",
            primary_goal="Gestionar autos y consultas",
        )
    )

    workflow = result.manifest["codex"]["creation_workflow"]
    assert workflow["runner"] == "codex_cli"
    assert workflow["mode"] == "generator_reviewer_batches"
    assert workflow["generator_runs"] == DEFAULT_CREATION_GENERATOR_RUNS == 10
    assert workflow["reviewer_runs"] == DEFAULT_CREATION_REVIEWER_RUNS == 10


def test_seed_admin_manifest_uses_env_names_and_never_plain_password(
    tmp_path: Path,
) -> None:
    service = ProjectFactoryManifestService(projects_root=tmp_path)

    result = service.plan_manifest(
        ProjectFactoryManifestInput(
            name="Resto Admin",
            business_type="restaurant",
            primary_goal="Administrar platos y reservas",
        )
    )

    seed_admin = result.manifest["seed_admin"]
    assert seed_admin == {
        "enabled_by_env": True,
        "username_env": "SEED_ADMIN_USERNAME",
        "email_env": "SEED_ADMIN_EMAIL",
        "password_env": "SEED_ADMIN_PASSWORD",
        "role": "owner",
    }
    assert "Nienfoadmin1994" not in str(result.to_payload())


def test_invalid_values_are_blocked_without_manifest(tmp_path: Path) -> None:
    service = ProjectFactoryManifestService(projects_root=tmp_path)

    result = service.plan_manifest(
        ProjectFactoryManifestInput(
            name="",
            slug="-bad-",
            business_type="",
            primary_goal="",
            platforms=("web", "desktop"),
            backend="rails",
            logo_mode="magic",
            visual_reference_paths=("../outside.png", "/tmp/logo.png", ""),
        )
    )

    assert result.ok is False
    assert result.manifest == {}
    assert [error.code for error in result.errors] == [
        "missing_name",
        "missing_business_type",
        "missing_primary_goal",
            "invalid_slug",
        "unsupported_platform",
        "unsupported_backend",
        "unsupported_logo_mode",
        "unsafe_visual_reference",
        "unsafe_visual_reference",
        "empty_visual_reference",
    ]


def test_existing_project_folder_is_blocked_by_default(tmp_path: Path) -> None:
    (tmp_path / "clinica-norte").mkdir()
    service = ProjectFactoryManifestService(projects_root=tmp_path)

    result = service.plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
        )
    )

    assert result.ok is False
    assert [error.code for error in result.errors] == ["project_already_exists"]


def test_allow_existing_supports_future_regeneration_validation(
    tmp_path: Path,
) -> None:
    (tmp_path / "clinica-norte").mkdir()
    service = ProjectFactoryManifestService(projects_root=tmp_path)

    result = service.plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
        ),
        allow_existing=True,
    )

    assert result.ok is True
    assert result.target_path == str(tmp_path / "clinica-norte")
