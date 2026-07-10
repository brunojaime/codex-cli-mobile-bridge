# T004 Define position, pinning, and layout metadata

Spec: 016-diagram-mcp-rendering-engine

Plan: Diagram Domain And Schema Contract

Status: completed

- [x] T004 Define position, pinning, and layout metadata.

## Acceptance Notes

- Position coordinates, pinned state, and layout mode are described in the spec.
- Pinned nodes are preserved by automatic and incremental layout.
- Invalid coordinates have explicit validation errors.

## Implementation Notes

- Separate manual position from semantic component identity.
- Define snap-to-grid updates as operations on DiagramSpec.
