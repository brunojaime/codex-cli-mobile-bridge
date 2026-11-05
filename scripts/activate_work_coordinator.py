"""Activate hash-pinned Bridge additions only after accepted work is fully idle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import httpx


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)


def activate(name, plan, state, report):
    runtime, stage = Path(plan["runtime"]), Path(plan["stage"])
    port = 8118 if name == "dev" else 8000
    command = (
        ["systemctl", "--user", "restart", "codex-mobile-bridge-dev.service"]
        if name == "dev"
        else [
            "sudo",
            "-n",
            "systemctl",
            "restart",
            "codex-mobile-bridge-backend.service",
        ]
    )
    with httpx.Client(
        base_url=f"http://127.0.0.1:{port}", timeout=90, trust_env=False
    ) as client:
        status = client.get("/maintenance/drain").raise_for_status().json()
        state[name] = {
            "state": "waiting_for_idle",
            "active_jobs": status["active_job_count"],
            "in_flight_messages": status["in_flight_message_count"],
        }
        atomic(report, state)
        if (
            status["requested"]
            or status["active_job_count"]
            or status["in_flight_message_count"]
            or status["active_session_count"]
        ):
            return False
        # Pin all sources BEFORE admitting a restart. Never overwrite a concurrent fix.
        for relative, hashes in plan["files"].items():
            if (
                digest(stage / relative) != hashes["after_sha256"]
                or digest(runtime / relative) != hashes["before_sha256"]
            ):
                state[name] = {
                    "state": "blocked_runtime_or_candidate_changed",
                    "file": relative,
                }
                atomic(report, state)
                return True
        owned_drain = False
        try:
            status = (
                client.post("/maintenance/drain", json={"requested": True})
                .raise_for_status()
                .json()
            )
            owned_drain = True
            if not status["ready_to_restart"]:
                return False
            backup = stage.parent / "originals" / name
            backup.mkdir(parents=True, exist_ok=True, mode=0o700)
            for relative, hashes in plan["files"].items():
                destination = runtime / relative
                if destination.exists():
                    saved = backup / relative
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    saved.write_bytes(destination.read_bytes())
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_suffix(".activation-tmp")
                temporary.write_bytes((stage / relative).read_bytes())
                temporary.chmod(0o644)
                temporary.replace(destination)
            state[name] = {"state": "restarting_idle_backend"}
            atomic(report, state)
            subprocess.run(command, check=True, timeout=90, capture_output=True)
            for _ in range(60):
                try:
                    response = client.get("/openapi.json")
                    if response.is_success and "/work" in response.json().get(
                        "paths", {}
                    ):
                        health = client.get("/health").raise_for_status().json()
                        state[name] = {
                            "state": "active",
                            "routes_loaded": True,
                            "health_ok": health.get("status") == "ok",
                            "files_verified": all(
                                digest(runtime / f) == h["after_sha256"]
                                for f, h in plan["files"].items()
                            ),
                        }
                        atomic(report, state)
                        return True
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            raise RuntimeError("new_backend_not_healthy")
        except Exception as exc:
            state[name] = {
                "state": "activation_failed_requires_inspection",
                "error_type": type(exc).__name__,
            }
            atomic(report, state)
            return True
        finally:
            if owned_drain:
                try:
                    client.post(
                        "/maintenance/drain", json={"requested": False}
                    ).raise_for_status()
                except httpx.HTTPError:
                    state[name] = {**state.get(name, {}), "drain_cleanup_pending": True}
                    atomic(report, state)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    plans = json.loads(args.plan.read_text())
    guard = Path(__file__).resolve().parent / "environment_guard.py"
    for target in plans:
        subprocess.run(
            [
                sys.executable,
                str(guard),
                "--operation",
                "work-coordinator-activation",
                "--target-environment",
                target,
                "--action",
                "deploy",
            ],
            check=True,
            capture_output=True,
        )
    state = {name: {"state": "prepared_waiting_for_idle"} for name in plans}
    atomic(args.report, state)
    pending = list(plans)
    while pending:
        for name in list(pending):
            try:
                if activate(name, plans[name], state, args.report):
                    pending.remove(name)
            except httpx.HTTPError:
                state[name] = {"state": "waiting_for_backend_connection"}
                atomic(args.report, state)
        if pending:
            time.sleep(15)  # OS sleep; no model calls or tokens.
    return int(any(s.get("state") != "active" for s in state.values()))


if __name__ == "__main__":
    raise SystemExit(main())
