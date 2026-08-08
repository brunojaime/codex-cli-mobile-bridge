from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from backend.app.application.services.project_manifest_compatibility import (
    ProjectManifestCompatibilityAdapter,
)
from backend.app.application.services.project_scaffold_providers import (
    DeclarativeTargetProvider,
    ProviderDescriptor,
    ProviderRegistry,
    ProviderRegistryError,
    ProviderContext,
    STACK_PRESETS,
    default_provider_registry,
)
from backend.app.domain.entities.project_scaffold import (
    ApiDeploymentStatus,
    AwsReadinessMode,
    CapabilityEvidence,
    CapabilityEvidenceState,
    CloudflareMode,
    CreationMode,
    ProjectManifestV2,
    ScaffoldLifecycleState,
    TargetKind,
    TargetSelection,
)


def _manifest() -> ProjectManifestV2:
    return ProjectManifestV2(
        name="Example",
        slug="example",
        creation_mode=CreationMode.SCAFFOLD,
        mobile=TargetSelection(
            TargetKind.MOBILE,
            "react_native_expo",
            True,
            "apps/mobile",
            ("android", "ios"),
        ),
        web=TargetSelection(TargetKind.WEB, "sveltekit", True, "apps/web"),
        api=TargetSelection(
            TargetKind.API,
            "go",
            True,
            "services/api",
            deployment_status=ApiDeploymentStatus.PREPARED,
        ),
        cloudflare_mode=CloudflareMode.GENERATE_ONLY,
        aws_mode=AwsReadinessMode.TERRAFORM_READY,
    )


def test_manifest_v2_round_trip_and_scaffold_guardrails() -> None:
    payload = _manifest().to_payload()

    restored = ProjectManifestCompatibilityAdapter().read_view(payload)

    assert restored.to_payload() == payload
    assert payload["creation"] == {
        "mode": "scaffold",
        "auto_start_domain_factory": False,
        "bootstrap_level": "buildable",
    }
    assert payload["infrastructure"]["web_edge"]["d1"] is False
    assert payload["infrastructure"]["aws"]["apply"] is False
    assert payload["artifacts"]["android"]["publish_during_scaffold"] is False


def test_manifest_v2_round_trip_preserves_capability_evidence() -> None:
    manifest = _manifest()
    manifest = replace(
        manifest,
        capabilities=(
            CapabilityEvidence(
                capability="openapi",
                state=CapabilityEvidenceState.LOCALLY_VERIFIED,
                provider="go",
                evidence=("go test ./...", "black-box parity"),
            ),
            CapabilityEvidence(
                capability="cloudflare_output",
                state=CapabilityEvidenceState.BLOCKED,
                provider="sveltekit",
                blocker="credentials unavailable",
            ),
        ),
    )
    payload = manifest.to_payload()

    restored = ProjectManifestCompatibilityAdapter().read_view(payload)

    assert restored.to_payload() == payload


def test_manifest_v2_rejects_malformed_capability_evidence() -> None:
    payload = _manifest().to_payload()
    payload["capabilities"] = [
        {
            "capability": "openapi",
            "state": "locally_verified",
            "provider": "go",
            "evidence": "not-a-list",
        }
    ]

    with pytest.raises(ValueError, match="evidence must be a list"):
        ProjectManifestCompatibilityAdapter().read_view(payload)


def test_manifest_v2_rejects_inconsistent_none_target() -> None:
    with pytest.raises(ValueError, match="enabled/provider combination"):
        ProjectManifestV2(
            name="Bad",
            slug="bad",
            creation_mode=CreationMode.SCAFFOLD,
            mobile=TargetSelection(TargetKind.MOBILE, "none", True),
            web=TargetSelection(TargetKind.WEB, "none", False),
            api=TargetSelection(TargetKind.API, "none", False),
        )


def test_v1_compatibility_is_read_only_and_does_not_disguise_legacy_go() -> None:
    source = {
        "schema_version": 1,
        "name": "Legacy",
        "slug": "legacy",
        "frontend_strategy": "svelte",
        "backend": {"framework": "go", "template": "fastapi-legacy"},
        "runtime_profiles": {
            "preview": {"api_runtime": "cloudflare_preview"}
        },
    }
    original = deepcopy(source)

    view = ProjectManifestCompatibilityAdapter().read_view(source)

    assert source == original
    assert view.creation_mode is CreationMode.PRODUCT
    assert view.mobile.provider == "none"
    assert view.web.provider == "svelte_legacy"
    assert view.api.provider == "go"
    assert view.compatibility["legacy_generated_api_provider"] == "fastapi"
    assert view.compatibility["preserve_recorded_artifacts"] is True


def test_scaffold_lifecycle_allows_explicit_product_transition_only() -> None:
    manifest = _manifest()
    ready = manifest.transition(ScaffoldLifecycleState.SCAFFOLD_CONTRACT_READY)
    initializing = ready.transition(ScaffoldLifecycleState.SCAFFOLD_INITIALIZING)
    completed = initializing.transition(ScaffoldLifecycleState.SCAFFOLD_READY)

    assert completed.transition(ScaffoldLifecycleState.DOMAIN_INTAKE).lifecycle_state is (
        ScaffoldLifecycleState.DOMAIN_INTAKE
    )
    with pytest.raises(ValueError, match="Invalid lifecycle transition"):
        manifest.transition(ScaffoldLifecycleState.DOMAIN_INTAKE)

    blocked = initializing.transition(
        ScaffoldLifecycleState.SCAFFOLD_BLOCKED_WITH_CONTEXT
    )
    assert blocked.to_payload()["lifecycle"]["next_action"] == "retry_scaffold"


