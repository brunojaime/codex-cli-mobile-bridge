# Tasks

This file is the legacy task index. Task numbering is local to each plan in `tree.json`.

## Plan 1: Manifest Contract

- [x] T001 Add project manifest dataclasses and validation service. ([Task 1](./tasks/plan-1-task-1/task.md))
- [x] T002 Add default auth, RBAC, admin, notification, Codex, SDD, and release manifest sections. ([Task 2](./tasks/plan-1-task-2/task.md))
- [x] T003 Add slug/path validation under PROJECTS_ROOT with no writes. ([Task 3](./tasks/plan-1-task-3/task.md))
- [x] T004 Add tests for valid defaults, invalid names/slugs, existing folders, owner permissions, seed-admin env-only behavior, and SDD artifacts. ([Task 4](./tasks/plan-1-task-4/task.md))

## Plan 2: Backend Draft And Job API

- [x] T005 Add API schemas for wizard options, draft request, dry-run response, generate response, and job status. ([Task 1](./tasks/plan-2-task-1/task.md))
- [x] T006 Add project-factory routes. ([Task 2](./tasks/plan-2-task-2/task.md))
- [x] T007 Add persisted draft/job state model and deterministic status payloads. ([Task 3](./tasks/plan-2-task-3/task.md))
- [x] T008 Add route tests for draft, dry-run, validation errors, status, history, duplicate generation, and recovery. ([Task 4](./tasks/plan-2-task-4/task.md))

## Plan 3: Mobile Chat Flow

- [x] T009 Add New project entry point to the existing Flutter app. ([Task 1](./tasks/plan-3-task-1/task.md))
- [x] T010 Add chat-first New Project mode that asks for name, business type, goal, platforms, visual references, logo/icon, backend, style, preview, and confirmation through the normal conversation. ([Task 2](./tasks/plan-3-task-2/task.md))
- [x] T010a Gate reviewer/build mode until the agent has validated spec, plan, tasks, domain entities, and baseline diagram readiness with the user. ([Task 3](./tasks/plan-3-task-3/task.md))
- [x] T011 Add API client calls, progress display, and Project Factory History. ([Task 4](./tasks/plan-3-task-4/task.md))
- [x] T012 Add Flutter widget tests for the wizard, progress, and history. ([Task 5](./tasks/plan-3-task-5/task.md))

## Plan 4: Research And Visual Direction

- [x] T013 Add business-type research prompt/output contracts. ([Task 1](./tasks/plan-4-task-1/task.md))
- [x] T014 Add typical-app UX pattern prompt generation. ([Task 2](./tasks/plan-4-task-2/task.md))
- [x] T015 Add uploaded-image handoff, project copy, and visual reference docs. ([Task 3](./tasks/plan-4-task-3/task.md))
- [x] T016 Add design token/style guide placeholders and generator tests. ([Task 4](./tasks/plan-4-task-4/task.md))

## Plan 5: Local Generator

- [x] T017 Write local project directory and .codex/project.yaml. ([Task 1](./tasks/plan-5-task-1/task.md))
- [x] T018 Generate README, AGENTS, research/design/release/infra folders. ([Task 2](./tasks/plan-5-task-2/task.md))
- [x] T019 Generate initial specs/001-product-foundation package. ([Task 3](./tasks/plan-5-task-3/task.md))
- [x] T020 Initialize git safely and prove no secrets are committed. ([Task 4](./tasks/plan-5-task-4/task.md))

## Plan 6: Flutter And Backend Templates

- [x] T021 Generate Flutter app with responsive web/mobile shell. ([Task 1](./tasks/plan-6-task-1/task.md))
- [x] T022 Add auth, Google placeholder config, admin shell, RBAC guards, domain CRUD shell, and notifications shell. Feedback Bridge and updater remain generated follow-up tasks. ([Task 2](./tasks/plan-6-task-2/task.md))
- [x] T023 Generate FastAPI backend with health, auth, RBAC, seed admin, notifications, domain resources, and tests. ([Task 3](./tasks/plan-6-task-3/task.md))
- [x] T024 Run generated Flutter/backend validation through generated E2E script. ([Task 4](./tasks/plan-6-task-4/task.md))

