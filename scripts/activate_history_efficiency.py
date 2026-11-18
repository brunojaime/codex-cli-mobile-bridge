#!/usr/bin/env python3
"""Activate a reviewed history release only when both shared-source backends idle.

Never kills a working conversation. Uses the existing systemd Restart=always
policy after SIGTERM, and refuses unknown processes, drift, or incomplete drain.
No databases, environment files, credentials or installed APKs are replaced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import time
import urllib.request

ENVIRONMENTS = {
    "dev": (
        8118,
        "codex-mobile-bridge-dev.service",
        True,
        ".run/dev-backend-8118/data/chat_store.sqlite3",
    ),
    "prod": (
        8000,
        "codex-mobile-bridge-backend.service",
        False,
        ".data/chat_store.sqlite3",
    ),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def fully_idle(status, *, drained=False):
    counts = ("active_job_count", "active_session_count", "in_flight_message_count")
    lists = (
        "active_jobs",
        "active_session_ids",
        "in_flight_message_ids",
        "active_agent_run_ids",
        "pending_follow_up_message_ids",
        "unknown_blockers",
        "sdd_codex_job_ids",
        "project_factory_job_ids",
        "domain_factory_job_ids",
    )
    return (
        all(status.get(key) == 0 for key in counts)
        and all(status.get(key) == [] for key in lists)
        and (
            not drained
            or (
                status.get("requested") is True
                and status.get("ready_to_restart") is True
            )
        )
    )


def request(port, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.load(response)


def service_pid(name):
    _, unit, user, _ = ENVIRONMENTS[name]
    cmd = [
        "systemctl",
        *(["--user"] if user else []),
        "show",
        unit,
        "-p",
        "MainPID",
        "--value",
    ]
    return int(subprocess.check_output(cmd, text=True).strip())


def verify_process(name, root):
    pid = service_pid(name)
    if pid <= 1:
        raise RuntimeError(f"{name}: no running service")
    proc = Path("/proc") / str(pid)
    if (proc / "cwd").resolve() != root:
        raise RuntimeError(f"{name}: unexpected working directory")
    cmd = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode()
    if str(root / "main.py") not in cmd:
        raise RuntimeError(f"{name}: unexpected process command")
    if ENVIRONMENTS[name][1] not in (proc / "cgroup").read_text():
        raise RuntimeError(f"{name}: unexpected service owner")
    health = request(ENVIRONMENTS[name][0], "/health")
    if health.get("environment_identity", {}).get("environment") != name:
        raise RuntimeError(f"{name}: unexpected environment identity")
    return pid


def database_has_jobs(root, name):
    path = root / ENVIRONMENTS[name][3]
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        return (
            connection.execute(
                "SELECT count(*) FROM jobs WHERE status NOT IN ('completed','failed','cancelled')"
            ).fetchone()[0]
            != 0
        )


def verify_files(root, release, manifest):
    for relative, expected in manifest["baseline"].items():
        if digest(root / relative) != expected:
            raise RuntimeError(f"Source changed since validation: {relative}")
    for relative, expected in manifest["files"].items():
        if digest(release / relative) != expected:
            raise RuntimeError(f"Release file changed: {relative}")


def atomic_copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".history-new")
    temporary.write_bytes(source.read_bytes())
    temporary.chmod(source.stat().st_mode & 0o777)
    os.replace(temporary, destination)


def install_files(root, release, report, files):
    installed = []
    try:
        for relative in files:
            existed = (root / relative).is_file()
            if existed:
                atomic_copy(root / relative, report / "rollback" / relative)
            installed.append((relative, existed))
            atomic_copy(release / relative, root / relative)
    except Exception:
        # No backend has restarted at this point. Undo a partial file install.
        for relative, existed in reversed(installed):
            if existed:
                atomic_copy(report / "rollback" / relative, root / relative)
            else:
                (root / relative).unlink(missing_ok=True)
        raise


def activate(manifest_path, wait_seconds=86400):
    manifest = json.loads(manifest_path.read_text())
    root = Path(manifest["root"]).resolve()
    release = Path(manifest["release"]).resolve()
    report = manifest_path.parent
    owned_drains = set()

    def record(status, **facts):
        data = {"status": status, "at": time.time(), **facts}
        (report / "activation.json").write_text(json.dumps(data, indent=2))
        print(json.dumps(data), flush=True)

    try:
        verify_files(root, release, manifest)
        for name in ENVIRONMENTS:
            subprocess.run(
                [
                    str(release / ".venv/bin/python"),
                    str(release / "scripts/environment_guard.py"),
                    "--current-environment",
                    "control",
                    "--target-environment",
                    name,
                    "--operation",
                    "activate-history-efficiency",
                    "--action",
                    "deploy",
                    "--audit-log",
                    str(report / "environment-audit.jsonl"),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
        deadline = time.monotonic() + wait_seconds
        record("waiting_for_idle", environments=list(ENVIRONMENTS))
        while time.monotonic() < deadline:
            # Cheap read-only check; don't repeatedly reconcile running agents.
            if any(database_has_jobs(root, name) for name in ENVIRONMENTS):
                time.sleep(30)
                continue
            pids = {name: verify_process(name, root) for name in ENVIRONMENTS}
            statuses = {
                name: request(values[0], "/maintenance/drain")
                for name, values in ENVIRONMENTS.items()
            }
            if any(status["requested"] for status in statuses.values()):
                raise RuntimeError(
                    "Another operator owns an existing maintenance drain"
                )
            if not all(fully_idle(status) for status in statuses.values()):
                time.sleep(30)
                continue
            ready = True
            for name, values in ENVIRONMENTS.items():
                owned_drains.add(name)
                status = request(values[0], "/maintenance/drain", {"requested": True})
                ready = ready and fully_idle(status, drained=True)
            if ready:
                break
            for name in list(owned_drains):
                request(
                    ENVIRONMENTS[name][0], "/maintenance/drain", {"requested": False}
                )
                owned_drains.remove(name)
            time.sleep(30)
        else:
            record("pending_active_conversations")
            return 2
        verify_files(root, release, manifest)
        for name in ENVIRONMENTS:
            if verify_process(name, root) != pids[name]:
                raise RuntimeError("Service changed during preflight")
        record("installing", pids_before=pids, active_jobs_at_drain=0)
        install_files(root, release, report, manifest["files"])
        for name, values in ENVIRONMENTS.items():
            if verify_process(name, root) != pids[name]:
                raise RuntimeError(f"{name}: process changed before restart")
            if not fully_idle(request(values[0], "/maintenance/drain"), drained=True):
                raise RuntimeError(f"{name}: no longer safe to restart")
            record("restarting", environment=name, pid_before=pids[name])
            os.kill(pids[name], signal.SIGTERM)
            for _ in range(90):
                time.sleep(2)
                try:
                    if service_pid(name) == pids[name]:
                        continue
                    health = request(values[0], "/health")
                    if (
                        health.get("environment_identity", {}).get("environment")
                        != name
                    ):
                        continue
                    if not health.get("features", {}).get("session_pagination_v1"):
                        continue
                    page = request(values[0], "/sessions/page?limit=1")
                    if (
                        not isinstance(page.get("items"), list)
                        or len(page["items"]) > 1
                    ):
                        continue
                    request(values[0], "/maintenance/drain", {"requested": False})
                    owned_drains.discard(name)
                    record(
                        "backend_verified",
                        environment=name,
                        pid_after=service_pid(name),
                    )
                    break
                except (OSError, ValueError):
                    continue
            else:
                raise RuntimeError(
                    f"{name}: restart not verified; no forced shutdown attempted"
                )
        # Publish only the validated build, after both APIs are available.
        if manifest.get("web"):
            web = root / "frontend/mobile_app/build/web"
            prepared = Path(manifest["web"])
            if digest(prepared / "main.dart.js") != manifest["web_sha256"]:
                raise RuntimeError("Web artifact changed")
            import shutil

            next_web = web.with_name("web-history-next")
            if next_web.exists():
                raise RuntimeError("Unexpected existing web staging directory")
            shutil.copytree(prepared, next_web)
            if web.exists():
                os.replace(web, report / "rollback-web")
            os.replace(next_web, web)
        record(
            "activated",
            pids_after={name: service_pid(name) for name in ENVIRONMENTS},
            rollback=str(report / "rollback"),
            web_published=bool(manifest.get("web")),
        )
        return 0
    except Exception as exc:
        record("stopped_safely", error=str(exc))
        return 1
    finally:
        for name in owned_drains:
            try:
                request(
                    ENVIRONMENTS[name][0], "/maintenance/drain", {"requested": False}
                )
            except Exception:
                print(f"Could not clear owned drain: {name}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--wait-seconds", type=int, default=86400)
    args = parser.parse_args()
    raise SystemExit(activate(args.manifest, args.wait_seconds))
