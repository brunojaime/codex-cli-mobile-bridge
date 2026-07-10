# Project Factory Preview Hardening

id: 015-project-factory-preview-hardening
status: planned
owner: codex-mobile-bridge

## Intent

Capture the SAT Showroom Initial Preview Release lessons as a reusable Project
Factory contract so future generated apps do not repeat the same preview,
invite, Workbench, Cloudflare cache, or email-delivery failures.

This spec complements:

- `005-new-project-factory`
- `006-web-preview-delivery`
- `007-initial-preview-release`
- `011-new-project-guided-intake`
- `014-project-factory-frontend-strategy`
- `002-sdd-visual-workbench`

## Product Outcome

When a New Project Factory build produces an Initial Preview Release, the user
gets a stable public preview that works from a mobile browser, can activate
admin invites without manual token pasting, can re-enter after logout with a
normal login, shows only product-domain navigation inside the generated app,
and reports email invite delivery truthfully.

Generated apps must still provide:

- `https://preview.nienfos.com/{slug}` web preview;
- `https://preview.nienfos.com/{slug}/api` real Preview API;
- Cloudflare D1 persistence;
- Android preview APK for Flutter projects;
- Bridge app registration when the selected frontend strategy supports it;
- production blocked until explicit promotion;
- no mock/demo data unless the user explicitly requested a mock/demo release.

## Lessons Learned

SAT Showroom exposed these generator and runtime gaps:

- Flutter web preview can show a blank page when Cloudflare Assets SPA fallback
  or cache behavior bypasses the Worker route that should set preview access.
- Non-hashed Flutter boot assets such as `flutter_bootstrap.js` and
  `main.dart.js` can remain stale unless preview cache headers prevent reuse.
- Flutter web runtime dependencies can be blocked by CSP if CanvasKit and font
  origins are not allowed or self-hosted.
- PWA manifest and icon requests must not fail solely because the browser has
  not yet established preview access.
- Invite URLs already carry the token, so the first-access UI should not ask a
  user to paste "Invite token or link".
- `/api/invites/accept` must remain single-use, but a used invite may still
  grant preview access until expiration or revocation.
- Logout and re-entry must use normal email/password login rather than invite
  acceptance.
- Bridge Workbench and SDD surfaces are development tooling, not product
  domain features. Generated product apps must not show a `Workbench` tab or
  route inside their customer/admin navigation.
- Email invite delivery cannot be reported as sent when the Bridge is in manual
  mode or a provider fails. Manual links remain a fallback, not a fake success.
- The preferred future email provider is Cloudflare Email Service or a
  Cloudflare-backed SMTP/API provider for `preview@nienfos.com` or
  `invites@nienfos.com`.
- Cloudflare deploy tooling must update existing module Workers reliably and
  validate route behavior after deploy.

## Core Rules

- Generated product navigation may include only product-domain surfaces.
- Bridge Workbench must be Bridge-owned development UI, presented through a
  Bridge/Codex entry point or external overlay, not as a generated app tab.
- Generated project SDD files, manifests, and Workbench metadata remain
  available to the Bridge Workbench.
- Invite links carry the token in the URL. First-access UI must auto-read the
  token and hide token mechanics from normal users.
- First access shows a concise account activation form:
  `Email`, `Create password`, `Repeat password`, and `Activate account`.
- If the invite metadata binds an email, the email field should be prefilled
  and locked or clearly fixed.
- Re-entry after logout uses normal login with email/password.
- `/api/invites/accept` is single-use for account activation.
- Preview access may still be refreshed from a used invite link while the link
  is unexpired and not revoked.
- Preview access cookies and app auth sessions are separate.
- Web preview routing and asset delivery must not bypass Worker access logic.
- Preview SPA fallback belongs in the Worker when access rules are required.
- Do not configure Cloudflare Assets
  `not_found_handling = "single-page-application"` for protected previews.
- `index.html`, `flutter_bootstrap.js`, `main.dart.js`, `manifest.json`, and
  invite/access routes must be no-cache/no-store in preview.
- Content-hashed assets may be immutable only when the filename is content
  hashed.
- PWA manifest and icon assets may be public-safe, but API and protected app
  data remain access controlled.
- CSP must support Flutter web runtime dependencies or the generated app must
  self-host those dependencies.
