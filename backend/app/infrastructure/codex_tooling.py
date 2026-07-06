from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tomllib

from backend.app.infrastructure.mcp_apps import (
    CodexMcpApp,
    CodexInstalledMcpServerLookup,
    get_installed_mcp_server_lookup,
    inspect_repo_mcp_apps,
)


_SKILL_DESCRIPTION_LIMIT = 240
_REPO_SKILLS_DIR_NAME = "codex-skills"


@dataclass(frozen=True, slots=True)
class CodexSkill:
    skill_id: str
    name: str
    description: str
    source: str
    path: str


@dataclass(frozen=True, slots=True)
class CodexConfigProfile:
    name: str


@dataclass(frozen=True, slots=True)
class CodexMcpServer:
    server_id: str
    summary: str
    source: str = "external"
    backing_app_id: str | None = None
    status: str | None = None
    selectable: bool = True
    selectable_reason: str | None = None
    disabled_reason: str | None = None
    lookup_error: str | None = None


@dataclass(frozen=True, slots=True)
class CodexMcpServerSelectionSnapshot:
    servers: tuple[CodexMcpServer, ...]
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CodexMcpServerSelectionIssue:
    server_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class CodexStatus:
    cli_available: bool
    command: str
    version: str | None
    logged_in: bool
    auth_mode: str | None
    status_summary: str
    raw_status: str | None
    usage_available: bool
    usage_label: str | None
    usage_summary: str | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CodexRateLimitWindow:
    used_percent: float
    window_duration_mins: int | None
    resets_at: int | None


@dataclass(frozen=True, slots=True)
class CodexCreditsSnapshot:
    has_credits: bool
    unlimited: bool
    balance: str | None


@dataclass(frozen=True, slots=True)
class CodexRateLimitSnapshot:
    limit_id: str | None
    limit_name: str | None
    primary: CodexRateLimitWindow | None
    secondary: CodexRateLimitWindow | None
    credits: CodexCreditsSnapshot | None
    plan_type: str | None
    rate_limit_reached_type: str | None


@dataclass(frozen=True, slots=True)
class CodexToolingSnapshot:
    status: CodexStatus
    skills: tuple[CodexSkill, ...]
    profiles: tuple[CodexConfigProfile, ...]
    mcp_servers: tuple[CodexMcpServer, ...]
    mcp_apps: tuple[CodexMcpApp, ...]
    mcp_server_inventory_complete: bool = True
    mcp_raw_output: str | None = None
    mcp_error: str | None = None
    config_path: str | None = None


def inspect_codex_tooling(
    command: str,
    *,
    home: Path | None = None,
    repo_root: Path | None = None,
    apps_repo_root: Path | None = None,
    projects_root: str | None = None,
) -> CodexToolingSnapshot:
    resolved_home = home or Path.home()
    skills = discover_codex_skills(resolved_home, repo_root=repo_root)
    profiles, config_path = discover_codex_profiles(resolved_home)
    status = query_codex_status(command)
    mcp_servers, mcp_raw_output, mcp_error = query_codex_mcp_servers(command)
    mcp_apps = inspect_repo_mcp_apps(
        command=command,
        repo_root=apps_repo_root or repo_root,
        projects_root=projects_root or "",
    )
    mcp_servers = _decorate_mcp_servers(command, mcp_servers, mcp_apps)
    inventory_complete = mcp_error is None
    if not inventory_complete:
        mcp_servers = _mark_mcp_server_inventory_incomplete(
            mcp_servers,
            mcp_error=mcp_error,
        )
    return CodexToolingSnapshot(
        status=status,
        skills=tuple(skills),
        profiles=tuple(profiles),
        mcp_servers=tuple(mcp_servers),
        mcp_apps=tuple(mcp_apps),
        mcp_server_inventory_complete=inventory_complete,
        mcp_raw_output=mcp_raw_output,
        mcp_error=mcp_error,
        config_path=str(config_path) if config_path is not None else None,
    )


