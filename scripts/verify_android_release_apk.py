#!/usr/bin/env python3
"""Verify a built Codex Mobile release APK before publication."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any


EXPECTED_BY_CHANNEL = {
    "prod": {
        "package_id": "com.example.codex_mobile_frontend",
        "variant": "prodRelease",
        "output_file": "app-prod-release.apk",
    },
    "dev": {
        "package_id": "com.example.codex_mobile_frontend.dev",
        "variant": "devRelease",
        "output_file": "app-dev-release.apk",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed verification for Codex Mobile Android APKs."
    )
    parser.add_argument("--channel", required=True, choices=sorted(EXPECTED_BY_CHANNEL))
    parser.add_argument("--apk", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--expected-package-id", default=None)
    parser.add_argument("--expected-output-file", default=None)
    args = parser.parse_args()

    expected = dict(EXPECTED_BY_CHANNEL[args.channel])
    if args.expected_package_id:
        expected["package_id"] = args.expected_package_id
    if args.expected_output_file:
        expected["output_file"] = args.expected_output_file

    apk_path = Path(args.apk)
    metadata_path = Path(args.metadata)
    blockers: list[str] = []
    evidence: dict[str, Any] = {
        "channel": args.channel,
        "apk": str(apk_path),
        "metadata": str(metadata_path),
        "expected": expected,
    }

    if not apk_path.is_file():
        blockers.append("missing_apk")
    elif apk_path.name != expected["output_file"]:
        blockers.append("apk_file_name_mismatch")
    if not metadata_path.is_file():
        blockers.append("missing_output_metadata")
    else:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            evidence["metadata"] = _metadata_evidence(metadata)
            _validate_metadata(metadata, expected, blockers)
        except json.JSONDecodeError:
            blockers.append("invalid_output_metadata_json")

    aapt = _find_aapt()
    evidence["aapt"] = aapt or None
    if aapt and apk_path.is_file():
        package_id = _read_aapt_package(aapt, apk_path, blockers)
        evidence["aapt_package_id"] = package_id
        if package_id != expected["package_id"]:
            blockers.append("apk_package_id_mismatch")

    blockers = list(dict.fromkeys(blockers))
    print(
        json.dumps(
            {
                "kind": "codex.androidReleaseApkVerification",
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


def _metadata_evidence(metadata: dict[str, Any]) -> dict[str, Any]:
    elements = metadata.get("elements")
    element = elements[0] if isinstance(elements, list) and elements else {}
    return {
        "application_id": metadata.get("applicationId"),
        "variant_name": metadata.get("variantName"),
        "output_file": element.get("outputFile") if isinstance(element, dict) else None,
        "version_code": element.get("versionCode") if isinstance(element, dict) else None,
        "version_name": element.get("versionName") if isinstance(element, dict) else None,
    }


def _validate_metadata(
    metadata: dict[str, Any],
    expected: dict[str, str],
    blockers: list[str],
) -> None:
    if metadata.get("applicationId") != expected["package_id"]:
        blockers.append("metadata_application_id_mismatch")
    if metadata.get("variantName") != expected["variant"]:
        blockers.append("metadata_variant_mismatch")
    elements = metadata.get("elements")
    if not isinstance(elements, list) or len(elements) != 1:
        blockers.append("metadata_elements_invalid")
        return
    element = elements[0]
    if not isinstance(element, dict):
        blockers.append("metadata_elements_invalid")
        return
    if element.get("outputFile") != expected["output_file"]:
        blockers.append("metadata_output_file_mismatch")


def _find_aapt() -> str | None:
    direct = shutil.which("aapt")
    if direct:
        return direct
    roots = [
        Path(value)
        for value in [
            *filter(None, [os.environ.get("ANDROID_HOME")]),
            *filter(None, [os.environ.get("ANDROID_SDK_ROOT")]),
            str(Path.home() / "Android" / "Sdk"),
        ]
    ]
    candidates: list[Path] = []
    for root in roots:
        if root.exists():
            candidates.extend(root.glob("build-tools/*/aapt"))
    if not candidates:
        return None
    return str(sorted(candidates)[-1])


def _read_aapt_package(aapt: str, apk_path: Path, blockers: list[str]) -> str | None:
    try:
        result = subprocess.run(
            [aapt, "dump", "badging", str(apk_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        blockers.append("aapt_failed")
        return None
    if result.returncode != 0:
        blockers.append("aapt_failed")
        return None
    match = re.search(r"package: name='([^']+)'", result.stdout)
    if not match:
        blockers.append("aapt_package_missing")
        return None
    return match.group(1)


if __name__ == "__main__":
    sys.exit(main())
