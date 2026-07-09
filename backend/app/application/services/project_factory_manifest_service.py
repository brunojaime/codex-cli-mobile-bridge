from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


DEFAULT_PLATFORMS = ("ios", "android", "web")
DEFAULT_ROLES = ("owner", "admin", "manager", "staff", "customer", "guest")
DEFAULT_BACKEND = "fastapi"
DEFAULT_FRONTEND = "flutter"
DEFAULT_FRONTEND_STRATEGY = "flutter"
DEFAULT_CREATION_GENERATOR_RUNS = 20
DEFAULT_CREATION_REVIEWER_RUNS = 20
DEFAULT_FIRST_RELEASE_MODE = "preview"

ALLOWED_PLATFORMS = frozenset({"ios", "android", "web"})
ALLOWED_BACKENDS = frozenset({"fastapi", "go", "none"})
ALLOWED_LOGO_MODES = frozenset({"upload", "generate", "placeholder"})
ALLOWED_FIRST_RELEASE_MODES = frozenset({"preview", "mock"})
BLOCKED_INITIAL_RELEASE_MODES = frozenset({"production", "promote", "promotion", "real"})
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,78}[a-z0-9]$")

FRONTEND_STRATEGIES: dict[str, dict[str, Any]] = {
    "flutter": {
        "id": "flutter",
        "display_name": "Flutter",
        "framework": "flutter",
        "project_kind": "mobile_web",
        "source_root": "apps/mobile",
        "web_build_command": "scripts/build_web_preview.sh",
        "web_build_output": "build/web-preview/{slug}",
        "preview_api_env": "API_BASE_URL",
        "runtime_profile_env": "APP_RUNTIME_PROFILE",
        "api_runtime_env": "API_RUNTIME",
        "supports_android_preview_apk": True,
        "supports_bridge_installable_app": True,
        "supports_workbench_apk_entry": True,
        "cloudflare_preview_required": True,
        "d1_preview_required": True,
        "release_channel": "prerelease",
        "production_ready": False,
        "mock_or_demo": False,
    },
    "svelte": {
        "id": "svelte",
        "display_name": "Svelte",
        "framework": "svelte",
        "project_kind": "web",
        "source_root": "apps/web",
        "web_build_command": "scripts/build_web_preview.sh",
        "web_build_output": "build/web-preview/{slug}",
        "preview_api_env": "VITE_API_BASE_URL",
        "runtime_profile_env": "VITE_APP_RUNTIME_PROFILE",
        "api_runtime_env": "VITE_API_RUNTIME",
        "supports_android_preview_apk": False,
        "supports_bridge_installable_app": False,
        "supports_workbench_apk_entry": False,
        "cloudflare_preview_required": True,
        "d1_preview_required": True,
        "release_channel": "prerelease",
        "production_ready": False,
        "mock_or_demo": False,
    },
}
ALLOWED_FRONTEND_STRATEGIES = frozenset(FRONTEND_STRATEGIES)


@dataclass(frozen=True, slots=True)
class ProjectFactoryManifestInput:
    name: str
    business_type: str
    primary_goal: str
    slug: str | None = None
    platforms: tuple[str, ...] = DEFAULT_PLATFORMS
    backend: str = DEFAULT_BACKEND
    frontend_strategy: str = DEFAULT_FRONTEND_STRATEGY
    logo_mode: str = "generate"
    first_release_mode: str = DEFAULT_FIRST_RELEASE_MODE
    initial_admin_emails: tuple[str, ...] = ()
    visual_reference_paths: tuple[str, ...] = ()
    visual_reference_assets: tuple[Mapping[str, object], ...] = ()
    project_assets: tuple[Mapping[str, object], ...] = ()
    guided_intake_enabled: bool = False


