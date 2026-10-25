import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest
from backend.app.infrastructure.media import video_transcript as vt
from backend.app.infrastructure.transcription.faster_whisper_transcriber import (
    FasterWhisperAudioTranscriber,
)
from test_message_flow import build_session_client_with_container, wait_for_job

SPEECH = Path(__file__).parent / "fixtures/video-speech.mp4"
SILENT = Path(__file__).parent / "fixtures/whatsapp-video.mp4"


@pytest.fixture(autouse=True)
def isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_QUALITY_DATABASE", str(tmp_path / "quality.sqlite3"))
    monkeypatch.setenv("PIPELINE_QUALITY_JEV_ENABLED", "false")


def test_real_offline_speech_cache_language_and_integrity(tmp_path):
    p = tmp_path / "speech.mp4"
    shutil.copyfile(SPEECH, p)
    before = p.read_bytes()
    r = vt.prepare_video_transcript(p, language="es")
    assert r["status"] == "transcribed"
    text = " ".join(s["text"] for s in r["segments"]).lower()
    assert "transcripción automática" in text and "reservar un turno" in text
    assert all(0 <= s["start"] < s["end"] < 12 for s in r["segments"])
    cache = next(tmp_path.glob("video-transcript-*/transcript.json"))
    mtime = cache.stat().st_mtime_ns
    assert vt.prepare_video_transcript(p, language="es") == r
    assert cache.stat().st_mtime_ns == mtime and p.read_bytes() == before
    # Identical bytes with a different filename share the same cache in this scope.
    second = tmp_path / "copy.mp4"
    second.write_bytes(before)
    assert vt.prepare_video_transcript(second, language="es") == r
    assert cache.stat().st_mtime_ns == mtime
    cache.write_text("{}")
    assert vt.prepare_video_transcript(p, language="es")["status"] == "transcribed"
    assert (
        json.loads(cache.read_text())["sha256"]
        == hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest()
    )


def test_no_track_silence_errors_limits_and_cache_isolation(tmp_path, monkeypatch):
    import av
    import numpy as np

    p = tmp_path / "clip.mp4"
    shutil.copyfile(SILENT, p)
    assert vt.prepare_video_transcript(p)["status"] == "no_audio"
    assert vt.prepare_video_transcript(p, language="es")["status"] == "no_audio"
    assert len(list(tmp_path.glob("video-transcript-*"))) == 2
    other = tmp_path / "other"
    other.mkdir()
    shutil.copyfile(p, other / "clip.mp4")
    assert vt.prepare_video_transcript(other / "clip.mp4")["status"] == "no_audio"
    assert len(list(other.glob("video-transcript-*"))) == 1
    silent = tmp_path / "silence.mp4"
    with av.open(str(silent), "w") as out:
        a = out.add_stream("aac", rate=16000)
        frame = av.AudioFrame.from_ndarray(
            np.zeros((1, 16000), dtype=np.int16), format="s16", layout="mono"
        )
        frame.sample_rate = 16000
        for packet in a.encode(frame):
            out.mux(packet)
        for packet in a.encode():
            out.mux(packet)
    assert vt.prepare_video_transcript(silent)["status"] == "no_speech"
    monkeypatch.setattr(vt, "MAX_SECONDS", 0.001)
    assert vt.decode(silent, {})["status"] == "limit"
    p.write_bytes(b"invalid")
    assert vt.prepare_video_transcript(p)["status"] == "unavailable"

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("transcribe", 180)

    monkeypatch.setattr(vt.subprocess, "run", timeout)
    assert vt.prepare_video_transcript(p)["status"] == "unavailable"
    assert "does not prove" in vt.transcript_note({"status": "no_speech"})


def test_automatic_context_mixed_batch_retry_and_document(tmp_path):
    client, container = build_session_client_with_container()
    container.message_service._audio_transcriber = FasterWhisperAudioTranscriber(
        model="small"
    )
    reply = client.post(
        "/message/attachments",
        data={"message": "Descripción original"},
        files=[
            ("attachments", ("speech.mp4", SPEECH.read_bytes(), "video/mp4")),
            ("attachments", ("no-track.mp4", SILENT.read_bytes(), "video/mp4")),
            ("attachments", ("image.png", b"image", "image/png")),
        ],
    )
    assert reply.status_code == 202, reply.text
    job = wait_for_job(client, reply.json()["job_id"], timeout_seconds=30)
    assert (
        "transcripción automática" in job["response"]
        and "Video audio status: no_audio" in job["response"]
    )
    assert "Descripción original" in job["response"]
    stored = container.message_service._repository.get_job(job["job_id"])
    assert [Path(p).read_bytes() for p in stored.video_paths] == [
        SPEECH.read_bytes(),
        SILENT.read_bytes(),
    ]

    def fail(*a, **k):
        raise AssertionError("Retry must not transcribe again")

    container.message_service._audio_transcriber.transcribe_video = fail
    retry = client.post(f"/jobs/{job['job_id']}/retry")
    assert retry.is_success
    retried = wait_for_job(client, retry.json()["job_id"], timeout_seconds=30)
    assert "transcripción automática" in retried["response"]
    # Failures are visible and never lose the original or previews.
    reply = client.post(
        "/message/document",
        data={"message": "Inspect"},
        files={"document": ("clip.mp4", SILENT.read_bytes(), "video/mp4")},
    )
    assert reply.status_code == 202
    failed = wait_for_job(client, reply.json()["job_id"], timeout_seconds=30)
    assert "Video audio status: unavailable" in failed["response"]
    stored = container.message_service._repository.get_job(failed["job_id"])
    assert len(stored.image_paths) == 2 and len(stored.video_paths) == 1


def test_whatsapp_waits_for_bounded_preprocessing(monkeypatch, tmp_path):
    from services.whatsapp_ingest.worker import BridgeClient
    import urllib.request

    captured = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return b"{}"

    def open_request(request, timeout):
        captured.append(timeout)
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", open_request)
    p = tmp_path / "clip.mp4"
    p.write_bytes(b"video")
    client = BridgeClient("http://localhost:1")
    client._request_multipart("/message/attachments", fields={}, attachments=[p, p])
    assert captured == [480]
