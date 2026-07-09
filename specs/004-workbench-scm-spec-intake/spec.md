---
id: 004-workbench-scm-spec-intake
title: Workbench SCM Spec Intake
status: draft
type: feature
domains:
  - workbench
  - scm
  - codex-actions
  - multimodal-intake
---

# Workbench SCM Spec Intake

## Intent

Workbench must let a user create and edit specs from the repo UX or Codex CLI
Bridge captures. The user may provide text, audio, one image, cropped/marked
image regions, multiple screenshots, or an image sequence with audio. The
system must preserve the raw intake, let the user choose whether it targets no
spec, a new spec, or an existing spec, and then run Codex CLI in the target repo
with the correct context.

The product experience should expose specs as visible SCM units while keeping
the underlying SDD/context-pack machinery internal.

## Scope

This spec covers:

- A shared `spec_target` model used by Workbench and Codex CLI Bridge.
- Multimodal intake for text, audio, images, crops, marked regions, and image
  sequences.
- New spec creation from Workbench.
- Existing spec editing from Workbench.
- Spec targeting from Codex CLI Bridge captures.
- Automatic title and description generation.
- Automatic title/description refresh after spec-relevant changes.
- Task progress summaries per spec.
- Codex CLI orchestration in the target repo.
- Status updates visible in the app while Codex CLI runs.
- Traceability from raw intake to spec, plan, tasks, diagrams, and validation.

## Non-Goals

- Do not replace the existing feedback capture flow.
- Do not require video encoding in the first implementation; image sequence plus
  audio is the initial walkthrough format.
- Do not implement release publishing or APK workflows.
- Do not make SAT-specific behavior part of the generic Workbench flow.
- Do not run Codex CLI without an explicit target workspace.
- Do not let doctor mutate files; writes must happen through explicit
  create/edit/backfill actions.

## User-Facing Model

The user can see and choose specs. The user does not need to know context packs,
indexes, sidecars, or traceability internals.

Every captured request has exactly one target:

```yaml
spec_target:
  mode: none | new_spec | existing_spec
  spec_id: null
  artifact: auto | spec | plan | tasks | diagram
```

`none` keeps the capture as ordinary feedback or a comment. `new_spec` creates a
new feature/spec record. `existing_spec` updates a chosen spec or one of its
artifacts.

### Spec Target Contract

`spec_target.mode: none` means the payload must not create or edit spec files.
The backend may store the capture as ordinary feedback and may offer a later
"promote to spec" action, but the first save is non-SCM. Required inputs are the
workspace target and at least one intake item. `spec_id` must be absent or null,
and `artifact` must be `auto` or absent. Any non-null `spec_id` with `none` is
invalid.

`spec_target.mode: new_spec` means the payload creates a new spec package after
dry-run validation. Required inputs are the target workspace, at least one
intake item, and either a user-provided title seed or enough text/transcript for
title generation. `spec_id` may be absent; if present, it is treated as a
requested slug and must pass slug validation and collision checks. `artifact`
must be `auto` or absent. Selecting `plan`, `tasks`, or `diagram` for a new spec
is invalid because those artifacts are generated as part of the package.

`spec_target.mode: existing_spec` means the payload edits an existing spec
package. Required inputs are target workspace, `spec_id`, at least one intake
item, and an artifact target. `artifact: auto` lets the backend/Codex choose
which artifacts to update from the intake. `artifact: spec`, `plan`, `tasks`, or
`diagram` constrains the update to that artifact family unless the context pack
explicitly returns related required files. The selected `spec_id` must resolve
to `specs/<spec_id>/` inside the target workspace after path normalization.

Invalid combinations are hard validation failures before writes or Codex CLI
execution:

