# Diagram Domain And Schema Contract

Define the canonical domain model for diagram generation, rendering, validation, layout metadata, and template registry compatibility.

Required outcomes:

1. `DiagramSpec` has a stable JSON contract for components, connections, layout, positions, and versioning.
2. Component connections encode consumer, interface, and provider semantics without relying on SVG geometry.
3. Template registry, anchors, ports, validation errors, and warnings are specified before implementation.
