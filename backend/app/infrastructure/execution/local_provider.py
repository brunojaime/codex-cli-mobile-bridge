from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import IO
from uuid import uuid4

from backend.app.domain.entities.job import JobStatus
from backend.app.infrastructure.execution.base import ExecutionProvider


@dataclass(slots=True)
class _ExecutionState:
    status: JobStatus
    response: str | None = None
    error: str | None = None
    provider_session_id: str | None = None
    phase: str | None = None
    latest_activity: str | None = None


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
        self._set_state(
            job_id,
            status=JobStatus.PENDING,
            phase="Queued",
            latest_activity="Prompt accepted by the backend.",
        )
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

    def get_phase(self, job_id: str) -> str | None:
        state = self._get_state(job_id)
        return state.phase if state else None

    def get_latest_activity(self, job_id: str) -> str | None:
        state = self._get_state(job_id)
        return state.latest_activity if state else None

    def _run_job(
        self,
        job_id: str,
        message: str,
        provider_session_id: str | None = None,
        workdir: str | None = None,
    ) -> None:
        self._set_state(
            job_id,
            status=JobStatus.RUNNING,
            phase="Starting Codex CLI",
            latest_activity="Launching the local Codex subprocess.",
            provider_session_id=provider_session_id,
        )
        command_parts, output_path = self._build_command(
            message,
            provider_session_id=provider_session_id,
        )

        try:
            process = subprocess.Popen(
                command_parts,
                cwd=workdir or self._workdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            self._set_state(
                job_id,
                status=JobStatus.FAILED,
                error=f"Codex command not found: {exc}",
                phase="Failed",
                latest_activity="The configured Codex command was not found.",
            )
            self._cleanup_output_file(output_path)
            return
        except Exception as exc:  # pragma: no cover - defensive path
            self._set_state(
                job_id,
                status=JobStatus.FAILED,
                error=f"Unexpected execution error: {exc}",
                phase="Failed",
                latest_activity="The local Codex subprocess could not be started.",
            )
            self._cleanup_output_file(output_path)
            return

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        stdout_thread = threading.Thread(
            target=self._consume_stream,
            args=(job_id, process.stdout, stdout_lines, True),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=self._consume_stream,
            args=(job_id, process.stderr, stderr_lines, False),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        try:
            return_code = process.wait(timeout=self._timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)
            self._set_state(
                job_id,
                status=JobStatus.FAILED,
                error=f"Execution timed out after {self._timeout_seconds} seconds.",
                phase="Timed out",
                latest_activity="The Codex subprocess exceeded the configured timeout.",
            )
            self._cleanup_output_file(output_path)
            return

        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)

        stdout_text = "\n".join(stdout_lines).strip()
        stderr_text = "\n".join(stderr_lines).strip()
        resolved_provider_session_id = self._extract_provider_session_id(stdout_text)
        output = self._resolve_output(
            output_path=output_path,
            stdout_text=stdout_text,
            stderr_text=stderr_text,
        )

        if return_code == 0:
            self._set_state(
                job_id,
                status=JobStatus.COMPLETED,
                response=output or "Execution completed with no output.",
                provider_session_id=resolved_provider_session_id or provider_session_id,
                phase="Completed",
                latest_activity="Codex returned a final response.",
            )
            return

        self._set_state(
            job_id,
            status=JobStatus.FAILED,
            error=output or f"Codex exited with code {return_code}.",
            provider_session_id=resolved_provider_session_id or provider_session_id,
            phase="Failed",
            latest_activity=self._first_non_empty(stderr_lines)
            or "Codex exited with a non-zero status.",
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

    def _consume_stream(
        self,
        job_id: str,
        stream: IO[str] | None,
        sink: list[str],
        is_stdout: bool,
    ) -> None:
        if stream is None:
            return

        try:
            for raw_line in iter(stream.readline, ""):
                line = raw_line.rstrip()
                if not line:
                    continue
                sink.append(line)
                if is_stdout:
                    self._handle_stdout_line(job_id, line)
                else:
                    self._handle_stderr_line(job_id, line)
        finally:
            stream.close()

    def _handle_stdout_line(self, job_id: str, line: str) -> None:
        payload = self._parse_json_line(line)
        if payload is None:
            self._set_state(
                job_id,
                status=JobStatus.RUNNING,
                phase="Running Codex",
                latest_activity=line,
            )
            return

        provider_session_id = payload.get("thread_id")
        phase, latest_activity = self._describe_event(payload)
        self._set_state(
            job_id,
            status=JobStatus.RUNNING,
            provider_session_id=provider_session_id,
            phase=phase,
            latest_activity=latest_activity,
        )

    def _handle_stderr_line(self, job_id: str, line: str) -> None:
        self._set_state(
            job_id,
            status=JobStatus.RUNNING,
            phase="Running Codex",
            latest_activity=line,
        )

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
        stdout_human = "\n".join(
            line for line in stdout_text.splitlines() if not self._looks_like_json(line)
        ).strip()
        if stdout_human and stderr_text:
            return f"{stdout_human}\n\n[stderr]\n{stderr_text}"
        return stdout_human or stderr_text

    def _extract_provider_session_id(self, stdout_text: str) -> str | None:
        for line in stdout_text.splitlines():
            payload = self._parse_json_line(line)
            if payload and payload.get("type") == "thread.started":
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
            self._cleanup_output_file(output_path)

    def _cleanup_output_file(self, output_path: str | None) -> None:
        if output_path is None:
            return

        try:
            Path(output_path).unlink(missing_ok=True)
        except OSError:
            pass

    def _parse_json_line(self, line: str) -> dict[str, object] | None:
        if not line.startswith("{"):
            return None
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _looks_like_json(self, line: str) -> bool:
        return self._parse_json_line(line) is not None

    def _describe_event(self, payload: dict[str, object]) -> tuple[str, str]:
        event_type = str(payload.get("type") or "running")
        if event_type == "thread.started":
            return ("Starting session", "Codex started a new chat session.")
        if event_type == "turn.started":
            return ("Reasoning", "Codex started working on the current turn.")
        if event_type == "turn.completed":
            return ("Finalizing", "Codex finished the turn and is preparing the final output.")

        if event_type in {"item.started", "item.completed"}:
            item = payload.get("item")
            item_type = ""
            if isinstance(item, dict):
                item_type = str(item.get("type") or "")

            if item_type == "agent_message":
                if event_type == "item.completed":
                    return ("Drafting reply", "Codex produced an assistant message.")
                return ("Drafting reply", "Codex is composing the reply.")
            if item_type:
                human_item = self._humanize(item_type)
                if event_type == "item.completed":
                    return ("Running tools", f"Completed {human_item.lower()}.")
                return ("Running tools", f"Started {human_item.lower()}.")

        return ("Running Codex", self._humanize(event_type))

    def _humanize(self, value: str) -> str:
        return value.replace(".", " ").replace("_", " ").strip().capitalize()

    def _first_non_empty(self, lines: list[str]) -> str | None:
        for line in lines:
            if line.strip():
                return line.strip()
        return None

    def _set_state(
        self,
        job_id: str,
        *,
        status: JobStatus,
        response: str | None = None,
        error: str | None = None,
        provider_session_id: str | None = None,
        phase: str | None = None,
        latest_activity: str | None = None,
    ) -> None:
        with self._lock:
            current = self._states.get(job_id)
            self._states[job_id] = _ExecutionState(
                status=status,
                response=response if response is not None else (current.response if current else None),
                error=error if error is not None else (current.error if current else None),
                provider_session_id=provider_session_id
                if provider_session_id is not None
                else (current.provider_session_id if current else None),
                phase=phase if phase is not None else (current.phase if current else None),
                latest_activity=latest_activity
                if latest_activity is not None
                else (current.latest_activity if current else None),
            )

    def _get_state(self, job_id: str) -> _ExecutionState | None:
        with self._lock:
            return self._states.get(job_id)
