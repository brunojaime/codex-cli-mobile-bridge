"""Register immutable, already published preview artifacts in the local Bridge."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request
from urllib.parse import urlsplit
from datetime import datetime, timezone


def register(root: Path, display_name: str) -> dict:
    if not display_name.strip() or len(display_name) > 160:
        raise ValueError("Invalid display name")
    config = json.loads((root / "infra/mobile/release.json").read_text())
    project = json.loads((root / "infra/mobile/project.json").read_text())
    tag = f"android-{config['profile']}-v{config['version']}-build.{config['androidBuild']}"
    if not re.fullmatch(r"android-preview-v\d+\.\d+\.\d+-build\.\d+", tag):
        raise ValueError(
            "This catalog tool supports preview APKs; store promotion is separate"
        )
    output = root / "dist/mobile" / tag
    receipt = json.loads((output / "release.json").read_text())
    validation = json.loads((output / "validation.json").read_text())
    source = project["sourceApp"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", source):
        raise ValueError("Invalid sourceApp")
    target = project["profiles"]["preview"]
    if (
        receipt["tag"] != tag
        or receipt["sourceApp"] != source
        or receipt["packageId"] != target["androidApplicationId"]
        or receipt["apiOrigin"] != target["apiBaseUrl"]
        or receipt.get("mockOrDemo") is not False
        or validation.get("apkSha256") != receipt["sha256"]
        or validation.get("installLaunch") is not True
    ):
        raise ValueError("Release identity or runtime validation mismatch")
    result = subprocess.run(
        [
            "gh",
            "release",
            "view",
            tag,
            "--repo",
            config["repository"],
            "--json",
            "assets,isPrerelease,url",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode:
        raise ValueError("Published GitHub release could not be verified")
    published = json.loads(result.stdout)
    asset = next(
        (a for a in published["assets"] if a["name"] == receipt["artifact"]), None
    )
    if (
        not published["isPrerelease"]
        or not asset
        or asset.get("digest") != "sha256:" + receipt["sha256"]
    ):
        raise ValueError("Published artifact does not match validated build")
    token = os.environ.get("INSTALLABLE_APPS_REGISTRATION_TOKEN", "")
    if not token:
        raise ValueError(
            "Configure the Bridge registration credential in the service environment"
        )
    base = "http://127.0.0.1:8000"
    payload = {
        "sourceApp": source,
        "displayName": display_name,
        "repo": config["repository"],
        "releaseTagPattern": "android-preview-v*",
        "apkAssetPattern": receipt["artifact"],
        "latestAssetName": receipt["artifact"],
        "releaseChannel": "prerelease",
        "expectedPackageId": receipt["packageId"],
        "verifiedPackageIds": {
            tag: receipt["packageId"],
            receipt["artifact"]: receipt["packageId"],
        },
        "previewUrl": receipt["apiOrigin"],
        "runtimeProfile": "preview",
        "productionReady": False,
        "mockOrDemo": False,
        "enabled": True,
        "releaseMetadata": {
            k: receipt[k]
            for k in (
                "tag",
                "sha256",
                "gitCommit",
                "toolkitVersion",
                "signingCertificateSha256",
            )
        },
    }
    request = urllib.request.Request(
        base + "/installable-apps",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Bridge-Registration-Token": token,
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 201:
            raise ValueError("Catalog registration failed")
    with urllib.request.urlopen(
        base + "/installable-apps/" + source, timeout=60
    ) as response:
        detail = json.load(response)
    if (
        not detail.get("available")
        or detail.get("releaseTag") != tag
        or detail.get("sha256") != receipt["sha256"]
        or detail.get("packageId") != receipt["packageId"]
    ):
        raise ValueError("Catalog does not resolve the validated release")
    url = urlsplit(detail["apkUrl"])
    if not url.path.startswith("/app-updates/"):
        raise ValueError("Catalog download must use the Bridge proxy")
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(
        base + url.path + ("?" + url.query if url.query else ""), timeout=120
    ) as response:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    if digest.hexdigest() != receipt["sha256"] or size != asset["size"]:
        raise ValueError("Bridge download digest or size mismatch")
    evidence = {
        "schema": "nienfos.mobile-catalog-validation/v1",
        "sourceApp": source,
        "displayName": display_name,
        "tag": tag,
        "packageId": receipt["packageId"],
        "sha256": digest.hexdigest(),
        "sizeBytes": size,
        "available": True,
        "downloadVerified": True,
        "releaseUrl": published["url"],
        "runtimeProfile": "preview",
        "productionReady": False,
        "verifiedAt": datetime.now(timezone.utc).isoformat(),
    }
    (output / "catalog-validation.json").write_text(
        json.dumps(evidence, indent=2) + "\n"
    )
    return evidence
