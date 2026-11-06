from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.app.api.work_routes import router, get_container
from backend.app.application.services.work_coordinator import (
    WorkCoordinator,
    WorkInput,
    WorkPolicy,
    WorkConflict,
    WorkspaceBusy,
)
from test_generator_reviewer_launch import rig as base_rig


def git(path, *args):
    return subprocess.check_output(
        ["git", *args], cwd=path, text=True, stderr=subprocess.DEVNULL
    ).strip()


@pytest.fixture
def rig(tmp_path):
    yield from base_rig.__wrapped__(tmp_path)


@pytest.fixture
def work(rig):
    git(rig.workspace, "init", "-b", "dev/lab")
    git(rig.workspace, "config", "user.name", "Work Test")
    git(rig.workspace, "config", "user.email", "work-test@example.invalid")
    (rig.workspace / "index.html").write_text("<h1>Inicio</h1>")
    git(rig.workspace, "add", "index.html")
    git(rig.workspace, "commit", "-m", "Initial lab")
    receipts = []

    def deliver(task, policy):
        receipt = {
            "environment": "dev",
            "commit": git(rig.workspace, "rev-parse", "HEAD"),
            "remote_confirmed": True,
            "dev_url": policy.dev_url,
        }
        receipts.append(receipt)
        return receipt

    clock = [datetime(2026, 11, 6, 2, 0, tzinfo=timezone.utc)]
    service = WorkCoordinator(
        rig.messages,
        rig.db.with_suffix(".work.sqlite3"),
        delivery=deliver,
        clock=lambda: clock[0],
    )
    policy = WorkPolicy(
        workspace_path=str(rig.workspace),
        enabled=True,
        dev_branch="dev/lab",
        dev_url="http://127.0.0.1:19876/version.json",
        validate=[["python3", "-c", "pass"]],
        deploy=["python3", "-c", "pass"],
        dev_isolated=True,
        reconcile_dev=False,
    )
    service.policy(policy)
    return SimpleNamespace(
        service=service, rig=rig, policy=policy, receipts=receipts, clock=clock
    )


def request(work, key="one", **changes):
    return WorkInput(
        workspace_path=str(work.rig.workspace),
        source="chat",
        source_key=key,
        instruction="Cambiar el título del laboratorio",
        **changes,
    )


def complete_cycle(work, task, response="Título actualizado y comprobado"):
    for _ in range(12):
        jobs = work.rig.messages.list_stored_jobs_for_session(task["session_id"])
        for job in jobs:
            if not job.status.is_terminal:
                work.rig.provider.complete_job(job.id, response=response)
                work.rig.messages.get_job(job.id)
        session = work.rig.messages.get_session(task["session_id"])
        if session.active_agent_run_id is None and all(
            j.status.is_terminal
            for j in work.rig.messages.list_stored_jobs_for_session(task["session_id"])
        ):
            return
    raise AssertionError("Agent cycle did not close within its budget")


def test_serial_queue_context_delivery_and_no_drive_trigger(work):
    service = work.service
    first = service.enqueue(request(work))
    second = service.enqueue(request(work, "two"))
    assert service.enqueue(request(work))["id"] == first["id"]
    service.tick()
    overview = service.overview()
    active = overview["projects"][0]["active"]
    assert active["id"] == first["id"]
    assert len(work.rig.provider.requests) == 1
    service.tick()
    assert len(work.rig.provider.requests) == 1
    with pytest.raises(WorkspaceBusy):
        work.rig.messages.submit_message(
            "No parallel writer", session_id=work.rig.source.id
        )
    complete_cycle(work, active)
    service.tick()
    assert len(work.receipts) == 1
    service.tick()
    active = service.overview()["projects"][0]["active"]
    assert active["id"] == second["id"]
    assert "Título actualizado" in work.rig.provider.requests[-1]["message"]
    assert service.overview()["folder_triggers"] is False


def test_does_not_advance_when_generator_finishes_but_reviewer_is_active(work):
    service = work.service
    service.enqueue(request(work))
    service.enqueue(request(work, "two"))
    service.tick()
    active = service.overview()["projects"][0]["active"]
    first = work.rig.messages.list_stored_jobs_for_session(active["session_id"])[0]
    work.rig.provider.complete_job(first.id, response="First implementation")
    service.tick()
    assert service.overview()["projects"][0]["active"]["id"] == active["id"]
    assert not work.receipts


