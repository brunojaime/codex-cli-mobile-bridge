# Tasks

## Phase 1: Workbench SDD Standard

- [x] T001 Add the source-of-truth standard artifact at
      `backend/app/infrastructure/config/sdd_standards/workbench-sdd/v1.yaml`.
- [x] T002 Add `backend/app/application/services/sdd_standard_service.py` with a
      read-only loader for `workbench-sdd/v1`.
- [x] T003 Add standard loader fixtures under
      `tests/fixtures/sdd_standards/`.
- [x] T004 Add tests covering successful `workbench-sdd/v1` resolution,
      missing artifact errors, and unknown-version errors.
- [x] T005 Define in the standard artifact: artifact taxonomy, spec lifecycle,
      required metadata, diagram taxonomy, traceability schema, context pack
      names, index schemas, and LLM rules.
- [x] T006 Add compatibility rules to the loader: v1 is supported, v1.x is
      backward-compatible, unknown major versions are hard errors for write,
      context, indexing, and Codex action flows.
- [x] T007 Add a documented serialized standard payload shape that Workbench
      prompts and future package exports can use without rereading arbitrary
      files.
- [x] T008 Add LLM-facing standard resolution instructions to the prompt/source
      template used by Workbench Codex actions.

## Phase 2: Project Manifest Adoption And Early Validation

- [x] T009 Extend the backend manifest parser to accept `sdd.standard`,
      `sdd.project_type`, `sdd.domain_root`, `sdd.data_root`,
      `sdd.generated_index_root`, `sdd.protected_baseline`, and
      `sdd.context_rules`.
- [x] T010 Preserve backward compatibility with existing manifest fields:
      `constitution`, `specs`, `architecture`, `requiredDiagramCategories`,
      and `diagramChangeRequests`.
- [x] T011 Define the `sdd.context_rules` schema for domain-to-module mappings,
      preferred context files, excluded paths, stricter candidate limits, and
      protected baseline overrides.
- [x] T012 Implement context rule merge precedence in the manifest layer:
      Workbench default -> project profile -> project overrides.
- [x] T013 Validate that project overrides cannot disable mandatory Workbench
      safety rules: manifest-first resolution, baseline impact gates,
      no-broad-read behavior, and unknown-version hard failures.
- [x] T014 Add manifest fixtures for legacy, valid v1, invalid standard,
      invalid context rules, and protected baseline override cases.
- [x] T015 Add tests for manifest parsing, compatibility warnings, context-rule
      merge output, and invalid override errors.
- [x] T016 Add CLI/doctor output for manifest adoption validation before any
      scaffold write command is available.

## Phase 3: Preflight Validation And New Project Scaffolding

- [x] T017 Add a preflight validator service for standard resolution, manifest
      adoption, required roots, template availability, and scaffold eligibility.
- [x] T018 Add a scaffold planner that produces a dry-run plan only: created,
      existing, skipped, blocked, and would-overwrite artifacts.
- [x] T019 Add dry-run fixtures for empty repo, partial SDD repo, existing
      custom files, legacy manifest, and invalid standard version.
- [x] T020 Add tests that prove dry-run validation blocks writes when standard,
      manifest, template, or path-safety validation fails.
- [x] T021 Add a bootstrap write flow only after T017-T020 pass, using the dry
      run plan as the write contract.
- [x] T022 Create missing `.specify/memory/constitution.md`,
      `architecture/overview.md`, `domain/glossary.md`,
      `data/persistence-model.md`, `specs/`, and `.sdd/` only when absent.
- [x] T023 Detect existing artifacts and avoid overwriting user content.
- [x] T024 Return a bootstrap summary with created, existing, skipped, blocked,
      and next-action sections.
- [x] T025 Add tests for bootstrap idempotency, non-destructive behavior,
      path-safety, and blocked writes.

## Phase 4: Documentation Templates

- [x] T026 Add template for project constitution.
- [x] T027 Add templates for architecture overview and ADRs.
- [x] T028 Add templates for domain glossary and domain model notes.
- [x] T029 Add templates for data model, entity relationship notes, and
      persistence notes.
- [x] T030 Add templates for `spec.md`, `plan.md`, `tasks.md`, and
      `traceability.yaml`.
- [x] T031 Add diagram metadata templates for baseline and feature-local
      diagrams.
- [x] T032 Add template usage tests or snapshot fixtures.

## Phase 5: Diagram Taxonomy And Governance

- [x] T033 Define diagram taxonomy: system-context, components, deployment,
      sequence, state, domain-model, entity-relationship, component-impact,
      domain-impact, and data-impact.
- [x] T034 Define Mermaid notation requirements for each diagram type.
- [x] T035 Add baseline diagram protection policies.
- [x] T036 Add feature-local impact diagram rules.
- [x] T037 Add validation for diagram metadata and unsupported diagram types.
- [x] T038 Add Mermaid syntax/render validation where the configured renderer is
      available; report failures as validation output without crashing.

## Phase 6: SDD Indexer

- [x] T039 Generate `.sdd/spec-index.yaml` from feature spec metadata and
      summaries.
