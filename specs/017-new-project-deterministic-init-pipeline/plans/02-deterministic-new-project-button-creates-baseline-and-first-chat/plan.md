# Deterministic New Project Button Creates Baseline And First Chat

Status: completed

Change the New Project button so it creates or focuses the first chat and starts
the deterministic init pipeline before business LLM work.

## Deterministic Pipeline Scope

- Button starts or resumes init.
- First chat is created immediately.
- Draft, chat, init job, and generated workspace are linked.
- Chat timeline shows deterministic phase progress.
- Business LLM work is gated until init is ready or explicitly continued with a
  blocked context pack.

## Tasks

- T006 Change New Project button flow to create or focus the first New Project chat before business LLM work.
- T007 Start or resume deterministic init from the New Project button and link it to the draft/chat.
- T008 Render init phase progress, blockers, commands, and retry actions in the chat timeline.
- T009 Block business LLM actions until init is `ready` or explicitly continued with blocked context.
- T010 Preserve New Project chat, draft, init job, and workspace continuity across app restarts.
