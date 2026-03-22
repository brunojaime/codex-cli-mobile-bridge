from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from uuid import uuid4

import httpx

from backend.app.domain.entities.job import JobStatus
from backend.app.infrastructure.execution.base import ExecutionProvider


@dataclass(slots=True)
class _LambdaState:
    status: JobStatus
    response: str | None = None
    error: str | None = None
    provider_session_id: str | None = None
    phase: str | None = None
    latest_activity: str | None = None


class LambdaExecutionProvider(ExecutionProvider):
    def __init__(self, *, endpoint: str, timeout_seconds: int = 30) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._states: dict[str, _LambdaState] = {}
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

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            worker = threading.Thread(
                target=lambda: asyncio.run(
                    self._dispatch(job_id, message, provider_session_id, workdir),
                ),
                daemon=True,
            )
            worker.start()
        else:
            loop.create_task(
                self._dispatch(job_id, message, provider_session_id, workdir),
            )

        return job_id

    def get_status(self, job_id: str) -> JobStatus:
        state = self._get_state(job_id)
        return state.status if state else JobStatus.FAILED

    def get_result(self, job_id: str) -> str | None:
        state = self._get_state(job_id)
        return state.response if state else None

    def get_error(self, job_id: str) -> str | None:
        state = self._get_state(job_id)
        return state.error if state else "Unknown Lambda job id."

    def get_provider_session_id(self, job_id: str) -> str | None:
        state = self._get_state(job_id)
        return state.provider_session_id if state else None

    def get_phase(self, job_id: str) -> str | None:
        state = self._get_state(job_id)
        return state.phase if state else None

    def get_latest_activity(self, job_id: str) -> str | None:
        state = self._get_state(job_id)
        return state.latest_activity if state else None

    async def _dispatch(
        self,
        job_id: str,
        message: str,
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
            self._states[job_id] = _LambdaState(
                status=status,
                response=response,
                error=error,
                provider_session_id=provider_session_id,
                phase=phase,
                latest_activity=latest_activity,
            )

    def _get_state(self, job_id: str) -> _LambdaState | None:
        with self._lock:
            return self._states.get(job_id)
