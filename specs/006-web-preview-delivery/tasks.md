# Tasks

## Phase 1: Preview Contract And SDD Alignment

- [ ] T001 Add `006-web-preview-delivery` SDD metadata and link it to Project Factory.
- [ ] T002 Define Preview API v1 endpoint, payload, error, auth, pagination, and timestamp contract.
- [ ] T003 Define web preview final job payload including stable URL, build id, invites, Cloudflare resources, validation, and blockers.
- [ ] T004 Define stable URL rules for `https://preview.nienfos.com/<app-slug>`.
- [ ] T005 Define preview lifecycle states: draft, provisioning, active, updating, expired, disabled, blocked, and failed.
- [ ] T006 Define security and cost guardrail language for preview delivery.

## Phase 2: Cloudflare Configuration And Client Boundary

- [x] T007 Add bridge-host Cloudflare settings for platform token, DNS token, account id, zone id, zone name, and preview base domain.
- [x] T008 Add a Cloudflare doctor service that validates account, zone, token scopes, D1 access, Pages access, Worker access, DNS record access, and optional R2 access.
- [x] T009 Add a side-effect-free Cloudflare provisioning planner.
- [x] T010 Add Cloudflare DNS client support for read/create/update preview records.
- [x] T011 Add Cloudflare Worker deployment client boundary.
- [x] T012 Add D1 database/migration client boundary and tests with fake Cloudflare responses.

## Phase 3: Preview Runtime Data Model

- [ ] T013 Define D1 migrations for preview apps, builds, tenants, users, sessions, roles, admin invites, notifications, domain entities, domain records, assets, and events.
- [ ] T014 Add migration idempotency checks.
- [ ] T015 Add app/tenant scoping constraints and indexes.
- [ ] T016 Add password hash and invite token hash storage rules.
- [ ] T017 Add preview expiration and disable state fields.
- [ ] T018 Add audit event records for invite, login, preview publish, update, disable, and extend actions.
- [ ] T019 Add D1 schema tests using local or mocked D1 execution.

## Phase 4: Cloudflare Worker Preview Runtime

- [x] T020 Scaffold the shared Preview Worker runtime.
- [ ] T021 Implement app config resolution for `preview.nienfos.com/<app-slug>`.
- [ ] T022 Implement auth login, logout, session refresh, and `auth/me`.
- [ ] T023 Implement admin invite accept and first password setup.
- [ ] T024 Implement admin users and roles APIs.
- [ ] T025 Implement notification APIs.
- [ ] T026 Implement generic domain CRUD APIs with app/tenant isolation.
- [ ] T027 Implement preview disable and expiration enforcement.

## Phase 5: Flutter Web Preview Adapter

- [x] T028 Add generated Flutter runtime config for `APP_RUNTIME_PROFILE=preview`.
- [x] T029 Add generated Flutter API runtime selector for `cloudflare_preview`.
- [ ] T030 Update generated Flutter API client to use Preview API v1 in preview mode.
- [ ] T031 Add invite accept/password setup screen to the generated Flutter template.
- [ ] T032 Add admin/user management screens to consume Preview API v1.
- [ ] T033 Add Flutter tests for preview runtime config, invite accept, login, and admin routing.

## Phase 6: Admin Invite And Email Delivery

- [ ] T034 Extend New Project chat intake prompt to ask for initial admin emails.
- [ ] T035 Add fallback structured admin email field for non-chat flows.
- [ ] T036 Add admin invite validation, deduplication, role selection, and expiration defaults.
- [ ] T037 Add email provider abstraction and bridge-host provider settings.
- [ ] T038 Add first provider implementation, with missing-provider blocked/manual-link behavior.
- [ ] T039 Add resend, revoke, expire, and list invite operations.
- [ ] T040 Add tests for token hashing, single-use behavior, expiry, resend, and manual invite fallback.

## Phase 7: Project Factory Backend Integration

- [x] T041 Add Project Factory preview delivery schemas.
- [ ] T042 Add preview delivery service that combines Cloudflare planning, Flutter web build metadata, Worker/D1 provisioning, DNS, and invite creation.
- [ ] T043 Add preview delivery stage to Project Factory job runner after local validation.
- [ ] T044 Persist preview metadata in draft/job state.
- [x] T045 Add idempotent update behavior for existing app slugs and stable URLs.
- [x] T046 Add preview history/status endpoints.
- [ ] T047 Add interrupted preview job recovery behavior.

## Phase 8: Mobile And Workbench UX

- [ ] T048 Update New Project kickoff prompt to require admin emails before build-ready marker.
- [ ] T049 Update build-ready preview text to include admin emails, URL, expiration, and delivery assumptions.
- [ ] T050 Add Project Factory history UI fields for web preview status, URL, build id, expiration, and invite status.
- [ ] T051 Add UI actions to open/copy preview URL, resend invite, create invite, extend preview, and disable preview.
- [ ] T052 Add Workbench release/readiness view fields for web preview status and blockers.

## Phase 9: Validation And Contract Tests

- [ ] T053 Add Preview API v1 contract test suite.
- [ ] T054 Run contract tests against the Worker preview runtime.
- [x] T055 Add Flutter web build validation for generated projects.
- [ ] T056 Add preview URL smoke test.
- [ ] T057 Add invite accept smoke test with a disposable test invite.
- [ ] T058 Add no-secret scan coverage for Cloudflare, email, invite, and session secrets.
- [ ] T059 Add cost posture validation for free-tier-compatible MVP previews.

## Phase 10: Operations And Documentation

- [ ] T060 Document Cloudflare setup for `nienfos.com`, tokens, D1, Worker, Pages, DNS, and optional R2.
- [ ] T061 Document AWS domain delegation and auto-renew requirements.
- [ ] T062 Document email provider setup and sender-domain verification.
- [ ] T063 Document preview lifecycle operations: publish, update, extend, disable, expire, resend invite, revoke invite.
- [ ] T064 Document DNS propagation and Cloudflare activation troubleshooting.
- [ ] T065 Document secret rotation and token scope expectations.
- [ ] T066 Update Project Factory operational docs and generated-project readiness docs.
- [ ] T067 Document that Web Preview Delivery is additive and does not replace GitHub publication, Android APK release, updater metadata, or Bridge installable-app registration.
- [ ] T068 Add regression tests proving generated release scripts, Android workflow, updater endpoint, release metadata, and installable-app registration remain present after preview delivery integration.
