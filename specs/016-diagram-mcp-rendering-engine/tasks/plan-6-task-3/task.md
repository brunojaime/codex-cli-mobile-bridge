# T029 Define MCP tool integration tests

Spec: 016-diagram-mcp-rendering-engine

Plan: Quality Observability And Export

Status: completed

- [x] T029 Define MCP tool integration tests.

## Acceptance Notes

- MCP integration tests cover create, validate, move, render, and export flows.
- HTTPS localhost startup behavior is exercised.
- Structured error responses are asserted.

## Implementation Notes

- Use real local transport configuration in tests.
- Avoid mock/demo data paths for release-like validation.
