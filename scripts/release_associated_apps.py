#!/usr/bin/env python3
"""Prepare associated app releases when a shared Flutter package changes."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSOCIATIONS = (
    ROOT / "backend/app/infrastructure/config/app_release_associations.json"
)
DEFAULT_REGISTRY = ROOT / "backend/app/infrastructure/config/app_updates.json"


class ReleasePlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class AssociatedApp:
    source_app: str
    display_name: str
    repo: str
    local_path: Path
    default_branch: str
    pubspec_path: Path
    release_tag_prefix: str
    release_workflow: str


@dataclass(frozen=True)
class Component:
    name: str
    display_name: str
    dependency_name: str
    dependency_ref_prefix: str
    apps: tuple[AssociatedApp, ...]


@dataclass(frozen=True)
class AppReleasePlan:
    app: AssociatedApp
    dependency_name: str
    dependency_url: str | None
    current_version: str
    current_build: int
    next_version: str
    next_build: int
    current_dependency_ref: str | None
    next_dependency_ref: str | None
    release_branch: str
    release_tag: str
    commands: tuple[str, ...]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bump and tag app releases that embed a shared Flutter package. "
            "Dry-run by default; use --execute to edit target repos."
        )
    )
    parser.add_argument("--component", default="codex_app_updater")
    parser.add_argument("--app", action="append", dest="apps")
    parser.add_argument("--dependency-ref")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--allow-existing-branch", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--associations", type=Path, default=DEFAULT_ASSOCIATIONS)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    args = parser.parse_args()

    try:
        if args.push and not args.execute:
            raise ReleasePlanError("--push requires --execute.")
        component = load_component(args.associations, args.component)
        registry = load_registry(args.registry)
        selected_apps = select_apps(component, set(args.apps or []))
        plans = [
            build_plan(
                component=component,
                app=app,
                registry=registry,
                dependency_ref=args.dependency_ref,
            )
            for app in selected_apps
        ]
        if args.execute:
            preflight(plans, allow_existing_branch=args.allow_existing_branch)
            for plan in plans:
                execute_plan(
                    plan,
                    push=args.push,
                    allow_existing_branch=args.allow_existing_branch,
                )
        emit(
            plans, json_output=args.json_output, executed=args.execute, pushed=args.push
        )
    except ReleasePlanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def load_component(path: Path, name: str) -> Component:
    raw = read_json(path)
    if name not in raw:
        raise ReleasePlanError(f"Component {name!r} is not configured in {path}.")
    payload = raw[name]
    apps = tuple(
        AssociatedApp(
            source_app=str(item["sourceApp"]),
            display_name=str(item.get("displayName") or item["sourceApp"]),
            repo=str(item["repo"]),
            local_path=(ROOT / str(item["localPath"])).resolve(),
            default_branch=str(item.get("defaultBranch") or "main"),
            pubspec_path=Path(str(item["pubspecPath"])),
            release_tag_prefix=str(item["releaseTagPrefix"]),
            release_workflow=str(item.get("releaseWorkflow") or ""),
        )
        for item in payload.get("apps", [])
    )
    if not apps:
        raise ReleasePlanError(f"Component {name!r} has no associated apps.")
    return Component(
        name=name,
        display_name=str(payload.get("displayName") or name),
        dependency_name=str(payload["dependencyName"]),
        dependency_ref_prefix=str(payload.get("dependencyRefPrefix") or ""),
        apps=apps,
    )


def load_registry(path: Path) -> dict[str, Any]:
    raw = read_json(path)
    if not isinstance(raw, dict):
        raise ReleasePlanError(f"App update registry {path} must be an object.")
    return raw


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise ReleasePlanError(f"Missing config file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReleasePlanError(f"Invalid JSON in {path}: {exc}") from exc


def select_apps(component: Component, requested: set[str]) -> tuple[AssociatedApp, ...]:
    if not requested:
        return component.apps
    selected = tuple(app for app in component.apps if app.source_app in requested)
    missing = requested.difference(app.source_app for app in selected)
    if missing:
        raise ReleasePlanError(
            f"Unknown app(s) for {component.name}: {', '.join(sorted(missing))}"
        )
    return selected


def build_plan(
    *,
    component: Component,
    app: AssociatedApp,
    registry: dict[str, Any],
    dependency_ref: str | None,
) -> AppReleasePlan:
    validate_registry(app, registry)
    pubspec = app.local_path / app.pubspec_path
    text = read_text(pubspec)
    version, build = parse_pubspec_version(text, pubspec)
    current_ref = find_dependency_ref(text, component.dependency_name)
    dependency_url = find_dependency_url(text, component.dependency_name)
    next_ref = dependency_ref
    if next_ref and component.dependency_ref_prefix:
        if not next_ref.startswith(component.dependency_ref_prefix):
            raise ReleasePlanError(
                f"{component.dependency_name} ref {next_ref!r} must start with "
                f"{component.dependency_ref_prefix!r}."
            )
    if next_ref:
        if dependency_url is None:
            raise ReleasePlanError(
                f"{component.dependency_name!r} has no git url in {pubspec}."
            )
        ensure_dependency_ref_exists(
            dependency_url,
            next_ref,
            app=app.source_app,
            dependency_name=component.dependency_name,
        )
    next_build = build + 1
    next_version = f"{version}+{next_build}"
    release_tag = f"{app.release_tag_prefix}{version}-build.{next_build}"
    release_branch = f"release/{app.source_app}/{release_tag}"
    commands = release_commands(
        app=app,
        pubspec_path=app.pubspec_path,
        release_branch=release_branch,
        release_tag=release_tag,
        push=False,
    )
    return AppReleasePlan(
        app=app,
        dependency_name=component.dependency_name,
        dependency_url=dependency_url,
        current_version=version,
        current_build=build,
        next_version=next_version,
        next_build=next_build,
        current_dependency_ref=current_ref,
        next_dependency_ref=next_ref,
        release_branch=release_branch,
        release_tag=release_tag,
        commands=commands,
    )


def validate_registry(app: AssociatedApp, registry: dict[str, Any]) -> None:
    entry = registry.get(app.source_app)
    if not isinstance(entry, dict):
        raise ReleasePlanError(
            f"{app.source_app!r} is missing from the Bridge app update registry."
        )
    if entry.get("enabled") is not True:
        raise ReleasePlanError(f"{app.source_app!r} is not enabled in the registry.")
    if entry.get("repo") != app.repo:
        raise ReleasePlanError(
            f"{app.source_app!r} repo mismatch: associations use {app.repo}, "
            f"registry uses {entry.get('repo')}."
        )
    pattern = str(entry.get("releaseTagPattern") or "")
    prefix_pattern = pattern.rstrip("*")
    if pattern and not fnmatch.fnmatchcase(app.release_tag_prefix, prefix_pattern):
        raise ReleasePlanError(
            f"{app.source_app!r} tag prefix {app.release_tag_prefix!r} does not "
            f"match registry pattern {pattern!r}."
        )


def read_text(path: Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError as exc:
        raise ReleasePlanError(f"Missing file: {path}") from exc


def parse_pubspec_version(text: str, path: Path) -> tuple[str, int]:
    match = re.search(r"(?m)^version:\s*([0-9]+(?:\.[0-9]+){2})\+([0-9]+)\s*$", text)
    if not match:
        raise ReleasePlanError(f"Could not parse version: x.y.z+build in {path}.")
    return match.group(1), int(match.group(2))


def find_dependency_ref(text: str, dependency_name: str) -> str | None:
    block = dependency_block(text, dependency_name)
    if block is None:
        return None
    for line in block:
        match = re.match(r"^\s+ref:\s*(\S+)\s*$", line)
        if match:
            return match.group(1)
    return None


def find_dependency_url(text: str, dependency_name: str) -> str | None:
    block = dependency_block(text, dependency_name)
    if block is None:
        return None
    for line in block:
        match = re.match(r"^\s+url:\s*(\S+)\s*$", line)
        if match:
            return match.group(1)
    return None


def dependency_block(text: str, dependency_name: str) -> list[str] | None:
    lines = text.splitlines()
    block_start = None
    dependency_pattern = re.compile(rf"^\s{{2}}{re.escape(dependency_name)}:\s*$")
    for index, line in enumerate(lines):
        if dependency_pattern.match(line):
            block_start = index
            break
    if block_start is None:
        return None
    block: list[str] = []
    for line in lines[block_start + 1 :]:
        if re.match(r"^\s{2}\S", line):
            break
        block.append(line)
    return block


def ensure_dependency_ref_exists(
    dependency_url: str,
    dependency_ref: str,
    *,
    app: str,
    dependency_name: str,
) -> None:
    result = subprocess.run(
        ["git", "ls-remote", "--exit-code", dependency_url, dependency_ref],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode == 0:
        return
    tag_result = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--tags", dependency_url, dependency_ref],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if tag_result.returncode == 0:
        return
    detail = (result.stderr or tag_result.stderr).strip()
    suffix = f" {detail}" if detail else ""
    raise ReleasePlanError(
        f"{dependency_name} ref {dependency_ref!r} for {app} is not resolvable "
        f"from {dependency_url}.{suffix}"
    )


def release_commands(
    *,
    app: AssociatedApp,
    pubspec_path: Path,
    release_branch: str,
    release_tag: str,
    push: bool,
) -> tuple[str, ...]:
    commands = [
        f"cd {app.local_path}",
        f"git checkout -b {release_branch}",
        f"edit {pubspec_path}",
        f"git add {pubspec_path}",
        "git commit -m '<generated release commit message>'",
        f"git tag -a {release_tag} -m '<generated Android release message>'",
    ]
    if push:
        commands.extend(
            [
                f"git push -u origin {release_branch}",
                f"git push origin {release_tag}",
            ]
        )
    return tuple(commands)


def preflight(
    plans: list[AppReleasePlan],
    *,
    allow_existing_branch: bool = False,
) -> None:
    errors: list[str] = []
    for plan in plans:
        try:
            ensure_repo_ready(plan.app.local_path)
            ensure_tag_absent(plan.app.local_path, plan.release_tag)
            ensure_branch_absent(
                plan.app.local_path,
                plan.release_branch,
                allow_existing_branch=allow_existing_branch,
            )
        except ReleasePlanError as exc:
            errors.append(f"{plan.app.source_app}: {exc}")
    if errors:
        raise ReleasePlanError("Preflight failed:\n- " + "\n- ".join(errors))


def execute_plan(
    plan: AppReleasePlan,
    *,
    push: bool,
    allow_existing_branch: bool = False,
) -> None:
    app = plan.app
    ensure_repo_ready(app.local_path)
    ensure_tag_absent(app.local_path, plan.release_tag)
    ensure_branch_absent(
        app.local_path,
        plan.release_branch,
        allow_existing_branch=allow_existing_branch,
    )
    checkout_release_branch(
        app.local_path,
        plan.release_branch,
        allow_existing_branch=allow_existing_branch,
    )
    pubspec = app.local_path / app.pubspec_path
    text = read_text(pubspec)
    text = replace_pubspec_version(text, plan.next_version, pubspec)
    if plan.next_dependency_ref:
        text = replace_dependency_ref(
            text,
            dependency_name=plan.dependency_name,
            new_ref=plan.next_dependency_ref,
            path=pubspec,
        )
    pubspec.write_text(text)
    run(["git", "add", str(app.pubspec_path)], cwd=app.local_path)
    commit_message = (
        f"Release {app.display_name} for {plan.release_tag}\n\n"
        f"Build: {plan.current_build} -> {plan.next_build}\n"
    )
    if plan.next_dependency_ref:
        commit_message += (
            f"Updater ref: {plan.current_dependency_ref or 'missing'} -> "
            f"{plan.next_dependency_ref}\n"
        )
    run(["git", "commit", "-m", commit_message], cwd=app.local_path)
    run(
        [
            "git",
            "tag",
            "-a",
            plan.release_tag,
            "-m",
            f"Android release {plan.next_version}",
        ],
        cwd=app.local_path,
    )
    if push:
        run(["git", "push", "-u", "origin", plan.release_branch], cwd=app.local_path)
        run(["git", "push", "origin", plan.release_tag], cwd=app.local_path)


def ensure_repo_ready(repo: Path) -> None:
    if not repo.exists():
        raise ReleasePlanError(f"Local repo not found: {repo}")
    status = run(["git", "status", "--porcelain"], cwd=repo).stdout.strip()
    if status:
        raise ReleasePlanError(f"Worktree is dirty in {repo}; commit or stash first.")


def ensure_tag_absent(repo: Path, tag: str) -> None:
    local = run(["git", "tag", "--list", tag], cwd=repo).stdout.strip()
    if local:
        raise ReleasePlanError(f"Tag already exists locally: {tag}")
    remote_url = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if remote_url.returncode != 0:
        return
    remote = run(["git", "ls-remote", "--tags", "origin", tag], cwd=repo).stdout.strip()
    if remote:
        raise ReleasePlanError(f"Tag already exists on origin: {tag}")


def ensure_branch_absent(
    repo: Path,
    branch: str,
    *,
    allow_existing_branch: bool,
) -> None:
    if allow_existing_branch:
        return
    local = run(["git", "branch", "--list", branch], cwd=repo).stdout.strip()
    if local:
        raise ReleasePlanError(
            f"Release branch already exists locally: {branch}. "
            "Use --allow-existing-branch only after verifying it is safe."
        )
    if has_origin(repo):
        remote = run(
            ["git", "ls-remote", "--heads", "origin", branch],
            cwd=repo,
        ).stdout.strip()
        if remote:
            raise ReleasePlanError(
                f"Release branch already exists on origin: {branch}. "
                "Use --allow-existing-branch only after verifying it is safe."
            )


def checkout_release_branch(
    repo: Path,
    branch: str,
    *,
    allow_existing_branch: bool,
) -> None:
    if (
        allow_existing_branch
        and run(
            ["git", "branch", "--list", branch],
            cwd=repo,
        ).stdout.strip()
    ):
        run(["git", "checkout", branch], cwd=repo)
        return
    run(["git", "checkout", "-b", branch], cwd=repo)


def has_origin(repo: Path) -> bool:
    remote_url = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return remote_url.returncode == 0


def replace_pubspec_version(text: str, new_version: str, path: Path) -> str:
    updated, count = re.subn(
        r"(?m)^version:\s*[0-9]+(?:\.[0-9]+){2}\+[0-9]+\s*$",
        f"version: {new_version}",
        text,
        count=1,
    )
    if count != 1:
        raise ReleasePlanError(f"Could not replace version in {path}.")
    return updated


def replace_dependency_ref(
    text: str,
    *,
    dependency_name: str,
    new_ref: str,
    path: Path,
) -> str:
    lines = text.splitlines(keepends=True)
    dependency_pattern = re.compile(rf"^\s{{2}}{re.escape(dependency_name)}:\s*$")
    block_start = None
    for index, line in enumerate(lines):
        if dependency_pattern.match(line.rstrip("\n")):
            block_start = index
            break
    if block_start is None:
        raise ReleasePlanError(f"Missing dependency {dependency_name!r} in {path}.")
    for index in range(block_start + 1, len(lines)):
        line_without_newline = lines[index].rstrip("\n")
        if re.match(r"^\s{2}\S", line_without_newline):
            break
        match = re.match(r"^(\s+ref:\s*)\S+(\s*)$", line_without_newline)
        if match:
            newline = "\n" if lines[index].endswith("\n") else ""
            lines[index] = f"{match.group(1)}{new_ref}{match.group(2)}{newline}"
            return "".join(lines)
    raise ReleasePlanError(f"Missing git ref for {dependency_name!r} in {path}.")


def run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip()
        raise ReleasePlanError(
            f"{' '.join(command)} failed in {cwd}: {detail}"
        ) from exc


def emit(
    plans: list[AppReleasePlan],
    *,
    json_output: bool,
    executed: bool,
    pushed: bool,
) -> None:
    payload = [
        {
            "sourceApp": plan.app.source_app,
            "repo": plan.app.repo,
            "localPath": str(plan.app.local_path),
            "pubspecPath": str(plan.app.pubspec_path),
            "branch": plan.release_branch,
            "currentVersion": f"{plan.current_version}+{plan.current_build}",
            "nextVersion": plan.next_version,
            "dependencyName": plan.dependency_name,
            "dependencyUrl": plan.dependency_url,
            "currentDependencyRef": plan.current_dependency_ref,
            "nextDependencyRef": plan.next_dependency_ref,
            "releaseTag": plan.release_tag,
            "releaseWorkflow": plan.app.release_workflow,
            "commands": list(
                release_commands(
                    app=plan.app,
                    pubspec_path=plan.app.pubspec_path,
                    release_branch=plan.release_branch,
                    release_tag=plan.release_tag,
                    push=pushed,
                )
            ),
            "executed": executed,
            "pushed": pushed,
        }
        for plan in plans
    ]
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    for item in payload:
        print(f"{item['sourceApp']} ({item['repo']})")
        print(f"  version: {item['currentVersion']} -> {item['nextVersion']}")
        print(f"  branch: {item['branch']}")
        if item["nextDependencyRef"]:
            print(
                "  dependency ref: "
                f"{item['currentDependencyRef']} -> {item['nextDependencyRef']}"
            )
        print(f"  tag: {item['releaseTag']}")
        print(f"  workflow: {item['releaseWorkflow'] or 'tag push'}")
        print(f"  mode: {'executed' if executed else 'dry-run'}")


if __name__ == "__main__":
    raise SystemExit(main())
