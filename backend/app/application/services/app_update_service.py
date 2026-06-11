from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Protocol

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
    required: bool
    available: bool


class GitHubReleaseError(RuntimeError):
    pass


class UnknownAppError(ValueError):
    pass


class AppDisabledError(ValueError):
    pass


class GitHubReleaseClient(Protocol):
    def list_releases(self, repo: str) -> list[GitHubRelease]: ...

    def download_asset(self, repo: str, asset: GitHubAsset) -> bytes: ...


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

    def download_asset(self, repo: str, asset: GitHubAsset) -> bytes:
        del repo
        url = asset.api_url or asset.browser_download_url
        if not url:
            raise GitHubReleaseError("GitHub release asset has no download URL.")
        try:
            response = httpx.get(
                url,
                follow_redirects=True,
                headers=self._headers(accept="application/octet-stream"),
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise GitHubReleaseError(str(exc)) from exc
        return response.content

    def _headers(self, *, accept: str) -> dict[str, str]:
        headers = {
            "Accept": accept,
            "User-Agent": "codex-mobile-bridge-app-updater",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers


class AppUpdateRegistry:
    def __init__(self, configs: dict[str, AppUpdateConfig]) -> None:
        self._configs = configs

    @classmethod
    def from_json_file(cls, path: str | Path) -> "AppUpdateRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("App update registry must be a JSON object.")
        configs: dict[str, AppUpdateConfig] = {}
        for source_app, raw_config in payload.items():
            if not isinstance(raw_config, dict):
                raise ValueError(f"Invalid app update config for {source_app}.")
            configs[source_app] = AppUpdateConfig(
                source_app=source_app,
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
            )
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


class AppUpdateService:
    def __init__(
        self,
        *,
        registry: AppUpdateRegistry,
        release_client: GitHubReleaseClient,
    ) -> None:
        self._registry = registry
        self._release_client = release_client

    def list_apps(self) -> list[AppUpdateConfig]:
        return self._registry.list_configs()

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

        config = self._registry.get(source_app)
        latest = self._latest_valid_release(config, channel=channel)
        if latest is None:
            return _empty_result(
                config,
                platform=platform,
                current_version=current_version,
                current_build=current_build,
            )

        release, apk_asset, latest_version, latest_build = latest
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
            required=required,
            available=available,
        )

    def download_apk_asset(
        self,
        *,
        source_app: str,
        release_tag: str,
        asset_name: str,
    ) -> tuple[bytes, GitHubAsset]:
        config = self._registry.get(source_app)
        for release in self._release_client.list_releases(config.repo):
            if release.tag_name != release_tag:
                continue
            if release.draft or not fnmatch.fnmatch(
                release.tag_name,
                config.release_tag_pattern,
            ):
                break
            asset = _find_downloadable_apk_asset(release.assets, config, asset_name)
            if asset is None:
                break
            content = self._release_client.download_asset(config.repo, asset)
            if not content.startswith(b"PK\x03\x04"):
                raise GitHubReleaseError("Downloaded asset is not an APK archive.")
            return content, asset
        raise UnknownAppError(f"{source_app}:{release_tag}:{asset_name}")

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
            if channel == "stable" and release.prerelease:
                continue
            if not fnmatch.fnmatch(release.tag_name, config.release_tag_pattern):
                continue
            apk_asset = _select_apk_asset(release.assets, config)
            if apk_asset is None:
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
        required=False,
        available=False,
    )


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
