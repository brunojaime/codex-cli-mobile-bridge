# T087 Generate D1 schema and data access layer for preview auth, sessions, app updates, and domain records

Spec: `007-initial-preview-release`

Plan: `Cloudflare Preview Backend Readiness`

## Checklist

- [ ] Generate app-scoped D1 tables for preview users, sessions, app-update
      metadata, notifications, and generated domain records.
- [ ] Generate Worker-side D1 query helpers and migrations that are idempotent
      and safe for a shared preview database.
