# DEV Main Merge Queue And Conflict Gates Plan

## Goal

Integrate stage branches into `dev/main` through a serialized deterministic
merge queue with preflight, conflict detection, validation, and evidence.

## Scope

- Merge queue schema.
- Stage readiness gates.
- Rebase/merge execution.
- Conflict capture.
- Integration validation and Workbench reporting.

## Tasks

- T031 Define serialized merge queue schema for stage branch to `dev/main` integration.
- T032 Implement merge preflight for clean worktree, approved spec state, completed reviewer, required tests, and fresh base.
- T033 Implement deterministic rebase/merge attempt with conflict capture and no partial integration on failure.
- T034 Run integration validation after merge and record commit, test evidence, SDD doctor output, and blockers.
- T035 Add user-visible merge status and conflict remediation instructions in DEV Workbench.
- T036 Add tests for successful merge, stale branch, conflict, dirty tree, failed validation, and serialized queue behavior.

## Acceptance Criteria

- Only one stage integrates into `dev/main` at a time.
- Dirty trees, stale branches, missing approval, failed reviewer, and failed
  tests block the merge.
- Conflicts are reported with exact files and no partial `dev/main` mutation.
- Successful merge stores commit id and validation evidence.

## Validation

- Temporary git repository tests for merge scenarios.
- Backend API tests for merge queue status.
- Workbench UI tests for conflict and success states.

