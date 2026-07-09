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
        "flutter-runtime-profiles-auth-admin-notifications-v1"
    )
    assert manifest["backend"]["framework"] == "fastapi"
    assert manifest["backend"]["template"] == (
        "fastapi-runtime-profiles-auth-rbac-admin-notifications-v1"
    )
    assert manifest["runtime_profiles"]["env"] == "APP_RUNTIME_PROFILE"
    assert manifest["runtime_profiles"]["default_profile"] == "preview"
    assert manifest["runtime_profiles"]["preview"]["default_for_initial_release"] is True
    assert manifest["runtime_profiles"]["preview"]["api_runtime"] == (
        "cloudflare_preview"
    )
    assert manifest["runtime_profiles"]["preview"]["api_base_url"] == (
        "https://preview.nienfos.com/clinica-norte/api"
    )
    assert manifest["runtime_profiles"]["mock"]["opt_in"] is True
    assert manifest["runtime_profiles"]["real"]["default_for_productive_release"] is True
    assert manifest["runtime_profiles"]["real"]["mock_or_demo"] is False
    assert manifest["release"]["initial_preview_release_required"] is True
    assert manifest["release"]["mock_or_demo_release_required"] is False
    assert manifest["release"]["mock_or_demo_release_opt_in"] is True
    assert manifest["release"]["productive_release_required"] is False
    assert manifest["auth"]["required"] is True
    assert manifest["auth"]["google_login"] is True
    assert manifest["auth"]["google_credentials_status"] == "pending_credentials"
    assert manifest["access_control"]["model"] == "rbac"
    assert manifest["access_control"]["owner_has_all_permissions"] is True
    assert manifest["admin"]["domain_management"] is True
    assert manifest["notifications"]["channels"] == ["in_app", "push", "email"]
    assert (
        manifest["visual_references"]["strong_reference_contract"][
            "generic_material_shell_forbidden_when_references_exist"
        ]
        is True
    )
    assert "screen_structure" in manifest["visual_references"][
        "strong_reference_contract"
    ]["required_analysis_per_image"]
    assert manifest["sdd"]["required_artifacts"] == [
        "spec.md",
        "plan.md",
        "tasks.md",
        "metadata.yaml",
    ]


def test_creation_workflow_defaults_to_twenty_generator_and_twenty_reviewer_runs(
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
    assert workflow["mode"] == "generator_reviewer_pairs"
    assert workflow["generator_runs"] == DEFAULT_CREATION_GENERATOR_RUNS == 20
    assert workflow["reviewer_runs"] == DEFAULT_CREATION_REVIEWER_RUNS == 20


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


def test_manifest_includes_deduped_initial_admin_invites(tmp_path: Path) -> None:
    service = ProjectFactoryManifestService(projects_root=tmp_path)

    result = service.plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
            initial_admin_emails=(
                "ADMIN@Example.COM",
                "admin@example.com",
                "owner@example.com",
            ),
        )
    )

    assert result.ok is True
    initial_invites = result.manifest["admin"]["initial_invites"]
    assert initial_invites["required_for_web_preview"] is True
    assert initial_invites["emails"] == ["admin@example.com", "owner@example.com"]
    assert initial_invites["default_role"] == "owner"
    assert initial_invites["dedupe"] is True


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


def test_svelte_frontend_strategy_is_web_first(tmp_path: Path) -> None:
    service = ProjectFactoryManifestService(projects_root=tmp_path)

    result = service.plan_manifest(
        ProjectFactoryManifestInput(
            name="Portal Clientes",
            business_type="services",
            primary_goal="Clientes consultan estados",
            platforms=("web",),
            frontend_strategy="svelte",
        )
    )

    assert result.ok is True
    manifest = result.manifest
    assert manifest["frontend_strategy"] == "svelte"
    assert manifest["frontend"]["framework"] == "svelte"
    assert manifest["frontend"]["source_root"] == "apps/web"
    assert manifest["frontend"]["strategy_capabilities"][
        "supports_android_preview_apk"
    ] is False
    assert manifest["frontend"]["strategy_capabilities"][
        "supports_bridge_installable_app"
    ] is False
    assert manifest["runtime_profiles"]["env"] == "VITE_APP_RUNTIME_PROFILE"
    assert manifest["runtime_profiles"]["api_runtime_env"] == "VITE_API_RUNTIME"
    assert manifest["runtime_profiles"]["preview_api_env"] == "VITE_API_BASE_URL"
    assert manifest["runtime_profiles"]["preview"]["release_tag_patterns"] == []
    assert manifest["runtime_profiles"]["mock"]["release_tag_patterns"] == []
    assert manifest["runtime_profiles"]["real"]["release_tag_patterns"] == []
    assert all(
        "android-" not in contract
        for contract in manifest["release"]["ci_contracts"]
    )
    assert result.to_payload()["frontend_strategy"] == "svelte"


def test_svelte_frontend_strategy_blocks_mobile_platforms(tmp_path: Path) -> None:
    service = ProjectFactoryManifestService(projects_root=tmp_path)

    result = service.plan_manifest(
        ProjectFactoryManifestInput(
            name="Portal Clientes",
            business_type="services",
            primary_goal="Clientes consultan estados",
            platforms=("web", "android"),
            frontend_strategy="svelte",
        )
    )

    assert result.ok is False
    assert [error.code for error in result.errors] == [
        "unsupported_frontend_strategy_platforms"
    ]


def test_unknown_frontend_strategy_blocks_with_supported_list(
    tmp_path: Path,
) -> None:
    service = ProjectFactoryManifestService(projects_root=tmp_path)

    result = service.plan_manifest(
        ProjectFactoryManifestInput(
            name="Portal Clientes",
            business_type="services",
            primary_goal="Clientes consultan estados",
            platforms=("web",),
            frontend_strategy="react",
        )
    )

    assert result.ok is False
    assert [error.code for error in result.errors] == [
        "unsupported_frontend_strategy"
    ]
    assert "flutter, svelte" in result.errors[0].message
