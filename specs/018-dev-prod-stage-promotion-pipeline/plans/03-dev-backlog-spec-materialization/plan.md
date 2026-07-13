# DEV Backlog Spec Materialization Plan

## Goal

Consume queued handoffs in DEV, claim them safely, and materialize them into
existing or new Workbench specs without modifying PROD or overloading
`metadata.status`.

## Scope

- Backlog item lifecycle.
- Worker claim and locking.
- Existing-spec attachment versus new-spec creation.
- Delivery state storage outside SDD lifecycle.
- Workbench/Kanban projection.

## Tasks

- T013 Define DEV backlog item states, claim semantics, locks, retries, cancellation, and terminal states.
- T014 Implement DEV worker claim/import flow that materializes queued handoffs only in DEV workspaces.
- T015 Implement spec attachment rules for existing spec versus new spec creation.
- T016 Store delivery/runtime state outside `metadata.status` while keeping SDD lifecycle compatible.
- T017 Add Workbench/Kanban visibility for backlog items, materialized specs, blocked imports, and active stages.
- T018 Add tests for duplicate handoffs, claim races, blocked materialization, and delivery-state projection.

## Acceptance Criteria

- A handoff can be claimed by only one DEV worker.
- Handoff import writes only under a DEV workspace/stage.
- Existing SDD readers still understand spec lifecycle.
- Workbench can show queued, claimed, blocked, materialized, and active items.

## Validation

- Backend concurrency tests for claim races.
- Spec creation/edit tests for target workspace enforcement.
- Kanban projection tests for delivery state.

