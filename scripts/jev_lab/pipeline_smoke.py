#!/usr/bin/env python3
"""Real runner + optional real Jev, using only an isolated synthetic defect.

The repair is predetermined, not performed by an autonomous coding model. This
checks integration and provenance; it does not measure developer productivity.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.app.application.services.pipeline_quality_service import (
    PipelineQualityService,
)
from backend.app.application.services.jev_advisor import JevAdvisor
from backend.app.infrastructure.config.settings import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--live-jev",
        action="store_true",
        help="At most two model calls with synthetic failures",
    )
    args = parser.parse_args()
    settings = Settings()
    if args.live_jev and not settings.open_router_api_key:
        raise SystemExit("Configure OPEN_ROUTER_API_KEY in Secrets first.")
    with tempfile.TemporaryDirectory(prefix="nienfos-pipeline-smoke-") as temporary:
        base = Path(temporary)
        root = base / "sample"
        root.mkdir()
        (root / "storage.py").write_text("def reload_value():\n    return 1\n")
        (root / "check.py").write_text(
            "from storage import reload_value\nassert reload_value() == 2, 'expected persisted value 2, observed 1'\n"
        )
        (root / ".gitignore").write_text("__pycache__/\n")
        for argv in (
            ["init", "-q"],
            ["add", "."],
            [
                "-c",
                "user.name=Pipeline Lab",
                "-c",
                "user.email=lab@example.invalid",
                "commit",
                "-qm",
                "baseline",
            ],
        ):
            subprocess.run(
                ["git", "-C", str(root), *argv], check=True, capture_output=True
            )
        advisor = JevAdvisor(
            api_key=settings.open_router_api_key.get_secret_value()
            if settings.open_router_api_key
            else None,
            enabled=args.live_jev,
            timeout=5,
            model=settings.pipeline_quality_jev_model,
        )
        service = PipelineQualityService(
            database_path=base / "ledger.sqlite", allowed_roots=[base], advisor=advisor
        )
        contract = {
            "version": 1,
            "project_id": "synthetic-storage",
            "environment": "local",
            "component_ids": ["synthetic-storage"],
            "criteria": [
                {
                    "id": "persistence",
                    "description": "Read returns stored value 2",
                    "check_ids": ["reload"],
                    "feedback_item_id": "lab-feedback-1",
                }
            ],
            "checks": [
                {
                    "id": "reload",
                    "argv": [sys.executable, "-B", "check.py"],
                    "timeout_seconds": 10,
                }
            ],
        }
        packet = service.register(
            workspace=str(root), work_item_id="synthetic-repair", contract=contract
        )
        first = service.execute(packet["id"], attempt_key="fail-1")
        second = service.execute(packet["id"], attempt_key="fail-2")
        assert not first["quality"]["verified"] and second["diagnosis"]["stalled"]
        (root / "storage.py").write_text("def reload_value():\n    return 2\n")
        fixed = service.execute(packet["id"], attempt_key="fixed")
        assert fixed["quality"]["verified"]
        lesson = service.save_lesson(
            packet_id=packet["id"],
            failed_receipt_id=second["receipt_ids"][0],
            passed_receipt_id=fixed["receipt_ids"][0],
            symptom="Wrong value after reload",
            cause_hypothesis="Incorrect stored value",
            resolution="Return correct stored value",
            conditions="Synthetic storage fixture; do not apply to real apps without reproduction",
        )
        service.close(packet["id"])
        exported = service.gestion_payload(
            packet["id"], "20000000-0000-4000-8000-000000000001"
        )
        (root / "storage.py").write_text("def reload_value():\n    return 3\n")
        assert not service.status(packet["id"])["verified"]
        stale_export = service.gestion_payload(packet["id"], exported["projectId"])
        assert (
            stale_export["sequence"] > exported["sequence"]
            and not stale_export["observation"]["verified"]
        )
        advice = [first["diagnosis"]["advice"], second["diagnosis"]["advice"]]
        output = {
            "scope": "Synthetic integration check; predetermined repair, not an autonomous productivity benchmark",
            "checks": {
                "failure_recorded": True,
                "repeated_failure_detected": True,
                "repair_verified": True,
                "verified_lesson_created": lesson["status"] == "verified_repair",
                "changed_source_invalidated": True,
                "gestion_sequence_advanced": True,
            },
            "jev_enabled": args.live_jev,
            "advice": advice,
            "reported_cost": sum(x.get("cost") or 0 for x in advice),
            "receipts": [
                {
                    "id": r["id"],
                    "status": r["status"],
                    "exit_code": r.get("exit_code"),
                    "source": r["source"],
                    "duration_ms": r["duration_ms"],
                }
                for r in service._list("receipt", packet["id"])
            ],
            "gestion_payload_for_isolated_test_only": exported,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "checks_passed": len(output["checks"]),
                    "advice_status": [x["status"] for x in advice],
                    "reported_cost": output["reported_cost"],
                }
            )
        )


if __name__ == "__main__":
    main()
