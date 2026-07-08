# Workbench UX For Specs

Expose a spec list with title, description, status, task progress, updated
timestamp, and last run state. Add new spec and edit spec flows with text,
audio, image, crop, marked region, and image sequence inputs.

Target modules:

- `packages/codex_bridge_workbench/lib/src/widgets/sdd_explorer_panel.dart`
- `packages/codex_bridge_workbench/lib/src/services/sdd_explorer_client.dart`
- `packages/codex_bridge_workbench/lib/src/models/sdd_project.dart`
- `packages/codex_bridge_workbench/test/codex_bridge_workbench_test.dart`

The UI consumes backend state and submitter boundaries; it must not write files
directly.
