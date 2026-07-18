# UX Agent Lane Plan

## Phase 1: Model And Skill Binding

- Add first-class `ux_generator` and `ux_reviewer` ids/types.
- Add `required_skills` to agent configuration and API schemas.
- Resolve `visual-ux-polish` at run time and inject its required references.
- Add fail-closed `ux_skill_unavailable` behavior.

## Phase 2: Lane Sequencing

- Add `generator_reviewer_ux` or equivalent workflow option.
- Add a pre-Project-Factory lightweight `ux_generator` planning pass.
- Sequence post-baseline work as
  `baseline_generator -> baseline_reviewer -> ux_generator -> ux_reviewer`.
- Stop automatic New Project work after the post-baseline UX reviewer returns
  complete or blocked.
- Preserve existing solo, review, triad, supervisor, and Domain Factory flows
  when UX lane is not selected.

## Phase 2b: Manual Slash UX Commands

- Add `/ux` for a generator-only UX pass on the current project.
- Add `/ux-full` for a UX generator/reviewer loop.
- Set `/ux-full` default maximum iterations to 15.
- Let `ux_reviewer` decide early stop through complete/continue/blocked status.
- Keep no-functionality boundaries for both commands.

## Phase 3: UX Evidence

- Generate UX brief from New Project and Domain Factory contracts.
- Persist benchmark, screenshots, UAT scenarios, generator report, and reviewer
  report under `.codex/ux/`.
- Attach UX evidence artifacts to run/session projections.
- Render UX lane state and evidence in mobile/workbench UI.

## Phase 4: Validation And Gates

- Add UX path allow/deny rules.
- Add screenshot and mechanical visual checks where app execution is available.
- Add UX reviewer JSON parsing and continuation prompts.
- Fail pre-release UX gate on unresolved blocker/major issues or missing primary
  evidence unless the user explicitly overrides.

## Phase 5: Regression Coverage

- Test agent model/schema compatibility.
- Test required-skill resolution and fail-closed behavior.
- Test lane sequencing and reviewer continuation.
- Test `/ux` and `/ux-full` slash dispatch, iteration limits, and reviewer stop.
- Test UX scope enforcement.
- Test mobile UX lane state and evidence rendering.
