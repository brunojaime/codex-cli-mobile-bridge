---
id: 008-sdd-workbench-lazy-loading
title: SDD Workbench Lazy Loading
status: draft
type: feature
domains:
  - sdd
  - workbench
  - mobile
  - backend-api
related_specs:
  - 001-codex-bridge-sdd-wrapper
  - 002-sdd-visual-workbench
  - 003-workbench-sdd-standard
---

# SDD Workbench Lazy Loading

## Intent

The SDD Workbench must open quickly and avoid loading every spec, plan, task,
diagram, and source document at panel startup. It should first load a lightweight
project summary and only fetch the full detail for a specific spec when the user
opens that spec.

## Product Outcome

When a user opens the Workbench:

- the spec list appears from a lightweight summary response;
- selecting a spec loads only that spec's complete tree, plans, tasks, diagrams,
  and files;
- already opened specs are cached in the client while the panel remains open;
- older Bridge backends still work through the existing full snapshot endpoint;
- generated apps that include the shared Workbench package inherit the lazy
  loading behavior after they update the package/build.

## Core Rule

Opening the Workbench must not require reading or transferring all SDD artifact
content for every spec.

The old full snapshot endpoint remains compatible, but the new Workbench client
must prefer:

```text
GET /sdd/project/summary?workspace_path=...
GET /sdd/project/spec?workspace_path=...&spec_id=...
```

## Scope

- Add a backend summary endpoint with project metadata and spec summaries only.
- Add a backend spec-detail endpoint that returns one complete `SddSpec`.
- Keep `GET /sdd/project` working for older clients.
- Optimize diagram listing so it does not need the full project snapshot.
- Update the Workbench client to load summary first and hydrate specs on demand.
- Add per-spec loading, error, retry, and in-memory cache behavior.
- Validate backend, Workbench package, mobile app integration, and Android
  release.

## Non-Goals

- Do not remove or rename existing SDD endpoints.
- Do not change the on-disk Workbench SDD standard.
- Do not require generated projects to regenerate their SDD files.
- Do not lazy-load every individual task file yet; spec-level lazy loading is
  the first stable boundary.

## API Contract

### Project Summary

`GET /sdd/project/summary?workspace_path=<path>`

Returns:

- workspace name/path;
- required/missing status;
- manifest and constitution metadata;
- architecture diagrams if available;
- spec summaries containing id, title, description, lifecycle, traceability,
  task counts, metadata warnings, missing status, and paths;
- no full plan/task/spec file contents for every spec.

### Spec Detail

`GET /sdd/project/spec?workspace_path=<path>&spec_id=<id>`

Returns one full `SddSpec` using the same response shape as items inside the
legacy `GET /sdd/project` response.

Invalid workspace paths return `400`. Unknown spec IDs return `404`.

## Frontend Contract

The Workbench client must:

- call summary at startup;
- fall back to the legacy full snapshot if the summary endpoint is unavailable;
- call spec detail when a user opens a spec whose tree/content is not loaded;
- replace the summary spec with the detailed spec in the in-memory project
  model;
- cache loaded specs for the lifetime of the panel;
- show a local loading/error state for the selected spec without blanking the
  whole Workbench.

## Release Contract

Because this changes the shared Workbench behavior used by Codex Mobile, the
change must ship in a new Codex Mobile Android release after backend and Flutter
tests pass.