- Email provider state must distinguish delivered, failed, skipped/manual, and
  pending.
- Missing email provider credentials must produce manual-link fallback, not a
  sent email claim.
- Production release remains out of scope for Initial Preview Release.

## Invite UX Contract

Generated preview auth must support these states:

- `invite_activation`: URL includes an invite token that has not been accepted.
  The UI shows account activation fields and no token input.
- `invite_access_refresh`: URL includes a used but valid preview invite. The
  runtime refreshes preview access and directs the user to normal login.
- `login`: user enters email/password after logout or after an already accepted
  invite.
- `expired_or_revoked`: user sees a clear message that a new preview link is
  required.

Manual fallback links can still be copied by an operator, but the user-facing
link must contain the token in the URL and should open the correct state
directly.

## Workbench Boundary Contract

Generated apps may include development metadata, SDD files, and Bridge
registration references, but they must not include:

- bottom navigation item labeled `Workbench`;
- product route named `Workbench`;
- app-domain RBAC permission that grants Bridge Workbench UI;
- user-facing feature copy that describes Workbench as part of the product.

Bridge may expose Workbench for the generated project through:

- Codex Mobile Bridge project/workspace screen;
- a dev-only overlay or external launcher branded as Codex/Bridge;
- the same visual convention used by Codex CLI Mobile Bridge, including the
  Codex "C" identity when available.

## Cloudflare Preview Contract

The generated Worker and deploy service must:

- use ES module Worker syntax for D1, Assets, and Fetch handlers;
- update existing preview Workers rather than silently skipping script updates;
- own route dispatch for `/api`, invite/access routes, health routes, static
  assets, and SPA fallback;
- validate deployed route behavior after every apply;
- serve JS/CSS/assets with correct MIME types;
- protect the app shell/API as configured while allowing public-safe manifest
  and icon assets;
- avoid route alias sprawl as a workaround for stale cache;
- purge or version preview cache as an explicit deploy step when needed.

## Cloudflare Email Contract

The target provider is Cloudflare-backed email delivery for invite messages.
Implementation must support a provider mode named `cloudflare_email` or a more
specific Cloudflare transport name once the exact Cloudflare service is chosen.

Provider configuration must include:

- sender address such as `preview@nienfos.com` or `invites@nienfos.com`;
- token or API credentials stored outside source control;
- endpoint or SMTP host/port/security mode;
- delivery status and provider message ID when available;
- secret redaction in logs and SDD output.

If SMTP is used through Cloudflare, implicit TLS on port `465` must use an
SMTP_SSL-compatible client. If a REST API is used, the provider must expose the
same internal delivery result contract.

Manual-link fallback remains required and must be surfaced whenever provider
configuration is missing or delivery fails.

## Validation Requirements

Validation must fail when:

- a generated product app contains a `Workbench` product tab or route;
- Bridge Workbench cannot discover generated SDD/spec/plan/task artifacts;
- an invite URL opens a screen requiring manual token paste;
- first activation does not require password confirmation;
- a used invite can be accepted twice;
- a used but valid invite cannot refresh preview access;
- logout cannot re-enter via normal login;
- web preview renders a blank page in Chrome/Android browser smoke tests;
- Flutter web JS or bootstrap assets are cached stale in preview;
- CSP blocks Flutter web runtime dependencies;
- manifest/icon requests break first load;
- Cloudflare deploy reports success without updating and verifying the Worker;
- email delivery reports sent while in manual mode or after provider failure;
- production or user-installable releases contain mock/demo data without an
  explicit mock/demo request.

## Acceptance Criteria

- AC-001: New Project Factory generated apps no longer expose Workbench as
  product-domain navigation.
- AC-002: Bridge Workbench still opens generated project SDD and release
  artifacts through a Bridge-owned development entry point.
- AC-003: First invite links auto-consume URL tokens and show activation fields
  without a token/link input.
- AC-004: Logout and re-entry work through normal email/password login.
- AC-005: Used invites cannot be re-accepted but can refresh preview access
  while valid.
- AC-006: Cloudflare preview routing, cache headers, CSP, manifest/icons, and
  Worker updates are validated against a deployed preview.
- AC-007: Cloudflare email provider support is specified and implemented with
  truthful delivery status plus manual-link fallback.
- AC-008: The Initial Preview Release gate includes regression checks for the
  SAT Showroom failures.
