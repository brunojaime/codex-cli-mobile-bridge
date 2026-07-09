# 04. Visible Run Status

## Objective

Let the app show the real status of each submitted feedback batch.

## User Flow

1. User sends a feedback batch.
2. App receives batch/session/job identifiers.
3. App shows status such as pending, running, review, release, complete, failed.
4. User can refresh status from the app.

## Scope

- Status belongs to a batch, not each individual screenshot.
- Status should represent the whole workflow.
- Generator-only completes after generator.
- Generator-reviewer completes after reviewer.
- Release-enabled completes after release succeeds or fails.

## Backend Impact

- Persist feedback batch records.
- Link batch to session/job/run ids.
- Provide status endpoint or include status in history endpoint.
- Derive status from existing job/session/run state instead of duplicating execution logic.

## Flutter Package Impact

- Show status labels in history/detail views.
- Poll lightly when user opens the status screen.
- Avoid aggressive background polling.

## Validation

- Submitted batch returns identifiers.
- Status changes are visible through API.
- Failed job appears failed.
- Completed workflow appears complete only when whole workflow is done.
- Disabled wrapper shows no status UI.

## Tests

- Backend test for batch status response.
- Backend test for missing job/session fallback.
- Flutter widget test for status list rendering.
- HTTP mock test for refresh status.

## Operational Constraint

Do not restart, stop, replace, or reset the real Bridge backend while validating live status. Restarting can break in-flight run tracking and make active jobs unrecoverable. Use tests, TestClient, mocks, or an isolated backend process on another port.
