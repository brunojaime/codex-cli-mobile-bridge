# 09. Actionable Notification Center

## Objective

Provide a central in-app view for completed, active, failed, and summarized feedback runs.

## User Flow

1. User taps bell or history control.
2. App opens notification center.
3. User sees unread completed runs, active runs, failed runs, and available summaries.
4. User opens detail or marks items as read.

## Scope

- Filter by current `sourceApp`.
- Show status, date, item count, preset, release flag, and summary availability.
- Provide mark-read action.
- Provide open-summary action when available.

## Backend Impact

- Return combined history/notification data.
- Support mark-read endpoint.
- Keep data app-scoped by `sourceApp`.

## Flutter Package Impact

- Build reusable notification center UI.
- Use simple tabs or sections.
- Avoid app-specific text beyond display name.

## Validation

- Completed unread items appear first.
- Active items are visible but not counted as unread completed notifications.
- Failed items are clear.
- Mark-read persists.
- Summary opens from completed item.

## Tests

- Backend test for notification center response.
- Backend test for mark-read.
- Flutter widget test for sections.
- Flutter widget test for summary action.

## Operational Constraint

Do not restart Bridge backend during manual validation with active user runs. Use existing running process and read-only refreshes.
