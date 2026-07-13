# Dev Prod Stage Promotion Pipeline

Spec: `018-dev-prod-stage-promotion-pipeline`

## Operating Rules

PROD is the stable daily-work lane. Normal PROD sessions may chat and enqueue a
DEV handoff only through the narrow handoff endpoint. They must not write Bridge
code, run shell commands, restart services, deploy releases, read DEV worktrees,
or start DEV agents.

DEV is the isolated implementation lane. Each DEV chat must be bound to one
stage, one spec, one branch, one worktree, and one stage backend URL. A stage
restart may affect only that registered stage runtime.

The control plane stores immutable handoffs, backlog locks, stage records,
session bindings, merge queue records, promotion evidence, release-channel
validation, and PROD backend update gate state. It is not a code worktree.

## Environment Identity

The backend exposes the active lane through `/health` as
`environment_identity`. Mobile clients render this identity independently from
the existing `CODEX DEV` developer wrapper signal.

Important fields:

- `environment`: `prod`, `dev`, or `control`.
- `stage_id`, `spec_id`, `branch`, `worktree_path`: present for DEV stages.
- `backend_url`: the source of truth for the current backend.
- `app_channel`, `app_label`, `updater_channel`, `color`: release-channel UI
  and updater identity.
- `allowed_capabilities` and `denied_capabilities`: deterministic permission
  contract for tools and UI.

## PROD Handoff

Enable with `DEV_PIPELINE_PROD_HANDOFF_ENABLED=true` only when PROD should show
the explicit handoff action.

Endpoint:

```text
POST /dev-pipeline/handoffs
```

The payload must use:

```yaml
kind: bridge.devHandoff
source_environment: prod
target_environment: dev
operation: enqueue_only
```

The endpoint accepts an `X-Idempotency-Key` header. Reusing the key returns the
same immutable handoff and prevents duplicate backlog items.

Normal PROD cannot read `/dev-pipeline` snapshots and cannot call stage,
session, lifecycle, merge, promotion, update, or release-channel mutation
endpoints. `/dev-pipeline/identity` and `/dev-pipeline/permissions` expose only
the current PROD identity and minimal PROD permission modes.

## Endpoint Access Matrix

- PROD: `GET /health`, `GET /dev-pipeline/identity`,
  `GET /dev-pipeline/permissions`, `POST /dev-pipeline/handoffs` when
  `DEV_PIPELINE_PROD_HANDOFF_ENABLED=true`, and PROD update status/acknowledge
  views where allowed by the update gate.
- DEV: backlog claim/materialize, stage registry, stage session binding, stage
  runs, stage lifecycle, merge queue, projection, and backfill dry-run.
- CONTROL: promotion request/status/advance, release-channel validation,
  projection, backfill dry-run, and PROD update prepare/force/acknowledge.
- PROD normal is blocked from DEV internals: backlog, stages, sessions, runs,
  merge queue, promotions, release validation, backfill, and projection.

## DEV Backlog And Stages

Run DEV workers only with `BRIDGE_ENVIRONMENT=dev`.

Claim the next handoff:

```text
POST /dev-pipeline/backlog/claim
```

Register or reuse a stage:

```text
POST /dev-pipeline/stages
```

The default stage branch and port are deterministic. For
`018-dev-prod-stage-promotion-pipeline`, the stage is `spec-018`, the branch is
`dev/spec-018-dev-prod-stage-promotion-pipeline`, and the backend port is `8118`.

Bind a chat session:

```text
POST /dev-pipeline/sessions/bind
```

The backend rejects mismatched branches and worktree paths.

Stage lifecycle:

```text
POST /dev-pipeline/stages/{stage_id}/lifecycle
```

Use `apply=false` to inspect the exact deterministic command. Use `apply=true`
only from a DEV stage runtime when a stage backend should actually be started,
stopped, or restarted. Stage lifecycle writes `.env.stage` under the registered
stage runtime root and uses stage-specific `API_PORT`, `API_BASE_URL`, data dir,
logs dir, and PID file. Do not use this for the live PROD backend.

Known lifecycle limitation: start, stop, restart, status, and logs are covered;
`healthcheck` is also covered and performs a short `/health` request against
the registered stage backend URL. It updates `runtime.health` and
`runtime.last_healthcheck_at` without restarting anything.

Stage run controls:

```text
POST /dev-pipeline/stage-runs/{run_id}/pause
POST /dev-pipeline/stage-runs/{run_id}/resume
```

Pause/resume are explicit control states because MessageService has no real
pause primitive. They record `pause_requested` and `resume_requested` with
blocker reasons instead of pretending to suspend a running process.

