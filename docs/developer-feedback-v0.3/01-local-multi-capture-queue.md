# 01. Local Multi-Capture Queue

## Objective

Allow a user to capture multiple screenshots, each with its own comment, selection bounds, and optional audio, before sending anything to Codex.

## User Flow

1. User enables the feedback wrapper.
2. User marks an area of the screen.
3. User adds comment and optional audio.
4. User saves the item locally.
5. User repeats the process for more screenshots.
6. User later opens the queue and sends all selected items as one batch.

## Scope

- Store feedback items locally in the wrapper until sent.
- Preserve per-item screenshot, comment, bounds, points, audio metadata, and creation time.
- Keep queue visible only when the wrapper is enabled.
- Support clearing one item or the whole queue.
- Keep the queue generic for any `sourceApp`.

## Backend Impact

The backend receives the complete batch only when the user sends it. It should still accept legacy individual queue submissions for compatibility.

## Flutter Package Impact

- Maintain an in-memory queue at minimum.
- Consider optional persistence later if app restarts should preserve drafts.
- Keep API compatible with existing wrapper configuration.

## Validation

- Saving one item increments pending count.
- Saving multiple items keeps item order.
- Deleting one item does not delete others.
- Clearing queue removes all local drafts.
- Disabled wrapper shows no queue UI and intercepts no app gestures.
- Batch send uses all queued items.

## Tests

- Flutter widget test for adding three feedback items.
- Flutter widget test for deleting one queued item.
- Flutter widget test for clearing queue.
- Flutter widget test proving disabled wrapper has no queue controls.
- Package serialization test for multiple items in one batch.

## Operational Constraint

Do not restart the Bridge backend while validating an active user flow. Use package-level tests or an isolated backend test process.
