# Codex Developer Feedback Template

Reusable Flutter package for the Codex developer feedback overlay, Bridge-backed
feedback actions, background app update checks, and the optional developer role
gate.

## Role Gate

`CodexDeveloperRoleGate` provides optional login screens before the app body.
It is disabled by default and must be enabled explicitly. To show the gate's
username/password login, set:

```text
--dart-define=CODEX_FEEDBACK_ROLE_AUTH_ENABLED=true
```

The package ships with one generic admin credential so every app can opt in
without implementing its own temporary auth shell:

```text
CODEX_FEEDBACK_ADMIN_ROLE_ID=admin
CODEX_FEEDBACK_ADMIN_ROLE_LABEL=Administrador
CODEX_FEEDBACK_ADMIN_USERNAME=admin
CODEX_FEEDBACK_ADMIN_PASSWORD=admin
```

Internal builds can show direct admin role entry, without username/password, by
setting:

```text
--dart-define=CODEX_FEEDBACK_ADMIN_ROLE_LOGIN_ENABLED=true
```

When `CODEX_FEEDBACK_ADMIN_ROLE_LOGIN_ENABLED` is false or absent, the direct
admin role selector is hidden. When both role login and credential login are
false or absent, the role gate does not block the app body and the app's
classic login appears.

Apps can override those values at build time with their own `--dart-define`
values. The role gate also accepts explicit `roles` and `credentials` lists when
an app needs a richer role model. Do not use role login as a production security
boundary; it is a reusable developer/admin entry point for internal builds.

## Updater And Bridge

Apps should always mount `DeveloperFeedbackTemplate` or
`CodexDeveloperFeedbackTemplate` and pass feature flags through `enabled:`. The
template owns background update checks, so hiding the feedback toolbar must not
remove the template from the widget tree.

When `CODEX_FEEDBACK_BRIDGE_URL` is empty, the template can fall back to the
updater Bridge URL through `appUpdaterBridgeUrl`. Bridge-backed actions remain
visible and show a clear unavailable-Bridge dialog if no usable URL exists.
