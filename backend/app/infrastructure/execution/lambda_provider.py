from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import httpx

from backend.app.domain.entities.job import JobStatus
from backend.app.infrastructure.execution.base import ExecutionProvider, ExecutionSnapshot


@dataclass(slots=True)
class _LambdaState:
    status: JobStatus
    response: str | None = None
    error: str | None = None
    provider_session_id: str | None = None
    phase: str | None = None
    latest_activity: str | None = None


@dataclass(slots=True)
class _QueuedLambdaExecution:
    job_id: str
    message: str
    image_paths: list[str] | None = None
    cleanup_paths: list[str] | None = None
    provider_session_id: str | None = None
    workdir: str | None = None
    serial_key: str | None = None


class LambdaExecutionProvider(ExecutionProvider):
    def __init__(
        self,
        *,
        endpoint: str,
        timeout_seconds: float | None = 30,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._timeout_seconds = (
            None
            if timeout_seconds is None or timeout_seconds <= 0
            else timeout_seconds
        )
        self._states: dict[str, _LambdaState] = {}
        self._subscribers: dict[str, list[Callable[[ExecutionSnapshot], None]]] = {}
        self._queued_executions: dict[str, _QueuedLambdaExecution] = {}
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
        serial_key: str | None = None,
        submission_token: str | None = None,
        workdir: str | None = None,
    ) -> str:
        job_id = str(uuid4())
        execution = _QueuedLambdaExecution(
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

    def supports_submission_lookup(self) -> bool:
        return True

    def get_job_id_by_submission_token(self, submission_token: str) -> str | None:
        with self._lock:
            return self._submission_tokens.get(submission_token)

    def get_status(self, job_id: str) -> JobStatus:
        state = self._get_state(job_id)
        return state.status if state else JobStatus.FAILED

    def get_result(self, job_id: str) -> str | None:
        state = self._get_state(job_id)
        return state.response if state else None

    def get_error(self, job_id: str) -> str | None:
        state = self._get_state(job_id)
        return state.error if state else "Unknown Lambda job id."

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

    async def _dispatch(
        self,
        job_id: str,
        message: str,
        image_paths: list[str] | None = None,
        cleanup_paths: list[str] | None = None,
        provider_session_id: str | None = None,
        workdir: str | None = None,
    ) -> None:
        self._set_state(
            job_id,
            status=JobStatus.RUNNING,
            phase="Dispatching request",
            latest_activity="Sending prompt to Lambda execution endpoint.",
        )

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                create_response = await client.post(
                    f"{self._endpoint}/message",
                    json={
                        "message": message,
                        "image_paths": image_paths or [],
                        "client_job_id": job_id,
                        "provider_session_id": provider_session_id,
                        "workdir": workdir,
                    },
                )
                create_response.raise_for_status()

                remote_payload = create_response.json()
                remote_job_id = remote_payload.get("job_id", job_id)
                remote_provider_session_id = remote_payload.get("provider_session_id")
                while True:
                    poll_response = await client.get(
                        f"{self._endpoint}/response/{remote_job_id}",
                    )
                    poll_response.raise_for_status()
                    payload = poll_response.json()
                    status = JobStatus(payload["status"])

                    if status == JobStatus.COMPLETED:
                        self._set_state(
                            job_id,
                            status=JobStatus.COMPLETED,
                            response=payload.get("response"),
                            provider_session_id=payload.get("provider_session_id")
                            or remote_provider_session_id
                            or provider_session_id,
                            phase=payload.get("phase") or "Completed",
                            latest_activity=payload.get("latest_activity")
                            or "Remote execution finished successfully.",
                        )
                        return

                    if status == JobStatus.FAILED:
                        self._set_state(
                            job_id,
                            status=JobStatus.FAILED,
                            error=payload.get("error") or "Lambda execution failed.",
                            provider_session_id=payload.get("provider_session_id")
                            or remote_provider_session_id
                            or provider_session_id,
                            phase=payload.get("phase") or "Failed",
                            latest_activity=payload.get("latest_activity")
                            or payload.get("error")
                            or "Remote execution failed.",
                        )
                        return

                    self._set_state(
                        job_id,
                        status=status,
                        provider_session_id=payload.get("provider_session_id")
                        or remote_provider_session_id
                        or provider_session_id,
                        phase=payload.get("phase") or "Running",
                        latest_activity=payload.get("latest_activity")
                        or "Waiting for remote execution result.",
                    )
                    await asyncio.sleep(2)
        except Exception as exc:  # pragma: no cover - stub transport
            self._set_state(
                job_id,
                status=JobStatus.FAILED,
                error=f"Lambda provider is configured but unreachable: {exc}",
                phase="Failed",
                latest_activity="Could not reach the configured Lambda endpoint.",
            )
        finally:
            self._cleanup_paths(cleanup_paths)
            with self._lock:
                self._queued_executions.pop(job_id, None)

    def _cleanup_paths(self, paths: list[str] | None) -> None:
        if not paths:
            return

        for path in paths:
            try:
                Path(path).unlink(missing_ok=True)
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
        phase: str | None = None,
        latest_activity: str | None = None,
    ) -> None:
        listeners: list[Callable[[ExecutionSnapshot], None]]
        snapshot: ExecutionSnapshot
        should_start_successor = False
        provider_session_id_to_pass: str | None = None
        with self._lock:
            current = self._states.get(job_id)
            self._states[job_id] = _LambdaState(
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

    def _get_state(self, job_id: str) -> _LambdaState | None:
        with self._lock:
            return self._states.get(job_id)

    def _snapshot_from_state(
        self,
        job_id: str,
        state: _LambdaState | None,
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

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            worker = threading.Thread(
                target=lambda: asyncio.run(
                    self._dispatch(
                        job_id,
                        execution.message,
                        execution.image_paths,
                        execution.cleanup_paths,
                        resolved_provider_session_id,
                        execution.workdir,
                    ),
                ),
                daemon=True,
            )
            worker.start()
        else:
            loop.create_task(
                self._dispatch(
                    job_id,
                    execution.message,
                    execution.image_paths,
                    execution.cleanup_paths,
                    resolved_provider_session_id,
                    execution.workdir,
                ),
            )

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
                self._job_serial_keys.pop(completed_job_id, None)
                self._serial_predecessors.pop(completed_job_id, None)
                return

            self._serial_predecessors.pop(successor_job_id, None)
            self._job_serial_keys.pop(completed_job_id, None)
            self._serial_predecessors.pop(completed_job_id, None)

        self._start_execution(
            successor_job_id,
            provider_session_id_override=provider_session_id,
        )
