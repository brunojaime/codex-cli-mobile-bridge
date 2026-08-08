from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
from typing import Mapping, Protocol

from backend.app.application.services.project_scaffold_providers import (
    resolve_android_sdk_root,
)


def resolve_android_build_tool(
    name: str,
    env: Mapping[str, str] | None = None,
) -> str:
    """Resolve a pinned SDK build-tool when it is not already on PATH."""
    search_path = env.get("PATH") if env else None
    direct = (
        shutil.which(name, path=search_path)
        if search_path is not None
        else shutil.which(name)
    )
    if direct:
        return direct
    sdk_root = resolve_android_sdk_root(env)
    if sdk_root is not None:
        candidates = sorted(
            (path for path in (sdk_root / "build-tools").glob(f"*/{name}") if path.is_file()),
            key=lambda path: tuple(
                int(part) if part.isdigit() else 0
                for part in re.split(r"[.-]", path.parent.name)
            ),
            reverse=True,
        )
        if candidates:
            return str(candidates[0])
    return name


@dataclass(frozen=True, slots=True)
class NormalizedAndroidArtifact:
    kind: str
    source_app: str
    provider: str
    framework: str
    package_id: str
    version: str
    build_number: int
    release_tag: str
    asset_name: str
    build_command: tuple[str, ...]
    build_working_directory: str
    signing_contract: str
    runtime_profile: str
    mock_or_demo: bool
    candidate_paths: tuple[str, ...]

    def find_existing(self, workspace: Path) -> Path | None:
        root = workspace.resolve()
        for relative in self.candidate_paths:
            candidate = (root / relative.format(asset_name=self.asset_name)).resolve()
            if not candidate.is_relative_to(root):
                raise ValueError(
                    "Android artifact output path escapes the project workspace."
                )
            if candidate.is_file():
                return candidate
        return None

    def to_payload(
        self,
        *,
        sha256: str | None = None,
        signing_status: str = "required",
    ) -> dict[str, object]:
        return {
            "kind": self.kind,
            "sourceApp": self.source_app,
            "provider": self.provider,
            "framework": self.framework,
            "packageId": self.package_id,
            "version": self.version,
            "buildNumber": self.build_number,
            "releaseTag": self.release_tag,
            "assetName": self.asset_name,
            "buildCommand": list(self.build_command),
            "buildWorkingDirectory": self.build_working_directory,
            "signingContract": self.signing_contract,
            "signingStatus": signing_status,
            "runtimeProfile": self.runtime_profile,
            "mockOrDemo": self.mock_or_demo,
            "sha256": sha256,
            "candidatePaths": list(self.candidate_paths),
        }


@dataclass(frozen=True, slots=True)
class AndroidSigningMaterial:
    keystore_path: Path
    key_alias: str
    store_password: str
    key_password: str
    store_type: str = "JKS"


class AndroidArtifactAdapter(Protocol):
    provider_id: str

    def resolve(self, workspace: Path, *, slug: str) -> NormalizedAndroidArtifact: ...

    def prepare_build(
        self,
        workspace: Path,
        artifact: NormalizedAndroidArtifact,
        signing: AndroidSigningMaterial,
    ) -> dict[str, str]: ...

    def cleanup_build(
        self,
        workspace: Path,
        artifact: NormalizedAndroidArtifact,
    ) -> None: ...


