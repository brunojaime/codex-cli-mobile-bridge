# 05. In-App Feedback History

## Objective

Show previous feedback batches sent from the current app.

## User Flow

1. User opens feedback history from wrapper UI.
2. App lists batches for its `sourceApp`.
3. User can open a batch detail.
4. Detail shows screenshots metadata, comments, status, preset, and summary if available.

## Scope

- Filter history by `sourceApp`.
- Include date, item count, preset, status, session id, job id, and release flag.
- Do not show other apps' history unless explicitly configured.
- Keep history UI available only when wrapper is enabled.

## Backend Impact

- Persist feedback batch records.
- Add history endpoint filtered by `sourceApp`.
- Return stable v0.3 response shape.

## Flutter Package Impact

- Add history entry point.
- Render list and detail.
- Support refresh.
- Handle offline/unavailable Bridge gracefully.

## Validation

- App sees only its own history.
- History updates after new batch send.
- Empty history state is clear.
- Bridge unavailable state is clear.

## Tests

- Backend test for source app filtering.
- Backend test for empty history.
- Backend test for newest-first ordering.
- Flutter widget test for history list.
- Flutter widget test for empty/error states.

## Operational Constraint

Do not restart the Bridge backend during manual history validation if user runs are active. Use read-only API calls against the running process.
