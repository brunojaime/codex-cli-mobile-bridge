# Tasks

This file is the legacy task index. Task numbering is local to each plan in `tree.json`.

## Plan 1: Release Mode Contract

- [ ] T001 Add preview release mode to Project Factory planning models. ([Task 1](./tasks/plan-1-task-1/task.md))
- [ ] T002 Define release profile metadata for preview, real, and mock. ([Task 2](./tasks/plan-1-task-2/task.md))
- [ ] T003 Define tag prefixes: android-preview-v*, android-v*, and android-mock-v*. ([Task 3](./tasks/plan-1-task-3/task.md))
- [ ] T004 Define job readiness rules for Initial Preview Release. ([Task 4](./tasks/plan-1-task-4/task.md))
- [ ] T005 Define preview-to-production promotion metadata. ([Task 5](./tasks/plan-1-task-5/task.md))
- [ ] T006 Add contract tests for mutually exclusive release modes. ([Task 6](./tasks/plan-1-task-6/task.md))

## Plan 2: Project Factory Contract Updates

- [ ] T007 Add first-release mode to draft request/response schemas. ([Task 1](./tasks/plan-2-task-1/task.md))
- [ ] T008 Default first-release mode to preview. ([Task 2](./tasks/plan-2-task-2/task.md))
- [ ] T009 Add explicit production and mock/demo opt-in validation. ([Task 3](./tasks/plan-2-task-3/task.md))
- [ ] T010 Update chat-first New Project prompt to describe Initial Preview Release as the default. ([Task 4](./tasks/plan-2-task-4/task.md))
- [ ] T011 Update build-ready preview text with Cloudflare URL, D1 persistence, Android APK, Bridge registration, and production-not-ready state. ([Task 5](./tasks/plan-2-task-5/task.md))
- [ ] T012 Add Initial Preview Release fields to job history/status payloads. ([Task 6](./tasks/plan-2-task-6/task.md))
- [ ] T013 Update generated release/ docs to explain preview, production, and mock/demo channels. ([Task 7](./tasks/plan-2-task-7/task.md))

## Plan 3: Cloudflare Preview Backend Readiness

- [ ] T014 Reuse Cloudflare doctor results as a hard gate for preview apply. ([Task 1](./tasks/plan-3-task-1/task.md))
- [ ] T015 Add preview apply enablement flag and blocked output when disabled. ([Task 2](./tasks/plan-3-task-2/task.md))
- [ ] T016 Provision or verify https://preview.nienfos.com/<app-slug>. ([Task 3](./tasks/plan-3-task-3/task.md))
- [ ] T017 Provision or select D1 database/scope for the generated app. ([Task 4](./tasks/plan-3-task-4/task.md))
- [ ] T018 Generate D1 migrations from generated domain entities. ([Task 5](./tasks/plan-3-task-5/task.md))
- [ ] T019 Apply D1 migrations idempotently. ([Task 6](./tasks/plan-3-task-6/task.md))
- [ ] T020 Seed only required preview bootstrap/admin data, not fake demo data. ([Task 7](./tasks/plan-3-task-7/task.md))
- [ ] T021 Verify preview API /health. ([Task 8](./tasks/plan-3-task-8/task.md))
- [ ] T022 Verify app/tenant scoping for D1 records. ([Task 9](./tasks/plan-3-task-9/task.md))
- [ ] T023 Add cost posture report before paid resources can be used. ([Task 10](./tasks/plan-3-task-10/task.md))
- [ ] T024 Add blocked status for paid-resource requirements without operator confirmation. ([Task 11](./tasks/plan-3-task-11/task.md))
- [ ] T086 Generate Cloudflare Preview API Worker routes for generated app contracts. ([Task 12](./tasks/plan-3-task-12/task.md))
- [ ] T087 Generate D1 schema and data access layer for preview auth, sessions, app updates, and domain records. ([Task 13](./tasks/plan-3-task-13/task.md))
- [ ] T088 Implement preview bootstrap and invite-to-admin flow for first usable login. ([Task 14](./tasks/plan-3-task-14/task.md))
- [ ] T089 Add local Worker harness and smoke tests for Preview API v1 endpoints. ([Task 15](./tasks/plan-3-task-15/task.md))
- [ ] T090 Verify deployed preview API routes before Android preview release can run. ([Task 16](./tasks/plan-3-task-16/task.md))

