from fastapi.testclient import TestClient
import pytest

from backend.app.application.services.session_file_service import (
    MAX_TEXT_BYTES,
    SessionFileError,
    resolve_session_file,
    session_file_metadata,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.main import create_app


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "project"
    reports = root / "reports"
    reports.mkdir(parents=True)
    (reports / "INFORME.md").write_text(
        "# Informe\n\n[Captura](captura.png)", encoding="utf-8"
    )
    (reports / "captura.png").write_bytes(b"image-bytes")
    (root / "AGENTS.md").write_text("instrucciones", encoding="utf-8")
    return root


@pytest.mark.parametrize(
    "target", ["reports/INFORME.md", "reports/INFORME.md:38", "reports/INFORME.md#L38"]
)
def test_report_and_line_references(workspace, target):
    result = session_file_metadata(str(workspace), target)
    assert result["text"].startswith("# Informe")
    assert result["path"] == "reports/INFORME.md"
    assert result["kind"] == "text"
    assert resolve_session_file(str(workspace), "AGENTS.md:38").name == "AGENTS.md"


def test_absolute_file_uri_and_relative_screenshot(workspace):
    report = workspace / "reports/INFORME.md"
    assert resolve_session_file(str(workspace), report.as_uri()) == report
    result = session_file_metadata(str(workspace), "captura.png", "reports/INFORME.md")
    assert result["kind"] == "image"
    assert result["path"] == "reports/captura.png"
    assert result["text"] is None


@pytest.mark.parametrize(
    "target",
    [
        "../outside.txt",
        "/etc/passwd",
        ".env",
        ".env.prod",
        "secrets/report.md",
        ".git/config",
        "https://example.com/file.md",
    ],
)
def test_denies_private_and_outside_files(workspace, target):
    with pytest.raises(SessionFileError):
        resolve_session_file(str(workspace), target)


def test_symlinks_cannot_escape_or_expose_env(workspace):
    outside = workspace.parent / "outside.txt"
    outside.write_text("private")
    (workspace / "leak.txt").symlink_to(outside)
    (workspace / ".env").write_text("secret")
    (workspace / "alias.txt").symlink_to(workspace / ".env")
    for name in ("leak.txt", "alias.txt"):
        with pytest.raises(SessionFileError):
            resolve_session_file(str(workspace), name)


def test_missing_file_and_bounded_preview(workspace):
    with pytest.raises(SessionFileError) as error:
        resolve_session_file(str(workspace), "missing.md")
    assert error.value.status_code == 404
    (workspace / "large.txt").write_text("a" * (MAX_TEXT_BYTES + 100))
    metadata = session_file_metadata(str(workspace), "large.txt")
    assert metadata["truncated"] is True
    assert len(metadata["text"]) == MAX_TEXT_BYTES


def test_directory_omits_secrets(workspace):
    (workspace / ".env").write_text("secret")
    metadata = session_file_metadata(str(workspace), ".")
    assert metadata["kind"] == "directory"
    assert {entry["name"] for entry in metadata["entries"]} == {"AGENTS.md", "reports"}


def test_session_routes_report_image_download_and_workspace_boundary(workspace):
    settings = Settings(
        codex_command="unused",
        projects_root=str(workspace.parent),
        codex_workdir=str(workspace),
        chat_store_backend="memory",
        audio_transcription_backend="disabled",
        speech_synthesis_backend="disabled",
    )
    with TestClient(create_app(settings)) as client:
        response = client.post("/sessions", json={"workspace_path": str(workspace)})
        assert response.status_code == 201, response.text
        session_id = response.json()["id"]
        url = f"/sessions/{session_id}/files"
        result = client.get(url, params={"path": str(workspace / "reports/INFORME.md")})
        assert result.status_code == 200, result.text
        assert result.json()["kind"] == "text"
        image = client.get(
            url + "/content",
            params={"path": "captura.png", "relative_to": "reports/INFORME.md"},
        )
        assert image.status_code == 200
        assert image.content == b"image-bytes"
        assert image.headers["content-type"] == "image/png"
        assert image.headers["x-content-type-options"] == "nosniff"
        assert "sandbox" in image.headers["content-security-policy"]
        assert client.get(url, params={"path": "../outside.md"}).status_code == 403
        assert client.get(url + "/content", params={"path": ".env"}).status_code == 403
        assert client.get(url, params={"path": "missing.md"}).status_code == 404
        assert (
            client.get(
                "/sessions/unknown/files", params={"path": "reports/INFORME.md"}
            ).status_code
            == 404
        )
