# Dev Prod Stage And Deterministic Promotion Pipeline

id: 018-dev-prod-stage-promotion-pipeline
status: ready-for-review
owner: codex-mobile-bridge

## Intent

Create the operating model that lets the user work daily in a stable PROD lane
while improvements to Codex Mobile Bridge are captured, planned, implemented,
reviewed, merged, released, and promoted through isolated DEV lanes.

The system must make isolation and promotion deterministic. The LLM must not
remember procedures, choose git commands, decide release mechanics, or infer
which environment it is allowed to mutate. The backend, tools, queues, stage
registry, worktree bindings, and promotion orchestrator must enforce the rules.

## Core Outcome

The user can work in PROD, notice a Bridge problem, use an explicit slash/action
to create a DEV handoff, and continue PROD work without exposing PROD agents to
DEV internals. DEV receives the handoff as a backlog/spec item, materializes it
into an isolated stage, runs Generator/Reviewer loops in the existing chat agent
engine, and produces user-validation evidence. Multiple DEV specs can run in
parallel without sharing branches, worktrees, backend processes, or mutable
runtime state. Integration into `dev/main` and promotion to PROD are performed
only by deterministic tools.

## Diagram Set

The professional diagram set for this spec is stored under
`diagrams/index.md`. These diagrams are part of the implementation contract and
must stay aligned with future changes to the plan and tasks.

- `diagrams/system-context.mmd` shows the complete PROD, DEV, control-plane,
  release, and script boundary.
- `diagrams/lane-permission-model.mmd` shows allowed and denied capabilities by
  operating mode.
- `diagrams/prod-handoff-sequence.mmd` shows the enqueue-only PROD slash/action
  flow.
- `diagrams/prod-to-dev-handoff-sequence.mmd` shows the broader path from PROD
  work through DEV worker materialization and chat binding.
- `diagrams/backlog-stage-lifecycle.mmd` shows backlog, stage, merge, and
  promotion delivery states.
- `diagrams/backlog-stage-state-machine.mmd` shows the compact state-machine
  view for backlog, validation, merge, and promotion readiness.
- `diagrams/stage-worktree-topology.mmd` shows branch, worktree, backend, app,
  and chat isolation per DEV stage.
- `diagrams/worktree-topology.mmd` shows branch, worktree, backend-instance,
  merge-gate, and promotion-gate topology.
- `diagrams/dev-agent-review-loop.mmd` shows the Generator/Reviewer execution
  loop inside one registered stage.
- `diagrams/dev-main-merge-queue.mmd` shows serialized integration into
  `dev/main` and conflict handling.
- `diagrams/promotion-pipeline.mmd` shows promotion as a deterministic
  gate-by-gate flowchart.
- `diagrams/promotion-state-machine.mmd` shows the deterministic promotion
  state machine.
- `diagrams/prod-promotion-sequence.mmd` shows validation, approval, drain,
  backend deploy, app release, and post-validation.
- `diagrams/release-channel-deployment.mmd` shows DEV and PROD APK channel
  separation, colors, labels, API URLs, updater channels, and identity checks.
- `diagrams/control-plane-data-model.mmd` shows the full control-plane data
  model for environments, handoffs, backlog, stages, runs, merges, promotions,
  validations, and releases.
- `diagrams/observability-evidence-model.mmd` shows evidence, release,
  handoff, stage, merge, and promotion records.
- `diagrams/prod-backend-update-gate.mmd` shows automatic PROD backend updates
  when idle, waiting-for-idle notification, force restart, validation, and user
  acknowledgement.

## Non-Negotiable Rules

- PROD agents do not know about DEV, stage worktrees, promotion mechanics, or
  internal Bridge improvement workflows during normal operation.
- PROD agents cannot write Bridge code, apply patches, restart Bridge services,
  deploy Bridge releases, or mutate DEV worktrees.
- The only PROD-side exception is an explicit slash/action that loads a
  temporary handoff context and writes an immutable item to a DEV queue.
- The slash/action must not grant file-write, command, restart, deploy, or git
  permissions in PROD.
- DEV agents operate only inside their assigned stage worktree and branch.
- One DEV chat is bound to exactly one stage, one spec, one branch, and one
  worktree.
- Multiple DEV stages may run in parallel, but integration into `dev/main` is
  serialized.
- The LLM cannot run ad hoc promotion commands. It may only request a promotion
  tool with validated parameters.
- Promotion tools must fail closed on dirty trees, conflicts, failed tests,
  stale branches, active PROD jobs, missing approvals, missing release
  configuration, missing secrets, or invalid environment identity.
- PROD backend updates may apply automatically only after a deterministic
  quiescence detector proves there are no active jobs and no pending agent-chain
  follow-ups.
