# Stage Registry Worktrees And Chat Binding Plan

## Goal

Ensure every DEV spec runs in its own branch, worktree, backend context, and
chat so parallel work never shares mutable checkout state.

## Scope

- Stage registry schema.
- Deterministic branch/worktree creation and reuse.
- Session binding to stage metadata.
- Backend guardrails for workspace/branch mismatch.
- Frontend stage identity display.

## Tasks

- T019 Define Stage Registry schema for spec id, stage id, branch, worktree, base branch, backend URL, app channel, status, and ownership.
- T020 Implement deterministic branch and worktree creation/reuse for one spec per stage.
- T021 Bind every DEV chat/session to exactly one stage worktree and branch through backend-owned session metadata.
- T022 Add backend guards that reject DEV stage actions when `workspace_path`, branch, or worktree do not match the registry.
- T023 Render DEV chat header with environment, spec, branch, worktree label, and backend URL source.
- T024 Add tests for parallel spec 017/spec 018 stages, branch mismatch rejection, and chat-stage continuity.

## Acceptance Criteria

- One chat maps to one stage.
- One stage maps to one branch and one worktree.
- The frontend shows the backend-provided stage identity in every DEV chat.
- A branch/worktree mismatch blocks execution before commands run.

## Validation

- Backend tests for registry creation, lookup, and mismatch rejection.
- Git/worktree adapter tests using temporary repos.
- Flutter tests for visible stage header and stage switching.

