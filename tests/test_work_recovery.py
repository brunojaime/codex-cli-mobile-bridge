"""Recovery with durable task identity, controlled agents and real Git/HTTP DEV."""
from datetime import timedelta
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading

import pytest

from test_work_coordinator import work, rig, request, complete_cycle, git
from backend.app.application.services.work_coordinator import WorkCoordinator, WorkCommandFailure
from backend.app.application.services.work_recovery import command_diagnostic


def enable(work, **overrides):
    policy = work.policy.model_copy(update={"automatic_recovery": True,
                                           "recovery_delay_seconds": 0, **overrides})
    work.service.policy(policy)
    return policy


def project(work):
    return work.service.overview()["projects"][0]


def block_validation(work):
    enable(work)
    task = work.service.enqueue(request(work))
    work.service.tick()
    active = project(work)["active"]
    complete_cycle(work, active)
    work.service.delivery = lambda task, policy: work.service._delivery_command(
        task, policy, "validate", 0, ["python3", "-c", "raise AssertionError('test failure')"]
    )
    work.service.tick()
    return task, active


def test_recovery_survives_restart_preserves_base_and_delivers_next_task(work, tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    git(work.rig.workspace, "remote", "add", "origin", str(remote))
    validator = work.rig.workspace / "validate.py"
    validator.write_text("from pathlib import Path\nassert 'fixed' in Path('index.html').read_text()\n")
    deploy = work.rig.workspace / "deploy.py"
    deploy.write_text("import json,pathlib,subprocess,sys\np=pathlib.Path(sys.argv[1]);p.mkdir(exist_ok=True)\n(p/'version.json').write_text(json.dumps({'environment':'dev','commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()}))\n")
    git(work.rig.workspace, "add", ".")
    git(work.rig.workspace, "commit", "-m", "Add actual local delivery")
    base = git(work.rig.workspace, "rev-parse", "HEAD")
    published = tmp_path / "dev"
    published.mkdir()
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(SimpleHTTPRequestHandler, directory=str(published)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        enable(work, validate=[["python3", "validate.py"]],
               deploy=["python3", "deploy.py", str(published)],
               dev_url=f"http://127.0.0.1:{server.server_port}/version.json")
        work.service.delivery = work.service._deliver
        first = work.service.enqueue(request(work))
        second = work.service.enqueue(request(work, "later"))
        work.service.tick()
        active = project(work)["active"]
        (work.rig.workspace / "index.html").write_text("<h1>Still broken</h1>")
        git(work.rig.workspace, "add", ".")
        git(work.rig.workspace, "commit", "-m", "First attempt")
        complete_cycle(work, active)
        work.service.tick()
        blocked = project(work)["queue"][0]
        assert blocked["status"] == "blocked"
        assert blocked["recovery"]["failure"]["stage"] == "validate"
        old_session = active["session_id"]
        # A real coordinator recreation proves the recovery state is durable.
        work.service = WorkCoordinator(work.rig.messages, work.service.database, clock=lambda: work.clock[0])
        work.service.tick()
        repair = project(work)["active"]
        assert repair["id"] == first["id"]
        assert repair["session_id"] != old_session
        assert repair["base_commit"] == base
        messages = work.rig.messages.list_messages(repair["session_id"])
        assert any("Recuperación automática del MISMO encargo" in m.content for m in messages)
        (work.rig.workspace / "index.html").write_text("<h1>fixed</h1>")
        git(work.rig.workspace, "add", ".")
        git(work.rig.workspace, "commit", "-m", "Correct failing validation")
        complete_cycle(work, repair)
        work.service.tick()
        delivered = project(work)["completed"][0]
        assert delivered["id"] == first["id"]
        assert delivered["recovery"]["state"] == "recovered"
        receipt = json.loads((published / "version.json").read_text())
        assert receipt["commit"] == git(work.rig.workspace, "rev-parse", "HEAD")
        assert git(work.rig.workspace, "ls-remote", "origin", "refs/heads/dev/lab").split()[0] == receipt["commit"]
        work.service.tick()
        assert project(work)["active"]["id"] == second["id"]
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("condition", ["day", "disabled", "stopped", "budget", "dirty", "uncertain"])
def test_recovery_respects_admission_and_preserves_work(work, condition):
    task, _ = block_validation(work)
    if condition == "day":
        work.clock[0] = work.clock[0].replace(hour=15)
    elif condition == "disabled":
        work.service.project_settings.update(str(work.rig.workspace), {"automatic_execution": False})
    elif condition == "dirty":
        (work.rig.workspace / "index.html").write_text("Unrelated WIP")
    else:
        with work.service.ledger() as db:
            if condition == "stopped":
                db.execute("UPDATE work_tasks SET stop_requested=1 WHERE id=?", (task["id"],))
            elif condition == "budget":
                db.execute("UPDATE work_tasks SET recoveries=3 WHERE id=?", (task["id"],))
            else:
                db.execute("UPDATE work_tasks SET status='uncertain' WHERE id=?", (task["id"],))
            db.commit()
    calls = len(work.rig.provider.requests)
    work.service.tick()
    assert len(work.rig.provider.requests) == calls
    if condition == "dirty":
        assert (work.rig.workspace / "index.html").read_text() == "Unrelated WIP"
        assert project(work)["queue"][0]["recovery"]["failure"] is None


def test_repeated_same_revision_failure_stops_without_spinning(work):
    _, _ = block_validation(work)
    work.service.tick()
    complete_cycle(work, project(work)["active"])
    work.service.tick()
    assert project(work)["queue"][0]["recovery"]["state"] == "repeated_failure"
    calls = len(work.rig.provider.requests)
    for _ in range(4):
        work.service.tick()
    assert len(work.rig.provider.requests) == calls


@pytest.mark.parametrize("stage,output,expected", [
    ("deploy", "test failed", "publication_needs_reconciliation"),
    ("validate", "Unauthorized", "credentials_required"),
    ("validate", "Previous publication attempt exists", "publication_uncertain"),
    ("validate", "Official gate changed", "operator_setup_required"),
])
def test_nonrepairable_failures_do_not_launch_models(work, stage, output, expected):
    task, _ = block_validation(work)
    diagnostic = command_diagnostic(stage=stage, index=0, argv=["python3", "operator.py"], returncode=1, output=output, revision="a" * 40)
    with work.service.ledger() as db:
        db.execute("UPDATE work_tasks SET failure=? WHERE id=?", (json.dumps(diagnostic), task["id"]))
        db.commit()
    count = len(work.rig.provider.requests)
    work.service.tick()
    assert len(work.rig.provider.requests) == count
    assert project(work)["queue"][0]["recovery"]["state"] == expected


def test_command_output_and_argv_secrets_never_enter_public_diagnostic(work):
    task = work.service.enqueue(request(work))
    secret = "FAKE_TEST_ONLY_credential_493"
    with pytest.raises(WorkCommandFailure) as exc:
        work.service._delivery_command(task, work.policy, "validate", 0,
            ["python3", "-c", f"print('{secret}');raise AssertionError('{secret}')"])
    assert secret not in str(exc.value)
    assert secret not in json.dumps(exc.value.diagnostic)
    logs = list((work.service.database.parent / "work-command-logs").glob("*.log"))
    assert len(logs) == 1
    assert secret in logs[0].read_text()
    assert logs[0].stat().st_mode & 0o777 == 0o600


def test_legacy_failure_is_diagnosed_before_launching_a_repair(work):
    policy = enable(work, validate=[["python3", "-c", "raise AssertionError('old failure')"]])
    task = work.service.enqueue(request(work))
    with work.service.ledger() as db:
        db.execute("UPDATE work_tasks SET status='blocked',policy=?,problem=? WHERE id=?",
                   (policy.model_dump_json(), "Falló una operación de validación/DEV (python, código 1)", task["id"]))
        db.commit()
    work.service.delivery = work.service._deliver
    work.service.tick()
    assert not work.rig.provider.requests
    blocked = project(work)["queue"][0]
    assert blocked["recovery"]["failure"]["stage"] == "validate"
    work.service.tick()
    assert project(work)["active"]["id"] == task["id"]
    assert len(work.rig.provider.requests) == 1


def test_interrupted_delivery_does_not_reuse_previous_validation_failure(work):
    task, _ = block_validation(work)
    work.service.tick()
    repair = project(work)["active"]
    complete_cycle(work, repair)
    with work.service.ledger() as db:
        db.execute("UPDATE work_tasks SET status='delivering' WHERE id=?", (task["id"],))
        db.commit()
    work.service.tick()
    assert project(work)["queue"][0]["recovery"]["failure"] is None
    count = len(work.rig.provider.requests)
    work.service.tick()
    assert len(work.rig.provider.requests) == count


def test_failed_cycle_does_not_reuse_previous_validation_failure(work):
    from backend.app.domain.entities.job import JobStatus
    task, _ = block_validation(work)
    work.service.tick()
    repair = project(work)["active"]
    complete_cycle(work, repair)
    job = work.rig.messages.list_stored_jobs_for_session(repair["session_id"])[0]
    # Fake provider is controlled, but the persisted terminal failure is real.
    job.status = JobStatus.FAILED
    work.rig.messages._repository.save_job(job)
    work.service.tick()
    assert project(work)["queue"][0]["recovery"]["failure"] is None


def test_legacy_validation_success_never_blindly_redeploys(work):
    policy = enable(work)
    task = work.service.enqueue(request(work))
    with work.service.ledger() as db:
        db.execute("UPDATE work_tasks SET status='blocked',policy=?,problem=? WHERE id=?",
                   (policy.model_dump_json(), "Falló una operación de validación/DEV (python, código 1)", task["id"]))
        db.commit()
    # There is deliberately no remote in this test. Read-only diagnosis stops;
    # the deployment callback must never be called to resolve an unknown phase.
    work.service.tick()
    assert not work.receipts
    assert not work.rig.provider.requests
    assert project(work)["queue"][0]["status"] == "blocked"


def test_known_operator_exposes_only_structural_missing_review_hint(work, tmp_path):
    from backend.app.application.services.work_recovery import operator_hints
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"state": str(tmp_path / "private-state")}))
    hints = operator_hints(["node", "gestion_dev_delivery.mjs", str(config), "validate"], work.rig.workspace, 0)
    assert hints == "\nFileNotFoundError: review.json"


