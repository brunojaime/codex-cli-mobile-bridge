#!/usr/bin/env python3
"""Publish a shared Flutter web build to the four installed Lenovo shortcuts.

Only local web assets change. Each front retains its backend and environment;
old builds are retained under the runtime's backups directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil


def configure(
    directory: Path, *, port: int, label: str, channel: str, revision: str
) -> None:
    (directory / "bridge-config.json").write_text(
        json.dumps(
            {
                "api_base_url": f"http://127.0.0.1:{port}",
                "app_label": label,
                "source_app": "codex-mobile-dev"
                if channel == "dev"
                else "codex-mobile",
                "updater_channel": channel,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    version_path = directory / "version.json"
    version = json.loads(version_path.read_text())
    version.update(
        local_revision=revision,
        api_base_url=f"http://127.0.0.1:{port}",
        app_label=label,
    )
    version_path.write_text(json.dumps(version, ensure_ascii=False, indent=2) + "\n")


def publish(build: Path, runtime: Path) -> list[dict]:
    if not (build / "main.dart.js").is_file() or not (build / "version.json").is_file():
        raise ValueError("A completed Flutter web build is required.")
    digest = hashlib.sha256((build / "main.dart.js").read_bytes()).hexdigest()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    revision = f"activity-{timestamp}-{digest[:12]}"
    backup = runtime / "backups" / f"fronts-{timestamp}"
    backup.mkdir(parents=True, exist_ok=False)
    targets = [
        (
            "lenovo-dev",
            runtime / "web-dev",
            5178,
            8001,
            "Codex Bridge Lenovo DEV",
            "dev",
        ),
        (
            "lenovo-prod",
            runtime / "web-prod",
            5179,
            8000,
            "Codex Bridge Lenovo PROD",
            "prod",
        ),
        (
            "batata-dev",
            runtime / "batata/web-dev",
            5188,
            18201,
            "Codex Bridge Batata DEV",
            "dev",
        ),
        (
            "batata-prod",
            runtime / "batata/web-prod",
            5189,
            18200,
            "Codex Bridge Batata PROD",
            "prod",
        ),
    ]
    results = []
    for name, directory, web_port, api_port, label, channel in targets:
        if not directory.is_dir():
            raise ValueError(f"Installed front is missing: {directory}")
        staged = directory.with_name(f"{directory.name}.incoming-{timestamp}")
        shutil.copytree(build, staged)
        configure(
            staged, port=api_port, label=label, channel=channel, revision=revision
        )
        old = backup / name
        directory.rename(old)
        try:
            staged.rename(directory)
        except Exception:
            old.rename(directory)
            raise
        results.append(
            {
                "target": name,
                "url": f"http://127.0.0.1:{web_port}",
                "api_url": f"http://127.0.0.1:{api_port}",
                "revision": revision,
                "main_sha256": digest,
                "backup": str(old),
            }
        )
    configure(
        build,
        port=8011,
        label="Codex Bridge Lenovo · Actividad",
        channel="dev",
        revision=revision,
    )
    (backup / "publication.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n"
    )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=Path.home() / ".local/share/codex-bridge-runtime",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            publish(args.build_dir.resolve(), args.runtime_root.resolve()),
            ensure_ascii=False,
            indent=2,
        )
    )