class FlutterAndroidArtifactAdapter:
    provider_id = "flutter"

    def resolve(self, workspace: Path, *, slug: str) -> NormalizedAndroidArtifact:
        version_value = _yaml_scalar(workspace / "apps/mobile/pubspec.yaml", "version")
        if not version_value:
            raise ValueError("Flutter Android artifact requires apps/mobile/pubspec.yaml version.")
        version, build_number = _version_and_build(version_value)
        package_id = _gradle_application_id(
            workspace / "apps/mobile/android/app/build.gradle.kts"
        ) or f"com.nienfos.{_android_package_segment(slug)}"
        return NormalizedAndroidArtifact(
            kind="android_apk",
            source_app=slug,
            provider="gradle_apk",
            framework="flutter",
            package_id=package_id,
            version=version,
            build_number=build_number,
            release_tag=_release_tag(version, build_number),
            asset_name=f"{slug}.apk",
            build_command=("flutter", "build", "apk", "--release"),
            build_working_directory="apps/mobile",
            signing_contract="flutter_gradle_upload_keystore",
            runtime_profile="preview",
            mock_or_demo=False,
            candidate_paths=(
                "apps/mobile/build/app/outputs/flutter-apk/{asset_name}",
                "apps/mobile/build/app/outputs/flutter-apk/app-release.apk",
                "release/{asset_name}",
            ),
        )

    def prepare_build(
        self,
        workspace: Path,
        artifact: NormalizedAndroidArtifact,
        signing: AndroidSigningMaterial,
    ) -> dict[str, str]:
        del artifact
        android = workspace / "apps/mobile/android"
        if not android.is_dir():
            raise ValueError("Flutter Android artifact requires apps/mobile/android.")
        build_gradle = android / "app/build.gradle.kts"
        if not build_gradle.is_file():
            raise ValueError(
                "Flutter Android artifact requires android/app/build.gradle.kts."
            )
        _patch_flutter_release_signing(build_gradle)
        target_keystore = android / "upload-keystore.jks"
        shutil.copyfile(signing.keystore_path, target_keystore)
        (android / "key.properties").write_text(
            "\n".join(
                (
                    "storeFile=upload-keystore.jks",
                    f"storePassword={signing.store_password}",
                    f"keyPassword={signing.key_password}",
                    f"keyAlias={signing.key_alias}",
                    f"storeType={signing.store_type}",
                    "",
                )
            ),
            encoding="utf-8",
        )
        return {}

    def cleanup_build(
        self,
        workspace: Path,
        artifact: NormalizedAndroidArtifact,
    ) -> None:
        del artifact
        android = workspace / "apps/mobile/android"
        (android / "key.properties").unlink(missing_ok=True)
        (android / "upload-keystore.jks").unlink(missing_ok=True)


class ExpoAndroidArtifactAdapter:
    provider_id = "react_native_expo"

    def resolve(self, workspace: Path, *, slug: str) -> NormalizedAndroidArtifact:
        package = _json_object(workspace / "apps/mobile/package.json")
        app_config = _json_object(workspace / "apps/mobile/app.json")
        expo = app_config.get("expo") if isinstance(app_config.get("expo"), dict) else {}
        android = expo.get("android") if isinstance(expo.get("android"), dict) else {}
        version = str(expo.get("version") or package.get("version") or "").strip()
        build_number = android.get("versionCode", 1)
        package_id = str(android.get("package") or "").strip()
        if not version or not isinstance(build_number, int) or build_number < 1:
            raise ValueError(
                "Expo Android artifact requires a version and positive android.versionCode."
            )
        if not package_id:
            raise ValueError("Expo Android artifact requires expo.android.package.")
        return NormalizedAndroidArtifact(
            kind="android_apk",
            source_app=slug,
            provider="gradle_apk",
            framework="react_native_expo",
            package_id=package_id,
            version=version,
            build_number=build_number,
            release_tag=_release_tag(version, build_number),
            asset_name=f"{slug}.apk",
            build_command=(
                "./gradlew",
                "assembleRelease",
                "--no-daemon",
            ),
            build_working_directory="apps/mobile/android",
            signing_contract="react_native_gradle_upload_keystore",
            runtime_profile="preview",
            mock_or_demo=False,
            candidate_paths=(
                "apps/mobile/android/app/build/outputs/apk/release/{asset_name}",
                "apps/mobile/android/app/build/outputs/apk/release/app-release.apk",
                "release/{asset_name}",
            ),
        )

    def prepare_build(
        self,
        workspace: Path,
        artifact: NormalizedAndroidArtifact,
        signing: AndroidSigningMaterial,
    ) -> dict[str, str]:
        del artifact
        android = workspace / "apps/mobile/android"
        if not (android / "gradlew").is_file():
            raise ValueError(
                "Expo Android artifact requires deterministic prebuild output at "
                "apps/mobile/android."
            )
        environment = {
            "NODE_ENV": "production",
            "ANDROID_KEYSTORE_PATH": str(signing.keystore_path),
            "ANDROID_KEY_ALIAS": signing.key_alias,
            "ANDROID_STORE_PASSWORD": signing.store_password,
            "ANDROID_KEY_PASSWORD": signing.key_password,
            "ANDROID_STORE_TYPE": signing.store_type,
        }
        android_sdk = resolve_android_sdk_root()
        if android_sdk is not None:
            environment["ANDROID_HOME"] = str(android_sdk)
            environment["ANDROID_SDK_ROOT"] = str(android_sdk)
        return environment

    def cleanup_build(
        self,
        workspace: Path,
        artifact: NormalizedAndroidArtifact,
    ) -> None:
        del workspace, artifact


