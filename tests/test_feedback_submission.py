from concurrent.futures import ThreadPoolExecutor
import pytest
from pydantic import ValidationError
from backend.app.api.schemas import FeedbackBatchStartRequest
from backend.app.application.services.feedback_submission import (
    FeedbackSubmissions,
    SubmissionConflict,
)


def test_contract_versions_sources_and_workspace():
    assert FeedbackBatchStartRequest(workspacePath="test").workspace_path == "test"
    for extra in (
        {"version": 999},
        {"kind": "invented"},
        {"invented": True},
        {"sourceApp": "a", "items": [{"id": "x", "sourceApp": "b", "comment": "test"}]},
    ):
        with pytest.raises(ValidationError):
            FeedbackBatchStartRequest(**extra)


def test_receipt_survives_restart_and_conflicts(tmp_path):
    path = tmp_path / "submissions.sqlite3"
    store = FeedbackSubmissions(path)
    payload = {"batch_id": "stable", "sourceApp": "fixture", "items": []}
    first = store.reserve(payload)
    assert first["state"] == "new"
    store.finish(first["id"], first["owner"], {"job_id": "one"})
    assert FeedbackSubmissions(path).reserve(payload)["receipt"] == {"job_id": "one"}
    with pytest.raises(SubmissionConflict):
        store.reserve({**payload, "sourceApp": "other"})


def test_concurrent_duplicate_and_interruption_do_not_relaunch(tmp_path):
    store = FeedbackSubmissions(tmp_path / "state.sqlite3")
    payload = {"sourceApp": "fixture", "items": [{"id": "same"}]}
    with ThreadPoolExecutor(max_workers=8) as pool:
        reservations = list(pool.map(lambda _: store.reserve(payload), range(12)))
    assert sum(r["state"] == "new" for r in reservations) == 1
    first = next(r for r in reservations if r["state"] == "new")
    store.finish(first["id"], first["owner"], None)
    assert store.reserve(payload)["state"] == "uncertain"
    assert store.status(first["id"])["receipt"] is None
