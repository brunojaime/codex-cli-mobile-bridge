from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
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


def test_registry_parses_preview_metadata_booleans_explicitly() -> None:
    base = _registry_item(
        productionReady=False,
        mockOrDemo=True,
        runtimeProfile="preview",
        previewUrl="https://preview.nienfos.com/adjornos",
    )

    config = AppUpdateRegistry.from_mapping({"adjornos": base}).get("adjornos")
    assert config.production_ready is False
    assert config.mock_or_demo is True
    assert config.runtime_profile == "preview"
    assert config.preview_url == "https://preview.nienfos.com/adjornos"

    string_config = AppUpdateRegistry.from_mapping(
        {
            "adjornos": _registry_item(
                productionReady="false",
                mockOrDemo="true",
                runtimeProfile="Preview",
                previewUrl="https://preview.nienfos.com/adjornos",
            )
        }
    ).get("adjornos")
    assert string_config.production_ready is False
    assert string_config.mock_or_demo is True
    assert string_config.runtime_profile == "preview"

    with pytest.raises(ValueError, match="productionReady"):
        AppUpdateRegistry.from_mapping(
            {"adjornos": _registry_item(productionReady="nope")}
        )
    with pytest.raises(ValueError, match="mockOrDemo"):
        AppUpdateRegistry.from_mapping({"adjornos": _registry_item(mockOrDemo="")})
    with pytest.raises(ValueError, match="runtimeProfile"):
        AppUpdateRegistry.from_mapping(
            {"adjornos": _registry_item(runtimeProfile="local")}
        )
    with pytest.raises(ValueError, match="previewUrl"):
        AppUpdateRegistry.from_mapping(
            {"adjornos": _registry_item(previewUrl="http://preview.nienfos.com/app")}
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


def test_default_registry_resolves_smart_nienfos_from_flutter_app_release() -> None:
    registry = AppUpdateRegistry.from_json_file(
        Path(__file__).resolve().parents[1]
        / "backend/app/infrastructure/config/app_updates.json",
    )

    config = registry.get("smart-nienfos")

    assert config.enabled is True
    assert config.repo == "brunojaime/smart-nienfos-flutter-app"
    assert config.release_tag_pattern == "android-smart-nienfos-v*"
    assert config.apk_asset_pattern == "smart-nienfos-*.apk"
    assert config.latest_asset_name == "smart-nienfos.apk"
    assert config.expected_package_id == "com.example.client"
    assert (
        config.verified_package_ids["smart-nienfos-admin-android-v1.0.0-build.12"]
        == "com.smartnienfos.admin"
    )
    assert (
        config.verified_package_ids["smart-nienfos-admin-android-v1.0.0-build.13"]
        == "com.example.client"
    )
    assert config.verified_package_ids["android-smart-nienfos-v*"] == (
        "com.example.client"
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


def test_smart_nienfos_discards_package_mismatch_and_chooses_compat_build(
    tmp_path: Path,
) -> None:
    client = _build_app_update_client(
        tmp_path,
        source_app="smart-nienfos",
        display_name="Smart Nienfos Admin",
        repo="brunojaime/smart-nienfos-flutter-app",
        release_tag_pattern="android-smart-nienfos-v*",
        apk_asset_pattern="smart-nienfos-*.apk",
        latest_asset_name="smart-nienfos.apk",
        expected_package_id="com.example.client",
        verified_package_ids={
            "smart-nienfos-admin-android-v1.0.0-build.12": ("com.smartnienfos.admin"),
            "android-smart-nienfos-v*": "com.example.client",
        },
        releases=[
            _release(
                "android-smart-nienfos-v1.0.0-build.14",
                assets=[_apk_asset("smart-nienfos.apk")],
            ),
            _release(
                "smart-nienfos-admin-android-v1.0.0-build.12",
                assets=[_apk_asset("smart-nienfos.apk")],
            ),
        ],
    )

    response = client.get(
        "/app-updates/smart-nienfos",
        params={"currentVersion": "1.0.0", "currentBuild": 11},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["latestBuild"] == 14
    assert payload["releaseTag"] == "android-smart-nienfos-v1.0.0-build.14"
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
                "android-smart-nienfos-v1.0.0-build.12",
                assets=[_apk_asset("smart-nienfos.apk")],
            ),
        ],
    )
    client = _build_app_update_client(
        tmp_path,
        source_app="smart-nienfos",
        display_name="Smart Nienfos Admin",
        repo="brunojaime/smart-nienfos-flutter-app",
        release_tag_pattern="android-smart-nienfos-v*",
        apk_asset_pattern="smart-nienfos-*.apk",
        latest_asset_name="smart-nienfos.apk",
        expected_package_id="com.example.client",
        verified_package_ids={
            "android-smart-nienfos-v1.0.0-build.12": "com.smartnienfos.admin",
        },
        releases=github_client,
    )

    response = client.get(
        "/app-updates/smart-nienfos",
        params={"currentVersion": "1.0.0", "currentBuild": 11},
    )
    proxy_response = client.get(
        "/app-updates/smart-nienfos/apk/"
        "android-smart-nienfos-v1.0.0-build.12/smart-nienfos.apk",
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


def test_installable_apps_lists_available_app_with_bridge_apk_url(
    tmp_path: Path,
) -> None:
    digest = "c" * 64
    client = _build_app_update_client(
        tmp_path,
        expected_package_id="com.ambientando.calendar",
        verified_package_ids={"android-v1.0.0-build.40": "com.ambientando.calendar"},
        releases=[
            _release(
                "android-v1.0.0-build.40",
                assets=[
                    _apk_asset(
                        "ambientando-calendar.apk",
                        digest=f"sha256:{digest}",
                    ),
                ],
            ),
        ],
    )

    response = client.get("/installable-apps")

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "codex.installableApps"
    app = payload["apps"][0]
    assert app["kind"] == "codex.installableApp"
    assert app["sourceApp"] == "ambientando-calendar"
    assert app["displayName"] == "Ambientando Calendar"
    assert app["repo"] == "brunojaime/ambientando-calendar"
    assert app["enabled"] is True
    assert app["available"] is True
    assert app["installStatusHint"] == "available"
    assert app["latestVersion"] == "1.0.0"
    assert app["latestBuild"] == 40
    assert app["releaseTag"] == "android-v1.0.0-build.40"
    assert app["apkAssetName"] == "ambientando-calendar.apk"
    assert app["apkUrl"].startswith("http://testserver/app-updates/")
    assert "github.com" not in app["apkUrl"]
    assert app["sha256"] == digest
    assert app["sizeBytes"] == 12345
    assert app["packageId"] == "com.ambientando.calendar"


def test_installable_app_uses_public_base_url_for_apk_proxy(
    tmp_path: Path,
) -> None:
    client = _build_app_update_client(
        tmp_path,
        app_update_public_base_url="https://bridge.example.test",
        releases=[
            _release(
                "android-v1.0.0-build.40",
                assets=[_apk_asset("ambientando-calendar.apk")],
            ),
        ],
    )

    response = client.get("/installable-apps/ambientando-calendar")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["apkUrl"] == (
        "https://bridge.example.test/app-updates/ambientando-calendar/apk/"
        "android-v1.0.0-build.40/ambientando-calendar.apk"
        "?platform=android&channel=stable"
    )


def test_installable_app_prefers_request_host_for_nonlocal_clients(
    tmp_path: Path,
) -> None:
    client = _build_app_update_client(
        tmp_path,
        app_update_public_base_url="https://bridge.example.test",
        releases=[
            _release(
                "android-v1.0.0-build.40",
                assets=[_apk_asset("ambientando-calendar.apk")],
            ),
        ],
    )

    response = client.get(
        "/installable-apps/ambientando-calendar",
        headers={"host": "100.122.233.6:8000"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["apkUrl"] == (
        "http://100.122.233.6:8000/app-updates/ambientando-calendar/apk/"
        "android-v1.0.0-build.40/ambientando-calendar.apk"
        "?platform=android&channel=stable"
    )


def test_installable_app_detail_returns_single_app(tmp_path: Path) -> None:
    client = _build_app_update_client(
        tmp_path,
        releases=[
            _release(
                "android-v1.0.0-build.40",
                assets=[_apk_asset("ambientando-calendar.apk")],
            ),
        ],
    )

    response = client.get("/installable-apps/ambientando-calendar")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sourceApp"] == "ambientando-calendar"
    assert payload["available"] is True
    assert payload["apkUrl"].startswith("http://testserver/app-updates/")


def test_installable_disabled_app_is_visible_without_install(
    tmp_path: Path,
) -> None:
    client = _build_app_update_client(
        tmp_path,
        enabled=False,
        expected_package_id="com.ambientando.calendar",
        releases=[
            _release(
                "android-v1.0.0-build.40",
                assets=[_apk_asset("ambientando-calendar.apk")],
            ),
        ],
    )

    response = client.get("/installable-apps")

    assert response.status_code == 200
    app = response.json()["apps"][0]
    assert app["enabled"] is False
    assert app["available"] is False
    assert app["apkUrl"] is None
    assert app["installStatusHint"] == "disabled"
    assert app["packageId"] == "com.ambientando.calendar"


def test_installable_app_without_release_does_not_break_list(tmp_path: Path) -> None:
    client = _build_app_update_client(tmp_path, releases=[])

    response = client.get("/installable-apps")

    assert response.status_code == 200
    app = response.json()["apps"][0]
    assert app["sourceApp"] == "ambientando-calendar"
    assert app["enabled"] is True
    assert app["available"] is False
    assert app["apkUrl"] is None
    assert app["installStatusHint"] == "no_release_available"


def test_installable_app_release_without_apk_is_visible_without_install(
    tmp_path: Path,
) -> None:
    client = _build_app_update_client(
        tmp_path,
        releases=[
            _release(
                "android-v1.0.0-build.40",
                assets=[
                    GitHubAsset(
                        "release-notes.txt",
                        "https://example.test/release-notes.txt",
                        size=100,
                    )
                ],
            ),
        ],
    )

    response = client.get("/installable-apps")

    assert response.status_code == 200
    app = response.json()["apps"][0]
    assert app["available"] is False
    assert app["apkUrl"] is None
    assert app["releaseTag"] is None
    assert app["installStatusHint"] == "no_release_available"


def test_installable_app_unknown_returns_404(tmp_path: Path) -> None:
    client = _build_app_update_client(tmp_path, releases=[])

    response = client.get("/installable-apps/missing-app")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "unknown_source_app"


def test_installable_app_registration_updates_registry_without_restart(
    tmp_path: Path,
) -> None:
    client = _build_app_update_client(
        tmp_path,
        releases=[
            _release(
                "android-v0.1.0-build.1",
                assets=[_apk_asset("adjornos.apk")],
            ),
        ],
    )

    response = client.post(
        "/installable-apps",
        headers={"Authorization": "Bearer test-registration-token"},
        json={
            "sourceApp": "adjornos",
            "displayName": "Adjornos",
            "repo": "brunojaime/adjornos",
            "releaseTagPattern": "android-v*",
            "apkAssetPattern": "adjornos*.apk",
            "latestAssetName": "adjornos.apk",
            "expectedPackageId": "com.adjornos.app",
            "verifiedPackageIds": {
                "android-v0.1.0-build.1": "com.adjornos.app",
            },
            "previewUrl": "https://preview.nienfos.com/adjornos",
            "runtimeProfile": "preview",
            "productionReady": False,
            "mockOrDemo": False,
            "releaseMetadata": {
                "initialPreviewRelease": True,
                "releaseTagPattern": "android-v*",
            },
            "enabled": True,
        },
    )

    assert response.status_code == 201
    assert response.json()["sourceApp"] == "adjornos"
    registry = json.loads((tmp_path / "app_updates.json").read_text(encoding="utf-8"))
    assert registry["adjornos"]["displayName"] == "Adjornos"
    assert registry["adjornos"]["repo"] == "brunojaime/adjornos"
    assert registry["adjornos"]["previewUrl"] == "https://preview.nienfos.com/adjornos"
    assert registry["adjornos"]["runtimeProfile"] == "preview"
    assert registry["adjornos"]["productionReady"] is False
    assert registry["adjornos"]["mockOrDemo"] is False
    assert registry["adjornos"]["releaseMetadata"]["initialPreviewRelease"] is True

    detail = client.get("/installable-apps/adjornos")

    assert detail.status_code == 200
    app = detail.json()
    assert app["sourceApp"] == "adjornos"
    assert app["displayName"] == "Adjornos"
    assert app["available"] is True
    assert app["apkUrl"].startswith("http://testserver/app-updates/adjornos/apk/")
    assert "github.com" not in app["apkUrl"]
    assert app["packageId"] == "com.adjornos.app"
    assert app["releaseTagPattern"] == "android-v*"
    assert app["apkAssetPattern"] == "adjornos*.apk"
    assert app["latestAssetName"] == "adjornos.apk"
    assert app["previewUrl"] == "https://preview.nienfos.com/adjornos"
    assert app["runtimeProfile"] == "preview"
    assert app["productionReady"] is False
    assert app["mockOrDemo"] is False
    assert app["releaseMetadata"]["initialPreviewRelease"] is True


def test_installable_app_registration_rejects_unsafe_values(tmp_path: Path) -> None:
    client = _build_app_update_client(tmp_path, releases=[])

    bad_source = client.post(
        "/installable-apps",
        headers={"X-Bridge-Registration-Token": "test-registration-token"},
        json={
            "sourceApp": "../adjornos",
            "displayName": "Adjornos",
            "repo": "brunojaime/adjornos",
        },
    )
    bad_repo = client.post(
        "/installable-apps",
        headers={"X-Bridge-Registration-Token": "test-registration-token"},
        json={
            "sourceApp": "adjornos",
            "displayName": "Adjornos",
            "repo": "https://github.com/brunojaime/adjornos",
        },
    )

    assert bad_source.status_code == 400
    assert bad_repo.status_code == 400


def test_installable_app_registration_requires_configured_token(
    tmp_path: Path,
) -> None:
    disabled_client = _build_app_update_client(
        tmp_path / "disabled",
        releases=[],
        registration_token=None,
    )
    enabled_client = _build_app_update_client(
        tmp_path / "enabled",
        releases=[],
        registration_token="expected-token",
    )
    payload = {
        "sourceApp": "adjornos",
        "displayName": "Adjornos",
        "repo": "brunojaime/adjornos",
    }

    disabled = disabled_client.post("/installable-apps", json=payload)
    missing = enabled_client.post("/installable-apps", json=payload)
    invalid = enabled_client.post(
        "/installable-apps",
        headers={"Authorization": "Bearer wrong-token"},
        json=payload,
    )

    assert disabled.status_code == 503
    assert disabled.json()["detail"]["code"] == "installable_app_registration_disabled"
    assert missing.status_code == 401
    assert missing.json()["detail"]["code"] == "missing_registration_token"
    assert invalid.status_code == 403
    assert invalid.json()["detail"]["code"] == "invalid_registration_token"


def test_installable_app_registration_rejects_invalid_metadata(
    tmp_path: Path,
) -> None:
    client = _build_app_update_client(tmp_path, releases=[])
    base_payload = {
        "sourceApp": "adjornos",
        "displayName": "Adjornos",
        "repo": "brunojaime/adjornos",
    }

    invalid_package = client.post(
        "/installable-apps",
        headers={"X-Bridge-Registration-Token": "test-registration-token"},
        json={**base_payload, "expectedPackageId": "bad-package"},
    )
    invalid_asset = client.post(
        "/installable-apps",
        headers={"X-Bridge-Registration-Token": "test-registration-token"},
        json={**base_payload, "latestAssetName": "../app.apk"},
    )
    invalid_pattern = client.post(
        "/installable-apps",
        headers={"X-Bridge-Registration-Token": "test-registration-token"},
        json={**base_payload, "apkAssetPattern": "../*.apk"},
    )
    arbitrary_url = client.post(
        "/installable-apps",
        headers={"X-Bridge-Registration-Token": "test-registration-token"},
        json={**base_payload, "apkUrl": "https://github.com/example/app.apk"},
    )
    invalid_runtime_profile = client.post(
        "/installable-apps",
        headers={"X-Bridge-Registration-Token": "test-registration-token"},
        json={**base_payload, "runtimeProfile": "local"},
    )
    invalid_preview_url = client.post(
        "/installable-apps",
        headers={"X-Bridge-Registration-Token": "test-registration-token"},
        json={**base_payload, "previewUrl": "http://preview.nienfos.com/adjornos"},
    )

    assert invalid_package.status_code == 400
    assert invalid_asset.status_code == 400
    assert invalid_pattern.status_code == 400
    assert arbitrary_url.status_code == 422
    assert invalid_runtime_profile.status_code == 400
    assert invalid_preview_url.status_code == 400


def test_installable_app_registration_is_idempotent_and_updates_metadata(
    tmp_path: Path,
) -> None:
    client = _build_app_update_client(tmp_path, releases=[])
    payload = {
        "sourceApp": "adjornos",
        "displayName": "Adjornos",
        "repo": "brunojaime/adjornos",
        "releaseTagPattern": "android-v*",
        "apkAssetPattern": "adjornos*.apk",
        "latestAssetName": "adjornos.apk",
        "expectedPackageId": "com.adjornos.app",
    }

    first = client.post(
        "/installable-apps",
        headers={"X-Bridge-Registration-Token": "test-registration-token"},
        json=payload,
    )
    second = client.post(
        "/installable-apps",
        headers={"X-Bridge-Registration-Token": "test-registration-token"},
        json=payload,
    )
    updated = client.post(
        "/installable-apps",
        headers={"X-Bridge-Registration-Token": "test-registration-token"},
        json={
            **payload,
            "releaseTagPattern": "android-v1.*",
            "latestAssetName": "adjornos-v2.apk",
        },
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert updated.status_code == 201
    registry = json.loads((tmp_path / "app_updates.json").read_text(encoding="utf-8"))
    assert list(key for key in registry if key == "adjornos") == ["adjornos"]
    assert registry["adjornos"]["releaseTagPattern"] == "android-v1.*"
    assert registry["adjornos"]["latestAssetName"] == "adjornos-v2.apk"


def test_installable_app_registry_file_reload_does_not_require_restart(
    tmp_path: Path,
) -> None:
    client = _build_app_update_client(
        tmp_path,
        releases=[
            _release(
                "android-v0.1.0-build.1",
                assets=[_apk_asset("adjornos.apk")],
            ),
        ],
    )
    registry_path = tmp_path / "app_updates.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["adjornos"] = {
        "displayName": "Adjornos",
        "repo": "brunojaime/adjornos",
        "releaseTagPattern": "android-v*",
        "apkAssetPattern": "adjornos*.apk",
        "latestAssetName": "adjornos.apk",
        "expectedPackageId": "com.adjornos.app",
        "verifiedPackageIds": {
            "android-v0.1.0-build.1": "com.adjornos.app",
        },
        "requiredMinimumBuild": None,
        "enabled": True,
    }
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    response = client.get("/installable-apps/adjornos")

    assert response.status_code == 200
    assert response.json()["sourceApp"] == "adjornos"
    assert response.json()["available"] is True


def test_installable_app_registry_recovers_from_corrupt_json_on_register(
    tmp_path: Path,
) -> None:
    client = _build_app_update_client(tmp_path, releases=[])
    registry_path = tmp_path / "app_updates.json"
    registry_path.write_text("{not-json", encoding="utf-8")

    response = client.post(
        "/installable-apps",
        headers={"X-Bridge-Registration-Token": "test-registration-token"},
        json={
            "sourceApp": "adjornos",
            "displayName": "Adjornos",
            "repo": "brunojaime/adjornos",
        },
    )

    assert response.status_code == 201
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert "adjornos" in registry
    backups = list(tmp_path.glob("app_updates.json.corrupt.*"))
    assert backups


def test_installable_app_registration_handles_basic_concurrency(
    tmp_path: Path,
) -> None:
    client = _build_app_update_client(tmp_path, releases=[])

    def register(source_app: str) -> int:
        response = client.post(
            "/installable-apps",
            headers={"X-Bridge-Registration-Token": "test-registration-token"},
            json={
                "sourceApp": source_app,
                "displayName": source_app.title(),
                "repo": f"brunojaime/{source_app}",
            },
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(register, ["adjornos-a", "adjornos-b"]))

    assert statuses == [201, 201]
    registry = json.loads((tmp_path / "app_updates.json").read_text(encoding="utf-8"))
    assert "adjornos-a" in registry
    assert "adjornos-b" in registry


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
    registration_token: str | None = "test-registration-token",
    app_update_public_base_url: str | None = None,
) -> TestClient:
    tmp_path.mkdir(parents=True, exist_ok=True)
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
        installable_apps_registration_token=registration_token,
        app_update_public_base_url=app_update_public_base_url,
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
        registry_path=registry_path,
    )
    return TestClient(app)


def _registry_item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "displayName": "Adjornos",
        "repo": "brunojaime/adjornos",
        "releaseTagPattern": "android-preview-v*",
        "apkAssetPattern": "adjornos*.apk",
        "latestAssetName": "adjornos.apk",
        "requiredMinimumBuild": None,
        "releaseChannel": "prerelease",
        "expectedPackageId": None,
        "verifiedPackageIds": {},
        "enabled": True,
    }
    item.update(overrides)
    return item


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
