# Cloudflare Preview Backend Readiness

Reuse Web Preview Delivery as the backend for initial releases.

- Require Cloudflare doctor checks before apply.
- Provision or update the stable preview URL.
- Provision or select D1 persistence for the app.
- Apply generated D1 migrations for domain entities.
- Verify preview API health.
- Verify tenant/app scoping.
- Report free-compatible cost posture and paid blockers before creating paid
  resources.
