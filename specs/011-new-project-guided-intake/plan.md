# New Project Guided Intake Plan

## Plan 1: Intake Contract

- Define draft intake state.
- Define question and option models.
- Define answer sources, defaults, assumptions, confidence, and readiness.

## Plan 2: Backend Draft Persistence

- Persist guided intake state with drafts.
- Add or extend endpoints to answer questions, list pending questions, preview
  contracts, confirm contracts, and start builds.
- Keep existing draft and generate endpoints compatible.

## Plan 3: Intake Engine

- Compute missing required topics.
- Generate focused questions.
- Infer safe defaults and recommended options.
- Track blockers separately from defaults.

## Plan 4: Frontend Chat Experience

- Reuse the existing New Project entry.
- Render questions and recommended options in chat.
- Update draft state from option taps or free-text answers.
- Render contract preview, confirmation, and blocked states.

## Plan 5: Build Gate Integration

- Block build until confirmed.
- Route confirmed builds into the existing generator/reviewer workflow.
- Preserve asset, Workbench, web preview, release, and installable-app behavior.

## Plan 6: Validation

- Add backend state-machine and API tests.
- Add Flutter model/API/widget tests.
- Run Project Factory regression tests.
- Publish Android release only when frontend behavior ships.
