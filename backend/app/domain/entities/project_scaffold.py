from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


class CreationMode(StrEnum):
    SCAFFOLD = "scaffold"
    PRODUCT = "product"


class BootstrapLevel(StrEnum):
    BUILDABLE = "buildable"


class TargetKind(StrEnum):
    MOBILE = "mobile"
    WEB = "web"
    API = "api"
    WEB_EDGE = "web_edge"
    AWS_READINESS = "aws_readiness"
    ANDROID_ARTIFACT = "android_artifact"


class CloudflareMode(StrEnum):
    PROVISION_SCAFFOLD = "provision_scaffold"
    GENERATE_ONLY = "generate_only"
    DISABLED = "disabled"


class AwsReadinessMode(StrEnum):
    NONE = "none"
    ARCHITECTURE_DOCS_ONLY = "architecture_docs_only"
    TERRAFORM_READY = "terraform_ready"


class ApiDeploymentStatus(StrEnum):
    PREPARED = "prepared"
    DEPLOYED = "deployed"
    BLOCKED = "blocked"


class ScaffoldLifecycleState(StrEnum):
    DRAFT = "draft"
    SCAFFOLD_CONTRACT_READY = "scaffold_contract_ready"
    SCAFFOLD_INITIALIZING = "scaffold_initializing"
    SCAFFOLD_BLOCKED_WITH_CONTEXT = "scaffold_blocked_with_context"
    SCAFFOLD_READY = "scaffold_ready"
    DOMAIN_INTAKE = "domain_intake"
    PRODUCT_FOUNDATION = "product_foundation"
    PREVIEW_READY = "preview_ready"


class CapabilityEvidenceState(StrEnum):
    DECLARED = "declared"
    LOCALLY_VERIFIED = "locally_verified"
    REMOTELY_VERIFIED = "remotely_verified"
    PREPARED = "prepared"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    UNSUPPORTED = "unsupported"


ALLOWED_SCAFFOLD_TRANSITIONS: dict[ScaffoldLifecycleState, frozenset[ScaffoldLifecycleState]] = {
    ScaffoldLifecycleState.DRAFT: frozenset(
        {ScaffoldLifecycleState.SCAFFOLD_CONTRACT_READY}
    ),
    ScaffoldLifecycleState.SCAFFOLD_CONTRACT_READY: frozenset(
        {ScaffoldLifecycleState.SCAFFOLD_INITIALIZING}
    ),
    ScaffoldLifecycleState.SCAFFOLD_INITIALIZING: frozenset(
        {
            ScaffoldLifecycleState.SCAFFOLD_BLOCKED_WITH_CONTEXT,
            ScaffoldLifecycleState.SCAFFOLD_READY,
        }
    ),
    ScaffoldLifecycleState.SCAFFOLD_BLOCKED_WITH_CONTEXT: frozenset(
        {
            ScaffoldLifecycleState.SCAFFOLD_INITIALIZING,
            ScaffoldLifecycleState.DOMAIN_INTAKE,
        }
    ),
    ScaffoldLifecycleState.SCAFFOLD_READY: frozenset(
        {ScaffoldLifecycleState.DOMAIN_INTAKE}
    ),
    ScaffoldLifecycleState.DOMAIN_INTAKE: frozenset(
        {ScaffoldLifecycleState.PRODUCT_FOUNDATION}
    ),
    ScaffoldLifecycleState.PRODUCT_FOUNDATION: frozenset(
        {ScaffoldLifecycleState.PREVIEW_READY}
    ),
    ScaffoldLifecycleState.PREVIEW_READY: frozenset(),
}


SCAFFOLD_SKIPPED_PRODUCT_WORK: tuple[str, ...] = (
    "business/domain inference",
    "entities, roles, permissions, and workflows",
    "auth, RBAC, admin, notifications, persistence, and seed data",
    "product screens, navigation, colors, logo, icon, and UX",
    "Domain Factory and UX lane activation",
    "Android publication and Bridge installable registration",
)


SCAFFOLD_FORBIDDEN_CONTENT: tuple[str, ...] = (
    "auth",
    "rbac",
    "seed user",
    "seed data",
    "mock data",
    "demo data",
    "dashboard",
    "inventory",
    "catalog",
    "booking",
    "role management",
    "notification",
)


@dataclass(frozen=True, slots=True)
class TargetSelection:
    kind: TargetKind
    provider: str
    enabled: bool
    source_root: str | None = None
    platforms: tuple[str, ...] = ()
    deployment_status: ApiDeploymentStatus | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "enabled": self.enabled,
            "provider": self.provider,
        }
        if self.source_root:
            payload["source_root"] = self.source_root
        if self.platforms:
            payload["platforms"] = list(self.platforms)
        if self.deployment_status is not None:
            payload["deployment_status"] = self.deployment_status.value
        return payload


