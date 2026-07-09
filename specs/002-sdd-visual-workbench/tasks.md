# Tasks

This file is the legacy task index. Task numbering is local to each plan in `tree.json`.

## Plan 1: SDD Explorer

- [x] Add a dev-mode workbench entry point in MaterialApp.builder. ([Task 1](./tasks/plan-1-task-1/task.md))
- [x] Load /sdd/projects only in the bridge/control app context. ([Task 2](./tasks/plan-1-task-2/task.md))
- [x] Load /sdd/project?workspace_path=... for the selected/current project. ([Task 3](./tasks/plan-1-task-3/task.md))
- [x] Load /sdd/project/diagrams?workspace_path=... for diagram source and metadata. ([Task 4](./tasks/plan-1-task-4/task.md))
- [x] Display constitution, specs, plans, tasks, and diagram source. ([Task 5](./tasks/plan-1-task-5/task.md))
- [x] Show missing, oversized, or unreadable SDD artifacts. ([Task 6](./tasks/plan-1-task-6/task.md))
- [x] Keep ChatScreen product behavior unchanged. ([Task 7](./tasks/plan-1-task-7/task.md))

## Plan 2: Diagram Rendering

- [x] Choose a dev-mode Mermaid rendering approach. ([Task 1](./tasks/plan-2-task-1/task.md))
- [x] Render component, deployment, sequence, class, ER, and use case diagrams. ([Task 2](./tasks/plan-2-task-2/task.md))
- [x] Provide full-screen diagram inspection. ([Task 3](./tasks/plan-2-task-3/task.md))
- [x] Let users switch between source and rendered preview. ([Task 4](./tasks/plan-2-task-4/task.md))
- [x] Support selecting or marking diagram nodes, edges, and regions. ([Task 5](./tasks/plan-2-task-5/task.md))
- [x] Treat render failures as validation feedback, not app crashes. ([Task 6](./tasks/plan-2-task-6/task.md))

## Plan 3: Architecture UX

- [x] Add tabs for Overview, Specs, Diagrams, and SDD files. ([Task 1](./tasks/plan-3-task-1/task.md))
- [x] Add diagram-family filters. ([Task 2](./tasks/plan-3-task-2/task.md))
- [x] Add search across specs, tasks, actors, components, entities, and diagrams. ([Task 3](./tasks/plan-3-task-3/task.md))
- [x] Add project-local architecture health indicators. ([Task 4](./tasks/plan-3-task-4/task.md))
- [x] Add clear empty and invalid states. ([Task 5](./tasks/plan-3-task-5/task.md))

## Plan 4: Feedback Linked To Specs And Diagrams

- [x] Extend feedback metadata with optional SDD references. ([Task 1](./tasks/plan-4-task-1/task.md))
- [x] Add diagram region selection and annotation. ([Task 2](./tasks/plan-4-task-2/task.md))
- [x] Capture diagram node and edge selection metadata when available. ([Task 3](./tasks/plan-4-task-3/task.md))
- [x] Link feedback to diagram files and SDD artifacts when available. ([Task 4](./tasks/plan-4-task-4/task.md))
- [x] Show feedback grouped by spec, component, actor, entity, and diagram. ([Task 5](./tasks/plan-4-task-5/task.md))
- [x] Keep production feedback behavior unchanged when dev mode is off. ([Task 6](./tasks/plan-4-task-6/task.md))

## Plan 5: Codex Actions From Specs

- [x] Add actions to ask Codex to update a spec. ([Task 1](./tasks/plan-5-task-1/task.md))
- [x] Add actions to ask Codex to update a plan or tasks. ([Task 2](./tasks/plan-5-task-2/task.md))
- [x] Add actions to ask Codex to update a diagram from linked feedback. ([Task 3](./tasks/plan-5-task-3/task.md))
- [x] Add actions to start an implementation session from a task. ([Task 4](./tasks/plan-5-task-4/task.md))
- [x] Add actions to run the SDD doctor and summarize results. ([Task 5](./tasks/plan-5-task-5/task.md))

## Plan 6: Current Project Dashboard

- [x] Add a project-local dashboard for the current project. ([Task 1](./tasks/plan-6-task-1/task.md))
- [x] Summarize only the current project's specs, diagrams, feedback, and tasks. ([Task 2](./tasks/plan-6-task-2/task.md))
- [x] In inherited apps, do not show other projects. ([Task 3](./tasks/plan-6-task-3/task.md))
- [x] In the bridge/control app, allow selecting a project before opening the project-local dashboard. ([Task 4](./tasks/plan-6-task-4/task.md))
- [x] Surface diagram coverage by required diagram family. ([Task 5](./tasks/plan-6-task-5/task.md))
- [x] Surface real Android release, updater, backend, and feedback configuration references for the selected/current project when available. ([Task 6](./tasks/plan-6-task-6/task.md))
- [x] Keep the dashboard out of downstream repos except for the SDD contract files they expose. ([Task 7](./tasks/plan-6-task-7/task.md))
