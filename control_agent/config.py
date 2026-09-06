from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class EnvironmentConfig:
    name: str
    display_name: str
    service_name: str
    backend_url: str


@dataclass(frozen=True)
class ControlSettings:
    token: str
    environments: tuple[EnvironmentConfig, ...]
    host: str = "0.0.0.0"
    port: int = 8010
    drain_timeout_seconds: int = 3600
    restart_timeout_seconds: int = 90
    poll_seconds: float = 2.0
    codex_command: str = "codex"

    @classmethod
    def from_env(cls) -> "ControlSettings":
        token = os.getenv("CONTROL_TOKEN", "").strip()
        if not token:
            raise RuntimeError(
                "CONTROL_TOKEN is required; the control API will not start without authentication."
            )
        return cls(
            token=token,
            environments=_parse_environments(
                os.getenv("CONTROL_ENVIRONMENTS_JSON", "")
            ),
            host=os.getenv("CONTROL_HOST", "0.0.0.0"),
            port=int(os.getenv("CONTROL_PORT", "8010")),
            drain_timeout_seconds=int(
                os.getenv("CONTROL_DRAIN_TIMEOUT_SECONDS", "3600")
            ),
            restart_timeout_seconds=int(
                os.getenv("CONTROL_RESTART_TIMEOUT_SECONDS", "90")
            ),
            poll_seconds=float(os.getenv("CONTROL_POLL_SECONDS", "2")),
            codex_command=os.getenv("CONTROL_CODEX_COMMAND", "codex"),
        )


def _parse_environments(raw: str) -> tuple[EnvironmentConfig, ...]:
    if not raw.strip():
        return (
            EnvironmentConfig(
                name="prod",
                display_name="Production",
                service_name="codex-mobile-bridge-backend.service",
                backend_url="http://127.0.0.1:8000",
            ),
            EnvironmentConfig(
                name="dev",
                display_name="Development",
                service_name="codex-mobile-bridge-dev.service",
                backend_url="http://127.0.0.1:8001",
            ),
        )

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("CONTROL_ENVIRONMENTS_JSON must be valid JSON.") from exc
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("CONTROL_ENVIRONMENTS_JSON must be a non-empty list.")

    environments: list[EnvironmentConfig] = []
    names: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            raise RuntimeError("Every control environment must be a JSON object.")
        environment = EnvironmentConfig(
            name=str(item.get("name", "")).strip(),
            display_name=str(item.get("display_name", "")).strip(),
            service_name=str(item.get("service_name", "")).strip(),
            backend_url=str(item.get("backend_url", "")).strip().rstrip("/"),
        )
        _validate_environment(environment)
        if environment.name in names:
            raise RuntimeError(f"Duplicate control environment: {environment.name}")
        names.add(environment.name)
        environments.append(environment)
    return tuple(environments)


def _validate_environment(environment: EnvironmentConfig) -> None:
    if not environment.name or not environment.name.replace("-", "").isalnum():
        raise RuntimeError("Environment names may only contain letters, numbers, and dashes.")
    if not environment.display_name:
        raise RuntimeError(f"Environment {environment.name} needs a display_name.")
    if not environment.service_name.startswith("codex-mobile-bridge-"):
        raise RuntimeError(
            f"Environment {environment.name} has a service outside the allowlist prefix."
        )
    if not environment.service_name.endswith(".service"):
        raise RuntimeError(f"Environment {environment.name} needs a .service unit.")
    if not environment.backend_url.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise RuntimeError(
            f"Environment {environment.name} backend_url must target localhost."
        )
