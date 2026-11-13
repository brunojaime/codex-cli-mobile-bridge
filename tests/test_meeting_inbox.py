from __future__ import annotations

from copy import deepcopy
import base64
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4
import zipfile
from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest

from backend.app.api.meeting_intake_routes import get_container, router
from backend.app.application.services.message_service import MessageService
from backend.app.domain.entities.agent_configuration import AgentId
from backend.app.infrastructure.persistence.sqlite_chat_repository import SqliteChatRepository
from backend.app.infrastructure.transcription.disabled_transcriber import DisabledAudioTranscriber
from services.relevamientos.delivery import Delivery, POLL_SECONDS, READY_NAME
from services.relevamientos.drive import FOLDER
from services.relevamientos.inbox import Monitor
from services.relevamientos.inbox_drive import InboxDrive
from services.relevamientos.drive_auth import auth_status, credentials
from test_message_flow import _ControlledExecutionProvider


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def rig(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    db = tmp_path / "chats.sqlite3"
    repo = SqliteChatRepository(database_path=str(db), projects_root=str(tmp_path))
    provider = _ControlledExecutionProvider()
    messages = MessageService(
        repository=repo, execution_provider=provider,
        default_workspace_path=str(workspace), audio_transcriber=DisabledAudioTranscriber(),
        bridge_api_port=8123, follow_up_reconcile_interval_seconds=None,
    )
    app = FastAPI()
    app.dependency_overrides[get_container] = lambda: SimpleNamespace(
        message_service=messages, settings=SimpleNamespace(chat_store_path=str(db)),
    )
    app.include_router(router)
    return SimpleNamespace(workspace=workspace, messages=messages, repo=repo,
                           provider=provider, client=TestClient(app), db=db)


class FakeDrive:
    root_id = "root"

    def __init__(self, recording_kind="video"):
        self.recording_kind = recording_kind
        self.recording_path = "audio.mp3" if recording_kind == "audio" else "video.mp4"
        self.project = {"id": "project", "name": "project", "mimeType": FOLDER}
        self.relevamientos = {"id": "surveys", "name": "relevamientos", "mimeType": FOLDER}
        self.meeting = {"id": "meeting", "name": "2026-11-03_revision", "mimeType": FOLDER}
        self.allowed = {"root", "project", "surveys", "meeting"}
        self.data = {
            recording_kind: b"recording", "transcript": "Revisamos permisos. Aprobar el acceso de administradores. Luego hablamos de fútbol.".encode(),
            "summary": b"Revision de permisos", "photo": b"photo",
        }
        self.manifest = {
            "schema_version": 1, "status": "complete", "project": "project",
            "meeting_id": str(uuid4()), "revision": 1, "folder_id": "meeting",
            "completed_at": "2026-11-03T18:30:00-03:00", "files": [],
        }
        self.items = {}
        for name, ident, role in [
            (self.recording_path, recording_kind, recording_kind), ("transcripcion.md", "transcript", "transcript"),
            ("resumen.md", "summary", "summary"), ("adjuntos/foto.txt", "photo", "attachment"),
        ]:
            data = self.data[ident]
            self.items[name] = self.meta(ident, name.split("/")[-1], data)
            self.manifest["files"].append({"path": name, "drive_id": ident, "role": role,
                                          "size": len(data), "sha256": sha(data)})
        self.publish()
        self.fetches = []
        self.mutate_after_fetch = None

    @staticmethod
    def meta(ident, name, data):
        return {"id": ident, "name": name, "mimeType": "application/octet-stream", "size": str(len(data)),
                "version": "1", "sha256Checksum": sha(data), "parents": ["meeting"],
                "capabilities": {"canDownload": True}}

    def publish(self):
        data = json.dumps(self.manifest).encode()
        self.data["ready"] = data
        self.items[READY_NAME] = self.meta("ready", READY_NAME, data)

    def folders(self, parent):
        return {"root": [self.project], "project": [self.relevamientos], "surveys": [self.meeting]}[parent]

    def children(self, parent):
        if parent == "meeting":
            return list(deepcopy(self.items).values())
        assert parent == "surveys"
        return [self.meeting]

    def inventory(self, folder):
        assert folder == "meeting"
        return deepcopy(self.items)

    def fetch(self, meta, target, *, limit, expected_hash=None):
        data = self.data[meta["id"]]
        assert len(data) <= limit
        if expected_hash and sha(data) != expected_hash:
            raise ValueError("content_hash_mismatch")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        self.fetches.append(meta["id"])
        if self.mutate_after_fetch:
            callback, self.mutate_after_fetch = self.mutate_after_fetch, None
            callback()


class LocalBridge:
    def __init__(self, rig):
        self.rig = rig
        self.lost_response = False

    def workspaces(self):
        return [{"name": "project", "path": str(self.rig.workspace)}]

    def launch(self, request):
        response = self.rig.client.post("/meeting-intakes", json=request)
        response.raise_for_status()
        if self.lost_response:
            self.lost_response = False
            raise TimeoutError("response lost after accepted")
        return response.json()

    def job(self, ident):
        return {"status": "running"}


@pytest.mark.parametrize("recording_kind", ["video", "audio"])
def test_verified_delivery_launches_once_with_complete_sources_and_no_drive_writes(rig, tmp_path, recording_kind):
    drive, bridge = FakeDrive(recording_kind), LocalBridge(rig)
    monitor = Monitor(tmp_path / "inbox", drive, bridge)
    monitor.tick()
    record = monitor.get("meeting")
    assert record["state"] == "running", record
    assert len(rig.provider.requests) == 1
    execution = rig.provider.requests[0]["message"]
    assert "Luego hablamos de fútbol" in execution  # Full source reaches analysis.
    assert "Excluí charlas personales" in execution
    assert "photo" in execution
    assert "No escribas ni subas resultados a Google Drive" in execution
    assert recording_kind not in drive.fetches  # Server SHA-256 checked instead.
    envelope = json.loads(record["request"]["prompt"].split("\n\n")[-1])
    assert envelope["files"][0]["role"] == recording_kind
    assert envelope["files"][0]["path"] == drive.recording_path
    assert record["request"]["attachments"] == ["adjuntos/foto.txt"]
    session = rig.messages.get_session(record["session_id"])
    assert session.workspace_path == str(rig.workspace)
    assert {a.agent_id for a in session.agent_configuration.agents.values() if a.enabled} == {AgentId.GENERATOR}
    assert 'sandbox_mode="read-only"' in rig.provider.requests[0]["codex_options"].config_overrides
    Monitor(tmp_path / "inbox", drive, bridge).tick()
    assert len(rig.provider.requests) == 1
    assert POLL_SECONDS == 600


@pytest.mark.parametrize("fault", ["no_marker", "missing_file", "extra_attachment", "wrong_size", "wrong_hash", "wrong_id", "wrong_project", "wrong_folder", "not_downloadable", "empty_transcript", "bad_path", "duplicate_entry"])
@pytest.mark.parametrize("recording_kind", ["video", "audio"])
def test_incomplete_or_invalid_delivery_never_launches(rig, tmp_path, fault, recording_kind):
    drive, bridge = FakeDrive(recording_kind), LocalBridge(rig)
    if fault == "no_marker":
        del drive.items[READY_NAME]
    elif fault == "missing_file":
        del drive.items["adjuntos/foto.txt"]
    elif fault == "extra_attachment":
        drive.items["adjuntos/extra.txt"] = drive.meta("extra", "extra.txt", b"extra")
    elif fault == "wrong_size":
        drive.items[drive.recording_path]["size"] = "500"
    elif fault == "wrong_hash":
        drive.items[drive.recording_path]["sha256Checksum"] = "0" * 64
    elif fault == "wrong_id":
        drive.items[drive.recording_path]["id"] = "replacement"
    elif fault == "wrong_project":
        drive.manifest["project"] = "other"
        drive.publish()
    elif fault == "wrong_folder":
        drive.manifest["folder_id"] = "other"
        drive.publish()
    elif fault == "not_downloadable":
        drive.items[drive.recording_path]["capabilities"]["canDownload"] = False
    elif fault == "empty_transcript":
        drive.data["transcript"] = b" " * len(drive.data["transcript"])
        drive.manifest["files"][1]["sha256"] = sha(drive.data["transcript"])
        drive.items["transcripcion.md"]["sha256Checksum"] = sha(drive.data["transcript"])
        drive.publish()
    elif fault == "bad_path":
        drive.manifest["files"][-1]["path"] = "adjuntos/../../.env"
        drive.publish()
    elif fault == "duplicate_entry":
        drive.manifest["files"].append(drive.manifest["files"][-1])
        drive.publish()
    monitor = Monitor(tmp_path / "inbox", drive, bridge)
    monitor.tick()
    assert monitor.get("meeting")["state"] == "waiting"
    assert not rig.provider.requests


@pytest.mark.parametrize("recording_kind", ["video", "audio"])
def test_source_change_during_validation_waits_and_later_recovers(rig, tmp_path, recording_kind):
    drive, bridge = FakeDrive(recording_kind), LocalBridge(rig)
    drive.mutate_after_fetch = lambda: drive.items[drive.recording_path].update(version="2")
    monitor = Monitor(tmp_path / "inbox", drive, bridge)
    monitor.tick()
    assert monitor.get("meeting")["state"] == "waiting"
    assert not rig.provider.requests
    monitor.tick()
    assert monitor.get("meeting")["state"] == "running"
    assert len(rig.provider.requests) == 1


@pytest.mark.parametrize("recording_kind", ["video", "audio"])
def test_lost_http_response_and_restart_reuses_same_backend_chat(rig, tmp_path, recording_kind):
    drive, bridge = FakeDrive(recording_kind), LocalBridge(rig)
    bridge.lost_response = True
    monitor = Monitor(tmp_path / "inbox", drive, bridge)
    monitor.tick()
    assert monitor.get("meeting")["state"] == "submitting"
    assert len(rig.provider.requests) == 1
    monitor = Monitor(tmp_path / "inbox", drive, bridge)
    monitor.tick()
    assert monitor.get("meeting")["state"] == "running"
    assert len(rig.provider.requests) == 1


def test_unknown_and_ambiguous_projects_never_launch(rig, tmp_path):
    drive, bridge = FakeDrive(), LocalBridge(rig)
    bridge.workspaces = lambda: [{"name": "other", "path": str(rig.workspace)}]
    monitor = Monitor(tmp_path / "inbox", drive, bridge)
    monitor.tick()
    assert monitor.get("project:project")["state"] == "unmatched_project"
    assert not rig.provider.requests
    bridge.workspaces = lambda: [{"name": "project", "path": str(rig.workspace)}] * 2
    monitor.tick()
    assert not rig.provider.requests


@pytest.mark.parametrize("recording_kind", ["video", "audio"])
def test_missing_recording_checksum_streams_and_verifies_bytes(rig, tmp_path, recording_kind):
    drive = FakeDrive(recording_kind)
    del drive.items[drive.recording_path]["sha256Checksum"]
    monitor = Monitor(tmp_path / "inbox", drive, LocalBridge(rig))
    monitor.tick()
    assert recording_kind in drive.fetches
    assert monitor.get("meeting")["state"] == "running"


def test_audio_without_remote_checksum_rejects_corrupted_download(rig, tmp_path):
    drive = FakeDrive("audio")
    del drive.items[drive.recording_path]["sha256Checksum"]
    drive.data["audio"] = b"corrupted"
    monitor = Monitor(tmp_path / "inbox", drive, LocalBridge(rig))
    monitor.tick()
    assert monitor.get("meeting")["state"] == "waiting"
    assert monitor.get("meeting")["problem"] == "content_hash_mismatch"
    assert not rig.provider.requests


@pytest.mark.parametrize("fault", ["missing_recording", "two_audio", "audio_and_video", "unsupported_audio", "mp3_as_video", "video_as_audio", "nested_audio", "missing_summary"])
def test_audio_contract_rejects_invalid_recording_inventory(rig, tmp_path, fault):
    drive = FakeDrive("audio")
    recording = drive.manifest["files"][0]
    if fault == "missing_recording":
        drive.manifest["files"].pop(0)
        del drive.items[drive.recording_path]
    elif fault in {"two_audio", "audio_and_video"}:
        other = dict(recording, path="second.mp3", drive_id="second")
        if fault == "audio_and_video":
            other.update(path="video.mp4", role="video")
        drive.manifest["files"].append(other)
        drive.data["second"] = drive.data["audio"]
        drive.items[other["path"]] = drive.meta("second", other["path"], drive.data["second"])
    elif fault == "mp3_as_video":
        recording["role"] = "video"
    elif fault == "missing_summary":
        drive.manifest["files"].pop(2)
        del drive.items["resumen.md"]
    else:
        path = {"unsupported_audio": "audio.exe", "video_as_audio": "video.mp4", "nested_audio": "adjuntos/audio.mp3"}[fault]
        recording["path"] = path
        drive.items[path] = drive.items.pop(drive.recording_path)
        drive.items[path]["name"] = path.split("/")[-1]
    drive.publish()
    monitor = Monitor(tmp_path / "inbox", drive, LocalBridge(rig))
    monitor.tick()
    assert monitor.get("meeting")["state"] == "waiting"
    assert not rig.provider.requests


def test_audio_contract_accepts_uppercase_mp3_extension():
    drive = FakeDrive("audio")
    drive.manifest["files"][0]["path"] = "Grabacion.MP3"
    assert Delivery.model_validate(drive.manifest).files[0].role == "audio"


def test_backend_rejects_changed_payload_and_path_escape(rig, tmp_path):
    monitor = Monitor(tmp_path / "inbox", FakeDrive(), LocalBridge(rig))
    monitor.tick()
    request = monitor.get("meeting")["request"]
    request["prompt"] = "different"
    assert rig.client.post("/meeting-intakes", json=request).status_code == 409
    request["delivery_key"] = "a" * 64
    request["attachments"] = ["../secret.txt"]
    assert rig.client.post("/meeting-intakes", json=request).status_code == 422
    assert len(rig.provider.requests) == 1


def test_uncertain_provider_submission_is_not_repeated(rig, tmp_path):
    original = rig.messages.submit_message

    def fail_before_submit(*args, **kwargs):
        raise RuntimeError("provider may have accepted before persistence")

    rig.messages.submit_message = fail_before_submit
    monitor = Monitor(tmp_path / "inbox", FakeDrive(), LocalBridge(rig))
    monitor.tick()
    assert monitor.get("meeting")["state"] == "uncertain"
    rig.messages.submit_message = original
    monitor.tick()
    assert not rig.provider.requests


def test_inventory_duplicates_and_unexpected_folders_are_rejected(tmp_path):
    drive = InboxDrive("root", tmp_path / "receipts.json")
    drive.children = lambda _: [
        {"id": "a", "name": "adjuntos", "mimeType": FOLDER},
        {"id": "b", "name": "adjuntos", "mimeType": FOLDER},
    ] if _ == "root" else []
    with pytest.raises(ValueError, match="duplicate_remote_path"):
        drive.inventory("root")
    drive.children = lambda _: [{"id": "a", "name": "unexpected", "mimeType": FOLDER}]
    with pytest.raises(ValueError, match="unexpected_meeting_folder"):
        drive.inventory("root")


def test_drive_adapter_uses_paginated_readonly_requests(tmp_path):
    drive = InboxDrive("root", tmp_path / "receipts.json")
    drive.token = "synthetic-test-token"
    calls = []

    def handle(request):
        calls.append(request)
        assert request.method == "GET"
        if request.url.params.get("pageToken"):
            return httpx.Response(200, json={"files": [{"id": "b", "name": "B", "mimeType": FOLDER}]})
        assert "sha256Checksum" in request.url.params["fields"]
        return httpx.Response(200, json={"nextPageToken": "next", "files": [{"id": "a", "name": "A", "mimeType": FOLDER}]})

    drive.http = httpx.Client(transport=httpx.MockTransport(handle))
    assert [f["id"] for f in drive.folders("root")] == ["a", "b"]
    assert len(calls) == 2
    assert {"a", "b"} <= drive.allowed


def test_manifest_limits_and_required_roles():
    drive = FakeDrive()
    assert Delivery.model_validate(drive.manifest).schema_version == 1
    drive.manifest["files"][1]["role"] = "summary"
    with pytest.raises(ValueError):
        Delivery.model_validate(drive.manifest)


def test_focus_is_frozen_across_timeout_and_new_remote_edits(rig, tmp_path):
    drive, bridge = FakeDrive(), LocalBridge(rig)
    drive.data["focus"] = b"Priorizar permisos y aprobaciones."
    focus = drive.meta("focus", "foco.md", drive.data["focus"])
    drive.children = lambda _: [drive.meeting, focus]
    bridge.lost_response = True
    monitor = Monitor(tmp_path / "inbox", drive, bridge)
    monitor.tick()
    assert monitor.get("meeting")["state"] == "submitting"
    frozen = monitor.get("meeting")["request"]["prompt"]
    assert "Priorizar permisos y aprobaciones" in frozen
    drive.data["focus"] = b"Priorizar ventas."
    monitor.tick()
    assert monitor.get("meeting")["request"]["prompt"] == frozen
    assert len(rig.provider.requests) == 1


def test_images_and_documents_are_passed_to_the_existing_analyzer(rig, tmp_path):
    drive = FakeDrive()
    document = BytesIO()
    with zipfile.ZipFile(document, "w") as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Contrato: requiere doble aprobación.</w:t></w:r></w:p></w:body></w:document>')
    image = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")
    for name, ident, data in [("adjuntos/contrato.docx", "docx", document.getvalue()), ("adjuntos/captura.png", "png", image)]:
        drive.data[ident] = data
        drive.items[name] = drive.meta(ident, name.split("/")[-1], data)
        drive.manifest["files"].append({"path": name, "drive_id": ident, "role": "attachment", "size": len(data), "sha256": sha(data)})
    drive.publish()
    monitor = Monitor(tmp_path / "inbox", drive, LocalBridge(rig))
    monitor.tick()
    assert monitor.get("meeting")["state"] == "running"
    assert "Contrato: requiere doble aprobación" in rig.provider.requests[0]["message"]
    assert len(rig.provider.requests[0]["image_paths"]) == 1


def test_completed_analysis_stays_in_chat_and_is_not_resubmitted(rig, tmp_path):
    bridge = LocalBridge(rig)
    monitor = Monitor(tmp_path / "inbox", FakeDrive(), bridge)
    monitor.tick()
    record = monitor.get("meeting")
    rig.provider.complete_job(record["job_id"], response="Mejoras: revisar permisos. Próximo paso: validar roles.")

    def read_job(ident):
        job = rig.messages.get_job(ident)
        return {"status": job.status.value, "response": job.response}

    bridge.job = read_job
    monitor.tick()
    assert monitor.get("meeting")["state"] == "completed"
    assert "validar roles" in rig.messages.get_job(record["job_id"]).response
    monitor.tick()
    assert len(rig.provider.requests) == 1


def test_failed_delivery_requires_republished_marker_before_new_attempt(rig, tmp_path):
    drive, bridge = FakeDrive(), LocalBridge(rig)
    monitor = Monitor(tmp_path / "inbox", drive, bridge)
    monitor.tick()
    original = monitor.get("meeting")
    bridge.job = lambda _: {"status": "failed"}
    monitor.tick()
    monitor.tick()
    assert monitor.get("meeting")["state"] == "failed"
    assert len(rig.provider.requests) == 1
    # Even identical JSON gets a new Drive version when deliberately uploaded.
    drive.items[READY_NAME]["version"] = "2"
    bridge.job = lambda _: {"status": "running"}
    monitor.tick()
    retried = monitor.get("meeting")
    assert retried["state"] == "running"
    assert retried["session_id"] != original["session_id"]
    assert len(rig.provider.requests) == 2
    monitor.tick()
    assert len(rig.provider.requests) == 2


def test_analysis_mcp_overrides_disable_real_server_names(tmp_path, monkeypatch):
    from backend.app.application.services.meeting_intake_service import analysis_options
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "config.toml").write_text('[mcp_servers.project-catalog]\ncommand="catalog"\n')
    overrides = analysis_options().config_overrides
    assert 'mcp_servers.project-catalog.enabled=false' in overrides
    assert not any('mcp_servers."' in value for value in overrides)


