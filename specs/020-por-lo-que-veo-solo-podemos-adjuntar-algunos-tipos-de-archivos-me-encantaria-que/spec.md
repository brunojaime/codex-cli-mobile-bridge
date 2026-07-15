# Agregar soporte para adjuntar PDF, PPTX, XLSX, DOCX y otros archivos de oficina en Codex Mobile Bridge

## Problem

Actualmente Codex Mobile Bridge parece permitir adjuntar solo algunos tipos de archivos. El usuario quiere poder adjuntar documentos comunes como PDF, PowerPoint, Excel y Word para que el backend los guarde en una carpeta accesible a la sesión/workspace y Codex pueda procesarlos o inspeccionarlos desde ahí. Esta funcionalidad afecta backend/app de producción, por lo que no debe implementarse en PROD; debe entrar a DEV mediante handoff/queue.

## Context

Handoff generado desde PROD en modo read-only para revisión DEV. Sesión PROD: d6570ff3-4913-4e64-8acc-d81fe5470416. Workspace: /home/batata/Projects/codex-cli-mobile-bridge. El pedido original está en español y solicita ampliar los tipos de adjuntos permitidos: PDF, PPTX, Excel, Word y potencialmente otros formatos. La respuesta de PROD indicó que no podía tocar backend/app de producción y que la implementación debía pasar por DEV vía /dev-handoff. Assumption: los formatos mínimos requeridos son .pdf, .pptx, .xlsx, .docx; formatos legacy como .ppt, .xls, .doc y otros tipos de oficina deben evaluarse explícitamente en DEV antes de habilitarse.

## Acceptance Criteria

DEV materializes a spec named 020-por-lo-que-veo-solo-podemos-adjuntar-algunos-tipos-de-archivos-me-encantaria-que and a plan named 01-por-lo-que-veo-solo-podemos-adjuntar-algunos-tipos-de-archivos-me-encantaria-que from this handoff. Implementation happens only in the DEV stage/worktree. PROD chat, reading, project/factory creation, and non-bridge repository work continue to function. Strong bridge modifications remain blocked in PROD and enter DEV through the queue. Targeted backend and mobile tests pass before promotion is considered. Users can attach at least PDF, PPTX, XLSX, and DOCX files from the mobile app. Backend validation accepts the supported file extensions/MIME types, rejects unsupported or unsafe files with a clear error, stores accepted files in the correct session/workspace-accessible folder, and exposes them to Codex through the existing file/session processing path. File handling must preserve real backend/workspace configuration and must not introduce mock/demo data paths in release builds.

## Implemented DEV Policy

The DEV implementation supports `.pdf`, `.docx`, `.pptx`, and `.xlsx`, while preserving existing text/code, image, and audio attachment support. Legacy `.doc`, `.xls`, `.ppt`, archives, and arbitrary unsupported extensions that claim an office/PDF MIME type remain explicitly unsupported for this spec.

When a filename includes a useful extension, office/PDF uploads validate by that extension first and reject unsupported extensions even if the uploaded MIME type is otherwise supported. Existing MIME-first classification for `text/*`, `image/*`, and `audio/*` remains preserved for Android/provider filenames with uncommon extensions.

Accepted non-image documents are copied into the active workspace under `.codex-mobile-bridge/attachments/<session-id>/`, and the Codex execution prompt includes the stored path so the file can be inspected from the real workspace. No mock/demo/local demo data paths were introduced.

## Merge Readiness

Implementation was committed in the DEV stage branch as `8e5b88f Support office document attachments`. The branch was then updated with `dev/main` through merge commit `8aa327b Merge branch 'dev/main' into dev/spec-020-por-lo-que-veo-solo-podemos-adjuntar-algunos-tipos-de-archivos-me-encantaria-que`, resolving the stale-branch preflight blocker for this worktree. Focused backend and mobile validations passed again after that merge.

## Risks

- Office documents can contain large files or embedded content; DEV should enforce size limits and avoid unsafe parsing in the bridge layer unless a secure parser already exists.
- MIME types differ across Android providers, so validation should combine extension and MIME checks carefully without accepting arbitrary binary files.
- Legacy formats .doc, .xls, and .ppt may be harder to inspect safely than modern .docx, .xlsx, and .pptx; enabling them should be an explicit DEV decision.
- If Codex can only read files after they are placed in a specific workspace/session folder, storing attachments elsewhere may make uploads appear successful but unusable.
- Changing file picker filters may unintentionally hide currently supported file types if the existing allowlist is replaced instead of extended.
- PROD policy forbids strong bridge modifications in PROD; all implementation and tests must stay in DEV until reviewed and promoted.