@dataclass(frozen=True, slots=True)
class CapabilityEvidence:
    capability: str
    state: CapabilityEvidenceState
    provider: str
    evidence: tuple[str, ...] = ()
    blocker: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "state": self.state.value,
            "provider": self.provider,
            "evidence": list(self.evidence),
            "blocker": self.blocker,
        }


@dataclass(frozen=True, slots=True)
class ProjectManifestV2:
    name: str
    slug: str
    creation_mode: CreationMode
    mobile: TargetSelection
    web: TargetSelection
    api: TargetSelection
    cloudflare_mode: CloudflareMode = CloudflareMode.DISABLED
    aws_mode: AwsReadinessMode = AwsReadinessMode.NONE
    lifecycle_state: ScaffoldLifecycleState = ScaffoldLifecycleState.DRAFT
    capabilities: tuple[CapabilityEvidence, ...] = ()
    artifacts: Mapping[str, Any] = field(default_factory=dict)
    compatibility: Mapping[str, Any] = field(default_factory=dict)

    schema_version: int = 2
    bootstrap_level: BootstrapLevel = BootstrapLevel.BUILDABLE

    def __post_init__(self) -> None:
        if self.schema_version != 2:
            raise ValueError("ProjectManifestV2 requires schema_version=2")
        if not self.name.strip() or not self.slug.strip():
            raise ValueError("Project name and slug are required")
        for expected, target in (
            (TargetKind.MOBILE, self.mobile),
            (TargetKind.WEB, self.web),
            (TargetKind.API, self.api),
        ):
            if target.kind is not expected:
                raise ValueError(f"{expected.value} target has wrong kind")
            if target.enabled == (target.provider == "none"):
                raise ValueError(
                    f"{expected.value} enabled/provider combination is inconsistent"
                )
        if self.creation_mode is CreationMode.SCAFFOLD:
            if self.lifecycle_state in {
                ScaffoldLifecycleState.PRODUCT_FOUNDATION,
                ScaffoldLifecycleState.PREVIEW_READY,
            }:
                raise ValueError("Scaffold creation cannot start in a product state")

    def transition(self, target: ScaffoldLifecycleState) -> "ProjectManifestV2":
        if target not in ALLOWED_SCAFFOLD_TRANSITIONS[self.lifecycle_state]:
            raise ValueError(
                f"Invalid lifecycle transition: {self.lifecycle_state.value} -> {target.value}"
            )
        values = self.__dict__ if hasattr(self, "__dict__") else {
            field_name: getattr(self, field_name)
            for field_name in self.__dataclass_fields__
        }
        return ProjectManifestV2(**{**values, "lifecycle_state": target})

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "creation": {
                "mode": self.creation_mode.value,
                "auto_start_domain_factory": False,
                "bootstrap_level": self.bootstrap_level.value,
            },
            "project": {"name": self.name, "slug": self.slug},
            "targets": {
                "mobile": self.mobile.to_payload(),
                "web": self.web.to_payload(),
                "api": self.api.to_payload(),
            },
            "infrastructure": {
                "web_edge": {
                    "provider": "cloudflare"
                    if self.cloudflare_mode is not CloudflareMode.DISABLED
                    else "none",
                    "mode": self.cloudflare_mode.value,
                    "d1": False,
                },
                "aws": {
                    "provider": (
                        self.aws_mode.value
                        if self.aws_mode is not AwsReadinessMode.NONE
                        else "none"
                    ),
                    "mode": self.aws_mode.value,
                    "apply": False,
                },
            },
            "artifacts": {
                "android": {
                    "provider": "gradle_apk",
                    "publish_during_scaffold": False,
                },
                **dict(self.artifacts),
            },
            "capabilities": [item.to_payload() for item in self.capabilities],
            "lifecycle": {
                "state": self.lifecycle_state.value,
                "next_action": (
                    "start_product"
                    if self.lifecycle_state is ScaffoldLifecycleState.SCAFFOLD_READY
                    else "retry_scaffold"
                    if self.lifecycle_state
                    is ScaffoldLifecycleState.SCAFFOLD_BLOCKED_WITH_CONTEXT
                    else None
                ),
            },
            "scaffold": {
                "neutral": True,
                "skipped_product_work": list(SCAFFOLD_SKIPPED_PRODUCT_WORK),
            },
            **(
                {"compatibility": dict(self.compatibility)}
                if self.compatibility
                else {}
            ),
        }


def creation_mode_from_payload(payload: Mapping[str, Any]) -> CreationMode:
    creation = payload.get("creation")
    if isinstance(creation, Mapping):
        raw = creation.get("mode")
        if raw is not None:
            return CreationMode(str(raw))
    return CreationMode.PRODUCT


def assert_scaffold_transition(
    current: ScaffoldLifecycleState,
    target: ScaffoldLifecycleState,
) -> None:
    if target not in ALLOWED_SCAFFOLD_TRANSITIONS[current]:
        raise ValueError(f"Invalid lifecycle transition: {current.value} -> {target.value}")
