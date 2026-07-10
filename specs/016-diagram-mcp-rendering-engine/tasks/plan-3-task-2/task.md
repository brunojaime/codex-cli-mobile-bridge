# T012 Define automatic LR layout phases

Spec: 016-diagram-mcp-rendering-engine

Plan: Layout Anchors And Routing Engine

Status: pending

- [ ] T012 Define automatic LR layout phases.

## Acceptance Notes

- LR layout phases are ordered and deterministic.
- Consumers appear left of providers for normal flows.
- Multiple providers and outputs receive predictable vertical distribution.

## Implementation Notes

- Use graph depth/column assignment before coordinate assignment.
- Keep column and row spacing constants configurable.
