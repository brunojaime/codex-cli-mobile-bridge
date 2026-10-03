#!/usr/bin/env python3
"""Execute isolated launch and UI checks; no LLM, deployment or live jobs."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/generator-reviewer-launch"
REPORT.mkdir(parents=True, exist_ok=True)


def execute(name, argv, cwd=ROOT):
    try:
        result = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, timeout=360
        )
        (REPORT / (name + ".log")).write_text(result.stdout + "\n" + result.stderr)
        print(f"{name}: exit={result.returncode}", flush=True)
        return result.returncode == 0, result.stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        (REPORT / (name + ".log")).write_text(type(exc).__name__)
        print(f"{name}: {type(exc).__name__}", flush=True)
        return False, ""


def main():
    junit = REPORT / "backend.xml"
    junit.unlink(missing_ok=True)
    backend_ok, _ = execute(
        "backend-checks",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_generator_reviewer_launch.py",
            "-q",
            "--disable-warnings",
            f"--junitxml={junit}",
        ],
    )
    cases = list(ET.parse(junit).iter("testcase")) if junit.exists() else []

    def backend_group(prefix):
        matches = [c for c in cases if c.attrib.get("name", "").startswith(prefix)]
        return bool(matches) and all(len(c) == 0 for c in matches)

    flutter = shutil.which("flutter")
    frontend_ok, output = execute(
        "frontend-checks",
        [
            flutter or "flutter",
            "test",
            "--no-pub",
            "test/internal_chat_link_test.dart",
            "test/slash_command_palette_test.dart",
            "test/slash_command_model_test.dart",
            "--reporter=json",
        ],
        ROOT / "frontend/mobile_app",
    )
    names = {}
    results = {}
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "testStart":
            names[event["test"]["id"]] = event["test"]["name"]
        if event.get("type") == "testDone":
            results[event["testID"]] = event.get(
                "result"
            ) == "success" and not event.get("skipped", False)

    def frontend_group(fragment):
        selected = [id for id, name in names.items() if fragment in name]
        return bool(selected) and all(results.get(id, False) for id in selected)

    validator = (
        Path.home() / ".codex/skills/.system/skill-creator/scripts/quick_validate.py"
    )
    skill_ok, _ = execute(
        "skill-check",
        [sys.executable, str(validator), str(ROOT / "codex-skills/generator-reviewer")],
    )
    observations = {
        "free-prompts": backend_group("test_free_prompts_") and skill_ok,
        "launch": backend_group("test_free_prompts_and_launch_")
        and backend_group("test_launch_"),
        "turn-budgets": backend_group("test_turn_budgets_"),
        "idempotency": backend_group("test_idempotency_"),
        "slash": frontend_group("ejecutar inserts"),
        "chat-link": frontend_group("chat link navigates")
        and frontend_group("internal links accept"),
        "evidence": backend_ok and frontend_ok and skill_ok,
    }
    summary = {
        "target": "isolated local backend (SQLite + controlled provider), MCP stdio, Flutter test",
        "backend_cases": len(cases),
        "frontend_cases": len(results),
        "model_calls": 0,
        "observations": observations,
    }
    (REPORT / "executed-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("NIENFOS_OBSERVATIONS_V1 " + json.dumps({"observations": observations}))
    return 0 if all(observations.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
