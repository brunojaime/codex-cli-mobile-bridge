# Tasks: Agregar soporte para adjuntar PDF, PPTX, XLSX, DOCX y otros archivos de oficina en Codex Mobile Bridge

- [x] Inspect the current mobile attachment picker, accepted MIME/extension list, backend upload endpoint, storage path conventions, and any session/workspace file indexing logic.
- [x] Define the supported document policy for DEV: minimum .pdf, .pptx, .xlsx, .docx; decide whether to also include .ppt, .xls, .doc, .csv, .txt, .md, images, or archives based on existing security constraints.
- [x] Update mobile app file picker filters and UI copy so users can select the supported document formats without implying mock/demo behavior.
- [x] Update backend upload validation to accept the agreed extensions and MIME types while enforcing existing size limits, path sanitization, workspace/session scoping, and unsupported-type rejection.
- [x] Ensure accepted files are stored in the appropriate session/workspace folder that Codex can read from, using existing storage abstractions rather than hardcoded placeholder paths.
- [x] If the bridge has a file manifest, attachment metadata table, or event stream, update it so these office documents appear consistently with existing attachments.
- [x] Add clear error handling for unsupported file types, oversized files, failed writes, and files that cannot be indexed or exposed to the session.
- [x] Document the final supported types and any explicit exclusions in the DEV spec/plan.
- [x] Run targeted backend and mobile tests in DEV only; do not modify or restart PROD services.
- [x] Prepare promotion notes that call out real backend configuration and confirm no mock/demo/local demo mode was enabled.

## Regression

- [x] Backend upload test accepts valid .pdf, .pptx, .xlsx, and .docx files and stores them under the expected session/workspace-accessible folder.
- [x] Backend upload test rejects unsupported extensions and suspicious filenames/path traversal attempts.
- [x] Backend upload test preserves existing supported attachment types and does not break current chat, reading, project/factory creation, or non-bridge repository flows.
- [x] Mobile test or manual DEV validation confirms the file picker can select PDF, PowerPoint, Excel, and Word documents on Android.
- [x] Mobile/backend integration test confirms an uploaded office document appears in the session attachment list or equivalent Codex-readable context.
- [x] Error-state test confirms unsupported or oversized files produce a user-visible failure without crashing the app.
- [x] Release/build validation confirms real API_BASE_URL/bridge configuration is used and no mock/demo data path is introduced.

## Evidence

- Backend: `uv run pytest tests/test_message_flow.py -k "document_message_flow or attachment_batch_flow_accepts_office_documents or attachment_batch_flow_accepts_images or attachment_batch_flow_rejects_unsupported_extension_with_office_mime or attachment_batch_flow_preserves_text_image_audio_mime_classification or image_attachment_download"` passed 21 selected tests.
- Backend lint: `uv run ruff check backend/app/application/services/message_service.py backend/app/api/routes.py tests/test_message_flow.py` passed.
- Mobile picker: `flutter test test/widget_test.dart --plain-name "attachment picker includes supported office documents"` passed.
- Mobile static check: `flutter analyze lib/src/screens/chat_screen.dart test/widget_test.dart` reported no issues.
- Release config: no release build defines, API base URL wiring, update channel config, or mock/demo/local demo paths were changed.

## Promotion Notes

- Supported office formats are `.pdf`, `.docx`, `.pptx`, and `.xlsx`.
- Legacy `.doc`, `.xls`, `.ppt`, archives, and arbitrary unsupported extensions remain intentionally unsupported in the office/PDF path, even when the declared MIME type is office/PDF.
- Existing MIME-first classification remains preserved for `text/*`, `image/*`, and `audio/*` provider uploads with uncommon extensions such as `.foo`, `.heic`, and `.aif`.
- Mobile `FileType.custom` includes the previously recognized audio extensions `.aif`, `.aiff`, `.amr`, and `.oga`.
- Accepted non-image documents are stored under `.codex-mobile-bridge/attachments/<session-id>/` inside the active workspace and referenced in the Codex execution prompt.
