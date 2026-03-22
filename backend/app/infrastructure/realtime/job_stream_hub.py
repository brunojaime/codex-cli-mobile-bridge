from __future__ import annotations

import asyncio

from fastapi import WebSocket

from backend.app.application.services.message_service import MessageService


class JobStreamHub:
    def __init__(self, *, poll_interval_seconds: int) -> None:
        self._poll_interval_seconds = poll_interval_seconds

    async def stream_job(self, websocket: WebSocket, *, job_id: str, service: MessageService) -> None:
        await websocket.accept()

        try:
            while True:
                job = service.get_job(job_id)
                if job is None:
                    await websocket.send_json({"error": "Job not found."})
                    return

                await websocket.send_json(
                    {
                        "job_id": job.id,
                        "session_id": job.session_id,
                        "status": job.status,
                        "response": job.response,
                        "error": job.error,
                        "provider_session_id": job.provider_session_id,
                        "phase": job.phase,
                        "latest_activity": job.latest_activity,
                        "elapsed_seconds": job.elapsed_seconds,
                        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                        "updated_at": job.updated_at.isoformat(),
                    }
                )

                if job.status.is_terminal:
                    return

                await asyncio.sleep(self._poll_interval_seconds)
        finally:
            await websocket.close()
