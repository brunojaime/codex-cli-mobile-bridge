# Plan

This file is the legacy index for tools that expect a root `plan.md`. The canonical Workbench hierarchy is in `tree.json`.

## Plan 1: SDD Explorer

- File: [`plans/01-sdd-explorer/plan.md`](plans/01-sdd-explorer/plan.md)
- Status: `done`
- Tasks: `7`

## Plan 2: Diagram Rendering

- File: [`plans/02-diagram-rendering/plan.md`](plans/02-diagram-rendering/plan.md)
- Status: `in_progress`
- Tasks: `6`

## Plan 3: Architecture UX

- File: [`plans/03-architecture-ux/plan.md`](plans/03-architecture-ux/plan.md)
- Status: `in_progress`
- Tasks: `5`

## Plan 4: Feedback Linked To Specs And Diagrams

- File: [`plans/04-feedback-linked-to-specs-and-diagrams/plan.md`](plans/04-feedback-linked-to-specs-and-diagrams/plan.md)
- Status: `in_progress`
- Tasks: `6`

## Plan 5: Codex Actions From Specs

- File: [`plans/05-codex-actions-from-specs/plan.md`](plans/05-codex-actions-from-specs/plan.md)
- Status: `in_progress`
- Tasks: `5`

## Plan 6: Current Project Dashboard

- File: [`plans/06-current-project-dashboard/plan.md`](plans/06-current-project-dashboard/plan.md)
- Status: `in_progress`
- Tasks: `7`

## Notes

### Implementation Notes

- Keep all work behind `CODEX_BRIDGE_DEV_MODE`.
- Keep SDD reads read-only unless a future explicit write flow is designed.
- Do not add demo data, mock URLs, or placeholder backend configuration.
- Do not change release identifiers, package ids, backend URLs, or updater
  configuration as part of this SDD.
- Keep diagram source as `.mmd`; rendered SVG/PNG remains cache only.
- Do not hard-code monolith or microservice assumptions.