def inspect_codex_mcp_server_selection(
    command: str,
    *,
    repo_root: Path | None = None,
    projects_root: str | None = None,
) -> CodexMcpServerSelectionSnapshot:
    mcp_servers, _mcp_raw_output, mcp_error = query_codex_mcp_servers(command)
    if mcp_error is not None:
        return CodexMcpServerSelectionSnapshot(
            servers=(),
            error=mcp_error,
        )
    mcp_apps = inspect_repo_mcp_apps(
        command=command,
        repo_root=repo_root,
        projects_root=projects_root or "",
    )
    return CodexMcpServerSelectionSnapshot(
        servers=tuple(_decorate_mcp_servers(command, mcp_servers, mcp_apps)),
        error=None,
    )


def validate_requested_mcp_server_ids(
    snapshot: CodexMcpServerSelectionSnapshot,
    requested_server_ids: tuple[str, ...] | list[str],
) -> tuple[CodexMcpServerSelectionIssue, ...]:
    servers_by_id = {server.server_id: server for server in snapshot.servers}
    issues: list[CodexMcpServerSelectionIssue] = []
    for server_id in requested_server_ids:
        server = servers_by_id.get(server_id)
        if server is None:
            issues.append(
                CodexMcpServerSelectionIssue(
                    server_id=server_id,
                    reason="is not configured in current Codex MCP tooling.",
                )
            )
            continue
        if server.selectable:
            continue
        reason = server.selectable_reason or "is currently not selectable."
        if server.source == "repo_app":
            status = server.status or "unusable"
            reason = f"is repo-backed and currently `{status}`. {reason}"
        elif server.status is not None:
            reason = f"is external and currently `{server.status}`. {reason}"
        issues.append(
            CodexMcpServerSelectionIssue(
                server_id=server_id,
                reason=reason,
            )
        )
    return tuple(issues)


def discover_codex_skills(
    home: Path,
    *,
    repo_root: Path | None = None,
) -> list[CodexSkill]:
    skills_by_id: dict[str, CodexSkill] = {}

    search_roots = [
        home / ".codex" / "skills",
        home / ".codex" / "plugins",
    ]
    repo_skills_root = _repo_skills_root(repo_root)
    if repo_skills_root is not None:
        search_roots.append(repo_skills_root)
    for root in search_roots:
        if not root.exists():
            continue
        for skill_file in sorted(root.rglob("SKILL.md")):
            skill = _skill_from_path(skill_file, home=home, repo_root=repo_root)
            if skill is None or skill.skill_id in skills_by_id:
                continue
            skills_by_id[skill.skill_id] = skill

    return sorted(skills_by_id.values(), key=lambda item: (item.source, item.skill_id))


def sync_repo_skills(home: Path, *, repo_root: Path | None = None) -> tuple[str, ...]:
    repo_skills_root = _repo_skills_root(repo_root)
    if repo_skills_root is None or not repo_skills_root.exists():
        return ()

    installed_skill_ids: list[str] = []
    target_root = home / ".codex" / "skills"
    target_root.mkdir(parents=True, exist_ok=True)

    for skill_dir in sorted(_iter_repo_skill_directories(repo_skills_root)):
        skill_id = skill_dir.name.strip()
        if not skill_id:
            continue
        shutil.copytree(skill_dir, target_root / skill_id, dirs_exist_ok=True)
        installed_skill_ids.append(skill_id)
    return tuple(installed_skill_ids)


def discover_codex_profiles(home: Path) -> tuple[list[CodexConfigProfile], Path | None]:
    config_path = home / ".codex" / "config.toml"
    if not config_path.exists():
        return [], None

    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return [], config_path

    raw_profiles = data.get("profiles")
    if not isinstance(raw_profiles, dict):
        return [], config_path

    profiles = [
        CodexConfigProfile(name=profile_name)
        for profile_name in sorted(raw_profiles)
        if isinstance(profile_name, str) and profile_name.strip()
    ]
    return profiles, config_path


