"""Activate the prepared meeting route after current DEV chats finish."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.relevamientos.core import atomic  # noqa: E402

FILES = (
    "backend/app/main.py", "backend/app/api/meeting_intake_routes.py",
    "backend/app/application/services/meeting_intake_service.py",
)


def stage(runtime):
    """Only add this feature; refuse to replace unrelated runtime changes."""
    local_main = (ROOT / FILES[0]).read_text()
    old_main = local_main.replace(
        "from backend.app.api.meeting_intake_routes import router as meeting_intake_router\n", ""
    ).replace("    app.include_router(meeting_intake_router)\n", "").replace(
        '    app.include_router(meeting_intake_router, prefix="/api/v1")\n', ""
    )
    if (runtime / FILES[0]).read_text() not in {local_main, old_main}:
        raise ValueError("runtime_main_has_unrelated_changes")
    for relative in FILES[1:]:
        target, source = runtime / relative, ROOT / relative
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise ValueError("runtime_module_already_has_different_content")
    for relative in FILES:
        source, target = ROOT / relative, runtime / relative
        if source.resolve() != target.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(".py.meeting-tmp")
            temporary.write_bytes(source.read_bytes())
            os.chmod(temporary, 0o644)
            temporary.replace(target)
    return {relative: hashlib.sha256((runtime / relative).read_bytes()).hexdigest() for relative in FILES}


def main():
    os.umask(0o077)
    load_dotenv(ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=ROOT)
    parser.add_argument("--stage-only", action="store_true")
    args = parser.parse_args()
    runtime = args.runtime_root.resolve()
    hashes = stage(runtime)
    output = ROOT / ".data/relevamientos-inbox/activation.json"
    api = os.environ.get("RELEVAMIENTOS_BRIDGE_URL", "http://127.0.0.1:8118").rstrip("/")

    def record(state, **facts):
        value = {"state": state, "updated_at": time.time(), "source_sha256": hashes, **facts}
        atomic(output, value)
        atomic(ROOT / "reports/relevamientos-automaticos/activacion.json", value)

    record("staged_waiting_for_idle_backend")
    if args.stage_only:
        return 0
    client = httpx.Client(base_url=api, timeout=15)
    requested = False
    try:
        deadline = time.monotonic() + 7200
        while time.monotonic() < deadline:
            if any(hashlib.sha256((runtime / f).read_bytes()).hexdigest() != h for f, h in hashes.items()):
                record("blocked_runtime_source_changed")
                return 1
            try:
                schema = client.get("/openapi.json")
                schema.raise_for_status()
                if "/meeting-intakes" in schema.json().get("paths", {}):
                    break
                response = client.get("/maintenance/drain")
                response.raise_for_status()
                status = response.json()
                if status["active_job_count"] == 0 and status["in_flight_message_count"] == 0:
                    response = client.post("/maintenance/drain", json={"requested": True})
                    response.raise_for_status()
                    requested = True
                    if response.json()["ready_to_restart"]:
                        record("restarting_idle_backend")
                        subprocess.run(["systemctl", "--user", "restart", "codex-mobile-bridge-dev.service"], check=True, timeout=90)
                        for _ in range(60):
                            time.sleep(1)
                            try:
                                response = client.get("/openapi.json")
                                if response.is_success and "/meeting-intakes" in response.json().get("paths", {}):
                                    break
                            except httpx.HTTPError:
                                pass
                        else:
                            record("blocked_backend_route_not_loaded")
                            return 1
                        break
                    client.post("/maintenance/drain", json={"requested": False}).raise_for_status()
                    requested = False
            except httpx.HTTPError:
                pass
            time.sleep(5)
        else:
            record("blocked_backend_did_not_become_idle")
            return 1
        if requested:
            client.post("/maintenance/drain", json={"requested": False}).raise_for_status()
            requested = False
        subprocess.run(["systemctl", "--user", "enable", "--now", "codex-meeting-inbox.service"], check=True, timeout=30, capture_output=True)
        probe = subprocess.run([str(ROOT / ".venv/bin/python"), "-m", "services.relevamientos.inbox", "doctor", "--check-drive"],
                               cwd=ROOT, text=True, capture_output=True, timeout=60)
        facts = json.loads(probe.stdout)
        record("ready_for_real_delivery" if facts["drive_access_verified"] else "backend_and_monitor_active_drive_authorization_required",
               backend_route_loaded=True, monitor_enabled=True, drive_access=facts)
        return 0
    except Exception as error:
        record("activation_failed", error_type=type(error).__name__)
        return 1
    finally:
        if requested:
            try:
                client.post("/maintenance/drain", json={"requested": False})
            except httpx.HTTPError:
                pass
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
