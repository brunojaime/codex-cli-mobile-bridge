---
id: 003-workbench-sdd-standard
title: Workbench SDD Standard And Context Routing
status: validated
type: platform-standard
domains:
  - workbench
  - sdd
  - context-routing
  - traceability
baseline_architecture_impact: true
---

# Workbench SDD Standard And Context Routing

## Intent

Codex Bridge Workbench must become the built-in SDD operating model for any
project that adopts it. A new project should be able to declare its domain,
follow Workbench rules, create feature specs, plan implementation work, maintain
traceability, and route LLM context without reading the whole repository or all
historical specs.

This spec defines the action plan for the twelve implementation phases required
to make the standard reusable, domain-neutral, and understandable by any LLM.

## Core Principle

Workbench owns the process. The project owns the content.

Workbench-defined behavior includes artifact taxonomy, required metadata,
feature lifecycle, diagram taxonomy, traceability rules, generated index schema,
context-pack routing, validation, and LLM operating instructions.

Project-defined content includes domains, business language, architecture
content, domain models, data models, specs, implementation modules, diagrams,
and project-specific governance overrides.

## Scope

This spec covers:

- A versioned `workbench-sdd/v1` standard.
- A source-of-truth standard artifact at
  `backend/app/infrastructure/config/sdd_standards/workbench-sdd/v1.yaml`.
- A backend loader boundary named `SddStandardService` that resolves standard
  identifiers for backend APIs, doctor scripts, Workbench prompts, and future
  package export paths.
- `codex-bridge.yaml` as the project adoption manifest.
- Bootstrap/scaffolding for new projects.
- Documentation and diagram standards.
- Domain, data, architecture, and feature artifact separation.
- Generated indexes for large repositories.
- Context packs that constrain what an LLM reads.
- Workbench UI workflows for project health, specs, traceability, context, and
  baseline impact review.
- Validation and doctor checks.
- SAT as the first pilot project after the standard exists.
- Documentation that lets future projects adopt the standard.

This spec does not implement the phases directly. It creates the plan,
traceability, and task inventory that later implementation iterations will
execute with reviewer involvement.

## Non-Goals

- Do not make SAT-specific assumptions part of the Workbench standard.
- Do not require a single monolithic system spec.
- Do not force every project to use the same domains, modules, stack, or
  deployment topology.
- Do not require an LLM to read all specs before acting.
- Do not replace project-owned architecture, domain, or data content with
  generated summaries.
- Do not modify baseline architecture, domain, or data diagrams without an
  explicit impact path.
- Do not start implementation work until this SDD has a reviewer pass, a
  revision pass, and a final self-review pass.

## Required Conceptual Layers

1. Workbench Standard: universal rules and schemas.
2. Project Manifest: how a repo adopts the standard.
3. Project Governance: project-specific principles and constraints.
4. Baseline Content: architecture, domain, and data artifacts.
5. Feature Specs: per-feature spec, plan, tasks, diagrams, and traceability.
6. Generated Indexes: machine-readable navigation and context routing.

## Workbench-Owned Responsibilities

- Define artifact types and required metadata.
- Define spec lifecycle states.
- Define documentation templates.
- Define diagram taxonomy and notation rules.
- Define baseline-vs-feature artifact policies.
- Define traceability schema and required link types.
- Define generated index schemas.
- Define context pack presets.
- Define LLM operating instructions.
- Provide validators and health summaries.
- Provide UI workflows that operate on the standard.
- Provide deterministic behavior for missing, stale, unknown, or unsupported
  standard and index versions.

## Project-Owned Responsibilities

- Declare project type, domains, roots, and protected baseline artifacts.
- Maintain project constitution and governance principles.
- Maintain architecture, domain, and data baseline content.
- Maintain feature specs, plans, tasks, and diagrams.
- Declare project-specific context rules and allowed overrides.
- Keep generated indexes current through Workbench tooling.

## Versioned Standard Resolution

The source-of-truth standard for this spec is:

```text
backend/app/infrastructure/config/sdd_standards/workbench-sdd/v1.yaml
```

The loader boundary is:

```text
backend/app/application/services/sdd_standard_service.py
```

The loader resolves the manifest value `sdd.standard: workbench-sdd/v1` to the
artifact above. Backend SDD services, doctor scripts, Workbench-generated LLM
prompts, and future Flutter package exports must all use that loader or a
serialized payload produced by it. A prompt that tells an LLM to resolve the
standard must point to either the backend-provided standard payload or this
repo-local artifact path.

Compatibility rules:

- `workbench-sdd/v1` is the only supported major version for this rollout.
- Unknown standard IDs are hard errors for write flows, Codex actions,
  scaffolding, indexing, and context-pack generation.
- Read-only SDD inspection may continue for legacy projects without a declared
  standard, but must show a compatibility warning.
- Future `workbench-sdd/v1.x` additions must be backward-compatible with v1
  required fields.
- A future major version requires an explicit migration path and doctor output
  that explains the upgrade.