## Plan 4: Generated App Runtime Profile

- [ ] T025 Generate APP_RUNTIME_PROFILE=preview support for Flutter web and Android. ([Task 1](./tasks/plan-4-task-1/task.md))
- [ ] T026 Generate API_RUNTIME=cloudflare_preview support. ([Task 2](./tasks/plan-4-task-2/task.md))
- [ ] T027 Generate preview API_BASE_URL using the stable preview app route. ([Task 3](./tasks/plan-4-task-3/task.md))
- [ ] T028 Generate APP_SLUG runtime define. ([Task 4](./tasks/plan-4-task-4/task.md))
- [ ] T029 Route preview API clients through Preview API v1. ([Task 5](./tasks/plan-4-task-5/task.md))
- [ ] T030 Keep FastAPI real/staging clients separate from preview clients. ([Task 6](./tasks/plan-4-task-6/task.md))
- [ ] T031 Fail preview validation on localhost, example URLs, or missing preview API URL. ([Task 7](./tasks/plan-4-task-7/task.md))
- [ ] T032 Fail preview validation when mock/local seeded data is the primary runtime. ([Task 8](./tasks/plan-4-task-8/task.md))
- [ ] T033 Add generated Flutter tests for preview runtime selection. ([Task 9](./tasks/plan-4-task-9/task.md))

## Plan 5: Android Preview Release Workflow

- [ ] T034 Generate .github/workflows/android-preview-release.yml. ([Task 1](./tasks/plan-5-task-1/task.md))
- [ ] T035 Generate scripts/publish_android_preview_release.sh. ([Task 2](./tasks/plan-5-task-2/task.md))
- [ ] T036 Generate scripts/validate_preview_release_profiles.sh. ([Task 3](./tasks/plan-5-task-3/task.md))
- [ ] T037 Build preview APKs with preview runtime defines. ([Task 4](./tasks/plan-5-task-4/task.md))
- [ ] T038 Write release/preview-runtime.json. ([Task 5](./tasks/plan-5-task-5/task.md))
- [ ] T039 Publish GitHub releases with android-preview-v* tags. ([Task 6](./tasks/plan-5-task-6/task.md))
- [ ] T040 Verify APK asset presence and checksum. ([Task 7](./tasks/plan-5-task-7/task.md))
- [ ] T041 Verify app updater metadata points to the preview channel. ([Task 8](./tasks/plan-5-task-8/task.md))
- [ ] T042 Allow debug-preview signing only with explicit metadata. ([Task 9](./tasks/plan-5-task-9/task.md))
- [ ] T043 Keep android-v* productive signing gates unchanged. ([Task 10](./tasks/plan-5-task-10/task.md))
- [ ] T044 Add tests for preview release tag and metadata validation. ([Task 11](./tasks/plan-5-task-11/task.md))

## Plan 6: Bridge Installable-App Registration

- [ ] T045 Extend Bridge registration payload with release_channel=preview. ([Task 1](./tasks/plan-6-task-1/task.md))
- [ ] T046 Register display name as <App Name> Preview. ([Task 2](./tasks/plan-6-task-2/task.md))
- [ ] T047 Include preview URL in installable-app metadata. ([Task 3](./tasks/plan-6-task-3/task.md))
- [ ] T048 Include runtime profile, tag, APK asset, and update metadata. ([Task 4](./tasks/plan-6-task-4/task.md))
- [ ] T049 Include production_ready=false and mock_or_demo=false. ([Task 5](./tasks/plan-6-task-5/task.md))
- [ ] T050 Verify Bridge catalog lookup by source_app. ([Task 6](./tasks/plan-6-task-6/task.md))
- [ ] T051 Block with manual command when BRIDGE_URL is missing. ([Task 7](./tasks/plan-6-task-7/task.md))
- [ ] T052 Block with manual command when registration token is missing. ([Task 8](./tasks/plan-6-task-8/task.md))
- [ ] T053 Add tests for successful preview app registration. ([Task 9](./tasks/plan-6-task-9/task.md))
- [ ] T054 Add tests for blocked registration config. ([Task 10](./tasks/plan-6-task-10/task.md))

## Plan 7: Factory Runner Orchestration

