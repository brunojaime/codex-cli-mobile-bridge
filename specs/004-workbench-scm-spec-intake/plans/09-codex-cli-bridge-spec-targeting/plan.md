# Codex CLI Bridge Spec Targeting

Extend Bridge capture flows so screenshots, selected images, audio, comments,
and capture batches can target no spec, a new spec, or an existing spec. The
Bridge should send the same `spec_target` payload as Workbench.

Target modules:

- existing feedback/capture payload schemas in backend API.
- Flutter feedback/capture widgets in the current Bridge app.
- shared package metadata structures where feedback payloads are built.
- focused payload compatibility tests.

This phase reuses existing capture behavior and only adds target metadata and
spec picker UI.