def test_concurrent_intake_and_worker_admission_are_idempotent(work):
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(
            pool.map(lambda _: work.service.enqueue(request(work)), range(3))
        )
    assert len({r["id"] for r in results}) == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: work.service.tick(), range(2)))
    assert len(work.rig.provider.requests) == 1


def test_delivery_failure_is_visible_not_completed(work):
    work.service.delivery = lambda *_: (_ for _ in ()).throw(
        WorkConflict("DEV no corresponde al commit")
    )
    work.service.enqueue(request(work))
    work.service.tick()
    task = work.service.overview()["projects"][0]["active"]
    complete_cycle(work, task)
    work.service.tick()
    overview = work.service.overview()
    assert overview["summary"]["completed"] == 0
    assert overview["summary"]["blocked"] == 1
    assert "DEV" in overview["projects"][0]["queue"][0]["problem"]


def test_night_spans_midnight_and_budget_does_not_reset_at_midnight(work):
    work.service.policy(work.policy.model_copy(update={"max_tasks_per_day": 1}))
    assert work.service._night(work.policy) == "2026-11-05"
    work.service.enqueue(request(work))
    work.service.enqueue(request(work, "two"))
    work.service.tick()
    task = work.service.overview()["projects"][0]["active"]
    complete_cycle(work, task)
    work.service.tick()
    work.clock[0] = datetime(2026, 11, 6, 8, 0, tzinfo=timezone.utc)  # 05:00 Argentina
    assert work.service._night(work.policy) == "2026-11-05"
    work.service.tick()
    assert work.service.overview()["projects"][0]["active"] is None
    assert len(work.receipts) == 1


def test_paused_policy_and_empty_queue_use_no_model(work):
    for _ in range(5):
        work.service.tick()
    assert not work.rig.provider.requests
    work.service.policy(work.policy.model_copy(update={"enabled": False}))
    work.service.enqueue(request(work))
    work.service.tick()
    assert not work.rig.provider.requests


def test_read_only_supervisor_question_and_choice(work):
    work.service.policy(
        work.policy.model_copy(
            update={"autonomous": True, "focus": "Revisar textos del laboratorio"}
        )
    )
    work.service.tick()
    assert len(work.rig.provider.requests) == 1
    options = work.rig.provider.requests[0]["codex_options"]
    assert any("read-only" in c for c in options.config_overrides)
    response = json.dumps(
        {
            "decision": "question",
            "summary": "¿Qué texto priorizamos?",
            "options": [
                {"label": "Título", "instruction": "Mejorar el título"},
                {"label": "Descripción", "instruction": "Mejorar descripción"},
            ],
        }
    )
    work.rig.provider.complete_job("job-1", response=response)
    work.service.tick()
    questions = work.service.overview()["questions"]
    assert len(questions) == 1
    chosen = work.service.choose(questions[0]["id"], 0)
    assert work.service.choose(questions[0]["id"], 0)["id"] == chosen["id"]
    with pytest.raises(WorkConflict):
        work.service.choose(questions[0]["id"], 1)


def test_routes_intake_modes_and_no_folder(work):
    app = FastAPI()
    container = SimpleNamespace(work_coordinator_service=work.service)
    app.dependency_overrides[get_container] = lambda: container
    app.include_router(router)
    with TestClient(app) as client:
        assert (
            client.post(
                "/work/backlog", json={**request(work).model_dump(), "source": "folder"}
            ).status_code
            == 422
        )
        assert (
            client.post("/work/backlog", json=request(work).model_dump()).status_code
            == 201
        )
        assert client.get("/work").json()["summary"]["queued"] == 1


