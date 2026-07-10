# T030 Define observability and diagnostics

Spec: 016-diagram-mcp-rendering-engine

Plan: Quality Observability And Export

Status: pending

- [ ] T030 Define observability and diagnostics.

## Acceptance Notes

- Logs include operation names, diagram IDs, timing, and validation summaries.
- Full SVG is not logged by default.
- Diagnostics expose enough state to debug layout/routing failures.

## Implementation Notes

- Use redaction for labels if needed.
- Keep diagnostic payloads bounded.
