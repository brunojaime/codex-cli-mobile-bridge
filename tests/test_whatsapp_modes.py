from datetime import datetime, timezone
from dataclasses import replace
from types import SimpleNamespace
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.whatsapp_ingest.worker import (
    BridgeClient,
    CHANNEL_PROFILES,
    PLANNER_PROFILE_COLOR,
    PreparedRecord,
    WhatsAppIntakeWorker,
    WorkerSettings,
    SUBMISSION_FILENAME,
    validate_response_channel,
)
from backend.app.application.services.workspace_execution_order import (
    workspaces_by_execution,
)


def test_selected_profiles_have_distinct_prompts_and_same_origin_color(
    tmp_path, monkeypatch
):
    client = BridgeClient("http://bridge.invalid")
    calls = []

    def request(path, **kwargs):
        calls.append((path, kwargs))
        if path == "/agent-profiles":
            return []
        return {
            "id": "new-session",
            "agent_configuration": {
                "agents": [{"agent_id": "generator", "prompt": "legacy"}]
            },
        }

    monkeypatch.setattr(client, "_request", request)
    for channel in CHANNEL_PROFILES:
        assert (
            client.create_channel_session(
                channel=channel, title="WhatsApp · Project", workspace_path=tmp_path
            )
            == "new-session"
        )
    profiles = [
        c[1]["payload"]["profiles"][0]
        for c in calls
        if c[0] == "/agent-profiles/import"
    ]
    assert len(profiles) == 1
    assert profiles[0]["color_hex"] == PLANNER_PROFILE_COLOR
    created = [c[1]["payload"] for c in calls if c[0] == "/sessions"]
    assert all(c["agent_profile_id"] == "whatsapp_intake_planner" for c in created)
    prompts = [
        c[1]["payload"]["agents"][0]["prompt"]
        for c in calls
        if c[0].endswith("/agents")
    ]
    assert len(prompts) == 2
    assert "charla" in prompts[0]
    execution = prompts[1]
    assert "WhatsApp" not in execution and "Esperando aprobación" not in execution
    assert "ejecución" in execution and "verificá" in execution
    assert all("Sólo un mensaje humano posterior" not in p for p in prompts)


@pytest.mark.parametrize("channel", ["bridge", "whatsapp"])
def test_channel_dispatch_preserves_content_attachments_mode_and_session(
    tmp_path, channel
):
    workspace = tmp_path / "projects" / "project"
    workspace.mkdir(parents=True)
    record_dir = tmp_path / "record"
    record_dir.mkdir()
    image = record_dir / "image.png"
    image.write_bytes(b"synthetic-image")

    class Client:
        def __init__(self):
            self.sessions = []
            self.messages = []

        def create_channel_session(self, **kwargs):
            self.sessions.append(kwargs)
            return "channel-session"

        def submit_standard(self, **kwargs):
            self.messages.append(kwargs)
            return {"job_id": "job"}

    bridge, dev = Client(), Client()
    worker = WhatsAppIntakeWorker(
        settings=WorkerSettings(
            data_dir=tmp_path / "data", projects_root=workspace.parent
        ),
        bridge=bridge,
        direct_cli_bridge=dev,
    )
    record = PreparedRecord(
        path=record_dir,
        project="project",
        workspace=workspace,
        group_id="private",
        group_subject="test",
        message_id="one",
        received_at="",
        participant_id=None,
        push_name=None,
        kind="image",
        content="Implementá el pedido",
        media_path=image,
        source="whatsapp-direct",
        delivery_mode="triage",
        direct_batch_id="batch",
        ready_mtime=0,
        response_channel=channel,
    )
    worker._process_group([record])
    assert bridge.sessions[0]["channel"] == channel
    assert bridge.messages[0]["prompt"] == "Implementá el pedido"
    assert bridge.messages[0]["attachment_paths"] == [image]
    assert not dev.messages
    submission = json.loads((record_dir / SUBMISSION_FILENAME).read_text())
    assert submission["response_channel"] == channel
    worker._process_channel_batch([record])
    assert len(bridge.sessions) == 1  # persisted session reused after a retry
    with pytest.raises(RuntimeError, match="mixes response"):
        worker._process_group(
            [
                record,
                replace(
                    record,
                    response_channel="whatsapp" if channel == "bridge" else "bridge",
                ),
            ]
        )
    with pytest.raises(RuntimeError, match="conflicting response"):
        worker._process_channel_batch(
            [
                replace(
                    record,
                    response_channel="whatsapp" if channel == "bridge" else "bridge",
                )
            ]
        )
    record_cli = replace(record, delivery_mode="direct_cli")
    # A fresh record keeps the CLI backend separate.
    second = tmp_path / "second"
    second.mkdir()
    worker._process_group([replace(record_cli, path=second)])
    assert len(dev.sessions) == 1


def test_channel_validation():
    assert validate_response_channel(None) is None
    assert validate_response_channel("bridge") == "bridge"
    with pytest.raises(ValueError):
        validate_response_channel("both")


