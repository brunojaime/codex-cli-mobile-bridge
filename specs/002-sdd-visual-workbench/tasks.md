# Tasks

## Slice 1: SDD Explorer

- [x] Add a dev-mode workbench entry point in `MaterialApp.builder`.
- [x] Load `/sdd/projects` only in the bridge/control app context.
- [x] Load `/sdd/project?workspace_path=...` for the selected/current project.
- [x] Load `/sdd/project/diagrams?workspace_path=...` for diagram source and
      metadata.
- [x] Display constitution, specs, plans, tasks, and diagram source.
- [x] Show missing, oversized, or unreadable SDD artifacts.
- [x] Keep `ChatScreen` product behavior unchanged.

## Slice 2: Diagram Rendering

- [x] Choose a dev-mode Mermaid rendering approach.
- [x] Render component, deployment, sequence, class, ER, and use case diagrams.
- [ ] Provide full-screen diagram inspection.
- [x] Let users switch between source and rendered preview.
- [ ] Support selecting or marking diagram nodes, edges, and regions.
- [x] Treat render failures as validation feedback, not app crashes.

## Slice 3: Architecture UX

- [x] Add tabs for Overview, Specs, Diagrams, and SDD files.
- [x] Add diagram-family filters.
- [ ] Add search across specs, tasks, actors, components, entities, and diagrams.
- [x] Add project-local architecture health indicators.
- [x] Add clear empty and invalid states.

## Slice 4: Feedback Linked To Specs And Diagrams

- [x] Extend feedback metadata with optional SDD references.
- [ ] Add diagram region selection and annotation.
- [ ] Capture diagram node and edge selection metadata when available.
- [x] Link feedback to diagram files and SDD artifacts when available.
- [ ] Show feedback grouped by spec, component, actor, entity, and diagram.
- [x] Keep production feedback behavior unchanged when dev mode is off.

## Slice 5: Codex Actions From Specs

- [x] Add actions to ask Codex to update a spec.
- [x] Add actions to ask Codex to update a plan or tasks.
- [x] Add actions to ask Codex to update a diagram from linked feedback.
- [ ] Add actions to start an implementation session from a task.
- [ ] Add actions to run the SDD doctor and summarize results.

## Slice 6: Current Project Dashboard

- [x] Add a project-local dashboard for the current project.
- [x] Summarize only the current project's specs, diagrams, feedback, and tasks.
- [x] In inherited apps, do not show other projects.
- [ ] In the bridge/control app, allow selecting a project before opening the
      project-local dashboard.
- [ ] Surface diagram coverage by required diagram family.
- [ ] Surface real Android release, updater, backend, and feedback
      configuration references for the selected/current project when available.
- [x] Keep the dashboard out of downstream repos except for the SDD contract
      files they expose.
