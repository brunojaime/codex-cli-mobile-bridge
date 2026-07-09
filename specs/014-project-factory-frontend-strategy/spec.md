# Project Factory Frontend Strategy

id: 014-project-factory-frontend-strategy
status: implemented
owner: codex-mobile-bridge

## Intent

Define a frontend strategy layer for New Project Factory so a new project can
choose a known frontend implementation path instead of assuming every project is
the same Flutter app.

The first supported strategies are:

- `flutter`: the current default path. It must keep Android preview APK,
  Flutter web preview, Workbench, Bridge installable registration, and
  Cloudflare Preview API/D1.
- `svelte`: a new web-first path. It must generate an independent Svelte app,
  deploy public web preview through Cloudflare, use the same Cloudflare Preview
  API/D1 contract, and avoid claiming Android installability unless an Android
  wrapper strategy is explicitly selected and implemented.

The goal is not to weaken Initial Preview Release. The goal is to make the
frontend choice explicit, testable, and blocked when a requested strategy cannot
fulfill its release contract.

## Product Outcome

When a user creates a new project, New Project Factory can select or infer a
frontend strategy and show exactly what release deliverables will be produced.

For a Flutter project, the Factory produces:

- Flutter mobile/web app;
- Android preview APK published as `android-preview-v*`;
- Flutter web assets deployed to `https://preview.nienfos.com/{slug}`;
- API calls pointed at `https://preview.nienfos.com/{slug}/api`;
- Workbench visible in preview for owner/admin;
- Bridge installable app registration;
- Cloudflare Worker/D1 preview backend.

For a Svelte project, the Factory produces:

- Svelte web app;
- web preview deployed to `https://preview.nienfos.com/{slug}`;
- API calls pointed at `https://preview.nienfos.com/{slug}/api`;
- Cloudflare Worker/D1 preview backend;
- release output that is explicit about web-first status;
- no APK or Bridge installable claim unless a Svelte Android wrapper strategy is
  enabled and validated.

## Core Rules

- Flutter remains the default strategy for mobile app requests and for requests
  that require Android APK installation.
- Svelte is a first-class web strategy, not a Flutter fallback.
- Every strategy must declare release capabilities before generation starts.
- Strategy selection must be visible in draft, manifest, generated spec, plan,
  tasks, release contracts, workflows, and release output.
- Preview runtime remains `APP_RUNTIME_PROFILE=preview` or an equivalent
  strategy-specific profile variable mapped to `preview`.
- Preview API runtime remains `cloudflare_preview`.
- Preview API base URL must be `https://preview.nienfos.com/{slug}/api`.
- No strategy may use localhost, mock, placeholder, or production backend URLs
  for an Initial Preview Release.
- Cloudflare Worker/D1 is the required preview backend for both Flutter and
  Svelte strategies.
- A strategy may not report `installable=true` unless it produces a verified APK
  or another Bridge-supported installable artifact.
- Svelte web-first releases must not be registered as Android installable apps
  unless an Android wrapper release path is implemented.
- Productive release remains blocked until explicit promotion, regardless of
  frontend strategy.

## Strategy Contract

Each frontend strategy must declare:

```yaml
id: flutter | svelte
display_name: Flutter | Svelte
project_kind: mobile_web | web
source_root: apps/mobile | apps/web
web_build_command: <command>
web_build_output: <path>
preview_api_env: API_BASE_URL
runtime_profile_env: APP_RUNTIME_PROFILE
api_runtime_env: API_RUNTIME
supports_android_preview_apk: true | false
supports_bridge_installable_app: true | false
supports_workbench_apk_entry: true | false
cloudflare_preview_required: true
d1_preview_required: true
release_channel: prerelease
production_ready: false
mock_or_demo: false
validation_scripts:
  - <strategy validation script>
```

The generated project must include this contract in:

- `.codex/project.yaml`;
- `release/release-contracts.yaml`;
- `release/preview-runtime.json`;
- `deploy/web-preview/web-preview-manifest.yaml`;
- strategy-specific config files;
- generated workflows;
- generated spec/plan/tasks.

## Flutter Strategy

Flutter strategy is the current complete mobile/web release path. It remains the
default for:

- mobile app requests;
- iOS/Android platform requests;
- requests that need APK installability;
- requests that need Workbench inside the preview APK.

Flutter release requirements:

- generated app under `apps/mobile`;
- Android project present under `apps/mobile/android`;
- web build via Flutter web;
- Android preview workflow `.github/workflows/android-preview-release.yml`;
- preview APK release tag `android-preview-v*`;
- GitHub release `prerelease`;
- Bridge `/installable-apps/{sourceApp}` registration with `available=true`;
- Workbench visible in preview for owner/admin;
- Flutter tests for runtime profile and Workbench visibility.

