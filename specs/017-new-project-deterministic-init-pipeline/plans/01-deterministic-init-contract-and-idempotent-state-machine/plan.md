# Deterministic Init Contract And Idempotent State Machine

Status: completed

Define the domain contract for New Project init as a resumable, deterministic
pipeline. This plan moves the shape of setup work out of prompts and into typed
state.

## Deterministic Pipeline Scope

- Init job identity and lifecycle.
- Stable phase names.
- Phase idempotency and retry behavior.
- Command evidence and artifact summaries.
- Remote resource identities for GitHub, Cloudflare, D1, releases, and Bridge.
- Completion states that distinguish ready, blocked, failed, cancelled, and
  resumable work.

## Tasks

- T001 Define persisted init job, phase, command evidence, blocker, artifact, and context-pack schemas.
- T002 Define stable deterministic init phase names and idempotency rules.
- T003 Define draft, chat, init job, generated workspace, and Workbench scope relationships.
- T004 Define remote-resource identity model for GitHub repo, Cloudflare Worker, route, D1, release, and installable app.
- T005 Define init completion states: `ready`, `blocked_with_context`, `failed`, `cancelled`, and `resumable`.
