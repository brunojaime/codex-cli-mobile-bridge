# T006 Define local HTTPS server configuration

Spec: 016-diagram-mcp-rendering-engine

Plan: MCP Local HTTPS Server Contract

Status: pending

- [ ] T006 Define local HTTPS server configuration.

## Acceptance Notes

- Server configuration requires loopback host and HTTPS certificate/key paths.
- Startup fails clearly when HTTPS configuration is absent.
- Public interface binding is not enabled by default.

## Implementation Notes

- Keep local development configuration explicit.
- Document certificate expectations before implementing transport.
