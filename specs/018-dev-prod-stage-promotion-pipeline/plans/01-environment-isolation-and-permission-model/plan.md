# Environment Isolation And Permission Model Plan

## Goal

Create a deterministic environment identity and permission model that makes PROD,
DEV, and control-plane behavior explicit and enforceable outside prompts.

## Scope

- Environment identity schema.
- Capability matrix for each operating mode.
- Backend health/environment payload.
- PROD normal-mode hard denials.
- Tests proving no hidden DEV/promotion context is available to normal PROD
  agents.

## Tasks

- T001 Define environment identity schema for PROD, DEV, control plane, stage, channel, backend URL, app label, and allowed capabilities.
- T002 Define deterministic permission matrix for PROD normal mode, PROD slash mode, DEV stage mode, DEV integration mode, and PROD promotion mode.
- T003 Add backend environment identity source and health payload fields used by frontend and tools.
- T004 Enforce PROD normal-mode denial for Bridge code writes, shell commands, restarts, deploys, and DEV workspace reads.
- T005 Add tests proving PROD normal sessions cannot access DEV/backlog/promotion context or mutation capabilities.
- T006 Document environment isolation rules in operator-facing docs without injecting them into normal PROD agent context.

## Acceptance Criteria

- Backend can report environment identity without relying on prompt text.
- PROD normal mode has no mutation capabilities for Bridge self-improvement.
- DEV and control-plane capabilities are granted only by backend mode/session
  metadata.
- Tests fail if PROD normal sessions can access DEV stage data or mutation
  tools.

## Validation

- Backend unit tests for environment identity and capability matrix.
- API tests for PROD denial behavior.
- SDD doctor remains compatible with existing specs.

