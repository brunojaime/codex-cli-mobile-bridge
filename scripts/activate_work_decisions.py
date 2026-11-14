"""Activate recovery decisions using the existing idle/drain/hash-pinned rollout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import httpx
import activate_nightly_recovery as rollout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    target = plan["targets"]["prod"]
    report = Path(plan["reports"]) / "activation.json"
    # This additive feature must not modify any project's recovery policy.
    rollout.configure_recovery = lambda client: []
    deadline = time.monotonic() + 12 * 3600
    while time.monotonic() < deadline:
        try:
            done = rollout.activate(
                target, Path(plan["stage"]), args.plan.parent, report, allow_prod=True
            )
        except Exception as exc:
            rollout.save(
                report,
                {
                    "state": "activation_requires_inspection",
                    "error_type": type(exc).__name__,
                },
            )
            return 1
        if done:
            result = json.loads(report.read_text())
            if result["state"] != "active":
                return 1
            # The coordinator's normal scheduler backfills existing blocks.
            with httpx.Client(
                base_url=target["bridge_url"], trust_env=False, timeout=60
            ) as client:
                for _ in range(20):
                    overview = client.get("/work").raise_for_status().json()
                    questions = [
                        q for q in overview["questions"] if q.get("source_task_id")
                    ]
                    if questions and all(q.get("notice_sent") for q in questions):
                        break
                    time.sleep(3)
            result.update(
                feature="recovery_decisions",
                questions=[
                    {
                        "id": q["id"],
                        "task_id": q["source_task_id"],
                        "notice_persisted": bool(q.get("notice_sent")),
                    }
                    for q in questions
                ],
                worker=overview.get("worker"),
                physical_phone_receipt_verified=False,
            )
            rollout.save(report, result)
            return 0
        time.sleep(15)
    rollout.save(report, {"state": "accepted_work_did_not_become_idle"})
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
