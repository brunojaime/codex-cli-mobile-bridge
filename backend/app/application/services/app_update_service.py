from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import hashlib
import json
import re
import shutil
import threading
import time
from pathlib import Path
from collections.abc import Iterator
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True, slots=True)
class AppUpdateConfig:
    source_app: str
    display_name: str
    repo: str
    release_tag_pattern: str
    apk_asset_pattern: str
    latest_asset_name: str | None
    required_minimum_build: int | None
    enabled: bool
    release_channel: str = "stable"
    expected_package_id: str | None = None
    verified_package_ids: dict[str, str] | None = None
    preview_url: str | None = None
    runtime_profile: str | None = None
    production_ready: bool | None = None
    mock_or_demo: bool | None = None
    release_metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class GitHubAsset:
    name: str
    browser_download_url: str
    size: int | None = None
    digest: str | None = None
    api_url: str | None = None


@dataclass(frozen=True, slots=True)
class GitHubRelease:
    tag_name: str
    html_url: str
    body: str | None
    draft: bool
    prerelease: bool
    assets: tuple[GitHubAsset, ...]


@dataclass(frozen=True, slots=True)
class AppUpdateResult:
    source_app: str
    display_name: str | None
    platform: str
    current_version: str | None
    current_build: int | None
    latest_version: str | None
    latest_build: int | None
    release_tag: str | None
    release_url: str | None
    apk_url: str | None
    apk_asset_name: str | None
    sha256: str | None
    size_bytes: int | None
    release_notes: str | None
    release_channel: str
    release_prerelease: bool
    private_install: bool
    package_id: str | None
    required: bool
    available: bool


class GitHubReleaseError(RuntimeError):
    pass


class UnknownAppError(ValueError):
    pass


class AppDisabledError(ValueError):
    pass


class AppUpdateAssetNotFoundError(ValueError):
    pass


class GitHubReleaseClient(Protocol):
    def list_releases(self, repo: str) -> list[GitHubRelease]: ...

    def open_asset_stream(
        self, repo: str, asset: GitHubAsset
    ) -> "GitHubAssetStream": ...


class GitHubAssetStream(Protocol):
    @property
    def content_length(self) -> int | None: ...

    def iter_bytes(self) -> Iterator[bytes]: ...

    def close(self) -> None: ...


class HttpGitHubReleaseClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._token = token
        self._timeout_seconds = timeout_seconds

    def list_releases(self, repo: str) -> list[GitHubRelease]:
        url = f"https://api.github.com/repos/{repo}/releases"
        try:
            response = httpx.get(
                url,
                headers=self._headers(accept="application/vnd.github+json"),
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise GitHubReleaseError(str(exc)) from exc

        payload = response.json()
        if not isinstance(payload, list):
            raise GitHubReleaseError("GitHub releases response was not a list.")
        return [_release_from_json(item) for item in payload]

    def open_asset_stream(self, repo: str, asset: GitHubAsset) -> GitHubAssetStream:
        del repo
        url = asset.api_url or asset.browser_download_url
        if not url:
            raise GitHubReleaseError("GitHub release asset has no download URL.")
        return _HttpGitHubAssetStream(
            url=url,
            headers=self._headers(accept="application/octet-stream"),
            timeout_seconds=self._timeout_seconds,
        ).open()

    def _headers(self, *, accept: str) -> dict[str, str]:
        headers = {
            "Accept": accept,
            "User-Agent": "codex-mobile-bridge-app-updater",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers


class _HttpGitHubAssetStream:
    def __init__(
        self,
        *,
        url: str,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> None:
        self._url = url
        self._headers = headers
        self._timeout_seconds = timeout_seconds
        self._context: Any | None = None
        self._response: httpx.Response | None = None

    def open(self) -> "_HttpGitHubAssetStream":
        self._context = httpx.stream(
            "GET",
            self._url,
            follow_redirects=True,
            headers=self._headers,
            timeout=self._timeout_seconds,
        )
        try:
            self._response = self._context.__enter__()
            self._response.raise_for_status()
        except httpx.HTTPError as exc:
            self.close()
            raise GitHubReleaseError(str(exc)) from exc
        return self

    @property
    def content_length(self) -> int | None:
        response = self._response
        if response is None:
            return None
        value = response.headers.get("content-length")
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def iter_bytes(self) -> Iterator[bytes]:
        response = self._response
        if response is None:
            return iter(())
        return response.iter_bytes()

    def close(self) -> None:
        if self._context is not None:
            self._context.__exit__(None, None, None)
            self._context = None
        self._response = None


class AppUpdateRegistry:
    def __init__(self, configs: dict[str, AppUpdateConfig]) -> None:
        self._configs = configs

    @classmethod
    def from_json_file(cls, path: str | Path) -> "AppUpdateRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_mapping(payload)

    @classmethod
    def from_mapping(cls, payload: Any) -> "AppUpdateRegistry":
        if not isinstance(payload, dict):
            raise ValueError("App update registry must be a JSON object.")
        configs: dict[str, AppUpdateConfig] = {}
        for source_app, raw_config in payload.items():
            if not isinstance(raw_config, dict):
                raise ValueError(f"Invalid app update config for {source_app}.")
            configs[str(source_app)] = _config_from_raw(str(source_app), raw_config)
        return cls(configs)

    def list_configs(self) -> list[AppUpdateConfig]:
        return sorted(self._configs.values(), key=lambda config: config.source_app)

    def get(self, source_app: str) -> AppUpdateConfig:
        config = self._configs.get(source_app)
        if config is None:
            raise UnknownAppError(source_app)
        if not config.enabled:
            raise AppDisabledError(source_app)
        return config

    def to_mapping(self) -> dict[str, Any]:
        return {
            config.source_app: _config_to_raw(config)
            for config in self.list_configs()
        }


class AppUpdateService:
    def __init__(
        self,
        *,
        registry: AppUpdateRegistry,
        release_client: GitHubReleaseClient,
        registry_path: str | Path | None = None,
    ) -> None:
        self._registry = registry
        self._release_client = release_client
        self._registry_path = Path(registry_path) if registry_path is not None else None
        self._registry_mtime_ns = self._current_registry_mtime_ns()
        self._lock = threading.RLock()

    def list_apps(self) -> list[AppUpdateConfig]:
        with self._lock:
            self._reload_if_changed()
            return self._registry.list_configs()

    def register_app(
        self,
        *,
        source_app: str,
        display_name: str,
        repo: str,
        release_tag_pattern: str,
        apk_asset_pattern: str,
        latest_asset_name: str | None,
        required_minimum_build: int | None,
        enabled: bool,
        release_channel: str = "stable",
        expected_package_id: str | None = None,
        verified_package_ids: dict[str, str] | None = None,
        preview_url: str | None = None,
        runtime_profile: str | None = None,
        production_ready: bool | None = None,
        mock_or_demo: bool | None = None,
        release_metadata: dict[str, Any] | None = None,
    ) -> AppUpdateConfig:
        if self._registry_path is None:
            raise ValueError("App update registry path is not writable.")
        normalized_source_app = _validate_source_app(source_app)
        normalized_repo = _validate_repo(repo)
        _validate_channel(release_channel)
        if required_minimum_build is not None and required_minimum_build < 0:
            raise ValueError("requiredMinimumBuild must be greater than or equal to 0.")
        normalized_package_id = (
            _validate_android_package_id(expected_package_id)
            if expected_package_id
            else None
        )
        normalized_verified_package_ids = {
            _non_empty_string(str(key), "verifiedPackageIds key"): (
                _validate_android_package_id(str(value))
            )
            for key, value in (verified_package_ids or {}).items()
        }
        entry = {
            "displayName": _non_empty_string(display_name, "displayName"),
            "repo": normalized_repo,
            "releaseTagPattern": _non_empty_string(
                _safe_pattern(release_tag_pattern, "releaseTagPattern"),
                "releaseTagPattern",
            ),
            "apkAssetPattern": _non_empty_string(
                _safe_pattern(apk_asset_pattern, "apkAssetPattern"),
                "apkAssetPattern",
            ),
            "latestAssetName": (
                _safe_asset_name(latest_asset_name) if latest_asset_name else None
            ),
            "requiredMinimumBuild": required_minimum_build,
            "releaseChannel": release_channel,
            "expectedPackageId": normalized_package_id,
            "verifiedPackageIds": normalized_verified_package_ids,
            "enabled": enabled,
        }
        if preview_url is not None:
            entry["previewUrl"] = _validate_preview_url(preview_url)
        if runtime_profile is not None:
            entry["runtimeProfile"] = _validate_runtime_profile(runtime_profile)
        if production_ready is not None:
            entry["productionReady"] = _parse_registry_bool(
                production_ready,
                "productionReady",
            )
        if mock_or_demo is not None:
            entry["mockOrDemo"] = _parse_registry_bool(mock_or_demo, "mockOrDemo")
        if release_metadata is not None:
            entry["releaseMetadata"] = dict(release_metadata)
        config = _config_from_raw(normalized_source_app, entry)
        with self._lock:
            payload = self._read_registry_payload()
            payload[normalized_source_app] = entry
            self._write_registry_payload(payload)
            self._registry = AppUpdateRegistry.from_mapping(payload)
            self._registry_mtime_ns = self._current_registry_mtime_ns()
        return config

    def check_update(
        self,
        *,
        source_app: str,
        platform: str = "android",
        current_version: str | None = None,
        current_build: int | None = None,
        channel: str = "stable",
    ) -> AppUpdateResult:
        if platform != "android":
            raise ValueError("Only android app updates are currently supported.")
        _validate_channel(channel)

        with self._lock:
            self._reload_if_changed()
            config = self._registry.get(source_app)
        effective_channel = _effective_channel(config, requested_channel=channel)
        latest = self._latest_valid_release(config, channel=effective_channel)
        if latest is None:
            return _empty_result(
                config,
                platform=platform,
                current_version=current_version,
                current_build=current_build,
            )

        release, apk_asset, latest_version, latest_build = latest
        package_id = _verified_package_id_for(config, release, apk_asset)
        available = (
            current_build is None
            or latest_build is None
            or latest_build > current_build
        )
        required = (
            current_build is not None
            and config.required_minimum_build is not None
            and current_build < config.required_minimum_build
        )
        return AppUpdateResult(
            source_app=config.source_app,
            display_name=config.display_name,
            platform=platform,
            current_version=current_version,
            current_build=current_build,
            latest_version=latest_version,
            latest_build=latest_build,
            release_tag=release.tag_name,
            release_url=release.html_url,
            apk_url=apk_asset.browser_download_url if available else None,
            apk_asset_name=apk_asset.name if available else None,
            sha256=_sha256_for_asset(release.assets, apk_asset) if available else None,
            size_bytes=apk_asset.size if available else None,
            release_notes=release.body if available else None,
            release_channel=effective_channel,
            release_prerelease=release.prerelease,
            private_install=effective_channel == "private-install",
            package_id=package_id,
            required=required,
            available=available,
        )

    def resolve_apk_asset(
        self,
        *,
        source_app: str,
        release_tag: str,
        asset_name: str,
        platform: str = "android",
        channel: str = "stable",
    ) -> tuple[AppUpdateConfig, GitHubAsset]:
        if platform != "android":
            raise ValueError("Only android app updates are currently supported.")
        _validate_channel(channel)
        if not _is_safe_asset_name(asset_name):
            raise AppUpdateAssetNotFoundError(
                f"{source_app}:{release_tag}:{asset_name}"
            )
        with self._lock:
            self._reload_if_changed()
            config = self._registry.get(source_app)
        effective_channel = _effective_channel(config, requested_channel=channel)
        for release in self._release_client.list_releases(config.repo):
            if release.tag_name != release_tag:
                continue
            if (
                release.draft
                or not _release_allowed_for_channel(release, effective_channel)
                or not fnmatch.fnmatch(release.tag_name, config.release_tag_pattern)
            ):
                break
            asset = _find_downloadable_apk_asset(release.assets, config, asset_name)
            if asset is None:
                break
            if not _release_package_matches(config, release, asset):
                break
            return config, asset
        raise AppUpdateAssetNotFoundError(f"{source_app}:{release_tag}:{asset_name}")

    def open_apk_asset_stream(
        self,
        *,
        source_app: str,
        release_tag: str,
        asset_name: str,
        platform: str = "android",
        channel: str = "stable",
    ) -> tuple[GitHubAsset, GitHubAssetStream]:
        config, asset = self.resolve_apk_asset(
            source_app=source_app,
            release_tag=release_tag,
            asset_name=asset_name,
            platform=platform,
            channel=channel,
        )
        stream = self._release_client.open_asset_stream(config.repo, asset)
        return asset, stream

    def _read_registry_payload(self) -> dict[str, Any]:
        if self._registry_path is None:
            return {}
        if not self._registry_path.exists():
            return {}
        try:
            payload = json.loads(self._registry_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("App update registry must be a JSON object.")
        except (json.JSONDecodeError, ValueError):
            self._backup_registry_file(suffix="corrupt")
            return self._registry.to_mapping()
        return payload

    def _write_registry_payload(self, payload: dict[str, Any]) -> None:
        if self._registry_path is None:
            raise ValueError("App update registry path is not writable.")
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        if self._registry_path.exists():
            self._backup_registry_file(suffix="bak")
        tmp_path = self._registry_path.with_name(f".{self._registry_path.name}.tmp")
        tmp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(self._registry_path)

    def _reload_if_changed(self) -> None:
        if self._registry_path is None:
            return
        mtime_ns = self._current_registry_mtime_ns()
        if mtime_ns == self._registry_mtime_ns:
            return
        try:
            self._registry = AppUpdateRegistry.from_json_file(self._registry_path)
        except (json.JSONDecodeError, ValueError):
            self._backup_registry_file(suffix="corrupt")
        self._registry_mtime_ns = mtime_ns

    def _current_registry_mtime_ns(self) -> int | None:
        if self._registry_path is None or not self._registry_path.exists():
            return None
        return self._registry_path.stat().st_mtime_ns

    def _backup_registry_file(self, *, suffix: str) -> None:
        if self._registry_path is None or not self._registry_path.exists():
            return
        timestamp = int(time.time() * 1000)
        backup_path = self._registry_path.with_name(
            f"{self._registry_path.name}.{suffix}.{timestamp}",
        )
        shutil.copy2(self._registry_path, backup_path)

    def _latest_valid_release(
        self,
        config: AppUpdateConfig,
        *,
        channel: str,
    ) -> tuple[GitHubRelease, GitHubAsset, str | None, int | None] | None:
        releases = self._release_client.list_releases(config.repo)
        candidates: list[
            tuple[int, GitHubRelease, GitHubAsset, str | None, int | None]
        ] = []
        for release in releases:
            if release.draft:
                continue
            if not _release_allowed_for_channel(release, channel):
                continue
            if not fnmatch.fnmatch(release.tag_name, config.release_tag_pattern):
                continue
            apk_asset = _select_apk_asset(release.assets, config)
            if apk_asset is None:
                continue
            if not _release_package_matches(config, release, apk_asset):
                continue
            latest_version, latest_build = _derive_version_and_build(
                release.tag_name,
                apk_asset.name,
            )
            sort_build = latest_build if latest_build is not None else -1
            candidates.append(
                (sort_build, release, apk_asset, latest_version, latest_build)
            )
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1].tag_name), reverse=True)
        _, release, apk_asset, latest_version, latest_build = candidates[0]
        return release, apk_asset, latest_version, latest_build


def _empty_result(
    config: AppUpdateConfig,
    *,
    platform: str,
    current_version: str | None,
    current_build: int | None,
) -> AppUpdateResult:
    return AppUpdateResult(
        source_app=config.source_app,
        display_name=config.display_name,
        platform=platform,
        current_version=current_version,
        current_build=current_build,
        latest_version=current_version,
        latest_build=current_build,
        release_tag=None,
        release_url=None,
        apk_url=None,
        apk_asset_name=None,
        sha256=None,
        size_bytes=None,
        release_notes=None,
        release_channel=config.release_channel,
        release_prerelease=False,
        private_install=config.release_channel == "private-install",
        package_id=None,
        required=False,
        available=False,
    )


def _config_from_raw(source_app: str, raw_config: dict[str, Any]) -> AppUpdateConfig:
    return AppUpdateConfig(
        source_app=_validate_source_app(source_app),
        display_name=str(raw_config["displayName"]),
        repo=str(raw_config["repo"]),
        release_tag_pattern=str(raw_config["releaseTagPattern"]),
        apk_asset_pattern=str(raw_config["apkAssetPattern"]),
        latest_asset_name=(
            str(raw_config["latestAssetName"])
            if raw_config.get("latestAssetName") is not None
            else None
        ),
        required_minimum_build=(
            int(raw_config["requiredMinimumBuild"])
            if raw_config.get("requiredMinimumBuild") is not None
            else None
        ),
        enabled=bool(raw_config.get("enabled", True)),
        release_channel=_validate_release_channel_value(
            str(raw_config.get("releaseChannel", "stable"))
        ),
        expected_package_id=(
            str(raw_config["expectedPackageId"])
            if raw_config.get("expectedPackageId") is not None
            else None
        ),
        verified_package_ids={
            str(key): str(value)
            for key, value in (raw_config.get("verifiedPackageIds") or {}).items()
        },
        preview_url=(
            _validate_preview_url(raw_config["previewUrl"])
            if raw_config.get("previewUrl") is not None
            else None
        ),
        runtime_profile=(
            _validate_runtime_profile(raw_config["runtimeProfile"])
            if raw_config.get("runtimeProfile") is not None
            else None
        ),
        production_ready=(
            _parse_registry_bool(raw_config["productionReady"], "productionReady")
            if raw_config.get("productionReady") is not None
            else None
        ),
        mock_or_demo=(
            _parse_registry_bool(raw_config["mockOrDemo"], "mockOrDemo")
            if raw_config.get("mockOrDemo") is not None
            else None
        ),
        release_metadata=(
            dict(raw_config["releaseMetadata"])
            if isinstance(raw_config.get("releaseMetadata"), dict)
            else None
        ),
    )


def _config_to_raw(config: AppUpdateConfig) -> dict[str, Any]:
    return {
        "displayName": config.display_name,
        "repo": config.repo,
        "releaseTagPattern": config.release_tag_pattern,
        "apkAssetPattern": config.apk_asset_pattern,
        "latestAssetName": config.latest_asset_name,
        "requiredMinimumBuild": config.required_minimum_build,
        "releaseChannel": config.release_channel,
        "expectedPackageId": config.expected_package_id,
        "verifiedPackageIds": config.verified_package_ids or {},
        "enabled": config.enabled,
        "previewUrl": config.preview_url,
        "runtimeProfile": config.runtime_profile,
        "productionReady": config.production_ready,
        "mockOrDemo": config.mock_or_demo,
        "releaseMetadata": config.release_metadata or {},
    }


def _release_from_json(payload: Any) -> GitHubRelease:
    if not isinstance(payload, dict):
        raise GitHubReleaseError("Invalid GitHub release item.")
    assets_payload = payload.get("assets", [])
    if not isinstance(assets_payload, list):
        assets_payload = []
    return GitHubRelease(
        tag_name=str(payload.get("tag_name") or ""),
        html_url=str(payload.get("html_url") or ""),
        body=payload.get("body") if isinstance(payload.get("body"), str) else None,
        draft=bool(payload.get("draft", False)),
        prerelease=bool(payload.get("prerelease", False)),
        assets=tuple(_asset_from_json(item) for item in assets_payload),
    )


def _asset_from_json(payload: Any) -> GitHubAsset:
    if not isinstance(payload, dict):
        raise GitHubReleaseError("Invalid GitHub release asset.")
    return GitHubAsset(
        name=str(payload.get("name") or ""),
        browser_download_url=str(payload.get("browser_download_url") or ""),
        size=payload.get("size") if isinstance(payload.get("size"), int) else None,
        digest=payload.get("digest")
        if isinstance(payload.get("digest"), str)
        else None,
        api_url=payload.get("url") if isinstance(payload.get("url"), str) else None,
    )


def _select_apk_asset(
    assets: tuple[GitHubAsset, ...],
    config: AppUpdateConfig,
) -> GitHubAsset | None:
    if config.latest_asset_name:
        for asset in assets:
            if asset.name == config.latest_asset_name:
                return asset
    for asset in assets:
        if fnmatch.fnmatch(asset.name, config.apk_asset_pattern):
            return asset
    return None


def _validate_channel(channel: str) -> None:
    if channel not in {
        "stable",
        "prod",
        "dev",
        "preview",
        "prerelease",
        "private-install",
        "all",
    }:
        raise ValueError("Unsupported app update channel.")


def _parse_registry_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise ValueError(f"{field_name} must be a boolean or 'true'/'false' string.")


def _validate_runtime_profile(value: Any) -> str:
    profile = _non_empty_string(str(value), "runtimeProfile").lower()
    if profile not in {"mock", "preview", "real", "staging"}:
        raise ValueError(
            "runtimeProfile must be one of mock, preview, real, or staging."
        )
    return profile


def _validate_preview_url(value: Any) -> str:
    url = _non_empty_string(str(value), "previewUrl")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("previewUrl must be an HTTPS URL.")
    return url


def _validate_source_app(source_app: str) -> str:
    value = source_app.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,119}", value):
        raise ValueError("sourceApp must be a safe lowercase app id.")
    return value


