#!/usr/bin/env python3
"""Validate Flutter apps that consume the Codex developer feedback package."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSOCIATIONS = (
    ROOT / "backend/app/infrastructure/config/app_release_associations.json"
)
DEFAULT_REGISTRY = ROOT / "backend/app/infrastructure/config/app_updates.json"
DEFAULT_COMPONENT = "codex_developer_feedback_template"
MINIMUM_DEPENDENCY_REFS = {
    "codex_developer_feedback_template": "codex-developer-feedback-template-v0.4.3",
}


class FeedbackIntegrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class AssociatedApp:
    source_app: str
    display_name: str
    repo: str
    local_path: Path
    pubspec_path: Path


@dataclass(frozen=True)
class Component:
    name: str
    dependency_name: str
    dependency_ref_prefix: str
    apps: tuple[AssociatedApp, ...]


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class AppReport:
    app: AssociatedApp
    checks: tuple[Check, ...]

    @property
    def ok(self) -> bool:
        return all(check.status != "fail" for check in self.checks)

    @property
    def warning_count(self) -> int:
        return sum(1 for check in self.checks if check.status == "warn")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate app-side Codex developer feedback wrapper integration. "
            "The command is read-only and is safe to run in CI."
        )
    )
    parser.add_argument("--component", default=DEFAULT_COMPONENT)
    parser.add_argument("--app", action="append", dest="apps")
    parser.add_argument("--associations", type=Path, default=DEFAULT_ASSOCIATIONS)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument(
        "--workspace-aliases",
        default=os.environ.get("FEEDBACK_SOURCE_WORKSPACE_ALIASES", ""),
        help=(
            "Comma-separated sourceApp:/workspace/path aliases. Defaults to "
            "FEEDBACK_SOURCE_WORKSPACE_ALIASES."
        ),
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings, such as missing workspace aliases, as failures.",
    )
    args = parser.parse_args()

    try:
        component = load_component(args.associations, args.component)
        registry = load_registry(args.registry)
        requested = set(args.apps or [])
        reports = [
            build_report(
                component=component,
                app=app,
                registry=registry,
                workspace_aliases=parse_workspace_aliases(args.workspace_aliases),
            )
            for app in select_apps(component, requested)
        ]
        emit(reports, json_output=args.json_output)
        has_failure = any(not report.ok for report in reports)
        has_warning = any(report.warning_count for report in reports)
        return 1 if has_failure or (args.strict and has_warning) else 0
    except FeedbackIntegrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def load_component(path: Path, name: str) -> Component:
    raw = read_json(path)
    if name not in raw:
        raise FeedbackIntegrationError(f"Component {name!r} is not configured in {path}.")
    payload = raw[name]
    apps = tuple(
        AssociatedApp(
            source_app=str(item["sourceApp"]),
            display_name=str(item.get("displayName") or item["sourceApp"]),
            repo=str(item["repo"]),
            local_path=(ROOT / str(item["localPath"])).resolve(),
            pubspec_path=Path(str(item["pubspecPath"])),
        )
        for item in payload.get("apps", [])
    )
    if not apps:
        raise FeedbackIntegrationError(f"Component {name!r} has no associated apps.")
    return Component(
        name=name,
        dependency_name=str(payload["dependencyName"]),
        dependency_ref_prefix=str(payload.get("dependencyRefPrefix") or ""),
        apps=apps,
    )


def load_registry(path: Path) -> dict[str, Any]:
    raw = read_json(path)
    if not isinstance(raw, dict):
        raise FeedbackIntegrationError(f"App update registry {path} must be an object.")
    return raw


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise FeedbackIntegrationError(f"Missing config file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise FeedbackIntegrationError(f"Invalid JSON in {path}: {exc}") from exc


def select_apps(component: Component, requested: set[str]) -> tuple[AssociatedApp, ...]:
    if not requested:
        return component.apps
    selected = tuple(app for app in component.apps if app.source_app in requested)
    missing = requested.difference(app.source_app for app in selected)
    if missing:
        raise FeedbackIntegrationError(
            f"Unknown app(s) for {component.name}: {', '.join(sorted(missing))}"
        )
    return selected


def build_report(
    *,
    component: Component,
    app: AssociatedApp,
    registry: dict[str, Any],
    workspace_aliases: dict[str, str],
) -> AppReport:
    checks = [
        check_local_path(app),
        check_registry(app, registry),
        *check_pubspec(component, app),
        *check_app_code(app),
        check_tests(app),
        check_workspace_alias(app, workspace_aliases),
    ]
    return AppReport(app=app, checks=tuple(checks))


def check_local_path(app: AssociatedApp) -> Check:
    if app.local_path.is_dir():
        return Check("local_path", "pass", str(app.local_path))
    return Check("local_path", "fail", f"Missing app repo at {app.local_path}")


def check_registry(app: AssociatedApp, registry: dict[str, Any]) -> Check:
    entry = registry.get(app.source_app)
    if not isinstance(entry, dict):
        return Check("registry", "fail", f"{app.source_app!r} is missing from registry")
    if entry.get("enabled") is not True:
        return Check("registry", "fail", f"{app.source_app!r} is disabled in registry")
    if entry.get("repo") != app.repo:
        return Check(
            "registry",
            "fail",
            f"repo mismatch: associations use {app.repo}, registry uses {entry.get('repo')}",
        )
    return Check("registry", "pass", "enabled app update registry entry")


def check_pubspec(component: Component, app: AssociatedApp) -> list[Check]:
    pubspec = app.local_path / app.pubspec_path
    text = read_optional_text(pubspec)
    if text is None:
        return [Check("pubspec", "fail", f"Missing {pubspec}")]

    checks = [Check("pubspec", "pass", str(pubspec))]
    block = dependency_block(text, component.dependency_name)
    if block is None:
        return [
            *checks,
            Check(
                "dependency",
                "fail",
                f"Missing dependency {component.dependency_name!r}",
            ),
        ]

    checks.append(Check("dependency", "pass", component.dependency_name))
    ref = yaml_scalar(block, "ref")
    if not ref:
        checks.append(Check("dependency_ref", "fail", "Missing git ref"))
    elif component.dependency_ref_prefix and not ref.startswith(
        component.dependency_ref_prefix
    ):
        checks.append(
            Check(
                "dependency_ref",
                "fail",
                f"{ref!r} must start with {component.dependency_ref_prefix!r}",
            )
        )
    else:
        checks.append(Check("dependency_ref", "pass", ref))
        minimum_ref = MINIMUM_DEPENDENCY_REFS.get(component.name)
        if minimum_ref and dependency_ref_is_older(
            ref,
            minimum_ref,
            component.dependency_ref_prefix,
        ):
            checks.append(
                Check(
                    "dependency_ref_minimum",
                    "fail",
                    (
                        f"{ref!r} is too old; upgrade to {minimum_ref!r} or newer "
                        "so feedback, updater, bridge diagnostics, and role gate "
                        "come from the reusable template."
                    ),
                )
            )
        elif minimum_ref:
            checks.append(Check("dependency_ref_minimum", "pass", minimum_ref))

    package_path = yaml_scalar(block, "path")
    if package_path == "packages/codex_developer_feedback_template":
        checks.append(Check("dependency_path", "pass", package_path))
    else:
        checks.append(
            Check(
                "dependency_path",
                "fail",
                "Expected path packages/codex_developer_feedback_template",
            )
        )
    return checks


def dependency_block(text: str, dependency_name: str) -> str | None:
    pattern = rf"(?ms)^  {re.escape(dependency_name)}:\n((?:    .*\n?)*)"
    match = re.search(pattern, text)
    if not match:
        return None
    return match.group(1)


def yaml_scalar(text: str, key: str) -> str | None:
    match = re.search(rf"(?m)^\s+{re.escape(key)}:\s*(.+?)\s*$", text)
    return match.group(1).strip("'\"") if match else None


def dependency_ref_is_older(ref: str, minimum_ref: str, prefix: str) -> bool:
    current_version = dependency_ref_version(ref, prefix)
    minimum_version = dependency_ref_version(minimum_ref, prefix)
    if current_version is None or minimum_version is None:
        return True
    return current_version < minimum_version


def dependency_ref_version(ref: str, prefix: str) -> tuple[int, ...] | None:
    if prefix and not ref.startswith(prefix):
        return None
    raw = ref[len(prefix) :] if prefix else ref
    match = re.match(r"^(\d+(?:\.\d+)*)", raw)
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def check_app_code(app: AssociatedApp) -> list[Check]:
    lib_dir = app.local_path / app.pubspec_path.parent / "lib"
    if not lib_dir.is_dir():
        return [Check("app_code", "fail", f"Missing {lib_dir}")]
    dart_files = sorted(path for path in lib_dir.rglob("*.dart") if path.is_file())
    if not dart_files:
        return [Check("app_code", "fail", f"No Dart files under {lib_dir}")]
    text = "\n".join(path.read_text(errors="ignore") for path in dart_files)
    checks = [Check("app_code", "pass", f"{len(dart_files)} Dart file(s) under {lib_dir}")]
    if "package:codex_developer_feedback_template/developer_feedback_template.dart" in text:
        checks.append(Check("import", "pass", "feedback package import"))
    else:
        checks.append(Check("import", "fail", "Missing feedback package import"))

    if "DeveloperFeedbackTemplate(" in text or "CodexDeveloperFeedbackTemplate(" in text:
        checks.append(Check("wrapper", "pass", "feedback template wrapper"))
        checks.append(check_wrapper_placement(text))
        checks.append(check_template_always_mounted(text))
    else:
        checks.append(Check("wrapper", "fail", "Missing feedback template wrapper"))

    if app.source_app in text and "CODEX_FEEDBACK_SOURCE_APP" in text:
        checks.append(Check("source_app", "pass", app.source_app))
    else:
        checks.append(
            Check(
                "source_app",
                "fail",
                f"Missing CODEX_FEEDBACK_SOURCE_APP default for {app.source_app}",
            )
        )

    if app.display_name in text and "CODEX_FEEDBACK_SOURCE_NAME" in text:
        checks.append(Check("source_display_name", "pass", app.display_name))
    else:
        checks.append(
            Check(
                "source_display_name",
                "fail",
                f"Missing CODEX_FEEDBACK_SOURCE_NAME default for {app.display_name}",
            )
        )

    if "developerFeedbackBridgeUrl" in text:
        checks.append(Check("bridge_url", "pass", "developerFeedbackBridgeUrl"))
    else:
        checks.append(
            Check("bridge_url", "fail", "Wrapper should use developerFeedbackBridgeUrl")
        )

    if "appUpdaterBridgeUrl:" in text or "developerFeedbackAppUpdaterBridgeUrl" in text:
        checks.append(
            Check(
                "template_updater_bridge",
                "pass",
                "feedback template receives updater Bridge URL",
            )
        )
    elif "CODEX_APP_UPDATER_BRIDGE_URL" in text:
        checks.append(
            Check(
                "template_updater_bridge",
                "warn",
                (
                    "CODEX_APP_UPDATER_BRIDGE_URL is present, but pass "
                    "appUpdaterBridgeUrl into DeveloperFeedbackTemplate when the "
                    "app resolves updater URLs in code."
                ),
            )
        )
    else:
        checks.append(
            Check(
                "template_updater_bridge",
                "fail",
                (
                    "Missing appUpdaterBridgeUrl/template updater configuration; "
                    "updates must be driven by codex_developer_feedback_template."
                ),
            )
        )

    if "CodexAppUpdater(" in text:
        checks.append(
            Check(
                "app_level_updater",
                "fail",
                (
                    "Remove app-level CodexAppUpdater wrapper; updater must be "
                    "embedded through codex_developer_feedback_template."
                ),
            )
        )
    else:
        checks.append(Check("app_level_updater", "pass", "no app-level updater wrapper"))

    if "CodexDeveloperRoleGate(" in text:
        checks.append(Check("role_gate", "pass", "reusable role gate wrapper"))
    else:
        checks.append(
            Check(
                "role_gate",
                "fail",
                (
                    "Missing CodexDeveloperRoleGate; default admin/role login must "
                    "come from codex_developer_feedback_template."
                ),
            )
        )
    return checks


def check_wrapper_placement(text: str) -> Check:
    unsafe_pattern = (
        r"(?:Codex)?DeveloperFeedbackTemplate\s*\("
        r"(?s:.*?)"
        r"child:\s*MaterialApp\s*\("
    )
    if re.search(unsafe_pattern, text):
        return Check(
            "wrapper_placement",
            "warn",
            "Place DeveloperFeedbackTemplate in MaterialApp.builder, not around MaterialApp",
        )
    return Check(
        "wrapper_placement",
        "pass",
        "feedback template is not wrapping MaterialApp directly",
    )


def check_template_always_mounted(text: str) -> Check:
    conditional_pattern = (
        r"if\s*\("
        r"(?s:[^)]*)"
        r"(?:developerFeedbackTemplateEnabled|feedbackTemplateEnabled|feedbackEnabled)"
        r"(?s:[^)]*)"
        r"\)\s*\{"
        r"(?s:.{0,600})"
        r"(?:Codex)?DeveloperFeedbackTemplate\s*\("
    )
    if re.search(conditional_pattern, text):
        return Check(
            "template_always_mounted",
            "fail",
            (
                "DeveloperFeedbackTemplate must always be mounted; pass the "
                "feedback flag to enabled: so updater, bridge diagnostics, and "
                "role support remain active when feedback tools are hidden."
            ),
        )
    return Check(
        "template_always_mounted",
        "pass",
        "feedback template is always mounted",
    )


def check_tests(app: AssociatedApp) -> Check:
    test_dir = app.local_path / app.pubspec_path.parent / "test"
    if not test_dir.is_dir():
        return Check("tests", "warn", f"Missing test directory {test_dir}")
    combined = "\n".join(
        path.read_text(errors="ignore")
        for path in sorted(test_dir.rglob("*.dart"))
        if path.is_file()
    )
    if "DeveloperFeedbackTemplate" in combined and app.source_app in combined:
        return Check("tests", "pass", "wrapper configuration is covered")
    return Check(
        "tests",
        "warn",
        "Add a widget test for DeveloperFeedbackTemplate sourceApp/displayName/bridgeUrl",
    )


def check_workspace_alias(app: AssociatedApp, aliases: dict[str, str]) -> Check:
    if app.source_app in aliases:
        path = Path(aliases[app.source_app]).expanduser()
        if path.exists():
            return Check("workspace_alias", "pass", aliases[app.source_app])
        return Check(
            "workspace_alias",
            "warn",
            f"Alias for {app.source_app} points to missing path {path}",
        )
    if app.local_path.exists():
        return Check("workspace_alias", "pass", f"registered localPath {app.local_path}")
    normalized_source = normalize_key(app.source_app)
    local_parts = {normalize_key(part) for part in app.local_path.parts}
    if normalized_source in local_parts:
        return Check("workspace_alias", "pass", "sourceApp matches local path name")
    return Check(
        "workspace_alias",
        "warn",
        (
            f"Set FEEDBACK_SOURCE_WORKSPACE_ALIASES with "
            f"{app.source_app}:{app.local_path}"
        ),
    )


def parse_workspace_aliases(raw: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for raw_entry in raw.split(","):
        entry = raw_entry.strip()
        if not entry or ":" not in entry:
            continue
        source_app, workspace_path = entry.split(":", 1)
        source_app = source_app.strip()
        workspace_path = workspace_path.strip()
        if source_app and workspace_path:
            aliases[source_app] = workspace_path
    return aliases


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def read_optional_text(path: Path) -> str | None:
    try:
        return path.read_text()
    except FileNotFoundError:
        return None


def emit(reports: list[AppReport], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps([report_to_json(report) for report in reports], indent=2))
        return
    for report in reports:
        status = "ok" if report.ok else "failed"
        print(f"{report.app.source_app}: {status}")
        for check in report.checks:
            marker = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}[check.status]
            print(f"  [{marker}] {check.name}: {check.detail}")


def report_to_json(report: AppReport) -> dict[str, Any]:
    return {
        "sourceApp": report.app.source_app,
        "displayName": report.app.display_name,
        "repo": report.app.repo,
        "localPath": str(report.app.local_path),
        "pubspecPath": str(report.app.pubspec_path),
        "ok": report.ok,
        "checks": [
            {"name": check.name, "status": check.status, "detail": check.detail}
            for check in report.checks
        ],
    }


if __name__ == "__main__":
    sys.exit(main())
