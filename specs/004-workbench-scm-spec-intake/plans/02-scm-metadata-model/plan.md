# SCM Metadata Model

Add `metadata.yaml` support for specs. The model must include title,
description, status, timestamps, generated/pinned field flags, task summary, and
last Codex run state.

Target modules:

- `backend/app/application/services/sdd_project_service.py`
- `backend/app/application/services/sdd_workbench_view_service.py`
- `packages/codex_bridge_workbench/lib/src/models/sdd_project.dart`
- `tests/test_sdd_spec_metadata.py`
- focused Workbench model/widget tests.

This phase is read-only. Missing metadata must use fallback values.
