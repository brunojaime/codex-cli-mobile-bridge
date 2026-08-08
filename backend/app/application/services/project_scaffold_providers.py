from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Mapping, Protocol

from backend.app.domain.entities.project_scaffold import (
    CapabilityEvidence,
    CapabilityEvidenceState,
    TargetKind,
)


class ProviderRegistryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RuntimeBinding:
    logical_key: str
    environment_key: str
    public: bool
    delivery: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "logical_key": self.logical_key,
            "environment_key": self.environment_key,
            "public": self.public,
            "delivery": self.delivery,
        }


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    id: str
    display_name: str
    target_kind: TargetKind
    source_root: str | None
    required_tools: tuple[str, ...]
    capabilities: Mapping[str, bool]
    runtime_bindings: tuple[RuntimeBinding, ...] = ()
    minimum_versions: Mapping[str, str] = field(default_factory=dict)
    ci_steps: tuple[Mapping[str, Any], ...] = ()
    outputs: Mapping[str, str] = field(default_factory=dict)
    command_environment: Mapping[str, str] = field(default_factory=dict)
    bootstrap_artifacts: tuple[str, ...] = ()
    validation_artifacts: tuple[str, ...] = ()
    selectable_for_scaffold: bool = True
    version: str = "1"

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "target_kind": self.target_kind.value,
            "source_root": self.source_root,
            "required_tools": list(self.required_tools),
            "capabilities": dict(self.capabilities),
            "runtime_bindings": [item.to_payload() for item in self.runtime_bindings],
            "minimum_versions": dict(self.minimum_versions),
            "ci_steps": [dict(item) for item in self.ci_steps],
            "outputs": dict(self.outputs),
            "command_environment": dict(self.command_environment),
            "bootstrap_artifacts": list(self.bootstrap_artifacts),
            "validation_artifacts": list(self.validation_artifacts),
            "selectable_for_scaffold": self.selectable_for_scaffold,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class ProviderContext:
    workspace: Path
    project_name: str
    slug: str
    creation_mode: str
    cloudflare_mode: str
    values: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TargetPlan:
    provider_id: str
    target_kind: TargetKind
    source_root: str | None
    phases: tuple[str, ...]
    generated_paths: tuple[str, ...]
    remote_effects: tuple[str, ...] = ()
    content_hash: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "target_kind": self.target_kind.value,
            "source_root": self.source_root,
            "phases": list(self.phases),
            "generated_paths": list(self.generated_paths),
            "remote_effects": list(self.remote_effects),
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True, slots=True)
class ProviderBlocker:
    code: str
    message: str
    next_action: str
    recoverable: bool = True

    def to_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "next_action": self.next_action,
            "recoverable": self.recoverable,
        }


@dataclass(frozen=True, slots=True)
class ProviderResult:
    provider_id: str
    target_kind: TargetKind
    status: CapabilityEvidenceState
    generated_files: tuple[str, ...] = ()
    commands: tuple[tuple[str, ...], ...] = ()
    tool_versions: Mapping[str, str] = field(default_factory=dict)
    capabilities: tuple[CapabilityEvidence, ...] = ()
    artifacts: tuple[Mapping[str, Any], ...] = ()
    blockers: tuple[ProviderBlocker, ...] = ()
    content_hash: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "target_kind": self.target_kind.value,
            "status": self.status.value,
            "generated_files": list(self.generated_files),
            "commands": [list(command) for command in self.commands],
            "tool_versions": dict(self.tool_versions),
            "capabilities": [item.to_payload() for item in self.capabilities],
            "artifacts": [dict(item) for item in self.artifacts],
            "blockers": [item.to_payload() for item in self.blockers],
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True, slots=True)
class ProviderDoctorResult:
    provider_id: str
    ok: bool
    tools: Mapping[str, str | None]
    tool_versions: Mapping[str, str] = field(default_factory=dict)
    blockers: tuple[ProviderBlocker, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "ok": self.ok,
            "tools": dict(self.tools),
            "tool_versions": dict(self.tool_versions),
            "blockers": [item.to_payload() for item in self.blockers],
        }


