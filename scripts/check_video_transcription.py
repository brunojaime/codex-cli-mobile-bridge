#!/usr/bin/env python3
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.probe_video_transcription import probe, request, OUT  # noqa: E402
from backend.app.infrastructure.media.video_transcript import prepare_video_transcript  # noqa: E402


def identity():
    h = request("http://127.0.0.1:8118", "/health")
    return {
        "environment": h["environment_identity"]["environment"],
        "origin": "https://batata-default-string.tail0302c4.ts.net:8443",
        "release_id": h["backend_commit"]
        + (
            ":video-transcription-v1"
            if h["features"].get("video_transcription_v1")
            else ":not-activated"
        ),
    }


def main():
    before = identity()
    with (OUT / "registered-tests.txt").open("w") as log:
        tests = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_video_transcript.py",
                "tests/test_video_preview.py",
                "tests/test_whatsapp_video.py",
                "-q",
            ],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=240,
        )
    facts = {
        "automatic-transcript": tests.returncode == 0,
        "local-honest": tests.returncode == 0,
        "cache-preservation": tests.returncode == 0,
    }
    probes = []
    for env in ("prod", "dev"):
        try:
            probes.append(probe(env)["context_verified"])
        except (AssertionError, OSError):
            pass
    real = [
        prepare_video_transcript(
            ROOT / f"reports/whatsapp-video-inspection-20261005/video-{i}/original.mp4",
            language="es",
        )
        for i in (1, 2)
    ]
    if len(probes) == 2:
        facts["deployed-evidence"] = all(probes) and all(
            r["status"] in {"no_audio", "no_speech", "transcribed"} for r in real
        )
    result = {
        "observations": facts,
        "target_before": before,
        "target_after": identity(),
    }
    (OUT / "check-evidence.json").write_text(json.dumps(result, indent=2))
    print("NIENFOS_OBSERVATIONS_V1 " + json.dumps(result))
    return 0 if len(facts) == 4 and all(facts.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