Reviewer evidence for stage runs must be structured JSON:

```json
{"status":"continue","prompt":"Add missing validation."}
{"status":"complete","summary":"All acceptance criteria pass."}
```

`complete` synthesizes final run summary evidence. Invalid JSON is persisted as
a reviewer contract blocker.

## Merge And Promotion

Queue merge preflight:

```text
POST /dev-pipeline/merge-queue
```

The merge gate blocks missing worktrees, dirty stage trees, inactive stages, and
unapproved stages.

Merge apply runs an allowlisted inline SDD doctor dry-run before updating
`dev/main`. Failed SDD doctor output is persisted in merge evidence and blocks
the merge without partial integration.

Promotion is disabled unless `DEV_PIPELINE_PROMOTION_ENABLED=true`.

```text
POST /dev-pipeline/promotions
```

Promotion fails closed unless the user approved the promotion, the PROD drain
status is quiescent, the repository is clean, and the release tag is a PROD
`android-v*` tag.

Promotion, PROD update, and release-channel validation endpoints require
`BRIDGE_ENVIRONMENT=control`.

## Release Channels

Validate DEV and PROD release identities:

```text
POST /dev-pipeline/release-channels/validate
```

Channel contract:

- PROD: `channel=prod`, `BRIDGE_APP_CHANNEL=prod`,
  `BRIDGE_UPDATER_CHANNEL=prod`, source app `codex-mobile`, Android package
  `com.example.codex_mobile_frontend`, app label `Codex Mobile Bridge`, real
  `API_BASE_URL`, non-local app update registry/public URL, and release tags
  matching `android-v*`.
- DEV: `channel=dev`, `BRIDGE_APP_CHANNEL=dev`,
  `BRIDGE_UPDATER_CHANNEL=dev`, source app `codex-mobile-dev`, Android package
  `com.example.codex_mobile_frontend.dev`, a visible DEV app label/badge, a
  DEV stage/backend URL, visible stage/branch identity, and release tags
  matching `android-dev-v*`.

Release builds must use real backend configuration and real data paths. PROD
API URLs containing `localhost`, `127.0.0.1`, `0.0.0.0`, `mock`, `demo`, or
`local` markers are rejected outside DEV. Mock/demo APKs require an explicit
user request and must be named as such in version scope, release tag, and final
report.

Before publishing Android artifacts, run the dry-run channel validator:

```text
.venv/bin/python scripts/validate_android_release_channel.py \
  --channel prod \
  --api-base-url http://batata-default-string.tail0302c4.ts.net \
  --app-label "Codex Mobile Bridge" \
  --updater-channel prod \
  --environment-color "#55D6BE" \
  --release-tag android-vX.Y.Z-build.N
```

The validator reads `frontend/mobile_app/pubspec.yaml` and the app update
registry, reports `ok/blockers/evidence`, and never creates tags, invokes
GitHub, publishes APKs, or deploys a backend.

Promotion dry-runs include release-channel validation evidence and fail closed
when PROD channel validation fails. A dry-run may reach `rollback_ready`, but it
must not mark backend deploy or APK publication as completed. Real release
publishing still requires a separate explicit operator instruction.

## PROD Backend Update Gate

Check update state:

```text
POST /dev-pipeline/prod-update/status
```

The gate reports `waiting_for_idle` while active jobs, active sessions, or
in-flight messages exist. It reports `auto_update_eligible` only when the
existing backend drain detector says restart is safe. Forced updates require a
strong confirmation action and must record interruption evidence before a real
restart is attempted.

Real restart/update execution is allowlisted and additionally gated by
`DEV_PIPELINE_PROD_UPDATE_EXECUTOR_ENABLED`. With the flag disabled, the gate
records planned/eligible evidence and does not restart PROD.

## Operator Runbook

Rollout flags:

- `DEV_PIPELINE_ENABLED=true` enables the state machine endpoints.
- `DEV_PIPELINE_PROD_HANDOFF_ENABLED=true` enables the narrow PROD handoff
  action.
- `DEV_PIPELINE_PROMOTION_ENABLED=true` enables control-plane promotion
  planning and dry-runs.
- `DEV_PIPELINE_PROD_UPDATE_EXECUTOR_ENABLED=true` is required before any
  allowlisted PROD update executor can run. Leave it disabled for dry-run
  validation.

Nominal flow:

1. PROD enqueues a handoff with `POST /dev-pipeline/handoffs`.
2. DEV claims it with `POST /dev-pipeline/backlog/claim`.
3. DEV materializes it with
   `POST /dev-pipeline/backlog/{handoff_id}/materialize`.
