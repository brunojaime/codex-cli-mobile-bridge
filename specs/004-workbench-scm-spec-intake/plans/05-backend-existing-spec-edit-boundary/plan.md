# Backend Existing Spec Edit Boundary

Add a backend service and API boundary that can target an existing spec artifact
for update. It must validate workspace, spec id, artifact path, and context
before invoking Codex.

Target modules:

- `backend/app/application/services/sdd_spec_edit_service.py`
- `backend/app/application/services/sdd_context_pack_service.py`
- `tests/test_sdd_spec_edit_service.py`

This phase prepares edit requests and dry-run validation. It does not execute
Codex CLI yet.
