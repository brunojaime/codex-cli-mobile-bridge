import json
import socket
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api import relevo_routes


def _client(tmp_path, monkeypatch, script_body: str) -> TestClient:
    hosts = {"hosts": {
        "lenovo": {"match_hostnames": [socket.gethostname()], "bridges": ["http://x"]},
        "batata": {"match_hostnames": ["batata"], "bridges": ["http://b"]},
        "mac": {"enabled": False, "match_hostnames": [], "bridges": []},
    }}
    hosts_path = tmp_path / "hosts.json"
    hosts_path.write_text(json.dumps(hosts))
    script = tmp_path / "fake_relevo.py"
    script.write_text(script_body)
    monkeypatch.setenv("RELEVO_HOSTS_FILE", str(hosts_path))
    monkeypatch.setenv("RELEVO_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(relevo_routes, "SCRIPT", script)
    app = FastAPI()
    app.include_router(relevo_routes.router)
    return TestClient(app)


SLOW = """import sys, time, json
assert sys.argv[1:] == ["ir", "batata", "--todo"], sys.argv
print("Cerrando 2 chat(s) activos por steering", file=sys.stderr, flush=True)
time.sleep(1.5)
print(json.dumps({"proyectos": [{"proyecto": "/p/app", "estado": "en batata: ok", "chat_destino": "abc"}]}))
"""


def _wait_done(client, run_id, limit=10):
    end = time.time() + limit
    while time.time() < end:
        view = client.get(f"/relevo/runs/{run_id}").json()
        if view["status"] != "running":
            return view
        time.sleep(0.2)
    raise AssertionError("no terminó")


def test_destinations_exclude_self_and_flag_disabled(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, SLOW)
    items = {d["name"]: d["enabled"] for d in client.get("/relevo/destinations").json()["destinations"]}
    assert items == {"batata": True, "mac": False}


def test_single_flight_progress_and_result(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, SLOW)
    first = client.post("/relevo/runs", json={"destination": "batata"})
    assert first.status_code == 202 and first.json()["already_running"] is False
    second = client.post("/relevo/runs", json={"destination": "batata"}).json()
    assert second["already_running"] is True and second["id"] == first.json()["id"]
    time.sleep(0.5)
    running = client.get("/relevo/runs/latest").json()
    assert running["status"] == "running"
    assert any("Cerrando 2 chat" in line for line in running["progress"])
    done = _wait_done(client, first.json()["id"])
    assert done["status"] == "finished" and done["exit_code"] == 0
    assert done["projects"][0]["chat_destino"] == "abc"
    # terminado el anterior, un nuevo pedido inicia otra ejecución
    third = client.post("/relevo/runs", json={"destination": "batata"}).json()
    assert third["already_running"] is False and third["id"] != first.json()["id"]
    _wait_done(client, third["id"])


def test_failure_and_disabled_destination(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, "import sys\nprint('No llego al Bridge de batata', file=sys.stderr)\nsys.exit(1)\n")
    assert client.post("/relevo/runs", json={"destination": "mac"}).status_code == 400
    run = client.post("/relevo/runs", json={"destination": "batata"}).json()
    done = _wait_done(client, run["id"])
    assert done["status"] == "failed" and "No llego" in done["error"]
    assert client.get("/relevo/runs/nada").status_code == 404
