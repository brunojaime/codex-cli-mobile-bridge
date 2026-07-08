from __future__ import annotations

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
    workflow = manifest["codex"]["creation_workflow"]
    project_assets = manifest.get("asset_depot", {}).get("project_assets", [])
    files = {
        ".codex/project.yaml": _to_yaml(manifest),
        "codex-bridge.yaml": _codex_bridge_yaml(slug, name),
        ".gitignore": _gitignore(),
        "README.md": _readme(name, business_type, primary_goal),
        "AGENTS.md": _agents(name),
        ".github/workflows/android-release.yml": _generated_android_release_workflow(),
        "scripts/finalize_local_commit.sh": _finalize_local_commit_script(),
        "scripts/publish_project.sh": _publish_script(),
        "scripts/register_installable_app.sh": _register_installable_app_script(
            slug,
            name,
        ),
        "scripts/build_web_preview.sh": _build_web_preview_script(slug),
        "scripts/deploy_web_preview.sh": _deploy_web_preview_script(slug),
        "scripts/validate_web_preview.sh": _validate_web_preview_script(slug),
        "scripts/validate_generated_project.sh": _validation_script(),
        "scripts/validate_publication_ready.sh": _publication_validation_script(),
        "scripts/validate_release_profiles.sh": _release_profile_validation_script(),
        "deploy/web-preview/README.md": _web_preview_readme(slug, name),
        "deploy/web-preview/web-preview-manifest.yaml": _to_yaml(
            _web_preview_manifest_payload(slug, name)
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
        "specs/001-product-foundation/spec.md": _initial_spec(
            name,
            business_type,
            primary_goal,
            workflow,
            project_assets,
        ),
        "specs/001-product-foundation/plan.md": _initial_plan(name),
        "specs/001-product-foundation/tasks.md": _initial_tasks(),
        "specs/001-product-foundation/metadata.yaml": _initial_metadata(slug, name),
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
            "Domain features and suggested MVP scope will be tracked here.",
        ),
        "docs/workbench.md": _workbench_doc(slug, name),
        "design/app-style-guide.md": _placeholder_doc(
            "App Style Guide",
            "Generated look and feel decisions will be documented here.",
        ),
        "design/reference-components.md": _visual_components_contract_doc(),
        "design/tokens.yaml": _to_yaml(
            {
                "schema_version": 1,
                "source": "visual-references-required-when-provided",
                "runtime_profiles": ["mock", "real", "staging"],
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
        "design/visual-validation-report.md": _visual_validation_report_template(),
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
        "release/app-store-checklist.md": _placeholder_doc(
            "App Store Checklist",
            "Apple release readiness items and pending credentials will be tracked here.",
        ),
        "release/play-store-checklist.md": _placeholder_doc(
            "Play Store Checklist",
            "Google Play release readiness items and pending credentials will be tracked here.",
        ),
        "release/runtime-profiles.md": _runtime_profiles_doc(name),
        "release/release-contracts.yaml": _release_contracts_yaml(slug),
        "release/release-output-template.md": _release_output_template(),
    }
    files.update(_baseline_diagram_files(name, business_type, primary_goal))
    files.update(_backend_files(slug))
    files.update(_mobile_files(name, slug))
    return files


def _readme(name: str, business_type: str, primary_goal: str) -> str:
    return f"""# {name}

Generated by Codex Mobile Bridge Project Factory.

## Product

- Business type: `{business_type}`
- Primary goal: {primary_goal}
- Runtime profile: `APP_RUNTIME_PROFILE=real` by default. Mock/demo is opt-in.

## Structure

- `.codex/project.yaml`: source of truth for project generation and validation.
- `specs/001-product-foundation/`: initial SDD package for Workbench-driven work.
- `architecture/`: baseline Workbench diagrams for components, classes, data, and deployment.
- `apps/mobile/`: Flutter app target.
- `backend/`: API target.
- `docs/research/`: business, UX, and visual research.
- `design/`: visual direction and design tokens.
- `infra/aws/`: AWS readiness.
- `release/`: App Store, Play Store, runtime profile, and release contract readiness.
- `deploy/web-preview/`: Cloudflare web preview manifest, Worker scaffold, and
  Wrangler example with no secrets.
- `scripts/validate_release_profiles.sh`: guardrails for mock/demo vs productive releases.
- `scripts/build_web_preview.sh`: builds the Flutter web artifact for preview.
- `scripts/validate_web_preview.sh`: validates preview manifest/runtime guardrails.
- `scripts/register_installable_app.sh`: registers this app in Codex Mobile
  Bridge so it appears in the Codex Mobile Apps catalog after an APK release.

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
                "enabledProfiles": ["mock", "staging"],
                "hiddenProfiles": ["real"],
            },
            "workbench": {
                "required": True,
                "docs": "docs/workbench.md",
                "visibleProfiles": ["mock"],
                "hiddenProfiles": ["real"],
            },
        }
    )


def _workbench_doc(slug: str, name: str) -> str:
    return f"""# Workbench

`{name}` is generated with Workbench SDD artifacts from the first commit.

## Identity

- `sourceApp`: `{slug}`
- SDD standard: `workbench-sdd/v1`
- Spec index: `.sdd/spec-index.yaml`
- Diagram index: `.sdd/diagram-index.yaml`

## Runtime Visibility

- `APP_RUNTIME_PROFILE=mock`: Workbench/developer feedback may be visible for
  internal testing.
- `APP_RUNTIME_PROFILE=staging`: Workbench/developer feedback may be available
  to internal testers only.
- `APP_RUNTIME_PROFILE=real`: Workbench/developer feedback must be hidden or
  disabled in UI/build config.

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


def _web_preview_manifest_payload(slug: str, name: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source_app": slug,
        "display_name": name,
        "stable_url": f"https://preview.nienfos.com/{slug}",
        "runtime": {
            "type": "cloudflare_worker_assets",
            "default_profile": "real",
            "allowed_profiles": ["real", "staging", "preview", "mock"],
            "api_runtime": "cloudflare_preview",
            "api_base_url": "https://preview.nienfos.com",
            "app_slug": slug,
            "health_path": "/__preview/health",
            "asset_binding": "ASSETS",
            "spa_fallback": "index.html",
            "mock_preview_requires_opt_in": True,
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
            "d1_binding": "PREVIEW_DB",
            "migrations_dir": "deploy/web-preview/d1/migrations",
            "required_worker_secrets": ["WEB_PREVIEW_INVITE_SECRET"],
            "public_paths": ["/__preview/health"],
        },
        "build": {
            "flutter_project": "apps/mobile",
            "output_dir": f"build/web-preview/{slug}",
            "entrypoint": "apps/mobile/lib/main.dart",
            "script": "scripts/build_web_preview.sh",
            "validation_script": "scripts/validate_web_preview.sh",
            "asset_entrypoint": "index.html",
            "required_files": [
                "index.html",
                "manifest.json",
                "flutter_bootstrap.js",
            ],
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
            f"/{slug}/apps/{slug}/config",
            f"/{slug}/dashboard",
        ],
        "preview_api_v1": {
            "health": "/__preview/health",
            "app_config": f"/apps/{slug}/config",
            "auth": ["/auth/login", "/auth/logout", "/auth/me"],
            "admin": ["/admin/users", "/admin/roles"],
            "notifications": ["/notifications", "/notifications/{id}"],
            "domain_crud": "/domain/{entity}",
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
API_BASE_URL=https://preview.nienfos.com \\
APP_RUNTIME_PROFILE=real \\
API_RUNTIME=cloudflare_preview \\
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
marks first use atomically when `single_use=true`, sets an HttpOnly cookie, and
redirects to the app. The Bridge stores invite metadata and token SHA256 only,
never the plaintext token. `used_at` is written by the Worker in D1; the Bridge
does not read it back yet.
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
not_found_handling = "single-page-application"

[vars]
PREVIEW_ACCESS_MODE = "invite_token"
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
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT,
  revoked_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_preview_invites_token_sha256
  ON preview_invites(token_sha256);

CREATE INDEX IF NOT EXISTS idx_preview_invites_app
  ON preview_invites(source_app, app_slug);

CREATE TABLE IF NOT EXISTS preview_access_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invite_id TEXT,
  source_app TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


def _web_preview_worker_js(slug: str, name: str) -> str:
    template = """const SOURCE_APP = '__SOURCE_APP__';
const DISPLAY_NAME = __DISPLAY_NAME__;
const DEFAULT_RUNTIME_PROFILE = 'real';
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
    'content-security-policy': "default-src 'self'; connect-src 'self' https://preview.nienfos.com; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'wasm-unsafe-eval'; font-src 'self' data:;",
  };
}

function cacheControlFor(pathname) {
  if (pathname === '/' || pathname.endsWith('/index.html')) {
    return 'no-cache, no-store, must-revalidate';
  }
  if (/[.-][a-f0-9]{8,}\\./i.test(pathname)) {
    return 'public, max-age=31536000, immutable';
  }
  return 'public, max-age=3600';
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
      `SELECT invite_id, token_sha256, source_app, app_slug, single_use, expires_at, used_at, revoked_at
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

async function fetchAsset(env, request, pathname) {
  if (!env.ASSETS || typeof env.ASSETS.fetch !== 'function') {
    return null;
  }
  const assetUrl = new URL(request.url);
  assetUrl.pathname = pathname;
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

export default {
  async fetch(request, env) {
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
        runtime: 'cloudflare_preview',
        runtime_type: 'cloudflare_worker_assets',
        access_mode: ACCESS_MODE,
        build_id: env.PREVIEW_BUILD_ID || null,
        version: env.PREVIEW_VERSION || null,
        commit: env.PREVIEW_COMMIT_SHA || null,
        deployed_at: env.PREVIEW_DEPLOYED_AT || null,
        d1_bound: Boolean(env.PREVIEW_DB),
        assets_bound: Boolean(env.ASSETS),
      });
    }

    const configMatch = assetPath.match(/^\\/apps\\/([^/]+)\\/config\\/?$/);
    if (request.method === 'GET' && configMatch) {
      return json({
        app_slug: configMatch[1],
        source_app: SOURCE_APP,
        display_name: DISPLAY_NAME,
        runtime_profile: env.APP_RUNTIME_PROFILE || DEFAULT_RUNTIME_PROFILE,
        api_runtime: 'cloudflare_preview',
        api_base_url: 'https://preview.nienfos.com',
        health_path: '/__preview/health',
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
      const active = validateInviteRow(lookup.row, { allowUsed: false });
      if (!active.ok) {
        return accessDenied(active.code, active.status);
      }
      const marked = await markInviteUsed(env, lookup.row);
      if (!marked.ok) {
        return accessDenied(marked.code, marked.status);
      }
      const sessionToken = await createAccessSession(env, verified.payload, tokenHash);
      return redirectWithCookie(url, sessionToken, verified.payload);
    }

    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return json({ error: { code: 'method_not_allowed', message: 'Method not allowed' } }, { status: 405 });
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
  inviteRow('wpi-revoked', revokedToken, { revoked_at: new Date().toISOString() }),
  inviteRow('wpi-d1-expired', d1ExpiredToken, { expires_at: new Date(Date.now() - 1000).toISOString() }),
]) {
  d1Rows.set(`${row.invite_id}:${row.token_sha256}`, row);
}

function fakeD1() {
  return {
    prepare(sql) {
      return {
        bind(...args) {
          return {
            async first() {
              const [inviteId, tokenHash, sourceApp, appSlug] = args;
              const row = d1Rows.get(`${inviteId}:${tokenHash}`);
              if (!row || row.source_app !== sourceApp || row.app_slug !== appSlug) {
                return null;
              }
              return { ...row };
            },
            async run() {
              const [_usedAt, inviteId, tokenHash] = args;
              const row = d1Rows.get(`${inviteId}:${tokenHash}`);
              if (!row || row.used_at || row.revoked_at) {
                return { meta: { changes: 0 } };
              }
              row.used_at = _usedAt;
              d1Rows.set(`${inviteId}:${tokenHash}`, row);
              return { meta: { changes: 1 } };
            },
          };
        },
      };
    },
  };
}

const assets = new Map([
  ['/index.html', response('<!doctype html><div id="flt"></div>', {{ headers: {{ 'content-type': 'text/html' }} }})],
  ['/flutter_bootstrap.js', response('console.log("bootstrap");', {{ headers: {{ 'content-type': 'application/javascript' }} }})],
  ['/assets/AssetManifest.bin', response('asset-manifest')],
]);

const env = {{
  APP_RUNTIME_PROFILE: 'real',
  PREVIEW_BUILD_ID: 'local-harness',
  PREVIEW_COMMIT_SHA: 'test-commit',
  WEB_PREVIEW_INVITE_SECRET: secret,
  PREVIEW_DB: fakeD1(),
  ASSETS: {{
    async fetch(request) {{
      const url = new URL(request.url);
      return assets.get(url.pathname) || response('missing', {{ status: 404 }});
    }},
  }},
}};

async function fetchPath(path) {{
  return worker.fetch(new Request(`https://preview.nienfos.com${{path}}`), env, {{}});
}}

const health = await fetchPath('/__SOURCE_APP__/__preview/health');
assert.equal(health.status, 200);
assert.equal((await health.json()).source_app, '__SOURCE_APP__');

const blocked = await fetchPath('/__SOURCE_APP__/dashboard/orders');
assert.equal(blocked.status, 401);
assert.equal((await blocked.json()).error.code, 'missing_invite_token');

const access = await fetchPath(`/__SOURCE_APP__/__preview/access?token=${validToken}`);
assert.equal(access.status, 302);
const cookie = access.headers.get('set-cookie') || '';
assert.match(cookie, /codex_preview_access=/);

const secondUse = await fetchPath(`/__SOURCE_APP__/__preview/access?token=${validToken}`);
assert.equal(secondUse.status, 403);
assert.equal((await secondUse.json()).error.code, 'used_invite_token');

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


def _build_web_preview_script(slug: str) -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail

fail() {{
  printf 'web preview build failed: %s\\n' "$*" >&2
  exit 1
}}

ROOT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
MOBILE_DIR="$ROOT_DIR/apps/mobile"
APP_SLUG="${{APP_SLUG:-{slug}}}"
APP_RUNTIME_PROFILE="${{APP_RUNTIME_PROFILE:-real}}"
API_RUNTIME="${{API_RUNTIME:-cloudflare_preview}}"
API_BASE_URL="${{API_BASE_URL:-https://preview.nienfos.com}}"
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
  --dart-define=APP_RUNTIME_PROFILE="$APP_RUNTIME_PROFILE" \\
  --dart-define=API_RUNTIME="$API_RUNTIME" \\
  --dart-define=API_BASE_URL="$API_BASE_URL" \\
  --dart-define=APP_SLUG="$APP_SLUG" \\
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
BRIDGE_URL="${{BRIDGE_URL:-http://127.0.0.1:8000}}"
BRIDGE_URL="${{BRIDGE_URL%/}}"
MODE="${{1:---plan}}"
PROJECT_PATH="${{PROJECT_PATH:-$ROOT_DIR}}"
SOURCE_APP="${{SOURCE_APP:-{slug}}}"

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

python3 - "$endpoint" "$payload" <<'PY'
import json
import sys
import urllib.error
import urllib.request

url = sys.argv[1]
payload = sys.argv[2].encode()
request = urllib.request.Request(
    url,
    data=payload,
    headers={{"content-type": "application/json"}},
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


def _validate_web_preview_script(slug: str) -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail

fail() {{
  printf 'web preview validation failed: %s\\n' "$*" >&2
  exit 1
}}

ROOT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
MANIFEST="$ROOT_DIR/deploy/web-preview/web-preview-manifest.yaml"
WORKER="$ROOT_DIR/deploy/web-preview/worker/src/index.js"
WORKER_HARNESS="$ROOT_DIR/deploy/web-preview/worker/local_preview_test.mjs"
WRANGLER_EXAMPLE="$ROOT_DIR/deploy/web-preview/wrangler.toml.example"
D1_MIGRATION="$ROOT_DIR/deploy/web-preview/d1/migrations/0001_preview_invites.sql"
APP_SLUG="${{APP_SLUG:-{slug}}}"
APP_RUNTIME_PROFILE="${{APP_RUNTIME_PROFILE:-real}}"
API_RUNTIME="${{API_RUNTIME:-cloudflare_preview}}"
API_BASE_URL="${{API_BASE_URL:-https://preview.nienfos.com}}"
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
[[ -f "$D1_MIGRATION" ]] || fail "missing deploy/web-preview/d1/migrations/0001_preview_invites.sql"
[[ -f "$ROOT_DIR/apps/mobile/pubspec.yaml" ]] || fail "missing apps/mobile/pubspec.yaml"
[[ -f "$ROOT_DIR/apps/mobile/lib/main.dart" ]] || fail "missing apps/mobile/lib/main.dart"

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
    ("stable_url", payload.get("stable_url"), "https://preview.nienfos.com/" + expected_slug),
    ("runtime.type", runtime.get("type") if isinstance(runtime, dict) else None, "cloudflare_worker_assets"),
    ("runtime.api_runtime", runtime.get("api_runtime") if isinstance(runtime, dict) else None, "cloudflare_preview"),
    ("runtime.default_profile", runtime.get("default_profile") if isinstance(runtime, dict) else None, "real"),
    ("runtime.health_path", runtime.get("health_path") if isinstance(runtime, dict) else None, "/__preview/health"),
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
if not isinstance(access, dict) or "WEB_PREVIEW_INVITE_SECRET" not in access.get("required_worker_secrets", []):
    raise SystemExit("access.required_worker_secrets must include WEB_PREVIEW_INVITE_SECRET")
PY

grep -q 'export default' "$WORKER" || fail "worker module export missing"
grep -q '/__preview/health' "$WORKER" || fail "worker health route missing"
grep -q 'ASSETS' "$WORKER" || fail "worker asset binding missing"
grep -q 'asset_not_found' "$WORKER" || fail "worker asset 404 missing"
grep -q 'content-security-policy' "$WORKER" || fail "worker security headers missing"
grep -q 'WEB_PREVIEW_INVITE_SECRET' "$WORKER" || fail "worker invite secret binding missing"
grep -q 'PREVIEW_DB' "$WORKER" || fail "worker D1 binding missing"
grep -q '/__preview/access' "$WORKER" || fail "worker access route missing"
grep -q 'missing_invite_token' "$WORKER" || fail "worker missing-token response missing"
grep -q 'expired_invite_token' "$WORKER" || fail "worker expired-token response missing"
grep -q 'PREVIEW_DB' "$WRANGLER_EXAMPLE" || fail "wrangler D1 binding missing"
grep -q 'binding = "ASSETS"' "$WRANGLER_EXAMPLE" || fail "wrangler assets binding missing"
grep -q 'WEB_PREVIEW_INVITE_SECRET' "$WRANGLER_EXAMPLE" || fail "wrangler invite secret documentation missing"
grep -q 'CREATE TABLE IF NOT EXISTS preview_invites' "$D1_MIGRATION" || fail "D1 preview_invites migration missing"
grep -q 'token_sha256' "$D1_MIGRATION" || fail "D1 token hash column missing"
grep -q 'used_at' "$D1_MIGRATION" || fail "D1 used_at column missing"
grep -q 'revoked_at' "$D1_MIGRATION" || fail "D1 revoked_at column missing"
grep -q 'APP_RUNTIME_PROFILE' "$ROOT_DIR/apps/mobile/lib/main.dart" || fail "Flutter runtime profile define missing"
grep -q 'API_RUNTIME' "$ROOT_DIR/apps/mobile/lib/main.dart" || fail "Flutter API runtime define missing"
grep -q 'APP_SLUG' "$ROOT_DIR/apps/mobile/lib/main.dart" || fail "Flutter app slug define missing"

if command -v node >/dev/null 2>&1; then
  node --check --input-type=module < "$WORKER" >/dev/null
  node "$WORKER_HARNESS" >/dev/null
else
  printf 'node not found; skipping Worker syntax and local harness validation\\n'
fi

if [[ "$REQUIRE_WEB_BUILD_OUTPUT" == "true" ]]; then
  [[ -f "$WEB_PREVIEW_BUILD_DIR/index.html" ]] || fail "missing web build output index.html at $WEB_PREVIEW_BUILD_DIR"
  [[ -f "$WEB_PREVIEW_BUILD_DIR/manifest.json" ]] || fail "missing web build output manifest.json at $WEB_PREVIEW_BUILD_DIR"
  [[ -f "$WEB_PREVIEW_BUILD_DIR/flutter_bootstrap.js" ]] || fail "missing web build output flutter_bootstrap.js at $WEB_PREVIEW_BUILD_DIR"
  [[ -d "$WEB_PREVIEW_BUILD_DIR/assets" ]] || fail "missing web build output assets directory at $WEB_PREVIEW_BUILD_DIR/assets"
else
  printf 'web build output check skipped; set REQUIRE_WEB_BUILD_OUTPUT=true after scripts/build_web_preview.sh\\n'
fi

printf 'web preview validation completed: profile=%s api_runtime=%s url=%s\\n' "$APP_RUNTIME_PROFILE" "$API_RUNTIME" "$API_BASE_URL"
'''


def _validation_script() -> str:
    return r'''#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
MOBILE_DIR="$ROOT_DIR/apps/mobile"
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
domains = request("GET", "/admin/domains", token=token)
assert isinstance(domains, list), domains
domain_name = "validation-domain-" + token[:8].lower().replace("_", "x").replace("-", "x")
created = request("POST", "/admin/domains", {"name": domain_name}, token=token)
assert created["name"] == domain_name, created
notifications = request("GET", "/notifications", token=token)
assert isinstance(notifications, list), notifications
print("contract ok: auth/me/admin/domains/notifications")
PY

cd "$ROOT_DIR"
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

cd "$ROOT_DIR"
APP_RUNTIME_PROFILE=real \
API_RUNTIME=cloudflare_preview \
API_BASE_URL=https://preview.nienfos.com \
scripts/validate_web_preview.sh

echo "generated project validation completed"
'''


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
if ! gh repo view "$REPO" >/dev/null 2>&1; then
  gh repo create "$REPO" "--$VISIBILITY" --source . --remote origin --push
else
  if ! git remote get-url origin >/dev/null 2>&1; then
    git remote add origin "https://github.com/$REPO.git"
  fi
  git push -u origin "$BRANCH"
fi

echo "published: https://github.com/$REPO"
'''


def _register_installable_app_script(slug: str, name: str) -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
DRY_RUN=false
BRIDGE_URL="${{BRIDGE_URL:-}}"
SOURCE_APP="${{SOURCE_APP:-{slug}}}"
DISPLAY_NAME="${{DISPLAY_NAME:-{name}}}"
RELEASE_TAG_PATTERN="${{RELEASE_TAG_PATTERN:-android-v*}}"
APK_ASSET_PATTERN="${{APK_ASSET_PATTERN:-${{SOURCE_APP}}*.apk}}"
LATEST_ASSET_NAME="${{LATEST_ASSET_NAME:-${{SOURCE_APP}}.apk}}"
RELEASE_CHANNEL="${{RELEASE_CHANNEL:-stable}}"
ENABLED="${{ENABLED:-true}}"
REQUIRE_INSTALLABLE_APK="${{REQUIRE_INSTALLABLE_APK:-true}}"
EXPECTED_PACKAGE_ID="${{EXPECTED_PACKAGE_ID:-}}"
EXPECTED_SHA256="${{EXPECTED_SHA256:-}}"
APP_RELEASE_TAG="${{APP_RELEASE_TAG:-}}"
BRIDGE_REGISTRATION_TOKEN="${{BRIDGE_REGISTRATION_TOKEN:-${{INSTALLABLE_APPS_REGISTRATION_TOKEN:-}}}}"

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

cd "$ROOT_DIR"

if [[ -z "$BRIDGE_URL" ]]; then
  echo "BRIDGE_URL is required. Example: BRIDGE_URL=http://127.0.0.1:8000 $0" >&2
  exit 2
fi
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
export SOURCE_APP DISPLAY_NAME GITHUB_REPO RELEASE_TAG_PATTERN APK_ASSET_PATTERN
export LATEST_ASSET_NAME RELEASE_CHANNEL ENABLED EXPECTED_PACKAGE_ID EXPECTED_SHA256

if [[ -z "$APP_RELEASE_TAG" && -f apps/mobile/pubspec.yaml ]]; then
  version="$(awk '/^version:/ {{ print $2; exit }}' apps/mobile/pubspec.yaml)"
  if [[ -n "$version" ]]; then
    APP_RELEASE_TAG="android-v${{version//+/-build.}}"
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

curl -fsS "$BRIDGE_URL/installable-apps/$SOURCE_APP" \\
  >/tmp/project-factory-installable-app-detail.json

python3 - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

registered = json.loads(Path("/tmp/project-factory-register-installable-app.json").read_text())
detail = json.loads(Path("/tmp/project-factory-installable-app-detail.json").read_text())
print(f"registered installable app: {{registered['sourceApp']}} -> {{registered['displayName']}}")
print(f"install status: {{detail.get('installStatusHint')}}")
print(f"apk url: {{detail.get('apkUrl')}}")
expected_sha = os.environ.get("EXPECTED_SHA256", "").strip().lower()
actual_sha = str(detail.get("sha256") or "").lower()
if expected_sha and actual_sha and expected_sha != actual_sha:
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
  curl -fsSI "$apk_url" >/dev/null || {{
    echo "Bridge APK proxy did not respond for $apk_url" >&2
    exit 2
  }}
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


def _publication_validation_script() -> str:
    return r'''#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'publication validation failed: %s\n' "$*" >&2
  exit 1
}

mode="${PUBLICATION_VALIDATION_MODE:-remote}"

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

branch="$(git symbolic-ref --short HEAD 2>/dev/null || true)"
[[ -n "$branch" ]] || fail "HEAD is detached; publish from a named branch"

upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
[[ -n "$upstream" ]] || fail "current branch has no upstream"

git fetch --quiet origin "$branch" || fail "could not fetch origin/$branch"
local_head="$(git rev-parse HEAD)"
remote_head="$(git rev-parse "$upstream" 2>/dev/null || true)"
[[ "$local_head" == "$remote_head" ]] || fail "local HEAD is not pushed to $upstream"

if [[ -f apps/mobile/pubspec.yaml ]]; then
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
  mock|real|staging) ;;
  *) fail "APP_RUNTIME_PROFILE must be mock, real, or staging" ;;
esac

if [[ "$TAG" == android-v* ]]; then
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

if [[ "$TAG" == android-v* ]]; then
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


def _generated_android_release_workflow() -> str:
    return """name: Android Release

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
      APP_RUNTIME_PROFILE: ${{ github.event.inputs.runtime_profile || (startsWith(github.ref_name, 'android-mock-') && 'mock') || (startsWith(github.ref_name, 'android-local-') && 'mock') || 'real' }}
      API_BASE_URL: ${{ vars.API_BASE_URL }}
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
          args+=(--dart-define=CODEX_FEEDBACK_BRIDGE_URL="${{ vars.CODEX_FEEDBACK_BRIDGE_URL }}")
          args+=(--dart-define=CODEX_FEEDBACK_ENABLED="${{ vars.CODEX_FEEDBACK_ENABLED || 'false' }}")
          flutter build apk --release "${args[@]}"

      - name: Publish GitHub release
        uses: softprops/action-gh-release@v2
        with:
          files: apps/mobile/build/app/outputs/flutter-apk/app-release.apk
          generate_release_notes: true
"""


def _runtime_profiles_doc(name: str) -> str:
    return f"""# Runtime Profiles

`{name}` must keep mock/demo and productive runtime paths separate.

## Profiles

- `APP_RUNTIME_PROFILE=real`: default for productive releases. Requires
  `API_BASE_URL`, real backend, real auth, updater metadata with
  `mock_or_demo=false`, and hidden Workbench/dev tools.
- `APP_RUNTIME_PROFILE=staging`: real backend path for pre-production testing.
- `APP_RUNTIME_PROFILE=preview`: web preview path against the shared
  Cloudflare Preview API runtime.
- `APP_RUNTIME_PROFILE=mock`: opt-in demo path. Does not require backend and may
  show seed role selection.

## Release Tags

- Productive: `android-vX.Y.Z-build.N`
- Mock/demo: `android-mock-vX.Y.Z-build.N` or `android-local-vX.Y.Z-build.N`

Run before any release:

```bash
APP_RELEASE_TAG=<tag> APP_RUNTIME_PROFILE=<profile> API_BASE_URL=<url> scripts/validate_release_profiles.sh
```
"""


def _release_contracts_yaml(slug: str) -> str:
    return _to_yaml(
        {
            "schema_version": 1,
            "source_app": slug,
            "runtime_profiles": {
                "default": "real",
                "allowed": ["mock", "real", "staging"],
                "env": "APP_RUNTIME_PROFILE",
            },
            "mock_release": {
                "tag_patterns": ["android-mock-v*", "android-local-v*"],
                "runtime_profile": "mock",
                "mock_or_demo": True,
                "backend_required": False,
                "seed_role_selector": True,
            },
            "productive_release": {
                "tag_patterns": ["android-v*"],
                "runtime_profile": "real",
                "mock_or_demo": False,
                "backend_required": True,
                "forbidden": [
                    "LOCAL_DATA_MODE=true",
                    "localhost API_BASE_URL",
                    "placeholder API_BASE_URL",
                    "visible seed users",
                    "visible Workbench UI",
                    "hardcoded demo data",
                ],
            },
            "workbench": {
                "required": True,
                "visible_profiles": ["mock"],
                "hidden_profiles": ["real"],
                "identity_file": "codex-bridge.yaml",
                "docs": "docs/workbench.md",
            },
            "codex_mobile_catalog": {
                "required": True,
                "registration_script": "scripts/register_installable_app.sh",
                "bridge_endpoint": "/installable-apps",
                "verification_endpoint": "/installable-apps/{sourceApp}",
                "requires_apk_url": True,
            },
            "web_preview": {
                "required": True,
                "stable_url": f"https://preview.nienfos.com/{slug}",
                "manifest": "deploy/web-preview/web-preview-manifest.yaml",
                "build_script": "scripts/build_web_preview.sh",
                "validation_script": "scripts/validate_web_preview.sh",
                "api_runtime": "cloudflare_preview",
                "default_runtime_profile": "real",
                "cloudflare_resources": {
                    "worker_name": "nienfos-preview-runtime",
                    "pages_project": "nienfos-preview-web",
                    "d1_database": "nienfos-preview",
                    "r2_bucket": None,
                },
            },
        }
    )


def _release_output_template() -> str:
    return """# Factory Final Output

- commit_hash:
- repo_url:
- branch:
- mock_release_tag:
- productive_release_tag:
- apk_urls:
- runtime_profiles:
- mock_or_demo:
- backend_url:
- updater_response:
- workbench_status:
- codex_mobile_catalog_status:
- installable_app_url:
- tests_executed:
- blockers:
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
        "apps/mobile/test/config_test.dart": _mobile_config_test_dart(package_name),
        "apps/mobile/test/api_client_test.dart": _mobile_api_client_test_dart(
            package_name
        ),
        "apps/mobile/test/session_controller_test.dart": (
            _mobile_session_controller_test_dart(package_name)
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
    defaultValue: 'real',
  );
  const apiRuntime = String.fromEnvironment(
    'API_RUNTIME',
    defaultValue: 'fastapi',
  );
  const appSlug = String.fromEnvironment('APP_SLUG');
  final config = AppConfig.fromEnvironment(
    apiBaseUrl: apiBaseUrl,
    runtimeProfile: runtimeProfile,
    apiRuntime: apiRuntime,
    appSlug: appSlug,
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
    return MaterialApp(
      title: '{name}',
      theme: ThemeData(useMaterial3: true, colorSchemeSeed: Colors.teal),
      home: ProjectHome(
        projectName: '{name}',
        runtimeProfile: config.runtimeProfile,
        controller: SessionController(
          api: api,
          runtimeProfile: config.runtimeProfile,
        ),
      ),
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
  });

  final String? apiBaseUrl;
  final String runtimeProfile;
  final String apiRuntime;
  final String? appSlug;

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
  }) {
    final trimmed = apiBaseUrl.trim().replaceAll(RegExp(r'/$'), '');
    final normalizedProfile = runtimeProfile.trim().toLowerCase();
    final normalizedApiRuntime = apiRuntime.trim().toLowerCase();
    final trimmedSlug = appSlug.trim();
    return AppConfig(
      apiBaseUrl: trimmed.isEmpty ? null : trimmed,
      runtimeProfile: normalizedProfile.isEmpty ? 'real' : normalizedProfile,
      apiRuntime: normalizedApiRuntime.isEmpty ? 'fastapi' : normalizedApiRuntime,
      appSlug: trimmedSlug.isEmpty ? null : trimmedSlug,
    );
  }
}
"""


def _mobile_models_dart() -> str:
    return """class AppUser {
  const AppUser({required this.id, required this.email, required this.roles});

  final int id;
  final String email;
  final List<String> roles;

  bool get canAccessAdmin => roles.contains('owner') || roles.contains('admin');

  factory AppUser.fromJson(Map<String, dynamic> json) {
    return AppUser(
      id: json['id'] as int,
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
  final int id;
  final String email;
  final bool isActive;

  factory AdminUser.fromJson(Map<String, dynamic> json) {
    return AdminUser(
      id: json['id'] as int,
      email: json['email'] as String,
      isActive: json['is_active'] as bool,
    );
  }
}

class DomainRecord {
  const DomainRecord({required this.id, required this.name, required this.isActive});
  final int id;
  final String name;
  final bool isActive;

  factory DomainRecord.fromJson(Map<String, dynamic> json) {
    return DomainRecord(
      id: json['id'] as int,
      name: json['name'] as String,
      isActive: json['is_active'] as bool,
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

  final int id;
  final String title;
  final String body;
  final String? readAt;
  final String createdAt;

  bool get isRead => readAt != null;

  factory AppNotification.fromJson(Map<String, dynamic> json) {
    return AppNotification(
      id: json['id'] as int,
      title: json['title'] as String,
      body: json['body'] as String,
      readAt: json['read_at'] as String?,
      createdAt: json['created_at'] as String,
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

  Future<List<DomainRecord>> domains(String token) async {
    final response = await _client.get(_uri('/admin/domains'), headers: _authHeaders(token));
    if (response.statusCode != 200) {
      throw ApiException('Domains failed', response.statusCode, response.body);
    }
    return _list(response).map(DomainRecord.fromJson).toList(growable: false);
  }

  Future<DomainRecord> createDomain(String token, String name) async {
    final response = await _postJson('/admin/domains', {'name': name}, token: token);
    if (response.statusCode != 200) {
      throw ApiException('Create domain failed', response.statusCode, response.body);
    }
    return DomainRecord.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<List<AppNotification>> notifications(String token) async {
    final response = await _client.get(_uri('/notifications'), headers: _authHeaders(token));
    if (response.statusCode != 200) {
      throw ApiException('Notifications failed', response.statusCode, response.body);
    }
    return _list(response).map(AppNotification.fromJson).toList(growable: false);
  }

  Future<void> markNotificationRead(String token, int id) async {
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
  final List<DomainRecord> _domains = <DomainRecord>[
    DomainRecord(id: 1, name: 'Demo workspace', isActive: true),
  ];
  final List<AppNotification> _notifications = <AppNotification>[
    AppNotification(
      id: 1,
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
      id: seedRoles.indexOf(safeRole) + 1,
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
    final user = AppUser(id: _sessions.length + 1, email: email, roles: const <String>['customer']);
    _sessions[token] = user;
    _users.add(AdminUser(id: user.id, email: user.email, isActive: true));
    return AuthToken(accessToken: token, tokenType: 'mock');
  }

  @override
  Future<AuthToken> login({required String email, required String password}) {
    return register(email: email, password: password);
  }

  @override
  Future<AppUser> me(String token) async => _sessions[token] ?? const AppUser(id: 0, email: 'guest@mock.local', roles: <String>['guest']);

  @override
  Future<void> logout(String token) async {}

  @override
  Future<List<AdminUser>> adminUsers(String token) async => List<AdminUser>.from(_users);

  @override
  Future<List<String>> adminRoles(String token) async => seedRoles;

  @override
  Future<List<DomainRecord>> domains(String token) async => List<DomainRecord>.from(_domains);

  @override
  Future<DomainRecord> createDomain(String token, String name) async {
    final domain = DomainRecord(id: _domains.length + 1, name: name, isActive: true);
    _domains.add(domain);
    return domain;
  }

  @override
  Future<List<AppNotification>> notifications(String token) async => List<AppNotification>.from(_notifications);

  @override
  Future<void> markNotificationRead(String token, int id) async {}
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
    required this.controller,
  }});

  final String projectName;
  final String runtimeProfile;
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
  const AuthScreen({{super.key, required this.controller, required this.projectName}});
  final SessionController controller;
  final String projectName;

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}}

class _AuthScreenState extends State<AuthScreen> {{
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _register = false;
  String _seedRole = 'owner';

  @override
  void dispose() {{
    _email.dispose();
    _password.dispose();
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
                TextField(controller: _email, decoration: const InputDecoration(labelText: 'Email')),
                const SizedBox(height: 12),
                TextField(controller: _password, decoration: const InputDecoration(labelText: 'Password'), obscureText: true),
                const SizedBox(height: 16),
                if (widget.controller.isMockRuntime) ...[
                  DropdownButtonFormField<String>(
                    value: _seedRole,
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
                  child: Text(_register ? 'Register' : 'Login'),
                ),
                TextButton(
                  onPressed: () => setState(() => _register = !_register),
                  child: Text(_register ? 'Use login' : 'Create account'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }}

  Future<void> _submit() async {{
    if (_register) {{
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
  List<DomainRecord> _domains = <DomainRecord>[];
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
    _domains = await widget.api.domains(widget.token);
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
            TextField(controller: _domain, decoration: const InputDecoration(labelText: 'New domain')),
            FilledButton(onPressed: _createDomain, child: const Text('Create domain')),
            if (_domains.isEmpty) const Text('No domains'),
            ..._domains.map((domain) => ListTile(title: Text(domain.name))),
          ],
        );
      }},
    );
  }}

  Future<void> _createDomain() async {{
    final name = _domain.text.trim();
    if (name.isEmpty) return;
    await widget.api.createDomain(widget.token, name);
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
      apiBaseUrl: 'https://preview.nienfos.com',
      runtimeProfile: 'real',
      apiRuntime: 'cloudflare_preview',
      appSlug: 'clinica-norte',
    );
    expect(preview.isConfigured, isTrue);
    expect(preview.isPreview, isTrue);
    expect(preview.appSlug, 'clinica-norte');
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
        if (request.url.path == '/auth/login') return http.Response('{{"access_token":"t","token_type":"bearer"}}', 200);
        if (request.url.path == '/auth/me') return http.Response('{{"id":1,"email":"a@example.com","roles":["owner"]}}', 200);
        if (request.url.path == '/admin/users') return http.Response('[{{"id":1,"email":"a@example.com","is_active":true}}]', 200);
        if (request.url.path == '/admin/roles') return http.Response('["owner","customer"]', 200);
        if (request.url.path == '/admin/domains' && request.method == 'GET') return http.Response('[{{"id":1,"name":"primary","is_active":true}}]', 200);
        if (request.url.path == '/admin/domains' && request.method == 'POST') return http.Response('{{"id":2,"name":"new","is_active":true}}', 200);
        if (request.url.path == '/notifications' && request.method == 'GET') return http.Response('[{{"id":1,"title":"Welcome","body":"Hi","read_at":null,"created_at":"now"}}]', 200);
        if (request.url.path == '/notifications/1/read') return http.Response('{{"status":"read"}}', 200);
        return http.Response('missing', 404);
      }}),
    );
    expect(await api.health(), isTrue);
    final token = await api.login(email: 'a@example.com', password: 'secret');
    expect(token.accessToken, 't');
    expect((await api.me('t')).canAccessAdmin, isTrue);
    expect(await api.adminUsers('t'), hasLength(1));
    expect(await api.adminRoles('t'), contains('owner'));
    expect(await api.domains('t'), hasLength(1));
    expect((await api.createDomain('t', 'new')).name, 'new');
    expect(await api.notifications('t'), hasLength(1));
    await api.markNotificationRead('t', 1);
    expect(calls, contains('GET /health'));
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
    const user = AppUser(id: 1, email: 'user@example.com', roles: ['customer']);
    expect(user.canAccessAdmin, isFalse);
  }});
}}