def test_real_git_and_dev_delivery(work, tmp_path):
    """Real local remote + HTTP DEV receipt; no model or cloud deployment involved."""
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    import threading
    import functools

    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)], check=True, capture_output=True
    )
    git(work.rig.workspace, "remote", "add", "origin", str(remote))
    published = tmp_path / "dev"
    published.mkdir()
    script = work.rig.workspace / "deploy.py"
    script.write_text(
        "import json, pathlib, subprocess, sys\np=pathlib.Path(sys.argv[1]);p.mkdir(exist_ok=True)\np.joinpath('version.json').write_text(json.dumps({'environment':'dev','commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()}))\n"
    )
    git(work.rig.workspace, "add", "deploy.py")
    git(work.rig.workspace, "commit", "-m", "Add lab deployment")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(published))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        policy = work.policy.model_copy(
            update={
                "dev_url": f"http://127.0.0.1:{server.server_port}/version.json",
                "deploy": ["python3", "deploy.py", str(published)],
            }
        )
        receipt = work.service._deliver(request(work).model_dump(), policy)
        assert receipt["remote_confirmed"]
        assert (
            git(
                work.rig.workspace, "ls-remote", "origin", "refs/heads/dev/lab"
            ).split()[0]
            == receipt["commit"]
        )
    finally:
        server.shutdown()
        server.server_close()


def test_two_tasks_publish_in_sequence_with_real_git_and_dev(work, tmp_path):
    """Controlled agents, actual commits/push/DEV HTTP, then dependent work."""
    import functools
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    import os
    import threading

    remote = tmp_path / "pilot.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)], check=True, capture_output=True
    )
    git(work.rig.workspace, "remote", "add", "origin", str(remote))
    published = tmp_path / "published-dev"
    published.mkdir()
    (work.rig.workspace / "deploy.py").write_text(
        "import json,pathlib,subprocess,sys,shutil\np=pathlib.Path(sys.argv[1]);p.mkdir(exist_ok=True)\n"
        "shutil.copy('index.html',p/'index.html')\n"
        "(p/'version.json').write_text(json.dumps({'environment':'dev','commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()}))\n"
    )
    git(work.rig.workspace, "add", "deploy.py")
    git(work.rig.workspace, "commit", "-m", "Configure isolated DEV")
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        functools.partial(SimpleHTTPRequestHandler, directory=str(published)),
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        work.service.delivery = work.service._deliver
        policy = work.policy.model_copy(
            update={
                "dev_url": f"http://127.0.0.1:{server.server_port}/version.json",
                "deploy": ["python3", "deploy.py", str(published)],
            }
        )
        work.service.policy(policy)
        first = work.service.enqueue(request(work, "pilot-title"))
        second = work.service.enqueue(
            WorkInput(
                workspace_path=str(work.rig.workspace),
                source="whatsapp",
                source_key="pilot-description",
                instruction="Agregar una descripción manteniendo el título anterior",
            )
        )
        evidence = []
        for position, task in enumerate([first, second]):
            work.service.tick()
            active = work.service.overview()["projects"][0]["active"]
            assert active["id"] == task["id"]
            if position:
                assert (
                    evidence[0]["commit"] in work.rig.provider.requests[-1]["message"]
                )
            html = (
                '<!doctype html><html lang="es"><meta name="viewport" content="width=device-width"><title>Laboratorio nocturno</title><body><h1>Laboratorio nocturno</h1>'
                + (
                    "<p>El segundo encargo conservó el título y agregó esta descripción.</p>"
                    if position
                    else ""
                )
                + "</body></html>"
            )
            (work.rig.workspace / "index.html").write_text(html)
            git(work.rig.workspace, "add", "index.html")
            git(work.rig.workspace, "commit", "-m", f"Pilot task {position + 1}")
            complete_cycle(
                work, active, response="Cambio implementado, validado y commiteado"
            )
            work.service.tick()
            completed = next(
                t
                for t in work.service.overview()["projects"][0]["completed"]
                if t["id"] == task["id"]
            )
            receipt = completed["receipt"]
            assert completed["status"] == "completed"
            assert (
                git(
                    work.rig.workspace, "ls-remote", "origin", "refs/heads/dev/lab"
                ).split()[0]
                == receipt["commit"]
            )
            assert (published / "index.html").read_text() == html
            evidence.append(
                {
                    "step": position + 1,
                    "status": "completed",
                    "commit": receipt["commit"],
                    "remote_confirmed": True,
                    "dev_confirmed": True,
                    "source": task["source"],
                }
            )
            if os.environ.get("CAPTURE_WORK_PILOT") == "1":
                folder = (
                    Path(__file__).resolve().parents[1]
                    / "reports/work-coordinator-pilot"
                )
                folder.mkdir(parents=True, exist_ok=True)
                (folder / f"paso-{position + 1}.html").write_text(html)
        assert evidence[0]["commit"] != evidence[1]["commit"]
        if os.environ.get("CAPTURE_WORK_PILOT") == "1":
            (folder / "evidencia.json").write_text(
                json.dumps(
                    {
                        "agents": "controlled test provider; no model calls",
                        "git": "isolated local bare remote",
                        "dev": "isolated HTTP service, not public",
                        "steps": evidence,
                    },
                    indent=2,
                )
            )
    finally:
        server.shutdown()
        server.server_close()


