from __future__ import annotations

import asyncio
from collections.abc import Callable

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from backend.app.application.services.message_service import MessageService
from backend.app.api.schemas import JobResponse


class JobStreamHub:
    def __init__(self, *, poll_interval_seconds: int) -> None:
        self._poll_interval_seconds = poll_interval_seconds

    async def stream_job(self, websocket: WebSocket, *, job_id: str, service: MessageService) -> None:
        await websocket.accept()
        unsubscribe: Callable[[], None] | None = None

        try:
            initial_job = await self._send_job_snapshot(websocket, job_id=job_id, service=service)
            if initial_job is None or initial_job.status.is_terminal:
                return

            queue: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
            loop = asyncio.get_running_loop()

            def on_change(_: object) -> None:
                loop.call_soon_threadsafe(self._enqueue_signal, queue)

            unsubscribe = service.watch_job(job_id, on_change)

            if unsubscribe is None:
                while True:
                    await asyncio.sleep(self._poll_interval_seconds)
                    job = await self._send_job_snapshot(websocket, job_id=job_id, service=service)
                    if job is None or job.status.is_terminal:
                        return
            else:
                while True:
                    await queue.get()
                    job = await self._send_job_snapshot(websocket, job_id=job_id, service=service)
                    if job is None or job.status.is_terminal:
                        return
        except (_ClientDisconnected, WebSocketDisconnect):
            return
        finally:
            if unsubscribe is not None:
                unsubscribe()
            await self._close_websocket(websocket)

    async def _send_job_snapshot(
        self,
        websocket: WebSocket,
        *,
        job_id: str,
        service: MessageService,
    ):
        job = service.get_job(job_id)
        if job is None:
            await self._send_json(websocket, {"error": "Job not found."})
            return None

        await self._send_json(
            websocket,
            JobResponse.from_domain(job).model_dump(mode="json"),
        )
        return job

    def _enqueue_signal(self, queue: asyncio.Queue[None]) -> None:
        if queue.full():
            return
        queue.put_nowait(None)

    async def _send_json(self, websocket: WebSocket, payload: object) -> None:
        try:
            await websocket.send_json(payload)
        except (RuntimeError, WebSocketDisconnect) as exc:
            if self._is_client_disconnect(exc):
                raise _ClientDisconnected from exc
            raise

    async def _close_websocket(self, websocket: WebSocket) -> None:
        if websocket.application_state == WebSocketState.DISCONNECTED:
            return
        try:
            await websocket.close()
        except (RuntimeError, WebSocketDisconnect):
            return

    def _is_client_disconnect(self, exc: Exception) -> bool:
        return isinstance(exc, WebSocketDisconnect) or (
            isinstance(exc, RuntimeError)
            and "close message has been sent" in str(exc).lower()
        )


class _ClientDisconnected(RuntimeError):
    pass
