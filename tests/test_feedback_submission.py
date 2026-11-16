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


def review_evidence():
    return {"environment": "dev", "reason": "Verified deterministic workspace denial before any job", "session_id": "empty-fixture-session", "session_messages": 0, "session_runs": 0, "no_active_operations": True}


def test_reviewed_retry_preserves_identity_digest_and_single_admission(tmp_path):
    import sqlite3
    path = tmp_path / "state.sqlite3"
    store = FeedbackSubmissions(path)
    payload = {"batch_id": "stable", "sourceApp": "fixture", "items": [{"id": "same"}]}
    first = store.reserve(payload)
    store.finish(first["id"], first["owner"], None)
    review = store.authorize_reviewed_retry(first["id"], review_evidence())
    assert review["state"] == "retryable"
    with pytest.raises(SubmissionConflict):
        store.reserve({**payload, "sourceApp": "different"})
    with ThreadPoolExecutor(max_workers=8) as pool:
        reservations = list(pool.map(lambda _: FeedbackSubmissions(path).reserve(payload), range(12)))
    assert sum(r["state"] == "new" for r in reservations) == 1
    retry = next(r for r in reservations if r["state"] == "new")
    assert retry["id"] == first["id"] and retry["owner"] != first["owner"]
    with pytest.raises(SubmissionConflict):
        store.finish(first["id"], first["owner"], {"job_id": "stale"})
    store.finish(retry["id"], retry["owner"], {"job_id": "exactly-one"})
    assert store.reserve(payload)["receipt"] == {"job_id": "exactly-one"}
    with sqlite3.connect(path) as db:
        rows = db.execute("SELECT previous_state,next_state,digest FROM submission_reviews").fetchall()
    assert rows == [("uncertain", "retryable", store.identity(payload)[1])]
    with pytest.raises(SubmissionConflict):
        store.authorize_reviewed_retry(first["id"], review_evidence())


def test_review_does_not_release_inflight_or_unproven_submissions(tmp_path):
    store = FeedbackSubmissions(tmp_path / "state.sqlite3")
    first = store.reserve({"batch_id": "stable", "items": []})
    with pytest.raises(SubmissionConflict):
        store.authorize_reviewed_retry(first["id"], review_evidence())
    store.finish(first["id"], first["owner"], None)
    for invalid in [{}, {**review_evidence(), "environment": "prod"}, {**review_evidence(), "session_messages": 1}, {**review_evidence(), "session_runs": 1}, {**review_evidence(), "no_active_operations": False}]:
        with pytest.raises(SubmissionConflict):
            store.authorize_reviewed_retry(first["id"], invalid)
    assert store.status(first["id"])["state"] == "uncertain"