def test_registry_is_single_source_for_ids_capabilities_and_phase_selection() -> None:
    registry = default_provider_registry()

    assert registry.ids(TargetKind.MOBILE) == (
        "flutter",
        "none",
        "react_native_expo",
    )
    assert registry.ids(TargetKind.WEB) == (
        "flutter_web",
        "none",
        "svelte_legacy",
        "sveltekit",
    )
    assert registry.get(TargetKind.API, "go").descriptor.capabilities["openapi"]
    assert "mobile_validation" in registry.phases_for(
        {
            TargetKind.MOBILE: "react_native_expo",
            TargetKind.WEB: "sveltekit",
            TargetKind.API: "go",
            TargetKind.WEB_EDGE: "none",
        }
    )
    with pytest.raises(ProviderRegistryError, match="Unknown api provider"):
        registry.get(TargetKind.API, "python-disguised-as-go")


def test_registry_rejects_unsafe_or_inconsistent_provider_outputs() -> None:
    registry = ProviderRegistry()
    with pytest.raises(ProviderRegistryError, match="unsafe workspace path"):
        registry.register(
            DeclarativeTargetProvider(
                ProviderDescriptor(
                    id="unsafe",
                    display_name="Unsafe",
                    target_kind=TargetKind.WEB,
                    source_root="../escape",
                    required_tools=(),
                    capabilities={"cloudflare_output": True},
                )
            )
        )
    with pytest.raises(ProviderRegistryError, match="without capability"):
        registry.register(
            DeclarativeTargetProvider(
                ProviderDescriptor(
                    id="inconsistent",
                    display_name="Inconsistent",
                    target_kind=TargetKind.WEB,
                    source_root="apps/web",
                    required_tools=(),
                    capabilities={"cloudflare_output": False},
                    outputs={"cloudflare": "apps/web/build"},
                )
            )
        )


def test_cloudflare_generate_only_does_not_require_remote_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "backend.app.application.services.project_scaffold_providers.shutil.which",
        lambda _: None,
    )
    provider = default_provider_registry().get(TargetKind.WEB_EDGE, "cloudflare")
    generate_only = provider.doctor(
        ProviderContext(
            workspace=tmp_path,
            project_name="Neutral",
            slug="neutral",
            creation_mode="scaffold",
            cloudflare_mode="generate_only",
        )
    )
    provision = provider.doctor(
        ProviderContext(
            workspace=tmp_path,
            project_name="Neutral",
            slug="neutral",
            creation_mode="scaffold",
            cloudflare_mode="provision_scaffold",
        )
    )

    assert generate_only.ok is True
    assert generate_only.tools == {}
    assert provision.ok is False
    assert provision.blockers[0].code == "provider_tool_missing"


def test_presets_cover_required_composable_matrix() -> None:
    triples = {
        (item["mobile"], item["web"], item["api"]) for item in STACK_PRESETS
    }
    assert ("react_native_expo", "sveltekit", "fastapi") in triples
    assert ("react_native_expo", "sveltekit", "go") in triples
    assert ("flutter", "sveltekit", "fastapi") in triples
    assert ("flutter", "sveltekit", "go") in triples
    assert ("none", "sveltekit", "go") in triples


@pytest.mark.parametrize(
    ("fixture", "mobile", "web", "api", "lifecycle"),
    (
        ("v1-flutter.yaml", "flutter", "flutter_web", "fastapi", "preview_ready"),
        ("v1-svelte.yaml", "none", "svelte_legacy", "fastapi", "product_foundation"),
        (
            "v1-go-declaration-fastapi-artifact.yaml",
            "flutter",
            "flutter_web",
            "go",
            "product_foundation",
        ),
        (
            "v1-interrupted.yaml",
            "flutter",
            "flutter_web",
            "fastapi",
            "scaffold_initializing",
        ),
    ),
)
def test_v1_migration_fixtures_are_adapted_without_rewrite(
    fixture: str,
    mobile: str,
    web: str,
    api: str,
    lifecycle: str,
) -> None:
    path = Path("tests/fixtures/project_manifests") / fixture
    before = path.read_bytes()
    payload = yaml.safe_load(before)

    view = ProjectManifestCompatibilityAdapter().read_view(payload)

    assert path.read_bytes() == before
    assert view.creation_mode is CreationMode.PRODUCT
    assert view.mobile.provider == mobile
    assert view.web.provider == web
    assert view.api.provider == api
    assert view.lifecycle_state.value == lifecycle
    assert view.compatibility["read_only"] is True


def test_legacy_svelte_provider_is_compatibility_only_for_new_scaffolds(
    tmp_path: Path,
) -> None:
    from backend.app.application.services.project_scaffold_service import (
        ProjectScaffoldService,
        ScaffoldDraftInput,
        ScaffoldError,
    )

    projects = tmp_path / "projects"
    projects.mkdir()
    service = ProjectScaffoldService(
        projects_root=projects,
        state_root=tmp_path / "state",
    )

    with pytest.raises(ScaffoldError, match="compatibility-only"):
        service.create_draft(
            ScaffoldDraftInput(
                name="Legacy Not New",
                stack_preset=None,
                mobile_provider="none",
                web_provider="svelte_legacy",
                api_provider="none",
            )
        )
