from datetime import datetime, timezone
import json

import httpx
import pytest

from services.nightly_discovery.worker import Worker, night_key, parse_result


def test_night_identity_and_boundaries():
    def key(value):
        return night_key(datetime.fromisoformat(value))
    assert key("2026-11-07T01:29:00+00:00") is None
    assert key("2026-11-07T01:30:00+00:00") == "2026-11-06"
    assert key("2026-11-07T10:59:00+00:00") == "2026-11-06"
    assert key("2026-11-07T11:00:00+00:00") is None


def test_opportunities_require_evidence():
    with pytest.raises(ValueError):
        parse_result(json.dumps({"decision": "task", "summary": "Improve", "instruction": "Do it"}))


def test_discovery_without_delivery_is_read_only_and_idempotent(tmp_path):
    calls = []
    task = {"decision": "task", "summary": "Fix missing label", "instruction": "Add label and verify keyboard navigation", "evidence": ["src/form.html:12 missing label"]}
    def respond(request):
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        path = request.url.path
        if path == "/work/settings":
            data = {"projects": [{"workspace_path": "/project", "settings": {"automatic_execution": True}, "execution_status": "needs_setup"}]}
        elif path == "/work":
            data = {"projects": []}
        elif path == "/sessions":
            data = {"id": "session", "agent_configuration": {"preset": "review", "agents": [{"agent_id": "generator"}, {"agent_id": "reviewer"}]}}
        elif path.endswith("/agents"):
            data = body
        elif path.endswith("/messages"):
            data = {"job_id": "job"}
        elif path == "/sessions/session":
            data = {"messages": [{"role": "assistant", "job_id": "job", "job_status": "completed", "content": json.dumps(task)}]}
        elif path == "/work/backlog":
            data = {"id": "task"}
        else:
            raise AssertionError(path)
        return httpx.Response(200, json=data)
    with httpx.Client(base_url="http://bridge", transport=httpx.MockTransport(respond)) as client:
        config = {"enabled": True, "projects": [{"name": "Project", "workspace_path": "/project"}]}
        worker = Worker(config, tmp_path / "state.sqlite", tmp_path / "report.json", client)
        now = datetime(2026, 11, 7, 3, tzinfo=timezone.utc)
        worker.tick(now)
        worker.tick(now)
        worker.tick(now)
        assert worker.db.execute("SELECT status FROM reviews").fetchone()[0] == "completed"
        submissions = [body for _, path, body in calls if path.endswith("/messages")]
        assert len(submissions) == 1
        assert 'sandbox_mode="read-only"' in submissions[0]["codex_options"]["config_overrides"]
        configuration = next(body for _, path, body in calls if path.endswith("/agents"))
        assert configuration["preset"] == "solo"
        assert [a["agent_id"] for a in configuration["agents"] if a["enabled"]] == ["generator"]
        backlogs = [body for _, path, body in calls if path == "/work/backlog"]
        assert len(backlogs) == 1
        assert backlogs[0]["source_key"].startswith("nightly-discovery:")
        assert "references" not in backlogs[0]
        assert task["evidence"][0] in backlogs[0]["instruction"]
        assert not any("deploy" in path for _, path, _ in calls)


def test_uncertain_submission_never_resends(tmp_path):
    calls = []
    def respond(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"messages": []})
    with httpx.Client(base_url="http://bridge", transport=httpx.MockTransport(respond)) as client:
        worker = Worker({"enabled": True, "projects": []}, tmp_path / "state.sqlite", tmp_path / "report.json", client)
        worker.db.execute("INSERT INTO reviews(night,workspace,name,status,session_id) VALUES ('2026-11-06','/project','Project','submitting','session')")
        worker.db.commit()
        worker.tick(datetime(2026, 11, 7, 3, tzinfo=timezone.utc))
        assert worker.db.execute("SELECT status FROM reviews").fetchone()[0] == "uncertain"
        assert calls == ["/sessions/session"]


def test_disabled_and_daytime_do_not_start_jobs(tmp_path):
    with httpx.Client(base_url="http://bridge", transport=httpx.MockTransport(lambda request: pytest.fail("Unexpected API call"))) as client:
        worker = Worker({"enabled": False, "projects": []}, tmp_path / "state.sqlite", tmp_path / "report.json", client)
        worker.tick(datetime(2026, 11, 7, 3, tzinfo=timezone.utc))
        worker.config["enabled"] = True
        worker.tick(datetime(2026, 11, 7, 15, tzinfo=timezone.utc))


def test_delivery_uses_real_backlog_contract(tmp_path):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app.api.work_routes import router, get_container
    from backend.app.application.services.work_coordinator import WorkCoordinator

    workspace = tmp_path / "project"
    workspace.mkdir()
    messages = SimpleNamespace(list_workspaces=lambda: [SimpleNamespace(path=str(workspace), name="Project")])
    coordinator = WorkCoordinator(messages, tmp_path / "work.sqlite3")
    app = FastAPI()
    app.dependency_overrides[get_container] = lambda: SimpleNamespace(work_coordinator_service=coordinator)
    app.include_router(router)
    row = {"night": "2026-11-06", "workspace": str(workspace), "result": json.dumps({
        "decision": "task", "summary": "Fix scheduling", "instruction": "Fix the calculation",
        "evidence": ["src/schedule.js:12 uses the wrong date"],
    })}
    with TestClient(app) as client:
        worker = Worker({"projects": []}, tmp_path / "state.sqlite", tmp_path / "report.json", client)
        worker.deliver(row)
        worker.deliver(row)
        tasks = coordinator.overview()["projects"][0]["queue"]
        assert len(tasks) == 1
        assert tasks[0]["status"] == "queued"
        assert "src/schedule.js:12" in tasks[0]["instruction"]
        assert "Falta preparar" in tasks[0]["problem"]


def test_project_can_deliver_to_its_dev_coordinator(tmp_path):
    requests = []
    with httpx.Client(base_url='http://primary', transport=httpx.MockTransport(
        lambda request: (requests.append(request) or httpx.Response(200, json={'id': 'saved'}))
    )) as client:
        worker = Worker({'projects': [{'workspace_path': '/bridge', 'execution_bridge_url': 'http://dev:8118'}]}, tmp_path / 'state.sqlite', tmp_path / 'report.json', client)
        worker.deliver({'night': '2026-11-06', 'workspace': '/bridge', 'result': json.dumps({
            'decision': 'task', 'summary': 'Fix viewer', 'instruction': 'Validate malformed paths', 'evidence': ['viewer.py:12']})})
    assert requests[0].url.host == 'dev'
    assert requests[0].url.port == 8118
    assert requests[0].url.path == '/work/backlog'


def test_dev_execution_setting_controls_dev_owned_project(tmp_path):
    def respond(request):
        if request.url.path == '/work/settings':
            return httpx.Response(200, json={'projects': [{'workspace_path': '/bridge', 'settings': {'automatic_execution': request.url.host == 'dev'}}]})
        return httpx.Response(200, json={'projects': []})
    with httpx.Client(base_url='http://primary', transport=httpx.MockTransport(respond)) as client:
        worker = Worker({'enabled': True, 'projects': [{'name': 'Bridge', 'workspace_path': '/bridge', 'execution_bridge_url': 'http://dev:8118'}]}, tmp_path / 'state.sqlite', tmp_path / 'report.json', client)
        started = []
        worker.start = lambda *args: started.append(args)
        worker.tick(datetime(2026, 11, 7, 3, tzinfo=timezone.utc))
        assert len(started) == 1