class TargetProvider(Protocol):
    descriptor: ProviderDescriptor

    def plan(self, context: ProviderContext) -> TargetPlan: ...

    def scaffold(self, context: ProviderContext, plan: TargetPlan) -> ProviderResult: ...

    def validate(self, context: ProviderContext, plan: TargetPlan) -> ProviderResult: ...

    def runtime_contract(self, context: ProviderContext) -> tuple[RuntimeBinding, ...]: ...

    def release_contract(self, context: ProviderContext) -> Mapping[str, Any]: ...

    def doctor(self, context: ProviderContext) -> ProviderDoctorResult: ...


class DeclarativeTargetProvider:
    def __init__(self, descriptor: ProviderDescriptor) -> None:
        self.descriptor = descriptor

    def plan(self, context: ProviderContext) -> TargetPlan:
        paths = (self.descriptor.source_root,) if self.descriptor.source_root else ()
        return TargetPlan(
            provider_id=self.descriptor.id,
            target_kind=self.descriptor.target_kind,
            source_root=self.descriptor.source_root,
            phases=("target_bootstrap", "target_validation"),
            generated_paths=paths,
        )

    def scaffold(self, context: ProviderContext, plan: TargetPlan) -> ProviderResult:
        del context, plan
        return ProviderResult(
            provider_id=self.descriptor.id,
            target_kind=self.descriptor.target_kind,
            status=CapabilityEvidenceState.PREPARED,
            capabilities=self._capabilities(CapabilityEvidenceState.DECLARED),
        )

    def validate(self, context: ProviderContext, plan: TargetPlan) -> ProviderResult:
        del context, plan
        return ProviderResult(
            provider_id=self.descriptor.id,
            target_kind=self.descriptor.target_kind,
            status=CapabilityEvidenceState.PREPARED,
            capabilities=self._capabilities(CapabilityEvidenceState.DECLARED),
        )

    def runtime_contract(self, context: ProviderContext) -> tuple[RuntimeBinding, ...]:
        del context
        return self.descriptor.runtime_bindings

    def release_contract(self, context: ProviderContext) -> Mapping[str, Any]:
        del context
        return {
            "provider": self.descriptor.id,
            "android_apk": bool(self.descriptor.capabilities.get("android_apk")),
            "publish_during_scaffold": False,
            "bridge_installable": bool(
                self.descriptor.capabilities.get("bridge_installable")
            ),
        }

    def doctor(self, context: ProviderContext) -> ProviderDoctorResult:
        required_tools = self.descriptor.required_tools
        if (
            self.descriptor.target_kind is TargetKind.WEB_EDGE
            and context.cloudflare_mode != "provision_scaffold"
        ):
            required_tools = ()
        tools = {name: shutil.which(name) for name in required_tools}
        blocker_list = [
            ProviderBlocker(
                code="provider_tool_missing",
                message=f"{self.descriptor.id} requires {name}.",
                next_action=f"Install {name} and retry target validation.",
            )
            for name, path in tools.items()
            if path is None
        ]
        if self.descriptor.capabilities.get("android_apk"):
            android_sdk = resolve_android_sdk_root()
            tools["android_sdk"] = str(android_sdk) if android_sdk else None
            if android_sdk is None:
                blocker_list.append(
                    ProviderBlocker(
                        code="provider_android_sdk_missing",
                        message=f"{self.descriptor.id} requires an Android SDK.",
                        next_action=(
                            "Set ANDROID_HOME/ANDROID_SDK_ROOT or install the SDK in "
                            "a standard user location, then retry."
                        ),
                    )
                )
        tool_versions: dict[str, str] = {}
        for name, minimum in self.descriptor.minimum_versions.items():
            path = tools.get(name)
            if not path:
                continue
            version = _tool_version(path)
            tool_versions[name] = version or "unknown"
            if version is None or _version_tuple(version) < _version_tuple(minimum):
                blocker_list.append(
                    ProviderBlocker(
                        code="provider_tool_version_unsupported",
                        message=(
                            f"{self.descriptor.id} requires {name}>={minimum}; "
                            f"found {version or 'unknown'}."
                        ),
                        next_action=f"Install {name}>={minimum} and retry.",
                    )
                )
        blockers = tuple(blocker_list)
        return ProviderDoctorResult(
            provider_id=self.descriptor.id,
            ok=not blockers,
            tools=tools,
            tool_versions=tool_versions,
            blockers=blockers,
        )

    def _capabilities(
        self,
        state: CapabilityEvidenceState,
    ) -> tuple[CapabilityEvidence, ...]:
        return tuple(
            CapabilityEvidence(
                capability=name,
                state=state if supported else CapabilityEvidenceState.UNSUPPORTED,
                provider=self.descriptor.id,
            )
            for name, supported in sorted(self.descriptor.capabilities.items())
        )


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[tuple[TargetKind, str], TargetProvider] = {}

    def register(self, provider: TargetProvider) -> None:
        descriptor = provider.descriptor
        if not descriptor.id or descriptor.id != descriptor.id.strip().lower():
            raise ProviderRegistryError("Provider id must be stable lowercase text")
        if len(set(descriptor.required_tools)) != len(descriptor.required_tools):
            raise ProviderRegistryError(
                f"Provider {descriptor.id} declares duplicate required tools"
            )
        declared_paths = tuple(
            item
            for item in (descriptor.source_root, *descriptor.outputs.values())
            if item
        )
        if any(Path(item).is_absolute() or ".." in Path(item).parts for item in declared_paths):
            raise ProviderRegistryError(
                f"Provider {descriptor.id} declares an unsafe workspace path"
            )
        if (
            "cloudflare" in descriptor.outputs
            and not descriptor.capabilities.get("cloudflare_output")
        ):
            raise ProviderRegistryError(
                f"Provider {descriptor.id} declares Cloudflare output without capability"
            )
        key = (descriptor.target_kind, descriptor.id)
        if key in self._providers:
            raise ProviderRegistryError(
                f"Duplicate provider {descriptor.target_kind.value}/{descriptor.id}"
            )
        self._providers[key] = provider

    def get(self, kind: TargetKind, provider_id: str) -> TargetProvider:
        try:
            return self._providers[(kind, provider_id)]
        except KeyError as exc:
            supported = ", ".join(self.ids(kind)) or "none"
            raise ProviderRegistryError(
                f"Unknown {kind.value} provider '{provider_id}'. Supported: {supported}."
            ) from exc

    def ids(self, kind: TargetKind) -> tuple[str, ...]:
        return tuple(sorted(key[1] for key in self._providers if key[0] is kind))

    def descriptors(self, kind: TargetKind | None = None) -> tuple[ProviderDescriptor, ...]:
        providers = (
            provider
            for (provider_kind, _), provider in self._providers.items()
            if kind is None or provider_kind is kind
        )
        return tuple(
            sorted(
                (provider.descriptor for provider in providers),
                key=lambda item: (item.target_kind.value, item.id),
            )
        )

    def phases_for(self, selections: Mapping[TargetKind, str]) -> tuple[str, ...]:
        phases: list[str] = []
        for kind, provider_id in selections.items():
            provider = self.get(kind, provider_id)
            if provider_id == "none":
                continue
            if provider.descriptor.capabilities.get("local_validation"):
                phases.extend((f"{kind.value}_bootstrap", f"{kind.value}_validation"))
            if provider.descriptor.capabilities.get("remote_provision"):
                phases.append(f"{kind.value}_provision")
        return tuple(dict.fromkeys(phases))


