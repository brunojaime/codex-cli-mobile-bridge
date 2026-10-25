import hashlib
from pathlib import Path
import shutil
import subprocess

import av
import pytest

from backend.app.infrastructure.media.video_preview import prepare_video_preview
from test_message_flow import build_session_client_with_container, wait_for_job

FIXTURE = Path(__file__).parent / "fixtures/whatsapp-video.mp4"


@pytest.fixture(autouse=True)
def isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_QUALITY_DATABASE", str(tmp_path / "quality.sqlite3"))
    monkeypatch.setenv("PIPELINE_QUALITY_JEV_ENABLED", "false")


def test_native_pixels_timestamps_cache_and_repair(tmp_path):
    source = tmp_path / "video.mp4"
    shutil.copyfile(FIXTURE, source)
    before = source.read_bytes()
    frames, note = prepare_video_preview(str(source))
    assert len(frames) == 2
    assert "t=0.000s" in note and "t=0.800s" in note
    assert "separate video audio status" in note and "not continuous playback" in note
    with av.open(frames[0]) as c:
        pixels = next(c.decode(video=0)).to_ndarray(format="rgb24")
    assert pixels.shape == (64, 64, 3)
    assert pixels[32, 32, 2] > 240 and pixels[32, 32, 0] < 10
    hashes = [hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in frames]
    mtimes = [Path(f).stat().st_mtime_ns for f in frames]
    assert prepare_video_preview(str(source)) == (frames, note)
    assert mtimes == [Path(f).stat().st_mtime_ns for f in frames]
    Path(frames[0]).write_bytes(b"corrupted")
    assert prepare_video_preview(str(source))[0] == frames
    assert hashes == [hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in frames]
    assert source.read_bytes() == before


def test_failure_limits_and_isolation(tmp_path, monkeypatch):
    source = tmp_path / "bad.mp4"
    source.write_bytes(b"invalid")
    assert prepare_video_preview(str(source))[0] == []
    assert "Do not claim visual inspection" in prepare_video_preview(str(source))[1]
    shutil.copyfile(FIXTURE, source)
    assert prepare_video_preview(str(source), max_frames=0)[0] == []
    assert len(prepare_video_preview(str(source), max_frames=1)[0]) == 1
    other = tmp_path / "other"
    other.mkdir()
    shutil.copyfile(source, other / "video.mp4")
    assert set(prepare_video_preview(str(source))[0]).isdisjoint(
        prepare_video_preview(str(other / "video.mp4"))[0]
    )

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("decode", 35)

    monkeypatch.setattr(subprocess, "run", timeout)
    assert prepare_video_preview(str(source))[0] == []


def test_two_videos_native_model_inputs_and_retry(tmp_path):
    client, container = build_session_client_with_container()
    # Fake provider echoes the actual execution inputs; no model opinion passes this test.
    reply = client.post(
        "/message/attachments",
        data={"message": "Compare both recordings"},
        files=[
            ("attachments", ("first.mp4", FIXTURE.read_bytes(), "video/mp4")),
            ("attachments", ("second.mp4", FIXTURE.read_bytes(), "video/mp4")),
            ("attachments", ("image.png", b"image", "image/png")),
        ],
    )
    assert reply.status_code == 202
    job = wait_for_job(client, reply.json()["job_id"], timeout_seconds=30)
    assert job["status"] == "completed"
    stored = container.message_service._repository.get_job(job["job_id"])
    assert len(stored.image_paths) == 5 and len(stored.video_paths) == 2
    assert job["response"].count("sampled frames attached as images") == 2
    assert "[images: " in job["response"]
    for image_path in stored.image_paths:
        assert Path(image_path).name in job["response"].split("[images: ")[-1]
    for path in stored.image_paths[:4]:
        assert Path(path).read_bytes().startswith(b"\x89PNG")
    assert all(Path(p).read_bytes() == FIXTURE.read_bytes() for p in stored.video_paths)
    retry = client.post(f"/jobs/{job['job_id']}/retry")
    assert retry.is_success
    retried = container.message_service._repository.get_job(retry.json()["job_id"])
    assert [Path(p).read_bytes() for p in retried.image_paths] == [
        Path(p).read_bytes() for p in stored.image_paths
    ]


def test_document_video_supplies_native_images():
    client, container = build_session_client_with_container()
    reply = client.post(
        "/message/document",
        data={"message": "Inspect"},
        files={"document": ("clip.mp4", FIXTURE.read_bytes(), "video/mp4")},
    )
    assert reply.status_code == 202, reply.text
    stored = container.message_service._repository.get_job(reply.json()["job_id"])
    assert len(stored.image_paths) == 2 and len(stored.video_paths) == 1


def test_samples_follow_real_scene_changes_and_resize(tmp_path):
    import numpy as np

    source = tmp_path / "changing.mp4"
    with av.open(str(source), "w") as out:
        stream = out.add_stream("mpeg4", rate=2)
        stream.width, stream.height, stream.pix_fmt = 1400, 64, "yuv420p"
        for i in range(12):
            pixels = np.zeros((64, 1400, 3), dtype=np.uint8)
            pixels[:, :, 0 if i < 6 else 1] = 255
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            for packet in stream.encode(frame):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
    frames, note = prepare_video_preview(str(source))
    assert len(frames) == 3
    colors = []
    for path in frames:
        with av.open(path) as container:
            frame = next(container.decode(video=0))
            assert frame.width == 1280 and frame.height < 64
            colors.append(frame.to_ndarray(format="rgb24")[10, 10].argmax())
    assert colors[0] == 0 and colors[-1] == 1
    assert "6.000 seconds" in note
