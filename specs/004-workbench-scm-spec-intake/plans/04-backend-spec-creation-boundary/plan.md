# Backend Spec Creation Boundary

Add a backend service and API boundary that can create a new spec package from a
normalized intake. The first implementation must be dry-run capable and must
avoid overwriting existing spec directories.

Target modules:

- `backend/app/api/routes.py`
- `backend/app/api/schemas.py`
- `backend/app/application/services/sdd_spec_creation_service.py`
- `tests/test_sdd_spec_creation_service.py`

The write flow must consume the dry-run plan as its write contract.
