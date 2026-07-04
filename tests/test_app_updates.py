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


def test_api_v1_prefix_serves_health_update_and_apk_proxy(tmp_path: Path) -> None:
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
    client = _build_app_update_client(tmp_path, releases=github_client)

    health_response = client.get("/api/v1/health")
    update_response = client.get(
        "/api/v1/app-updates/ambientando-calendar",
        params={"currentVersion": "1.0.0", "currentBuild": 39},
    )
    apk_response = client.head(
        "/api/v1/app-updates/ambientando-calendar/apk/"
        "android-v1.0.0-build.40/ambientando-calendar-1.0.0-build.40.apk",
    )

    assert health_response.status_code == 200
    assert update_response.status_code == 200
    assert update_response.json()["apkUrl"].startswith(
        "http://testserver/api/v1/app-updates/"
    )
    assert apk_response.status_code == 200
    assert apk_response.headers["content-type"] == (
        "application/vnd.android.package-archive"
    )


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


def test_default_registry_accepts_latest_ambientando_release_package_id() -> None:
    registry = AppUpdateRegistry.from_json_file(
        Path(__file__).resolve().parents[1]
        / "backend/app/infrastructure/config/app_updates.json",
    )

    config = registry.get("ambientando-calendar")

    assert config.expected_package_id == "com.ambientando.calendar"
    assert config.release_tag_pattern == "android-*-feedback-v*"
    assert (
        config.verified_package_ids["android-local-demo-feedback-v*"]
        == "com.ambientando.calendar"
    )
    assert (
        config.verified_package_ids["android-prod-feedback-v*"]
        == "com.ambientando.calendar"
    )


def test_default_registry_includes_sat_catalog_updates() -> None:
    registry = AppUpdateRegistry.from_json_file(
        Path(__file__).resolve().parents[1]
        / "backend/app/infrastructure/config/app_updates.json",
    )

    config = registry.get("sat-catalogo-ropa")

    assert config.enabled is True
    assert config.display_name == "SAT Catalogo Ropa"
    assert config.repo == "brunojaime/sat-catalogo-ropa"
    assert config.release_tag_pattern == "android-feedback*-v*"
    assert config.apk_asset_pattern == "sat-catalogo-ropa*.apk"
    assert config.latest_asset_name == "sat-catalogo-ropa.apk"
    assert config.expected_package_id == "com.sat.sat_catalogo_ropa"
    assert (
        config.verified_package_ids["android-feedback*-v*"]
        == "com.sat.sat_catalogo_ropa"
    )


