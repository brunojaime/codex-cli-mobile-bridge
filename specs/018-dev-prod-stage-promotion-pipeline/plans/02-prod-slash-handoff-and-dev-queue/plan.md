# PROD Slash Handoff And DEV Queue Plan

## Goal

Add the explicit slash/action path that lets PROD create an immutable DEV
handoff without teaching normal PROD agents about DEV or granting mutation
permissions.

## Scope

- Temporary slash/action context.
- Handoff payload schema.
- Queue endpoint/tool.
- Audit records and redaction.
- Frontend action behavior.

## Tasks

- T007 Define PROD slash/action contract for temporary DEV handoff context loading.
- T008 Implement queue payload schema, validation, immutability, idempotency keys, and source/target environment checks.
- T009 Add backend endpoint/tool for enqueue-only DEV handoffs with no file-write or command permissions.
- T010 Add frontend slash/action UI that enters temporary plan/handoff mode and exits after enqueue.
- T011 Add tests that slash mode can enqueue but cannot edit files, run commands, restart services, or launch DEV agents.
- T012 Add handoff audit records with source session, selected context, created item id, and redacted evidence.

## Acceptance Criteria

- Normal PROD chat has no DEV instructions.
- Slash/action context is loaded only for the handoff action.
- The only successful operation in slash mode is enqueue.
- Handoff items are immutable after creation except for control-plane status
  transitions.

## Validation

- API tests for valid enqueue, invalid environment, duplicate idempotency key,
  and forbidden operations.
- Frontend tests for entering and leaving handoff mode.
- Redaction tests for payload/audit records.

