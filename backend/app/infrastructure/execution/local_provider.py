from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Literal
from uuid import uuid4

from backend.app.domain.entities.codex_options import CodexRunOptions
from backend.app.domain.entities.job import JobStatus
from backend.app.infrastructure.codex_tooling import sync_repo_skills
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
    model: str | None = None
    codex_options: CodexRunOptions | None = None
    workdir: str | None = None
    serial_key: str | None = None


class LocalExecutionProvider(ExecutionProvider):
    def __init__(
        self,
        *,
        command: str,
        use_exec_mode: bool = True,
        streaming_mode: Literal["auto", "exec", "app_server"] = "auto",
        exec_args: str = "--skip-git-repo-check --color never",
        resume_args: str = "--skip-git-repo-check",
        default_reasoning_effort: str | None = None,
        workdir: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self._command = command
        self._use_exec_mode = use_exec_mode
        self._streaming_mode = streaming_mode
        self._exec_args = exec_args
        self._resume_args = resume_args
        self._default_reasoning_effort = (
            (default_reasoning_effort or "").strip() or None
        )
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
        self._submission_tokens: dict[str, str] = {}
        self._lock = threading.RLock()

    def execute(
        self,
        message: str,
        *,
        image_paths: list[str] | None = None,
        cleanup_paths: list[str] | None = None,
        provider_session_id: str | None = None,
        model: str | None = None,
        codex_options: CodexRunOptions | None = None,
        serial_key: str | None = None,
        submission_token: str | None = None,
        workdir: str | None = None,
    ) -> str:
        job_id = str(uuid4())
        execution = _QueuedExecution(
            job_id=job_id,
            message=message,
            image_paths=image_paths,
            cleanup_paths=cleanup_paths,
            provider_session_id=provider_session_id,
            model=model,
            codex_options=codex_options.normalized() if codex_options else None,
            workdir=workdir,
            serial_key=serial_key,
        )
        should_queue = False

        with self._lock:
            self._queued_executions[job_id] = execution
            if submission_token:
                self._submission_tokens[submission_token] = job_id
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

    def supports_submission_lookup(self) -> bool:
        return True

    def get_job_id_by_submission_token(self, submission_token: str) -> str | None:
        with self._lock:
            return self._submission_tokens.get(submission_token)

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
                execution.model,
                execution.codex_options,
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
        model: str | None = None,
        codex_options: CodexRunOptions | None = None,
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
        if self._should_use_app_server(
            image_paths=image_paths,
            codex_options=codex_options,
        ):
            self._run_job_with_app_server(
                job_id,
                message,
                cleanup_paths=cleanup_paths,
                provider_session_id=provider_session_id,
                model=model,
                codex_options=codex_options,
                workdir=workdir,
            )
            return

        self._run_job_with_exec(
            job_id,
            message,
            image_paths=image_paths,
            cleanup_paths=cleanup_paths,
            provider_session_id=provider_session_id,
            model=model,
            codex_options=codex_options,
            workdir=workdir,
        )

    def _run_job_with_exec(
        self,
        job_id: str,
        message: str,
        *,
        image_paths: list[str] | None = None,
        cleanup_paths: list[str] | None = None,
        provider_session_id: str | None = None,
        model: str | None = None,
        codex_options: CodexRunOptions | None = None,
        workdir: str | None = None,
    ) -> None:
        output_path: str | None = None
        resolved_workdir = workdir or self._workdir
        try:
            if resolved_workdir:
                sync_repo_skills(
                    Path.home(),
                    repo_root=Path(resolved_workdir).resolve(),
                )
            command_parts, output_path = self._build_command(
                message,
                image_paths=image_paths,
                provider_session_id=provider_session_id,
                model=model,
                codex_options=codex_options,
            )

            if self._is_cancelled(job_id):
                return

            try:
                process = subprocess.Popen(
                    command_parts,
                    cwd=resolved_workdir,
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

    def _run_job_with_app_server(
        self,
        job_id: str,
        message: str,
        *,
        cleanup_paths: list[str] | None = None,
        provider_session_id: str | None = None,
        model: str | None = None,
        codex_options: CodexRunOptions | None = None,
        workdir: str | None = None,
    ) -> None:
        process: subprocess.Popen[str] | None = None
        stderr_lines: list[str] = []
        response_buffer = ""
        final_response: str | None = None
        turn_completed = False
        thread_id = provider_session_id
        resolved_workdir = workdir or self._workdir

        def response_buffer_setter(value: str) -> None:
            nonlocal response_buffer
            response_buffer = value

        def final_response_setter(value: str | None) -> None:
            nonlocal final_response
            final_response = value

        def turn_completed_setter() -> None:
            nonlocal turn_completed
            turn_completed = True

        try:
            if resolved_workdir:
                sync_repo_skills(
                    Path.home(),
                    repo_root=Path(resolved_workdir).resolve(),
                )

            command_parts = self._build_app_server_command(codex_options=codex_options)
            process = subprocess.Popen(
                command_parts,
                cwd=resolved_workdir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            with self._lock:
                self._processes[job_id] = process

            stderr_thread = threading.Thread(
                target=self._consume_stream,
                args=(job_id, process.stderr, stderr_lines, False),
                daemon=True,
            )
            stderr_thread.start()

            self._app_server_send(
                process,
                {
                    "id": "initialize",
                    "method": "initialize",
                    "params": {
                        "clientInfo": {
                            "name": "codex-mobile-bridge",
                            "title": "Codex Mobile Bridge",
                            "version": "0.1.0",
                        },
                        "capabilities": {
                            "experimentalApi": True,
                        },
                    },
                },
            )
            self._await_app_server_response(
                process,
                request_id="initialize",
                job_id=job_id,
                response_buffer_ref=lambda: response_buffer,
                set_response_buffer=lambda value: None,
                set_final_response=lambda value: None,
                mark_turn_completed=lambda: None,
            )
            self._app_server_send(process, {"method": "initialized"})

            if provider_session_id:
                self._app_server_send(
                    process,
                    {
                        "id": "thread-resume",
                        "method": "thread/resume",
                        "params": {
                            "threadId": provider_session_id,
                        },
                    },
                )
                try:
                    thread_id = self._await_thread_response(
                        process,
                        request_id="thread-resume",
                        job_id=job_id,
                        response_buffer_ref=lambda: response_buffer,
                        set_response_buffer=lambda value: None,
                        set_final_response=lambda value: None,
                        mark_turn_completed=lambda: None,
                    )
                except _AppServerRequestError:
                    thread_id = None

            if thread_id is None:
                self._app_server_send(
                    process,
                    {
                        "id": "thread-start",
                        "method": "thread/start",
                        "params": {
                            "cwd": resolved_workdir,
                            "model": model,
                            "approvalPolicy": self._approval_policy_for_app_server(
                                self._exec_args
                            ),
                            "sandbox": self._sandbox_for_app_server(self._exec_args),
                            "experimentalRawEvents": False,
                        },
                    },
                )
                thread_id = self._await_thread_response(
                    process,
                    request_id="thread-start",
                    job_id=job_id,
                    response_buffer_ref=lambda: response_buffer,
                    set_response_buffer=lambda value: None,
                    set_final_response=lambda value: None,
                    mark_turn_completed=lambda: None,
                )

            if self._is_cancelled(job_id):
                return

            self._set_state(
                job_id,
                status=JobStatus.RUNNING,
                provider_session_id=thread_id,
                phase="Reasoning",
                latest_activity="Codex started working on the current turn.",
            )

            reasoning_effort = self._reasoning_effort_for_job(codex_options)
            self._app_server_send(
                process,
                {
                    "id": "turn-start",
                    "method": "turn/start",
                    "params": {
                        "threadId": thread_id,
                        "input": [
                            {
                                "type": "text",
                                "text": message,
                                "text_elements": [],
                            }
                        ],
                        "cwd": resolved_workdir,
                        "approvalPolicy": self._approval_policy_for_app_server(
                            self._resume_args if provider_session_id else self._exec_args
                        ),
                        "sandboxPolicy": self._sandbox_for_app_server(
                            self._resume_args if provider_session_id else self._exec_args
                        ),
                        "model": model,
                        "effort": reasoning_effort,
                    },
                },
            )
            self._await_app_server_response(
                process,
                request_id="turn-start",
                job_id=job_id,
                response_buffer_ref=lambda: response_buffer,
                set_response_buffer=lambda value: response_buffer_setter(value),
                set_final_response=lambda value: final_response_setter(value),
                mark_turn_completed=lambda: turn_completed_setter(),
            )

            if self._timeout_seconds is None or self._timeout_seconds <= 0:
                self._stream_app_server_notifications(
                    process,
                    job_id=job_id,
                    thread_id=thread_id,
                    response_buffer_ref=lambda: response_buffer,
                    set_response_buffer=lambda value: response_buffer_setter(value),
                    set_final_response=lambda value: final_response_setter(value),
                    mark_turn_completed=lambda: turn_completed_setter(),
                )
            else:
                self._stream_app_server_notifications(
                    process,
                    job_id=job_id,
                    thread_id=thread_id,
                    response_buffer_ref=lambda: response_buffer,
                    set_response_buffer=lambda value: response_buffer_setter(value),
                    set_final_response=lambda value: final_response_setter(value),
                    mark_turn_completed=lambda: turn_completed_setter(),
                    timeout_seconds=self._timeout_seconds,
                )

            if self._is_cancelled(job_id):
                return

            completed_response = (
                final_response
                or response_buffer.strip()
                or "Execution completed with no output."
            )
            self._set_state(
                job_id,
                status=JobStatus.COMPLETED,
                response=completed_response,
                provider_session_id=thread_id,
                phase="Completed",
                latest_activity="Codex returned a final response.",
            )
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
        except subprocess.TimeoutExpired:
            if process is not None:
                process.kill()
            if self._is_cancelled(job_id):
                return
            self._set_state(
                job_id,
                status=JobStatus.FAILED,
                error=f"Execution timed out after {self._timeout_seconds} seconds.",
                provider_session_id=thread_id,
                phase="Timed out",
                latest_activity="The Codex subprocess exceeded the configured timeout.",
            )
        except _AppServerRequestError as exc:
            if self._is_cancelled(job_id):
                return
            fallback_error = self._first_non_empty(stderr_lines) or str(exc)
            self._set_state(
                job_id,
                status=JobStatus.FAILED,
                error=fallback_error,
                provider_session_id=thread_id,
                phase="Failed",
                latest_activity=str(exc),
            )
        except Exception as exc:  # pragma: no cover - defensive path
            if self._is_cancelled(job_id):
                return
            fallback_error = self._first_non_empty(stderr_lines) or f"Unexpected execution error: {exc}"
            self._set_state(
                job_id,
                status=JobStatus.FAILED,
                error=fallback_error,
                provider_session_id=thread_id,
                phase="Failed",
                latest_activity="The local Codex app-server could not be started.",
            )
        finally:
            with self._lock:
                self._processes.pop(job_id, None)
            if process is not None and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=1)
                except (OSError, subprocess.TimeoutExpired):
                    try:
                        process.kill()
                    except OSError:
                        pass
            self._cleanup_paths(cleanup_paths)

    def _should_use_app_server(
        self,
        *,
        image_paths: list[str] | None,
        codex_options: CodexRunOptions | None,
    ) -> bool:
        if not self._use_exec_mode:
            return False
        if self._streaming_mode == "exec":
            return False
        if image_paths:
            return False
        if codex_options is not None and codex_options.normalized().search_enabled:
            return False
        if self._streaming_mode == "app_server":
            return True
        base_parts = shlex.split(self._command)
        if not base_parts:
            return False
        return Path(base_parts[0]).name == "codex"

    def _build_command(
        self,
        message: str,
        *,
        image_paths: list[str] | None = None,
        provider_session_id: str | None = None,
        model: str | None = None,
        codex_options: CodexRunOptions | None = None,
    ) -> tuple[list[str], str | None]:
        base_parts = shlex.split(self._command)
        image_args = self._build_image_args(image_paths)
        model_args = ["--model", model] if model else []
        codex_args = self._build_codex_args(codex_options)

        if not self._use_exec_mode:
            return [*base_parts, *model_args, *codex_args, message, *image_args], None

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
                *model_args,
                *codex_args,
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
                *model_args,
                *codex_args,
                message,
                *image_args,
            ]
        return exec_parts, output_path

    def _build_app_server_command(
        self,
        *,
        codex_options: CodexRunOptions | None,
    ) -> list[str]:
        return [
            *shlex.split(self._command),
            "app-server",
            "--listen",
            "stdio://",
            *self._build_app_server_args(codex_options),
        ]

    def _build_app_server_args(
        self,
        codex_options: CodexRunOptions | None,
    ) -> list[str]:
        if codex_options is None:
            return []

        normalized = codex_options.normalized()
        args: list[str] = []
        if normalized.profile:
            args.extend(["--profile", normalized.profile])
        for override in normalized.config_overrides:
            args.extend(["-c", override])
        return args

    def _build_codex_args(self, codex_options: CodexRunOptions | None) -> list[str]:
        normalized = codex_options.normalized() if codex_options is not None else None
        codex_args: list[str] = []
        if normalized is not None and normalized.profile:
            codex_args.extend(["--profile", normalized.profile])
        if normalized is not None and normalized.search_enabled:
            codex_args.append("--search")
        overrides = list(normalized.config_overrides) if normalized is not None else []
        if (
            self._default_reasoning_effort is not None
            and not any(
                override.strip().startswith("model_reasoning_effort")
                for override in overrides
            )
        ):
            overrides.append(
                f'model_reasoning_effort="{self._default_reasoning_effort}"'
            )
        for override in overrides:
            codex_args.extend(["-c", override])
        return codex_args

    def _build_image_args(self, image_paths: list[str] | None) -> list[str]:
        if not image_paths:
            return []

        image_args: list[str] = []
        for image_path in image_paths:
            image_args.extend(["-i", image_path])
        return image_args

    def _reasoning_effort_for_job(
        self,
        codex_options: CodexRunOptions | None,
    ) -> str | None:
        normalized = codex_options.normalized() if codex_options is not None else None
        overrides = normalized.config_overrides if normalized is not None else ()
        for override in overrides:
            key, _, value = override.partition("=")
            if key.strip() != "model_reasoning_effort":
                continue
            return value.strip().strip('"').strip("'") or None
        return self._default_reasoning_effort

    def _approval_policy_for_app_server(self, args: str) -> str | None:
        parts = shlex.split(args)
        if "--dangerously-bypass-approvals-and-sandbox" in parts:
            return "never"
        if "--full-auto" in parts:
            return "on-request"
        for index, part in enumerate(parts):
            if part in {"-a", "--ask-for-approval"} and index + 1 < len(parts):
                return parts[index + 1]
        return None

    def _sandbox_for_app_server(self, args: str) -> str | None:
        parts = shlex.split(args)
        if "--dangerously-bypass-approvals-and-sandbox" in parts:
            return "danger-full-access"
        if "--full-auto" in parts:
            return "workspace-write"
        for index, part in enumerate(parts):
            if part in {"-s", "--sandbox"} and index + 1 < len(parts):
                return parts[index + 1]
        return None

    def _app_server_send(
        self,
        process: subprocess.Popen[str],
        payload: dict[str, object],
    ) -> None:
        if process.stdin is None:
            raise _AppServerRequestError("Codex app-server stdin is not available.")
        process.stdin.write(json.dumps(payload) + "\n")
        process.stdin.flush()

    def _await_thread_response(
        self,
        process: subprocess.Popen[str],
        *,
        request_id: str,
        job_id: str,
        response_buffer_ref: Callable[[], str],
        set_response_buffer: Callable[[str], None],
        set_final_response: Callable[[str | None], None],
        mark_turn_completed: Callable[[], None],
    ) -> str:
        payload = self._await_app_server_response(
            process,
            request_id=request_id,
            job_id=job_id,
            response_buffer_ref=response_buffer_ref,
            set_response_buffer=set_response_buffer,
            set_final_response=set_final_response,
            mark_turn_completed=mark_turn_completed,
        )
        result = payload.get("result")
        if not isinstance(result, dict):
            raise _AppServerRequestError(f"Codex app-server returned no result for {request_id}.")
        thread = result.get("thread")
        if not isinstance(thread, dict):
            raise _AppServerRequestError(f"Codex app-server returned no thread for {request_id}.")
        thread_id = thread.get("id")
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise _AppServerRequestError(f"Codex app-server returned an invalid thread id for {request_id}.")
        return thread_id

    def _await_app_server_response(
        self,
        process: subprocess.Popen[str],
        *,
        request_id: str,
        job_id: str,
        response_buffer_ref: Callable[[], str],
        set_response_buffer: Callable[[str], None],
        set_final_response: Callable[[str | None], None],
        mark_turn_completed: Callable[[], None],
    ) -> dict[str, object]:
        while True:
            payload = self._read_app_server_payload(process)
            if payload.get("id") == request_id:
                error = payload.get("error")
                if isinstance(error, dict):
                    message = error.get("message")
                    if isinstance(message, str) and message.strip():
                        raise _AppServerRequestError(message)
                    raise _AppServerRequestError(
                        f"Codex app-server request {request_id} failed."
                    )
                return payload
            self._handle_app_server_payload(
                job_id,
                payload,
                response_buffer_ref=response_buffer_ref,
                set_response_buffer=set_response_buffer,
                set_final_response=set_final_response,
                mark_turn_completed=mark_turn_completed,
            )

    def _stream_app_server_notifications(
        self,
        process: subprocess.Popen[str],
        *,
        job_id: str,
        thread_id: str,
        response_buffer_ref: Callable[[], str],
        set_response_buffer: Callable[[str], None],
        set_final_response: Callable[[str | None], None],
        mark_turn_completed: Callable[[], None],
        timeout_seconds: int | None = None,
    ) -> None:
        deadline = (
            time.monotonic() + timeout_seconds
            if timeout_seconds is not None and timeout_seconds > 0
            else None
        )
        while True:
            remaining_timeout: int | None
            if deadline is None:
                remaining_timeout = None
            else:
                remaining_seconds = max(0.0, deadline - time.monotonic())
                if remaining_seconds <= 0:
                    raise subprocess.TimeoutExpired("codex app-server", timeout_seconds or 0)
                remaining_timeout = max(1, int(remaining_seconds))
            payload = self._read_app_server_payload(
                process,
                timeout_seconds=remaining_timeout,
            )
            if self._handle_app_server_payload(
                job_id,
                payload,
                response_buffer_ref=response_buffer_ref,
                set_response_buffer=set_response_buffer,
                set_final_response=set_final_response,
                mark_turn_completed=mark_turn_completed,
            ):
                return

    def _read_app_server_payload(
        self,
        process: subprocess.Popen[str],
        *,
        timeout_seconds: int | None = None,
    ) -> dict[str, object]:
        if process.stdout is None:
            raise _AppServerRequestError("Codex app-server stdout is not available.")
        if timeout_seconds is None or timeout_seconds <= 0:
            line = process.stdout.readline()
        else:
            result: dict[str, str | None] = {"line": None}
            error: dict[str, BaseException | None] = {"value": None}

            def reader() -> None:
                try:
                    result["line"] = process.stdout.readline()
                except BaseException as exc:  # pragma: no cover - defensive path
                    error["value"] = exc

            worker = threading.Thread(target=reader, daemon=True)
            worker.start()
            worker.join(timeout_seconds)
            if worker.is_alive():
                raise subprocess.TimeoutExpired("codex app-server", timeout_seconds)
            if error["value"] is not None:
                raise _AppServerRequestError(str(error["value"]))
            line = result["line"] or ""

        if not line:
            if process.poll() is not None:
                raise _AppServerRequestError(
                    "Codex app-server exited before returning a complete response."
                )
            raise _AppServerRequestError(
                "Codex app-server closed stdout before returning a complete response."
            )

        payload = self._parse_json_line(line.rstrip())
        if payload is None:
            raise _AppServerRequestError("Codex app-server emitted a non-JSON payload.")
        return payload

    def _handle_app_server_payload(
        self,
        job_id: str,
        payload: dict[str, object],
        *,
        response_buffer_ref: Callable[[], str],
        set_response_buffer: Callable[[str], None],
        set_final_response: Callable[[str | None], None],
        mark_turn_completed: Callable[[], None],
    ) -> bool:
        method = payload.get("method")
        if not isinstance(method, str):
            return False

        if method == "codex/event/agent_message_content_delta":
            params = payload.get("params")
            if not isinstance(params, dict):
                return False
            msg = params.get("msg")
            if not isinstance(msg, dict):
                return False
            delta = msg.get("delta")
            if not isinstance(delta, str) or not delta:
                return False
            updated_response = response_buffer_ref() + delta
            set_response_buffer(updated_response)
            self._set_state(
                job_id,
                status=JobStatus.RUNNING,
                response=updated_response,
                phase="Drafting reply",
                latest_activity="Codex is composing the reply.",
            )
            return False

        if method in {"item/completed", "codex/event/item_completed"}:
            final_text = self._extract_app_server_agent_message(payload)
            if final_text is not None:
                set_final_response(final_text)
                set_response_buffer(final_text)
                self._set_state(
                    job_id,
                    status=JobStatus.RUNNING,
                    response=final_text,
                    phase="Finalizing",
                    latest_activity="Codex finished the turn and is preparing the final output.",
                )
                return False

        if method == "codex/event/agent_message":
            params = payload.get("params")
            if isinstance(params, dict):
                msg = params.get("msg")
                if isinstance(msg, dict):
                    message = msg.get("message")
                    if isinstance(message, str):
                        set_final_response(message)
                        set_response_buffer(message)
                        self._set_state(
                            job_id,
                            status=JobStatus.RUNNING,
                            response=message,
                            phase="Finalizing",
                            latest_activity="Codex completed the reply.",
                        )
            return False

        phase, latest_activity = self._describe_app_server_event(payload)
        if phase is not None or latest_activity is not None:
            self._set_state(
                job_id,
                status=JobStatus.RUNNING,
                phase=phase,
                latest_activity=latest_activity,
            )

        if method == "turn/completed":
            mark_turn_completed()
            return True

        return False

    def _extract_app_server_agent_message(
        self,
        payload: dict[str, object],
    ) -> str | None:
        params = payload.get("params")
        if not isinstance(params, dict):
            return None
        item = params.get("item")
        if not isinstance(item, dict):
            return None
        item_type = str(item.get("type") or "")
        if item_type not in {"agentMessage", "AgentMessage"}:
            return None
        text = item.get("text")
        if isinstance(text, str):
            return text
        content = item.get("content")
        if not isinstance(content, list):
            return None
        segments: list[str] = []
        for entry in content:
            if not isinstance(entry, dict):
                continue
            text_value = entry.get("text")
            if isinstance(text_value, str):
                segments.append(text_value)
        if not segments:
            return None
        return "".join(segments)

    def _describe_app_server_event(
        self,
        payload: dict[str, object],
    ) -> tuple[str | None, str | None]:
        method = payload.get("method")
        if not isinstance(method, str):
            return (None, None)
        if method == "thread/started":
            return ("Starting session", "Codex started a new chat session.")
        if method == "turn/started":
            return ("Reasoning", "Codex started working on the current turn.")
        if method == "turn/completed":
            return (
                "Finalizing",
                "Codex finished the turn and is preparing the final output.",
            )
        if method == "codex/event/mcp_startup_update":
            params = payload.get("params")
            if not isinstance(params, dict):
                return ("Starting Codex CLI", None)
            msg = params.get("msg")
            if not isinstance(msg, dict):
                return ("Starting Codex CLI", None)
            server = str(msg.get("server") or "MCP server")
            status = msg.get("status")
            if not isinstance(status, dict):
                return ("Starting Codex CLI", f"{server} startup changed.")
            state = str(status.get("state") or "starting")
            if state == "failed":
                error = str(status.get("error") or "unknown error")
                return ("Starting Codex CLI", f"{server} failed to start: {error}")
            return ("Starting Codex CLI", f"{server} is {state}.")
        if method in {"item/started", "item/completed"}:
            params = payload.get("params")
            if not isinstance(params, dict):
                return ("Running Codex", None)
            item = params.get("item")
            if not isinstance(item, dict):
                return ("Running Codex", None)
            item_type = str(item.get("type") or "")
            if item_type in {"agentMessage", "AgentMessage"}:
                if method == "item/completed":
                    return ("Finalizing", "Codex completed the reply.")
                return ("Drafting reply", "Codex is composing the reply.")
            if item_type:
                human_item = self._humanize(item_type)
                if method == "item/completed":
                    return ("Running tools", f"Completed {human_item.lower()}.")
                return ("Running tools", f"Started {human_item.lower()}.")
        return (None, None)

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

        streamed_message = self._extract_agent_message(stdout_text)
        if streamed_message:
            return streamed_message

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

    def _extract_agent_message(self, stdout_text: str) -> str | None:
        latest_message: str | None = None

        for line in stdout_text.splitlines():
            payload = self._parse_json_line(line)
            if payload is None or payload.get("type") != "item.completed":
                continue

            item = payload.get("item")
            if not isinstance(item, dict) or item.get("type") != "agent_message":
                continue

            text = item.get("text")
            if isinstance(text, str) and text.strip():
                latest_message = text.strip()

        return latest_message

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


class _AppServerRequestError(RuntimeError):
    pass