@dataclass(frozen=True, slots=True)
class ProjectFactoryValidationError:
    code: str
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class ProjectFactoryManifestPlan:
    ok: bool
    status: str
    target_path: str | None
    manifest_path: str | None
    manifest: dict[str, Any]
    errors: tuple[ProjectFactoryValidationError, ...]
    next_actions: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": "codex.projectFactoryManifestPlan",
            "version": 1,
            "ok": self.ok,
            "status": self.status,
            "target_path": self.target_path,
            "manifest_path": self.manifest_path,
            "first_release_mode": _first_release_mode_from_manifest(self.manifest),
            "frontend_strategy": _frontend_strategy_from_manifest(self.manifest),
            "manifest": self.manifest,
            "errors": [
                {
                    "code": error.code,
                    "field": error.field,
                    "message": error.message,
                }
                for error in self.errors
            ],
            "next_actions": list(self.next_actions),
        }


class ProjectFactoryManifestService:
    def __init__(self, *, projects_root: str | Path) -> None:
        self._projects_root = Path(projects_root).expanduser().resolve()

    def plan_manifest(
        self,
        request: ProjectFactoryManifestInput,
        *,
        allow_existing: bool = False,
    ) -> ProjectFactoryManifestPlan:
        errors: list[ProjectFactoryValidationError] = []
        name = request.name.strip()
        business_type = _normalize_business_type(request.business_type)
        primary_goal = request.primary_goal.strip()
        slug = request.slug.strip() if request.slug is not None else _normalize_slug(name)

        self._validate_name(name, errors)
        self._validate_business_type(business_type, errors)
        self._validate_primary_goal(primary_goal, errors)
        self._validate_slug(slug, errors)
        self._validate_platforms(request.platforms, errors)
        self._validate_backend(request.backend, errors)
        frontend_strategy = normalize_frontend_strategy(
            request.frontend_strategy,
            request.platforms,
            errors,
        )
        self._validate_logo_mode(request.logo_mode, errors)
        first_release_mode = normalize_first_release_mode(
            request.first_release_mode,
            errors,
        )
        initial_admin_emails = _normalize_admin_emails(
            request.initial_admin_emails,
            errors,
        )
        self._validate_visual_reference_paths(request.visual_reference_paths, errors)

        target_path: Path | None = None
        if slug:
            target_path = (self._projects_root / slug).resolve()
            if not _is_relative_to(target_path, self._projects_root):
                errors.append(
                    ProjectFactoryValidationError(
                        code="unsafe_target_path",
                        field="slug",
                        message="Project target must resolve under PROJECTS_ROOT.",
                    )
                )
            elif target_path.exists() and not allow_existing:
                errors.append(
                    ProjectFactoryValidationError(
                        code="project_already_exists",
                        field="slug",
                        message="A project with this slug already exists.",
                    )
                )

        manifest = (
            _build_manifest(
                name=name,
                slug=slug,
                business_type=business_type,
                primary_goal=primary_goal,
                platforms=request.platforms,
                backend=request.backend,
                frontend_strategy=frontend_strategy,
                logo_mode=request.logo_mode,
                first_release_mode=first_release_mode,
                initial_admin_emails=initial_admin_emails,
                visual_reference_paths=request.visual_reference_paths,
                visual_reference_assets=request.visual_reference_assets,
                project_assets=request.project_assets,
            )
            if not errors
            else {}
        )
        ok = not errors
        manifest_path = (
            str(target_path / ".codex" / "project.yaml")
            if ok and target_path is not None
            else None
        )
        return ProjectFactoryManifestPlan(
            ok=ok,
            status="valid" if ok else "blocked",
            target_path=str(target_path) if target_path is not None else None,
            manifest_path=manifest_path,
            manifest=manifest,
            errors=tuple(errors),
            next_actions=()
            if ok
            else ("Fix validation errors before creating project files.",),
        )

    def _validate_name(
        self,
        name: str,
        errors: list[ProjectFactoryValidationError],
    ) -> None:
        if not name:
            errors.append(
                ProjectFactoryValidationError(
                    "missing_name",
                    "name",
                    "Project name is required.",
                )
            )
        elif len(name) > 80:
            errors.append(
                ProjectFactoryValidationError(
                    "name_too_long",
                    "name",
                    "Project name must be 80 characters or fewer.",
                )
            )

    def _validate_business_type(
        self,
        business_type: str,
        errors: list[ProjectFactoryValidationError],
    ) -> None:
        if not business_type:
            errors.append(
                ProjectFactoryValidationError(
                    "missing_business_type",
                    "business_type",
                    "Business type is required.",
                )
            )
        elif len(business_type) > 80:
            errors.append(
                ProjectFactoryValidationError(
                    "business_type_too_long",
                    "business_type",
                    "Business type must be 80 characters or fewer.",
                )
            )

    def _validate_primary_goal(
        self,
        primary_goal: str,
        errors: list[ProjectFactoryValidationError],
    ) -> None:
        if not primary_goal:
            errors.append(
                ProjectFactoryValidationError(
                    "missing_primary_goal",
                    "primary_goal",
                    "Primary goal is required.",
                )
            )

    def _validate_slug(
        self,
        slug: str,
        errors: list[ProjectFactoryValidationError],
    ) -> None:
        if not slug:
            errors.append(
                ProjectFactoryValidationError(
                    "missing_slug",
                    "slug",
                    "Project slug is required.",
                )
            )
        elif not SLUG_PATTERN.match(slug):
            errors.append(
                ProjectFactoryValidationError(
                    "invalid_slug",
                    "slug",
                    "Project slug must use lowercase letters, numbers, and hyphens.",
                )
            )

    def _validate_platforms(
        self,
        platforms: tuple[str, ...],
        errors: list[ProjectFactoryValidationError],
    ) -> None:
        if not platforms:
            errors.append(
                ProjectFactoryValidationError(
                    "missing_platforms",
                    "platforms",
                    "At least one platform is required.",
                )
            )
            return
        unsupported = sorted(set(platforms) - ALLOWED_PLATFORMS)
        if unsupported:
            errors.append(
                ProjectFactoryValidationError(
                    "unsupported_platform",
                    "platforms",
                    "Unsupported platforms: " + ", ".join(unsupported),
                )
            )

    def _validate_backend(
        self,
        backend: str,
        errors: list[ProjectFactoryValidationError],
    ) -> None:
        if backend not in ALLOWED_BACKENDS:
            errors.append(
                ProjectFactoryValidationError(
                    "unsupported_backend",
                    "backend",
                    "Backend must be fastapi, go, or none.",
                )
            )

    def _validate_logo_mode(
        self,
        logo_mode: str,
        errors: list[ProjectFactoryValidationError],
    ) -> None:
        if logo_mode not in ALLOWED_LOGO_MODES:
            errors.append(
                ProjectFactoryValidationError(
                    "unsupported_logo_mode",
                    "logo_mode",
                    "Logo mode must be upload, generate, or placeholder.",
                )
            )

    def _validate_visual_reference_paths(
        self,
        visual_reference_paths: tuple[str, ...],
        errors: list[ProjectFactoryValidationError],
    ) -> None:
        for index, reference in enumerate(visual_reference_paths):
            if not reference.strip():
                errors.append(
                    ProjectFactoryValidationError(
                        "empty_visual_reference",
                        f"visual_reference_paths[{index}]",
                        "Visual reference paths cannot be empty.",
                    )
                )
                continue
            reference_path = Path(reference)
            if reference_path.is_absolute() or ".." in reference_path.parts:
                errors.append(
                    ProjectFactoryValidationError(
                        "unsafe_visual_reference",
                        f"visual_reference_paths[{index}]",
                        "Visual reference paths must be relative safe paths.",
                    )
                )


