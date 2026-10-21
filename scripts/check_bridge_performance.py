#!/usr/bin/env python3
"""Execute local performance/regression checks; no network service or model calls."""

import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/bridge-performance-20261010"


def main():
    OUT.mkdir(exist_ok=True)
    backend = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_bridge_performance.py",
            "tests/test_current_run_execution.py",
            "tests/test_reviewer_status.py",
            "tests/test_conversation_product.py",
            "-q",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    (OUT / "backend-check.txt").write_text(backend.stdout + backend.stderr)
    files = [
        "bridge_performance_test",
        "chat_controller_latency_test",
        "rich_message_content_test",
        "message_tables_test",
        "chat_controller_streaming_response_test",
        "chat_controller_notification_test",
        "chat_controller_active_job_summary_test",
        "chat_controller_reviewer_state_test",
        "chat_controller_run_history_test",
        "chat_transcript_lazy_loading_test",
        "chat_screen_refresh_test",
        "api_client_test",
    ]
    flutter = subprocess.run(
        [
            shutil.which("flutter") or "flutter",
            "test",
            "--no-pub",
            *["test/" + f + ".dart" for f in files],
            "--reporter=json",
        ],
        cwd=ROOT / "frontend/mobile_app",
        capture_output=True,
        text=True,
        timeout=360,
    )
    (OUT / "flutter-check.jsonl").write_text(flutter.stdout + flutter.stderr)
    names, outcomes = {}, {}
    for line in flutter.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "testStart":
            names[event["test"]["id"]] = event["test"]["name"]
        if event.get("type") == "testDone":
            outcomes[event["testID"]] = event.get(
                "result"
            ) == "success" and not event.get("skipped", False)

    def group(prefix):
        ids = [i for i, n in names.items() if n.startswith(prefix)]
        return bool(ids) and all(outcomes.get(i, False) for i in ids)

    tests = [
        i
        for i in outcomes
        if not names.get(i, "").startswith("loading ")
        and not names.get(i, "").endswith(("(setUpAll)", "(tearDownAll)"))
    ]
    facts = {
        "flow-audit": backend.returncode == 0
        and group("compact:")
        and group("refresh:")
        and group("render:"),
        "compact-sessions": backend.returncode == 0 and group("compact:"),
        "refresh-efficiency": group("refresh:") and group("send:") and group("switch:"),
        "render-efficiency": group("render:") and flutter.returncode == 0,
        "executed-evidence": backend.returncode == 0 and flutter.returncode == 0,
    }
    summary = {
        "target": "Local SQLite/API and Flutter widget tests; not installed APK",
        "backend_exit": backend.returncode,
        "flutter_exit": flutter.returncode,
        "flutter_tests": len(tests),
        "flutter_passed": sum(outcomes[i] for i in tests),
        "failed_tests": [names[i] for i in tests if not outcomes[i]],
        "observations": facts,
    }
    (OUT / "executed-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(summary, ensure_ascii=False))
    print("NIENFOS_OBSERVATIONS_V1 " + json.dumps({"observations": facts}))
    return 0 if all(facts.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
