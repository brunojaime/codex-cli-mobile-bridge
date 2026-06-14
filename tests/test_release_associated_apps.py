from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts/release_associated_apps.py"
SPEC = importlib.util.spec_from_file_location("release_associated_apps", SCRIPT_PATH)
assert SPEC is not None
releases = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = releases
SPEC.loader.exec_module(releases)


def test_build_plan_reports_complete_json_shape(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path)
    component = releases.load_component(fixture.associations, "codex_app_updater")
    plan = _build_plan(component, fixture.registry)

    assert plan.current_version == "1.0.0"
    assert plan.current_build == 56
    assert plan.next_version == "1.0.0+57"
    assert plan.current_dependency_ref == "codex-app-updater-v0.1.1"
    assert plan.next_dependency_ref == "codex-app-updater-v0.1.2"
    assert plan.release_branch == (
        "release/ambientando-calendar/"
        "android-local-demo-feedback-v1.0.0-build.57"
    )
    assert plan.release_tag == "android-local-demo-feedback-v1.0.0-build.57"

    payload = _run_script(
        [
            "--associations",
            str(fixture.associations),
            "--registry",
            str(fixture.registry),
            "--dependency-ref",
            "codex-app-updater-v0.1.2",
            "--json",
        ]
    )
    item = json.loads(payload.stdout)[0]
    assert item["repo"] == "brunojaime/ambientando-calendar"
    assert item["localPath"] == str(fixture.app_repos[0])
    assert item["dependencyUrl"] == str(fixture.dependency_repo)
    assert item["currentDependencyRef"] == "codex-app-updater-v0.1.1"
    assert item["nextDependencyRef"] == "codex-app-updater-v0.1.2"
    assert item["currentVersion"] == "1.0.0+56"
    assert item["nextVersion"] == "1.0.0+57"
    assert item["branch"] == plan.release_branch
    assert item["releaseTag"] == plan.release_tag
    assert item["releaseWorkflow"] == "Android Release"
    assert any(command.startswith("git checkout -b ") for command in item["commands"])


def test_dry_run_does_not_modify_repo_files_branch_or_tags(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path)
    _init_app_repo(fixture.app_repos[0])
    original_pubspec = _pubspec(fixture.app_repos[0]).read_text()

    _run_script(
        [
            "--dry-run",
            "--associations",
            str(fixture.associations),
            "--registry",
            str(fixture.registry),
            "--dependency-ref",
            "codex-app-updater-v0.1.2",
            "--json",
        ]
    )

    assert _pubspec(fixture.app_repos[0]).read_text() == original_pubspec
    assert _git(["branch", "--show-current"], fixture.app_repos[0]).stdout.strip() == (
        "main"
    )
    assert _git(["tag", "--list"], fixture.app_repos[0]).stdout.strip() == ""
    assert _git(["status", "--porcelain"], fixture.app_repos[0]).stdout.strip() == ""


def test_execute_plan_updates_only_target_dependency_ref_commits_branch_and_tags(
    tmp_path: Path,
) -> None:
    fixture = _write_fixture(tmp_path, include_other_ref=True)
    _init_app_repo(fixture.app_repos[0])
    component = releases.load_component(fixture.associations, "codex_app_updater")
    plan = _build_plan(component, fixture.registry)

    releases.preflight([plan])
    releases.execute_plan(plan, push=False)

    pubspec = _pubspec(fixture.app_repos[0]).read_text()
    assert "version: 1.0.0+57" in pubspec
    assert "ref: codex-app-updater-v0.1.2" in pubspec
    assert "ref: other-package-v9" in pubspec
    assert _git(["branch", "--show-current"], fixture.app_repos[0]).stdout.strip() == (
        plan.release_branch
    )
    assert _git(["tag", "--points-at", "HEAD"], fixture.app_repos[0]).stdout.strip() == (
        "android-local-demo-feedback-v1.0.0-build.57"
    )


