# Codex CLI Orchestration

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
