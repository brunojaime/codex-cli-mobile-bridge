# Slice 5: Codex Actions From Specs

## Goal

Let the user start useful Codex workflows from the SDD workbench.

## Actions

- Update spec from feedback.
- Update plan from spec changes.
- Update tasks from plan changes.
- Update diagram from marked diagram feedback.
- Start implementation from a task.
- Run SDD doctor and summarize failures.

## Done When

- Actions are tied to explicit SDD artifacts.
- Generated prompts include workspace, spec id, file path, diagram selection,
  feedback id, and selected context when available.
- Actions do not run automatically without user intent.
- Action results link back to the originating spec, task, feedback item, or
  diagram mark.
