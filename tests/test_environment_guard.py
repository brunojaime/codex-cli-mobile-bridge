from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.environment_guard import decide


SCRIPT = Path("scripts/environment_guard.py")


def test_environment_guard_allows_same_environment() -> None:
    decision = decide(current_environment="dev", target_environment="dev")

    assert decision.allowed is True
    assert decision.reason == "same_environment_allowed"


def test_environment_guard_blocks_dev_to_prod() -> None:
    decision = decide(current_environment="dev", target_environment="prod")

    assert decision.allowed is False
    assert decision.reason == "environment_boundary_violation"


def test_environment_guard_blocks_prod_to_dev() -> None:
    decision = decide(current_environment="prod", target_environment="dev")

    assert decision.allowed is False
    assert decision.reason == "environment_boundary_violation"


def test_environment_guard_allows_control_orchestration() -> None:
    decision = decide(current_environment="control", target_environment="prod")

    assert decision.allowed is True
    assert decision.reason == "control_environment_allowed"


def test_environment_guard_cli_writes_denied_audit(tmp_path: Path) -> None:
    audit_log = tmp_path / "environment_guard.jsonl"

    result = subprocess.run(
        [
            ".venv/bin/python",
            str(SCRIPT),
            "--operation",
            "report-update",
            "--current-environment",
            "dev",
            "--target-environment",
            "prod",
            "--action",
            "write",
            "--audit-log",
            str(audit_log),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 3
    payload = json.loads(result.stdout)
    assert payload["allowed"] is False
    assert payload["reason"] == "environment_boundary_violation"

    events = [json.loads(line) for line in audit_log.read_text().splitlines()]
    assert len(events) == 1
    assert events[0]["operation"] == "report-update"
    assert events[0]["current_environment"] == "dev"
    assert events[0]["target_environment"] == "prod"
    assert events[0]["allowed"] is False
