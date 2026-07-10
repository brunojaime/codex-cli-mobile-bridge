# T009 Define render and export tools

Spec: 016-diagram-mcp-rendering-engine

Plan: MCP Local HTTPS Server Contract

Status: pending

- [ ] T009 Define render and export tools.

## Acceptance Notes

- render_diagram_svg returns deterministic SVG without semantic mutation.
- export_diagram supports svg for MVP.
- Unsupported export formats return structured errors.

## Implementation Notes

- Keep render and export functions side-effect free unless cache is explicitly requested.
- Include warnings in tool output.
