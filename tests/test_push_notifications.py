import hashlib
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.push_notification_routes import install_push_notifications
from backend.app.application.services.push_notification_service import (
    PushNotificationService,
    PushError,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.persistence.sqlite_chat_repository import (
    SqliteChatRepository,
)
from backend.app.domain.entities.chat_session import ChatSession


@pytest.fixture
def service(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    database = tmp_path / "chat.sqlite"
    repo = SqliteChatRepository(
        database_path=str(database), projects_root=str(tmp_path)
    )
    repo.save_session(
        ChatSession(
            id="chat-a",
            title="Chat A",
            workspace_path=str(workspace),
            workspace_name="Project A",
        )
    )
    settings = Settings(
        _env_file=None,
        chat_store_path=str(database),
        projects_root=str(tmp_path),
        pipeline_quality_enabled=False,
    )
    return PushNotificationService(settings)


def device(service, verified=True):
    credential = "a" * 43
    stamp = int(time.time() * 1000)
    with service.connect() as db:
        db.execute(
            "INSERT INTO bridge_push_installations VALUES(?,?,1,?,?,?)",
            (
                "phone",
                hashlib.sha256(credential.encode()).hexdigest(),
                stamp if verified else None,
                stamp,
                stamp,
            ),
        )
    return service.authenticate(credential)


def test_enrollment_only_accepts_private_tailnet_and_no_browser_origin():
    assert PushNotificationService.trusted_network("100.65.0.2")
    assert PushNotificationService.trusted_network("127.0.0.1")
    assert PushNotificationService.trusted_network("fd7a:115c:a1e0::12")
    assert not PushNotificationService.trusted_network("8.8.8.8")
    assert not PushNotificationService.trusted_network(
        "100.65.0.2", "https://evil.example"
    )


def test_revoked_devices_lose_authority_and_queued_pushes(service):
    current = device(service)
    service.revoke(current)
    with pytest.raises(PushError) as exc:
        service.authenticate("a" * 43)
    assert exc.value.status == 401


def test_project_read_does_not_read_other_installations(service):
    current = device(service)
    service.read(current, "chat-a", True)
    with service.connect() as db:
        reads = db.execute("SELECT * FROM bridge_push_reads").fetchall()
    assert len(reads) == 1
    assert reads[0]["installation_id"] == "phone"
    assert reads[0]["resource"].startswith("project:")


def test_logo_discovery_upload_and_path_escape(service, tmp_path):
    workspace = tmp_path / "project"
    (workspace / "assets/branding").mkdir(parents=True)
    original = workspace / "assets/branding/app_icon.png"
    original.write_bytes(b"\x89PNG\r\n\x1a\nexisting")
    assert service.logo("chat-a") == original
    uploaded = b"\xff\xd8\xff" + b"photo"
    service.upload_logo("chat-a", uploaded)
    assert service.logo("chat-a").read_bytes() == uploaded
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside")
    with pytest.raises(PushError):
        service.set_logo("chat-a", "../outside.png")
    with pytest.raises(PushError):
        service.upload_logo("chat-a", b"<svg>not-an-image</svg>")


def test_persistent_rate_limit(service):
    for _ in range(3):
        service.limit("phone:test", 3)
    with pytest.raises(PushError) as exc:
        service.limit("phone:test", 3)
    assert exc.value.status == 429


def test_event_resolution_requires_the_installation_recipient(service):
    current = device(service)
    with pytest.raises(PushError):
        service.event(current, "not-addressed-to-this-device")


def test_public_enrollment_is_rejected_without_echoing_credentials(service):
    app = FastAPI()
    install_push_notifications(app, SimpleNamespace(settings=service.settings))
    client = TestClient(app, client=("8.8.8.8", 12345))
    response = client.post(
        "/notifications/devices",
        headers={"Authorization": "Bearer " + "a" * 43},
        json={
            "installationId": "invalid",
            "token": "private-token",
            "platform": "android",
        },
    )
    assert response.status_code == 403
    assert "private-token" not in response.text


def test_native_configuration_and_invalid_request_are_safe(service):
    app = FastAPI()
    install_push_notifications(app, SimpleNamespace(settings=service.settings))
    client = TestClient(app, client=("100.64.1.2", 12345))
    response = client.get("/notifications/config")
    assert response.status_code == 200
    assert response.json()["configured"] is False
    response = client.post(
        "/notifications/devices",
        json={"installationId": "bad", "token": "hidden", "platform": "android"},
    )
    assert response.status_code == 422
    assert "hidden" not in response.text


def test_device_test_is_queued_without_waiting_for_provider(service, monkeypatch):
    current = device(service, verified=False)

    def provider_unavailable(*args, **kwargs):
        pytest.fail("Request must not wait for worker/provider RPC")

    monkeypatch.setattr(service, "rpc", provider_unavailable)
    result = service.test(current)
    assert result["status"] == "queued"
    with service.connect() as db:
        event = db.execute(
            "SELECT * FROM bridge_push_events WHERE id=?", (result["event_id"],)
        ).fetchone()
    assert event["kind"] == "device.test"
    assert event["installation_id"] == current["id"]
    assert event["expanded_at"] is None
    assert service.authenticate("a" * 43)["verified_at"] is None


def test_logo_resolves_declared_manifest_and_rejects_escape(service, tmp_path):
    import json
    root = tmp_path / "project"
    static = root / "apps/web/static"
    (static / "icons").mkdir(parents=True)
    image = static / "icons/product.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nproduct")
    manifest = static / "manifest.webmanifest"
    manifest.write_text(json.dumps({"icons": [{"src": "/icons/product.png"}]}))
    assert service.logo("chat-a") == image
    manifest.write_text(json.dumps({"icons": [{"src": "../../../../outside.png"}]}))
    (tmp_path / "outside.png").write_bytes(b"outside")
    from backend.app.application.services.project_logo_discovery import discover_project_logo
    assert discover_project_logo(root) is None


def test_logo_catalog_handles_moved_workspace_and_preserves_manual_override(service, tmp_path):
    import json
    with service.connect():
        pass
    service.root = tmp_path / "bridge-source"
    catalog = service.root / "services/notifications/assets/project-logos"
    catalog.mkdir(parents=True)
    own = catalog / "own.png"
    own.write_bytes(b"\x89PNG\r\n\x1a\nreal-app")
    fallback = catalog / "fallback.png"
    fallback.write_bytes(b"\x89PNG\r\n\x1a\nbrand")
    workspace = str((tmp_path / "project").resolve())
    (catalog / "catalog.json").write_text(json.dumps({
        "workspaces": {workspace: {"asset": "own.png", "kind": "application"}},
        "fallback": {"asset": "fallback.png"},
    }))
    assert service.logo("chat-a") == own
    uploaded = b"\xff\xd8\xffchosen"
    service.upload_logo("chat-a", uploaded)
    assert service.logo("chat-a").read_bytes() == uploaded
    with service.connect() as db:
        db.execute("DELETE FROM bridge_project_logos")
    import shutil
    shutil.rmtree(tmp_path / "project")
    assert service.logo("chat-a") == own
    (catalog / "catalog.json").write_text(json.dumps({"fallback": {"asset": "fallback.png"}}))
    assert service.logo("chat-a") == fallback


def test_logo_discovery_does_not_follow_external_static_symlink(service, tmp_path):
    root = tmp_path / "project"
    (root / "apps/web").mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    (external / "logo.png").write_bytes(b"private")
    (external / "manifest.json").write_text('{"icons":[{"src":"/logo.png"}]}')
    (root / "apps/web/static").symlink_to(external, target_is_directory=True)
    from backend.app.application.services.project_logo_discovery import discover_project_logo
    assert discover_project_logo(root) is None