def test_retry_uses_new_session_and_does_not_duplicate_completed_run(work):
    task = work.service.enqueue(request(work))
    work.service.tick()
    active = work.service.overview()["projects"][0]["active"]
    first_session = active["session_id"]
    complete_cycle(work, active)
    work.service.delivery = lambda *_: (_ for _ in ()).throw(
        ValueError("DEV unavailable")
    )
    work.service.tick()
    blocked = work.service.overview()["projects"][0]["queue"][0]
    assert blocked["status"] == "blocked"
    work.service.control(task["id"], blocked["revision"], "retry")
    work.service.tick()
    active = work.service.overview()["projects"][0]["active"]
    assert active["status"] in {"starting", "running"}
    assert active["session_id"] != first_session


def test_intake_during_delivery_remains_responsive(work):
    work.service.enqueue(request(work))
    work.service.tick()
    complete_cycle(work, work.service.overview()["projects"][0]["active"])
    original = work.service.delivery

    def deliver(task, policy):
        with ThreadPoolExecutor() as pool:
            result = pool.submit(
                work.service.enqueue, request(work, "during-publish")
            ).result(timeout=3)
            assert result["status"] == "queued"
        return original(task, policy)

    work.service.delivery = deliver
    work.service.tick()
    assert len(work.service.overview()["projects"][0]["queue"]) == 1


def test_blocked_delivery_holds_later_tasks(work):
    work.service.enqueue(request(work))
    work.service.enqueue(request(work, "later"))
    work.service.tick()
    active = work.service.overview()["projects"][0]["active"]
    complete_cycle(work, active)
    work.service.delivery = lambda *_: (_ for _ in ()).throw(
        ValueError("DEV unavailable")
    )
    work.service.tick()
    calls = len(work.rig.provider.requests)
    work.service.tick()
    assert len(work.rig.provider.requests) == calls
    assert work.service.overview()["projects"][0]["active"] is None


@pytest.mark.parametrize("evidence_kind", ["normal", "dense_annotations", "long_comments"])
def test_feedback_backlog_preserves_screenshot_and_does_not_start_a_job(tmp_path, evidence_kind):
    import base64
    from test_message_flow import build_feedback_queue_client

    projects = tmp_path / "projects"
    workspace = projects / "lab"
    workspace.mkdir(parents=True)
    client = build_feedback_queue_client(
        tmp_path, projects_root=projects, bridge_environment="dev"
    )
    payload = {
        "sourceApp": "lab",
        "sourceDisplayName": "Laboratorio",
        "workspacePath": str(workspace),
        "batchId": "stable-feedback",
        "executionMode": "backlog",
        "workflowPresetId": "default",
        "items": [
            {
                "id": "one",
                "comment": "Cambiar el título",
                "screenshotPngBase64": base64.b64encode(b"fixture image").decode(),
            }
        ],
    }
    if evidence_kind == "dense_annotations":
        payload["items"][0]["contextMetadata"] = {
            "pathname": "/admin/configuracion",
            "annotations": {"strokes": [{"points": [{"x": i / 10, "y": i / 20} for i in range(5000)]}]},
        }
    elif evidence_kind == "long_comments":
        payload["items"] = [{**payload["items"][0], "id": str(i), "comment": "Detalle original " + "á" * 9000} for i in range(4)]
    original_comments = [item["comment"] for item in payload["items"]]
    original_context = payload["items"][0].get("contextMetadata", {})
    response = client.post("/feedback-batches/start-session", json=payload)
    assert response.status_code == 202, response.text
    receipt = response.json()
    assert receipt["backlogId"]
    assert client.get("/work").json()["summary"]["queued"] == 1
    assert (
        client.post("/feedback-batches/start-session", json=payload).json() == receipt
    )
    task = client.get("/work").json()["projects"][0]["queue"][0]
    assert len(task["instruction"]) <= 30000
    assert len(task["references"]) == 1
    evidence = json.loads(Path(task["references"][0]).read_text())
    assert [item["comment"] for item in evidence["items"]] == original_comments
    assert evidence["items"][0]["context_metadata"] == original_context
    assert len(evidence["items"]) == len(payload["items"])
    assert "annotations" not in task["instruction"]
    payload["items"][0]["comment"] = "Otro alcance"
    assert (
        client.post("/feedback-batches/start-session", json=payload).status_code == 409
    )
    project = client.get("/work").json()["projects"][0]
    assert len(project["queue"][0]["attachments"]) == len(payload["items"])
    assert client.get("/sessions").json() == []