- `none` with non-null `spec_id`.
- `new_spec` with `artifact` other than `auto`.
- `existing_spec` without `spec_id`.
- any `spec_id` containing `/`, `\`, `.`, `..`, an absolute path, URL syntax, or
  characters outside `[a-z0-9-]`.
- selected artifacts outside `spec.md`, `plan.md`, `tasks.md`, `traceability.yaml`,
  or `diagrams/*.mmd` under the selected spec root.
- target workspace outside the configured projects root or workspace aliases.

If Codex CLI Bridge and Workbench both send a target, the backend treats the
explicit payload target as authoritative only when both targets are identical.
Conflicting targets return `409 target_conflict` with both targets in the
machine-readable error and no files written. A later UX may ask the user to pick
one target and resubmit.

## Feature Artifact Shape

New specs created by this flow should use:

```text
specs/<id-slug>/
  intake/
    intake.yaml
    original-request.md
    transcript.md
    visual-summary.md
    media/
      001.png
      002.png
      narration.m4a
  metadata.yaml
  spec.md
  plan.md
  tasks.md
  traceability.yaml
  diagrams/
```

`metadata.yaml` is the SCM summary used by the UX:

```yaml
id: CHG-2026-07-06-001
slug: favoritos-productos
title: Favoritos de productos
description: Permite guardar productos favoritos y consultarlos luego.
status: draft
created_at: 2026-07-06T00:00:00Z
updated_at: 2026-07-06T00:00:00Z
generated:
  title: true
  description: true
  user_pinned_title: false
  user_pinned_description: false
tasks:
  total: 0
  completed: 0
  pending: 0
```

## Automatic Title And Description

For new specs, Codex generates title and description from the normalized intake.
For existing specs, Codex refreshes title and description only when the relevant
content changes and the user has not pinned those fields.

If `user_pinned_title` or `user_pinned_description` is true, Codex may propose a
replacement but must not overwrite the pinned field without user confirmation.

Metadata refresh is triggered after these events:

- a new spec package is created.
- `spec.md`, `plan.md`, `tasks.md`, `traceability.yaml`, or `diagrams/*.mmd`
  changes through a Workbench/Codex action.
- intake transcript or visual summary is regenerated.

Refresh is idempotent: running it twice on unchanged inputs must produce the
same `metadata.yaml` except for explicitly updated `last_refreshed_at` or run
status fields. Staleness is detected with source file digests recorded in
`metadata.yaml`. When source digests differ from the stored metadata digest, the
UX shows metadata as stale until refresh completes.

Conflict rules:

- If a user edits title/description in the UI, the field becomes pinned.
- If Codex proposes a different value for a pinned field, the proposal is stored
  under `generated.proposed_title` or `generated.proposed_description` and the
  visible value is not overwritten.
- If metadata refresh fails, the previous metadata remains and the job reports
  `metadata_refresh_failed` with next actions.

Observable refresh output must include: refreshed fields, skipped pinned fields,
task counts, stale source paths, old digest, new digest, and next actions.

## Multimodal Intake

Raw user input must be preserved before any summarization. The normalized
request must reference the raw assets instead of replacing them.

Supported intake types:

- text.
- audio plus transcript.
- image.
- cropped image.
- marked image region.
- multiple screenshots.
- image sequence plus audio narration.

Image sequence metadata records the order and optional timestamps:

```yaml
timeline:
  - at_ms: 0
    image: media/frame-001.png
  - at_ms: 4200
    image: media/frame-002.png
audio: media/narration.m4a
```

### Media Policy

Supported formats for the first implementation:

- text: UTF-8 plain text or markdown, maximum 64 KiB per item.
- audio: `m4a`, `mp3`, `wav`, or `webm`, maximum 25 MiB per file and 10 minutes
  duration.
- images: `png`, `jpg`, `jpeg`, or `webp`, maximum 10 MiB per image.
- crops and marked regions: stored as derived images plus metadata pointing to
  the original image and crop rectangle.
- multi-capture batch: maximum 20 images.
- image+audio sequence: maximum 60 timeline frames and one audio track.

All media paths are stored under:

```text
specs/<spec-id>/intake/media/
```

Before a new spec id exists, temporary intake must be stored under a backend
staging area scoped by job id, then moved into the spec root only after dry-run
creation succeeds. Staged media older than 24 hours without a spec association
is eligible for cleanup. Media attached to a spec is retained with that spec
unless the user explicitly removes it through a future cleanup action.

Privacy boundaries:

- Do not copy media outside the target workspace except transient backend upload
  buffering.
- Do not include binary blobs inline in generated specs.
- Generated specs may reference media paths and summaries, but raw media remains
  in `intake/media/`.
- Logs must contain media paths, sizes, and hashes, not binary content.
- Transcripts and visual summaries are project artifacts and should be treated as
  repo data.

Every intake item records: original filename when available, stored path, media
kind, MIME type, byte size, sha256 digest, capture timestamp when available,
source app, and optional crop/region metadata.

## Codex CLI Orchestration

Every create/edit action runs Codex CLI in the target repo. The backend builds a
context pack, writes a job record, invokes Codex CLI, streams status, and then
refreshes spec metadata and indexes.

Required states:

- received
- processing-media
- preparing-context
- queued
- running-codex
- applying-changes
- refreshing-metadata
- validating
- ready
- failed
- blocked

### Codex CLI Execution Safety

The backend must validate the target workspace using the same project root and
workspace alias rules as existing SDD project APIs. The final `cwd` passed to
Codex CLI must be the resolved target workspace, not a user-provided string.

Command construction must use an argument vector, never shell string
interpolation. User text, transcripts, filenames, and paths must be passed
through prompt files or structured JSON files inside the job directory, not
spliced into a shell command.

The execution environment must be explicit:

- `cwd`: resolved target workspace.
- `env`: allowlisted variables only, including required Codex/Bridge settings.
- `PATH`: inherited only if already trusted by the backend process.
- job files: stored under a backend-managed job directory.

Cancellation and timeouts:

- Every job has a timeout. The first implementation default is 30 minutes.
- Users can cancel queued or running jobs.
- Cancellation sends a graceful termination first, then a forced kill after a
  short grace period.
- A cancelled job reports `cancelled` and must not be marked as failed or ready.

Concurrency:

- Only one write job may run per target workspace at a time.
- Read-only context preview jobs may run concurrently.
- A second write submission for the same workspace is queued or rejected with
  `workspace_busy`, depending on the API option.

Logs:

- stdout, stderr, exit code, start time, end time, command argv redacted where
  needed, context pack id, and touched file summary are captured.
- Logs must not contain raw binary media.
- Failed jobs preserve raw intake and job logs for review.

Failure mapping:

- validation error before process start -> `blocked`.
- process timeout -> `failed` with reason `timeout`.
- user cancellation -> `cancelled`.
- non-zero Codex CLI exit -> `failed` with reason `codex_exit`.
- metadata refresh failure after file changes -> `failed` with reason
  `postprocess_failed` and next actions.
- doctor/index failure after file changes -> `failed` with reason
  `validation_failed` and next actions.

## Functional Requirements

- FR-001: Workbench SHALL expose a user-facing way to create a new spec from
  text, audio, images, crops, marked regions, or image sequences.
- FR-002: Workbench SHALL expose a user-facing way to edit a selected existing
  spec using the same intake types.
- FR-003: Codex CLI Bridge SHALL let captured feedback choose no spec, new spec,
  or existing spec as the target.
- FR-004: The backend SHALL persist raw intake assets and normalized request
  summaries before running Codex.
- FR-005: The backend SHALL run Codex CLI in the selected target repo for every
  spec create/edit action.
- FR-006: The backend SHALL provide context-pack input to Codex CLI and prevent
  broad all-spec reads.
- FR-007: The system SHALL generate a title and short description for new specs.
- FR-008: The system SHALL refresh title, description, task summary, and status
  after spec-relevant changes unless the user has pinned fields.
- FR-009: The UX SHALL show spec title, description, status, task progress,
  updated timestamp, and last run state.
- FR-010: The UX SHALL show Codex run states while background work executes.
- FR-011: The system SHALL update traceability and `.sdd` indexes after create
  or edit actions.
- FR-012: The system SHALL keep ordinary feedback possible when `spec_target`
  mode is `none`.
- FR-013: The implementation SHALL preserve read-only doctor behavior.
- FR-014: The implementation SHALL include reviewer checkpoints before
  implementation phases proceed.

## Acceptance Criteria

- AC-001: Creating a new spec from text-only Workbench input validates
  `spec_target.mode: new_spec`, creates exactly one new `specs/<id>/` directory,
  writes no files outside that directory and `.sdd/`, and returns a job payload
  with final state `ready`.
- AC-002: Creating a new spec from audio preserves the original audio file,
  creates `intake/transcript.md`, records audio size/digest/duration metadata,
  and fails before Codex execution when the audio format, size, or duration
  limit is exceeded.
- AC-003: Creating or editing from images preserves each original image under
  `intake/media/`, records crop/region metadata when provided, rejects invalid
  formats or over-limit files, and references images by relative paths in
  generated specs.
- AC-004: Image+audio walkthrough intake accepts ordered frames plus one audio
  track, rejects more than 60 frames, preserves timeline order, and does not
  require video encoding.
- AC-005: Codex CLI Bridge captures can submit `spec_target.mode` values `none`,
  `new_spec`, and `existing_spec`; invalid target combinations return a
  machine-readable validation error and no files are written.
- AC-006: Existing spec selection lists every readable spec with title,
  description, status, completed task count, pending task count, total task
  count, and updated timestamp.
- AC-007: New spec creation produces `metadata.yaml`, `spec.md`, `plan.md`,
  `tasks.md`, `traceability.yaml`, `intake/`, optional diagrams, and fresh
  `.sdd` indexes.
- AC-008: Existing spec edit rejects invalid `spec_id`, traversal, absolute
  paths, missing selected spec roots, and unsupported artifact targets before
  Codex CLI starts.
- AC-009: Existing spec edit writes only under the selected spec root and `.sdd/`
  unless the reviewed context pack explicitly authorizes related files.
- AC-010: Title and description generation is deterministic for the same
  normalized intake and records generated/pinned metadata flags.
- AC-011: Metadata refresh is idempotent on unchanged inputs, detects stale
  metadata from source digests, respects pinned fields, and exposes refreshed,
  skipped, and proposed field output.
- AC-012: Task progress shows completed, pending, and total task counts per spec
  and matches checkbox parsing from `tasks.md`.
- AC-013: Codex CLI execution uses validated workspace cwd, argv command
  construction, allowlisted env, timeout, cancellation, log capture, and
  per-workspace write concurrency control.
- AC-014: Failed, blocked, timed out, and cancelled jobs preserve raw intake,
  expose next actions, and do not report partial silent success.
- AC-015: Doctor strict readiness remains pass after generated specs are
  validated, traceability is updated, and indexes are refreshed.
- AC-016: SAT can pilot new spec creation, existing spec edit, and Bridge target
  selection without SAT-specific platform code.

## Open Questions

- Should `metadata.yaml` use `CHG-*` ids, `SPEC-*` ids, or the existing
  `specs/<number>-slug` convention as the primary user-facing identifier?
- Should audio transcription run in the backend before Codex CLI or be delegated
  to the Codex CLI prompt with attached media paths?
- Should pinned title/description be editable only from metadata UI or also from
  the rendered spec header?
- Should ordinary feedback later be promotable to a spec after it was initially
  saved as `spec_target.mode: none`?
