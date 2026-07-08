# Status Streaming And Activity

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
