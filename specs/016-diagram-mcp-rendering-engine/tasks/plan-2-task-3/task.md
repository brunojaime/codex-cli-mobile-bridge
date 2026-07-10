# T008 Define create and update diagram tools

Spec: 016-diagram-mcp-rendering-engine

Plan: MCP Local HTTPS Server Contract

Status: completed

- [x] T008 Define create and update diagram tools.

## Acceptance Notes

- Create/update tools operate on DiagramSpec semantics, not SVG patches.
- move_node sets position and pinned=true.
- remove_element validates impact before confirmation.

## Implementation Notes

- Implement updates as deterministic operations that can feed undo/redo.
- Reject unknown template IDs before storing changes.
