# Tasks

## Plan 1: Charter Contract And Data Model

- [x] T001 Define `project_management` manifest schema for `.codex/project.yaml`, including standard id, primary document, render artifact, latest release, modules, and validation policy.
- [x] T002 Define charter metadata schema for `docs/project-management/acta/current/metadata.yaml`, including title, client, author, status, draft version, delivered version, source hash, render hash, and timestamps.
- [x] T003 Define brand metadata schema for `brand.yaml`, including logo status, logo source, logo path, client export requirement, and notes.
- [x] T004 Define document state machine: `draft`, `internal_review`, `client_delivered`, `client_revised`, and `superseded`.
- [x] T005 Define versioning rules for `v0.x`, `v1.0`, `v1.x`, and `v2.0`, including which charter sections require minor or major delivered version changes.
- [x] T006 Define validation result payload with severity, code, field, message, next action, blocking flag, and affected file.
- [x] T007 Add traceability from Project Factory draft/contract fields to charter fields: project name, client, logo, project objective, product objective, benefits, scope, and pending definitions.

## Plan 2: Deterministic Project Factory Baseline

- [x] T008 Update Project Factory manifest planning so approved draft/contract data is available to deterministic init.
- [x] T009 Remove the generic deterministic init fallback that rebuilds generated projects with `business_type=project` and `primary_goal=Generated deterministic baseline` when approved draft data exists.
- [x] T010 Generate `docs/project-management/index.md`, `glossary.md`, `versioning.md`, and `context-routing.md` for every new project.
- [x] T011 Generate the `acta/current` source, metadata, brand metadata, render manifest, changelog, validation rules, and export rules.
- [x] T012 Generate dormant module folders for WBS, roles, risks, and alternatives with README files but without loading their full context into charter work.
- [x] T013 Generate an initial charter from the New Project contract with required sections and explicit pending definitions for unknown fields.
- [x] T014 Copy or reference logo/app icon assets from Asset Depot into `assets/brand/` and set brand metadata consistently.
- [x] T015 Update Project Factory generator tests to assert the documentation framework exists, contains no TODO/lorem ipsum placeholders in deliverable sections, and is committed in the generated baseline.

## Plan 3: Modular Context And Natural-Language Routing

- [x] T016 Write module-specific instructions for charter, WBS, roles, risks, and alternatives, each explaining when to read and when not to read the module.
- [x] T017 Add a charter glossary covering project objective, product objective, benefits, preliminary scope, pending definitions, revision history, draft, delivered version, and client export.
- [x] T018 Define natural-language intent categories for charter identity, executive summary, project objective, product objective, benefits, scope, pending definitions, versioning, render/export, WBS, roles, risks, and alternatives.
- [x] T019 Add prompt/context rules so agents can update charter fields when user intent implies charter impact, even if the user does not name the file.
- [x] T020 Add prompt/context rules that prevent agents from silently delivering or versioning a charter without explicit user intent.
- [x] T021 Add context routing rules so charter-only updates read only the index, charter README, current charter, metadata, and validation rules.
- [x] T022 Add tests for natural-language routing examples such as adding benefits, changing product objective, preparing a client version, and starting WBS without loading alternatives.

## Plan 4: Versioning, Changelog, Validation, And Release Snapshots

- [x] T023 Implement charter validation for required fields, valid status, revision history, logo decision, no placeholders, and source/render hash consistency.
- [x] T024 Implement brand/logo export gate: block client export when logo is required and pending.
- [x] T025 Implement draft edit behavior that updates current source and metadata without bumping latest delivered version.
- [x] T026 Implement release snapshot creation under `acta/releases/vX.Y/` with source, render, optional PDF, metadata, and source hash.
- [x] T027 Enforce immutable delivered releases by blocking overwrite of an existing version directory.
- [x] T028 Implement changelog requirement when prior delivered content exists and charter-impacting content changes.
- [x] T029 Define and implement minor/major version recommendations based on changed fields.
- [x] T030 Add tests for draft edits, first delivery, minor delivery, major delivery, immutable snapshots, stale render blocking, and changelog blocking.

## Plan 5: Rendering And Export Pipeline

- [x] T031 Choose the first-rendering path: Markdown source to sanitized HTML with print CSS as the canonical preview artifact.
- [x] T032 Add charter print stylesheet that matches the client-facing structure: cover, revision history, index, headings, sections, page width, margins, and logo placement.
- [x] T033 Implement deterministic render manifest containing source hash, renderer version, generated timestamp, output path, and validation state.
- [x] T034 Render the latest charter to `acta/current/render.html` during generation and on refresh.
- [x] T035 Add optional PDF export hook that can use Chromium/Pandoc later without changing Markdown as source of truth.
- [x] T036 Add export validation so PDF/client export is blocked when render output is stale or validation has blocking errors.
- [x] T037 Add tests for render refresh, source hash changes, stale render detection, sanitized output, and print stylesheet presence.

## Plan 6: Backend Document APIs And Workbench Indexing

- [x] T038 Add a backend service for safe project document discovery under a workspace root.
- [x] T039 Add `GET /project-documents` to list document modules and latest status for a workspace.
- [x] T040 Add `GET /project-documents/charter` to return charter metadata, source summary, render path, validation state, and latest release.
- [x] T041 Add `POST /project-documents/charter/validate` and `POST /project-documents/charter/render`.
- [x] T042 Add `POST /project-documents/charter/release` with idempotency and immutable-version checks.
- [x] T043 Add release listing/read endpoints for previous delivered charter versions.
- [x] T044 Expose Project Charter/Documents in Workbench discovery without treating it as a feature spec or loading full module context by default.

## Plan 7: Flutter/Workbench Viewer

- [x] T045 Add mobile API client models and methods for project document list, latest charter, validation, render refresh, release creation, and release list.
- [x] T046 Add a Workbench/SDD navigation entry for `Documents` or `Project Charter`.
- [x] T047 Build a latest-charter view that shows version, status, last updated, validation status, and rendered document.
- [x] T048 Render the PDF-like HTML preview inside Flutter using the selected safe viewer approach.
- [x] T049 Add a validation panel with blocking issues and next actions.
- [x] T050 Add an action to request a natural-language charter change in the current chat.
- [x] T051 Add an action to refresh render and, when valid, create a client-delivered version.
- [x] T052 Add a secondary previous-versions panel with version, date, status, and open action.

## Plan 8: Validation, Migration, And Documentation

- [x] T053 Add backend API tests for document discovery, validation, render, release, and path safety.
- [x] T054 Add Flutter widget tests for document navigation, latest preview, validation state, render refresh action, and previous version listing.
- [x] T055 Add Project Factory init baseline tests proving generated projects include charter docs and Workbench document discovery.
- [x] T056 Add migration/backfill guidance for existing generated projects that do not yet have `docs/project-management`.
- [x] T057 Document operator workflow: create project, review charter, request changes, render preview, deliver version, later expand WBS/roles/risks/alternatives.
- [x] T058 Run focused regression validation for Project Factory, deterministic init, Workbench SDD view, and mobile document UI.