def _validate_repo(repo: str) -> str:
    value = repo.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("repo must use the OWNER/REPO format.")
    return value


def _non_empty_string(value: str | None, field_name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


def _safe_asset_name(value: str) -> str:
    normalized = _non_empty_string(value, "latestAssetName")
    if not _is_safe_asset_name(normalized):
        raise ValueError("latestAssetName must be a safe file name.")
    return normalized


def _safe_pattern(value: str, field_name: str) -> str:
    normalized = _non_empty_string(value, field_name)
    if (
        "/" in normalized
        or "\\" in normalized
        or "\x00" in normalized
        or ".." in normalized
    ):
        raise ValueError(f"{field_name} must not contain path traversal.")
    return normalized


def _validate_android_package_id(value: str) -> str:
    normalized = _non_empty_string(value, "packageId")
    part = r"[A-Za-z][A-Za-z0-9_]*"
    if not re.fullmatch(rf"{part}(\.{part})+", normalized):
        raise ValueError("packageId must be a valid Android package id.")
    return normalized


def _release_allowed_for_channel(release: GitHubRelease, channel: str) -> bool:
    _validate_channel(channel)
    if channel in {"stable", "prod"}:
        return not release.prerelease
    if channel in {"dev", "preview", "prerelease", "private-install"}:
        return release.prerelease
    return True


def _validate_release_channel_value(channel: str) -> str:
    _validate_channel(channel)
    if channel == "all":
        raise ValueError("App update releaseChannel cannot be 'all'.")
    return channel


def _effective_channel(config: AppUpdateConfig, *, requested_channel: str) -> str:
    _validate_channel(requested_channel)
    if requested_channel == "stable" and config.release_channel != "stable":
        return config.release_channel
    return requested_channel


def _is_safe_asset_name(asset_name: str) -> bool:
    if not asset_name or asset_name in {".", ".."}:
        return False
    if "/" in asset_name or "\\" in asset_name:
        return False
    if asset_name != Path(asset_name).name:
        return False
    return asset_name.endswith(".apk")


def _find_downloadable_apk_asset(
    assets: tuple[GitHubAsset, ...],
    config: AppUpdateConfig,
    asset_name: str,
) -> GitHubAsset | None:
    for asset in assets:
        if asset.name != asset_name:
            continue
        if config.latest_asset_name and asset.name == config.latest_asset_name:
            return asset
        if fnmatch.fnmatch(asset.name, config.apk_asset_pattern):
            return asset
    return None


def _verified_package_id_for(
    config: AppUpdateConfig,
    release: GitHubRelease,
    apk_asset: GitHubAsset,
) -> str | None:
    verified = config.verified_package_ids or {}
    exact = verified.get(release.tag_name) or verified.get(apk_asset.name)
    if exact is not None:
        return exact
    for pattern, package_id in verified.items():
        if fnmatch.fnmatch(release.tag_name, pattern) or fnmatch.fnmatch(
            apk_asset.name,
            pattern,
        ):
            return package_id
    return None


def _release_package_matches(
    config: AppUpdateConfig,
    release: GitHubRelease,
    apk_asset: GitHubAsset,
) -> bool:
    expected = config.expected_package_id
    if expected is None:
        return True
    package_id = _verified_package_id_for(config, release, apk_asset)
    return package_id == expected


def _derive_version_and_build(*values: str) -> tuple[str | None, int | None]:
    joined = " ".join(values)
    version_match = re.search(r"v(?P<version>\d+(?:\.\d+){1,3})", joined)
    build_match = re.search(r"(?:build[.-]?|[+])(?P<build>\d+)", joined, re.IGNORECASE)
    latest_version = version_match.group("version") if version_match else None
    latest_build = int(build_match.group("build")) if build_match else None
    return latest_version, latest_build


def _sha256_for_asset(
    assets: tuple[GitHubAsset, ...],
    apk_asset: GitHubAsset,
) -> str | None:
    sha_asset_names = {
        f"{apk_asset.name}.sha256",
        f"{apk_asset.name}.sha256sum",
        f"{apk_asset.name}.sha256.txt",
    }
    for asset in assets:
        normalized_name = asset.name.lower()
        if asset.name in sha_asset_names or (
            normalized_name.endswith(".sha256")
            and normalized_name.startswith(apk_asset.name.lower())
        ):
            checksum = download_checksum_asset(asset.browser_download_url)
            if checksum:
                return checksum
    if apk_asset.digest:
        digest = apk_asset.digest.strip()
        if digest.startswith("sha256:"):
            digest = digest.split(":", maxsplit=1)[1]
        if re.fullmatch(r"[a-fA-F0-9]{64}", digest):
            return digest.lower()
    return None


def download_checksum_asset(url: str) -> str | None:
    if not url:
        return None
    try:
        response = httpx.get(url, timeout=10)
        response.raise_for_status()
    except httpx.HTTPError:
        return None
    text = response.text.strip()
    match = re.search(r"\b([a-fA-F0-9]{64})\b", text)
    return match.group(1).lower() if match else None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
