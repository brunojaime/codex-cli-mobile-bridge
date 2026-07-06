# Plan

## Phase 1: Spec Target Contract

Define the shared `spec_target` payload used by Workbench and Codex CLI Bridge.
The contract must support `none`, `new_spec`, and `existing_spec`, plus an
optional artifact target: `auto`, `spec`, `plan`, `tasks`, or `diagram`.

Target modules:

- `backend/app/api/schemas.py`
- `backend/app/application/services/sdd_spec_target_service.py`
- `tests/test_sdd_spec_target.py`

No file-writing behavior is allowed in this phase.

## Phase 2: SCM Metadata Model

Add `metadata.yaml` support for specs. The model must include title,
description, status, timestamps, generated/pinned field flags, task summary, and
last Codex run state.

Target modules:

- `backend/app/application/services/sdd_project_service.py`
- `backend/app/application/services/sdd_workbench_view_service.py`
- `packages/codex_bridge_workbench/lib/src/models/sdd_project.dart`
- `tests/test_sdd_spec_metadata.py`
- focused Workbench model/widget tests.

This phase is read-only. Missing metadata must use fallback values.

## Phase 3: Multimodal Intake Storage

Persist text, audio, images, cropped images, marked regions, multiple
screenshots, and image sequences under `specs/<id>/intake/`. Raw input must be
preserved before transcription, visual summarization, or spec generation.

Target modules:

- `backend/app/api/schemas.py`
- `backend/app/application/services/sdd_intake_service.py`
- `tests/fixtures/sdd_intake/`
- `tests/test_sdd_intake_service.py`

This phase adds dry-run planning and validation only. Writes are blocked until
size, format, path, and collision checks pass.

## Phase 4: Backend Spec Creation Boundary

Add a backend service and API boundary that can create a new spec package from a
normalized intake. The first implementation must be dry-run capable and must
avoid overwriting existing spec directories.

Target modules:

- `backend/app/api/routes.py`
- `backend/app/api/schemas.py`
- `backend/app/application/services/sdd_spec_creation_service.py`
- `tests/test_sdd_spec_creation_service.py`

The write flow must consume the dry-run plan as its write contract.

## Phase 5: Backend Existing Spec Edit Boundary

Add a backend service and API boundary that can target an existing spec artifact
for update. It must validate workspace, spec id, artifact path, and context
before invoking Codex.

Target modules:

- `backend/app/application/services/sdd_spec_edit_service.py`
- `backend/app/application/services/sdd_context_pack_service.py`
- `tests/test_sdd_spec_edit_service.py`

This phase prepares edit requests and dry-run validation. It does not execute
Codex CLI yet.

## Phase 6: Codex CLI Orchestration

Run Codex CLI in an isolated job sandbox copied from the target workspace for
create/edit actions. The service must build the correct context pack, pass
raw/normalized intake references, expose job states, capture results, and
report blocked/failed states. Generated changes must remain in the job sandbox
until an explicit review/apply step validates paths, conflicts, and protected
baseline rules.

Target modules:

- `backend/app/application/services/sdd_codex_job_service.py`
- `backend/app/application/services/message_service.py` if existing session/job
  infrastructure is reused.
- `backend/app/api/routes.py`
- `tests/test_sdd_codex_job_service.py`

Codex CLI execution must use argv command construction, validated cwd,
allowlisted env, timeout, cancellation, process log capture, and one active job
per target workspace. The process cwd must be the job sandbox, not the
destination repo root.

## Phase 7: Metadata Refresh

After every successful create/edit action, refresh title, description, status,
task summary, traceability, and `.sdd` indexes. Pinned title/description fields
must not be overwritten.

Target modules:

- `backend/app/application/services/sdd_metadata_refresh_service.py`
- `backend/app/application/services/sdd_index_service.py`
- `tests/test_sdd_metadata_refresh_service.py`

Refresh must be idempotent and expose stale/updated/skipped/proposed fields.

## Phase 8: Workbench UX For Specs

