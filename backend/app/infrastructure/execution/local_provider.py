from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import IO
from uuid import uuid4

from backend.app.domain.entities.job import JobStatus
from backend.app.infrastructure.execution.base import ExecutionProvider, ExecutionSnapshot


@dataclass(slots=True)
class _ExecutionState:
    status: JobStatus
    response: str | None = None
    error: str | None = None
    provider_session_id: str | None = None
    phase: str | None = None
    latest_activity: str | None = None


@dataclass(slots=True)
class _QueuedExecution:
    job_id: str
    message: str
    image_paths: list[str] | None = None
    cleanup_paths: list[str] | None = None
    provider_session_id: str | None = None
    workdir: str | None = None
    serial_key: str | None = None


class LocalExecutionProvider(ExecutionProvider):
    def __init__(
        self,
        *,
        command: str,
        use_exec_mode: bool = True,
        exec_args: str = "--skip-git-repo-check --color never",
        resume_args: str = "--skip-git-repo-check",
        workdir: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self._command = command
        self._use_exec_mode = use_exec_mode
        self._exec_args = exec_args
        self._resume_args = resume_args
        self._workdir = str(Path(workdir).resolve()) if workdir else None
        self._timeout_seconds = timeout_seconds
        self._states: dict[str, _ExecutionState] = {}
        self._subscribers: dict[str, list[Callable[[ExecutionSnapshot], None]]] = {}
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._queued_executions: dict[str, _QueuedExecution] = {}
        self._serial_tails: dict[str, str] = {}
        self._serial_successors: dict[str, str] = {}
        self._serial_predecessors: dict[str, str] = {}
        self._job_serial_keys: dict[str, str] = {}
        self._lock = threading.RLock()

    def execute(
        self,
        message: str,
        *,
        image_paths: list[str] | None = None,
        cleanup_paths: list[str] | None = None,
        provider_session_id: str | None = None,
        serial_key: str | None = None,
        workdir: str | None = None,
    ) -> str:
        job_id = str(uuid4())
        execution = _QueuedExecution(
            job_id=job_id,
            message=message,
            image_paths=image_paths,
            cleanup_paths=cleanup_paths,
            provider_session_id=provider_session_id,
            workdir=workdir,
            serial_key=serial_key,
        )
        should_queue = False

        with self._lock:
            self._queued_executions[job_id] = execution
            predecessor_job_id: str | None = None
            if serial_key:
                self._job_serial_keys[job_id] = serial_key
                predecessor_job_id = self._serial_tails.get(serial_key)
                self._serial_tails[serial_key] = job_id
                predecessor_state = (
                    self._states.get(predecessor_job_id)
                    if predecessor_job_id is not None
                    else None
                )
                if predecessor_state is not None and not predecessor_state.status.is_terminal:
                    should_queue = True
                    self._serial_successors[predecessor_job_id] = job_id
                    self._serial_predecessors[job_id] = predecessor_job_id

        self._set_state(
            job_id,
            status=JobStatus.PENDING,
            phase="Queued behind previous turn" if should_queue else "Queued",
            latest_activity=(
                "Waiting for the previous turn in this chat to finish."
                if should_queue
                else "Prompt accepted by the backend."
            ),
        )
        if not should_queue:
            self._start_execution(job_id)
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

    def has_job(self, job_id: str) -> bool:
        return self._get_state(job_id) is not None

    def get_provider_session_id(self, job_id: str) -> str | None:
        state = self._get_state(job_id)
        return state.provider_session_id if state else None

    def get_phase(self, job_id: str) -> str | None:
        state = self._get_state(job_id)
        return state.phase if state else None

    def get_latest_activity(self, job_id: str) -> str | None:
        state = self._get_state(job_id)
        return state.latest_activity if state else None

    def watch_job(
        self,
        job_id: str,
        on_change: Callable[[ExecutionSnapshot], None],
    ) -> Callable[[], None] | None:
        with self._lock:
            self._subscribers.setdefault(job_id, []).append(on_change)
            snapshot = self._snapshot_from_state(job_id, self._states.get(job_id))

        if snapshot is not None:
            on_change(snapshot)

        def unsubscribe() -> None:
            with self._lock:
                listeners = self._subscribers.get(job_id)
                if listeners is None:
                    return
                try:
                    listeners.remove(on_change)
                except ValueError:
                    return
                if not listeners:
                    self._subscribers.pop(job_id, None)

        return unsubscribe

    def supports_job_cancellation(self) -> bool:
        return True

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            current = self._states.get(job_id)
            process = self._processes.get(job_id)

        if current is None or current.status.is_terminal:
            return False

        self._set_state(
            job_id,
            status=JobStatus.CANCELLED,
            error="Cancelled by user.",
            phase="Cancelled",
            latest_activity="Execution was cancelled by the user.",
        )

        if process is not None:
            try:
                process.terminate()
            except OSError:
                pass
        else:
            self._remove_queued_job(job_id)

        return True

    def _start_execution(
        self,
        job_id: str,
        *,
        provider_session_id_override: str | None = None,
    ) -> None:
        with self._lock:
            execution = self._queued_executions.get(job_id)

        if execution is None:
            return

        resolved_provider_session_id = (
            provider_session_id_override
            if provider_session_id_override is not None
            else execution.provider_session_id
        )
        worker = threading.Thread(
            target=self._run_job,
            args=(
                job_id,
                execution.message,
                execution.image_paths,
                execution.cleanup_paths,
                resolved_provider_session_id,
                execution.workdir,
            ),
            daemon=True,
        )
        worker.start()

    def _run_job(
        self,
        job_id: str,
        message: str,
        image_paths: list[str] | None = None,
        cleanup_paths: list[str] | None = None,
        provider_session_id: str | None = None,
        workdir: str | None = None,
    ) -> None:
        if self._is_cancelled(job_id):
            return
        self._set_state(
            job_id,
            status=JobStatus.RUNNING,
            phase="Starting Codex CLI",
            latest_activity="Launching the local Codex subprocess.",
            provider_session_id=provider_session_id,
        )
        output_path: str | None = None
        try:
            command_parts, output_path = self._build_command(
                message,
                image_paths=image_paths,
                provider_session_id=provider_session_id,
            )

            if self._is_cancelled(job_id):
                return

            try:
                process = subprocess.Popen(
                    command_parts,
                    cwd=workdir or self._workdir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                )
                with self._lock:
                    self._processes[job_id] = process
            except FileNotFoundError as exc:
                if self._is_cancelled(job_id):
                    return
                self._set_state(
                    job_id,
                    status=JobStatus.FAILED,
                    error=f"Codex command not found: {exc}",
                    phase="Failed",
                    latest_activity="The configured Codex command was not found.",
                )
                return
            except Exception as exc:  # pragma: no cover - defensive path
                if self._is_cancelled(job_id):
                    return
                self._set_state(
                    job_id,
                    status=JobStatus.FAILED,
                    error=f"Unexpected execution error: {exc}",
                    phase="Failed",
                    latest_activity="The local Codex subprocess could not be started.",
                )
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
                if self._timeout_seconds is None or self._timeout_seconds <= 0:
                    return_code = process.wait()
                else:
                    return_code = process.wait(timeout=self._timeout_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout_thread.join(timeout=1)
                stderr_thread.join(timeout=1)
                if self._is_cancelled(job_id):
                    return
                self._set_state(
                    job_id,
                    status=JobStatus.FAILED,
                    error=f"Execution timed out after {self._timeout_seconds} seconds.",
                    phase="Timed out",
                    latest_activity="The Codex subprocess exceeded the configured timeout.",
                )
                return

            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)

            if self._is_cancelled(job_id):
                return

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

            if self._is_cancelled(job_id):
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
        finally:
            with self._lock:
                self._processes.pop(job_id, None)
            self._cleanup_output_file(output_path)
            self._cleanup_paths(cleanup_paths)

    def _build_command(
        self,
        message: str,
        *,
        image_paths: list[str] | None = None,
        provider_session_id: str | None = None,
    ) -> tuple[list[str], str | None]:
        base_parts = shlex.split(self._command)
        image_args = self._build_image_args(image_paths)

        if not self._use_exec_mode:
            return [*base_parts, message, *image_args], None

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
                *image_args,
            ]
        else:
            exec_options = [*shlex.split(self._exec_args), "--json", "-o", output_path]
            exec_parts = [
                *base_parts,
                "exec",
                *exec_options,
                message,
                *image_args,
            ]
        return exec_parts, output_path

    def _build_image_args(self, image_paths: list[str] | None) -> list[str]:
        if not image_paths:
            return []

        image_args: list[str] = []
        for image_path in image_paths:
            image_args.extend(["-i", image_path])
        return image_args

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
        if self._is_cancelled(job_id):
            return
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
        # Keep stderr for terminal diagnostics, but do not surface transient
        # transport/auth noise in the live chat UI while the run is still active.
        return

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

    def _cleanup_paths(self, paths: list[str] | None) -> None:
        if not paths:
            return

        for path in paths:
            try:
                Path(path).unlink(missing_ok=True)
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
        listeners: list[Callable[[ExecutionSnapshot], None]]
        snapshot: ExecutionSnapshot
        should_start_successor = False
        provider_session_id_to_pass: str | None = None
        with self._lock:
            current = self._states.get(job_id)
            if (
                current is not None
                and current.status == JobStatus.CANCELLED
                and status != JobStatus.CANCELLED
            ):
                snapshot = self._snapshot_from_state(job_id, current)
                listeners = list(self._subscribers.get(job_id, ()))
            else:
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
                snapshot = self._snapshot_from_state(job_id, self._states[job_id])
                listeners = list(self._subscribers.get(job_id, ()))
                should_start_successor = (
                    status.is_terminal
                    and not (current.status.is_terminal if current else False)
                    and job_id not in self._serial_predecessors
                )
                provider_session_id_to_pass = self._states[job_id].provider_session_id

        for listener in listeners:
            try:
                listener(snapshot)
            except Exception:
                continue

        if should_start_successor:
            self._start_serial_successor(
                job_id,
                provider_session_id=provider_session_id_to_pass,
            )

    def _get_state(self, job_id: str) -> _ExecutionState | None:
        with self._lock:
            return self._states.get(job_id)

    def _is_cancelled(self, job_id: str) -> bool:
        state = self._get_state(job_id)
        return state is not None and state.status == JobStatus.CANCELLED

    def _snapshot_from_state(
        self,
        job_id: str,
        state: _ExecutionState | None,
    ) -> ExecutionSnapshot:
        if state is None:
            return ExecutionSnapshot(job_id=job_id, status=JobStatus.FAILED)
        return ExecutionSnapshot(
            job_id=job_id,
            status=state.status,
            response=state.response,
            error=state.error,
            provider_session_id=state.provider_session_id,
            phase=state.phase,
            latest_activity=state.latest_activity,
        )

    def _remove_queued_job(self, job_id: str) -> None:
        with self._lock:
            execution = self._queued_executions.pop(job_id, None)
            predecessor_job_id = self._serial_predecessors.pop(job_id, None)
            successor_job_id = self._serial_successors.pop(job_id, None)
            serial_key = self._job_serial_keys.pop(job_id, None)

            if predecessor_job_id is not None:
                if successor_job_id is not None:
                    self._serial_successors[predecessor_job_id] = successor_job_id
                    self._serial_predecessors[successor_job_id] = predecessor_job_id
                else:
                    self._serial_successors.pop(predecessor_job_id, None)
            elif successor_job_id is not None:
                self._serial_predecessors.pop(successor_job_id, None)

            if serial_key is not None and self._serial_tails.get(serial_key) == job_id:
                replacement_tail = successor_job_id or predecessor_job_id
                if replacement_tail is None:
                    self._serial_tails.pop(serial_key, None)
                else:
                    self._serial_tails[serial_key] = replacement_tail

        if execution is not None:
            self._cleanup_paths(execution.cleanup_paths)

    def _start_serial_successor(
        self,
        completed_job_id: str,
        *,
        provider_session_id: str | None,
    ) -> None:
        with self._lock:
            successor_job_id = self._serial_successors.pop(completed_job_id, None)
            serial_key = self._job_serial_keys.get(completed_job_id)
            if successor_job_id is None:
                if serial_key is not None and self._serial_tails.get(serial_key) == completed_job_id:
                    self._serial_tails.pop(serial_key, None)
                self._queued_executions.pop(completed_job_id, None)
                self._job_serial_keys.pop(completed_job_id, None)
                self._serial_predecessors.pop(completed_job_id, None)
                return

            self._serial_predecessors.pop(successor_job_id, None)
            self._queued_executions.pop(completed_job_id, None)
            self._job_serial_keys.pop(completed_job_id, None)
            self._serial_predecessors.pop(completed_job_id, None)

        self._start_execution(
            successor_job_id,
            provider_session_id_override=provider_session_id,
        )
