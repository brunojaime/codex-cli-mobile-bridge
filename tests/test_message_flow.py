from __future__ import annotations

import time

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.infrastructure.config.settings import Settings


def build_test_client() -> TestClient:
    settings = Settings(
        codex_command="python3 tests/fixtures/fake_codex.py",
        codex_use_exec=False,
        projects_root="..",
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
    )
    app = create_app(settings)
    return TestClient(app)


def build_session_client() -> TestClient:
    settings = Settings(
        codex_command="python3 tests/fixtures/fake_codex_session.py",
        codex_use_exec=True,
        projects_root="..",
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
    )
    app = create_app(settings)
    return TestClient(app)


def wait_for_job(client: TestClient, job_id: str, *, timeout_seconds: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout_seconds
    payload: dict | None = None

    while time.monotonic() < deadline:
        response = client.get(f"/response/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.05)

    raise AssertionError(f"Job {job_id} did not finish in time: {payload}")


def test_message_flow_returns_completed_response() -> None:
    client = build_test_client()

    create_response = client.post("/message", json={"message": "hello from test"})

    assert create_response.status_code == 202
    job_id = create_response.json()["job_id"]

    payload = wait_for_job(client, job_id)

    assert payload["status"] == "completed"
    assert payload["response"] == "Codex response: hello from test"


def test_message_flow_returns_failed_response() -> None:
    client = build_test_client()

    create_response = client.post("/message", json={"message": "fail:boom"})

    assert create_response.status_code == 202
    job_id = create_response.json()["job_id"]

    payload = wait_for_job(client, job_id)

    assert payload["status"] == "failed"
    assert payload["error"] == "boom"


def test_session_message_flow_reuses_provider_session() -> None:
    client = build_session_client()

    first_response = client.post("/message", json={"message": "first prompt"})
    assert first_response.status_code == 202
    first_job = wait_for_job(client, first_response.json()["job_id"])

    session_id = first_job["session_id"]
    session_detail = client.get(f"/sessions/{session_id}")
    assert session_detail.status_code == 200
    provider_session_id = session_detail.json()["provider_session_id"]
    assert provider_session_id is not None
    assert session_detail.json()["messages"][1]["content"].startswith("new:")

    second_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "second prompt"},
    )
    assert second_response.status_code == 202

    second_job = wait_for_job(client, second_response.json()["job_id"])
    assert second_job["provider_session_id"] == provider_session_id

    updated_session = client.get(f"/sessions/{session_id}")
    payload = updated_session.json()
    assert payload["provider_session_id"] == provider_session_id
    assert len(payload["messages"]) == 4
    assert payload["messages"][3]["content"] == f"resume:{provider_session_id}:second prompt"

    sessions_response = client.get("/sessions")
    assert sessions_response.status_code == 200
    sessions = sessions_response.json()
    assert len(sessions) == 1
    assert sessions[0]["id"] == session_id


def test_workspaces_endpoint_and_session_workspace_binding() -> None:
    client = build_session_client()

    workspaces_response = client.get("/workspaces")
    assert workspaces_response.status_code == 200
    workspaces = workspaces_response.json()
    assert any(workspace["name"] == "cli-codex-project" for workspace in workspaces)

    target_workspace = next(
        workspace for workspace in workspaces if workspace["name"] == "cli-codex-project"
    )
    create_response = client.post(
        "/sessions",
        json={"title": "Fixtures chat", "workspace_path": target_workspace["path"]},
    )
    assert create_response.status_code == 201
    payload = create_response.json()
    assert payload["workspace_name"] == "cli-codex-project"
    assert payload["workspace_path"] == target_workspace["path"]
