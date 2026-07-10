# T002 Define component and connection semantic model

Spec: 016-diagram-mcp-rendering-engine

Plan: Diagram Domain And Schema Contract

Status: completed

- [x] T002 Define component and connection semantic model.

## Acceptance Notes

- Consumer/provider direction is defined for every connection.
- Derived interface nodes are described as render-time visual nodes, not persisted components.
- Self-connections and unsupported component references have deterministic validation behavior.

## Implementation Notes

- Model semantic connections before any layout/router concerns.
- Document normalization from from/interface/to into two rendered connector segments.