def _tool_version(path: str) -> str | None:
    version_arg = "version" if Path(path).name == "go" else "--version"
    try:
        completed = subprocess.run(
            (path, version_arg),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"\d+(?:\.\d+){1,2}", completed.stdout + completed.stderr)
    return match.group(0) if match else None


def _version_tuple(value: str) -> tuple[int, int, int]:
    parts = [int(item) for item in re.findall(r"\d+", value)[:3]]
    return tuple((parts + [0, 0, 0])[:3])  # type: ignore[return-value]


def resolve_android_sdk_root(
    environment: Mapping[str, str] | None = None,
) -> Path | None:
    values = environment or os.environ
    candidates: list[Path] = []
    for key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = values.get(key)
        if value:
            candidates.append(Path(value).expanduser())
    candidates.extend(
        (
            Path.home() / "Android/Sdk",
            Path.home() / ".local/share/android-sdk",
            Path("/opt/android-sdk"),
        )
    )
    adb = shutil.which("adb")
    if adb:
        candidates.append(Path(adb).resolve().parent.parent)
    for candidate in candidates:
        if (candidate / "platform-tools").is_dir():
            return candidate.resolve()
    return None


def default_provider_registry() -> ProviderRegistry:
    from backend.app.application.services.project_scaffold_templates import (
        provider_for_descriptor,
    )

    registry = ProviderRegistry()
    for descriptor in _default_descriptors():
        registry.register(provider_for_descriptor(descriptor))
    return registry


