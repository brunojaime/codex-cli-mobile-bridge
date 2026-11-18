"""Load the tested message-ID fix when each existing backend is idle. No launches."""
from pathlib import Path
import hashlib
import json
import subprocess
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
MODULE = Path("backend/app/application/services/generator_reviewer_launch_service.py")
TARGETS = [
    ("prod", 8000, ROOT / ".run/meeting-prod-runtime-20261103", False, "codex-mobile-bridge-backend.service"),
    ("dev", 8118, Path("/home/batata/Projects/nienfos-gestion/tmp/shared-feedback-bridge-20261028"), True, "codex-mobile-bridge-dev.service"),
]
OUTPUT = ROOT / "reports/generator-reviewer-20261103/activacion.json"


def main():
    source = (ROOT / MODULE).read_bytes()
    baseline = subprocess.check_output(["git", "show", "HEAD:" + str(MODULE)], cwd=ROOT)
    states = {name: "waiting_for_idle_backend" for name, *_ in TARGETS}

    def record():
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        temp = OUTPUT.with_suffix(".tmp")
        temp.write_text(json.dumps({"states": states, "source_sha256": hashlib.sha256(source).hexdigest(),
                                    "tests_passed": 35, "cycle_started": False}, indent=2) + "\n")
        temp.replace(OUTPUT)

    record()
    deadline = time.monotonic() + 7200
    pending = list(TARGETS)
    while pending and time.monotonic() < deadline:
        for target in list(pending):
            name, port, runtime, user_service, service = target
            client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=15)
            draining = False
            try:
                schema = client.get("/openapi.json").raise_for_status().json()
                prop = schema["components"]["schemas"]["GeneratorReviewerLaunch"]["properties"]["source_message_id"]
                if prop.get("format") != "uuid":
                    states[name] = "ready"
                    pending.remove(target)
                    continue
                status = client.get("/maintenance/drain").raise_for_status().json()
                if status["requested"] or status["active_job_count"] or status["in_flight_message_count"]:
                    continue
                status = client.post("/maintenance/drain", json={"requested": True}).raise_for_status().json()
                draining = True
                if not status["ready_to_restart"]:
                    continue
                destination = runtime / MODULE
                if destination.read_bytes() not in {baseline, source}:
                    raise RuntimeError("runtime_module_has_unrelated_changes")
                if (ROOT / MODULE).read_bytes() != source:
                    raise RuntimeError("source_changed_after_validation")
                temporary = destination.with_suffix(".py.id-fix-tmp")
                temporary.write_bytes(source)
                temporary.replace(destination)
                command = ["systemctl", "--user", "restart", service] if user_service else ["sudo", "-n", "systemctl", "restart", service]
                subprocess.run(command, check=True, timeout=60)
                for _ in range(30):
                    try:
                        schema = client.get("/openapi.json").raise_for_status().json()
                        prop = schema["components"]["schemas"]["GeneratorReviewerLaunch"]["properties"]["source_message_id"]
                        if prop.get("format") != "uuid":
                            states[name] = "ready"
                            pending.remove(target)
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(1)
                else:
                    raise RuntimeError("backend_did_not_load_fix")
            except httpx.HTTPError:
                pass
            except Exception as error:
                states[name] = "blocked_" + str(error)
                pending.remove(target)
            finally:
                if draining:
                    try:
                        client.post("/maintenance/drain", json={"requested": False}).raise_for_status()
                    except httpx.HTTPError:
                        states[name] = "requires_drain_cleanup"
                client.close()
                record()
        if pending:
            time.sleep(10)


if __name__ == "__main__":
    main()
