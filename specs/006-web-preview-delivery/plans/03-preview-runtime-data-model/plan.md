# Preview Runtime Data Model

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