def test_nightly_dev_reconciliation_uses_no_models(work):
    work.service.policy(work.policy.model_copy(update={"reconcile_dev": True}))
    work.service.tick()
    assert len(work.receipts) == 1
    assert not work.rig.provider.requests
    work.service.tick()
    assert len(work.receipts) == 1  # sleeps for an hour, no duplicate publication


def test_question_observations_and_rejection_never_start_a_model(work):
    with work.service.ledger() as db:
        db.execute(
            "INSERT INTO work_questions(id,workspace,title,options,created_at) VALUES (?,?,?,?,?)",
            (
                "question",
                str(work.rig.workspace),
                "Cómo seguimos",
                json.dumps(
                    [
                        {"label": "Mejorar", "instruction": "Mejorar accesibilidad"},
                        {"label": "Ordenar", "instruction": "Ordenar pendientes"},
                    ]
                ),
                work.clock[0].isoformat(),
            ),
        )
        db.commit()
    work.service.respond("question", "observations", "Conservar colores")
    assert not work.rig.provider.requests
    task = work.service.choose("question", 0)
    assert "Conservar colores" in task["instruction"]
    assert not work.rig.provider.requests
    with pytest.raises(WorkConflict):
        work.service.respond("question", "reject")
    with work.service.ledger() as db:
        db.execute(
            "INSERT INTO work_questions(id,workspace,title,options,created_at) VALUES (?,?,?,?,?)",
            (
                "discard",
                str(work.rig.workspace),
                "Otra",
                "[]",
                work.clock[0].isoformat(),
            ),
        )
        db.commit()
    assert work.service.respond("discard", "reject")["status"] == "rejected"
    assert work.service.respond("discard", "reject")["status"] == "rejected"
    assert len(work.service.overview()["projects"][0]["queue"]) == 1


def test_stop_waits_for_confirmed_cycle_end_and_never_publishes(work):
    work.service.enqueue(request(work))
    work.service.enqueue(request(work, "later"))
    work.service.tick()
    active = work.service.overview()["projects"][0]["active"]
    work.service.control(active["id"], active["revision"], "stop")
    for _ in range(8):
        work.service.tick()
        if work.service.overview()["projects"][0]["active"] is None:
            break
    project = work.service.overview()["projects"][0]
    assert project["active"] is None
    assert project["queue"][0]["status"] == "blocked"
    assert not work.receipts
    assert len(work.rig.provider.requests) == 1


def test_intake_cannot_impersonate_supervisor_or_pass_git_flags(work):
    with pytest.raises(ValueError):
        work.service.enqueue(request(work, "supervisor-dev:untrusted"))
    with pytest.raises(ValueError):
        WorkPolicy.model_validate({**work.policy.model_dump(), "remote": "-f"})


def test_corrupt_claim_never_admits_another_writer(work):
    work.service.lock_root.mkdir(parents=True, exist_ok=True)
    work.service._marker(str(work.rig.workspace)).write_text("{")
    with pytest.raises(WorkspaceBusy):
        work.rig.messages.submit_message(
            "Should not start", session_id=work.rig.source.id
        )
    assert not work.rig.provider.requests


