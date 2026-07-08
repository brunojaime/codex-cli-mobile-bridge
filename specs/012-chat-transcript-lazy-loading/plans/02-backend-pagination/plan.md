# Plan 2: Backend Pagination

Implement safe backend pagination and lightweight session summary behavior.

## Scope

- Repository/service paging methods.
- Initial latest-user exchange window.
- API response metadata.
- Lightweight `GET /sessions` behavior.

## Acceptance

- Opening or listing chats no longer requires returning every message body.
- Cursor paging is stable when new messages are appended.

