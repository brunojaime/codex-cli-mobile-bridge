# Workbench Kanban Curator Plan

## Phase 1: Kanban Domain Contract

Define the board, card, scope, evidence, and history models. Separate confirmed SDD task state from inferred activity.

## Phase 2: Deterministic SDD Projection

Build the projection service that reads existing SDD artifacts and computes deterministic task cards, phase summaries, columns, ordering, and deltas without modifying source artifacts.

## Phase 3: Passive Run Observer

Observe Project Factory jobs, Codex/session activity, command/test/build outcomes, generated repository creation, and Reviewer findings as read-only inputs.

## Phase 4: Curator Agent And History

Run a read-only Curator from board deltas and evidence. Persist latest update and append-only history with dedupe, retention, and evidence hashes.

## Phase 5: Workbench Kanban UI

Add the Kanban tab, board rendering, latest update panel, history list/detail view, overview compact card, and responsive mobile behavior.

## Phase 6: Validation And Rollout

Add backend, projection, Curator, API, Flutter, and New Project continuity tests. Validate that Generator and Reviewer behavior is unchanged.
