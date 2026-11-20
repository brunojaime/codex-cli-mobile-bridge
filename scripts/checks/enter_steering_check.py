#!/usr/bin/env python3
"""Real Enter-steering check against a running Bridge (DEV or an isolated lab).

Runs real agent turns in a dedicated synthetic chat, steers them through the
same endpoint the composer uses on Enter, and prints one
``NIENFOS_OBSERVATIONS_V1`` line computed from what the Bridge returned.
Usage: enter_steering_check.py BRIDGE_URL WORKSPACE_PATH [ORIGIN_LABEL]
"""

import json
import sys
import time
import urllib.error
import urllib.request

BASE, WORKSPACE = sys.argv[1].rstrip("/"), sys.argv[2]
ORIGIN = sys.argv[3] if len(sys.argv) > 3 else BASE
MARKER = "STEERED-OK"
TERMINAL = {"completed", "failed", "cancelled"}


def call(method, path, body=None, timeout=60):
    request = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def target():
    _, health = call("GET", "/health")
    return {"environment": "dev", "origin": ORIGIN, "release_id": health.get("backend_commit")}


def wait_job(job_id, until, limit=240):
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        _, snapshot = call("GET", f"/response/{job_id}")
        if until(snapshot) or snapshot.get("status") in TERMINAL:
            return snapshot
        time.sleep(0.4)
    raise TimeoutError(job_id)


def scenario(name, task, ready):
    _, session = call("POST", "/sessions", {"title": f"check steering {name}", "workspace_path": WORKSPACE})
    _, accepted = call("POST", "/message", {"message": task, "session_id": session["id"]})
    job_id = accepted["job_id"]
    running = wait_job(job_id, lambda s: s.get("status") == "running" and ready(s))
    steer_status, _ = call(
        "POST", f"/jobs/{job_id}/steer",
        {"message": f"Además, al final agregá la palabra {MARKER}.", "client_submission_id": f"check-{name}-{session['id']}"},
    )
    final = wait_job(job_id, lambda s: False)
    _, detail = call("GET", f"/sessions/{session['id']}")
    after_status, _ = call("POST", f"/jobs/{job_id}/steer", {"message": "tarde"})
    steered = [m for m in detail["messages"] if m.get("reason_code") == "steered_into_running_turn"]
    jobs = {m["job_id"] for m in detail["messages"] if m.get("job_id")}
    return {
        "was_running": running.get("status") == "running",
        "steer_http": steer_status,
        "final": final.get("status"),
        "marker": MARKER in (final.get("response") or ""),
        "steered_once_same_run": len(steered) == 1 and steered[0]["run_id"] == final.get("run_id"),
        "single_job": len(jobs) == 1,
        "refused_after_finish": after_status == 409,
    }


before = target()
mid = scenario(
    "midturn",
    "Run the shell command `sleep 12 && echo step-one`. When it finishes run `sleep 6 && echo step-two` as a separate step. Then answer FINISHED.",
    lambda s: any(a.get("kind") not in (None, "steer", "commentary", "usage") for a in s.get("activities", [])),
)
late = scenario(
    "late",
    "Without using any tool, write a 250-word paragraph about rivers.",
    lambda s: bool(s.get("response")),
)
after = target()
observations = {
    "midturn-steered-same-turn": mid["was_running"] and mid["steer_http"] == 200 and mid["final"] == "completed" and mid["marker"] and mid["single_job"],
    "late-steer-answered-before-finish": late["was_running"] and late["steer_http"] == 200 and late["final"] == "completed" and late["marker"] and late["single_job"],
    "steer-persisted-once-same-run": mid["steered_once_same_run"] and late["steered_once_same_run"],
    "finished-job-refuses-steer": mid["refused_after_finish"] and late["refused_after_finish"],
}
print(json.dumps({"midturn": mid, "late": late}), file=sys.stderr)
print("NIENFOS_OBSERVATIONS_V1 " + json.dumps({"observations": observations, "target_before": before, "target_after": after}))
sys.exit(0 if all(observations.values()) else 1)
