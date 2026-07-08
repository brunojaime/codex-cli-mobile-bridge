# Tasks

This file is the legacy task index. Task numbering is local to each plan in `tree.json`.

## Plan 1: Workbench SDD Standard

- [x] T001 Add the source-of-truth standard artifact at backend/app/infrastructure/config/sdd_standards/workbench-sdd/v1.yaml. ([Task 1](./tasks/plan-1-task-1/task.md))
- [x] T002 Add backend/app/application/services/sdd_standard_service.py with a read-only loader for workbench-sdd/v1. ([Task 2](./tasks/plan-1-task-2/task.md))
- [x] T003 Add standard loader fixtures under tests/fixtures/sdd_standards/. ([Task 3](./tasks/plan-1-task-3/task.md))
- [x] T004 Add tests covering successful workbench-sdd/v1 resolution, missing artifact errors, and unknown-version errors. ([Task 4](./tasks/plan-1-task-4/task.md))
- [x] T005 Define in the standard artifact: artifact taxonomy, spec lifecycle, required metadata, diagram taxonomy, traceability schema, context pack names, index schemas, and LLM rules. ([Task 5](./tasks/plan-1-task-5/task.md))
- [x] T006 Add compatibility rules to the loader: v1 is supported, v1.x is backward-compatible, unknown major versions are hard errors for write, context, indexing, and Codex action flows. ([Task 6](./tasks/plan-1-task-6/task.md))
- [x] T007 Add a documented serialized standard payload shape that Workbench prompts and future package exports can use without rereading arbitrary files. ([Task 7](./tasks/plan-1-task-7/task.md))
- [x] T008 Add LLM-facing standard resolution instructions to the prompt/source template used by Workbench Codex actions. ([Task 8](./tasks/plan-1-task-8/task.md))

## Plan 2: Project Manifest Adoption

- [x] T009 Extend the backend manifest parser to accept sdd.standard, sdd.project_type, sdd.domain_root, sdd.data_root, sdd.generated_index_root, sdd.protected_baseline, and sdd.context_rules. ([Task 1](./tasks/plan-2-task-1/task.md))
- [x] T010 Preserve backward compatibility with existing manifest fields: constitution, specs, architecture, requiredDiagramCategories, and diagramChangeRequests. ([Task 2](./tasks/plan-2-task-2/task.md))
- [x] T011 Define the sdd.context_rules schema for domain-to-module mappings, preferred context files, excluded paths, stricter candidate limits, and protected baseline overrides. ([Task 3](./tasks/plan-2-task-3/task.md))
- [x] T012 Implement context rule merge precedence in the manifest layer: Workbench default -> project profile -> project overrides. ([Task 4](./tasks/plan-2-task-4/task.md))
- [x] T013 Validate that project overrides cannot disable mandatory Workbench safety rules: manifest-first resolution, baseline impact gates, no-broad-read behavior, and unknown-version hard failures. ([Task 5](./tasks/plan-2-task-5/task.md))
- [x] T014 Add manifest fixtures for legacy, valid v1, invalid standard, invalid context rules, and protected baseline override cases. ([Task 6](./tasks/plan-2-task-6/task.md))
- [x] T015 Add tests for manifest parsing, compatibility warnings, context-rule merge output, and invalid override errors. ([Task 7](./tasks/plan-2-task-7/task.md))
- [x] T016 Add CLI/doctor output for manifest adoption validation before any scaffold write command is available. ([Task 8](./tasks/plan-2-task-8/task.md))

## Plan 3: Preflight Validation And Scaffolding