def _build_manifest(
    *,
    name: str,
    slug: str,
    business_type: str,
    primary_goal: str,
    platforms: tuple[str, ...],
    backend: str,
    frontend_strategy: str,
    logo_mode: str,
    first_release_mode: str,
    initial_admin_emails: tuple[str, ...],
    visual_reference_paths: tuple[str, ...],
    visual_reference_assets: tuple[Mapping[str, object], ...],
    project_assets: tuple[Mapping[str, object], ...],
) -> dict[str, Any]:
    strategy = _strategy_payload(frontend_strategy, slug)
    is_svelte = frontend_strategy == "svelte"
    runtime_env = str(strategy["runtime_profile_env"])
    api_runtime_env = str(strategy["api_runtime_env"])
    preview_api_env = str(strategy["preview_api_env"])
    return {
        "schema_version": 1,
        "name": name,
        "slug": slug,
        "business_type": business_type,
        "primary_goal": primary_goal,
        "platforms": {platform: platform in platforms for platform in DEFAULT_PLATFORMS},
        "frontend_strategy": frontend_strategy,
        "frontend": {
            "framework": strategy["framework"],
            "strategy": frontend_strategy,
            "display_name": strategy["display_name"],
            "project_kind": strategy["project_kind"],
            "source_root": strategy["source_root"],
            "responsive_web": True,
            "mobile_first": frontend_strategy == "flutter",
            "mobile_template": (
                "flutter-runtime-profiles-auth-admin-notifications-v1"
                if frontend_strategy == "flutter"
                else None
            ),
            "strategy_capabilities": strategy,
        },
        "backend": {
            "framework": backend,
            "default_framework": DEFAULT_BACKEND,
            "template": "fastapi-runtime-profiles-auth-rbac-admin-notifications-v1",
        },
        "runtime_profiles": {
            "required": True,
            "default_profile": "preview",
            "first_release_mode": first_release_mode,
            "allowed": ["mock", "preview", "real", "staging"],
            "env": runtime_env,
            "api_runtime_env": api_runtime_env,
            "preview_api_env": preview_api_env,
            "preview": {
                "default_for_initial_release": True,
                "backend_required": True,
                "mock_or_demo": False,
                "api_runtime": "cloudflare_preview",
                "api_base_url": f"https://preview.nienfos.com/{slug}/api",
                "data_persistence": "cloudflare_d1",
                "release_tag_patterns": [] if is_svelte else ["android-preview-v*"],
            },
            "mock": {
                "opt_in": True,
                "backend_required": False,
                "mock_or_demo": True,
                "seed_role_selector": True,
                "release_tag_patterns": (
                    [] if is_svelte else ["android-mock-v*", "android-local-v*"]
                ),
            },
            "real": {
                "default_for_productive_release": True,
                "backend_required": True,
                "mock_or_demo": False,
                "seed_role_selector": False,
                "release_tag_patterns": [] if is_svelte else ["android-v*"],
            },
            "staging": {
                "backend_required": True,
                "mock_or_demo": False,
                "seed_role_selector": False,
            },
        },
        "research": {
            "business_type_research": True,
            "typical_app_patterns": True,
            "look_and_feel": True,
        },
        "visual_references": {
            "mode": "user_uploaded_or_generated",
            "uploaded_images": list(visual_reference_paths),
            "reference_assets": [dict(asset) for asset in visual_reference_assets],
            "analysis_file": "docs/research/visual-reference-analysis.md",
            "generated_tokens": "design/tokens.yaml",
            "logo_mode": logo_mode,
            "strong_reference_contract": {
                "enabled": True,
                "analyze_each_image": True,
                "required_analysis_per_image": [
                    "screen_structure",
                    "navigation",
                    "headers",
                    "cards",
                    "buttons",
                    "chips_filters",
                    "lists",
                    "iconography",
                    "typographic_hierarchy",
                    "spacing",
                    "border_radius",
                    "empty_states",
                    "primary_actions_position",
                    "dashboard_or_inventory_patterns",
                ],
                "map_references_to_real_screens": True,
                "generic_material_shell_forbidden_when_references_exist": True,
                "derive_design_tokens": True,
                "create_reusable_components": True,
                "preview_before_build": True,
                "visual_validation_required": True,
                "report_required": True,
                "logo_icon_fallback": {
                    "logo_only_also_sets_app_icon_source": True,
                    "app_icon_only_also_sets_logo": True,
                    "preserve_source_bytes": True,
                },
            },
        },
        "asset_depot": {
            "project_assets": [dict(asset) for asset in project_assets],
        },
        "auth": {
            "required": True,
            "email_password": True,
            "registration": True,
            "password_reset": True,
            "google_login": True,
            "google_credentials_status": "pending_credentials",
        },
        "access_control": {
            "model": "rbac",
            "roles": list(DEFAULT_ROLES),
            "permissions_generated_from_domain": True,
            "owner_role": "owner",
            "owner_has_all_permissions": True,
        },
        "admin": {
            "enabled": True,
            "domain_management": True,
            "settings_management": True,
            "user_management": True,
            "role_management": True,
            "permission_management": True,
            "initial_invites": {
                "required_for_web_preview": True,
                "emails": list(initial_admin_emails),
                "default_role": "owner",
                "dedupe": True,
                "delivery": "web_preview_invite_email_or_manual_link",
            },
        },
        "seed_admin": {
            "enabled_by_env": True,
            "username_env": "SEED_ADMIN_USERNAME",
            "email_env": "SEED_ADMIN_EMAIL",
            "password_env": "SEED_ADMIN_PASSWORD",
            "role": "owner",
        },
        "notifications": {
            "enabled": True,
            "channels": ["in_app", "push", "email"],
            "device_tokens": True,
            "templates": True,
            "preferences": True,
        },
        "codex": {
            "feedback_bridge": True,
            "dev_workbench": True,
            "workbench_visibility": {
                "mock": "visible",
                "staging": "internal",
                "real": "hidden",
            },
            "auto_update": True,
            "creation_workflow": {
                "runner": "codex_cli",
                "mode": "generator_reviewer_batches",
                "generator_runs": DEFAULT_CREATION_GENERATOR_RUNS,
                "reviewer_runs": DEFAULT_CREATION_REVIEWER_RUNS,
                "first_release_mode": first_release_mode,
            },
        },
        "sdd": {
            "enabled": True,
            "initial_spec_id": "001-product-foundation",
            "required_artifacts": ["spec.md", "plan.md", "tasks.md", "metadata.yaml"],
        },
        "release": {
            "first_release_mode": first_release_mode,
            "default_runtime_profile": "preview",
            "initial_preview_release_required": True,
            "mock_or_demo_release_required": False,
            "mock_or_demo_release_opt_in": True,
            "productive_release_required": False,
            "ci_contracts": [
                *(
                    [
                        "VITE_APP_RUNTIME_PROFILE must be preview for Initial Preview Release",
                        "VITE_API_RUNTIME must be cloudflare_preview",
                        f"VITE_API_BASE_URL must be https://preview.nienfos.com/{slug}/api",
                        "Svelte web-first must not claim mobile binary or Bridge installability without wrapper strategy",
                        "productive releases must not use localhost, placeholder, or example API URLs",
                    ]
                    if is_svelte
                    else [
                        "android-preview-v tags must use APP_RUNTIME_PROFILE=preview",
                        "android-preview-v tags must use https://preview.nienfos.com/<slug>/api",
                        "android-v tags must not use APP_RUNTIME_PROFILE=mock",
                        "android-v tags must not use LOCAL_DATA_MODE=true",
                        "productive releases must not use localhost, placeholder, or example API URLs",
                        "productive updater metadata must return mock_or_demo=false",
                        "mock releases must use android-mock-v* or android-local-v* tags",
                        "APK assets and release metadata are required",
                        "Workbench integration must be present or blocked with exact command",
                    ]
                ),
            ],
            "app_store_ready": not is_svelte,
            "play_store_ready": not is_svelte,
            "publish_contract": {
                "local_git_commit_required": True,
                "github_repository_required": True,
                "push_required": True,
                "release_status_must_be_explicit": True,
                "bridge_installable_required": not is_svelte,
                "android_preview_apk_required": not is_svelte,
            },
        },
        "cloud": {
            "provider": "aws",
            "deployment_status": "readiness_only",
        },
    }


