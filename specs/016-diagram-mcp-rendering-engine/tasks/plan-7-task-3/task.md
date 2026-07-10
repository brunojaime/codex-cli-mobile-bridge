# T035 Add Diagrams section gallery for rendered artifacts

Spec: 016-diagram-mcp-rendering-engine

Plan: Frontend Diagram Viewer

Status: completed

- [x] T035 Add Diagrams section gallery for rendered artifacts.

## Acceptance Notes

- The frontend has a Diagrams section that lists workspace diagrams by title, type, scope, and format.
- SVG-rendered MCP diagrams appear in the same list as Mermaid diagrams.
- Empty, loading, permission, and backend error states are visible and actionable.

## Implementation Notes

- Use the existing bridge API client and server profile configuration.
- Keep the first screen functional and dense; this is a workbench surface, not a landing page.
- Avoid duplicating SDD parsing logic in Flutter.

