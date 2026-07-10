# T020 Define connector rendering and interface labels

Spec: 016-diagram-mcp-rendering-engine

Plan: SVG Templates And Renderer

Status: pending

- [ ] T020 Define connector rendering and interface labels.

## Acceptance Notes

- Connector SVG groups have stable IDs and semantic attributes.
- Interface labels are readable and deterministic.
- Connector paths originate and terminate on declared anchors/ports.

## Implementation Notes

- Render connector paths after node geometry is resolved.
- Avoid arrowheads unless the template contract adds them explicitly.
