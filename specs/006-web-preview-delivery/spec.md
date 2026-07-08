---
id: 006-web-preview-delivery
title: Web Preview Delivery Platform
status: draft
type: feature
domains:
  - project-factory
  - web-preview
  - cloudflare
  - admin-invites
  - release-readiness
---

# Web Preview Delivery Platform

## Intent

New Project Factory must finish with a usable web preview, not just generated
files. A generated project is considered shareable only when the Factory can
publish a stable web URL, provision the required Cloudflare preview resources,
create one or more initial admin invitations, and verify that an invited admin
can reach the app and complete first login.

The first delivery target is web only. App Store and Play Store distribution are
out of scope for this spec. This does not replace the existing generated-project
release contract: GitHub repository publication, Android release workflows,
app-updater metadata, Bridge installable-app registration, and release-readiness
validation must remain intact.

## Product Outcome

For every generated project, the user should be able to give a client something
like:

```text
URL: https://preview.nienfos.com/clinica-norte
Admin invite: sent to admin@example.com
Expires: 7 days
```

The public URL must remain stable across redeploys. Internal deployments may
change, but the client-facing URL must not change when the Factory publishes a
new build for the same project.

## Current Infrastructure Assumptions

- `nienfos.com` is registered in AWS and delegated to Cloudflare nameservers.
- Cloudflare zone `nienfos.com` is active.
- The bridge host has Cloudflare platform and DNS API tokens stored outside git.
- The preview base domain is `preview.nienfos.com`.
- Route 53 is not used for runtime DNS after delegation to Cloudflare.
- R2 may require a one-time dashboard enablement before asset storage is used.

The implementation must not assume those local secrets exist in generated
projects. It must read bridge-host deployment configuration from environment or
operator-owned secret files.

## Scope

- Cloudflare provisioning for the preview platform.
- Stable preview URL generation.
- Flutter Web build publication.
- Cloudflare Worker preview runtime.
- D1-backed tenant, app, user, session, role, invite, build, and preview state.
- Optional R2-backed asset storage when enabled.
- Admin invite collection during Project Factory intake.
- Admin invite email generation and delivery through a provider abstraction.
- First-login password setup for invited admins.
- Preview lifecycle controls: publish, update, disable, expire, extend, resend.
- Contract tests proving the generated Flutter app works against Preview API v1.
- Factory job output that reports preview URL, invite status, build id,
  expiration, validation results, and blockers.

## Non-Goals

- Do not implement App Store or Play Store delivery.
- Do not remove or weaken the existing Android/GitHub release, updater,
  installable-app, or generated release-readiness flows.
- Do not create one VPS, FastAPI process, database, or container stack per app.
- Do not make Cloudflare previews the final production backend for every future
  product.
- Do not send plaintext permanent passwords by email.
- Do not store Cloudflare, email, or invite signing secrets in generated repos.
- Do not require R2 for the first text-only preview if no persistent assets are
  needed.
- Do not make a mock/demo release appear as a real production release.

## Architecture Principle

The preview platform is shared. Generated apps are tenants.

```text
Generated Flutter Web app
  -> stable preview URL
  -> Cloudflare Worker Preview Runtime
  -> D1 tenant/app data
  -> R2 assets when enabled
```

The Factory must not publish a separate backend server per app. It may still
generate a FastAPI backend for future production paths, but the first shareable
web preview must run on the shared Cloudflare preview runtime.

## Stable URL Contract

The first supported client-facing URL format is:

```text
https://preview.nienfos.com/<app-slug>
```

Examples:

```text
https://preview.nienfos.com/clinica-norte
https://preview.nienfos.com/ropa-sur
```

The app slug is normalized by the Project Factory manifest service. Once a
preview URL is created for a project, redeploys update the active build behind
that URL rather than issuing a different client-facing URL.

Future support for per-app subdomains is allowed:

```text
https://clinica-norte.preview.nienfos.com
```

but it is not the first implementation target.

## Preview API v1 Contract

