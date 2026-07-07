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
DEFAULT_CREATION_GENERATOR_RUNS = 10
DEFAULT_CREATION_REVIEWER_RUNS = 10

ALLOWED_PLATFORMS = frozenset({"ios", "android", "web"})
ALLOWED_BACKENDS = frozenset({"fastapi", "go", "none"})
ALLOWED_LOGO_MODES = frozenset({"upload", "generate", "placeholder"})
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,78}[a-z0-9]$")


@dataclass(frozen=True, slots=True)
class ProjectFactoryManifestInput:
    name: str
    business_type: str
    primary_goal: str
    slug: str | None = None
    platforms: tuple[str, ...] = DEFAULT_PLATFORMS
    backend: str = DEFAULT_BACKEND
    logo_mode: str = "generate"
    visual_reference_paths: tuple[str, ...] = ()
    visual_reference_assets: tuple[Mapping[str, object], ...] = ()


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
        self._validate_logo_mode(request.logo_mode, errors)
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
                logo_mode=request.logo_mode,
                visual_reference_paths=request.visual_reference_paths,
                visual_reference_assets=request.visual_reference_assets,
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
    logo_mode: str,
    visual_reference_paths: tuple[str, ...],
    visual_reference_assets: tuple[Mapping[str, object], ...],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "name": name,
        "slug": slug,
        "business_type": business_type,
        "primary_goal": primary_goal,
        "platforms": {platform: platform in platforms for platform in DEFAULT_PLATFORMS},
        "frontend": {
            "framework": DEFAULT_FRONTEND,
            "responsive_web": True,
            "mobile_first": True,
            "mobile_template": "flutter-auth-admin-notifications-v1",
        },
        "backend": {
            "framework": backend,
            "default_framework": DEFAULT_BACKEND,
            "template": "fastapi-auth-rbac-admin-notifications-v1",
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
            "auto_update": True,
            "creation_workflow": {
                "runner": "codex_cli",
                "mode": "generator_reviewer_batches",
                "generator_runs": DEFAULT_CREATION_GENERATOR_RUNS,
                "reviewer_runs": DEFAULT_CREATION_REVIEWER_RUNS,
            },
        },
        "sdd": {
            "enabled": True,
            "initial_spec_id": "001-product-foundation",
            "required_artifacts": ["spec.md", "plan.md", "tasks.md", "metadata.yaml"],
        },
        "release": {
            "data_mode": "real",
            "mock_or_demo_release": False,
            "app_store_ready": True,
            "play_store_ready": True,
        },
        "cloud": {
            "provider": "aws",
            "deployment_status": "readiness_only",
        },
    }


def _normalize_business_type(value: str) -> str:
    return _normalize_slug(value.strip()).replace("-", "_")


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