class _FakeApi extends ProjectApiClient {{
  _FakeApi() : super(baseUrl: 'http://fake');

  @override
  Future<AuthToken> login({{required String email, required String password}}) async {{
    return const AuthToken(accessToken: 'token', tokenType: 'bearer');
  }}

  @override
  Future<AppUser> me(String token) async {{
    return const AppUser(id: 1, email: 'admin@example.com', roles: ['owner']);
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
    return """APP_RUNTIME_PROFILE=real
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
    runtime_profile = os.getenv("APP_RUNTIME_PROFILE", "real").strip().lower()
    if runtime_profile not in {"mock", "real", "staging"}:
        raise RuntimeError("APP_RUNTIME_PROFILE must be mock, real, or staging.")
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
            CREATE TABLE IF NOT EXISTS domains (
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


class DomainCreate(BaseModel):
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


@router.get("/domains")
def list_domains(_user=Depends(require_roles("admin", "manager"))):
    with connect() as conn:
        rows = conn.execute("SELECT id, name, is_active FROM domains ORDER BY id").fetchall()
    return [{"id": int(row["id"]), "name": row["name"], "is_active": bool(row["is_active"])} for row in rows]


@router.post("/domains")
def create_domain(payload: DomainCreate, _user=Depends(require_roles("admin"))):
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO domains(name, is_active) VALUES (?, 1)",
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
            "/admin/domains",
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
) -> dict[str, str]:
    return {
        "architecture/components.mmd": _components_diagram(),
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
        "architecture/deployment.mmd": _deployment_diagram(name),
        "architecture/deployment.yaml": _diagram_metadata(
            "deployment",
            "deployment",
            "architecture/deployment.mmd",
            f"Baseline deployment shape for {name}.",
        ),
        "architecture/overview.md": (
            "# Architecture Overview\n\n"
            f"`{name}` starts with Flutter clients, a FastAPI backend, RBAC, "
            "domain management, notifications, and Workbench SDD artifacts.\n\n"
            f"- Business type: `{business_type}`\n"
            f"- Primary goal: {primary_goal}\n\n"
            "Keep these baseline diagrams updated as specs, plans, and tasks evolve.\n"
        ),
    }


def _components_diagram() -> str:
    return """flowchart LR
    user[User]
    admin[Admin]
    mobile[Flutter Mobile App]
    web[Flutter Web App]
    api[FastAPI Backend]
    auth[Auth and RBAC]
    domain[Domain Management]
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
    api --> domain
    api --> notifications
    auth --> db
    domain --> db
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
    class DomainRecord {{
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
    AppUser "1" --> "*" DomainRecord
    {app_class}App --> AppUser
    {app_class}App --> DomainRecord
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


def _deployment_diagram(name: str) -> str:
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
) -> str:
    return f"""# Product Foundation

## Intent

Build `{name}` as a Flutter iOS/Android/Web app with a FastAPI backend, auth,
admin, roles, permissions, domain management, notifications, Codex Feedback
Bridge, app updater, and Workbench-driven feature growth.

## Business Context

- Business type: `{business_type}`
- Primary goal: {primary_goal}

## Promoted Assets

{_promoted_assets_spec_section(project_assets)}

## Creation Workflow

New-project creation uses Codex CLI by default with:

- generator runs: {workflow["generator_runs"]}
- reviewer runs: {workflow["reviewer_runs"]}
- mode: `{workflow["mode"]}`

## Required Foundation

- Login and registration.
- Google login placeholders.
- RBAC with owner/admin/manager/staff/customer/guest.
- Admin domain-management shell.
- Notification foundations.
- FastAPI backend v1 with SQLite DATABASE_URL, PBKDF2 password hashing,
  JWT-compatible HS256 tokens, admin seed by env, RBAC guards, domain CRUD,
  notification outbox, healthcheck, CORS, and generated tests.
- Flutter mobile v1 with API_BASE_URL configuration, real auth/session calls,
  RBAC admin gating, domain management screens, notifications, and generated tests.
- SDD artifacts for future Workbench features.
- Baseline Workbench diagrams for components, classes, entity relationships, and
  deployment.
"""


def _initial_plan(name: str) -> str:
    return f"""# Plan

Create the foundation for `{name}` in incremental validated slices:

1. Complete business research and visual direction.
2. Extend the generated Flutter auth/admin/notification app with domain UX.
3. Extend FastAPI backend v1 beyond the generated auth/RBAC/admin/notification base.
4. Add domain-specific resources and workflows.
5. Wire Feedback Bridge, updater, and Workbench.
6. Validate local run and release readiness.
"""


def _initial_tasks() -> str:
    return """# Tasks

- [ ] Complete business research.
- [ ] Complete visual reference analysis.
- [x] Generate Flutter mobile v1 with API_BASE_URL, auth/session, RBAC admin gating, domain management, notifications, and generated tests.
- [x] Generate backend v1 with FastAPI, auth, RBAC, admin, domain CRUD foundation, and notifications.
- [x] Add auth and Google login placeholders.
- [x] Add RBAC and admin shell.
- [x] Add domain CRUD foundation.
- [x] Add notification foundation.
- [x] Add baseline SDD diagrams for components, classes, data, and deployment.
- [ ] Wire Feedback Bridge and updater.
- [ ] Validate Workbench integration and release readiness.
"""


def _initial_metadata(slug: str, name: str) -> str:
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
            "tasks": {"total": 10, "completed": 0, "pending": 10},
            "last_run_state": None,
            "metadata_status": "fresh",
            "metadata_warnings": [],
            "metadata_stale_paths": [],
            "available_files": ["spec.md", "plan.md", "tasks.md"],
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


def _visual_validation_report_template() -> str:
    return """# Visual Validation Report

## References Used

- TODO: list asset IDs, filenames, roles, and SHA256 values.

## Derived Screens

- TODO: map each reference to generated screens.

## Logo And Icon

- TODO: logo path.
- TODO: app icon source path.
- TODO: whether logo and icon share the same source.

## Preview Screenshots

- TODO: list generated screenshots/previews.

## What Was Preserved

- TODO: layout, navigation, components, typography, spacing, visual rhythm.

## Intentional Differences

- TODO: palette changes, domain adaptations, accessibility changes.

## Result

Generation must fail if the UI remains generic while visual references exist.
"""


def _gitignore() -> str:
    return """.env
.env.*
!.env.example
.dart_tool/
build/
__pycache__/
*.pyc
.codex-bridge/
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