## Project-Owned Context Rules

Projects may configure context routing in `codex-bridge.yaml` under
`sdd.context_rules`. The schema is Workbench-owned, but the values are
project-owned.

The precedence order is:

1. Workbench defaults from `workbench-sdd/v1`.
2. Project profile defaults, such as `flutter_app`, `backend_api`, or `monorepo`.
3. Project overrides from `codex-bridge.yaml`.

Allowed overrides include:

- domain-to-module mappings.
- preferred context files for a domain.
- paths excluded from LLM context routing.
- protected baseline artifacts.
- context pack candidate limits that are stricter than the Workbench default.

Project overrides may narrow context, add project-owned references, or protect
more files. They must not disable required Workbench safety rules such as
manifest-first resolution, baseline impact gates, or no-broad-read behavior.

## Required Artifact Families

- `codex-bridge.yaml`: project manifest and SDD adoption declaration.
- `.specify/memory/constitution.md`: project-owned governance.
- `architecture/`: system context, components, deployment, runtime flows, ADRs.
- `domain/`: glossary and conceptual domain models.
- `data/`: entity relationship, persistence, and data lifecycle models.
- `specs/<id-slug>/`: per-feature specs, plans, tasks, diagrams, traceability.
- `.sdd/`: generated indexes, health reports, context maps, and caches.

## Diagram Standard

The standard renderer is Mermaid. The modeling type depends on the artifact
purpose:

- System context: Mermaid flowchart or C4-style flowchart.
- Components: Mermaid flowchart with explicit component labels.
- Deployment: Mermaid flowchart with physical or logical locations.
- Runtime interaction: Mermaid sequence diagram. Baseline runtime sequences may
  live in `architecture/`; feature-specific sequences live under
  `specs/<feature>/diagrams/`.
- Entity lifecycle: Mermaid state diagram.
- Domain model: Mermaid class diagram used conceptually.
- Persistent data model: Mermaid ER diagram.
- Feature impact: local feature diagrams before baseline promotion.

Baseline diagrams require impact justification before edits. Feature diagrams
are the default place to describe new behavior or impact.

Current backend validation checks Mermaid source presence, supported top-level
directives, diagram metadata, ownership, scope, and protected-baseline policy.
Full Mermaid render validation is a non-goal until a backend renderer is
configured; validator output must say that render validation was skipped instead
of silently implying a rendered check ran.

## LLM Context Routing Requirement

The Workbench must prevent context sprawl. Any Codex or LLM action launched
from the Workbench must start with a context pack. The LLM must:

1. Read `codex-bridge.yaml`.
2. Resolve the declared SDD standard version.
3. Read generated indexes before broad file reads.
4. Read the project constitution.
5. Select only the context required by the action preset.
6. Avoid unrelated completed or archived specs unless selected by the context
   pack.
7. Avoid baseline edits unless an impact policy allows them.

If generated indexes are missing or stale, the context pack engine must attempt
deterministic regeneration before selecting related specs. If regeneration
succeeds, the observable output must report `index_status: regenerated`. If
regeneration fails, the output must report `index_status: failed`,
`degraded: true`, and a human-readable next action. In degraded mode, the
engine may provide only the manifest, standard, constitution, active selected
artifact, and explicitly required baseline files. It must not fall back to
reading all specs.

The required `.sdd/` index set is `spec-index.yaml`, `diagram-index.yaml`,
`module-index.yaml`, and `context-index.yaml`. Each index records standard
version, manifest digest, source freshness markers, and a shared fingerprint.
Observable states are `fresh`, `missing`, `stale`, `regenerated`, and `failed`.
When auto-regeneration is disabled, `missing` or `stale` is a hard failure for
context routing and still forbids all-spec fallback.

Context packs consume `.sdd` indexes plus the manifest, standard payload, and
constitution. They must never route by scanning every full spec body. Candidate
ranking is deterministic and uses indexed path, title, summary, type, scope, and
selected artifact signals.

Required presets are `new-feature`, `modify-existing-feature`, `bugfix`,
`architecture-change`, `data-model-change`, `domain-model-change`,
`implementation-from-spec`, `diagram-update`, and `sdd-audit`.

Default limits are at most 5 related specs and at most 3 related diagrams.
Project `sdd.context_rules.candidate_limits` may make those limits stricter but
cannot expand them beyond the Workbench default. Every pack must include
`index_status`, routing decisions, blocked-read rules, and next actions when
blocked or degraded.

Workbench-generated LLM instructions must serialize the context pack output
directly into the action prompt. The prompt must expose `index_status`,
`blocked_reads`, `routing_decisions`, `required_files`, `related_specs`,
`related_diagrams`, and `next_actions`. If standard resolution fails, context
rules are invalid, indexes are stale with regeneration disabled, or indexes are
unavailable, the prompt must be blocked or degraded and must not authorize broad
spec reads. Prompts must also restate protected baseline rules and preserve
project-owned domain language and stricter `sdd.context_rules` overrides.

