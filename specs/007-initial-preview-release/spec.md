---
id: 007-initial-preview-release
title: Initial Preview Release
status: draft
type: feature
domains:
  - project-factory
  - release-readiness
  - cloudflare
  - android
  - installable-apps
related_specs:
  - 005-new-project-factory
  - 006-web-preview-delivery
---

# Initial Preview Release

## Intent

Every New Project Factory run must produce a first usable release that a user can
open, install, and validate without waiting for final production hosting. The
default first release is an Initial Preview Release: a Cloudflare-backed preview
environment with persistent real preview data, a stable preview URL, and an
Android APK registered in Codex Mobile Apps.

This release is not a mock/demo build and is not final production. It uses a real
preview backend and real persistence, but it is clearly labeled as preview so it
cannot be confused with a production `android-v*` release.

## Implementation Context

This spec is self-contained for implementation planning, but it intentionally
extends two existing contracts that an implementation agent must load before
changing code:

- `specs/005-new-project-factory/` defines New Project intake, generated repo
  structure, runner phases, release publication, and Bridge visibility.
- `specs/006-web-preview-delivery/` defines Cloudflare preview planning/apply,
  stable preview URLs, Worker runtime, D1 persistence, invite/access behavior,
  and preview status surfaces.

If those specs and this spec conflict, this spec wins only for the default
first-release mode and preview Android registration. It must not weaken
production gates, mock/demo labeling, or Web Preview Delivery safety gates from
the existing specs.

## Product Outcome

After the first successful New Project run, the final report should be able to
show:

```text
Project: <Project Name>
Repo: https://github.com/<owner>/<app-slug>
Preview URL: https://preview.nienfos.com/<app-slug>
Android APK: registered in Codex Mobile Apps
Runtime profile: preview
Data: Cloudflare D1 preview database
Production status: not requested
```

The user should be able to:

- open the web preview in a browser;
- install the Android preview APK from Codex Mobile Apps;
- log in as an invited/admin preview user;
- create and edit real preview records that persist in Cloudflare D1;
- review feedback and continue development from the generated project.

## Core Rule

The first release for a new project defaults to `preview`, not `real` production
and not `mock`.

```text
Initial release default: preview
Production release: explicit later step
Mock/demo release: explicit opt-in only
```

The Factory must not require a final product domain such as
`https://api.<project>.com` for the initial release. It must require a working
Cloudflare preview URL and a working preview API instead.

## Scope

- Add an Initial Preview Release contract to New Project Factory.
- Require Cloudflare preview provisioning for first release readiness.
- Require a D1 preview database or tenant-scoped D1 tables for persistent
  preview data.
- Require Android preview APK generation and GitHub release publication.
- Require Bridge installable-app registration for the preview APK.
- Add release tags, metadata, validation, and job states for preview releases.
- Keep final production release validation strict and separate.
- Keep mock/demo releases explicit and visibly different.
- Surface web preview and Android preview status in Project Factory history,
  generated release docs, and Workbench readiness.

## Non-Goals

- Do not deploy final production infrastructure during the initial preview
  release.
- Do not require AWS, VPS, final database hosting, Play Store, or App Store
  credentials for the initial preview release.
- Do not mark preview as production-ready.
- Do not register mock/demo builds as normal preview builds.
- Do not use localhost, in-memory-only data, seeded demo selectors, or
  placeholder API URLs in an Initial Preview Release.
- Do not weaken productive release gates for `android-v*` tags.

## Release Modes

### Preview

Preview is the default first release mode.

```yaml
runtime_profile: preview
mock_or_demo: false
backend_required: true
backend_kind: cloudflare_preview
data_persistence: cloudflare_d1
production_ready: false
tag_prefix: android-preview-v
```

Preview releases use real remote preview data paths. They may use generated
preview admin accounts and invite flows, but they must not use fake local data as
the primary runtime.

### Production

Production is a later explicit release mode.

```yaml
runtime_profile: real
mock_or_demo: false
backend_required: true
backend_kind: production
data_persistence: production_selected
production_ready: true
tag_prefix: android-v
```

Production releases must keep the existing hard gates: real backend health,
non-placeholder API URL, release signing, updater metadata, GitHub release
assets, and Bridge registration.

### Mock Or Demo

Mock/demo is explicit opt-in only.

```yaml
runtime_profile: mock
mock_or_demo: true
backend_required: false
backend_kind: local_or_seeded
data_persistence: local_or_seeded
production_ready: false
tag_prefix: android-mock-v
```

Mock/demo releases must be labeled in version scope, tag, release title,
metadata, Bridge catalog entry, and final report.

## Cloudflare Preview Backend Contract

The Initial Preview Release depends on Web Preview Delivery from
`006-web-preview-delivery`, with one additional requirement: Android preview apps
must use the same preview API and D1 persistence as the web preview.

Required runtime configuration:

```text
APP_RUNTIME_PROFILE=preview
API_RUNTIME=cloudflare_preview
API_BASE_URL=https://preview.nienfos.com/<app-slug>/api
APP_SLUG=<app-slug>
```

Cloudflare provisioning must provide:

