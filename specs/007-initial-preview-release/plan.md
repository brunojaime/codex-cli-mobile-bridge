# Plan

## Phase 1: Release Mode Contract

Define the first-release state model before changing runner behavior.

- Add `preview` as the default New Project first-release mode.
- Define mutually exclusive `preview`, `real`, and `mock` release profiles.
- Define release tag prefixes and metadata for each profile.
- Define when a New Project job may report `ready`, `blocked`, or `failed`.
- Define the promotion path from preview to later production.

## Phase 2: Project Factory Contract Updates

Update Factory intake, generated metadata, and final reports so the expected
first release is explicit.

- Add first-release mode to draft/job schemas.
- Default the mode to `preview`.
- Preserve explicit opt-in choices for production and mock/demo.
- Update build-ready preview text to describe Cloudflare preview, Android APK,
  Bridge registration, cost posture, and production-not-ready status.
- Update job history payloads to include Initial Preview Release status.

## Phase 3: Cloudflare Preview Backend Readiness

Reuse Web Preview Delivery as the backend for initial releases.

- Require Cloudflare doctor checks before apply.
- Provision or update the stable preview URL.
- Provision or select D1 persistence for the app.
- Apply generated D1 migrations for domain entities.
- Verify preview API health.
- Verify tenant/app scoping.
- Report free-compatible cost posture and paid blockers before creating paid
  resources.

## Phase 4: Generated App Runtime Profile

Make generated Flutter apps able to run against preview from both web and
Android.

- Generate `APP_RUNTIME_PROFILE=preview`.
- Generate `API_RUNTIME=cloudflare_preview`.
- Generate preview `API_BASE_URL` and `APP_SLUG` defines.
- Route API clients through Preview API v1 in preview mode.
- Keep FastAPI production/staging clients separate.
- Prevent mock/local data paths from being compiled into preview releases as the
  primary runtime.

## Phase 5: Android Preview Release Workflow

Add a preview-specific Android release lane.

- Generate `android-preview-v*` tag workflow.
- Generate `scripts/publish_android_preview_release.sh`.
- Build APKs with preview runtime defines.
- Allow explicit debug-preview signing only when metadata says so.
- Keep productive release signing gates unchanged.
- Verify GitHub release assets and app updater metadata.

## Phase 6: Bridge Installable-App Registration

Register the preview APK as an installable app entry.

- Add preview channel metadata to the Bridge registration payload.
- Register display name as `<App Name> Preview`.
- Include preview URL, runtime profile, tag, APK asset, update metadata, and
  production readiness state.
- Verify Bridge catalog lookup by `source_app`.
- Block with a manual registration command when Bridge config is missing.

## Phase 7: Factory Runner Orchestration

Orchestrate the complete first-release pipeline.

- Run local validation.
- Publish/verify GitHub repository.
- Run Cloudflare preview apply.
- Run web preview smoke tests.
- Run Android preview release.
- Run Bridge registration.
- Run final readiness validation across all surfaces.
- Persist each phase status and interrupted recovery state.

## Phase 8: Mobile And Workbench UX

Expose the first-release result without making preview look like production.

- Show preview URL and open/copy actions.
- Show Android preview APK install action through Apps catalog.
- Show preview release channel, tag, signing mode, and expiration/disable state.
- Show production as pending/not requested until a later real release.
- Show blockers with exact missing configuration and commands.
- Add Workbench readiness fields for Initial Preview Release.

## Phase 9: Validation And Regression Coverage

Add tests that prevent historical false-readiness regressions and preview/production
mixups.

- Test first release defaults to preview.
- Test a job cannot become `ready` without Cloudflare preview and Bridge
  registration.
- Test missing Cloudflare config becomes `blocked`.
- Test missing Bridge config becomes `blocked`.
- Test preview APK metadata points to preview API, not production or localhost.
- Test productive tags still require production backend health and release
  signing.
- Test mock/demo tags stay visibly separate.

## Phase 10: Operations Documentation

Document how operators run and troubleshoot the new flow.

- Document required environment variables and secret ownership.
- Document Cloudflare setup and cost guardrail behavior.
- Document Android preview signing policy.
- Document Bridge registration and manual fallback.
- Document preview disable/extend/update operations.
- Document promotion from preview to production.

## Implementation Order

1. Contract and schemas.
2. Generated runtime metadata and validation.
3. Cloudflare readiness reuse from Web Preview Delivery.
4. Android preview release lane.
5. Bridge preview registration.
6. Runner orchestration.
7. Mobile/Workbench visibility.
8. End-to-end validation and docs.
