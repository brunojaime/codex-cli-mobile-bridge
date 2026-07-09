# Chat Transcript Lazy Loading Plan

## Phase 1: Message Window Contract

Define the transcript window contract, cursor semantics, and compatibility behavior for existing clients.

## Phase 2: Backend Pagination

Add bounded session detail/message window APIs and make chat list summaries avoid full transcript serialization.

## Phase 3: Frontend Lazy Thread

Update the mobile chat controller and UI to open with the latest user exchange and load older pages on upward scroll.

## Phase 4: Active Run And Context

Preserve current run, reviewer state, jobs, recovery affordances, attachments, and conversation context when only a partial transcript is loaded.

## Phase 5: Validation And Rollout

Add backend, Flutter, integration, and performance regression coverage. Deploy only after confirming it does not disrupt active long-running sessions.

