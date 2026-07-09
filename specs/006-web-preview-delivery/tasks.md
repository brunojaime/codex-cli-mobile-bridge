# Tasks

This file is the legacy task index. Task numbering is local to each plan in `tree.json`.

## Plan 1: Preview Contract And SDD Alignment

- [ ] T001 Add 006-web-preview-delivery SDD metadata and link it to Project Factory. ([Task 1](./tasks/plan-1-task-1/task.md))
- [ ] T002 Define Preview API v1 endpoint, payload, error, auth, pagination, and timestamp contract. ([Task 2](./tasks/plan-1-task-2/task.md))
- [ ] T003 Define web preview final job payload including stable URL, build id, invites, Cloudflare resources, validation, and blockers. ([Task 3](./tasks/plan-1-task-3/task.md))
- [ ] T004 Define stable URL rules for https://preview.nienfos.com/<app-slug>. ([Task 4](./tasks/plan-1-task-4/task.md))
- [ ] T005 Define preview lifecycle states: draft, provisioning, active, updating, expired, disabled, blocked, and failed. ([Task 5](./tasks/plan-1-task-5/task.md))
- [ ] T006 Define security and cost guardrail language for preview delivery. ([Task 6](./tasks/plan-1-task-6/task.md))

## Plan 2: Cloudflare Configuration And Client Boundary

- [x] T007 Add bridge-host Cloudflare settings for platform token, DNS token, account id, zone id, zone name, and preview base domain. ([Task 1](./tasks/plan-2-task-1/task.md))
- [x] T008 Add a Cloudflare doctor service that validates account, zone, token scopes, D1 access, Pages access, Worker access, DNS record access, and optional R2 access. ([Task 2](./tasks/plan-2-task-2/task.md))
- [x] T009 Add a side-effect-free Cloudflare provisioning planner. ([Task 3](./tasks/plan-2-task-3/task.md))
- [x] T010 Add Cloudflare DNS client support for read/create/update preview records. ([Task 4](./tasks/plan-2-task-4/task.md))
- [x] T011 Add Cloudflare Worker deployment client boundary. ([Task 5](./tasks/plan-2-task-5/task.md))
- [x] T012 Add D1 database/migration client boundary and tests with fake Cloudflare responses. ([Task 6](./tasks/plan-2-task-6/task.md))

## Plan 3: Preview Runtime Data Model

- [ ] T013 Define D1 migrations for preview apps, builds, tenants, users, sessions, roles, admin invites, notifications, domain entities, domain records, assets, and events. ([Task 1](./tasks/plan-3-task-1/task.md))
- [ ] T014 Add migration idempotency checks. ([Task 2](./tasks/plan-3-task-2/task.md))
- [ ] T015 Add app/tenant scoping constraints and indexes. ([Task 3](./tasks/plan-3-task-3/task.md))
- [ ] T016 Add password hash and invite token hash storage rules. ([Task 4](./tasks/plan-3-task-4/task.md))
- [ ] T017 Add preview expiration and disable state fields. ([Task 5](./tasks/plan-3-task-5/task.md))
- [ ] T018 Add audit event records for invite, login, preview publish, update, disable, and extend actions. ([Task 6](./tasks/plan-3-task-6/task.md))
- [ ] T019 Add D1 schema tests using local or mocked D1 execution. ([Task 7](./tasks/plan-3-task-7/task.md))

## Plan 4: Cloudflare Worker Preview Runtime

- [x] T020 Scaffold the shared Preview Worker runtime. ([Task 1](./tasks/plan-4-task-1/task.md))
- [x] T021 Implement app config resolution for preview.nienfos.com/<app-slug>. ([Task 2](./tasks/plan-4-task-2/task.md))
- [ ] T022 Implement auth login, logout, session refresh, and auth/me. ([Task 3](./tasks/plan-4-task-3/task.md))
- [ ] T023 Implement admin invite accept and first password setup. ([Task 4](./tasks/plan-4-task-4/task.md))
- [ ] T024 Implement admin users and roles APIs. ([Task 5](./tasks/plan-4-task-5/task.md))
- [ ] T025 Implement notification APIs. ([Task 6](./tasks/plan-4-task-6/task.md))
- [ ] T026 Implement generic domain CRUD APIs with app/tenant isolation. ([Task 7](./tasks/plan-4-task-7/task.md))
- [ ] T027 Implement preview disable and expiration enforcement. ([Task 8](./tasks/plan-4-task-8/task.md))

## Plan 5: Flutter Web Preview Adapter

- [x] T028 Add generated Flutter runtime config for APP_RUNTIME_PROFILE=preview. ([Task 1](./tasks/plan-5-task-1/task.md))
- [x] T029 Add generated Flutter API runtime selector for cloudflare_preview. ([Task 2](./tasks/plan-5-task-2/task.md))
- [ ] T030 Update generated Flutter API client to use Preview API v1 in preview mode. ([Task 3](./tasks/plan-5-task-3/task.md))
- [ ] T031 Add invite accept/password setup screen to the generated Flutter template. ([Task 4](./tasks/plan-5-task-4/task.md))
- [ ] T032 Add admin/user management screens to consume Preview API v1. ([Task 5](./tasks/plan-5-task-5/task.md))
- [ ] T033 Add Flutter tests for preview runtime config, invite accept, login, and admin routing. ([Task 6](./tasks/plan-5-task-6/task.md))

## Plan 6: Admin Invite And Email Delivery