def test_preflight_aborts_dirty_staged_worktree_before_any_mutation(
    tmp_path: Path,
) -> None:
    fixture = _write_fixture(tmp_path, app_count=2)
    for repo in fixture.app_repos:
        _init_app_repo(repo)
    (_pubspec(fixture.app_repos[1]).parent / "staged.txt").write_text("staged")
    _git(["add", "frontend/staged.txt"], fixture.app_repos[1])
    component = releases.load_component(fixture.associations, "codex_app_updater")
    plans = [
        releases.build_plan(
            component=component,
            app=app,
            registry=releases.load_registry(fixture.registry),
            dependency_ref="codex-app-updater-v0.1.2",
        )
        for app in component.apps
    ]

    with pytest.raises(releases.ReleasePlanError, match="Preflight failed"):
        releases.preflight(plans)

    assert "version: 1.0.0+56" in _pubspec(fixture.app_repos[0]).read_text()
    assert _git(["tag", "--list"], fixture.app_repos[0]).stdout.strip() == ""
    assert _git(["branch", "--show-current"], fixture.app_repos[0]).stdout.strip() == (
        "main"
    )


def test_preflight_aborts_existing_tag_or_branch(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path)
    _init_app_repo(fixture.app_repos[0])
    component = releases.load_component(fixture.associations, "codex_app_updater")
    plan = _build_plan(component, fixture.registry)

    _git(["tag", plan.release_tag], fixture.app_repos[0])
    with pytest.raises(releases.ReleasePlanError, match="Tag already exists"):
        releases.preflight([plan])
    _git(["tag", "-d", plan.release_tag], fixture.app_repos[0])
    _git(["branch", plan.release_branch], fixture.app_repos[0])

    with pytest.raises(releases.ReleasePlanError, match="Release branch already exists"):
        releases.preflight([plan])


def test_dependency_ref_must_be_resolvable(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path)
    component = releases.load_component(fixture.associations, "codex_app_updater")

    with pytest.raises(releases.ReleasePlanError, match="not resolvable"):
        releases.build_plan(
            component=component,
            app=component.apps[0],
            registry=releases.load_registry(fixture.registry),
            dependency_ref="codex-app-updater-v9.9.9",
        )


def test_registry_missing_or_disabled_app_fails(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path)
    component = releases.load_component(fixture.associations, "codex_app_updater")
    registry_payload = json.loads(fixture.registry.read_text())
    registry_payload.pop("ambientando-calendar")
    fixture.registry.write_text(json.dumps(registry_payload))

    with pytest.raises(releases.ReleasePlanError, match="missing"):
        _build_plan(component, fixture.registry)

    fixture = _write_fixture(tmp_path / "disabled")
    component = releases.load_component(fixture.associations, "codex_app_updater")
    registry_payload = json.loads(fixture.registry.read_text())
    registry_payload["ambientando-calendar"]["enabled"] = False
    fixture.registry.write_text(json.dumps(registry_payload))

    with pytest.raises(releases.ReleasePlanError, match="not enabled"):
        _build_plan(component, fixture.registry)


def test_default_associations_reference_enabled_registry_entries() -> None:
    registry = releases.load_registry(releases.DEFAULT_REGISTRY)

    for component_name in (
        "codex_app_updater",
        "codex_developer_feedback_template",
    ):
        component = releases.load_component(
            releases.DEFAULT_ASSOCIATIONS,
            component_name,
        )

        for app in component.apps:
            releases.validate_registry(app, registry)


def test_xr18_default_release_association_uses_android_release_tags() -> None:
    registry = releases.load_registry(releases.DEFAULT_REGISTRY)

    for component_name in (
        "codex_developer_feedback_template",
        "codex_app_updater",
    ):
        component = releases.load_component(
            releases.DEFAULT_ASSOCIATIONS,
            component_name,
        )
        xr18 = next(
            app for app in component.apps if app.source_app == "xr18-mobile-control"
        )

        assert xr18.release_tag_prefix == "android-v"
        assert xr18.repo == "brunojaime/xr18-mobile-control"
        assert str(xr18.local_path).endswith("/xr18-mobile-control")
        assert xr18.pubspec_path == Path("pubspec.yaml")
        releases.validate_registry(xr18, registry)

    assert registry["xr18-mobile-control"]["releaseTagPattern"] == "android-v*"
    assert (
        registry["xr18-mobile-control"]["apkAssetPattern"]
        == "xr18-mobile-control-*.apk"
    )


def test_smart_house_is_not_release_associated_until_flutter_app_is_tracked() -> None:
    registry = releases.load_registry(releases.DEFAULT_REGISTRY)

    assert registry["smart-nienfos-smart-house"]["enabled"] is False
    for component_name in (
        "codex_developer_feedback_template",
        "codex_app_updater",
    ):
        component = releases.load_component(
            releases.DEFAULT_ASSOCIATIONS,
            component_name,
        )
        assert all(
            app.source_app != "smart-nienfos-smart-house" for app in component.apps
        )


