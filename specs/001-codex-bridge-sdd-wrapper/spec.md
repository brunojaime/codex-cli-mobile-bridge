# Codex Bridge SDD Wrapper

## Intent

Codex Mobile Bridge projects must expose a mandatory SDD structure that can be
read by the backend and surfaced by the frontend when `CODEX_BRIDGE_DEV_MODE`
is enabled.

## Acceptance Criteria

- The repo contains the required SDD contract files.
- The backend exposes read-only SDD endpoints.
- SDD file reads are path-safe and extension-limited.
- The frontend has exactly one public compile-time flag for wrapper visibility.
- The normal app UI is unchanged when `CODEX_BRIDGE_DEV_MODE=false`.