def test_existing_task_uses_linked_checkout_and_preserves_project_identity(
    work, tmp_path
):
    service = work.service
    original = work.rig.workspace
    with service.ledger() as db:
        db.execute("DELETE FROM work_policies")
        db.commit()
    service.project_settings.update(str(original), {"automatic_execution": True})
    task = service.enqueue(request(work, "preexisting-linked"))
    service.tick()
    assert (
        service.project_settings.overview()["projects"][0]["execution_status"]
        == "needs_setup"
    )
    assert not work.rig.provider.requests
    checkout = tmp_path / "isolated"
    git(original, "worktree", "add", "-b", "dev/isolated", str(checkout))
    (original / "foreign.txt").write_text("foreign pending changes\n")
    before = git(original, "status", "--porcelain")
    service.policy(
        work.policy.model_copy(
            update={
                "execution_workspace": str(checkout),
                "dev_branch": "dev/isolated",
                "execution_context": "Preserve request and attachments; QA/PROD have their own procedure.",
            }
        )
    )
    service.tick()
    active = service.overview()["projects"][0]["active"]
    assert active["id"] == task["id"]
    assert active["source_key"] == "preexisting-linked"
    assert active["revision"] == task["revision"]
    session = work.rig.messages.get_session(active["session_id"])
    assert session.workspace_path == str(original)
    assert service.execution_workspace_for(session) == str(checkout)
    assert work.rig.provider.requests[-1]["workdir"] == str(checkout)
    assert service._marker(str(checkout)).exists()
    with pytest.raises(WorkspaceBusy):
        service.check_claim(str(checkout), None)
    complete_cycle(work, active)
    service.tick()
    assert not service._marker(str(checkout)).exists()
    assert git(original, "status", "--porcelain") == before
    assert (original / "foreign.txt").read_text() == "foreign pending changes\n"


def test_separate_checkout_rejects_unrelated_repository(work, tmp_path):
    other = tmp_path / "unrelated"
    other.mkdir()
    git(other, "init", "-b", "dev/other")
    with pytest.raises(WorkConflict, match="repositorio"):
        work.service.checkout(
            work.policy.model_copy(update={"execution_workspace": str(other)})
        )


@pytest.mark.parametrize("environment", ["dev", "qa"])
def test_sveltekit_receipt_verifies_actual_health_and_commit(
    work, tmp_path, environment
):
    import functools
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    import threading

    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)], check=True, capture_output=True
    )
    git(work.rig.workspace, "remote", "add", "origin", str(remote))
    checkout = tmp_path / "delivery-worktree"
    git(work.rig.workspace, "worktree", "add", "-b", "dev/svelte", str(checkout))
    (work.rig.workspace / "foreign.txt").write_text("keep unchanged")
    (checkout / "index.html").write_text("<h1>Changed</h1>")
    git(checkout, "add", "index.html")
    git(checkout, "commit", "-m", "Implement task")
    commit = git(checkout, "rev-parse", "HEAD")
    published = tmp_path / "published"
    (published / "_app").mkdir(parents=True)
    (published / "api").mkdir()
    (published / "_app/version.json").write_text(json.dumps({"version": commit}))
    (published / "api/health").write_text(
        json.dumps({"status": "ok", "environment": environment})
    )
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        functools.partial(SimpleHTTPRequestHandler, directory=str(published)),
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        policy = work.policy.model_copy(
            update={
                "execution_workspace": str(checkout),
                "dev_branch": "dev/svelte",
                "dev_url": f"http://127.0.0.1:{server.server_port}/_app/version.json",
                "verification_strategy": "sveltekit",
                "deploy": ["python3", "-c", "pass"],
            }
        )
        if environment == "dev":
            assert (
                work.service._deliver(request(work).model_dump(), policy)["commit"]
                == commit
            )
        else:
            with pytest.raises(WorkConflict, match="versión servida"):
                work.service._deliver(request(work).model_dump(), policy)
        assert (work.rig.workspace / "foreign.txt").read_text() == "keep unchanged"
        assert (
            git(checkout, "ls-remote", "origin", "refs/heads/dev/svelte").split()[0]
            == commit
        )
    finally:
        server.shutdown()
        server.server_close()


def test_leader_lock_prevents_second_coordinator_admission(work):
    import fcntl

    service = work.service
    service.enqueue(request(work, "leader-lock"))
    with service.database.with_suffix(".worker.lock").open("a") as leader:
        fcntl.flock(leader, fcntl.LOCK_EX)
        service.tick()
        assert not work.rig.provider.requests
    service.tick()
    assert len(work.rig.provider.requests) == 1


