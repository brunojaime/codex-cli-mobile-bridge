from __future__ import annotations

import json
import hashlib
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from backend.app.api.routes import get_container
from backend.app.application.services.app_update_service import (
    AppDisabledError,
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
        "?platform=android&channel=stable"
    )
    assert payload["apkAssetName"] == "ambientando-calendar-1.0.0-build.40.apk"
    assert payload["releaseNotes"] == "Cambios disponibles."


def test_xr18_app_update_uses_android_release_tags(tmp_path: Path) -> None:
    client = _build_app_update_client(
        tmp_path,
        source_app="xr18-mobile-control",
        display_name="XR18 Mobile Control",
        repo="brunojaime/xr18-mobile-control",
        release_tag_pattern="android-v*",
        apk_asset_pattern="xr18-mobile-control-*.apk",
        latest_asset_name="xr18-mobile-control.apk",
        releases=[
            _release(
                "internal-android-v1.0.0-build.99",
                assets=[_apk_asset("xr18-mobile-control-1.0.0-build.99.apk")],
            ),
            _release(
                "android-v1.0.0-build.16",
                assets=[_apk_asset("xr18-mobile-control-1.0.0-build.16.apk")],
            ),
        ],
    )

    response = client.get(
        "/app-updates/xr18-mobile-control",
        params={"currentVersion": "1.0.0", "currentBuild": 15},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sourceApp"] == "xr18-mobile-control"
    assert payload["available"] is True
    assert payload["latestBuild"] == 16
    assert payload["releaseTag"] == "android-v1.0.0-build.16"
    assert payload["apkAssetName"] == "xr18-mobile-control-1.0.0-build.16.apk"


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


def test_default_smart_house_update_registry_is_disabled_until_publishable() -> None:
    registry = AppUpdateRegistry.from_json_file(
        Path(__file__).resolve().parents[1]
        / "backend/app/infrastructure/config/app_updates.json",
    )
    configs = {config.source_app: config for config in registry.list_configs()}

    assert configs["smart-nienfos-smart-house"].enabled is False
    with pytest.raises(AppDisabledError):
        registry.get("smart-nienfos-smart-house")


def test_default_registry_disables_apps_without_apk_backed_releases() -> None:
    registry = AppUpdateRegistry.from_json_file(
        Path(__file__).resolve().parents[1]
        / "backend/app/infrastructure/config/app_updates.json",
    )
    configs = {config.source_app: config for config in registry.list_configs()}

    assert configs["smart-nienfos-smart-house"].enabled is False
    assert configs["ambientando-calendar"].enabled is True
    assert configs["xr18-mobile-control"].enabled is True
    assert configs["gestion-ludmilo"].enabled is True
    assert configs["smart-nienfos-moldegon"].enabled is True


def test_default_registry_resolves_smart_nienfos_admin_from_monorepo_release() -> None:
    registry = AppUpdateRegistry.from_json_file(
        Path(__file__).resolve().parents[1]
        / "backend/app/infrastructure/config/app_updates.json",
    )

    config = registry.get("smart-nienfos-admin")

    assert config.enabled is True
    assert config.repo == "brunojaime/smart_nienfos"
    assert config.release_tag_pattern == "smart-nienfos-admin-android-v*"
    assert config.apk_asset_pattern == "smart-nienfos-admin-*.apk"
    assert config.latest_asset_name == "smart-nienfos-admin.apk"


def test_enabled_default_update_configs_include_release_asset_metadata() -> None:
    registry = AppUpdateRegistry.from_json_file(
        Path(__file__).resolve().parents[1]
        / "backend/app/infrastructure/config/app_updates.json",
    )

    for config in registry.list_configs():
        if not config.enabled:
            continue
        assert "/" in config.repo
        assert config.release_tag_pattern.endswith("*")
        assert config.apk_asset_pattern.endswith(".apk")
        assert config.latest_asset_name is not None
        assert config.latest_asset_name.endswith(".apk")


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
    content = b"PK\x03\x04fake apk"
    github_client = _FakeGitHubReleaseClient(
        [
            _release(
                "android-v1.0.0-build.40",
                assets=[asset],
            ),
        ],
        asset_content=content,
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
    assert response.content == content
    assert (
        hashlib.sha256(response.content).hexdigest()
        == hashlib.sha256(
            content,
        ).hexdigest()
    )
    assert response.headers["content-type"] == "application/vnd.android.package-archive"
    assert response.headers["content-disposition"] == (
        'attachment; filename="ambientando-calendar-1.0.0-build.40.apk"'
    )
    assert response.headers["cache-control"] == "private, max-age=300"
    assert response.headers["content-length"] == str(len(content))
    assert github_client.streamed_assets == [asset]


def test_app_update_apk_proxy_head_returns_metadata_only(tmp_path: Path) -> None:
    asset = _apk_asset("ambientando-calendar-1.0.0-build.40.apk")
    github_client = _FakeGitHubReleaseClient(
        [
            _release(
                "android-v1.0.0-build.40",
                assets=[asset],
            ),
        ],
    )
    client = _build_app_update_client(
        tmp_path,
        releases=github_client,
    )

    response = client.head(
        "/app-updates/ambientando-calendar/apk/"
        "android-v1.0.0-build.40/ambientando-calendar-1.0.0-build.40.apk",
    )

    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["content-type"] == "application/vnd.android.package-archive"
    assert response.headers["content-length"] == "12345"
    assert response.headers["cache-control"] == "private, max-age=300"
    assert github_client.streamed_assets == []


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


@pytest.mark.parametrize(
    "asset_name",
    [
        "missing.apk",
        "..\\secret.apk",
        "..",
        "ambientando-calendar.txt",
    ],
)
def test_app_update_apk_proxy_rejects_invalid_asset_names(
    tmp_path: Path,
    asset_name: str,
) -> None:
    github_client = _FakeGitHubReleaseClient(
        [
            _release(
                "android-v1.0.0-build.40",
                assets=[_apk_asset("ambientando-calendar-1.0.0-build.40.apk")],
            ),
        ],
    )
    client = _build_app_update_client(tmp_path, releases=github_client)

    response = client.get(
        f"/app-updates/ambientando-calendar/apk/android-v1.0.0-build.40/{asset_name}",
    )

    assert response.status_code == 404
    detail = response.json()["detail"]
    if isinstance(detail, dict):
        assert detail["code"] == "apk_asset_not_found"
    assert github_client.streamed_assets == []


def test_app_update_apk_proxy_rejects_unknown_app(tmp_path: Path) -> None:
    client = _build_app_update_client(tmp_path, releases=[])

    response = client.get(
        "/app-updates/unknown-app/apk/android-v1.0.0-build.40/demo.apk",
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "unknown_source_app"


def test_app_update_apk_proxy_rejects_release_without_apk(tmp_path: Path) -> None:
    github_client = _FakeGitHubReleaseClient(
        [
            _release(
                "android-v1.0.0-build.40",
                assets=[GitHubAsset("notes.txt", "https://example.test/notes.txt")],
            ),
        ],
    )
    client = _build_app_update_client(tmp_path, releases=github_client)

    response = client.get(
        "/app-updates/ambientando-calendar/apk/"
        "android-v1.0.0-build.40/ambientando-calendar-1.0.0-build.40.apk",
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "apk_asset_not_found"
    assert github_client.streamed_assets == []


@pytest.mark.parametrize(
    "params",
    [
        {"platform": "ios"},
        {"channel": "nightly"},
    ],
)
def test_app_update_apk_proxy_rejects_invalid_platform_or_channel(
    tmp_path: Path,
    params: dict[str, str],
) -> None:
    client = _build_app_update_client(
        tmp_path,
        releases=[
            _release(
                "android-v1.0.0-build.40",
                assets=[_apk_asset("ambientando-calendar-1.0.0-build.40.apk")],
            ),
        ],
    )

    response = client.get(
        "/app-updates/ambientando-calendar/apk/"
        "android-v1.0.0-build.40/ambientando-calendar-1.0.0-build.40.apk",
        params=params,
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "error",
    [
        GitHubReleaseError("GitHub 401 token SECRET_TOKEN"),
        GitHubReleaseError("GitHub 404 token SECRET_TOKEN"),
        GitHubReleaseError("Timeout token SECRET_TOKEN"),
    ],
)
def test_app_update_apk_proxy_sanitizes_github_errors(
    tmp_path: Path,
    error: GitHubReleaseError,
) -> None:
    client = _build_app_update_client(
        tmp_path,
        releases=_FakeGitHubReleaseClient(
            [
                _release(
                    "android-v1.0.0-build.40",
                    assets=[_apk_asset("ambientando-calendar-1.0.0-build.40.apk")],
                ),
            ],
            stream_error=error,
        ),
    )

    response = client.get(
        "/app-updates/ambientando-calendar/apk/"
        "android-v1.0.0-build.40/ambientando-calendar-1.0.0-build.40.apk",
    )

    body = response.text
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "github_unavailable"
    assert "SECRET_TOKEN" not in body
    assert "GitHub 401" not in body
    assert "GitHub 404" not in body
    assert "Timeout" not in body


def test_app_update_metadata_sanitizes_github_errors(tmp_path: Path) -> None:
    client = _build_app_update_client(
        tmp_path,
        releases=GitHubReleaseError("metadata failed token SECRET_TOKEN"),
    )

    response = client.get("/app-updates/ambientando-calendar")

    body = response.text
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "github_unavailable"
    assert "SECRET_TOKEN" not in body
    assert "metadata failed" not in body


def test_app_update_apk_proxy_double_request_uses_same_configured_asset(
    tmp_path: Path,
) -> None:
    asset = _apk_asset("ambientando-calendar-1.0.0-build.40.apk")
    github_client = _FakeGitHubReleaseClient(
        [
            _release(
                "android-v1.0.0-build.40",
                assets=[asset],
            ),
        ],
    )
    client = _build_app_update_client(tmp_path, releases=github_client)
    url = (
        "/app-updates/ambientando-calendar/apk/"
        "android-v1.0.0-build.40/ambientando-calendar-1.0.0-build.40.apk"
    )

    first = client.get(url)
    second = client.get(url)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.content == second.content
    assert github_client.streamed_assets == [asset, asset]


class _FakeGitHubReleaseClient:
    def __init__(
        self,
        releases: list[GitHubRelease] | GitHubReleaseError,
        *,
        asset_content: bytes = b"PK\x03\x04fake apk",
        stream_error: GitHubReleaseError | None = None,
    ) -> None:
        self._releases = releases
        self._asset_content = asset_content
        self._stream_error = stream_error
        self.requested_repos: list[str] = []
        self.streamed_assets: list[GitHubAsset] = []

    def list_releases(self, repo: str) -> list[GitHubRelease]:
        self.requested_repos.append(repo)
        if isinstance(self._releases, GitHubReleaseError):
            raise self._releases
        return self._releases

    def open_asset_stream(
        self, repo: str, asset: GitHubAsset
    ) -> "_FakeGitHubAssetStream":
        self.requested_repos.append(repo)
        if self._stream_error is not None:
            raise self._stream_error
        self.streamed_assets.append(asset)
        return _FakeGitHubAssetStream(self._asset_content)


class _FakeGitHubAssetStream:
    def __init__(self, content: bytes) -> None:
        self._content = content
        self.closed = False

    @property
    def content_length(self) -> int:
        return len(self._content)

    def iter_bytes(self):
        midpoint = max(1, len(self._content) // 2)
        yield self._content[:midpoint]
        yield self._content[midpoint:]

    def close(self) -> None:
        self.closed = True


def _build_app_update_client(
    tmp_path: Path,
    *,
    releases: list[GitHubRelease] | GitHubReleaseError | _FakeGitHubReleaseClient,
    source_app: str = "ambientando-calendar",
    display_name: str = "Ambientando Calendar",
    repo: str = "brunojaime/ambientando-calendar",
    release_tag_pattern: str = "android-v*",
    apk_asset_pattern: str = "ambientando-calendar-*.apk",
    latest_asset_name: str = "ambientando-calendar.apk",
    enabled: bool = True,
    required_minimum_build: int | None = None,
) -> TestClient:
    registry_path = tmp_path / "app_updates.json"
    registry_path.write_text(
        json.dumps(
            {
                source_app: {
                    "displayName": display_name,
                    "repo": repo,
                    "releaseTagPattern": release_tag_pattern,
                    "apkAssetPattern": apk_asset_pattern,
                    "latestAssetName": latest_asset_name,
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