4. DEV creates or binds a stage chat session with
   `POST /dev-pipeline/stages/{stage_id}/sessions`.
5. DEV starts a stage run with
   `POST /dev-pipeline/stages/{stage_id}/runs/start`.
6. DEV queues and applies a merge into `dev/main` through
   `/dev-pipeline/merge-queue`.
7. CONTROL validates release channels and runs promotion dry-run with
   `/dev-pipeline/release-channels/validate` and `/dev-pipeline/promotions`.
8. CONTROL prepares the PROD backend update gate with
   `/dev-pipeline/prod-update/prepare`.

Visibility:

- DEV and CONTROL can read `/dev-pipeline/projection`.
- PROD normal is blocked from `/dev-pipeline` and
  `/dev-pipeline/projection`; it can read only identity, permissions, health,
  and the explicit handoff result.
- Projection filters: `stage_id`, `spec_id`, `handoff_id`, and `status`.
- The `workbench` section summarizes backlog items, materialized specs,
  blocked imports, active stages, stage runs, merge status, and promotion
  status. `events` preserves recent audit trail entries.

Backfill dry-run:

```text
POST /dev-pipeline/backfill/stages
```

Use `{ "dry_run": true }` to inspect existing `specs/NNN-*` directories,
expected branches, and expected worktrees without writing state. Blockers such
as `missing_branch`, `dirty_worktree`, `incompatible_worktree`, and
`worktree_branch_mismatch` must be remediated before converting a legacy spec
into a managed stage/backlog candidate. Spec 017 should appear as a candidate
when `specs/017-*` exists.

Recovery:

- Blocked materialization: inspect `partial_artifacts` and blocker reason in
  backlog/projection. Retry only after fixing the recorded artifact mismatch or
  removing artifacts created by the failed operation.
- Blocked merge: inspect merge `blockers`, `stderr/stdout`, source/target SHAs,
  and `partial_artifacts`. Resolve stale branches, dirty worktrees, conflicts,
  or validation failures, then queue/apply a fresh merge.
- Blocked promotion: inspect `evidence.release_config`, `evidence.drain`,
  `evidence.merge`, `planned_commands`, and `next_required_action`. Promotion
  dry-run must not be treated as a deployed backend or published APK.
- Blocked update: inspect `quiescence`, `blockers`, and `action_history`.
  Forced update requires strong confirmation and records interrupted work plus
  recovery plan evidence.

DEV APK and PROD APK:

- DEV APKs use the DEV app label/badge, updater channel `dev`, DEV/stage
  backend URL, source app `codex-mobile-dev`, package suffix `.dev`, and DEV
  tag pattern `android-dev-v*`. GitHub Actions publishes DEV releases as
  prereleases with assets `codex-mobile-dev.apk` and
  `codex-mobile-dev-<version>.apk`.
- PROD/user-installable APKs use the PROD app label, updater channel `prod`,
  source app `codex-mobile`, package `com.example.codex_mobile_frontend`, real
  `API_BASE_URL`, real update registry/public URL, and tag pattern
  `android-v*`. GitHub Actions publishes PROD releases with assets
  `codex-mobile.apk` and `codex-mobile-<version>.apk`.
- Both DEV and PROD release workflows fail closed if Android signing secrets are
  missing, if the API URL points to localhost/mock/demo/local placeholders, or
  if the built APK metadata does not match the expected package, variant, and
  output file.
- Local release builds for smoke testing may pass
  `-Pcodex.allowDebugReleaseSigning=true`, but those outputs are explicitly
  non-publishable and are not accepted by the GitHub release workflow.
- Do not publish mock/demo/local release builds as PROD. If a demo APK is
  explicitly requested, label the version, tag, and final report as demo/mock.

Publishing commands:

```text
scripts/publish_android_release.sh --channel prod --push
scripts/publish_android_release.sh --channel dev --push
```

Required GitHub Actions variables:

- `API_BASE_URL`: real PROD Bridge URL for `android-v*`.
- `DEV_API_BASE_URL`: real DEV/stage Bridge URL for `android-dev-v*`.

DEV APK backend on `8118`:

The DEV APK published from `android-dev-v*` points at
`http://batata-default-string.tail0302c4.ts.net:8118` with source app
`codex-mobile-dev` and updater channel `dev`. Use the repo script below to
bring up or recover that backend without touching the PROD backend on `8000`:

```text
scripts/dev_backend_8118.sh start
scripts/dev_backend_8118.sh status
scripts/dev_backend_8118.sh restart
scripts/dev_backend_8118.sh stop
```