def query_codex_status(command: str) -> CodexStatus:
    version_output, version_error = _run_codex_command(command, ["--version"])
    status_output, status_error = _run_codex_command(command, ["login", "status"])

    if status_error is not None and status_output is None:
        return CodexStatus(
            cli_available=False,
            command=command,
            version=version_output,
            logged_in=False,
            auth_mode=None,
            status_summary="Codex CLI is unavailable.",
            raw_status=None,
            usage_available=False,
            usage_label=None,
            usage_summary=None,
            error=status_error,
        )

    raw_status = status_output or ""
    summary = raw_status.strip() or "Codex login status returned no output."
    auth_mode: str | None = None
    if "Logged in using " in summary:
        auth_mode = summary.split("Logged in using ", maxsplit=1)[1].strip() or None

    rate_limits, rate_limit_error = query_codex_rate_limits(command)
    usage_available = rate_limits is not None
    usage_label = None
    usage_summary = (
        "The local Codex CLI does not expose remaining quota or consumption "
        "details through `codex login status`."
    )
    if rate_limits is not None:
        usage_label = _format_rate_limit_label(rate_limits)
        usage_summary = _format_rate_limit_summary(rate_limits)
    elif rate_limit_error:
        usage_summary = (
            f"Codex app-server rate limits were unavailable. {rate_limit_error}"
        )

    return CodexStatus(
        cli_available=True,
        command=command,
        version=version_output,
        logged_in=status_error is None,
        auth_mode=auth_mode,
        status_summary=summary,
        raw_status=raw_status or None,
        usage_available=usage_available,
        usage_label=usage_label,
        usage_summary=usage_summary,
        error=status_error,
    )


def query_codex_rate_limits(
    command: str,
) -> tuple[CodexRateLimitSnapshot | None, str | None]:
    responses, error = _run_codex_app_server_requests(
        command,
        requests=[
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {
                        "name": "codex-mobile-bridge",
                        "version": "1.0",
                    },
                    "capabilities": {
                        "experimentalApi": True,
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "account/rateLimits/read",
                "params": None,
            },
        ],
    )
    if error is not None:
        return None, error

    payload = responses.get(2)
    if not isinstance(payload, dict):
        return None, "Codex app-server did not return rate limit data."
    result = payload.get("result")
    if not isinstance(result, dict):
        return None, "Codex app-server rate limit response was malformed."
    rate_limits = result.get("rateLimits")
    if not isinstance(rate_limits, dict):
        return None, "Codex app-server returned no rate limit snapshot."

    return _parse_rate_limit_snapshot(rate_limits), None


def query_codex_mcp_servers(
    command: str,
) -> tuple[list[CodexMcpServer], str | None, str | None]:
    output, error = _run_codex_command(command, ["mcp", "list"])
    if output is None:
        return [], None, error

    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines or output.strip().startswith("No MCP servers configured yet."):
        return [], output, error

    servers: list[CodexMcpServer] = []
    seen: set[str] = set()
    for line in lines:
        if line.startswith("No MCP servers configured yet."):
            continue
        if _is_mcp_list_header(line):
            continue
        server_id = _parse_mcp_server_id(line)
        if not server_id:
            continue
        if server_id in seen:
            continue
        seen.add(server_id)
        servers.append(
            CodexMcpServer(
                server_id=server_id,
                summary=line,
            )
        )
    return servers, output, error


def _decorate_mcp_servers(
    command: str,
    servers: list[CodexMcpServer],
    mcp_apps: list[CodexMcpApp],
) -> list[CodexMcpServer]:
    apps_by_server_id = {app.recommended_server_id: app for app in mcp_apps}
    decorated: list[CodexMcpServer] = []
    for server in servers:
        backing_app = apps_by_server_id.get(server.server_id)
        if backing_app is None:
            decorated.append(_decorate_external_mcp_server(command, server))
            continue
        selectable = backing_app.install_state == "matching"
        decorated.append(
            CodexMcpServer(
                server_id=server.server_id,
                summary=server.summary,
                source="repo_app",
                backing_app_id=backing_app.app_id,
                status=backing_app.install_state,
                selectable=selectable,
                selectable_reason=(
                    None
                    if selectable
                    else _repo_backed_server_not_selectable_reason(backing_app)
                ),
                disabled_reason=backing_app.disabled_reason,
                lookup_error=backing_app.lookup_error,
            )
        )
    return decorated


