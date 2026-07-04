# SDD Visual Workbench

## Intent

Build the development-mode visual workbench for Codex Mobile Bridge. The
workbench lets a user inspect and validate the living SDD artifacts of the
current project: specs, plans, tasks, architecture diagrams, feedback, and
Codex actions.

The workbench is visible only when the frontend is compiled with:

```text
CODEX_BRIDGE_DEV_MODE=true
```

When the flag is disabled, the product UI must be returned unchanged.

The workbench reads real project SDD files and real Bridge configuration. It
must not introduce mock data, seeded demo state, local demo mode, placeholder
backend URLs, or fake update paths.

## Scope

This spec covers the visual SDD experience inside the Codex CLI Mobile Bridge
app and the reusable conventions that project apps inherit.

The project dashboard is local to the current project context. It must not
become a cross-project dashboard inside every inherited app. A project app
should explain its own specs, diagrams, feedback, and architecture only.

The Codex CLI Mobile Bridge app may still list projects because it is the
bridge/control app. That listing is not part of the per-project inherited
dashboard contract.

## Required Diagram Types

Every project should be able to carry these diagram families as source files:

- Component diagram: components involved and their relationships.
- Deployment diagram: where each component physically or operationally lives,
  such as device, local host, VPS, AWS, GitHub Actions, storage, or external
  services.
- Sequence diagram: interaction order across actors, frontend, backend,
  services, and Codex agents.
- Class diagram: important software classes, models, services, and their
  relationships.
- Entity relationship diagram: persisted entities, external records, and
  logical data relationships.
- Use case diagram: users, roles, and their goals.

The project may be a monolith, a microservice system, or a hybrid. The
workbench must not force a hard classification now. The diagram model should
stay extensible enough to represent those shapes later.

## Diagram Feedback

Diagrams are validation surfaces. Users must be able to inspect, mark, and
request changes on a diagram in the same spirit as visual app feedback.

The workbench should eventually allow a user to:

- Select or mark a diagram node, edge, or region.
- Attach a comment to that region.
- Link the comment to a spec, task, component, actor, entity, or sequence step.
- Send the marked diagram feedback into Codex workflows.
- Iterate with Codex until the diagram communicates the intended architecture.

The stored context must be specific enough to identify the current workspace,
diagram file, selected node/edge/region, requested change, related spec or
task, feedback item, and Codex action that should resolve it.

## Acceptance Criteria

- A dev-mode workbench is available only through `CODEX_BRIDGE_DEV_MODE`.
- The first screen can inspect SDD artifacts read from the existing backend
  endpoints.
- The workbench communicates missing or invalid SDD artifacts without breaking
  the normal app.
- Diagram support is based on diagram-as-code source files, with `.mmd` as the
  current source of truth.
- Diagram families use software engineering and UML-oriented nomenclature.
- Feedback can evolve from app screenshots to diagram annotations without
  changing the production app behavior.
- Slice 6 is a project-local dashboard, not a dashboard about other projects
  inside every inherited app.
- The dashboard can mention real Android release, updater, backend, and
  feedback configuration references for the current project when those
  references exist.
- The workbench never treats feedback/edit mode as permission to use mock
  data or placeholder URLs.
