# UX Agent Lane Tasks

Status note: this spec is currently implemented as a label-based MVP. The
existing `generator` and `reviewer` ids are configured as `UX Generator` and
`UX Reviewer`; first-class `ux_generator`/`ux_reviewer` domain ids remain
deferred.

## Completed In MVP

- [x] T019 Add prompt builders for the label-based UX generator with product
      contract, UX brief requirement, required skill context, benchmark,
      screenshots, UAT, scope, and evidence paths.
- [x] T020 Add prompt builders for the label-based UX reviewer with strict JSON
      response schema for manual `/ux-full`, evidence review, scope rules, and
      reviewer stop guidance.
- [x] T036 Add pre-Project-Factory lightweight UX planning pass that creates UX
      direction without code changes.
- [x] T037 Add post-Project-Factory automatic UX generator and UX reviewer
      prompts with up to 10 passes and reviewer-controlled early stop.
- [x] T038 Add `/ux` slash command for manual generator-only UX pass in the
      current project.
- [x] T039 Add `/ux-full` slash command for manual UX generator/reviewer loop
      with default max 15 iterations.

## Partially Completed

- [ ] T003 Add a required-skill contract field for agent definitions and enforce
      `visual-ux-polish` for UX lane agents.
      MVP status: backend Project Factory runner now fails closed if the
      `visual-ux-polish` skill and required references cannot be loaded. A
      first-class per-agent required-skill field is not implemented.
- [ ] T012 Persist `.codex/ux/ux-brief.md` in generated project workspaces.
      MVP status: the runner requires `.codex/ux/pre-project-ux-brief.md` and
      writes `.codex/ux/evidence-index.json`; the exact `ux-brief.md` artifact
      name remains deferred.
- [ ] T013 Add benchmark evidence support under `.codex/ux/benchmark.md` and
      `.codex/ux/references/`.
      MVP status: prompts require these artifacts, but backend does not enforce
      or project them yet.
- [ ] T014 Add screenshot evidence storage under `.codex/ux/screenshots/`.
      MVP status: prompts require screenshots when the app can run, but backend
      does not enforce or project them yet.
- [ ] T015 Add UAT scenario evidence under `.codex/ux/uat-scenarios.md`.
      MVP status: prompts require UAT evidence, but backend does not enforce or
      project it yet.
- [ ] T016 Add UX generator report evidence under
      `.codex/ux/ux-generator-report.md`.
      MVP status: prompts require the report and evidence index discovers it if
      present.
- [ ] T017 Add UX reviewer report evidence under
      `.codex/ux/ux-reviewer-report.md`.
      MVP status: prompts require the report and evidence index discovers it if
      present.
- [ ] T040 Add reviewer-controlled stop handling for `/ux-full`, including
      early complete, continue, blocked, and iteration-limit states.
      MVP status: manual `/ux-full` uses the existing chat reviewer
      continue/complete loop with 15-turn budget. Automatic Project Factory UX
      now has a 10-pass reviewer-controlled stop; UX-specific blocked/lifecycle
      states are deferred.

## Deferred Target Architecture

- [ ] T001 Add `ux_generator` and `ux_reviewer` to the agent id/type domain
      model while preserving legacy agent ids.
- [ ] T002 Define default labels, prompts, visibility, max turns, and trigger
      intervals for both first-class UX agents.
- [ ] T004 Update API schemas and validation so first-class UX lane agents are
      accepted without breaking generator/reviewer/summary requirements.
- [ ] T005 Add an agent preset or workflow option for
      `generator_reviewer_ux` lane sequencing.
- [ ] T006 Add deterministic lane sequencing for
      `domain_generator -> domain_reviewer -> ux_generator -> ux_reviewer`.
- [ ] T007 Add deterministic lane sequencing for
      `baseline_generator -> baseline_reviewer -> ux_generator -> ux_reviewer`.
- [ ] T008 Define UX scope allow/deny path rules for generated Flutter/web
      projects and Bridge-owned artifacts.
- [ ] T009 Add reviewer checks that flag UX scope violations against protected
      backend, auth, RBAC, persistence, release, and runtime files.
- [ ] T010 Create the UX brief builder from New Project and Domain Factory
      contracts.
- [ ] T011 Allow UX agents to ask only missing UX-critical intake questions
      before build approval.
- [ ] T018 Attach UX evidence artifacts to agent run records and expose them
      through the session detail API.
- [ ] T021 Parse and validate automatic backend UX reviewer JSON responses into
      complete, continue, or blocked lane states.
- [ ] T022 Route automatic backend UX reviewer `continue` responses back to
      `ux_generator` with the continuation prompt.
- [ ] T023 Add UX lane lifecycle states to backend run/session projections.
- [ ] T024 Render UX lane state, benchmark summary, screenshots, UAT scenarios,
      and reviewer findings in the mobile/workbench UI.
- [ ] T025 Add or integrate Playwright/visual capture tooling for web previews
      when available.
- [ ] T026 Add Flutter screenshot or widget validation hooks for mobile-first
      generated apps when available.
- [ ] T027 Add mechanical visual checks for overflow, clipped content, small
      touch targets, focus visibility, and sticky overlay obstruction.
- [ ] T028 Ensure UX release gate fails on unresolved blocker/major findings or
      missing primary UX evidence.
- [ ] T029 Ensure release-facing UX validation uses real preview/backend
      configuration and never enables mock/demo/local data unless explicitly
      requested.
- [ ] T030 Add backend tests for first-class agent model, schema validation,
      workflow sequencing, reviewer response parsing, and scope rules.
- [ ] T031 Add frontend tests for UX lane state rendering and evidence display.
- [ ] T032 Add integration tests or fixtures for New Project and Domain Factory
      runs that include the full UX lane.
- [ ] T033 Document the full UX lane operating model in Workbench or product
      docs.
- [ ] T034 Add migration or compatibility handling for existing sessions that
      have the old advisory `ux` specialist only.
- [ ] T035 Validate that existing solo, review, triad, supervisor, and Domain
      Factory workflows still run without UX lane when not selected.
