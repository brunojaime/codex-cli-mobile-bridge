# Frontend Diagram Viewer

Add first-class diagram visualization to the Codex Mobile/Bridge frontend so MCP-rendered SVG diagrams can be discovered from the workspace, previewed in the Diagrams section, and inspected without requiring the user to open files manually.

Required outcomes:

1. The backend read model exposes rendered SVG diagram artifacts alongside existing Mermaid sources.
2. The frontend Diagrams section renders SVG previews safely with pan, zoom, loading, empty, and error states.
3. The viewer preserves semantic SVG IDs so later selection, feedback, and edit actions can target MCP diagram elements.