- If a PROD backend update is available while work is active or pending, the
  frontend must show a persistent waiting-for-update/restart notice instead of
  restarting immediately.
- The user may force a PROD backend update/restart only through an explicit
  strong-confirmation action that records interrupted work and validation
  evidence.
- DEV and PROD mobile apps must be visibly distinct through release channel,
  app label/badge, environment color, API base URL, updater channel, and
  workspace/stage display.
- Release builds must use real backend configuration and real data paths unless
  the user explicitly requests a demo/mock APK.
- User-installable Android releases must be signed with the configured release
  keystore. Debug-signed release builds are allowed only for local smoke tests
  behind an explicit non-publishable Gradle property and must never be published
  by GitHub Actions.

## Environment Model

The system has three logical areas.

1. PROD lane
   - Stable user-facing Bridge application.
   - Used for real daily work and long-running processes.
   - Read-only with respect to Bridge self-modification.
   - Can enqueue DEV handoffs only through the explicit slash/action.

2. DEV lane
   - Active improvement area for Bridge itself.
   - Contains `dev/main` and isolated stage worktrees such as `dev/spec-018`.
   - Runs DEV backend/app instances separate from PROD.
   - Can break, restart, and iterate without affecting PROD.

3. Control plane
   - Queue, stage registry, merge queue, promotion records, evidence, and
     notifications.
   - Not a code worktree.
   - Enforces permissions and stores immutable handoffs and deterministic run
     records.

## Branch And Worktree Model

`dev/main` is the DEV integration branch. Each spec gets its own branch and
worktree:

```text
dev/spec-017-new-project-deterministic-init-pipeline
dev/spec-018-dev-prod-stage-promotion-pipeline
dev/spec-019-...
```

Each stage record must include:

```yaml
stage_id: spec-018
environment: dev
spec_id: 018-dev-prod-stage-promotion-pipeline
branch: dev/spec-018-dev-prod-stage-promotion-pipeline
base_branch: dev/main
worktree_path: /.../codex-cli-mobile-bridge-spec-018
backend_url: http://127.0.0.1:<allocated-port>
app_channel: dev
status: active
```

Each stage also owns a runtime record. Worktrees isolate files; runtime records
isolate processes:

```yaml
stage_id: spec-018
backend:
  url: http://127.0.0.1:8118
  port: 8118
  data_dir: /home/batata/.codex-bridge/stages/spec-018/data
  logs_dir: /home/batata/.codex-bridge/stages/spec-018/logs
  pid_file: /home/batata/.codex-bridge/stages/spec-018/backend.pid
  env_file: /home/batata/.codex-bridge/stages/spec-018/.env.stage
  health: running
  last_restart_at:
```

Stage backend lifecycle commands must be deterministic:

```text
stage.start_backend(stage_id)
stage.stop_backend(stage_id)
stage.restart_backend(stage_id)
stage.status(stage_id)
stage.logs(stage_id)
```

These commands may operate only on the registered stage worktree and runtime
paths. A backend restart requested from `spec-018` must never restart or block
`spec-017`.

The frontend must render the backend-provided environment and stage identity in
every DEV chat. The chat header must make the current lane visible without
requiring prompt text:

```text
DEV - spec-018 - dev/spec-018-dev-prod-stage-promotion-pipeline
```

## PROD Handoff Model

The PROD slash/action loads a temporary context. The normal PROD agent does not
carry this context.

Allowed slash/action behavior:

- read the current conversation context selected by the user;
- create a structured handoff payload;
- send it to the DEV queue through a narrow backend endpoint;
- return the queued item id and a concise confirmation.

Forbidden slash/action behavior:

- editing files;
- running shell commands;
- changing git state;
- restarting services;
- reading DEV worktrees;
- applying changes to PROD or DEV code;
- starting DEV Generator/Reviewer directly.

The handoff payload must include enough context for DEV without leaking broad
PROD runtime state:

```yaml
kind: bridge.devHandoff
version: 1
source_environment: prod
target_environment: dev
operation: enqueue_only
title:
problem:
context:
evidence:
proposed_spec:
proposed_plan:
proposed_tasks:
acceptance_criteria:
regression_tests:
risks:
created_from_session_id:
created_by_action:
```

## DEV Backlog And Spec Materialization

DEV workers consume queued handoffs. A DEV worker may either attach the handoff
to an existing spec or materialize a new spec. Materialization must happen in
the target DEV worktree, not in PROD.

Backlog states:

```text
queued
claimed
materializing
materialized
blocked
cancelled
```

Spec lifecycle and delivery state must stay separate. `metadata.status` remains
the SDD lifecycle. Runtime execution status is stored under a dedicated delivery
or control-plane record so existing SDD readers do not break.

