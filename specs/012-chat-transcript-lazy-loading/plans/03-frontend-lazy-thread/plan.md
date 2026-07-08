# Plan 3: Frontend Lazy Thread

Render chat transcripts from a bounded initial window and fetch older pages on demand.

## Scope

- API client and model changes.
- Chat controller window state.
- Scroll-up loading behavior.
- Loading/retry/exhausted states.

## Acceptance

- The user can read the latest exchange immediately and scroll upward for history.
- Existing chat rendering modes continue to work over the loaded window.

