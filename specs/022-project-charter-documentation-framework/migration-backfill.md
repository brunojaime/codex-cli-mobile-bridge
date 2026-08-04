# Migration And Backfill Guidance

This guide is for existing generated projects that predate the
`docs/project-management` framework. It is intentionally manual and
operator-safe. Do not delete or rewrite existing project documents as part of
backfill.

## Detect

1. Open the target workspace root.
2. Check whether `docs/project-management/index.md` exists.
3. Check whether `.codex/project.yaml` has a `project_management` section.
4. Check whether `docs/project-management/acta/current/acta.md`,
   `metadata.yaml`, `brand.yaml`, `render.html`, and `render-manifest.json`
   exist.

If any of those are missing, treat the workspace as needing a documentation
framework backfill.

## Backup

Before adding the framework:

1. Confirm `git status --short` and identify unrelated user changes.
2. Commit or archive the current workspace state according to the project's
   normal backup process.
3. If the project is not under git, copy existing `docs/`, `.codex/`, and
   release metadata to a timestamped backup outside the workspace.

Backfill must preserve existing documents. Never remove an existing file to fit
the new framework.

## Add Baseline Framework

Prefer regenerating the documentation framework from the same deterministic
Project Factory contract used for the project. The backfilled files should
match the current standard:

- `.codex/project.yaml` with `project_management`
- `docs/project-management/index.md`
- `docs/project-management/glossary.md`
- `docs/project-management/versioning.md`
- `docs/project-management/context-routing.md`
- `docs/project-management/acta/README.md`
- `docs/project-management/acta/current/acta.md`
- `docs/project-management/acta/current/metadata.yaml`
- `docs/project-management/acta/current/brand.yaml`
- `docs/project-management/acta/current/render.html`
- `docs/project-management/acta/current/render-manifest.json`
- `docs/project-management/acta/changelog.md`
- `docs/project-management/acta/validation-rules.md`
- `docs/project-management/acta/export-rules.md`
- dormant module folders for `wbs`, `roles`, `risks`, and `alternatives`
- `docs/project-management/assets/brand/.gitkeep`

When the original Project Factory contract is unavailable, create a conservative
initial charter from known facts only. Unknown client, product objective,
benefits, scope, and logo decisions must be explicit pending definitions.

## Preserve Existing Docs

If the workspace already has project documents in another location:

1. Keep those files where they are.
2. Add references from `docs/project-management/index.md` or the relevant
   module README.
3. Do not copy large unrelated documents into charter context by default.
4. Do not mark a client-delivered version until validation and release steps are
   run explicitly.

## Validate

After backfill, run focused validation from the bridge repository:

```bash
.venv/bin/pytest -q tests/test_project_documents_api.py tests/test_project_charter_document_service.py
python3 -m json.tool specs/022-project-charter-documentation-framework/tree.json
```

For a mobile/workbench verification:

```bash
cd frontend/mobile_app
flutter analyze
flutter test test/project_documents_panel_test.dart test/chat_screen_overflow_test.dart
```

The backfill is ready when the charter validates, `render.html` is fresh
relative to `acta.md`, and Workbench discovery shows `documents.available=true`
without listing the charter as an SDD feature spec.
