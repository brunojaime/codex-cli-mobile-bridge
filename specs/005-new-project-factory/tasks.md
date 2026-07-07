# Tasks

## Phase 1: Manifest Contract

- [x] T001 Add project manifest dataclasses and validation service.
- [x] T002 Add default auth, RBAC, admin, notification, Codex, SDD, and release
      manifest sections.
- [x] T003 Add slug/path validation under `PROJECTS_ROOT` with no writes.
- [x] T004 Add tests for valid defaults, invalid names/slugs, existing folders,
      owner permissions, seed-admin env-only behavior, and SDD artifacts.

## Phase 2: Backend Draft And Job API

- [x] T005 Add API schemas for wizard options, draft request, dry-run response,
      generate response, and job status.
- [x] T006 Add project-factory routes.
- [x] T007 Add persisted draft/job state model and deterministic status payloads.
- [x] T008 Add route tests for draft, dry-run, validation errors, status, history,
      duplicate generation, and recovery.

## Phase 3: Mobile Chat Flow

- [x] T009 Add New project entry point to the existing Flutter app.
- [x] T010 Add chat-first New Project mode that asks for name, business type,
      goal, platforms, visual references, logo/icon, backend, style, preview,
      and confirmation through the normal conversation.
- [x] T011 Add API client calls, progress display, and Project Factory History.
- [x] T012 Add Flutter widget tests for the wizard, progress, and history.

## Phase 4: Research And Visual Direction

- [x] T013 Add business-type research prompt/output contracts.
- [x] T014 Add typical-app UX pattern prompt generation.
- [x] T015 Add uploaded-image handoff, project copy, and visual reference docs.
- [x] T016 Add design token/style guide placeholders and generator tests.

## Phase 5: Local Generator

- [x] T017 Write local project directory and `.codex/project.yaml`.
- [x] T018 Generate README, AGENTS, research/design/release/infra folders.
- [x] T019 Generate initial `specs/001-product-foundation` package.
- [x] T020 Initialize git safely and prove no secrets are committed.

## Phase 6: Flutter And Backend Templates

- [x] T021 Generate Flutter app with responsive web/mobile shell.
- [x] T022 Add auth, Google placeholder config, admin shell, RBAC guards, domain
      CRUD shell, and notifications shell. Feedback Bridge and updater remain
      generated follow-up tasks.
- [x] T023 Generate FastAPI backend with health, auth, RBAC, seed admin,
      notifications, domain resources, and tests.
- [x] T024 Run generated Flutter/backend validation through generated E2E script.

## Phase 7: GitHub And Release Readiness

- [ ] T025 Add optional GitHub repository creation.
- [x] T026 Generate AWS, App Store, and Play Store readiness docs.
- [x] T027 Mark Google/AWS/store credentials as pending without failing local
      project creation.

## Phase 8: End-To-End Validation

- [x] T028 Add project-factory doctor.
- [x] T029 Add generated-project E2E validation flow.
- [x] T030 Validate Workbench discovery, auth/RBAC, admin, domain CRUD,
      notifications, Flutter, backend, and no secrets.

## Phase 9: Acceptance Hardening

- [x] T031 Persist drafts/jobs and recover queued/running as interrupted.
- [x] T032 Add draft/job history APIs and mobile history panel.
- [x] T033 Document operational config, toolchain, and generated validation.
- [x] T034 Run acceptance validation.

## Phase 10: Post-Release Chat-Mode Hardening

- [x] T035 Add backend version/capability metadata for Project Factory.
- [x] T036 Harden backend PID handling and post-restart validation.
- [x] T037 Move primary New project UX from modal form to chat-mode kickoff.
- [x] T038 Update creation defaults to 20 generator and 20 reviewer runs.
