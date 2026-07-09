# Cloudflare Preview Backend Readiness

Reuse Web Preview Delivery as the backend for initial releases.

- Require Cloudflare doctor checks before apply.
- Provision or update the stable preview URL.
- Provision or select D1 persistence for the app.
- Apply generated D1 migrations for domain entities.
- Generate the Preview API Worker routes required by the generated Flutter app.
- Generate app-scoped D1 schema and query helpers for auth, sessions, app
  updates, notifications, and domain records.
- Add preview bootstrap/admin login flow without demo role selectors.
- Test Preview API endpoints locally with a Worker/D1 harness.
- Verify preview API health.
- Verify tenant/app scoping.
- Verify deployed Preview API routes before any Android preview release runs.
- Report free-compatible cost posture and paid blockers before creating paid
  resources.