def test_project_recency_uses_runs_not_session_or_folder_modification():
    def dt(n):
        return datetime(2026, 10, n, tzinfo=timezone.utc)

    workspaces = [
        SimpleNamespace(name=n, path=f"/projects/{n}") for n in ["A", "Z", "B", "Never"]
    ]
    sessions = [
        SimpleNamespace(id=n, workspace_path=f"/projects/{n}", updated_at=dt(26))
        for n in ["A", "Z", "B", "Unknown"]
    ]

    def job(session, n, status="completed"):
        return SimpleNamespace(
            session_id=session,
            status=status,
            completed_at=None,
            updated_at=dt(n),
            created_at=dt(1),
        )

    ordered = workspaces_by_execution(
        workspaces,
        sessions,
        [
            job("A", 2),
            job("Z", 25),
            job("B", 20),
            job("A", 26, "pending"),
            job("Unknown", 26),
        ],
    )
    assert [w.name for w, _ in ordered] == ["Z", "B", "A", "Never"]
    assert ordered[-1][1] is None
    assert [w.name for w, _ in workspaces_by_execution(workspaces, [], [])] == [
        "A",
        "B",
        "Never",
        "Z",
    ]


def test_ordered_catalog_endpoint_and_client(tmp_path, monkeypatch):
    from backend.app.api.routes import router, get_message_service

    workspaces = [SimpleNamespace(name=n, path=str(tmp_path / n)) for n in ["A", "Z"]]
    service = SimpleNamespace(
        list_workspaces=lambda: workspaces,
        list_sessions=lambda: [
            SimpleNamespace(id="s", workspace_path=str(tmp_path / "Z"))
        ],
        list_summary_jobs=lambda: [
            SimpleNamespace(
                session_id="s",
                status="running",
                completed_at=None,
                updated_at=datetime(2026, 10, 26, tzinfo=timezone.utc),
                created_at=None,
            )
        ],
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_message_service] = lambda: service
    with TestClient(app) as http:
        response = http.get("/workspaces?order=last_execution")
        assert response.status_code == 200
        assert [v["name"] for v in response.json()] == ["Z", "A"]
        assert response.json()[0]["last_execution_at"] is not None
        assert [v["name"] for v in http.get("/workspaces").json()] == ["A", "Z"]
        assert http.get("/workspaces?order=invalid").status_code == 422
        client = BridgeClient("http://bridge.invalid")
        monkeypatch.setattr(client, "_request", lambda path: http.get(path).json())
        assert [v["name"] for v in client.list_recent_projects()] == ["Z", "A"]


def test_selected_mode_propagates_to_whole_private_batch(tmp_path):
    data = tmp_path / "data"
    projects = tmp_path / "projects"
    (projects / "project").mkdir(parents=True)
    entries = []
    for i, channel in enumerate(["bridge", None]):
        record = data / "inbox" / "direct-bruno" / "date" / str(i)
        record.mkdir(parents=True)
        manifest = {
            "kind": "text",
            "text": "Proyecto: project" if i == 0 else "Contenido adicional",
            "message_id": str(i),
            "response_channel": channel,
        }
        (record / "message.json").write_text(json.dumps(manifest))
        entries.append((i, record, manifest))
    worker = WhatsAppIntakeWorker(
        settings=WorkerSettings(data_dir=data, projects_root=projects)
    )
    worker._route_direct_batch(entries)
    manifests = [
        json.loads(p.read_text())
        for p in (data / "inbox" / "project").glob("*/*/message.json")
    ]
    assert len(manifests) == 2
    assert {m["response_channel"] for m in manifests} == {"bridge"}


def test_whatsapp_backlog_records_durable_receipt_without_opening_chat(tmp_path):
    from services.whatsapp_ingest.interactive import enqueue_backlog
    inbox = tmp_path / 'inbox' / 'request'
    inbox.mkdir(parents=True)
    (inbox / 'message.json').write_text(json.dumps({'id': 'original'}))
    workspace = tmp_path / 'projects' / 'lab'
    workspace.mkdir(parents=True)
    calls = []
    class Client:
        def _request(self, path, **kwargs):
            calls.append((path, kwargs))
            return {'id': 'durable-task', 'status': 'queued'}
    worker = SimpleNamespace(settings=SimpleNamespace(data_dir=tmp_path), bridge=Client(), _prepare_record=lambda _: SimpleNamespace(kind='text', content='Cambiar título', media_path=None, workspace=workspace))
    state = {'id': 'request-id', 'records': ['inbox/request'], 'project': 'lab'}
    target = tmp_path / 'state.json'
    enqueue_backlog(worker, state, target, {})
    assert state['status'] == 'finished'
    assert state['backlog_id'] == 'durable-task'
    assert not (inbox / 'READY').exists()
    assert len(calls) == 1
    assert calls[0][0] == '/work/backlog'
    assert calls[0][1]['payload']['source'] == 'whatsapp'
    assert calls[0][1]['payload']['source_key'] == 'request-id'
    enqueue_backlog(worker, state, target, {})
    assert calls[0][1]['payload'] == calls[1][1]['payload']