- [x] T017 Add a preflight validator service for standard resolution, manifest adoption, required roots, template availability, and scaffold eligibility. ([Task 1](./tasks/plan-3-task-1/task.md))
- [x] T018 Add a scaffold planner that produces a dry-run plan only: created, existing, skipped, blocked, and would-overwrite artifacts. ([Task 2](./tasks/plan-3-task-2/task.md))
- [x] T019 Add dry-run fixtures for empty repo, partial SDD repo, existing custom files, legacy manifest, and invalid standard version. ([Task 3](./tasks/plan-3-task-3/task.md))
- [x] T020 Add tests that prove dry-run validation blocks writes when standard, manifest, template, or path-safety validation fails. ([Task 4](./tasks/plan-3-task-4/task.md))
- [x] T021 Add a bootstrap write flow only after T017-T020 pass, using the dry run plan as the write contract. ([Task 5](./tasks/plan-3-task-5/task.md))
- [x] T022 Create missing .specify/memory/constitution.md, architecture/overview.md, domain/glossary.md, data/persistence-model.md, specs/, and .sdd/ only when absent. ([Task 6](./tasks/plan-3-task-6/task.md))
- [x] T023 Detect existing artifacts and avoid overwriting user content. ([Task 7](./tasks/plan-3-task-7/task.md))
- [x] T024 Return a bootstrap summary with created, existing, skipped, blocked, and next-action sections. ([Task 8](./tasks/plan-3-task-8/task.md))
- [x] T025 Add tests for bootstrap idempotency, non-destructive behavior, path-safety, and blocked writes. ([Task 9](./tasks/plan-3-task-9/task.md))

## Plan 4: Documentation Templates

- [x] T026 Add template for project constitution. ([Task 1](./tasks/plan-4-task-1/task.md))
- [x] T027 Add templates for architecture overview and ADRs. ([Task 2](./tasks/plan-4-task-2/task.md))
- [x] T028 Add templates for domain glossary and domain model notes. ([Task 3](./tasks/plan-4-task-3/task.md))
- [x] T029 Add templates for data model, entity relationship notes, and persistence notes. ([Task 4](./tasks/plan-4-task-4/task.md))
- [x] T030 Add templates for spec.md, plan.md, tasks.md, and traceability.yaml. ([Task 5](./tasks/plan-4-task-5/task.md))
- [x] T031 Add diagram metadata templates for baseline and feature-local diagrams. ([Task 6](./tasks/plan-4-task-6/task.md))
- [x] T032 Add template usage tests or snapshot fixtures. ([Task 7](./tasks/plan-4-task-7/task.md))

## Plan 5: Diagram Taxonomy And Governance

- [x] T033 Define diagram taxonomy: system-context, components, deployment, sequence, state, domain-model, entity-relationship, component-impact, domain-impact, and data-impact. ([Task 1](./tasks/plan-5-task-1/task.md))
- [x] T034 Define Mermaid notation requirements for each diagram type. ([Task 2](./tasks/plan-5-task-2/task.md))
- [x] T035 Add baseline diagram protection policies. ([Task 3](./tasks/plan-5-task-3/task.md))
- [x] T036 Add feature-local impact diagram rules. ([Task 4](./tasks/plan-5-task-4/task.md))
- [x] T037 Add validation for diagram metadata and unsupported diagram types. ([Task 5](./tasks/plan-5-task-5/task.md))
- [x] T038 Add Mermaid syntax/render validation where the configured renderer is available; report failures as validation output without crashing. ([Task 6](./tasks/plan-5-task-6/task.md))

## Plan 6: SDD Indexer

- [x] T039 Generate .sdd/spec-index.yaml from feature spec metadata and summaries. ([Task 1](./tasks/plan-6-task-1/task.md))
- [x] T040 Generate .sdd/diagram-index.yaml from baseline and feature diagram metadata. ([Task 2](./tasks/plan-6-task-2/task.md))
- [x] T041 Generate .sdd/module-index.yaml from manifest roots, context_rules, and spec-declared affected modules. ([Task 3](./tasks/plan-6-task-3/task.md))
- [x] T042 Generate .sdd/context-index.yaml for context pack routing. ([Task 4](./tasks/plan-6-task-4/task.md))
- [x] T043 Add freshness markers using source paths, mtimes or hashes, standard version, and manifest digest. ([Task 5](./tasks/plan-6-task-5/task.md))
- [x] T044 Add missing/stale index detection with observable states: fresh, missing, stale, regenerated, and failed. ([Task 6](./tasks/plan-6-task-6/task.md))
- [x] T045 Add deterministic index regeneration before context pack selection. ([Task 7](./tasks/plan-6-task-7/task.md))
- [x] T046 Add tests for large spec sets proving fresh-index routing does not read every spec body. ([Task 8](./tasks/plan-6-task-8/task.md))
- [x] T047 Add tests for missing, stale, regenerated, and failed index outputs. ([Task 9](./tasks/plan-6-task-9/task.md))

