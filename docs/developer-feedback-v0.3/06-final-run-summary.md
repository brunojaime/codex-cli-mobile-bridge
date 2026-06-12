# 06. Final Didactic Run Summary

## Objective

Generate and display a final summary after the entire feedback workflow finishes.

## User Flow

1. User sends a batch.
2. Codex completes generator/reviewer/release workflow as configured.
3. A final summary is generated.
4. User opens summary from notification, history, or batch detail.

## Summary Requirements

The summary should be more than 10 lines and explain:

- What the user asked for.
- Which screenshots/comments were used.
- What area or bounds were selected.
- What likely issue was identified.
- What files or areas were changed.
- What implementation was done.
- What validation was run.
- Whether reviewer ran.
- Whether release ran.
- Final result.
- Any remaining risk or next step.

## Backend Impact

- Detect when workflow is complete.
- Trigger or request a final summary step.
- Store summary on the batch record.
- Expose summary through history/detail endpoints.

## Flutter Package Impact

- Show summary availability.
- Open summary detail screen/dialog.
- Keep summary associated with source screenshot/batch.

## Validation

- Summary is absent while run is active.
- Summary appears after workflow completes.
- Summary has at least 10 non-empty lines.
- Summary is tied to the correct batch.
- Failed workflow summary explains failure.

## Tests

- Backend test for summary persistence.
- Backend test for minimum line count validation or prompt instruction.
- Flutter widget test for summary detail.
- Flutter widget test for summary loading state.

## Operational Constraint

Do not restart the Bridge backend while waiting for a final summary from a live run. A restart can break completion detection.
