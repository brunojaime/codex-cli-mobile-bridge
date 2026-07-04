# Codex Bridge Constitution

SDD is mandatory for every project integrated with Codex Mobile Bridge.

## Principles

1. Every project has a living spec structure before user-installable behavior
   is released.
2. Feedback, implementation tasks, architecture diagrams, and release behavior
   must remain traceable to specs.
3. `CODEX_BRIDGE_DEV_MODE` is the only frontend visibility switch for the Codex
   development wrapper.
4. Production and user-installable releases use real backend configuration and
   real data paths unless the user explicitly requests a demo or mock release.
5. Diagram source lives in `.mmd` files. Rendered SVG/PNG files are cache only.
6. SDD dashboards are project-local. The Bridge app may discover many projects,
   but a dashboard view describes only the selected or current workspace.
7. Mature SDD coverage includes component, deployment, sequence, class, entity
   relationship, and use case diagrams.
8. Diagrams are validation artifacts. Users must be able to request changes on
   diagram nodes, edges, or regions and trace those requests to specs,
   feedback, and Codex actions.

## Required Project Artifacts

- `codex-bridge.yaml`
- `.specify/memory/constitution.md`
- `specs/<feature>/spec.md`
- `specs/<feature>/plan.md`
- `specs/<feature>/tasks.md`
- `specs/<feature>/diagrams/*.mmd`
- `architecture/*.mmd`

## Required Diagram Categories

- Component diagrams identify involved runtime and source components.
- Deployment diagrams identify where each relevant component physically or
  logically lives, such as device, host, cloud provider, release system, or
  configured backend.
- Sequence diagrams identify ordered interactions between users, apps,
  backend services, files, feedback, and Codex actions.
- Class diagrams identify domain, read-model, UI coordination, and action
  objects.
- Entity relationship diagrams identify persisted or file-backed entities and
  their relationships.
- Use case diagrams identify actors, system boundaries, and user goals.
