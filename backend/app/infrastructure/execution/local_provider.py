from __future__ import annotations

import os
import json
import shlex
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from backend.app.domain.entities.job import JobStatus
from backend.app.infrastructure.execution.base import ExecutionProvider


@dataclass(slots=True)
class _ExecutionState:
    status: JobStatus
    response: str | None = None
    error: str | None = None
    provider_session_id: str | None = None


class LocalExecutionProvider(ExecutionProvider):
    def __init__(
        self,
        *,
        command: str,
        use_exec_mode: bool = True,
        exec_args: str = "--skip-git-repo-check --color never",
        resume_args: str = "--skip-git-repo-check",
        workdir: str | None = None,
        timeout_seconds: int = 900,
    ) -> None:
        self._command = command
        self._use_exec_mode = use_exec_mode
        self._exec_args = exec_args
        self._resume_args = resume_args
        self._workdir = str(Path(workdir).resolve()) if workdir else None
        self._timeout_seconds = timeout_seconds
        self._states: dict[str, _ExecutionState] = {}
        self._lock = threading.RLock()

    def execute(
        self,
        message: str,
        *,
        provider_session_id: str | None = None,
        workdir: str | None = None,
    ) -> str:
        job_id = str(uuid4())
        self._set_state(job_id, status=JobStatus.PENDING)
        worker = threading.Thread(
            target=self._run_job,
            args=(job_id, message, provider_session_id, workdir),
            daemon=True,
        )
        worker.start()
        return job_id

    def get_status(self, job_id: str) -> JobStatus:
        state = self._get_state(job_id)
        return state.status if state else JobStatus.FAILED

    def get_result(self, job_id: str) -> str | None:
        state = self._get_state(job_id)
        return state.response if state else None

    def get_error(self, job_id: str) -> str | None:
        state = self._get_state(job_id)
        return state.error if state else "Unknown job id."

    def get_provider_session_id(self, job_id: str) -> str | None:
        state = self._get_state(job_id)
        return state.provider_session_id if state else None

    def _run_job(
        self,
        job_id: str,
        message: str,
        provider_session_id: str | None = None,
        workdir: str | None = None,
    ) -> None:
        self._set_state(job_id, status=JobStatus.RUNNING)
        command_parts, output_path = self._build_command(
            message,
            provider_session_id=provider_session_id,
        )

        try:
            completed_process = subprocess.run(
                command_parts,
                cwd=workdir or self._workdir,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            self._set_state(
                job_id,
                status=JobStatus.FAILED,
                error=f"Codex command not found: {exc}",
            )
            return
        except subprocess.TimeoutExpired:
            self._set_state(
                job_id,
                status=JobStatus.FAILED,
                error=f"Execution timed out after {self._timeout_seconds} seconds.",
            )
            return
        except Exception as exc:  # pragma: no cover - defensive path
            self._set_state(
                job_id,
                status=JobStatus.FAILED,
                error=f"Unexpected execution error: {exc}",
            )
            return

        stdout_text = completed_process.stdout.strip()
        stderr_text = completed_process.stderr.strip()
        resolved_provider_session_id = self._extract_provider_session_id(stdout_text)
        output = self._resolve_output(
            output_path=output_path,
            stdout_text=stdout_text,
            stderr_text=stderr_text,
        )

        if completed_process.returncode == 0:
            self._set_state(
                job_id,
                status=JobStatus.COMPLETED,
                response=output or "Execution completed with no output.",
                provider_session_id=resolved_provider_session_id or provider_session_id,
            )
            return

        self._set_state(
            job_id,
            status=JobStatus.FAILED,
            error=output or f"Codex exited with code {completed_process.returncode}.",
            provider_session_id=resolved_provider_session_id or provider_session_id,
        )

    def _build_command(
        self,
        message: str,
        *,
        provider_session_id: str | None = None,
    ) -> tuple[list[str], str | None]:
        base_parts = shlex.split(self._command)

        if not self._use_exec_mode:
            return [*base_parts, message], None

        file_descriptor, output_path = tempfile.mkstemp(
            prefix="codex-last-message-",
            suffix=".txt",
        )
        os.close(file_descriptor)

        if provider_session_id:
            resume_options = [*shlex.split(self._resume_args), "--json", "-o", output_path]
            exec_parts = [
                *base_parts,
                "exec",
                "resume",
                *resume_options,
                provider_session_id,
                message,
            ]
        else:
            exec_options = [*shlex.split(self._exec_args), "--json", "-o", output_path]
            exec_parts = [
                *base_parts,
                "exec",
                *exec_options,
                message,
            ]
        return exec_parts, output_path

    def _resolve_output(
        self,
        *,
        output_path: str | None,
        stdout_text: str,
        stderr_text: str,
    ) -> str:
        last_message = self._read_last_message(output_path)
        if last_message:
            return last_message

        return self._build_output(stdout_text, stderr_text)

    def _build_output(self, stdout_text: str, stderr_text: str) -> str:
        if stdout_text and stderr_text:
            return f"{stdout_text}\n\n[stderr]\n{stderr_text}"
        return stdout_text or stderr_text

    def _extract_provider_session_id(self, stdout_text: str) -> str | None:
        for line in stdout_text.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("type") == "thread.started":
                return payload.get("thread_id")
        return None

    def _read_last_message(self, output_path: str | None) -> str | None:
        if output_path is None:
            return None

        try:
            content = Path(output_path).read_text(encoding="utf-8").strip()
            return content or None
        except OSError:
            return None
        finally:
            try:
                Path(output_path).unlink(missing_ok=True)
            except OSError:
                pass

    def _set_state(
        self,
        job_id: str,
        *,
        status: JobStatus,
        response: str | None = None,
        error: str | None = None,
        provider_session_id: str | None = None,
    ) -> None:
        with self._lock:
            self._states[job_id] = _ExecutionState(
                status=status,
                response=response,
                error=error,
                provider_session_id=provider_session_id,
            )

    def _get_state(self, job_id: str) -> _ExecutionState | None:
        with self._lock:
            return self._states.get(job_id)