- stable preview route: `https://preview.nienfos.com/<app-slug>`;
- API route prefix: `https://preview.nienfos.com/<app-slug>/api`;
- API route for generated app clients;
- D1 database or tenant-scoped D1 schema;
- migrations for generated domain entities;
- preview auth/session storage;
- admin invite or generated admin bootstrap path;
- app update metadata endpoint;
- health endpoint;
- disable/expire controls.

The Preview API is not satisfied by a static web-preview Worker. The Worker or
bound Cloudflare runtime must implement the generated app's required API surface
under `/<app-slug>/api`, including:

- `GET /health`;
- auth/session endpoints required by the generated Flutter app;
- app config and app-update metadata endpoints;
- generated catalog/domain CRUD endpoints;
- generated admin read/write endpoints needed for first validation;
- generated notification endpoints;
- app-scoped D1 reads and writes with cross-app isolation.

The Factory must not build or publish an Android preview APK until the deployed
Preview API passes health, authentication, representative persistence, and
app-scope isolation smoke tests.

The Factory must report `blocked` if Cloudflare apply is disabled, credentials
are missing, D1 migration fails, the Worker health check fails, or the stable URL
cannot be verified.

## Android Preview Contract

The first Android build must point at the Cloudflare preview API, not at a final
production API domain.

Required generated artifacts:

```text
.github/workflows/android-preview-release.yml
scripts/publish_android_preview_release.sh
scripts/validate_preview_release_profiles.sh
release/preview-release-output-template.md
release/preview-runtime.json
```

The preview APK release tag must use:

```text
android-preview-v<version>-build.<build>
```

The GitHub release must include:

- APK asset;
- source commit;
- preview URL;
- `runtime_profile=preview`;
- `backend_kind=cloudflare_preview`;
- `mock_or_demo=false`;
- `production_ready=false`;
- app updater metadata;
- Bridge registration metadata.

Debug signing may be allowed for preview APKs only when the final report,
release metadata, and Bridge catalog entry say `signing=debug_preview`. A
production `android-v*` tag must still require real release signing.

## Bridge Registration Contract

A successful Initial Preview Release is not complete until the APK is registered
with Codex Mobile Bridge installable apps.

The Bridge catalog entry must make preview status visible:

```yaml
source_app: <app-slug>
display_name: "<Project Name> Preview"
runtime_profile: preview
release_channel: prerelease
preview_url: https://preview.nienfos.com/<app-slug>
apk_release_tag: android-preview-v0.1.0-build.1
production_ready: false
mock_or_demo: false
```

If `BRIDGE_URL` or `INSTALLABLE_APPS_REGISTRATION_TOKEN` is missing, the Factory
job must end as `blocked` with a manual registration command. It must not report
the project as installable.

## Factory Job Flow

Remote preview publication mode must run these phases in order:

1. Finalize and validate local generated project.
2. Create or verify GitHub repository, push the branch, and configure the
   GitHub Actions `API_BASE_URL` variable to
   `https://preview.nienfos.com/<app-slug>/api`.
3. Provision or update Cloudflare preview resources.
4. Apply D1 migrations and generated preview seed/bootstrap data.
5. Build and smoke-test Flutter web preview.
6. Build Android preview APK with preview runtime defines.
7. Publish the `android-preview-v*` GitHub release and verify APK assets.
8. Register the preview APK in Bridge installable apps.
9. Validate web preview, preview API health, APK metadata, updater metadata, and
   Bridge catalog visibility.

The job may complete as `ready` only when web preview and Android preview
registration both pass. Missing configuration must produce `blocked`, not
`ready`.

## Final Job Payload

```yaml
initial_preview_release:
  status: ready | blocked | failed | skipped
  release_mode: preview
  project_slug: <app-slug>
  github:
    repository_url: https://github.com/<owner>/<repo>
    branch: main
    commit: <sha>
  cloudflare:
    status: active | blocked | failed
    preview_url: https://preview.nienfos.com/<app-slug>
    api_base_url: https://preview.nienfos.com/<app-slug>/api
    worker_name: <worker-name>
    d1_database: <database-or-shared-name>
    d1_scope: <app-slug-or-tenant-id>
  android:
    status: published | blocked | failed
    release_tag: android-preview-v0.1.0-build.1
    apk_asset: app-release.apk
    runtime_profile: preview
    signing: release_preview | debug_preview | blocked_missing_signing
  bridge:
    status: registered | blocked | failed
    source_app: <app-slug>
    catalog_channel: prerelease
  validation:
    generated_project: pass | fail | skipped
    cloudflare_health: pass | fail | skipped
    d1_migrations: pass | fail | skipped
    web_preview_smoke: pass | fail | skipped
    android_metadata: pass | fail | skipped
    apk_asset: pass | fail | skipped
    bridge_catalog: pass | fail | skipped
  blockers: []
```

## Cost Guardrail

Initial Preview Release should target Cloudflare free-compatible usage for small
preview apps. The implementation must not assume that every account or usage
pattern is free forever. Instead, it must report a cost posture before applying
resources:

```yaml
cost_posture:
  target: free_compatible_preview
  paid_resources_required: false
  paid_blockers: []
  operator_confirmation_required: false
```