## Plan 7: Context Pack Engine

- [x] T048 Define context pack preset schema. ([Task 1](./tasks/plan-7-task-1/task.md))
- [x] T049 Implement new-feature context pack with required files: manifest, standard payload, constitution, context index, and architecture overview when present. ([Task 2](./tasks/plan-7-task-2/task.md))
- [x] T050 Implement modify-existing-feature context pack with selected spec, plan, tasks, traceability, and max 5 related specs. ([Task 3](./tasks/plan-7-task-3/task.md))
- [x] T051 Implement bugfix context pack with selected modules, relevant specs, test paths, and blocked broad spec reads. ([Task 4](./tasks/plan-7-task-4/task.md))
- [x] T052 Implement architecture-change context pack with protected baseline files, ADR requirement, and max 3 related diagrams. ([Task 5](./tasks/plan-7-task-5/task.md))
- [x] T053 Implement data-model-change and domain-model-change context packs with data/domain baselines and feature-local impact diagram rules. ([Task 6](./tasks/plan-7-task-6/task.md))
- [x] T054 Implement implementation-from-spec, diagram-update, and sdd-audit context packs. ([Task 7](./tasks/plan-7-task-7/task.md))
- [x] T055 Add degraded mode for failed index regeneration: selected artifact only, required baseline files only, no all-spec fallback, and explicit next action. ([Task 8](./tasks/plan-7-task-8/task.md))
- [x] T056 Add hard-failure behavior for actions that cannot safely run without indexes or selected artifacts. ([Task 9](./tasks/plan-7-task-9/task.md))
- [x] T057 Add tests for required files, max candidate counts, blocked-read scopes, degraded mode, and hard failures. ([Task 10](./tasks/plan-7-task-10/task.md))

## Plan 8: LLM Operating Instructions

- [x] T058 Update Workbench Codex action prompt builder to require manifest, standard payload, constitution, indexes, and context pack flow. ([Task 1](./tasks/plan-8-task-1/task.md))
- [x] T059 Add prompt language that prevents reading all specs unless the context pack explicitly permits it. ([Task 2](./tasks/plan-8-task-2/task.md))
- [x] T060 Add prompt language that protects baseline architecture, domain, and data artifacts. ([Task 3](./tasks/plan-8-task-3/task.md))
- [x] T061 Add prompt language that preserves project-owned domain rules and context overrides. ([Task 4](./tasks/plan-8-task-4/task.md))
- [x] T062 Add tests for generated prompts, including unknown-standard, stale-index, degraded-context, and protected-baseline scenarios. ([Task 5](./tasks/plan-8-task-5/task.md))

## Plan 9: Workbench UI

- [x] T063 Add Project SDD Health view. ([Task 1](./tasks/plan-9-task-1/task.md))
- [x] T064 Add Standards Compliance view. ([Task 2](./tasks/plan-9-task-2/task.md))
- [x] T065 Add Feature Specs view with lifecycle and traceability status. ([Task 3](./tasks/plan-9-task-3/task.md))
- [x] T066 Add Architecture, Domain, and Data Baseline views. ([Task 4](./tasks/plan-9-task-4/task.md))
- [x] T067 Add Traceability Matrix view. ([Task 5](./tasks/plan-9-task-5/task.md))
- [x] T068 Add Context Pack Preview view showing required files, candidates, blocked reads, index status, and degraded mode. ([Task 6](./tasks/plan-9-task-6/task.md))
- [x] T069 Add Architecture/Domain/Data Impact Queue view. ([Task 7](./tasks/plan-9-task-7/task.md))
- [x] T070 Add focused widget tests for the new views. ([Task 8](./tasks/plan-9-task-8/task.md))

