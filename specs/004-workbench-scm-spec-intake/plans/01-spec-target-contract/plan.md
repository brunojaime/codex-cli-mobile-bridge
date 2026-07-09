# Spec Target Contract

Define the shared `spec_target` payload used by Workbench and Codex CLI Bridge.
The contract must support `none`, `new_spec`, and `existing_spec`, plus an
optional artifact target: `auto`, `spec`, `plan`, `tasks`, or `diagram`.

Target modules:

- `backend/app/api/schemas.py`
- `backend/app/application/services/sdd_spec_target_service.py`
- `tests/test_sdd_spec_target.py`

No file-writing behavior is allowed in this phase.
