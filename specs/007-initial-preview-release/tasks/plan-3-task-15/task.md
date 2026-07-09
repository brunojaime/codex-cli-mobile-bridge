# T089 Add local Worker harness and smoke tests for Preview API v1 endpoints

Spec: `007-initial-preview-release`

Plan: `Cloudflare Preview Backend Readiness`

## Checklist

- [ ] Extend the local Worker harness to exercise `/<app-slug>/api/health`,
      auth/session, representative domain CRUD, notifications, and app-update
      endpoints against fake D1.
- [ ] Assert persistence, app scoping, and no static-asset fallback for API
      requests.
