# 11. Quick Ask Provenance

## Objective

Preserve traceability for each quick ask: what was selected, what was asked, and what was answered.

## User Flow

1. User opens quick ask history or detail.
2. App shows screenshot preview, selected bounds, original question, answer, and timestamp.
3. User can understand exactly what the answer referred to.

## Scope

- Store screenshot or durable reference.
- Store selection points/bounds.
- Store question.
- Store answer.
- Store source app and display name.
- Store session/job/run ids if applicable.

## Backend Impact

- Persist quick ask records.
- Expose quick ask history/detail endpoints.
- Keep records filtered by `sourceApp`.

## Flutter Package Impact

- Render screenshot preview and marked area.
- Show question and answer.
- Provide link/action to act from answer.

## Validation

- Quick ask detail displays correct screenshot.
- Bounds match user selection.
- Answer belongs to correct question.
- History is filtered by source app.

## Tests

- Backend test for quick ask source filtering.
- Backend test for screenshot reference.
- Flutter widget test for provenance detail.
- Serialization test for bounds.

## Operational Constraint

Do not restart Bridge backend while validating provenance for active quick asks.
