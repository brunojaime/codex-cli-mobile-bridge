# T022 Define editor canvas contract

Spec: 016-diagram-mcp-rendering-engine

Plan: Interactive Editor Integration

Status: pending

- [ ] T022 Define editor canvas contract.

## Acceptance Notes

- The editor consumes SVG as display output.
- Selection uses semantic SVG IDs instead of rebuilding UML shapes.
- The canvas includes grid and viewport behavior expectations.

## Implementation Notes

- Keep UML drawing rules in the engine.
- Expose only semantic edit operations from the frontend.
