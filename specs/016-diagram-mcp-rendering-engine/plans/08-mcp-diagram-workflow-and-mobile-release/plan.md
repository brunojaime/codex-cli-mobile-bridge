# MCP Diagram Workflow And Mobile Release

Wire generated diagrams into the existing Codex workflow and ship the frontend change through the normal real-backend mobile release path.

Required outcomes:

1. Diagram generation and update runs can select the local Diagram MCP server from the frontend.
2. MCP exports are persisted into the workspace spec diagram folders with metadata that the Diagrams section can discover.
3. Android release preparation uses the real bridge backend configuration, not demo or mock data.

