# T018 Define uml_component SVG template

Spec: 016-diagram-mcp-rendering-engine

Plan: SVG Templates And Renderer

Status: pending

- [ ] T018 Define uml_component SVG template.

## Acceptance Notes

- The component template renders border, label, and UML component icon.
- Component dimensions and anchors match registry defaults.
- Long labels are handled without breaking the bounding box.

## Implementation Notes

- Use one engine-owned template function for all uml_component nodes.
- Do not let callers inject arbitrary SVG.
