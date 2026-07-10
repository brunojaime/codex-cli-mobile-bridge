# T007 Define MCP tool manifest and lifecycle

Spec: 016-diagram-mcp-rendering-engine

Plan: MCP Local HTTPS Server Contract

Status: pending

- [ ] T007 Define MCP tool manifest and lifecycle.

## Acceptance Notes

- The MCP manifest exposes the required tool names and input/output summaries.
- Tool lifecycle distinguishes create, validate, layout, render, move, update, remove, and export operations.
- Read-only versus mutating tools are annotated where the SDK supports it.

## Implementation Notes

- Keep tool names identical to the spec contract.
- Return JSON-friendly payloads only.
