# T023 Define drag, snap, and pin behavior

Spec: 016-diagram-mcp-rendering-engine

Plan: Interactive Editor Integration

Status: pending

- [ ] T023 Define drag, snap, and pin behavior.

## Acceptance Notes

- Dragging snaps to grid before persistence.
- Moved nodes store position and pinned=true.
- Rerender uses updated anchors and ports.

## Implementation Notes

- Define drag end as the persistence boundary.
- Keep transient drag state out of DiagramSpec until committed.
