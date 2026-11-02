from __future__ import annotations

import threading
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, ValidationError

from backend.app.api.schemas import CodexRunOptionsRequest
from backend.app.application.services.message_outbox_service import (
    MessageOutboxService,
    OutboxConflict,
)

_creation_lock = threading.Lock()


def get_outbox(container):
    with _creation_lock:
        if container.message_outbox_service is None:

            def validate(payload):
                # Preserve the same DEV/STAGE execution gate as /message.
                if payload.get("session_id"):
                    container.dev_pipeline_service.validate_stage_session_execution(
                        session_id=payload["session_id"],
                        workspace_path=payload.get("workspace_path"),
                        backend_url=container.settings.api_base_url,
                    )
                container.message_service._ensure_accepting_new_jobs()

            container.message_outbox_service = MessageOutboxService(
                database_path=(
                    container.settings.chat_store_path + ".outbox.sqlite3"
                    if container.settings.chat_store_backend == "sqlite"
                    else ":memory:"
                ),
                message_service=container.message_service,
                transcriber=container.audio_transcriber,
                validate_submission=validate,
            )
        return container.message_outbox_service


class IntakePayload(BaseModel):
    kind: Literal["text", "audio"]
    message: str = Field(default="", max_length=10000)
    session_id: str | None = Field(default=None, max_length=200)
    workspace_path: str | None = Field(default=None, max_length=4000)
    conversation_key: str = Field(min_length=1, max_length=200)
    filename: str = Field(default="voice-note.m4a", max_length=255)
    content_type: str | None = Field(default=None, max_length=200)
    language: str | None = Field(default=None, max_length=40)
    codex_options: CodexRunOptionsRequest | None = None


def build_message_outbox_router(get_container, validate_options):
    router = APIRouter(prefix="/message-outbox")

    @router.post("/{submission_id}", status_code=202)
    async def accept(
        submission_id: str,
        payload_json: str = Form(...),
        audio: UploadFile | None = File(default=None),
        container=Depends(get_container),
    ):
        if not (16 <= len(submission_id) <= 100) or not all(
            c.isalnum() or c in "-_" for c in submission_id
        ):
            raise HTTPException(422, "ID de envío inválido.")
        try:
            payload = IntakePayload.model_validate_json(payload_json)
        except ValidationError:
            raise HTTPException(422, "Contenido de envío inválido.")
        try:
            if payload.kind == "text" and not payload.message.strip():
                raise HTTPException(422, "El texto está vacío.")
            if (payload.kind == "audio") != (audio is not None):
                raise HTTPException(422, "El archivo no corresponde al tipo de envío.")
            await validate_options(
                payload.codex_options.to_domain() if payload.codex_options else None,
                container=container,
            )
            data = None
            if audio:
                data = await audio.read(container.settings.audio_max_upload_bytes + 1)
                if not data or len(data) > container.settings.audio_max_upload_bytes:
                    raise HTTPException(413, "Audio vacío o demasiado grande.")
            service = get_outbox(container)
            return await run_in_threadpool(
                service.accept, submission_id, payload.model_dump(mode="json"), data
            )
        except OutboxConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        finally:
            if audio:
                await audio.close()

    @router.get("/{submission_id}")
    async def get(submission_id: str, container=Depends(get_container)):
        try:
            return await run_in_threadpool(get_outbox(container).get, submission_id)
        except KeyError:
            raise HTTPException(404, "No se encontró el envío.")

    @router.post("/{submission_id}/{action}")
    async def action(
        submission_id: str,
        action: Literal["retry", "discard"],
        container=Depends(get_container),
    ):
        try:
            operation = getattr(get_outbox(container), action)
            return await run_in_threadpool(operation, submission_id)
        except KeyError:
            raise HTTPException(404, "No se encontró el envío.")
        except OutboxConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    return router
