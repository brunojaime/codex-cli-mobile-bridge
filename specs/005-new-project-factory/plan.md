# Plan

## Phase 1: Manifest Contract

Define and test the project manifest model before any file-writing generator is
added.

- Add a pure project manifest planning service.
- Validate project name, slug, platforms, backend, business type, and target
  path under `PROJECTS_ROOT`.
- Include mandatory auth, RBAC, admin, notifications, Codex, SDD, and release
  defaults.
- Include Codex CLI creation workflow defaults of 20 generator runs and 20
  reviewer runs.
- Keep seed admin values as environment variable names only.
- Prove validation is deterministic and write-free.

## Phase 2: Backend Draft And Job API

- Add project-factory request/response schemas.
- Add draft creation, listing/detail, dry-run, reference assets, generation,
  job listing/detail, and doctor endpoints.
- Add persistent draft/job state with interrupted recovery and failure
  reporting.
- Block duplicate generation for the same draft.

## Phase 3: Mobile Chat Flow

- Add the New project action to the current app.
- Implement the primary chat-mode flow: create a normal chat titled "New
  project", configure Project Factory generator/reviewer agents, and send the
  kickoff prompt that asks for missing project context.
- Support optional visual references through the existing chat attachment tray.
- Show dry-run summary and generation progress.
- Open the generated workspace after success.
- Add Project Factory History so persisted jobs can be inspected, watched again,
  or opened after app restart.

## Phase 4: Research And Visual Direction

- Generate placeholder business research documents that Codex CLI batches fill.
- Generate typical-app pattern docs by business type through Codex prompts.
- Copy uploaded images into generated repos with traceable metadata.
- Generate design token/style guide placeholders for subsequent Codex runs.

## Phase 5: Local Generator

- Create the sibling project directory under `PROJECTS_ROOT`.
- Write `.codex/project.yaml`.
- Create README, AGENTS, docs, design, release, and infra folders.
- Create the initial SDD spec package.
- Initialize git without pushing secrets.

## Phase 6: Flutter And Backend Templates

- Generate the Flutter iOS/Android/Web app with auth, admin domain management,
  RBAC-gated admin navigation, notifications, API config, and generated tests.
- Generate the FastAPI backend with health, auth, RBAC, seed admin, domain
  resources, notification resources, and tests.
- Leave Feedback Bridge and app updater as generated SDD follow-up tasks until
  those packages are wired into the template.

## Phase 7: GitHub And Release Readiness

- Create an initial local git commit for every generated project.
- In remote publication mode, execute the generated GitHub publish script so the
  repository is actually created/verified and pushed, not merely documented.
- Generate and execute an Android release script that creates the productive tag,
  pushes it, waits for the GitHub Actions release workflow, and verifies APK
  assets.
- Register the published APK in the Bridge installable-app catalog so Codex
  Mobile can show it under Apps.
- Leave an explicit `blocked` publish state when GitHub, release, Bridge URL, or
  registration-token configuration is missing. Do not report `ready` for local
  foundations that have not been remotely published.
- Generate AWS, App Store, and Play Store readiness files.
- Keep Google, AWS, Apple, and Play credentials as explicit pending items.

## Phase 8: End-To-End Validation

- Add a doctor endpoint with Projects root and toolchain checks.
- Add generated-project validation script.
- Add regression coverage for the SAT Showroom gap: remote publication phases
  must run before `ready`, and missing GitHub/release/Bridge config must end as
  `blocked`.
- Validate Workbench discovery, Flutter, backend, auth/RBAC, admin, notifications,
  and no-secret output.

## Phase 9: Acceptance Hardening

- Persist drafts/jobs and recover interrupted jobs after restart.
- Add history APIs and mobile history panel.
- Document operational configuration and validation.
- Run backend, Flutter, and generated-project E2E validation.
