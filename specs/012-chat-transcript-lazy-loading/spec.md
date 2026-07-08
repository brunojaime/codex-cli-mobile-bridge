# Chat Transcript Lazy Loading

id: 012-chat-transcript-lazy-loading
status: validated
owner: codex-mobile-bridge

## Intent

Make opening a chat fast and predictable even when the conversation contains many user, generator, reviewer, summary, specialist, and system messages.

The mobile app must not load the entire transcript when the user opens a chat. It should open at the most recent user-authored message and include every message after that point, because that is the active conversational unit the user needs to continue reading. Older history is loaded only when the user scrolls upward or explicitly requests older messages.

## Product Outcome

When a chat is opened, the user sees the latest user message and all following assistant/agent messages immediately. If there is older conversation history before that user message, the top of the list exposes a loading affordance and loads older pages as the user scrolls upward.

Long New Project, generator/reviewer, Workbench, and feedback conversations should feel responsive without losing context or corrupting active runs.

## Core Rules

- Opening a chat must fetch a bounded transcript window, not the full message history.
- The default anchor is the latest visible user-authored message.
- The initial window includes the anchor user message and all later messages.
- Older messages are fetched in pages when scrolling upward.
- Message ordering must remain chronological in the UI.
- New messages arriving after the initial window append normally without forcing a full reload.
- Session summary, current run, active jobs, reviewer state, and conversation product must remain accurate even when the transcript body is partial.
- The backend must expose whether the returned transcript is partial and whether older pages exist.
- Attachments, job links, feedback links, recovery messages, and turn summaries must remain addressable when the related message is visible.
- No endpoint may require the frontend to download a full transcript just to render the chat list or open the latest exchange.

## Initial Window Semantics

The initial chat detail endpoint should support a mode equivalent to:

```text
anchor=latest_user_message
include_after_anchor=true
older_limit=<page size>
```

The returned message window begins at the latest eligible user message and includes every message after it. If that would still exceed a safety cap because a single run generated a very large number of messages, the backend may apply a secondary cap, but it must expose truncation metadata and a cursor to fetch the missing older part of that run.

If a chat has no user-authored messages, the backend returns the latest page of messages with the same paging metadata.

## Pagination Contract

The backend must provide stable cursors for loading older transcript pages. Cursor semantics must not depend on list indexes that can shift when messages are appended.

Recommended cursor fields:

- `oldest_cursor`: cursor before the first visible message.
- `newest_cursor`: cursor after the last visible message, if needed later.
- `has_older`: true when older messages exist before the returned window.
- `has_newer`: true only when fetching historical pages that are not at the live tail.
- `window_anchor_message_id`: the latest user message selected for the initial window.
- `is_partial`: true when the response does not contain the full transcript.

The page size should be configurable, with a small mobile default. The product default should target the latest user exchange, not a fixed number of messages.

## Frontend Behavior

The mobile app should:

- show a placeholder/session shell immediately from the existing session summary;
- fetch the initial transcript window;
- render the latest user exchange at the bottom-ready reading position;
- lazy-load older pages when the user scrolls near the top;
- preserve scroll position when older pages are prepended;
- keep the composer usable while older history loads;
- show a non-blocking loading row for older messages;
- show a retry affordance when loading older messages fails;
- avoid duplicate messages when pages overlap or live updates append messages.

The frontend should not use transcript filtering as a substitute for pagination. Collapse modes and summary views may still hide messages visually, but the data window itself must stay bounded.

## Backend Behavior

The backend should:

- keep `GET /sessions` lightweight enough for chat lists;
- allow `GET /sessions/{id}` to return a default partial window or introduce a compatible endpoint for transcript windows;
- expose explicit request parameters for full transcript only when needed by developer tools or exports;
- compute session summary/current run metadata without requiring full message serialization in the response body;
- support stable message pagination by `created_at` plus `id` or another monotonic cursor;
- keep existing clients compatible during migration.

## Non-Goals

- Do not change Codex CLI execution behavior.
- Do not change how generator/reviewer jobs are scheduled.
- Do not delete or summarize old messages to save storage.
- Do not change New Project build gating.
- Do not touch generated project repos such as SAT Showroom.

## Worktree And Parallel Implementation Guidance

This spec is safe to implement independently from New Project Guided Intake and Slash Command Palette if each implementation runs in a separate worktree or branch. The risky operations are backend restarts, shared state migrations, or edits to the same frontend chat controller/API files.

Implementation agents should:

- use a dedicated worktree for this spec;
- avoid restarting the live backend while another long-running Codex session is active;
- avoid editing generated app project folders;
- merge through normal git review rather than copying files between worktrees;
- run mobile and backend regression tests before deploying.

## Acceptance Criteria

- Opening a long chat no longer downloads the entire transcript.
- The first visible loaded exchange starts at the latest user-authored message and includes later generator/reviewer/assistant messages.
- Scrolling upward loads older pages without visual jumps or duplicates.
- Chat list loading does not serialize every full message body for every session.
- Active jobs, reviewer state, current run, and message recovery still render correctly for the visible window.
- Tests cover initial anchor selection, cursor pagination, older-page loading, append behavior, attachments, and active run metadata.

