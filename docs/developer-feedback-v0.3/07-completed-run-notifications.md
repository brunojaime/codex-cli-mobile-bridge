# 07. Completed Run Notifications

## Objective

Notify the app user when a complete feedback workflow has finished.

## User Flow

1. User sends a batch.
2. Workflow runs in Codex.
3. App later detects that the batch is complete.
4. App shows a notification/indicator for the completed batch.

## Scope

- Notify at batch completion only.
- Do not notify for each screenshot/comment.
- Do not notify only because generator finished if reviewer or release is still pending.
- Start with in-app notifications; Android system notifications can be a later phase.

## Backend Impact

- Track notification read/unread state per batch.
- Mark notification as available when workflow reaches terminal state.
- Include notification status in history/detail responses.

## Flutter Package Impact

- Poll or refresh notifications when app opens/resumes.
- Show new completed-run indicator.
- Allow marking notification as read.

## Validation

- Completed batch creates one unread notification.
- Active batch does not create notification.
- Generator-reviewer notifies only after reviewer completion.
- Release-enabled notifies only after release completion or release failure.
- Marking as read decrements unread count.

## Tests

- Backend tests for notification creation rules.
- Backend test for read/unread update.
- Flutter widget test for notification indicator.
- Flutter HTTP mock test for read action.

## Operational Constraint

Do not restart the Bridge backend to force notification state during active runs. Use test records or isolated test processes.
