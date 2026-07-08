# Plan

This file is the legacy index for tools that expect a root `plan.md`. The canonical Workbench hierarchy is in `tree.json`.

## Plan 1: Spec Target Contract

- File: [`plans/01-spec-target-contract/plan.md`](plans/01-spec-target-contract/plan.md)
- Status: `done`
- Tasks: `4`

## Plan 2: SCM Metadata Model

- File: [`plans/02-scm-metadata-model/plan.md`](plans/02-scm-metadata-model/plan.md)
- Status: `done`
- Tasks: `4`

## Plan 3: Multimodal Intake Storage

- File: [`plans/03-multimodal-intake-storage/plan.md`](plans/03-multimodal-intake-storage/plan.md)
- Status: `done`
- Tasks: `6`

## Plan 4: Backend Spec Creation Boundary

- File: [`plans/04-backend-spec-creation-boundary/plan.md`](plans/04-backend-spec-creation-boundary/plan.md)
- Status: `done`
- Tasks: `5`

## Plan 5: Backend Existing Spec Edit Boundary

- File: [`plans/05-backend-existing-spec-edit-boundary/plan.md`](plans/05-backend-existing-spec-edit-boundary/plan.md)
- Status: `done`
- Tasks: `4`

## Plan 6: Codex CLI Orchestration

- File: [`plans/06-codex-cli-orchestration/plan.md`](plans/06-codex-cli-orchestration/plan.md)
- Status: `done`
- Tasks: `8`

## Plan 7: Metadata Refresh

- File: [`plans/07-metadata-refresh/plan.md`](plans/07-metadata-refresh/plan.md)
- Status: `done`
- Tasks: `7`

## Plan 8: Workbench UX For Specs

- File: [`plans/08-workbench-ux-for-specs/plan.md`](plans/08-workbench-ux-for-specs/plan.md)
- Status: `done`
- Tasks: `13`

## Plan 9: Codex CLI Bridge Spec Targeting

- File: [`plans/09-codex-cli-bridge-spec-targeting/plan.md`](plans/09-codex-cli-bridge-spec-targeting/plan.md)
- Status: `done`
- Tasks: `9`

## Plan 10: Status Streaming And Activity

- File: [`plans/10-status-streaming-and-activity/plan.md`](plans/10-status-streaming-and-activity/plan.md)
- Status: `done`
- Tasks: `5`

## Plan 11: Validation And Tests

- File: [`plans/11-validation-and-tests/plan.md`](plans/11-validation-and-tests/plan.md)
- Status: `done`
- Tasks: `6`

## Plan 12: SAT Pilot And Reviewer Closeout

- File: [`plans/12-sat-pilot-and-reviewer-closeout/plan.md`](plans/12-sat-pilot-and-reviewer-closeout/plan.md)
- Status: `done`
- Tasks: `8`

## Notes

### Implementation Strategy

1. Keep the first slice schema/read-only where possible.
2. Add dry-run and validation before any write flow.
3. Add write flows only through explicit create/edit actions.
4. Wire Codex CLI orchestration only after target validation and context pack
   generation are tested.
5. Add media writes only after size, format, retention, and privacy rules are
   test-covered.
6. Add Codex CLI execution only after dry-run create/edit flows are safe.
7. Add UX surfaces after backend boundaries are machine-testable.
8. Pilot SAT only after generic Workbench behavior exists.

### Risks

- Spec creation could overwrite or fork an existing spec if slug/id generation
  is weak.
- Media intake could lose original user evidence if summarization replaces raw
  assets.
- Codex CLI could run in the wrong repo if target workspace validation is weak.
- Automatic description refresh could overwrite user wording unless pinned
  fields are respected.
- Bridge capture payloads and Workbench payloads could drift if they do not
  share the same `spec_target` contract.
- The user experience could expose too much internal SDD language instead of
  SCM/spec language.

### Mitigations

- Use deterministic id/slug generation with collision checks.
- Store raw intake before any generated summaries.
- Require target workspace validation and explicit target repo in every job.
- Track generated and pinned metadata flags separately.
- Use one shared backend contract for Workbench and Bridge captures.
- Keep UX copy focused on specs, functionality, changes, and tasks.
