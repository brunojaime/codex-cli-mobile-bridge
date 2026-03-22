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
                        "status": job.status,
                        "response": job.response,
                        "error": job.error,
                        "updated_at": job.updated_at.isoformat(),
                    }
                )

                if job.status.is_terminal:
                    return

                await asyncio.sleep(self._poll_interval_seconds)
        finally:
            await websocket.close()
