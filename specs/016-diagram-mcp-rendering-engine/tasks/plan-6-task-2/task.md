# T028 Define deterministic snapshot tests

Spec: 016-diagram-mcp-rendering-engine

Plan: Quality Observability And Export

Status: completed

- [x] T028 Define deterministic snapshot tests.

## Acceptance Notes

- Snapshot tests cover stable layout and SVG rendering for representative specs.
- Snapshots normalize non-semantic whitespace if needed.
- Changing template geometry requires intentional snapshot updates.

## Implementation Notes

- Use fixed input specs and deterministic ordering.
- Test semantic SVG IDs as well as geometry.
