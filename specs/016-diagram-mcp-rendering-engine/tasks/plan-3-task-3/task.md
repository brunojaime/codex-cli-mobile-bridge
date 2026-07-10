# T013 Define anchor and dynamic port allocation rules

Spec: 016-diagram-mcp-rendering-engine

Plan: Layout Anchors And Routing Engine

Status: pending

- [ ] T013 Define anchor and dynamic port allocation rules.

## Acceptance Notes

- Component anchors and interface anchors resolve to concrete points.
- Dynamic ports are assigned deterministically for repeated renders.
- Multiple same-side ports do not share the exact same y coordinate.

## Implementation Notes

- Sort port allocations by stable connection ID.
- Use the documented portY formula as the MVP baseline.