- [ ] T055 Add initial_preview_release phase group to Factory jobs. ([Task 1](./tasks/plan-7-task-1/task.md))
- [ ] T056 Run local generated-project validation before preview publication. ([Task 2](./tasks/plan-7-task-2/task.md))
- [ ] T057 Run GitHub repository create/verify/push before preview release. ([Task 3](./tasks/plan-7-task-3/task.md))
- [ ] T058 Run Cloudflare preview apply after GitHub publication. ([Task 4](./tasks/plan-7-task-4/task.md))
- [ ] T059 Run web preview smoke tests after Cloudflare apply. ([Task 5](./tasks/plan-7-task-5/task.md))
- [ ] T060 Run Android preview release after preview API health passes. ([Task 6](./tasks/plan-7-task-6/task.md))
- [ ] T061 Run Bridge registration after APK asset verification. ([Task 7](./tasks/plan-7-task-7/task.md))
- [ ] T062 Run final readiness validation across GitHub, Cloudflare, Android, updater metadata, and Bridge. ([Task 8](./tasks/plan-7-task-8/task.md))
- [ ] T063 Persist per-phase status, logs, blockers, and manual next steps. ([Task 9](./tasks/plan-7-task-9/task.md))
- [ ] T064 Recover interrupted preview release jobs without duplicating resources. ([Task 10](./tasks/plan-7-task-10/task.md))

## Plan 8: Mobile And Workbench UX

- [ ] T065 Show Initial Preview Release status in Project Factory History. ([Task 1](./tasks/plan-8-task-1/task.md))
- [ ] T066 Add open/copy preview URL actions. ([Task 2](./tasks/plan-8-task-2/task.md))
- [ ] T067 Show Android preview APK install state through Apps catalog. ([Task 3](./tasks/plan-8-task-3/task.md))
- [ ] T068 Show release channel, tag, signing mode, and production readiness. ([Task 4](./tasks/plan-8-task-4/task.md))
- [ ] T069 Show production release as pending/not requested after preview success. ([Task 5](./tasks/plan-8-task-5/task.md))
- [ ] T070 Show exact blockers and manual commands for missing config. ([Task 6](./tasks/plan-8-task-6/task.md))
- [ ] T071 Add Workbench readiness fields for preview URL, APK, Bridge registration, and blockers. ([Task 7](./tasks/plan-8-task-7/task.md))

## Plan 9: Validation And Regression Coverage

- [ ] T072 Add regression test that first release defaults to preview. ([Task 1](./tasks/plan-9-task-1/task.md))
- [ ] T073 Add regression test that jobs cannot report ready without Cloudflare preview success. ([Task 2](./tasks/plan-9-task-2/task.md))
- [ ] T074 Add regression test that jobs cannot report ready without Bridge preview registration. ([Task 3](./tasks/plan-9-task-3/task.md))
- [ ] T075 Add validation test that preview APK points to preview API. ([Task 4](./tasks/plan-9-task-4/task.md))
- [ ] T076 Add validation test that preview APK does not use localhost, placeholder, or mock primary data paths. ([Task 5](./tasks/plan-9-task-5/task.md))
- [ ] T077 Add validation test that android-v* still requires production backend health and release signing. ([Task 6](./tasks/plan-9-task-6/task.md))
- [ ] T078 Add validation test that mock/demo releases stay visibly separate from preview releases. ([Task 7](./tasks/plan-9-task-7/task.md))

## Plan 10: Operations Documentation

- [ ] T079 Document Initial Preview Release required environment variables. ([Task 1](./tasks/plan-10-task-1/task.md))
- [ ] T080 Document Cloudflare apply, D1, Worker, DNS, and cost guardrails. ([Task 2](./tasks/plan-10-task-2/task.md))
- [ ] T081 Document Android preview signing policy. ([Task 3](./tasks/plan-10-task-3/task.md))
- [ ] T082 Document Bridge preview registration and manual fallback. ([Task 4](./tasks/plan-10-task-4/task.md))
- [ ] T083 Document preview update, disable, extend, and troubleshooting. ([Task 5](./tasks/plan-10-task-5/task.md))
- [ ] T084 Document promotion from preview to production. ([Task 6](./tasks/plan-10-task-6/task.md))
- [ ] T085 Update Project Factory runbooks with generic false-readiness failure examples. ([Task 7](./tasks/plan-10-task-7/task.md))
