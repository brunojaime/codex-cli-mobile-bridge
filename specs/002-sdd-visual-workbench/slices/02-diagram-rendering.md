# Slice 2: Diagram Rendering

## Goal

Render diagrams visually from `.mmd` source.

## Diagram Families

- Component diagram.
- Deployment diagram.
- Sequence diagram.
- Class diagram.
- Entity relationship diagram.
- Use case diagram.

## Rendering Rules

The `.mmd` source is the source of truth. Rendered SVG or PNG files are cache
only. Render failures should be shown as validation states with the source still
available.

## Change Marking

The rendered diagram should support selecting or marking:

- Node.
- Edge.
- Region.

The mark must keep enough context to request a specific diagram change through
feedback and Codex actions.

## Done When

- The workbench can preview Mermaid diagrams in dev mode.
- The user can inspect source and rendered output.
- The user can mark a diagram area or element for a requested change.
- Empty, malformed, or unsupported diagrams do not crash the app.
