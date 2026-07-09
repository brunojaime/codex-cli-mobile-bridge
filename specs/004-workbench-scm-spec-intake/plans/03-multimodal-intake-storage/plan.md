# Multimodal Intake Storage

Persist text, audio, images, cropped images, marked regions, multiple
screenshots, and image sequences under `specs/<id>/intake/`. Raw input must be
preserved before transcription, visual summarization, or spec generation.

Target modules:

- `backend/app/api/schemas.py`
- `backend/app/application/services/sdd_intake_service.py`
- `tests/fixtures/sdd_intake/`
- `tests/test_sdd_intake_service.py`

This phase adds dry-run planning and validation only. Writes are blocked until
size, format, path, and collision checks pass.
