# Codex Bridge SDD Architecture

Codex Bridge projects must carry a living Spec-Driven Development structure.
The structure is mandatory for every project integrated with the Bridge. The
single runtime switch `CODEX_BRIDGE_DEV_MODE` only controls whether the
development wrapper is visible in the frontend.

## Contract

Every project root is expected to expose this structure:

```text
.specify/
  memory/
    constitution.md
specs/
  <feature>/
    spec.md
    plan.md
    tasks.md
    diagrams/
      *.mmd
architecture/
  *.mmd
codex-bridge.yaml
```

The `.mmd` files are the source of truth for diagrams. Rendered SVG or PNG
outputs are cache artifacts only and should live outside the contract, for
example under `.codex-bridge/cache/diagrams/`.

## Required Files

- `codex-bridge.yaml` declares the project-level Bridge contract.
- `.specify/memory/constitution.md` describes mandatory architecture and
  product rules for the project.
- `specs/<feature>/spec.md` captures user intent and acceptance criteria.
- `specs/<feature>/plan.md` captures the implementation approach.
- `specs/<feature>/tasks.md` captures actionable implementation tasks.
- `specs/<feature>/diagrams/*.mmd` captures feature-specific flows.
- `architecture/*.mmd` captures project-wide architecture diagrams.

## Required Diagram Categories

Mature SDD coverage uses software engineering notation and keeps these diagram
categories as Mermaid source:

- Component diagram: involved runtime and source components.
- Deployment diagram: where each relevant component physically or logically
  lives, including device, host, cloud provider, update service, release
  system, backend, or project filesystem.
- Sequence diagram: ordered interactions for important workflows.
- Class diagram: domain, read-model, UI coordination, and action objects.
- Entity relationship diagram: persisted or file-backed entities and links.
- Use case diagram: actors, system boundaries, and user goals.

The Bridge must stay extensible for monoliths, modular apps, microservices,
and hybrid systems. A project does not need to declare one of those categories
up front for the diagrams to be useful.

## Frontend Visibility

The project always keeps the SDD structure. The frontend development wrapper is
controlled by exactly one compile-time flag:

```text
CODEX_BRIDGE_DEV_MODE=true
```

When the flag is disabled, the app returns the normal product UI without the
Codex development wrapper. Backend SDD endpoints remain read-only and available
for tooling.

## Project-Local Dashboard Scope

The SDD dashboard is implemented in Codex Mobile Bridge. Downstream projects
only provide the SDD contract files and real configuration.

The Bridge may use `/sdd/projects` to discover workspaces, but dashboard
content must be scoped to one selected or current project at a time. A project
opened through the Bridge should not see an embedded dashboard about unrelated
projects.

## Diagram Change Requests

Diagrams are validation artifacts. The visual panel should let users mark a
diagram node, edge, or region and request a specific change. The request must
carry enough context to trace it back to the workspace, diagram file, related
spec, feedback item, and Codex action.

Rendered diagram assets are cache only. The `.mmd` source remains the file that
Codex should update when a diagram change is accepted.

## Backend Read Model

The backend exposes read-only SDD metadata:

- `GET /sdd/projects`
- `GET /sdd/project?workspace_path=...`
- `GET /sdd/project/diagrams?workspace_path=...`

The same endpoints are also available under `/api/v1` through the existing
router registration.

The backend never executes Mermaid, shell commands, or project scripts. It only
reads files with these extensions:

- `.md`
- `.mmd`
- `.yaml`
- `.yml`
- `.json`

Files are constrained by a per-file size limit. Oversized files are reported
without reading their content.

## Path Safety

Workspace reads must resolve under `PROJECTS_ROOT` or through known project
aliases. Symlink escapes, traversal outside allowed roots, and unsupported file
extensions are rejected or ignored.
