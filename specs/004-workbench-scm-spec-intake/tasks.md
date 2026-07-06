# Tasks

## Phase 1: Spec Target Contract

- [x] T001 Add `SpecTargetRequest`/response schemas in
      `backend/app/api/schemas.py` for `none`, `new_spec`, and `existing_spec`.
- [x] T002 Add artifact target enum support for `auto`, `spec`, `plan`,
      `tasks`, and `diagram` in the same schema boundary.
- [x] T003 Add `backend/app/application/services/sdd_spec_target_service.py`
      with pure validation and normalization only.
- [x] T004 Add `tests/test_sdd_spec_target.py` covering valid targets, invalid
      combinations, Bridge/Workbench target conflicts, invalid spec IDs, path
      traversal, absolute paths, and unsupported artifact targets.

## Phase 2: SCM Metadata Model

- [x] T005 Add metadata dataclasses/schema parsing for `metadata.yaml` in
      `backend/app/application/services/sdd_project_service.py`.
- [x] T006 Extend `SddWorkbenchViewService` feature spec output with
      description, timestamps, generated/pinned flags, task summary, and last
      run state.
- [x] T007 Add metadata fallback behavior: title from heading, description from
      indexed spec summary, task counts from checkbox parsing in `tasks.md`.
- [x] T008 Add `tests/test_sdd_spec_metadata.py` for valid metadata, missing
      metadata fallback, malformed metadata warnings, stale metadata flags, and
      task summary parsing.

## Phase 3: Multimodal Intake Storage

- [x] T009 Define `SddIntakeRequest`/`SddIntakeItem` schemas in
      `backend/app/api/schemas.py` for text, audio, image, crop, marked region,
      screenshot batch, and image sequence inputs.
- [x] T010 Add `backend/app/application/services/sdd_intake_service.py` with
      dry-run storage planning under backend staging and
      `specs/<id>/intake/media/`.
- [x] T011 Implement media policy validation in `SddIntakeService`: supported
      formats, size limits, duration limits, image count limits, timeline order,
      sha256 metadata, and privacy-safe log metadata.
- [x] T012 Add dry-run output for intake writes: would_create, existing,
      blocked, rejected_media, and next_actions.
- [x] T013 Add `tests/fixtures/sdd_intake/` and `tests/test_sdd_intake_service.py`
      covering safe storage, no overwrite, path traversal blocking, media limit
      violations, unsupported formats, crop metadata, marked region metadata,
      failed transcription/vision placeholders, and image sequence ordering.
- [x] T068 Add safe media persistence in
      `backend/app/application/services/sdd_intake_service.py` and tests for
      text/audio/image/crop/region/batch/sequence payload refs, sha256
      verification, no overwrite, cleanup on failure, and job handoff
      references.

## Phase 4: Backend Spec Creation Boundary

- [x] T014 Add `backend/app/application/services/sdd_spec_creation_service.py`
      with new spec dry-run planning from normalized intake.
- [x] T015 Add deterministic id/slug generation with collision handling and
      tests for duplicate requested slugs.
- [x] T016 Add API endpoint schemas/routes for new spec dry-run in
      `backend/app/api/schemas.py` and `backend/app/api/routes.py`; apply stays
      blocked until T017.
- [x] T017 Add explicit apply/write flow that consumes the dry-run plan and
      writes only inside the new spec root plus `.sdd/`.
- [x] T018 Add `tests/test_sdd_spec_creation_service.py` for text-only new spec
      creation, dry-run before write, blocked collisions, no unintended writes,
      missing required intake, and strict doctor after creation.

## Phase 5: Backend Existing Spec Edit Boundary

- [x] T019 Add `backend/app/application/services/sdd_spec_edit_service.py` with
      dry-run validation for existing spec edit requests.
- [x] T020 Validate selected spec id, spec root, selected artifact, and context
      pack eligibility before Codex execution.
- [x] T021 Add API endpoint schemas/routes for existing spec edit dry-run and
      apply preparation in `backend/app/api/schemas.py` and
      `backend/app/api/routes.py`.
- [x] T022 Add `tests/test_sdd_spec_edit_service.py` for invalid spec id,
      missing spec root, invalid artifact, path traversal, unsupported artifact,
      safe selected artifact targeting, and no files written on failed
      validation.

## Phase 6: Codex CLI Orchestration

- [x] T023 Add `backend/app/application/services/sdd_codex_job_service.py` with
      job model, job directory, target workspace, context pack id, and state
      machine.
- [x] T024 Implement validated Codex CLI process launch using argv command
      construction, resolved cwd, allowlisted env, prompt/context files, and no
      shell interpolation.
