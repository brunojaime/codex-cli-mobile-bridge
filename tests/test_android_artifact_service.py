from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from backend.app.application.services.android_artifact_service import (
    AndroidSigningMaterial,
    AndroidArtifactService,
)


def test_flutter_android_artifact_is_normalized(tmp_path: Path) -> None:
    pubspec = tmp_path / "apps/mobile/pubspec.yaml"
    pubspec.parent.mkdir(parents=True)
    pubspec.write_text("name: neutral\nversion: 1.2.3+47\n", encoding="utf-8")

    artifact = AndroidArtifactService().resolve(
        "flutter", tmp_path, slug="neutral"
    )

    assert artifact.framework == "flutter"
    assert artifact.kind == "android_apk"
    assert artifact.source_app == "neutral"
    assert artifact.package_id == "com.nienfos.neutral"
    assert artifact.version == "1.2.3"
    assert artifact.build_number == 47
    assert artifact.release_tag == "android-preview-v1.2.3-build.47"
    assert artifact.asset_name == "neutral.apk"
    assert artifact.build_command == ("flutter", "build", "apk", "--release")
    assert artifact.build_working_directory == "apps/mobile"


def test_flutter_prepare_build_binds_stable_release_signing(tmp_path: Path) -> None:
    mobile = tmp_path / "apps/mobile"
    android = mobile / "android"
    build_gradle = android / "app/build.gradle.kts"
    build_gradle.parent.mkdir(parents=True)
    (mobile / "pubspec.yaml").write_text(
        "name: neutral\nversion: 1.2.3+4\n", encoding="utf-8"
    )
    build_gradle.write_text(
        "plugins {\n}\n\nandroid {\n    buildTypes {\n        release {\n            signingConfig = signingConfigs.getByName(\"debug\")\n        }\n    }\n}\n",
        encoding="utf-8",
    )
    keystore = tmp_path / "upload.jks"
    keystore.write_bytes(b"keystore")
    service = AndroidArtifactService()
    artifact = service.resolve("flutter", tmp_path, slug="neutral")

    service.prepare_build(
        "flutter",
        tmp_path,
        artifact,
        AndroidSigningMaterial(
            keystore_path=keystore,
            key_alias="preview",
            store_password="store-secret",
            key_password="key-secret",
        ),
    )

    gradle = build_gradle.read_text(encoding="utf-8")
    assert 'create("release")' in gradle
    assert 'signingConfigs.getByName("release")' in gradle
    assert (android / "upload-keystore.jks").read_bytes() == b"keystore"
    assert "storePassword=store-secret" in (android / "key.properties").read_text(
        encoding="utf-8"
    )

    service.cleanup_build("flutter", tmp_path, artifact)

    assert not (android / "key.properties").exists()
    assert not (android / "upload-keystore.jks").exists()


def test_expo_android_artifact_uses_reproducible_gradle_output(tmp_path: Path) -> None:
    mobile = tmp_path / "apps/mobile"
    mobile.mkdir(parents=True)
    (mobile / "package.json").write_text(
        json.dumps({"name": "neutral", "version": "2.4.0"}), encoding="utf-8"
    )
    (mobile / "app.json").write_text(
        json.dumps(
            {
                "expo": {
                    "name": "Neutral",
                    "version": "2.4.0",
                    "android": {
                        "versionCode": 19,
                        "package": "com.nienfos.neutral",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    apk = mobile / "android/app/build/outputs/apk/release/app-release.apk"
    apk.parent.mkdir(parents=True)
    apk.write_bytes(b"apk")

    artifact = AndroidArtifactService().resolve(
        "react_native_expo", tmp_path, slug="neutral"
    )

    assert artifact.framework == "react_native_expo"
    assert artifact.package_id == "com.nienfos.neutral"
    assert artifact.release_tag == "android-preview-v2.4.0-build.19"
    assert artifact.build_command == (
        "./gradlew",
        "assembleRelease",
        "--no-daemon",
    )
    assert artifact.build_working_directory == "apps/mobile/android"
    assert artifact.find_existing(tmp_path) == apk


def test_expo_prepare_build_uses_provider_signing_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mobile = tmp_path / "apps/mobile"
    android = mobile / "android"
    android.mkdir(parents=True)
    (android / "gradlew").write_text("#!/usr/bin/env sh\n", encoding="utf-8")
    (mobile / "package.json").write_text(
        json.dumps({"name": "neutral", "version": "1.0.0"}), encoding="utf-8"
    )
    (mobile / "app.json").write_text(
        json.dumps(
            {
                "expo": {
                    "version": "1.0.0",
                    "android": {
                        "versionCode": 2,
                        "package": "com.nienfos.neutral",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    keystore = tmp_path / "upload.jks"
    keystore.write_bytes(b"keystore")
    sdk = tmp_path / "android-sdk"
    (sdk / "platform-tools").mkdir(parents=True)
    monkeypatch.setenv("ANDROID_HOME", str(sdk))
    service = AndroidArtifactService()
    artifact = service.resolve("react_native_expo", tmp_path, slug="neutral")

    env = service.prepare_build(
        "react_native_expo",
        tmp_path,
        artifact,
        AndroidSigningMaterial(
            keystore_path=keystore,
            key_alias="preview",
            store_password="store-secret",
            key_password="key-secret",
        ),
    )

    assert env["ANDROID_KEYSTORE_PATH"] == str(keystore)
    assert env["ANDROID_KEY_ALIAS"] == "preview"
    assert env["NODE_ENV"] == "production"
    assert env["ANDROID_HOME"] == str(sdk)
    assert env["ANDROID_SDK_ROOT"] == str(sdk)


def test_android_artifact_rejects_unknown_provider(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported"):
        AndroidArtifactService().resolve("fastapi", tmp_path, slug="bad")


@pytest.mark.parametrize("slug", ("../escape", "/absolute", "bad_slug"))
def test_android_artifact_rejects_unsafe_source_app_slug(
    tmp_path: Path,
    slug: str,
) -> None:
    with pytest.raises(ValueError, match="safe project slug"):
        AndroidArtifactService().resolve("flutter", tmp_path, slug=slug)


def test_android_artifact_rejects_candidate_path_escape(tmp_path: Path) -> None:
    pubspec = tmp_path / "apps/mobile/pubspec.yaml"
    pubspec.parent.mkdir(parents=True)
    pubspec.write_text("name: neutral\nversion: 1.0.0+1\n", encoding="utf-8")
    artifact = AndroidArtifactService().resolve("flutter", tmp_path, slug="neutral")
    unsafe = replace(artifact, candidate_paths=("../outside.apk",))

    with pytest.raises(ValueError, match="escapes"):
        unsafe.find_existing(tmp_path)