The script is idempotent. It uses isolated runtime files under
`.run/dev-backend-8118/`, including:

- `.run/dev-backend-8118/backend.pid`
- `.run/dev-backend-8118/backend.log`
- `.run/dev-backend-8118/dev.env`
- `.run/dev-backend-8118/data/`
- `.run/dev-backend-8118/runtime/`

Verification:

```text
curl -fsS http://127.0.0.1:8118/health | jq '.environment_identity'
tailscale --socket=/home/batata/.local/share/tailscale-userspace/tailscaled.sock serve status
curl -fsSI 'http://127.0.0.1:8118/app-updates/codex-mobile-dev/apk/android-dev-v1.0.0-build.105/codex-mobile-dev.apk?platform=android&channel=dev'
```

Expected Tailscale Serve mapping:

```text
http://batata-default-string.tail0302c4.ts.net:8118
|-- proxy http://127.0.0.1:8118
```

Persistence limitation: this is a repo-local process launcher, not a systemd
service. After a host reboot, run `scripts/dev_backend_8118.sh start` again, or
install a separate systemd unit that executes that command. `status` returns
non-zero if the DEV backend, DEV health identity, or Tailscale Serve mapping is
missing.

## Implementation Evidence

Validation commands executed during closeout:

```text
.venv/bin/python -m ruff check backend/app/application/services/dev_pipeline_service.py backend/app/api/routes.py backend/app/api/schemas.py backend/app/application/services/message_service.py backend/app/container.py backend/app/infrastructure/config/settings.py scripts/backend_process_lib.sh scripts/run_backend_detached.sh scripts/stop_backend.sh scripts/validate_android_release_channel.py tests/test_dev_pipeline.py tests/test_backend_process_scripts.py tests/test_android_release_channel_validation.py tests/test_message_flow.py
.venv/bin/pytest tests/test_dev_pipeline.py tests/test_backend_process_scripts.py tests/test_android_release_channel_validation.py -q
.venv/bin/pytest tests/test_dev_pipeline.py tests/test_message_flow.py -k 'dev_pipeline or prod_update or backend_drain or follow_up or stage_run or reviewer' -q
.venv/bin/python scripts/validate_android_release_channel.py --channel prod --api-base-url https://bridge.example.invalid --app-label "Codex Mobile Bridge" --updater-channel prod --environment-color "#55D6BE" --release-tag android-v1.2.3 --pubspec frontend/mobile_app/pubspec.yaml --app-updates-registry backend/app/infrastructure/config/app_updates.json
.venv/bin/python scripts/validate_android_release_channel.py --channel dev --api-base-url http://batata-default-string.tail0302c4.ts.net:8118 --app-label "Codex Mobile Bridge DEV" --updater-channel dev --environment-color "#38BDF8" --release-tag android-dev-v1.2.3 --pubspec frontend/mobile_app/pubspec.yaml --app-updates-registry backend/app/infrastructure/config/app_updates.json
flutter test test/api_client_test.dart test/dev_handoff_dialog_test.dart test/environment_identity_badge_test.dart test/prod_update_banner_test.dart test/slash_command_model_test.dart test/slash_command_palette_test.dart test/new_project_factory_dialog_test.dart
flutter analyze lib/src/models/server_health.dart lib/src/models/dev_pipeline_handoff.dart lib/src/models/prod_update_status.dart lib/src/models/slash_command.dart lib/src/models/project_factory.dart lib/src/services/api_client.dart lib/src/screens/chat_screen.dart test/api_client_test.dart test/dev_handoff_dialog_test.dart test/environment_identity_badge_test.dart test/prod_update_banner_test.dart test/slash_command_model_test.dart test/slash_command_palette_test.dart test/new_project_factory_dialog_test.dart
.venv/bin/python scripts/codex_bridge_sdd_doctor.py --workspace . --projects-root .. --json
```

Flag-gated or dry-run-only behavior:

- PROD handoff UI/API requires `DEV_PIPELINE_PROD_HANDOFF_ENABLED=true`.
- Promotion requires `DEV_PIPELINE_PROMOTION_ENABLED=true` and remains dry-run;
  it records planned allowlisted commands but does not publish a release.
- PROD backend update execution requires
  `DEV_PIPELINE_PROD_UPDATE_EXECUTOR_ENABLED=true`; disabled mode records
  `auto_update_eligible` or blockers without restart.
- Backfill is dry-run only and does not create backlog/stage state.

Not executed during the dry-run implementation closeout:

- No PROD backend restart.
- No backend deploy.
- No APK publishing.
- No GitHub release creation.
- No real production update executor.
