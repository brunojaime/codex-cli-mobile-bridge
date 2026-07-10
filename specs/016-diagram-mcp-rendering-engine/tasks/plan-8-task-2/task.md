# T039 Persist MCP exports into spec diagram folders

Spec: 016-diagram-mcp-rendering-engine

Plan: MCP Diagram Workflow And Mobile Release

Status: completed

- [x] T039 Persist MCP exports into spec diagram folders.

## Acceptance Notes

- Generated diagrams can be saved under `specs/<spec-id>/diagrams/` with stable filenames.
- Each saved SVG has adjacent metadata that lets the bridge classify and display it.
- Existing generated files are updated intentionally rather than duplicated with random names.

## Implementation Notes

- Treat `DiagramSpec` and SVG as separate artifacts when both are present.
- Runtime `.data/` storage remains local cache, not the published spec artifact.

