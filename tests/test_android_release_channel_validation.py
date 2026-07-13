from __future__ import annotations

import json
import subprocess
from pathlib import Path


SCRIPT = Path("scripts/validate_android_release_channel.py")
VERIFY_SCRIPT = Path("scripts/verify_android_release_apk.py")
PUBLISH_SCRIPT = Path("scripts/publish_android_release.sh")


def test_android_release_channel_dry_run_accepts_prod_real_config(
    tmp_path: Path,
) -> None:
    pubspec = tmp_path / "pubspec.yaml"
    registry = tmp_path / "app_updates.json"
    pubspec.write_text("name: codex_mobile\nversion: 1.2.3+4\n", encoding="utf-8")
    registry.write_text(
        json.dumps(
            {
                "codex-mobile": {
                    "releaseChannel": "prod",
                    "releaseTagPattern": "android-v*",
                    "latestAssetName": "codex-mobile.apk",
                    "expectedPackageId": "com.example.codex_mobile_frontend",
                }
            }
        ),
        encoding="utf-8",
    )

    result = _run_validator(
        "--channel",
        "prod",
        "--api-base-url",
        "http://batata-default-string.tail0302c4.ts.net",
        "--app-label",
        "Codex Mobile Bridge",
        "--updater-channel",
        "prod",
        "--environment-color",
        "#55D6BE",
        "--release-tag",
        "android-v1.2.3-build.4",
        "--pubspec",
        str(pubspec),
        "--app-updates-registry",
        str(registry),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["blockers"] == []
    assert payload["evidence"]["published"] is False
    assert payload["evidence"]["expected_dart_defines"]["API_BASE_URL"] == (
        "http://batata-default-string.tail0302c4.ts.net"
    )


def test_android_release_channel_dry_run_rejects_bad_prod_config(
    tmp_path: Path,
) -> None:
    pubspec = tmp_path / "pubspec.yaml"
    pubspec.write_text("name: codex_mobile\nversion: 1.2.3+4\n", encoding="utf-8")

    result = _run_validator(
        "--channel",
        "prod",
        "--api-base-url",
        "http://localhost:8000",
        "--app-label",
        "Codex Mobile Bridge DEV",
        "--updater-channel",
        "dev",
        "--environment-color",
        "blue",
        "--release-tag",
        "android-dev-v1.2.3",
        "--pubspec",
        str(pubspec),
        "--app-updates-registry",
        str(tmp_path / "missing.json"),
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert {
        "missing_app_updates_registry",
        "invalid_environment_color",
        "prod_api_cannot_be_mock_demo_or_local",
        "invalid_prod_updater_channel",
        "invalid_prod_app_label",
        "invalid_release_tag",
    } <= set(payload["blockers"])
    assert payload["evidence"]["published"] is False


def test_android_release_channel_dry_run_accepts_dev_config(
    tmp_path: Path,
) -> None:
    pubspec = tmp_path / "pubspec.yaml"
    registry = tmp_path / "app_updates.json"
    pubspec.write_text("name: codex_mobile\nversion: 1.2.3+4\n", encoding="utf-8")
    registry.write_text(
        json.dumps(
            {
                "codex-mobile-dev": {
                    "releaseChannel": "dev",
                    "releaseTagPattern": "android-dev-v*",
                    "latestAssetName": "codex-mobile-dev.apk",
                    "expectedPackageId": "com.example.codex_mobile_frontend.dev",
                }
            }
        ),
        encoding="utf-8",
    )

    result = _run_validator(
        "--channel",
        "dev",
        "--api-base-url",
        "http://batata-default-string.tail0302c4.ts.net:8118",
        "--app-label",
        "Codex Mobile Bridge DEV",
        "--updater-channel",
        "dev",
        "--environment-color",
        "#38BDF8",
        "--release-tag",
        "android-dev-v1.2.3-build.4",
        "--pubspec",
        str(pubspec),
        "--app-updates-registry",
        str(registry),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["blockers"] == []
    assert payload["evidence"]["expected_dart_defines"]["BRIDGE_APP_CHANNEL"] == "dev"
    assert (
        payload["evidence"]["expected_dart_defines"]["BRIDGE_UPDATER_CHANNEL"]
        == "dev"
    )


def test_android_release_channel_rejects_local_or_mock_urls(
    tmp_path: Path,
) -> None:
    pubspec = tmp_path / "pubspec.yaml"
    registry = tmp_path / "app_updates.json"
    pubspec.write_text("name: codex_mobile\nversion: 1.2.3+4\n", encoding="utf-8")
    registry.write_text(
        json.dumps(
            {
                "codex-mobile": {
                    "releaseChannel": "prod",
                    "releaseTagPattern": "android-v*",
                    "latestAssetName": "codex-mobile.apk",
                    "expectedPackageId": "com.example.codex_mobile_frontend",
                },
                "codex-mobile-dev": {
                    "releaseChannel": "dev",
                    "releaseTagPattern": "android-dev-v*",
                    "latestAssetName": "codex-mobile-dev.apk",
                    "expectedPackageId": "com.example.codex_mobile_frontend.dev",
                },
            }
        ),
        encoding="utf-8",
    )

    prod = _run_validator(
        "--channel",
        "prod",
        "--api-base-url",
        "http://localhost:8000",
        "--app-label",
        "Codex Mobile Bridge",
        "--updater-channel",
        "prod",
        "--environment-color",
        "#55D6BE",
        "--release-tag",
        "android-v1.2.3-build.4",
        "--pubspec",
        str(pubspec),
        "--app-updates-registry",
        str(registry),
    )
    dev = _run_validator(
        "--channel",
        "dev",
        "--api-base-url",
        "https://mock.example.invalid",
        "--app-label",
        "Codex Mobile Bridge DEV",
        "--updater-channel",
        "dev",
        "--environment-color",
        "#38BDF8",
        "--release-tag",
        "android-dev-v1.2.3-build.4",
        "--pubspec",
        str(pubspec),
        "--app-updates-registry",
        str(registry),
    )

    assert prod.returncode == 1
    assert "prod_api_cannot_be_mock_demo_or_local" in json.loads(prod.stdout)[
        "blockers"
    ]
    assert dev.returncode == 1
    assert "dev_api_cannot_be_mock_demo_or_local" in json.loads(dev.stdout)[
        "blockers"
    ]


def test_android_release_channel_rejects_tag_channel_mismatch(
    tmp_path: Path,
) -> None:
    pubspec = tmp_path / "pubspec.yaml"
    registry = tmp_path / "app_updates.json"
    pubspec.write_text("name: codex_mobile\nversion: 1.2.3+4\n", encoding="utf-8")
    registry.write_text(
        json.dumps(
            {
                "codex-mobile-dev": {
                    "releaseChannel": "dev",
                    "releaseTagPattern": "android-dev-v*",
                    "latestAssetName": "codex-mobile-dev.apk",
                    "expectedPackageId": "com.example.codex_mobile_frontend.dev",
                }
            }
        ),
        encoding="utf-8",
    )

    result = _run_validator(
        "--channel",
        "dev",
        "--api-base-url",
        "http://batata-default-string.tail0302c4.ts.net:8118",
        "--app-label",
        "Codex Mobile Bridge DEV",
        "--updater-channel",
        "dev",
        "--environment-color",
        "#38BDF8",
        "--release-tag",
        "android-v1.2.3-build.4",
        "--pubspec",
        str(pubspec),
        "--app-updates-registry",
        str(registry),
    )

    assert result.returncode == 1
    assert "invalid_release_tag" in json.loads(result.stdout)["blockers"]


def test_verify_android_release_apk_checks_output_metadata(tmp_path: Path) -> None:
    apk = tmp_path / "app-dev-release.apk"
    apk.write_bytes(b"fake-apk")
    metadata = tmp_path / "output-metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "applicationId": "com.example.codex_mobile_frontend.dev",
                "variantName": "devRelease",
                "elements": [{"outputFile": "app-dev-release.apk"}],
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            ".venv/bin/python",
            str(VERIFY_SCRIPT),
            "--channel",
            "dev",
            "--apk",
            str(apk),
            "--metadata",
            str(metadata),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["ok"] is True

    metadata.write_text(
        json.dumps(
            {
                "applicationId": "com.example.codex_mobile_frontend",
                "variantName": "prodRelease",
                "elements": [{"outputFile": "app-prod-release.apk"}],
            }
        ),
        encoding="utf-8",
    )
    mismatch = subprocess.run(
        [
            ".venv/bin/python",
            str(VERIFY_SCRIPT),
            "--channel",
            "dev",
            "--apk",
            str(apk),
            "--metadata",
            str(metadata),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert mismatch.returncode == 1
    blockers = set(json.loads(mismatch.stdout)["blockers"])
    assert "metadata_application_id_mismatch" in blockers
    assert "metadata_variant_mismatch" in blockers


def test_publish_script_preflights_before_tag_and_requires_dev_url() -> None:
    script = PUBLISH_SCRIPT.read_text(encoding="utf-8")
    assert script.index("validate_android_release_channel.py") < script.index(
        'git -C "$ROOT_DIR" tag'
    )
    assert "DEV_API_BASE_URL or CODEX_DEV_APP_UPDATER_BRIDGE_URL is required" in script

    result = subprocess.run(
        [
            "env",
            "-u",
            "DEV_API_BASE_URL",
            "-u",
            "CODEX_DEV_APP_UPDATER_BRIDGE_URL",
            "bash",
            str(PUBLISH_SCRIPT),
            "--channel",
            "dev",
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 1
    assert "DEV_API_BASE_URL" in result.stderr


def test_workflow_and_gradle_fail_closed_for_real_release_signing() -> None:
    workflow = Path(".github/workflows/android-release.yml").read_text(
        encoding="utf-8"
    )
    gradle = Path("frontend/mobile_app/android/app/build.gradle.kts").read_text(
        encoding="utf-8"
    )

    assert "Missing required Android release signing secret" in workflow
    assert "using debug signing fallback" not in workflow
    assert "scripts/verify_android_release_apk.py" in workflow
    assert "codex.allowDebugReleaseSigning" in gradle
    assert "throw GradleException" in gradle
    assert 'signingConfigs.getByName("debug")' in gradle


def _run_validator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [".venv/bin/python", str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
