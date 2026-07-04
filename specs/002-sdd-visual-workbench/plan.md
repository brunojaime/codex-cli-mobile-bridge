# Plan

## Slice 1: SDD Explorer

Create the first read-only workbench screen. It should load the current
project's SDD snapshot and expose constitution, specs, plans, tasks, and
diagram source files through the existing read-only SDD backend endpoints.

## Slice 2: Diagram Rendering

Render Mermaid diagrams visually in dev mode. The initial target is preview
quality, not production diagram publishing. The original `.mmd` file remains
the source of truth and rendered output is cache only.

## Slice 3: Architecture UX

Turn the raw explorer into a focused architecture review surface with tabs,
status summaries, search, and diagram family navigation.

## Slice 4: Feedback Linked To Specs And Diagrams

Extend developer feedback so items can be linked to specs, components, screens,
actors, entities, sequence steps, and marked diagram regions.

Feedback metadata should be optional and backward-compatible. Existing
feedback senders that do not know about SDD must keep working.

## Slice 5: Codex Actions From Specs

Allow the user to trigger Codex workflows from a spec, task, feedback item, or
diagram annotation.

## Slice 6: Current Project Dashboard

Create a dashboard for the project currently being inspected. In inherited
apps, this dashboard must describe only that app/project. The bridge app may
still provide project selection because it is the control surface.

The dashboard may show real release, updater, backend, and feedback
configuration references for the current project. It must not generate or
suggest mock/demo configuration.

## Implementation Notes

- Keep all work behind `CODEX_BRIDGE_DEV_MODE`.
- Keep SDD reads read-only unless a future explicit write flow is designed.
- Do not add demo data, mock URLs, or placeholder backend configuration.
- Do not change release identifiers, package ids, backend URLs, or updater
  configuration as part of this SDD.
- Keep diagram source as `.mmd`; rendered SVG/PNG remains cache only.
- Do not hard-code monolith or microservice assumptions.