If the selected Cloudflare account, feature, storage usage, route strategy, or
email provider requires paid resources, the job must become blocked until the
operator explicitly confirms.

## Security Requirements

- Keep Cloudflare, Bridge, signing, and email provider secrets outside generated
  repos.
- Do not log plaintext invite tokens, passwords, API tokens, keystore passwords,
  or Bridge registration tokens.
- Scope all D1 data by app or tenant.
- Deny cross-app data reads and writes.
- Support preview disablement even if generated app code is broken.
- Expire preview invites by default.
- Keep production release gates stricter than preview gates.
- Make `preview`, `real`, and `mock` mutually explicit in release metadata.

## Hardening Contract

Initial Preview Release uses `runtime_profile=preview`, Android tags
`android-preview-v*`, and Bridge/GitHub release channel `prerelease`.
`mock_or_demo=false`, `backend_required=true`, and `production_ready=false` are
required in generated release metadata, Bridge registration, updater metadata,
and final release output. Productive `android-v*` release publication remains
blocked until explicit promotion.

Workbench visibility is part of preview completeness:

- `mock`: Workbench visible.
- `preview`: Workbench visible for `owner`/`admin`, or explicitly authorized
  developer mode.
- `staging`: internal/developer-authorized only.
- `real`: Workbench hidden.

Generated Flutter tests must fail if `APP_RUNTIME_PROFILE=preview` does not show
a Workbench entry for `owner` or `admin`, or if `APP_RUNTIME_PROFILE=real` shows
Workbench.

The generated Cloudflare Worker must match the Bridge deploy mode. When Bridge
uploads `application/javascript` classic Worker code, the generated Worker must
use `addEventListener('fetch', ...)` and must not use `export default`.
Validation must fail if the generated Worker format and deploy mode diverge.

Bridge verification is required through `/installable-apps/{sourceApp}`. The
response must include `available=true`, `apkUrl`, `releaseTag` matching
`android-preview-v*`, `releaseChannel=prerelease`, and a 64-character SHA256
when a checksum is available.

Cloudflare readiness must explicitly validate DNS read/edit, Worker script
edit, Workers Routes read/edit, D1 create/query, and Pages read/create when
Pages is used. Missing `Workers Routes: Edit` must be an explicit doctor
failure. Apply cannot be marked ready unless the public health route, Preview
API health route, Worker route, D1 migrations, and DNS state are verified.

`release/release-output-template.md` is updated by final preview validation with
current commit, push state, APK URL, APK SHA256 if available, GitHub release URL,
Bridge installable URL, Cloudflare URLs, validations executed, and remaining
blockers. Validation fails if the output is stale for the current commit or
claims preview/release/installable/API readiness without the corresponding
Cloudflare, APK, Bridge, Workbench, or D1 evidence.

## Relationship To Existing Specs

This section is normative implementation routing, not background. An agent
implementing this package must inspect the referenced specs directly.

`005-new-project-factory` defines the project creation and publication contract.
This spec changes the default first release mode from productive Android release
to Initial Preview Release.

`006-web-preview-delivery` defines the Cloudflare web preview platform. This
spec requires Android preview builds to use that same platform and requires
Bridge registration before the first release is considered usable.

Existing productive release scripts, updater metadata, and validation remain
required for later `android-v*` releases.

## Acceptance Criteria

- AC-001: A new project's first release defaults to `runtime_profile=preview`.
- AC-002: The first release provisions or updates
  `https://preview.nienfos.com/<app-slug>`.
- AC-003: The preview API uses Cloudflare Worker and D1-backed persistent data.
- AC-004: The generated Android preview APK points to the preview API URL.
- AC-005: The Android preview release tag uses `android-preview-v*`.
- AC-006: The preview APK is registered in Bridge installable apps before the
  job reports `ready`.
- AC-007: Codex Mobile Apps shows the preview entry as preview, not production.
- AC-008: Missing Cloudflare apply/config, D1 migration, GitHub release, APK
  asset, Bridge URL, or Bridge token ends in `blocked` with concrete next steps.
- AC-009: Productive `android-v*` releases still fail without real backend
  health, real signing, production-safe metadata, and Bridge registration.
- AC-010: Mock/demo releases remain explicit and cannot be confused with preview
  or production.
- AC-011: Project Factory history shows repo, preview URL, APK release,
  installable-app registration, validation, and blockers.
- AC-012: Generated release docs explain how to promote from preview to
  production later.
- AC-013: Preview APKs show Workbench for `owner`/`admin` and hide it in
  productive `real` releases.
- AC-014: `/installable-apps/{sourceApp}` returns `available=true`, `apkUrl`,
  `releaseTag=android-preview-v*`, `releaseChannel=prerelease`, and checksum
  when available before the job can be complete.
- AC-015: Cloudflare doctor and apply fail explicitly when Workers Routes edit,
  D1 migration, public health, API health, route, or DNS verification is
  missing.
- AC-016: Generated Worker format is classic `addEventListener('fetch', ...)`
  when deployed as `application/javascript`.
- AC-017: Final release output is regenerated from current evidence and cannot
  be stale or overpromise readiness.