Current delivery projections are exposed through DEV/control-only
`/dev-pipeline/projection`; PROD normal cannot read backlog, stage, run, merge,
promotion, or release validation internals.

## DEV Agent Execution

The existing chat agent engine must be reused. Do not build a second
Generator/Reviewer engine unless a later spec proves the current one cannot
serve this workflow.

For a DEV stage run:

- the backend creates or selects the chat bound to the stage;
- the backend sets the chat `workspace_path` to the stage worktree;
- the backend applies an `AgentConfiguration` with Generator and Reviewer
  enabled and matching turn budgets;
- the Reviewer prompt should support JSON completion:
  `{"status":"complete","summary":"..."}`;
- if Reviewer returns `continue`, its prompt goes back to Generator;
- if Reviewer returns `complete`, the run stops and final evidence is written;
- a final user-facing completion summary is generated without leaking internal
  reviewer chatter as raw context.

Implemented stage controls support start, pause, cancel, retry, resume, and
status. Pause/resume are explicit control states because MessageService does
not expose a real pause primitive; they record `pause_requested` and
`resume_requested` without pretending to stop an already-running job.

Reviewer evidence for stage runs is parsed from strict JSON:

```json
{"status":"continue","prompt":"Add the missing regression test."}
{"status":"complete","summary":"All acceptance criteria pass."}
```

Invalid reviewer JSON is persisted as a `reviewer_contract_invalid` blocker.
When Reviewer returns `complete`, the stage run evidence includes a synthesized
final summary.

Final summary shape:

```text
Termine.

Que cambio
Archivos tocados
Tests ejecutados
Riesgos
Que deberias probar
Resultado final
```

## Merge Model

Only deterministic merge tooling can integrate stage branches into `dev/main`.
The merge queue is serialized.

Required merge gates:

- stage branch exists and points to the registered worktree;
- stage worktree has no unexpected uncommitted changes;
- spec tasks are complete or explicitly waived by a Reviewer finding;
- Reviewer reached complete;
- required tests or explicit validation evidence are present;
- branch is rebased or merged against current `dev/main`;
- conflicts are reported as blocked with exact files;
- merge result runs integration validation before marking success.

Current merge apply records commit IDs, validation logs, tests, blockers,
stdout/stderr, conflict details, and an inline allowlisted SDD doctor dry-run.
If SDD doctor fails, merge apply blocks before updating `dev/main`.

The second stage that touches an already-changed file must resolve conflicts in
its own stage branch before entering `dev/main`.

## Promotion Model

Promotion from `dev/main` to PROD is a deterministic state machine. The LLM can
request promotion, but only the promotion tool can execute it.

Promotion states:

```text
requested
preflight
validation
approval_required
drain_waiting
ready_to_promote
blocked
failed
dry_run_passed
rollback_ready
```

Promotion must reuse existing deterministic assets where possible:

- Android release tag script;
- GitHub Actions Android release workflow;
- backend drain/restart script;
- backend post-release validation;
- SDD doctor;
- release network validation;
- app update registry validation.

The promotion tool records allowlisted command argv, dry-run outputs, release
tag intent, backend URL, app channels, validation evidence, blockers, and
rollback hints. Real backend deploy, APK publication, GitHub release creation,
and PROD restart remain blocked unless a future explicit operator instruction
enables the relevant flags and action.

## PROD Backend Update And Restart Gate

A prepared PROD backend update is allowed to apply automatically only when PROD
is truly idle. This does not mean only "no process is currently running"; it
means there is no active or pending agent chain left to execute.

The quiescence detector must treat PROD as busy when any of these exists:

- active CLI process or active job;
- `active_agent_run_id`;
- queued, reserved, or scheduled agent turn;
- Generator completed but Reviewer is pending;
- Reviewer requested another Generator turn;
- final Summary follow-up is pending;
- SDD/Codex job is running or reserved;
- Project Factory job is running or reserved;
- background task required to finish the current user-visible run.

Update states:

```text
idle
update_available
waiting_for_idle
auto_update_eligible
updating
updated_pending_ack
acknowledged
force_requested
blocked
failed
```

Behavior:

- if an update is available and the detector says idle, the gate marks
  `auto_update_eligible`; real restart/update execution is allowlisted,
  flag-gated, and disabled by default;
- if an update is available and the detector says busy, PROD shows a persistent
  notice such as `Actualizacion disponible - esperando que terminen las tareas`;
- the waiting notice must expose a force action, but only after strong user
  confirmation;
- after successful update and validation, PROD shows a persistent
  updated/restarted notice until the user acknowledges or dismisses it;
- failed updates remain visible with exact validation failure and retry/force
  options.