- [x] T025 Build context packs for `new_spec` and `existing_spec` jobs through
      `SddContextPackService` without duplicating routing logic.
- [x] T026 Pass intake references and normalized request to Codex CLI through
      structured files in the job directory.
- [x] T027 Capture stdout, stderr, exit code, timestamps, timeout, cancellation,
      touched file summary, and redacted argv in machine-readable job output.
- [x] T028 Add `tests/test_sdd_codex_job_service.py` covering target workspace
      validation, command injection prevention, cwd/env handling, timeout,
      cancellation, Codex CLI non-zero exit, concurrent submissions for one
      workspace, context pack use, and no broad all-spec fallback.
- [x] T069 Isolate Codex CLI execution in a per-job sandbox under
      `.codex-bridge/sdd-jobs/<job-id>/sandbox`, with handoff files and copied
      context artifacts, so Codex cannot modify target spec files directly by
      normal cwd-based writes.
- [x] T070 Add Codex generated-output review/apply behavior in
      `SddCodexJobService`: changed file detection, patch references, blocked
      path/protected-baseline/conflict reporting, explicit apply, metadata/index
      refresh, and no-partial-write rollback tests.

## Phase 7: Metadata Refresh

- [x] T029 Add `backend/app/application/services/sdd_metadata_refresh_service.py`
      with deterministic title generation for new specs.
- [x] T030 Add deterministic short description generation and proposed
      replacements for pinned descriptions.
- [x] T031 Add source digest tracking and stale metadata detection for spec,
      plan, tasks, traceability, diagrams, transcript, and visual summary.
- [x] T032 Respect `user_pinned_title` and `user_pinned_description`; never
      overwrite pinned fields without explicit confirmation.
- [x] T033 Recompute completed, pending, and total task summary from checkbox
      tasks.
- [x] T034 Refresh traceability and `.sdd` indexes after successful create/edit
      actions through existing index/backfill boundaries.
- [x] T035 Add `tests/test_sdd_metadata_refresh_service.py` for title/description
      refresh, pinned field conflict output, stale detection, idempotency,
      task summaries, traceability refresh, fresh indexes, and failed refresh
      next actions.

## Phase 8: Workbench UX For Specs

- [x] T036 Extend Workbench models in
      `packages/codex_bridge_workbench/lib/src/models/sdd_project.dart` with
      description, timestamps, task summary, last run state, and metadata stale
      state.
- [x] T037 Add spec list cards/table in
      `packages/codex_bridge_workbench/lib/src/widgets/sdd_explorer_panel.dart`
      with title, description, status, task progress, updated timestamp, and
      last run state.
- [x] T038 Add "New spec" Workbench flow with text input wired to the backend
      dry-run endpoint before apply.
- [x] T039 Add audio input affordance for new/edit spec intake, preserving the
      current capture/audio patterns.
- [x] T040 Add image input and native marked-region affordances reusing existing
      screenshot/bounds behavior. Pixel crop artifact generation is covered by
      T079.
- [x] T041 Add image sequence input affordance for walkthrough-style requests
      through the structured host-injected attachment boundary.
- [x] T042 Add existing spec edit flow with spec picker and artifact target
      selection.
- [x] T043 Extend `packages/codex_bridge_workbench/test/codex_bridge_workbench_test.dart`
      for spec list metadata, new spec dry-run/apply states, edit target
      selection, task progress, media inputs, blocked states, and failed states.
- [x] T071 Add text-first Workbench job controls for queued sandbox jobs:
      run, status display, generated-output review display, explicit reviewed
      apply, blocked/error rendering, and disabled audio/image controls until
      media upload is implemented end-to-end.
- [x] T072 Add first real Workbench image upload slice: backend staging
      endpoint, Workbench client multipart upload, optional host-provided image
      picker, staged attachment display/removal, and dry-run/apply handoff via
      validated intake items. Audio, crop, marked-region, batch, and sequence
      capture remain pending.
- [x] T073 Add staged media lifecycle management before broader capture modes:
      backend delete and retention cleanup boundaries, explicit
      staged/consumed/deleted/cleanup-eligible lifecycle metadata, consumed
      media delete blocking, Workbench remove wired to backend delete, and audio
      upload/staging through the same safe pipeline with duration/size/type
      validation. Native audio capture, crop, marked-region, batch, and
      sequence UX remain pending.
- [x] T074 Add structured media-derived intake support before Bridge capture:
      validate staged parent/child references for crop, marked region,
      screenshot batch, and image+audio sequence items; reject missing/deleted
      refs, invalid bounds, duplicate refs, and invalid ordering; persist
      structured metadata through intake storage/job handoff; expose
      host-injected structured attachments in Workbench without native
      drawing/crop UI.
