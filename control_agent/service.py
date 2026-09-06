from __future__ import annotations

import json
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from control_agent.config import ControlSettings, EnvironmentConfig


RestartMode = Literal["graceful", "force"]
CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_command_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(
            command,
            127,
            stdout="",
            stderr=str(exc),
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            command,
            124,
            stdout=exc.stdout or "",
            stderr=exc.stderr or f"Command timed out: {command[0]}",
        )


@dataclass
class RestartAction:
    id: str
    environment: str
    mode: RestartMode
    status: Literal["queued", "running", "completed", "failed"] = "queued"
    stage: str = "queued"
    detail: str = "Restart queued."
    created_at: str = ""
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "environment": self.environment,
            "mode": self.mode,
            "status": self.status,
            "stage": self.stage,
            "detail": self.detail,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ControlService:
    def __init__(
        self,
        settings: ControlSettings,
        *,
        command_runner: CommandRunner = default_command_runner,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self._environments = {item.name: item for item in settings.environments}
        self._command_runner = command_runner
        self._sleeper = sleeper
        self._actions: dict[str, RestartAction] = {}
        self._active_action_by_environment: dict[str, str] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=max(2, len(settings.environments)),
            thread_name_prefix="control-restart",
        )

    def environment(self, name: str) -> EnvironmentConfig:
        try:
            return self._environments[name]
        except KeyError as exc:
            raise KeyError(f"Unknown environment: {name}") from exc

    def list_environment_statuses(self) -> list[dict[str, Any]]:
        return [self.environment_status(item) for item in self.settings.environments]

    def environment_status(self, environment: EnvironmentConfig) -> dict[str, Any]:
        unit = self._systemd_status(environment.service_name)
        backend_health, backend_error = self._request_json(
            "GET", f"{environment.backend_url}/health"
        )
        drain, drain_error = self._request_json(
            "GET", f"{environment.backend_url}/maintenance/drain"
        )
        active_action = self._active_action(environment.name)
        return {
            "name": environment.name,
            "display_name": environment.display_name,
            "service_name": environment.service_name,
            "backend_url": environment.backend_url,
            "service": unit,
            "backend_reachable": backend_health is not None,
            "backend_health": backend_health,
            "backend_error": backend_error,
            "active_job_count": (drain or {}).get("active_job_count"),
            "active_jobs": (drain or {}).get("active_jobs", []),
            "active_session_count": (drain or {}).get("active_session_count"),
            "in_flight_message_count": (drain or {}).get(
                "in_flight_message_count"
            ),
            "drain_requested": (drain or {}).get("requested"),
            "drain_error": drain_error,
            "active_action": active_action.as_dict() if active_action else None,
            "observed_at": utc_now(),
        }

    def codex_status(self) -> dict[str, Any]:
        version = self._command_runner([self.settings.codex_command, "--version"])
        if version.returncode != 0:
            return {
                "available": False,
                "authenticated": False,
                "version": None,
                "detail": (version.stderr or version.stdout).strip()
                or "codex --version failed",
            }
        login = self._command_runner(
            [self.settings.codex_command, "login", "status"]
        )
        return {
            "available": True,
            "authenticated": login.returncode == 0,
            "version": version.stdout.strip(),
            "detail": (login.stdout or login.stderr).strip(),
        }

    def submit_restart(self, environment_name: str, mode: RestartMode) -> RestartAction:
        environment = self.environment(environment_name)
        now = utc_now()
        with self._lock:
            existing = self._active_action(environment.name)
            if existing:
                raise RuntimeError(
                    f"A restart is already {existing.status} for {environment.name}."
                )
            action = RestartAction(
                id=str(uuid.uuid4()),
                environment=environment.name,
                mode=mode,
                created_at=now,
                updated_at=now,
            )
            self._actions[action.id] = action
            self._active_action_by_environment[environment.name] = action.id
            self._executor.submit(self._run_restart, action.id, environment)
            return RestartAction(**action.__dict__)

    def action(self, action_id: str) -> RestartAction:
        with self._lock:
            try:
                return RestartAction(**self._actions[action_id].__dict__)
            except KeyError as exc:
                raise KeyError(f"Unknown action: {action_id}") from exc

    def _active_action(self, environment_name: str) -> RestartAction | None:
        with self._lock:
            action_id = self._active_action_by_environment.get(environment_name)
            if not action_id:
                return None
            action = self._actions.get(action_id)
            if action is None or action.status in {"completed", "failed"}:
                self._active_action_by_environment.pop(environment_name, None)
                return None
            return RestartAction(**action.__dict__)

    def _run_restart(self, action_id: str, environment: EnvironmentConfig) -> None:
        try:
            self._update_action(
                action_id,
                status="running",
                stage="checking_backend",
                detail="Checking backend and active runs.",
            )
            action = self.action(action_id)
            if action.mode == "graceful":
                self._drain_backend(action_id, environment)

            self._update_action(
                action_id,
                status="running",
                stage="restarting_service",
                detail=f"Restarting {environment.service_name}.",
            )
            result = self._command_runner(
                ["systemctl", "--user", "restart", environment.service_name]
            )
            if result.returncode != 0:
                raise RuntimeError(
                    (result.stderr or result.stdout).strip()
                    or f"systemctl failed with exit code {result.returncode}"
                )

            self._wait_until_healthy(action_id, environment)
            self._update_action(
                action_id,
                status="completed",
                stage="healthy",
                detail="Service restarted and backend healthcheck passed.",
            )
        except Exception as exc:  # noqa: BLE001 - action records stable failure details
            self._update_action(
                action_id,
                status="failed",
                stage="failed",
                detail=str(exc),
            )
        finally:
            with self._lock:
                if self._active_action_by_environment.get(environment.name) == action_id:
                    self._active_action_by_environment.pop(environment.name, None)

    def _drain_backend(self, action_id: str, environment: EnvironmentConfig) -> None:
        drain, _error = self._request_json(
            "POST",
            f"{environment.backend_url}/maintenance/drain",
            {"requested": True},
        )
        if drain is None:
            self._update_action(
                action_id,
                status="running",
                stage="backend_unreachable",
                detail="Backend is unreachable; continuing with recovery restart.",
            )
            return

        deadline = time.monotonic() + self.settings.drain_timeout_seconds
        while not bool(drain.get("ready_to_restart")):
            active_count = drain.get("active_job_count", 0)
            self._update_action(
                action_id,
                status="running",
                stage="draining",
                detail=f"Waiting for {active_count} active run(s) to finish.",
            )
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "Timed out waiting for active runs; the service was not restarted."
                )
            self._sleeper(self.settings.poll_seconds)
            drain, error = self._request_json(
                "GET", f"{environment.backend_url}/maintenance/drain"
            )
            if drain is None:
                raise RuntimeError(
                    f"Backend became unreachable while draining: {error or 'unknown error'}"
                )

    def _wait_until_healthy(
        self, action_id: str, environment: EnvironmentConfig
    ) -> None:
        deadline = time.monotonic() + self.settings.restart_timeout_seconds
        last_error = "healthcheck has not completed"
        while time.monotonic() < deadline:
            self._update_action(
                action_id,
                status="running",
                stage="waiting_for_health",
                detail="Waiting for backend healthcheck.",
            )
            health, error = self._request_json(
                "GET", f"{environment.backend_url}/health"
            )
            if health is not None and health.get("status") == "ok":
                return
            last_error = error or f"Unexpected health response: {health}"
            self._sleeper(self.settings.poll_seconds)
        raise RuntimeError(f"Restarted service did not become healthy: {last_error}")

    def _systemd_status(self, service_name: str) -> dict[str, Any]:
        result = self._command_runner(
            [
                "systemctl",
                "--user",
                "show",
                service_name,
                "--no-pager",
                "--property=LoadState,ActiveState,SubState,MainPID,NRestarts,ExecMainStartTimestamp",
            ]
        )
        values: dict[str, str] = {}
        for line in result.stdout.splitlines():
            key, separator, value = line.partition("=")
            if separator:
                values[key] = value
        return {
            "loaded": values.get("LoadState") == "loaded",
            "active_state": values.get("ActiveState", "unknown"),
            "sub_state": values.get("SubState", "unknown"),
            "main_pid": int(values.get("MainPID", "0") or 0),
            "restart_count": int(values.get("NRestarts", "0") or 0),
            "started_at": values.get("ExecMainStartTimestamp") or None,
            "detail": None
            if result.returncode == 0
            else (result.stderr or result.stdout).strip(),
        }

    def _request_json(
        self,
        method: str,
        url: str,
        body: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    return None, "Expected a JSON object."
                return payload, None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return None, str(exc)

    def _update_action(
        self,
        action_id: str,
        *,
        status: Literal["queued", "running", "completed", "failed"],
        stage: str,
        detail: str,
    ) -> None:
        with self._lock:
            action = self._actions[action_id]
            action.status = status
            action.stage = stage
            action.detail = detail
            action.updated_at = utc_now()
