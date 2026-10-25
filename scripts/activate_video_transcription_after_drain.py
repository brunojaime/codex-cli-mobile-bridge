#!/usr/bin/env python3
"""One authorized activation, after work finishes. Never force-stop active jobs."""

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.probe_video_transcription import OUT, probe, request  # noqa: E402

FILES = [
    "backend/app/api/routes.py",
    "backend/app/application/services/message_service.py",
    "backend/app/infrastructure/media/video_preview.py",
    "backend/app/infrastructure/media/video_transcript.py",
    "backend/app/infrastructure/transcription/faster_whisper_transcriber.py",
    "services/whatsapp_ingest/worker.py",
]


def record(env, status, **facts):
    (OUT / f"{env}-activation.json").write_text(
        json.dumps({"status": status, "at": time.time(), **facts}, indent=2)
    )


def pid(env):
    cmd = ["systemctl"] + (["--user"] if env == "dev" else [])
    return int(
        subprocess.check_output(
            cmd
            + [
                "show",
                "codex-mobile-bridge-"
                + ("dev" if env == "dev" else "backend")
                + ".service",
                "-p",
                "MainPID",
                "--value",
            ]
        )
    )


def activate(env, hashes):
    base = "http://127.0.0.1:" + ("8000" if env == "prod" else "8118")
    record(env, "waiting_for_active_chats", source_sha256=hashes)
    for _ in range(1440):
        if any(
            hashlib.sha256((ROOT / f).read_bytes()).hexdigest() != h
            for f, h in hashes.items()
        ):
            record(env, "pending_source_changed")
            return False
        try:
            health = request(base, "/health")
            if health["features"].get("video_transcription_v1"):
                record(env, "already_active", pid_after=pid(env), source_sha256=hashes)
                return True
            drain = request(base, "/maintenance/drain")
            if drain["active_job_count"] == 0 and drain["in_flight_message_count"] == 0:
                drain = request(base, "/maintenance/drain", {"requested": True})
                if drain["ready_to_restart"]:
                    before = pid(env)
                    record(
                        env,
                        "restarting",
                        pid_before=before,
                        active_jobs=0,
                        source_sha256=hashes,
                    )
                    # systemd Restart=always restarts after graceful shutdown.
                    os.kill(before, signal.SIGTERM)
                    for _ in range(20):
                        time.sleep(1)
                        if pid(env) != before:
                            break
                    else:
                        # Already drained; only close lingering idle streams.
                        os.kill(before, signal.SIGINT)
                    break
                request(base, "/maintenance/drain", {"requested": False})
        except (OSError, ValueError):
            pass
        time.sleep(5)
    else:
        record(env, "pending_active_chats")
        return False
    for _ in range(60):
        time.sleep(1)
        try:
            health = request(base, "/health")
            if health["features"].get("video_transcription_v1"):
                request(base, "/maintenance/drain", {"requested": False})
                record(
                    env,
                    "activated",
                    pid_before=before,
                    pid_after=pid(env),
                    active_jobs_at_drain=0,
                    source_sha256=hashes,
                    backend_commit=health["backend_commit"],
                )
                return True
        except (OSError, ValueError):
            pass
    record(env, "pending_health")
    return False


def main():
    hashes = {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in FILES}
    # Independent activation loops so a busy PROD does not prevent DEV draining.
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {env: pool.submit(activate, env, hashes) for env in ("prod", "dev")}
        results = {}
        for env, future in futures.items():
            results[env] = future.result()
            if results[env]:
                try:
                    probe(env)
                except Exception as exc:
                    (OUT / f"{env}-probe-error.json").write_text(
                        json.dumps(
                            {"error_type": type(exc).__name__, "detail": str(exc)[:200]}
                        )
                    )
    commands = [
        (
            "post-activation-check.txt",
            [sys.executable, "scripts/check_video_transcription.py"],
        ),
        (
            "ledger-run.json",
            [
                sys.executable,
                "scripts/pipeline_quality.py",
                "--database",
                ".data/pipeline_quality.sqlite3",
                "run",
                "quality-e17f39b864738a74500f66ca",
                "--attempt",
                "transcription-after-drain-1",
            ],
        ),
        (
            "acceptance.json",
            [
                sys.executable,
                "scripts/pipeline_quality.py",
                "--database",
                ".data/pipeline_quality.sqlite3",
                "evaluate-feedback",
                "requirement-5659b3809f475d705f3e834d",
            ],
        ),
    ]
    for filename, command in commands:
        with (OUT / filename).open("w") as log:
            try:
                results[filename] = subprocess.run(
                    command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=360
                ).returncode
            except subprocess.TimeoutExpired:
                results[filename] = 124
    (OUT / "deferred-results.json").write_text(json.dumps(results, indent=2))
    if results.get("post-activation-check.txt") == 0:
        report = OUT / "informe.md"
        report.write_text(
            "**Actualización automática:** pruebas contra PROD y DEV aprobadas después de activar sin trabajos activos. [Evidencia](check-evidence.json). La aceptación formal permanece separada.\n\n"
            + report.read_text()
        )


if __name__ == "__main__":
    main()