def _decorate_external_mcp_server(
    command: str,
    server: CodexMcpServer,
) -> CodexMcpServer:
    lookup = get_installed_mcp_server_lookup(command, server.server_id)
    if lookup.status == "present" and lookup.config is not None:
        if lookup.config.enabled:
            return CodexMcpServer(
                server_id=server.server_id,
                summary=server.summary,
                source="external",
                status="healthy",
                selectable=True,
            )
        disabled_reason = lookup.config.disabled_reason
        return CodexMcpServer(
            server_id=server.server_id,
            summary=server.summary,
            source="external",
            status="disabled",
            selectable=False,
            selectable_reason=_external_server_disabled_reason(disabled_reason),
            disabled_reason=disabled_reason,
        )
    if lookup.status == "missing":
        return CodexMcpServer(
            server_id=server.server_id,
            summary=server.summary,
            source="external",
            status="unreadable",
            selectable=False,
            selectable_reason=(
                "`codex mcp list` reported this external server, but "
                "`codex mcp get --json` did not return a matching stored config."
            ),
            lookup_error="`codex mcp get --json` did not return a matching stored config.",
        )
    return CodexMcpServer(
        server_id=server.server_id,
        summary=server.summary,
        source="external",
        status="unreadable",
        selectable=False,
        selectable_reason=_external_server_unreadable_reason(lookup),
        lookup_error=lookup.error,
    )


def _mark_mcp_server_inventory_incomplete(
    servers: list[CodexMcpServer],
    *,
    mcp_error: str | None,
) -> list[CodexMcpServer]:
    reason = _mcp_server_inventory_incomplete_reason(mcp_error)
    return [
        CodexMcpServer(
            server_id=server.server_id,
            summary=server.summary,
            source=server.source,
            backing_app_id=server.backing_app_id,
            status=server.status,
            selectable=False,
            selectable_reason=reason,
            disabled_reason=server.disabled_reason,
            lookup_error=server.lookup_error,
        )
        for server in servers
    ]


def _repo_backed_server_not_selectable_reason(app: CodexMcpApp) -> str:
    if app.install_state == "disabled" and app.config_matches is False:
        return (
            "This repo-backed server is disabled and drifted. Use the app card "
            "to reconcile and enable it first."
        )
    if app.install_state == "disabled":
        return (
            "This repo-backed server is disabled. Use the app card to re-enable "
            "it first."
        )
    if app.install_state == "drifted":
        return (
            "This repo-backed server drifted from the repo app spec. Use the app "
            "card to reconcile it first."
        )
    if app.install_state == "unreadable":
        return (
            "Codex could not read the stored server state safely. Fix that before "
            "selecting this repo-backed server."
        )
    if app.install_state == "protocol-broken":
        return (
            "This repo app failed protocol inspection. Fix the app before selecting "
            "its server."
        )
    if app.install_state == "invalid":
        return "This repo app is invalid. Fix the app before selecting its server."
    return "This repo-backed server is not ready for direct selection. Use the app card first."


def _external_server_disabled_reason(disabled_reason: str | None) -> str:
    if disabled_reason is None:
        return (
            "This external MCP server is disabled in Codex. Re-enable it before "
            "selecting it."
        )
    return (
        "This external MCP server is disabled in Codex. "
        f"Disabled reason: {disabled_reason}"
    )


def _external_server_unreadable_reason(
    lookup: CodexInstalledMcpServerLookup,
) -> str:
    if lookup.server_present:
        return (
            "Codex reported this external MCP server, but its stored config is "
            "unreadable. Fix the stored Codex server entry before selecting it."
        )
    return (
        "Codex could not read this external MCP server safely. Fix the stored "
        "Codex server entry before selecting it."
    )


def _mcp_server_inventory_incomplete_reason(mcp_error: str | None) -> str:
    detail = (
        mcp_error.strip()
        if mcp_error is not None
        else "Codex MCP inventory is incomplete."
    )
    return (
        "Codex MCP inventory is incomplete, so direct MCP server selection is "
        f"temporarily unavailable. {detail}"
    )


def _skill_from_path(
    skill_file: Path,
    *,
    home: Path,
    repo_root: Path | None = None,
) -> CodexSkill | None:
    skill_id, source = _skill_identity_for_path(
        skill_file,
        home=home,
        repo_root=repo_root,
    )
    if not skill_id:
        return None

    frontmatter = _parse_frontmatter(skill_file)
    description = frontmatter.get("description") or f"Codex skill `{skill_id}`."
    return CodexSkill(
        skill_id=skill_id,
        name=frontmatter.get("name") or skill_id,
        description=description[:_SKILL_DESCRIPTION_LIMIT],
        source=source,
        path=str(skill_file),
    )


