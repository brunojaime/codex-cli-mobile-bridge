# Dev Prod Stage And Deterministic Promotion Pipeline Tasks

- [x] T001 Define environment identity schema for PROD, DEV, control plane, stage, channel, backend URL, app label, and allowed capabilities.
- [x] T002 Define deterministic permission matrix for PROD normal mode, PROD slash mode, DEV stage mode, DEV integration mode, and PROD promotion mode.
- [x] T003 Add backend environment identity source and health payload fields used by frontend and tools.
- [x] T004 Enforce PROD normal-mode denial for Bridge code writes, shell commands, restarts, deploys, and DEV workspace reads.
- [x] T005 Add tests proving PROD normal sessions cannot access DEV/backlog/promotion context or mutation capabilities.
- [x] T006 Document environment isolation rules in operator-facing docs without injecting them into normal PROD agent context.
- [x] T007 Define PROD slash/action contract for temporary DEV handoff context loading.
- [x] T008 Implement queue payload schema, validation, immutability, idempotency keys, and source/target environment checks.
- [x] T009 Add backend endpoint/tool for enqueue-only DEV handoffs with no file-write or command permissions.
- [x] T010 Add frontend slash/action UI that enters temporary plan/handoff mode and exits after enqueue.
- [x] T011 Add tests that slash mode can enqueue but cannot edit files, run commands, restart services, or launch DEV agents.
- [x] T012 Add handoff audit records with source session, selected context, created item id, and redacted evidence.
- [x] T013 Define DEV backlog item states, claim semantics, locks, retries, cancellation, and terminal states.
- [x] T014 Implement DEV worker claim/import flow that materializes queued handoffs only in DEV workspaces.
- [x] T015 Implement spec attachment rules for existing spec versus new spec creation.
- [x] T016 Store delivery/runtime state outside `metadata.status` while keeping SDD lifecycle compatible.
- [x] T017 Add Workbench/Kanban visibility for backlog items, materialized specs, blocked imports, and active stages.
- [x] T018 Add tests for duplicate handoffs, claim races, blocked materialization, and delivery-state projection.
- [x] T019 Define Stage Registry schema for spec id, stage id, branch, worktree, base branch, backend URL, app channel, status, and ownership.
- [x] T020 Implement deterministic branch and worktree creation/reuse for one spec per stage.
- [x] T021 Bind every DEV chat/session to exactly one stage worktree and branch through backend-owned session metadata.
- [x] T022 Add backend guards that reject DEV stage actions when `workspace_path`, branch, or worktree do not match the registry.
- [x] T023 Render DEV chat header with environment, spec, branch, worktree label, and backend URL source.
- [x] T024 Add tests for parallel spec 017/spec 018 stages, branch mismatch rejection, and chat-stage continuity.
- [x] T025 Define DEV stage AgentConfiguration presets for Generator/Reviewer pairs and optional Summary completion.
- [x] T026 Reuse MessageService auto-chain for Generator -> Reviewer -> Generator loops inside the registered stage chat.
- [x] T027 Add Reviewer completion JSON contract and final summary synthesis for DEV stage runs.
- [x] T028 Persist run evidence, changed files, tests, risks, user validation checklist, and reviewer completion state.
- [x] T029 Add DEV worker controls for start, pause, cancel, retry, and resume stage agent runs.
- [x] T030 Add tests for reviewer continue, reviewer complete, failed follow-up recovery, and final summary output.
- [x] T031 Define serialized merge queue schema for stage branch to `dev/main` integration.
- [x] T032 Implement merge preflight for clean worktree, approved spec state, completed reviewer, required tests, and fresh base.
- [x] T033 Implement deterministic rebase/merge attempt with conflict capture and no partial integration on failure.
- [x] T034 Run integration validation after merge and record commit, test evidence, SDD doctor output, and blockers.
- [x] T035 Add user-visible merge status and conflict remediation instructions in DEV Workbench.
- [x] T036 Add tests for successful merge, stale branch, conflict, dirty tree, failed validation, and serialized queue behavior.
- [x] T037 Define Promotion Orchestrator state machine for `dev/main` to PROD with preflight, validation, approval, drain, deploy, release, post-validation, notify, blocked, failed, and rollback states.
- [x] T038 Wrap existing Android release, GitHub Actions release, backend drain/restart, post-release validation, SDD doctor, and release-network checks as deterministic promotion steps.
- [x] T039 Add promotion API/tool that accepts validated parameters only and never exposes ad hoc shell/git/deploy command execution to the LLM.
- [x] T040 Enforce PROD active-job drain gate and user approval gate before restart or production release.
- [x] T041 Persist promotion evidence, logs, release tags, release URLs, backend validation, app update metadata, and rollback hints.
- [x] T042 Add tests for blocked promotion, active job drain, failed validation, successful promotion, and no-LLM-command execution.
- [x] T043 Define DEV and PROD release channels, app labels, environment badges, color tokens, API base URLs, updater channels, and workspace/stage visibility rules.
- [x] T044 Add backend configuration for separate DEV and PROD app/update channels without mock/demo defaults.
- [x] T045 Add frontend environment banner/header rendering that is independent from existing `CODEX DEV` developer-mode signal.
- [x] T046 Build release validation for DEV APK and PROD APK to verify labels, colors, API URLs, updater URLs, and environment identity.
- [x] T047 Update Android release workflow or deterministic release wrapper to support DEV and PROD channels safely.
- [x] T048 Add Flutter/widget tests for distinct DEV/PROD UI colors, badges, headers, and stage identity display.
- [x] T049 Add end-to-end tests for PROD handoff -> DEV backlog -> stage run -> merge -> promotion dry-run.
- [x] T050 Add observability endpoints and notifications for backlog, stage, merge, promotion, release, and validation events.
- [x] T051 Add operator documentation for creating stages, running backlog, merging to `dev/main`, promoting to PROD, and recovering failures.
- [x] T052 Add migration/backfill strategy for existing untracked or already-created specs such as spec 017.
- [x] T053 Add rollout flags so the new pipeline can be enabled for DEV first and PROD slash/handoff later.
- [x] T054 Run full regression suite, SDD doctor, Android release-network validation, and backend post-release validation dry-runs before implementation closeout.
- [x] T055 Define stage runtime schema for backend URL, port, data dir, logs dir, PID file, env file, health, and restart policy.
- [x] T056 Implement deterministic per-stage port allocation with collision detection and stable reuse.
- [x] T057 Implement stage backend lifecycle commands for start, stop, restart, status, healthcheck, and log lookup.
- [x] T058 Bind DEV chat API calls and worker actions to the stage backend URL instead of a shared DEV backend.
- [x] T059 Render per-chat stage backend status, port, health, and last restart in the DEV frontend.
- [x] T060 Add tests proving restart/failure of one stage backend does not affect another stage backend or chat.
- [x] T061 Define PROD backend update state machine, including update_available, waiting_for_idle, auto_update_eligible, updating, updated_pending_ack, acknowledged, force_requested, blocked, and failed.
- [x] T062 Implement PROD quiescence detector that includes active CLI jobs, active_agent_run_id, queued/reserved agent turns, Generator -> Reviewer -> Generator follow-ups, Summary follow-ups, SDD/Codex jobs, Project Factory jobs, and pending background tasks.
- [x] T063 Implement automatic PROD backend update when a prepared update is available and the quiescence detector proves no active or pending agent chain exists.
- [x] T064 Add persistent PROD update notification UI that shows waiting-for-idle, updating, updated, failed, and acknowledgement states without requiring a modal pop-up.
- [x] T065 Add force restart/update action with strong confirmation, interruption evidence, recovery summary, and post-update validation.
- [x] T066 Add tests for idle auto-update, busy waiting, Generator-to-Reviewer pending chains, forced restart, failed validation, and user acknowledgement dismissal.

## Implementation Audit - 2026-07-13

Covered tasks are marked above only where backend, mobile, tests, or operator
documentation provide concrete evidence. The 2026-07-13 follow-up closed the
previous seven open items with strict reviewer JSON parsing/final summary
evidence, pause/resume control states, inline SDD doctor merge validation,
dedicated stage healthcheck, mobile stage runtime display, and HTTP test-double
backend isolation checks. No PROD restart, deploy, release, or real update
executor was run.
