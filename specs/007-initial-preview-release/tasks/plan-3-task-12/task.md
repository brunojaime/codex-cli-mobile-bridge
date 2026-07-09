# T086 Generate Cloudflare Preview API Worker routes for generated app contracts

Spec: `007-initial-preview-release`

Plan: `Cloudflare Preview Backend Readiness`

## Checklist

- [x] Generate Worker routes under `/<app-slug>/api` for the API surface required
      by generated Flutter clients: health, app config, auth/session, admin
      basics, catalog/domain CRUD, notifications, and app updates.
- [x] Ensure the generated routes are app-scoped and do not fall back to static
      asset handling or mock/local data.