Expose a spec list with title, description, status, task progress, updated
timestamp, and last run state. Add new spec and edit spec flows with text,
audio, image, crop, marked region, and image sequence inputs.

Target modules:

- `packages/codex_bridge_workbench/lib/src/widgets/sdd_explorer_panel.dart`
- `packages/codex_bridge_workbench/lib/src/services/sdd_explorer_client.dart`
- `packages/codex_bridge_workbench/lib/src/models/sdd_project.dart`
- `packages/codex_bridge_workbench/test/codex_bridge_workbench_test.dart`

The UI consumes backend state and submitter boundaries; it must not write files
directly.

## Phase 9: Codex CLI Bridge Spec Targeting

Extend Bridge capture flows so screenshots, selected images, audio, comments,
and capture batches can target no spec, a new spec, or an existing spec. The
Bridge should send the same `spec_target` payload as Workbench.

Target modules:

- existing feedback/capture payload schemas in backend API.
- Flutter feedback/capture widgets in the current Bridge app.
- shared package metadata structures where feedback payloads are built.
- focused payload compatibility tests.

This phase reuses existing capture behavior and only adds target metadata and
spec picker UI.

## Phase 10: Status Streaming And Activity

Show background states in the app: received, processing-media, preparing-context,
queued, running-codex, applying-changes, refreshing-metadata, validating, ready,
failed, and blocked.

Retry is a new-job operation, not a mutation of a failed sandbox. A retry may
only be created from `failed`, `timed_out`, or `cancelled` jobs. The backend
copies the original validated request/context/prompt/base-manifest handoff into
a fresh `.codex-bridge/sdd-jobs/<retry-id>/sandbox`, rejects queued, running,
completed, applied, blocked, missing, stale, or concurrency-conflicting jobs,
and preserves the rule that generated output is never written to the target repo
until explicit reviewed apply.

Target modules:

- `backend/app/api/schemas.py`
- `backend/app/api/routes.py`
- `backend/app/application/services/sdd_codex_job_service.py`
- Workbench activity widgets.
- tests for state transitions and API response shapes.

## Phase 11: Validation And Tests

Add focused tests for contract parsing, path safety, dry-run creation, existing
spec edit targeting, metadata refresh, pinned fields, task summaries, context
pack use, Codex CLI job state output, and no broad spec fallback.

This phase consolidates doctor/readiness checks and end-to-end fixtures. It must
run strict doctor against generated fixture workspaces and prove no unintended
writes outside the destination repo.

## Phase 12: SAT Pilot And Reviewer Closeout

Pilot the flow on SAT without SAT-specific platform code. Run reviewer pass,
address findings, self-review, strict doctor, and SAT-focused validation before
marking the feature complete.

SAT writes, if any, must be explicit pilot actions and reported separately.

## Implementation Strategy

1. Keep the first slice schema/read-only where possible.
2. Add dry-run and validation before any write flow.
3. Add write flows only through explicit create/edit actions.
4. Wire Codex CLI orchestration only after target validation and context pack
   generation are tested.
5. Add media writes only after size, format, retention, and privacy rules are
   test-covered.
6. Add Codex CLI execution only after dry-run create/edit flows are safe.
7. Add UX surfaces after backend boundaries are machine-testable.
8. Pilot SAT only after generic Workbench behavior exists.

## Risks

- Spec creation could overwrite or fork an existing spec if slug/id generation
  is weak.
- Media intake could lose original user evidence if summarization replaces raw
  assets.
- Codex CLI could run in the wrong repo if target workspace validation is weak.
- Automatic description refresh could overwrite user wording unless pinned
  fields are respected.
- Bridge capture payloads and Workbench payloads could drift if they do not
  share the same `spec_target` contract.
- The user experience could expose too much internal SDD language instead of
  SCM/spec language.

## Mitigations

- Use deterministic id/slug generation with collision checks.
- Store raw intake before any generated summaries.
- Require target workspace validation and explicit target repo in every job.
- Track generated and pinned metadata flags separately.
- Use one shared backend contract for Workbench and Bridge captures.
- Keep UX copy focused on specs, functionality, changes, and tasks.
