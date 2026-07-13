# Deterministic Promotion Orchestrator Plan

## Goal

Create a backend promotion state machine that moves validated `dev/main` into
PROD using deterministic steps and existing scripts, never ad hoc LLM commands.

## Scope

- Promotion state machine.
- Wrapper around existing release/restart/validation scripts.
- Tool/API for validated promotion requests.
- PROD drain and approval gates.
- Evidence and rollback hints.

## Tasks

- T037 Define Promotion Orchestrator state machine for `dev/main` to PROD with preflight, validation, approval, drain, deploy, release, post-validation, notify, blocked, failed, and rollback states.
- T038 Wrap existing Android release, GitHub Actions release, backend drain/restart, post-release validation, SDD doctor, and release-network checks as deterministic promotion steps.
- T039 Add promotion API/tool that accepts validated parameters only and never exposes ad hoc shell/git/deploy command execution to the LLM.
- T040 Enforce PROD active-job drain gate and user approval gate before restart or production release.
- T041 Persist promotion evidence, logs, release tags, release URLs, backend validation, app update metadata, and rollback hints.
- T042 Add tests for blocked promotion, active job drain, failed validation, successful promotion, and no-LLM-command execution.

## Acceptance Criteria

- LLMs can request promotion only through validated tool parameters.
- Active PROD jobs block restart/release until drain says restart is safe.
- Promotion records include all commands, evidence, release tags, and
  validation outcomes.
- Existing scripts remain the deterministic primitives.

## Validation

- State machine unit tests.
- Script-wrapper tests with faked command runners.
- API/tool contract tests for allowed and forbidden parameters.

