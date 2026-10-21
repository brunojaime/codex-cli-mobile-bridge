"""Provider status for the existing frontend tooling contract."""
import json
from pathlib import Path
import shlex
import subprocess

from backend.app.api.schemas import CodexStatusResponse, CodexToolingResponse, CodexSkillResponse
from backend.app.infrastructure.codex_tooling import discover_codex_skills
from backend.app.infrastructure.execution.claude_options import resolve_skill


def inspect_claude_tooling(command: str, repo_root: Path) -> CodexToolingResponse:
    status = CodexStatusResponse(cli_available=False, command=command, status_summary="Claude unavailable")
    try:
        argv = shlex.split(command)
        version = subprocess.run([*argv, "--version"], capture_output=True, text=True, timeout=10)
        status.cli_available = version.returncode == 0
        status.version = version.stdout.strip()[:200]
        auth = subprocess.run([*argv, "auth", "status"], capture_output=True, text=True, timeout=10)
        data = json.loads(auth.stdout)
        status.logged_in = bool(data.get("loggedIn"))
        status.auth_mode = data.get("authMethod")
        status.status_summary = "Claude authenticated" if status.logged_in else "Claude login required"
    except (OSError, ValueError, subprocess.SubprocessError):
        status.error = "Could not verify Claude CLI authentication"
    skills = []
    for skill in discover_codex_skills(Path.home(), repo_root=repo_root):
        if resolve_skill(skill.skill_id, str(repo_root)) is not None:
            skills.append(CodexSkillResponse(skill_id=skill.skill_id, name=skill.name,
                description=skill.description, source=skill.source, path=skill.path))
    return CodexToolingResponse(status=status, skills=skills, mcp_server_inventory_complete=False,
        mcp_error="Codex profiles, plugins and MCP selections require explicit Claude configuration.")
