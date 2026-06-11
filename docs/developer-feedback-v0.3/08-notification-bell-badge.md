# 08. Notification Bell And Badge

## Objective

Show a notification bell with unread count in the feedback wrapper UI.

## User Flow

1. Wrapper is enabled.
2. App detects unread completed-run notifications.
3. Toolbar shows bell with badge count.
4. User taps bell to open notification center.

## Scope

- Bell appears only when wrapper is enabled.
- Badge count represents unread completed-run notifications for current `sourceApp`.
- Badge should handle 0, 1, 2, and large counts.
- Disabled wrapper shows no bell.

## Backend Impact

- Provide unread count filtered by `sourceApp`.
- Include count in notification/history endpoint or a dedicated endpoint.

## Flutter Package Impact

- Add bell UI to toolbar.
- Keep layout stable on small screens.
- Refresh count on open/resume and after mark-read.

## Validation

- Badge hidden at zero.
- Badge shows correct count.
- Badge updates after reading notifications.
- Disabled wrapper has no bell.
- Toolbar remains draggable and within viewport.

## Tests

- Flutter widget test for zero unread.
- Flutter widget test for unread count.
- Flutter widget test for disabled wrapper.
- Flutter widget test for compact viewport.

## Operational Constraint

Do not restart Bridge backend while validating notification count against live active runs.
