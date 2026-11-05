"""Run the coordinator with exclusive ledger ownership without restarting API jobs.

The worker imports its checked-out runtime and reuses the live backend's process
configuration in memory. It does not start API, outbox or global recovery loops.
The ordinary backend scheduler yields on the same worker lock. Claims, task IDs,
settings and receipts stay in the original ledger. Stop this worker only after
its active task/delivery closes, then let a compatible backend resume scheduling.
"""

from __future__ import annotations

import argparse
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-service", required=True)
    parser.add_argument("--bridge-root", type=Path, required=True)
    parser.add_argument("--expected-database", type=Path, required=True)
    parser.add_argument("--policy", type=Path)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    pid = subprocess.check_output(
        [
            "systemctl",
            "--user",
            "show",
            args.backend_service,
            "--property=MainPID",
            "--value",
        ],
        text=True,
    ).strip()
    if not pid.isdecimal() or pid == "0":
        raise RuntimeError("The source backend must be running")
    for item in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"):
        if b"=" in item:
            key, value = item.split(b"=", 1)
            os.environ[key.decode()] = value.decode()
    os.chdir(args.bridge_root)
    sys.path.insert(0, str(source))
    from backend.app.api.work_routes import get_work
    from backend.app.application.services.work_coordinator import WorkPolicy
    from backend.app.container import build_container
    from backend.app.infrastructure.config.settings import Settings

    settings = Settings()
    settings.poll_interval_seconds = 0  # Do not reconcile unrelated sessions.
    service = get_work(build_container(settings))
    if service.database.resolve() != args.expected_database.resolve():
        raise RuntimeError("Refusing a different coordination ledger")
    with service.database.with_suffix(".worker.lock").open("a") as leader:
        fcntl.flock(leader, fcntl.LOCK_EX)
        # Do not replace a policy during an active task. Active tasks also retain
        # their immutable policy snapshots independently of project settings.
        if args.policy:
            policy = WorkPolicy.model_validate_json(args.policy.read_text())
            with service.ledger() as db:
                active = db.execute(
                    "SELECT 1 FROM work_tasks WHERE workspace=? AND status IN ('starting','running','delivering','uncertain')",
                    (policy.workspace_path,),
                ).fetchone()
            if active:
                raise RuntimeError(
                    "An active task must close before changing its procedure"
                )
            service.checkout(policy)
            service.policy(policy)
        while True:
            service._complete_delivery(service._tick_locked())
            time.sleep(5)


if __name__ == "__main__":
    main()
