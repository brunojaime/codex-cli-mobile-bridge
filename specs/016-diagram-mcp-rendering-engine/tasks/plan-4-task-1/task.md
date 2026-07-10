# T017 Define SVG document contract

Spec: 016-diagram-mcp-rendering-engine

Plan: SVG Templates And Renderer

Status: completed

- [x] T017 Define SVG document contract.

## Acceptance Notes

- SVG includes viewBox, semantic IDs, and deterministic group structure.
- SVG is self-contained and frontend agnostic.
- Renderer output avoids runtime dependencies on Mermaid, PlantUML, or Draw.io.

## Implementation Notes

- Keep style definitions deterministic and local to the SVG.
- Preserve data-node-id and data-node-type attributes for editor selection.
