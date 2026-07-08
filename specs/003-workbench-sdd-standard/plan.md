# Plan

This file is the legacy index for tools that expect a root `plan.md`. The canonical Workbench hierarchy is in `tree.json`.

## Plan 1: Workbench SDD Standard

- File: [`plans/01-workbench-sdd-standard/plan.md`](plans/01-workbench-sdd-standard/plan.md)
- Status: `done`
- Tasks: `8`

## Plan 2: Project Manifest Adoption

- File: [`plans/02-project-manifest-adoption/plan.md`](plans/02-project-manifest-adoption/plan.md)
- Status: `done`
- Tasks: `8`

## Plan 3: Preflight Validation And Scaffolding

- File: [`plans/03-preflight-validation-and-scaffolding/plan.md`](plans/03-preflight-validation-and-scaffolding/plan.md)
- Status: `done`
- Tasks: `9`

## Plan 4: Documentation Templates

- File: [`plans/04-documentation-templates/plan.md`](plans/04-documentation-templates/plan.md)
- Status: `done`
- Tasks: `7`

## Plan 5: Diagram Taxonomy And Governance

- File: [`plans/05-diagram-taxonomy-and-governance/plan.md`](plans/05-diagram-taxonomy-and-governance/plan.md)
- Status: `done`
- Tasks: `6`

## Plan 6: SDD Indexer

- File: [`plans/06-sdd-indexer/plan.md`](plans/06-sdd-indexer/plan.md)
- Status: `done`
- Tasks: `9`

## Plan 7: Context Pack Engine

- File: [`plans/07-context-pack-engine/plan.md`](plans/07-context-pack-engine/plan.md)
- Status: `done`
- Tasks: `10`

## Plan 8: LLM Operating Instructions

- File: [`plans/08-llm-operating-instructions/plan.md`](plans/08-llm-operating-instructions/plan.md)
- Status: `done`
- Tasks: `5`

## Plan 9: Workbench UI

- File: [`plans/09-workbench-ui/plan.md`](plans/09-workbench-ui/plan.md)
- Status: `done`
- Tasks: `8`

## Plan 10: Validators And Doctor Checks

- File: [`plans/10-validators-and-doctor-checks/plan.md`](plans/10-validators-and-doctor-checks/plan.md)
- Status: `done`
- Tasks: `8`

## Plan 11: SAT Pilot Adoption

- File: [`plans/11-sat-pilot-adoption/plan.md`](plans/11-sat-pilot-adoption/plan.md)
- Status: `done`
- Tasks: `5`

## Plan 12: Adoption Documentation

- File: [`plans/12-adoption-documentation/plan.md`](plans/12-adoption-documentation/plan.md)
- Status: `done`
- Tasks: `7`

## Plan 13: Review And Iteration

- File: [`plans/13-review-and-iteration/plan.md`](plans/13-review-and-iteration/plan.md)
- Status: `done`
- Tasks: `5`

## Notes

### Implementation Strategy

1. Keep the first implementation slice schema-only and read-only.
2. Add standard, manifest, template, and scaffold dry-run validators before
   adding bootstrap write flows.
3. Add scaffolding writes only after validation has a passing dry-run path and
   explicit non-overwrite guarantees.
4. Add indexes and context packs before expanding Codex actions.
5. Add UI surfaces after backend/service behavior can produce real data.
6. Pilot on SAT only after generic behavior exists.
7. Iterate with reviewer feedback after each phase or small group of phases.

### Risks

- The standard could become SAT-specific if project-owned content leaks into
  platform-owned schemas.
- Generated indexes could become stale if the update flow is not clear.
- LLM prompts could still read too broadly if context packs are advisory only.
- Baseline diagrams could become noisy if impact gates are too weak.
- Too many required artifacts could make adoption feel heavy for small projects.
- Unknown standard versions could be treated as legacy projects and accidentally
  allow writes.
- Bootstrap could create files before the project has passed schema and template
  validation.

### Mitigations

- Keep Workbench schemas domain-neutral.
- Make indexes regeneratable and validated.
- Make context pack rules explicit in generated prompts.
- Require impact metadata before baseline edits.
- Allow project profiles and optional artifact families where appropriate.
- Treat unknown standards as hard failures for write/context/action flows.
- Require dry-run validation before bootstrap writes.
