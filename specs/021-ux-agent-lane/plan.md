# UX Agent Lane Plan

## Current Implementation Status

This spec is implemented as a label-based MVP slice. The shipped behavior uses
the existing `generator` and `reviewer` agent ids with UX labels/prompts,
workspace-guarded `/ux` and `/ux-full` slash commands, a Project Factory
pre-planning UX brief, fail-closed `visual-ux-polish` loading, one automatic
post-baseline UX generator step, one UX reviewer step, and a local UX evidence
index.

The first-class UX lane below remains the target architecture unless a phase is
marked as shipped in MVP.

## Phase 1: Model And Skill Binding

MVP status: partially shipped. The backend Project Factory runner resolves the
`visual-ux-polish` skill and required references before UX phases, and fails
closed with `ux_skill_unavailable` when it cannot load them. First-class
`ux_generator` and `ux_reviewer` ids/types and per-agent required-skill schema
fields remain deferred.

- Add first-class `ux_generator` and `ux_reviewer` ids/types.
- Add `required_skills` to agent configuration and API schemas.
- Resolve `visual-ux-polish` at run time and inject its required references.
- Add fail-closed `ux_skill_unavailable` behavior.

## Phase 2: Lane Sequencing

MVP status: partially shipped for Project Factory only. A lightweight UX brief
runs before planning, downstream prompts explicitly require that brief, and one
post-baseline UX generator/reviewer pass runs after the baseline. Backend
reviewer JSON parsing, continuation routing, lifecycle states, and Domain
Factory sequencing remain deferred.

- Add `generator_reviewer_ux` or equivalent workflow option.
- Add a pre-Project-Factory lightweight `ux_generator` planning pass.
- Sequence post-baseline work as
  `baseline_generator -> baseline_reviewer -> ux_generator -> ux_reviewer`.
- Stop automatic New Project work after the post-baseline UX reviewer returns
  complete or blocked.
- Preserve existing solo, review, triad, supervisor, and Domain Factory flows
  when UX lane is not selected.

## Phase 2b: Manual Slash UX Commands

MVP status: shipped as label-based slash behavior. `/ux` and `/ux-full` require
an active backend and a selected project chat with a real workspace. `/ux-full`
sets the existing reviewer loop budget to 15. UX-specific backend lifecycle
states for these manual commands remain deferred.

- Add `/ux` for a generator-only UX pass on the current project.
- Add `/ux-full` for a UX generator/reviewer loop.
- Set `/ux-full` default maximum iterations to 15.
- Let `ux_reviewer` decide early stop through complete/continue/blocked status.
- Keep no-functionality boundaries for both commands.

## Phase 3: UX Evidence

MVP status: partially shipped. Prompts require UX benchmark, screenshot, UAT,
generator report, and reviewer report evidence under `.codex/ux/`, and the
runner writes `.codex/ux/evidence-index.json` for artifacts present there.
Evidence projection through API/session state and mobile/workbench rendering
remain deferred.

- Generate UX brief from New Project and Domain Factory contracts.
- Persist benchmark, screenshots, UAT scenarios, generator report, and reviewer
  report under `.codex/ux/`.
- Attach UX evidence artifacts to run/session projections.
- Render UX lane state and evidence in mobile/workbench UI.

## Phase 4: Validation And Gates

MVP status: prompt-level only, except for required skill loading. Mechanical
visual checks, UX scope allow/deny enforcement, reviewer JSON parsing, and
release gates remain deferred.

- Add UX path allow/deny rules.
- Add screenshot and mechanical visual checks where app execution is available.
- Add UX reviewer JSON parsing and continuation prompts.
- Fail pre-release UX gate on unresolved blocker/major issues or missing primary
  evidence unless the user explicitly overrides.

## Phase 5: Regression Coverage

MVP status: focused regression coverage exists for slash command enablement,
Project Factory prompt/brief/skill loading, fail-closed skill behavior, and
empty guided-intake hydration. Full-lane schema, lifecycle, evidence UI, scope,
and release-gate tests remain deferred.

- Test agent model/schema compatibility.
- Test required-skill resolution and fail-closed behavior.
- Test lane sequencing and reviewer continuation.
- Test `/ux` and `/ux-full` slash dispatch, iteration limits, and reviewer stop.
- Test UX scope enforcement.
- Test mobile UX lane state and evidence rendering.
