# T010 Define security, auth, and origin controls

Spec: 016-diagram-mcp-rendering-engine

Plan: MCP Local HTTPS Server Contract

Status: completed

- [x] T010 Define security, auth, and origin controls.

## Acceptance Notes

- Allowed origins, optional local token, and request size limits are defined.
- Labels are sanitized before SVG rendering.
- SVG output cannot include scripts or unsafe foreign content.

## Implementation Notes

- Enforce security at the MCP boundary and renderer boundary.
- Avoid logging complete SVG by default.