- [ ] T034 Extend New Project chat intake prompt to ask for initial admin emails. ([Task 1](./tasks/plan-6-task-1/task.md))
- [ ] T035 Add fallback structured admin email field for non-chat flows. ([Task 2](./tasks/plan-6-task-2/task.md))
- [ ] T036 Add admin invite validation, deduplication, role selection, and expiration defaults. ([Task 3](./tasks/plan-6-task-3/task.md))
- [ ] T037 Add email provider abstraction and bridge-host provider settings. ([Task 4](./tasks/plan-6-task-4/task.md))
- [ ] T038 Add first provider implementation, with missing-provider blocked/manual-link behavior. ([Task 5](./tasks/plan-6-task-5/task.md))
- [ ] T039 Add resend, revoke, expire, and list invite operations. ([Task 6](./tasks/plan-6-task-6/task.md))
- [ ] T040 Add tests for token hashing, single-use behavior, expiry, resend, and manual invite fallback. ([Task 7](./tasks/plan-6-task-7/task.md))

## Plan 7: Project Factory Backend Integration

- [x] T041 Add Project Factory preview delivery schemas. ([Task 1](./tasks/plan-7-task-1/task.md))
- [ ] T042 Add preview delivery service that combines Cloudflare planning, Flutter web build metadata, Worker/D1 provisioning, DNS, and invite creation. ([Task 2](./tasks/plan-7-task-2/task.md))
- [ ] T043 Add preview delivery stage to Project Factory job runner after local validation. ([Task 3](./tasks/plan-7-task-3/task.md))
- [ ] T044 Persist preview metadata in draft/job state. ([Task 4](./tasks/plan-7-task-4/task.md))
- [x] T045 Add idempotent update behavior for existing app slugs and stable URLs. ([Task 5](./tasks/plan-7-task-5/task.md))
- [x] T046 Add preview history/status endpoints. ([Task 6](./tasks/plan-7-task-6/task.md))
- [ ] T047 Add interrupted preview job recovery behavior. ([Task 7](./tasks/plan-7-task-7/task.md))

## Plan 8: Mobile And Workbench UX

- [ ] T048 Update New Project kickoff prompt to require admin emails before build-ready marker. ([Task 1](./tasks/plan-8-task-1/task.md))
- [ ] T049 Update build-ready preview text to include admin emails, URL, expiration, and delivery assumptions. ([Task 2](./tasks/plan-8-task-2/task.md))
- [ ] T050 Add Project Factory history UI fields for web preview status, URL, build id, expiration, and invite status. ([Task 3](./tasks/plan-8-task-3/task.md))
- [ ] T051 Add UI actions to open/copy preview URL, resend invite, create invite, extend preview, and disable preview. ([Task 4](./tasks/plan-8-task-4/task.md))
- [ ] T052 Add Workbench release/readiness view fields for web preview status and blockers. ([Task 5](./tasks/plan-8-task-5/task.md))

## Plan 9: Validation And Contract Tests

- [ ] T053 Add Preview API v1 contract test suite. ([Task 1](./tasks/plan-9-task-1/task.md))
- [x] T054 Run contract tests against the Worker preview runtime. ([Task 2](./tasks/plan-9-task-2/task.md))
- [x] T055 Add Flutter web build validation for generated projects. ([Task 3](./tasks/plan-9-task-3/task.md))
- [ ] T056 Add preview URL smoke test. ([Task 4](./tasks/plan-9-task-4/task.md))
- [ ] T057 Add invite accept smoke test with a disposable test invite. ([Task 5](./tasks/plan-9-task-5/task.md))
- [ ] T058 Add no-secret scan coverage for Cloudflare, email, invite, and session secrets. ([Task 6](./tasks/plan-9-task-6/task.md))
- [ ] T059 Add cost posture validation for free-tier-compatible MVP previews. ([Task 7](./tasks/plan-9-task-7/task.md))

## Plan 10: Operations And Documentation

- [ ] T060 Document Cloudflare setup for nienfos.com, tokens, D1, Worker, Pages, DNS, and optional R2. ([Task 1](./tasks/plan-10-task-1/task.md))
- [ ] T061 Document AWS domain delegation and auto-renew requirements. ([Task 2](./tasks/plan-10-task-2/task.md))
- [ ] T062 Document email provider setup and sender-domain verification. ([Task 3](./tasks/plan-10-task-3/task.md))
- [ ] T063 Document preview lifecycle operations: publish, update, extend, disable, expire, resend invite, revoke invite. ([Task 4](./tasks/plan-10-task-4/task.md))
- [ ] T064 Document DNS propagation and Cloudflare activation troubleshooting. ([Task 5](./tasks/plan-10-task-5/task.md))
- [ ] T065 Document secret rotation and token scope expectations. ([Task 6](./tasks/plan-10-task-6/task.md))
- [ ] T066 Update Project Factory operational docs and generated-project readiness docs. ([Task 7](./tasks/plan-10-task-7/task.md))
- [ ] T067 Document that Web Preview Delivery is additive and does not replace GitHub publication, Android APK release, updater metadata, or Bridge installable-app registration. ([Task 8](./tasks/plan-10-task-8/task.md))
- [ ] T068 Add regression tests proving generated release scripts, Android workflow, updater endpoint, release metadata, and installable-app registration remain present after preview delivery integration. ([Task 9](./tasks/plan-10-task-9/task.md))
