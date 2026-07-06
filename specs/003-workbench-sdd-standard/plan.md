# Plan

## Phase 1: Workbench SDD Standard

Define `workbench-sdd/v1` as the platform-owned contract. The standard must
describe artifact families, lifecycle states, metadata, diagram taxonomy,
traceability links, context pack names, generated index schemas, and LLM rules.
The source-of-truth artifact is
`backend/app/infrastructure/config/sdd_standards/workbench-sdd/v1.yaml`, loaded
through `SddStandardService`. This phase also defines unknown-version errors,
compatibility behavior, and fixture coverage.

## Phase 2: Project Manifest Adoption

Extend `codex-bridge.yaml` so projects declare how they adopt the standard:
roots, project type, domains, protected baseline artifacts, generated index
location, context rules, and allowed project overrides. This phase includes
manifest/schema validation and context-rule precedence before any scaffolding
write flow exists.

## Phase 3: Preflight Validation And Scaffolding

Add standard, manifest, template, and scaffold dry-run validators first. Only
after preflight passes, add a bootstrap write flow that creates missing SDD
artifacts for a repo that wants to use Workbench. The write flow must detect
existing files, avoid destructive writes, and produce actionable next steps for
incomplete projects.

## Phase 4: Documentation Templates

Create templates for the required documents and metadata. Templates must stay
domain-neutral and explain what is Workbench-owned versus project-owned.

## Phase 5: Diagram Taxonomy And Governance

Define built-in diagram types and Mermaid notation rules. Separate baseline
architecture, domain, and data diagrams from feature-local impact diagrams.
Baseline edits must require explicit impact justification.

## Phase 6: SDD Indexer

Generate `.sdd/` indexes from project artifacts. Indexes must let the Workbench
and LLMs identify relevant specs, diagrams, modules, domains, statuses, and
traceability without scanning every spec. Missing or stale indexes must produce
observable status. Context pack flows attempt deterministic regeneration first;
if regeneration fails, they return a degraded pack or a hard failure depending
on the action instead of reading all specs.

## Phase 7: Context Pack Engine

Implement context pack presets that map user intent to required files, candidate
indexes, retrieval limits, forbidden broad reads, and escalation rules.

## Phase 8: LLM Operating Instructions

Update Workbench-launched Codex actions so every LLM starts from manifest,
standard, constitution, indexes, and a context pack. Prompts must prohibit
unbounded spec reads unless the selected pack requires them.

## Phase 9: Workbench UI

Expose project SDD health, standards compliance, feature specs, baselines,
traceability matrix, context pack preview, and architecture/domain/data impact
queues.

## Phase 10: Validators And Doctor Checks

Add validation for manifest schema, artifact presence, metadata, diagram types,
traceability links, stale indexes, and unsafe baseline edits.

## Phase 11: SAT Pilot Adoption

Apply the standard to SAT as the first real project. SAT must declare its
domains and project-specific rules without adding SAT-specific assumptions to
the platform standard.

## Phase 12: Adoption Documentation

Document how any new project adopts the standard, creates a feature, generates
context packs, protects baseline artifacts, and applies Workbench rules to its
own domain.

## Implementation Strategy

1. Keep the first implementation slice schema-only and read-only.
2. Add standard, manifest, template, and scaffold dry-run validators before
   adding bootstrap write flows.
3. Add scaffolding writes only after validation has a passing dry-run path and
   explicit non-overwrite guarantees.
4. Add indexes and context packs before expanding Codex actions.
5. Add UI surfaces after backend/service behavior can produce real data.
6. Pilot on SAT only after generic behavior exists.
7. Iterate with reviewer feedback after each phase or small group of phases.

## Risks

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

## Mitigations

- Keep Workbench schemas domain-neutral.
- Make indexes regeneratable and validated.
- Make context pack rules explicit in generated prompts.
- Require impact metadata before baseline edits.
- Allow project profiles and optional artifact families where appropriate.
- Treat unknown standards as hard failures for write/context/action flows.
- Require dry-run validation before bootstrap writes.