def _default_descriptors() -> tuple[ProviderDescriptor, ...]:
    mobile_runtime = (
        RuntimeBinding("api_base_url", "API_BASE_URL", True, "dart_define"),
        RuntimeBinding("runtime_profile", "APP_RUNTIME_PROFILE", True, "dart_define"),
        RuntimeBinding("source_app", "SOURCE_APP", True, "dart_define"),
    )
    expo_runtime = (
        RuntimeBinding("api_base_url", "EXPO_PUBLIC_API_BASE_URL", True, "expo_public"),
        RuntimeBinding("runtime_profile", "EXPO_PUBLIC_RUNTIME_PROFILE", True, "expo_public"),
        RuntimeBinding("source_app", "EXPO_PUBLIC_SOURCE_APP", True, "expo_public"),
    )
    svelte_runtime = (
        RuntimeBinding("api_base_url", "PUBLIC_API_BASE_URL", True, "svelte_public_env"),
        RuntimeBinding("runtime_profile", "PUBLIC_RUNTIME_PROFILE", True, "svelte_public_env"),
        RuntimeBinding("source_app", "PUBLIC_SOURCE_APP", True, "svelte_public_env"),
    )
    api_runtime = (
        RuntimeBinding("runtime_profile", "APP_RUNTIME_PROFILE", False, "process_env"),
        RuntimeBinding("source_app", "SOURCE_APP", False, "process_env"),
        RuntimeBinding("version", "APP_VERSION", False, "process_env"),
    )
    descriptors = [
        ProviderDescriptor("flutter", "Flutter", TargetKind.MOBILE, "apps/mobile", ("flutter", "dart"), {"local_validation": True, "android_apk": True, "bridge_installable": True, "product_feedback_adapter": True, "product_updater_adapter": True}, mobile_runtime, ci_steps=({"uses": "subosito/flutter-action@v2", "with": {"channel": "stable", "cache": True}},), bootstrap_artifacts=("apps/mobile/pubspec.lock", "apps/mobile/android/gradlew"), validation_artifacts=("apps/mobile/build/app/outputs/flutter-apk/app-debug.apk",)),
        ProviderDescriptor("react_native_expo", "React Native (Expo)", TargetKind.MOBILE, "apps/mobile", ("node", "npm", "java"), {"local_validation": True, "android_apk": True, "bridge_installable": True, "product_feedback_adapter": True, "product_updater_adapter": True}, expo_runtime, {"node": "22.18.0", "java": "17.0.0"}, ci_steps=({"uses": "actions/setup-node@v4", "with": {"node-version": "22.18.0", "cache": "npm", "cache-dependency-path": "apps/mobile/package-lock.json"}}, {"uses": "actions/setup-java@v4", "with": {"distribution": "temurin", "java-version": "17"}}, {"uses": "android-actions/setup-android@v3"}), command_environment={"NODE_ENV": "development"}, bootstrap_artifacts=("apps/mobile/package-lock.json", "apps/mobile/android/gradlew"), validation_artifacts=("apps/mobile/android/app/build/outputs/apk/debug/app-debug.apk",)),
        ProviderDescriptor("none", "No mobile target", TargetKind.MOBILE, None, (), {"local_validation": False, "android_apk": False, "bridge_installable": False}),
        ProviderDescriptor("flutter_web", "Flutter Web", TargetKind.WEB, "apps/web", ("flutter",), {"local_validation": True, "web_build": True, "cloudflare_output": True}, mobile_runtime, ci_steps=({"uses": "subosito/flutter-action@v2", "with": {"channel": "stable", "cache": True}},), outputs={"cloudflare": "apps/web/build/web"}, bootstrap_artifacts=("apps/web/pubspec.lock", "apps/web/web/index.html"), validation_artifacts=("apps/web/build/web",)),
        ProviderDescriptor("sveltekit", "SvelteKit", TargetKind.WEB, "apps/web", ("node", "npm"), {"local_validation": True, "web_build": True, "cloudflare_output": True}, svelte_runtime, {"node": "22.18.0"}, ci_steps=({"uses": "actions/setup-node@v4", "with": {"node-version": "22.18.0", "cache": "npm", "cache-dependency-path": "apps/web/package-lock.json"}},), outputs={"cloudflare": "apps/web/.svelte-kit/cloudflare"}, bootstrap_artifacts=("apps/web/package-lock.json",), validation_artifacts=("apps/web/.svelte-kit/cloudflare",)),
        ProviderDescriptor("svelte_legacy", "Svelte (legacy compatibility)", TargetKind.WEB, "apps/web", ("node", "npm"), {"local_validation": True, "web_build": True, "cloudflare_output": True}, svelte_runtime, outputs={"cloudflare": "apps/web/dist"}, selectable_for_scaffold=False),
        ProviderDescriptor("none", "No web target", TargetKind.WEB, None, (), {"local_validation": False, "web_build": False, "cloudflare_output": False}),
        ProviderDescriptor("fastapi", "FastAPI", TargetKind.API, "services/api", ("python3",), {"local_validation": True, "openapi": True, "health": True, "container_build": True}, api_runtime, ci_steps=({"uses": "actions/setup-python@v5", "with": {"python-version": "3.12"}},), bootstrap_artifacts=("services/api/requirements.lock",)),
        ProviderDescriptor("go", "Go", TargetKind.API, "services/api", ("go",), {"local_validation": True, "openapi": True, "health": True, "binary_build": True}, api_runtime, {"go": "1.24.0"}, ci_steps=({"uses": "actions/setup-go@v5", "with": {"go-version-file": "services/api/go.mod"}},), validation_artifacts=("services/api/build/api",)),
        ProviderDescriptor("none", "No API target", TargetKind.API, None, (), {"local_validation": False, "openapi": False, "health": False}),
        ProviderDescriptor("cloudflare", "Cloudflare", TargetKind.WEB_EDGE, "infra/cloudflare", ("wrangler",), {"local_validation": True, "remote_provision": True, "generate_only": True, "d1_default": False}),
        ProviderDescriptor("none", "No web edge", TargetKind.WEB_EDGE, None, (), {"local_validation": False, "remote_provision": False}),
        ProviderDescriptor("terraform_ready", "Terraform-ready", TargetKind.AWS_READINESS, "infra/aws", ("terraform",), {"local_validation": True, "terraform_apply": False, "resource_creation": False}, minimum_versions={"terraform": "1.12.2"}),
        ProviderDescriptor("architecture_docs_only", "Architecture docs only", TargetKind.AWS_READINESS, "infra/aws", (), {"local_validation": True, "terraform_apply": False, "resource_creation": False}),
        ProviderDescriptor("none", "No AWS readiness", TargetKind.AWS_READINESS, None, (), {"local_validation": False, "terraform_apply": False, "resource_creation": False}),
        ProviderDescriptor("gradle_apk", "Normalized Gradle APK", TargetKind.ANDROID_ARTIFACT, None, ("java",), {"android_apk": True, "publish_during_scaffold": False}),
    ]
    return tuple(descriptors)


STACK_PRESETS: tuple[dict[str, Any], ...] = (
    {"id": "expo-sveltekit-fastapi", "recommended": True, "mobile": "react_native_expo", "web": "sveltekit", "api": "fastapi"},
    {"id": "expo-sveltekit-go", "recommended": False, "mobile": "react_native_expo", "web": "sveltekit", "api": "go"},
    {"id": "flutter-sveltekit-fastapi", "recommended": False, "mobile": "flutter", "web": "sveltekit", "api": "fastapi"},
    {"id": "flutter-sveltekit-go", "recommended": False, "mobile": "flutter", "web": "sveltekit", "api": "go"},
    {"id": "sveltekit-fastapi-web-only", "recommended": False, "mobile": "none", "web": "sveltekit", "api": "fastapi"},
    {"id": "sveltekit-go-web-only", "recommended": False, "mobile": "none", "web": "sveltekit", "api": "go"},
)
