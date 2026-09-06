from __future__ import annotations

import subprocess
import time

from fastapi.testclient import TestClient

from control_agent.config import ControlSettings, EnvironmentConfig
from control_agent.main import create_app
from control_agent.service import ControlService


def _settings() -> ControlSettings:
    return ControlSettings(
        token="test-token",
        environments=(
            EnvironmentConfig(
                name="prod",
                display_name="Production",
                service_name="codex-mobile-bridge-backend.service",
                backend_url="http://127.0.0.1:8000",
            ),
        ),
        poll_seconds=0.001,
        drain_timeout_seconds=1,
        restart_timeout_seconds=1,
    )


def _completed(command: list[str], stdout: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr="")


def test_control_api_requires_bearer_token() -> None:
    settings = _settings()
    service = ControlService(settings, command_runner=lambda command: _completed(command))
    client = TestClient(create_app(settings, service))

    response = client.get("/health")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_control_token"


def test_environment_status_uses_only_allowlisted_systemd_unit(monkeypatch) -> None:
    settings = _settings()
    commands: list[list[str]] = []

    def run(command: list[str]):
        commands.append(command)
        if command[-1:] == ["--version"]:
            return _completed(command, "codex-cli 1.2.3\n")
        if command[-2:] == ["login", "status"]:
            return _completed(command, "Logged in\n")
        return _completed(
            command,
            "LoadState=loaded\nActiveState=active\nSubState=running\n"
            "MainPID=123\nNRestarts=2\nExecMainStartTimestamp=now\n",
        )

    service = ControlService(settings, command_runner=run)
    monkeypatch.setattr(
        service,
        "_request_json",
        lambda method, url, body=None: (
            ({"status": "ok"}, None)
            if url.endswith("/health")
            else ({"requested": False, "active_job_count": 3}, None)
        ),
    )
    client = TestClient(create_app(settings, service))

    response = client.get(
        "/environments", headers={"Authorization": "Bearer test-token"}
    )

    assert response.status_code == 200
    environment = response.json()["environments"][0]
    assert environment["service"]["active_state"] == "active"
    assert environment["service"]["main_pid"] == 123
    assert environment["active_job_count"] == 3
    assert commands[0][0:4] == [
        "systemctl",
        "--user",
        "show",
        "codex-mobile-bridge-backend.service",
    ]


def test_graceful_restart_drains_then_restarts_and_waits_for_health(monkeypatch) -> None:
    settings = _settings()
    commands: list[list[str]] = []
    requests: list[tuple[str, str, object]] = []

    def run(command: list[str]):
        commands.append(command)
        return _completed(command)

    service = ControlService(settings, command_runner=run, sleeper=lambda _seconds: None)
    drain_reads = iter(
        [
            ({"ready_to_restart": False, "active_job_count": 1}, None),
            ({"ready_to_restart": True, "active_job_count": 0}, None),
        ]
    )

    def request(method: str, url: str, body=None):
        requests.append((method, url, body))
        if url.endswith("/maintenance/drain"):
            return next(drain_reads)
        return {"status": "ok"}, None

    monkeypatch.setattr(service, "_request_json", request)

    action = service.submit_restart("prod", "graceful")
    for _ in range(1000):
        resolved = service.action(action.id)
        if resolved.status in {"completed", "failed"}:
            break
        time.sleep(0.001)
    else:
        raise AssertionError("Restart action did not finish")

    assert resolved.status == "completed"
    assert requests[0] == (
        "POST",
        "http://127.0.0.1:8000/maintenance/drain",
        {"requested": True},
    )
    assert [
        "systemctl",
        "--user",
        "restart",
        "codex-mobile-bridge-backend.service",
    ] in commands


def test_unknown_environment_cannot_select_an_arbitrary_service() -> None:
    settings = _settings()
    service = ControlService(settings, command_runner=lambda command: _completed(command))
    client = TestClient(create_app(settings, service))

    response = client.post(
        "/environments/ssh.service/restart",
        headers={"Authorization": "Bearer test-token"},
        json={"mode": "force"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "unknown_environment"
