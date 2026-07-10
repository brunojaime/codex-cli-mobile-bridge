# T040 Add backend and Flutter tests for diagram viewing

Spec: 016-diagram-mcp-rendering-engine

Plan: MCP Diagram Workflow And Mobile Release

Status: pending

- [ ] T040 Add backend and Flutter tests for diagram viewing.

## Acceptance Notes

- Backend tests cover discovery of Mermaid and MCP-rendered SVG diagrams.
- Flutter widget tests cover gallery rendering, SVG detail rendering, empty states, and malformed SVG errors.
- Tests verify the committed `browser-gateway-example.svg` appears in the diagram list once the feature is implemented.

## Implementation Notes

- Keep tests focused; do not require a long-running MCP server.
- Use fixture files in the spec package rather than generated temp-only examples for the main happy path.

