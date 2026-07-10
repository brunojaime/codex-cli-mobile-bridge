# Interactive Editor Integration

Define how the editor shows generated SVG, maps user interactions back to diagram operations, supports drag and snap, and persists manual positions.

Required outcomes:

1. The editor treats SVG as display output and sends semantic operations back to the engine.
2. Dragged nodes update `position`, set `pinned: true`, and trigger connection rerouting.
3. Undo, redo, selection, inspector state, and synchronization rules are specified.
