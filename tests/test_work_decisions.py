# ruff: noqa: F811
"""Real ledger/chat integration: escalation, same-task choices and restart safety."""

import pytest
from test_work_coordinator import work, rig, request  # noqa: F401
from backend.app.application.services.work_coordinator import WorkConflict
from backend.app.application.services.work_decisions import reconcile


def blocked(work, state="credentials_required"):
    task = work.service.enqueue(request(work))
    with work.service.ledger() as db:
        db.execute(
            "UPDATE work_tasks SET status='blocked',policy=?,problem='Configured operator needs attention',recovery_state=? WHERE id=?",
            (work.policy.model_dump_json(), state, task["id"]),
        )
        db.commit()
        reconcile(work.service, db)
    return task


def questions(work):
    return work.service.overview()["questions"]


def test_existing_block_creates_one_decision_and_real_notice_without_agent(work):
    task = blocked(work)
    q = questions(work)[0]
    assert q["source_task_id"] == task["id"]
    assert len(q["options"]) == 2
    with work.service.ledger() as db:
        reconcile(work.service, db)
        assert db.execute("SELECT count(*) FROM work_questions").fetchone()[0] == 1
    sessions = work.rig.messages.list_sessions()
    notices = [
        m
        for s in sessions
        for m in work.rig.messages.list_messages(s.id)
        if m.dedupe_key == "work-decision:" + q["id"]
    ]
    assert len(notices) == 1
    assert "Trabajo → Decisiones" in notices[0].content
    assert not work.rig.messages.list_stored_jobs_for_session(notices[0].session_id)


def test_choice_preserves_task_and_is_idempotent(work):
    task = blocked(work)
    q = questions(work)[0]
    before = work.service.overview()["projects"][0]["queue"][0]
    after = work.service.choose(q["id"], 0)
    assert after["id"] == task["id"]
    assert after["status"] == "queued"
    assert after["recovery"]["mode"] == "diagnose"
    assert after["recovery"]["attempts"] == before["recovery"]["attempts"]
    assert work.service.choose(q["id"], 0)["id"] == task["id"]
    with work.service.ledger() as db:
        assert db.execute("SELECT count(*) FROM work_tasks").fetchone()[0] == 1
    with pytest.raises(WorkConflict):
        work.service.choose(q["id"], 1)


def test_stale_choice_cannot_resume_a_changed_task(work):
    task = blocked(work)
    q = questions(work)[0]
    with work.service.ledger() as db:
        db.execute(
            "UPDATE work_tasks SET revision=revision+1 WHERE id=?", (task["id"],)
        )
        db.commit()
    with pytest.raises(WorkConflict):
        work.service.choose(q["id"], 0)


def test_hold_does_not_recreate_question_or_resume(work):
    blocked(work)
    q = questions(work)[0]
    assert work.service.choose(q["id"], 1)["status"] == "blocked"
    with work.service.ledger() as db:
        reconcile(work.service, db)
    assert questions(work) == []


def test_resolved_block_closes_question(work):
    task = blocked(work)
    with work.service.ledger() as db:
        db.execute("UPDATE work_tasks SET status='completed' WHERE id=?", (task["id"],))
        db.commit()
        reconcile(work.service, db)
    assert questions(work) == []


def test_notice_failure_retries_without_losing_decision_or_blocking(work, monkeypatch):
    from backend.app.application.services import work_decisions

    original = work_decisions.notify

    def interrupted(service, q):
        original(service, q)
        raise RuntimeError("simulate crash after chat commit")

    monkeypatch.setattr(work_decisions, "notify", interrupted)
    blocked(work)
    q = questions(work)[0]
    assert q["notice_sent"] == 0
    monkeypatch.setattr(work_decisions, "notify", original)
    with work.service.ledger() as db:
        reconcile(work.service, db)
    assert questions(work)[0]["notice_sent"] == 1
    notices = [
        m
        for s in work.rig.messages.list_sessions()
        for m in work.rig.messages.list_messages(s.id)
        if m.dedupe_key == "work-decision:" + q["id"]
    ]
    assert len(notices) == 1


def test_notice_trigger_and_resolution_cancel_existing_push_intent(work):
    import sqlite3
    from pathlib import Path

    with sqlite3.connect(work.rig.db) as chat:
        chat.executescript(
            Path("services/notifications/migrations/001-push.sql").read_text()
        )
        chat.executescript(
            Path(
                "services/notifications/migrations/002-trigger-idempotency.sql"
            ).read_text()
        )
    blocked(work)
    q = questions(work)[0]
    with sqlite3.connect(work.rig.db) as chat:
        events = chat.execute(
            "SELECT id,cancelled_at FROM bridge_push_events"
        ).fetchall()
        assert len(events) == 1 and events[0][1] is None
    work.service.choose(q["id"], 1)
    with sqlite3.connect(work.rig.db) as chat:
        assert (
            chat.execute("SELECT cancelled_at FROM bridge_push_events").fetchone()[0]
            is not None
        )


def test_reject_cancels_notice_and_keeps_task(work):
    blocked(work)
    q = questions(work)[0]
    work.service.respond(q["id"], "reject")
    assert not questions(work)
    assert work.service.overview()["projects"][0]["queue"][0]["status"] == "blocked"


def test_chosen_diagnosis_never_calls_deploy_or_model(work):
    task = blocked(work)
    q = questions(work)[0]
    work.service.choose(q["id"], 0)
    calls = []

    def diagnosis(current, policy):
        calls.append(current["id"])
        return {"environment": "dev", "commit": "a" * 40, "remote_confirmed": True}

    def forbidden(*args):
        pytest.fail("A diagnostic choice must not publish or invoke a model")

    work.service._diagnose_delivery = diagnosis
    work.service.delivery = forbidden
    work.rig.messages.start_auto_run = forbidden
    work.service.tick()
    assert calls == [task["id"]]
    assert work.service.overview()["projects"][0]["completed"][0]["id"] == task["id"]


def test_decision_surfaces_even_after_daily_budget_exhaustion(work):
    blocked(work)
    policy = work.policy.model_copy(update={"max_tasks_per_day": 1})
    work.service.policy(policy)
    with work.service.ledger() as db:
        db.execute("UPDATE work_questions SET selected=-2")
        db.execute("DELETE FROM work_questions")
        db.execute(
            "INSERT INTO work_events(task_id,kind,text,created_at) SELECT id,'starting','starting',? FROM work_tasks",
            (work.clock[0].isoformat(),),
        )
        db.commit()
    work.service.tick()
    assert questions(work)
