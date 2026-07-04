# Slice 6: Current Project Dashboard

## Goal

Create a dashboard for the project currently being inspected.

## Scope Rule

Inherited project apps must not show dashboards about other projects. They only
show their own current project's SDD state.

The Codex CLI Mobile Bridge app may show project selection because it is the
control app. Once a project is selected, the dashboard content is still scoped
to that project.

## Dashboard Content

- SDD contract status.
- Required diagram coverage.
- Open specs and tasks.
- Feedback linked to this project.
- Recent Codex actions for this project.
- Doctor status for this project.
- Real Android release, updater, backend, and feedback configuration
  references for this project when available.

## Done When

- The dashboard answers: "What is the state of this project?"
- It does not answer: "What is happening across all projects?" except in the
  bridge/control app project picker context.
- Downstream repos only need to expose SDD files and real configuration; they
  do not need to copy the Bridge dashboard implementation.
