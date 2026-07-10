# T037 Preserve semantic SVG IDs for feedback and future edits

Spec: 016-diagram-mcp-rendering-engine

Plan: Frontend Diagram Viewer

Status: pending

- [ ] T037 Preserve semantic SVG IDs for feedback and future edits.

## Acceptance Notes

- Rendered SVG IDs such as `node-*`, `connector-*`, and `data-node-id` remain available to frontend selection logic where the renderer exposes them.
- The detail view can submit diagram feedback with the diagram path and optional selected element metadata.
- Selection fallback supports region-level feedback when exact SVG element hit-testing is unavailable.

## Implementation Notes

- Start with metadata preservation and feedback payload plumbing; pixel-perfect SVG hit-testing can be a later enhancement.
- Keep the MCP engine as the owner of diagram semantics and geometry.