## Svelte Strategy

Svelte strategy is web-first and must not pretend to be a mobile APK release.

Svelte release requirements:

- generated app under `apps/web`;
- package manager lockfile and scripts for install, test, lint, and build;
- web build output suitable for Cloudflare preview assets;
- Cloudflare preview Worker route `preview.nienfos.com/{slug}/*`;
- Preview API calls configured to `https://preview.nienfos.com/{slug}/api`;
- Svelte tests that fail on localhost/mock/placeholder preview API config;
- release output that says `web_preview_ready=true` only after public health and
  API health pass;
- `installable_android=false` unless a wrapper strategy is selected.

Optional future Svelte installable path:

- `svelte-capacitor-android` or another named wrapper strategy may produce an
  APK, but it must have its own contract, workflow, tests, APK checksum,
  GitHub prerelease, and Bridge installable registration before it can claim
  installability.

## Strategy Selection

The Factory should select strategy from explicit user input first, then infer
from requested platforms:

- explicit `frontendStrategy=flutter`: Flutter path;
- explicit `frontendStrategy=svelte`: Svelte web-first path;
- platforms include `android` or `ios`: default to Flutter unless the user
  explicitly selects a supported wrapper strategy;
- platforms are web-only and user asks for Svelte: Svelte path;
- unknown strategy: block with supported strategy list.

If user asks for Svelte plus Android APK before a wrapper strategy exists, the
Factory must block or ask for clarification. It must not silently generate a
non-installable project while promising an APK.

## Cloudflare Preview Contract

Both strategies use the same Cloudflare preview backend:

- public web preview: `https://preview.nienfos.com/{slug}`;
- public API preview: `https://preview.nienfos.com/{slug}/api`;
- Worker route: `preview.nienfos.com/{slug}/*`;
- API runtime: `cloudflare_preview`;
- D1 persistence: required;
- health routes: `/__preview/health` and `/api/health`;
- no localhost/mock/placeholder API URL for preview.

The shared Cloudflare doctor and apply gate must run before either strategy is
allowed to report preview readiness.

## Release Output Contract

Release output must be strategy-aware.

Flutter output must include:

- APK URL and SHA256 when available;
- GitHub prerelease URL;
- Bridge installable URL;
- Cloudflare web/API URLs;
- Workbench APK visibility validation.

Svelte output must include:

- web preview URL;
- API preview URL;
- Cloudflare route and D1 migration evidence;
- public health and API health results;
- explicit `installable_android=false` unless wrapper release evidence exists;
- blockers for missing APK only when the selected strategy promises APK.

## Validation Requirements

Strategy validation must fail when:

- selected strategy is missing from any source of truth;
- strategy capability says APK is supported but Android release workflow is
  missing;
- strategy capability says APK is not supported but release output or Bridge
  catalog claims installability;
- preview API does not point to `https://preview.nienfos.com/{slug}/api`;
- Cloudflare public health fails;
- API public health fails;
- D1 migrations are not applied;
- generated strategy tests are missing;
- Flutter preview does not show Workbench for owner/admin;
- Svelte preview uses mock/local data for Initial Preview Release.

## Non-Goals

- Do not replace Flutter as the default mobile strategy.
- Do not implement Svelte Android APK support without a named wrapper strategy.
- Do not publish production releases from this spec.
- Do not weaken Initial Preview Release gates.
- Do not register web-only Svelte projects as installable Android apps.

## Acceptance Criteria

- AC-001: Project Factory options expose known frontend strategies `flutter` and
  `svelte`.
- AC-002: Draft and manifest payloads include selected `frontendStrategy`.
- AC-003: Generated Flutter projects keep the existing Initial Preview Release
  contract and tests.
- AC-004: Generated Svelte projects have a web-first Cloudflare preview contract.
- AC-005: Strategy metadata is present in `.codex/project.yaml`,
  `release/release-contracts.yaml`, `release/preview-runtime.json`, web preview
  manifest, generated workflows, and release output.
- AC-006: Strategy validation fails when a promised APK, Bridge registration,
  Workbench entry, Cloudflare route, API health, or D1 persistence evidence is
  missing.
- AC-007: A web-only Svelte project can reach `web_preview_ready=true` without
  claiming Android installability.
- AC-008: A Svelte request that also requires Android installability blocks until
  a supported wrapper strategy is selected.
- AC-009: Both strategies use the Cloudflare Preview API/D1 backend for preview.
- AC-010: Spec, plan, tasks, traceability, generated project validation, and
  frontend strategy tests cover both paths.
