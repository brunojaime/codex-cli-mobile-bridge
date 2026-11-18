#!/usr/bin/env python3
"""One identified real API upload; verify persisted execution inputs, not model opinions."""

import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.whatsapp_ingest.worker import encode_multipart_form  # noqa: E402

OUT = ROOT / "reports/whatsapp-video-transcription-20261005"


def request(base, path, data=None):
    req = urllib.request.Request(
        base + path,
        data=None if data is None else json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def probe(env):
    base = "http://127.0.0.1:" + ("8000" if env == "prod" else "8118")
    health = request(base, "/health")
    assert health["features"].get("video_transcription_v1"), (
        "Backend activation pending"
    )
    path = OUT / f"{env}-probe.json"
    state = json.loads(path.read_text()) if path.exists() else {}
    if not state.get("session_id"):
        state["session_id"] = request(
            base,
            "/sessions",
            {
                "title": "Prueba técnica · transcripción video · " + env,
                "workspace_path": str(ROOT),
            },
        )["id"]
        path.write_text(json.dumps(state, indent=2))
    files = [
        ROOT / "tests/fixtures/video-speech.mp4",
        ROOT / "tests/fixtures/whatsapp-video.mp4",
    ]
    if not state.get("job_id"):
        if state.get("upload_started"):
            raise RuntimeError("Uncertain upload: inspect before retry")
        state["upload_started"] = True
        path.write_text(json.dumps(state, indent=2))
        boundary = "video-transcription-v1"
        body = encode_multipart_form(
            boundary,
            {
                "session_id": state["session_id"],
                "message": "PRUEBA TÉCNICA DE TRANSCRIPCIÓN. No modificar archivos ni usar herramientas. Responder brevemente qué estado de audio tiene cada video y si se adjuntó una transcripción. Son datos sintéticos; no hay pedido de implementar.",
            },
            files,
        )
        req = urllib.request.Request(
            base + "/message/attachments",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req, timeout=480) as r:
            state["job_id"] = json.load(r)["job_id"]
        path.write_text(json.dumps(state, indent=2))
    db = ROOT / (
        ".data/chat_store.sqlite3"
        if env == "prod"
        else ".run/dev-backend-8118/data/chat_store.sqlite3"
    )
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as connection:
        row = connection.execute(
            "SELECT execution_message FROM jobs WHERE id=?", (state["job_id"],)
        ).fetchone()
    assert row
    context = row[0]
    assert "transcripción automática" in context and "reservar un turno" in context
    assert (
        "Video audio status: no_audio" in context
        and "Video audio status: transcribed" in context
    )
    session = request(base, "/sessions/" + state["session_id"])
    user = next(m for m in session["messages"] if m["role"] == "user")
    originals = [a for a in user["attachments"] if a["kind"] == "video"]
    assert len(originals) == 2
    hashes = []
    for attachment, expected in zip(originals, files):
        with urllib.request.urlopen(base + attachment["download_url"], timeout=15) as r:
            data = r.read()
        assert data == expected.read_bytes()
        hashes.append(hashlib.sha256(data).hexdigest())
    image_count = sum(a["kind"] == "image" for a in user["attachments"])
    assert image_count >= 4
    state.update(
        context_verified=True,
        original_sha256=hashes,
        image_count=image_count,
        source="actual API upload and persisted job execution inputs",
        release_id=health["backend_commit"] + ":video-transcription-v1",
    )
    path.write_text(json.dumps(state, indent=2))
    return state


if __name__ == "__main__":
    print(json.dumps(probe(sys.argv[1])))
