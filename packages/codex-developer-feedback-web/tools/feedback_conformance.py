"""Cross-platform extension of developer_feedback_integration; no remote writes."""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assess(root: Path, release_path: Path):
    root = root.resolve()
    release = json.loads(release_path.read_text())
    manifest_path = root / "feedback.project.json"
    checks = []

    def check(name, ok, detail):
        checks.append(
            {"name": name, "status": "pass" if ok else "fail", "detail": detail}
        )

    if not manifest_path.is_file():
        return {
            "root": str(root),
            "ok": False,
            "checks": [
                {
                    "name": "manifest",
                    "status": "fail",
                    "detail": "feedback.project.json missing",
                }
            ],
        }
    manifest = json.loads(manifest_path.read_text())
    for value in [
        manifest.get("artifact", "missing"),
        manifest.get("packageManifest", "missing"),
        manifest.get("packageRoot", "missing"),
        *manifest.get("entryPoints", []),
    ]:
        target = root / value
        if (
            not isinstance(value, str)
            or Path(value).is_absolute()
            or ".." in Path(value).parts
            or not target.resolve().is_relative_to(root)
        ):
            raise ValueError("Consumer path escapes workspace")
    check(
        "schema",
        manifest.get("schema") == "codex.feedback-consumer/v1",
        "Explicit consumer contract",
    )
    check(
        "source",
        bool(
            re.fullmatch(
                r"[a-zA-Z0-9][a-zA-Z0-9_-]{1,119}", manifest.get("sourceApp", "")
            )
        ),
        "Stable sourceApp",
    )
    check(
        "environment",
        manifest.get("enabledEnvironments") == ["dev"],
        "Only dev is enabled",
    )
    check(
        "scope",
        manifest.get("queueScopePolicy") in ("session", "internal-operator"),
        "Explicit queue identity policy",
    )
    check("release", manifest.get("release") == release["id"], release["id"])
    check(
        "integration_state",
        manifest.get("integrationState", "ready") == "ready",
        manifest.get("integrationState", "ready"),
    )
    platform = manifest.get("platform")
    package = release["packages"].get("flutter" if platform == "flutter" else "web")
    check("platform", platform in ("web", "flutter", "react-native"), str(platform))
    if not package:
        return {
            "root": str(root),
            "sourceApp": manifest.get("sourceApp"),
            "ok": False,
            "checks": checks,
        }
    artifact = root / manifest.get("artifact", "missing")
    check(
        "artifact",
        artifact.is_file() and digest(artifact) == package["sha256"],
        "Exact approved artifact SHA-256",
    )
    dependency = root / manifest.get("packageManifest", "missing")
    if dependency.is_file():
        text = dependency.read_text()
        if platform == "flutter":
            # Vendored snapshots are permitted only with exact file hashes.
            check(
                "dependency",
                "codex_developer_feedback_template:" in text
                and (package["version"] in text or manifest.get("packageRoot")),
                "Approved Flutter package reference",
            )
        else:
            deps = json.loads(text)
            spec = {
                **deps.get("dependencies", {}),
                **deps.get("devDependencies", {}),
            }.get("@codex/developer-feedback-web", "")
            check(
                "dependency",
                spec.startswith("file:")
                and (dependency.parent / spec[5:]).resolve() == artifact.resolve(),
                "Manifest resolves the approved artifact",
            )
    else:
        check("dependency", False, "Package manifest missing")
    entries = manifest.get("entryPoints", [])
    check(
        "entries",
        bool(entries) and all((root / p).is_file() for p in entries),
        "Consumer mount/config entrypoints exist",
    )
    content = "\n".join((root / p).read_text() for p in entries if (root / p).is_file())
    expected = (
        "codex_developer_feedback_template"
        if platform == "flutter"
        else "@codex/developer-feedback-web"
    )
    check("shared_import", expected in content, "Uses official adapter")
    if platform != "flutter":
        check(
            "mount",
            ("mountFeedback" if platform == "web" else "createNativeFeedback")
            in content,
            "Official public mount/client",
        )
    else:
        check(
            "mount",
            bool(
                re.search(
                    r"(?:DeveloperFeedbackTemplate|CodexDeveloperFeedbackTemplate)\s*\(",
                    content,
                )
            ),
            "Official wrapper",
        )
    forbidden = re.compile(
        r"feedback-batches/start-session|developer-feedback/batches|new\s+MediaRecorder|from\s+['\"]html2canvas|shadowRoot|inject:\s*\[.*feedback-transport"
    )
    for entry in entries:
        f = root / entry
        if f.is_file():
            check(
                "no_local_engine:" + entry,
                not forbidden.search(f.read_text()),
                "No copied transport/capture or private widget access",
            )
    if manifest.get("packageRoot"):
        package_root = root / manifest["packageRoot"]
        expected_files = package.get("files", {})
        check(
            "snapshot_files",
            bool(expected_files)
            and all(
                (package_root / p).is_file() and digest(package_root / p) == h
                for p, h in expected_files.items()
            ),
            "Vendored snapshot matches every approved source file",
        )
        extra_sources = set(
            str(p.relative_to(package_root)) for p in package_root.rglob("*.dart")
        ) - set(expected_files)
        check(
            "snapshot_extra_sources",
            not extra_sources,
            "No additional unapproved Dart sources",
        )
    if platform == "flutter":
        check(
            "resolved_package",
            bool(manifest.get("packageRoot")),
            "Managed Flutter snapshot required",
        )
        block = (
            re.search(
                r"(?m)^  codex_developer_feedback_template:\s*\n((?:    .*(?:\n|$))+)",
                dependency.read_text(),
            )
            if dependency.is_file()
            else None
        )
        declared_path = (
            re.search(r"(?m)^    path:\s*([^\n]+)", block[1]) if block else None
        )
        expected_root = (
            root
            / manifest.get("packageRoot", "missing")
            / "codex_developer_feedback_template"
        )
        check(
            "dependency_path",
            bool(declared_path)
            and (dependency.parent / declared_path[1].strip()).resolve()
            == expected_root.resolve(),
            "Flutter dependency resolves the verified snapshot",
        )
    else:
        location = dependency.parent
        installed = location / "node_modules/@codex/developer-feedback-web"
        while not installed.is_dir() and location != root and root in location.parents:
            location = location.parent
            installed = location / "node_modules/@codex/developer-feedback-web"
        expected_files = package.get("files", {})
        check(
            "installed_files",
            bool(expected_files)
            and installed.is_dir()
            and all(
                (installed / p).is_file() and digest(installed / p) == h
                for p, h in expected_files.items()
            ),
            "Installed official bytes match descriptor",
        )
    return {
        "root": str(root),
        "sourceApp": manifest.get("sourceApp"),
        "platform": platform,
        "release": manifest.get("release"),
        "ok": all(c["status"] == "pass" for c in checks),
        "checks": checks,
        "deployed": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = assess(args.project, args.release)
    except (OSError, ValueError, KeyError, TypeError) as error:
        report = {"ok": False, "code": type(error).__name__}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
