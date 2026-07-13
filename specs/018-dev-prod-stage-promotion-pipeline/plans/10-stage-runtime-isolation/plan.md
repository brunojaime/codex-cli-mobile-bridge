# Stage Runtime Isolation Plan

## Goal

Make every DEV stage own its backend process, port, data directory, logs, PID,
environment file, and health state so restarting one spec backend never affects
other active DEV specs.

## Scope

- Stage runtime schema.
- Deterministic port allocation.
- Per-stage backend lifecycle commands.
- Chat-to-stage backend routing.
- Frontend runtime status display.
- Tests proving process isolation.

## Tasks

- T055 Define stage runtime schema for backend URL, port, data dir, logs dir, PID file, env file, health, and restart policy.
- T056 Implement deterministic per-stage port allocation with collision detection and stable reuse.
- T057 Implement stage backend lifecycle commands for start, stop, restart, status, healthcheck, and log lookup.
- T058 Bind DEV chat API calls and worker actions to the stage backend URL instead of a shared DEV backend.
- T059 Render per-chat stage backend status, port, health, and last restart in the DEV frontend.
- T060 Add tests proving restart/failure of one stage backend does not affect another stage backend or chat.

## Acceptance Criteria

- A stage can start its own backend from its registered worktree.
- Restarting one stage backend leaves other stage backends and chats available.
- Port, data, logs, PID, and env paths are deterministic and recorded in the
  Stage Registry.
- Chat actions route to the backend URL registered for that chat's stage.
- Stage runtime lifecycle commands cannot operate outside the registered stage.

## Validation

- Backend tests for port allocation, lifecycle state, healthcheck, and path
  safety.
- Integration tests with two active stages and two backend processes.
- Frontend tests for per-chat backend status display.

