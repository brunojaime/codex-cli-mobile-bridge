#!/usr/bin/env python3
"""Validate Android release networking for the real Codex Mobile backend."""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse


ANDROID_NS = "http://schemas.android.com/apk/res/android"
ANDROID = f"{{{ANDROID_NS}}}"
DEFAULT_RELEASE_BRIDGE_URL = "http://batata-default-string.tail0302c4.ts.net"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "10.0.2.2"}
PLACEHOLDER_FRAGMENTS = (
    "example.com",
    "placeholder",
    "changeme",
    "your-",
    "invalid",
)


def validate(
    repo_root: Path,
    *,
    api_base_url: str | None = None,
    updater_bridge_url: str | None = None,
) -> list[str]:
    errors: list[str] = []
    api_url = _normalize_url(api_base_url or DEFAULT_RELEASE_BRIDGE_URL)
    updater_url = _normalize_url(updater_bridge_url or api_url)

    api = _validate_real_url("API_BASE_URL", api_url, errors)
    updater = _validate_real_url(
        "CODEX_APP_UPDATER_BRIDGE_URL",
        updater_url,
        errors,
    )
    if api is None or updater is None:
        return errors
    if api.scheme != updater.scheme or api.hostname != updater.hostname:
        errors.append(
            "CODEX_APP_UPDATER_BRIDGE_URL must use the same release backend "
            "host as API_BASE_URL."
        )

    if api.scheme == "http":
        _validate_android_cleartext_host(repo_root, api.hostname or "", errors)
    return errors


def _normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


def _validate_real_url(label: str, url: str, errors: list[str]):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        errors.append(f"{label} must be an absolute http(s) URL, got: {url!r}")
        return None
    if host in LOCAL_HOSTS:
        errors.append(f"{label} must not point at a local-only host: {host}")
    if any(fragment in host for fragment in PLACEHOLDER_FRAGMENTS):
        errors.append(f"{label} host looks like a placeholder: {host}")
    return parsed


def _validate_android_cleartext_host(
    repo_root: Path,
    hostname: str,
    errors: list[str],
) -> None:
    manifest_path = (
        repo_root
        / "frontend/mobile_app/android/app/src/main/AndroidManifest.xml"
    )
    manifest = ET.parse(manifest_path).getroot()
    application = manifest.find("application")
    if application is None:
        errors.append("AndroidManifest.xml is missing <application>.")
        return

    if application.attrib.get(f"{ANDROID}usesCleartextTraffic") == "true":
        errors.append(
            "Release AndroidManifest.xml uses broad "
            "android:usesCleartextTraffic=\"true\"; use a narrow "
            "networkSecurityConfig for the release HTTP host."
        )

    config_ref = application.attrib.get(f"{ANDROID}networkSecurityConfig")
    if not config_ref or not config_ref.startswith("@xml/"):
        errors.append(
            "HTTP API_BASE_URL requires android:networkSecurityConfig in "
            "the release manifest."
        )
        return

    config_name = config_ref.removeprefix("@xml/")
    config_path = (
        repo_root
        / "frontend/mobile_app/android/app/src/main/res/xml"
        / f"{config_name}.xml"
    )
    if not config_path.exists():
        errors.append(f"networkSecurityConfig file is missing: {config_path}")
        return

    config = ET.parse(config_path).getroot()
    if _host_is_cleartext_permitted(config, hostname):
        return
    errors.append(
        f"networkSecurityConfig does not permit cleartext HTTP for {hostname}."
    )


def _host_is_cleartext_permitted(config: ET.Element, hostname: str) -> bool:
    for domain_config in config.findall("domain-config"):
        if domain_config.attrib.get("cleartextTrafficPermitted") != "true":
            continue
        for domain in domain_config.findall("domain"):
            configured = (domain.text or "").strip().lower()
            include_subdomains = (
                domain.attrib.get("includeSubdomains") == "true"
            )
            if configured == hostname:
                return True
            if include_subdomains and hostname.endswith(f".{configured}"):
                return True
    return False


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    errors = validate(
        repo_root,
        api_base_url=os.environ.get("API_BASE_URL"),
        updater_bridge_url=os.environ.get("CODEX_APP_UPDATER_BRIDGE_URL"),
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    api_url = _normalize_url(os.environ.get("API_BASE_URL") or DEFAULT_RELEASE_BRIDGE_URL)
    updater_url = _normalize_url(
        os.environ.get("CODEX_APP_UPDATER_BRIDGE_URL") or api_url
    )
    print(f"Android release networking ok: API_BASE_URL={api_url}")
    print(f"Android release updater ok: CODEX_APP_UPDATER_BRIDGE_URL={updater_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
