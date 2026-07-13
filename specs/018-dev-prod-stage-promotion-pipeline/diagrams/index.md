# SPEC 018 Diagram Index

These diagrams are the visual contract for the DEV/PROD stage and deterministic
promotion pipeline.

| Diagram | Type | Purpose |
| --- | --- | --- |
| `system-context.mmd` | system-context | Shows PROD, DEV, control plane, GitHub Actions, releases, and scripts. |
| `lane-permission-model.mmd` | component-impact | Shows allowed and denied capabilities by operating lane. |
| `prod-handoff-sequence.mmd` | sequence | Shows the enqueue-only PROD slash/action handoff. |
| `prod-to-dev-handoff-sequence.mmd` | sequence | Shows the broader handoff path through DEV worker materialization. |
| `backlog-stage-lifecycle.mmd` | state | Shows backlog and stage delivery state transitions. |
| `backlog-stage-state-machine.mmd` | state | Shows the compact backlog, stage, validation, merge, and promotion readiness machine. |
| `stage-worktree-topology.mmd` | deployment | Shows branch, worktree, backend, app, and chat isolation per spec stage. |
| `worktree-topology.mmd` | deployment | Shows branch, worktree, backend instance, merge gate, and promotion gate topology. |
| `dev-agent-review-loop.mmd` | sequence | Shows Generator/Reviewer execution inside a registered DEV stage. |
| `dev-main-merge-queue.mmd` | component-impact | Shows serialized stage branch integration into `dev/main`. |
| `promotion-pipeline.mmd` | component-impact | Shows promotion as a gate-by-gate flowchart. |
| `promotion-state-machine.mmd` | state | Shows the deterministic `dev/main` to PROD promotion state machine. |
| `prod-promotion-sequence.mmd` | sequence | Shows promotion orchestration across validation, drain, release, deploy, and post-validation. |
| `release-channel-deployment.mmd` | deployment | Shows distinct DEV and PROD mobile app channels and backend identity checks. |
| `control-plane-data-model.mmd` | data-impact | Shows the full control-plane data model for environments, handoffs, backlog, stages, runs, merges, promotions, validations, and releases. |
| `observability-evidence-model.mmd` | entity-relationship | Shows records captured for audit, evidence, and recovery. |
| `stage-runtime-isolation.mmd` | deployment | Shows one backend process, port, data dir, logs, PID, env file, and chat route per DEV stage. |
| `prod-backend-update-gate.mmd` | state | Shows automatic PROD backend update eligibility, waiting-for-idle notification, force restart, validation, and user acknowledgement. |
