# Metadata Refresh

After every successful create/edit action, refresh title, description, status,
task summary, traceability, and `.sdd` indexes. Pinned title/description fields
must not be overwritten.

Target modules:

- `backend/app/application/services/sdd_metadata_refresh_service.py`
- `backend/app/application/services/sdd_index_service.py`
- `tests/test_sdd_metadata_refresh_service.py`

Refresh must be idempotent and expose stale/updated/skipped/proposed fields.
