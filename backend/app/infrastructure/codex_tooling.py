from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex
import subprocess
import tomllib


_SKILL_DESCRIPTION_LIMIT = 240


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
    usage_summary: str | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CodexToolingSnapshot:
    status: CodexStatus
    skills: tuple[CodexSkill, ...]
    profiles: tuple[CodexConfigProfile, ...]
    mcp_servers: tuple[CodexMcpServer, ...]
    mcp_raw_output: str | None = None
    mcp_error: str | None = None
    config_path: str | None = None


def inspect_codex_tooling(command: str, *, home: Path | None = None) -> CodexToolingSnapshot:
    resolved_home = home or Path.home()
    skills = discover_codex_skills(resolved_home)
    profiles, config_path = discover_codex_profiles(resolved_home)
    status = query_codex_status(command)
    mcp_servers, mcp_raw_output, mcp_error = query_codex_mcp_servers(command)
    return CodexToolingSnapshot(
        status=status,
        skills=tuple(skills),
        profiles=tuple(profiles),
        mcp_servers=tuple(mcp_servers),
        mcp_raw_output=mcp_raw_output,
        mcp_error=mcp_error,
        config_path=str(config_path) if config_path is not None else None,
    )


def discover_codex_skills(home: Path) -> list[CodexSkill]:
    skills_by_id: dict[str, CodexSkill] = {}

    search_roots = [
        home / ".codex" / "skills",
        home / ".codex" / "plugins",
    ]
    for root in search_roots:
        if not root.exists():
            continue
        for skill_file in sorted(root.rglob("SKILL.md")):
            skill = _skill_from_path(skill_file, home=home)
            if skill is None or skill.skill_id in skills_by_id:
                continue
            skills_by_id[skill.skill_id] = skill

    return sorted(skills_by_id.values(), key=lambda item: (item.source, item.skill_id))


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
            usage_summary=None,
            error=status_error,
        )

    raw_status = status_output or ""
    summary = raw_status.strip() or "Codex login status returned no output."
    auth_mode: str | None = None
    if "Logged in using " in summary:
        auth_mode = summary.split("Logged in using ", maxsplit=1)[1].strip() or None

    return CodexStatus(
        cli_available=True,
        command=command,
        version=version_output,
        logged_in=status_error is None,
        auth_mode=auth_mode,
        status_summary=summary,
        raw_status=raw_status or None,
        usage_available=False,
        usage_summary=(
            "The local Codex CLI does not expose remaining quota or consumption "
            "details through `codex login status`."
        ),
        error=status_error,
    )


def query_codex_mcp_servers(command: str) -> tuple[list[CodexMcpServer], str | None, str | None]:
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
        server_id = _parse_mcp_server_id(line)
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


def _skill_from_path(skill_file: Path, *, home: Path) -> CodexSkill | None:
    skill_id, source = _skill_identity_for_path(skill_file, home=home)
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


def _skill_identity_for_path(skill_file: Path, *, home: Path) -> tuple[str | None, str]:
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
    if "skills" in parts:
        skills_index = parts.index("skills")
        if skills_index + 1 < len(parts):
            skill_name = parts[skills_index + 1]
            if skills_index >= 2:
                plugin_name = parts[skills_index - 2]
                return f"{plugin_name}:{skill_name}", "plugin"
            return skill_name, "plugin"
    return skill_file.parent.name, "unknown"


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
        return stdout or None, stderr or f"Command failed with exit code {completed.returncode}."
    return stdout or stderr or "", None


def _parse_mcp_server_id(line: str) -> str:
    if ":" in line:
        return line.split(":", maxsplit=1)[0].strip()
    return line.split(maxsplit=1)[0].strip()
