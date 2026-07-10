# T033 Extend SDD diagram read model for rendered SVG artifacts

Spec: 016-diagram-mcp-rendering-engine

Plan: Frontend Diagram Viewer

Status: completed

- [x] T033 Extend SDD diagram read model for rendered SVG artifacts.

## Acceptance Notes

- `GET /sdd/project/diagrams` includes MCP-rendered `.svg` diagrams from `architecture/` and `specs/*/diagrams/`.
- Each rendered diagram response identifies `diagram_type`, `source_format`, `rendered_format`, `scope`, and optional metadata path.
- Existing Mermaid discovery remains backward-compatible.

## Implementation Notes

- Extend the backend allowlist and SDD diagram scanner deliberately instead of treating every SVG asset as a diagram.
- Prefer metadata files such as `*.yaml` next to SVGs to classify MCP-rendered diagrams.
- Keep file-size limits and safe workspace path checks in place.

