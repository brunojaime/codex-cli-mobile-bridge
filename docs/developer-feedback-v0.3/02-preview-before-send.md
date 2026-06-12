# 02. Preview Before Sending

## Objective

Show a clear preview of the pending feedback batch before it starts a Codex run.

## User Flow

1. User opens pending feedback.
2. App shows queued screenshots, comments, audio indicators, and selection metadata.
3. User chooses workflow preset and release option.
4. User confirms send.

## Scope

- Show screenshot thumbnails.
- Show per-item comments.
- Show selection bounds summary.
- Show audio presence, duration, and byte size.
- Show selected preset.
- Show `releaseWhenComplete`.
- Allow deleting items before send.

## Backend Impact

No backend call is required for local preview. Presets may be loaded from `/feedback-workflow-presets`.

## Flutter Package Impact

- Add preview UI inside reusable package.
- Avoid app-specific labels except `sourceDisplayName`.
- Ensure responsive layout on mobile screens.

## Validation

- Preview shows all queued screenshots.
- Preview updates after deleting an item.
- Preview preserves preset selection.
- Send button disabled while batch is empty or sending.
- Failed send leaves items in queue.

## Tests

- Flutter widget test for screenshot preview.
- Flutter widget test for preset dropdown.
- Flutter widget test for release checkbox.
- Flutter widget test for failed send preserving queue.
- HTTP mock test asserting sent batch matches preview contents.

## Operational Constraint

Do not restart the Bridge backend during manual preview-to-send validation if a real user run is active.