## Plan 7: GitHub And Release Readiness

- [x] T025 Add mandatory initial git commit and generated GitHub publish script. ([Task 1](./tasks/plan-7-task-1/task.md))
- [x] T026 Generate AWS, App Store, and Play Store readiness docs. ([Task 2](./tasks/plan-7-task-2/task.md))
- [x] T027 Mark Google/AWS/store credentials as pending without failing local project creation. ([Task 3](./tasks/plan-7-task-3/task.md))
- [x] T027a Execute GitHub publish, Android release, installable-app registration, and remote publication verification from the Factory runner when remote publication mode is active. ([Task 4](./tasks/plan-7-task-4/task.md))
- [x] T027b Mark publication gaps as blocked with concrete command/log output instead of ready when GitHub origin, release APK, or Bridge registration is missing. ([Task 5](./tasks/plan-7-task-5/task.md))

## Plan 8: End-To-End Validation

- [x] T028 Add project-factory doctor. ([Task 1](./tasks/plan-8-task-1/task.md))
- [x] T029 Add generated-project E2E validation flow. ([Task 2](./tasks/plan-8-task-2/task.md))
- [x] T030 Validate Workbench discovery, auth/RBAC, admin, domain CRUD, notifications, Flutter, backend, and no secrets. ([Task 3](./tasks/plan-8-task-3/task.md))

## Plan 9: Acceptance Hardening

- [x] T031 Persist drafts/jobs and recover queued/running as interrupted. ([Task 1](./tasks/plan-9-task-1/task.md))
- [x] T032 Add draft/job history APIs and mobile history panel. ([Task 2](./tasks/plan-9-task-2/task.md))
- [x] T033 Document operational config, toolchain, and generated validation. ([Task 3](./tasks/plan-9-task-3/task.md))
- [x] T034 Run acceptance validation. ([Task 4](./tasks/plan-9-task-4/task.md))

## Plan 10: Post-Release Chat-Mode Hardening

- [x] T035 Add backend version/capability metadata for Project Factory. ([Task 1](./tasks/plan-10-task-1/task.md))
- [x] T036 Harden backend PID handling and post-restart validation. ([Task 2](./tasks/plan-10-task-2/task.md))
- [x] T037 Move primary New project UX from modal form to chat-mode kickoff. ([Task 3](./tasks/plan-10-task-3/task.md))
- [x] T038 Update creation defaults to 20 generator and 20 reviewer runs. ([Task 4](./tasks/plan-10-task-4/task.md))
- [x] T039 Generate mandatory baseline Workbench diagrams and SDD indexes for new projects. ([Task 5](./tasks/plan-10-task-5/task.md))

## Plan 11: Publication Contract Hardening

- [x] T040 Document the SAT Showroom gap where a local foundation finished without GitHub repo, Android release, or Bridge app registration. ([Task 1](./tasks/plan-11-task-1/task.md))
- [x] T041 Add runner-owned github_publish, android_release, and installable_app_registration phases for remote Project Factory jobs. ([Task 2](./tasks/plan-11-task-2/task.md))
- [x] T042 Generate scripts/publish_android_release.sh and a stable <sourceApp>.apk GitHub release asset. ([Task 3](./tasks/plan-11-task-3/task.md))
- [x] T043 Pass required GitHub/release/Bridge environment variables to generated publication scripts without printing secrets. ([Task 4](./tasks/plan-11-task-4/task.md))
- [x] T044 Treat missing external publication configuration as blocked, not ready. ([Task 5](./tasks/plan-11-task-5/task.md))
- [x] T045 Add regression tests for remote publication phase execution and blocked publication outcomes. ([Task 6](./tasks/plan-11-task-6/task.md))
