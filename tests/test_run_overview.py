import json
from datetime import datetime, timedelta, timezone

from backend.app.application.services.run_overview import overview, run_card
from backend.app.domain.entities.job import Job, JobStatus

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)


def _job(status, activities=(), **kw):
    return Job(id=kw.pop("id", "j"), session_id="s", message="Arreglá el login\nmás detalle",
               status=status, activities=list(activities),
               created_at=NOW - timedelta(seconds=90), updated_at=NOW, **kw)


def _card(job):
    return run_card(job, session_title="Login", workspace_name="app", now=NOW)


def test_working_run_describes_current_step_in_plain_words():
    card = _card(_job(JobStatus.RUNNING, [
        {"id": "1", "kind": "tool", "title": "Edit", "detail": json.dumps({"file_path": "/a/login.py"}), "status": "completed"},
        {"id": "2", "kind": "tool", "title": "Bash", "detail": json.dumps({"command": "pytest -q"}), "status": "running"},
        {"id": "u", "kind": "usage", "title": "x", "detail": "", "status": "completed"},
    ], provider_session_id="claude:abc", response="Voy probando"))
    assert card["state"] == "working" and card["engine"] == "claude"
    assert card["headline"] == "Ejecutando pytest -q"
    assert card["request"] == "Arreglá el login"
    assert card["files_changed"] == 1 and card["steps"] == 2
    assert card["elapsed_seconds"] == 90 and card["output"] == "Voy probando"


def test_waiting_interaction_wins_and_is_sorted_first():
    waiting = _card(_job(JobStatus.RUNNING, [{
        "id": "interaction-r1", "kind": "permission", "title": "Claude pide permiso para usar Bash",
        "detail": "$ rm x", "status": "waiting",
        "interaction": json.dumps({"request_id": "r1", "tool_name": "Bash", "input": {"command": "rm x"}}),
    }], id="w"))
    done = _card(_job(JobStatus.COMPLETED, response="## Listo\nTodo ok", id="d", completed_at=NOW))
    failed = _card(_job(JobStatus.FAILED, error="boom", id="f", completed_at=NOW))
    assert waiting["state"] == "needs_you" and waiting["pending"][0]["request_id"] == "r1"
    assert done["headline"] == "Listo" and done["output"] == ""
    result = overview([done, failed, waiting])
    assert [c["state"] for c in result["runs"]] == ["needs_you", "failed", "done"]
    assert result["counts"]["needs_you"] == 1 and result["counts"]["working"] == 0


def test_finished_run_never_offers_stale_requests():
    card = _card(_job(JobStatus.FAILED, [{
        "id": "interaction-r1", "kind": "question", "title": "¿Color?", "detail": "", "status": "waiting",
        "interaction": "{}",
    }], error="Claude did not return a final result.", completed_at=NOW))
    assert card["pending"] == [] and card["headline"] == "Claude did not return a final result."