def test_sat_catalog_app_update_returns_latest_feedback_release(
    tmp_path: Path,
) -> None:
    asset_name = "sat-catalogo-ropa.apk"
    asset_digest = (
        "sha256:78795fd8e81bd89755e03c9f4393ad5ce673741a8f74b71562367a9ad65e2751"
    )
    client = _build_app_update_client(
        tmp_path,
        source_app="sat-catalogo-ropa",
        display_name="SAT Catalogo Ropa",
        repo="brunojaime/sat-catalogo-ropa",
        release_tag_pattern="android-feedback*-v*",
        apk_asset_pattern="sat-catalogo-ropa*.apk",
        latest_asset_name=asset_name,
        expected_package_id="com.sat.sat_catalogo_ropa",
        verified_package_ids={
            "android-feedback*-v*": "com.sat.sat_catalogo_ropa",
        },
        releases=[
            _release(
                "android-feedback-updater-v1.0.4-build.5",
                assets=[_apk_asset(asset_name, digest=asset_digest)],
                body="SAT feedback release.",
            ),
        ],
    )

    response = client.get(
        "/app-updates/sat-catalogo-ropa",
        params={"currentVersion": "1.0.3", "currentBuild": 4},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sourceApp"] == "sat-catalogo-ropa"
    assert payload["available"] is True
    assert payload["latestVersion"] == "1.0.4"
    assert payload["latestBuild"] == 5
    assert payload["releaseTag"] == "android-feedback-updater-v1.0.4-build.5"
    assert payload["apkAssetName"] == asset_name
    assert (
        payload["sha256"]
        == "78795fd8e81bd89755e03c9f4393ad5ce673741a8f74b71562367a9ad65e2751"
    )
    assert payload["packageId"] == "com.sat.sat_catalogo_ropa"
    assert payload["releaseNotes"] == "SAT feedback release."
    assert payload["apkUrl"] == (
        "http://testserver/app-updates/sat-catalogo-ropa/apk/"
        "android-feedback-updater-v1.0.4-build.5/"
        "sat-catalogo-ropa.apk"
        "?platform=android&channel=stable"
    )


def test_default_registry_resolves_smart_nienfos_admin_from_flutter_app_release() -> None:
    registry = AppUpdateRegistry.from_json_file(
        Path(__file__).resolve().parents[1]
        / "backend/app/infrastructure/config/app_updates.json",
    )

    config = registry.get("smart-nienfos-admin")

    assert config.enabled is True
    assert config.repo == "brunojaime/smart-nienfos-flutter-app"
    assert config.release_tag_pattern == "smart-nienfos-admin-android-v*"
    assert config.apk_asset_pattern == "smart-nienfos-admin-*.apk"
    assert config.latest_asset_name == "smart-nienfos-admin.apk"
    assert config.expected_package_id == "com.example.client"
    assert (
        config.verified_package_ids[
            "smart-nienfos-admin-android-v1.0.0-build.12"
        ]
        == "com.smartnienfos.admin"
    )
    assert (
        config.verified_package_ids[
            "smart-nienfos-admin-android-v1.0.0-build.13"
        ]
        == "com.example.client"
    )


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
        if config.expected_package_id is not None:
            assert config.verified_package_ids


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


def test_private_install_config_returns_prerelease_update_by_default(
    tmp_path: Path,
) -> None:
    package_id = "com.smartnienfos.molding.molding_operator_app"
    client = _build_app_update_client(
        tmp_path,
        source_app="smart-nienfos-moldegon",
        display_name="Moldegon",
        repo="brunojaime/smart_nienfos",
        release_tag_pattern="moldegon-android-v*",
        apk_asset_pattern="smart-nienfos-moldegon-*.apk",
        latest_asset_name="smart-nienfos-moldegon.apk",
        release_channel="private-install",
        expected_package_id=package_id,
        verified_package_ids={
            "moldegon-android-v1.0.0-build.8": package_id,
        },
        releases=[
            _release(
                "moldegon-android-v1.0.0-build.8",
                assets=[_apk_asset("smart-nienfos-moldegon.apk")],
                prerelease=True,
            ),
        ],
    )

    response = client.get(
        "/app-updates/smart-nienfos-moldegon",
        params={"currentVersion": "1.0.0", "currentBuild": 7},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["latestBuild"] == 8
    assert payload["releaseTag"] == "moldegon-android-v1.0.0-build.8"
    assert payload["releaseChannel"] == "private-install"
    assert payload["releasePrerelease"] is True
    assert payload["privateInstall"] is True
    assert payload["packageId"] == package_id
    assert payload["apkUrl"] == (
        "http://testserver/app-updates/smart-nienfos-moldegon/apk/"
        "moldegon-android-v1.0.0-build.8/smart-nienfos-moldegon.apk"
        "?platform=android&channel=private-install"
    )


def test_smart_admin_discards_package_mismatch_and_chooses_compat_build(
    tmp_path: Path,
) -> None:
    client = _build_app_update_client(
        tmp_path,
        source_app="smart-nienfos-admin",
        display_name="Smart Nienfos Admin",
        repo="brunojaime/smart-nienfos-flutter-app",
        release_tag_pattern="smart-nienfos-admin-android-v*",
        apk_asset_pattern="smart-nienfos-admin-*.apk",
        latest_asset_name="smart-nienfos-admin.apk",
        expected_package_id="com.example.client",
        verified_package_ids={
            "smart-nienfos-admin-android-v1.0.0-build.12": (
                "com.smartnienfos.admin"
            ),
            "smart-nienfos-admin-android-v1.0.0-build.13": "com.example.client",
        },
        releases=[
            _release(
                "smart-nienfos-admin-android-v1.0.0-build.13",
                assets=[_apk_asset("smart-nienfos-admin.apk")],
            ),
            _release(
                "smart-nienfos-admin-android-v1.0.0-build.12",
                assets=[_apk_asset("smart-nienfos-admin.apk")],
            ),
        ],
    )

    response = client.get(
        "/app-updates/smart-nienfos-admin",
        params={"currentVersion": "1.0.0", "currentBuild": 11},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["latestBuild"] == 13
    assert payload["releaseTag"] == "smart-nienfos-admin-android-v1.0.0-build.13"
    assert payload["packageId"] == "com.example.client"


def test_package_verification_accepts_release_tag_patterns(tmp_path: Path) -> None:
    client = _build_app_update_client(
        tmp_path,
        source_app="ambientando-calendar",
        display_name="Ambientando Calendar",
        repo="brunojaime/ambientando-calendar",
        release_tag_pattern="android-*-feedback-v*",
        apk_asset_pattern="ambientando-calendar-*.apk",
        latest_asset_name="ambientando-calendar.apk",
        expected_package_id="com.ambientando.calendar",
        verified_package_ids={
            "android-local-demo-feedback-v*": "com.ambientando.calendar",
            "android-prod-feedback-v*": "com.ambientando.calendar",
        },
        releases=[
            _release(
                "android-v1.0.0-build.112",
                assets=[_apk_asset("ambientando-calendar.apk")],
            ),
            _release(
                "android-local-demo-feedback-v1.0.0-build.99",
                assets=[_apk_asset("ambientando-calendar.apk")],
            ),
            _release(
                "android-prod-feedback-v1.0.0-build.100",
                assets=[_apk_asset("ambientando-calendar.apk")],
            ),
        ],
    )

    response = client.get(
        "/app-updates/ambientando-calendar",
        params={"currentVersion": "1.0.0", "currentBuild": 98},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["latestBuild"] == 100
    assert payload["releaseTag"] == "android-prod-feedback-v1.0.0-build.100"
    assert payload["packageId"] == "com.ambientando.calendar"


def test_package_mismatch_release_is_not_offered_or_served(tmp_path: Path) -> None:
    github_client = _FakeGitHubReleaseClient(
        [
            _release(
                "smart-nienfos-admin-android-v1.0.0-build.12",
                assets=[_apk_asset("smart-nienfos-admin.apk")],
            ),
        ],
    )
    client = _build_app_update_client(
        tmp_path,
        source_app="smart-nienfos-admin",
        display_name="Smart Nienfos Admin",
        repo="brunojaime/smart-nienfos-flutter-app",
        release_tag_pattern="smart-nienfos-admin-android-v*",
        apk_asset_pattern="smart-nienfos-admin-*.apk",
        latest_asset_name="smart-nienfos-admin.apk",
        expected_package_id="com.example.client",
        verified_package_ids={
            "smart-nienfos-admin-android-v1.0.0-build.12": (
                "com.smartnienfos.admin"
            ),
        },
        releases=github_client,
    )

    response = client.get(
        "/app-updates/smart-nienfos-admin",
        params={"currentVersion": "1.0.0", "currentBuild": 11},
    )
    proxy_response = client.get(
        "/app-updates/smart-nienfos-admin/apk/"
        "smart-nienfos-admin-android-v1.0.0-build.12/smart-nienfos-admin.apk",
    )

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["latestBuild"] == 11
    assert response.json()["packageId"] is None
    assert proxy_response.status_code == 404
    assert github_client.streamed_assets == []


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
    release_channel: str = "stable",
    expected_package_id: str | None = None,
    verified_package_ids: dict[str, str] | None = None,
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
                    "releaseChannel": release_channel,
                    "expectedPackageId": expected_package_id,
                    "verifiedPackageIds": verified_package_ids or {},
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