- [x] T040 Generate `.sdd/diagram-index.yaml` from baseline and feature diagram
      metadata.
- [x] T041 Generate `.sdd/module-index.yaml` from manifest roots,
      context_rules, and spec-declared affected modules.
- [x] T042 Generate `.sdd/context-index.yaml` for context pack routing.
- [x] T043 Add freshness markers using source paths, mtimes or hashes, standard
      version, and manifest digest.
- [x] T044 Add missing/stale index detection with observable states:
      `fresh`, `missing`, `stale`, `regenerated`, and `failed`.
- [x] T045 Add deterministic index regeneration before context pack selection.
- [x] T046 Add tests for large spec sets proving fresh-index routing does not
      read every spec body.
- [x] T047 Add tests for missing, stale, regenerated, and failed index outputs.

## Phase 7: Context Pack Engine

- [x] T048 Define context pack preset schema.
- [x] T049 Implement `new-feature` context pack with required files:
      manifest, standard payload, constitution, context index, and architecture
      overview when present.
- [x] T050 Implement `modify-existing-feature` context pack with selected spec,
      plan, tasks, traceability, and max 5 related specs.
- [x] T051 Implement `bugfix` context pack with selected modules, relevant
      specs, test paths, and blocked broad spec reads.
- [x] T052 Implement `architecture-change` context pack with protected baseline
      files, ADR requirement, and max 3 related diagrams.
- [x] T053 Implement `data-model-change` and `domain-model-change` context
      packs with data/domain baselines and feature-local impact diagram rules.
- [x] T054 Implement `implementation-from-spec`, `diagram-update`, and
      `sdd-audit` context packs.
- [x] T055 Add degraded mode for failed index regeneration: selected artifact
      only, required baseline files only, no all-spec fallback, and explicit
      next action.
- [x] T056 Add hard-failure behavior for actions that cannot safely run without
      indexes or selected artifacts.
- [x] T057 Add tests for required files, max candidate counts, blocked-read
      scopes, degraded mode, and hard failures.

## Phase 8: LLM Operating Instructions

- [x] T058 Update Workbench Codex action prompt builder to require manifest,
      standard payload, constitution, indexes, and context pack flow.
- [x] T059 Add prompt language that prevents reading all specs unless the
      context pack explicitly permits it.
- [x] T060 Add prompt language that protects baseline architecture, domain, and
      data artifacts.
- [x] T061 Add prompt language that preserves project-owned domain rules and
      context overrides.
- [x] T062 Add tests for generated prompts, including unknown-standard,
      stale-index, degraded-context, and protected-baseline scenarios.

## Phase 9: Workbench UI

- [x] T063 Add Project SDD Health view.
- [x] T064 Add Standards Compliance view.
- [x] T065 Add Feature Specs view with lifecycle and traceability status.
- [x] T066 Add Architecture, Domain, and Data Baseline views.
- [x] T067 Add Traceability Matrix view.
- [x] T068 Add Context Pack Preview view showing required files, candidates,
      blocked reads, index status, and degraded mode.
- [x] T069 Add Architecture/Domain/Data Impact Queue view.
- [x] T070 Add focused widget tests for the new views.

## Phase 10: Validators And Doctor Checks

- [x] T071 Expand doctor checks for manifest adoption fields.
- [x] T072 Validate required artifact presence.
- [x] T073 Validate spec and diagram metadata.
- [x] T074 Validate requirements-to-tasks traceability.
- [x] T075 Validate diagram taxonomy, Mermaid renderability where available,
      and baseline impact policies.
- [x] T076 Validate generated index freshness and regeneration output.
- [x] T077 Add doctor output for errors, warnings, degraded context, blocked
      actions, and next actions.
- [x] T078 Add backend and script tests for validation output.

## Phase 11: SAT Pilot Adoption

- [x] T079 Update SAT manifest to declare `workbench-sdd/v1` adoption.
- [x] T080 Add SAT-owned domains, roots, context rules, and protected baselines.
- [x] T081 Add or align SAT architecture, domain, data, specs, and indexes with
      the standard.
- [x] T082 Verify SAT uses Workbench generic behavior without SAT-specific
      platform code.
- [x] T083 Run SAT-focused Workbench tests.

## Phase 12: Adoption Documentation

- [x] T084 Document Workbench SDD adoption for new repos.
- [x] T085 Document artifact ownership boundaries.
- [x] T086 Document feature creation workflow.
- [x] T087 Document context pack behavior for LLMs, including stale/missing
      index behavior and blocked reads.
- [x] T088 Document baseline diagram governance.
- [x] T089 Document standard version resolution, compatibility, and upgrade
      behavior.
- [x] T090 Document SAT as a pilot example without making it normative.

## Review And Iteration

- [x] T091 Request reviewer pass on this spec, plan, tasks, traceability, and
      diagrams before implementation begins.
- [x] T092 Address reviewer findings in the SDD documents.
- [x] T093 Perform one additional self-review pass after reviewer feedback.
- [x] T094 Record that implementation remains blocked until the first
      implementation iteration is explicitly started.
- [x] T095 Split implementation into reviewer-friendly iterations.