Flutter Web must depend on a stable Preview API v1 contract rather than on
FastAPI-specific behavior. FastAPI and Cloudflare Worker may both implement the
same contract, but the preview delivery path is Worker-backed.

Minimum endpoint families:

```text
GET  /health
GET  /apps/{app_slug}/config
POST /auth/login
POST /auth/logout
GET  /auth/me
POST /admin-invites/accept
POST /admin-invites/password
GET  /admin/users
POST /admin/users
GET  /admin/roles
GET  /notifications
PATCH /notifications/{id}
GET  /app-updates/current
GET  /domain/{entity}
POST /domain/{entity}
PATCH /domain/{entity}/{id}
DELETE /domain/{entity}/{id}
```

The contract must define request and response shapes, error envelopes, auth
token behavior, role checks, pagination, timestamp format, and tenant scoping.

## Tenant And Data Model

The Worker/D1 preview runtime owns these logical records:

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

Every user, session, invite, domain record, notification, and asset must be
scoped to an app or tenant. Cross-app data reads are validation failures.

## Admin Invite Contract

Project Factory intake must collect one or more initial admin emails before web
preview publication. The user may provide them in chat mode or through a
fallback structured field.

Each invite is:

- tied to exactly one app;
- tied to exactly one email;
- tied to a role, defaulting to `admin` unless `owner` is explicitly selected;
- single-use by default;
- expiring, with a default of seven days;
- stored as a token hash, never as a plaintext token;
- auditable through preview events.

Invite URL shape:

```text
https://preview.nienfos.com/<app-slug>/admin-invite?t=<token>
```

First accept flow:

1. User opens the invite URL.
2. Worker validates app, token hash, expiry, and use state.
3. UI shows the invited email and asks the user to create a password.
4. Worker hashes the password, creates or activates the admin user, marks the
   invite used, creates a session, and redirects into the app.
5. The invite URL cannot be used again.

If a client needs five admins, the Factory creates five distinct invite tokens.
One shared admin link for several people is not allowed.

## Email Delivery Contract

The platform must use an email provider abstraction. The first provider may be
Resend, Brevo, SendGrid, or another provider configured through bridge-host
secrets.

Email delivery must be optional at generation time. If no provider is
configured, the Factory must still create invite records and return manual
invite links as a visible blocker:

```text
email_status: blocked_missing_provider
manual_next_step: Configure EMAIL_PROVIDER and EMAIL_API_KEY or copy invite links manually.
```

No generated project may contain the provider API key.

## Cloudflare Provisioning Contract

The bridge-host Factory provisioning layer must manage:

- Cloudflare account and zone discovery from env/secrets.
- DNS record creation for `preview.nienfos.com` when needed.
- Worker script deployment.
- D1 database creation or lookup.
- D1 migrations.
- Pages project creation or static artifact upload strategy.
- R2 bucket creation or lookup when asset storage is enabled.
- Secret binding for Worker runtime.
- Idempotent re-run behavior.

Provisioning must be safe to run more than once. Existing resources are reused
when their names and metadata match the expected project/platform contract.
Unexpected resources are reported as blockers instead of overwritten.

## Factory Job Contract

Project Factory generation must add a web preview stage after local project
validation and before reporting the generated app as shareable. This stage is
additive: it must not skip, delete, replace, or downgrade the existing release
stages that create/verify GitHub publication, release metadata, Android APK
workflows, updater endpoints, and Bridge installable-app registration.

The final job payload must include:

```yaml
web_preview:
  status: active | blocked | failed | skipped
  stable_url: https://preview.nienfos.com/<app-slug>
  app_slug: <app-slug>
  active_build_id: <build-id>
  expires_at: <iso8601>
  admin_invites:
    - email: admin@example.com
      role: admin
      status: sent | created | failed | used | expired
      expires_at: <iso8601>
  cloudflare:
    zone_name: nienfos.com
    worker_name: <worker-name>
    d1_database: <database-name>
    pages_project: <project-name>
    r2_bucket: <bucket-name-or-null>
  validation:
    flutter_web_build: pass | fail | skipped
    worker_health: pass | fail | skipped
    invite_accept_smoke: pass | fail | skipped
    preview_url_smoke: pass | fail | skipped
  blockers: []
```

