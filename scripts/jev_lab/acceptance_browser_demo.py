#!/usr/bin/env python3
"""Real local browser/SQLite failure and repair; at most one optional live Jev call.

Uses synthetic data and a predetermined repair, not an autonomous implementation
or a deployment. Reports contain no credentials, customer data or ledger copies.
"""
# ruff: noqa: E402 -- standalone entry point sets the repository import path.

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.app.application.services.pipeline_quality_service import (
    PipelineQualityService,
)
from backend.app.application.services.jev_advisor import JevAdvisor
from backend.app.infrastructure.config.settings import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live-jev", action="store_true")
    parser.add_argument("--node", default=shutil.which("node"))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    settings = Settings()
    version = subprocess.check_output([args.node, "--version"], text=True).strip()
    if int(version.lstrip("v").split(".")[0]) < 20:
        raise SystemExit("Pass --node with an installed Node >=20 for Playwright")
    calls = []

    def simulated(payload):
        calls.append(payload)
        return {
            "model": "simulated-for-control-flow",
            "answers": {
                "fulfillment": {
                    "type": "choice",
                    "choice": "fulfilled",
                    "probabilities": {
                        "fulfilled": 1,
                        "partial": 0,
                        "not_fulfilled": 0,
                        "insufficient_evidence": 0,
                    },
                }
            },
        }

    if args.live_jev and not settings.open_router_api_key:
        raise SystemExit("OPEN_ROUTER_API_KEY must be configured through Secrets")
    advisor = JevAdvisor(
        enabled=True,
        api_key=settings.open_router_api_key.get_secret_value()
        if args.live_jev
        else None,
        model=settings.pipeline_quality_jev_model,
        timeout=8,
        transport=None if args.live_jev else simulated,
    )
    with tempfile.TemporaryDirectory(prefix="acceptance-browser-") as directory:
        base = Path(directory)
        app = base / "application"
        app.mkdir()
        for name in ("acceptance_browser_server.py", "acceptance_browser_probe.mjs"):
            shutil.copy2(ROOT / "tests/fixtures" / name, app / name)
        (app / ".gitignore").write_text(".runtime/\n__pycache__/\n")
        (app / "listing.py").write_text("def list_clients(stored):\n    return []\n")
        for arguments in (
            ["init", "-q"],
            ["add", "."],
            [
                "-c",
                "user.name=Acceptance Lab",
                "-c",
                "user.email=lab@example.invalid",
                "commit",
                "-qm",
                "failing local fixture",
            ],
        ):
            subprocess.run(
                ["git", "-C", str(app), *arguments], check=True, capture_output=True
            )
        env = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "LANG"}}
        server = subprocess.Popen(
            [sys.executable, "-B", "acceptance_browser_server.py"],
            cwd=app,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 5
            while not (app / ".runtime/port").exists():
                if server.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Local fixture did not start")
                time.sleep(0.05)
            s = PipelineQualityService(
                database_path=base / "ledger.sqlite",
                allowed_roots=[app],
                advisor=advisor,
            )
            original = "El cliente creado debe persistir y aparecer al volver a la cartera y después de recargar."
            s.chat_intake_context(
                workspace=app, source_ref="local-browser-demonstration", text=original
            )
            source = s.requirement_sources(app)[0]
            descriptions = {
                "persisted": "Saved client can be read by its ID",
                "return_visible": "Saved client is visible on returning to the list",
                "reload_visible": "Saved client remains visible after page reload",
                "same_release": "The same application build is observed at the beginning and end of the test",
            }
            req = s.requirement_from_source(
                source["id"],
                {
                    "requirement_id": "LOCAL-CLIENT",
                    "project_id": "acceptance-lab",
                    "environment": "local",
                    "criteria": [
                        {"id": k, "description": v} for k, v in descriptions.items()
                    ],
                },
            )
            contract = {
                "project_id": "acceptance-lab",
                "environment": "local",
                "criteria": [
                    {
                        "id": k,
                        "description": v,
                        "feedback_item_id": req["feedback_item_id"],
                        "check_ids": ["browser"],
                    }
                    for k, v in descriptions.items()
                ],
                "checks": [
                    {
                        "id": "browser",
                        "argv": [
                            args.node,
                            "acceptance_browser_probe.mjs",
                            str(
                                ROOT
                                / "packages/codex-developer-feedback-web/node_modules/playwright/index.mjs"
                            ),
                            str(output),
                        ],
                        "timeout_seconds": 60,
                    }
                ],
            }
            packet = s.register(
                workspace=app, work_item_id="browser-client", contract=contract
            )
            s.bind_feedback_plan(
                req["id"],
                {
                    "packet_id": packet["id"],
                    "request_digest": req["request_digest"],
                    "scope": "local",
                    "semantic_brief": "A created client must persist, appear when returning to the list and remain visible after reloading. Verify against one consistent application build.",
                    "observations": [
                        {
                            "id": k,
                            "criterion_id": k,
                            "check_id": "browser",
                            "description": v,
                        }
                        for k, v in descriptions.items()
                    ],
                },
            )
            before = s.execute(packet["id"], attempt_key="before-repair")
            if before["quality"]["verified"]:
                raise RuntimeError(
                    "Deliberately broken fixture was incorrectly accepted"
                )
            facts = {
                o["id"]: o["passed"]
                for o in before["feedback_validation"][0]["observations"]
            }
            if facts != {
                "persisted": True,
                "return_visible": False,
                "reload_visible": False,
                "same_release": True,
            }:
                print(
                    json.dumps(
                        [
                            r.get("output_excerpt")
                            for r in before["quality"]["current_receipts"]
                        ]
                    )
                )
                raise RuntimeError(
                    "Browser did not reproduce the intended visibility defect"
                )
            (app / "listing.py").write_text(
                "def list_clients(stored):\n    return stored\n"
            )
            after = s.execute(packet["id"], attempt_key="after-repair")
            if not after["quality"]["verified"]:
                print(
                    json.dumps(
                        {
                            "blockers": after["quality"]["blockers"],
                            "runner": [
                                r.get("output_excerpt")
                                for r in after["quality"]["current_receipts"]
                            ],
                        }
                    )
                )
                raise RuntimeError("Repaired fixture did not pass the browser test")
            result = {
                "fixture": "Local browser and SQLite; not Gestion DEV",
                "repair": "Predetermined change to list_clients",
                "live_jev": args.live_jev,
                "before": before["feedback_validation"][0],
                "after": after["feedback_validation"][0],
                "screenshots": ["fallo.png", "corregido.png"],
                "manual_confirmation": "Not performed by Bruno; pending",
                "max_live_calls": 1 if args.live_jev else 0,
            }
            (output / "resultado.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            )
            print(
                json.dumps(
                    {
                        "before": result["before"]["verdict"],
                        "after": result["after"]["verdict"],
                        "technical_tests_passed_after": True,
                        "jev": result["after"]["advice"],
                        "output": str(output),
                    },
                    ensure_ascii=False,
                )
            )
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == "__main__":
    main()
