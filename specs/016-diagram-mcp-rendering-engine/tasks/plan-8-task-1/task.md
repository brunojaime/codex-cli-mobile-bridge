# T038 Wire frontend runs to the Diagram MCP server

Spec: 016-diagram-mcp-rendering-engine

Plan: MCP Diagram Workflow And Mobile Release

Status: completed

- [x] T038 Wire frontend runs to the Diagram MCP server.

## Acceptance Notes

- The frontend can select `diagram-mcp-rendering-engine` as an MCP server for diagram generation/update runs.
- Codex prompts launched from the Diagrams section include the selected diagram path and workspace context.
- Missing MCP registration produces a clear setup message instead of a failed silent run.

## Implementation Notes

- Reuse the existing MCP server selection model in chat options.
- Do not hardcode user-specific absolute paths into the mobile app.

