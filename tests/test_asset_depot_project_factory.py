from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.infrastructure.config.settings import Settings
from backend.app.main import create_app


def test_asset_depot_upload_list_get_download_and_delete(tmp_path: Path) -> None:
    client = _client(tmp_path)
    content = b"exact-logo-bytes"

    upload = client.post(
        "/assets",
        data={"source": "manual_upload"},
        files={"asset": ("logo.png", content, "image/png")},
    )

    assert upload.status_code == 200
    asset = upload.json()
    assert asset["original_filename"] == "logo.png"
    assert asset["content_type"] == "image/png"
    assert asset["size_bytes"] == len(content)
    assert asset["sha256"] == hashlib.sha256(content).hexdigest()
    assert asset["storage_path"].startswith("files/")

    listed = client.get("/assets")
    assert listed.status_code == 200
    assert listed.json()["assets"][0]["asset_id"] == asset["asset_id"]

    fetched = client.get(f"/assets/{asset['asset_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["sha256"] == asset["sha256"]

    downloaded = client.get(f"/assets/{asset['asset_id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == content

    deleted = client.delete(f"/assets/{asset['asset_id']}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get(f"/assets/{asset['asset_id']}").status_code == 404


def test_asset_depot_rejects_invalid_uploads(tmp_path: Path) -> None:
    client = _client(tmp_path, asset_max_bytes=4)

    bad_mime = client.post(
        "/assets",
        files={"asset": ("logo.exe", b"abc", "application/octet-stream")},
    )
    assert bad_mime.status_code == 422

    traversal = client.post(
        "/assets",
        files={"asset": ("../logo.png", b"abc", "image/png")},
    )
    assert traversal.status_code == 422

    too_large = client.post(
        "/assets",
        files={"asset": ("logo.png", b"abcde", "image/png")},
    )
    assert too_large.status_code == 413


def test_project_factory_promotes_asset_roles_and_preserves_bytes(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    draft_id = _create_draft(client)
    assets = {
        "visual_reference": ("visual.png", b"visual-bytes", "image/png"),
        "exact_asset": ("source.json", b'{"source":true}', "application/json"),
        "logo": ("logo.png", b"logo-bytes", "image/png"),
        "app_icon": ("icon.png", b"icon-bytes", "image/png"),
        "document_context": ("brief.txt", b"context text", "text/plain"),
    }
    uploaded: dict[str, dict[str, object]] = {}
    for role, (filename, content, content_type) in assets.items():
        response = client.post(
            "/assets",
            data={"source": "manual_upload"},
            files={"asset": (filename, content, content_type)},
        )
        assert response.status_code == 200
        uploaded[role] = response.json()
        linked = client.post(
            f"/project-factory/drafts/{draft_id}/assets",
            json={
                "asset_id": response.json()["asset_id"],
                "role": role,
                "notes": f"use as {role}",
            },
        )
        assert linked.status_code == 200
        assert linked.json()["role"] == role

    listed = client.get(f"/project-factory/drafts/{draft_id}/assets")
    assert listed.status_code == 200
    assert {item["role"] for item in listed.json()["assets"]} == set(assets)

    generated = client.post(f"/project-factory/drafts/{draft_id}/generate")
    assert generated.status_code == 200
    project = tmp_path / "asset-depot-demo"
    assert project.is_dir()

    expected_paths = {
        "visual_reference": (
            project / "references/images",
            b"visual-bytes",
        ),
        "exact_asset": (
            project / "assets/source",
            b'{"source":true}',
        ),
        "logo": (
            project / "assets/brand/logo.png",
            b"logo-bytes",
        ),
        "app_icon": (
            project / "assets/brand/app_icon_source.png",
            b"icon-bytes",
        ),
        "document_context": (
            project / "references/documents",
            b"context text",
        ),
    }
    for role, (target, content) in expected_paths.items():
        if target.is_dir():
            matches = list(target.glob(f"{uploaded[role]['asset_id']}*"))
            assert matches, f"missing generated asset for role {role}"
            assert matches[0].read_bytes() == content
        else:
            assert target.read_bytes() == content

    mobile_icon = project / "apps/mobile/assets/brand/app_icon_source.png"
    assert mobile_icon.read_bytes() == b"icon-bytes"
    metadata = (project / "assets/asset-depot-assets.yaml").read_text(
        encoding="utf-8"
    )
    for role, asset in uploaded.items():
        assert role in metadata
        assert str(asset["sha256"]) in metadata
    spec = (project / "specs/001-product-foundation/spec.md").read_text(
        encoding="utf-8"
    )
    assert "Promoted Assets" in spec
    assert str(uploaded["app_icon"]["sha256"]) in spec
    pubspec = (project / "apps/mobile/pubspec.yaml").read_text(encoding="utf-8")
    assert "assets/brand/" in pubspec


def _client(tmp_path: Path, *, asset_max_bytes: int = 25_000_000) -> TestClient:
    settings = Settings(
        projects_root=str(tmp_path),
        chat_store_backend="memory",
        audio_transcription_backend="disabled",
        speech_synthesis_backend="disabled",
        asset_depot_dir=str(tmp_path / ".asset-depot"),
        asset_depot_max_upload_bytes=asset_max_bytes,
        project_factory_reference_asset_dir=str(tmp_path / ".reference-assets"),
        project_factory_state_dir=str(tmp_path / ".factory-state"),
        project_factory_async_jobs=False,
        project_factory_generator_runs_override=0,
        project_factory_reviewer_runs_override=0,
    )
    return TestClient(create_app(settings))


def _create_draft(client: TestClient) -> str:
    response = client.post(
        "/project-factory/drafts",
        json={
            "name": "Asset Depot Demo",
            "businessType": "professional_services",
            "primaryGoal": "Validate promoted assets",
        },
    )
    assert response.status_code == 200
    return str(response.json()["draft_id"])
