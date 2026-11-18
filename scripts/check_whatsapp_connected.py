#!/usr/bin/env python3
"""Record tests and minimized observations from the enabled real intake."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen

root = Path(__file__).resolve().parents[1]
folder = root / "reports/whatsapp-connected-20261026"
folder.mkdir(exist_ok=True, parents=True)
env = {
    **os.environ,
    "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}",
    "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{os.getuid()}/bus",
}


def pid(unit):
    return subprocess.check_output(
        ["systemctl", "--user", "show", unit, "-p", "MainPID", "--value"],
        text=True,
        env=env,
    ).strip()


def get(url):
    with urlopen(url, timeout=15) as response:
        return json.load(response)


node = str(Path(f"/proc/{pid('nienfos-whatsapp-ingest.service')}/exe").resolve())
results = []
for name, argv in [
    (
        "node-tests.txt",
        [
            node,
            "--test",
            *map(
                str, sorted((root / "services/whatsapp_ingest/test").glob("*.test.mjs"))
            ),
        ],
    ),
    (
        "python-tests.txt",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_whatsapp_connected.py",
            "tests/test_whatsapp_modes.py",
            "tests/test_whatsapp_intake_worker.py",
            "tests/test_whatsapp_video.py",
            "-q",
        ],
    ),
]:
    result = subprocess.run(argv, cwd=root, capture_output=True, text=True)
    (folder / name).write_text(result.stdout + result.stderr)
    results.append(result.returncode == 0)
state_root = root / ".data/whatsapp_ingest/interactive"
catalog = json.loads((state_root / "catalog.json").read_text())
observations = {}
if all(results):
    observations.update({"native-selection-tests": True, "isolation-tests": True})
health = get("http://127.0.0.1:8787/health")
receipts = []
for name, base in [
    ("smoke-ref.json", "http://127.0.0.1:8118"),
    ("bridge-smoke-ref.json", "http://127.0.0.1:8000"),
]:
    rid = json.loads((folder / name).read_text())["id"]
    state = json.loads((state_root / "requests" / f"{rid}.json").read_text())
    session = get(base + "/sessions/" + state["session_id"])
    job = get(base + "/response/" + state["job_id"])
    prompt = next(
        a["prompt"]
        for a in session["agent_configuration"]["agents"]
        if a["agent_id"] == "generator"
    )
    expected = (
        "Conexión WhatsApp con Codex confirmada."
        if state["channel"] == "whatsapp"
        else "Canal Bridge conectado."
    )
    reply_ok = job["status"] == "completed" and expected in (job.get("response") or "")
    mode_ok = (
        "charla" in prompt
        if state["channel"] == "whatsapp"
        else ("ejecución" in prompt and "WhatsApp" not in prompt)
    )
    color_ok = (
        session["agent_profile_id"] == "whatsapp_intake_planner"
        and session["agent_profile_color"] == "#25D366"
    )
    delivery_ok = state["status"] == "delivered" and (
        bool(state.get("delivery_ids"))
        if state["channel"] == "whatsapp"
        else not state.get("delivery_ids")
    )
    receipts.append(
        {
            "origin": "operator-smoke",
            "channel": state["channel"],
            "session_id": session["id"],
            "job_id": state["job_id"],
            "backend_target": "Bridge DEV" if base.endswith(":8118") else "Bridge habitual",
            "completed": reply_ok,
            "mode_correct": mode_ok,
            "origin_color_metadata": color_ok,
            "delivery_correct": delivery_ok,
            "delivery_ids": state.get("delivery_ids", []),
            "response_sha256": hashlib.sha256(
                (job.get("response") or "").encode()
            ).hexdigest(),
        }
    )
    observations["real-" + state["channel"]] = bool(
        reply_ok and mode_ok and color_ok and delivery_ok
    )
connected = (
    health.get("connection") == "connected"
    and int(pid("nienfos-whatsapp-intake-worker.service")) > 0
)
if connected and catalog["projects"]:
    observations["activated"] = True
# Full native interaction needs the user's new vote, rather than operator-created smoke input.
dialog_path = state_root / "dialog.json"
dialog = json.loads(dialog_path.read_text()) if dialog_path.exists() else {}
if dialog.get("polls"):
    requests = [
        json.loads(p.read_text()) for p in (state_root / "requests").glob("*.json")
    ]
    done = next(
        (
            r
            for r in requests
            if r.get("origin") != "operator-smoke" and r.get("status") == "delivered"
        ),
        None,
    )
    if done:
        observations["human-native-roundtrip"] = True
(folder / "live-receipt.json").write_text(
    json.dumps(
        {
            "connected": connected,
            "project_count": len(catalog["projects"]),
            "catalog_updated_at": catalog["updated_at"],
            "smoke_requests": receipts,
            "new_native_roundtrip": observations.get(
                "human-native-roundtrip", "pending"
            ),
            "human_receipt": "pending",
        },
        ensure_ascii=False,
        indent=2,
    )
)
print("NIENFOS_OBSERVATIONS_V1 " + json.dumps({"observations": observations}))
raise SystemExit(
    0
    if all(results)
    and connected
    and all(
        r["delivery_correct"] and r["completed"] and r["mode_correct"] for r in receipts
    )
    else 1
)