def test_missing_linked_checkout_blocks_task_without_touching_original(work, tmp_path):
    checkout = tmp_path / "removed-worktree"
    git(work.rig.workspace, "worktree", "add", "-b", "dev/removed", str(checkout))
    work.service.policy(
        work.policy.model_copy(
            update={"execution_workspace": str(checkout), "dev_branch": "dev/removed"}
        )
    )
    task = work.service.enqueue(request(work, "removed-checkout"))
    git(work.rig.workspace, "worktree", "remove", str(checkout))
    work.service.tick()
    queued = work.service.overview()["projects"][0]["queue"]
    assert queued[0]["id"] == task["id"]
    assert queued[0]["status"] == "blocked"
    assert not work.rig.provider.requests
    assert git(work.rig.workspace, "status", "--porcelain") == ""


def test_project_switch_is_durable_and_controls_next_task(work):
    service = work.service
    path = str(work.rig.workspace)
    first = service.enqueue(request(work))
    service.enqueue(request(work, 'next'))
    service.project_settings.update(path, {'automatic_execution': False})
    service.tick()
    assert service.overview()['projects'][0]['active'] is None
    assert service.project_settings.overview()['projects'][0]['execution_status'] == 'disabled'
    service.project_settings.update(path, {'automatic_execution': True})
    service.tick()
    active = service.overview()['projects'][0]['active']
    assert active['id'] == first['id']
    service.project_settings.update(path, {'automatic_execution': False})
    complete_cycle(work, active)
    service.tick()
    service.tick()
    assert len(work.receipts) == 1
    assert service.overview()['projects'][0]['queue'][0]['status'] == 'queued'
    restarted = WorkCoordinator(work.rig.messages, service.database, delivery=service.delivery)
    assert restarted.project_settings.overview()['projects'][0]['settings']['automatic_execution'] is False


def test_settings_lists_empty_projects_and_explains_missing_delivery(work):
    service = work.service
    path = str(work.rig.workspace)
    with service.ledger() as db:
        db.execute('DELETE FROM work_policies')
        db.commit()
    assert service.project_settings.overview()['projects'][0]['settings'] == {'automatic_execution': False}
    service.project_settings.update(path, {'automatic_execution': True})
    project = service.project_settings.overview()['projects'][0]
    assert project['execution_status'] == 'needs_setup'
    service.tick()
    assert service.project_settings.overview()['projects'][0]['settings']['automatic_execution'] is True


def test_project_settings_api_validates_keys_values_and_workspace(work):
    app = FastAPI()
    from backend.app.api.work_routes import get_work
    app.include_router(router)
    app.dependency_overrides[get_work] = lambda: work.service
    client = TestClient(app)
    path = str(work.rig.workspace)
    assert client.get('/work/settings').status_code == 200
    payload = {'workspace_path': path, 'settings': {'automatic_execution': False}}
    assert client.put('/work/settings', json=payload).json()['settings']['automatic_execution'] is False
    for settings in [{'unknown': True}, {'automatic_execution':'false'}, {}]:
        assert client.put('/work/settings', json={**payload, 'settings': settings}).status_code == 422
    assert client.put('/work/settings', json={**payload, 'workspace_path':'/missing'}).status_code == 422


def test_execution_configuration_uses_registered_strategy(work):
    from backend.app.application.services.work_settings import ProjectSettings
    class DisableStrategy:
        key = 'automatic_execution'
        def default(self, policy):
            return True
        def apply(self, policy, value):
            return {**policy, 'enabled': False}
    settings = ProjectSettings(work.service, strategies=[DisableStrategy()])
    with work.service.ledger() as db:
        assert settings.effective(db, work.policy.model_dump())['enabled'] is False


def test_dev_receipt_identifies_bridge_to_origin(work):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading

    requests = []

    class Origin(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, self.headers.get("User-Agent")))
            if self.headers.get("User-Agent") != "Codex-Bridge/1.0":
                self.send_error(403)
                return
            self.send_response(200)
            self.end_headers()
            data = {"version": "a" * 40} if self.path == "/_app/version.json" else {"environment": "dev"}
            self.wfile.write(json.dumps(data).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Origin)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        policy = work.policy.model_copy(update={"dev_url": f"http://127.0.0.1:{server.server_port}/_app/version.json", "verification_strategy": "sveltekit"})
        assert work.service.dev_receipt(policy) == {"environment": "dev", "commit": "a" * 40}
        assert requests == [("/_app/version.json", "Codex-Bridge/1.0"), ("/api/health", "Codex-Bridge/1.0")]
    finally:
        server.shutdown()
        server.server_close()
