#!/usr/bin/env python3
"""Dry-run validation for Codex Mobile Android release channel wiring."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Android release channel inputs without publishing."
    )
    parser.add_argument("--channel", required=True, choices=["prod", "dev"])
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--app-label", required=True)
    parser.add_argument("--updater-channel", required=True)
    parser.add_argument("--environment-color", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument(
        "--pubspec",
        default="frontend/mobile_app/pubspec.yaml",
    )
    parser.add_argument(
        "--app-updates-registry",
        default="backend/app/infrastructure/config/app_updates.json",
    )
    parser.add_argument("--source-app", default=None)
    parser.add_argument("--expected-package-id", default=None)
    parser.add_argument(
        "--allow-demo-mock",
        action="store_true",
        help="Allow explicitly labelled demo/mock builds. Real release workflows must not use this.",
    )
    args = parser.parse_args()
    source_app = args.source_app or (
        "codex-mobile-dev" if args.channel == "dev" else "codex-mobile"
    )
    expected_package_id = args.expected_package_id or (
        "com.example.codex_mobile_frontend.dev"
        if args.channel == "dev"
        else "com.example.codex_mobile_frontend"
    )
    blockers: list[str] = []
    evidence: dict[str, Any] = {
        "channel": args.channel,
        "source_app": source_app,
        "expected_package_id": expected_package_id,
        "api_base_url": args.api_base_url,
        "app_label": args.app_label,
        "updater_channel": args.updater_channel,
        "environment_color": args.environment_color,
        "release_tag": args.release_tag,
        "pubspec": args.pubspec,
        "app_updates_registry": args.app_updates_registry,
        "published": False,
    }

    pubspec = Path(args.pubspec)
    if not pubspec.is_file():
        blockers.append("missing_pubspec")
    else:
        version = _read_pubspec_version(pubspec)
        evidence["pubspec_version"] = version
        if not version:
            blockers.append("missing_pubspec_version")

    registry = Path(args.app_updates_registry)
    if not registry.is_file():
        blockers.append("missing_app_updates_registry")
    else:
        try:
            registry_payload = json.loads(registry.read_text(encoding="utf-8"))
            if not isinstance(registry_payload, dict):
                blockers.append("invalid_app_updates_registry_json")
            else:
                evidence["app_updates_registry_entries"] = len(registry_payload)
                registry_entry = registry_payload.get(source_app)
                if not isinstance(registry_entry, dict):
                    blockers.append("missing_source_app_registry_entry")
                else:
                    evidence["registry_entry"] = {
                        "source_app": source_app,
                        "release_channel": registry_entry.get("releaseChannel"),
                        "release_tag_pattern": registry_entry.get(
                            "releaseTagPattern"
                        ),
                        "latest_asset_name": registry_entry.get("latestAssetName"),
                        "expected_package_id": registry_entry.get(
                            "expectedPackageId"
                        ),
                    }
                    expected_pattern = (
                        "android-dev-v*" if args.channel == "dev" else "android-v*"
                    )
                    expected_asset = (
                        "codex-mobile-dev.apk"
                        if args.channel == "dev"
                        else "codex-mobile.apk"
                    )
                    if registry_entry.get("releaseChannel") != args.channel:
                        blockers.append("registry_release_channel_mismatch")
                    if registry_entry.get("releaseTagPattern") != expected_pattern:
                        blockers.append("registry_release_tag_pattern_mismatch")
                    if registry_entry.get("latestAssetName") != expected_asset:
                        blockers.append("registry_latest_asset_name_mismatch")
                    if registry_entry.get("expectedPackageId") != expected_package_id:
                        blockers.append("registry_expected_package_id_mismatch")
        except json.JSONDecodeError:
            blockers.append("invalid_app_updates_registry_json")

    if not args.environment_color.startswith("#") or len(args.environment_color) != 7:
        blockers.append("invalid_environment_color")
    if not args.api_base_url.startswith(("http://", "https://")):
        blockers.append("invalid_api_base_url")

    lowered_url = args.api_base_url.lower()
    blocked_markers = [
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "10.0.2.2",
        "mock",
        "demo",
        "local",
        "placeholder",
        "example.invalid",
    ]
    if not args.allow_demo_mock and any(marker in lowered_url for marker in blocked_markers):
        blockers.append(f"{args.channel}_api_cannot_be_mock_demo_or_local")

    if args.channel == "prod":
        if args.updater_channel != "prod":
            blockers.append("invalid_prod_updater_channel")
        if "dev" in args.app_label.lower():
            blockers.append("invalid_prod_app_label")
        if not args.release_tag.startswith("android-v"):
            blockers.append("invalid_release_tag")
    else:
        if args.updater_channel != "dev":
            blockers.append("invalid_dev_updater_channel")
        if "dev" not in args.app_label.lower():
            blockers.append("invalid_dev_app_label")
        if not args.release_tag.startswith("android-dev-v"):
            blockers.append("invalid_release_tag")

    evidence["expected_dart_defines"] = {
        "API_BASE_URL": args.api_base_url,
        "BRIDGE_APP_CHANNEL": args.channel,
        "BRIDGE_UPDATER_CHANNEL": args.updater_channel,
        "BRIDGE_APP_LABEL": args.app_label,
        "BRIDGE_ENVIRONMENT_COLOR": args.environment_color,
    }
    blockers = list(dict.fromkeys(blockers))
    print(
        json.dumps(
            {
                "kind": "codex.androidReleaseChannelDryRun",
                "version": 1,
                "ok": not blockers,
                "blockers": blockers,
                "evidence": evidence,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if not blockers else 1


def _read_pubspec_version(path: Path) -> str | None:
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^version:\s*(\S+)\s*$", line)
        if match:
            return match.group(1)
    return None


if __name__ == "__main__":
    sys.exit(main())
