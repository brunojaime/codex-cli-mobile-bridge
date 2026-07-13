# PROD Backend Update Idle Gate Plan

## Goal

Apply prepared PROD backend updates automatically only when PROD is truly idle,
and otherwise keep a visible pending-update notice with an explicit force option.

## Scope

- PROD backend update state machine.
- Full quiescence detector for running and pending agent chains.
- Automatic update execution when idle.
- Persistent frontend notification and acknowledgement state.
- Force restart/update path with explicit confirmation.
- Tests for idle, busy, pending-chain, forced, failed, and acknowledged states.

## Tasks

- T061 Define PROD backend update state machine, including update_available, waiting_for_idle, auto_update_eligible, updating, updated_pending_ack, acknowledged, force_requested, blocked, and failed.
- T062 Implement PROD quiescence detector that includes active CLI jobs, active_agent_run_id, queued/reserved agent turns, Generator -> Reviewer -> Generator follow-ups, Summary follow-ups, SDD/Codex jobs, Project Factory jobs, and pending background tasks.
- T063 Implement automatic PROD backend update when a prepared update is available and the quiescence detector proves no active or pending agent chain exists.
- T064 Add persistent PROD update notification UI that shows waiting-for-idle, updating, updated, failed, and acknowledgement states without requiring a modal pop-up.
- T065 Add force restart/update action with strong confirmation, interruption evidence, recovery summary, and post-update validation.
- T066 Add tests for idle auto-update, busy waiting, Generator-to-Reviewer pending chains, forced restart, failed validation, and user acknowledgement dismissal.

## Acceptance Criteria

- A prepared PROD backend update applies automatically when no active or pending
  agent chain exists.
- A prepared update does not restart PROD while any running job, reserved
  follow-up, pending Reviewer, pending Generator, pending Summary, SDD/Codex job,
  Project Factory job, or background task remains.
- The user sees a persistent pending-update notice while the update is waiting
  for idle, plus a force action protected by strong confirmation.
- A successful update leaves a persistent updated/acknowledgement notice until
  the user dismisses it.
- A forced update records interrupted work, recovery status, post-validation
  results, and rollback hints.

## Validation

- Unit tests for quiescence detector inputs and state transitions.
- Backend tests for automatic idle update and busy waiting.
- Frontend tests for pending, updating, updated, failed, force, and dismissed
  notification states.
- Integration tests proving a Generator completion with a pending Reviewer does
  not count as idle until the full chain finishes.
