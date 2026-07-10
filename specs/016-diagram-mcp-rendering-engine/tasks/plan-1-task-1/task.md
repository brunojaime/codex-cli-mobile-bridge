# T001 Define DiagramSpec JSON schema

Spec: 016-diagram-mcp-rendering-engine

Plan: Diagram Domain And Schema Contract

Status: completed

- [x] T001 Define DiagramSpec JSON schema.

## Acceptance Notes

- A JSON Schema draft is available for the MVP DiagramSpec fields.
- The schema rejects missing version, diagramType, components, and connections collections.
- The schema documents extension points for future diagram types without accepting arbitrary geometry.

## Implementation Notes

- Keep the schema independent from SVG output.
- Use snake_case ID constraints and explicit enums for MVP-only fields.
