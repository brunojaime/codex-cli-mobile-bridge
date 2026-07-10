# T024 Define selected element and inspector model

Spec: 016-diagram-mcp-rendering-engine

Plan: Interactive Editor Integration

Status: completed

- [x] T024 Define selected element and inspector model.

## Acceptance Notes

- Selected component, interface, and connector metadata are represented consistently.
- Inspector edits map to update_node or connection operations.
- Unknown SVG IDs fail gracefully.

## Implementation Notes

- Use data attributes from rendered SVG as selection keys.
- Avoid direct SVG mutation from inspector actions.
