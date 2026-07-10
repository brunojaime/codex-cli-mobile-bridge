# T016 Define incremental layout behavior for pinned nodes

Spec: 016-diagram-mcp-rendering-engine

Plan: Layout Anchors And Routing Engine

Status: completed

- [x] T016 Define incremental layout behavior for pinned nodes.

## Acceptance Notes

- Pinned nodes keep their manual positions during relayout.
- New or unpinned nodes can be placed around pinned nodes.
- Removing nodes leaves remaining pinned positions intact.

## Implementation Notes

- Treat pinned coordinates as layout constraints.
- Use deterministic fallback when constraints conflict.
