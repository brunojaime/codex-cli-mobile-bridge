"""Activate a hash-pinned recovery candidate after all accepted work finishes."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

import httpx


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def save(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def ready(status):
    return not status["requested"] and not any(status[k] for k in (
        "active_job_count", "active_session_count", "in_flight_message_count"))


def configure_recovery(client):
    """Extend existing policies without creating projects or changing preferences."""
    overview = client.get("/work").raise_for_status().json()
    changed = []
    for project in overview["projects"]:
        policy = project.get("policy")
        if not policy:
            continue
        policy = {**policy, "automatic_recovery": True,
                  "max_recoveries_per_task": 3, "recovery_delay_seconds": 120}
        client.put("/work/policy", json=policy).raise_for_status()
        changed.append({"name": project["name"], "enabled": policy["enabled"]})
    return changed


def activate(target, stage, state_root, report, *, allow_prod=False, client=None, run=subprocess.run):
    name = target["environment"]
    if name not in {"dev", "prod"}:
        raise ValueError("Unknown coordinator environment")
    if name == "prod" and not allow_prod:
        save(report, {"state": "prepared_requires_prod_restart_authorization", "environment": name})
        return True
    own_client = client is None
    client = client or httpx.Client(base_url=target["bridge_url"], timeout=30, trust_env=False)
    runtime = Path(target["runtime"])
    owned_drain = False
    worker_lock = None

    def pins_valid():
        return all(sha(stage / f) == h["after"] and sha(runtime / f) == h["before"]
                   for f, h in target["files"].items())

    try:
        status = client.get("/maintenance/drain").raise_for_status().json()
        if not ready(status):
            save(report, {"state": "waiting_for_accepted_work", "environment": name,
                          "active_jobs": status["active_job_count"],
                          "active_sessions": status["active_session_count"],
                          "pending_messages": status["in_flight_message_count"]})
            return False
        if name == "prod":
            worker_lock = Path(target["coordinator_database"]).with_suffix(".worker.lock").open("a")
            try:
                fcntl.flock(worker_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                save(report, {"state": "waiting_for_coordinator_pass", "environment": name})
                return False
            work = client.get("/work").raise_for_status().json()
            if any(p.get("active") for p in work["projects"]):
                save(report, {"state": "waiting_for_claimed_work", "environment": name})
                return False
        if not pins_valid():
            save(report, {"state": "blocked_candidate_or_runtime_changed", "environment": name})
            return True
        status = client.post("/maintenance/drain", json={"requested": True}).raise_for_status().json()
        owned_drain = True
        if not status["ready_to_restart"]:
            return False
        # Recheck under the admission barrier; no concurrent patch is overwritten.
        if not pins_valid():
            save(report, {"state": "blocked_candidate_or_runtime_changed", "environment": name})
            return True
        for relative in target["files"]:
            destination = runtime / relative
            if destination.exists():
                backup = state_root / "originals" / name / relative
                backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                if not backup.exists():
                    backup.write_bytes(destination.read_bytes())
                    backup.chmod(0o600)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(".recovery-tmp")
            temporary.write_bytes((stage / relative).read_bytes())
            temporary.chmod(0o644)
            temporary.replace(destination)
        save(report, {"state": "restarting_idle_coordinator", "environment": name})
        command = (["sudo", "-n", "systemctl", "restart", "codex-mobile-bridge-backend.service"]
                   if name == "prod" else ["systemctl", "--user", "restart", "codex-mobile-bridge-dev.service"])
        run(command, check=True, timeout=90, capture_output=True)
        for _ in range(45):
            try:
                health = client.get("/health").raise_for_status().json()
                schema = client.get("/openapi.json").raise_for_status().json()
                loaded = "automatic_recovery" in schema["components"]["schemas"]["WorkPolicy"]["properties"]
                if health.get("status") == "ok" and loaded:
                    configured = configure_recovery(client) if name == "prod" else []
                    save(report, {"state": "active", "environment": name,
                                  "health_verified": True, "recovery_schema_loaded": True,
                                  "recovery_policies": configured,
                                  "files_verified": all(sha(runtime / f) == h["after"] for f, h in target["files"].items())})
                    return True
            except (httpx.HTTPError, KeyError):
                pass
            time.sleep(1)
        raise RuntimeError("Recovery candidate did not become healthy")
    finally:
        if owned_drain:
            try:
                client.post("/maintenance/drain", json={"requested": False}).raise_for_status()
            except httpx.HTTPError:
                save(report, {"state": "drain_release_requires_inspection", "environment": name})
        if own_client:
            client.close()
        if worker_lock:
            worker_lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--environment", choices=["dev", "prod"], required=True)
    parser.add_argument("--allow-prod-coordinator-restart", action="store_true")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    target = plan["targets"][args.environment]
    report = Path(plan["reports"]) / (args.environment + "-activation.json")
    deadline = time.monotonic() + 12 * 3600
    while time.monotonic() < deadline:
        try:
            if activate(target, Path(plan["stage"]), args.plan.parent, report,
                        allow_prod=args.allow_prod_coordinator_restart):
                return int(json.loads(report.read_text())["state"] != "active")
        except Exception as exc:
            save(report, {"state": "activation_requires_inspection", "error_type": type(exc).__name__})
            return 1
        time.sleep(15)
    save(report, {"state": "accepted_work_did_not_become_idle", "environment": args.environment})
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
