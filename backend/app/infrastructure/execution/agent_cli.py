"""Shared CLI contract for the isolated SDD and Project Factory processes."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
from dataclasses import dataclass

from backend.app.domain.ai_runtime import AiRuntimePolicy


@dataclass(frozen=True)
class AgentCli:
    policy: AiRuntimePolicy
    codex_command: str = "codex"
    claude_command: str = "claude"
    permission_mode: str = "default"

    @property
    def command(self) -> str:
        return self.claude_command if self.policy.engine == "claude" else self.codex_command

    def argv(self, *, prompt: str | None = None, prompt_path: Path | None = None) -> tuple[str, ...]:
        base = tuple(shlex.split(self.command))
        if not base:
            raise ValueError("AI executable is empty")
        model = self.policy.resolve_model()
        if self.policy.engine == "claude":
            args = (*base, "--print", "--output-format", "json", "--model",
                    model.removeprefix("claude:"), "--effort", self.policy.effort,
                    "--permission-mode", self.permission_mode)
            if prompt_path is not None:
                # The file is materialized after preview and before execution.
                return (*args, "--append-system-prompt-file", str(prompt_path), "--",
                        "Complete the supplied task in this workspace. Follow applicable AGENTS.md instructions.")
            return (*args, "--", "Follow applicable AGENTS.md instructions in the workspace and its ancestors before working. Never print secrets.\n\n" + (prompt or ""))
        args = (*base, "exec", "--skip-git-repo-check", "--color", "never")
        if model:
            args += ("--model", model)
        if self.policy.provider != "auto":
            args += ("-c", f'model_reasoning_effort="{self.policy.effort}"')
        if prompt_path is not None:
            # Codex exec has no --input flag. Ask the agent to read the local handoff.
            return (*args, "--", f"Read {prompt_path} and complete its task in this workspace.")
        return (*args, "--", prompt or "")


def run_process(*, argv, cwd, env, timeout_seconds):
    """Retain existing result fields, kill descendants on timeout, normalize Claude."""
    process = subprocess.Popen(list(argv), cwd=cwd, env=env, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds if timeout_seconds > 0 else None)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        raise
    result = subprocess.CompletedProcess(list(argv), process.returncode, stdout, stderr)
    # Only our explicitly structured Claude invocation uses this result contract.
    if "--output-format" in argv and "json" in argv and "--print" in argv:
        try:
            payload = json.loads(stdout)
            if not isinstance(payload, dict) or payload.get("type") != "result":
                raise ValueError("missing result")
            denied = bool(payload.get("permission_denials"))
            result.stdout = payload.get("result") or ""
            if payload.get("is_error") or denied:
                result.returncode = result.returncode or 1
                result.stderr = ("Claude tool permissions denied. " if denied else "Claude failed. ") + (
                    result.stdout or "; ".join(payload.get("errors", []))
                )
        except (ValueError, TypeError):
            result.returncode = result.returncode or 1
            result.stderr = "Claude returned no valid final result. " + stderr
    return result