class Fixture:
    def __init__(
        self,
        *,
        associations: Path,
        registry: Path,
        dependency_repo: Path,
        app_repos: list[Path],
    ) -> None:
        self.associations = associations
        self.registry = registry
        self.dependency_repo = dependency_repo
        self.app_repos = app_repos


def _write_fixture(
    tmp_path: Path,
    *,
    app_count: int = 1,
    include_other_ref: bool = False,
) -> Fixture:
    tmp_path.mkdir(parents=True, exist_ok=True)
    dependency_repo = tmp_path / "codex-cli-mobile-bridge"
    _init_dependency_repo(dependency_repo)
    app_repos = [tmp_path / f"ambientando-calendar-{index}" for index in range(app_count)]
    apps = []
    registry = {}
    for index, app_repo in enumerate(app_repos):
        source_app = "ambientando-calendar" if index == 0 else f"ambientando-calendar-{index}"
        display_name = "Ambientando Calendar" if index == 0 else f"Ambientando {index}"
        _write_app_pubspec(
            app_repo,
            dependency_repo=dependency_repo,
            include_other_ref=include_other_ref,
        )
        apps.append(
            {
                "sourceApp": source_app,
                "displayName": display_name,
                "repo": f"brunojaime/{source_app}",
                "localPath": str(app_repo),
                "defaultBranch": "main",
                "pubspecPath": "frontend/pubspec.yaml",
                "releaseTagPrefix": "android-local-demo-feedback-v",
                "releaseWorkflow": "Android Release",
            }
        )
        registry[source_app] = {
            "displayName": display_name,
            "repo": f"brunojaime/{source_app}",
            "releaseTagPattern": "android-local-demo-feedback-v*",
            "apkAssetPattern": "ambientando-calendar-*.apk",
            "latestAssetName": "ambientando-calendar.apk",
            "enabled": True,
        }
    associations = tmp_path / "associations.json"
    associations.write_text(
        json.dumps(
            {
                "codex_app_updater": {
                    "displayName": "Codex App Updater",
                    "dependencyName": "codex_app_updater",
                    "dependencyRefPrefix": "codex-app-updater-v",
                    "apps": apps,
                }
            }
        )
    )
    registry_path = tmp_path / "app_updates.json"
    registry_path.write_text(json.dumps(registry))
    return Fixture(
        associations=associations,
        registry=registry_path,
        dependency_repo=dependency_repo,
        app_repos=app_repos,
    )


def _init_dependency_repo(repo: Path) -> None:
    repo.mkdir(parents=True)
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "tests@example.com"], repo)
    _git(["config", "user.name", "Tests"], repo)
    (repo / "README.md").write_text("dependency")
    _git(["add", "."], repo)
    _git(["commit", "-m", "Initial dependency"], repo)
    _git(["tag", "codex-app-updater-v0.1.1"], repo)
    _git(["tag", "codex-app-updater-v0.1.2"], repo)


def _write_app_pubspec(
    repo: Path,
    *,
    dependency_repo: Path,
    include_other_ref: bool,
) -> None:
    (repo / "frontend").mkdir(parents=True)
    other_dep = (
        """
  other_package:
    git:
      url: https://example.test/other.git
      ref: other-package-v9
      path: packages/other
"""
        if include_other_ref
        else ""
    )
    _pubspec(repo).write_text(
        f"""
name: ambientando_calendar_frontend
version: 1.0.0+56
dependencies:
  codex_app_updater:
    git:
      url: {dependency_repo}
      ref: codex-app-updater-v0.1.1
      path: packages/codex_app_updater
{other_dep}
""".lstrip()
    )


def _init_app_repo(repo: Path) -> None:
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "tests@example.com"], repo)
    _git(["config", "user.name", "Tests"], repo)
    _git(["add", "."], repo)
    _git(["commit", "-m", "Initial app"], repo)


def _build_plan(component: object, registry: Path) -> object:
    return releases.build_plan(
        component=component,
        app=component.apps[0],
        registry=releases.load_registry(registry),
        dependency_ref="codex-app-updater-v0.1.2",
    )


def _pubspec(repo: Path) -> Path:
    return repo / "frontend/pubspec.yaml"


def _run_script(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _git(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *command],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
