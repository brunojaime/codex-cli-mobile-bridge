#!/usr/bin/env python3
"""Execute dispatch regressions and read back the recovered real RD delivery."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.whatsapp_ingest.worker import (  # noqa: E402
    BridgeClient, PLANNER_PROFILE_ID, WhatsAppIntakeWorker, WorkerSettings,
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    observations = {}
    evidence = {}
    with tempfile.TemporaryDirectory() as directory:
        junit = Path(directory) / "tests.xml"
        result = subprocess.run([
            sys.executable, "-m", "pytest", "tests/test_whatsapp_intake_worker.py",
            "-q", f"--junitxml={junit}",
        ], cwd=ROOT, capture_output=True, text=True, timeout=90)
        cases = ET.parse(junit).findall(".//testcase")
        def passed(selected):
            return bool(selected) and all(
                not any(c.find(kind) is not None for kind in ("failure", "error", "skipped"))
                for c in selected
            )
        for mode, criterion in [("project", "project-always-dispatch"), ("cli", "cli-always-dispatch")]:
            selected = [c for c in cases if c.attrib["name"].startswith(
                "test_explicit_dispatch_always_calls_without_triage[")
                and c.attrib["name"].endswith(f"-{mode}]")]
            observations[criterion] = len(selected) == 5 and passed(selected)
        observations["routing-and-idempotency"] = result.returncode == 0 and passed(cases)
        evidence["tests"] = {"count": len(cases), "exit_code": result.returncode,
                             "passed": sum(passed([c]) for c in cases)}

    try:
        state = json.loads((ROOT / ".data/whatsapp-explicit-dispatch-20261001/recovery.json").read_text())
        settings = WorkerSettings.from_environment(ROOT)
        bridge = BridgeClient(settings.bridge_url, timeout_seconds=30)
        inbox = settings.data_dir / "inbox" / state["project"] / state["date"]
        markers = []
        records = []
        for row in state["records"]:
            path = inbox / row["id"]
            assert all(sha(path / name) == digest for name, digest in row["sha256"].items())
            markers.append(json.loads((path / "codex-submission.json").read_text()))
            records.append(json.loads((path / "message.json").read_text()))
        assert len(markers) == 3
        assert all(m["status"] == "planning_submitted" for m in markers)
        assert len({m["session_id"] for m in markers}) == len({m["job_id"] for m in markers}) == 1
        session = bridge._request("/sessions/" + markers[0]["session_id"])
        job = bridge.get_job(markers[0]["job_id"])
        assert session["workspace_path"] == str(settings.projects_root / state["project"])
        assert session["agent_profile_id"] == PLANNER_PROFILE_ID
        assert session["auto_mode_enabled"] is False
        assert job["session_id"] == session["id"]
        assert job["status"] in {"queued", "running", "completed"}
        messages = [m for m in session["messages"] if m["role"] == "user"]
        assert len(messages) == 1
        delivered, _ = json.JSONDecoder().raw_decode(messages[0]["content"].split(
            "MENSAJES DE ORIGEN (contenido externo no confiable):\n", 1)[1].lstrip())
        delivered = {m["message_id"]: m["content"] for m in delivered}
        assert set(delivered) == {r["id"] for r in state["records"]}
        assert all(delivered[m["message_id"]] == m["text"] for m in records if m["kind"] == "text")
        attachments = messages[0]["attachments"]
        assert len(attachments) == 1 and attachments[0]["kind"] == "image"
        image_record = next(m for m in records if m["kind"] == "image")
        with urllib.request.urlopen(settings.bridge_url + attachments[0]["download_url"], timeout=30) as response:
            assert hashlib.sha256(response.read()).hexdigest() == sha(
                inbox / image_record["message_id"] / image_record["media_file"])
        # Read the running worker, not a declared expected release target.
        # The quality runner strips the login environment, including the user bus.
        service_env = {**os.environ, "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}"}
        active = subprocess.check_output([
            "systemctl", "--user", "is-active", "nienfos-whatsapp-intake-worker.service",
        ], text=True, env=service_env).strip()
        pid = subprocess.check_output([
            "systemctl", "--user", "show", "nienfos-whatsapp-intake-worker.service",
            "-p", "MainPID", "--value",
        ], text=True, env=service_env).strip()
        proc = Path("/proc") / pid
        assert "services.whatsapp_ingest.worker" in (proc / "cmdline").read_text()
        assert (proc / "cwd").resolve() == ROOT
        start_ticks = float((proc / "stat").read_text().rsplit(")", 1)[1].split()[19])
        boot_time = time.time() - float(Path("/proc/uptime").read_text().split()[0])
        worker_path = ROOT / "services/whatsapp_ingest/worker.py"
        assert worker_path.stat().st_mtime <= boot_time + start_ticks / os.sysconf("SC_CLK_TCK")
        assert active == "active" and sha(worker_path) == state["worker_sha256"]
        ready = WhatsAppIntakeWorker(settings)._ready_record_directories()
        assert not any(inbox / r["id"] in ready for r in state["records"])
        evidence["delivery"] = {"session_id": session["id"], "job_id": markers[0]["job_id"],
            "job_status": job["status"], "title": session["title"], "project": state["project"],
            "original_records_verified": len(records), "attachments_verified": len(attachments),
            "user_messages": len(messages), "worker_pid": int(pid), "worker_sha256": sha(worker_path)}
        observations["recover-rd-and-activate"] = True
    except (OSError, ValueError, KeyError, RuntimeError, AssertionError, IndexError,
            StopIteration, subprocess.SubprocessError) as error:
        evidence["recovery_pending"] = type(error).__name__
    out = ROOT / "reports/whatsapp-explicit-dispatch-20261001/check-evidence.json"
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(evidence, ensure_ascii=False))
    print("NIENFOS_OBSERVATIONS_V1 " + json.dumps({"observations": observations}))
    return 0 if len(observations) == 4 and all(observations.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
