# Slice 4: Feedback Linked To Specs And Diagrams

## Goal

Make developer feedback attachable to SDD artifacts and diagram regions.

## Feedback Targets

Feedback may target:

- Spec.
- Plan.
- Task.
- Component.
- Screen.
- Actor.
- Entity.
- Class.
- Sequence step.
- Diagram file.
- Diagram region.

## Diagram Annotation

The user should be able to mark a diagram node, edge, or region and add a
comment. That annotation should be sent to Codex with enough context to update
the diagram, the related spec, or implementation tasks.

The feedback payload should be able to carry:

- Workspace path.
- Spec id.
- Screen.
- Component.
- Diagram path.
- Diagram selection kind.
- Diagram selection identifier or region.
- Requested change.

## Done When

- Feedback metadata can reference SDD artifacts.
- Diagram annotations can be captured without changing production behavior.
- Feedback can be grouped by SDD target in the workbench.
- Existing feedback without SDD metadata remains valid.
