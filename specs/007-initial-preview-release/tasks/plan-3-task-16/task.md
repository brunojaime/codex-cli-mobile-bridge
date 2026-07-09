# T090 Verify deployed preview API routes before Android preview release can run

Spec: `007-initial-preview-release`

Plan: `Cloudflare Preview Backend Readiness`

## Checklist

- [ ] Gate Android preview release on deployed Preview API checks for health,
      authentication, representative persistence, app updates, and app-scope
      isolation.
- [ ] Return `blocked` with concrete diagnostics when any deployed Preview API
      route is missing or returns static preview content instead of API JSON.
