"""Interactive selection adapter through the real local API, isolated model and data."""

import json
import sqlite3
from pathlib import Path

import pytest
from test_message_flow import build_session_client, wait_for_job
from test_whatsapp_video import LocalAPIBridge
from services.whatsapp_ingest.worker import WorkerSettings, WhatsAppIntakeWorker
from services.whatsapp_ingest.interactive import tick


@pytest.mark.parametrize("channel", ["whatsapp", "bridge"])
def test_interactive_request_to_real_api_reply_and_restart(
    tmp_path, monkeypatch, channel
):
    monkeypatch.setenv("PIPELINE_QUALITY_DATABASE", str(tmp_path / "quality.sqlite3"))
    monkeypatch.setenv("PIPELINE_QUALITY_JEV_ENABLED", "false")
    data, projects = tmp_path / "data", tmp_path / "projects"
    workspace = projects / "example"
    workspace.mkdir(parents=True)
    root = data / "interactive"
    (root / "requests").mkdir(parents=True)
    (root / "config.json").write_text(json.dumps({"enabled": True, "databases": []}))
    record = data / "inbox" / "direct-bruno" / "date" / "one"
    record.mkdir(parents=True)
    (record / "message.json").write_text(
        json.dumps(
            {
                "message_id": "one",
                "kind": "text",
                "text": "Hola prueba",
                "source": "whatsapp-direct",
                "group_id": "private",
                "whatsapp_timestamp": "2026-10-26T12:00:00Z",
            }
        )
    )
    request = root / "requests" / "request.json"
    request.write_text(
        json.dumps(
            {
                "id": "request",
                "status": "queued",
                "records": [str(record.relative_to(data))],
                "channel": channel,
                "project": "example",
                "cli": False,
            }
        )
    )
    with build_session_client(
        projects_root=str(projects), codex_workdir=str(Path.cwd())
    ) as client:
        bridge = LocalAPIBridge(client)
        worker = WhatsAppIntakeWorker(
            WorkerSettings(data_dir=data, projects_root=projects),
            bridge=bridge,
            direct_cli_bridge=bridge,
        )
        tick(worker)
        state = json.loads(request.read_text())
        assert state["status"] in {"running", "finished"}
        job = wait_for_job(client, state["job_id"])
        assert job["status"] == "completed"
        tick(worker)
        state = json.loads(request.read_text())
        assert state["status"] == "finished" and state["reply"]
        session = client.get("/sessions/" + state["session_id"]).json()
        assert session["agent_profile_id"] == "whatsapp_intake_planner"
        assert session["agent_profile_color"] == "#25D366"
        prompt = next(
            a["prompt"]
            for a in session["agent_configuration"]["agents"]
            if a["agent_id"] == "generator"
        )
        if channel == "bridge":
            assert "WhatsApp" not in prompt and "ejecución" in prompt
        else:
            assert "charla" in prompt
        before = len(client.get("/sessions").json())
        # Completed requests are not submitted again, including after an adapter restart.
        tick(
            WhatsAppIntakeWorker(
                worker.settings, bridge=bridge, direct_cli_bridge=bridge
            )
        )
        assert len(client.get("/sessions").json()) == before
        assert worker._ready_record_directories() == []
        catalog = json.loads((root / "catalog.json").read_text())
        assert [p["slug"] for p in catalog["projects"]] == ["example"]


def test_catalog_reads_only_execution_metadata_and_orders_all_projects(tmp_path):
    from types import SimpleNamespace

    root = tmp_path / "interactive"
    root.mkdir()
    projects = tmp_path / "projects"
    projects.mkdir()
    for name in ["old", "recent", "never"]:
        (projects / name).mkdir()
    db = tmp_path / "metadata.sqlite3"
    with sqlite3.connect(db) as c:
        c.executescript(
            "CREATE TABLE sessions(id TEXT,workspace_path TEXT); CREATE TABLE jobs(session_id TEXT,status TEXT,completed_at TEXT,updated_at TEXT,created_at TEXT);"
        )
        for name, stamp in [("old", "2026-10-01"), ("recent", "2026-10-26")]:
            c.execute("INSERT INTO sessions VALUES (?,?)", (name, str(projects / name)))
            c.execute(
                "INSERT INTO jobs VALUES (?,?,?,?,?)",
                (name, "completed", stamp, stamp, stamp),
            )
    (root / "config.json").write_text(
        json.dumps({"enabled": True, "databases": [str(db)]})
    )

    class Client:
        def _request(self, _):
            return [{"name": p.name, "path": str(p)} for p in projects.iterdir()]

    tick(
        SimpleNamespace(
            settings=SimpleNamespace(data_dir=tmp_path, projects_root=projects),
            bridge=Client(),
        )
    )
    assert [
        p["slug"] for p in json.loads((root / "catalog.json").read_text())["projects"]
    ] == ["recent", "old", "never"]
