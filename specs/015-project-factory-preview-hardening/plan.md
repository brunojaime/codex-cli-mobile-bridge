# Project Factory Preview Hardening Plan

## Plan 1: Workbench Boundary And Generated App UX

Separate Bridge development tooling from generated product application UI.

- Audit generated Flutter and Svelte navigation templates for Workbench tabs,
  routes, labels, and RBAC permissions.
- Define a Bridge-owned Workbench launch contract for generated workspaces.
- Keep SDD/spec/plan/task artifacts discoverable from Codex Mobile Bridge.
- Add generator tests proving product apps do not expose Bridge Workbench as a
  product feature.

## Plan 2: Invite URL And First Access UX

Replace manual token paste with URL-driven invite activation and normal login
re-entry.

- Auto-read invite token from URL/query/path state.
- Hide token mechanics in normal first-access UI.
- Show account activation form with email, create password, repeat password,
  and activate action.
- Keep invite acceptance single-use.
- Allow valid used invite links to refresh preview access and route to login.
- Separate preview access cookie from app auth session.
- Test expired, revoked, used, and first-use invite states.

## Plan 3: Cloudflare Worker, Assets, Routing, Cache

Harden generated preview Workers and deploy behavior so browser preview cannot
blank due route or cache issues.

- Generate ES module Workers compatible with D1, Assets, and Fetch.
- Make the Worker own protected SPA fallback after access checks.
- Remove protected preview dependence on Cloudflare Assets SPA fallback.
- Apply no-cache/no-store headers for preview shell and non-hashed Flutter
  boot assets.
- Keep hashed assets immutable only when content-hashed.
- Validate MIME types, CSP, manifest/icon accessibility, route behavior, and
  preview cookies in local and deployed smoke tests.
- Update existing Workers reliably and verify the deployed version.

## Plan 4: Email Delivery Via Cloudflare

Add a real Cloudflare-backed invite email provider without losing manual-link
fallback.

- Define the provider contract and configuration surface.
- Support sender addresses under the verified domain, such as
  `preview@nienfos.com` or `invites@nienfos.com`.
- Store credentials outside source control and redact secrets in logs.
- Support delivery status: delivered, failed, pending, skipped/manual.
- Include operator runbook items for SPF, DKIM, DMARC, sender permissions,
  token scope, and provider diagnostics.
- Keep manual fallback links visible and accurate.

## Plan 5: Generator Contracts And Regression Coverage

Bake the hardening into Project Factory output and release validation.

- Update generator templates, release manifests, docs, and reviewer checklists.
- Add SAT Showroom regression fixture or golden generated project checks.
- Validate Flutter and Svelte strategy behavior where applicable.
- Add health/smoke/browser/APK/Bridge checks to the Initial Preview Release
  gate.
- Record validation evidence in SDD traceability.

## Plan 6: Initial Preview Release Reproducibility Gate

Make every generated Flutter + FastAPI + Cloudflare Preview release use one
real-data, repeatable path from secrets loading through final validation.

- Generate one official Bridge env/secrets loader and use it from D1,
  Wrangler, smoke, invite, Android release, Bridge registration, and final
  validation scripts.
- Require `APP_RUNTIME_PROFILE=preview`, `API_RUNTIME=cloudflare_preview`, and
  `API_BASE_URL=https://preview.nienfos.com/{slug}/api` for Initial Preview
  Release.
- Verify both `/{slug}/__preview/health` and `/{slug}/api/health` after deploy
  and require `d1_bound=true` plus `assets_bound=true`.
- Keep business app API URLs on Cloudflare Preview and Bridge dev-tool URLs on
  Tailscale Bridge variables.
- Fail preflight early with clear missing-variable diagnostics.

## Plan 7: Schema Evolution, Android Signing, And Final Audit

Remove one-off release fixes by generating durable migrations, signing, release
metadata, and audit checks.

- Support idempotent D1 schema evolution with column checks, repeatable
  add-column migrations, and backfills that Bridge and shell scripts both
  understand.
- Require stable Android preview signing and verify APK signer metadata before
  Bridge registration.
- Use stable release metadata fields:
  `validated_source_commit`, `android_tag_commit`,
  `report_generated_from_commit`, and optional `release_report_commit`.
- Generate final readiness audit checks for stale TODO/blocker language, old
  release tags, generic endpoints, ambiguous commit hashes, and mock/demo
  leakage in real preview releases.