The implementation uses fake/test executors in automated tests and does not
restart PROD during dry-run validation.

The LLM does not decide whether restart is safe. It can only surface the
backend-owned state and call the deterministic force/acknowledge tools when the
user explicitly requests them.

## DEV And PROD App Release Requirements

There must be two visibly distinct app channels:

1. PROD app
   - `prod` app/update channel;
   - source app `codex-mobile`;
   - Android package `com.example.codex_mobile_frontend`;
   - release tags `android-v*`;
   - stable/prod API base URL;
   - PROD environment badge;
   - PROD color token;
   - production updater channel;
   - no DEV stage controls unless explicitly enabled for authorized developer
     mode.

2. DEV app
   - `dev` app/update channel;
   - source app `codex-mobile-dev`;
   - Android package `com.example.codex_mobile_frontend.dev` so it installs
     side-by-side with PROD;
   - release tags `android-dev-v*`;
   - DEV API base URL;
   - DEV environment badge;
   - DEV color token;
   - DEV updater channel;
   - stage selector and stage/chat identity visible in every chat.

The existing `CODEX DEV` signal must not be repurposed if it already means a
different developer-mode feature. This spec adds an environment identity layer
separate from existing developer-mode labeling.

Visual distinction must be deterministic and testable:

- app label or header contains `DEV` or `PROD`;
- environment badge is always visible in chat;
- color palette differs between DEV and PROD;
- backend `/health` or environment endpoint reports environment identity;
- mobile app validates its configured environment against the backend response.

## CI/CD Platform Position

The preferred platform is the existing repository tooling:

- GitHub Actions for hosted builds/releases on this public repository;
- backend promotion service for local/server-side state machine execution;
- existing scripts for tag, drain, restart, and validation;
- future MCP/tool wrapper for LLM access to promotion commands.

Do not introduce Jenkins, Terraform, or a large workflow platform for this
first delivery. Terraform remains useful for infrastructure provisioning, but
not for the merge/promotion workflow itself.

## Diagrams

This spec includes feature-local diagrams that explain the target process from
different angles:

- `diagrams/system-context.mmd`: end-to-end system context for PROD, DEV,
  control plane, worktrees, merge queue, promotion, GitHub Actions, and runtime.
- `diagrams/prod-to-dev-handoff-sequence.mmd`: sequence from normal PROD work to
  temporary slash handoff and DEV stage materialization.
- `diagrams/backlog-stage-state-machine.mmd`: lifecycle for backlog items,
  stage execution, user validation, integration, and promotion readiness.
- `diagrams/worktree-topology.mmd`: branch, worktree, backend-instance, merge
  gate, and promotion gate topology for parallel DEV specs.
- `diagrams/promotion-pipeline.mmd`: deterministic promotion state machine from
  `dev/main` to PROD.
- `diagrams/control-plane-data-model.mmd`: data model for environments,
  handoffs, backlog, stages, runs, evidence, merge queue, promotion, validation,
  and release artifacts.
- `diagrams/stage-runtime-isolation.mmd`: deployment view for per-stage backend
  processes, ports, data dirs, logs, PID files, env files, and frontend routing.
- `diagrams/prod-backend-update-gate.mmd`: state view for automatic PROD
  backend update eligibility, waiting-for-idle notification, force restart,
  post-validation, and user acknowledgement.

## Success Criteria

- PROD normal chats have no DEV/backlog/promotion context.
- PROD slash/action can enqueue handoffs without write or command permissions.
- DEV can run two spec stages in parallel without sharing worktrees or
  branches.
- PROD backend updates apply automatically only when the full agent/job chain is
  idle, otherwise they wait visibly with an explicit force option.
- DEV can restart one spec backend without affecting another active spec.
- DEV frontend shows environment, stage, branch, and spec for each chat.
- Stage merge into `dev/main` is deterministic and serialized.
- Promotion to PROD is deterministic, tool-driven, observable, and blocked when
  active PROD jobs make restart unsafe.
- DEV and PROD APK/releases are visually distinct and use separate channels.
- Existing Android release, backend drain, post-release validation, and SDD
  doctor scripts remain the underlying deterministic primitives.

## Release Closeout Notes

All control-plane tasks in this spec are implemented or modeled behind safe
control states. PROD restart, backend deploy, and real update execution remain
flag-gated. APK publication and GitHub release creation are allowed only after
explicit operator instruction and must use the deterministic Android workflow:
`android-v*` publishes the PROD APK, and `android-dev-v*` publishes the DEV APK
as a prerelease. The workflow fails closed on missing release signing secrets,
mock/local/demo API URLs, missing DEV API URL, or APK metadata that does not
match the expected channel package.
operator instruction plus the relevant rollout flags.
