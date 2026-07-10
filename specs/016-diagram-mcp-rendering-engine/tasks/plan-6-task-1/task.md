# T027 Define persistence and diagram IDs

Spec: 016-diagram-mcp-rendering-engine

Plan: Quality Observability And Export

Status: pending

- [ ] T027 Define persistence and diagram IDs.

## Acceptance Notes

- Diagram IDs are stable and collision-resistant.
- Persisted records include DiagramSpec, layout, pins, and optional SVG cache.
- Cache invalidation rules are defined.

## Implementation Notes

- Keep persistence format versioned.
- Avoid making cached SVG authoritative.
