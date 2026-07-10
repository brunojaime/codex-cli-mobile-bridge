# T031 Define export acceptance tests

Spec: 016-diagram-mcp-rendering-engine

Plan: Quality Observability And Export

Status: completed

- [x] T031 Define export acceptance tests.

## Acceptance Notes

- SVG export acceptance verifies valid, self-contained SVG output.
- Future PNG/PDF export placeholders are explicit non-MVP behavior.
- Export errors are structured and testable.

## Implementation Notes

- Start with SVG only.
- Keep export code separate from tool transport concerns.