def _normalize_business_type(value: str) -> str:
    return _normalize_slug(value.strip()).replace("-", "_")


def normalize_first_release_mode(
    value: str | None,
    errors: list[ProjectFactoryValidationError] | None = None,
) -> str:
    raw = (value or DEFAULT_FIRST_RELEASE_MODE).strip().lower()
    aliases = {
        "demo": "mock",
        "local": "mock",
        "mock-demo": "mock",
        "mock_demo": "mock",
    }
    mode = aliases.get(raw, raw)
    if mode in ALLOWED_FIRST_RELEASE_MODES:
        return mode
    message = (
        "firstReleaseMode must be preview by default or mock when an explicit "
        "demo/mock release is requested. Production/promotion is not part of "
        "initial release creation."
    )
    if errors is not None:
        code = (
            "production_initial_release_not_supported"
            if mode in BLOCKED_INITIAL_RELEASE_MODES
            else "unsupported_first_release_mode"
        )
        errors.append(ProjectFactoryValidationError(code, "first_release_mode", message))
    return DEFAULT_FIRST_RELEASE_MODE


def _normalize_admin_emails(
    values: tuple[str, ...],
    errors: list[ProjectFactoryValidationError],
) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        email = raw.strip().lower()
        if not email:
            continue
        if len(email) > 254 or "@" not in email:
            errors.append(
                ProjectFactoryValidationError(
                    "invalid_admin_email",
                    "initial_admin_emails",
                    "Initial admin emails must be valid email addresses.",
                )
            )
            continue
        local, domain = email.rsplit("@", 1)
        if not local or not domain or "." not in domain:
            errors.append(
                ProjectFactoryValidationError(
                    "invalid_admin_email",
                    "initial_admin_emails",
                    "Initial admin emails must be valid email addresses.",
                )
            )
            continue
        if email in seen:
            continue
        seen.add(email)
        normalized.append(email)
    return tuple(normalized)


