# T088 Implement preview bootstrap and invite-to-admin flow for first usable login

Spec: `007-initial-preview-release`

Plan: `Cloudflare Preview Backend Readiness`

## Checklist

- [x] Provide a first-login path for preview admins through invite/bootstrap
      state, without exposing mock role selectors or seeded demo accounts.
- [x] Persist bootstrap/admin state in D1 and include blocked output when the
      invite secret or bootstrap configuration is missing.
