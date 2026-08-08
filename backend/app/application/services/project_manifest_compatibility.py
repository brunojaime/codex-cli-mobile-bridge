from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

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


class ProjectManifestCompatibilityError(ValueError):
    pass


class ProjectManifestCompatibilityAdapter:
    """Build an in-memory v2 view without mutating or writing the source."""

    def read_view(self, payload: Mapping[str, Any]) -> ProjectManifestV2:
        source = deepcopy(dict(payload))
        version = int(source.get("schema_version") or 1)
        if version == 2:
            return _parse_v2(source)
        if version != 1:
            raise ProjectManifestCompatibilityError(
                f"Unsupported project manifest schema_version={version}"
            )
        return _adapt_v1(source)


def _adapt_v1(source: Mapping[str, Any]) -> ProjectManifestV2:
    strategy = str(source.get("frontend_strategy") or "").strip().lower()
    frontend = source.get("frontend")
    if not strategy and isinstance(frontend, Mapping):
        strategy = str(frontend.get("strategy") or frontend.get("framework") or "")
    strategy = strategy or "flutter"
    backend = source.get("backend")
    backend_name = (
        str(backend.get("framework") or "fastapi")
        if isinstance(backend, Mapping)
        else str(backend or "fastapi")
    ).lower()
    if backend_name not in {"fastapi", "go", "none"}:
        backend_name = "none"

    if strategy == "svelte":
        mobile = TargetSelection(TargetKind.MOBILE, "none", False)
        web = TargetSelection(TargetKind.WEB, "svelte_legacy", True, "apps/web")
    else:
        mobile = TargetSelection(
            TargetKind.MOBILE,
            "flutter",
            True,
            "apps/mobile",
            ("android", "ios"),
        )
        web = TargetSelection(TargetKind.WEB, "flutter_web", True, "apps/mobile")
    api = TargetSelection(
        TargetKind.API,
        backend_name,
        backend_name != "none",
        "services/api" if backend_name != "none" else None,
        deployment_status=(
            ApiDeploymentStatus.PREPARED if backend_name != "none" else None
        ),
    )
    return ProjectManifestV2(
        name=str(source.get("name") or source.get("slug") or "Legacy project"),
        slug=str(source.get("slug") or "legacy-project"),
        creation_mode=CreationMode.PRODUCT,
        mobile=mobile,
        web=web,
        api=api,
        cloudflare_mode=(
            CloudflareMode.PROVISION_SCAFFOLD
            if _legacy_cloudflare_enabled(source)
            else CloudflareMode.DISABLED
        ),
        aws_mode=AwsReadinessMode.NONE,
        lifecycle_state=_legacy_lifecycle(source),
        compatibility={
            "source_schema_version": 1,
            "read_only": True,
            "legacy_frontend_strategy": strategy,
            "legacy_backend_declaration": backend_name,
            "legacy_generated_api_provider": _legacy_generated_api_provider(
                source,
                declared=backend_name,
            ),
            "preserve_recorded_artifacts": True,
        },
    )


def _parse_v2(source: Mapping[str, Any]) -> ProjectManifestV2:
    project = _mapping(source, "project")
    creation = _mapping(source, "creation")
    targets = _mapping(source, "targets")
    infrastructure = _mapping(source, "infrastructure")
    lifecycle = _mapping(source, "lifecycle")
    return ProjectManifestV2(
        name=str(project.get("name") or ""),
        slug=str(project.get("slug") or ""),
        creation_mode=CreationMode(str(creation.get("mode") or "product")),
        mobile=_target(TargetKind.MOBILE, targets.get("mobile")),
        web=_target(TargetKind.WEB, targets.get("web")),
        api=_target(TargetKind.API, targets.get("api")),
        cloudflare_mode=CloudflareMode(
            str(_mapping(infrastructure, "web_edge").get("mode") or "disabled")
        ),
        aws_mode=AwsReadinessMode(
            str(_mapping(infrastructure, "aws").get("mode") or "none")
        ),
        lifecycle_state=ScaffoldLifecycleState(
            str(lifecycle.get("state") or "draft")
        ),
        capabilities=_capabilities(source.get("capabilities")),
        artifacts=(source.get("artifacts") if isinstance(source.get("artifacts"), Mapping) else {}),
        compatibility=(source.get("compatibility") if isinstance(source.get("compatibility"), Mapping) else {}),
    )


def _target(kind: TargetKind, value: Any) -> TargetSelection:
    data = value if isinstance(value, Mapping) else {}
    provider = str(data.get("provider") or "none")
    enabled = bool(data.get("enabled", provider != "none"))
    deployment = data.get("deployment_status")
    return TargetSelection(
        kind=kind,
        provider=provider,
        enabled=enabled,
        source_root=str(data.get("source_root")) if data.get("source_root") else None,
        platforms=tuple(str(item) for item in (data.get("platforms") or ())),
        deployment_status=(
            ApiDeploymentStatus(str(deployment)) if deployment is not None else None
        ),
    )


def _capabilities(value: Any) -> tuple[CapabilityEvidence, ...]:
    if not isinstance(value, list):
        return ()
    results: list[CapabilityEvidence] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ProjectManifestCompatibilityError(
                "Manifest v2 capabilities must be objects."
            )
        evidence = item.get("evidence")
        if evidence is not None and not isinstance(evidence, list):
            raise ProjectManifestCompatibilityError(
                "Manifest v2 capability evidence must be a list."
            )
        results.append(
            CapabilityEvidence(
                capability=str(item.get("capability") or ""),
                state=CapabilityEvidenceState(str(item.get("state") or "declared")),
                provider=str(item.get("provider") or ""),
                evidence=tuple(str(entry) for entry in (evidence or ())),
                blocker=(
                    str(item["blocker"])
                    if item.get("blocker") is not None
                    else None
                ),
            )
        )
    return tuple(results)


def _legacy_generated_api_provider(
    source: Mapping[str, Any],
    *,
    declared: str,
) -> str:
    backend = source.get("backend")
    markers: list[str] = []
    if isinstance(backend, Mapping):
        markers.extend(
            str(backend.get(key) or "").lower()
            for key in ("generated_template", "template", "generated_framework")
        )
    artifacts = source.get("artifacts")
    if isinstance(artifacts, Mapping):
        markers.extend(str(value).lower() for value in artifacts.values())
    if any("fastapi" in marker or marker.endswith(".py") or "/app/main.py" in marker for marker in markers):
        return "fastapi"
    if any(marker.endswith(".go") or "/cmd/server" in marker for marker in markers):
        return "go"
    return declared


def _mapping(source: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = source.get(key)
    return value if isinstance(value, Mapping) else {}


def _legacy_cloudflare_enabled(source: Mapping[str, Any]) -> bool:
    runtime = source.get("runtime_profiles")
    if not isinstance(runtime, Mapping):
        return False
    preview = runtime.get("preview")
    return isinstance(preview, Mapping) and preview.get("api_runtime") == "cloudflare_preview"


def _legacy_lifecycle(source: Mapping[str, Any]) -> ScaffoldLifecycleState:
    lifecycle = source.get("lifecycle")
    state = lifecycle.get("state") if isinstance(lifecycle, Mapping) else None
    aliases = {
        "ready": ScaffoldLifecycleState.PREVIEW_READY,
        "blocked_with_context": ScaffoldLifecycleState.SCAFFOLD_BLOCKED_WITH_CONTEXT,
        "initializing": ScaffoldLifecycleState.SCAFFOLD_INITIALIZING,
    }
    return aliases.get(str(state), ScaffoldLifecycleState.PRODUCT_FOUNDATION)