def test_existing_operator_token_file_is_reused_without_new_secret_variables(tmp_path, monkeypatch):
    token = tmp_path / "google-token.json"
    token.write_text(json.dumps({"client_id": "test-client", "client_secret": "test-secret", "refresh_token": "test-refresh"}))
    env = {"GOOGLE_DRIVE_TOKEN_FILE": str(token)}
    assert auth_status(env) == {"ready": True, "source": "configured_token_file", "missing_secret_names": []}
    assert "test-secret" not in json.dumps(auth_status(env))
    assert credentials(env)[0]["refresh_token"] == "test-refresh"
    monkeypatch.setenv("GOOGLE_DRIVE_TOKEN_FILE", str(token))
    for name in ("RELEVAMIENTOS_GOOGLE_TOKEN_FILE", "RELEVAMIENTOS_GOOGLE_CLIENT_ID", "RELEVAMIENTOS_GOOGLE_CLIENT_SECRET", "RELEVAMIENTOS_GOOGLE_REFRESH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    drive = InboxDrive("root", tmp_path / "receipts.json")

    def handle(request):
        assert request.url.host == "oauth2.googleapis.com"
        assert request.method == "POST"
        assert b"refresh_token=test-refresh" in request.content
        return httpx.Response(200, json={"access_token": "test-access"})

    drive.http = httpx.Client(transport=httpx.MockTransport(handle))
    drive.refresh()
    assert drive.token == "test-access"
    assert json.loads(token.read_text())["refresh_token"] == "test-refresh"


def test_project_binding_cannot_be_redirected_by_catalog_change(rig, tmp_path):
    drive, bridge = FakeDrive(), LocalBridge(rig)
    del drive.items[READY_NAME]
    monitor = Monitor(tmp_path / "inbox", drive, bridge)
    monitor.tick()
    bridge.workspaces = lambda: [{"name": "project", "path": str(tmp_path / "other-workspace")}]
    drive.publish()
    monitor.tick()
    assert monitor.get("project:project")["state"] == "project_binding_changed"
    assert not rig.provider.requests


def test_invalid_token_file_reports_only_safe_status(tmp_path):
    token = tmp_path / "broken-token.json"
    token.write_text('{"client_secret":"never-display-this"}')
    status = auth_status({"GOOGLE_DRIVE_TOKEN_FILE": str(token)})
    assert not status["ready"]
    assert "never-display-this" not in json.dumps(status)