def _skill_identity_for_path(
    skill_file: Path,
    *,
    home: Path,
    repo_root: Path | None = None,
) -> tuple[str | None, str]:
    parts = skill_file.parts
    try:
        relative = skill_file.relative_to(home / ".codex")
    except ValueError:
        relative = skill_file

    relative_parts = relative.parts
    if len(relative_parts) >= 3 and relative_parts[:2] == ("skills", ".system"):
        return relative_parts[2], "system"
    if len(relative_parts) >= 2 and relative_parts[0] == "skills":
        return relative_parts[1], "user"
    repo_skills_root = _repo_skills_root(repo_root)
    if repo_skills_root is not None:
        try:
            repo_relative = skill_file.relative_to(repo_skills_root)
        except ValueError:
            repo_relative = None
        if repo_relative is not None and len(repo_relative.parts) >= 2:
            return repo_relative.parts[0], "repo"
    if "skills" in parts:
        skills_index = parts.index("skills")
        if skills_index + 1 < len(parts):
            skill_name = parts[skills_index + 1]
            if skills_index >= 2:
                plugin_name = parts[skills_index - 2]
                return f"{plugin_name}:{skill_name}", "plugin"
            return skill_name, "plugin"
    return skill_file.parent.name, "unknown"


def _repo_skills_root(repo_root: Path | None) -> Path | None:
    if repo_root is None:
        return None
    return repo_root.resolve() / _REPO_SKILLS_DIR_NAME


def _iter_repo_skill_directories(repo_skills_root: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for path in repo_skills_root.iterdir()
        if path.is_dir() and (path / "SKILL.md").exists()
    )


def _parse_frontmatter(skill_file: Path) -> dict[str, str]:
    try:
        content = skill_file.read_text(encoding="utf-8")
    except OSError:
        return {}

    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    metadata: dict[str, str] = {}
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        if ":" not in line:
            continue
        key, raw_value = line.split(":", maxsplit=1)
        value = raw_value.strip().strip('"').strip("'")
        metadata[key.strip()] = value
    return metadata