## Functional Requirements

- FR-001: The Workbench SHALL define a versioned reusable SDD standard.
- FR-002: The Workbench SHALL use `codex-bridge.yaml` as the project adoption
  manifest instead of requiring an unrelated primary manifest.
- FR-003: The Workbench SHALL distinguish Workbench-owned process rules from
  project-owned domain content.
- FR-004: The Workbench SHALL provide bootstrap behavior for projects that lack
  SDD artifacts without overwriting existing project content.
- FR-005: The Workbench SHALL define documentation templates for constitution,
  architecture, domain, data, feature specs, plans, tasks, traceability, ADRs,
  and diagram metadata.
- FR-006: The Workbench SHALL define a diagram taxonomy and Mermaid notation
  rules for baseline and feature-local diagrams.
- FR-007: The Workbench SHALL generate machine-readable SDD indexes from project
  artifacts.
- FR-008: The Workbench SHALL provide context pack presets for common LLM
  actions.
- FR-009: The Workbench SHALL include LLM instructions that require indexes and
  context packs before broad repository reads.
- FR-010: The Workbench SHALL expose UI surfaces for health, compliance,
  feature specs, baselines, traceability, context previews, and impact queues.
- FR-011: The Workbench SHALL validate manifest, artifact, traceability, diagram,
  and context-pack consistency.
- FR-012: The Workbench SHALL pilot the standard on SAT without making SAT rules
  part of the platform standard.
- FR-013: The Workbench SHALL document adoption steps for future repositories.
- FR-014: The Workbench SHALL resolve `workbench-sdd/v1` from a known standard
  artifact and report unknown or incompatible versions deterministically.
- FR-015: The Workbench SHALL validate standard, manifest, template, and
  scaffold dry-run inputs before any bootstrap task writes project files.
- FR-016: The Workbench SHALL support project-owned context rules through a
  validated override schema and deterministic precedence order.
- FR-017: The Workbench SHALL require reviewer pass, document revision, and
  self-review before implementation starts.

## Acceptance Criteria

- AC-001: A new repo can declare `workbench-sdd/v1` in `codex-bridge.yaml` and
  be understood by the Workbench.
- AC-002: Workbench-owned schemas and project-owned content are documented and
  separated.
- AC-003: A bootstrap flow can create missing SDD structure while preserving
  existing files.
- AC-004: A feature can be represented by `spec.md`, `plan.md`, `tasks.md`,
  `traceability.yaml`, and feature-local diagrams.
- AC-005: Baseline architecture, domain, and data diagrams are protected by
  explicit impact policies.
- AC-006: Generated indexes can identify relevant specs, diagrams, modules, and
  context without reading all specs. For a context query, the engine must return
  at most 5 related specs and at most 3 related diagrams by default, include
  `index_status`, include the reason each candidate was selected, and never
  scan every spec body when a fresh index is available.
- AC-007: A context pack can constrain what an LLM reads for new-feature,
  implementation, bugfix, architecture-change, data-model-change,
  domain-model-change, diagram-update, and SDD-audit workflows. Every generated
  pack must list required files, candidate files, blocked read scopes, max
  candidate counts, index status, fallback/degraded behavior, and observable
  next actions.
- AC-008: Workbench UI can show standard compliance and context-pack previews.
- AC-009: Doctor checks can report missing artifacts, invalid metadata,
  unlinked tasks, stale indexes, and unsafe baseline edits.
- AC-010: SAT can adopt the standard as a pilot through project-specific domain
  declarations.
- AC-011: Documentation explains how another project adopts and applies the
  standard to its own domain.
- AC-012: `workbench-sdd/v1` can be resolved from
  `backend/app/infrastructure/config/sdd_standards/workbench-sdd/v1.yaml` by
  backend code, doctor scripts, Workbench prompts, and LLM instructions; unknown
  versions produce a structured error before write flows run.
- AC-013: Bootstrap write tasks are blocked until standard resolution, manifest
  validation, template validation, and scaffold dry-run validation pass.
- AC-014: Project-owned `sdd.context_rules` are validated, merged in the order
  Workbench default -> project profile -> project override, and cannot disable
  required Workbench safety rules.
- AC-015: Mermaid diagram files are checked for supported notation and
  syntax/renderability where the configured renderer is available; failures are
  reported as validation output and do not crash the Workbench.
- AC-016: Implementation is blocked until reviewer feedback has been addressed
  in the SDD documents and a final self-review pass records that the documents
  are ready for implementation slicing.

## Open Questions

- Should generated `.sdd/*.yaml` files be committed by default, or regenerated
  locally and ignored?
- Should context retrieval remain YAML plus file scanning first, or should a
  later phase add SQLite/FTS storage?
- Should project profiles live in the package, backend, or repo-local
  configuration?
- Should baseline diagram promotion require an ADR for every project, or only
  for protected artifacts declared in `codex-bridge.yaml`?
