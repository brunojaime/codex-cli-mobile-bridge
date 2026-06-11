from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from backend.app.api.routes import get_container
from backend.app.application.services.app_update_service import (
    AppUpdateRegistry,
    AppUpdateService,
    GitHubAsset,
    GitHubRelease,
    GitHubReleaseError,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.main import create_app


def test_known_app_with_newer_release_returns_update(tmp_path: Path) -> None:
    client = _build_app_update_client(
        tmp_path,
        releases=[
            _release(
                "android-v1.0.0-build.40",
                assets=[
                    _apk_asset("ambientando-calendar-1.0.0-build.40.apk"),
                ],
                body="Cambios disponibles.",
            ),
        ],
    )

    response = client.get(
        "/app-updates/ambientando-calendar",
        params={"currentVersion": "1.0.0", "currentBuild": 39},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "codex.appUpdate"
    assert payload["sourceApp"] == "ambientando-calendar"
    assert payload["available"] is True
    assert payload["required"] is False
    assert payload["latestVersion"] == "1.0.0"
    assert payload["latestBuild"] == 40
    assert payload["apkUrl"] == (
        "http://testserver/app-updates/ambientando-calendar/apk/"
        "android-v1.0.0-build.40/ambientando-calendar-1.0.0-build.40.apk"
    )
    assert payload["apkAssetName"] == "ambientando-calendar-1.0.0-build.40.apk"
    assert payload["releaseNotes"] == "Cambios disponibles."


def test_known_app_with_same_build_is_up_to_date(tmp_path: Path) -> None:
    client = _build_app_update_client(
        tmp_path,
        releases=[
            _release(
                "android-v1.0.0-build.40",
                assets=[_apk_asset("ambientando-calendar.apk")],
            ),
        ],
    )

    response = client.get(
        "/app-updates/ambientando-calendar",
        params={"currentVersion": "1.0.0", "currentBuild": 40},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["latestBuild"] == 40
    assert payload["apkUrl"] is None


def test_unknown_app_returns_404(tmp_path: Path) -> None:
    client = _build_app_update_client(tmp_path, releases=[])

    response = client.get("/app-updates/unknown-app")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "unknown_source_app"


def test_disabled_app_returns_no_update(tmp_path: Path) -> None:
    client = _build_app_update_client(
        tmp_path,
        releases=[
            _release("android-v1.0.0-build.40", assets=[_apk_asset("demo.apk")]),
        ],
        enabled=False,
    )

    response = client.get(
        "/app-updates/ambientando-calendar",
        params={"currentVersion": "1.0.0", "currentBuild": 39},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["required"] is False
    assert payload["latestBuild"] == 39


def test_release_without_apk_asset_is_ignored(tmp_path: Path) -> None:
    client = _build_app_update_client(
        tmp_path,
        releases=[
            _release(
                "android-v1.0.0-build.40",
                assets=[GitHubAsset("notes.txt", "https://example.test/notes.txt")],
            ),
        ],
    )

    response = client.get(
        "/app-updates/ambientando-calendar",
        params={"currentVersion": "1.0.0", "currentBuild": 39},
    )

    assert response.status_code == 200
    assert response.json()["available"] is False


def test_drafts_prereleases_and_invalid_assets_are_ignored(tmp_path: Path) -> None:
    client = _build_app_update_client(
        tmp_path,
        releases=[
            _release(
                "android-v1.0.0-build.50",
                assets=[_apk_asset("ambientando-calendar-1.0.0-build.50.apk")],
                draft=True,
            ),
            _release(
                "android-v1.0.0-build.49",
                assets=[_apk_asset("ambientando-calendar-1.0.0-build.49.apk")],
                prerelease=True,
            ),
            _release(
                "android-v1.0.0-build.48",
                assets=[GitHubAsset("wrong-app.apk", "https://example.test/wrong.apk")],
            ),
            _release(
                "android-v1.0.0-build.47",
                assets=[_apk_asset("ambientando-calendar-1.0.0-build.47.apk")],
            ),
        ],
    )

    response = client.get(
        "/app-updates/ambientando-calendar",
        params={"currentVersion": "1.0.0", "currentBuild": 39},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["latestBuild"] == 47
    assert payload["releaseTag"] == "android-v1.0.0-build.47"


def test_multiple_releases_choose_highest_valid_build(tmp_path: Path) -> None:
    client = _build_app_update_client(
        tmp_path,
        releases=[
            _release(
                "android-v1.0.0-build.40",
                assets=[_apk_asset("ambientando-calendar-1.0.0-build.40.apk")],
            ),
            _release(
                "android-v1.0.0-build.42",
                assets=[GitHubAsset("notes.txt", "https://example.test/notes.txt")],
            ),
            _release(
                "android-v1.0.0-build.41",
                assets=[_apk_asset("ambientando-calendar-1.0.0-build.41.apk")],
            ),
        ],
    )

    response = client.get(
        "/app-updates/ambientando-calendar",
        params={"currentVersion": "1.0.0", "currentBuild": 39},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["latestBuild"] == 41
    assert payload["releaseTag"] == "android-v1.0.0-build.41"


def test_required_update_when_current_build_below_minimum(tmp_path: Path) -> None:
    client = _build_app_update_client(
        tmp_path,
        releases=[
            _release(
                "android-v1.0.0-build.41",
                assets=[_apk_asset("ambientando-calendar-1.0.0-build.41.apk")],
            ),
        ],
        required_minimum_build=40,
    )

    response = client.get(
        "/app-updates/ambientando-calendar",
        params={"currentVersion": "1.0.0", "currentBuild": 38},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["required"] is True


def test_github_failure_returns_stable_error_response(tmp_path: Path) -> None:
    client = _build_app_update_client(
        tmp_path,
        releases=GitHubReleaseError("GitHub unavailable"),
    )

    response = client.get("/app-updates/ambientando-calendar")

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "github_unavailable"


def test_checksum_digest_is_surfaced_when_available(tmp_path: Path) -> None:
    digest = "a" * 64
    client = _build_app_update_client(
        tmp_path,
        releases=[
            _release(
                "android-v1.0.0-build.40",
                assets=[
                    _apk_asset(
                        "ambientando-calendar-1.0.0-build.40.apk",
                        digest=f"sha256:{digest}",
                    ),
                ],
            ),
        ],
    )

    response = client.get(
        "/app-updates/ambientando-calendar",
        params={"currentVersion": "1.0.0", "currentBuild": 39},
    )

    assert response.status_code == 200
    assert response.json()["sha256"] == digest


def test_sha256_asset_is_preferred_over_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sha_asset_digest = "b" * 64
    github_digest = "a" * 64
    monkeypatch.setattr(
        "backend.app.application.services.app_update_service.download_checksum_asset",
        lambda _url: sha_asset_digest,
    )
    client = _build_app_update_client(
        tmp_path,
        releases=[
            _release(
                "android-v1.0.0-build.40",
                assets=[
                    _apk_asset(
                        "ambientando-calendar-1.0.0-build.40.apk",
                        digest=f"sha256:{github_digest}",
                    ),
                    GitHubAsset(
                        "ambientando-calendar-1.0.0-build.40.apk.sha256",
                        "https://example.test/app.apk.sha256",
                    ),
                ],
            ),
        ],
    )

    response = client.get(
        "/app-updates/ambientando-calendar",
        params={"currentVersion": "1.0.0", "currentBuild": 39},
    )

    assert response.status_code == 200
    assert response.json()["sha256"] == sha_asset_digest


def test_app_updates_lists_configured_apps_without_repo_secrets(tmp_path: Path) -> None:
    client = _build_app_update_client(tmp_path, releases=[])

    response = client.get("/app-updates")

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "codex.appUpdateRegistry"
    assert payload["apps"][0]["sourceApp"] == "ambientando-calendar"
    assert "repo" not in payload["apps"][0]
    assert "github" not in json.dumps(payload).lower()


def test_app_update_apk_url_is_bridge_proxy_not_github(tmp_path: Path) -> None:
    client = _build_app_update_client(
        tmp_path,
        releases=[
            _release(
                "android-v1.0.0-build.40",
                assets=[
                    _apk_asset("ambientando-calendar-1.0.0-build.40.apk"),
                ],
            ),
        ],
    )

    response = client.get(
        "/app-updates/ambientando-calendar",
        params={"currentVersion": "1.0.0", "currentBuild": 39},
    )

    assert response.status_code == 200
    apk_url = response.json()["apkUrl"]
    assert apk_url.startswith("http://testserver/app-updates/")
    assert "github.com" not in apk_url


def test_app_update_apk_proxy_downloads_private_asset(tmp_path: Path) -> None:
    asset = _apk_asset("ambientando-calendar-1.0.0-build.40.apk")
    github_client = _FakeGitHubReleaseClient(
        [
            _release(
                "android-v1.0.0-build.40",
                assets=[asset],
            ),
        ],
        asset_content=b"PK\x03\x04fake apk",
    )
    client = _build_app_update_client(
        tmp_path,
        releases=github_client,
    )

    response = client.get(
        "/app-updates/ambientando-calendar/apk/"
        "android-v1.0.0-build.40/ambientando-calendar-1.0.0-build.40.apk",
    )

    assert response.status_code == 200
    assert response.content == b"PK\x03\x04fake apk"
    assert response.headers["content-type"] == "application/vnd.android.package-archive"
    assert github_client.downloaded_assets == [asset]


def test_app_update_apk_proxy_rejects_non_apk_asset(tmp_path: Path) -> None:
    client = _build_app_update_client(
        tmp_path,
        releases=_FakeGitHubReleaseClient(
            [
                _release(
                    "android-v1.0.0-build.40",
                    assets=[_apk_asset("ambientando-calendar-1.0.0-build.40.apk")],
                ),
            ],
            asset_content=b"not an apk",
        ),
    )

    response = client.get(
        "/app-updates/ambientando-calendar/apk/"
        "android-v1.0.0-build.40/ambientando-calendar-1.0.0-build.40.apk",
    )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "github_unavailable"


class _FakeGitHubReleaseClient:
    def __init__(
        self,
        releases: list[GitHubRelease] | GitHubReleaseError,
        *,
        asset_content: bytes = b"PK\x03\x04fake apk",
    ) -> None:
        self._releases = releases
        self._asset_content = asset_content
        self.requested_repos: list[str] = []
        self.downloaded_assets: list[GitHubAsset] = []

    def list_releases(self, repo: str) -> list[GitHubRelease]:
        self.requested_repos.append(repo)
        if isinstance(self._releases, GitHubReleaseError):
            raise self._releases
        return self._releases

    def download_asset(self, repo: str, asset: GitHubAsset) -> bytes:
        self.requested_repos.append(repo)
        self.downloaded_assets.append(asset)
        return self._asset_content


def _build_app_update_client(
    tmp_path: Path,
    *,
    releases: list[GitHubRelease] | GitHubReleaseError | _FakeGitHubReleaseClient,
    enabled: bool = True,
    required_minimum_build: int | None = None,
) -> TestClient:
    registry_path = tmp_path / "app_updates.json"
    registry_path.write_text(
        json.dumps(
            {
                "ambientando-calendar": {
                    "displayName": "Ambientando Calendar",
                    "repo": "brunojaime/ambientando-calendar",
                    "releaseTagPattern": "android-v*",
                    "apkAssetPattern": "ambientando-calendar-*.apk",
                    "latestAssetName": "ambientando-calendar.apk",
                    "requiredMinimumBuild": required_minimum_build,
                    "enabled": enabled,
                }
            },
        ),
        encoding="utf-8",
    )
    settings = Settings(
        chat_store_backend="memory",
        audio_transcription_backend="disabled",
        app_update_registry_path=str(registry_path),
    )
    app = create_app(settings)
    container = app.dependency_overrides[get_container]()
    release_client = (
        releases
        if isinstance(releases, _FakeGitHubReleaseClient)
        else _FakeGitHubReleaseClient(releases)
    )
    container.app_update_service = AppUpdateService(
        registry=AppUpdateRegistry.from_json_file(registry_path),
        release_client=release_client,
    )
    return TestClient(app)


def _release(
    tag_name: str,
    *,
    assets: list[GitHubAsset],
    body: str | None = None,
    draft: bool = False,
    prerelease: bool = False,
) -> GitHubRelease:
    return GitHubRelease(
        tag_name=tag_name,
        html_url=f"https://github.com/example/repo/releases/tag/{tag_name}",
        body=body,
        draft=draft,
        prerelease=prerelease,
        assets=tuple(assets),
    )


def _apk_asset(name: str, *, digest: str | None = None) -> GitHubAsset:
    return GitHubAsset(
        name=name,
        browser_download_url=f"https://github.com/example/repo/releases/download/tag/{name}",
        size=12345,
        digest=digest,
    )
