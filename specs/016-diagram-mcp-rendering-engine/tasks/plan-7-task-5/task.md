# T037 Preserve semantic SVG IDs for feedback and future edits

Spec: 016-diagram-mcp-rendering-engine

Plan: Frontend Diagram Viewer

Status: completed

- [x] T037 Preserve semantic SVG IDs for feedback and future edits.

## Acceptance Notes

- Rendered SVG IDs such as `node-*`, `connector-*`, and `data-node-id` remain available to frontend selection logic where the renderer exposes them.
- The detail view can submit diagram feedback with the diagram path and optional selected element metadata.
- Selection exposes practical node and connector targets from semantic SVG IDs (`data-node-id`, `data-connection-id`, `node-*`, and `connector-*`) and keeps region-level feedback as a fallback.

## Implementation Notes

- Flutter renders SVG previews through WebView, so the frontend does not rely on geometric SVG hit-testing. It lists semantic targets as selectable chips and sends the selected ID in the feedback payload.
- Keep the MCP engine as the owner of diagram semantics and geometry.