@pytest.mark.parametrize("changed_after_choice", [False, True])
def test_explicit_delivery_resume_keeps_commit_and_does_not_rerun_agents(work, changed_after_choice):
    task, original_run = block_validation(work)
    (work.rig.workspace / "index.html").write_text("<h1>implemented</h1>")
    git(work.rig.workspace, "add", ".")
    git(work.rig.workspace, "commit", "-m", "Implementation already prepared")
    commit = git(work.rig.workspace, "rev-parse", "HEAD")
    diagnostic = command_diagnostic(stage="deploy", index=0, argv=["python3", "operator.py"],
                                    returncode=1, output="Previous publication attempt requires inspection", revision=commit)
    with work.service.ledger() as db:
        db.execute("UPDATE work_tasks SET failure=? WHERE id=?", (json.dumps(diagnostic), task["id"]))
        db.commit()
    blocked = project(work)["queue"][0]
    calls = len(work.rig.provider.requests)
    base = blocked["base_commit"]
    work.service.control(task["id"], blocked["revision"], "retry_delivery", commit)
    if changed_after_choice:
        (work.rig.workspace / "index.html").write_text("<h1>foreign newer commit</h1>")
        git(work.rig.workspace, "add", ".")
        git(work.rig.workspace, "commit", "-m", "Concurrent commit")
    delivered = []
    def deliver(task, policy):
        delivered.append(task)
        return {"environment": "dev", "commit": commit, "remote_confirmed": True}
    work.service.delivery = deliver
    work.service.tick()
    assert len(work.rig.provider.requests) == calls
    if changed_after_choice:
        assert not delivered
        assert project(work)["queue"][0]["status"] == "blocked"
    else:
        assert len(delivered) == 1
        assert delivered[0]["session_id"] == original_run["session_id"]
        assert delivered[0]["base_commit"] == base
        assert project(work)["completed"][0]["id"] == task["id"]


def test_delivery_resume_rejects_unprepared_task(work):
    from backend.app.application.services.work_coordinator import WorkConflict
    task = work.service.enqueue(request(work))
    with pytest.raises(WorkConflict):
        work.service.control(task["id"], task["revision"], "retry_delivery", git(work.rig.workspace, "rev-parse", "HEAD"))
