# Implementation Plan: Agregar soporte para adjuntar PDF, PPTX, XLSX, DOCX y otros archivos de oficina en Codex Mobile Bridge

Proposed plan: 01-por-lo-que-veo-solo-podemos-adjuntar-algunos-tipos-de-archivos-me-encantaria-que

## Scope

Materialized from a PROD to DEV handoff.

## Final Supported Type Policy

- Enabled office/document formats: `.pdf`, `.docx`, `.pptx`, `.xlsx`.
- Preserved existing supported formats: text/code files, CSV/Markdown, images, and audio attachments through the existing document/attachment paths.
- Explicitly excluded for this DEV change: legacy `.doc`, `.xls`, `.ppt` and archives. These formats remain unsupported until a separate security review decides how to inspect them safely.
- Accepted MIME policy combines filename extension with known modern MIME types, common Android generic binary types, and ZIP MIME only for OpenXML containers.
- Office/PDF filename extensions are authoritative: unsupported extensions such as `.exe` are rejected when the declared MIME type is office/PDF. Existing MIME-first classification remains preserved for `text/*`, `image/*`, and `audio/*` provider uploads with uncommon extensions.
- The mobile picker allowlist includes previously recognized audio extensions `.aif`, `.aiff`, `.amr`, and `.oga` so switching from `FileType.any` to `FileType.custom` does not hide those files.
- Non-image office files are copied into the active workspace at `.codex-mobile-bridge/attachments/<session-id>/` and the Codex execution prompt receives the stored file path. No mock/demo/local data path was introduced.

## Proposed Tasks

- Inspect the current mobile attachment picker, accepted MIME/extension list, backend upload endpoint, storage path conventions, and any session/workspace file indexing logic.
- Define the supported document policy for DEV: minimum .pdf, .pptx, .xlsx, .docx; decide whether to also include .ppt, .xls, .doc, .csv, .txt, .md, images, or archives based on existing security constraints.
- Update mobile app file picker filters and UI copy so users can select the supported document formats without implying mock/demo behavior.
- Update backend upload validation to accept the agreed extensions and MIME types while enforcing existing size limits, path sanitization, workspace/session scoping, and unsupported-type rejection.
- Ensure accepted files are stored in the appropriate session/workspace folder that Codex can read from, using existing storage abstractions rather than hardcoded placeholder paths.
- If the bridge has a file manifest, attachment metadata table, or event stream, update it so these office documents appear consistently with existing attachments.
- Add clear error handling for unsupported file types, oversized files, failed writes, and files that cannot be indexed or exposed to the session.
- Document the final supported types and any explicit exclusions in the DEV spec/plan.
- Run targeted backend and mobile tests in DEV only; do not modify or restart PROD services.
- Prepare promotion notes that call out real backend configuration and confirm no mock/demo/local demo mode was enabled.

## Validation

DEV materializes a spec named 020-por-lo-que-veo-solo-podemos-adjuntar-algunos-tipos-de-archivos-me-encantaria-que and a plan named 01-por-lo-que-veo-solo-podemos-adjuntar-algunos-tipos-de-archivos-me-encantaria-que from this handoff. Implementation happens only in the DEV stage/worktree. PROD chat, reading, project/factory creation, and non-bridge repository work continue to function. Strong bridge modifications remain blocked in PROD and enter DEV through the queue. Targeted backend and mobile tests pass before promotion is considered. Users can attach at least PDF, PPTX, XLSX, and DOCX files from the mobile app. Backend validation accepts the supported file extensions/MIME types, rejects unsupported or unsafe files with a clear error, stores accepted files in the correct session/workspace-accessible folder, and exposes them to Codex through the existing file/session processing path. File handling must preserve real backend/workspace configuration and must not introduce mock/demo data paths in release builds.

## Regression Tests

- Backend upload test accepts valid .pdf, .pptx, .xlsx, and .docx files and stores them under the expected session/workspace-accessible folder.
- Backend upload test rejects unsupported extensions and suspicious filenames/path traversal attempts.
- Backend upload test preserves existing supported attachment types and does not break current chat, reading, project/factory creation, or non-bridge repository flows.
- Mobile test or manual DEV validation confirms the file picker can select PDF, PowerPoint, Excel, and Word documents on Android.
- Mobile/backend integration test confirms an uploaded office document appears in the session attachment list or equivalent Codex-readable context.
- Error-state test confirms unsupported or oversized files produce a user-visible failure without crashing the app.
- Release/build validation confirms real API_BASE_URL/bridge configuration is used and no mock/demo data path is introduced.

## Evidence

- `uv run pytest tests/test_message_flow.py -k "document_message_flow or attachment_batch_flow_accepts_office_documents or attachment_batch_flow_accepts_images or attachment_batch_flow_rejects_unsupported_extension_with_office_mime or attachment_batch_flow_preserves_text_image_audio_mime_classification or image_attachment_download"`: 21 passed.
- `uv run ruff check backend/app/application/services/message_service.py backend/app/api/routes.py tests/test_message_flow.py`: passed.
- `flutter test test/widget_test.dart --plain-name "attachment picker includes supported office documents"`: passed.
- `flutter analyze lib/src/screens/chat_screen.dart test/widget_test.dart`: no issues found.
