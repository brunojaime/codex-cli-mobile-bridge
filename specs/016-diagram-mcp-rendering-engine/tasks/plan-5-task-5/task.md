# T026 Define undo redo and change history

Spec: 016-diagram-mcp-rendering-engine

Plan: Interactive Editor Integration

Status: pending

- [ ] T026 Define undo redo and change history.

## Acceptance Notes

- Undo and redo are based on semantic operations.
- Move, add, update, and remove operations are reversible where possible.
- Render cache is invalidated after history navigation.

## Implementation Notes

- Store enough operation payload to reverse state changes.
- Do not store SVG diffs as undo history.
