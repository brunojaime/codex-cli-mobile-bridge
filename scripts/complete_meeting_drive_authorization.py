"""Finish the prepared monitor setup after the user consents in Google."""
from __future__ import annotations

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


def main():
    load_dotenv(ROOT / ".env", override=False)
    output = ROOT / "reports/relevamientos-automaticos/activacion.json"
    pending = ROOT / ".data/relevamientos-inbox/oauth-status.json"

    def record(state, **facts):
        current = json.loads(output.read_text()) if output.exists() else {}
        atomic(output, {**current, "state": state, "updated_at": time.time(), **facts})

    record("backend_and_monitor_active_google_signin_required", backend_route_loaded=True,
           oauth_state="waiting_for_google_authorization")
    deadline = time.monotonic() + 1850
    while time.monotonic() < deadline:
        state = json.loads(pending.read_text()).get("state") if pending.exists() else None
        if state == "authorization_complete":
            break
        if state in {"authorization_failed", "authorization_denied", "authorization_timed_out"}:
            record("google_authorization_not_completed", oauth_state=state)
            return 1
        time.sleep(2)
    else:
        record("google_authorization_not_completed", oauth_state="timeout")
        return 1
    run = subprocess.run([sys.executable, "-m", "services.relevamientos.inbox", "doctor", "--check-drive"],
                         cwd=ROOT, capture_output=True, text=True, timeout=60)
    diagnosis = json.loads(run.stdout)
    atomic(ROOT / "reports/relevamientos-automaticos/diagnostico-drive.json", diagnosis)
    if run.returncode or not diagnosis.get("drive_access_verified"):
        record("drive_verification_failed_after_consent", drive_access=diagnosis)
        return 1
    url = os.environ.get("RELEVAMIENTOS_BRIDGE_URL", "http://127.0.0.1:8118").rstrip("/")
    response = httpx.get(url + "/openapi.json", timeout=15)
    response.raise_for_status()
    if "/meeting-intakes" not in response.json().get("paths", {}):
        record("blocked_backend_route_not_loaded", drive_access=diagnosis)
        return 1
    subprocess.run(["systemctl", "--user", "restart", "codex-meeting-inbox.service"], check=True, timeout=30)
    active = subprocess.run(["systemctl", "--user", "is-active", "--quiet", "codex-meeting-inbox.service"]).returncode == 0
    record("ready_for_real_delivery" if active else "monitor_start_failed", drive_access=diagnosis,
           backend_route_loaded=True, monitor_enabled=active, oauth_state="authorization_complete")
    return 0 if active else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"state": "authorization_completion_failed", "error_type": type(error).__name__}))
        raise SystemExit(1) from None