class AndroidArtifactService:
    def __init__(self, adapters: tuple[AndroidArtifactAdapter, ...] | None = None) -> None:
        values = adapters or (
            FlutterAndroidArtifactAdapter(),
            ExpoAndroidArtifactAdapter(),
        )
        self._adapters = {adapter.provider_id: adapter for adapter in values}
        if len(self._adapters) != len(values):
            raise ValueError("Android artifact adapter ids must be unique.")

    def resolve(
        self, provider_id: str, workspace: str | Path, *, slug: str
    ) -> NormalizedAndroidArtifact:
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?", slug):
            raise ValueError("Android artifact source app must be a safe project slug.")
        adapter = self._adapters.get(provider_id)
        if adapter is None:
            raise ValueError(f"Android artifact provider is unsupported: {provider_id}")
        return adapter.resolve(Path(workspace).resolve(), slug=slug)

    def supports(self, provider_id: str) -> bool:
        return provider_id in self._adapters

    def prepare_build(
        self,
        provider_id: str,
        workspace: str | Path,
        artifact: NormalizedAndroidArtifact,
        signing: AndroidSigningMaterial,
    ) -> dict[str, str]:
        adapter = self._adapters.get(provider_id)
        if adapter is None:
            raise ValueError(f"Android artifact provider is unsupported: {provider_id}")
        return adapter.prepare_build(Path(workspace), artifact, signing)

    def cleanup_build(
        self,
        provider_id: str,
        workspace: str | Path,
        artifact: NormalizedAndroidArtifact,
    ) -> None:
        adapter = self._adapters.get(provider_id)
        if adapter is None:
            raise ValueError(f"Android artifact provider is unsupported: {provider_id}")
        adapter.cleanup_build(Path(workspace), artifact)


def _yaml_scalar(path: Path, key: str) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        candidate, separator, value = line.partition(":")
        if separator and candidate.strip() == key:
            return value.strip() or None
    return None


def _json_object(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _version_and_build(value: str) -> tuple[str, int]:
    version, separator, raw_build = value.partition("+")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-.][0-9A-Za-z.-]+)?", version):
        raise ValueError(f"Invalid Android semantic version: {value}")
    build_number = int(raw_build) if separator and raw_build.isdigit() else 1
    return version, build_number


def _release_tag(version: str, build_number: int) -> str:
    return f"android-preview-v{version}-build.{build_number}"


def _gradle_application_id(path: Path) -> str | None:
    if not path.is_file():
        return None
    match = re.search(
        r"applicationId\s*=\s*[\"']([^\"']+)[\"']",
        path.read_text(encoding="utf-8"),
    )
    return match.group(1) if match else None


def _android_package_segment(value: str) -> str:
    segment = re.sub(r"[^a-z0-9_]", "_", value.lower()).strip("_") or "app"
    return f"app_{segment}" if segment[0].isdigit() else segment


def _patch_flutter_release_signing(path: Path) -> None:
    content = path.read_text(encoding="utf-8")
    if "keystoreProperties" not in content:
        content = content.replace(
            "plugins {\n",
            "import java.util.Properties\n\nplugins {\n",
            1,
        )
        content = content.replace(
            "\nandroid {\n",
            (
                "\nval keystoreProperties = Properties()\n"
                'val keystorePropertiesFile = rootProject.file("key.properties")\n'
                "if (keystorePropertiesFile.exists()) {\n"
                "    keystorePropertiesFile.inputStream().use { "
                "keystoreProperties.load(it) }\n"
                "}\n\nandroid {\n"
            ),
            1,
        )
    if 'create("release")' not in content:
        content = content.replace(
            "    buildTypes {\n",
            (
                "    signingConfigs {\n"
                '        create("release") {\n'
                '            keyAlias = keystoreProperties["keyAlias"] as String?\n'
                '            keyPassword = keystoreProperties["keyPassword"] as String?\n'
                '            storeFile = keystoreProperties["storeFile"]?.let { '
                "rootProject.file(it) }\n"
                '            storePassword = keystoreProperties["storePassword"] as String?\n'
                '            storeType = (keystoreProperties["storeType"] as String?) '
                '?: "JKS"\n'
                "        }\n"
                "    }\n\n"
                "    buildTypes {\n"
            ),
            1,
        )
    content = content.replace(
        'signingConfig = signingConfigs.getByName("debug")',
        'signingConfig = signingConfigs.getByName("release")',
    )
    path.write_text(content, encoding="utf-8")
