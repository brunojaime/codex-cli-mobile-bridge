# T015 Define collision and overlap handling

Spec: 016-diagram-mcp-rendering-engine

Plan: Layout Anchors And Routing Engine

Status: completed

- [x] T015 Define collision and overlap handling.

## Acceptance Notes

- Known overlap cases are detected or warned about.
- Parallel paths maintain minimum visual separation.
- Node movement triggers recomputation without semantic changes.

## Implementation Notes

- Document MVP limitations for hard collision cases.
- Return warnings instead of silently producing misleading geometry.
