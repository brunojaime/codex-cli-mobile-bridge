# Plan

## Phase 1: Preview Contract And SDD Alignment

Define the Web Preview Delivery contract before implementation.

- Add Preview API v1 contract documents.
- Define web preview final job payload shape.
- Define stable URL and app slug rules.
- Define admin invite request/response schemas.
- Define preview lifecycle states.
- Define cost, security, and blocker reporting language.
- Extend New Project Factory spec references so generated projects are not
  considered shareable until web preview delivery succeeds or is explicitly
  blocked with manual next steps.
- Preserve the existing generated-project release contract. Web Preview
  Delivery is additive and must not replace GitHub publication, Android APK
  workflows, app-updater metadata, release validation, or Bridge installable-app
  registration.

## Phase 2: Cloudflare Configuration And Client Boundary

Create a bridge-host Cloudflare integration boundary that reads operator-owned
configuration and never depends on generated project secrets.

Expected configuration:

```text
CLOUDFLARE_API_TOKEN
CLOUDFLARE_DNS_API_TOKEN
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_ZONE_ID
CLOUDFLARE_ZONE_NAME=nienfos.com
PREVIEW_BASE_DOMAIN=preview.nienfos.com
```

The service should support:

- account lookup;
- zone lookup;
- DNS record create/update/read for preview records;
- Worker script deploy;
- D1 database create/lookup;
- D1 migration execution;
- Pages project/artifact publication;
- R2 bucket create/lookup when enabled;
- safe dry-run output.

## Phase 3: Preview Runtime Data Model

Design and implement D1 migrations for the shared preview platform.

Core tables:

```text
preview_apps
preview_builds
preview_tenants
preview_users
preview_sessions
preview_roles
preview_admin_invites
preview_notifications
preview_domain_entities
preview_domain_records
preview_assets
preview_events
```

All records must include app or tenant scoping. Tests must prove cross-app reads
are rejected.

## Phase 4: Cloudflare Worker Preview Runtime

Build the Worker runtime that serves Preview API v1.

The Worker owns:

- app config resolution from URL path;
- auth and session handling;
- invite accept and password setup;
- admin user/role APIs;
- notification APIs;
- generic domain CRUD APIs;
- app update metadata;
- preview disable/expiration enforcement;
- CORS for preview hosts.

The Worker must be deployable independently from any generated app.

## Phase 5: Flutter Web Preview Adapter

Update generated Flutter templates so the web build can run against the shared
preview runtime.

Generated app config must support:

```text
APP_RUNTIME_PROFILE=preview
API_RUNTIME=cloudflare_preview
API_BASE_URL=https://preview.nienfos.com
APP_SLUG=<app-slug>
```

The Flutter API client must use Preview API v1 for preview mode and must not
call FastAPI-only endpoints in the preview path.

## Phase 6: Admin Invite And Email Delivery

Add the invite workflow end to end.

- Collect admin emails during chat-first New Project intake.
- Validate email syntax and duplicate emails.
- Generate one invite per email.
- Store token hashes, never plaintext tokens.
- Send email through a provider abstraction.
- Return manual invite links when the provider is missing.
- Mark invites as sent, failed, used, expired, or revoked.
- Add resend and revoke operations.

## Phase 7: Project Factory Backend Integration

Extend Project Factory services and APIs.

- Add preview delivery request/response schemas.
- Add preview provisioning stage to the job runner.
- Add preview status and history payloads.
- Add recovery behavior for interrupted preview jobs.
- Add idempotent update behavior for existing app slugs.
- Add blockers for missing Cloudflare or email configuration.
- Persist preview metadata with drafts/jobs.
- Keep existing release job phases and generated release artifacts intact.
- Report release status and web preview status independently.

## Phase 8: Mobile And Workbench UX

Expose the workflow without making the user manage infrastructure details.

Mobile app changes:

- New Project chat kickoff asks for one or more initial admin emails.
- Build-ready preview includes admin emails, preview URL, expiration, and
  delivery assumptions.
- Project Factory history shows preview status.
- User can open/copy preview URL.
- User can resend invites, create another invite, extend preview, or disable
  preview.

Workbench changes:

- Show preview readiness in release/readiness surfaces.
- Surface preview blockers with exact next actions.
- Link preview delivery status to generated project SDD metadata.

## Phase 9: Validation And Contract Tests

Add validation layers that fail before a broken preview is reported as ready.

Required checks:

- Cloudflare configuration doctor.
- DNS record lookup for `preview.nienfos.com`.
- D1 migration validation.
- Worker health check.
- Flutter web build.
- Preview URL smoke test.
- Invite accept smoke test using a test invite.
- Contract tests for Preview API v1.
- No-secret scan for generated repos.
- Cost posture report.
- Regression checks that generated release scripts, Android workflow, updater
  endpoint, release metadata, and installable-app registration scripts are still
  generated and validated.

## Phase 10: Operations And Documentation

Document and support operating the preview platform.

- Setup guide for Cloudflare, AWS domain delegation, and email provider.
- Token scope documentation.
- R2 enablement note.
- Preview lifecycle runbook.
- Invite troubleshooting runbook.
- DNS propagation troubleshooting.
- Secret rotation runbook.
- Cost guardrail documentation.

## Implementation Order

1. Contract and docs first.
2. Cloudflare doctor/client second.
3. Worker runtime and D1 third.
4. Flutter preview adapter fourth.
5. Factory job integration fifth.
6. Mobile/Workbench UX sixth.
7. End-to-end validation last.

This keeps infrastructure validation and contract tests ahead of user-facing
claims that previews are ready.
