# Developer Feedback v0.3 Documentation Index

This index tracks the proposed v0.3 work for the reusable Developer Feedback Template and Codex Mobile Bridge feedback workflow.

This is documentation only. Do not implement these features from this file unless the user explicitly asks for implementation.

Important operational constraint: restart the Bridge backend through `scripts/safe_restart_backend.sh` when feedback or Codex runs may be active. The script enables backend drain mode, blocks new jobs, waits for accepted runs to finish, and only then restarts the backend.

## Feature Index

1. [Local Multi-Capture Queue](developer-feedback-v0.3/01-local-multi-capture-queue.md)
2. [Preview Before Sending](developer-feedback-v0.3/02-preview-before-send.md)
3. [Audio Transcription](developer-feedback-v0.3/03-audio-transcription.md)
4. [Visible Run Status](developer-feedback-v0.3/04-visible-run-status.md)
5. [In-App Feedback History](developer-feedback-v0.3/05-in-app-feedback-history.md)
6. [Final Didactic Run Summary](developer-feedback-v0.3/06-final-run-summary.md)
7. [Completed Run Notifications](developer-feedback-v0.3/07-completed-run-notifications.md)
8. [Notification Bell And Badge](developer-feedback-v0.3/08-notification-bell-badge.md)
9. [Actionable Notification Center](developer-feedback-v0.3/09-actionable-notification-center.md)
10. [Quick Ask On Screen Selection](developer-feedback-v0.3/10-quick-ask-screen-selection.md)
11. [Quick Ask Provenance](developer-feedback-v0.3/11-quick-ask-provenance.md)
12. [Act From Quick Ask](developer-feedback-v0.3/12-act-from-quick-ask.md)
13. [Formal v0.3 Contract](developer-feedback-v0.3/13-formal-v0.3-contract.md)

## Architecture Boundary

- Flutter reusable package: user-facing feedback UI, local queue, preview, quick ask, history, notifications, and status rendering.
- Bridge backend: source app routing, batch persistence, status aggregation, audio transcription, final summaries, notifications, and v0.3 API contract.
- Codex workflow: generator, reviewer, release, quick ask answer, and final summary execution.
- Consumer apps such as Ambientando Calendar: only configure the wrapper, update the package ref, and publish a new app build when required.

## Release Principle

Consumer apps should not receive app-specific logic for these features. They should inherit the behavior by updating the reusable package and releasing a new APK. Any new configuration should be optional or capability-driven so existing wrapper usage remains compatible.
