from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

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


def test_app_updates_lists_configured_apps_without_repo_secrets(tmp_path: Path) -> None:
    client = _build_app_update_client(tmp_path, releases=[])

    response = client.get("/app-updates")

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "codex.appUpdateRegistry"
    assert payload["apps"][0]["sourceApp"] == "ambientando-calendar"
    assert "repo" not in payload["apps"][0]
    assert "github" not in json.dumps(payload).lower()


class _FakeGitHubReleaseClient:
    def __init__(self, releases: list[GitHubRelease] | GitHubReleaseError) -> None:
        self._releases = releases
        self.requested_repos: list[str] = []

    def list_releases(self, repo: str) -> list[GitHubRelease]:
        self.requested_repos.append(repo)
        if isinstance(self._releases, GitHubReleaseError):
            raise self._releases
        return self._releases


def _build_app_update_client(
    tmp_path: Path,
    *,
    releases: list[GitHubRelease] | GitHubReleaseError,
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
    container.app_update_service = AppUpdateService(
        registry=AppUpdateRegistry.from_json_file(registry_path),
        release_client=_FakeGitHubReleaseClient(releases),
    )
    return TestClient(app)


def _release(
    tag_name: str,
    *,
    assets: list[GitHubAsset],
    body: str | None = None,
) -> GitHubRelease:
    return GitHubRelease(
        tag_name=tag_name,
        html_url=f"https://github.com/example/repo/releases/tag/{tag_name}",
        body=body,
        draft=False,
        prerelease=False,
        assets=tuple(assets),
    )


def _apk_asset(name: str, *, digest: str | None = None) -> GitHubAsset:
    return GitHubAsset(
        name=name,
        browser_download_url=f"https://github.com/example/repo/releases/download/tag/{name}",
        size=12345,
        digest=digest,
    )