## Mobile/Workbench UX Contract

The New Project chat intake must ask for admin invite emails before the build
marker is emitted. The prompt must explain that these users will become initial
admins for the generated app preview.

The UI must expose preview status and recovery actions:

- open preview URL;
- copy preview URL;
- resend invite;
- create another admin invite;
- extend preview;
- disable preview;
- view build id and validation status.

The old modal/fallback flow may include an optional admin email field, but the
primary path remains chat-first.

## Relationship To Existing Release Flow

Generated projects must continue to include:

- `.github/workflows/android-release.yml`;
- `scripts/publish_project.sh`;
- `scripts/finalize_local_commit.sh`;
- `scripts/validate_publication_ready.sh`;
- `scripts/validate_release_profiles.sh`;
- `scripts/register_installable_app.sh`;
- backend `/app-updates/current`;
- release metadata and release readiness docs;
- Bridge installable-app registration through protected Bridge endpoints after
  an APK release exists.

Web Preview Delivery adds a faster client trial path. It must not be treated as
evidence that the installable/mobile release path is complete. Final job output
must report both surfaces separately:

```yaml
release:
  github_publish: complete | blocked | failed
  android_release: complete | blocked | failed | not_requested
  installable_app_registration: complete | blocked | failed | not_ready
web_preview:
  status: active | blocked | failed | skipped
```

## Security Requirements

- Store invite tokens as hashes.
- Generate high-entropy invite tokens.
- Expire invites by default after seven days.
- Expire previews by default after a configurable period.
- Require app/tenant scoping on every Worker API request.
- Restrict CORS to preview hosts.
- Do not expose Worker/D1/R2 credentials to generated projects.
- Do not commit secrets.
- Do not log plaintext tokens or passwords.
- Allow preview disablement even if generated app code is broken.
- Support credential rotation for Cloudflare and email provider secrets.

## Cost Requirements

The default MVP path must fit Cloudflare free tiers for low-volume previews.
The Factory must report estimated cost posture:

```text
cloudflare_plan: free-compatible
route53_hosted_zone_required: false
email_provider_free_tier_expected: true
paid_blockers: []
```

If a preview requires paid features or exceeds known free-tier assumptions, the
job must report the reason before provisioning paid resources.

## Acceptance Criteria

- AC-001: A generated project can be published to a stable web preview URL under
  `preview.nienfos.com/<app-slug>`.
- AC-002: Redeploying the same project updates the active build without changing
  the client-facing URL.
- AC-003: The Factory intake captures one or more initial admin emails before
  build confirmation.
- AC-004: Each initial admin receives or can be given a unique single-use invite
  link.
- AC-005: Accepting an invite creates an admin user, sets a password, starts a
  session, and invalidates the invite.
- AC-006: The Worker preview runtime enforces app/tenant isolation for every
  user, session, invite, notification, domain record, and asset.
- AC-007: Flutter Web works against Preview API v1 without depending on
  FastAPI-specific behavior.
- AC-008: Contract tests run against the Worker preview runtime and fail on API
  shape drift.
- AC-009: The Factory final report includes stable URL, build id, invite status,
  expiration, Cloudflare resources, validation results, and blockers.
- AC-010: Missing Cloudflare, DNS, R2, or email provider configuration creates a
  clear blocked status with exact manual next steps.
- AC-011: Secrets remain outside generated repos and are never written to
  committed files.
- AC-012: Preview disable and expiration prevent further authenticated use while
  leaving an operator-readable status.
- AC-013: The MVP path does not require a paid server per generated app.
- AC-014: R2 is optional until persistent asset storage is required.
- AC-015: Workbench surfaces preview status as part of the generated project's
  release/readiness state.
- AC-016: Existing release artifacts, Android workflow, updater metadata,
  publication validation, and installable-app registration remain present and
  validated after Web Preview Delivery is added.