- [x] T079 Add true pixel-crop generation in Workbench so a selected rectangle
      produces a separate cropped image artifact through the staged-media path,
      with backend/client tests proving the crop file is persisted end-to-end.

## Phase 9: Codex CLI Bridge Spec Targeting

- [x] T044 Extend existing feedback/capture backend payload schemas with
      `spec_target` while preserving backward compatibility.
- [x] T045 Add Bridge capture UI selector for no spec, new spec, and existing
      spec.
- [x] T046 Add Bridge spec picker using existing `/sdd/project` spec data.
- [x] T047 Route Bridge capture batches to the shared intake backend boundary
      instead of adding a Bridge-only creation path.
- [x] T048 Add backend and Flutter tests for capture payload compatibility,
      no-spec feedback preservation, new-spec targeting, existing-spec
      targeting, Bridge/Workbench target conflict, and missing submitter states.
- [x] T075 Add first backend Bridge-to-SDD capture adapter and API boundary:
      convert queued Bridge comments, screenshots, optional audio, selection
      bounds, and multiple captures into validated SDD intake items; support
      `none`, `new_spec`, and `existing_spec` targets through the shared
      target validator and safe spec-intake services.
- [x] T076 Add backend-focused Bridge capture tests for no-spec preservation,
      screenshot bounds propagation, deterministic multi-capture ordering,
      screenshot+audio sequence references, new-spec dry-run/apply, existing
      spec Codex job enqueue, invalid targets, and API dry-run from the
      feedback queue. Flutter/Bridge selector and compatibility tests are
      covered by T048 and T077.
- [x] T077 Add Flutter Bridge capture UI tests for SDD target selector states,
      `none` preserving ordinary batch submission, `new_spec` preview/apply,
      `existing_spec` picker/job enqueue, backend blocked-state display, and
      no real Codex execution. Native crop/drawing UI remains pending.
- [x] T078 Add native Bridge capture marked-region editor in the feedback queue:
      draw, edit, validate, and remove rectangular screenshot regions; submit
      them through existing `selectionBounds`/`imageCapture.annotations` into
      `new_spec` and `existing_spec` SDD intake flows. Pixel crop generation
      remains pending because no cropped image artifact is produced end-to-end.

## Phase 10: Status Streaming And Activity

- [x] T049 Add API response schemas for job states: received, processing-media,
      preparing-context, queued, running-codex, applying-changes,
      refreshing-metadata, validating, ready, failed, blocked, and cancelled.
- [x] T050 Expose job state read endpoint and optional polling/streaming route
      in `backend/app/api/routes.py`.
- [x] T051 Show job activity in Workbench and Bridge capture flows without
      blocking ordinary feedback submission.
- [x] T052 Add retry/cancel behavior for queued/running/failed jobs where safe.
- [x] T053 Add tests for state transitions, cancellation, timeout, retry,
      concurrent submissions, and user-visible activity output.

## Phase 11: Validation And Tests

- [x] T054 Extend doctor/readiness checks for spec metadata, stale metadata,
      intake artifacts, job failures, and media policy warnings.
- [x] T055 Add end-to-end tests for new spec from text through API/service
      boundaries.
- [x] T056 Add end-to-end tests for new spec from audio transcript fixture and
      failed transcription fixture.
- [x] T057 Add end-to-end tests for image, crop, marked region, and image
      sequence fixtures.
- [x] T058 Add end-to-end tests for existing spec edits across `spec`, `plan`,
      `tasks`, and `diagram` artifact targets.
- [x] T059 Add regression tests for Workbench API/UI surfaces, strict doctor
      readiness after generated specs, no unintended writes outside the target
      repo, and context-pack no-broad-read behavior.

## Phase 12: SAT Pilot And Reviewer Closeout

- [x] T060 Pilot new spec creation on SAT using generic Workbench behavior.
- [x] T061 Pilot existing spec edit on SAT using generic Workbench behavior.
- [x] T062 Verify SAT capture flows can choose no spec, new spec, and existing
      spec targets without SAT-specific platform code.
- [x] T063 Run SAT strict doctor and focused Workbench tests.
- [x] T064 Request reviewer pass on this spec, plan, tasks, traceability, and
      diagrams before implementation begins.
- [x] T065 Address reviewer findings in the SDD documents.
- [x] T066 Perform one additional self-review pass after reviewer feedback.
- [x] T067 Record that implementation remains blocked until the first
      implementation iteration is explicitly started.
