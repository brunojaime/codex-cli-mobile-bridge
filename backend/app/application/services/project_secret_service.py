from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import threading

from dotenv import set_key
from dotenv.parser import parse_stream


_SECRET_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_GITIGNORE_BLOCK = (
    "# Local secrets managed by Codex Mobile Bridge\n"
    "/.env\n"
)
_AGENT_GUIDANCE_MARKER = "<!-- codex-mobile-project-secrets -->"
_AGENT_GUIDANCE_BLOCK = f"""\
{_AGENT_GUIDANCE_MARKER}
## Project secrets

Add or rotate credentials through the chat's **Secrets** panel. They are stored in the workspace `.env`; never ask the user to paste secret values into chat and never print or reveal them.
"""


class ProjectSecretError(RuntimeError):
    pass


class ProjectSecretWorkspaceError(ProjectSecretError):
    pass


class ProjectSecretStorageError(ProjectSecretError):
    pass


class ProjectSecretService:
    """Write-only project secret management backed by a workspace .env file."""

    def __init__(
        self,
        *,
        projects_root: str | Path,
        workspace_aliases: dict[str, str] | None = None,
    ) -> None:
        self._projects_root = Path(projects_root).expanduser().resolve()
        self._workspace_aliases = {
            key: Path(value).expanduser().resolve()
            for key, value in (workspace_aliases or {}).items()
            if key.strip() and str(value).strip()
        }
        self._lock = threading.RLock()

    def list_secret_names(self, *, workspace_path: str) -> dict[str, object]:
        workspace = self._resolve_workspace(workspace_path)
        env_path = self._env_path(workspace)
        with self._lock:
            names = self._read_secret_names(env_path)
        return self._payload(workspace, names)

    def set_secret(
        self,
        *,
        workspace_path: str,
        name: str,
        value: str,
    ) -> dict[str, object]:
        workspace = self._resolve_workspace(workspace_path)
        normalized_name = name.strip()
        if not _SECRET_NAME_PATTERN.fullmatch(normalized_name):
            raise ProjectSecretStorageError(
                "Secret names must start with a letter or underscore and contain "
                "only letters, numbers, and underscores."
            )
        if not value:
            raise ProjectSecretStorageError("Secret values cannot be empty.")
        if "\x00" in value:
            raise ProjectSecretStorageError("Secret values cannot contain NUL bytes.")

        env_path = self._env_path(workspace)
        with self._lock:
            self._ensure_env_is_not_tracked(workspace)
            self._ensure_env_is_ignored(workspace)
            self._ensure_agent_guidance(workspace)
            try:
                set_key(
                    env_path,
                    normalized_name,
                    value,
                    quote_mode="always",
                    follow_symlinks=False,
                )
                os.chmod(env_path, 0o600)
            except OSError as exc:
                raise ProjectSecretStorageError(
                    "Could not update the project .env file."
                ) from exc
            names = self._read_secret_names(env_path)
        return self._payload(workspace, names)

    def _resolve_workspace(self, workspace_path: str) -> Path:
        raw_path = workspace_path.strip()
        if not raw_path:
            raise ProjectSecretWorkspaceError("workspace_path is required.")
        alias_path = self._workspace_aliases.get(raw_path)
        candidate = alias_path if alias_path is not None else Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = self._projects_root / candidate
        resolved = candidate.resolve()
        if not self._is_allowed_workspace(resolved):
            raise ProjectSecretWorkspaceError(
                "workspace_path must resolve under PROJECTS_ROOT or a known alias."
            )
        if not resolved.is_dir():
            raise ProjectSecretWorkspaceError(
                "workspace_path must point to a project directory."
            )
        return resolved

    def _is_allowed_workspace(self, path: Path) -> bool:
        if path == self._projects_root or self._projects_root in path.parents:
            return True
        return any(path == alias_path for alias_path in self._workspace_aliases.values())

    def _env_path(self, workspace: Path) -> Path:
        env_path = workspace / ".env"
        if env_path.is_symlink():
            raise ProjectSecretStorageError(
                "The project .env file cannot be a symbolic link."
            )
        if env_path.exists() and not env_path.is_file():
            raise ProjectSecretStorageError(
                "The project .env path must be a regular file."
            )
        return env_path

    def _read_secret_names(self, env_path: Path) -> list[str]:
        if not env_path.exists():
            return []
        try:
            with env_path.open(encoding="utf-8") as handle:
                names = {
                    mapping.key
                    for mapping in parse_stream(handle)
                    if mapping.key is not None
                }
        except (OSError, UnicodeError) as exc:
            raise ProjectSecretStorageError(
                "Could not read secret names from the project .env file."
            ) from exc
        return sorted(names, key=lambda item: (item.casefold(), item))

    def _ensure_env_is_not_tracked(self, workspace: Path) -> None:
        if not self._is_git_worktree(workspace):
            return
        try:
            result = subprocess.run(
                ["git", "-C", str(workspace), "ls-files", "--error-unmatch", "--", ".env"],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProjectSecretStorageError(
                "Could not verify that .env is excluded from version control."
            ) from exc
        if result.returncode == 0:
            raise ProjectSecretStorageError(
                "The project .env file is tracked by Git. Remove it from Git before storing secrets."
            )

    def _ensure_env_is_ignored(self, workspace: Path) -> None:
        if not self._is_git_worktree(workspace):
            return
        if self._git_ignores_env(workspace):
            return
        gitignore_path = workspace / ".gitignore"
        if gitignore_path.is_symlink():
            raise ProjectSecretStorageError(
                "The project .gitignore cannot be a symbolic link."
            )
        try:
            existing = (
                gitignore_path.read_text(encoding="utf-8")
                if gitignore_path.exists()
                else ""
            )
            separator = "" if not existing or existing.endswith("\n") else "\n"
            with gitignore_path.open("a", encoding="utf-8") as handle:
                handle.write(f"{separator}{_GITIGNORE_BLOCK}")
        except (OSError, UnicodeError) as exc:
            raise ProjectSecretStorageError(
                "Could not exclude .env from version control."
            ) from exc
        if not self._git_ignores_env(workspace):
            raise ProjectSecretStorageError(
                "Could not verify that .env is excluded from version control."
            )

    def _is_git_worktree(self, workspace: Path) -> bool:
        try:
            result = subprocess.run(
                ["git", "-C", str(workspace), "rev-parse", "--is-inside-work-tree"],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            if (workspace / ".git").exists():
                raise ProjectSecretStorageError(
                    "Could not verify the project's Git state."
                ) from exc
            return False
        return result.returncode == 0 and result.stdout.strip() == "true"

    def _git_ignores_env(self, workspace: Path) -> bool:
        try:
            result = subprocess.run(
                ["git", "-C", str(workspace), "check-ignore", "--quiet", "--", ".env"],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProjectSecretStorageError(
                "Could not verify that .env is excluded from version control."
            ) from exc
        return result.returncode == 0

    def _ensure_agent_guidance(self, workspace: Path) -> None:
        agents_path = workspace / "AGENTS.md"
        if agents_path.is_symlink():
            raise ProjectSecretStorageError(
                "The project AGENTS.md cannot be a symbolic link."
            )
        try:
            existing = (
                agents_path.read_text(encoding="utf-8")
                if agents_path.exists()
                else ""
            )
            if _AGENT_GUIDANCE_MARKER in existing:
                return
            separator = "" if not existing or existing.endswith("\n") else "\n"
            if existing:
                separator += "\n"
            with agents_path.open("a", encoding="utf-8") as handle:
                handle.write(f"{separator}{_AGENT_GUIDANCE_BLOCK}")
        except (OSError, UnicodeError) as exc:
            raise ProjectSecretStorageError(
                "Could not add secret handling guidance to AGENTS.md."
            ) from exc

    def _payload(self, workspace: Path, names: list[str]) -> dict[str, object]:
        return {
            "workspace_path": str(workspace),
            "workspace_name": workspace.name,
            "env_file": ".env",
            "names": names,
        }
