# Tasks

## Phase 1: Release Mode Contract

- [ ] T001 Add `preview` release mode to Project Factory planning models.
- [ ] T002 Define release profile metadata for `preview`, `real`, and `mock`.
- [ ] T003 Define tag prefixes: `android-preview-v*`, `android-v*`, and
      `android-mock-v*`.
- [ ] T004 Define job readiness rules for Initial Preview Release.
- [ ] T005 Define preview-to-production promotion metadata.
- [ ] T006 Add contract tests for mutually exclusive release modes.

## Phase 2: Project Factory Contract Updates

- [ ] T007 Add first-release mode to draft request/response schemas.
- [ ] T008 Default first-release mode to `preview`.
- [ ] T009 Add explicit production and mock/demo opt-in validation.
- [ ] T010 Update chat-first New Project prompt to describe Initial Preview
      Release as the default.
- [ ] T011 Update build-ready preview text with Cloudflare URL, D1 persistence,
      Android APK, Bridge registration, and production-not-ready state.
- [ ] T012 Add Initial Preview Release fields to job history/status payloads.
- [ ] T013 Update generated `release/` docs to explain preview, production, and
      mock/demo channels.

## Phase 3: Cloudflare Preview Backend Readiness

- [ ] T014 Reuse Cloudflare doctor results as a hard gate for preview apply.
- [ ] T015 Add preview apply enablement flag and blocked output when disabled.
- [ ] T016 Provision or verify `https://preview.nienfos.com/<app-slug>`.
- [ ] T017 Provision or select D1 database/scope for the generated app.
- [ ] T018 Generate D1 migrations from generated domain entities.
- [ ] T019 Apply D1 migrations idempotently.
- [ ] T020 Seed only required preview bootstrap/admin data, not fake demo data.
- [ ] T021 Verify preview API `/health`.
- [ ] T022 Verify app/tenant scoping for D1 records.
- [ ] T023 Add cost posture report before paid resources can be used.
- [ ] T024 Add blocked status for paid-resource requirements without operator
      confirmation.

## Phase 4: Generated App Runtime Profile

- [ ] T025 Generate `APP_RUNTIME_PROFILE=preview` support for Flutter web and
      Android.
- [ ] T026 Generate `API_RUNTIME=cloudflare_preview` support.
- [ ] T027 Generate preview `API_BASE_URL` using the stable preview app route.
- [ ] T028 Generate `APP_SLUG` runtime define.
- [ ] T029 Route preview API clients through Preview API v1.
- [ ] T030 Keep FastAPI real/staging clients separate from preview clients.
- [ ] T031 Fail preview validation on localhost, example URLs, or missing
      preview API URL.
- [ ] T032 Fail preview validation when mock/local seeded data is the primary
      runtime.
- [ ] T033 Add generated Flutter tests for preview runtime selection.

## Phase 5: Android Preview Release Workflow

- [ ] T034 Generate `.github/workflows/android-preview-release.yml`.
- [ ] T035 Generate `scripts/publish_android_preview_release.sh`.
- [ ] T036 Generate `scripts/validate_preview_release_profiles.sh`.
- [ ] T037 Build preview APKs with preview runtime defines.
- [ ] T038 Write `release/preview-runtime.json`.
- [ ] T039 Publish GitHub releases with `android-preview-v*` tags.
- [ ] T040 Verify APK asset presence and checksum.
- [ ] T041 Verify app updater metadata points to the preview channel.
- [ ] T042 Allow debug-preview signing only with explicit metadata.
- [ ] T043 Keep `android-v*` productive signing gates unchanged.
- [ ] T044 Add tests for preview release tag and metadata validation.

## Phase 6: Bridge Installable-App Registration

- [ ] T045 Extend Bridge registration payload with `release_channel=preview`.
- [ ] T046 Register display name as `<App Name> Preview`.
- [ ] T047 Include preview URL in installable-app metadata.
- [ ] T048 Include runtime profile, tag, APK asset, and update metadata.
- [ ] T049 Include `production_ready=false` and `mock_or_demo=false`.
- [ ] T050 Verify Bridge catalog lookup by `source_app`.
- [ ] T051 Block with manual command when `BRIDGE_URL` is missing.
- [ ] T052 Block with manual command when registration token is missing.
- [ ] T053 Add tests for successful preview app registration.
- [ ] T054 Add tests for blocked registration config.

## Phase 7: Factory Runner Orchestration

- [ ] T055 Add `initial_preview_release` phase group to Factory jobs.
- [ ] T056 Run local generated-project validation before preview publication.
- [ ] T057 Run GitHub repository create/verify/push before preview release.
- [ ] T058 Run Cloudflare preview apply after GitHub publication.
- [ ] T059 Run web preview smoke tests after Cloudflare apply.
- [ ] T060 Run Android preview release after preview API health passes.
- [ ] T061 Run Bridge registration after APK asset verification.
- [ ] T062 Run final readiness validation across GitHub, Cloudflare, Android,
      updater metadata, and Bridge.
- [ ] T063 Persist per-phase status, logs, blockers, and manual next steps.
- [ ] T064 Recover interrupted preview release jobs without duplicating
      resources.

## Phase 8: Mobile And Workbench UX

- [ ] T065 Show Initial Preview Release status in Project Factory History.
- [ ] T066 Add open/copy preview URL actions.
- [ ] T067 Show Android preview APK install state through Apps catalog.
- [ ] T068 Show release channel, tag, signing mode, and production readiness.
- [ ] T069 Show production release as pending/not requested after preview
      success.
- [ ] T070 Show exact blockers and manual commands for missing config.
- [ ] T071 Add Workbench readiness fields for preview URL, APK, Bridge
      registration, and blockers.

## Phase 9: Validation And Regression Coverage

- [ ] T072 Add regression test that first release defaults to preview.
- [ ] T073 Add regression test that jobs cannot report `ready` without
      Cloudflare preview success.
- [ ] T074 Add regression test that jobs cannot report `ready` without Bridge
      preview registration.
- [ ] T075 Add validation test that preview APK points to preview API.
- [ ] T076 Add validation test that preview APK does not use localhost,
      placeholder, or mock primary data paths.
- [ ] T077 Add validation test that `android-v*` still requires production
      backend health and release signing.
- [ ] T078 Add validation test that mock/demo releases stay visibly separate
      from preview releases.

## Phase 10: Operations Documentation

- [ ] T079 Document Initial Preview Release required environment variables.
- [ ] T080 Document Cloudflare apply, D1, Worker, DNS, and cost guardrails.
- [ ] T081 Document Android preview signing policy.
- [ ] T082 Document Bridge preview registration and manual fallback.
- [ ] T083 Document preview update, disable, extend, and troubleshooting.
- [ ] T084 Document promotion from preview to production.
- [ ] T085 Update Project Factory runbooks with generic false-readiness failure examples.