def _run_codex_command(command: str, args: list[str]) -> tuple[str | None, str | None]:
    try:
        completed = subprocess.run(
            [*shlex.split(command), *args],
            capture_output=True,
            check=False,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode != 0:
        return (
            stdout or None,
            stderr or f"Command failed with exit code {completed.returncode}.",
        )
    return stdout or stderr or "", None


def _run_codex_app_server_requests(
    command: str,
    *,
    requests: list[dict[str, object]],
) -> tuple[dict[int, dict[str, object]], str | None]:
    payload = "".join(f"{json.dumps(item)}\n" for item in requests)
    try:
        completed = subprocess.run(
            [
                *shlex.split(command),
                "-c",
                'sandbox_mode="danger-full-access"',
                "app-server",
                "--listen",
                "stdio://",
            ],
            input=payload,
            capture_output=True,
            check=False,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        return {}, str(exc)

    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        return (
            {},
            stderr or f"Codex app-server exited with code {completed.returncode}.",
        )

    responses: dict[int, dict[str, object]] = {}
    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(message, dict):
            continue
        message_id = message.get("id")
        if isinstance(message_id, int):
            responses[message_id] = message
    return responses, None


def _parse_rate_limit_snapshot(payload: dict[str, object]) -> CodexRateLimitSnapshot:
    return CodexRateLimitSnapshot(
        limit_id=_as_optional_str(payload.get("limitId")),
        limit_name=_as_optional_str(payload.get("limitName")),
        primary=_parse_rate_limit_window(payload.get("primary")),
        secondary=_parse_rate_limit_window(payload.get("secondary")),
        credits=_parse_credits_snapshot(payload.get("credits")),
        plan_type=_as_optional_str(payload.get("planType")),
        rate_limit_reached_type=_as_optional_str(payload.get("rateLimitReachedType")),
    )


def _parse_rate_limit_window(payload: object) -> CodexRateLimitWindow | None:
    if not isinstance(payload, dict):
        return None
    used_percent = payload.get("usedPercent")
    if not isinstance(used_percent, (int, float)):
        return None
    return CodexRateLimitWindow(
        used_percent=float(used_percent),
        window_duration_mins=_as_optional_int(payload.get("windowDurationMins")),
        resets_at=_as_optional_int(payload.get("resetsAt")),
    )


def _parse_credits_snapshot(payload: object) -> CodexCreditsSnapshot | None:
    if not isinstance(payload, dict):
        return None
    has_credits = payload.get("hasCredits")
    unlimited = payload.get("unlimited")
    if not isinstance(has_credits, bool) or not isinstance(unlimited, bool):
        return None
    return CodexCreditsSnapshot(
        has_credits=has_credits,
        unlimited=unlimited,
        balance=_as_optional_str(payload.get("balance")),
    )


def _format_rate_limit_label(snapshot: CodexRateLimitSnapshot) -> str:
    plan = _format_plan_name(snapshot.plan_type)
    segments = [plan]
    if snapshot.primary is not None:
        segments.append(
            f"{snapshot.primary.used_percent:.0f}%/{_format_window_duration(snapshot.primary.window_duration_mins)}"
        )
    if snapshot.secondary is not None:
        segments.append(
            f"{snapshot.secondary.used_percent:.0f}%/{_format_window_duration(snapshot.secondary.window_duration_mins)}"
        )
    return " · ".join(segment for segment in segments if segment)


def _format_rate_limit_summary(snapshot: CodexRateLimitSnapshot) -> str:
    parts = [f"Codex account: {_format_plan_name(snapshot.plan_type)}."]
    if snapshot.primary is not None:
        parts.append(
            f"{_format_window_duration(snapshot.primary.window_duration_mins)} window {snapshot.primary.used_percent:.0f}% used"
            f" (resets {_format_reset_time(snapshot.primary.resets_at)})."
        )
    if snapshot.secondary is not None:
        parts.append(
            f"{_format_window_duration(snapshot.secondary.window_duration_mins)} window {snapshot.secondary.used_percent:.0f}% used"
            f" (resets {_format_reset_time(snapshot.secondary.resets_at)})."
        )
    if snapshot.credits is not None:
        if snapshot.credits.unlimited:
            parts.append("Credits: unlimited.")
        elif snapshot.credits.balance is not None:
            parts.append(f"Credits balance: {snapshot.credits.balance}.")
        else:
            parts.append(
                "Credits available."
                if snapshot.credits.has_credits
                else "Credits unavailable."
            )
    if snapshot.rate_limit_reached_type:
        parts.append(f"Limit status: {snapshot.rate_limit_reached_type}.")
    parts.append(
        "This is live Codex account data from the app-server, which can still be briefly stale until refreshed."
    )
    return " ".join(parts)


def _format_plan_name(plan_type: str | None) -> str:
    if not plan_type:
        return "Codex"
    return plan_type.replace("_", " ").title()


def _format_window_duration(window_duration_mins: int | None) -> str:
    if window_duration_mins is None:
        return "window"
    if window_duration_mins % (60 * 24 * 7) == 0:
        weeks = window_duration_mins // (60 * 24 * 7)
        return "7d" if weeks == 1 else f"{weeks}w"
    if window_duration_mins % (60 * 24) == 0:
        days = window_duration_mins // (60 * 24)
        return "1d" if days == 1 else f"{days}d"
    if window_duration_mins % 60 == 0:
        hours = window_duration_mins // 60
        return "1h" if hours == 1 else f"{hours}h"
    return f"{window_duration_mins}m"


def _format_reset_time(timestamp: int | None) -> str:
    if timestamp is None:
        return "later"
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )


def _as_optional_str(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _as_optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _parse_mcp_server_id(line: str) -> str:
    if ":" in line:
        return line.split(":", maxsplit=1)[0].strip()
    return line.split(maxsplit=1)[0].strip()


def _is_mcp_list_header(line: str) -> bool:
    columns = line.split()
    return len(columns) >= 2 and columns[0] == "Name" and columns[1] == "Command"
