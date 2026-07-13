# DEV Agent Execution And Review Loop Plan

## Goal

Reuse the existing MessageService agent chain for DEV stage implementation runs,
with Generator/Reviewer loops bound to the stage worktree and deterministic final
evidence.

## Scope

- DEV stage AgentConfiguration presets.
- Generator/Reviewer auto-chain reuse.
- Reviewer JSON completion contract.
- Final user-facing summary.
- Stage run controls and recovery.

## Tasks

- T025 Define DEV stage AgentConfiguration presets for Generator/Reviewer pairs and optional Summary completion.
- T026 Reuse MessageService auto-chain for Generator -> Reviewer -> Generator loops inside the registered stage chat.
- T027 Add Reviewer completion JSON contract and final summary synthesis for DEV stage runs.
- T028 Persist run evidence, changed files, tests, risks, user validation checklist, and reviewer completion state.
- T029 Add DEV worker controls for start, pause, cancel, retry, and resume stage agent runs.
- T030 Add tests for reviewer continue, reviewer complete, failed follow-up recovery, and final summary output.

## Acceptance Criteria

- DEV stage execution uses the existing agent chain, not a second
  implementation loop.
- Reviewer can continue work or terminate the run with structured JSON.
- Final output gives the user what changed, tests, risks, and manual validation
  steps.
- Failed follow-ups can be recovered without losing stage binding.

## Validation

- MessageService tests for Generator/Reviewer chaining and completion.
- Stage run tests for retry/cancel/resume.
- Summary tests for expected final format.

