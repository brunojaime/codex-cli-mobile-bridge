# T021 Define theme, scaling, and viewBox behavior

Spec: 016-diagram-mcp-rendering-engine

Plan: SVG Templates And Renderer

Status: pending

- [ ] T021 Define theme, scaling, and viewBox behavior.

## Acceptance Notes

- Theme tokens, spacing, stroke widths, and viewBox padding are specified.
- Canvas size grows to include all rendered nodes and routes.
- Scaling rules do not change semantic geometry.

## Implementation Notes

- Keep theme small for deterministic snapshots.
- Use explicit numeric constants rather than CSS environment-dependent values.