## Plan 10: Validators And Doctor Checks

- [x] T071 Expand doctor checks for manifest adoption fields. ([Task 1](./tasks/plan-10-task-1/task.md))
- [x] T072 Validate required artifact presence. ([Task 2](./tasks/plan-10-task-2/task.md))
- [x] T073 Validate spec and diagram metadata. ([Task 3](./tasks/plan-10-task-3/task.md))
- [x] T074 Validate requirements-to-tasks traceability. ([Task 4](./tasks/plan-10-task-4/task.md))
- [x] T075 Validate diagram taxonomy, Mermaid renderability where available, and baseline impact policies. ([Task 5](./tasks/plan-10-task-5/task.md))
- [x] T076 Validate generated index freshness and regeneration output. ([Task 6](./tasks/plan-10-task-6/task.md))
- [x] T077 Add doctor output for errors, warnings, degraded context, blocked actions, and next actions. ([Task 7](./tasks/plan-10-task-7/task.md))
- [x] T078 Add backend and script tests for validation output. ([Task 8](./tasks/plan-10-task-8/task.md))

## Plan 11: SAT Pilot Adoption

- [x] T079 Update SAT manifest to declare workbench-sdd/v1 adoption. ([Task 1](./tasks/plan-11-task-1/task.md))
- [x] T080 Add SAT-owned domains, roots, context rules, and protected baselines. ([Task 2](./tasks/plan-11-task-2/task.md))
- [x] T081 Add or align SAT architecture, domain, data, specs, and indexes with the standard. ([Task 3](./tasks/plan-11-task-3/task.md))
- [x] T082 Verify SAT uses Workbench generic behavior without SAT-specific platform code. ([Task 4](./tasks/plan-11-task-4/task.md))
- [x] T083 Run SAT-focused Workbench tests. ([Task 5](./tasks/plan-11-task-5/task.md))

## Plan 12: Adoption Documentation

- [x] T084 Document Workbench SDD adoption for new repos. ([Task 1](./tasks/plan-12-task-1/task.md))
- [x] T085 Document artifact ownership boundaries. ([Task 2](./tasks/plan-12-task-2/task.md))
- [x] T086 Document feature creation workflow. ([Task 3](./tasks/plan-12-task-3/task.md))
- [x] T087 Document context pack behavior for LLMs, including stale/missing index behavior and blocked reads. ([Task 4](./tasks/plan-12-task-4/task.md))
- [x] T088 Document baseline diagram governance. ([Task 5](./tasks/plan-12-task-5/task.md))
- [x] T089 Document standard version resolution, compatibility, and upgrade behavior. ([Task 6](./tasks/plan-12-task-6/task.md))
- [x] T090 Document SAT as a pilot example without making it normative. ([Task 7](./tasks/plan-12-task-7/task.md))

## Plan 13: Review And Iteration

- [x] T091 Request reviewer pass on this spec, plan, tasks, traceability, and diagrams before implementation begins. ([Task 1](./tasks/plan-13-task-1/task.md))
- [x] T092 Address reviewer findings in the SDD documents. ([Task 2](./tasks/plan-13-task-2/task.md))
- [x] T093 Perform one additional self-review pass after reviewer feedback. ([Task 3](./tasks/plan-13-task-3/task.md))
- [x] T094 Record that implementation remains blocked until the first implementation iteration is explicitly started. ([Task 4](./tasks/plan-13-task-4/task.md))
- [x] T095 Split implementation into reviewer-friendly iterations. ([Task 5](./tasks/plan-13-task-5/task.md))