def normalize_frontend_strategy(
    value: str | None,
    platforms: tuple[str, ...],
    errors: list[ProjectFactoryValidationError] | None = None,
) -> str:
    strategy = (value or DEFAULT_FRONTEND_STRATEGY).strip().lower()
    if not strategy:
        strategy = DEFAULT_FRONTEND_STRATEGY
    if strategy not in ALLOWED_FRONTEND_STRATEGIES:
        if errors is not None:
            errors.append(
                ProjectFactoryValidationError(
                    "unsupported_frontend_strategy",
                    "frontend_strategy",
                    "Frontend strategy must be one of: "
                    + ", ".join(sorted(ALLOWED_FRONTEND_STRATEGIES))
                    + ".",
                )
            )
        return DEFAULT_FRONTEND_STRATEGY
    mobile_platforms = {"android", "ios"} & set(platforms)
    if strategy == "svelte" and mobile_platforms and errors is not None:
        errors.append(
            ProjectFactoryValidationError(
                "unsupported_frontend_strategy_platforms",
                "frontend_strategy",
                "Svelte is web-first in this release and cannot promise "
                "Android/iOS or installable APK output. Select Flutter for "
                "mobile platforms.",
            )
        )
    return strategy


def _first_release_mode_from_manifest(manifest: Mapping[str, Any]) -> str:
    runtime_profiles = manifest.get("runtime_profiles")
    if isinstance(runtime_profiles, Mapping):
        mode = runtime_profiles.get("first_release_mode")
        if isinstance(mode, str) and mode.strip():
            return mode
    release = manifest.get("release")
    if isinstance(release, Mapping):
        mode = release.get("first_release_mode")
        if isinstance(mode, str) and mode.strip():
            return mode
    return DEFAULT_FIRST_RELEASE_MODE


def _frontend_strategy_from_manifest(manifest: Mapping[str, Any]) -> str:
    strategy = manifest.get("frontend_strategy")
    if isinstance(strategy, str) and strategy.strip():
        return strategy
    frontend = manifest.get("frontend")
    if isinstance(frontend, Mapping):
        strategy = frontend.get("strategy")
        if isinstance(strategy, str) and strategy.strip():
            return strategy
    return DEFAULT_FRONTEND_STRATEGY


def _strategy_payload(strategy: str, slug: str) -> dict[str, Any]:
    payload = dict(FRONTEND_STRATEGIES[strategy])
    payload["web_build_output"] = str(payload["web_build_output"]).format(slug=slug)
    return payload


def _normalize_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value.lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
