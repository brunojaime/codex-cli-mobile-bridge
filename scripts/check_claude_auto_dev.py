#!/usr/bin/env python3
"""Small real DEV checks for Claude auto permissions through the existing app API.

Only targets the DEV bridge (port 8118) and a scratch workspace under .run/.
Evidence comes from the CLI init event the backend verifies, never from asking
the model who it is. No external messages, deploys or releases are triggered.
"""
import argparse
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:8118"
WORKSPACE = ROOT / ".run" / "claude-auto-e2e-workspace"
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c63f8cfc0f01f0005000201a5f0f9b80000000049454e44ae426082"
)


def call(method, path, body=None, *, raw=None, headers=None, timeout=30):
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    request = urllib.request.Request(API + path, data=data, method=method,
        headers=headers or {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"null")


def wait_job(job_id, timeout=300, on_poll=None):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _, job = call("GET", f"/response/{job_id}")
        if on_poll:
            on_poll(job)
        if job.get("status") in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(1)
    raise TimeoutError(job_id)


def wait_idle(session_id, timeout=600):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _, drain = call("GET", "/maintenance/drain")
        _, session = call("GET", f"/sessions/{session_id}")
        busy = session_id in drain.get("active_session_ids", []) or any(
            m["status"] in {"pending", "reserved", "submission_pending", "running"}
            for m in session.get("messages", []))
        if not busy:
            return session
        time.sleep(2)
    raise TimeoutError(session_id)


def new_session(title, **extra):
    status, session = call("POST", "/sessions", {"title": title, "workspace_path": str(WORKSPACE), **extra})
    assert status == 201, session
    return session


def legacy_agents(session, preset, enabled, *, model="gpt-5.4", members=()):
    """Re-send the configuration the way an old frontend would, with a GPT model."""
    config = session["agent_configuration"]
    agents = []
    for agent in config["agents"]:
        agent = {k: v for k, v in agent.items() if k != "provider_session_id"}
        agent["model"] = model
        agent["enabled"] = agent["agent_id"] in enabled
        if agent["agent_id"] in enabled and agent["max_turns"] == 0:
            agent["max_turns"] = 1
        agents.append(agent)
    body = {**{k: config[k] for k in ("display_mode", "turn_budget_mode", "summary_strategy")},
            "preset": preset, "agents": agents, "supervisor_member_ids": list(members)}
    status, updated = call("PUT", f"/sessions/{session['id']}/agents", body)
    assert status == 200, updated
    return updated


def chat_checks(results):
    session = new_session("Claude auto · chat DEV")
    session = legacy_agents(session, "solo", {"generator"})
    results["saved_models"] = sorted({a["model"] for a in session["agent_configuration"]["agents"]})
    activities = set()
    status, accepted = call("POST", "/message", {"session_id": session["id"], "message": (
        "Prueba técnica DEV. Creá el archivo auto_probe.txt con el contenido AUTO_OK, "
        "luego ejecutá el comando de shell `ls -1` y respondé sólo DONE.")})
    assert status == 202, accepted
    job = wait_job(accepted["job_id"], on_poll=lambda j: activities.add(j.get("latest_activity")))
    results["write_and_bash"] = {"status": job["status"], "response": job.get("response"),
        "error": job.get("error"), "file": (WORKSPACE / "auto_probe.txt").read_text().strip()
        if (WORKSPACE / "auto_probe.txt").exists() else None,
        "init_activity": sorted(a for a in activities if a and "permissions=" in a),
        "provider_session_id": job.get("provider_session_id")}
    wait_idle(session["id"])
    status, accepted = call("POST", "/message", {"session_id": session["id"],
        "message": "Sin usar herramientas: ¿qué contenido escribiste en el archivo? Respondé sólo ese contenido."})
    job2 = wait_job(accepted["job_id"])
    results["continuation"] = {"status": job2["status"], "response": job2.get("response"),
        "same_native_session": job2.get("provider_session_id") == job.get("provider_session_id")}
    wait_idle(session["id"])
    boundary = uuid.uuid4().hex
    form = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"session_id\"\r\n\r\n{session['id']}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"message\"\r\n\r\n"
            "Sin herramientas: describí en tres palabras el color dominante de la imagen.\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"px.png\"\r\n"
            "Content-Type: image/png\r\n\r\n").encode() + PNG_1PX + f"\r\n--{boundary}--\r\n".encode()
    status, accepted = call("POST", "/message/image", raw=form,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    image_job = wait_job(accepted["job_id"]) if status == 202 else {"status": f"http {status}", "error": accepted}
    results["image"] = {"status": image_job["status"], "response": image_job.get("response"),
                        "error": image_job.get("error")}
    wait_idle(session["id"])
    status, accepted = call("POST", "/message", {"session_id": session["id"], "message":
        "Ejecutá el comando de shell `sleep 25` y después respondé sólo RETRY_OK."})
    time.sleep(6)
    cancel_status, cancelled = call("POST", f"/jobs/{accepted['job_id']}/cancel")
    cancelled = wait_job(accepted["job_id"])
    retry_status, retried = call("POST", f"/jobs/{accepted['job_id']}/retry")
    retried_job = wait_job(retried["job_id"]) if retry_status in {200, 202} else {"status": f"http {retry_status}"}
    results["cancel_retry"] = {"cancel_http": cancel_status, "cancelled": cancelled["status"],
        "retry_http": retry_status, "retried": retried_job["status"], "response": retried_job.get("response")}
    results["chat_session_id"] = session["id"]
    return session


def loop_checks(results):
    session = new_session("Claude auto · Generator/Reviewer DEV")
    session = legacy_agents(session, "review", {"generator", "reviewer"})
    status, _ = call("PUT", f"/sessions/{session['id']}/auto-mode", {"enabled": True, "max_turns": 1})
    status, accepted = call("POST", "/message", {"session_id": session["id"], "message":
        "Prueba breve DEV sin herramientas: respondé GENERATOR_OK. El Reviewer debe devolver su veredicto."})
    final = wait_idle(session["id"])
    jobs = [m for m in final["messages"] if m["role"] == "assistant"]
    results["generator_reviewer"] = {
        "assistant_turns": [(m["agent_id"], m["status"]) for m in jobs],
        "reviewer": next((m["content"][:300] for m in jobs if m["agent_id"] == "reviewer"), None)}
    session = new_session("Claude auto · Supervisor DEV")
    session = legacy_agents(session, "supervisor", {"supervisor", "qa"}, members=("qa",))
    status, accepted = call("POST", "/message", {"session_id": session["id"], "message":
        "Prueba breve DEV sin herramientas: pedile a QA que responda QA_OK y luego cerrá el ciclo."})
    final = wait_idle(session["id"], timeout=900)
    results["supervisor"] = {"http": status, "assistant_turns": [
        (m["agent_id"], m["status"], m["content"][:160]) for m in final["messages"] if m["role"] == "assistant"]}


def secondary_cli_checks(results):
    """Run the SDD/Project Factory CLI contract with DEV's own settings and env file."""
    import os
    import sys
    sys.path.insert(0, str(ROOT))
    from backend.app.container import _agent_cli
    from backend.app.infrastructure.config.settings import Settings
    from backend.app.infrastructure.execution.agent_cli import run_process
    from backend.app.infrastructure.execution.claude_evidence import latest
    settings = Settings(_env_file=(str(ROOT / ".run/dev-backend-8118/dev.env"),))
    argv = _agent_cli(settings).argv(prompt="Creá cli_probe.txt con CLI_OK y respondé sólo DONE.")
    env = {k: v for k, v in os.environ.items() if k in {"HOME", "PATH", "LANG", "TERM", "USER"}}
    result = run_process(argv=argv, cwd=WORKSPACE, env=env, timeout_seconds=300)
    results["secondary_cli"] = {"returncode": result.returncode, "stdout": result.stdout[:200],
        "stderr": result.stderr[:300], "evidence": latest().get("agent_cli"),
        "file": (WORKSPACE / "cli_probe.txt").read_text().strip() if (WORKSPACE / "cli_probe.txt").exists() else None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / ".run" / "claude-auto-dev-e2e.json"))
    parser.add_argument("--continue-session")
    args = parser.parse_args()
    _, health = call("GET", "/health")
    assert health.get("status") == "ok"
    _, runtime = call("GET", "/ai/runtime")
    results = {"started_at": time.time(), "backend_commit": health.get("backend_commit"),
               "runtime_before": runtime}
    if args.continue_session:
        status, accepted = call("POST", "/message", {"session_id": args.continue_session,
            "message": "Sin herramientas: ¿qué contenido escribiste antes en auto_probe.txt? Respondé sólo eso."})
        job = wait_job(accepted["job_id"])
        results["after_restart"] = {"status": job["status"], "response": job.get("response"),
                                    "provider_session_id": job.get("provider_session_id")}
    else:
        WORKSPACE.mkdir(parents=True, exist_ok=True)
        for name in ("auto_probe.txt", "cli_probe.txt"):
            (WORKSPACE / name).unlink(missing_ok=True)
        for check in (chat_checks, loop_checks, secondary_cli_checks):
            try:
                check(results)
            except Exception as exc:  # Record and continue; the report must show it.
                results[check.__name__ + "_error"] = f"{type(exc).__name__}: {exc}"
    _, results["runtime_after"] = call("GET", "/ai/runtime")
    Path(args.out).write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
