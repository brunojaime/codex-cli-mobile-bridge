# T014 Define orthogonal routing strategy

Spec: 016-diagram-mcp-rendering-engine

Plan: Layout Anchors And Routing Engine

Status: completed

- [x] T014 Define orthogonal routing strategy.

## Acceptance Notes

- Aligned anchors use straight segments.
- Non-aligned anchors produce orthogonal SVG paths.
- Routes avoid node bounding boxes when the simple strategy can do so.

## Implementation Notes

- Keep router local and deterministic for MVP.
- Prefer readable output over global crossing optimization.
