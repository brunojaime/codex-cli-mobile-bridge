from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.application.services.asset_depot_service import (
    AssetDepotService,
)
from backend.app.application.services.project_factory_manifest_service import (
    ProjectFactoryManifestPlan,
)
from backend.app.application.services.project_factory_reference_asset_service import (
    ProjectFactoryReferenceAsset,
    ProjectFactoryReferenceAssetService,
)


@dataclass(frozen=True, slots=True)
class ProjectFactoryGeneratedFile:
    path: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ProjectFactoryGenerationResult:
    ok: bool
    status: str
    target_path: str
    generated_files: tuple[ProjectFactoryGeneratedFile, ...]
    git_status: str
    message: str

    def to_payload(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "status": self.status,
            "target_path": self.target_path,
            "generated_files": [
                {"path": item.path, "size_bytes": item.size_bytes}
                for item in self.generated_files
            ],
            "git_status": self.git_status,
            "message": self.message,
        }


class ProjectFactoryGeneratorError(RuntimeError):
    pass


class ProjectFactoryGeneratorService:
    def __init__(
        self,
        *,
        reference_asset_service: ProjectFactoryReferenceAssetService | None = None,
        asset_depot_service: AssetDepotService | None = None,
    ) -> None:
        self._reference_asset_service = reference_asset_service
        self._asset_depot_service = asset_depot_service

    def generate(
        self,
        manifest_plan: ProjectFactoryManifestPlan,
        *,
        reference_assets: Sequence[ProjectFactoryReferenceAsset] = (),
        project_assets: Sequence[object] = (),
    ) -> ProjectFactoryGenerationResult:
        if not manifest_plan.ok or not manifest_plan.target_path:
            raise ProjectFactoryGeneratorError(
                "Manifest plan must be valid before generation."
            )
        target = Path(manifest_plan.target_path).expanduser().resolve()
        if target.exists():
            raise ProjectFactoryGeneratorError(
                f"Target project already exists: {target}"
            )

        written: list[ProjectFactoryGeneratedFile] = []
        try:
            target.mkdir(parents=False)
            for relative_path, content in _project_files(manifest_plan.manifest).items():
                path = target / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                if relative_path.startswith("scripts/") and relative_path.endswith(".sh"):
                    path.chmod(0o755)
                written.append(
                    ProjectFactoryGeneratedFile(
                        path=relative_path,
                        size_bytes=path.stat().st_size,
                    )
                )
            for relative_dir in (
                "assets/reference/uploaded",
                "assets/source",
                "assets/brand",
                "apps/mobile",
                "apps/mobile/assets/brand",
                "backend",
                "references/images",
                "references/documents",
            ):
                directory = target / relative_dir
                directory.mkdir(parents=True, exist_ok=True)
                gitkeep = directory / ".gitkeep"
                if not gitkeep.exists():
                    gitkeep.write_text("", encoding="utf-8")
                    written.append(
                        ProjectFactoryGeneratedFile(
                            path=str(gitkeep.relative_to(target)),
                            size_bytes=0,
                        )
                    )
            if reference_assets:
                if self._reference_asset_service is None:
                    raise ProjectFactoryGeneratorError(
                        "Reference asset service is required to copy assets."
                    )
                copied_assets = self._reference_asset_service.copy_assets_to_project(
                    assets=tuple(reference_assets),
                    target_project=target,
                )
                for relative_path in copied_assets:
                    path = target / relative_path
                    written.append(
                        ProjectFactoryGeneratedFile(
                            path=relative_path,
                            size_bytes=path.stat().st_size,
                        )
                    )
            if project_assets:
                if self._asset_depot_service is None:
                    raise ProjectFactoryGeneratorError(
                        "Asset Depot service is required to copy project assets."
                    )
                copied_project_assets = _copy_project_assets_to_project(
                    asset_depot_service=self._asset_depot_service,
                    project_assets=tuple(project_assets),
                    target_project=target,
                )
                for relative_path in copied_project_assets:
                    path = target / relative_path
                    written.append(
                        ProjectFactoryGeneratedFile(
                            path=relative_path,
                            size_bytes=path.stat().st_size,
                        )
                    )
            git_status = _init_git(target)
        except Exception as exc:
            _cleanup_created_target(target)
            if isinstance(exc, ProjectFactoryGeneratorError):
                raise
            raise ProjectFactoryGeneratorError(str(exc)) from exc

        return ProjectFactoryGenerationResult(
            ok=True,
            status="ready",
            target_path=str(target),
            generated_files=tuple(sorted(written, key=lambda item: item.path)),
            git_status=git_status,
            message="Local project foundation generated.",
        )


def _project_files(manifest: dict[str, Any]) -> dict[str, str]:
    name = str(manifest["name"])
    slug = str(manifest["slug"])
    business_type = str(manifest["business_type"])
    primary_goal = str(manifest["primary_goal"])
    frontend_strategy = str(manifest.get("frontend_strategy") or "flutter")
    workflow = manifest["codex"]["creation_workflow"]
    project_assets = manifest.get("asset_depot", {}).get("project_assets", [])
    files = {
        ".codex/project.yaml": _to_yaml(manifest),
        "codex-bridge.yaml": _codex_bridge_yaml(slug, name),
        ".gitignore": _gitignore(),
        "README.md": _readme(name, business_type, primary_goal, frontend_strategy),
        "AGENTS.md": _agents(name),
        "scripts/finalize_local_commit.sh": _finalize_local_commit_script(),
        "scripts/load_bridge_env.sh": _bridge_env_loader_script(),
        "scripts/github_repo_access.sh": _github_repo_access_helper_script(),
        "scripts/publish_project.sh": _publish_script(),
        "scripts/apply_cloudflare_preview.sh": _apply_cloudflare_preview_script(slug),
        "scripts/apply_preview_d1_migrations.sh": _apply_preview_d1_migrations_script(),
        "scripts/validate_cloudflare_cost_posture.sh": (
            _cloudflare_cost_posture_check_script()
        ),
        "scripts/final_readiness_audit.sh": _final_readiness_audit_script(),
        "scripts/smoke_preview_api.sh": _smoke_preview_api_script(slug),
        "scripts/smoke_web_preview.sh": _smoke_web_preview_script(slug),
        "scripts/build_web_preview.sh": _build_web_preview_script(
            slug,
            frontend_strategy,
        ),
        "scripts/deploy_web_preview.sh": _deploy_web_preview_script(slug),
        "scripts/validate_web_preview.sh": _validate_web_preview_script(
            slug,
            frontend_strategy,
        ),
        "scripts/validate_generated_project.sh": _validation_script(
            frontend_strategy,
        ),
        "scripts/validate_initial_preview_release.sh": (
            _initial_preview_release_validation_script(slug, frontend_strategy)
        ),
        "scripts/validate_publication_ready.sh": _publication_validation_script(),
        "scripts/validate_release_profiles.sh": _release_profile_validation_script(),
        "scripts/validate_preview_release_profiles.sh": (
            _preview_release_profile_validation_script(slug, frontend_strategy)
        ),
        "deploy/web-preview/README.md": _web_preview_readme(slug, name),
        "deploy/web-preview/web-preview-manifest.yaml": _to_yaml(
            _web_preview_manifest_payload(slug, name, frontend_strategy)
        ),
        "deploy/web-preview/wrangler.toml.example": _web_preview_wrangler_example(
            slug,
        ),
        "deploy/web-preview/worker/src/index.js": _web_preview_worker_js(slug, name),
        "deploy/web-preview/worker/local_preview_test.mjs": (
            _web_preview_worker_harness_js(slug)
        ),
        "deploy/web-preview/d1/migrations/0001_preview_invites.sql": (
            _web_preview_d1_invites_migration()
        ),
        "deploy/web-preview/d1/migrations/0002_business_records.sql": (
            _web_preview_d1_business_records_migration(slug)
        ),
        "deploy/web-preview/d1/migrations/0003_preview_schema_evolution.sql": (
            _web_preview_d1_schema_evolution_migration()
        ),
        "specs/001-product-foundation/spec.md": _initial_spec(
            name,
            business_type,
            primary_goal,
            workflow,
            project_assets,
            frontend_strategy,
        ),
        "specs/001-product-foundation/plan.md": _initial_plan(
            name,
            frontend_strategy,
        ),
        "specs/001-product-foundation/tasks.md": _initial_tasks(
            frontend_strategy,
        ),
        "specs/001-product-foundation/tree.json": _initial_tree_json(
            frontend_strategy,
        ),
        "specs/001-product-foundation/plans/01-foundation/plan.md": _initial_plan(
            name,
            frontend_strategy,
        ),
        "specs/001-product-foundation/metadata.yaml": _initial_metadata(
            slug,
            name,
            frontend_strategy,
        ),
        ".sdd/spec-index.yaml": _spec_index(slug, name),
        ".sdd/diagram-index.yaml": _diagram_index(),
        "docs/research/business-brief.md": _placeholder_doc(
            "Business Brief",
            "Codex research will summarize the business, users, and product risks here.",
        ),
        "docs/research/typical-apps.md": _placeholder_doc(
            "Typical Apps",
            "Codex research will document common app patterns for this business type here.",
        ),
        "docs/research/visual-reference-analysis.md": _visual_reference_analysis_doc(),
        "docs/research/feature-map.md": _placeholder_doc(
            "Feature Map",
            "Business workflow features and suggested MVP scope will be tracked here.",
        ),
        "docs/workbench.md": _workbench_doc(slug, name, frontend_strategy),
        "design/app-style-guide.md": _placeholder_doc(
            "App Style Guide",
            "Generated look and feel decisions will be documented here.",
        ),
        "design/reference-components.md": _visual_components_contract_doc(),
        "design/tokens.yaml": _to_yaml(
            {
                "schema_version": 1,
                "source": "visual-references-required-when-provided",
                "runtime_profiles": ["mock", "preview", "real", "staging"],
                "colors": {
                    "background": "derived_from_visual_references",
                    "surface": "derived_from_visual_references",
                    "primary_text": "derived_from_visual_references",
                    "secondary_text": "derived_from_visual_references",
                    "accent": "derived_from_visual_references_or_user_palette",
                },
                "typography": {
                    "hierarchy": "derived_from_visual_references",
                },
                "spacing": {
                    "scale": "derived_from_visual_references",
                },
                "components": {
                    "cards": "derived_from_visual_references",
                    "buttons": "derived_from_visual_references",
                    "chips": "derived_from_visual_references",
                    "navigation": "derived_from_visual_references",
                },
            }
        ),
        "design/visual-validation-report.md": _visual_validation_report_template(
            project_assets
        ),
        "infra/aws/recommended-architecture.md": _placeholder_doc(
            "AWS Recommended Architecture",
            "AWS deployment recommendations will be generated here.",
        ),
        "infra/aws/iam-required-permissions.md": _placeholder_doc(
            "IAM Required Permissions",
            "Least-privilege IAM requirements will be generated here.",
        ),
        "infra/aws/deploy-plan.md": _placeholder_doc(
            "Deploy Plan",
            "The deployment plan will be generated here.",
        ),
        "release/app-store-checklist.md": _store_checklist_doc(
            store="App Store",
            frontend_strategy=frontend_strategy,
        ),
        "release/play-store-checklist.md": _store_checklist_doc(
            store="Play Store",
            frontend_strategy=frontend_strategy,
        ),
        "release/runtime-profiles.md": _runtime_profiles_doc(
            name,
            frontend_strategy,
        ),
        "release/preview-runtime.json": _preview_runtime_json(
            slug,
            name,
            frontend_strategy,
        ),
        "release/preview-signing-policy.json": _preview_signing_policy_json(
            slug,
            frontend_strategy,
        ),
        "release/promotion-contract.json": _promotion_contract_json(
            slug,
            name,
            frontend_strategy,
        ),
        "release/cloudflare-cost-posture.json": _cloudflare_cost_posture_json(slug),
        "release/release-contracts.yaml": _release_contracts_yaml(
            slug,
            frontend_strategy,
        ),
        "release/release-output-template.md": _release_output_template(
            frontend_strategy,
        ),
        "release/promotion-runbook.md": _promotion_runbook_doc(
            slug,
            name,
            frontend_strategy,
        ),
        "release/android-preview-signing.md": _android_preview_signing_doc(
            slug,
            frontend_strategy,
        ),
        "release/preview-operations-runbook.md": _preview_operations_runbook(
            slug,
            frontend_strategy,
        ),
        "release/aws-domain-delegation-runbook.md": (
            _aws_domain_delegation_runbook(slug)
        ),
        "release/email-provider-runbook.md": _email_provider_runbook(slug),
        "release/dns-cloudflare-troubleshooting.md": (
            _dns_cloudflare_troubleshooting_runbook(slug)
        ),
        "release/false-readiness-runbook.md": _false_readiness_runbook(
            slug,
            frontend_strategy,
        ),
    }
    files.update(_baseline_diagram_files(name, business_type, primary_goal, frontend_strategy))
    files.update(_initial_task_node_files(frontend_strategy))
    files.update(_backend_files(slug))
    if frontend_strategy == "svelte":
        files.update(_svelte_files(name, slug))
    else:
        files.update(
            {
                ".github/workflows/android-release.yml": (
                    _generated_android_release_workflow(slug)
                ),
                ".github/workflows/android-preview-release.yml": (
                    _generated_android_preview_release_workflow(slug)
                ),
                "scripts/publish_android_preview_release.sh": (
                    _publish_android_preview_release_script(slug)
                ),
                "scripts/publish_android_release.sh": _publish_android_release_script(),
                "scripts/register_installable_app.sh": _register_installable_app_script(
                    slug,
                    name,
                ),
            }
        )
        files.update(_mobile_files(name, slug))
    return files


def _readme(
    name: str,
    business_type: str,
    primary_goal: str,
    frontend_strategy: str = "flutter",
) -> str:
    if frontend_strategy == "svelte":
        return f"""# {name}

Generated by Codex Mobile Bridge Project Factory.

## Product

- Business type: `{business_type}`
- Primary goal: {primary_goal}
- Frontend strategy: `svelte`
- Initial runtime profile: `VITE_APP_RUNTIME_PROFILE=preview`. Mock/demo is
  opt-in and production `real` is a later explicit promotion.

## Structure

- `.codex/project.yaml`: source of truth for project generation and validation.
- `specs/001-product-foundation/`: initial SDD package for Workbench-driven work.
- `architecture/`: baseline Workbench diagrams for Svelte web, API, D1, and deployment.
- `apps/web/`: Svelte/Vite web app target.
- `backend/`: API target.
- `docs/research/`: business, UX, and visual research.
- `design/`: visual direction and design tokens.
- `infra/aws/`: AWS readiness notes for future production infrastructure.
- `release/`: web preview, runtime profile, and release contract readiness.
- `deploy/web-preview/`: Cloudflare web preview manifest, Worker scaffold, D1
  migrations, and Wrangler example with no secrets.
- `scripts/build_web_preview.sh`: builds the Svelte web artifact for preview.
- `scripts/validate_web_preview.sh`: validates preview manifest/runtime guardrails.

This strategy is web-only. It does not generate a native mobile package, Codex
Mobile catalog registration, or native marketplace readiness. A future wrapper
strategy must be implemented before claiming mobile installability.

## Validation

Run the generated backend and web contract validation with:

```bash
scripts/validate_generated_project.sh
```

Validate the Cloudflare web preview bundle locally with:

```bash
scripts/validate_web_preview.sh
```

The script uses process-local validation credentials unless `DATABASE_URL`,
`SECRET_KEY`, `ADMIN_EMAIL`, and `ADMIN_INITIAL_PASSWORD` are already set. It
does not write secrets to repository files.

## Runtime Profiles

Initial preview releases must use the Cloudflare preview API:

```bash
VITE_APP_RUNTIME_PROFILE=preview
VITE_API_RUNTIME=cloudflare_preview
VITE_API_BASE_URL=https://preview.nienfos.com/<slug>/api
```

Productive web releases must be an explicit promotion:

```bash
VITE_APP_RUNTIME_PROFILE=real
VITE_API_BASE_URL=https://your-real-backend.example
```

Early demo builds must be explicit:

```bash
VITE_APP_RUNTIME_PROFILE=mock
```

Preview output is not complete until Cloudflare public web health,
`/api/health`, D1 migrations, and generated validation all pass.

## Publish Contract

Project Factory must not leave this project as an uncommitted local scaffold.
The generated baseline is committed locally by the factory. After validation,
publish the repository with:

```bash
GITHUB_OWNER=<owner> scripts/publish_project.sh
```

The script creates or verifies the GitHub repository, pushes the current branch,
and reports the remote URL. Public preview readiness remains blocked until the
Cloudflare Worker, route, assets, and D1 evidence are present.
"""
    return f"""# {name}

Generated by Codex Mobile Bridge Project Factory.

## Product

- Business type: `{business_type}`
- Primary goal: {primary_goal}
- Initial runtime profile: `APP_RUNTIME_PROFILE=preview`. Mock/demo is opt-in
  and production `real` is a later explicit promotion.

## Structure

- `.codex/project.yaml`: source of truth for project generation and validation.
- `specs/001-product-foundation/`: initial SDD package for Workbench-driven work.
- `architecture/`: baseline Workbench diagrams for components, classes, data, and deployment.
- `apps/mobile/`: Flutter app target when `frontend_strategy=flutter`.
- `apps/web/`: Svelte/Vite app target when `frontend_strategy=svelte`.
- `backend/`: API target.
- `docs/research/`: business, UX, and visual research.
- `design/`: visual direction and design tokens.
- `infra/aws/`: AWS readiness.
- `release/`: App Store, Play Store, runtime profile, and release contract readiness.
- `deploy/web-preview/`: Cloudflare web preview manifest, Worker scaffold, and
  Wrangler example with no secrets.
- `scripts/validate_release_profiles.sh`: guardrails for mock/demo vs productive releases.
- `scripts/build_web_preview.sh`: builds the selected frontend web artifact for preview.
- `scripts/validate_web_preview.sh`: validates preview manifest/runtime guardrails.
- `scripts/register_installable_app.sh`: Flutter-only Bridge Apps catalog
  registration after an APK release.

## Validation

Run the generated backend and mobile contract validation with:

```bash
scripts/validate_generated_project.sh
```

Validate the Cloudflare web preview bundle locally with:

```bash
scripts/validate_web_preview.sh
```

The script uses process-local validation credentials unless `DATABASE_URL`,
`SECRET_KEY`, `ADMIN_EMAIL`, and `ADMIN_INITIAL_PASSWORD` are already set. It
does not write secrets to repository files.

## Runtime Profiles

Productive releases must use:

```bash
APP_RUNTIME_PROFILE=real
API_BASE_URL=https://your-real-backend.example
```

Initial preview releases must use:

```bash
APP_RUNTIME_PROFILE=preview
API_RUNTIME=cloudflare_preview
API_BASE_URL=https://preview.nienfos.com/<slug>/api
```

Early demo releases must be explicit:

```bash
APP_RUNTIME_PROFILE=mock
```

Mock/demo APKs use `android-mock-vX.Y.Z-build.N` or
`android-local-vX.Y.Z-build.N` tags and can show seed role selectors. Productive
`android-vX.Y.Z-build.N` releases must never include mock/local data, visible
seed users, localhost API URLs, placeholder API URLs, or visible
Workbench/developer tooling.

## Publish Contract

Project Factory must not leave this project as an uncommitted local scaffold.
The generated baseline is committed locally by the factory. After validation,
publish the repository with:

```bash
GITHUB_OWNER=<owner> scripts/publish_project.sh
```

The script creates or verifies the GitHub repository, pushes the current branch,
and reports the remote URL. Mobile/App Store/Play Store releases still require
their credentials and release workflow configuration; if those are missing, keep
the release state explicit in `release/` and do not mark the project fully
published.

After an Android APK release exists, register the app in Codex Mobile:

```bash
BRIDGE_URL=http://127.0.0.1:8000 \\
BRIDGE_REGISTRATION_TOKEN=<token> \\
scripts/register_installable_app.sh
```

The project is not installable from Codex Mobile until
`/installable-apps/{{sourceApp}}` returns this app with an APK URL.
"""


def _codex_bridge_yaml(slug: str, name: str) -> str:
    return _to_yaml(
        {
            "sourceApp": slug,
            "workspaceLabel": name,
            "sdd": {
                "standard": "workbench-sdd/v1",
                "specIndex": ".sdd/spec-index.yaml",
                "diagramIndex": ".sdd/diagram-index.yaml",
            },
            "feedback": {
                "bridgeRequired": True,
                "enabledProfiles": ["mock", "preview", "staging"],
                "hiddenProfiles": ["real"],
            },
            "workbench": {
                "required": True,
                "docs": "docs/workbench.md",
                "visibleProfiles": ["mock", "preview"],
                "visibleRoles": ["owner", "admin"],
                "developerAuthorizedProfiles": ["mock", "preview", "staging"],
                "hiddenProfiles": ["real"],
            },
        }
    )


def _workbench_doc(
    slug: str,
    name: str,
    frontend_strategy: str = "flutter",
) -> str:
    runtime_env = (
        "VITE_APP_RUNTIME_PROFILE"
        if frontend_strategy == "svelte"
        else "APP_RUNTIME_PROFILE"
    )
    frontend_note = (
        "The Svelte web strategy exposes SDD artifacts to Bridge Workbench only. "
        "It does not imply an installable mobile artifact or product Workbench route."
        if frontend_strategy == "svelte"
        else "The Flutter strategy must not expose Bridge Workbench as product "
        "navigation. Bridge opens SDD artifacts through a Bridge-owned entry point."
    )
    return f"""# Workbench

`{name}` is generated with Workbench SDD artifacts from the first commit.

## Identity

- `sourceApp`: `{slug}`
- SDD standard: `workbench-sdd/v1`
- Spec index: `.sdd/spec-index.yaml`
- Diagram index: `.sdd/diagram-index.yaml`

## Runtime Visibility

- `{runtime_env}=mock`: product UI may expose explicit demo/test affordances,
  but Bridge Workbench remains a Bridge-owned development entry point.
- `{runtime_env}=preview`: product navigation must contain only product-domain
  surfaces. Bridge may launch Workbench for this workspace externally.
- `{runtime_env}=staging`: product UI remains product-domain only unless an
  explicit Bridge-owned developer overlay is attached.
- `{runtime_env}=real`: Workbench/developer tooling must be hidden or disabled
  in product UI/build config.

{frontend_note}

Expected visibility contract:

- Product app tabs/routes: no `Workbench` item in any runtime profile.
- Bridge Workbench artifacts: discoverable through `codex-bridge.yaml`,
  `.sdd/spec-index.yaml`, `.sdd/diagram-index.yaml`, and `specs/`.
- Bridge launch: Codex Mobile Bridge opens the workspace by `sourceApp`.
- Product RBAC: owner/admin roles do not grant Bridge Workbench UI permissions
  inside the generated app.

## Bridge Registration

If the Bridge does not discover this project automatically, run:

```bash
codex-mobile-bridge register-workspace --source-app {slug} --path "$(pwd)"
```

If that command is unavailable, keep this as an explicit release blocker in
`release/release-output-template.md` until the Bridge registration is completed.
"""


def _backend_files(slug: str) -> dict[str, str]:
    return {
        "backend/pyproject.toml": _backend_pyproject(slug),
        "backend/.env.example": _backend_env_example(),
        "backend/README.md": _backend_readme(),
        "backend/app/__init__.py": "",
        "backend/app/config.py": _backend_config_py(),
        "backend/app/db.py": _backend_db_py(),
        "backend/app/security.py": _backend_security_py(),
        "backend/app/main.py": _backend_main_py(),
        "backend/app/routers/__init__.py": "",
        "backend/app/routers/auth.py": _backend_auth_router_py(),
        "backend/app/routers/admin.py": _backend_admin_router_py(),
        "backend/app/routers/notifications.py": _backend_notifications_router_py(),
        "backend/app/routers/google.py": _backend_google_router_py(),
        "backend/app/routers/app_updates.py": _backend_app_updates_router_py(),
        "backend/tests/test_backend.py": _backend_tests_py(),
    }


def _web_preview_manifest_payload(
    slug: str,
    name: str,
    frontend_strategy: str = "flutter",
) -> dict[str, Any]:
    is_svelte = frontend_strategy == "svelte"
    source_root = "apps/web" if is_svelte else "apps/mobile"
    entrypoint = "apps/web/src/main.ts" if is_svelte else "apps/mobile/lib/main.dart"
    required_files = (
        ["index.html"]
        if is_svelte
        else ["index.html", "manifest.json", "flutter_bootstrap.js"]
    )
    return {
        "schema_version": 1,
        "source_app": slug,
        "display_name": name,
        "frontend_strategy": frontend_strategy,
        "stable_url": f"https://preview.nienfos.com/{slug}",
        "runtime": {
            "type": "cloudflare_worker_assets",
            "default_profile": "preview",
            "allowed_profiles": ["real", "staging", "preview", "mock"],
            "api_runtime": "cloudflare_preview",
            "api_base_url": f"https://preview.nienfos.com/{slug}/api",
            "app_slug": slug,
            "health_path": "/api/health",
            "asset_binding": "ASSETS",
            "spa_fallback": "index.html",
            "mock_preview_requires_opt_in": True,
        },
        "first_release": {
            "mode": "preview",
            "runtime_profile": "preview",
            "api_runtime": "cloudflare_preview",
            "api_base_url": f"https://preview.nienfos.com/{slug}/api",
            "preview_url": f"https://preview.nienfos.com/{slug}",
            "android_tag_pattern": None if is_svelte else "android-preview-v*",
            "android_release_channel": "prerelease",
            "backend_required": True,
            "mock_or_demo": False,
            "data_persistence": "cloudflare_d1",
            "production_android_release_deferred": True,
            "installable_android": not is_svelte,
            "bridge_registration_required": not is_svelte,
        },
        "access": {
            "mode": "invite_token",
            "recommended_default": True,
            "audience": "codex.web-preview",
            "scope": "web_preview:access",
            "access_path": "/__preview/access",
            "token_query_param": "token",
            "cookie_name": "codex_preview_access",
            "single_use": True,
            "acceptance_single_use": True,
            "used_invite_access_refresh": True,
            "preview_access_cookie_separate_from_auth_session": True,
            "d1_binding": "PREVIEW_DB",
            "migrations_dir": "deploy/web-preview/d1/migrations",
            "required_worker_secrets": ["WEB_PREVIEW_INVITE_SECRET"],
            "public_paths": ["/__preview/health", "/api/health"],
        },
        "build": {
            "frontend_strategy": frontend_strategy,
            "source_root": source_root,
            "flutter_project": "apps/mobile" if not is_svelte else None,
            "svelte_project": "apps/web" if is_svelte else None,
            "output_dir": f"build/web-preview/{slug}",
            "entrypoint": entrypoint,
            "script": "scripts/build_web_preview.sh",
            "validation_script": "scripts/validate_web_preview.sh",
            "asset_entrypoint": "index.html",
            "required_files": required_files,
        },
        "cloudflare": {
            "provider": "cloudflare",
            "base_domain": "preview.nienfos.com",
            "route": f"preview.nienfos.com/{slug}/*",
            "resources": {
                "worker_name": "nienfos-preview-runtime",
                "pages_project": "nienfos-preview-web",
                "d1_database": "nienfos-preview",
                "r2_bucket": None,
            },
            "required_env": [
                "CLOUDFLARE_API_TOKEN",
                "CLOUDFLARE_DNS_API_TOKEN",
                "CLOUDFLARE_ACCOUNT_ID",
                "CLOUDFLARE_ZONE_ID",
                "PREVIEW_BASE_DOMAIN",
            ],
            "secrets_in_repo": False,
        },
        "expected_routes": [
            f"/{slug}/",
            f"/{slug}/__preview/health",
            f"/{slug}/__preview/access",
            f"/{slug}/api/health",
            f"/{slug}/api/auth/login",
            f"/{slug}/api/auth/me",
            f"/{slug}/api/app-updates/current",
            f"/{slug}/api/business/records",
            f"/{slug}/api/notifications",
            f"/{slug}/apps/{slug}/config",
            f"/{slug}/dashboard",
        ],
        "preview_api_v1": {
            "base_url": f"https://preview.nienfos.com/{slug}/api",
            "health": "/api/health",
            "app_config": f"/apps/{slug}/config",
            "auth": ["/api/auth/login", "/api/auth/logout", "/api/auth/me"],
            "admin": ["/api/admin/bootstrap", "/api/admin/users", "/api/admin/roles"],
            "notifications": ["/api/notifications", "/api/notifications/{id}"],
            "business_records": "/api/business/records",
            "app_updates": "/api/app-updates/current",
        },
    }


def _web_preview_readme(slug: str, name: str) -> str:
    return f"""# Web Preview Delivery

`{name}` includes a generated web preview bundle contract for:

```text
https://preview.nienfos.com/{slug}
```

This folder is deployable metadata and runtime scaffolding only. It does not
contain Cloudflare tokens and does not provision resources by itself.

## Local validation

```bash
scripts/validate_web_preview.sh
```

## Build web artifact

```bash
API_BASE_URL=https://preview.nienfos.com/{slug}/api \\
APP_RUNTIME_PROFILE=preview \\
API_RUNTIME=cloudflare_preview \\
APP_SLUG={slug} \\
scripts/build_web_preview.sh
```

Mock preview builds are blocked unless explicitly requested:

```bash
ALLOW_MOCK_WEB_PREVIEW=true APP_RUNTIME_PROFILE=mock scripts/validate_web_preview.sh
```

## Bridge deploy flow

Apply is intentionally gated by the Bridge:

```bash
BRIDGE_URL=http://127.0.0.1:8000 scripts/deploy_web_preview.sh --plan
BRIDGE_URL=http://127.0.0.1:8000 \\
EXPECTED_PLAN_HASH=<hash-from-plan> \\
CONFIRM_APPLY=true \\
scripts/deploy_web_preview.sh --apply
```

The Bridge must also have `WEB_PREVIEW_APPLY_ENABLED=true` and Cloudflare
operator secrets configured. Missing gates return explicit errors such as
`apply_disabled`, `dry_run_required`, or `cloudflare_configuration_missing`.

## Invite access

The generated preview defaults to `access.mode=invite_token`. Health is public,
but the SPA and static assets require a signed invite token.

The generated Worker is also the first real backend for the app. Its Preview API
is served from:

```text
https://preview.nienfos.com/{slug}/api
```

It must pass health, auth/session, D1 persistence, app-update metadata, domain
CRUD, notifications, and app-scope isolation smoke tests before an
`android-preview-v*` APK can be released or registered in Codex Mobile Apps.

1. The Bridge operator configures `WEB_PREVIEW_INVITE_SECRET` on the Bridge.
2. The Worker gets the same value as an operator-managed Worker secret:

```bash
wrangler secret put WEB_PREVIEW_INVITE_SECRET
```

3. Apply the D1 migration in `deploy/web-preview/d1/migrations/` to the shared
preview D1 database before enabling invite-token access. Without D1 the Worker
can validate HMAC tokens, but strong revoke and single-use enforcement are not
available and apply must stay blocked.

4. Create an invite after a dry-run plan exists:

```bash
curl -X POST "$BRIDGE_URL/web-previews/wp-{slug}/invites" \\
  -H 'content-type: application/json' \\
  -d '{{"ttlSeconds":604800,"singleUse":true}}'
```

5. The Bridge syncs invite rows into D1 during deploy apply and after later
create/revoke operations. The row uses `invite_id`, `token_sha256`, app fields,
expiration, `single_use`, and `revoked_at`; plaintext tokens are never stored or
sent to D1. If sync fails, retry it from the Bridge:

```bash
curl -X POST "$BRIDGE_URL/web-previews/wp-{slug}/invites/<invite-id>/sync"
```

6. Open the returned `invite_url`. The Worker validates the token, checks D1,
sets or refreshes the preview-access HttpOnly cookie, and redirects to the app.
If the invite is unused, the redirect includes URL state for account activation;
if it is already used but still valid, the redirect opens normal login.

7. The generated app accepts the invite through `/api/invites/accept` exactly
once with email, password, and password confirmation. That endpoint marks
`used_at` atomically when `single_use=true`. The Bridge stores invite metadata
and token SHA256 only, never the plaintext token.
"""


def _web_preview_wrangler_example(slug: str) -> str:
    return f"""# Example only. Copy to wrangler.toml in an operator-owned deployment
# workspace and fill Cloudflare resource IDs there. Do not commit secrets.
name = "nienfos-preview-runtime"
main = "worker/src/index.js"
compatibility_date = "2026-07-01"

routes = [
  {{ pattern = "preview.nienfos.com/{slug}/*", zone_name = "nienfos.com" }}
]

[[d1_databases]]
binding = "PREVIEW_DB"
database_name = "nienfos-preview"
database_id = "set-in-cloudflare-dashboard-or-doctor-output"

[assets]
binding = "ASSETS"
directory = "../../build/web-preview/{slug}"
# Protected previews must let the Worker own SPA fallback after access checks.

[vars]
PREVIEW_ACCESS_MODE = "invite_token"
APP_RUNTIME_PROFILE = "preview"
API_RUNTIME = "cloudflare_preview"
APP_SLUG = "{slug}"
API_BASE_URL = "https://preview.nienfos.com/{slug}/api"
# Configure the real value as a Worker secret, not here:
# wrangler secret put WEB_PREVIEW_INVITE_SECRET
"""


def _web_preview_d1_invites_migration() -> str:
    return """-- Web Preview Delivery access control.
-- Apply to the shared preview D1 database before enabling invite_token access.

CREATE TABLE IF NOT EXISTS preview_invites (
  invite_id TEXT PRIMARY KEY,
  token_sha256 TEXT NOT NULL UNIQUE,
  source_app TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  single_use INTEGER NOT NULL DEFAULT 1,
  email TEXT,
  role TEXT NOT NULL DEFAULT 'admin',
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT,
  revoked_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_preview_invites_token_sha256
  ON preview_invites(token_sha256);

CREATE INDEX IF NOT EXISTS idx_preview_invites_app
  ON preview_invites(source_app, app_slug);

CREATE TABLE IF NOT EXISTS preview_apps (
  source_app TEXT PRIMARY KEY,
  app_slug TEXT NOT NULL,
  display_name TEXT NOT NULL,
  stable_url TEXT NOT NULL,
  api_base_url TEXT NOT NULL,
  runtime_profile TEXT NOT NULL DEFAULT 'preview',
  api_runtime TEXT NOT NULL DEFAULT 'cloudflare_preview',
  lifecycle_status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  expires_at TEXT,
  disabled_at TEXT,
  disabled_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_preview_apps_slug
  ON preview_apps(app_slug);

CREATE TABLE IF NOT EXISTS preview_builds (
  build_id TEXT PRIMARY KEY,
  source_app TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  release_channel TEXT NOT NULL DEFAULT 'preview',
  release_tag TEXT,
  commit_sha TEXT,
  artifact_url TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  FOREIGN KEY(source_app) REFERENCES preview_apps(source_app)
);

CREATE INDEX IF NOT EXISTS idx_preview_builds_app_created
  ON preview_builds(source_app, app_slug, created_at);

CREATE TABLE IF NOT EXISTS preview_tenants (
  tenant_id TEXT PRIMARY KEY,
  source_app TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  display_name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(source_app, app_slug, display_name)
);

CREATE INDEX IF NOT EXISTS idx_preview_tenants_app
  ON preview_tenants(source_app, app_slug, status);

CREATE TABLE IF NOT EXISTS preview_access_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invite_id TEXT,
  source_app TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS preview_users (
  user_id TEXT PRIMARY KEY,
  source_app TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  email TEXT NOT NULL,
  display_name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  roles_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(source_app, app_slug, email)
);

CREATE INDEX IF NOT EXISTS idx_preview_users_app_email
  ON preview_users(source_app, app_slug, email);

CREATE TABLE IF NOT EXISTS preview_roles (
  role_id TEXT PRIMARY KEY,
  source_app TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  role_name TEXT NOT NULL,
  permissions_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(source_app, app_slug, role_name)
);

CREATE INDEX IF NOT EXISTS idx_preview_roles_app_name
  ON preview_roles(source_app, app_slug, role_name);

CREATE TABLE IF NOT EXISTS preview_admin_invites (
  admin_invite_id TEXT PRIMARY KEY,
  invite_id TEXT,
  source_app TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  email TEXT NOT NULL,
  role_name TEXT NOT NULL DEFAULT 'admin',
  delivery_status TEXT NOT NULL DEFAULT 'pending',
  delivery_error TEXT,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  accepted_at TEXT,
  revoked_at TEXT,
  UNIQUE(source_app, app_slug, email, revoked_at)
);

CREATE INDEX IF NOT EXISTS idx_preview_admin_invites_app_email
  ON preview_admin_invites(source_app, app_slug, email);

CREATE TABLE IF NOT EXISTS preview_sessions (
  session_id TEXT PRIMARY KEY,
  source_app TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  user_id TEXT NOT NULL,
  token_sha256 TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  revoked_at TEXT,
  FOREIGN KEY(user_id) REFERENCES preview_users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_preview_sessions_token
  ON preview_sessions(token_sha256);

CREATE TABLE IF NOT EXISTS preview_audit_events (
  event_id TEXT PRIMARY KEY,
  source_app TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  event_type TEXT NOT NULL,
  actor TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_preview_audit_events_app
  ON preview_audit_events(source_app, app_slug, created_at);

CREATE TABLE IF NOT EXISTS preview_app_updates (
  source_app TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  release_channel TEXT NOT NULL DEFAULT 'prerelease',
  release_tag TEXT NOT NULL,
  version TEXT NOT NULL,
  build_number TEXT NOT NULL,
  apk_url TEXT,
  sha256 TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  PRIMARY KEY(source_app, app_slug, release_channel)
);

CREATE TABLE IF NOT EXISTS preview_business_records (
  record_id TEXT PRIMARY KEY,
  source_app TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_preview_business_records_app
  ON preview_business_records(source_app, app_slug, created_at);

CREATE TABLE IF NOT EXISTS preview_assets (
  asset_id TEXT PRIMARY KEY,
  source_app TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  asset_type TEXT NOT NULL,
  path TEXT NOT NULL,
  content_type TEXT,
  sha256 TEXT,
  size_bytes INTEGER,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  UNIQUE(source_app, app_slug, path)
);

CREATE INDEX IF NOT EXISTS idx_preview_assets_app_type
  ON preview_assets(source_app, app_slug, asset_type);

CREATE TABLE IF NOT EXISTS preview_events (
  event_id TEXT PRIMARY KEY,
  source_app TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  event_type TEXT NOT NULL,
  subject_type TEXT,
  subject_id TEXT,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_preview_events_app_type
  ON preview_events(source_app, app_slug, event_type, created_at);

CREATE TABLE IF NOT EXISTS preview_notifications (
  notification_id TEXT PRIMARY KEY,
  source_app TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  user_id TEXT,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  read_at TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_preview_notifications_app_user
  ON preview_notifications(source_app, app_slug, user_id);
"""


def _web_preview_d1_business_records_migration(slug: str) -> str:
    return f"""-- Generated business records storage for {slug} Initial Preview Release.
-- This migration is intentionally separate from auth/session/update tables.
-- It is app-scoped and idempotent so it can be safely reapplied.

CREATE TABLE IF NOT EXISTS preview_business_record_events (
  event_id TEXT PRIMARY KEY,
  source_app TEXT NOT NULL,
  app_slug TEXT NOT NULL,
  record_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{{}}',
  created_at TEXT NOT NULL,
  FOREIGN KEY(record_id) REFERENCES preview_business_records(record_id)
);

CREATE INDEX IF NOT EXISTS idx_preview_business_record_events_app_record
  ON preview_business_record_events(source_app, app_slug, record_id);

CREATE INDEX IF NOT EXISTS idx_preview_business_record_events_app_type
  ON preview_business_record_events(source_app, app_slug, event_type);
"""


def _web_preview_d1_schema_evolution_migration() -> str:
    return """-- Project Factory D1 schema evolution directives.
-- These directives are applied by scripts/apply_preview_d1_migrations.sh and
-- Bridge WebPreviewDeployService with column checks before ALTER TABLE.
-- codex:d1:add-column preview_invites email TEXT
-- codex:d1:add-column preview_invites role TEXT NOT NULL DEFAULT 'admin'
-- codex:d1:add-column preview_app_updates sha256 TEXT
-- codex:d1:backfill preview_invites role 'admin' role IS NULL OR role = ''
"""


def _web_preview_worker_js(slug: str, name: str) -> str:
    template = """const SOURCE_APP = '__SOURCE_APP__';
const DISPLAY_NAME = __DISPLAY_NAME__;
const DEFAULT_RUNTIME_PROFILE = 'preview';
const API_RUNTIME = 'cloudflare_preview';
const ACCESS_MODE = 'invite_token';
const INVITE_AUDIENCE = 'codex.web-preview';
const INVITE_SCOPE = 'web_preview:access';
const ACCESS_COOKIE_NAME = 'codex_preview_access';
const STATIC_ASSET_EXTENSIONS = new Set([
  '.avif',
  '.bin',
  '.css',
  '.gif',
  '.ico',
  '.jpg',
  '.js',
  '.json',
  '.map',
  '.otf',
  '.png',
  '.svg',
  '.wasm',
  '.webp',
  '.woff',
  '.woff2',
]);

function json(payload, init = {{}}) {{
  return new Response(JSON.stringify(payload), {
    ...init,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      ...securityHeaders(),
      ...(init.headers || {{}}),
    }},
  });
}

function appSlugFromPath(pathname) {
  const parts = pathname.split('/').filter(Boolean);
  return parts.length > 0 ? parts[0] : SOURCE_APP;
}

function stripAppPrefix(pathname) {
  const prefix = `/${SOURCE_APP}`;
  if (pathname === prefix) {
    return '/';
  }
  if (pathname.startsWith(`${prefix}/`)) {
    return pathname.slice(prefix.length) || '/';
  }
  return pathname || '/';
}

function contentTypeFor(pathname) {
  const clean = pathname.toLowerCase();
  if (clean.endsWith('.html')) return 'text/html; charset=utf-8';
  if (clean.endsWith('.js')) return 'application/javascript; charset=utf-8';
  if (clean.endsWith('.css')) return 'text/css; charset=utf-8';
  if (clean.endsWith('.json') || clean.endsWith('.webmanifest')) return 'application/json; charset=utf-8';
  if (clean.endsWith('.svg')) return 'image/svg+xml';
  if (clean.endsWith('.png')) return 'image/png';
  if (clean.endsWith('.jpg') || clean.endsWith('.jpeg')) return 'image/jpeg';
  if (clean.endsWith('.webp')) return 'image/webp';
  if (clean.endsWith('.wasm')) return 'application/wasm';
  if (clean.endsWith('.woff2')) return 'font/woff2';
  if (clean.endsWith('.woff')) return 'font/woff';
  if (clean.endsWith('.otf')) return 'font/otf';
  return 'application/octet-stream';
}

function securityHeaders() {
  return {
    'x-content-type-options': 'nosniff',
    'referrer-policy': 'strict-origin-when-cross-origin',
    'permissions-policy': 'camera=(), microphone=(), geolocation=()',
    'content-security-policy': "default-src 'self'; connect-src 'self' https://preview.nienfos.com https://www.gstatic.com https://fonts.gstatic.com; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; script-src 'self' 'wasm-unsafe-eval' https://www.gstatic.com; font-src 'self' data: https://fonts.gstatic.com; worker-src 'self' blob:;",
  };
}

function cacheControlFor(pathname) {
  if (
    pathname === '/' ||
    pathname.endsWith('/index.html') ||
    pathname.endsWith('/flutter_bootstrap.js') ||
    pathname.endsWith('/main.dart.js') ||
    pathname.endsWith('/manifest.json') ||
    pathname.includes('/__preview/access')
  ) {
    return 'no-cache, no-store, must-revalidate';
  }
  if (/[.-][a-f0-9]{8,}\\./i.test(pathname)) {
    return 'public, max-age=31536000, immutable';
  }
  if (pathname.endsWith('.js') || pathname.endsWith('.css')) {
    return 'no-cache, no-store, must-revalidate';
  }
  return 'no-cache';
}

function base64UrlDecode(value) {
  const normalized = value.replace(/-/g, '+').replace(/_/g, '/');
  const padding = '='.repeat((4 - (normalized.length % 4)) % 4);
  const binary = atob(normalized + padding);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

function base64UrlEncode(bytes) {
  let binary = '';
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary).replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/g, '');
}

async function hmacSha256(secret, value) {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const signature = await crypto.subtle.sign(
    'HMAC',
    key,
    new TextEncoder().encode(value),
  );
  return base64UrlEncode(new Uint8Array(signature));
}

async function sha256Hex(value) {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(value),
  );
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

function nowIso() {
  return new Date().toISOString();
}

function randomId(prefix) {
  return `${prefix}_${crypto.randomUUID().replace(/-/g, '')}`;
}

function previewApiBaseUrl(env) {
  return (env.API_BASE_URL || `https://preview.nienfos.com/${SOURCE_APP}/api`).replace(/\/+$/, '');
}

async function readJson(request) {
  try {
    return await request.json();
  } catch (_error) {
    return {};
  }
}

function requirePreviewD1(env) {
  if (!env.PREVIEW_DB || typeof env.PREVIEW_DB.prepare !== 'function') {
    return {
      ok: false,
      response: json({
        error: {
          code: 'd1_required',
          message: 'Cloudflare D1 PREVIEW_DB binding is required.',
        },
      }, { status: 503 }),
    };
  }
  return { ok: true };
}

async function passwordHash(env, password) {
  const pepper = env.PREVIEW_AUTH_SECRET || env.WEB_PREVIEW_INVITE_SECRET || SOURCE_APP;
  return sha256Hex(`${pepper}:${password}`);
}

function base64UrlJson(payload) {
  return base64UrlEncode(new TextEncoder().encode(JSON.stringify(payload)));
}

async function signStructuredToken(env, payload) {
  const header = base64UrlJson({ alg: 'HS256', typ: 'JWT' });
  const body = base64UrlJson(payload);
  const signature = await hmacSha256(env.WEB_PREVIEW_INVITE_SECRET, `${header}.${body}`);
  return `${header}.${body}.${signature}`;
}

async function verifyStructuredToken(env, token) {
  if (!env.WEB_PREVIEW_INVITE_SECRET) {
    return null;
  }
  const parts = (token || '').split('.');
  if (parts.length !== 3) {
    return null;
  }
  const signingInput = `${parts[0]}.${parts[1]}`;
  const expected = await hmacSha256(env.WEB_PREVIEW_INVITE_SECRET, signingInput);
  if (expected !== parts[2]) {
    return null;
  }
  try {
    return JSON.parse(new TextDecoder().decode(base64UrlDecode(parts[1])));
  } catch (_error) {
    return null;
  }
}

function tokenFromCookie(cookieHeader) {
  if (!cookieHeader) {
    return null;
  }
  for (const part of cookieHeader.split(';')) {
    const [name, ...valueParts] = part.trim().split('=');
    if (name === ACCESS_COOKIE_NAME) {
      return decodeURIComponent(valueParts.join('='));
    }
  }
  return null;
}

function tokenFromRequest(request, url) {
  const queryToken = url.searchParams.get('token');
  if (queryToken) {
    return queryToken;
  }
  const auth = request.headers.get('authorization') || '';
  if (auth.toLowerCase().startsWith('bearer ')) {
    return auth.slice(7).trim();
  }
  return tokenFromCookie(request.headers.get('cookie'));
}

function sessionTokenFromRequest(request) {
  return tokenFromCookie(request.headers.get('cookie'));
}

async function verifyInviteToken(env, token) {
  if (!env.WEB_PREVIEW_INVITE_SECRET) {
    return { ok: false, status: 503, code: 'invite_secret_missing' };
  }
  const parts = (token || '').split('.');
  if (parts.length !== 3) {
    return { ok: false, status: 403, code: 'invalid_invite_token' };
  }
  const signingInput = `${parts[0]}.${parts[1]}`;
  const expected = await hmacSha256(env.WEB_PREVIEW_INVITE_SECRET, signingInput);
  if (expected !== parts[2]) {
    return { ok: false, status: 403, code: 'invalid_invite_token' };
  }
  let payload;
  try {
    payload = JSON.parse(new TextDecoder().decode(base64UrlDecode(parts[1])));
  } catch (_error) {
    return { ok: false, status: 403, code: 'invalid_invite_token' };
  }
  const now = Math.floor(Date.now() / 1000);
  if (payload.aud !== INVITE_AUDIENCE || payload.scope !== INVITE_SCOPE) {
    return { ok: false, status: 403, code: 'invalid_invite_token' };
  }
  if (payload.source_app !== SOURCE_APP || payload.app_slug !== SOURCE_APP) {
    return { ok: false, status: 403, code: 'invalid_invite_app' };
  }
  if (!payload.exp || Number(payload.exp) <= now) {
    return { ok: false, status: 403, code: 'expired_invite_token' };
  }
  return { ok: true, payload };
}

async function lookupInviteRow(env, inviteId, tokenHash) {
  if (!env.PREVIEW_DB || typeof env.PREVIEW_DB.prepare !== 'function') {
    return { ok: false, status: 503, code: 'd1_required' };
  }
  const row = await env.PREVIEW_DB
    .prepare(
      `SELECT invite_id, token_sha256, source_app, app_slug, single_use, email, role, expires_at, used_at, revoked_at
       FROM preview_invites
       WHERE invite_id = ?1 AND token_sha256 = ?2 AND source_app = ?3 AND app_slug = ?4
       LIMIT 1`,
    )
    .bind(inviteId, tokenHash, SOURCE_APP, SOURCE_APP)
    .first();
  if (!row) {
    return { ok: false, status: 403, code: 'invite_not_found' };
  }
  return { ok: true, row };
}

function validateInviteRow(row, { allowUsed }) {
  if (row.revoked_at) {
    return { ok: false, status: 403, code: 'revoked_invite_token' };
  }
  if (Date.parse(row.expires_at) <= Date.now()) {
    return { ok: false, status: 403, code: 'expired_invite_token' };
  }
  if (!allowUsed && Number(row.single_use) === 1 && row.used_at) {
    return { ok: false, status: 403, code: 'used_invite_token' };
  }
  return { ok: true };
}

async function markInviteUsed(env, row) {
  if (Number(row.single_use) !== 1) {
    return { ok: true };
  }
  const usedAt = new Date().toISOString();
  const result = await env.PREVIEW_DB
    .prepare(
      `UPDATE preview_invites
       SET used_at = COALESCE(used_at, ?1)
       WHERE invite_id = ?2
         AND token_sha256 = ?3
         AND used_at IS NULL
         AND revoked_at IS NULL`,
    )
    .bind(usedAt, row.invite_id, row.token_sha256)
    .run();
  const changes = Number(result?.meta?.changes || result?.changes || 0);
  if (changes < 1) {
    return { ok: false, status: 403, code: 'used_invite_token' };
  }
  return { ok: true, used_at: usedAt };
}

async function createAccessSession(env, invitePayload, tokenHash) {
  return signStructuredToken(env, {
    aud: 'codex.web-preview-session',
    scope: 'web_preview:session',
    source_app: SOURCE_APP,
    app_slug: SOURCE_APP,
    invite_id: invitePayload.invite_id,
    token_sha256: tokenHash,
    exp: invitePayload.exp,
    iat: Math.floor(Date.now() / 1000),
  });
}

async function verifyAccessSession(env, token) {
  const payload = await verifyStructuredToken(env, token);
  if (!payload) {
    return { ok: false, status: 403, code: 'invalid_access_session' };
  }
  if (payload.aud !== 'codex.web-preview-session' || payload.scope !== 'web_preview:session') {
    return { ok: false, status: 403, code: 'invalid_access_session' };
  }
  if (payload.source_app !== SOURCE_APP || payload.app_slug !== SOURCE_APP) {
    return { ok: false, status: 403, code: 'invalid_access_session' };
  }
  if (!payload.exp || Number(payload.exp) <= Math.floor(Date.now() / 1000)) {
    return { ok: false, status: 403, code: 'expired_access_session' };
  }
  const lookup = await lookupInviteRow(env, payload.invite_id, payload.token_sha256);
  if (!lookup.ok) {
    return lookup;
  }
  const active = validateInviteRow(lookup.row, { allowUsed: true });
  if (!active.ok) {
    return active;
  }
  return { ok: true, payload };
}

function apiError(code, message, status = 400) {
  return json({ error: { code, message } }, { status });
}

async function recordAuditEvent(env, eventType, actor, details = {}) {
  if (!env.PREVIEW_DB || typeof env.PREVIEW_DB.prepare !== 'function') {
    return;
  }
  const createdAt = nowIso();
  const material = `${SOURCE_APP}:${eventType}:${actor}:${createdAt}:${JSON.stringify(details)}`;
  const eventId = `wpa-${(await sha256Hex(material)).slice(0, 16)}`;
  try {
    await env.PREVIEW_DB
      .prepare(
        `INSERT INTO preview_audit_events
         (event_id, source_app, app_slug, event_type, actor, details_json, created_at)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)`,
      )
      .bind(eventId, SOURCE_APP, SOURCE_APP, eventType, actor, JSON.stringify(details), createdAt)
      .run();
  } catch (error) {
    console.warn('preview audit event skipped', eventType, error?.message || error);
  }
}

async function countPreviewUsers(env) {
  const row = await env.PREVIEW_DB
    .prepare(
      `SELECT COUNT(*) AS count
       FROM preview_users
       WHERE source_app = ?1 AND app_slug = ?2`,
    )
    .bind(SOURCE_APP, SOURCE_APP)
    .first();
  return Number(row?.count || 0);
}

async function createPreviewUser(env, { email, password, displayName, roles }) {
  const timestamp = nowIso();
  const user = {
    user_id: randomId('usr'),
    source_app: SOURCE_APP,
    app_slug: SOURCE_APP,
    email: String(email || '').trim().toLowerCase(),
    display_name: String(displayName || email || 'Preview Admin').trim(),
    password_hash: await passwordHash(env, password),
    roles_json: JSON.stringify(roles || ['owner', 'admin']),
    created_at: timestamp,
    updated_at: timestamp,
  };
  await env.PREVIEW_DB
    .prepare(
      `INSERT INTO preview_users
       (user_id, source_app, app_slug, email, display_name, password_hash, roles_json, created_at, updated_at)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)`,
    )
    .bind(
      user.user_id,
      user.source_app,
      user.app_slug,
      user.email,
      user.display_name,
      user.password_hash,
      user.roles_json,
      user.created_at,
      user.updated_at,
    )
    .run();
  return user;
}

async function findPreviewUserByEmail(env, email) {
  return env.PREVIEW_DB
    .prepare(
      `SELECT user_id, source_app, app_slug, email, display_name, password_hash, roles_json
       FROM preview_users
       WHERE source_app = ?1 AND app_slug = ?2 AND email = ?3
       LIMIT 1`,
    )
    .bind(SOURCE_APP, SOURCE_APP, String(email || '').trim().toLowerCase())
    .first();
}

function publicUser(row) {
  return {
    id: row.user_id,
    email: row.email,
    displayName: row.display_name,
    roles: JSON.parse(row.roles_json || '[]'),
    sourceApp: row.source_app,
    appSlug: row.app_slug,
  };
}

async function createPreviewSession(env, user) {
  const token = base64UrlEncode(crypto.getRandomValues(new Uint8Array(32)));
  const tokenHash = await sha256Hex(token);
  const sessionId = randomId('ses');
  const createdAt = nowIso();
  const expiresAt = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();
  await env.PREVIEW_DB
    .prepare(
      `INSERT INTO preview_sessions
       (session_id, source_app, app_slug, user_id, token_sha256, created_at, expires_at, revoked_at)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, NULL)`,
    )
    .bind(sessionId, SOURCE_APP, SOURCE_APP, user.user_id, tokenHash, createdAt, expiresAt)
    .run();
  return { token, expiresAt };
}

async function requireApiSession(env, request) {
  const auth = request.headers.get('authorization') || '';
  if (!auth.toLowerCase().startsWith('bearer ')) {
    return { ok: false, response: apiError('missing_bearer_token', 'Authorization bearer token is required.', 401) };
  }
  const tokenHash = await sha256Hex(auth.slice(7).trim());
  const session = await env.PREVIEW_DB
    .prepare(
      `SELECT session_id, source_app, app_slug, user_id, expires_at, revoked_at
       FROM preview_sessions
       WHERE source_app = ?1 AND app_slug = ?2 AND token_sha256 = ?3
       LIMIT 1`,
    )
    .bind(SOURCE_APP, SOURCE_APP, tokenHash)
    .first();
  if (!session || session.revoked_at || Date.parse(session.expires_at) <= Date.now()) {
    return { ok: false, response: apiError('invalid_session', 'Preview session is missing or expired.', 401) };
  }
  const user = await env.PREVIEW_DB
    .prepare(
      `SELECT user_id, source_app, app_slug, email, display_name, roles_json
       FROM preview_users
       WHERE source_app = ?1 AND app_slug = ?2 AND user_id = ?3
       LIMIT 1`,
    )
    .bind(SOURCE_APP, SOURCE_APP, session.user_id)
    .first();
  if (!user) {
    return { ok: false, response: apiError('invalid_session_user', 'Preview session user was not found.', 401) };
  }
  return { ok: true, user, session };
}

async function handlePreviewHealth(env) {
  return json({
    status: 'ok',
    source_app: SOURCE_APP,
    app_slug: SOURCE_APP,
    display_name: DISPLAY_NAME,
    runtime_profile: env.APP_RUNTIME_PROFILE || DEFAULT_RUNTIME_PROFILE,
    runtime: API_RUNTIME,
    api_base_url: previewApiBaseUrl(env),
    d1_bound: Boolean(env.PREVIEW_DB),
    d1_persistent: Boolean(env.PREVIEW_DB),
    assets_bound: Boolean(env.ASSETS),
    version: env.PREVIEW_VERSION || null,
    commit: env.PREVIEW_COMMIT_SHA || null,
    deployed_at: env.PREVIEW_DEPLOYED_AT || null,
  });
}

async function handlePreviewBootstrap(request, env) {
  const d1 = requirePreviewD1(env);
  if (!d1.ok) return d1.response;
  const body = await readJson(request);
  const expectedToken = env.PREVIEW_ADMIN_BOOTSTRAP_TOKEN || '';
  if (expectedToken && body.bootstrapToken !== expectedToken) {
    return apiError('invalid_bootstrap_token', 'Bootstrap token is invalid.', 403);
  }
  if (!expectedToken && env.PREVIEW_ALLOW_INSECURE_BOOTSTRAP !== 'true') {
    return apiError('bootstrap_token_required', 'PREVIEW_ADMIN_BOOTSTRAP_TOKEN is required for deployed bootstrap.', 403);
  }
  const email = String(body.email || env.PREVIEW_ADMIN_EMAIL || '').trim().toLowerCase();
  const password = String(body.password || env.PREVIEW_ADMIN_PASSWORD || '');
  if (!email || !password) {
    return apiError('admin_credentials_required', 'Admin email and password are required.', 400);
  }
  let user = await findPreviewUserByEmail(env, email);
  if (!user) {
    const userCount = await countPreviewUsers(env);
    const roles = userCount === 0 ? ['owner', 'admin'] : ['admin'];
    user = await createPreviewUser(env, {
      email,
      password,
      displayName: body.displayName || 'Preview Admin',
      roles,
    });
    await recordAuditEvent(env, 'admin_bootstrap_user_created', email, {
      userId: user.user_id,
      roles,
    });
  }
  const session = await createPreviewSession(env, user);
  await recordAuditEvent(env, 'admin_bootstrap_login', email, {
    userId: user.user_id,
  });
  return json({
    status: 'ready',
    sourceApp: SOURCE_APP,
    appSlug: SOURCE_APP,
    user: publicUser(user),
    accessToken: session.token,
    tokenType: 'bearer',
    expiresAt: session.expiresAt,
  });
}

async function handlePreviewLogin(request, env) {
  const d1 = requirePreviewD1(env);
  if (!d1.ok) return d1.response;
  const body = await readJson(request);
  const user = await findPreviewUserByEmail(env, body.email);
  if (!user || user.password_hash !== await passwordHash(env, String(body.password || ''))) {
    await recordAuditEvent(env, 'login_failed', String(body.email || '').trim().toLowerCase(), {
      reason: 'invalid_credentials',
    });
    return apiError('invalid_credentials', 'Email or password is invalid.', 401);
  }
  const session = await createPreviewSession(env, user);
  await recordAuditEvent(env, 'login_succeeded', user.email, {
    userId: user.user_id,
    sessionExpiresAt: session.expiresAt,
  });
  return json({
    access_token: session.token,
    token_type: 'bearer',
    expires_at: session.expiresAt,
    user: publicUser(user),
  });
}

async function handlePreviewInviteAccept(request, env) {
  const d1 = requirePreviewD1(env);
  if (!d1.ok) return d1.response;
  const body = await readJson(request);
  const inviteToken = String(body.inviteToken || body.invite_token || '').trim();
  const email = String(body.email || '').trim().toLowerCase();
  const password = String(body.password || '');
  const passwordConfirmation = String(body.passwordConfirmation || body.password_confirmation || '');
  if (!inviteToken || !email || !password || !passwordConfirmation) {
    return apiError('invite_accept_required', 'Invite token, email, password, and password confirmation are required.', 400);
  }
  if (password !== passwordConfirmation) {
    return apiError('password_confirmation_mismatch', 'Password confirmation must match.', 400);
  }
  const verified = await verifyInviteToken(env, inviteToken);
  if (!verified.ok) {
    return apiError(verified.code, 'Preview invite token is invalid.', verified.status);
  }
  const tokenHash = await sha256Hex(inviteToken);
  const lookup = await lookupInviteRow(env, verified.payload.invite_id, tokenHash);
  if (!lookup.ok) {
    return apiError(lookup.code, 'Preview invite row was not found.', lookup.status);
  }
  const active = validateInviteRow(lookup.row, { allowUsed: false });
  if (!active.ok) {
    return apiError(active.code, 'Preview invite token cannot be accepted.', active.status);
  }
  if (lookup.row.email && String(lookup.row.email).toLowerCase() !== email) {
    return apiError('invite_email_mismatch', 'This invite is bound to a different email address.', 403);
  }
  let user = await findPreviewUserByEmail(env, email);
  if (!user) {
    const userCount = await countPreviewUsers(env);
    const roles = userCount === 0 ? ['owner', 'admin'] : ['admin'];
    user = await createPreviewUser(env, {
      email,
      password,
      displayName: body.displayName || email,
      roles,
    });
  }
  const marked = await markInviteUsed(env, lookup.row);
  if (!marked.ok) {
    return apiError(marked.code, 'Preview invite token cannot be accepted.', marked.status);
  }
  const session = await createPreviewSession(env, user);
  await recordAuditEvent(env, 'invite_password_setup', email, {
    inviteId: verified.payload.invite_id,
    userId: user.user_id,
    sessionExpiresAt: session.expiresAt,
  });
  return json({
    access_token: session.token,
    token_type: 'bearer',
    expires_at: session.expiresAt,
    user: publicUser(user),
  });
}

async function handlePreviewMe(request, env) {
  const d1 = requirePreviewD1(env);
  if (!d1.ok) return d1.response;
  const session = await requireApiSession(env, request);
  if (!session.ok) return session.response;
  return json(publicUser(session.user));
}

async function handlePreviewLogout(request, env) {
  const d1 = requirePreviewD1(env);
  if (!d1.ok) return d1.response;
  const auth = request.headers.get('authorization') || '';
  if (!auth.toLowerCase().startsWith('bearer ')) {
    return json({ ok: true });
  }
  const tokenHash = await sha256Hex(auth.slice(7).trim());
  await env.PREVIEW_DB
    .prepare(
      `UPDATE preview_sessions
       SET revoked_at = ?1
       WHERE source_app = ?2 AND app_slug = ?3 AND token_sha256 = ?4 AND revoked_at IS NULL`,
    )
    .bind(nowIso(), SOURCE_APP, SOURCE_APP, tokenHash)
    .run();
  await recordAuditEvent(env, 'logout', 'api_user', {});
  return json({ ok: true });
}

async function handlePreviewAdmin(request, env, assetPath) {
  const d1 = requirePreviewD1(env);
  if (!d1.ok) return d1.response;
  const session = await requireApiSession(env, request);
  if (!session.ok) return session.response;
  const roles = JSON.parse(session.user.roles_json || '[]');
  if (!roles.includes('owner') && !roles.includes('admin')) {
    return apiError('admin_role_required', 'Admin role is required.', 403);
  }
  if (request.method === 'GET' && assetPath === '/api/admin/roles') {
    return json(['owner', 'admin', 'member', 'customer']);
  }
  if (request.method === 'GET' && assetPath === '/api/admin/users') {
    const rows = await env.PREVIEW_DB
      .prepare(
        `SELECT user_id, source_app, app_slug, email, display_name, roles_json
         FROM preview_users
         WHERE source_app = ?1 AND app_slug = ?2
         ORDER BY created_at ASC`,
      )
      .bind(SOURCE_APP, SOURCE_APP)
      .all();
    return json((rows.results || []).map(publicUser));
  }
  if (assetPath === '/api/admin/business-records') {
    if (request.method === 'GET') {
      const rows = await env.PREVIEW_DB
        .prepare(
          `SELECT record_id, payload_json, created_at, updated_at
           FROM preview_business_records
           WHERE source_app = ?1 AND app_slug = ?2
           ORDER BY created_at DESC`,
        )
        .bind(SOURCE_APP, SOURCE_APP)
        .all();
      return json((rows.results || []).map((row) => {
        const payload = JSON.parse(row.payload_json || '{}');
        return {
          id: row.record_id,
          name: payload.name || 'business record',
          is_active: payload.is_active !== false,
          created_at: row.created_at,
          updated_at: row.updated_at,
        };
      }));
    }
    if (request.method === 'POST') {
      const payload = await readJson(request);
      const timestamp = nowIso();
      const recordId = randomId('biz');
      await env.PREVIEW_DB
        .prepare(
          `INSERT INTO preview_business_records
           (record_id, source_app, app_slug, payload_json, created_at, updated_at)
           VALUES (?1, ?2, ?3, ?4, ?5, ?6)`,
        )
        .bind(
          recordId,
          SOURCE_APP,
          SOURCE_APP,
          JSON.stringify({
            name: String(payload.name || '').trim(),
            is_active: payload.is_active !== false,
          }),
          timestamp,
          timestamp,
        )
        .run();
      return json({
        id: recordId,
        name: String(payload.name || '').trim(),
        is_active: payload.is_active !== false,
        created_at: timestamp,
        updated_at: timestamp,
      });
    }
  }
  return apiError('preview_admin_route_not_found', `Preview admin route not found: ${assetPath}`, 404);
}

async function handlePreviewAppUpdate(env) {
  const d1 = requirePreviewD1(env);
  if (!d1.ok) return d1.response;
  const row = await env.PREVIEW_DB
    .prepare(
      `SELECT release_channel, release_tag, version, build_number, apk_url, sha256, metadata_json
       FROM preview_app_updates
       WHERE source_app = ?1 AND app_slug = ?2 AND release_channel = 'prerelease'
       LIMIT 1`,
    )
    .bind(SOURCE_APP, SOURCE_APP)
    .first();
  return json({
    sourceApp: SOURCE_APP,
    appSlug: SOURCE_APP,
    releaseChannel: 'prerelease',
    runtimeProfile: env.APP_RUNTIME_PROFILE || DEFAULT_RUNTIME_PROFILE,
    apiRuntime: API_RUNTIME,
    apiBaseUrl: previewApiBaseUrl(env),
    releaseTag: row?.release_tag || env.APP_RELEASE_TAG || null,
    version: row?.version || env.PREVIEW_VERSION || '0.1.0',
    buildNumber: row?.build_number || env.PREVIEW_BUILD_ID || '1',
    apkUrl: row?.apk_url || env.PREVIEW_APK_URL || null,
    sha256: row?.sha256 || null,
    mockOrDemo: false,
    backendRequired: true,
    metadata: row?.metadata_json ? JSON.parse(row.metadata_json) : {},
  });
}

async function handlePreviewBusinessRecords(request, env) {
  const d1 = requirePreviewD1(env);
  if (!d1.ok) return d1.response;
  const session = await requireApiSession(env, request);
  if (!session.ok) return session.response;
  if (request.method === 'GET') {
    const rows = await env.PREVIEW_DB
      .prepare(
        `SELECT record_id, source_app, app_slug, payload_json, created_at, updated_at
         FROM preview_business_records
         WHERE source_app = ?1 AND app_slug = ?2
         ORDER BY created_at DESC`,
      )
      .bind(SOURCE_APP, SOURCE_APP)
      .all();
    return json({
      sourceApp: SOURCE_APP,
      appSlug: SOURCE_APP,
      records: (rows.results || []).map((row) => ({
        id: row.record_id,
        sourceApp: row.source_app,
        appSlug: row.app_slug,
        payload: JSON.parse(row.payload_json || '{}'),
        createdAt: row.created_at,
        updatedAt: row.updated_at,
      })),
    });
  }
  if (request.method === 'POST') {
    const payload = await readJson(request);
    const timestamp = nowIso();
    const recordId = randomId('rec');
    await env.PREVIEW_DB
      .prepare(
        `INSERT INTO preview_business_records
         (record_id, source_app, app_slug, payload_json, created_at, updated_at)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6)`,
      )
      .bind(recordId, SOURCE_APP, SOURCE_APP, JSON.stringify(payload), timestamp, timestamp)
      .run();
    return json({
      id: recordId,
      sourceApp: SOURCE_APP,
      appSlug: SOURCE_APP,
      payload,
      createdAt: timestamp,
      updatedAt: timestamp,
    }, { status: 201 });
  }
  return apiError('method_not_allowed', 'Method not allowed.', 405);
}

async function handlePreviewNotifications(request, env) {
  const d1 = requirePreviewD1(env);
  if (!d1.ok) return d1.response;
  const session = await requireApiSession(env, request);
  if (!session.ok) return session.response;
  const rows = await env.PREVIEW_DB
    .prepare(
      `SELECT notification_id, source_app, app_slug, user_id, title, body, read_at, created_at
       FROM preview_notifications
       WHERE source_app = ?1 AND app_slug = ?2 AND (user_id IS NULL OR user_id = ?3)
       ORDER BY created_at DESC`,
    )
    .bind(SOURCE_APP, SOURCE_APP, session.user.user_id)
    .all();
  return json({
    sourceApp: SOURCE_APP,
    appSlug: SOURCE_APP,
    notifications: (rows.results || []).map((row) => ({
      id: row.notification_id,
      title: row.title,
      body: row.body,
      readAt: row.read_at,
      createdAt: row.created_at,
    })),
  });
}

async function handlePreviewApi(request, env, assetPath) {
  if (request.method === 'GET' && assetPath === '/api/health') {
    return handlePreviewHealth(env);
  }
  if (request.method === 'POST' && assetPath === '/api/admin/bootstrap') {
    return handlePreviewBootstrap(request, env);
  }
  if (request.method === 'POST' && assetPath === '/api/auth/login') {
    return handlePreviewLogin(request, env);
  }
  if (request.method === 'POST' && assetPath === '/api/invites/accept') {
    return handlePreviewInviteAccept(request, env);
  }
  if (request.method === 'GET' && assetPath === '/api/auth/me') {
    return handlePreviewMe(request, env);
  }
  if (request.method === 'POST' && assetPath === '/api/auth/logout') {
    return handlePreviewLogout(request, env);
  }
  if (assetPath === '/api/admin/users' || assetPath === '/api/admin/roles' || assetPath === '/api/admin/business-records') {
    return handlePreviewAdmin(request, env, assetPath);
  }
  if (assetPath === '/api/business/records') {
    return handlePreviewBusinessRecords(request, env);
  }
  if (request.method === 'GET' && assetPath === '/api/app-updates/current') {
    return handlePreviewAppUpdate(env);
  }
  if (request.method === 'GET' && assetPath === '/api/notifications') {
    return handlePreviewNotifications(request, env);
  }
  return apiError('preview_api_route_not_found', `Preview API route not found: ${assetPath}`, 404);
}

function accessDenied(code, status) {
  return json({
    error: {
      code,
      message: code === 'missing_invite_token'
        ? 'A valid preview invite token is required.'
        : 'Preview access is not allowed for this invite.',
    },
  }, { status });
}

async function requireAccess(env, request, url) {
  if (ACCESS_MODE === 'public') {
    return { ok: true };
  }
  const token = sessionTokenFromRequest(request);
  if (!token) {
    return { ok: false, response: accessDenied('missing_invite_token', 401) };
  }
  const verified = await verifyAccessSession(env, token);
  if (!verified.ok) {
    return { ok: false, response: accessDenied(verified.code, verified.status) };
  }
  return { ok: true, payload: verified.payload };
}

function redirectWithCookie(url, sessionToken, payload) {
  const next = url.searchParams.get('next');
  const safeNext = next && next.startsWith('/') && !next.startsWith('//')
    ? next
    : `/${SOURCE_APP}/`;
  const maxAge = Math.max(1, Number(payload.exp || 0) - Math.floor(Date.now() / 1000));
  return new Response(null, {
    status: 302,
    headers: {
      location: safeNext,
      'set-cookie': `${ACCESS_COOKIE_NAME}=${encodeURIComponent(sessionToken)}; Max-Age=${maxAge}; Path=/; HttpOnly; Secure; SameSite=Lax`,
      ...securityHeaders(),
    },
  });
}

function redirectWithPreviewAccess(url, sessionToken, payload, row, inviteToken) {
  const target = new URL(url.toString());
  target.pathname = `/${SOURCE_APP}/`;
  target.search = '';
  if (row.used_at) {
    target.searchParams.set('invite_state', 'login');
  } else {
    target.searchParams.set('invite_state', 'activate');
    target.searchParams.set('invite_token', inviteToken);
    if (row.email) {
      target.searchParams.set('email', row.email);
      target.searchParams.set('email_bound', 'true');
    }
  }
  url.searchParams.set('next', `${target.pathname}${target.search}`);
  return redirectWithCookie(url, sessionToken, payload);
}

function isStaticAssetPath(pathname) {
  const lastSegment = pathname.split('/').pop() || '';
  if (pathname.startsWith('/assets/') || pathname.startsWith('/canvaskit/') || pathname.startsWith('/icons/')) {
    return true;
  }
  const dot = lastSegment.lastIndexOf('.');
  if (dot === -1) {
    return false;
  }
  return STATIC_ASSET_EXTENSIONS.has(lastSegment.slice(dot).toLowerCase());
}

function isPublicSafeAssetPath(pathname) {
  return pathname === '/manifest.json' ||
    pathname === '/favicon.png' ||
    pathname === '/favicon.ico' ||
    pathname.startsWith('/icons/');
}

async function fetchAsset(env, request, pathname) {
  if (!env.ASSETS || typeof env.ASSETS.fetch !== 'function') {
    return null;
  }
  const assetUrl = new URL(request.url);
  assetUrl.pathname = pathname === '/index.html' ? '/' : pathname;
  assetUrl.search = '';
  return env.ASSETS.fetch(new Request(assetUrl.toString(), request));
}

async function assetResponse(env, request, pathname) {
  const response = await fetchAsset(env, request, pathname);
  if (!response || response.status === 404) {
    return null;
  }
  const headers = new Headers(response.headers);
  if (!headers.has('content-type')) {
    headers.set('content-type', contentTypeFor(pathname));
  }
  headers.set('cache-control', cacheControlFor(pathname));
  for (const [key, value] of Object.entries(securityHeaders())) {
    headers.set(key, value);
  }
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

async function serveSpa(env, request) {
  const response = await assetResponse(env, request, '/index.html');
  if (response) {
    return response;
  }
  return json({
    error: {
      code: 'preview_assets_unavailable',
      message: 'Preview assets binding is missing or index.html was not found.',
    },
  }, { status: 503 });
}

async function handleRequest(request, env = globalThis, ctx = undefined) {
  const url = new URL(request.url);
  const appSlug = appSlugFromPath(url.pathname);
  const assetPath = stripAppPrefix(url.pathname);

    if (request.method === 'GET' && (assetPath === '/__preview/health' || url.pathname === '/__preview/health')) {
    return json({
      status: 'ok',
      source_app: SOURCE_APP,
      app_slug: appSlug || SOURCE_APP,
      display_name: DISPLAY_NAME,
      runtime_profile: env.APP_RUNTIME_PROFILE || DEFAULT_RUNTIME_PROFILE,
      runtime: API_RUNTIME,
      runtime_type: 'cloudflare_worker_assets',
      api_base_url: previewApiBaseUrl(env),
      access_mode: ACCESS_MODE,
      build_id: env.PREVIEW_BUILD_ID || null,
      version: env.PREVIEW_VERSION || null,
      commit: env.PREVIEW_COMMIT_SHA || null,
      deployed_at: env.PREVIEW_DEPLOYED_AT || null,
      d1_bound: Boolean(env.PREVIEW_DB),
      assets_bound: Boolean(env.ASSETS),
    });
  }

    if (assetPath === '/api' || assetPath.startsWith('/api/')) {
    return handlePreviewApi(request, env, assetPath);
  }

    const configMatch = assetPath.match(/^\\/apps\\/([^/]+)\\/config\\/?$/);
    if (request.method === 'GET' && configMatch) {
    return json({
      app_slug: configMatch[1],
      source_app: SOURCE_APP,
      display_name: DISPLAY_NAME,
      runtime_profile: env.APP_RUNTIME_PROFILE || DEFAULT_RUNTIME_PROFILE,
      api_runtime: API_RUNTIME,
      api_base_url: previewApiBaseUrl(env),
      health_path: '/api/health',
      access_mode: ACCESS_MODE,
    });
  }

    if (request.method === 'GET' && assetPath === '/__preview/access') {
    const token = url.searchParams.get('token');
    if (!token) {
      return accessDenied('missing_invite_token', 401);
    }
    const verified = await verifyInviteToken(env, token);
    if (!verified.ok) {
      return accessDenied(verified.code, verified.status);
    }
    const tokenHash = await sha256Hex(token);
    const lookup = await lookupInviteRow(env, verified.payload.invite_id, tokenHash);
    if (!lookup.ok) {
      return accessDenied(lookup.code, lookup.status);
    }
    const active = validateInviteRow(lookup.row, { allowUsed: true });
    if (!active.ok) {
      await recordAuditEvent(env, 'invite_access_denied', verified.payload.invite_id, {
        reason: active.code,
      });
      return accessDenied(active.code, active.status);
    }
    const sessionToken = await createAccessSession(env, verified.payload, tokenHash);
    await recordAuditEvent(env, 'invite_access_granted', verified.payload.invite_id, {
      usedAt: lookup.row.used_at || null,
      state: lookup.row.used_at ? 'invite_access_refresh' : 'invite_activation',
    });
    return redirectWithPreviewAccess(url, sessionToken, verified.payload, lookup.row, token);
  }

    if (request.method !== 'GET' && request.method !== 'HEAD') {
    return json({ error: { code: 'method_not_allowed', message: 'Method not allowed' } }, { status: 405 });
  }

    if (isPublicSafeAssetPath(assetPath)) {
    const response = await assetResponse(env, request, assetPath);
    if (response) {
      return response;
    }
    return json({
      error: {
        code: 'asset_not_found',
        message: `Static asset not found: ${assetPath}`,
      },
    }, { status: 404 });
  }

    const access = await requireAccess(env, request, url);
    if (!access.ok) {
    return access.response;
  }

    if (isStaticAssetPath(assetPath)) {
    const response = await assetResponse(env, request, assetPath);
    if (response) {
      return response;
    }
    return json({
      error: {
        code: 'asset_not_found',
        message: `Static asset not found: ${assetPath}`,
      },
    }, { status: 404 });
  }

  return serveSpa(env, request);
}

export default {
  async fetch(request, env, ctx) {
    return handleRequest(request, env, ctx);
  },
};
"""
    return template.replace("__SOURCE_APP__", slug).replace(
        "__DISPLAY_NAME__",
        repr(name),
    ).replace("{{", "{").replace("}}", "}")


def _web_preview_worker_harness_js(slug: str) -> str:
    template = """import assert from 'node:assert/strict';
import { createHash, createHmac, webcrypto } from 'node:crypto';
import {{ readFile }} from 'node:fs/promises';

if (!globalThis.crypto) {
  Object.defineProperty(globalThis, 'crypto', { value: webcrypto });
}

const workerSource = await readFile(new URL('./src/index.js', import.meta.url), 'utf8');
const workerModule = await import(
  `data:text/javascript;base64,${{Buffer.from(workerSource).toString('base64')}}`
);
const worker = workerModule.default;
assert.equal(typeof worker, 'object');
assert.equal(typeof worker.fetch, 'function');

function response(body, init = {{}}) {{
  return new Response(body, init);
}}

function base64UrlJson(payload) {
  return Buffer.from(JSON.stringify(payload)).toString('base64url');
}

function signToken(payload, secret) {
  const header = base64UrlJson({ alg: 'HS256', typ: 'JWT' });
  const body = base64UrlJson(payload);
  const signature = createHmac('sha256', secret)
    .update(`${header}.${body}`)
    .digest('base64url');
  return `${header}.${body}.${signature}`;
}

function sha256Hex(value) {
  return createHash('sha256').update(value).digest('hex');
}

const secret = 'local-preview-secret-value-32-bytes';
const now = Math.floor(Date.now() / 1000);
const validToken = signToken({
  aud: 'codex.web-preview',
  scope: 'web_preview:access',
  preview_id: 'wp-__SOURCE_APP__',
  source_app: '__SOURCE_APP__',
  app_slug: '__SOURCE_APP__',
  invite_id: 'wpi-local',
  iat: now,
  exp: now + 3600,
}, secret);
const setupToken = signToken({
  aud: 'codex.web-preview',
  scope: 'web_preview:access',
  preview_id: 'wp-__SOURCE_APP__',
  source_app: '__SOURCE_APP__',
  app_slug: '__SOURCE_APP__',
  invite_id: 'wpi-setup',
  iat: now,
  exp: now + 3600,
}, secret);
const expiredToken = signToken({
  aud: 'codex.web-preview',
  scope: 'web_preview:access',
  preview_id: 'wp-__SOURCE_APP__',
  source_app: '__SOURCE_APP__',
  app_slug: '__SOURCE_APP__',
  invite_id: 'wpi-expired',
  iat: now - 7200,
  exp: now - 3600,
}, secret);
const revokedToken = signToken({
  aud: 'codex.web-preview',
  scope: 'web_preview:access',
  preview_id: 'wp-__SOURCE_APP__',
  source_app: '__SOURCE_APP__',
  app_slug: '__SOURCE_APP__',
  invite_id: 'wpi-revoked',
  iat: now,
  exp: now + 3600,
}, secret);
const d1ExpiredToken = signToken({
  aud: 'codex.web-preview',
  scope: 'web_preview:access',
  preview_id: 'wp-__SOURCE_APP__',
  source_app: '__SOURCE_APP__',
  app_slug: '__SOURCE_APP__',
  invite_id: 'wpi-d1-expired',
  iat: now,
  exp: now + 3600,
}, secret);
const missingRowToken = signToken({
  aud: 'codex.web-preview',
  scope: 'web_preview:access',
  preview_id: 'wp-__SOURCE_APP__',
  source_app: '__SOURCE_APP__',
  app_slug: '__SOURCE_APP__',
  invite_id: 'wpi-missing',
  iat: now,
  exp: now + 3600,
}, secret);

function inviteRow(inviteId, token, extra = {}) {
  return {
    invite_id: inviteId,
    token_sha256: sha256Hex(token),
    source_app: '__SOURCE_APP__',
    app_slug: '__SOURCE_APP__',
    single_use: 1,
    expires_at: new Date(Date.now() + 3600000).toISOString(),
    used_at: null,
    revoked_at: null,
    ...extra,
  };
}

const d1Rows = new Map();
for (const row of [
  inviteRow('wpi-local', validToken),
  inviteRow('wpi-setup', setupToken),
  inviteRow('wpi-revoked', revokedToken, { revoked_at: new Date().toISOString() }),
  inviteRow('wpi-d1-expired', d1ExpiredToken, { expires_at: new Date(Date.now() - 1000).toISOString() }),
]) {
  d1Rows.set(`${row.invite_id}:${row.token_sha256}`, row);
}
const previewUsers = new Map();
const previewSessions = new Map();
const previewBusinessRecords = [];
const previewNotifications = [
  {
    notification_id: 'ntf-local',
    source_app: '__SOURCE_APP__',
    app_slug: '__SOURCE_APP__',
    user_id: null,
    title: 'Preview ready',
    body: 'Local smoke notification',
    read_at: null,
    created_at: new Date().toISOString(),
  },
];

function fakeD1() {
  return {
    prepare(sql) {
      const normalized = sql.replace(/\s+/g, ' ').trim().toLowerCase();
      return {
        bind(...args) {
          return {
            async first() {
              if (normalized.includes('from preview_invites')) {
                const [inviteId, tokenHash, sourceApp, appSlug] = args;
                const row = d1Rows.get(`${inviteId}:${tokenHash}`);
                if (!row || row.source_app !== sourceApp || row.app_slug !== appSlug) {
                  return null;
                }
                return { ...row };
              }
              if (normalized.includes('count(*) as count') && normalized.includes('from preview_users')) {
                const [sourceApp, appSlug] = args;
                return {
                  count: [...previewUsers.values()].filter((row) => row.source_app === sourceApp && row.app_slug === appSlug).length,
                };
              }
              if (normalized.includes('from preview_users') && normalized.includes('email =')) {
                const [sourceApp, appSlug, email] = args;
                return [...previewUsers.values()].find((row) => row.source_app === sourceApp && row.app_slug === appSlug && row.email === email) || null;
              }
              if (normalized.includes('from preview_sessions')) {
                const [sourceApp, appSlug, tokenHash] = args;
                return [...previewSessions.values()].find((row) => row.source_app === sourceApp && row.app_slug === appSlug && row.token_sha256 === tokenHash) || null;
              }
              if (normalized.includes('from preview_users') && normalized.includes('user_id =')) {
                const [sourceApp, appSlug, userId] = args;
                const row = previewUsers.get(userId);
                if (!row || row.source_app !== sourceApp || row.app_slug !== appSlug) {
                  return null;
                }
                return { ...row };
              }
              if (normalized.includes('from preview_app_updates')) {
                return null;
              }
              return null;
            },
            async run() {
              if (normalized.startsWith('update preview_invites')) {
                const [_usedAt, inviteId, tokenHash] = args;
                const row = d1Rows.get(`${inviteId}:${tokenHash}`);
                if (!row || row.used_at || row.revoked_at) {
                  return { meta: { changes: 0 } };
                }
                row.used_at = _usedAt;
                d1Rows.set(`${inviteId}:${tokenHash}`, row);
                return { meta: { changes: 1 } };
              }
              if (normalized.startsWith('update preview_sessions')) {
                const [revokedAt, sourceApp, appSlug, tokenHash] = args;
                for (const [sessionId, row] of previewSessions.entries()) {
                  if (row.source_app === sourceApp && row.app_slug === appSlug && row.token_sha256 === tokenHash && !row.revoked_at) {
                    previewSessions.set(sessionId, { ...row, revoked_at: revokedAt });
                    return { meta: { changes: 1 } };
                  }
                }
                return { meta: { changes: 0 } };
              }
              if (normalized.startsWith('insert into preview_users')) {
                const [userId, sourceApp, appSlug, email, displayName, passwordHash, rolesJson, createdAt, updatedAt] = args;
                previewUsers.set(userId, {
                  user_id: userId,
                  source_app: sourceApp,
                  app_slug: appSlug,
                  email,
                  display_name: displayName,
                  password_hash: passwordHash,
                  roles_json: rolesJson,
                  created_at: createdAt,
                  updated_at: updatedAt,
                });
                return { meta: { changes: 1 } };
              }
              if (normalized.startsWith('insert into preview_sessions')) {
                const [sessionId, sourceApp, appSlug, userId, tokenHash, createdAt, expiresAt] = args;
                previewSessions.set(sessionId, {
                  session_id: sessionId,
                  source_app: sourceApp,
                  app_slug: appSlug,
                  user_id: userId,
                  token_sha256: tokenHash,
                  created_at: createdAt,
                  expires_at: expiresAt,
                  revoked_at: null,
                });
                return { meta: { changes: 1 } };
              }
              if (normalized.startsWith('insert into preview_business_records')) {
                const [recordId, sourceApp, appSlug] = args;
                const payloadJson = args[3];
                const createdAt = args[4];
                const updatedAt = args[5];
                previewBusinessRecords.push({
                  record_id: recordId,
                  source_app: sourceApp,
                  app_slug: appSlug,
                  payload_json: payloadJson,
                  created_at: createdAt,
                  updated_at: updatedAt,
                });
                return { meta: { changes: 1 } };
              }
              return { meta: { changes: 0 } };
            },
            async all() {
              if (normalized.includes('from preview_users')) {
                const [sourceApp, appSlug] = args;
                return {
                  results: [...previewUsers.values()].filter((row) => row.source_app === sourceApp && row.app_slug === appSlug),
                };
              }
              if (normalized.includes('from preview_business_records')) {
                const [sourceApp, appSlug] = args;
                return {
                  results: previewBusinessRecords.filter((row) => row.source_app === sourceApp && row.app_slug === appSlug),
                };
              }
              if (normalized.includes('from preview_notifications')) {
                const [sourceApp, appSlug, userId] = args;
                return {
                  results: previewNotifications.filter((row) => row.source_app === sourceApp && row.app_slug === appSlug && (!row.user_id || row.user_id === userId)),
                };
              }
              return { results: [] };
            },
          };
        },
      };
    },
  };
}

const assets = new Map([
  ['/', response('<!doctype html><div id="flt"></div>', {{ headers: {{ 'content-type': 'text/html' }} }})],
  ['/index.html', response('<!doctype html><div id="flt"></div>', {{ headers: {{ 'content-type': 'text/html' }} }})],
  ['/flutter_bootstrap.js', response('console.log("bootstrap");', {{ headers: {{ 'content-type': 'application/javascript' }} }})],
  ['/assets/AssetManifest.bin', response('asset-manifest')],
]);

const env = {{
  APP_RUNTIME_PROFILE: 'preview',
  API_RUNTIME: 'cloudflare_preview',
  API_BASE_URL: 'https://preview.nienfos.com/__SOURCE_APP__/api',
  APP_SLUG: '__SOURCE_APP__',
  PREVIEW_ALLOW_INSECURE_BOOTSTRAP: 'true',
  PREVIEW_ADMIN_BOOTSTRAP_TOKEN: 'local-bootstrap-token',
  PREVIEW_BUILD_ID: 'local-harness',
  PREVIEW_COMMIT_SHA: 'test-commit',
  WEB_PREVIEW_INVITE_SECRET: secret,
  PREVIEW_DB: fakeD1(),
  ASSETS: {{
    async fetch(request) {{
      const url = new URL(request.url);
      if (url.pathname === '/index.html') {
        return response('', {{ status: 307, headers: {{ location: `/${{url.search}}` }} }});
      }
      return assets.get(url.pathname) || response('missing', {{ status: 404 }});
    }},
  }},
}};

async function fetchPath(path) {{
  return worker.fetch(new Request(`https://preview.nienfos.com${{path}}`), env, {{}});
}}

async function fetchJson(path, options = {}) {{
  const headers = new Headers(options.headers || {});
  if (options.body && !headers.has('content-type')) {
    headers.set('content-type', 'application/json');
  }
  return worker.fetch(
    new Request(`https://preview.nienfos.com${{path}}`, {
      method: options.method || 'GET',
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
    }),
    env,
    {{}},
  );
}}

const health = await fetchPath('/__SOURCE_APP__/__preview/health');
assert.equal(health.status, 200);
assert.equal((await health.json()).source_app, '__SOURCE_APP__');

const apiHealth = await fetchJson('/__SOURCE_APP__/api/health');
assert.equal(apiHealth.status, 200);
const apiHealthBody = await apiHealth.json();
assert.equal(apiHealthBody.runtime, 'cloudflare_preview');
assert.equal(apiHealthBody.api_base_url, 'https://preview.nienfos.com/__SOURCE_APP__/api');
assert.equal(apiHealthBody.d1_bound, true);

const bootstrap = await fetchJson('/__SOURCE_APP__/api/admin/bootstrap', {
  method: 'POST',
  body: {
    bootstrapToken: 'local-bootstrap-token',
    email: 'admin@example.com',
    password: 'preview-password',
  },
});
assert.equal(bootstrap.status, 200);
const bootstrapBody = await bootstrap.json();
assert.equal(bootstrapBody.user.sourceApp, '__SOURCE_APP__');
assert.match(bootstrapBody.accessToken, /.+/);

const login = await fetchJson('/__SOURCE_APP__/api/auth/login', {
  method: 'POST',
  body: { email: 'admin@example.com', password: 'preview-password' },
});
assert.equal(login.status, 200);
const loginBody = await login.json();
assert.equal(loginBody.user.appSlug, '__SOURCE_APP__');
const apiAuth = { authorization: `Bearer ${loginBody.access_token}` };

const acceptedInvite = await fetchJson('/__SOURCE_APP__/api/invites/accept', {
  method: 'POST',
  body: {
    inviteToken: setupToken,
    email: 'invite-admin@example.com',
    password: 'invite-password',
    passwordConfirmation: 'invite-password',
  },
});
assert.equal(acceptedInvite.status, 200);
const acceptedInviteBody = await acceptedInvite.json();
assert.equal(acceptedInviteBody.user.appSlug, '__SOURCE_APP__');
assert.match(acceptedInviteBody.access_token, /.+/);

const duplicateInviteAccept = await fetchJson('/__SOURCE_APP__/api/invites/accept', {
  method: 'POST',
  body: {
    inviteToken: setupToken,
    email: 'invite-admin@example.com',
    password: 'invite-password',
    passwordConfirmation: 'invite-password',
  },
});
assert.equal(duplicateInviteAccept.status, 403);
assert.equal((await duplicateInviteAccept.json()).error.code, 'used_invite_token');

const usedInviteAccessRefresh = await fetchPath(`/__SOURCE_APP__/__preview/access?token=${setupToken}`);
assert.equal(usedInviteAccessRefresh.status, 302);
assert.match(usedInviteAccessRefresh.headers.get('location') || '', /invite_state=login/);

const me = await fetchJson('/__SOURCE_APP__/api/auth/me', { headers: apiAuth });
assert.equal(me.status, 200);
assert.equal((await me.json()).email, 'admin@example.com');

const roles = await fetchJson('/__SOURCE_APP__/api/admin/roles', { headers: apiAuth });
assert.equal(roles.status, 200);
assert.ok((await roles.json()).includes('owner'));

const users = await fetchJson('/__SOURCE_APP__/api/admin/users', { headers: apiAuth });
assert.equal(users.status, 200);
assert.equal((await users.json()).length, 2);

const createdRecord = await fetchJson('/__SOURCE_APP__/api/business/records', {
  method: 'POST',
  headers: apiAuth,
  body: { name: 'Ada Lovelace', status: 'lead' },
});
assert.equal(createdRecord.status, 201);
assert.equal((await createdRecord.json()).sourceApp, '__SOURCE_APP__');

const records = await fetchJson('/__SOURCE_APP__/api/business/records', { headers: apiAuth });
assert.equal(records.status, 200);
const recordsBody = await records.json();
assert.equal(recordsBody.sourceApp, '__SOURCE_APP__');
assert.equal(recordsBody.records.length, 1);
assert.equal(recordsBody.records[0].payload.name, 'Ada Lovelace');

const adminBusinessRecord = await fetchJson('/__SOURCE_APP__/api/admin/business-records', {
  method: 'POST',
  headers: apiAuth,
  body: { name: 'Primary workspace' },
});
assert.equal(adminBusinessRecord.status, 200);
assert.equal((await adminBusinessRecord.json()).name, 'Primary workspace');

const adminBusinessRecords = await fetchJson('/__SOURCE_APP__/api/admin/business-records', { headers: apiAuth });
assert.equal(adminBusinessRecords.status, 200);
const adminBusinessRecordsBody = await adminBusinessRecords.json();
assert.equal(adminBusinessRecordsBody.length, 2);
assert.ok(adminBusinessRecordsBody.some((row) => row.name === 'Primary workspace'));
assert.ok(adminBusinessRecordsBody.some((row) => row.name === 'Ada Lovelace'));

const notifications = await fetchJson('/__SOURCE_APP__/api/notifications', { headers: apiAuth });
assert.equal(notifications.status, 200);
assert.equal((await notifications.json()).notifications.length, 1);

const updates = await fetchJson('/__SOURCE_APP__/api/app-updates/current');
assert.equal(updates.status, 200);
const updatesBody = await updates.json();
assert.equal(updatesBody.releaseChannel, 'prerelease');
assert.equal(updatesBody.mockOrDemo, false);

const blocked = await fetchPath('/__SOURCE_APP__/dashboard/orders');
assert.equal(blocked.status, 401);
assert.equal((await blocked.json()).error.code, 'missing_invite_token');

const access = await fetchPath(`/__SOURCE_APP__/__preview/access?token=${validToken}`);
assert.equal(access.status, 302);
const cookie = access.headers.get('set-cookie') || '';
assert.match(cookie, /codex_preview_access=/);
assert.match(access.headers.get('location') || '', /invite_state=activate/);

const activationLanding = await worker.fetch(
  new Request(`https://preview.nienfos.com${access.headers.get('location') || '/__SOURCE_APP__/'}`, {
    headers: { cookie },
  }),
  env,
  {},
);
assert.equal(activationLanding.status, 200);
assert.equal(activationLanding.headers.get('location'), null);

const secondUse = await fetchPath(`/__SOURCE_APP__/__preview/access?token=${validToken}`);
assert.equal(secondUse.status, 302);

const expired = await fetchPath(`/__SOURCE_APP__/__preview/access?token=${expiredToken}`);
assert.equal(expired.status, 403);
assert.equal((await expired.json()).error.code, 'expired_invite_token');

const revoked = await fetchPath(`/__SOURCE_APP__/__preview/access?token=${revokedToken}`);
assert.equal(revoked.status, 403);
assert.equal((await revoked.json()).error.code, 'revoked_invite_token');

const d1Expired = await fetchPath(`/__SOURCE_APP__/__preview/access?token=${d1ExpiredToken}`);
assert.equal(d1Expired.status, 403);
assert.equal((await d1Expired.json()).error.code, 'expired_invite_token');

const missingRow = await fetchPath(`/__SOURCE_APP__/__preview/access?token=${missingRowToken}`);
assert.equal(missingRow.status, 403);
assert.equal((await missingRow.json()).error.code, 'invite_not_found');

const asset = await worker.fetch(
  new Request('https://preview.nienfos.com/__SOURCE_APP__/flutter_bootstrap.js', {
    headers: { cookie },
  }),
  env,
  {},
);
assert.equal(asset.status, 200);
assert.match(asset.headers.get('content-type') || '', /javascript/);

const spa = await worker.fetch(
  new Request('https://preview.nienfos.com/__SOURCE_APP__/dashboard/orders', {
    headers: { cookie },
  }),
  env,
  {},
);
assert.equal(spa.status, 200);
assert.match(spa.headers.get('cache-control') || '', /no-cache/);

const missingAsset = await worker.fetch(
  new Request('https://preview.nienfos.com/__SOURCE_APP__/assets/missing.png', {
    headers: { cookie },
  }),
  env,
  {},
);
assert.equal(missingAsset.status, 404);
assert.equal((await missingAsset.json()).error.code, 'asset_not_found');

console.log('worker local preview harness passed');
"""
    return template.replace("__SOURCE_APP__", slug).replace("{{", "{").replace("}}", "}")


def _build_web_preview_script(slug: str, frontend_strategy: str = "flutter") -> str:
    if frontend_strategy == "svelte":
        return f'''#!/usr/bin/env bash
set -euo pipefail

fail() {{
  printf 'web preview build failed: %s\\n' "$*" >&2
  exit 1
}}

ROOT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
WEB_DIR="$ROOT_DIR/apps/web"
APP_SLUG="${{APP_SLUG:-{slug}}}"
APP_RUNTIME_PROFILE="${{APP_RUNTIME_PROFILE:-preview}}"
API_RUNTIME="${{API_RUNTIME:-cloudflare_preview}}"
API_BASE_URL="${{API_BASE_URL:-https://preview.nienfos.com/{slug}/api}}"
WEB_PREVIEW_BUILD_DIR="${{WEB_PREVIEW_BUILD_DIR:-$ROOT_DIR/build/web-preview/$APP_SLUG}}"

case "$APP_RUNTIME_PROFILE" in
  real|staging|preview|mock) ;;
  *) fail "APP_RUNTIME_PROFILE must be real, staging, preview, or mock" ;;
esac
[[ "$APP_RUNTIME_PROFILE" != "mock" ]] || fail "Svelte Initial Preview Release cannot use mock runtime"
[[ "$API_RUNTIME" == "cloudflare_preview" ]] || fail "API_RUNTIME must be cloudflare_preview"
[[ "$API_BASE_URL" == "https://preview.nienfos.com/$APP_SLUG/api" ]] || fail "API_BASE_URL must be https://preview.nienfos.com/$APP_SLUG/api"
[[ -f "$WEB_DIR/package.json" ]] || fail "missing apps/web/package.json"

if ! command -v npm >/dev/null 2>&1; then
  fail "npm is required to build the Svelte web preview artifact"
fi

cd "$WEB_DIR"
npm ci
VITE_APP_RUNTIME_PROFILE="$APP_RUNTIME_PROFILE" \\
VITE_API_RUNTIME="$API_RUNTIME" \\
VITE_API_BASE_URL="$API_BASE_URL" \\
VITE_APP_SLUG="$APP_SLUG" \\
npm run build

rm -rf "$WEB_PREVIEW_BUILD_DIR"
mkdir -p "$(dirname "$WEB_PREVIEW_BUILD_DIR")"
cp -R dist "$WEB_PREVIEW_BUILD_DIR"

printf 'web preview build completed: %s\\n' "$WEB_PREVIEW_BUILD_DIR"
'''
    return f'''#!/usr/bin/env bash
set -euo pipefail

fail() {{
  printf 'web preview build failed: %s\\n' "$*" >&2
  exit 1
}}

ROOT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
MOBILE_DIR="$ROOT_DIR/apps/mobile"
APP_SLUG="${{APP_SLUG:-{slug}}}"
APP_RUNTIME_PROFILE="${{APP_RUNTIME_PROFILE:-preview}}"
API_RUNTIME="${{API_RUNTIME:-cloudflare_preview}}"
API_BASE_URL="${{API_BASE_URL:-https://preview.nienfos.com/{slug}/api}}"
WEB_PREVIEW_BUILD_DIR="${{WEB_PREVIEW_BUILD_DIR:-$ROOT_DIR/build/web-preview/$APP_SLUG}}"

case "$APP_RUNTIME_PROFILE" in
  real|staging|preview|mock) ;;
  *) fail "APP_RUNTIME_PROFILE must be real, staging, preview, or mock" ;;
esac

if [[ "$APP_RUNTIME_PROFILE" == "mock" && "${{ALLOW_MOCK_WEB_PREVIEW:-false}}" != "true" ]]; then
  fail "mock web preview builds require ALLOW_MOCK_WEB_PREVIEW=true"
fi

if [[ "$APP_RUNTIME_PROFILE" != "mock" ]]; then
  [[ -n "$API_BASE_URL" ]] || fail "API_BASE_URL is required"
  [[ "$API_BASE_URL" != *localhost* && "$API_BASE_URL" != *127.0.0.1* && "$API_BASE_URL" != *10.0.2.2* ]] || fail "API_BASE_URL must not be local for web preview"
  [[ "$API_BASE_URL" != *example* && "$API_BASE_URL" != *placeholder* ]] || fail "API_BASE_URL must not be placeholder"
fi

[[ "$API_RUNTIME" == "cloudflare_preview" ]] || fail "API_RUNTIME must be cloudflare_preview"
[[ -f "$MOBILE_DIR/pubspec.yaml" ]] || fail "missing apps/mobile/pubspec.yaml"

if ! command -v flutter >/dev/null 2>&1; then
  fail "flutter is required to build the web preview artifact"
fi

cd "$MOBILE_DIR"
flutter pub get
flutter build web --release \\
  --base-href "/$APP_SLUG/" \\
  --dart-define=APP_RUNTIME_PROFILE="$APP_RUNTIME_PROFILE" \\
  --dart-define=API_RUNTIME="$API_RUNTIME" \\
  --dart-define=API_BASE_URL="$API_BASE_URL" \\
  --dart-define=APP_SLUG="$APP_SLUG" \\
  --dart-define=CODEX_FEEDBACK_ENABLED="${{CODEX_FEEDBACK_ENABLED:-true}}" \\
  --dart-define=CODEX_FEEDBACK_BRIDGE_URL="${{CODEX_FEEDBACK_BRIDGE_URL:-}}" \\
  --dart-define=CODEX_BRIDGE_DEV_MODE="${{CODEX_BRIDGE_DEV_MODE:-true}}" \\
  --dart-define=CODEX_BRIDGE_WORKBENCH_URL="${{CODEX_BRIDGE_WORKBENCH_URL:-}}" \\
  --dart-define=CODEX_APP_UPDATER_ENABLED="${{CODEX_APP_UPDATER_ENABLED:-false}}" \\
  --dart-define=CODEX_APP_UPDATER_BRIDGE_URL="${{CODEX_APP_UPDATER_BRIDGE_URL:-}}" \\
  --output "$WEB_PREVIEW_BUILD_DIR"

printf 'web preview build completed: %s\\n' "$WEB_PREVIEW_BUILD_DIR"
'''


def _deploy_web_preview_script(slug: str) -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail

fail() {{
  printf 'web preview deploy failed: %s\\n' "$*" >&2
  exit 1
}}

ROOT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
cd "$ROOT_DIR"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/load_bridge_env.sh"
source "$ROOT_DIR/scripts/github_repo_access.sh"
bridge_env_require BRIDGE_URL
BRIDGE_URL="${{BRIDGE_URL}}"
BRIDGE_URL="${{BRIDGE_URL%/}}"
MODE="${{1:---plan}}"
PROJECT_PATH="${{PROJECT_PATH:-$ROOT_DIR}}"
SOURCE_APP="${{SOURCE_APP:-{slug}}}"
USER_AGENT="${{PREVIEW_SMOKE_USER_AGENT:-CodexProjectFactoryPreviewSmoke/1.0}}"

case "$MODE" in
  --plan)
    endpoint="$BRIDGE_URL/web-previews/plan"
    payload="$(printf '{{"projectPath":"%s","sourceApp":"%s"}}' "$PROJECT_PATH" "$SOURCE_APP")"
    ;;
  --apply)
    [[ "${{CONFIRM_APPLY:-false}}" == "true" ]] || fail "CONFIRM_APPLY=true is required"
    [[ -n "${{EXPECTED_PLAN_HASH:-}}" ]] || fail "EXPECTED_PLAN_HASH is required"
    endpoint="$BRIDGE_URL/web-previews/deploy"
    payload="$(printf '{{"projectPath":"%s","sourceApp":"%s","confirmApply":true,"expectedPlanHash":"%s"}}' "$PROJECT_PATH" "$SOURCE_APP" "$EXPECTED_PLAN_HASH")"
    ;;
  *)
    fail "usage: scripts/deploy_web_preview.sh --plan|--apply"
    ;;
esac

python3 - "$endpoint" "$payload" "$USER_AGENT" <<'PY'
import json
import sys
import urllib.error
import urllib.request

url = sys.argv[1]
payload = sys.argv[2].encode()
user_agent = sys.argv[3]
request = urllib.request.Request(
    url,
    data=payload,
    headers={{"content-type": "application/json", "user-agent": user_agent}},
    method="POST",
)
try:
    with urllib.request.urlopen(request, timeout=60) as response:
        print(json.dumps(json.loads(response.read().decode()), indent=2, sort_keys=True))
except urllib.error.HTTPError as exc:
    body = exc.read().decode()
    raise SystemExit(f"Bridge returned {{exc.code}}: {{body}}")
PY
'''


def _validate_web_preview_script(slug: str, frontend_strategy: str = "flutter") -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail

fail() {{
  printf 'web preview validation failed: %s\\n' "$*" >&2
  exit 1
}}

ROOT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
FRONTEND_STRATEGY="{frontend_strategy}"
export FRONTEND_STRATEGY
MANIFEST="$ROOT_DIR/deploy/web-preview/web-preview-manifest.yaml"
WORKER="$ROOT_DIR/deploy/web-preview/worker/src/index.js"
WORKER_HARNESS="$ROOT_DIR/deploy/web-preview/worker/local_preview_test.mjs"
WRANGLER_EXAMPLE="$ROOT_DIR/deploy/web-preview/wrangler.toml.example"
D1_MIGRATION="$ROOT_DIR/deploy/web-preview/d1/migrations/0001_preview_invites.sql"
BUSINESS_D1_MIGRATION="$ROOT_DIR/deploy/web-preview/d1/migrations/0002_business_records.sql"
SCHEMA_EVOLUTION_D1_MIGRATION="$ROOT_DIR/deploy/web-preview/d1/migrations/0003_preview_schema_evolution.sql"
APP_SLUG="${{APP_SLUG:-{slug}}}"
APP_RUNTIME_PROFILE="${{APP_RUNTIME_PROFILE:-preview}}"
API_RUNTIME="${{API_RUNTIME:-cloudflare_preview}}"
API_BASE_URL="${{API_BASE_URL:-https://preview.nienfos.com/{slug}/api}}"
WEB_PREVIEW_BUILD_DIR="${{WEB_PREVIEW_BUILD_DIR:-$ROOT_DIR/build/web-preview/$APP_SLUG}}"
REQUIRE_WEB_BUILD_OUTPUT="${{REQUIRE_WEB_BUILD_OUTPUT:-false}}"

case "$APP_RUNTIME_PROFILE" in
  real|staging|preview|mock) ;;
  *) fail "APP_RUNTIME_PROFILE must be real, staging, preview, or mock" ;;
esac

if [[ "$APP_RUNTIME_PROFILE" == "mock" && "${{ALLOW_MOCK_WEB_PREVIEW:-false}}" != "true" ]]; then
  fail "mock web preview validation requires ALLOW_MOCK_WEB_PREVIEW=true"
fi

if [[ "$APP_RUNTIME_PROFILE" != "mock" ]]; then
  [[ "$API_BASE_URL" == https://* ]] || fail "web preview API_BASE_URL must be https"
  [[ "$API_BASE_URL" != *localhost* && "$API_BASE_URL" != *127.0.0.1* && "$API_BASE_URL" != *10.0.2.2* ]] || fail "web preview API_BASE_URL must not be local"
  [[ "$API_BASE_URL" != *example* && "$API_BASE_URL" != *placeholder* ]] || fail "web preview API_BASE_URL must not be placeholder"
fi

[[ "$API_RUNTIME" == "cloudflare_preview" ]] || fail "API_RUNTIME must be cloudflare_preview"
[[ -f "$MANIFEST" ]] || fail "missing deploy/web-preview/web-preview-manifest.yaml"
[[ -f "$WORKER" ]] || fail "missing deploy/web-preview/worker/src/index.js"
[[ -f "$WORKER_HARNESS" ]] || fail "missing deploy/web-preview/worker/local_preview_test.mjs"
[[ -f "$WRANGLER_EXAMPLE" ]] || fail "missing deploy/web-preview/wrangler.toml.example"
[[ -f "$ROOT_DIR/scripts/load_bridge_env.sh" ]] || fail "missing scripts/load_bridge_env.sh"
[[ -f "$D1_MIGRATION" ]] || fail "missing deploy/web-preview/d1/migrations/0001_preview_invites.sql"
[[ -f "$BUSINESS_D1_MIGRATION" ]] || fail "missing deploy/web-preview/d1/migrations/0002_business_records.sql"
[[ -f "$SCHEMA_EVOLUTION_D1_MIGRATION" ]] || fail "missing deploy/web-preview/d1/migrations/0003_preview_schema_evolution.sql"
if [[ "$FRONTEND_STRATEGY" == "svelte" ]]; then
  [[ -f "$ROOT_DIR/apps/web/package.json" ]] || fail "missing apps/web/package.json"
  [[ -f "$ROOT_DIR/apps/web/src/main.ts" ]] || fail "missing apps/web/src/main.ts"
else
  [[ -f "$ROOT_DIR/apps/mobile/pubspec.yaml" ]] || fail "missing apps/mobile/pubspec.yaml"
  [[ -f "$ROOT_DIR/apps/mobile/lib/main.dart" ]] || fail "missing apps/mobile/lib/main.dart"
fi

if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 is required to validate web-preview-manifest.yaml"
fi

python3 - "$MANIFEST" "$APP_SLUG" <<'PY'
import sys
try:
    import yaml
except ModuleNotFoundError as exc:
    raise SystemExit("PyYAML is required to validate web-preview-manifest.yaml") from exc

manifest_path, expected_slug = sys.argv[1], sys.argv[2]
with open(manifest_path, encoding="utf-8") as handle:
    payload = yaml.safe_load(handle)
if not isinstance(payload, dict):
    raise SystemExit("manifest must be a YAML object")

runtime = payload.get("runtime")
build = payload.get("build")
cloudflare = payload.get("cloudflare")
resources = cloudflare.get("resources") if isinstance(cloudflare, dict) else None
access = payload.get("access")
expected_routes = payload.get("expected_routes")
checks = (
    ("source_app", payload.get("source_app"), expected_slug),
    ("frontend_strategy", payload.get("frontend_strategy"), "{frontend_strategy}"),
    ("stable_url", payload.get("stable_url"), "https://preview.nienfos.com/" + expected_slug),
    ("runtime.type", runtime.get("type") if isinstance(runtime, dict) else None, "cloudflare_worker_assets"),
    ("runtime.api_runtime", runtime.get("api_runtime") if isinstance(runtime, dict) else None, "cloudflare_preview"),
    ("runtime.default_profile", runtime.get("default_profile") if isinstance(runtime, dict) else None, "preview"),
    ("runtime.api_base_url", runtime.get("api_base_url") if isinstance(runtime, dict) else None, "https://preview.nienfos.com/" + expected_slug + "/api"),
    ("runtime.health_path", runtime.get("health_path") if isinstance(runtime, dict) else None, "/api/health"),
    ("runtime.asset_binding", runtime.get("asset_binding") if isinstance(runtime, dict) else None, "ASSETS"),
    ("build.output_dir", build.get("output_dir") if isinstance(build, dict) else None, "build/web-preview/" + expected_slug),
    ("build.asset_entrypoint", build.get("asset_entrypoint") if isinstance(build, dict) else None, "index.html"),
    ("cloudflare.worker_name", resources.get("worker_name") if isinstance(resources, dict) else None, "nienfos-preview-runtime"),
    ("cloudflare.d1_database", resources.get("d1_database") if isinstance(resources, dict) else None, "nienfos-preview"),
    ("access.mode", access.get("mode") if isinstance(access, dict) else None, "invite_token"),
    ("access.access_path", access.get("access_path") if isinstance(access, dict) else None, "/__preview/access"),
    ("access.cookie_name", access.get("cookie_name") if isinstance(access, dict) else None, "codex_preview_access"),
    ("access.single_use", access.get("single_use") if isinstance(access, dict) else None, True),
    ("access.d1_binding", access.get("d1_binding") if isinstance(access, dict) else None, "PREVIEW_DB"),
    ("access.migrations_dir", access.get("migrations_dir") if isinstance(access, dict) else None, "deploy/web-preview/d1/migrations"),
)
for label, actual, expected in checks:
    if actual != expected:
        raise SystemExit("%s mismatch: expected %r, got %r" % (label, expected, actual))
if not isinstance(expected_routes, list) or "/" + expected_slug + "/__preview/health" not in expected_routes:
    raise SystemExit("expected_routes must include the preview health route")
if not isinstance(expected_routes, list) or "/" + expected_slug + "/api/health" not in expected_routes:
    raise SystemExit("expected_routes must include the Preview API health route")
first_release = payload.get("first_release")
if not isinstance(first_release, dict) or first_release.get("mode") != "preview":
    raise SystemExit("first_release.mode must be preview")
if "{frontend_strategy}" == "flutter":
    if first_release.get("android_tag_pattern") != "android-preview-v*":
        raise SystemExit("first_release.android_tag_pattern must be android-preview-v*")
else:
    if first_release.get("android_tag_pattern") is not None:
        raise SystemExit("Svelte web preview must not declare android_tag_pattern")
if not isinstance(access, dict) or "WEB_PREVIEW_INVITE_SECRET" not in access.get("required_worker_secrets", []):
    raise SystemExit("access.required_worker_secrets must include WEB_PREVIEW_INVITE_SECRET")
PY

grep -q 'export default' "$WORKER" || fail "worker must use ES module export default"
grep -q 'async fetch(request, env, ctx)' "$WORKER" || fail "worker module fetch entrypoint missing"
! grep -q "addEventListener('fetch'" "$WORKER" || fail "worker must not use classic addEventListener fetch syntax"
! grep -q '__previewWorkerFetch' "$WORKER" || fail "worker must not use global classic harness exports"
grep -q '/__preview/health' "$WORKER" || fail "worker health route missing"
grep -q '/api/health' "$WORKER" || fail "worker Preview API health route missing"
grep -q '/api/auth/login' "$WORKER" || fail "worker Preview API auth route missing"
grep -q '/api/business/records' "$WORKER" || fail "worker Preview API business records route missing"
grep -q '/api/admin/business-records' "$WORKER" || fail "worker generated Flutter admin business records route missing"
grep -q 'ASSETS' "$WORKER" || fail "worker asset binding missing"
grep -q 'asset_not_found' "$WORKER" || fail "worker asset 404 missing"
grep -q 'content-security-policy' "$WORKER" || fail "worker security headers missing"
grep -q 'fonts.gstatic.com' "$WORKER" || fail "worker CSP must allow Flutter font runtime"
grep -q 'www.gstatic.com' "$WORKER" || fail "worker CSP must allow Flutter CanvasKit runtime"
grep -q 'flutter_bootstrap.js' "$WORKER" || fail "worker no-cache coverage missing for flutter_bootstrap.js"
grep -q 'main.dart.js' "$WORKER" || fail "worker no-cache coverage missing for main.dart.js"
grep -q 'manifest.json' "$WORKER" || fail "worker manifest handling missing"
grep -q 'isPublicSafeAssetPath' "$WORKER" || fail "worker public-safe manifest/icon handling missing"
grep -q 'WEB_PREVIEW_INVITE_SECRET' "$WORKER" || fail "worker invite secret binding missing"
grep -q 'PREVIEW_DB' "$WORKER" || fail "worker D1 binding missing"
grep -q '/__preview/access' "$WORKER" || fail "worker access route missing"
grep -q 'missing_invite_token' "$WORKER" || fail "worker missing-token response missing"
grep -q 'expired_invite_token' "$WORKER" || fail "worker expired-token response missing"
grep -q 'PREVIEW_DB' "$WRANGLER_EXAMPLE" || fail "wrangler D1 binding missing"
grep -q 'binding = "ASSETS"' "$WRANGLER_EXAMPLE" || fail "wrangler assets binding missing"
! grep -q 'not_found_handling = "single-page-application"' "$WRANGLER_EXAMPLE" || fail "protected previews must not use Cloudflare Assets SPA fallback"
grep -q 'WEB_PREVIEW_INVITE_SECRET' "$WRANGLER_EXAMPLE" || fail "wrangler invite secret documentation missing"
grep -q 'CREATE TABLE IF NOT EXISTS preview_invites' "$D1_MIGRATION" || fail "D1 preview_invites migration missing"
grep -q 'CREATE TABLE IF NOT EXISTS preview_apps' "$D1_MIGRATION" || fail "D1 preview_apps migration missing"
grep -q 'CREATE TABLE IF NOT EXISTS preview_builds' "$D1_MIGRATION" || fail "D1 preview_builds migration missing"
grep -q 'CREATE TABLE IF NOT EXISTS preview_tenants' "$D1_MIGRATION" || fail "D1 preview_tenants migration missing"
grep -q 'CREATE TABLE IF NOT EXISTS preview_users' "$D1_MIGRATION" || fail "D1 preview_users migration missing"
grep -q 'CREATE TABLE IF NOT EXISTS preview_sessions' "$D1_MIGRATION" || fail "D1 preview_sessions migration missing"
grep -q 'CREATE TABLE IF NOT EXISTS preview_roles' "$D1_MIGRATION" || fail "D1 preview_roles migration missing"
grep -q 'CREATE TABLE IF NOT EXISTS preview_admin_invites' "$D1_MIGRATION" || fail "D1 preview_admin_invites migration missing"
grep -q 'CREATE TABLE IF NOT EXISTS preview_business_records' "$D1_MIGRATION" || fail "D1 preview_business_records migration missing"
grep -q 'CREATE TABLE IF NOT EXISTS preview_assets' "$D1_MIGRATION" || fail "D1 preview_assets migration missing"
grep -q 'CREATE TABLE IF NOT EXISTS preview_events' "$D1_MIGRATION" || fail "D1 preview_events migration missing"
grep -q 'CREATE TABLE IF NOT EXISTS preview_notifications' "$D1_MIGRATION" || fail "D1 preview_notifications migration missing"
grep -q 'CREATE TABLE IF NOT EXISTS preview_app_updates' "$D1_MIGRATION" || fail "D1 preview_app_updates migration missing"
grep -q 'CREATE TABLE IF NOT EXISTS preview_business_record_events' "$BUSINESS_D1_MIGRATION" || fail "D1 preview_business_record_events migration missing"
grep -q 'codex:d1:add-column' "$SCHEMA_EVOLUTION_D1_MIGRATION" || fail "D1 schema evolution directives missing"
grep -q 'source_app TEXT NOT NULL' "$BUSINESS_D1_MIGRATION" || fail "D1 business records migration source_app scope missing"
grep -q 'app_slug TEXT NOT NULL' "$BUSINESS_D1_MIGRATION" || fail "D1 business records migration app_slug scope missing"
grep -q 'CREATE INDEX IF NOT EXISTS idx_preview_business_record_events_app_record' "$BUSINESS_D1_MIGRATION" || fail "D1 business record event index must be idempotent"
grep -q 'token_sha256' "$D1_MIGRATION" || fail "D1 token hash column missing"
grep -q 'used_at' "$D1_MIGRATION" || fail "D1 used_at column missing"
grep -q 'revoked_at' "$D1_MIGRATION" || fail "D1 revoked_at column missing"
grep -q 'email TEXT' "$D1_MIGRATION" || fail "D1 invite email column missing"
grep -q 'role TEXT' "$D1_MIGRATION" || fail "D1 invite role column missing"
if [[ "$FRONTEND_STRATEGY" == "svelte" ]]; then
  grep -q 'VITE_APP_RUNTIME_PROFILE' "$ROOT_DIR/apps/web/src/config.ts" || fail "Svelte runtime profile env missing"
  grep -q 'VITE_API_RUNTIME' "$ROOT_DIR/apps/web/src/config.ts" || fail "Svelte API runtime env missing"
  grep -q 'VITE_API_BASE_URL' "$ROOT_DIR/apps/web/src/config.ts" || fail "Svelte preview API env missing"
else
  grep -q 'APP_RUNTIME_PROFILE' "$ROOT_DIR/apps/mobile/lib/main.dart" || fail "Flutter runtime profile define missing"
  grep -q 'API_RUNTIME' "$ROOT_DIR/apps/mobile/lib/main.dart" || fail "Flutter API runtime define missing"
  grep -q 'APP_SLUG' "$ROOT_DIR/apps/mobile/lib/main.dart" || fail "Flutter app slug define missing"
fi

if command -v node >/dev/null 2>&1; then
  node --check --input-type=module < "$WORKER" >/dev/null
  node "$WORKER_HARNESS" >/dev/null
else
  printf 'node not found; skipping Worker syntax and local harness validation\\n'
fi

if [[ "$REQUIRE_WEB_BUILD_OUTPUT" == "true" ]]; then
  [[ -f "$WEB_PREVIEW_BUILD_DIR/index.html" ]] || fail "missing web build output index.html at $WEB_PREVIEW_BUILD_DIR"
  if [[ "$FRONTEND_STRATEGY" == "svelte" ]]; then
    grep -q '<script type="module"' "$WEB_PREVIEW_BUILD_DIR/index.html" || fail "Svelte web build index must load module assets"
    [[ ! -f "$WEB_PREVIEW_BUILD_DIR/flutter_bootstrap.js" ]] || fail "Svelte web build must not include Flutter bootstrap"
  else
    [[ -f "$WEB_PREVIEW_BUILD_DIR/manifest.json" ]] || fail "missing web build output manifest.json at $WEB_PREVIEW_BUILD_DIR"
    [[ -f "$WEB_PREVIEW_BUILD_DIR/flutter_bootstrap.js" ]] || fail "missing web build output flutter_bootstrap.js at $WEB_PREVIEW_BUILD_DIR"
    [[ -d "$WEB_PREVIEW_BUILD_DIR/assets" ]] || fail "missing web build output assets directory at $WEB_PREVIEW_BUILD_DIR/assets"
  fi
else
  printf 'web build output check skipped; set REQUIRE_WEB_BUILD_OUTPUT=true after scripts/build_web_preview.sh\\n'
fi

printf 'web preview validation completed: profile=%s api_runtime=%s url=%s\\n' "$APP_RUNTIME_PROFILE" "$API_RUNTIME" "$API_BASE_URL"
'''


def _validation_script(frontend_strategy: str = "flutter") -> str:
    return r'''#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
MOBILE_DIR="$ROOT_DIR/apps/mobile"
WEB_DIR="$ROOT_DIR/apps/web"
FRONTEND_STRATEGY="__FRONTEND_STRATEGY__"
VALIDATION_DIR="$ROOT_DIR/.generated-validation"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-0}"
BACKEND_HEALTH_TIMEOUT_SECONDS="${BACKEND_HEALTH_TIMEOUT_SECONDS:-30}"
VALIDATION_VENV="${VALIDATION_VENV:-$BACKEND_DIR/.venv}"

mkdir -p "$VALIDATION_DIR"

random_secret() {
  "$PYTHON_BIN" - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
}

free_port() {
  "$PYTHON_BIN" - <<'PY'
import socket
sock = socket.socket()
sock.bind(("127.0.0.1", 0))
print(sock.getsockname()[1])
sock.close()
PY
}

if [ "$BACKEND_PORT" = "0" ]; then
  BACKEND_PORT="$(free_port)"
fi

export BACKEND_HOST
export BACKEND_PORT
export BACKEND_HEALTH_TIMEOUT_SECONDS

if [ -z "${DATABASE_URL:-}" ]; then
  rm -f "$VALIDATION_DIR/app.db"
  export DATABASE_URL="sqlite:///$VALIDATION_DIR/app.db"
else
  export DATABASE_URL
fi
export SECRET_KEY="${SECRET_KEY:-$(random_secret)}"
export ADMIN_EMAIL="${ADMIN_EMAIL:-admin.validation@example.com}"
export ADMIN_INITIAL_PASSWORD="${ADMIN_INITIAL_PASSWORD:-$(random_secret)}"
export CORS_ORIGINS="${CORS_ORIGINS:-http://127.0.0.1:$BACKEND_PORT}"

if [ ! -x "$VALIDATION_VENV/bin/python" ]; then
  "$PYTHON_BIN" -m venv "$VALIDATION_VENV"
fi

# shellcheck disable=SC1091
. "$VALIDATION_VENV/bin/activate"

cd "$BACKEND_DIR"
python -m pip install -e ".[dev]"
python -m pytest

python -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" > "$VALIDATION_DIR/backend.log" 2>&1 &
BACKEND_PID="$!"

cleanup() {
  if kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
    wait "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

python - <<'PY'
import os
import time
import urllib.request

url = f"http://{os.environ.get('BACKEND_HOST', '127.0.0.1')}:{os.environ['BACKEND_PORT']}/health"
deadline = time.time() + int(os.environ.get("BACKEND_HEALTH_TIMEOUT_SECONDS", "30"))
last_error = None
while time.time() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            if response.status == 200:
                print(f"backend health ok: {url}")
                raise SystemExit(0)
    except Exception as exc:
        last_error = exc
        time.sleep(0.5)
raise SystemExit(f"backend health timeout for {url}: {last_error}")
PY

python - <<'PY'
import json
import os
import urllib.error
import urllib.request

base_url = f"http://{os.environ.get('BACKEND_HOST', '127.0.0.1')}:{os.environ['BACKEND_PORT']}"

def request(method, path, payload=None, token=None):
    data = None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        data = json.dumps(payload).encode()
    req = urllib.request.Request(base_url + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        raise AssertionError(f"{method} {path} failed: {exc.code} {body}") from exc

login = request(
    "POST",
    "/auth/login",
    {
        "email": os.environ["ADMIN_EMAIL"],
        "password": os.environ["ADMIN_INITIAL_PASSWORD"],
    },
)
token = login["access_token"]
me = request("GET", "/auth/me", token=token)
assert "owner" in me["roles"], me
roles = request("GET", "/admin/roles", token=token)
assert "owner" in roles and "customer" in roles, roles
business_records = request("GET", "/admin/business-records", token=token)
assert isinstance(business_records, list), business_records
business_record_name = "validation-business-record-" + token[:8].lower().replace("_", "x").replace("-", "x")
created = request("POST", "/admin/business-records", {"name": business_record_name}, token=token)
assert created["name"] == business_record_name, created
notifications = request("GET", "/notifications", token=token)
assert isinstance(notifications, list), notifications
print("contract ok: auth/me/admin/business-records/notifications")
PY

cd "$ROOT_DIR"
if [[ "$FRONTEND_STRATEGY" == "flutter" ]]; then
  APP_RELEASE_TAG=android-v0.1.0-build.1 \
  APP_RUNTIME_PROFILE=real \
  API_BASE_URL=https://api.validation.invalid \
  scripts/validate_release_profiles.sh

  APP_RELEASE_TAG=android-mock-v0.1.0-build.1 \
  APP_RUNTIME_PROFILE=mock \
  scripts/validate_release_profiles.sh

  if command -v flutter >/dev/null 2>&1; then
  cd "$MOBILE_DIR"
  flutter test --dart-define=API_BASE_URL="http://$BACKEND_HOST:$BACKEND_PORT"
  else
    echo "flutter not found; skipping mobile template tests"
  fi
else
  [[ -f "$WEB_DIR/package.json" ]] || {
    echo "missing apps/web/package.json for Svelte strategy" >&2
    exit 1
  }
  if command -v npm >/dev/null 2>&1; then
    cd "$WEB_DIR"
    npm ci
    npm run lint
    npm test
    npm run validate:preview
    VITE_APP_RUNTIME_PROFILE=preview \
    VITE_API_RUNTIME=cloudflare_preview \
    VITE_API_BASE_URL="https://preview.nienfos.com/${APP_SLUG:-$(basename "$ROOT_DIR")}/api" \
    npm run build
  else
    echo "npm not found; skipping Svelte template tests"
  fi
fi

cd "$ROOT_DIR"
APP_RUNTIME_PROFILE=preview \
API_RUNTIME=cloudflare_preview \
API_BASE_URL=https://preview.nienfos.com/${APP_SLUG:-$(basename "$ROOT_DIR")}/api \
scripts/validate_web_preview.sh

echo "generated project validation completed"
'''.replace("__FRONTEND_STRATEGY__", frontend_strategy)


def _publish_script() -> str:
    return r'''#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PROJECT_SLUG="$(python3 - <<'PY'
import pathlib
import re

project = pathlib.Path(".codex/project.yaml").read_text(encoding="utf-8")
match = re.search(r"^slug:\s*([A-Za-z0-9_.-]+)\s*$", project, re.MULTILINE)
if not match:
    raise SystemExit("Could not read slug from .codex/project.yaml")
print(match.group(1))
PY
)"
BRANCH="${PUBLISH_BRANCH:-main}"
OWNER="${GITHUB_OWNER:-}"
VISIBILITY="${GITHUB_VISIBILITY:-private}"

if ! command -v git >/dev/null 2>&1; then
  echo "git is required to publish this project." >&2
  exit 2
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) is required to create/verify the remote repository." >&2
  exit 2
fi

if [ -z "$OWNER" ]; then
  OWNER="$(gh api user --jq .login 2>/dev/null || true)"
fi
if [ -z "$OWNER" ]; then
  echo "Set GITHUB_OWNER or authenticate gh before publishing." >&2
  exit 2
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git init
fi

git add -A
if ! git diff --cached --quiet; then
  git -c user.name="${GIT_AUTHOR_NAME:-Codex Project Factory}" \
      -c user.email="${GIT_AUTHOR_EMAIL:-codex-project-factory@local}" \
      commit -m "${INITIAL_COMMIT_MESSAGE:-Initial Project Factory baseline}"
fi

git branch -M "$BRANCH"

REPO="$OWNER/$PROJECT_SLUG"
source "$ROOT_DIR/scripts/github_repo_access.sh"
if ! github_repo_accessible "$REPO"; then
  gh repo create "$REPO" "--$VISIBILITY" --source . --remote origin --push
else
  if ! git remote get-url origin >/dev/null 2>&1; then
    git remote add origin "https://github.com/$REPO.git"
  fi
  git push -u origin "$BRANCH"
fi

PREVIEW_API_BASE_URL="${PREVIEW_API_BASE_URL:-${API_BASE_URL:-https://preview.nienfos.com/$PROJECT_SLUG/api}}"
PREVIEW_API_BASE_URL="${PREVIEW_API_BASE_URL%/}"
if [[ "$PREVIEW_API_BASE_URL" != "https://preview.nienfos.com/$PROJECT_SLUG/api" ]]; then
  echo "PREVIEW_API_BASE_URL must be https://preview.nienfos.com/$PROJECT_SLUG/api" >&2
  exit 2
fi
gh variable set API_BASE_URL --repo "$REPO" --body "$PREVIEW_API_BASE_URL" >/dev/null

echo "published: https://github.com/$REPO"
'''

def _register_installable_app_script(slug: str, name: str) -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
cd "$ROOT_DIR"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/load_bridge_env.sh"
source "$ROOT_DIR/scripts/github_repo_access.sh"
DRY_RUN=false
BRIDGE_URL="${{BRIDGE_URL:-}}"
BRIDGE_PUBLIC_URL="${{BRIDGE_PUBLIC_URL:-}}"
SOURCE_APP="${{SOURCE_APP:-}}"
DISPLAY_NAME="${{DISPLAY_NAME:-}}"
RELEASE_TAG_PATTERN="${{RELEASE_TAG_PATTERN:-}}"
APK_ASSET_PATTERN="${{APK_ASSET_PATTERN:-}}"
LATEST_ASSET_NAME="${{LATEST_ASSET_NAME:-}}"
RELEASE_CHANNEL="${{RELEASE_CHANNEL:-}}"
PREVIEW_URL="${{PREVIEW_URL:-}}"
RUNTIME_PROFILE="${{RUNTIME_PROFILE:-}}"
PRODUCTION_READY="${{PRODUCTION_READY:-}}"
MOCK_OR_DEMO="${{MOCK_OR_DEMO:-}}"
ENABLED="${{ENABLED:-true}}"
REQUIRE_INSTALLABLE_APK="${{REQUIRE_INSTALLABLE_APK:-true}}"
EXPECTED_PACKAGE_ID="${{EXPECTED_PACKAGE_ID:-}}"
EXPECTED_SHA256="${{EXPECTED_SHA256:-}}"
APP_RELEASE_TAG="${{APP_RELEASE_TAG:-}}"
BRIDGE_REGISTRATION_TOKEN="${{BRIDGE_REGISTRATION_TOKEN:-${{INSTALLABLE_APPS_REGISTRATION_TOKEN:-}}}}"
RUNTIME_CONTRACT="$ROOT_DIR/release/preview-runtime.json"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --bridge-url)
      BRIDGE_URL="${{2:-}}"
      shift 2
      ;;
    --token)
      BRIDGE_REGISTRATION_TOKEN="${{2:-}}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -f "$RUNTIME_CONTRACT" ]]; then
  eval "$(python3 - "$RUNTIME_CONTRACT" <<'PY'
from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
fields = {{
    "RT_SOURCE_APP": payload.get("sourceApp"),
    "RT_DISPLAY_NAME": payload.get("displayName"),
    "RT_RELEASE_TAG_PATTERN": payload.get("releaseTagPattern"),
    "RT_APK_ASSET_PATTERN": payload.get("apkAssetPattern"),
    "RT_LATEST_ASSET_NAME": payload.get("latestAssetName"),
    "RT_RELEASE_CHANNEL": payload.get("releaseChannel"),
    "RT_PREVIEW_URL": payload.get("previewUrl"),
    "RT_RUNTIME_PROFILE": payload.get("runtimeProfile"),
    "RT_PRODUCTION_READY": payload.get("productionReady"),
    "RT_MOCK_OR_DEMO": payload.get("mockOrDemo"),
}}
for key, value in fields.items():
    if isinstance(value, bool):
        value = "true" if value else "false"
    if value is not None:
        print(f"{{key}}={{shlex.quote(str(value))}}")
PY
)"
fi

SOURCE_APP="${{SOURCE_APP:-${{RT_SOURCE_APP:-{slug}}}}}"
DISPLAY_NAME="${{DISPLAY_NAME:-${{RT_DISPLAY_NAME:-{name} Preview}}}}"
RELEASE_TAG_PATTERN="${{RELEASE_TAG_PATTERN:-${{RT_RELEASE_TAG_PATTERN:-android-preview-v*}}}}"
APK_ASSET_PATTERN="${{APK_ASSET_PATTERN:-${{RT_APK_ASSET_PATTERN:-${{SOURCE_APP}}*.apk}}}}"
LATEST_ASSET_NAME="${{LATEST_ASSET_NAME:-${{RT_LATEST_ASSET_NAME:-${{SOURCE_APP}}.apk}}}}"
RELEASE_CHANNEL="${{RELEASE_CHANNEL:-${{RT_RELEASE_CHANNEL:-prerelease}}}}"
PREVIEW_URL="${{PREVIEW_URL:-${{RT_PREVIEW_URL:-https://preview.nienfos.com/{slug}}}}}"
RUNTIME_PROFILE="${{RUNTIME_PROFILE:-${{RT_RUNTIME_PROFILE:-preview}}}}"
PRODUCTION_READY="${{PRODUCTION_READY:-${{RT_PRODUCTION_READY:-false}}}}"
MOCK_OR_DEMO="${{MOCK_OR_DEMO:-${{RT_MOCK_OR_DEMO:-false}}}}"

if [[ -z "$BRIDGE_URL" ]]; then
  echo "BRIDGE_URL is required. Example: BRIDGE_URL=http://127.0.0.1:8000 $0" >&2
  exit 2
fi
BRIDGE_URL="${{BRIDGE_URL%/}}"
BRIDGE_PUBLIC_URL="${{BRIDGE_PUBLIC_URL:-$BRIDGE_URL}}"
BRIDGE_PUBLIC_URL="${{BRIDGE_PUBLIC_URL%/}}"
if [[ -z "$BRIDGE_REGISTRATION_TOKEN" ]]; then
  echo "BRIDGE_REGISTRATION_TOKEN or INSTALLABLE_APPS_REGISTRATION_TOKEN is required." >&2
  exit 2
fi

GITHUB_REPO="${{GITHUB_REPO:-}}"
if [[ -z "$GITHUB_REPO" ]]; then
  origin_url="$(git remote get-url origin 2>/dev/null || true)"
  origin_url="${{origin_url#https://github.com/}}"
  origin_url="${{origin_url#git@github.com:}}"
  origin_url="${{origin_url%.git}}"
  GITHUB_REPO="$origin_url"
fi

if [[ -z "$GITHUB_REPO" || "$GITHUB_REPO" != */* ]]; then
  echo "Set GITHUB_REPO=owner/repo or configure git origin before registering." >&2
  exit 2
fi
github_require_repo_access "$GITHUB_REPO"
export SOURCE_APP DISPLAY_NAME GITHUB_REPO RELEASE_TAG_PATTERN APK_ASSET_PATTERN
export LATEST_ASSET_NAME RELEASE_CHANNEL ENABLED EXPECTED_PACKAGE_ID EXPECTED_SHA256
export PREVIEW_URL RUNTIME_PROFILE PRODUCTION_READY MOCK_OR_DEMO APP_RELEASE_TAG

if [[ -z "$APP_RELEASE_TAG" && -f apps/mobile/pubspec.yaml ]]; then
  version="$(awk '/^version:/ {{ print $2; exit }}' apps/mobile/pubspec.yaml)"
  if [[ -n "$version" ]]; then
    APP_RELEASE_TAG="android-preview-v${{version//+/-build.}}"
  fi
fi
if [[ -z "$APP_RELEASE_TAG" ]]; then
  echo "APP_RELEASE_TAG is required or apps/mobile/pubspec.yaml must define version." >&2
  exit 2
fi

if [[ -n "$EXPECTED_PACKAGE_ID" ]]; then
  python3 - <<'PY'
from __future__ import annotations

import os
import re

package_id = os.environ["EXPECTED_PACKAGE_ID"]
part = r"[A-Za-z][A-Za-z0-9_]*"
if not re.fullmatch(rf"{{part}}(\\.{{part}})+", package_id):
    raise SystemExit("EXPECTED_PACKAGE_ID is not a valid Android package id.")
PY
fi

if [[ -n "$EXPECTED_SHA256" && ! "$EXPECTED_SHA256" =~ ^[a-fA-F0-9]{{64}}$ ]]; then
  echo "EXPECTED_SHA256 must be 64 hex characters." >&2
  exit 2
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) is required to verify release APK assets." >&2
  exit 2
fi

asset_names="$(gh release view "$APP_RELEASE_TAG" --repo "$GITHUB_REPO" --json assets --jq '.assets[].name' 2>/dev/null || true)"
if [[ -z "$asset_names" ]]; then
  echo "Release $APP_RELEASE_TAG was not found or has no assets in $GITHUB_REPO." >&2
  exit 2
fi
if ! printf '%s\n' "$asset_names" | grep -Fx "$LATEST_ASSET_NAME" >/dev/null; then
  echo "Release $APP_RELEASE_TAG does not contain APK asset $LATEST_ASSET_NAME." >&2
  printf 'Available assets:\n%s\n' "$asset_names" >&2
  exit 2
fi

payload="$(python3 - <<'PY'
from __future__ import annotations

import json
import os

payload = {{
    "sourceApp": os.environ["SOURCE_APP"],
    "displayName": os.environ["DISPLAY_NAME"],
    "repo": os.environ["GITHUB_REPO"],
    "releaseTagPattern": os.environ["RELEASE_TAG_PATTERN"],
    "apkAssetPattern": os.environ["APK_ASSET_PATTERN"],
    "latestAssetName": os.environ["LATEST_ASSET_NAME"],
    "releaseChannel": os.environ["RELEASE_CHANNEL"],
    "enabled": os.environ.get("ENABLED", "true").lower() == "true",
    "previewUrl": os.environ["PREVIEW_URL"],
    "runtimeProfile": os.environ["RUNTIME_PROFILE"],
    "productionReady": os.environ.get("PRODUCTION_READY", "false").lower() == "true",
    "mockOrDemo": os.environ.get("MOCK_OR_DEMO", "false").lower() == "true",
    "releaseMetadata": {{
        "initialPreviewRelease": True,
        "releaseTagPattern": os.environ["RELEASE_TAG_PATTERN"],
        "releaseTag": os.environ["APP_RELEASE_TAG"],
        "latestAssetName": os.environ["LATEST_ASSET_NAME"],
    }},
}}
package_id = os.environ.get("EXPECTED_PACKAGE_ID", "").strip()
if package_id:
    payload["expectedPackageId"] = package_id
print(json.dumps(payload))
PY
)"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "$payload" | python3 -m json.tool
  echo "dry-run: release and asset were verified; registry was not mutated."
  exit 0
fi

curl -fsS \\
  -X POST "$BRIDGE_URL/installable-apps" \\
  -H "Authorization: Bearer $BRIDGE_REGISTRATION_TOKEN" \\
  -H 'Content-Type: application/json' \\
  -d "$payload" >/tmp/project-factory-register-installable-app.json

bridge_detail_headers=()
if [[ "$BRIDGE_PUBLIC_URL" != "$BRIDGE_URL" ]]; then
  public_host="$(python3 - "$BRIDGE_PUBLIC_URL" <<'PY'
from __future__ import annotations

import sys
from urllib.parse import urlparse

print(urlparse(sys.argv[1]).netloc)
PY
)"
  public_scheme="$(python3 - "$BRIDGE_PUBLIC_URL" <<'PY'
from __future__ import annotations

import sys
from urllib.parse import urlparse

print(urlparse(sys.argv[1]).scheme)
PY
)"
  [[ -n "$public_host" ]] && bridge_detail_headers+=(-H "Host: $public_host")
  [[ -n "$public_scheme" ]] && bridge_detail_headers+=(-H "X-Forwarded-Proto: $public_scheme")
fi

curl -fsS "${{bridge_detail_headers[@]}}" "$BRIDGE_URL/installable-apps/$SOURCE_APP" \\
  >/tmp/project-factory-installable-app-detail.json

python3 - <<'PY'
from __future__ import annotations

import json
import os
import re
from pathlib import Path

registered = json.loads(Path("/tmp/project-factory-register-installable-app.json").read_text())
detail = json.loads(Path("/tmp/project-factory-installable-app-detail.json").read_text())
print(f"registered installable app: {{registered['sourceApp']}} -> {{registered['displayName']}}")
print(f"install status: {{detail.get('installStatusHint')}}")
print(f"apk url: {{detail.get('apkUrl')}}")
if not detail.get("latestBuild"):
    raise SystemExit("Bridge registration must expose latestBuild.")
apk_url = str(detail.get("apkUrl") or "")
if not apk_url.startswith(("http://", "https://")):
    raise SystemExit("Bridge registration must expose an HTTP(S) APK proxy URL.")
actual_sha = str(detail.get("sha256") or "").lower()
if not re.fullmatch(r"[a-f0-9]{{64}}", actual_sha):
    raise SystemExit("Bridge registration must expose a 64 hex APK sha256.")
if detail.get("runtimeProfile") != "preview":
    raise SystemExit("Bridge registration runtimeProfile must be preview.")
if detail.get("productionReady") is not False:
    raise SystemExit("Bridge registration productionReady must be false.")
if detail.get("mockOrDemo") is not False:
    raise SystemExit("Bridge registration mockOrDemo must be false.")
expected_sha = os.environ.get("EXPECTED_SHA256", "").strip().lower()
if expected_sha and expected_sha != actual_sha:
    raise SystemExit("Registered APK checksum does not match EXPECTED_SHA256.")
if os.environ.get("REQUIRE_INSTALLABLE_APK", "true").lower() == "true" and not detail.get("apkUrl"):
    raise SystemExit(
        "Bridge registry updated, but no installable APK is available yet. "
        "Publish the Android release asset or rerun with REQUIRE_INSTALLABLE_APK=false."
    )
PY

apk_url="$(python3 - <<'PY'
from __future__ import annotations

import json
from pathlib import Path

detail = json.loads(Path("/tmp/project-factory-installable-app-detail.json").read_text())
print(detail.get("apkUrl") or "")
PY
)"
if [[ -n "$apk_url" ]]; then
  if curl -fsSI "$apk_url" >/dev/null; then
    :
  elif [[ "$BRIDGE_PUBLIC_URL" != "$BRIDGE_URL" && ( "$apk_url" == "$BRIDGE_PUBLIC_URL" || "$apk_url" == "$BRIDGE_PUBLIC_URL/"* ) ]]; then
    local_apk_url="$BRIDGE_URL${{apk_url#"$BRIDGE_PUBLIC_URL"}}"
    curl -fsSI "${{bridge_detail_headers[@]}}" "$local_apk_url" >/dev/null || {{
      echo "Bridge APK proxy did not respond for $apk_url or local bridge fallback $local_apk_url" >&2
      exit 2
    }}
    echo "Bridge APK proxy verified through local bridge transport for public APK URL: $apk_url"
  else
    echo "Bridge APK proxy did not respond for $apk_url" >&2
    exit 2
  fi
fi
'''


def _finalize_local_commit_script() -> str:
    return r'''#!/usr/bin/env bash
set -euo pipefail

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git init
fi

git add -A
if ! git diff --cached --quiet; then
  git -c user.name="${GIT_AUTHOR_NAME:-Codex Project Factory}" \
      -c user.email="${GIT_AUTHOR_EMAIL:-codex-project-factory@local}" \
      commit -m "${PROJECT_FACTORY_FINAL_COMMIT_MESSAGE:-Finalize Project Factory output}"
fi

printf 'local git commit ready\n'
'''


def _bridge_env_loader_script() -> str:
    return r'''#!/usr/bin/env bash
# Official Project Factory loader for real Bridge-owned Initial Preview Release
# secrets. It intentionally prints only file presence and missing variable names,
# never variable values.

bridge_env_load() {
  local bridge_root="${CODEX_MOBILE_BRIDGE_ROOT:-/home/batata/Projects/codex-cli-mobile-bridge}"
  local loaded=0
  local env_file
  for env_file in "$bridge_root/secrets/cloudflare.env" "$bridge_root/.env"; do
    if [[ -f "$env_file" ]]; then
      bridge_env_load_file "$env_file"
      loaded=1
    fi
  done
  export CODEX_MOBILE_BRIDGE_ENV_LOADED="$loaded"
}

bridge_env_load_file() {
  local env_file="$1"
  local line key value
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    [[ "$line" =~ ^[[:space:]]*export[[:space:]]+ ]] && line="${line#export }"
    [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || continue
    key="${line%%=*}"
    value="${line#*=}"
    if [[ "$value" == \"*\" && "$value" == *\" ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
      value="${value:1:${#value}-2}"
    fi
    if [[ -n "${!key+x}" ]]; then
      continue
    fi
    export "$key=$value"
  done < "$env_file"
}

bridge_env_require() {
  local missing=()
  local key
  for key in "$@"; do
    if [[ -z "${!key:-}" ]]; then
      missing+=("$key")
    fi
  done
  if (( ${#missing[@]} > 0 )); then
    printf 'Bridge env preflight failed. Missing required variable(s): %s\n' "${missing[*]}" >&2
    printf 'Load them from /home/batata/Projects/codex-cli-mobile-bridge/secrets/cloudflare.env or /home/batata/Projects/codex-cli-mobile-bridge/.env.\n' >&2
    return 2
  fi
}

bridge_env_require_any() {
  local label="$1"
  shift
  local key
  for key in "$@"; do
    if [[ -n "${!key:-}" ]]; then
      return 0
    fi
  done
  printf 'Bridge env preflight failed. Missing one of %s: %s\n' "$label" "$*" >&2
  printf 'Load it from /home/batata/Projects/codex-cli-mobile-bridge/secrets/cloudflare.env or /home/batata/Projects/codex-cli-mobile-bridge/.env.\n' >&2
  return 2
}

bridge_env_load_preview_signing() {
  local source_app="${SOURCE_APP:-${APP_SLUG:-}}"
  if [[ -z "$source_app" ]]; then
    printf 'Bridge env preflight failed. SOURCE_APP or APP_SLUG is required before loading preview signing.\n' >&2
    return 2
  fi
  local bridge_root="${CODEX_MOBILE_BRIDGE_ROOT:-/home/batata/Projects/codex-cli-mobile-bridge}"
  local signing_env="$bridge_root/secrets/$source_app-preview-signing.env"
  local keystore="$bridge_root/secrets/$source_app-preview-upload-keystore.jks"
  [[ -f "$signing_env" ]] || {
    printf 'Android preview signing env missing: %s\n' "$signing_env" >&2
    return 2
  }
  [[ -f "$keystore" ]] || {
    printf 'Android preview keystore missing: %s\n' "$keystore" >&2
    return 2
  }
  set -a
  # shellcheck disable=SC1090
  source "$signing_env"
  set +a
  export ANDROID_KEYSTORE_PATH="$keystore"
  bridge_env_require ANDROID_KEY_ALIAS ANDROID_STORE_PASSWORD ANDROID_KEY_PASSWORD
}

bridge_env_load
'''


def _github_repo_access_helper_script() -> str:
    return r'''#!/usr/bin/env bash
# Reusable GitHub repository access checks for private repos. GitHub may return
# 404 for unauthenticated API/web requests; these helpers force authenticated
# host checks before any script concludes that a repo/release/variable is
# missing.

github_repo_from_origin() {
  local origin_url
  origin_url="$(git remote get-url origin 2>/dev/null || true)"
  origin_url="${origin_url#https://github.com/}"
  origin_url="${origin_url#git@github.com:}"
  origin_url="${origin_url%.git}"
  printf '%s\n' "$origin_url"
}

github_repo_accessible() {
  local repo="$1"
  [[ "$repo" == */* ]] || return 2
  command -v gh >/dev/null 2>&1 || return 3
  command -v git >/dev/null 2>&1 || return 4
  gh repo view "$repo" >/tmp/project-factory-gh-repo-view.out 2>/tmp/project-factory-gh-repo-view.err || return 5
  git ls-remote "https://github.com/$repo.git" HEAD >/tmp/project-factory-git-ls-remote.out 2>/tmp/project-factory-git-ls-remote.err || return 6
}

github_require_repo_access() {
  local repo="$1"
  if github_repo_accessible "$repo"; then
    return 0
  fi
  local status=$?
  case "$status" in
    2) printf 'GitHub repo reference must be OWNER/REPO: %s\n' "$repo" >&2 ;;
    3) printf 'gh is required to inspect private GitHub repository access.\n' >&2 ;;
    4) printf 'git is required to verify private GitHub repository HEAD.\n' >&2 ;;
    5)
      printf 'Authenticated GitHub repo view failed for %s. Do not trust unauthenticated 404/missing results.\n' "$repo" >&2
      [[ -s /tmp/project-factory-gh-repo-view.err ]] && cat /tmp/project-factory-gh-repo-view.err >&2
      ;;
    6)
      printf 'git ls-remote HEAD failed for https://github.com/%s.git. Repository may be private, missing, or inaccessible with current credentials.\n' "$repo" >&2
      [[ -s /tmp/project-factory-git-ls-remote.err ]] && cat /tmp/project-factory-git-ls-remote.err >&2
      ;;
    *) printf 'GitHub repository access check failed for %s.\n' "$repo" >&2 ;;
  esac
  return "$status"
}
'''


def _final_readiness_audit_script() -> str:
    return r'''#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'final readiness audit failed: %s\n' "$*" >&2
  exit 2
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

files=()
for path in \
  design/visual-validation-report.md \
  release/initial-preview-validation-report.json \
  release/release-output-template.md \
  docs/workbench.md
do
  [[ -f "$path" ]] && files+=("$path")
done
while IFS= read -r path; do
  files+=("$path")
done < <(find specs -path '*/tasks.md' -type f 2>/dev/null | sort)
while IFS= read -r path; do
  files+=("$path")
done < <(find architecture -type f \( -name '*.md' -o -name '*.mmd' -o -name '*.yaml' -o -name '*.yml' \) 2>/dev/null | sort)

(( ${#files[@]} > 0 )) || fail "no readiness audit files found"

if grep -InE 'TODO|TBD|FIXME' "${files[@]}" >/tmp/project-factory-readiness-todos.txt; then
  if ! grep -InE 'TODO\(justified\)|TODO: justified|justified TODO' "${files[@]}" >/dev/null; then
    cat /tmp/project-factory-readiness-todos.txt >&2
    fail "unjustified TODO/TBD/FIXME markers remain"
  fi
fi

forbidden_patterns=(
  'D1 blocked'
  'domains endpoint'
  '/api/''domain/'
  '/admin/''domains'
  '/domain/''smoke_records'
  '/''domains'
  'domain ''CRUD'
  'domain-''management'
  'domain ''management'
  'domain ''UX'
  'domain-''specific resources'
  'domain-''specific workflows'
  'Domain ''features'
  'api --> ''domain'
  'domain --> ''db'
  'domain''['
  'preview_''domain_'
  'handlePreview''Domain'
  '0002_''domain_entities'
  'android-mock-v'
  'android-local-v'
  'mock_or_demo: true'
  'mockOrDemo: true'
  'LOCAL_DEMO_MODE=true'
  'runtime_profile: mock'
)

for pattern in "${forbidden_patterns[@]}"; do
  if grep -Ini "$pattern" "${files[@]}" >/tmp/project-factory-readiness-match.txt; then
    cat /tmp/project-factory-readiness-match.txt >&2
    fail "stale or forbidden readiness text found: $pattern"
  fi
done

if grep -InE '\b[0-9a-f]{7,39}\b' "${files[@]}" >/tmp/project-factory-ambiguous-commits.txt; then
  cat /tmp/project-factory-ambiguous-commits.txt >&2
  fail "ambiguous short commit hashes found; use full 40-character fields"
fi

grep -q 'validated_source_commit:' release/release-output-template.md || fail "release output missing validated_source_commit"
grep -q 'report_generated_from_commit:' release/release-output-template.md || fail "release output missing report_generated_from_commit"

printf 'final readiness audit passed\n'
'''


def _apply_cloudflare_preview_script(slug: str) -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail

fail() {{
  printf 'cloudflare preview apply blocked: %s\\n' "$*" >&2
  exit 2
}}

ROOT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
cd "$ROOT_DIR"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/load_bridge_env.sh"
source "$ROOT_DIR/scripts/github_repo_access.sh"

[[ -f deploy/web-preview/web-preview-manifest.yaml ]] || fail "missing deploy/web-preview/web-preview-manifest.yaml"
[[ -f deploy/web-preview/worker/src/index.js ]] || fail "missing Preview API Worker"
[[ -f deploy/web-preview/d1/migrations/0001_preview_invites.sql ]] || fail "missing D1 migration"
[[ -f deploy/web-preview/d1/migrations/0002_business_records.sql ]] || fail "missing business records D1 migration"
bridge_env_require APP_RUNTIME_PROFILE API_RUNTIME API_BASE_URL BRIDGE_URL CLOUDFLARE_API_TOKEN
bridge_env_require_any "preview D1 database" PREVIEW_D1_DATABASE CLOUDFLARE_D1_DATABASE
[[ "$APP_RUNTIME_PROFILE" == "preview" ]] || fail "APP_RUNTIME_PROFILE must be preview for initial release"
[[ "$API_RUNTIME" == "cloudflare_preview" ]] || fail "API_RUNTIME must be cloudflare_preview"

BRIDGE_URL="${{BRIDGE_URL}}"
BRIDGE_URL="${{BRIDGE_URL%/}}"
SOURCE_APP="${{SOURCE_APP:-{slug}}}"
[[ "${{API_BASE_URL%/}}" == "https://preview.nienfos.com/$SOURCE_APP/api" ]] || \\
  fail "API_BASE_URL must be https://preview.nienfos.com/$SOURCE_APP/api"
export BRIDGE_URL SOURCE_APP PROJECT_PATH="${{PROJECT_PATH:-$ROOT_DIR}}"

scripts/validate_web_preview.sh
scripts/validate_cloudflare_cost_posture.sh
scripts/apply_preview_d1_migrations.sh

plan_json="$(BRIDGE_URL="$BRIDGE_URL" SOURCE_APP="$SOURCE_APP" PROJECT_PATH="$PROJECT_PATH" scripts/deploy_web_preview.sh --plan)"
printf '%s\\n' "$plan_json" > /tmp/project-factory-cloudflare-preview-plan.json
EXPECTED_PLAN_HASH="${{EXPECTED_PLAN_HASH:-$(python3 - <<'PY'
from __future__ import annotations

import json
from pathlib import Path

payload = json.loads(Path("/tmp/project-factory-cloudflare-preview-plan.json").read_text())
print(payload.get("planHash") or payload.get("plan_hash") or payload.get("hash") or "")
PY
)}}"
[[ -n "$EXPECTED_PLAN_HASH" ]] || fail "Bridge plan did not include planHash"

CONFIRM_APPLY="${{CONFIRM_APPLY:-true}}" \\
EXPECTED_PLAN_HASH="$EXPECTED_PLAN_HASH" \\
BRIDGE_URL="$BRIDGE_URL" \\
SOURCE_APP="$SOURCE_APP" \\
PROJECT_PATH="$PROJECT_PATH" \\
scripts/deploy_web_preview.sh --apply > /tmp/project-factory-cloudflare-preview-apply.json

python3 - <<'PY'
from __future__ import annotations

import json
from pathlib import Path

payload = json.loads(Path("/tmp/project-factory-cloudflare-preview-apply.json").read_text())
status = str(payload.get("status") or payload.get("state") or "").lower()
if status and status not in {{"ready", "active", "applied", "deployed", "ok"}}:
    raise SystemExit(f"Cloudflare preview apply returned non-ready status: {{status}}")
recovery_status = payload.get("recoveryStatus") or payload.get("recovery_status")
if recovery_status:
    print(f"cloudflare preview recovery: {{recovery_status}}")
print("cloudflare preview apply completed")
PY

scripts/smoke_web_preview.sh
scripts/smoke_preview_api.sh
'''


def _apply_preview_d1_migrations_script() -> str:
    return r'''#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'preview D1 migration apply blocked: %s\n' "$*" >&2
  exit 2
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIGRATIONS_DIR="$ROOT_DIR/deploy/web-preview/d1/migrations"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/load_bridge_env.sh"
DATABASE="${PREVIEW_D1_DATABASE:-${CLOUDFLARE_D1_DATABASE:-}}"

[[ -d "$MIGRATIONS_DIR" ]] || fail "missing deploy/web-preview/d1/migrations"
bridge_env_require_any "preview D1 database" PREVIEW_D1_DATABASE CLOUDFLARE_D1_DATABASE
command -v wrangler >/dev/null 2>&1 || fail "wrangler is required to apply D1 migrations"
if [[ -z "${CLOUDFLARE_API_TOKEN:-}" && "${WRANGLER_AUTH_READY:-false}" != "true" ]]; then
  fail "set CLOUDFLARE_API_TOKEN or WRANGLER_AUTH_READY=true"
fi
# Migration execution is delegated to Python so it can run wrangler d1 execute
# PRAGMA checks before idempotent ALTER TABLE ADD COLUMN directives.

shopt -s nullglob
migrations=("$MIGRATIONS_DIR"/*.sql)
(( ${#migrations[@]} > 0 )) || fail "no D1 migration files found"

for migration in "${migrations[@]}"; do
  printf 'applying preview D1 migration: %s\n' "${migration#$ROOT_DIR/}"
  python3 - "$DATABASE" "$migration" <<'PY'
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

database, migration_path = sys.argv[1:3]
path = Path(migration_path)
content = path.read_text(encoding="utf-8")

def run_wrangler(args: list[str]) -> str:
    completed = subprocess.run(
        ["wrangler", "d1", "execute", database, "--remote", *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout

column_cache: dict[str, set[str]] = {}

def table_columns(table: str) -> set[str]:
    if table in column_cache:
        return column_cache[table]
    raw = run_wrangler(["--command", f"PRAGMA table_info({table})", "--json"])
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Could not parse wrangler JSON for PRAGMA table_info({table})") from exc
    rows = payload
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        rows = payload[0].get("results") or payload[0].get("result") or payload
    if isinstance(payload, dict):
        rows = payload.get("results") or payload.get("result") or []
    column_cache[table] = {str(row.get("name")) for row in rows if isinstance(row, dict) and row.get("name")}
    return column_cache[table]

directive_re = re.compile(r"^\s*--\s*codex:d1:(add-column|backfill)\s+(.+?)\s*$")
for line in content.splitlines():
    match = directive_re.match(line)
    if not match:
        continue
    action, payload = match.groups()
    if action == "add-column":
        parts = payload.split(None, 2)
        if len(parts) != 3:
            raise SystemExit(f"Invalid add-column directive in {path.name}: {payload}")
        table, column, definition = parts
        if column in table_columns(table):
            print(f"skipping existing D1 column: {table}.{column}")
            continue
        run_wrangler(["--command", f"ALTER TABLE {table} ADD COLUMN {column} {definition}"])
        table_columns(table).add(column)
        print(f"added D1 column: {table}.{column}")
    elif action == "backfill":
        parts = payload.split(None, 3)
        if len(parts) != 4:
            raise SystemExit(f"Invalid backfill directive in {path.name}: {payload}")
        table, column, value, predicate = parts
        if column not in table_columns(table):
            raise SystemExit(f"Cannot backfill missing D1 column: {table}.{column}")
        run_wrangler(["--command", f"UPDATE {table} SET {column} = {value} WHERE {predicate}"])
        print(f"backfilled D1 column: {table}.{column}")

sql_without_directives = "\n".join(
    line for line in content.splitlines() if not directive_re.match(line)
).strip()
if sql_without_directives:
    run_wrangler(["--file", str(path)])
PY
done

printf 'preview D1 migrations applied: %s\n' "$DATABASE"
'''


def _smoke_preview_api_script(slug: str) -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail

fail() {{
  printf 'preview api smoke failed: %s\\n' "$*" >&2
  exit 2
}}

SOURCE_APP="${{SOURCE_APP:-{slug}}}"
ROOT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/load_bridge_env.sh"
PREVIEW_API_BASE_URL="${{PREVIEW_API_BASE_URL:-${{API_BASE_URL:-https://preview.nienfos.com/$SOURCE_APP/api}}}}"
PREVIEW_API_BASE_URL="${{PREVIEW_API_BASE_URL%/}}"
USER_AGENT="${{PREVIEW_SMOKE_USER_AGENT:-CodexProjectFactoryPreviewSmoke/1.0}}"

[[ "$PREVIEW_API_BASE_URL" == "https://preview.nienfos.com/$SOURCE_APP/api" ]] || \\
  fail "PREVIEW_API_BASE_URL must be https://preview.nienfos.com/$SOURCE_APP/api"
bridge_env_require PREVIEW_ADMIN_PASSWORD

python3 - "$PREVIEW_API_BASE_URL" "$SOURCE_APP" "$USER_AGENT" <<'PY'
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

base_url, source_app, user_agent = sys.argv[1:4]
email = os.environ.get("PREVIEW_ADMIN_EMAIL", "admin.preview@example.com")
password = os.environ.get("PREVIEW_ADMIN_PASSWORD", "")
bootstrap_token = os.environ.get("PREVIEW_ADMIN_BOOTSTRAP_TOKEN", "")

def request(method: str, path: str, payload: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    headers = {{"content-type": "application/json", "user-agent": user_agent}}
    if token:
        headers["authorization"] = f"Bearer {{token}}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base_url + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else {{}}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            body = json.loads(raw)
        except Exception:
            body = {{"raw": raw}}
        return exc.code, body

def retry_request(method: str, path: str, payload: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    last: tuple[int, dict] = (0, {{"error": "not attempted"}})
    for delay in (0.5, 1.0, 2.0, 3.0):
        last = request(method, path, payload, token)
        status, body = last
        if status < 500 and status != 0:
            return last
        time.sleep(delay)
    return last

status, health = retry_request("GET", "/health")
if status != 200 or health.get("runtime") != "cloudflare_preview" or health.get("source_app") != source_app:
    raise SystemExit(f"health failed: {{status}} {{health}}")
if not health.get("d1_bound"):
    raise SystemExit("health did not report d1_bound=true")
if not health.get("assets_bound"):
    raise SystemExit("health did not report assets_bound=true")

if not password:
    raise SystemExit("PREVIEW_ADMIN_PASSWORD is required for deployed auth smoke")

if bootstrap_token:
    status, bootstrap = request(
        "POST",
        "/admin/bootstrap",
        {{"bootstrapToken": bootstrap_token, "email": email, "password": password}},
    )
    if status not in (200, 409):
        raise SystemExit(f"bootstrap failed: {{status}} {{bootstrap}}")

status, login = request("POST", "/auth/login", {{"email": email, "password": password}})
if status != 200 or not login.get("access_token"):
    raise SystemExit(f"login failed: {{status}} {{login}}")
token = login["access_token"]

status, me = request("GET", "/auth/me", token=token)
if status != 200 or me.get("sourceApp") != source_app:
    raise SystemExit(f"me failed: {{status}} {{me}}")

status, created = request("POST", "/business/records", {{"name": "preview-smoke"}}, token=token)
if status != 201 or created.get("sourceApp") != source_app:
    raise SystemExit(f"business record create failed: {{status}} {{created}}")

status, listed = request("GET", "/business/records", token=token)
if status != 200 or not listed.get("records"):
    raise SystemExit(f"business record list failed: {{status}} {{listed}}")
if any(row.get("sourceApp") != source_app or row.get("appSlug") != source_app for row in listed["records"]):
    raise SystemExit("business record list returned cross-app records")

status, notifications = request("GET", "/notifications", token=token)
if status != 200 or "notifications" not in notifications:
    raise SystemExit(f"notifications failed: {{status}} {{notifications}}")

status, updates = request("GET", "/app-updates/current")
if status != 200 or updates.get("releaseChannel") != "prerelease" or updates.get("mockOrDemo") is not False:
    raise SystemExit(f"app update metadata failed: {{status}} {{updates}}")

print(f"preview api smoke passed: {{base_url}}")
PY
'''


def _smoke_web_preview_script(slug: str) -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail

fail() {{
  printf 'web preview smoke failed: %s\\n' "$*" >&2
  exit 2
}}

SOURCE_APP="${{SOURCE_APP:-{slug}}}"
ROOT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/load_bridge_env.sh"
PREVIEW_URL="${{PREVIEW_URL:-https://preview.nienfos.com/$SOURCE_APP}}"
PREVIEW_URL="${{PREVIEW_URL%/}}"
USER_AGENT="${{PREVIEW_SMOKE_USER_AGENT:-CodexProjectFactoryPreviewSmoke/1.0}}"

[[ "$PREVIEW_URL" == "https://preview.nienfos.com/$SOURCE_APP" ]] || \\
  fail "PREVIEW_URL must be https://preview.nienfos.com/$SOURCE_APP"

python3 - "$PREVIEW_URL" "$SOURCE_APP" "$USER_AGENT" <<'PY'
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

preview_url, source_app, user_agent = sys.argv[1:4]

def get_json(path: str) -> tuple[int, dict]:
    request = urllib.request.Request(
        preview_url + path,
        headers={{"user-agent": user_agent, "accept": "application/json"}},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else {{}}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            body = json.loads(raw)
        except Exception:
            body = {{"raw": raw}}
        return exc.code, body

def retry_get_json(path: str) -> tuple[int, dict]:
    last: tuple[int, dict] = (0, {{"error": "not attempted"}})
    for delay in (0.5, 1.0, 2.0, 3.0):
        last = get_json(path)
        status, body = last
        if status == 200 and body.get("runtime") == "cloudflare_preview":
            return last
        time.sleep(delay)
    return last

status, web_health = retry_get_json("/__preview/health")
if status != 200 or web_health.get("source_app") != source_app:
    raise SystemExit(f"web preview health failed: {{status}} {{web_health}}")
if web_health.get("runtime") != "cloudflare_preview":
    raise SystemExit(f"web preview runtime mismatch: {{web_health}}")
if web_health.get("d1_bound") is not True:
    raise SystemExit(f"web preview health did not report d1_bound=true: {{web_health}}")
if web_health.get("assets_bound") is not True:
    raise SystemExit(f"web preview health did not report assets_bound=true: {{web_health}}")

status, api_health = retry_get_json("/api/health")
if status != 200 or api_health.get("source_app") != source_app:
    raise SystemExit(f"Preview API health failed: {{status}} {{api_health}}")
if api_health.get("runtime") != "cloudflare_preview":
    raise SystemExit(f"Preview API runtime mismatch: {{api_health}}")
if api_health.get("d1_bound") is not True:
    raise SystemExit(f"Preview API health did not report d1_bound=true: {{api_health}}")
if api_health.get("assets_bound") is not True:
    raise SystemExit(f"Preview API health did not report assets_bound=true: {{api_health}}")

print(f"web preview smoke passed: {{preview_url}}")
PY
'''


def _publish_android_preview_release_script(slug: str) -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
cd "$ROOT_DIR"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/load_bridge_env.sh"
source "$ROOT_DIR/scripts/github_repo_access.sh"

fail_blocked() {{
  printf 'android preview release blocked: %s\\n' "$*" >&2
  exit 2
}}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --push)
      shift
      ;;
    --watch)
      WAIT_FOR_ANDROID_RELEASE=true
      shift
      ;;
    --no-watch)
      WAIT_FOR_ANDROID_RELEASE=false
      shift
      ;;
    *)
      fail_blocked "unknown argument: $1"
      ;;
  esac
done

SOURCE_APP="${{SOURCE_APP:-{slug}}}"
PREVIEW_API_BASE_URL="${{PREVIEW_API_BASE_URL:-${{API_BASE_URL:-https://preview.nienfos.com/$SOURCE_APP/api}}}}"
PREVIEW_API_BASE_URL="${{PREVIEW_API_BASE_URL%/}}"

[[ -f apps/mobile/pubspec.yaml ]] || fail_blocked "apps/mobile/pubspec.yaml is required"
[[ -d apps/mobile/android ]] || fail_blocked "apps/mobile/android is required; run 'cd apps/mobile && flutter create --platforms=android .'"
bridge_env_require APP_RUNTIME_PROFILE API_RUNTIME API_BASE_URL
[[ "$PREVIEW_API_BASE_URL" == "https://preview.nienfos.com/$SOURCE_APP/api" ]] || \\
  fail_blocked "initial preview API must be https://preview.nienfos.com/$SOURCE_APP/api"
[[ "$APP_RUNTIME_PROFILE" == "preview" ]] || fail_blocked "APP_RUNTIME_PROFILE must be preview"
[[ "$API_RUNTIME" == "cloudflare_preview" ]] || fail_blocked "API_RUNTIME must be cloudflare_preview"
[[ "${{API_BASE_URL%/}}" == "$PREVIEW_API_BASE_URL" ]] || fail_blocked "API_BASE_URL must match preview API"
bridge_env_load_preview_signing || fail_blocked "stable Android preview signing is required"
cp "$ANDROID_KEYSTORE_PATH" apps/mobile/android/upload-keystore.jks
cat > apps/mobile/android/key.properties <<EOF
storeFile=upload-keystore.jks
storePassword=$ANDROID_STORE_PASSWORD
keyPassword=$ANDROID_KEY_PASSWORD
keyAlias=$ANDROID_KEY_ALIAS
storeType=${{ANDROID_STORE_TYPE:-JKS}}
EOF

scripts/smoke_preview_api.sh

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail_blocked "not inside a git repository"
git rev-parse --verify HEAD >/dev/null 2>&1 || fail_blocked "no git commit exists"
if [[ -n "$(git status --porcelain)" ]]; then
  git status --short >&2
  fail_blocked "working tree must be clean before tagging the preview release"
fi

origin_url="$(git remote get-url origin 2>/dev/null || true)"
[[ -n "$origin_url" ]] || fail_blocked "origin remote is not configured"
repo_ref="$origin_url"
repo_ref="${{repo_ref#https://github.com/}}"
repo_ref="${{repo_ref#git@github.com:}}"
repo_ref="${{repo_ref%.git}}"
[[ "$repo_ref" == */* ]] || fail_blocked "origin remote must point to a GitHub owner/repo"
github_require_repo_access "$repo_ref" || fail_blocked "GitHub repository is not accessible with authenticated tools"

if command -v gh >/dev/null 2>&1 && [[ "${{SKIP_GITHUB_API_BASE_URL_VAR_CHECK:-false}}" != "true" ]]; then
  workflow_api_base_url="$(
    gh variable list --repo "$repo_ref" --json name,value --jq '.[] | select(.name == "API_BASE_URL") | .value' 2>/dev/null || true
  )"
  [[ -n "$workflow_api_base_url" ]] || fail_blocked "GitHub Actions variable API_BASE_URL is not configured for $repo_ref"
  [[ "${{workflow_api_base_url%/}}" == "$PREVIEW_API_BASE_URL" ]] || \\
    fail_blocked "GitHub Actions variable API_BASE_URL does not match the preview API"
fi

branch="$(git symbolic-ref --short HEAD 2>/dev/null || true)"
[[ -n "$branch" ]] || fail_blocked "HEAD is detached; release from a named branch"
upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{{u}}' 2>/dev/null || true)"
[[ -n "$upstream" ]] || fail_blocked "current branch has no upstream"
local_head="$(git rev-parse HEAD)"
remote_head="$(git rev-parse "$upstream" 2>/dev/null || true)"
[[ "$local_head" == "$remote_head" ]] || fail_blocked "local HEAD is not pushed to $upstream"

version="$(awk '/^version:/ {{ print $2; exit }}' apps/mobile/pubspec.yaml)"
[[ -n "$version" ]] || fail_blocked "apps/mobile/pubspec.yaml has no version"
tag="${{APP_ANDROID_PREVIEW_RELEASE_TAG:-android-preview-v${{version//+/-build.}}}}"

APP_RELEASE_TAG="$tag" \\
APP_RUNTIME_PROFILE=preview \\
API_RUNTIME=cloudflare_preview \\
APP_SLUG="$SOURCE_APP" \\
API_BASE_URL="$PREVIEW_API_BASE_URL" \\
scripts/validate_preview_release_profiles.sh

if git rev-parse --verify "refs/tags/$tag" >/dev/null 2>&1; then
  tag_commit="$(git rev-list -n 1 "$tag")"
  [[ "$tag_commit" == "$local_head" ]] || fail_blocked "existing tag $tag does not point at HEAD"
else
  git tag "$tag"
fi

git push origin "$tag"

if [[ "${{WAIT_FOR_ANDROID_RELEASE:-true}}" != "true" ]]; then
  printf 'android preview release tag pushed: %s\\n' "$tag"
  exit 0
fi

command -v gh >/dev/null 2>&1 || fail_blocked "gh is required to verify GitHub release assets"
timeout="${{ANDROID_RELEASE_TIMEOUT_SECONDS:-1800}}"
poll="${{ANDROID_RELEASE_POLL_SECONDS:-15}}"
deadline=$((SECONDS + timeout))
while (( SECONDS <= deadline )); do
  assets="$(gh release view "$tag" --repo "$repo_ref" --json assets --jq '.assets[].name' 2>/dev/null || true)"
  if printf '%s\\n' "$assets" | grep -Fx "${{SOURCE_APP}}.apk" >/dev/null; then
    bridge_env_require BRIDGE_URL INSTALLABLE_APPS_REGISTRATION_TOKEN
    APP_RELEASE_TAG="$tag" \\
    BRIDGE_REGISTRATION_TOKEN="$INSTALLABLE_APPS_REGISTRATION_TOKEN" \\
    scripts/register_installable_app.sh
    printf 'android preview release completed: %s\\n' "$tag"
    printf '%s\\n' "$assets"
    exit 0
  fi
  sleep "$poll"
done

fail_blocked "GitHub release $tag did not expose $SOURCE_APP.apk within ${{timeout}}s"
'''


def _publish_android_release_script() -> str:
    return r'''#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/github_repo_access.sh"

fail_blocked() {
  printf 'android release blocked: %s\n' "$*" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --push)
      shift
      ;;
    --watch)
      WAIT_FOR_ANDROID_RELEASE=true
      shift
      ;;
    --no-watch)
      WAIT_FOR_ANDROID_RELEASE=false
      shift
      ;;
    *)
      fail_blocked "unknown argument: $1"
      ;;
  esac
done

[[ -f apps/mobile/pubspec.yaml ]] || fail_blocked "apps/mobile/pubspec.yaml is required"
[[ -d apps/mobile/android ]] || fail_blocked "apps/mobile/android is required; run 'cd apps/mobile && flutter create --platforms=android .'"
[[ -n "${API_BASE_URL:-}" ]] || fail_blocked "API_BASE_URL is required for a real Android release"
[[ "${API_BASE_URL:-}" != *localhost* && "${API_BASE_URL:-}" != *127.0.0.1* && "${API_BASE_URL:-}" != *10.0.2.2* ]] || \
  fail_blocked "API_BASE_URL must not point at a local backend"
[[ "${APP_RUNTIME_PROFILE:-real}" != "mock" ]] || fail_blocked "real Android release cannot use APP_RUNTIME_PROFILE=mock"

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail_blocked "not inside a git repository"
git rev-parse --verify HEAD >/dev/null 2>&1 || fail_blocked "no git commit exists"

if [[ -n "$(git status --porcelain)" ]]; then
  git status --short >&2
  fail_blocked "working tree must be clean before tagging the release"
fi

origin_url="$(git remote get-url origin 2>/dev/null || true)"
[[ -n "$origin_url" ]] || fail_blocked "origin remote is not configured"
repo_ref="$origin_url"
repo_ref="${repo_ref#https://github.com/}"
repo_ref="${repo_ref#git@github.com:}"
repo_ref="${repo_ref%.git}"
[[ "$repo_ref" == */* ]] || fail_blocked "origin remote must point to a GitHub owner/repo"
github_require_repo_access "$repo_ref" || fail_blocked "GitHub repository is not accessible with authenticated tools"

if command -v gh >/dev/null 2>&1 && [[ "${SKIP_GITHUB_API_BASE_URL_VAR_CHECK:-false}" != "true" ]]; then
  workflow_api_base_url="$(
    gh variable list --repo "$repo_ref" --json name,value --jq '.[] | select(.name == "API_BASE_URL") | .value' 2>/dev/null || true
  )"
  [[ -n "$workflow_api_base_url" ]] || fail_blocked "GitHub Actions variable API_BASE_URL is not configured for $repo_ref"
  [[ "${workflow_api_base_url%/}" == "${API_BASE_URL%/}" ]] || \
    fail_blocked "GitHub Actions variable API_BASE_URL does not match the requested API_BASE_URL"
fi

branch="$(git symbolic-ref --short HEAD 2>/dev/null || true)"
[[ -n "$branch" ]] || fail_blocked "HEAD is detached; release from a named branch"
upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
[[ -n "$upstream" ]] || fail_blocked "current branch has no upstream"
local_head="$(git rev-parse HEAD)"
remote_head="$(git rev-parse "$upstream" 2>/dev/null || true)"
[[ "$local_head" == "$remote_head" ]] || fail_blocked "local HEAD is not pushed to $upstream"

version="$(awk '/^version:/ { print $2; exit }' apps/mobile/pubspec.yaml)"
[[ -n "$version" ]] || fail_blocked "apps/mobile/pubspec.yaml has no version"
tag="${APP_ANDROID_RELEASE_TAG:-android-v${version//+/-build.}}"

APP_RELEASE_TAG="$tag" \
APP_RUNTIME_PROFILE="${APP_RUNTIME_PROFILE:-real}" \
API_BASE_URL="$API_BASE_URL" \
scripts/validate_release_profiles.sh

if git rev-parse --verify "refs/tags/$tag" >/dev/null 2>&1; then
  tag_commit="$(git rev-list -n 1 "$tag")"
  [[ "$tag_commit" == "$local_head" ]] || fail_blocked "existing tag $tag does not point at HEAD"
else
  git tag "$tag"
fi

git push origin "$tag"

if [[ "${WAIT_FOR_ANDROID_RELEASE:-true}" != "true" ]]; then
  printf 'android release tag pushed: %s\n' "$tag"
  exit 0
fi

if ! command -v gh >/dev/null 2>&1; then
  fail_blocked "gh is required to verify GitHub release assets"
fi

timeout="${ANDROID_RELEASE_TIMEOUT_SECONDS:-1800}"
poll="${ANDROID_RELEASE_POLL_SECONDS:-15}"
deadline=$((SECONDS + timeout))
while (( SECONDS <= deadline )); do
  assets="$(gh release view "$tag" --repo "$repo_ref" --json assets --jq '.assets[].name' 2>/dev/null || true)"
  if printf '%s\n' "$assets" | grep -Eq '\.apk$'; then
    printf 'android release completed: %s\n' "$tag"
    printf '%s\n' "$assets"
    exit 0
  fi
  sleep "$poll"
done

fail_blocked "GitHub release $tag did not expose an APK asset within ${timeout}s"
'''


def _publication_validation_script() -> str:
    return r'''#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'publication validation failed: %s\n' "$*" >&2
  exit 1
}

mode="${PUBLICATION_VALIDATION_MODE:-remote}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/github_repo_access.sh"

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "not inside a git repository"
git rev-parse --verify HEAD >/dev/null 2>&1 || fail "no git commit exists"

if [[ -n "$(git status --porcelain)" ]]; then
  git status --short >&2
  fail "working tree has uncommitted or untracked files"
fi

if [[ "$mode" == "local" ]]; then
  printf 'publication validation completed: local commit ready; remote publish not required in this mode\n'
  exit 0
fi

[[ "$mode" == "remote" ]] || fail "unsupported PUBLICATION_VALIDATION_MODE=$mode"

origin_url="$(git remote get-url origin 2>/dev/null || true)"
[[ -n "$origin_url" ]] || fail "origin remote is not configured"
repo_ref="$origin_url"
repo_ref="${repo_ref#https://github.com/}"
repo_ref="${repo_ref#git@github.com:}"
repo_ref="${repo_ref%.git}"
github_require_repo_access "$repo_ref" || fail "GitHub repository is not accessible with authenticated tools"

branch="$(git symbolic-ref --short HEAD 2>/dev/null || true)"
[[ -n "$branch" ]] || fail "HEAD is detached; publish from a named branch"

upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
[[ -n "$upstream" ]] || fail "current branch has no upstream"

git fetch --quiet origin "$branch" || fail "could not fetch origin/$branch"
local_head="$(git rev-parse HEAD)"
remote_head="$(git rev-parse "$upstream" 2>/dev/null || true)"
[[ "$local_head" == "$remote_head" ]] || fail "local HEAD is not pushed to $upstream"

if [[ -x "$ROOT_DIR/scripts/validate_initial_preview_release.sh" ]]; then
  "$ROOT_DIR/scripts/validate_initial_preview_release.sh"
  printf 'publication validation completed: initial preview release ready\n'
  exit 0
fi

if [[ -f apps/mobile/pubspec.yaml ]]; then
  [[ -d apps/mobile/android ]] || fail "missing apps/mobile/android; Android APK release cannot build"
  version="$(awk '/^version:/ { print $2; exit }' apps/mobile/pubspec.yaml)"
  [[ -n "$version" ]] || fail "apps/mobile/pubspec.yaml has no version"
  expected_tag="${APP_ANDROID_RELEASE_TAG:-android-v${version//+/-build.}}"
  APP_RELEASE_TAG="$expected_tag" \
    APP_RUNTIME_PROFILE="${APP_RUNTIME_PROFILE:-real}" \
    API_BASE_URL="${API_BASE_URL:-}" \
    "$ROOT_DIR/scripts/validate_release_profiles.sh"
  git rev-parse --verify "refs/tags/$expected_tag" >/dev/null 2>&1 || fail "missing Android release tag $expected_tag"
  tag_commit="$(git rev-list -n 1 "$expected_tag")"
  [[ "$tag_commit" == "$local_head" ]] || fail "Android release tag $expected_tag does not point at HEAD"
  git ls-remote --exit-code --tags origin "$expected_tag" >/dev/null 2>&1 || fail "Android release tag $expected_tag is not pushed"

  if ! command -v gh >/dev/null 2>&1; then
    fail "gh is required to verify Android APK release assets"
  fi
  assets="$(gh release view "$expected_tag" --repo "$repo_ref" --json assets --jq '.assets[].name' 2>/dev/null || true)"
  [[ -n "$assets" ]] || fail "GitHub release $expected_tag is missing or has no assets"
  printf '%s\n' "$assets" | grep -Eq '\.apk$' || fail "GitHub release $expected_tag has no APK asset"
fi

printf 'publication validation completed\n'
'''


def _preview_release_profile_validation_script(
    slug: str,
    frontend_strategy: str = "flutter",
) -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail

fail() {{
  printf 'preview release profile validation failed: %s\\n' "$*" >&2
  exit 1
}}

ROOT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
cd "$ROOT_DIR"
FRONTEND_STRATEGY="{frontend_strategy}"

RUNTIME_CONTRACT="$ROOT_DIR/release/preview-runtime.json"
WEB_PREVIEW_MANIFEST="$ROOT_DIR/deploy/web-preview/web-preview-manifest.yaml"
SIGNING_POLICY="$ROOT_DIR/release/preview-signing-policy.json"
PROJECT_MANIFEST="$ROOT_DIR/.codex/project.yaml"
RELEASE_CONTRACTS="$ROOT_DIR/release/release-contracts.yaml"
BACKEND_CONFIG="$ROOT_DIR/backend/app/config.py"
FLUTTER_CONFIG="$ROOT_DIR/apps/mobile/lib/src/config.dart"
ANDROID_MANIFEST="$ROOT_DIR/apps/mobile/android/app/src/main/AndroidManifest.xml"
ANDROID_PREVIEW_WORKFLOW="$ROOT_DIR/.github/workflows/android-preview-release.yml"
[[ -f "$RUNTIME_CONTRACT" ]] || fail "missing release/preview-runtime.json"
[[ -f "$WEB_PREVIEW_MANIFEST" ]] || fail "missing deploy/web-preview/web-preview-manifest.yaml"
[[ -f "$SIGNING_POLICY" ]] || fail "missing release/preview-signing-policy.json"
[[ -f "$PROJECT_MANIFEST" ]] || fail "missing .codex/project.yaml"
[[ -f "$RELEASE_CONTRACTS" ]] || fail "missing release/release-contracts.yaml"
[[ -f "$BACKEND_CONFIG" ]] || fail "missing backend/app/config.py"
if [[ "$FRONTEND_STRATEGY" == "flutter" ]]; then
  [[ -f "$FLUTTER_CONFIG" ]] || fail "missing apps/mobile/lib/src/config.dart"
  [[ -f "$ANDROID_MANIFEST" ]] || fail "missing apps/mobile/android/app/src/main/AndroidManifest.xml"
  [[ -f "$ANDROID_PREVIEW_WORKFLOW" ]] || fail "missing .github/workflows/android-preview-release.yml"
else
  [[ -f "$ROOT_DIR/apps/web/package.json" ]] || fail "missing apps/web/package.json"
  [[ -f "$ROOT_DIR/apps/web/src/config.ts" ]] || fail "missing apps/web/src/config.ts"
  [[ ! -f "$ANDROID_PREVIEW_WORKFLOW" ]] || fail "Svelte strategy must not generate Android preview workflow without wrapper support"
  [[ ! -f "$ROOT_DIR/scripts/register_installable_app.sh" ]] || fail "Svelte strategy must not generate Bridge installable registration without wrapper support"
fi

python3 - "$RUNTIME_CONTRACT" "$WEB_PREVIEW_MANIFEST" "$PROJECT_MANIFEST" "$RELEASE_CONTRACTS" "{slug}" "$FRONTEND_STRATEGY" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError as exc:
    raise SystemExit("PyYAML is required to validate web-preview-manifest.yaml") from exc

runtime_path, manifest_path, project_manifest_path, release_contracts_path, expected_slug, frontend_strategy = sys.argv[1:7]
runtime = json.loads(Path(runtime_path).read_text(encoding="utf-8"))
manifest = yaml.safe_load(Path(manifest_path).read_text(encoding="utf-8"))
project_manifest = yaml.safe_load(Path(project_manifest_path).read_text(encoding="utf-8"))
release_contracts = yaml.safe_load(Path(release_contracts_path).read_text(encoding="utf-8"))
if not isinstance(runtime, dict):
    raise SystemExit("release/preview-runtime.json must be a JSON object")
if not isinstance(manifest, dict):
    raise SystemExit("web-preview-manifest.yaml must be a YAML object")
if not isinstance(project_manifest, dict):
    raise SystemExit(".codex/project.yaml must be a YAML object")
if not isinstance(release_contracts, dict):
    raise SystemExit("release/release-contracts.yaml must be a YAML object")
manifest_runtime = manifest.get("runtime") if isinstance(manifest.get("runtime"), dict) else {{}}
first_release = manifest.get("first_release") if isinstance(manifest.get("first_release"), dict) else {{}}
project_profiles = project_manifest.get("runtime_profiles") if isinstance(project_manifest.get("runtime_profiles"), dict) else {{}}
release_profiles = release_contracts.get("runtime_profiles") if isinstance(release_contracts.get("runtime_profiles"), dict) else {{}}
project_frontend = project_manifest.get("frontend") if isinstance(project_manifest.get("frontend"), dict) else {{}}
checks = (
    ("sourceApp", runtime.get("sourceApp"), expected_slug),
    ("previewUrl", runtime.get("previewUrl"), f"https://preview.nienfos.com/{{expected_slug}}"),
    ("apiBaseUrl", runtime.get("apiBaseUrl"), f"https://preview.nienfos.com/{{expected_slug}}/api"),
    ("runtimeProfile", runtime.get("runtimeProfile"), "preview"),
    ("apiRuntime", runtime.get("apiRuntime"), "cloudflare_preview"),
    ("releaseChannel", runtime.get("releaseChannel"), "prerelease"),
    ("productionReady", runtime.get("productionReady"), False),
    ("mockOrDemo", runtime.get("mockOrDemo"), False),
    ("frontendStrategy", runtime.get("frontendStrategy"), frontend_strategy),
    ("manifest.frontend_strategy", manifest.get("frontend_strategy"), frontend_strategy),
    ("project.frontend.strategy", project_frontend.get("strategy"), frontend_strategy),
    ("manifest.source_app", manifest.get("source_app"), expected_slug),
    ("manifest.stable_url", manifest.get("stable_url"), runtime.get("previewUrl")),
    ("manifest.runtime.api_base_url", manifest_runtime.get("api_base_url"), runtime.get("apiBaseUrl")),
    ("manifest.runtime.default_profile", manifest_runtime.get("default_profile"), runtime.get("runtimeProfile")),
    ("manifest.runtime.api_runtime", manifest_runtime.get("api_runtime"), runtime.get("apiRuntime")),
    ("manifest.first_release.mode", first_release.get("mode"), "preview"),
    ("manifest.first_release.android_release_channel", first_release.get("android_release_channel"), runtime.get("releaseChannel")),
    ("project.runtime_profiles.default_profile", project_profiles.get("default_profile"), "preview"),
    ("release_contracts.runtime_profiles.default", release_profiles.get("default"), "preview"),
)
for label, actual, expected in checks:
    if actual != expected:
        raise SystemExit(f"{{label}} mismatch: expected {{expected!r}}, got {{actual!r}}")
if frontend_strategy == "flutter":
    if runtime.get("releaseTagPattern") != "android-preview-v*":
        raise SystemExit("releaseTagPattern must be android-preview-v*")
    if first_release.get("android_tag_pattern") != "android-preview-v*":
        raise SystemExit("manifest.first_release.android_tag_pattern must be android-preview-v*")
    if runtime.get("installableAndroid") is not True:
        raise SystemExit("Flutter preview must declare installableAndroid=true")
else:
    if runtime.get("releaseTagPattern") is not None:
        raise SystemExit("Svelte preview must not declare releaseTagPattern")
    if first_release.get("android_tag_pattern") is not None:
        raise SystemExit("Svelte preview must not declare android_tag_pattern")
    if runtime.get("installableAndroid") is not False:
        raise SystemExit("Svelte preview must declare installableAndroid=false")
    if runtime.get("bridgeRegistrationRequired") is not False:
        raise SystemExit("Svelte preview must declare bridgeRegistrationRequired=false")
for source_label, profiles in (
    (".codex/project.yaml", project_profiles.get("allowed")),
    ("release/release-contracts.yaml", release_profiles.get("allowed")),
    ("deploy/web-preview/web-preview-manifest.yaml", manifest_runtime.get("allowed_profiles")),
):
    if not isinstance(profiles, list) or set(profiles) != {{"mock", "preview", "real", "staging"}}:
        raise SystemExit(f"{{source_label}} must declare mock, preview, real, and staging profiles")
if "preview" not in project_profiles or not isinstance(project_profiles.get("preview"), dict):
    raise SystemExit(".codex/project.yaml runtime_profiles.preview is required")
bridge = runtime.get("bridge")
if frontend_strategy == "flutter" and (
    not isinstance(bridge, dict)
    or bridge.get("verificationEndpoint") != f"/installable-apps/{{expected_slug}}"
):
    raise SystemExit("bridge.verificationEndpoint mismatch")
if frontend_strategy == "svelte" and isinstance(bridge, dict) and bridge.get("requiresApkUrl"):
    raise SystemExit("Svelte preview must not require APK URL")
metadata = runtime.get("releaseMetadata")
if not isinstance(metadata, dict) or metadata.get("initialPreviewRelease") is not True:
    raise SystemExit("releaseMetadata.initialPreviewRelease must be true")
PY

grep -q '"preview"' "$BACKEND_CONFIG" || fail "backend config must allow preview runtime profile"
if [[ "$FRONTEND_STRATEGY" == "flutter" ]]; then
  grep -q "runtimeProfile != 'preview'" "$FLUTTER_CONFIG" || fail "Flutter config must validate preview runtime profile"
  grep -q 'android.permission.INTERNET' "$ANDROID_MANIFEST" || fail "Android preview manifest must include android.permission.INTERNET"
  grep -q 'APP_RUNTIME_PROFILE: preview' "$ANDROID_PREVIEW_WORKFLOW" || fail "Android preview workflow must set APP_RUNTIME_PROFILE=preview"
  grep -q 'API_RUNTIME: cloudflare_preview' "$ANDROID_PREVIEW_WORKFLOW" || fail "Android preview workflow must set API_RUNTIME=cloudflare_preview"
else
  grep -q 'VITE_APP_RUNTIME_PROFILE' "$ROOT_DIR/apps/web/src/config.ts" || fail "Svelte config must validate preview runtime profile"
  grep -q 'VITE_API_BASE_URL' "$ROOT_DIR/apps/web/src/config.ts" || fail "Svelte config must require preview API URL"
fi

python3 - "$SIGNING_POLICY" <<'PY'
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

policy = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if not isinstance(policy, dict):
    raise SystemExit("release/preview-signing-policy.json must be a JSON object")
frontend_strategy = os.environ.get("FRONTEND_STRATEGY", "flutter")
if frontend_strategy == "svelte":
    if policy.get("defaultSigningMode") != "not_applicable_web_only":
        raise SystemExit("Svelte preview signing policy must be not_applicable_web_only")
    if policy.get("signingRequired") is not False:
        raise SystemExit("Svelte preview signing policy must set signingRequired=false")
    if policy.get("installableAndroid") is not False:
        raise SystemExit("Svelte preview signing policy must set installableAndroid=false")
    if policy.get("bridgeRegistrationRequired") is not False:
        raise SystemExit("Svelte preview signing policy must set bridgeRegistrationRequired=false")
    if policy.get("releaseTagPattern") is not None:
        raise SystemExit("Svelte preview signing policy must not declare Android release tags")
    raise SystemExit(0)
if policy.get("defaultSigningMode") != "preview":
    raise SystemExit("defaultSigningMode must remain preview")
if policy.get("productionReady") is not False or policy.get("mockOrDemo") is not False:
    raise SystemExit("preview signing policy must not be production or mock/demo")
if "debugPreview" in policy:
    raise SystemExit("debugPreview signing policy is forbidden for installable Initial Preview Release")
PY

if [[ "$FRONTEND_STRATEGY" == "flutter" ]]; then
  API_BASE_URL="$(python3 - "$RUNTIME_CONTRACT" <<'PY'
import json
import sys
from pathlib import Path

print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["apiBaseUrl"])
PY
  )" \\
  APP_RUNTIME_PROFILE=preview \\
  API_RUNTIME=cloudflare_preview \\
  APP_RELEASE_TAG="${{APP_RELEASE_TAG:-android-preview-v0.0.0-build.0}}" \\
  scripts/validate_release_profiles.sh
fi

printf 'preview release profile validation completed\\n'
'''


def _initial_preview_release_validation_script(
    slug: str,
    frontend_strategy: str = "flutter",
) -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail

fail() {{
  printf 'initial preview release validation failed: %s\\n' "$*" >&2
  if [[ -n "${{CHECK_REPORT:-}}" && -f "${{CHECK_REPORT:-}}" ]]; then
    cat "$CHECK_REPORT" >&2
  fi
  exit 1
}}

CHECK_REPORT="${{CHECK_REPORT:-/tmp/project-factory-initial-preview-checks.tsv}}"
CHECK_REPORT_JSON="${{CHECK_REPORT_JSON:-release/initial-preview-validation-report.json}}"
: > "$CHECK_REPORT"
if [[ -z "${{CHECK_TIMESTAMP:-}}" ]]; then
  CHECK_TIMESTAMP="$(git log --reverse --format=%cI --max-count=1 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)"
  export CHECK_TIMESTAMP
fi

record_check() {{
  local name="$1"
  local status="$2"
  local command="${{3:-}}"
  local detail="${{4:-}}"
  local timestamp
  timestamp="${{CHECK_TIMESTAMP:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}}"
  printf '%s\\t%s\\t%s\\t%s\\t%s\\n' "$name" "$status" "$command" "$detail" "$timestamp" >> "$CHECK_REPORT"
}}

run_check() {{
  local name="$1"
  shift
  local command="$*"
  if ( "$@" ); then
    record_check "$name" "passed" "$command"
  else
    local code=$?
    record_check "$name" "failed" "$command" "exit_code=$code"
    return 0
  fi
}}

skip_check() {{
  record_check "$1" "skipped_with_reason" "" "$2"
}}

write_check_report_json() {{
  local source_tsv="$1"
  mkdir -p "$(dirname "$CHECK_REPORT_JSON")"
  python3 - "$source_tsv" "$CHECK_REPORT_JSON" "$SOURCE_APP" "$FRONTEND_STRATEGY" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

tsv_path, json_path, source_app, frontend_strategy = sys.argv[1:5]
checks = []
for line in Path(tsv_path).read_text(encoding="utf-8").splitlines():
    name, status, command, detail, timestamp = (line.split("\t") + ["", "", "", "", ""])[:5]
    checks.append({{
        "name": name,
        "status": status,
        "command": command,
        "detail": detail,
        "timestamp": timestamp,
    }})
payload = {{
    "kind": "codex.initialPreviewValidationReport",
    "version": 1,
    "sourceApp": source_app,
    "frontendStrategy": frontend_strategy,
    "checks": checks,
    "summary": {{
        "passed": sum(1 for item in checks if item["status"] == "passed"),
        "failed": sum(1 for item in checks if item["status"] == "failed"),
        "skipped": sum(1 for item in checks if item["status"] == "skipped_with_reason"),
    }},
}}
Path(json_path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
PY
}}

finish_checks() {{
  if [[ -z "${{CHECK_TIMESTAMP:-}}" ]]; then
    CHECK_TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    export CHECK_TIMESTAMP
  fi
  local base_report="${{CHECK_REPORT}}.base"
  local candidate_report="${{CHECK_REPORT}}.candidate"
  cp "$CHECK_REPORT" "$base_report"
  local pre_clean_status="passed"
  if awk -F '\\t' '$2 == "failed" {{ found=1 }} END {{ exit found ? 0 : 1 }}' "$base_report"; then
    pre_clean_status="failed"
  fi
  local candidate_validator_status="$pre_clean_status"
  cp "$base_report" "$candidate_report"
  printf '%s\\t%s\\t%s\\t%s\\t%s\\n' \\
    "clean git status" "passed" "git status --porcelain after validation report" "" "$CHECK_TIMESTAMP" >> "$candidate_report"
  printf '%s\\t%s\\t%s\\t%s\\t%s\\n' \\
    "validate_initial_preview_release.sh" "$candidate_validator_status" "scripts/validate_initial_preview_release.sh" "" "$CHECK_TIMESTAMP" >> "$candidate_report"
  write_check_report_json "$candidate_report"

  local git_status
  git_status="$(git status --porcelain)"
  local clean_status="passed"
  local clean_detail=""
  if [[ -n "$git_status" ]]; then
    clean_status="failed"
    clean_detail="$(printf '%s' "$git_status" | tr '\\n\\t' '; ' | sed 's/[; ]*$//')"
  fi
  local validator_status="$pre_clean_status"
  if [[ "$clean_status" == "failed" ]]; then
    validator_status="failed"
  fi

  cp "$base_report" "$CHECK_REPORT"
  record_check "clean git status" "$clean_status" "git status --porcelain after validation report" "$clean_detail"
  record_check "validate_initial_preview_release.sh" "$validator_status" "scripts/validate_initial_preview_release.sh"
  write_check_report_json "$CHECK_REPORT"
  printf 'initial preview release checks:\\n'
  awk -F '\\t' '{{ printf "- %s: %s%s\\n", $1, $2, ($4 ? " (" $4 ")" : "") }}' "$CHECK_REPORT"
  printf 'validation report: %s\\n' "$CHECK_REPORT_JSON"
  if [[ "$validator_status" == "failed" ]]; then
    fail "one or more required checks failed"
  fi
}}

ROOT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
cd "$ROOT_DIR"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/load_bridge_env.sh"
source "$ROOT_DIR/scripts/github_repo_access.sh"
FRONTEND_STRATEGY="{frontend_strategy}"

SOURCE_APP="${{SOURCE_APP:-{slug}}}"
PREVIEW_API_BASE_URL="${{PREVIEW_API_BASE_URL:-${{API_BASE_URL:-https://preview.nienfos.com/$SOURCE_APP/api}}}}"
PREVIEW_API_BASE_URL="${{PREVIEW_API_BASE_URL%/}}"

bridge_env_require APP_RUNTIME_PROFILE API_RUNTIME API_BASE_URL BRIDGE_URL PREVIEW_ADMIN_PASSWORD
bridge_env_require_any "preview D1 database" PREVIEW_D1_DATABASE CLOUDFLARE_D1_DATABASE
if [[ "$FRONTEND_STRATEGY" == "flutter" ]]; then
  bridge_env_require INSTALLABLE_APPS_REGISTRATION_TOKEN APP_RELEASE_TAG APP_ANDROID_PREVIEW_RELEASE_TAG
fi
if grep -q "PREVIEW_ADMIN_BOOTSTRAP_TOKEN" deploy/web-preview/worker/src/index.js 2>/dev/null; then
  bridge_env_require PREVIEW_ADMIN_BOOTSTRAP_TOKEN
fi
[[ "$APP_RUNTIME_PROFILE" == "preview" ]] || fail "APP_RUNTIME_PROFILE must be preview"
[[ "$API_RUNTIME" == "cloudflare_preview" ]] || fail "API_RUNTIME must be cloudflare_preview"
[[ "$PREVIEW_API_BASE_URL" == "https://preview.nienfos.com/$SOURCE_APP/api" ]] || \\
  fail "Preview API must be https://preview.nienfos.com/$SOURCE_APP/api"
[[ "${{API_BASE_URL%/}}" == "$PREVIEW_API_BASE_URL" ]] || fail "API_BASE_URL must match Preview API"

run_backend_tests() {{
  cd "$ROOT_DIR/backend"
  python3 -m pytest tests -q
}}

run_flutter_analyze() {{
  cd "$ROOT_DIR/apps/mobile"
  flutter analyze
}}

run_flutter_tests() {{
  cd "$ROOT_DIR/apps/mobile"
  flutter test \\
    --dart-define=APP_RUNTIME_PROFILE=preview \\
    --dart-define=API_RUNTIME=cloudflare_preview \\
    --dart-define=API_BASE_URL="$PREVIEW_API_BASE_URL" \\
    --dart-define=APP_SLUG="$SOURCE_APP"
}}

configure_preview_signing() {{
  bridge_env_load_preview_signing
  cp "$ANDROID_KEYSTORE_PATH" "$ROOT_DIR/apps/mobile/android/upload-keystore.jks"
  cat > "$ROOT_DIR/apps/mobile/android/key.properties" <<EOF
storeFile=upload-keystore.jks
storePassword=$ANDROID_STORE_PASSWORD
keyPassword=$ANDROID_KEY_PASSWORD
keyAlias=$ANDROID_KEY_ALIAS
storeType=${{ANDROID_STORE_TYPE:-JKS}}
EOF
}}

run_local_apk_build() {{
  configure_preview_signing
  cd "$ROOT_DIR/apps/mobile"
  flutter build apk --release \\
    --dart-define=APP_RUNTIME_PROFILE=preview \\
    --dart-define=API_RUNTIME=cloudflare_preview \\
    --dart-define=API_BASE_URL="$PREVIEW_API_BASE_URL" \\
    --dart-define=APP_SLUG="$SOURCE_APP"
}}

run_apksigner_verify() {{
  local apk="$ROOT_DIR/apps/mobile/build/app/outputs/flutter-apk/app-release.apk"
  [[ -f "$apk" ]] || apk="$ROOT_DIR/apps/mobile/build/app/outputs/flutter-apk/$SOURCE_APP.apk"
  [[ -f "$apk" ]] || {{
    printf 'APK not found after local build\\n' >&2
    return 2
  }}
  local apksigner_bin="${{APKSIGNER:-}}"
  if [[ -z "$apksigner_bin" ]]; then
    apksigner_bin="$(command -v apksigner || true)"
  fi
  if [[ -z "$apksigner_bin" && -n "${{ANDROID_HOME:-}}" ]]; then
    apksigner_bin="$(find "$ANDROID_HOME/build-tools" -name apksigner -type f 2>/dev/null | sort -V | tail -n 1)"
  fi
  [[ -n "$apksigner_bin" ]] || {{
    printf 'apksigner is required\\n' >&2
    return 2
  }}
  "$apksigner_bin" verify --verbose --print-certs "$apk" | tee /tmp/project-factory-apksigner.txt
  grep -q "Verified using" /tmp/project-factory-apksigner.txt
  if grep -Eqi 'CN=Android Debug|Android Debug' /tmp/project-factory-apksigner.txt; then
    printf 'Preview APK must not be signed with Android debug certificate.\\n' >&2
    return 2
  fi
  signer_sha256="$(awk -F': ' '/certificate SHA-256 digest/ {{ print $NF; exit }}' /tmp/project-factory-apksigner.txt | tr -d '[:space:]')"
  [[ "$signer_sha256" =~ ^[A-Fa-f0-9]{{64}}$ ]] || {{
    printf 'Could not parse signer certificate SHA256 from apksigner output.\\n' >&2
    return 2
  }}
  record_check "apksigner signer SHA256" "passed" "$apksigner_bin verify --print-certs" "$signer_sha256"
}}

run_invite_e2e() {{
  python3 - "$BRIDGE_URL" "$SOURCE_APP" "$PREVIEW_ADMIN_PASSWORD" <<'PY'
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

bridge_url, source_app, password = sys.argv[1:4]
bridge_url = bridge_url.rstrip("/")
preview_id = "wp-" + source_app
email = "preview-admin-" + str(int(time.time())) + "@example.test"

def request(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    headers = dict()
    headers["accept"] = "application/json"
    headers["content-type"] = "application/json"
    headers["user-agent"] = "CodexProjectFactoryPreviewSmoke/1.0"
    req = urllib.request.Request(
        bridge_url + path,
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else dict()
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = dict(raw=raw)
        return exc.code, payload

status, invite = request("POST", "/web-previews/" + preview_id + "/invites", dict(email=email, role="admin"))
if status >= 400:
    raise SystemExit("invite create failed: " + str(status) + " " + repr(invite))
if invite.get("email_delivery_status") not in ("sent", "manual_link_required"):
    raise SystemExit("unexpected invite delivery status: " + repr(invite))
if invite.get("sync_status") != "synced":
    raise SystemExit("invite sync_status must be synced: " + repr(invite))
if not invite.get("expires_at"):
    raise SystemExit("invite expires_at is required")
if invite.get("used_at") is not None:
    raise SystemExit("invite used_at must be empty before activation")
invite_url = str(invite.get("invite_url") or "")
token = invite_url.split("token=", 1)[-1] if "token=" in invite_url else ""
if not token:
    raise SystemExit("invite_url token missing for E2E activation")
api_base = "https://preview.nienfos.com/" + source_app + "/api"
api_headers = dict()
api_headers["content-type"] = "application/json"
api_headers["accept"] = "application/json"
api_headers["user-agent"] = "CodexProjectFactoryPreviewSmoke/1.0"
activate = urllib.request.Request(
    api_base + "/invites/accept",
    data=json.dumps(dict(
        inviteToken=token,
        email=email,
        password=password,
        passwordConfirmation=password,
    )).encode(),
    method="POST",
    headers=api_headers,
)
with urllib.request.urlopen(activate, timeout=30) as response:
    if response.status >= 400:
        raise SystemExit("invite activation failed: " + str(response.status))
status, listed = request("GET", "/web-previews/" + preview_id + "/invites")
if status >= 400:
    raise SystemExit("invite list failed after activation: " + str(status) + " " + repr(listed))
matches = [row for row in listed.get("invites", listed if isinstance(listed, list) else []) if row.get("invite_id") == invite.get("invite_id")]
if not matches or not matches[0].get("used_at"):
    raise SystemExit("invite used_at was not marked after activation")
login = urllib.request.Request(
    api_base + "/auth/login",
    data=json.dumps(dict(email=email, password=password)).encode(),
    method="POST",
    headers=api_headers,
)
with urllib.request.urlopen(login, timeout=30) as response:
    if response.status != 200:
        raise SystemExit("login after invite activation failed: " + str(response.status))
PY
}}

run_check "backend tests" run_backend_tests
if [[ "$FRONTEND_STRATEGY" == "flutter" ]]; then
  run_check "Flutter analyze" run_flutter_analyze
  run_check "Flutter tests" run_flutter_tests
  run_check "APK local build" run_local_apk_build
  run_check "apksigner verify" run_apksigner_verify
else
  skip_check "Flutter analyze" "frontend_strategy=$FRONTEND_STRATEGY"
  skip_check "Flutter tests" "frontend_strategy=$FRONTEND_STRATEGY"
  skip_check "APK local build" "frontend_strategy=$FRONTEND_STRATEGY"
  skip_check "apksigner verify" "frontend_strategy=$FRONTEND_STRATEGY"
fi
run_check "D1 migration apply" scripts/apply_preview_d1_migrations.sh
run_check "Cloudflare preview health" scripts/smoke_web_preview.sh
run_check "web preview smoke" scripts/smoke_web_preview.sh
run_check "API preview smoke" scripts/smoke_preview_api.sh
if [[ "$FRONTEND_STRATEGY" == "flutter" ]]; then
  run_check "Factory invite validation" run_invite_e2e
else
  skip_check "Factory invite validation" "frontend_strategy=$FRONTEND_STRATEGY"
fi

if [[ "$FRONTEND_STRATEGY" == "flutter" ]]; then
  [[ -f "$ROOT_DIR/apps/mobile/lib/src/screens.dart" ]] || fail "Flutter screens.dart missing"
  ! grep -q "label: 'Workbench'" "$ROOT_DIR/apps/mobile/lib/src/screens.dart" || fail "generated product app must not expose a Workbench navigation tab"
  ! grep -q "Invite token or link" "$ROOT_DIR/apps/mobile/lib/src/screens.dart" || fail "URL invite flow must not ask users to paste invite tokens"
  grep -q "Crear contraseña" "$ROOT_DIR/apps/mobile/lib/src/screens.dart" || fail "invite activation password label missing"
  grep -q "Repetir contraseña" "$ROOT_DIR/apps/mobile/lib/src/screens.dart" || fail "invite activation password confirmation label missing"
  grep -q "Aceptar invitación" "$ROOT_DIR/apps/mobile/lib/src/screens.dart" || fail "invite activation action missing"
  english_create_label="Create"" password"
  english_repeat_label="Repeat"" password"
  english_activate_action="Activate"" account"
  ! grep -q "$english_create_label" "$ROOT_DIR/apps/mobile/lib/src/screens.dart" || fail "invite activation must not use English create-password label"
  ! grep -q "$english_repeat_label" "$ROOT_DIR/apps/mobile/lib/src/screens.dart" || fail "invite activation must not use English repeat-password label"
  ! grep -q "$english_activate_action" "$ROOT_DIR/apps/mobile/lib/src/screens.dart" || fail "invite activation must not use English activate-account action"
fi

if [[ "$FRONTEND_STRATEGY" == "svelte" ]]; then
  record_check "GitHub Android release workflow" "skipped_with_reason" "svelte frontend has no Android preview workflow"
  record_check "GitHub release asset exists" "skipped_with_reason" "svelte frontend has no APK asset"
  record_check "APK SHA256" "skipped_with_reason" "svelte frontend has no APK"
  record_check "Bridge registration real" "skipped_with_reason" "svelte frontend has no installable Android registration"
  local_head="$(git rev-parse HEAD 2>/dev/null || echo unavailable)"
  branch="$(git symbolic-ref --short HEAD 2>/dev/null || true)"
  push_state="unknown"
  upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{{u}}' 2>/dev/null || true)"
  if [[ -n "$upstream" ]]; then
    remote_head="$(git rev-parse "$upstream" 2>/dev/null || true)"
    if [[ "$remote_head" == "$local_head" ]]; then
      push_state="pushed:$upstream"
    else
      push_state="not_pushed:$upstream"
    fi
  fi
  if [[ "${{UPDATE_RELEASE_OUTPUT:-false}}" == "true" ]]; then
    python3 - "$ROOT_DIR/release/release-output-template.md" "$SOURCE_APP" "$local_head" "$branch" "$push_state" "$PREVIEW_API_BASE_URL" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

output_path, source_app, source_commit, branch, push_state, api_url = sys.argv[1:7]
preview_url = f"https://preview.nienfos.com/{{source_app}}"
content = f"""# Factory Final Output

- source_app: {{source_app}}
- validated_source_commit: {{source_commit}}
- android_tag_commit: not_applicable_web_only
- report_generated_from_commit: {{source_commit}}
- release_report_commit:
- push_state: {{push_state}}
- branch: {{branch or "detached"}}
- frontend_strategy: svelte
- runtime_profile: preview
- release_channel: prerelease
- mock_or_demo: false
- backend_required: true
- production_ready: false
- production_release_blocked: true
- installable_android: false
- productive_release_tag: blocked_until_explicit_promotion
- release_url: not_applicable_web_only
- bridge_installable_url: not_applicable_web_only
- cloudflare_preview_url: {{preview_url}}
- cloudflare_preview_health_url: {{preview_url}}/__preview/health
- web_preview_ready: true
- preview_api_base_url: {{api_url}}
- preview_api_health_url: {{api_url}}/health
- workbench_status: not_applicable_web_only
- codex_mobile_catalog_status: not_applicable_web_only
- validations_executed:
  - backend tests
  - Svelte tests
  - Worker local preview test
  - generated project validation
  - release profile validation preview
  - Cloudflare public health
  - Preview API health
  - preview persistence login smoke
- blockers_remaining:
  - Android APK and Bridge installability require a future wrapper strategy
  - production release requires explicit promotion
"""
Path(output_path).write_text(content, encoding="utf-8")
PY
  fi
  grep -q "validated_source_commit:" "$ROOT_DIR/release/release-output-template.md" || fail "release output must include validated_source_commit"
  grep -q "report_generated_from_commit:" "$ROOT_DIR/release/release-output-template.md" || fail "release output must include report_generated_from_commit"
  grep -q "frontend_strategy: svelte" "$ROOT_DIR/release/release-output-template.md" || fail "release output must declare Svelte strategy"
  grep -q "installable_android: false" "$ROOT_DIR/release/release-output-template.md" || fail "Svelte release output must not claim installable Android"
  grep -q "bridge_installable_url: not_applicable_web_only" "$ROOT_DIR/release/release-output-template.md" || fail "Svelte release output must not claim Bridge installability"
  scripts/final_readiness_audit.sh
  finish_checks
  printf 'initial svelte preview release ready: %s\\n' "$SOURCE_APP"
  exit 0
fi

origin_url="$(git remote get-url origin 2>/dev/null || true)"
[[ -n "$origin_url" ]] || fail "origin remote is not configured"
repo_ref="$origin_url"
repo_ref="${{repo_ref#https://github.com/}}"
repo_ref="${{repo_ref#git@github.com:}}"
repo_ref="${{repo_ref%.git}}"
[[ "$repo_ref" == */* ]] || fail "origin remote must point to a GitHub owner/repo"
github_require_repo_access "$repo_ref" || fail "GitHub repository is not accessible with authenticated tools"

version="$(awk '/^version:/ {{ print $2; exit }}' apps/mobile/pubspec.yaml)"
[[ -n "$version" ]] || fail "apps/mobile/pubspec.yaml has no version"
expected_tag="android-preview-v${{version//+/-build.}}"
[[ "$APP_RELEASE_TAG" == "$expected_tag" ]] || fail "APP_RELEASE_TAG must be $expected_tag"
[[ "$APP_ANDROID_PREVIEW_RELEASE_TAG" == "$expected_tag" ]] || fail "APP_ANDROID_PREVIEW_RELEASE_TAG must be $expected_tag"

run_github_release_asset_exists() {{
  command -v gh >/dev/null 2>&1 || {{
    printf 'gh is required to verify Android preview APK release assets\\n' >&2
    return 2
  }}
  local assets
  assets="$(gh release view "$expected_tag" --repo "$repo_ref" --json assets --jq '.assets[].name' 2>/dev/null || true)"
  [[ -n "$assets" ]] || {{
    printf 'GitHub release %s is missing or has no assets\\n' "$expected_tag" >&2
    return 2
  }}
  printf '%s\\n' "$assets" | grep -Fx "$SOURCE_APP.apk" >/dev/null || {{
    printf 'GitHub release %s has no %s.apk asset\\n' "$expected_tag" "$SOURCE_APP" >&2
    return 2
  }}
}}

run_bridge_registration_validation() {{
  [[ -n "${{BRIDGE_URL:-}}" ]] || {{
    printf 'BRIDGE_URL is required to verify Codex Mobile Apps registration\\n' >&2
    return 2
  }}
  local detail
  detail="$(curl -fsS "${{BRIDGE_URL%/}}/installable-apps/$SOURCE_APP")" || {{
    printf 'Bridge registration lookup failed\\n' >&2
    return 2
  }}
  printf '%s\\n' "$detail" > /tmp/project-factory-installable-app-detail.json
  python3 - "$SOURCE_APP" "$expected_tag" "$ROOT_DIR/release/preview-runtime.json" "$ROOT_DIR/deploy/web-preview/web-preview-manifest.yaml" <<'PY'
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
try:
    import yaml
except ModuleNotFoundError as exc:
    raise SystemExit("PyYAML is required to validate web-preview-manifest.yaml") from exc

source_app, expected_tag, runtime_path, manifest_path = sys.argv[1:5]
detail = json.loads(Path("/tmp/project-factory-installable-app-detail.json").read_text())
runtime = json.loads(Path(runtime_path).read_text(encoding="utf-8"))
manifest = yaml.safe_load(Path(manifest_path).read_text(encoding="utf-8"))
if detail.get("sourceApp") != source_app:
    raise SystemExit("Bridge registration sourceApp mismatch")
if detail.get("releaseChannel") != runtime.get("releaseChannel"):
    raise SystemExit("Bridge registration is not prerelease channel")
if detail.get("releaseTagPattern") != runtime.get("releaseTagPattern"):
    raise SystemExit("Bridge registration does not use android-preview-v*")
if detail.get("available") is not True:
    raise SystemExit("Bridge registration must return available=true")
release_tag = detail.get("releaseTag")
if not release_tag:
    raise SystemExit("Bridge registration must return releaseTag")
if release_tag != expected_tag:
    raise SystemExit("Bridge registration releaseTag mismatch")
if not str(release_tag).startswith("android-preview-v"):
    raise SystemExit("Bridge registration releaseTag must use android-preview-v*")
if detail.get("previewUrl") != runtime.get("previewUrl"):
    raise SystemExit("Bridge registration previewUrl mismatch")
if detail.get("runtimeProfile") != runtime.get("runtimeProfile"):
    raise SystemExit("Bridge registration runtimeProfile must be preview")
if detail.get("productionReady") is not False:
    raise SystemExit("Bridge registration productionReady must be false")
if detail.get("mockOrDemo") is not False:
    raise SystemExit("Bridge registration mockOrDemo must be false")
latest_build = detail.get("latestBuild")
if not latest_build:
    raise SystemExit("Bridge registration must return latestBuild")
apk_url = str(detail.get("apkUrl") or "")
if not apk_url:
    raise SystemExit("Bridge registration does not expose apkUrl")
if not apk_url.startswith(("http://", "https://")):
    raise SystemExit("Bridge registration apkUrl must be an HTTP(S) proxy URL")
detail_sha = str(detail.get("sha256") or "")
if not re.fullmatch(r"[a-fA-F0-9]{{64}}", detail_sha):
    raise SystemExit("Bridge registration sha256 must be present and 64 hex characters")
manifest_runtime = manifest.get("runtime") if isinstance(manifest, dict) and isinstance(manifest.get("runtime"), dict) else {{}}
if manifest.get("stable_url") != runtime.get("previewUrl"):
    raise SystemExit("web-preview manifest stable_url disagrees with preview-runtime.json")
if manifest_runtime.get("api_base_url") != runtime.get("apiBaseUrl"):
    raise SystemExit("web-preview manifest api_base_url disagrees with preview-runtime.json")
if manifest_runtime.get("default_profile") != runtime.get("runtimeProfile"):
    raise SystemExit("web-preview manifest runtime profile disagrees with preview-runtime.json")
metadata = detail.get("releaseMetadata")
if isinstance(metadata, dict):
    if metadata.get("initialPreviewRelease") is not True:
        raise SystemExit("Bridge registration releaseMetadata.initialPreviewRelease must be true")
    if metadata.get("releaseTagPattern") != runtime.get("releaseTagPattern"):
        raise SystemExit("Bridge registration release metadata tag pattern mismatch")
print(f"initial preview release ready: {{source_app}} {{expected_tag}}")
PY
}}

run_apk_sha256_validation() {{
  python3 - <<'PY'
from __future__ import annotations

import json
import os
import re
from pathlib import Path

detail = json.loads(Path("/tmp/project-factory-installable-app-detail.json").read_text())
detail_sha = str(detail.get("sha256") or "")
if not re.fullmatch(r"[a-fA-F0-9]{{64}}", detail_sha):
    raise SystemExit("Bridge registration sha256 must be present and 64 hex characters")
expected_sha = os.environ.get("EXPECTED_SHA256", "").strip().lower()
if expected_sha:
    if not re.fullmatch(r"[a-fA-F0-9]{{64}}", expected_sha):
        raise SystemExit("EXPECTED_SHA256 must be 64 hex characters")
    if detail_sha.lower() != expected_sha:
        raise SystemExit("Bridge registration sha256 does not match EXPECTED_SHA256")
PY
  if [[ -n "${{EXPECTED_SHA256:-}}" ]]; then
    local apk_url
    apk_url="$(python3 - <<'PY'
import json
from pathlib import Path

detail = json.loads(Path("/tmp/project-factory-installable-app-detail.json").read_text())
print(detail["apkUrl"])
PY
)"
    printf 'verifying preview APK bytes with EXPECTED_SHA256 via download: %s\\n' "$apk_url"
    curl -fsSL "$apk_url" -o /tmp/project-factory-preview.apk
    local actual_sha
    actual_sha="$(sha256sum /tmp/project-factory-preview.apk | awk '{{ print $1 }}')"
    [[ "${{actual_sha,,}}" == "${{EXPECTED_SHA256,,}}" ]] || {{
      printf 'Preview APK checksum does not match EXPECTED_SHA256\\n' >&2
      return 2
    }}
    printf 'preview APK checksum verified: %s\\n' "$actual_sha"
  fi
}}

run_check "GitHub Android release workflow" gh workflow view android-preview-release.yml --repo "$repo_ref"
run_check "GitHub release asset exists" run_github_release_asset_exists

run_check "Bridge registration real" run_bridge_registration_validation
run_check "APK SHA256" run_apk_sha256_validation
if awk -F '\\t' '$2 == "failed" {{ found=1 }} END {{ exit found ? 0 : 1 }}' "$CHECK_REPORT"; then
  finish_checks
fi

release_url="$(gh release view "$expected_tag" --repo "$repo_ref" --json url --jq '.url' 2>/dev/null || true)"
local_head="$(git rev-parse HEAD)"
branch="$(git symbolic-ref --short HEAD 2>/dev/null || true)"
upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{{u}}' 2>/dev/null || true)"
push_state="unknown"
if [[ -n "$upstream" ]]; then
  remote_head="$(git rev-parse "$upstream" 2>/dev/null || true)"
  if [[ "$remote_head" == "$local_head" ]]; then
    push_state="pushed:$upstream"
  else
    push_state="not_pushed:$upstream"
  fi
fi

if [[ "${{UPDATE_RELEASE_OUTPUT:-false}}" == "true" ]]; then
  python3 - "$ROOT_DIR/release/release-output-template.md" "$SOURCE_APP" "$expected_tag" "$local_head" "$branch" "$push_state" "$release_url" "$PREVIEW_API_BASE_URL" "${{BRIDGE_URL%/}}/installable-apps/$SOURCE_APP" <<'PY'
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

(
    output_path,
    source_app,
    release_tag,
    source_commit,
    branch,
    push_state,
    release_url,
    api_url,
    bridge_url,
) = sys.argv[1:10]
detail = json.loads(Path("/tmp/project-factory-installable-app-detail.json").read_text())
apk_url = str(detail.get("apkUrl") or "")
apk_sha = str(detail.get("sha256") or os.environ.get("EXPECTED_SHA256") or "")
preview_url = str(detail.get("previewUrl") or f"https://preview.nienfos.com/{{source_app}}")
if not apk_url:
    raise SystemExit("release output cannot be written without apkUrl")
if detail.get("releaseChannel") != "prerelease":
    raise SystemExit("release output cannot overpromise non-prerelease channel")
if detail.get("productionReady") is not False:
    raise SystemExit("release output cannot mark preview as production ready")
if detail.get("mockOrDemo") is not False:
    raise SystemExit("release output cannot mark preview as mock/demo")
validations = [
    "backend tests",
    "Flutter tests",
    "Worker local preview test",
    "generated project validation",
    "release profile validation preview",
    "publication-ready local validation",
    "Cloudflare public health",
    "Preview API health",
    "preview persistence login smoke",
    "GitHub prerelease APK",
    "Bridge installable lookup",
    "Bridge Workbench artifact discoverability",
    "No Workbench product navigation",
]
content = f"""# Factory Final Output

- source_app: {{source_app}}
- validated_source_commit: {{source_commit}}
- android_tag_commit: {{source_commit}}
- report_generated_from_commit: {{source_commit}}
- release_report_commit:
- push_state: {{push_state}}
- branch: {{branch or "detached"}}
- runtime_profile: preview
- release_channel: prerelease
- mock_or_demo: false
- backend_required: true
- production_ready: false
- production_release_blocked: true
- android_preview_release_tag: {{release_tag}}
- productive_release_tag: blocked_until_explicit_promotion
- android_preview_apk_url: {{apk_url}}
- android_preview_apk_sha256: {{apk_sha or "unavailable"}}
- release_url: {{release_url or "unavailable"}}
- bridge_installable_url: {{bridge_url}}
- cloudflare_preview_url: {{preview_url}}
- cloudflare_preview_health_url: {{preview_url}}/__preview/health
- preview_api_base_url: {{api_url}}
- preview_api_health_url: {{api_url}}/health
- workbench_status: bridge_owned_dev_entrypoint
- codex_mobile_catalog_status: installable_preview_available
- validations_executed:
{{chr(10).join(f"  - {{item}}" for item in validations)}}
- blockers_remaining:
  - production release requires explicit promotion and must use android-v*
"""
for forbidden in ("preview listo sin APK", "release listo sin APK", "installable listo sin Bridge", "API preview real sin D1"):
    if forbidden in content:
        raise SystemExit(f"release output overpromises: {{forbidden}}")
Path(output_path).write_text(content, encoding="utf-8")
PY
fi

grep -q "validated_source_commit:" "$ROOT_DIR/release/release-output-template.md" || fail "release output must include validated_source_commit"
grep -q "android_tag_commit:" "$ROOT_DIR/release/release-output-template.md" || fail "release output must include android_tag_commit"
grep -q "report_generated_from_commit:" "$ROOT_DIR/release/release-output-template.md" || fail "release output must include report_generated_from_commit"
grep -q "release_channel: prerelease" "$ROOT_DIR/release/release-output-template.md" || fail "release output must declare prerelease channel"
grep -q "production_ready: false" "$ROOT_DIR/release/release-output-template.md" || fail "release output must not overpromise production readiness"
if [[ "${{UPDATE_RELEASE_OUTPUT:-false}}" == "true" ]]; then
  grep -q "android_preview_apk_url: http" "$ROOT_DIR/release/release-output-template.md" || fail "release output must include APK URL"
  grep -q "bridge_installable_url: http" "$ROOT_DIR/release/release-output-template.md" || fail "release output must include Bridge installable URL"
fi
run_check "final readiness audit" scripts/final_readiness_audit.sh
finish_checks
'''


def _release_profile_validation_script() -> str:
    return r'''#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'release profile validation failed: %s\n' "$*" >&2
  exit 1
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAG="${GITHUB_REF_NAME:-${APP_RELEASE_TAG:-}}"
PROFILE="${APP_RUNTIME_PROFILE:-real}"
LOCAL_DATA_MODE="${LOCAL_DATA_MODE:-false}"
API_URL="${API_BASE_URL:-}"
METADATA_FILE="${RELEASE_METADATA_FILE:-$ROOT_DIR/release/release-metadata.yaml}"

case "$PROFILE" in
  mock|real|staging|preview) ;;
  *) fail "APP_RUNTIME_PROFILE must be mock, real, staging, or preview" ;;
esac

if [[ "$TAG" == android-preview-v* ]]; then
  [[ "$PROFILE" == "preview" ]] || fail "android-preview-v* tags require APP_RUNTIME_PROFILE=preview"
  [[ "${API_RUNTIME:-cloudflare_preview}" == "cloudflare_preview" ]] || fail "android-preview-v* tags require API_RUNTIME=cloudflare_preview"
  [[ -n "$API_URL" ]] || fail "preview releases require API_BASE_URL"
  [[ "$API_URL" == https://preview.nienfos.com/*/api ]] || fail "preview releases require API_BASE_URL=https://preview.nienfos.com/<slug>/api"
  [[ "$LOCAL_DATA_MODE" != "true" ]] || fail "preview releases cannot use LOCAL_DATA_MODE=true"
  [[ "$API_URL" != *localhost* && "$API_URL" != *127.0.0.1* && "$API_URL" != *10.0.2.2* ]] || fail "preview releases cannot use local API_BASE_URL=$API_URL"
  [[ "$API_URL" != *example* && "$API_URL" != *placeholder* ]] || fail "preview releases cannot use placeholder API_BASE_URL=$API_URL"
elif [[ "$TAG" == android-v* ]]; then
  [[ "$PROFILE" == "real" || "$PROFILE" == "staging" ]] || fail "productive android-v* tags cannot use APP_RUNTIME_PROFILE=$PROFILE"
  [[ "$LOCAL_DATA_MODE" != "true" ]] || fail "productive android-v* tags cannot use LOCAL_DATA_MODE=true"
  [[ -n "$API_URL" ]] || fail "productive releases require API_BASE_URL"
  [[ "$API_URL" != *localhost* && "$API_URL" != *127.0.0.1* && "$API_URL" != *10.0.2.2* ]] || fail "productive releases cannot use local API_BASE_URL=$API_URL"
  [[ "$API_URL" != *example* && "$API_URL" != *placeholder* ]] || fail "productive releases cannot use placeholder API_BASE_URL=$API_URL"
elif [[ "$TAG" == android-mock-* || "$TAG" == android-local-* ]]; then
  [[ "$PROFILE" == "mock" ]] || fail "mock/local tags require APP_RUNTIME_PROFILE=mock"
else
  printf 'release profile validation warning: APP_RELEASE_TAG/GITHUB_REF_NAME is empty or non-standard; applying profile-only checks\n'
fi

if [[ -f "$METADATA_FILE" ]]; then
  if [[ "$TAG" == android-preview-v* ]]; then
    grep -Eq '^runtime_profile:\s*preview\s*$' "$METADATA_FILE" || fail "preview metadata must declare runtime_profile=preview"
    grep -Eq '^mock_or_demo:\s*false\s*$' "$METADATA_FILE" || fail "preview metadata must declare mock_or_demo=false"
    grep -Eq '^backend_required:\s*true\s*$' "$METADATA_FILE" || fail "preview metadata must declare backend_required=true"
  fi
  if [[ "$TAG" == android-v* ]]; then
    grep -Eq '^runtime_profile:\s*(real|staging)\s*$' "$METADATA_FILE" || fail "productive metadata must declare runtime_profile real/staging"
    grep -Eq '^mock_or_demo:\s*false\s*$' "$METADATA_FILE" || fail "productive metadata must declare mock_or_demo=false"
    grep -Eq '^backend_required:\s*true\s*$' "$METADATA_FILE" || fail "productive metadata must declare backend_required=true"
  fi
  if [[ "$TAG" == android-mock-* || "$TAG" == android-local-* ]]; then
    grep -Eq '^runtime_profile:\s*mock\s*$' "$METADATA_FILE" || fail "mock metadata must declare runtime_profile=mock"
    grep -Eq '^mock_or_demo:\s*true\s*$' "$METADATA_FILE" || fail "mock metadata must declare mock_or_demo=true"
    grep -Eq '^backend_required:\s*false\s*$' "$METADATA_FILE" || fail "mock metadata must declare backend_required=false"
  fi
fi

if [[ "$TAG" == android-preview-v* || "$TAG" == android-v* ]]; then
  if grep -RInE "defaultValue:\s*'mock'|runtimeProfile\s*=\s*'mock'|LOCAL_DATA_MODE\s*=\s*true|const bool.fromEnvironment\('LOCAL_DATA_MODE',\s*defaultValue:\s*true\)" \
      "$ROOT_DIR/apps/mobile/lib" "$ROOT_DIR/backend/app" >/tmp/project-factory-release-profile-grep.txt 2>/dev/null; then
    cat /tmp/project-factory-release-profile-grep.txt >&2
    fail "productive source defaults to mock/local runtime"
  fi
fi

[[ -f "$ROOT_DIR/codex-bridge.yaml" ]] || fail "codex-bridge.yaml is required for Workbench identity"
grep -q 'sourceApp:' "$ROOT_DIR/codex-bridge.yaml" || fail "codex-bridge.yaml must declare sourceApp"
grep -q 'workbench-sdd/v1' "$ROOT_DIR/codex-bridge.yaml" || fail "codex-bridge.yaml must declare workbench-sdd/v1"
[[ -f "$ROOT_DIR/docs/workbench.md" ]] || fail "docs/workbench.md must document Workbench usage or blocking command"

printf 'release profile validation completed: profile=%s tag=%s\n' "$PROFILE" "${TAG:-unset}"
'''


def _generated_android_release_workflow(slug: str) -> str:
    return f"""name: Android Release

on:
  push:
    tags:
      - "android-v*"
      - "android-mock-v*"
      - "android-local-v*"
  workflow_dispatch:
    inputs:
      runtime_profile:
        description: "Runtime profile: real, staging, or mock"
        required: true
        default: "real"

permissions:
  contents: write

jobs:
  build-release:
    runs-on: ubuntu-latest
    env:
      APP_RUNTIME_PROFILE: ${{{{ github.event.inputs.runtime_profile || (startsWith(github.ref_name, 'android-mock-') && 'mock') || (startsWith(github.ref_name, 'android-local-') && 'mock') || 'real' }}}}
      API_BASE_URL: ${{{{ vars.API_BASE_URL }}}}
      LOCAL_DATA_MODE: "false"

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"

      - uses: subosito/flutter-action@v2
        with:
          channel: stable

      - name: Validate release profile contract
        run: scripts/validate_release_profiles.sh

      - name: Flutter dependencies
        working-directory: apps/mobile
        run: flutter pub get

      - name: Analyze
        working-directory: apps/mobile
        run: flutter analyze

      - name: Test
        working-directory: apps/mobile
        run: flutter test

      - name: Build Android APK
        working-directory: apps/mobile
        run: |
          args=()
          args+=(--dart-define=APP_RUNTIME_PROFILE="$APP_RUNTIME_PROFILE")
          if [[ "$APP_RUNTIME_PROFILE" != "mock" ]]; then
            args+=(--dart-define=API_BASE_URL="$API_BASE_URL")
          fi
          args+=(--dart-define=CODEX_FEEDBACK_BRIDGE_URL="${{{{ vars.CODEX_FEEDBACK_BRIDGE_URL }}}}")
          args+=(--dart-define=CODEX_FEEDBACK_ENABLED="${{{{ vars.CODEX_FEEDBACK_ENABLED || 'false' }}}}")
          args+=(--dart-define=CODEX_BRIDGE_DEV_MODE="${{{{ vars.CODEX_BRIDGE_DEV_MODE || 'false' }}}}")
          args+=(--dart-define=CODEX_BRIDGE_WORKBENCH_URL="${{{{ vars.CODEX_BRIDGE_WORKBENCH_URL }}}}")
          args+=(--dart-define=CODEX_APP_UPDATER_ENABLED="${{{{ vars.CODEX_APP_UPDATER_ENABLED || 'false' }}}}")
          args+=(--dart-define=CODEX_APP_UPDATER_BRIDGE_URL="${{{{ vars.CODEX_APP_UPDATER_BRIDGE_URL }}}}")
          flutter build apk --release "${{args[@]}}"
          cp build/app/outputs/flutter-apk/app-release.apk build/app/outputs/flutter-apk/{slug}.apk

      - name: Publish GitHub release
        uses: softprops/action-gh-release@v2
        with:
          files: apps/mobile/build/app/outputs/flutter-apk/{slug}.apk
          generate_release_notes: true
"""


def _generated_android_preview_release_workflow(slug: str) -> str:
    return f"""name: Android Preview Release

on:
  push:
    tags:
      - "android-preview-v*"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  build-preview-release:
    runs-on: ubuntu-latest
    env:
      APP_RUNTIME_PROFILE: preview
      API_RUNTIME: cloudflare_preview
      APP_SLUG: {slug}
      API_BASE_URL: ${{{{ vars.API_BASE_URL }}}}
      LOCAL_DATA_MODE: "false"

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"

      - uses: subosito/flutter-action@v2
        with:
          channel: stable

      - name: Validate preview release profile contract
        run: scripts/validate_preview_release_profiles.sh

      - name: Flutter dependencies
        working-directory: apps/mobile
        run: flutter pub get

      - name: Analyze
        working-directory: apps/mobile
        run: flutter analyze

      - name: Test
        working-directory: apps/mobile
        run: flutter test

      - name: Configure Android preview signing
        working-directory: apps/mobile/android
        env:
          ANDROID_KEYSTORE_BASE64: ${{{{ secrets.ANDROID_KEYSTORE_BASE64 }}}}
          ANDROID_KEY_ALIAS: ${{{{ secrets.ANDROID_KEY_ALIAS }}}}
          ANDROID_KEY_PASSWORD: ${{{{ secrets.ANDROID_KEY_PASSWORD }}}}
          ANDROID_STORE_PASSWORD: ${{{{ secrets.ANDROID_STORE_PASSWORD }}}}
          ANDROID_STORE_TYPE: ${{{{ secrets.ANDROID_STORE_TYPE || 'JKS' }}}}
        run: |
          missing=()
          for key in ANDROID_KEYSTORE_BASE64 ANDROID_KEY_ALIAS ANDROID_KEY_PASSWORD ANDROID_STORE_PASSWORD; do
            if [[ -z "${{!key}}" ]]; then
              missing+=("$key")
            fi
          done
          if (( ${{#missing[@]}} > 0 )); then
            printf 'Missing Android preview signing secret(s): %s\\n' "${{missing[*]}}" >&2
            exit 2
          fi
          printf '%s' "$ANDROID_KEYSTORE_BASE64" | base64 -d > upload-keystore.jks
          {{
            printf 'storeFile=upload-keystore.jks\\n'
            printf 'storePassword=%s\\n' "$ANDROID_STORE_PASSWORD"
            printf 'keyPassword=%s\\n' "$ANDROID_KEY_PASSWORD"
            printf 'keyAlias=%s\\n' "$ANDROID_KEY_ALIAS"
            printf 'storeType=%s\\n' "$ANDROID_STORE_TYPE"
          }} > key.properties

      - name: Build Android preview APK
        working-directory: apps/mobile
        run: |
          flutter build apk --release \\
            --dart-define=APP_RUNTIME_PROFILE="$APP_RUNTIME_PROFILE" \\
            --dart-define=API_RUNTIME="$API_RUNTIME" \\
            --dart-define=API_BASE_URL="$API_BASE_URL" \\
            --dart-define=APP_SLUG="$APP_SLUG" \\
            --dart-define=CODEX_FEEDBACK_BRIDGE_URL="${{{{ vars.CODEX_FEEDBACK_BRIDGE_URL }}}}" \\
            --dart-define=CODEX_FEEDBACK_ENABLED="${{{{ vars.CODEX_FEEDBACK_ENABLED || 'true' }}}}" \\
            --dart-define=CODEX_BRIDGE_DEV_MODE="${{{{ vars.CODEX_BRIDGE_DEV_MODE || 'true' }}}}" \\
            --dart-define=CODEX_BRIDGE_WORKBENCH_URL="${{{{ vars.CODEX_BRIDGE_WORKBENCH_URL }}}}" \\
            --dart-define=CODEX_APP_UPDATER_ENABLED="${{{{ vars.CODEX_APP_UPDATER_ENABLED || 'false' }}}}" \\
            --dart-define=CODEX_APP_UPDATER_BRIDGE_URL="${{{{ vars.CODEX_APP_UPDATER_BRIDGE_URL }}}}"
          cp build/app/outputs/flutter-apk/app-release.apk build/app/outputs/flutter-apk/{slug}.apk

      - name: Verify Android preview APK signing
        working-directory: apps/mobile
        run: |
          apk="build/app/outputs/flutter-apk/{slug}.apk"
          apksigner="$(find "$ANDROID_HOME/build-tools" -name apksigner -type f 2>/dev/null | sort -V | tail -n 1)"
          if [[ -z "$apksigner" ]]; then
            echo "apksigner is required in ANDROID_HOME/build-tools." >&2
            exit 2
          fi
          "$apksigner" verify --verbose --print-certs "$apk" | tee /tmp/apksigner.txt
          grep -q "Verified using" /tmp/apksigner.txt
          if grep -Eqi 'CN=Android Debug|Android Debug' /tmp/apksigner.txt; then
            echo "Preview APK must not be signed with Android debug certificate." >&2
            exit 2
          fi
          signer_sha256="$(awk -F': ' '/certificate SHA-256 digest/ {{ print $NF; exit }}' /tmp/apksigner.txt | tr -d '[:space:]')"
          if [[ ! "$signer_sha256" =~ ^[A-Fa-f0-9]{{64}}$ ]]; then
            echo "Could not parse signer certificate SHA256 from apksigner output." >&2
            exit 2
          fi
          echo "ANDROID_PREVIEW_SIGNER_CERT_SHA256=$signer_sha256"
          sha256sum "$apk" | tee /tmp/{slug}-apk.sha256

      - name: Publish GitHub preview release
        uses: softprops/action-gh-release@v2
        with:
          prerelease: true
          files: apps/mobile/build/app/outputs/flutter-apk/{slug}.apk
          generate_release_notes: true
"""


def _runtime_profiles_doc(
    name: str,
    frontend_strategy: str = "flutter",
) -> str:
    if frontend_strategy == "svelte":
        return f"""# Runtime Profiles

`{name}` uses the Svelte web-first strategy. Runtime profile metadata is carried
through Vite environment variables and the Cloudflare Preview API.

## Profiles

- `VITE_APP_RUNTIME_PROFILE=preview`: default Initial Preview Release profile.
  Requires `VITE_API_RUNTIME=cloudflare_preview` and
  `VITE_API_BASE_URL=https://preview.nienfos.com/<slug>/api`.
- `VITE_APP_RUNTIME_PROFILE=staging`: internal pre-production web/API path.
- `VITE_APP_RUNTIME_PROFILE=real`: productive web/API path after explicit
  promotion.
- `VITE_APP_RUNTIME_PROFILE=mock`: opt-in local demo path only, not an Initial
  Preview Release.

## Release Shape

- Initial preview is web/API only.
- Native release tags, package signing, mobile marketplace readiness, and Codex
  Mobile catalog installability are not part of the Svelte strategy.
- A future wrapper strategy must define its own package/signing/catalog contract
  before claiming installability.

Run before web preview release validation:

```bash
VITE_APP_RUNTIME_PROFILE=preview \\
VITE_API_RUNTIME=cloudflare_preview \\
VITE_API_BASE_URL=https://preview.nienfos.com/<slug>/api \\
npm run validate:preview
```
"""
    return f"""# Runtime Profiles

`{name}` must keep mock/demo and productive runtime paths separate.

## Profiles

- `APP_RUNTIME_PROFILE=real`: default for productive releases. Requires
  `API_BASE_URL`, real backend, real auth, updater metadata with
  `mock_or_demo=false`, and hidden Workbench/dev tools.
- `APP_RUNTIME_PROFILE=staging`: real backend path for pre-production testing.
- `APP_RUNTIME_PROFILE=preview`: web preview path against the shared
  Cloudflare Preview API runtime. This is the default first release profile and
  uses `https://preview.nienfos.com/<slug>/api`.
- `APP_RUNTIME_PROFILE=mock`: opt-in demo path. Does not require backend and may
  show seed role selection.

## Release Tags

- Initial preview: `android-preview-vX.Y.Z-build.N`
- Productive promotion: `android-vX.Y.Z-build.N`
- Mock/demo: `android-mock-vX.Y.Z-build.N` or `android-local-vX.Y.Z-build.N`

Mock/demo releases are never part of the default initial release. They require an
explicit opt-in request and must use the visible mock/local tag prefixes above.

Run before any release:

```bash
APP_RELEASE_TAG=<tag> APP_RUNTIME_PROFILE=<profile> API_BASE_URL=<url> scripts/validate_release_profiles.sh
```
"""


def _store_checklist_doc(*, store: str, frontend_strategy: str = "flutter") -> str:
    if frontend_strategy == "svelte":
        return """# Native Store Checklist

Status: `not_applicable_web_only`.

This project uses the Svelte web-first strategy. It does not produce a mobile
binary, does not target native store submission, and must not be reported as
ready for a native store release.

Native store readiness requires a future explicit wrapper strategy with its own
build, signing, release, checksum, and installability validation contract.
"""
    return _placeholder_doc(
        f"{store} Checklist",
        f"{store} release readiness items and pending credentials will be tracked here.",
    )


def _release_contracts_yaml(slug: str, frontend_strategy: str = "flutter") -> str:
    is_svelte = frontend_strategy == "svelte"
    return _to_yaml(
        {
            "schema_version": 1,
            "source_app": slug,
            "frontend_strategy": frontend_strategy,
            "frontend_capabilities": {
                "source_root": "apps/web" if is_svelte else "apps/mobile",
                "project_kind": "web" if is_svelte else "mobile_web",
                "web_build_output": f"build/web-preview/{slug}",
                "supports_android_preview_apk": not is_svelte,
                "supports_bridge_installable_app": not is_svelte,
                "supports_workbench_apk_entry": False,
                "cloudflare_preview_required": True,
                "d1_preview_required": True,
                "release_channel": "prerelease",
                "production_ready": False,
                "mock_or_demo": False,
            },
            "runtime_profiles": {
                "default": "preview",
                "allowed": ["mock", "preview", "real", "staging"],
                "env": "VITE_APP_RUNTIME_PROFILE" if is_svelte else "APP_RUNTIME_PROFILE",
                "api_runtime_env": "VITE_API_RUNTIME" if is_svelte else "API_RUNTIME",
                "preview_api_env": "VITE_API_BASE_URL" if is_svelte else "API_BASE_URL",
            },
            "initial_preview_release": {
                "tag_patterns": [] if is_svelte else ["android-preview-v*"],
                "runtime_profile": "preview",
                "api_runtime": "cloudflare_preview",
                "api_base_url": f"https://preview.nienfos.com/{slug}/api",
                "mock_or_demo": False,
                "backend_required": True,
                "data_persistence": "cloudflare_d1",
                "required_gates": (
                    [
                        "cloudflare_health",
                        "preview_api_smoke",
                        "github_preview_apk_release",
                        "codex_mobile_apps_registration",
                    ]
                    if not is_svelte
                    else [
                        "cloudflare_health",
                        "preview_api_smoke",
                        "svelte_web_build_validation",
                    ]
                ),
            },
            "mock_release": {
                "tag_patterns": [] if is_svelte else ["android-mock-v*", "android-local-v*"],
                "runtime_profile": "mock",
                "mock_or_demo": True,
                "backend_required": False,
                "required": False,
                "opt_in": True,
                "seed_role_selector": True,
            },
            "productive_release": {
                "tag_patterns": [] if is_svelte else ["android-v*"],
                "runtime_profile": "real",
                "mock_or_demo": False,
                "backend_required": True,
                "promotion_metadata": "release/promotion-contract.json",
                "requires_preview_success": True,
                "must_not_reuse_preview_tag": not is_svelte,
                "forbidden": [
                    "LOCAL_DATA_MODE=true",
                    "localhost API_BASE_URL",
                    "placeholder API_BASE_URL",
                    "visible seed users",
                    "visible Workbench UI",
                    "hardcoded demo data",
                    *(
                        [
                            "Android APK claim without wrapper strategy",
                            "Codex Mobile catalog claim without wrapper strategy",
                        ]
                        if is_svelte
                        else []
                    ),
                ],
            },
            "preview_to_production_promotion": {
                "artifact": "release/promotion-contract.json",
                "initial_preview_is_production": False,
                "preview_tag_pattern": None if is_svelte else "android-preview-v*",
                "production_tag_pattern": None if is_svelte else "android-v*",
                "mock_tag_patterns": [] if is_svelte else ["android-mock-v*", "android-local-v*"],
            },
            "cloudflare_cost_posture": {
                "artifact": "release/cloudflare-cost-posture.json",
                "validation_script": "scripts/validate_cloudflare_cost_posture.sh",
                "default_policy": "free_compatible",
                "paid_resources_require_operator_confirmation": True,
            },
            "workbench": {
                "required": True,
                "launch_owner": "codex_mobile_bridge",
                "product_navigation_allowed": False,
                "visible_profiles": [],
                "hidden_profiles": ["real"],
                "identity_file": "codex-bridge.yaml",
                "docs": "docs/workbench.md",
                "artifact_sources": [
                    ".sdd/spec-index.yaml",
                    ".sdd/diagram-index.yaml",
                    "specs/",
                    "architecture/",
                    "release/preview-runtime.json",
                ],
            },
            "codex_mobile_catalog": {
                "required": not is_svelte,
                "registration_script": None if is_svelte else "scripts/register_installable_app.sh",
                "bridge_endpoint": "/installable-apps",
                "verification_endpoint": "/installable-apps/{sourceApp}",
                "requires_apk_url": not is_svelte,
            },
            "web_preview": {
                "required": True,
                "stable_url": f"https://preview.nienfos.com/{slug}",
                "manifest": "deploy/web-preview/web-preview-manifest.yaml",
                "build_script": "scripts/build_web_preview.sh",
                "validation_script": "scripts/validate_web_preview.sh",
                "api_runtime": "cloudflare_preview",
                "default_runtime_profile": "preview",
                "api_base_url": f"https://preview.nienfos.com/{slug}/api",
                "cloudflare_resources": {
                    "worker_name": "nienfos-preview-runtime",
                    "pages_project": "nienfos-preview-web",
                    "d1_database": "nienfos-preview",
                    "r2_bucket": None,
                },
            },
        }
    )


def _cloudflare_cost_posture_json(slug: str) -> str:
    return (
        json.dumps(
            {
                "schemaVersion": 1,
                "sourceApp": slug,
                "policy": "free_compatible",
                "paidResourcesAllowed": False,
                "operatorConfirmationRequiredForPaid": True,
                "operatorConfirmationEnv": "CLOUDFLARE_PAID_RESOURCES_CONFIRMED",
                "resources": [
                    {"type": "worker", "name": "nienfos-preview-runtime", "paid": False},
                    {"type": "d1", "name": f"{slug}-preview", "paid": False},
                    {"type": "pages", "name": "nienfos-preview-web", "paid": False},
                ],
                "blockedPaidResourceTypes": ["r2", "durable_objects", "queues"],
                "manualOverride": {
                    "env": "CLOUDFLARE_PAID_RESOURCES_CONFIRMED",
                    "requiredValue": "true",
                    "reasonEnv": "CLOUDFLARE_PAID_RESOURCES_REASON",
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _promotion_contract_json(
    slug: str,
    name: str,
    frontend_strategy: str = "flutter",
) -> str:
    is_svelte = frontend_strategy == "svelte"
    if is_svelte:
        payload = {
            "schemaVersion": 1,
            "sourceApp": slug,
            "displayName": name,
            "frontendStrategy": "svelte",
            "initialPreview": {
                "productionReady": False,
                "releaseChannel": "prerelease",
                "tagPattern": None,
                "runtimeProfile": "preview",
                "apiRuntime": "cloudflare_preview",
                "apiBaseUrl": f"https://preview.nienfos.com/{slug}/api",
                "webPreviewUrl": f"https://preview.nienfos.com/{slug}",
                "dataPersistence": "cloudflare_d1",
                "mockOrDemo": False,
                "installableAndroid": False,
                "bridgeRegistrationRequired": False,
            },
            "productionPromotion": {
                "releaseChannel": "production",
                "tagPattern": None,
                "runtimeProfile": "real",
                "requiresSeparateBackend": True,
                "requiresProductionSigning": False,
                "requiresPreviewGates": [
                    "cloudflare_web_preview_health",
                    "preview_api_smoke",
                    "svelte_web_build_validation",
                ],
                "requiresProductionGates": [
                    "production_backend_health",
                    "production_api_base_url",
                    "mock_or_demo_false",
                ],
                "forbidden": [
                    "placeholder API_BASE_URL",
                    "localhost API_BASE_URL",
                    "android APK claim without wrapper strategy",
                    "Codex Mobile catalog claim without wrapper strategy",
                ],
            },
            "mockDemo": {
                "optInOnly": True,
                "tagPatterns": [],
                "mustNotPromoteToProduction": True,
            },
        }
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"
    return (
        json.dumps(
            {
                "schemaVersion": 1,
                "sourceApp": slug,
                "displayName": name,
                "initialPreview": {
                    "productionReady": False,
                    "releaseChannel": "prerelease",
                    "tagPattern": "android-preview-v*",
                    "runtimeProfile": "preview",
                    "apiRuntime": "cloudflare_preview",
                    "apiBaseUrl": f"https://preview.nienfos.com/{slug}/api",
                    "dataPersistence": "cloudflare_d1",
                    "mockOrDemo": False,
                },
                "productionPromotion": {
                    "releaseChannel": "production",
                    "tagPattern": "android-v*",
                    "runtimeProfile": "real",
                    "requiresSeparateBackend": True,
                    "requiresProductionSigning": True,
                    "requiresPreviewGates": [
                        "cloudflare_preview_health",
                        "preview_api_smoke",
                        "android_preview_apk_release",
                        "bridge_preview_registration",
                    ],
                    "requiresProductionGates": [
                        "production_backend_health",
                        "production_api_base_url",
                        "production_signing_key",
                        "mock_or_demo_false",
                        "app_update_channel_production",
                    ],
                    "forbidden": [
                        "android-preview-v* tag reuse",
                        "android-mock-v* tag reuse",
                        "android-local-v* tag reuse",
                        "LOCAL_DATA_MODE=true",
                        "placeholder API_BASE_URL",
                        "localhost API_BASE_URL",
                    ],
                },
                "mockDemo": {
                    "optInOnly": True,
                    "tagPatterns": ["android-mock-v*", "android-local-v*"],
                    "mustNotPromoteToProduction": True,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _preview_signing_policy_json(
    slug: str,
    frontend_strategy: str = "flutter",
) -> str:
    if frontend_strategy == "svelte":
        return (
            json.dumps(
                {
                    "schemaVersion": 1,
                    "sourceApp": slug,
                    "frontendStrategy": "svelte",
                    "releaseChannel": "prerelease",
                    "releaseTagPattern": None,
                    "defaultSigningMode": "not_applicable_web_only",
                    "signingRequired": False,
                    "installableAndroid": False,
                    "bridgeRegistrationRequired": False,
                    "productionReady": False,
                    "mockOrDemo": False,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
    return (
        json.dumps(
            {
                "schemaVersion": 1,
                "sourceApp": slug,
                "releaseChannel": "prerelease",
                "releaseTagPattern": "android-preview-v*",
                "defaultSigningMode": "preview",
                "productionReady": False,
                "mockOrDemo": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _cloudflare_cost_posture_check_script() -> str:
    return r'''#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'cloudflare cost posture blocked: %s\n' "$*" >&2
  exit 2
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT="$ROOT_DIR/release/cloudflare-cost-posture.json"
[[ -f "$REPORT" ]] || fail "missing release/cloudflare-cost-posture.json"

python3 - "$REPORT" <<'PY'
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if not isinstance(payload, dict):
    raise SystemExit("release/cloudflare-cost-posture.json must be a JSON object")

resources = payload.get("resources") or []
paid = [
    item for item in resources
    if isinstance(item, dict) and item.get("paid") is True
]
paid_allowed = payload.get("paidResourcesAllowed") is True
confirmed = os.environ.get("CLOUDFLARE_PAID_RESOURCES_CONFIRMED", "").lower() == "true"
reason = os.environ.get("CLOUDFLARE_PAID_RESOURCES_REASON", "").strip()

if paid and not paid_allowed:
    names = ", ".join(str(item.get("name") or item.get("type") or "unknown") for item in paid)
    raise SystemExit(f"paid resources present but paidResourcesAllowed=false: {names}")
if paid and not confirmed:
    raise SystemExit(
        "paid Cloudflare resources require CLOUDFLARE_PAID_RESOURCES_CONFIRMED=true"
    )
if paid and not reason:
    raise SystemExit("paid Cloudflare resources require CLOUDFLARE_PAID_RESOURCES_REASON")

print("cloudflare cost posture ok")
PY
'''


def _preview_runtime_json(
    slug: str,
    name: str,
    frontend_strategy: str = "flutter",
) -> str:
    is_svelte = frontend_strategy == "svelte"
    payload = {
        "schemaVersion": 1,
        "sourceApp": slug,
        "displayName": f"{name} Preview",
        "frontendStrategy": frontend_strategy,
        "frontendSourceRoot": "apps/web" if is_svelte else "apps/mobile",
        "frontendProjectKind": "web" if is_svelte else "mobile_web",
        "webBuildOutput": f"build/web-preview/{slug}",
        "previewUrl": f"https://preview.nienfos.com/{slug}",
        "apiBaseUrl": f"https://preview.nienfos.com/{slug}/api",
        "runtimeProfile": "preview",
        "apiRuntime": "cloudflare_preview",
        "releaseChannel": "prerelease",
        "productionReady": False,
        "mockOrDemo": False,
        "backendRequired": True,
        "dataPersistence": "cloudflare_d1",
        "cloudflarePreviewRequired": True,
        "d1PreviewRequired": True,
        "installableAndroid": not is_svelte,
        "bridgeRegistrationRequired": not is_svelte,
        "workbenchApkEntryRequired": False,
        "workbenchLaunchOwner": "codex_mobile_bridge",
        "productWorkbenchNavigationAllowed": False,
        "releaseMetadata": {
            "initialPreviewRelease": True,
            "runtimeProfile": "preview",
            "apiRuntime": "cloudflare_preview",
            "frontendStrategy": frontend_strategy,
        },
    }
    if is_svelte:
        payload["bridge"] = {
            "endpoint": "/installable-apps",
            "verificationEndpoint": None,
            "requiresApkUrl": False,
        }
    else:
        payload.update(
            {
                "releaseTagPattern": "android-preview-v*",
                "apkAssetPattern": f"{slug}*.apk",
                "latestAssetName": f"{slug}.apk",
                "bridge": {
                    "endpoint": "/installable-apps",
                    "verificationEndpoint": f"/installable-apps/{slug}",
                    "requiresApkUrl": True,
                },
            }
        )
        payload["releaseMetadata"].update(
            {
                "releaseTagPattern": "android-preview-v*",
                "latestAssetName": f"{slug}.apk",
            }
        )
    return (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _svelte_files(name: str, slug: str) -> dict[str, str]:
    package_name = _npm_package_name(slug)
    return {
        "apps/web/package.json": _svelte_package_json(package_name),
        "apps/web/package-lock.json": _svelte_package_lock_json(package_name),
        "apps/web/index.html": _svelte_index_html(name),
        "apps/web/vite.config.ts": _svelte_vite_config_ts(),
        "apps/web/src/main.ts": _svelte_main_ts(),
        "apps/web/src/App.svelte": _svelte_app_svelte(name),
        "apps/web/src/config.ts": _svelte_config_ts(slug),
        "apps/web/test/preview-config.test.mjs": _svelte_preview_config_test_mjs(slug),
        "apps/web/README.md": _svelte_readme(name, slug),
    }


def _npm_package_name(slug: str) -> str:
    value = slug.lower().replace("_", "-")
    value = re.sub(r"[^a-z0-9-]+", "-", value).strip("-")
    if not value:
        value = "project-factory-app"
    if value[0].isdigit():
        value = f"app-{value}"
    return value


def _svelte_package_json(package_name: str) -> str:
    return (
        json.dumps(
            {
                "name": package_name,
                "private": True,
                "version": "0.1.0",
                "type": "module",
                "scripts": {
                    "dev": "vite --host 0.0.0.0",
                    "lint": "node test/preview-config.test.mjs --static",
                    "test": "node test/preview-config.test.mjs",
                    "validate:preview": "node test/preview-config.test.mjs --preview",
                    "build": "vite build",
                    "preview": "vite preview --host 0.0.0.0",
                },
                "dependencies": {
                    "@sveltejs/vite-plugin-svelte": "3.1.2",
                    "svelte": "4.2.19",
                    "vite": "5.4.21",
                },
                "devDependencies": {},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _svelte_package_lock_json(package_name: str) -> str:
    template = r'''{
  "name": "__PACKAGE_NAME__",
  "version": "0.1.0",
  "lockfileVersion": 3,
  "requires": true,
  "packages": {
    "": {
      "name": "__PACKAGE_NAME__",
      "version": "0.1.0",
      "dependencies": {
        "@sveltejs/vite-plugin-svelte": "3.1.2",
        "svelte": "4.2.19",
        "vite": "5.4.21"
      },
      "devDependencies": {}
    },
    "node_modules/@ampproject/remapping": {
      "version": "2.3.0",
      "resolved": "https://registry.npmjs.org/@ampproject/remapping/-/remapping-2.3.0.tgz",
      "integrity": "sha512-30iZtAPgz+LTIYoeivqYo853f02jBYSd5uGnGpkFV0M3xOt9aN73erkgYAmZU43x4VfqcnLxW9Kpg3R5LC4YYw==",
      "dependencies": {
        "@jridgewell/gen-mapping": "^0.3.5",
        "@jridgewell/trace-mapping": "^0.3.24"
      },
      "engines": {
        "node": ">=6.0.0"
      }
    },
    "node_modules/@esbuild/aix-ppc64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/aix-ppc64/-/aix-ppc64-0.21.5.tgz",
      "integrity": "sha512-1SDgH6ZSPTlggy1yI6+Dbkiz8xzpHJEVAlF/AM1tHPLsf5STom9rwtjE4hKAF20FfXXNTFqEYXyJNWh1GiZedQ==",
      "cpu": [
        "ppc64"
      ],
      "optional": true,
      "os": [
        "aix"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/android-arm": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/android-arm/-/android-arm-0.21.5.tgz",
      "integrity": "sha512-vCPvzSjpPHEi1siZdlvAlsPxXl7WbOVUBBAowWug4rJHb68Ox8KualB+1ocNvT5fjv6wpkX6o/iEpbDrf68zcg==",
      "cpu": [
        "arm"
      ],
      "optional": true,
      "os": [
        "android"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/android-arm64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/android-arm64/-/android-arm64-0.21.5.tgz",
      "integrity": "sha512-c0uX9VAUBQ7dTDCjq+wdyGLowMdtR/GoC2U5IYk/7D1H1JYC0qseD7+11iMP2mRLN9RcCMRcjC4YMclCzGwS/A==",
      "cpu": [
        "arm64"
      ],
      "optional": true,
      "os": [
        "android"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/android-x64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/android-x64/-/android-x64-0.21.5.tgz",
      "integrity": "sha512-D7aPRUUNHRBwHxzxRvp856rjUHRFW1SdQATKXH2hqA0kAZb1hKmi02OpYRacl0TxIGz/ZmXWlbZgjwWYaCakTA==",
      "cpu": [
        "x64"
      ],
      "optional": true,
      "os": [
        "android"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/darwin-arm64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/darwin-arm64/-/darwin-arm64-0.21.5.tgz",
      "integrity": "sha512-DwqXqZyuk5AiWWf3UfLiRDJ5EDd49zg6O9wclZ7kUMv2WRFr4HKjXp/5t8JZ11QbQfUS6/cRCKGwYhtNAY88kQ==",
      "cpu": [
        "arm64"
      ],
      "optional": true,
      "os": [
        "darwin"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/darwin-x64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/darwin-x64/-/darwin-x64-0.21.5.tgz",
      "integrity": "sha512-se/JjF8NlmKVG4kNIuyWMV/22ZaerB+qaSi5MdrXtd6R08kvs2qCN4C09miupktDitvh8jRFflwGFBQcxZRjbw==",
      "cpu": [
        "x64"
      ],
      "optional": true,
      "os": [
        "darwin"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/freebsd-arm64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/freebsd-arm64/-/freebsd-arm64-0.21.5.tgz",
      "integrity": "sha512-5JcRxxRDUJLX8JXp/wcBCy3pENnCgBR9bN6JsY4OmhfUtIHe3ZW0mawA7+RDAcMLrMIZaf03NlQiX9DGyB8h4g==",
      "cpu": [
        "arm64"
      ],
      "optional": true,
      "os": [
        "freebsd"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/freebsd-x64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/freebsd-x64/-/freebsd-x64-0.21.5.tgz",
      "integrity": "sha512-J95kNBj1zkbMXtHVH29bBriQygMXqoVQOQYA+ISs0/2l3T9/kj42ow2mpqerRBxDJnmkUDCaQT/dfNXWX/ZZCQ==",
      "cpu": [
        "x64"
      ],
      "optional": true,
      "os": [
        "freebsd"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/linux-arm": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/linux-arm/-/linux-arm-0.21.5.tgz",
      "integrity": "sha512-bPb5AHZtbeNGjCKVZ9UGqGwo8EUu4cLq68E95A53KlxAPRmUyYv2D6F0uUI65XisGOL1hBP5mTronbgo+0bFcA==",
      "cpu": [
        "arm"
      ],
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/linux-arm64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/linux-arm64/-/linux-arm64-0.21.5.tgz",
      "integrity": "sha512-ibKvmyYzKsBeX8d8I7MH/TMfWDXBF3db4qM6sy+7re0YXya+K1cem3on9XgdT2EQGMu4hQyZhan7TeQ8XkGp4Q==",
      "cpu": [
        "arm64"
      ],
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/linux-ia32": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/linux-ia32/-/linux-ia32-0.21.5.tgz",
      "integrity": "sha512-YvjXDqLRqPDl2dvRODYmmhz4rPeVKYvppfGYKSNGdyZkA01046pLWyRKKI3ax8fbJoK5QbxblURkwK/MWY18Tg==",
      "cpu": [
        "ia32"
      ],
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/linux-loong64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/linux-loong64/-/linux-loong64-0.21.5.tgz",
      "integrity": "sha512-uHf1BmMG8qEvzdrzAqg2SIG/02+4/DHB6a9Kbya0XDvwDEKCoC8ZRWI5JJvNdUjtciBGFQ5PuBlpEOXQj+JQSg==",
      "cpu": [
        "loong64"
      ],
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/linux-mips64el": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/linux-mips64el/-/linux-mips64el-0.21.5.tgz",
      "integrity": "sha512-IajOmO+KJK23bj52dFSNCMsz1QP1DqM6cwLUv3W1QwyxkyIWecfafnI555fvSGqEKwjMXVLokcV5ygHW5b3Jbg==",
      "cpu": [
        "mips64el"
      ],
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/linux-ppc64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/linux-ppc64/-/linux-ppc64-0.21.5.tgz",
      "integrity": "sha512-1hHV/Z4OEfMwpLO8rp7CvlhBDnjsC3CttJXIhBi+5Aj5r+MBvy4egg7wCbe//hSsT+RvDAG7s81tAvpL2XAE4w==",
      "cpu": [
        "ppc64"
      ],
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/linux-riscv64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/linux-riscv64/-/linux-riscv64-0.21.5.tgz",
      "integrity": "sha512-2HdXDMd9GMgTGrPWnJzP2ALSokE/0O5HhTUvWIbD3YdjME8JwvSCnNGBnTThKGEB91OZhzrJ4qIIxk/SBmyDDA==",
      "cpu": [
        "riscv64"
      ],
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/linux-s390x": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/linux-s390x/-/linux-s390x-0.21.5.tgz",
      "integrity": "sha512-zus5sxzqBJD3eXxwvjN1yQkRepANgxE9lgOW2qLnmr8ikMTphkjgXu1HR01K4FJg8h1kEEDAqDcZQtbrRnB41A==",
      "cpu": [
        "s390x"
      ],
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/linux-x64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/linux-x64/-/linux-x64-0.21.5.tgz",
      "integrity": "sha512-1rYdTpyv03iycF1+BhzrzQJCdOuAOtaqHTWJZCWvijKD2N5Xu0TtVC8/+1faWqcP9iBCWOmjmhoH94dH82BxPQ==",
      "cpu": [
        "x64"
      ],
      "optional": true,
      "os": [
        "linux"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/netbsd-x64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/netbsd-x64/-/netbsd-x64-0.21.5.tgz",
      "integrity": "sha512-Woi2MXzXjMULccIwMnLciyZH4nCIMpWQAs049KEeMvOcNADVxo0UBIQPfSmxB3CWKedngg7sWZdLvLczpe0tLg==",
      "cpu": [
        "x64"
      ],
      "optional": true,
      "os": [
        "netbsd"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/openbsd-x64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/openbsd-x64/-/openbsd-x64-0.21.5.tgz",
      "integrity": "sha512-HLNNw99xsvx12lFBUwoT8EVCsSvRNDVxNpjZ7bPn947b8gJPzeHWyNVhFsaerc0n3TsbOINvRP2byTZ5LKezow==",
      "cpu": [
        "x64"
      ],
      "optional": true,
      "os": [
        "openbsd"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/sunos-x64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/sunos-x64/-/sunos-x64-0.21.5.tgz",
      "integrity": "sha512-6+gjmFpfy0BHU5Tpptkuh8+uw3mnrvgs+dSPQXQOv3ekbordwnzTVEb4qnIvQcYXq6gzkyTnoZ9dZG+D4garKg==",
      "cpu": [
        "x64"
      ],
      "optional": true,
      "os": [
        "sunos"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/win32-arm64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/win32-arm64/-/win32-arm64-0.21.5.tgz",
      "integrity": "sha512-Z0gOTd75VvXqyq7nsl93zwahcTROgqvuAcYDUr+vOv8uHhNSKROyU961kgtCD1e95IqPKSQKH7tBTslnS3tA8A==",
      "cpu": [
        "arm64"
      ],
      "optional": true,
      "os": [
        "win32"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/win32-ia32": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/win32-ia32/-/win32-ia32-0.21.5.tgz",
      "integrity": "sha512-SWXFF1CL2RVNMaVs+BBClwtfZSvDgtL//G/smwAc5oVK/UPu2Gu9tIaRgFmYFFKrmg3SyAjSrElf0TiJ1v8fYA==",
      "cpu": [
        "ia32"
      ],
      "optional": true,
      "os": [
        "win32"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@esbuild/win32-x64": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/@esbuild/win32-x64/-/win32-x64-0.21.5.tgz",
      "integrity": "sha512-tQd/1efJuzPC6rCFwEvLtci/xNFcTZknmXs98FYDfGE4wP9ClFV98nyKrzJKVPMhdDnjzLhdUyMX4PsQAPjwIw==",
      "cpu": [
        "x64"
      ],
      "optional": true,
      "os": [
        "win32"
      ],
      "engines": {
        "node": ">=12"
      }
    },
    "node_modules/@jridgewell/gen-mapping": {
      "version": "0.3.13",
      "resolved": "https://registry.npmjs.org/@jridgewell/gen-mapping/-/gen-mapping-0.3.13.tgz",
      "integrity": "sha512-2kkt/7niJ6MgEPxF0bYdQ6etZaA+fQvDcLKckhy1yIQOzaoKjBBjSj63/aLVjYE3qhRt5dvM+uUyfCg6UKCBbA==",
      "dependencies": {
        "@jridgewell/sourcemap-codec": "^1.5.0",
        "@jridgewell/trace-mapping": "^0.3.24"
      }
    },
    "node_modules/@jridgewell/resolve-uri": {
      "version": "3.1.2",
      "resolved": "https://registry.npmjs.org/@jridgewell/resolve-uri/-/resolve-uri-3.1.2.tgz",
      "integrity": "sha512-bRISgCIjP20/tbWSPWMEi54QVPRZExkuD9lJL+UIxUKtwVJA8wW1Trb1jMs1RFXo1CBTNZ/5hpC9QvmKWdopKw==",
      "engines": {
        "node": ">=6.0.0"
      }
    },
    "node_modules/@jridgewell/sourcemap-codec": {
      "version": "1.5.5",
      "resolved": "https://registry.npmjs.org/@jridgewell/sourcemap-codec/-/sourcemap-codec-1.5.5.tgz",
      "integrity": "sha512-cYQ9310grqxueWbl+WuIUIaiUaDcj7WOq5fVhEljNVgRfOUhY9fy2zTvfoqWsnebh8Sl70VScFbICvJnLKB0Og=="
    },
    "node_modules/@jridgewell/trace-mapping": {
      "version": "0.3.31",
      "resolved": "https://registry.npmjs.org/@jridgewell/trace-mapping/-/trace-mapping-0.3.31.tgz",
      "integrity": "sha512-zzNR+SdQSDJzc8joaeP8QQoCQr8NuYx2dIIytl1QeBEZHJ9uW6hebsrYgbz8hJwUQao3TWCMtmfV8Nu1twOLAw==",
      "dependencies": {
        "@jridgewell/resolve-uri": "^3.1.0",
        "@jridgewell/sourcemap-codec": "^1.4.14"
      }
    },
    "node_modules/@rollup/rollup-android-arm-eabi": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-android-arm-eabi/-/rollup-android-arm-eabi-4.62.2.tgz",
      "integrity": "sha512-6o7ZLZK+BeenkZCFNDXqpbjw9bD6nuWonvS/lwQJp7NoVVxm6p3qE7qQ5jGuBjiFsgvqjD8mZAU5oWxTmbOeOg==",
      "cpu": [
        "arm"
      ],
      "optional": true,
      "os": [
        "android"
      ]
    },
    "node_modules/@rollup/rollup-android-arm64": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-android-arm64/-/rollup-android-arm64-4.62.2.tgz",
      "integrity": "sha512-BaH7BllCACHoH1LguOU56UItGfUWjujlO65kS9LAodViaN4bwIKd7oeW/ZHJ/4ljr/7MIiENnNy3HJ0zXv8Zkw==",
      "cpu": [
        "arm64"
      ],
      "optional": true,
      "os": [
        "android"
      ]
    },
    "node_modules/@rollup/rollup-darwin-arm64": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-darwin-arm64/-/rollup-darwin-arm64-4.62.2.tgz",
      "integrity": "sha512-v39RCCvj4He82I9sFmk+M1VZ0PLM9sfsLVikjfx2hYBNALhrrOR2D3JjQA6AhlaSOgcR+RzrKY7e1+bT6SUO/A==",
      "cpu": [
        "arm64"
      ],
      "optional": true,
      "os": [
        "darwin"
      ]
    },
    "node_modules/@rollup/rollup-darwin-x64": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-darwin-x64/-/rollup-darwin-x64-4.62.2.tgz",
      "integrity": "sha512-yl0y2vq3S3lHeuXhEdss6TWfKW8vkujImO12tn4ZkG/4oghr09LvdYm2RElVjokTQiUvDUGXLGsYeLqUMCKpGA==",
      "cpu": [
        "x64"
      ],
      "optional": true,
      "os": [
        "darwin"
      ]
    },
    "node_modules/@rollup/rollup-freebsd-arm64": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-freebsd-arm64/-/rollup-freebsd-arm64-4.62.2.tgz",
      "integrity": "sha512-tT4pvt4qXD+vEoezupCWi+a1F0vvDiksiHc+PxRlYTOH1I6/X4id9jPxTP+Fg+545euaFT1jJVs4CEdHZAU1vw==",
      "cpu": [
        "arm64"
      ],
      "optional": true,
      "os": [
        "freebsd"
      ]
    },
    "node_modules/@rollup/rollup-freebsd-x64": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-freebsd-x64/-/rollup-freebsd-x64-4.62.2.tgz",
      "integrity": "sha512-6nU5F2wCW+qvCBhTn1pdIU3bzsIoF7EUwsCDRxilWGprQR6yd508YnH9+OKFCwpfS8pjZqDUmnCAr7exax0XCg==",
      "cpu": [
        "x64"
      ],
      "optional": true,
      "os": [
        "freebsd"
      ]
    },
    "node_modules/@rollup/rollup-linux-arm-gnueabihf": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-arm-gnueabihf/-/rollup-linux-arm-gnueabihf-4.62.2.tgz",
      "integrity": "sha512-n1GJHPOvpIfhi3TmrCeh6S6URt9BFCt0KQE3qvexyGCTAKpR4Lg+eWvNZEqu7epxwus/8ElT3hacYEucm49SZg==",
      "cpu": [
        "arm"
      ],
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-arm-musleabihf": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-arm-musleabihf/-/rollup-linux-arm-musleabihf-4.62.2.tgz",
      "integrity": "sha512-JqgflS8wEB+UXV/vS1RpRbifGBeN4D5lz8D8oOFbFZw4vedvdOgCFAjfBmIMdW3yL10XpQQ0Ambepw6MXrhOnA==",
      "cpu": [
        "arm"
      ],
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-arm64-gnu": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-arm64-gnu/-/rollup-linux-arm64-gnu-4.62.2.tgz",
      "integrity": "sha512-wnFJkogWvN4jm/hQRF2UBaeUmk20j5+DmHvoyWii2b8HJDyvz1MF2OU/6ynXt2KR63rbZLWkFpoytpdc/yBuSA==",
      "cpu": [
        "arm64"
      ],
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-arm64-musl": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-arm64-musl/-/rollup-linux-arm64-musl-4.62.2.tgz",
      "integrity": "sha512-HVu2bp0zhvJ8xHEV9+UUs7S90VadmBSY3LcIMvozbPo4AuMGDWlz3ymHLHZPX4hR67TKTt8Qp5PJ5RBg/i+RMQ==",
      "cpu": [
        "arm64"
      ],
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-loong64-gnu": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-loong64-gnu/-/rollup-linux-loong64-gnu-4.62.2.tgz",
      "integrity": "sha512-mQqqAV8QaoSgr9I2fKDLY2BAVvmKjWoGiu/cSYQonsLvtqwEn1E4QYfnCOcp5zoEqNhsDYin1s6jx/VJmrxlZg==",
      "cpu": [
        "loong64"
      ],
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-loong64-musl": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-loong64-musl/-/rollup-linux-loong64-musl-4.62.2.tgz",
      "integrity": "sha512-IxKLoxCQ2IWi6bT2akyDUBGsOImDKB+sPp4EsTmwFQ/fMwpCKm8uLSSgP/Kx/QYUgKis6SEZ5/Nlhup0DIA0PQ==",
      "cpu": [
        "loong64"
      ],
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-ppc64-gnu": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-ppc64-gnu/-/rollup-linux-ppc64-gnu-4.62.2.tgz",
      "integrity": "sha512-Mk5ha2RQSgyFfmYYLkBpPnUk8D8FriBxesO1u9O75X0mHgXL1UQcH5Itl2lurWL2tj0RxV9b9tJgipac0hRY9A==",
      "cpu": [
        "ppc64"
      ],
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-ppc64-musl": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-ppc64-musl/-/rollup-linux-ppc64-musl-4.62.2.tgz",
      "integrity": "sha512-CjvEnqJL/0/TQ3TXX3OPIJ/kmBellrWd4heXUmHeJlTnmwjKpSJzoehLaL6Xk0ZnMHBu9dZuFADNOrtjF4v+2w==",
      "cpu": [
        "ppc64"
      ],
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-riscv64-gnu": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-riscv64-gnu/-/rollup-linux-riscv64-gnu-4.62.2.tgz",
      "integrity": "sha512-1SiZbzwdkaDURsew/tSOrooKiYy7EQGT6m8ufavAi9NEyQb/6VuIxFXAL1fqa4iZe3g4NbNk4P7J32z2tw5Mgg==",
      "cpu": [
        "riscv64"
      ],
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-riscv64-musl": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-riscv64-musl/-/rollup-linux-riscv64-musl-4.62.2.tgz",
      "integrity": "sha512-nQts12zJ3NQRoE6uYljOH89v7szzLDvG2JD/vsX+vGXU8w/At1GowTZ5/7qeFQ8m7L55rpR8Okugnuo5bgjy2Q==",
      "cpu": [
        "riscv64"
      ],
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-s390x-gnu": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-s390x-gnu/-/rollup-linux-s390x-gnu-4.62.2.tgz",
      "integrity": "sha512-E9/ll019jhPIJgpzfZoIkBGhcz+kKNgVWYRY0zr9srBdPPFVpvOKW8VaJKUbeK+eZXyQF9ltME+Kk6affeaPgg==",
      "cpu": [
        "s390x"
      ],
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-x64-gnu": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-x64-gnu/-/rollup-linux-x64-gnu-4.62.2.tgz",
      "integrity": "sha512-5BqxR/pshjey51iliyzTD5Xi3EN0aLmQ2lZ3lvefVV9c82BvrLo2/6OT55iifpWBufs6kdwWbuOKS841DrmK9A==",
      "cpu": [
        "x64"
      ],
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-linux-x64-musl": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-linux-x64-musl/-/rollup-linux-x64-musl-4.62.2.tgz",
      "integrity": "sha512-uNN83XxQrRAh/w0/pmAfibcwyb6YWt4gP+dpnQKPVJshAloQ785ii8CT8ZCIxkGg9opVsvAlGhFitSm6D1Jjpg==",
      "cpu": [
        "x64"
      ],
      "optional": true,
      "os": [
        "linux"
      ]
    },
    "node_modules/@rollup/rollup-openbsd-x64": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-openbsd-x64/-/rollup-openbsd-x64-4.62.2.tgz",
      "integrity": "sha512-srjEIxSH3LRnJN6THczDHWQplqEMFiAJrTab0msUryh9kwNpkICf3Ea6q6MN/2cZwRFUNx5w+h6Hpi4QuHS6Zg==",
      "cpu": [
        "x64"
      ],
      "optional": true,
      "os": [
        "openbsd"
      ]
    },
    "node_modules/@rollup/rollup-openharmony-arm64": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-openharmony-arm64/-/rollup-openharmony-arm64-4.62.2.tgz",
      "integrity": "sha512-8hOJnxgbyObnCm5AlRA3A931xX19xq80RjVTKgJOvEKWqJruP/Uf12IbAOaDjjEXYRewwHLfmF0YRIdK3OwKWA==",
      "cpu": [
        "arm64"
      ],
      "optional": true,
      "os": [
        "openharmony"
      ]
    },
    "node_modules/@rollup/rollup-win32-arm64-msvc": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-win32-arm64-msvc/-/rollup-win32-arm64-msvc-4.62.2.tgz",
      "integrity": "sha512-mmF4AY1i0hG/bLWUctUq59gtmgaSIRa3cu/A3JFRp/sCNEme2bgDEiDS22P9FbnJB8NJNF4jPJiSP5RHQpUTDg==",
      "cpu": [
        "arm64"
      ],
      "optional": true,
      "os": [
        "win32"
      ]
    },
    "node_modules/@rollup/rollup-win32-ia32-msvc": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-win32-ia32-msvc/-/rollup-win32-ia32-msvc-4.62.2.tgz",
      "integrity": "sha512-DZgkknc6jhHrk46V25vbAM0zZkyP0nSDkJB8/dRkLTxv470dOmWDqGoEJl/9A0dFfS7yE3REOwNDxpHwSLSt0Q==",
      "cpu": [
        "ia32"
      ],
      "optional": true,
      "os": [
        "win32"
      ]
    },
    "node_modules/@rollup/rollup-win32-x64-gnu": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-win32-x64-gnu/-/rollup-win32-x64-gnu-4.62.2.tgz",
      "integrity": "sha512-T6xr6ucWSFto+VGajA8YH26LdpHRuP4YLHEKAtCWvJDOlnmWcDZVCI2Jmjr+IFHDlt2zRaTAKE4tfjTaWLgJBg==",
      "cpu": [
        "x64"
      ],
      "optional": true,
      "os": [
        "win32"
      ]
    },
    "node_modules/@rollup/rollup-win32-x64-msvc": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/@rollup/rollup-win32-x64-msvc/-/rollup-win32-x64-msvc-4.62.2.tgz",
      "integrity": "sha512-BfzEnDJOt9T8M989/lA37EcJgat01wLRnoi5dQf3QzOH7jzpqTAzdDbVfRljVr5r+jzKqpbHeyOfAaXxAd0PAA==",
      "cpu": [
        "x64"
      ],
      "optional": true,
      "os": [
        "win32"
      ]
    },
    "node_modules/@sveltejs/vite-plugin-svelte": {
      "version": "3.1.2",
      "resolved": "https://registry.npmjs.org/@sveltejs/vite-plugin-svelte/-/vite-plugin-svelte-3.1.2.tgz",
      "integrity": "sha512-Txsm1tJvtiYeLUVRNqxZGKR/mI+CzuIQuc2gn+YCs9rMTowpNZ2Nqt53JdL8KF9bLhAf2ruR/dr9eZCwdTriRA==",
      "dependencies": {
        "@sveltejs/vite-plugin-svelte-inspector": "^2.1.0",
        "debug": "^4.3.4",
        "deepmerge": "^4.3.1",
        "kleur": "^4.1.5",
        "magic-string": "^0.30.10",
        "svelte-hmr": "^0.16.0",
        "vitefu": "^0.2.5"
      },
      "engines": {
        "node": "^18.0.0 || >=20"
      },
      "peerDependencies": {
        "svelte": "^4.0.0 || ^5.0.0-next.0",
        "vite": "^5.0.0"
      }
    },
    "node_modules/@sveltejs/vite-plugin-svelte-inspector": {
      "version": "2.1.0",
      "resolved": "https://registry.npmjs.org/@sveltejs/vite-plugin-svelte-inspector/-/vite-plugin-svelte-inspector-2.1.0.tgz",
      "integrity": "sha512-9QX28IymvBlSCqsCll5t0kQVxipsfhFFL+L2t3nTWfXnddYwxBuAEtTtlaVQpRz9c37BhJjltSeY4AJSC03SSg==",
      "dependencies": {
        "debug": "^4.3.4"
      },
      "engines": {
        "node": "^18.0.0 || >=20"
      },
      "peerDependencies": {
        "@sveltejs/vite-plugin-svelte": "^3.0.0",
        "svelte": "^4.0.0 || ^5.0.0-next.0",
        "vite": "^5.0.0"
      }
    },
    "node_modules/@types/estree": {
      "version": "1.0.9",
      "resolved": "https://registry.npmjs.org/@types/estree/-/estree-1.0.9.tgz",
      "integrity": "sha512-GhdPgy1el4/ImP05X05Uw4cw2/M93BCUmnEvWZNStlCzEKME4Fkk+YpoA5OiHNQmoS7Cafb8Xa3Pya8m1Qrzeg=="
    },
    "node_modules/acorn": {
      "version": "8.17.0",
      "resolved": "https://registry.npmjs.org/acorn/-/acorn-8.17.0.tgz",
      "integrity": "sha512-xRQbDb9BnwDafYNn6Vwl839DYVjqXYb1XVGtWAZ1kcDc6iwAL4hg3B1dZlRiuENFeO2H53gFG3in621AdERVAg==",
      "bin": {
        "acorn": "bin/acorn"
      },
      "engines": {
        "node": ">=0.4.0"
      }
    },
    "node_modules/aria-query": {
      "version": "5.3.2",
      "resolved": "https://registry.npmjs.org/aria-query/-/aria-query-5.3.2.tgz",
      "integrity": "sha512-COROpnaoap1E2F000S62r6A60uHZnmlvomhfyT2DlTcrY1OrBKn2UhH7qn5wTC9zMvD0AY7csdPSNwKP+7WiQw==",
      "engines": {
        "node": ">= 0.4"
      }
    },
    "node_modules/axobject-query": {
      "version": "4.1.0",
      "resolved": "https://registry.npmjs.org/axobject-query/-/axobject-query-4.1.0.tgz",
      "integrity": "sha512-qIj0G9wZbMGNLjLmg1PT6v2mE9AH2zlnADJD/2tC6E00hgmhUOfEB6greHPAfLRSufHqROIUTkw6E+M3lH0PTQ==",
      "engines": {
        "node": ">= 0.4"
      }
    },
    "node_modules/code-red": {
      "version": "1.0.4",
      "resolved": "https://registry.npmjs.org/code-red/-/code-red-1.0.4.tgz",
      "integrity": "sha512-7qJWqItLA8/VPVlKJlFXU+NBlo/qyfs39aJcuMT/2ere32ZqvF5OSxgdM5xOfJJ7O429gg2HM47y8v9P+9wrNw==",
      "dependencies": {
        "@jridgewell/sourcemap-codec": "^1.4.15",
        "@types/estree": "^1.0.1",
        "acorn": "^8.10.0",
        "estree-walker": "^3.0.3",
        "periscopic": "^3.1.0"
      }
    },
    "node_modules/css-tree": {
      "version": "2.3.1",
      "resolved": "https://registry.npmjs.org/css-tree/-/css-tree-2.3.1.tgz",
      "integrity": "sha512-6Fv1DV/TYw//QF5IzQdqsNDjx/wc8TrMBZsqjL9eW01tWb7R7k/mq+/VXfJCl7SoD5emsJop9cOByJZfs8hYIw==",
      "dependencies": {
        "mdn-data": "2.0.30",
        "source-map-js": "^1.0.1"
      },
      "engines": {
        "node": "^10 || ^12.20.0 || ^14.13.0 || >=15.0.0"
      }
    },
    "node_modules/debug": {
      "version": "4.4.3",
      "resolved": "https://registry.npmjs.org/debug/-/debug-4.4.3.tgz",
      "integrity": "sha512-RGwwWnwQvkVfavKVt22FGLw+xYSdzARwm0ru6DhTVA3umU5hZc28V3kO4stgYryrTlLpuvgI9GiijltAjNbcqA==",
      "dependencies": {
        "ms": "^2.1.3"
      },
      "engines": {
        "node": ">=6.0"
      },
      "peerDependenciesMeta": {
        "supports-color": {
          "optional": true
        }
      }
    },
    "node_modules/deepmerge": {
      "version": "4.3.1",
      "resolved": "https://registry.npmjs.org/deepmerge/-/deepmerge-4.3.1.tgz",
      "integrity": "sha512-3sUqbMEc77XqpdNO7FRyRog+eW3ph+GYCbj+rK+uYyRMuwsVy0rMiVtPn+QJlKFvWP/1PYpapqYn0Me2knFn+A==",
      "engines": {
        "node": ">=0.10.0"
      }
    },
    "node_modules/esbuild": {
      "version": "0.21.5",
      "resolved": "https://registry.npmjs.org/esbuild/-/esbuild-0.21.5.tgz",
      "integrity": "sha512-mg3OPMV4hXywwpoDxu3Qda5xCKQi+vCTZq8S9J/EpkhB2HzKXq4SNFZE3+NK93JYxc8VMSep+lOUSC/RVKaBqw==",
      "hasInstallScript": true,
      "bin": {
        "esbuild": "bin/esbuild"
      },
      "engines": {
        "node": ">=12"
      },
      "optionalDependencies": {
        "@esbuild/aix-ppc64": "0.21.5",
        "@esbuild/android-arm": "0.21.5",
        "@esbuild/android-arm64": "0.21.5",
        "@esbuild/android-x64": "0.21.5",
        "@esbuild/darwin-arm64": "0.21.5",
        "@esbuild/darwin-x64": "0.21.5",
        "@esbuild/freebsd-arm64": "0.21.5",
        "@esbuild/freebsd-x64": "0.21.5",
        "@esbuild/linux-arm": "0.21.5",
        "@esbuild/linux-arm64": "0.21.5",
        "@esbuild/linux-ia32": "0.21.5",
        "@esbuild/linux-loong64": "0.21.5",
        "@esbuild/linux-mips64el": "0.21.5",
        "@esbuild/linux-ppc64": "0.21.5",
        "@esbuild/linux-riscv64": "0.21.5",
        "@esbuild/linux-s390x": "0.21.5",
        "@esbuild/linux-x64": "0.21.5",
        "@esbuild/netbsd-x64": "0.21.5",
        "@esbuild/openbsd-x64": "0.21.5",
        "@esbuild/sunos-x64": "0.21.5",
        "@esbuild/win32-arm64": "0.21.5",
        "@esbuild/win32-ia32": "0.21.5",
        "@esbuild/win32-x64": "0.21.5"
      }
    },
    "node_modules/estree-walker": {
      "version": "3.0.3",
      "resolved": "https://registry.npmjs.org/estree-walker/-/estree-walker-3.0.3.tgz",
      "integrity": "sha512-7RUKfXgSMMkzt6ZuXmqapOurLGPPfgj6l9uRZ7lRGolvk0y2yocc35LdcxKC5PQZdn2DMqioAQ2NoWcrTKmm6g==",
      "dependencies": {
        "@types/estree": "^1.0.0"
      }
    },
    "node_modules/fsevents": {
      "version": "2.3.3",
      "resolved": "https://registry.npmjs.org/fsevents/-/fsevents-2.3.3.tgz",
      "integrity": "sha512-5xoDfX+fL7faATnagmWPpbFtwh/R77WmMMqqHGS65C3vvB0YHrgF+B1YmZ3441tMj5n63k0212XNoJwzlhffQw==",
      "hasInstallScript": true,
      "optional": true,
      "os": [
        "darwin"
      ],
      "engines": {
        "node": "^8.16.0 || ^10.6.0 || >=11.0.0"
      }
    },
    "node_modules/is-reference": {
      "version": "3.0.3",
      "resolved": "https://registry.npmjs.org/is-reference/-/is-reference-3.0.3.tgz",
      "integrity": "sha512-ixkJoqQvAP88E6wLydLGGqCJsrFUnqoH6HnaczB8XmDH1oaWU+xxdptvikTgaEhtZ53Ky6YXiBuUI2WXLMCwjw==",
      "dependencies": {
        "@types/estree": "^1.0.6"
      }
    },
    "node_modules/kleur": {
      "version": "4.1.5",
      "resolved": "https://registry.npmjs.org/kleur/-/kleur-4.1.5.tgz",
      "integrity": "sha512-o+NO+8WrRiQEE4/7nwRJhN1HWpVmJm511pBHUxPLtp0BUISzlBplORYSmTclCnJvQq2tKu/sgl3xVpkc7ZWuQQ==",
      "engines": {
        "node": ">=6"
      }
    },
    "node_modules/locate-character": {
      "version": "3.0.0",
      "resolved": "https://registry.npmjs.org/locate-character/-/locate-character-3.0.0.tgz",
      "integrity": "sha512-SW13ws7BjaeJ6p7Q6CO2nchbYEc3X3J6WrmTTDto7yMPqVSZTUyY5Tjbid+Ab8gLnATtygYtiDIJGQRRn2ZOiA=="
    },
    "node_modules/magic-string": {
      "version": "0.30.21",
      "resolved": "https://registry.npmjs.org/magic-string/-/magic-string-0.30.21.tgz",
      "integrity": "sha512-vd2F4YUyEXKGcLHoq+TEyCjxueSeHnFxyyjNp80yg0XV4vUhnDer/lvvlqM/arB5bXQN5K2/3oinyCRyx8T2CQ==",
      "dependencies": {
        "@jridgewell/sourcemap-codec": "^1.5.5"
      }
    },
    "node_modules/mdn-data": {
      "version": "2.0.30",
      "resolved": "https://registry.npmjs.org/mdn-data/-/mdn-data-2.0.30.tgz",
      "integrity": "sha512-GaqWWShW4kv/G9IEucWScBx9G1/vsFZZJUO+tD26M8J8z3Kw5RDQjaoZe03YAClgeS/SWPOcb4nkFBTEi5DUEA=="
    },
    "node_modules/ms": {
      "version": "2.1.3",
      "resolved": "https://registry.npmjs.org/ms/-/ms-2.1.3.tgz",
      "integrity": "sha512-6FlzubTLZG3J2a/NVCAleEhjzq5oxgHyaCU9yYXvcLsvoVaHJq/s5xXI6/XXP6tz7R9xAOtHnSO/tXtF3WRTlA=="
    },
    "node_modules/nanoid": {
      "version": "3.3.15",
      "resolved": "https://registry.npmjs.org/nanoid/-/nanoid-3.3.15.tgz",
      "integrity": "sha512-y7Wygv/7mEOvxTuEQDB8StXdMRBWf1kR/tlhAzBRUFkB2jfcLOAxO/SHmOO2zgz1pVgK29/kyupn059/bCHdjA==",
      "funding": [
        {
          "type": "github",
          "url": "https://github.com/sponsors/ai"
        }
      ],
      "bin": {
        "nanoid": "bin/nanoid.cjs"
      },
      "engines": {
        "node": "^10 || ^12 || ^13.7 || ^14 || >=15.0.1"
      }
    },
    "node_modules/periscopic": {
      "version": "3.1.0",
      "resolved": "https://registry.npmjs.org/periscopic/-/periscopic-3.1.0.tgz",
      "integrity": "sha512-vKiQ8RRtkl9P+r/+oefh25C3fhybptkHKCZSPlcXiJux2tJF55GnEj3BVn4A5gKfq9NWWXXrxkHBwVPUfH0opw==",
      "dependencies": {
        "@types/estree": "^1.0.0",
        "estree-walker": "^3.0.0",
        "is-reference": "^3.0.0"
      }
    },
    "node_modules/picocolors": {
      "version": "1.1.1",
      "resolved": "https://registry.npmjs.org/picocolors/-/picocolors-1.1.1.tgz",
      "integrity": "sha512-xceH2snhtb5M9liqDsmEw56le376mTZkEX/jEb/RxNFyegNul7eNslCXP9FDj/Lcu0X8KEyMceP2ntpaHrDEVA=="
    },
    "node_modules/postcss": {
      "version": "8.5.16",
      "resolved": "https://registry.npmjs.org/postcss/-/postcss-8.5.16.tgz",
      "integrity": "sha512-vuwillviilfKZsg0VGj5R/YwwcHx4SLsIOI/7K6mQkWx+l5cUHTjj5g0AasTBcyXsbfTgrwsUNmVUb5xVwyPwg==",
      "funding": [
        {
          "type": "opencollective",
          "url": "https://opencollective.com/postcss/"
        },
        {
          "type": "tidelift",
          "url": "https://tidelift.com/funding/github/npm/postcss"
        },
        {
          "type": "github",
          "url": "https://github.com/sponsors/ai"
        }
      ],
      "dependencies": {
        "nanoid": "^3.3.12",
        "picocolors": "^1.1.1",
        "source-map-js": "^1.2.1"
      },
      "engines": {
        "node": "^10 || ^12 || >=14"
      }
    },
    "node_modules/rollup": {
      "version": "4.62.2",
      "resolved": "https://registry.npmjs.org/rollup/-/rollup-4.62.2.tgz",
      "integrity": "sha512-RFnrW4lhXA3s3eqHDZvN654g8OTjzRfqpIRJYczCGB6HzphckVAi/Qh4tbPUbRuDi7s1Llv8g/NspLkttY3gTA==",
      "dependencies": {
        "@types/estree": "1.0.9"
      },
      "bin": {
        "rollup": "dist/bin/rollup"
      },
      "engines": {
        "node": ">=18.0.0",
        "npm": ">=8.0.0"
      },
      "optionalDependencies": {
        "@rollup/rollup-android-arm-eabi": "4.62.2",
        "@rollup/rollup-android-arm64": "4.62.2",
        "@rollup/rollup-darwin-arm64": "4.62.2",
        "@rollup/rollup-darwin-x64": "4.62.2",
        "@rollup/rollup-freebsd-arm64": "4.62.2",
        "@rollup/rollup-freebsd-x64": "4.62.2",
        "@rollup/rollup-linux-arm-gnueabihf": "4.62.2",
        "@rollup/rollup-linux-arm-musleabihf": "4.62.2",
        "@rollup/rollup-linux-arm64-gnu": "4.62.2",
        "@rollup/rollup-linux-arm64-musl": "4.62.2",
        "@rollup/rollup-linux-loong64-gnu": "4.62.2",
        "@rollup/rollup-linux-loong64-musl": "4.62.2",
        "@rollup/rollup-linux-ppc64-gnu": "4.62.2",
        "@rollup/rollup-linux-ppc64-musl": "4.62.2",
        "@rollup/rollup-linux-riscv64-gnu": "4.62.2",
        "@rollup/rollup-linux-riscv64-musl": "4.62.2",
        "@rollup/rollup-linux-s390x-gnu": "4.62.2",
        "@rollup/rollup-linux-x64-gnu": "4.62.2",
        "@rollup/rollup-linux-x64-musl": "4.62.2",
        "@rollup/rollup-openbsd-x64": "4.62.2",
        "@rollup/rollup-openharmony-arm64": "4.62.2",
        "@rollup/rollup-win32-arm64-msvc": "4.62.2",
        "@rollup/rollup-win32-ia32-msvc": "4.62.2",
        "@rollup/rollup-win32-x64-gnu": "4.62.2",
        "@rollup/rollup-win32-x64-msvc": "4.62.2",
        "fsevents": "~2.3.2"
      }
    },
    "node_modules/source-map-js": {
      "version": "1.2.1",
      "resolved": "https://registry.npmjs.org/source-map-js/-/source-map-js-1.2.1.tgz",
      "integrity": "sha512-UXWMKhLOwVKb728IUtQPXxfYU+usdybtUrK/8uGE8CQMvrhOpwvzDBwj0QhSL7MQc7vIsISBG8VQ8+IDQxpfQA==",
      "engines": {
        "node": ">=0.10.0"
      }
    },
    "node_modules/svelte": {
      "version": "4.2.19",
      "resolved": "https://registry.npmjs.org/svelte/-/svelte-4.2.19.tgz",
      "integrity": "sha512-IY1rnGr6izd10B0A8LqsBfmlT5OILVuZ7XsI0vdGPEvuonFV7NYEUK4dAkm9Zg2q0Um92kYjTpS1CAP3Nh/KWw==",
      "dependencies": {
        "@ampproject/remapping": "^2.2.1",
        "@jridgewell/sourcemap-codec": "^1.4.15",
        "@jridgewell/trace-mapping": "^0.3.18",
        "@types/estree": "^1.0.1",
        "acorn": "^8.9.0",
        "aria-query": "^5.3.0",
        "axobject-query": "^4.0.0",
        "code-red": "^1.0.3",
        "css-tree": "^2.3.1",
        "estree-walker": "^3.0.3",
        "is-reference": "^3.0.1",
        "locate-character": "^3.0.0",
        "magic-string": "^0.30.4",
        "periscopic": "^3.1.0"
      },
      "engines": {
        "node": ">=16"
      }
    },
    "node_modules/svelte-hmr": {
      "version": "0.16.0",
      "resolved": "https://registry.npmjs.org/svelte-hmr/-/svelte-hmr-0.16.0.tgz",
      "integrity": "sha512-Gyc7cOS3VJzLlfj7wKS0ZnzDVdv3Pn2IuVeJPk9m2skfhcu5bq3wtIZyQGggr7/Iim5rH5cncyQft/kRLupcnA==",
      "engines": {
        "node": "^12.20 || ^14.13.1 || >= 16"
      },
      "peerDependencies": {
        "svelte": "^3.19.0 || ^4.0.0"
      }
    },
    "node_modules/vite": {
      "version": "5.4.21",
      "resolved": "https://registry.npmjs.org/vite/-/vite-5.4.21.tgz",
      "integrity": "sha512-o5a9xKjbtuhY6Bi5S3+HvbRERmouabWbyUcpXXUA1u+GNUKoROi9byOJ8M0nHbHYHkYICiMlqxkg1KkYmm25Sw==",
      "dependencies": {
        "esbuild": "^0.21.3",
        "postcss": "^8.4.43",
        "rollup": "^4.20.0"
      },
      "bin": {
        "vite": "bin/vite.js"
      },
      "engines": {
        "node": "^18.0.0 || >=20.0.0"
      },
      "funding": {
        "url": "https://github.com/vitejs/vite?sponsor=1"
      },
      "optionalDependencies": {
        "fsevents": "~2.3.3"
      },
      "peerDependencies": {
        "@types/node": "^18.0.0 || >=20.0.0",
        "less": "*",
        "lightningcss": "^1.21.0",
        "sass": "*",
        "sass-embedded": "*",
        "stylus": "*",
        "sugarss": "*",
        "terser": "^5.4.0"
      },
      "peerDependenciesMeta": {
        "@types/node": {
          "optional": true
        },
        "less": {
          "optional": true
        },
        "lightningcss": {
          "optional": true
        },
        "sass": {
          "optional": true
        },
        "sass-embedded": {
          "optional": true
        },
        "stylus": {
          "optional": true
        },
        "sugarss": {
          "optional": true
        },
        "terser": {
          "optional": true
        }
      }
    },
    "node_modules/vitefu": {
      "version": "0.2.5",
      "resolved": "https://registry.npmjs.org/vitefu/-/vitefu-0.2.5.tgz",
      "integrity": "sha512-SgHtMLoqaeeGnd2evZ849ZbACbnwQCIwRH57t18FxcXoZop0uQu0uzlIhJBlF/eWVzuce0sHeqPcDo+evVcg8Q==",
      "peerDependencies": {
        "vite": "^3.0.0 || ^4.0.0 || ^5.0.0"
      },
      "peerDependenciesMeta": {
        "vite": {
          "optional": true
        }
      }
    }
  }
}
'''
    return template.replace("__PACKAGE_NAME__", package_name)


def _svelte_index_html(name: str) -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{name}</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
"""


def _svelte_vite_config_ts() -> str:
    return """import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [svelte()],
});
"""


def _svelte_main_ts() -> str:
    return """import App from './App.svelte';

const app = new App({
  target: document.getElementById('app') as HTMLElement,
});

export default app;
"""


def _svelte_app_svelte(name: str) -> str:
    return f"""<script lang="ts">
  import {{ previewConfig }} from './config';
</script>

<main>
  <section class="shell">
    <p class="eyebrow">{{previewConfig.runtimeProfile}}</p>
    <h1>{name}</h1>
    <p>Preview API: {{previewConfig.apiBaseUrl}}</p>
  </section>
</main>

<style>
  :global(body) {{
    margin: 0;
    font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: #172026;
    background: #f7f8fa;
  }}

  main {{
    min-height: 100vh;
    display: grid;
    place-items: center;
    padding: 32px;
  }}

  .shell {{
    width: min(720px, 100%);
    border: 1px solid #d7dde4;
    background: #ffffff;
    border-radius: 8px;
    padding: 32px;
  }}

  .eyebrow {{
    margin: 0 0 12px;
    color: #4f6f52;
    font-size: 13px;
    font-weight: 700;
    text-transform: uppercase;
  }}

  h1 {{
    margin: 0 0 16px;
    font-size: 32px;
    line-height: 1.15;
  }}

  p {{
    overflow-wrap: anywhere;
  }}
</style>
"""


def _svelte_config_ts(slug: str) -> str:
    return f"""const runtimeProfile = import.meta.env.VITE_APP_RUNTIME_PROFILE || 'preview';
const apiRuntime = import.meta.env.VITE_API_RUNTIME || 'cloudflare_preview';
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'https://preview.nienfos.com/{slug}/api';
const appSlug = import.meta.env.VITE_APP_SLUG || '{slug}';

const forbiddenApiFragments = ['localhost', '127.0.0.1', '10.0.2.2', 'example', 'placeholder', 'mock'];

if (runtimeProfile !== 'preview') {{
  throw new Error('Svelte Initial Preview Release requires VITE_APP_RUNTIME_PROFILE=preview');
}}
if (apiRuntime !== 'cloudflare_preview') {{
  throw new Error('Svelte Initial Preview Release requires VITE_API_RUNTIME=cloudflare_preview');
}}
if (apiBaseUrl !== `https://preview.nienfos.com/${{appSlug}}/api`) {{
  throw new Error('Svelte Initial Preview Release requires VITE_API_BASE_URL=https://preview.nienfos.com/{{slug}}/api');
}}
if (forbiddenApiFragments.some((fragment) => apiBaseUrl.includes(fragment))) {{
  throw new Error('Svelte Initial Preview Release cannot use localhost, mock, demo, or placeholder API URLs');
}}

export const previewConfig = {{
  appSlug,
  runtimeProfile,
  apiRuntime,
  apiBaseUrl,
  productionReady: false,
  mockOrDemo: false,
  releaseChannel: 'prerelease',
}};
"""


def _svelte_preview_config_test_mjs(slug: str) -> str:
    return f"""import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(process.cwd());
const configPath = path.join(root, 'src', 'config.ts');
const packagePath = path.join(root, 'package.json');
const config = fs.readFileSync(configPath, 'utf8');
const pkg = JSON.parse(fs.readFileSync(packagePath, 'utf8'));

assert.match(config, /VITE_APP_RUNTIME_PROFILE/);
assert.match(config, /VITE_API_RUNTIME/);
assert.match(config, /VITE_API_BASE_URL/);
assert.match(config, /cloudflare_preview/);
assert.match(config, /https:\\/\\/preview\\.nienfos\\.com\\/\\$\\{{appSlug\\}}\\/api/);
assert.equal(pkg.scripts.build, 'vite build');
assert.equal(pkg.scripts.test, 'node test/preview-config.test.mjs');
assert.equal(pkg.scripts['validate:preview'], 'node test/preview-config.test.mjs --preview');

const expectedUrl = 'https://preview.nienfos.com/{slug}/api';
const forbiddenApiFragments = ['localhost', '127.0.0.1', '10.0.2.2', 'example', 'placeholder', 'mock'];

function resolvePreviewConfig(env) {{
  const appSlug = env.VITE_APP_SLUG || '{slug}';
  const runtimeProfile = env.VITE_APP_RUNTIME_PROFILE || 'preview';
  const apiRuntime = env.VITE_API_RUNTIME || 'cloudflare_preview';
  const apiBaseUrl = env.VITE_API_BASE_URL || expectedUrl;
  if (runtimeProfile !== 'preview') {{
    throw new Error('runtime profile must be preview');
  }}
  if (apiRuntime !== 'cloudflare_preview') {{
    throw new Error('API runtime must be cloudflare_preview');
  }}
  if (apiBaseUrl !== `https://preview.nienfos.com/${{appSlug}}/api`) {{
    throw new Error('API base URL must point to the public preview API');
  }}
  if (forbiddenApiFragments.some((fragment) => apiBaseUrl.includes(fragment))) {{
    throw new Error('API base URL must not be local/mock/placeholder');
  }}
  return {{ appSlug, runtimeProfile, apiRuntime, apiBaseUrl }};
}}

const runtime = resolvePreviewConfig(process.env);
assert.equal(runtime.runtimeProfile, 'preview');
assert.equal(runtime.apiRuntime, 'cloudflare_preview');
assert.equal(runtime.apiBaseUrl, expectedUrl);

for (const env of [
  {{ VITE_API_BASE_URL: 'http://localhost:8000/api' }},
  {{ VITE_API_BASE_URL: 'https://example.com/api' }},
  {{ VITE_API_BASE_URL: 'https://preview.nienfos.com/placeholder/api' }},
  {{ VITE_API_BASE_URL: 'https://preview.nienfos.com/{slug}/mock' }},
  {{ VITE_APP_RUNTIME_PROFILE: 'mock', VITE_API_BASE_URL: expectedUrl }},
  {{ VITE_API_RUNTIME: 'fastapi', VITE_API_BASE_URL: expectedUrl }},
]) {{
  assert.throws(() => resolvePreviewConfig(env));
}}

console.log('Svelte preview config contract passed');
"""


def _svelte_readme(name: str, slug: str) -> str:
    return f"""# {name} Web

Svelte/Vite app generated by Project Factory with real Cloudflare Preview API
configuration. This strategy is web-only until an explicit Android wrapper
strategy exists.

```bash
npm ci
VITE_APP_RUNTIME_PROFILE=preview \\
VITE_API_RUNTIME=cloudflare_preview \\
VITE_API_BASE_URL=https://preview.nienfos.com/{slug}/api \\
npm test
npm run validate:preview
npm run build
```
"""


def _release_output_template(frontend_strategy: str = "flutter") -> str:
    if frontend_strategy == "svelte":
        return """# Factory Final Output

- source_app:
- validated_source_commit:
- android_tag_commit: not_applicable_web_only
- report_generated_from_commit:
- release_report_commit:
- push_state:
- branch:
- frontend_strategy: svelte
- runtime_profile: preview
- release_channel: prerelease
- mock_or_demo: false
- backend_required: true
- production_ready: false
- production_release_blocked: true
- installable_android: false
- web_preview_ready: false
- productive_release_tag: blocked_until_explicit_promotion
- release_url: not_applicable_web_only
- bridge_installable_url: not_applicable_web_only
- cloudflare_preview_url:
- cloudflare_preview_health_url:
- preview_api_base_url:
- preview_api_health_url:
- workbench_status: not_applicable_web_only
- codex_mobile_catalog_status: not_applicable_web_only
- validations_executed:
- blockers_remaining:
"""
    return """# Factory Final Output

- source_app:
- validated_source_commit:
- android_tag_commit:
- report_generated_from_commit:
- release_report_commit:
- push_state:
- branch:
- runtime_profile: preview
- release_channel: prerelease
- mock_or_demo: false
- backend_required: true
- production_ready: false
- production_release_blocked: true
- android_preview_release_tag:
- productive_release_tag: blocked_until_explicit_promotion
- android_preview_apk_url:
- android_preview_apk_sha256:
- release_url:
- bridge_installable_url:
- cloudflare_preview_url:
- cloudflare_preview_health_url:
- preview_api_base_url:
- preview_api_health_url:
- workbench_status:
- codex_mobile_catalog_status:
- validations_executed:
- blockers_remaining:
"""


def _promotion_runbook_doc(
    slug: str,
    name: str,
    frontend_strategy: str = "flutter",
) -> str:
    if frontend_strategy == "svelte":
        return f"""# Preview To Production Promotion

`{name}` starts with a Svelte web Initial Preview Release. The preview is public
web/API only; it does not produce a native mobile package and is not registered
in the Codex Mobile installable catalog.

## Separation Contract

- Preview URL: `https://preview.nienfos.com/{slug}`.
- Preview API: `https://preview.nienfos.com/{slug}/api`.
- Native mobile tags and package signing are not applicable for this strategy.
- Never promote localhost, placeholder API URLs, mock/demo data, or a mobile
  installability claim without a named wrapper strategy.

## Required Before Promotion

Promotion can only happen after:

- Web preview health and Preview API health pass.
- Preview API smoke confirms D1 persistence.
- A real production backend exists.
- `API_BASE_URL` points to production, not the preview API.
- `mockOrDemo=false`.

## Promotion Command Shape

```bash
APP_RUNTIME_PROFILE=real \\
API_BASE_URL=https://api.example.com \\
scripts/validate_release_profiles.sh
```
"""
    return f"""# Preview To Production Promotion

`{name}` starts with an Initial Preview Release. That preview is installable, but
it is not production.

## Separation Contract

- Preview tags use `android-preview-v*`.
- Production promotion tags use `android-v*`.
- Mock/demo tags use `android-mock-v*` or `android-local-v*`.
- Never reuse preview or mock APKs for production.
- Never promote `LOCAL_DATA_MODE=true`, localhost, placeholder API URLs, or seed
  demo users.

## Required Before Promotion

Read `release/promotion-contract.json` and verify:

```bash
python3 -m json.tool release/promotion-contract.json
scripts/validate_release_profiles.sh
```

Promotion can only happen after:

- Preview API health and smoke checks passed.
- `android-preview-v*` APK was published and registered in Bridge.
- A real production backend exists.
- `API_BASE_URL` points to that production backend, not
  `https://preview.nienfos.com/{slug}/api`.
- Android production signing credentials are configured.
- App update metadata reports production channel and `mockOrDemo=false`.

## Promotion Command Shape

```bash
APP_RELEASE_TAG=android-v<version> \\
APP_RUNTIME_PROFILE=real \\
API_BASE_URL=https://api.example.com \\
LOCAL_DATA_MODE=false \\
scripts/validate_release_profiles.sh

scripts/publish_android_release.sh
```
"""


def _android_preview_signing_doc(
    slug: str,
    frontend_strategy: str = "flutter",
) -> str:
    if frontend_strategy == "svelte":
        return f"""# Preview Signing Policy

The Svelte strategy is web-only. It does not generate native mobile artifacts,
does not use native preview signing, and must not publish native mobile release
tags.

Preview validation still requires:

- `VITE_APP_RUNTIME_PROFILE=preview`;
- `VITE_API_RUNTIME=cloudflare_preview`;
- `VITE_API_BASE_URL=https://preview.nienfos.com/{slug}/api`;
- Cloudflare Worker/D1 public health checks.

Mobile installability requires a future explicit wrapper strategy with its own
signing, package, prerelease, checksum, and catalog registration contract.
"""
    return f"""# Android Preview Signing Policy

Initial Preview Release uses `android-preview-v*` and `APP_RUNTIME_PROFILE=preview`.
It is user-installable for validation, but it is not production.

## Preview Signing

- Preview APKs may use preview/debug-compatible signing only when release
  metadata remains `productionReady=false`.
- The APK must point to `https://preview.nienfos.com/{slug}/api`.
- Bridge registration must keep `releaseChannel=prerelease`,
  `runtimeProfile=preview`, `productionReady=false`, and `mockOrDemo=false`.

## Debug Signing

Debug signing is forbidden for installable Initial Preview Release artifacts.
The generated workflow and validators require the stable preview upload key from
`/home/batata/Projects/codex-cli-mobile-bridge/secrets/<slug>-preview-upload-keystore.jks`
and never fall back to debug signing.

`release/preview-signing-policy.json` records this preview-only signing policy
and must not declare any debug signing override.

```bash
APP_RELEASE_TAG=android-preview-v<version> \\
APP_RUNTIME_PROFILE=preview \\
API_RUNTIME=cloudflare_preview \\
API_BASE_URL=https://preview.nienfos.com/{slug}/api \\
scripts/publish_android_preview_release.sh
```

Production signing is reserved for the later `android-v*` promotion path.
"""


def _preview_operations_runbook(
    slug: str,
    frontend_strategy: str = "flutter",
) -> str:
    if frontend_strategy == "svelte":
        return f"""# Preview Update Disable Extend Troubleshooting

The Svelte preview lane uses real Cloudflare Preview API and persistent D1 data.
It is web-only until a wrapper strategy is implemented.

## Update Preview

```bash
scripts/validate_generated_project.sh
scripts/validate_cloudflare_cost_posture.sh
scripts/apply_cloudflare_preview.sh
scripts/smoke_web_preview.sh
scripts/smoke_preview_api.sh
scripts/validate_initial_preview_release.sh
```

## Bridge Env Loader

All preview scripts load real Bridge secrets through `scripts/load_bridge_env.sh`.
The loader reads, when present:

- `/home/batata/Projects/codex-cli-mobile-bridge/secrets/cloudflare.env`
- `/home/batata/Projects/codex-cli-mobile-bridge/.env`

It prints missing variable names only, never secret values.

## Extend Preview

Add real Preview API routes under `deploy/web-preview/worker/src/index.js`, add
D1 schema changes, then rerun:

```bash
scripts/validate_web_preview.sh
scripts/apply_cloudflare_preview.sh
scripts/smoke_web_preview.sh
scripts/smoke_preview_api.sh
```

## Troubleshooting

- Missing Cloudflare config: run `scripts/deploy_web_preview.sh --plan`.
- Wrong API URL: `VITE_API_BASE_URL` must be `https://preview.nienfos.com/{slug}/api`.
- Native mobile output requested: choose a supported mobile strategy or implement an explicit wrapper strategy.
"""
    return f"""# Preview Update Disable Extend Troubleshooting

The preview lane uses real Cloudflare Preview API and persistent D1 data. Mock or
demo data is opt-in only and must use visible mock/local tags.

## Update Preview

```bash
scripts/validate_generated_project.sh
scripts/validate_cloudflare_cost_posture.sh
scripts/apply_cloudflare_preview.sh
scripts/smoke_preview_api.sh
scripts/publish_android_preview_release.sh
scripts/register_installable_app.sh
scripts/validate_initial_preview_release.sh
```

## Bridge Env Loader

All preview scripts load real Bridge secrets through `scripts/load_bridge_env.sh`.
The loader reads, when present:

- `/home/batata/Projects/codex-cli-mobile-bridge/secrets/cloudflare.env`
- `/home/batata/Projects/codex-cli-mobile-bridge/.env`

For Android preview signing it also expects:

- `/home/batata/Projects/codex-cli-mobile-bridge/secrets/{slug}-preview-upload-keystore.jks`
- `/home/batata/Projects/codex-cli-mobile-bridge/secrets/{slug}-preview-signing.env`

It prints missing variable names only, never secret values. Existing keystores
must be reused for compatible APK updates.

## Disable Preview

Disable the Bridge catalog entry first, then stop sharing the preview URL:

```bash
BRIDGE_URL=http://127.0.0.1:8000 \\
BRIDGE_REGISTRATION_TOKEN=<token> \\
ENABLED=false \\
scripts/register_installable_app.sh
```

## Extend Preview

Add new real Preview API routes under `deploy/web-preview/worker/src/index.js`,
add D1 schema changes, then rerun:

```bash
scripts/validate_web_preview.sh
scripts/apply_cloudflare_preview.sh
scripts/smoke_preview_api.sh
```

## Troubleshooting

- Missing Cloudflare config: run `scripts/deploy_web_preview.sh --plan` and fill
  Bridge Cloudflare settings.
- Paid-resource blocker: inspect `release/cloudflare-cost-posture.json`; only set
  `CLOUDFLARE_PAID_RESOURCES_CONFIRMED=true` with a real reason.
- Wrong API URL: `API_BASE_URL` must be `https://preview.nienfos.com/{slug}/api`.
- Bridge missing APK: publish `android-preview-v*`, then rerun
  `scripts/register_installable_app.sh`.
"""


def _aws_domain_delegation_runbook(slug: str) -> str:
    return f"""# AWS Domain Delegation And Renewal Runbook

Initial Preview Release uses `https://preview.nienfos.com/{slug}` through
Cloudflare. It is not production and must not be promoted by changing DNS only.

## Route 53 Delegation Check

```bash
export DOMAIN_NAME=nienfos.com
export PREVIEW_HOST=preview.nienfos.com

aws route53 list-hosted-zones-by-name --dns-name "$DOMAIN_NAME"
aws route53domains get-domain-detail --domain-name "$DOMAIN_NAME"
dig NS "$DOMAIN_NAME"
dig CNAME "$PREVIEW_HOST"
```

Expected:

- Registrar nameservers match the intended hosted zone or Cloudflare zone.
- `preview.nienfos.com` resolves through Cloudflare before apply is ready.
- Domain auto-renew is enabled if AWS owns the registration.

```bash
aws route53domains get-domain-detail --domain-name "$DOMAIN_NAME" \\
  --query '{{DomainName:DomainName,AutoRenew:AutoRenew,ExpirationDate:ExpirationDate}}'
```

If `AutoRenew=false`, keep preview delivery blocked and document the owner.
"""


def _email_provider_runbook(slug: str) -> str:
    return f"""# Web Preview Email Provider Runbook

Preview invite email is operator-owned. Missing provider config must fall back
to visible manual-link delivery; it must not fake successful delivery.

## Bridge Env Vars

```bash
WEB_PREVIEW_EMAIL_PROVIDER=cloudflare_email
WEB_PREVIEW_EMAIL_FROM=preview@nienfos.com
WEB_PREVIEW_EMAIL_ENDPOINT=https://api.cloudflare.example/email/send
WEB_PREVIEW_EMAIL_API_TOKEN=<operator-secret>
WEB_PREVIEW_INVITE_SECRET=<same-secret-as-worker>
```

`cloudflare_email` means the Bridge posts invite payloads to the
operator-provided `WEB_PREVIEW_EMAIL_ENDPOINT` with
`WEB_PREVIEW_EMAIL_API_TOKEN`. That endpoint may be a Cloudflare Worker or
another Cloudflare-backed mail transport controlled by the operator. Cloudflare
Email Routing alone is not assumed to send outbound mail; only report `sent`
when the configured endpoint accepts the message and returns success.

Repo-provided Cloudflare Worker endpoint:

```bash
cd deploy/cloudflare-email-endpoint
cp wrangler.toml.example wrangler.toml
wrangler secret put EMAIL_ENDPOINT_TOKEN
wrangler secret put BREVO_API_KEY
wrangler deploy
```

Set `WEB_PREVIEW_EMAIL_ENDPOINT` to the deployed Worker URL and set
`WEB_PREVIEW_EMAIL_API_TOKEN` to the same secret used for
`EMAIL_ENDPOINT_TOKEN`. Cloudflare Workers Free can host this endpoint, but
outbound mail still needs a sending backend. The included free-compatible relay
mode uses Brevo transactional email via `BREVO_API_KEY`. Native Cloudflare Email
Service sending to arbitrary invite recipients requires Workers Paid; Email
Routing is inbound/forwarding and is not enough by itself.

SMTP fallback:

```bash
WEB_PREVIEW_EMAIL_PROVIDER=smtp
WEB_PREVIEW_EMAIL_FROM=invites@nienfos.com
WEB_PREVIEW_SMTP_HOST=smtp.example.com
WEB_PREVIEW_SMTP_PORT=587
WEB_PREVIEW_SMTP_USERNAME=<smtp-user>
WEB_PREVIEW_SMTP_PASSWORD=<smtp-password>
WEB_PREVIEW_SMTP_USE_TLS=true
WEB_PREVIEW_SMTP_IMPLICIT_TLS=false
WEB_PREVIEW_SMTP_TIMEOUT_SECONDS=10
WEB_PREVIEW_INVITE_SECRET=<same-secret-as-worker>
```

Amazon SES SMTP profile (same pattern used by Ambientando Calendar):

```bash
WEB_PREVIEW_EMAIL_PROVIDER=smtp
WEB_PREVIEW_EMAIL_FROM=preview@nienfos.com
WEB_PREVIEW_SMTP_HOST=email-smtp.us-east-1.amazonaws.com
WEB_PREVIEW_SMTP_PORT=587
WEB_PREVIEW_SMTP_USERNAME=<ses-smtp-username>
WEB_PREVIEW_SMTP_PASSWORD=<ses-smtp-password>
WEB_PREVIEW_SMTP_USE_TLS=true
WEB_PREVIEW_SMTP_IMPLICIT_TLS=false
WEB_PREVIEW_SMTP_TIMEOUT_SECONDS=10
WEB_PREVIEW_INVITE_SECRET=<same-secret-as-worker>
```

SES currently includes up to 3,000 message charges per month for 12 months after
starting to use SES, subject to AWS free-tier account rules. This is separate
from SES sandbox: while sandboxed, both sender and recipient addresses must be
verified. Request SES production access before sending preview invites to
arbitrary users.

For implicit TLS on port `465`, set `WEB_PREVIEW_SMTP_IMPLICIT_TLS=true` so the
Bridge uses an SMTP_SSL-compatible client.

Manual fallback:

```bash
WEB_PREVIEW_EMAIL_PROVIDER=manual
```

## Sender Domain Verification

```bash
dig TXT nienfos.com
dig TXT default._domainkey.nienfos.com
dig TXT _dmarc.nienfos.com
```

Validate SPF, DKIM, DMARC alignment, sender permissions for
`preview@nienfos.com` or `invites@nienfos.com`, token/API scope, provider
diagnostics, and message IDs before reporting delivery as sent.

## Create And Resend Invites

```bash
BRIDGE_URL=http://127.0.0.1:8000
curl -X POST "$BRIDGE_URL/web-previews/wp-{slug}/invites" \\
  -H 'content-type: application/json' \\
  -d '{{"email":"admin@example.com","role":"owner","ttlSeconds":604800}}'

curl -X POST "$BRIDGE_URL/web-previews/wp-{slug}/invites/<invite-id>/resend" \\
  -H 'content-type: application/json' \\
  -d '{{"ttlSeconds":604800}}'
```

If response contains `manual_delivery_required=true`, copy `invite_url` through
an approved channel and keep email delivery visible as a manual-link state.
"""


def _dns_cloudflare_troubleshooting_runbook(slug: str) -> str:
    return f"""# DNS And Cloudflare Troubleshooting

Use this when Web Preview apply, health, or smoke checks fail for
`https://preview.nienfos.com/{slug}`.

## Required Env

```bash
CLOUDFLARE_API_TOKEN=<workers-d1-pages-token>
CLOUDFLARE_DNS_API_TOKEN=<dns-edit-token>
CLOUDFLARE_ACCOUNT_ID=<account-id>
CLOUDFLARE_ZONE_ID=<zone-id>
CLOUDFLARE_ZONE_NAME=nienfos.com
PREVIEW_D1_DATABASE=nienfos-preview
WEB_PREVIEW_APPLY_ENABLED=true
```

## Doctor And Plan

```bash
BRIDGE_URL=http://127.0.0.1:8000
curl "$BRIDGE_URL/project-factory/doctor"
scripts/deploy_web_preview.sh --plan
scripts/validate_cloudflare_cost_posture.sh
scripts/validate_web_preview.sh
```

## DNS Propagation

```bash
dig CNAME preview.nienfos.com
dig +trace preview.nienfos.com
curl -I https://preview.nienfos.com/{slug}/__preview/health
curl https://preview.nienfos.com/{slug}/api/health
```

Blocked states:

- `cloudflare_configuration_missing`: fill Bridge env vars above.
- `apply_disabled`: set `WEB_PREVIEW_APPLY_ENABLED=true` on the Bridge host.
- `preview_validation_failed`: run `scripts/validate_web_preview.sh` locally.
- `d1_database_id_missing`: rerun `scripts/apply_preview_d1_migrations.sh`.
- `health failed`: inspect Worker route and Cloudflare DNS proxy state.

These checks validate preview only. They do not claim production readiness.
"""


def _false_readiness_runbook(
    slug: str,
    frontend_strategy: str = "flutter",
) -> str:
    if frontend_strategy == "svelte":
        return f"""# False Readiness Examples

A Svelte Project Factory job is not ready until Cloudflare web health, Preview
API health, Preview API smoke, and Svelte build validation pass.

## Blocked Examples

```bash
VITE_APP_RUNTIME_PROFILE=mock \\
VITE_API_BASE_URL=https://preview.nienfos.com/{slug}/api \\
npm run validate:preview
```

Fails because Initial Preview Release cannot use mock as the runtime.

```bash
VITE_APP_RUNTIME_PROFILE=preview \\
VITE_API_BASE_URL=http://localhost:8000 \\
npm run validate:preview
```

Fails because preview cannot use localhost.

Codex Mobile catalog registration is blocked because Svelte web-only does not
generate native mobile package metadata.
"""
    return f"""# False Readiness Examples

A Project Factory job is not ready until Cloudflare health, Preview API smoke,
Android preview release, and Bridge registration all pass.

## Blocked Examples

```bash
APP_RELEASE_TAG=android-preview-v1.0.0 \\
APP_RUNTIME_PROFILE=mock \\
API_BASE_URL=https://preview.nienfos.com/{slug}/api \\
scripts/validate_release_profiles.sh
```

Fails because preview cannot use mock as the primary runtime.

```bash
APP_RELEASE_TAG=android-preview-v1.0.0 \\
APP_RUNTIME_PROFILE=preview \\
API_BASE_URL=http://localhost:8000 \\
scripts/validate_release_profiles.sh
```

Fails because installable preview releases cannot use localhost.

```bash
APP_RELEASE_TAG=android-v1.0.0 \\
APP_RUNTIME_PROFILE=preview \\
API_BASE_URL=https://preview.nienfos.com/{slug}/api \\
scripts/validate_release_profiles.sh
```

Fails because production promotion must use `APP_RUNTIME_PROFILE=real` and a real
production backend.

## Final Gate

```bash
scripts/validate_initial_preview_release.sh
```

This final gate verifies the preview runtime contract, Cloudflare manifest,
GitHub release/APK metadata, and Bridge installable-app metadata agree.
"""


def _mobile_files(name: str, slug: str) -> dict[str, str]:
    package_name = _dart_package_name(slug)
    return {
        "apps/mobile/pubspec.yaml": _mobile_pubspec(package_name),
        "apps/mobile/README.md": _mobile_readme(name),
        "apps/mobile/lib/main.dart": _mobile_main_dart(name),
        "apps/mobile/lib/src/config.dart": _mobile_config_dart(),
        "apps/mobile/lib/src/models.dart": _mobile_models_dart(),
        "apps/mobile/lib/src/api_client.dart": _mobile_api_client_dart(),
        "apps/mobile/lib/src/mock_api_client.dart": _mobile_mock_api_client_dart(),
        "apps/mobile/lib/src/session_controller.dart": _mobile_session_controller_dart(),
        "apps/mobile/lib/src/screens.dart": _mobile_screens_dart(name),
        "apps/mobile/web/index.html": _mobile_web_index_html(name),
        "apps/mobile/web/manifest.json": _mobile_web_manifest_json(name),
        "apps/mobile/android/.gitignore": "upload-keystore.jks\nkey.properties\n",
        "apps/mobile/android/app/src/main/AndroidManifest.xml": (
            _mobile_android_manifest()
        ),
        "apps/mobile/test/config_test.dart": _mobile_config_test_dart(package_name),
        "apps/mobile/test/api_client_test.dart": _mobile_api_client_test_dart(
            package_name
        ),
        "apps/mobile/test/session_controller_test.dart": (
            _mobile_session_controller_test_dart(package_name)
        ),
        "apps/mobile/test/workbench_visibility_test.dart": (
            _mobile_workbench_visibility_test_dart(package_name)
        ),
    }


def _dart_package_name(slug: str) -> str:
    package_name = slug.replace("-", "_")
    if package_name[0].isdigit():
        return f"app_{package_name}"
    return package_name


def _mobile_pubspec(package_name: str) -> str:
    return f"""name: {package_name}
description: Flutter app generated by Codex Mobile Bridge Project Factory.
publish_to: "none"
version: 0.1.0+1

environment:
  sdk: ">=3.4.0 <4.0.0"

dependencies:
  flutter:
    sdk: flutter
  http: ^1.2.2
  codex_developer_feedback_template:
    git:
      url: https://github.com/brunojaime/codex-cli-mobile-bridge.git
      path: packages/codex_developer_feedback_template
      ref: codex-developer-feedback-template-v0.2.1
  codex_app_updater:
    git:
      url: https://github.com/brunojaime/codex-cli-mobile-bridge.git
      path: packages/codex_app_updater
      ref: main
  codex_bridge_workbench:
    git:
      url: https://github.com/brunojaime/codex-cli-mobile-bridge.git
      path: packages/codex_bridge_workbench
      ref: main

dev_dependencies:
  flutter_test:
    sdk: flutter

flutter:
  uses-material-design: true
  assets:
    - assets/brand/
"""


def _mobile_readme(name: str) -> str:
    return f"""# {name} Mobile

Flutter app generated by Project Factory. It uses real backend calls and does
not include mock/demo runtime data.

## Run

Start the generated backend first, then run:

```bash
flutter pub get
flutter run --dart-define=API_BASE_URL=http://localhost:8000
```

For Android emulator talking to a backend on the host machine:

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

## Tests

```bash
flutter test
```

Session tokens are kept in memory in template v1. Add secure storage in a later
slice when persistence across app restarts is required.
"""


def _mobile_android_manifest() -> str:
    return """<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.INTERNET" />
    <application
        android:label="Generated Preview"
        android:name="${applicationName}"
        android:icon="@mipmap/ic_launcher">
        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:launchMode="singleTop"
            android:theme="@style/LaunchTheme"
            android:configChanges="orientation|keyboardHidden|keyboard|screenSize|smallestScreenSize|locale|layoutDirection|fontScale|screenLayout|density|uiMode"
            android:hardwareAccelerated="true"
            android:windowSoftInputMode="adjustResize">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
        <meta-data
            android:name="flutterEmbedding"
            android:value="2" />
    </application>
</manifest>
"""


def _mobile_web_index_html(name: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
  <base href="$FLUTTER_BASE_HREF">
  <meta charset="UTF-8">
  <meta content="IE=Edge" http-equiv="X-UA-Compatible">
  <meta name="description" content="{name} web preview">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="manifest" href="manifest.json">
  <title>{name}</title>
</head>
<body>
  <script src="flutter_bootstrap.js" async></script>
</body>
</html>
"""


def _mobile_web_manifest_json(name: str) -> str:
    return f"""{{
  "name": "{name}",
  "short_name": "{name}",
  "start_url": ".",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#00897b"
}}
"""


def _mobile_main_dart(name: str) -> str:
    return f"""import 'package:flutter/material.dart';
import 'package:codex_app_updater/codex_app_updater.dart';
import 'package:codex_bridge_workbench/codex_bridge_workbench.dart';
import 'package:codex_developer_feedback_template/developer_feedback_template.dart';
import 'package:http/http.dart' as http;

import 'src/api_client.dart';
import 'src/config.dart';
import 'src/mock_api_client.dart';
import 'src/screens.dart';
import 'src/session_controller.dart';

void main() {{
  const apiBaseUrl = String.fromEnvironment('API_BASE_URL');
  const runtimeProfile = String.fromEnvironment(
    'APP_RUNTIME_PROFILE',
    defaultValue: 'preview',
  );
  const apiRuntime = String.fromEnvironment(
    'API_RUNTIME',
    defaultValue: 'fastapi',
  );
  const appSlug = String.fromEnvironment('APP_SLUG');
  const developerWorkbenchEnabled = bool.fromEnvironment(
    'CODEX_BRIDGE_DEV_MODE',
    defaultValue: false,
  );
  const feedbackEnabled = bool.fromEnvironment(
    'CODEX_FEEDBACK_ENABLED',
    defaultValue: true,
  );
  const appUpdaterEnabled = bool.fromEnvironment(
    'CODEX_APP_UPDATER_ENABLED',
    defaultValue: false,
  );
  const feedbackBridgeUrl = String.fromEnvironment('CODEX_FEEDBACK_BRIDGE_URL');
  const workbenchBridgeUrl = String.fromEnvironment('CODEX_BRIDGE_WORKBENCH_URL');
  const updaterBridgeUrl = String.fromEnvironment('CODEX_APP_UPDATER_BRIDGE_URL');
  final config = AppConfig.fromEnvironment(
    apiBaseUrl: apiBaseUrl,
    runtimeProfile: runtimeProfile,
    apiRuntime: apiRuntime,
    appSlug: appSlug,
    developerWorkbenchEnabled: developerWorkbenchEnabled,
    feedbackEnabled: feedbackEnabled,
    appUpdaterEnabled: appUpdaterEnabled,
    feedbackBridgeUrl: feedbackBridgeUrl,
    workbenchBridgeUrl: workbenchBridgeUrl,
    updaterBridgeUrl: updaterBridgeUrl,
  );
  runApp(ProjectApp(config: config));
}}

class ProjectApp extends StatelessWidget {{
  const ProjectApp({{super.key, required this.config}});

  final AppConfig config;

  @override
  Widget build(BuildContext context) {{
    if (!config.isConfigured) {{
      return MaterialApp(
        title: '{name}',
        home: ConfigMissingScreen(message: config.errorMessage),
      );
    }}
    final api = config.isMock
        ? MockProjectApiClient()
        : ProjectApiClient(
            baseUrl: config.apiBaseUrl!,
            client: http.Client(),
          );
    final homeContent = ProjectHome(
      projectName: '{name}',
      runtimeProfile: config.runtimeProfile,
      developerWorkbenchEnabled: config.developerWorkbenchEnabled,
      controller: SessionController(
        api: api,
        runtimeProfile: config.runtimeProfile,
      ),
    );
    final workbenchWrapped = CodexBridgeDevModeWrapper(
      enabled: config.developerWorkbenchEnabled &&
          config.workbenchBridgeUrl != null &&
          config.workbenchBridgeUrl!.isNotEmpty,
      bridgeUrl: config.workbenchBridgeUrl ?? '',
      workspacePath: config.appSlug,
      child: homeContent,
    );
    final updaterWrapped = CodexAppUpdater(
      config: CodexAppUpdaterConfig(
        enabled: config.appUpdaterEnabled &&
            config.updaterBridgeUrl != null &&
            config.updaterBridgeUrl!.isNotEmpty,
        sourceApp: config.appSlug ?? 'generated-project',
        bridgeUrl: config.updaterBridgeUrl ?? '',
        currentVersion: '0.1.0',
        currentBuild: 1,
        channel: 'prerelease',
      ),
      checkOnStart: config.appUpdaterEnabled &&
          config.updaterBridgeUrl != null &&
          config.updaterBridgeUrl!.isNotEmpty,
      checkOnResume: config.appUpdaterEnabled &&
          config.updaterBridgeUrl != null &&
          config.updaterBridgeUrl!.isNotEmpty,
      child: workbenchWrapped,
    );
    final feedbackWrapped = DeveloperFeedbackTemplate(
      enabled: config.feedbackEnabled &&
          config.feedbackBridgeUrl != null &&
          config.feedbackBridgeUrl!.isNotEmpty,
      sourceApp: config.appSlug ?? 'generated-project',
      sourceDisplayName: '{name}',
      bridgeUrl: config.feedbackBridgeUrl ?? '',
      child: updaterWrapped,
    );
    return MaterialApp(
      title: '{name}',
      theme: ThemeData(useMaterial3: true, colorSchemeSeed: Colors.teal),
      home: feedbackWrapped,
    );
  }}
}}
"""


def _mobile_config_dart() -> str:
    return """class AppConfig {
  const AppConfig({
    required this.apiBaseUrl,
    required this.runtimeProfile,
    required this.apiRuntime,
    required this.appSlug,
    required this.developerWorkbenchEnabled,
    required this.feedbackEnabled,
    required this.appUpdaterEnabled,
    required this.feedbackBridgeUrl,
    required this.workbenchBridgeUrl,
    required this.updaterBridgeUrl,
  });

  final String? apiBaseUrl;
  final String runtimeProfile;
  final String apiRuntime;
  final String? appSlug;
  final bool developerWorkbenchEnabled;
  final bool feedbackEnabled;
  final bool appUpdaterEnabled;
  final String? feedbackBridgeUrl;
  final String? workbenchBridgeUrl;
  final String? updaterBridgeUrl;

  bool get isMock => runtimeProfile == 'mock';
  bool get isPreview => apiRuntime == 'cloudflare_preview';

  bool get isConfigured =>
      isMock ||
      (apiBaseUrl != null &&
          apiBaseUrl!.isNotEmpty &&
          (!isPreview || (appSlug != null && appSlug!.isNotEmpty)));

  String get errorMessage {
    if (runtimeProfile != 'mock' &&
        runtimeProfile != 'real' &&
        runtimeProfile != 'staging' &&
        runtimeProfile != 'preview') {
      return 'APP_RUNTIME_PROFILE must be mock, real, staging, or preview.';
    }
    if (isPreview && (appSlug == null || appSlug!.isEmpty)) {
      return 'APP_SLUG is required for API_RUNTIME=cloudflare_preview.';
    }
    return 'API_BASE_URL is required for APP_RUNTIME_PROFILE=$runtimeProfile.';
  }

  factory AppConfig.fromEnvironment({
    required String apiBaseUrl,
    required String runtimeProfile,
    String apiRuntime = 'fastapi',
    String appSlug = '',
    bool developerWorkbenchEnabled = false,
    bool feedbackEnabled = true,
    bool appUpdaterEnabled = false,
    String feedbackBridgeUrl = '',
    String workbenchBridgeUrl = '',
    String updaterBridgeUrl = '',
  }) {
    final trimmed = apiBaseUrl.trim().replaceAll(RegExp(r'/$'), '');
    final normalizedProfile = runtimeProfile.trim().toLowerCase();
    final normalizedApiRuntime = apiRuntime.trim().toLowerCase();
    final trimmedSlug = appSlug.trim();
    return AppConfig(
      apiBaseUrl: trimmed.isEmpty ? null : trimmed,
      runtimeProfile: normalizedProfile.isEmpty ? 'preview' : normalizedProfile,
      apiRuntime: normalizedApiRuntime.isEmpty ? 'fastapi' : normalizedApiRuntime,
      appSlug: trimmedSlug.isEmpty ? null : trimmedSlug,
      developerWorkbenchEnabled: developerWorkbenchEnabled,
      feedbackEnabled: feedbackEnabled,
      appUpdaterEnabled: appUpdaterEnabled,
      feedbackBridgeUrl: _emptyToNull(feedbackBridgeUrl),
      workbenchBridgeUrl: _emptyToNull(workbenchBridgeUrl),
      updaterBridgeUrl: _emptyToNull(updaterBridgeUrl),
    );
  }
}

String? _emptyToNull(String value) {
  final trimmed = value.trim().replaceAll(RegExp(r'/$'), '');
  return trimmed.isEmpty ? null : trimmed;
}
"""


def _mobile_models_dart() -> str:
    return """class AppUser {
  const AppUser({required this.id, required this.email, required this.roles});

  final String id;
  final String email;
  final List<String> roles;

  bool get canAccessAdmin => roles.contains('owner') || roles.contains('admin');
  bool get isDeveloperAuthorized => roles.contains('developer');

  bool canAccessWorkbench(
    String runtimeProfile, {
    bool developerModeAuthorized = false,
  }) {
    return false;
  }

  factory AppUser.fromJson(Map<String, dynamic> json) {
    return AppUser(
      id: json['id'].toString(),
      email: json['email'] as String,
      roles: (json['roles'] as List<dynamic>? ?? <dynamic>[])
          .whereType<String>()
          .toList(growable: false),
    );
  }
}

class AuthToken {
  const AuthToken({required this.accessToken, required this.tokenType});

  final String accessToken;
  final String tokenType;

  factory AuthToken.fromJson(Map<String, dynamic> json) {
    return AuthToken(
      accessToken: json['access_token'] as String,
      tokenType: json['token_type'] as String? ?? 'bearer',
    );
  }
}

class AdminUser {
  const AdminUser({required this.id, required this.email, required this.isActive});
  final String id;
  final String email;
  final bool isActive;

  factory AdminUser.fromJson(Map<String, dynamic> json) {
    return AdminUser(
      id: json['id'].toString(),
      email: json['email'] as String,
      isActive: json['is_active'] as bool? ?? true,
    );
  }
}

class BusinessRecord {
  const BusinessRecord({required this.id, required this.name, required this.isActive});
  final String id;
  final String name;
  final bool isActive;

  factory BusinessRecord.fromJson(Map<String, dynamic> json) {
    return BusinessRecord(
      id: json['id'].toString(),
      name: json['name'] as String,
      isActive: json['is_active'] as bool? ?? true,
    );
  }
}

class AppNotification {
  const AppNotification({
    required this.id,
    required this.title,
    required this.body,
    required this.readAt,
    required this.createdAt,
  });

  final String id;
  final String title;
  final String body;
  final String? readAt;
  final String createdAt;

  bool get isRead => readAt != null;

  factory AppNotification.fromJson(Map<String, dynamic> json) {
    return AppNotification(
      id: json['id'].toString(),
      title: json['title'] as String,
      body: json['body'] as String,
      readAt: (json['read_at'] ?? json['readAt']) as String?,
      createdAt: (json['created_at'] ?? json['createdAt']).toString(),
    );
  }
}
"""


def _mobile_api_client_dart() -> str:
    return """import 'dart:convert';

import 'package:http/http.dart' as http;

import 'models.dart';

class ProjectApiClient {
  ProjectApiClient({required this.baseUrl, http.Client? client})
      : _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;

  Future<bool> health() async {
    final response = await _client.get(Uri.parse('$baseUrl/health'));
    return response.statusCode == 200;
  }

  Future<AuthToken> register({required String email, required String password}) async {
    final response = await _postJson('/auth/register', {'email': email, 'password': password});
    if (response.statusCode != 200) {
      throw ApiException('Register failed', response.statusCode, response.body);
    }
    return login(email: email, password: password);
  }

  Future<AuthToken> login({required String email, required String password}) async {
    final response = await _postJson('/auth/login', {'email': email, 'password': password});
    if (response.statusCode != 200) {
      throw ApiException('Login failed', response.statusCode, response.body);
    }
    return AuthToken.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<AuthToken> acceptPreviewInvite({
    required String inviteToken,
    required String email,
    required String password,
    required String passwordConfirmation,
  }) async {
    final response = await _postJson('/invites/accept', {
      'inviteToken': inviteToken,
      'email': email,
      'password': password,
      'passwordConfirmation': passwordConfirmation,
    });
    if (response.statusCode != 200) {
      throw ApiException('Preview invite accept failed', response.statusCode, response.body);
    }
    return AuthToken.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<AppUser> me(String token) async {
    final response = await _client.get(_uri('/auth/me'), headers: _authHeaders(token));
    if (response.statusCode != 200) {
      throw ApiException('Me failed', response.statusCode, response.body);
    }
    return AppUser.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<void> logout(String token) async {
    await _client.post(_uri('/auth/logout'), headers: _authHeaders(token));
  }

  Future<List<AdminUser>> adminUsers(String token) async {
    final response = await _client.get(_uri('/admin/users'), headers: _authHeaders(token));
    if (response.statusCode != 200) {
      throw ApiException('Admin users failed', response.statusCode, response.body);
    }
    return _list(response).map(AdminUser.fromJson).toList(growable: false);
  }

  Future<List<String>> adminRoles(String token) async {
    final response = await _client.get(_uri('/admin/roles'), headers: _authHeaders(token));
    if (response.statusCode != 200) {
      throw ApiException('Admin roles failed', response.statusCode, response.body);
    }
    return (jsonDecode(response.body) as List<dynamic>).whereType<String>().toList();
  }

  Future<List<BusinessRecord>> businessRecords(String token) async {
    final response = await _client.get(_uri('/admin/business-records'), headers: _authHeaders(token));
    if (response.statusCode != 200) {
      throw ApiException('Domains failed', response.statusCode, response.body);
    }
    return _list(response).map(BusinessRecord.fromJson).toList(growable: false);
  }

  Future<BusinessRecord> createBusinessRecord(String token, String name) async {
    final response = await _postJson('/admin/business-records', {'name': name}, token: token);
    if (response.statusCode != 200) {
      throw ApiException('Create business record failed', response.statusCode, response.body);
    }
    return BusinessRecord.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<List<AppNotification>> notifications(String token) async {
    final response = await _client.get(_uri('/notifications'), headers: _authHeaders(token));
    if (response.statusCode != 200) {
      throw ApiException('Notifications failed', response.statusCode, response.body);
    }
    return _list(response).map(AppNotification.fromJson).toList(growable: false);
  }

  Future<void> markNotificationRead(String token, String id) async {
    final response = await _client.post(_uri('/notifications/$id/read'), headers: _authHeaders(token));
    if (response.statusCode != 200) {
      throw ApiException('Mark notification read failed', response.statusCode, response.body);
    }
  }

  Future<http.Response> _postJson(String path, Map<String, Object?> body, {String? token}) {
    return _client.post(
      _uri(path),
      headers: <String, String>{
        'Content-Type': 'application/json',
        if (token != null) ..._authHeaders(token),
      },
      body: jsonEncode(body),
    );
  }

  Uri _uri(String path) => Uri.parse('$baseUrl$path');

  Map<String, String> _authHeaders(String token) {
    return {'Authorization': 'Bearer $token'};
  }

  List<Map<String, dynamic>> _list(http.Response response) {
    return (jsonDecode(response.body) as List<dynamic>)
        .cast<Map<String, dynamic>>();
  }
}

class ApiException implements Exception {
  ApiException(this.message, this.statusCode, this.body);
  final String message;
  final int statusCode;
  final String body;

  @override
  String toString() => '$message ($statusCode): $body';
}
"""


def _mobile_mock_api_client_dart() -> str:
    return """import 'api_client.dart';
import 'models.dart';

class MockProjectApiClient extends ProjectApiClient {
  MockProjectApiClient() : super(baseUrl: 'mock://local');

  final Map<String, AppUser> _sessions = <String, AppUser>{};
  final List<AdminUser> _users = <AdminUser>[];
  final List<BusinessRecord> _businessRecords = <BusinessRecord>[
    BusinessRecord(id: '1', name: 'Demo workspace', isActive: true),
  ];
  final List<AppNotification> _notifications = <AppNotification>[
    AppNotification(
      id: '1',
      title: 'Demo notification',
      body: 'This notification exists only in APP_RUNTIME_PROFILE=mock.',
      readAt: null,
      createdAt: 'mock',
    ),
  ];

  static const seedRoles = <String>[
    'owner',
    'admin',
    'manager',
    'staff',
    'employee',
    'customer',
    'guest',
  ];

  @override
  Future<bool> health() async => true;

  Future<AuthToken> loginAsRole(String role) async {
    final safeRole = seedRoles.contains(role) ? role : 'guest';
    final token = 'mock-token-$safeRole';
    final user = AppUser(
      id: '${seedRoles.indexOf(safeRole) + 1}',
      email: '$safeRole@mock.local',
      roles: <String>[safeRole],
    );
    _sessions[token] = user;
    _users.add(AdminUser(id: user.id, email: user.email, isActive: true));
    return AuthToken(accessToken: token, tokenType: 'mock');
  }

  @override
  Future<AuthToken> register({
    required String email,
    required String password,
  }) async {
    final token = 'mock-token-user-${_sessions.length + 1}';
    final user = AppUser(id: '${_sessions.length + 1}', email: email, roles: const <String>['customer']);
    _sessions[token] = user;
    _users.add(AdminUser(id: user.id, email: user.email, isActive: true));
    return AuthToken(accessToken: token, tokenType: 'mock');
  }

  @override
  Future<AuthToken> login({required String email, required String password}) {
    return register(email: email, password: password);
  }

  @override
  Future<AppUser> me(String token) async => _sessions[token] ?? const AppUser(id: '0', email: 'guest@mock.local', roles: <String>['guest']);

  @override
  Future<void> logout(String token) async {}

  @override
  Future<List<AdminUser>> adminUsers(String token) async => List<AdminUser>.from(_users);

  @override
  Future<List<String>> adminRoles(String token) async => seedRoles;

  @override
  Future<List<BusinessRecord>> businessRecords(String token) async => List<BusinessRecord>.from(_businessRecords);

  @override
  Future<BusinessRecord> createBusinessRecord(String token, String name) async {
    final domain = BusinessRecord(id: '${_businessRecords.length + 1}', name: name, isActive: true);
    _businessRecords.add(domain);
    return domain;
  }

  @override
  Future<List<AppNotification>> notifications(String token) async => List<AppNotification>.from(_notifications);

  @override
  Future<void> markNotificationRead(String token, String id) async {}
}
"""


def _mobile_session_controller_dart() -> str:
    return """import 'package:flutter/foundation.dart';

import 'api_client.dart';
import 'mock_api_client.dart';
import 'models.dart';

class SessionController extends ChangeNotifier {
  SessionController({required this.api, required this.runtimeProfile});

  final ProjectApiClient api;
  final String runtimeProfile;
  String? token;
  AppUser? user;
  bool loading = false;
  String? error;

  bool get isMockRuntime => runtimeProfile == 'mock';
  bool get isPreviewRuntime => runtimeProfile == 'preview';

  List<String> get seedRoles => MockProjectApiClient.seedRoles;

  bool get isAuthenticated => token != null && user != null;

  Future<void> login({required String email, required String password}) async {
    await _run(() async {
      final auth = await api.login(email: email, password: password);
      token = auth.accessToken;
      user = await api.me(token!);
    });
  }

  Future<void> register({required String email, required String password}) async {
    await _run(() async {
      final auth = await api.register(email: email, password: password);
      token = auth.accessToken;
      user = await api.me(token!);
    });
  }

  Future<void> acceptPreviewInvite({
    required String inviteToken,
    required String email,
    required String password,
    required String passwordConfirmation,
  }) async {
    await _run(() async {
      final auth = await api.acceptPreviewInvite(
        inviteToken: inviteToken,
        email: email,
        password: password,
        passwordConfirmation: passwordConfirmation,
      );
      token = auth.accessToken;
      user = await api.me(token!);
    });
  }

  Future<void> loginAsSeedRole(String role) async {
    if (!isMockRuntime || api is! MockProjectApiClient) return;
    await _run(() async {
      final auth = await (api as MockProjectApiClient).loginAsRole(role);
      token = auth.accessToken;
      user = await api.me(token!);
    });
  }

  Future<void> logout() async {
    final currentToken = token;
    token = null;
    user = null;
    notifyListeners();
    if (currentToken != null) {
      await api.logout(currentToken);
    }
  }

  Future<void> _run(Future<void> Function() action) async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      await action();
    } catch (err) {
      error = err.toString();
    } finally {
      loading = false;
      notifyListeners();
    }
  }
}
"""


def _mobile_screens_dart(name: str) -> str:
    return f"""import 'package:flutter/material.dart';

import 'api_client.dart';
import 'models.dart';
import 'session_controller.dart';

class ConfigMissingScreen extends StatelessWidget {{
  const ConfigMissingScreen({{super.key, required this.message}});
  final String message;

  @override
  Widget build(BuildContext context) {{
    return Scaffold(
      appBar: AppBar(title: const Text('{name}')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(message, textAlign: TextAlign.center),
        ),
      ),
    );
  }}
}}

class ProjectHome extends StatefulWidget {{
  const ProjectHome({{
    super.key,
    required this.projectName,
    required this.runtimeProfile,
    required this.developerWorkbenchEnabled,
    required this.controller,
  }});

  final String projectName;
  final String runtimeProfile;
  final bool developerWorkbenchEnabled;
  final SessionController controller;

  @override
  State<ProjectHome> createState() => _ProjectHomeState();
}}

class _ProjectHomeState extends State<ProjectHome> {{
  int _index = 0;

  @override
  Widget build(BuildContext context) {{
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) {{
        if (!widget.controller.isAuthenticated) {{
          return AuthScreen(controller: widget.controller, projectName: widget.projectName);
        }}
        final user = widget.controller.user!;
        final pages = <Widget>[
          HomeScreen(user: user, onLogout: widget.controller.logout),
          NotificationsScreen(api: widget.controller.api, token: widget.controller.token!),
          if (user.canAccessAdmin)
            AdminScreen(api: widget.controller.api, token: widget.controller.token!),
        ];
        return Scaffold(
          appBar: AppBar(title: Text(widget.projectName)),
          body: pages[_index.clamp(0, pages.length - 1)],
          bottomNavigationBar: NavigationBar(
            selectedIndex: _index.clamp(0, pages.length - 1),
            onDestinationSelected: (value) => setState(() => _index = value),
            destinations: <Widget>[
              const NavigationDestination(icon: Icon(Icons.home_outlined), label: 'Home'),
              const NavigationDestination(icon: Icon(Icons.notifications_outlined), label: 'Notifications'),
              if (user.canAccessAdmin)
                const NavigationDestination(icon: Icon(Icons.admin_panel_settings_outlined), label: 'Admin'),
            ],
          ),
        );
      }},
    );
  }}
}}

class AuthScreen extends StatefulWidget {{
  const AuthScreen({{
    super.key,
    required this.controller,
    required this.projectName,
    this.initialUri,
  }});
  final SessionController controller;
  final String projectName;
  final Uri? initialUri;

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}}

class _AuthScreenState extends State<AuthScreen> {{
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _passwordConfirmation = TextEditingController();
  bool _register = false;
  String _seedRole = 'owner';
  late final String? _inviteTokenFromUrl;
  late final bool _emailBound;
  late final String _inviteState;

  @override
  void initState() {{
    super.initState();
    final uri = widget.initialUri ?? Uri.base;
    _inviteTokenFromUrl = uri.queryParameters['invite_token'] ?? uri.queryParameters['token'];
    _inviteState = uri.queryParameters['invite_state'] ?? (_inviteTokenFromUrl == null ? 'login' : 'activate');
    final invitedEmail = uri.queryParameters['email'] ?? '';
    _emailBound = uri.queryParameters['email_bound'] == 'true' && invitedEmail.isNotEmpty;
    if (invitedEmail.isNotEmpty) {{
      _email.text = invitedEmail;
    }}
  }}

  @override
  void dispose() {{
    _email.dispose();
    _password.dispose();
    _passwordConfirmation.dispose();
    super.dispose();
  }}

  @override
  Widget build(BuildContext context) {{
    return Scaffold(
      appBar: AppBar(title: Text(widget.projectName)),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(_title, style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 12),
                TextField(
                  controller: _email,
                  readOnly: _emailBound,
                  decoration: InputDecoration(labelText: 'Email', helperText: _emailBound ? 'Fixed by invite' : null),
                ),
                const SizedBox(height: 12),
                TextField(controller: _password, decoration: InputDecoration(labelText: _isInviteActivation ? 'Crear contraseña' : 'Contraseña'), obscureText: true),
                if (_isInviteActivation) ...[
                  const SizedBox(height: 12),
                  TextField(controller: _passwordConfirmation, decoration: const InputDecoration(labelText: 'Repetir contraseña'), obscureText: true),
                ],
                const SizedBox(height: 16),
                if (widget.controller.isMockRuntime) ...[
                  DropdownButtonFormField<String>(
                    initialValue: _seedRole,
                    decoration: const InputDecoration(labelText: 'Demo role'),
                    items: widget.controller.seedRoles
                        .map((role) => DropdownMenuItem(value: role, child: Text(role)))
                        .toList(),
                    onChanged: (value) => setState(() => _seedRole = value ?? 'guest'),
                  ),
                  const SizedBox(height: 8),
                  OutlinedButton(
                    onPressed: widget.controller.loading
                        ? null
                        : () => widget.controller.loginAsSeedRole(_seedRole),
                    child: const Text('Enter demo as role'),
                  ),
                  const SizedBox(height: 12),
                ],
                if (widget.controller.error != null)
                  Text(widget.controller.error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                const SizedBox(height: 8),
                FilledButton(
                  onPressed: widget.controller.loading ? null : _submit,
                  child: Text(_primaryAction),
                ),
                if (!widget.controller.isPreviewRuntime)
                  TextButton(
                    onPressed: () => setState(() => _register = !_register),
                    child: Text(_register ? 'Usar inicio de sesión' : 'Crear cuenta'),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }}

  bool get _isInviteActivation =>
      widget.controller.isPreviewRuntime &&
      _inviteTokenFromUrl != null &&
      _inviteState != 'login';

  String get _title {{
    if (_isInviteActivation) return 'Aceptar invitación al Preview';
    return widget.controller.isPreviewRuntime ? 'Ingreso Preview' : (_register ? 'Crear cuenta' : 'Iniciar sesión');
  }}

  String get _primaryAction {{
    if (_isInviteActivation) return 'Aceptar invitación';
    return _register && !widget.controller.isPreviewRuntime ? 'Crear cuenta' : 'Iniciar sesión';
  }}

  Future<void> _submit() async {{
    if (_isInviteActivation) {{
      if (_password.text != _passwordConfirmation.text) {{
        setState(() => widget.controller.error = 'Las contraseñas deben coincidir.');
        return;
      }}
      await widget.controller.acceptPreviewInvite(
        inviteToken: _inviteTokenFromUrl!,
        email: _email.text.trim(),
        password: _password.text,
        passwordConfirmation: _passwordConfirmation.text,
      );
    }} else if (widget.controller.isPreviewRuntime) {{
      await widget.controller.login(email: _email.text.trim(), password: _password.text);
    }} else if (_register) {{
      await widget.controller.register(email: _email.text.trim(), password: _password.text);
    }} else {{
      await widget.controller.login(email: _email.text.trim(), password: _password.text);
    }}
  }}
}}

class HomeScreen extends StatelessWidget {{
  const HomeScreen({{super.key, required this.user, required this.onLogout}});
  final AppUser user;
  final Future<void> Function() onLogout;

  @override
  Widget build(BuildContext context) {{
    return ListView(
      padding: const EdgeInsets.all(20),
      children: <Widget>[
        Text(user.email, style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        Text('Roles: ${{user.roles.join(', ')}}'),
        const SizedBox(height: 16),
        OutlinedButton(onPressed: onLogout, child: const Text('Logout')),
      ],
    );
  }}
}}

class AdminScreen extends StatefulWidget {{
  const AdminScreen({{super.key, required this.api, required this.token}});
  final ProjectApiClient api;
  final String token;

  @override
  State<AdminScreen> createState() => _AdminScreenState();
}}

class _AdminScreenState extends State<AdminScreen> {{
  late Future<void> _load;
  List<AdminUser> _users = <AdminUser>[];
  List<String> _roles = <String>[];
  List<BusinessRecord> _businessRecords = <BusinessRecord>[];
  final _domain = TextEditingController();

  @override
  void initState() {{
    super.initState();
    _load = _refresh();
  }}

  @override
  void dispose() {{
    _domain.dispose();
    super.dispose();
  }}

  Future<void> _refresh() async {{
    _users = await widget.api.adminUsers(widget.token);
    _roles = await widget.api.adminRoles(widget.token);
    _businessRecords = await widget.api.businessRecords(widget.token);
  }}

  @override
  Widget build(BuildContext context) {{
    return FutureBuilder<void>(
      future: _load,
      builder: (context, snapshot) {{
        if (snapshot.connectionState != ConnectionState.done) {{
          return const Center(child: CircularProgressIndicator());
        }}
        if (snapshot.hasError) {{
          return Center(child: Text(snapshot.error.toString()));
        }}
        return ListView(
          padding: const EdgeInsets.all(20),
          children: <Widget>[
            Text('Users', style: Theme.of(context).textTheme.titleMedium),
            if (_users.isEmpty) const Text('No users'),
            ..._users.map((user) => ListTile(title: Text(user.email), subtitle: Text(user.isActive ? 'active' : 'inactive'))),
            const Divider(),
            Text('Roles: ${{_roles.join(', ')}}'),
            const Divider(),
            TextField(controller: _domain, decoration: const InputDecoration(labelText: 'New business record')),
            FilledButton(onPressed: _createBusinessRecord, child: const Text('Create business record')),
            if (_businessRecords.isEmpty) const Text('No business records'),
            ..._businessRecords.map((domain) => ListTile(title: Text(domain.name))),
          ],
        );
      }},
    );
  }}

  Future<void> _createBusinessRecord() async {{
    final name = _domain.text.trim();
    if (name.isEmpty) return;
    await widget.api.createBusinessRecord(widget.token, name);
    _domain.clear();
    setState(() => _load = _refresh());
  }}
}}

class NotificationsScreen extends StatefulWidget {{
  const NotificationsScreen({{super.key, required this.api, required this.token}});
  final ProjectApiClient api;
  final String token;

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}}

class _NotificationsScreenState extends State<NotificationsScreen> {{
  late Future<List<AppNotification>> _load;

  @override
  void initState() {{
    super.initState();
    _load = widget.api.notifications(widget.token);
  }}

  @override
  Widget build(BuildContext context) {{
    return FutureBuilder<List<AppNotification>>(
      future: _load,
      builder: (context, snapshot) {{
        if (snapshot.connectionState != ConnectionState.done) {{
          return const Center(child: CircularProgressIndicator());
        }}
        if (snapshot.hasError) {{
          return Center(child: Text(snapshot.error.toString()));
        }}
        final items = snapshot.data ?? <AppNotification>[];
        if (items.isEmpty) {{
          return const Center(child: Text('No notifications'));
        }}
        return ListView(
          children: items.map((item) {{
            return ListTile(
              title: Text(item.title),
              subtitle: Text(item.body),
              trailing: item.isRead
                  ? const Icon(Icons.done)
                  : IconButton(
                      icon: const Icon(Icons.mark_email_read_outlined),
                      onPressed: () async {{
                        await widget.api.markNotificationRead(widget.token, item.id);
                        setState(() => _load = widget.api.notifications(widget.token));
                      }},
                    ),
            );
          }}).toList(),
        );
      }},
    );
  }}
}}
"""


def _mobile_config_test_dart(package_name: str) -> str:
    return f"""import 'package:flutter_test/flutter_test.dart';
import 'package:{package_name}/src/config.dart';

void main() {{
  test('real config requires API_BASE_URL and mock is opt-in without backend', () {{
    expect(AppConfig.fromEnvironment(apiBaseUrl: '', runtimeProfile: 'real').isConfigured, isFalse);
    expect(AppConfig.fromEnvironment(apiBaseUrl: '', runtimeProfile: 'mock').isConfigured, isTrue);
    final preview = AppConfig.fromEnvironment(
      apiBaseUrl: 'https://preview.nienfos.com/clinica-norte/api',
      runtimeProfile: 'preview',
      apiRuntime: 'cloudflare_preview',
      appSlug: 'clinica-norte',
      developerWorkbenchEnabled: true,
    );
    expect(preview.isConfigured, isTrue);
    expect(preview.isPreview, isTrue);
    expect(preview.appSlug, 'clinica-norte');
    expect(preview.developerWorkbenchEnabled, isTrue);
    expect(
      AppConfig.fromEnvironment(apiBaseUrl: 'http://localhost:8000/', runtimeProfile: 'real').apiBaseUrl,
      'http://localhost:8000',
    );
  }});
}}
"""


def _mobile_api_client_test_dart(package_name: str) -> str:
    return f"""import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:{package_name}/src/api_client.dart';

void main() {{
  test('api client calls auth admin and notifications endpoints', () async {{
    final calls = <String>[];
    final api = ProjectApiClient(
      baseUrl: 'http://api.test',
      client: MockClient((request) async {{
        calls.add('${{request.method}} ${{request.url.path}}');
        if (request.url.path == '/health') return http.Response('{{"status":"ok"}}', 200);
        if (request.url.path == '/invites/accept') return http.Response('{{"access_token":"invite-token","token_type":"bearer"}}', 200);
        if (request.url.path == '/auth/login') return http.Response('{{"access_token":"t","token_type":"bearer"}}', 200);
        if (request.url.path == '/auth/me') return http.Response('{{"id":1,"email":"a@example.com","roles":["owner"]}}', 200);
        if (request.url.path == '/admin/users') return http.Response('[{{"id":1,"email":"a@example.com","is_active":true}}]', 200);
        if (request.url.path == '/admin/roles') return http.Response('["owner","customer"]', 200);
        if (request.url.path == '/admin/business-records' && request.method == 'GET') return http.Response('[{{"id":1,"name":"primary","is_active":true}}]', 200);
        if (request.url.path == '/admin/business-records' && request.method == 'POST') return http.Response('{{"id":2,"name":"new","is_active":true}}', 200);
        if (request.url.path == '/notifications' && request.method == 'GET') return http.Response('[{{"id":1,"title":"Welcome","body":"Hi","read_at":null,"created_at":"now"}}]', 200);
        if (request.url.path == '/notifications/1/read') return http.Response('{{"status":"read"}}', 200);
        return http.Response('missing', 404);
      }}),
    );
    expect(await api.health(), isTrue);
    final inviteToken = await api.acceptPreviewInvite(
      inviteToken: 'signed-token',
      email: 'invite@example.com',
      password: 'secret',
      passwordConfirmation: 'secret',
    );
    expect(inviteToken.accessToken, 'invite-token');
    final token = await api.login(email: 'a@example.com', password: 'secret');
    expect(token.accessToken, 't');
    expect((await api.me('t')).canAccessAdmin, isTrue);
    expect(await api.adminUsers('t'), hasLength(1));
    expect(await api.adminRoles('t'), contains('owner'));
    expect(await api.businessRecords('t'), hasLength(1));
    expect((await api.createBusinessRecord('t', 'new')).name, 'new');
    expect(await api.notifications('t'), hasLength(1));
    await api.markNotificationRead('t', '1');
    expect(calls, contains('GET /health'));
    expect(calls, contains('POST /invites/accept'));
  }});
}}
"""


def _mobile_session_controller_test_dart(package_name: str) -> str:
    return f"""import 'package:flutter_test/flutter_test.dart';
import 'package:{package_name}/src/api_client.dart';
import 'package:{package_name}/src/mock_api_client.dart';
import 'package:{package_name}/src/models.dart';
import 'package:{package_name}/src/session_controller.dart';

void main() {{
  test('session login stores token and user', () async {{
    final controller = SessionController(api: _FakeApi(), runtimeProfile: 'real');
    await controller.login(email: 'admin@example.com', password: 'secret');
    expect(controller.isAuthenticated, isTrue);
    expect(controller.user!.canAccessAdmin, isTrue);
  }});

  test('preview invite accept stores token and user', () async {{
    final controller = SessionController(api: _FakeApi(), runtimeProfile: 'preview');
    await controller.acceptPreviewInvite(
      inviteToken: 'signed-token',
      email: 'admin@example.com',
      password: 'secret',
      passwordConfirmation: 'secret',
    );
    expect(controller.isAuthenticated, isTrue);
    expect(controller.token, 'invite-token');
    expect(controller.user!.canAccessAdmin, isTrue);
  }});

  test('mock runtime can enter as seed role', () async {{
    final controller = SessionController(
      api: MockProjectApiClient(),
      runtimeProfile: 'mock',
    );
    await controller.loginAsSeedRole('manager');
    expect(controller.isAuthenticated, isTrue);
    expect(controller.user!.roles, contains('manager'));
  }});

  test('rbac denies admin for customer role', () {{
    const user = AppUser(id: '1', email: 'user@example.com', roles: ['customer']);
    expect(user.canAccessAdmin, isFalse);
  }});

  test('product RBAC never grants Bridge Workbench UI inside the generated app', () {{
    const owner = AppUser(id: '1', email: 'owner@example.com', roles: ['owner']);
    const admin = AppUser(id: '2', email: 'admin@example.com', roles: ['admin']);
    const developer = AppUser(id: '3', email: 'dev@example.com', roles: ['developer']);
    const customer = AppUser(id: '4', email: 'user@example.com', roles: ['customer']);
    expect(owner.canAccessWorkbench('preview'), isFalse);
    expect(admin.canAccessWorkbench('preview'), isFalse);
    expect(developer.canAccessWorkbench('preview'), isFalse);
    expect(
      developer.canAccessWorkbench('preview', developerModeAuthorized: true),
      isFalse,
    );
    expect(customer.canAccessWorkbench('preview'), isFalse);
    expect(owner.canAccessWorkbench('real', developerModeAuthorized: true), isFalse);
  }});
}}

class _FakeApi extends ProjectApiClient {{
  _FakeApi() : super(baseUrl: 'http://fake');

  @override
  Future<AuthToken> login({{required String email, required String password}}) async {{
    return const AuthToken(accessToken: 'token', tokenType: 'bearer');
  }}

  @override
  Future<AuthToken> acceptPreviewInvite({{
    required String inviteToken,
    required String email,
    required String password,
    required String passwordConfirmation,
  }}) async {{
    return const AuthToken(accessToken: 'invite-token', tokenType: 'bearer');
  }}

  @override
  Future<AppUser> me(String token) async {{
    return const AppUser(id: '1', email: 'admin@example.com', roles: ['owner']);
  }}
}}
"""


def _mobile_workbench_visibility_test_dart(package_name: str) -> str:
    return f"""import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:{package_name}/main.dart';
import 'package:{package_name}/src/api_client.dart';
import 'package:{package_name}/src/config.dart';
import 'package:{package_name}/src/models.dart';
import 'package:{package_name}/src/screens.dart';
import 'package:{package_name}/src/session_controller.dart';

void main() {{
  testWidgets('preview auth consumes URL invite token and asks for password confirmation', (tester) async {{
    final controller = SessionController(api: _FakeApi(), runtimeProfile: 'preview');
    await tester.pumpWidget(MaterialApp(
      home: AuthScreen(
        controller: controller,
        projectName: 'Generated App',
        initialUri: Uri.parse('https://preview.nienfos.com/generated/?invite_state=activate&invite_token=signed-token&email=admin@example.com&email_bound=true'),
      ),
    ));

    expect(find.text('Aceptar invitación al Preview'), findsOneWidget);
    expect(find.text('Crear contraseña'), findsOneWidget);
    expect(find.text('Repetir contraseña'), findsOneWidget);
    expect(find.text('Aceptar invitación'), findsOneWidget);
    expect(find.text('Create' ' password'), findsNothing);
    expect(find.text('Repeat' ' password'), findsNothing);
    expect(find.text('Activate' ' account'), findsNothing);
    expect(find.text('Invite token or link'), findsNothing);

    await tester.enterText(find.byType(TextField).at(1), 'secret-password');
    await tester.enterText(find.byType(TextField).at(2), 'secret-password');
    await tester.tap(find.text('Aceptar invitación'));
    await tester.pumpAndSettle();

    expect(controller.isAuthenticated, isTrue);
    expect(find.text('admin@example.com'), findsOneWidget);
  }});

  testWidgets('preview re-entry uses normal login when invite is already accepted', (tester) async {{
    final controller = SessionController(api: _FakeApi(), runtimeProfile: 'preview');
    await tester.pumpWidget(MaterialApp(
      home: AuthScreen(
        controller: controller,
        projectName: 'Generated App',
        initialUri: Uri.parse('https://preview.nienfos.com/generated/?invite_state=login'),
      ),
    ));

    expect(find.text('Ingreso Preview'), findsOneWidget);
    expect(find.text('Iniciar sesión'), findsOneWidget);
    expect(find.text('Crear contraseña'), findsNothing);
    expect(find.text('Repetir contraseña'), findsNothing);
    expect(find.text('Invite token or link'), findsNothing);
    await tester.enterText(find.byType(TextField).at(0), 'admin@example.com');
    await tester.enterText(find.byType(TextField).at(1), 'secret-password');
    await tester.tap(find.text('Iniciar sesión'));
    await tester.pumpAndSettle();

    expect(controller.isAuthenticated, isTrue);
  }});

  testWidgets('APP_RUNTIME_PROFILE=preview does not show Workbench as product navigation', (tester) async {{
    final owner = _controller('preview', const AppUser(id: '1', email: 'owner@example.com', roles: ['owner']));
    await tester.pumpWidget(_app(owner, runtimeProfile: 'preview'));
    expect(find.text('Workbench'), findsNothing);

    final admin = _controller('preview', const AppUser(id: '2', email: 'admin@example.com', roles: ['admin']));
    await tester.pumpWidget(_app(admin, runtimeProfile: 'preview'));
    expect(find.text('Workbench'), findsNothing);

    final developer = _controller('preview', const AppUser(id: '4', email: 'dev@example.com', roles: ['developer']));
    await tester.pumpWidget(_app(
      developer,
      runtimeProfile: 'preview',
      developerWorkbenchEnabled: true,
    ));
    expect(find.text('Workbench'), findsNothing);
  }});

  testWidgets('real runtime hides Workbench even for owner', (tester) async {{
    final owner = _controller('real', const AppUser(id: '5', email: 'owner@example.com', roles: ['owner']));
    await tester.pumpWidget(_app(
      owner,
      runtimeProfile: 'real',
      developerWorkbenchEnabled: true,
    ));
    expect(find.text('Workbench'), findsNothing);
  }});

  testWidgets('preview dev mode shows CODEX DEV SDD entry outside product navigation', (tester) async {{
    const config = AppConfig(
      apiBaseUrl: 'https://preview.nienfos.com/generated/api',
      runtimeProfile: 'preview',
      apiRuntime: 'cloudflare_preview',
      appSlug: 'generated',
      developerWorkbenchEnabled: true,
      feedbackEnabled: false,
      appUpdaterEnabled: false,
      feedbackBridgeUrl: null,
      workbenchBridgeUrl: 'http://machine.tail000.ts.net',
      updaterBridgeUrl: null,
    );
    await tester.pumpWidget(const ProjectApp(config: config));
    expect(find.text('SDD'), findsOneWidget);
    expect(find.byTooltip('Open SDD Explorer'), findsOneWidget);
    expect(config.workbenchBridgeUrl, isNot(config.apiBaseUrl));
  }});
}}

SessionController _controller(String runtimeProfile, AppUser user) {{
  final controller = SessionController(api: _FakeApi(), runtimeProfile: runtimeProfile);
  controller.token = 'token';
  controller.user = user;
  return controller;
}}

Widget _app(
  SessionController controller, {{
  required String runtimeProfile,
  bool developerWorkbenchEnabled = false,
}}) {{
  return MaterialApp(
    home: ProjectHome(
      projectName: 'Generated App',
      runtimeProfile: runtimeProfile,
      developerWorkbenchEnabled: developerWorkbenchEnabled,
      controller: controller,
    ),
  );
}}

class _FakeApi extends ProjectApiClient {{
  _FakeApi() : super(baseUrl: 'http://fake');

  @override
  Future<AuthToken> acceptPreviewInvite({{
    required String inviteToken,
    required String email,
    required String password,
    required String passwordConfirmation,
  }}) async {{
    return const AuthToken(accessToken: 'invite-token', tokenType: 'bearer');
  }}

  @override
  Future<AuthToken> login({{
    required String email,
    required String password,
  }}) async {{
    return const AuthToken(accessToken: 'login-token', tokenType: 'bearer');
  }}

  @override
  Future<AppUser> me(String token) async {{
    return const AppUser(id: '1', email: 'admin@example.com', roles: ['owner']);
  }}
}}
"""


def _backend_pyproject(slug: str) -> str:
    return f"""[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{slug}-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115,<1.0",
    "uvicorn[standard]>=0.35,<1.0",
    "python-dotenv>=1.0,<2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3,<9.0",
    "httpx>=0.28,<1.0",
]
"""


def _backend_env_example() -> str:
    return """APP_RUNTIME_PROFILE=preview
APP_VERSION=0.1.0
APP_BUILD=1
APP_RELEASE_TAG=
APP_APK_URL=
APP_RELEASE_URL=
DATABASE_URL=sqlite:///./app.db
SECRET_KEY=
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
ADMIN_EMAIL=
ADMIN_INITIAL_PASSWORD=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
"""


def _backend_readme() -> str:
    return """# Backend

FastAPI backend generated by Project Factory.

## Setup

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Set real values in `.env`:

- `DATABASE_URL`
- `SECRET_KEY`
- `ADMIN_EMAIL`
- `ADMIN_INITIAL_PASSWORD`

If `ADMIN_EMAIL` or `ADMIN_INITIAL_PASSWORD` are missing, no admin is seeded.
Google auth is prepared but returns a clear pending-credentials error until
Google credentials are configured.

## Run

```bash
uvicorn app.main:app --reload
```

## Test

```bash
pytest
```
"""


def _backend_config_py() -> str:
    return '''from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    runtime_profile: str
    app_version: str
    app_build: int
    app_release_tag: str | None
    app_apk_url: str | None
    app_release_url: str | None
    database_url: str
    secret_key: str | None
    cors_origins: tuple[str, ...]
    admin_email: str | None
    admin_initial_password: str | None
    google_client_id: str | None
    google_client_secret: str | None


def get_settings() -> Settings:
    runtime_profile = os.getenv("APP_RUNTIME_PROFILE", "preview").strip().lower()
    if runtime_profile not in {"mock", "preview", "real", "staging"}:
        raise RuntimeError("APP_RUNTIME_PROFILE must be mock, preview, real, or staging.")
    origins = tuple(
        item.strip()
        for item in os.getenv("CORS_ORIGINS", "*").split(",")
        if item.strip()
    )
    return Settings(
        runtime_profile=runtime_profile,
        app_version=os.getenv("APP_VERSION", "0.1.0"),
        app_build=int(os.getenv("APP_BUILD", "1")),
        app_release_tag=os.getenv("APP_RELEASE_TAG") or None,
        app_apk_url=os.getenv("APP_APK_URL") or None,
        app_release_url=os.getenv("APP_RELEASE_URL") or None,
        database_url=os.getenv("DATABASE_URL", "sqlite:///./app.db"),
        secret_key=os.getenv("SECRET_KEY") or None,
        cors_origins=origins or ("*",),
        admin_email=os.getenv("ADMIN_EMAIL") or None,
        admin_initial_password=os.getenv("ADMIN_INITIAL_PASSWORD") or None,
        google_client_id=os.getenv("GOOGLE_CLIENT_ID") or None,
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET") or None,
    )
'''


def _backend_db_py() -> str:
    return '''from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import get_settings

ROLES = ("owner", "admin", "manager", "staff", "customer", "guest")


def database_path() -> Path:
    url = get_settings().database_url
    if not url.startswith("sqlite:///"):
        raise RuntimeError("Only sqlite:/// DATABASE_URL is supported by backend v1.")
    return Path(url.removeprefix("sqlite:///")).expanduser()


@contextmanager
def connect():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS roles (
                name TEXT PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id INTEGER NOT NULL,
                role_name TEXT NOT NULL,
                UNIQUE(user_id, role_name)
            );
            CREATE TABLE IF NOT EXISTS business_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                read_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        for role in ROLES:
            conn.execute("INSERT OR IGNORE INTO roles(name) VALUES (?)", (role,))
    seed_admin()


def seed_admin() -> None:
    from .security import hash_password

    settings = get_settings()
    if not settings.admin_email or not settings.admin_initial_password:
        return
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (settings.admin_email,),
        ).fetchone()
        if existing is None:
            cursor = conn.execute(
                "INSERT INTO users(email, password_hash, is_active) VALUES (?, ?, 1)",
                (settings.admin_email, hash_password(settings.admin_initial_password)),
            )
            user_id = int(cursor.lastrowid)
        else:
            user_id = int(existing["id"])
        conn.execute(
            "INSERT OR IGNORE INTO user_roles(user_id, role_name) VALUES (?, ?)",
            (user_id, "owner"),
        )
'''


def _backend_security_py() -> str:
    return '''from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, Header, HTTPException

from .config import get_settings
from .db import connect


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 210_000)
    return "pbkdf2_sha256$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        _scheme, salt_b64, digest_b64 = encoded.split("$", 2)
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 210_000)
    return hmac.compare_digest(actual, expected)


def create_token(user_id: int) -> str:
    secret = get_settings().secret_key
    if not secret:
        raise HTTPException(status_code=500, detail="SECRET_KEY is required for auth.")
    header = _b64({"alg": "HS256", "typ": "JWT"})
    payload = _b64({"sub": str(user_id), "iat": int(time.time())})
    signature = _sign(f"{header}.{payload}", secret)
    return f"{header}.{payload}.{signature}"


def decode_token(token: str) -> int:
    secret = get_settings().secret_key
    if not secret:
        raise HTTPException(status_code=500, detail="SECRET_KEY is required for auth.")
    try:
        header, payload, signature = token.split(".", 2)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token.") from None
    if not hmac.compare_digest(_sign(f"{header}.{payload}", secret), signature):
        raise HTTPException(status_code=401, detail="Invalid token.")
    data = json.loads(_unb64(payload))
    return int(data["sub"])


def current_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required.")
    user_id = decode_token(authorization.split(" ", 1)[1])
    with connect() as conn:
        user = conn.execute(
            "SELECT id, email, is_active FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if user is None or not int(user["is_active"]):
            raise HTTPException(status_code=401, detail="Inactive or missing user.")
        roles = conn.execute(
            "SELECT role_name FROM user_roles WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    return {
        "id": int(user["id"]),
        "email": str(user["email"]),
        "roles": [str(row["role_name"]) for row in roles],
    }


def require_roles(*allowed_roles: str):
    def dependency(user=Depends(current_user)):
        if "owner" in user["roles"] or any(role in user["roles"] for role in allowed_roles):
            return user
        raise HTTPException(status_code=403, detail="Insufficient role.")

    return dependency


def _b64(data: dict[str, object]) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(data: str) -> str:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode()).decode()


def _sign(data: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), data.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")
'''


def _backend_main_py() -> str:
    return '''from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db
from .routers import admin, app_updates, auth, google, notifications


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        yield

    settings = get_settings()
    app = FastAPI(title="Generated Project Backend", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "runtime_profile": settings.runtime_profile}

    app.include_router(auth.router)
    app.include_router(google.router)
    app.include_router(admin.router)
    app.include_router(notifications.router)
    app.include_router(app_updates.router)
    return app


app = create_app()
'''


def _backend_auth_router_py() -> str:
    return '''from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import connect
from ..security import create_token, current_user, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: str
    password: str


@router.post("/register")
def register(credentials: Credentials):
    with connect() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO users(email, password_hash, is_active) VALUES (?, ?, 1)",
                (credentials.email, hash_password(credentials.password)),
            )
        except Exception as exc:
            raise HTTPException(status_code=409, detail="User already exists.") from exc
        user_id = int(cursor.lastrowid)
        conn.execute(
            "INSERT OR IGNORE INTO user_roles(user_id, role_name) VALUES (?, ?)",
            (user_id, "customer"),
        )
    return {"id": user_id, "email": credentials.email}


@router.post("/login")
def login(credentials: Credentials):
    with connect() as conn:
        user = conn.execute(
            "SELECT id, email, password_hash, is_active FROM users WHERE email = ?",
            (credentials.email,),
        ).fetchone()
    if user is None or not int(user["is_active"]):
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    if not verify_password(credentials.password, str(user["password_hash"])):
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    return {"access_token": create_token(int(user["id"])), "token_type": "bearer"}


@router.get("/me")
def me(user=Depends(current_user)):
    return user


@router.post("/logout")
def logout():
    return {"status": "ok"}
'''


def _backend_admin_router_py() -> str:
    return '''from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..db import connect
from ..security import require_roles

router = APIRouter(prefix="/admin", tags=["admin"])


class BusinessRecordCreate(BaseModel):
    name: str


@router.get("/users")
def list_users(_user=Depends(require_roles("admin"))):
    with connect() as conn:
        rows = conn.execute("SELECT id, email, is_active FROM users ORDER BY id").fetchall()
    return [{"id": int(row["id"]), "email": row["email"], "is_active": bool(row["is_active"])} for row in rows]


@router.get("/roles")
def list_roles(_user=Depends(require_roles("admin"))):
    with connect() as conn:
        rows = conn.execute("SELECT name FROM roles ORDER BY name").fetchall()
    return [row["name"] for row in rows]


@router.get("/business-records")
def list_business_records(_user=Depends(require_roles("admin", "manager"))):
    with connect() as conn:
        rows = conn.execute("SELECT id, name, is_active FROM business_records ORDER BY id").fetchall()
    return [{"id": int(row["id"]), "name": row["name"], "is_active": bool(row["is_active"])} for row in rows]


@router.post("/business-records")
def create_business_record(payload: BusinessRecordCreate, _user=Depends(require_roles("admin"))):
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO business_records(name, is_active) VALUES (?, 1)",
            (payload.name,),
        )
    return {"id": int(cursor.lastrowid), "name": payload.name, "is_active": True}
'''


def _backend_notifications_router_py() -> str:
    return '''from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..db import connect
from ..security import current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(user=Depends(current_user)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title, body, read_at, created_at FROM notifications WHERE user_id = ? ORDER BY id DESC",
            (user["id"],),
        ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "title": row["title"],
            "body": row["body"],
            "read_at": row["read_at"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


@router.post("/{notification_id}/read")
def mark_read(notification_id: int, user=Depends(current_user)):
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM notifications WHERE id = ? AND user_id = ?",
            (notification_id, user["id"]),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Notification not found.")
        conn.execute(
            "UPDATE notifications SET read_at = CURRENT_TIMESTAMP WHERE id = ?",
            (notification_id,),
        )
    return {"status": "read", "id": notification_id}
'''


def _backend_google_router_py() -> str:
    return '''from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..config import get_settings

router = APIRouter(prefix="/auth/google", tags=["google-auth"])


@router.post("/login")
def google_login():
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=501,
            detail="Google auth credentials are pending. Configure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )
    raise HTTPException(status_code=501, detail="Google auth exchange is not implemented in backend v1.")
'''


def _backend_app_updates_router_py() -> str:
    return '''from __future__ import annotations

from fastapi import APIRouter

from ..config import get_settings

router = APIRouter(prefix="/app-updates", tags=["app-updates"])


@router.get("/current")
def current_update():
    settings = get_settings()
    mock_or_demo = settings.runtime_profile == "mock"
    return {
        "version": settings.app_version,
        "build": settings.app_build,
        "release_tag": settings.app_release_tag,
        "apk_url": settings.app_apk_url,
        "release_url": settings.app_release_url,
        "runtime_profile": settings.runtime_profile,
        "mock_or_demo": mock_or_demo,
        "backend_required": not mock_or_demo,
    }
'''


def _backend_tests_py() -> str:
    return '''from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import connect
from app.main import create_app


def test_health_auth_rbac_and_notifications(monkeypatch, tmp_path):
    db_path = tmp_path / "app.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("APP_RUNTIME_PROFILE", "real")
    monkeypatch.setenv("APP_VERSION", "1.2.3")
    monkeypatch.setenv("APP_BUILD", "42")
    monkeypatch.setenv("APP_RELEASE_TAG", "android-v1.2.3-build.42")
    monkeypatch.setenv("APP_APK_URL", "https://releases.example/app.apk")
    monkeypatch.setenv("APP_RELEASE_URL", "https://github.com/example/app/releases/tag/android-v1.2.3-build.42")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "admin-password")

    with TestClient(create_app()) as client:
        assert client.get("/health").json() == {"status": "ok", "runtime_profile": "real"}
        update = client.get("/app-updates/current").json()
        assert update["runtime_profile"] == "real"
        assert update["mock_or_demo"] is False
        assert update["backend_required"] is True
        assert update["release_tag"] == "android-v1.2.3-build.42"
        login = client.post(
            "/auth/login",
            json={"email": "admin@example.com", "password": "admin-password"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/auth/me", headers=headers).json()["roles"] == ["owner"]
        assert client.get("/admin/users", headers=headers).status_code == 200
        assert client.post(
            "/admin/business-records",
            json={"name": "primary"},
            headers=headers,
        ).status_code == 200

        registered = client.post(
            "/auth/register",
            json={"email": "user@example.com", "password": "user-password"},
        )
        assert registered.status_code == 200
        user_login = client.post(
            "/auth/login",
            json={"email": "user@example.com", "password": "user-password"},
        )
        user_headers = {"Authorization": f"Bearer {user_login.json()['access_token']}"}
        assert client.get("/admin/users", headers=user_headers).status_code == 403

        with connect() as conn:
            conn.execute(
                "INSERT INTO notifications(user_id, title, body) VALUES (?, ?, ?)",
                (registered.json()["id"], "Welcome", "Hello"),
            )
        notifications = client.get("/notifications", headers=user_headers)
        assert notifications.status_code == 200
        notification_id = notifications.json()[0]["id"]
        assert client.post(
            f"/notifications/{notification_id}/read",
            headers=user_headers,
        ).status_code == 200


def test_google_auth_reports_pending_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    with TestClient(create_app()) as client:
        response = client.post("/auth/google/login")
    assert response.status_code == 501
    assert "pending" in response.json()["detail"].lower()


def test_mock_runtime_update_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("APP_RUNTIME_PROFILE", "mock")
    monkeypatch.setenv("APP_RELEASE_TAG", "android-mock-v0.1.0-build.1")
    with TestClient(create_app()) as client:
        update = client.get("/app-updates/current").json()
    assert update["runtime_profile"] == "mock"
    assert update["mock_or_demo"] is True
    assert update["backend_required"] is False
'''


def _agents(name: str) -> str:
    return f"""# Agent Notes For {name}

## Product Factory Defaults

This project was created by Codex Mobile Bridge Project Factory.

- Keep release builds on real data paths unless a demo/mock release is explicitly requested.
- Use Workbench specs, plans, and tasks as the primary feature planning surface.
- Keep secrets in environment variables or secret managers; do not commit them.
- The seed admin password must come from `SEED_ADMIN_PASSWORD`.
- Google login is required but may remain `pending_credentials` until real OAuth credentials are provided.
"""


def _baseline_diagram_files(
    name: str,
    business_type: str,
    primary_goal: str,
    frontend_strategy: str = "flutter",
) -> dict[str, str]:
    is_svelte = frontend_strategy == "svelte"
    frontend_summary = (
        "Svelte/Vite web app, Cloudflare Preview Worker/API, D1 persistence"
        if is_svelte
        else "Flutter clients, a FastAPI backend, RBAC"
    )
    return {
        "architecture/components.mmd": _components_diagram(frontend_strategy),
        "architecture/components.yaml": _diagram_metadata(
            "components",
            "component",
            "architecture/components.mmd",
            f"Baseline component diagram for {name}.",
        ),
        "architecture/classes.mmd": _classes_diagram(name),
        "architecture/classes.yaml": _diagram_metadata(
            "classes",
            "class",
            "architecture/classes.mmd",
            f"Baseline class model for {name}.",
        ),
        "architecture/entity-relationship.mmd": _erd_diagram(),
        "architecture/entity-relationship.yaml": _diagram_metadata(
            "entity-relationship",
            "entity-relationship",
            "architecture/entity-relationship.mmd",
            f"Baseline data model for {name}.",
        ),
        "architecture/deployment.mmd": _deployment_diagram(name, frontend_strategy),
        "architecture/deployment.yaml": _diagram_metadata(
            "deployment",
            "deployment",
            "architecture/deployment.mmd",
            f"Baseline deployment shape for {name}.",
        ),
        "architecture/overview.md": (
            "# Architecture Overview\n\n"
            f"`{name}` starts with {frontend_summary}, business records management, "
            "notifications, and Workbench SDD artifacts.\n\n"
            f"- Business type: `{business_type}`\n"
            f"- Primary goal: {primary_goal}\n\n"
            "Keep these baseline diagrams updated as specs, plans, and tasks evolve.\n"
        ),
    }


def _components_diagram(frontend_strategy: str = "flutter") -> str:
    if frontend_strategy == "svelte":
        return """flowchart LR
    user[User Browser]
    admin[Admin Browser]
    web[Svelte Web App]
    worker[Cloudflare Preview Worker]
    api[Preview API]
    d1[(Cloudflare D1)]
    assets[Cloudflare Preview Assets]
    workbench[Codex Dev Workbench]
    specs[Specs / Plan / Tasks]

    user --> web
    admin --> web
    web --> assets
    web --> worker
    worker --> api
    api --> d1
    worker --> assets
    workbench --> specs
    specs --> web
    specs --> worker
"""
    return """flowchart LR
    user[User]
    admin[Admin]
    mobile[Flutter Mobile App]
    web[Flutter Web App]
    api[FastAPI Backend]
    auth[Auth and RBAC]
    businessRecords[Business Records]
    notifications[Notification Outbox]
    db[(Application Database)]
    workbench[Codex Dev Workbench]
    specs[Specs / Plan / Tasks]

    user --> mobile
    user --> web
    admin --> mobile
    admin --> web
    mobile --> api
    web --> api
    api --> auth
    api --> businessRecords
    api --> notifications
    auth --> db
    businessRecords --> db
    notifications --> db
    workbench --> specs
    specs --> api
    specs --> mobile
"""


def _classes_diagram(name: str) -> str:
    app_class = _diagram_class_name(name)
    return f"""classDiagram
    class AppUser {{
      +string id
      +string email
      +string displayName
      +bool isActive
    }}
    class Role {{
      +string name
      +string[] permissions
    }}
    class BusinessRecord {{
      +string id
      +string name
      +string status
      +map attributes
    }}
    class Notification {{
      +string id
      +string userId
      +string title
      +string body
      +bool read
    }}
    class {app_class}App {{
      +login()
      +manageDomain()
      +listNotifications()
    }}

    AppUser "*" --> "*" Role
    AppUser "1" --> "*" Notification
    AppUser "1" --> "*" BusinessRecord
    {app_class}App --> AppUser
    {app_class}App --> BusinessRecord
"""


def _erd_diagram() -> str:
    return """erDiagram
    USERS ||--o{ USER_ROLES : has
    ROLES ||--o{ USER_ROLES : grants
    USERS ||--o{ DOMAINS : manages
    USERS ||--o{ NOTIFICATIONS : receives

    USERS {
      string id PK
      string email
      string password_hash
      string display_name
      boolean is_active
    }
    ROLES {
      string name PK
      string permissions_json
    }
    USER_ROLES {
      string user_id FK
      string role_name FK
    }
    DOMAINS {
      string id PK
      string name
      string status
      string attributes_json
    }
    NOTIFICATIONS {
      string id PK
      string user_id FK
      string title
      string body
      boolean read
    }
"""


def _deployment_diagram(name: str, frontend_strategy: str = "flutter") -> str:
    if frontend_strategy == "svelte":
        preview_slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "app"
        return f"""flowchart TB
    browser[Browser]
    preview[preview.nienfos.com/{preview_slug}]
    worker[Cloudflare Worker]
    assets[Svelte/Vite Static Assets]
    api[Cloudflare Preview API]
    d1[(Cloudflare D1)]
    secrets[Cloudflare Secrets]
    workbench[Codex Dev Workbench]
    repo[{name} Repo]

    browser --> preview
    preview --> worker
    worker --> assets
    worker --> api
    api --> d1
    secrets --> worker
    workbench --> repo
    repo --> assets
    repo --> worker
"""
    return f"""flowchart TB
    phone[Installed Mobile App]
    browser[Web App]
    store[App Store / Play Store]
    cdn[Static Web Hosting]
    api[FastAPI Service]
    database[(DATABASE_URL)]
    secrets[Environment Secrets]
    bridge[Codex Mobile Bridge]
    workbench[Codex Dev Workbench]
    repo[{name} Repo]

    store --> phone
    cdn --> browser
    phone --> api
    browser --> api
    api --> database
    secrets --> api
    bridge --> workbench
    workbench --> repo
    repo --> api
    repo --> cdn
"""


def _diagram_metadata(
    diagram_id: str,
    diagram_type: str,
    source: str,
    title: str,
) -> str:
    return _to_yaml(
        {
            "id": diagram_id,
            "title": title,
            "diagram_type": diagram_type,
            "scope": "baseline",
            "owner": "project",
            "source": source,
            "status": "draft",
        }
    )


def _spec_index(slug: str, name: str) -> str:
    return _to_yaml(
        {
            "schema_version": 1,
            "index_type": "spec",
            "project_slug": slug,
            "specs": {
                "001-product-foundation": {
                    "title": "Product Foundation",
                    "path": "specs/001-product-foundation/spec.md",
                    "plan_path": "specs/001-product-foundation/plan.md",
                    "tasks_path": "specs/001-product-foundation/tasks.md",
                    "metadata_path": "specs/001-product-foundation/metadata.yaml",
                    "description": f"Initial product foundation for {name}.",
                }
            },
        }
    )


def _diagram_index() -> str:
    return _to_yaml(
        {
            "schema_version": 1,
            "index_type": "diagram",
            "diagrams": {
                "components": {
                    "path": "architecture/components.mmd",
                    "diagram_type": "component",
                    "scope": "baseline",
                    "metadata_path": "architecture/components.yaml",
                },
                "classes": {
                    "path": "architecture/classes.mmd",
                    "diagram_type": "class",
                    "scope": "baseline",
                    "metadata_path": "architecture/classes.yaml",
                },
                "entity-relationship": {
                    "path": "architecture/entity-relationship.mmd",
                    "diagram_type": "entity-relationship",
                    "scope": "baseline",
                    "metadata_path": "architecture/entity-relationship.yaml",
                },
                "deployment": {
                    "path": "architecture/deployment.mmd",
                    "diagram_type": "deployment",
                    "scope": "baseline",
                    "metadata_path": "architecture/deployment.yaml",
                },
            },
        }
    )


def _diagram_class_name(name: str) -> str:
    candidate = "".join(part.capitalize() for part in re.split(r"[^A-Za-z0-9]+", name))
    return candidate or "Generated"


def _copy_project_assets_to_project(
    *,
    asset_depot_service: AssetDepotService,
    project_assets: tuple[object, ...],
    target_project: Path,
) -> tuple[str, ...]:
    metadata: list[dict[str, object]] = []
    written: list[str] = []
    reference_lines: list[str] = []
    document_lines: list[str] = []
    for linked in project_assets:
        asset_id = str(getattr(linked, "asset_id", ""))
        role = str(getattr(linked, "role", ""))
        asset = asset_depot_service.get_asset(asset_id)
        if asset is None:
            raise ProjectFactoryGeneratorError(f"Promoted asset not found: {asset_id}")
        destinations = _asset_destinations_for_role(role, asset.id, asset.original_filename)
        copied_paths: list[str] = []
        for destination in destinations:
            copied = asset_depot_service.copy_asset_to(
                asset=asset,
                target_project=target_project,
                relative_destination=destination,
            )
            copied_paths.append(copied)
            written.append(copied)
        item = {
            "asset_id": asset.id,
            "role": role,
            "original_filename": asset.original_filename,
            "content_type": asset.content_type,
            "size_bytes": asset.size_bytes,
            "sha256": asset.sha256,
            "source": asset.source,
            "bridge_storage_path": asset.storage_path,
            "destinations": copied_paths,
            "notes": str(getattr(linked, "notes", "")),
        }
        metadata.append(item)
        if role == "visual_reference":
            reference_lines.append(_asset_markdown_item(item))
        if role == "document_context":
            document_lines.append(_asset_markdown_item(item))
    metadata_path = target_project / "assets" / "asset-depot-assets.yaml"
    metadata_path.write_text(_to_yaml({"assets": metadata}), encoding="utf-8")
    written.append(str(metadata_path.relative_to(target_project)))
    if reference_lines:
        reference_path = target_project / "references" / "reference-assets.md"
        existing = reference_path.read_text(encoding="utf-8") if reference_path.exists() else "# Reference Assets\n"
        reference_path.write_text(
            existing.rstrip()
            + "\n\n## Asset Depot Visual References\n\n"
            + "\n".join(reference_lines)
            + "\n",
            encoding="utf-8",
        )
        written.append(str(reference_path.relative_to(target_project)))
    if document_lines:
        document_path = target_project / "references" / "documents" / "document-assets.md"
        document_path.write_text(
            "# Document Context Assets\n\n" + "\n".join(document_lines) + "\n",
            encoding="utf-8",
        )
        written.append(str(document_path.relative_to(target_project)))
    return tuple(dict.fromkeys(written))


def _asset_destinations_for_role(
    role: str,
    asset_id: str,
    original_filename: str,
) -> tuple[str, ...]:
    suffix = Path(original_filename).suffix.lower() or ".bin"
    slug = _slug_filename(original_filename)
    if role == "visual_reference":
        return (f"references/images/{asset_id}-{slug}",)
    if role == "exact_asset":
        return (f"assets/source/{asset_id}-{slug}",)
    if role == "logo":
        return (f"assets/brand/logo{suffix}",)
    if role == "app_icon":
        return (
            f"assets/brand/app_icon_source{suffix}",
            f"apps/mobile/assets/brand/app_icon_source{suffix}",
        )
    if role == "document_context":
        return (f"references/documents/{asset_id}-{slug}",)
    return (f"assets/source/{asset_id}-{slug}",)


def _asset_markdown_item(item: dict[str, object]) -> str:
    destinations = ", ".join(f"`{path}`" for path in item["destinations"])
    return (
        f"- `{item['original_filename']}` role `{item['role']}` "
        f"sha256 `{item['sha256']}` -> {destinations}"
    )


def _promoted_assets_spec_section(project_assets: object) -> str:
    if not isinstance(project_assets, list) or not project_assets:
        return "- No promoted exact assets yet."
    lines = []
    for item in project_assets:
        if not isinstance(item, dict):
            continue
        lines.append(
            "- "
            f"{item.get('original_filename')} "
            f"role `{item.get('role')}` "
            f"sha256 `{item.get('sha256')}`"
        )
    return "\n".join(lines) if lines else "- No promoted exact assets yet."


def _slug_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    stem = Path(filename).stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", stem).strip("-") or "asset"
    return f"{slug}{suffix}"


def _initial_spec(
    name: str,
    business_type: str,
    primary_goal: str,
    workflow: dict[str, Any],
    project_assets: object,
    frontend_strategy: str = "flutter",
) -> str:
    if frontend_strategy == "svelte":
        return f"""# Product Foundation

## Intent

Build `{name}` as a Svelte/Vite web app under `apps/web` with a Cloudflare
Preview Worker/API, D1 persistence, auth, admin, roles, permissions, domain
management, notifications, Codex Feedback Bridge workspace metadata, and
Workbench-driven feature growth.

This strategy is web-only. It does not generate a mobile package, native store
release path, or Codex Mobile catalog registration unless a future wrapper
strategy is explicitly implemented.

## Business Context

- Business type: `{business_type}`
- Primary goal: {primary_goal}

## Promoted Assets

{_promoted_assets_spec_section(project_assets)}

## Creation Workflow

New-project creation uses Codex CLI by default with:

- mode: `{workflow["mode"]}`
- generator/reviewer pairs: {workflow["generator_runs"]}
- order: generator-01 -> reviewer-01 before generator-02 starts

## Required Foundation

- Login and registration.
- Google login placeholders.
- RBAC with owner/admin/manager/staff/customer/guest.
- Admin business-records shell.
- Notification foundations.
- FastAPI backend v1 with SQLite DATABASE_URL, PBKDF2 password hashing,
  JWT-compatible HS256 tokens, admin seed by env, RBAC guards, business records CRUD,
  notification outbox, healthcheck, CORS, and generated tests.
- Svelte web v1 with VITE_APP_RUNTIME_PROFILE, VITE_API_RUNTIME,
  VITE_API_BASE_URL configuration, Cloudflare preview API contract validation,
  web preview build output, and generated tests.
- Cloudflare Preview Worker/API/D1 contract for the initial preview release.
- SDD artifacts for future Workbench features.
- Baseline Workbench diagrams for components, classes, entity relationships, and
  deployment.
"""
    return f"""# Product Foundation

## Intent

Build `{name}` as a Flutter iOS/Android/Web app with a FastAPI backend, auth,
admin, roles, permissions, business records management, notifications, Codex Feedback
Bridge, app updater, and Workbench-driven feature growth.

## Business Context

- Business type: `{business_type}`
- Primary goal: {primary_goal}

## Promoted Assets

{_promoted_assets_spec_section(project_assets)}

## Creation Workflow

New-project creation uses Codex CLI by default with:

- mode: `{workflow["mode"]}`
- generator/reviewer pairs: {workflow["generator_runs"]}
- order: generator-01 -> reviewer-01 before generator-02 starts

## Required Foundation

- Login and registration.
- Google login placeholders.
- RBAC with owner/admin/manager/staff/customer/guest.
- Admin business-records shell.
- Notification foundations.
- FastAPI backend v1 with SQLite DATABASE_URL, PBKDF2 password hashing,
  JWT-compatible HS256 tokens, admin seed by env, RBAC guards, business records CRUD,
  notification outbox, healthcheck, CORS, and generated tests.
- Flutter mobile v1 with API_BASE_URL configuration, real auth/session calls,
  RBAC admin gating, business records screens, notifications, and generated tests.
- SDD artifacts for future Workbench features.
- Baseline Workbench diagrams for components, classes, entity relationships, and
  deployment.
"""


def _initial_plan(name: str, frontend_strategy: str = "flutter") -> str:
    if frontend_strategy == "svelte":
        return f"""# Plan

Create the foundation for `{name}` in incremental validated slices:

1. Complete business research and visual direction.
2. Extend the generated Svelte/Vite web app with business records UX.
3. Extend FastAPI backend v1 beyond the generated auth/RBAC/admin/notification base.
4. Add business workflow resources and workflows.
5. Wire Workbench/feedback metadata for web preview.
6. Validate local run, Cloudflare Preview API/D1 readiness, and web release readiness.
"""
    return f"""# Plan

Create the foundation for `{name}` in incremental validated slices:

1. Complete business research and visual direction.
2. Extend the generated Flutter auth/admin/notification app with business records UX.
3. Extend FastAPI backend v1 beyond the generated auth/RBAC/admin/notification base.
4. Add business workflow resources and workflows.
5. Wire Feedback Bridge, updater, and Workbench.
6. Validate local run and release readiness.
"""


def _initial_task_items(frontend_strategy: str = "flutter") -> tuple[dict[str, str], ...]:
    if frontend_strategy == "svelte":
        return (
            {
                "title": "Complete business research.",
                "status": "planned",
                "description": "Research users, operational constraints, risks, and business workflow patterns.",
            },
            {
                "title": "Complete visual reference analysis.",
                "status": "planned",
                "description": "Analyze user-provided visual references and convert them into tokens, components, and screen patterns.",
            },
            {
                "title": "Generate Svelte/Vite web v1 with VITE runtime config, auth/session, RBAC admin gating, business records management, notifications, and generated tests.",
                "status": "done",
                "description": "Generated Svelte/Vite web v1 foundation is present under apps/web.",
            },
            {
                "title": "Generate backend v1 with FastAPI, auth, RBAC, admin, business records CRUD foundation, and notifications.",
                "status": "done",
                "description": "Generated FastAPI backend v1 foundation is present.",
            },
            {
                "title": "Add auth and Google login placeholders.",
                "status": "done",
                "description": "Generated auth includes real email/password flow and explicit Google credential placeholders.",
            },
            {
                "title": "Add RBAC and admin shell.",
                "status": "done",
                "description": "Generated RBAC roles and admin shell are present.",
            },
            {
                "title": "Add business records CRUD foundation.",
                "status": "done",
                "description": "Generated business records management foundation is present.",
            },
            {
                "title": "Add notification foundation.",
                "status": "done",
                "description": "Generated notification model/endpoints/client foundation is present.",
            },
            {
                "title": "Add baseline SDD diagrams for Svelte web, Preview API, D1 data, and deployment.",
                "status": "done",
                "description": "Generated baseline Mermaid diagrams and metadata are present.",
            },
            {
                "title": "Wire Workbench and feedback metadata for web preview.",
                "status": "planned",
                "description": "Verify app-specific feedback routing and Workbench visibility before web release.",
            },
            {
                "title": "Validate Cloudflare Preview API/D1 and web release readiness.",
                "status": "planned",
                "description": "Run generated validation, web preview checks, public health checks, and Workbench checks.",
            },
        )
    return (
        {
            "title": "Complete business research.",
            "status": "planned",
            "description": "Research users, operational constraints, risks, and business workflow patterns.",
        },
        {
            "title": "Complete visual reference analysis.",
            "status": "planned",
            "description": "Analyze user-provided visual references and convert them into tokens, components, and screen patterns.",
        },
        {
            "title": "Generate Flutter mobile v1 with API_BASE_URL, auth/session, RBAC admin gating, business records management, notifications, and generated tests.",
            "status": "done",
            "description": "Generated Flutter mobile v1 foundation is present.",
        },
        {
            "title": "Generate backend v1 with FastAPI, auth, RBAC, admin, business records CRUD foundation, and notifications.",
            "status": "done",
            "description": "Generated FastAPI backend v1 foundation is present.",
        },
        {
            "title": "Add auth and Google login placeholders.",
            "status": "done",
            "description": "Generated auth includes real email/password flow and explicit Google credential placeholders.",
        },
        {
            "title": "Add RBAC and admin shell.",
            "status": "done",
            "description": "Generated RBAC roles and admin shell are present.",
        },
        {
            "title": "Add business records CRUD foundation.",
            "status": "done",
            "description": "Generated business records management foundation is present.",
        },
        {
            "title": "Add notification foundation.",
            "status": "done",
            "description": "Generated notification model/endpoints/client foundation is present.",
        },
        {
            "title": "Add baseline SDD diagrams for components, classes, data, and deployment.",
            "status": "done",
            "description": "Generated baseline Mermaid diagrams and metadata are present.",
        },
        {
            "title": "Wire Feedback Bridge and updater.",
            "status": "planned",
            "description": "Verify app-specific feedback routing and updater feed before release.",
        },
        {
            "title": "Validate Workbench integration and release readiness.",
            "status": "planned",
            "description": "Run generated validation, release profile checks, and Workbench checks.",
        },
    )


def _initial_tasks(frontend_strategy: str = "flutter") -> str:
    lines = ["# Tasks", ""]
    for item in _initial_task_items(frontend_strategy):
        marker = "x" if item["status"] == "done" else " "
        lines.append(f"- [{marker}] {item['title']}")
    return "\n".join(lines) + "\n"


def _initial_tree_json(frontend_strategy: str = "flutter") -> str:
    tasks = []
    for index, item in enumerate(_initial_task_items(frontend_strategy), start=1):
        task_id = f"plan-1-task-{index}"
        tasks.append(
            {
                "id": task_id,
                "number": index,
                "title": item["title"].rstrip("."),
                "status": item["status"],
                "description": item["description"],
                "file": f"tasks/{task_id}/task.md",
            }
        )
    return (
        json.dumps(
            {
                "spec": {"file": "spec.md"},
                "plans": [
                    {
                        "id": "plan-1",
                        "number": 1,
                        "title": "Product Foundation",
                        "status": "in_progress",
                        "description": "Create, validate, and prepare the generated project foundation.",
                        "file": "plans/01-foundation/plan.md",
                        "tasks": tasks,
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )


def _initial_task_node_files(frontend_strategy: str = "flutter") -> dict[str, str]:
    files: dict[str, str] = {}
    for index, item in enumerate(_initial_task_items(frontend_strategy), start=1):
        task_id = f"plan-1-task-{index}"
        files[
            f"specs/001-product-foundation/tasks/{task_id}/task.md"
        ] = f"""# {item["title"].rstrip(".")}

Status: {item["status"]}

{item["description"]}
"""
    return files


def _initial_metadata(
    slug: str,
    name: str,
    frontend_strategy: str = "flutter",
) -> str:
    task_items = _initial_task_items(frontend_strategy)
    completed = sum(1 for item in task_items if item["status"] == "done")
    pending = len(task_items) - completed
    return _to_yaml(
        {
            "id": "001-product-foundation",
            "slug": "001-product-foundation",
            "title": "Product Foundation",
            "description": f"Initial product foundation for {name}.",
            "lifecycle_status": "draft",
            "created_at": None,
            "updated_at": None,
            "generated": {
                "title": False,
                "description": False,
                "user_pinned_title": True,
                "user_pinned_description": True,
            },
            "tasks": {
                "total": len(task_items),
                "completed": completed,
                "pending": pending,
            },
            "last_run_state": None,
            "metadata_status": "fresh",
            "metadata_warnings": [],
            "metadata_stale_paths": [],
            "available_files": ["spec.md", "plan.md", "tasks.md", "tree.json"],
            "diagrams": [
                {
                    "id": "components",
                    "path": "architecture/components.mmd",
                    "diagram_type": "component",
                    "scope": "baseline",
                },
                {
                    "id": "classes",
                    "path": "architecture/classes.mmd",
                    "diagram_type": "class",
                    "scope": "baseline",
                },
                {
                    "id": "entity-relationship",
                    "path": "architecture/entity-relationship.mmd",
                    "diagram_type": "entity-relationship",
                    "scope": "baseline",
                },
                {
                    "id": "deployment",
                    "path": "architecture/deployment.mmd",
                    "diagram_type": "deployment",
                    "scope": "baseline",
                },
            ],
            "project_slug": slug,
        }
    )


def _placeholder_doc(title: str, body: str) -> str:
    return f"# {title}\n\n{body}\n"


def _visual_reference_analysis_doc() -> str:
    return """# Visual Reference Analysis

Every attached visual reference must be analyzed before UI implementation.

For each image, extract:

- screen structure;
- navigation;
- headers;
- cards;
- buttons;
- chips/filters;
- lists;
- iconography;
- typography hierarchy;
- spacing;
- borders/radii;
- empty states;
- primary action placement;
- dashboard, inventory, catalog, menu, or settings patterns.

## Screen Mapping

Map every visual reference to concrete screens. If a reference shows inventory,
catalog, dashboard, menu, settings, login, or detail pages, create equivalent
screens in the app. A generic Scaffold/AppBar/ListView shell is a failed
generation when references exist.

## Adaptation

Preserve layout rhythm, component structure, navigation pattern, spacing, and
interaction model. Adapt colors only when the user explicitly requests a
different palette.

## Required Output

- images used;
- screen(s) influenced by each image;
- design tokens derived;
- reusable components created;
- screenshots/previews generated;
- intentional differences;
- remaining visual risks.
"""


def _visual_components_contract_doc() -> str:
    return """# Reference-Based Components

When visual references are provided, implement reusable components based on
those references:

- app shell;
- branded header;
- bottom navigation;
- metric card;
- product/catalog card;
- inventory item card;
- category chip;
- primary action button;
- secondary action button;
- empty state;
- dashboard summary card;
- settings/menu row.

Use `design/tokens.yaml` as the source for colors, spacing, radii, borders,
shadows, typography, and icon sizes.
"""


def _visual_validation_report_template(project_assets: object = None) -> str:
    assets = project_assets if isinstance(project_assets, list) else []
    if not assets:
        return """# Visual Validation Report

## References Used

- No visual reference assets were attached to this Project Factory intake.

## Derived Screens

- No reference-to-screen mapping is required because no assets were provided.

## Logo And Icon

- No logo/app icon reference asset was provided.

## Preview Screenshots

- Preview screenshots are produced by the release validation lane when a web or APK preview is built.

## What Was Preserved

- No exact visual-reference bytes were provided.

## Intentional Differences

- The generated baseline uses the default Project Factory design system until references are attached.

## Result

Generation must fail if the UI remains generic while visual references exist.
"""
    lines = [
        "# Visual Validation Report",
        "",
        "## References Used",
        "",
    ]
    for item in assets:
        if not isinstance(item, dict):
            continue
        lines.append(
            "- asset_id: {asset_id}; filename: {filename}; role: {role}; sha256: {sha256}".format(
                asset_id=item.get("asset_id") or item.get("id") or "unknown",
                filename=item.get("filename") or item.get("name") or "unknown",
                role=item.get("role") or "visual_reference",
                sha256=item.get("sha256") or "unknown",
            )
        )
    lines.extend(
        [
            "",
            "## Derived Screens",
            "",
            "- login/auth: logo/app_icon/exact_asset references when present.",
            "- home/admin: product reference imagery and visual rhythm when present.",
            "- web/APK icon surfaces: app_icon references when present.",
            "",
            "## Logo And Icon",
            "",
            "- logo/app_icon/exact_asset bytes are preserved under generated asset paths when supplied.",
            "",
            "## Preview Screenshots",
            "",
            "- Preview screenshots are produced by the release validation lane.",
            "",
            "## What Was Preserved",
            "",
            "- Exact bytes for logo, app_icon, and exact_asset roles.",
            "",
            "## Intentional Differences",
            "",
            "- Accessibility and responsive layout changes may adapt spacing without replacing exact assets.",
            "",
            "## Result",
            "",
            "Generation must fail if the UI remains generic while visual references exist.",
            "",
        ]
    )
    return "\n".join(lines)


def _gitignore() -> str:
    return """.env
.env.*
!.env.example
.dart_tool/
build/
apps/mobile/.dart_tool/
apps/mobile/.flutter-plugins-dependencies
apps/mobile/android/app/src/main/java/io/flutter/plugins/GeneratedPluginRegistrant.java
apps/mobile/android/local.properties
apps/mobile/android/.gradle/
apps/mobile/build/
apps/mobile/pubspec.lock
apps/mobile/android/upload-keystore.jks
apps/mobile/android/key.properties
__pycache__/
*.pyc
*.iml
.idea/
.codex-bridge/
.codex/factory/
.generated-validation/
backend/.venv/
backend/*.egg-info/
"""


def _init_git(target: Path) -> str:
    try:
        subprocess.run(
            ["git", "init"],
            cwd=target,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["git", "add", "-A"],
            cwd=target,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=target,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if diff.returncode == 1:
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Codex Project Factory",
                    "-c",
                    "user.email=codex-project-factory@local",
                    "commit",
                    "-m",
                    "Initial Project Factory baseline",
                ],
                cwd=target,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except (OSError, subprocess.CalledProcessError):
        return "pending_git"
    return "initialized_committed"


def _cleanup_created_target(target: Path) -> None:
    if not target.exists():
        return
    for child in sorted(target.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if child.is_file() or child.is_symlink():
            child.unlink(missing_ok=True)
        elif child.is_dir():
            child.rmdir()
    target.rmdir()


def _to_yaml(value: Any, *, indent: int = 0) -> str:
    text = _yaml_value(value, indent=indent)
    return text if text.endswith("\n") else text + "\n"


def _yaml_value(value: Any, *, indent: int) -> str:
    prefix = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.append(_yaml_value(item, indent=indent + 2).rstrip())
            else:
                lines.append(f"{prefix}{key}: {_yaml_scalar(item)}")
        return "\n".join(lines) + "\n"
    if isinstance(value, list):
        if not value:
            return f"{prefix}[]\n"
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.append(_yaml_value(item, indent=indent + 2).rstrip())
            else:
                lines.append(f"{prefix}- {_yaml_scalar(item)}")
        return "\n".join(lines) + "\n"
    return f"{prefix}{_yaml_scalar(value)}\n"


def _yaml_scalar(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, int | float):
        return str(value)
    text = str(value)
    if not text:
        return '""'
    if re_match_plain_yaml(text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def re_match_plain_yaml(text: str) -> bool:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-./")
    return all(char in allowed for char in text)
