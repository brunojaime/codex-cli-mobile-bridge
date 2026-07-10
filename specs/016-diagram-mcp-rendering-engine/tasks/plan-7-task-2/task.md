# T034 Add diagram artifact metadata contract

Spec: 016-diagram-mcp-rendering-engine

Plan: Frontend Diagram Viewer

Status: pending

- [ ] T034 Add diagram artifact metadata contract.

## Acceptance Notes

- SVG diagram metadata records the MCP renderer, source DiagramSpec ID when available, title, diagram family, and rendered artifact path.
- The metadata contract supports both generated SVG-only diagrams and diagrams with a separate source file.
- Stale or missing metadata degrades to a readable frontend error instead of hiding the diagram silently.

## Implementation Notes

- Reuse the existing `diagrams/*.yaml` convention.
- Do not embed runtime-local absolute paths in committed metadata.
- Keep metadata compatible with future PNG/PDF exports.

