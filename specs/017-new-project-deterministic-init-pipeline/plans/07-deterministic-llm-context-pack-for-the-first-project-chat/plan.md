# Deterministic LLM Context Pack For The First Project Chat

Generate the first chat context from structured init state so business implementation LLM work
starts with the real project baseline instead of repeating setup instructions.

Status: completed

## Deterministic Pipeline Scope

- `.codex/factory/init-result.json`.
- `.codex/factory/llm-start-context.md`.
- Chat/session attachment.
- Generator/reviewer prompt inputs that consume init output.
- Context-pack hash and workspace mapping tests.

## Tasks

- [x] T032 Write `.codex/factory/init-result.json` from structured init state.
- [x] T033 Write `.codex/factory/llm-start-context.md` with deterministic project context and LLM business-phase rules.
- [x] T034 Attach the LLM context pack to the first New Project chat/session.
- [x] T035 Ensure business generator/reviewer prompts consume init result instead of repeating deterministic setup work.
- [x] T038 Add backend tests for context pack contents, hashes, chat linking, and workspace mapping.
