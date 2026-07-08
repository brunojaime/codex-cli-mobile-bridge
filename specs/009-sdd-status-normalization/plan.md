# SDD Status Normalization Plan

## Plan 1: Contract

- Define canonical status locations for specs, plans, and tasks.
- Document the distinction between UI source of truth and human-readable task
  indexes.

## Plan 2: Current Artifacts

- Normalize completed lazy-loading artifacts to `done`.
- Align metadata status and task counts with the completed tree.

## Plan 3: Generated Projects

- Emit `tree.json` from New Project Factory.
- Emit plan/task node files from New Project Factory.
- Compute metadata task totals from the same source used for `tree.json`.

## Plan 4: Validation

- Add generator tests for SDD status consistency.
- Run backend validation for Project Factory and SDD Workbench behavior.
