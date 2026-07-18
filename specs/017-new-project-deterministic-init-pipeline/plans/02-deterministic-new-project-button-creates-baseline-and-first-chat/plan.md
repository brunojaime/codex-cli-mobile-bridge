# Deterministic New Project Button Creates Baseline And First Chat

Status: completed

Change the New Project button so it creates or focuses the first intake chat,
confirms the domain/project contract, and starts the deterministic init pipeline
before business implementation LLM work.

## Deterministic Pipeline Scope

- Button starts or resumes guided intake.
- Contract approval starts or resumes init.
- First chat is created immediately.
- Draft, chat, init job, and generated workspace are linked.
- Chat timeline shows deterministic phase progress.
- Business implementation LLM work is gated until init is ready or explicitly
  continued with a blocked context pack.

## Tasks

- T006 Change New Project button flow to create or focus the first New Project intake chat before business implementation LLM work.
- T007 Start or resume deterministic init after contract approval and link it to the draft/chat.
- T008 Render init phase progress, blockers, commands, and retry actions in the chat timeline.
- T009 Block business implementation LLM actions until init is `ready` or explicitly continued with blocked context.
- T010 Preserve New Project chat, draft, init job, and workspace continuity across app restarts.
