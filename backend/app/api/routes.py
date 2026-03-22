from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, WebSocket

from backend.app.api.schemas import (
    AudioMessageAcceptedResponse,
    CreateSessionRequest,
    HealthResponse,
    JobResponse,
    MessageAcceptedResponse,
    MessageRequest,
    SessionDetailResponse,
    SessionSummaryResponse,
    WorkspaceResponse,
)
from backend.app.application.services.message_service import MessageService
from backend.app.container import AppContainer
from backend.app.infrastructure.network.tailscale import detect_tailscale_info
from backend.app.infrastructure.transcription.base import (
    AudioTranscriptionError,
    AudioTranscriptionUnavailableError,
)


router = APIRouter()


def get_container() -> AppContainer:
    raise RuntimeError("Container dependency was not configured.")


def get_message_service(container: AppContainer = Depends(get_container)) -> MessageService:
    return container.message_service


@router.get("/health", response_model=HealthResponse)
async def healthcheck(
    container: AppContainer = Depends(get_container),
) -> HealthResponse:
    tailscale = detect_tailscale_info(container.settings.tailscale_socket)
    audio_status = container.audio_transcriber.status()
    return HealthResponse(
        server_name=container.settings.server_name,
        backend_mode=container.settings.effective_backend_mode,
        projects_root=container.settings.projects_root,
        audio_transcription_backend=container.settings.audio_transcription_backend,
        audio_transcription_resolved_backend=audio_status.backend,
        audio_transcription_ready=audio_status.ready,
        audio_transcription_detail=audio_status.detail,
        tailscale_installed=tailscale.installed,
        tailscale_online=tailscale.online,
        tailscale_tailnet_name=tailscale.tailnet_name,
        tailscale_device_name=tailscale.device_name,
        tailscale_magic_dns_name=tailscale.magic_dns_name,
        tailscale_ipv4=tailscale.ipv4,
        tailscale_suggested_url=tailscale.suggested_url,
    )


@router.post("/message", response_model=MessageAcceptedResponse, status_code=202)
async def post_message(
    payload: MessageRequest,
    service: MessageService = Depends(get_message_service),
) -> MessageAcceptedResponse:
    try:
        job = service.submit_message(
            payload.message,
            session_id=payload.session_id,
            workspace_path=payload.workspace_path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MessageAcceptedResponse.from_domain(job)


@router.post("/message/audio", response_model=AudioMessageAcceptedResponse, status_code=202)
async def post_audio_message(
    audio: UploadFile = File(...),
    session_id: str | None = Form(default=None),
    workspace_path: str | None = Form(default=None),
    language: str | None = Form(default=None),
    container: AppContainer = Depends(get_container),
) -> AudioMessageAcceptedResponse:
    temp_path = await _store_uploaded_audio(
        audio,
        max_bytes=container.settings.audio_max_upload_bytes,
    )

    try:
        submission = container.message_service.submit_audio_message(
            str(temp_path),
            filename=audio.filename or temp_path.name,
            content_type=audio.content_type,
            session_id=session_id,
            workspace_path=workspace_path,
            language=language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AudioTranscriptionUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AudioTranscriptionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        temp_path.unlink(missing_ok=True)
        await audio.close()

    return AudioMessageAcceptedResponse.from_domain(
        submission.job,
        transcript=submission.transcript,
    )


@router.get("/workspaces", response_model=list[WorkspaceResponse])
async def list_workspaces(
    service: MessageService = Depends(get_message_service),
) -> list[WorkspaceResponse]:
    return [
        WorkspaceResponse(name=workspace.name, path=workspace.path)
        for workspace in service.list_workspaces()
    ]


@router.get("/sessions", response_model=list[SessionSummaryResponse])
async def list_sessions(
    service: MessageService = Depends(get_message_service),
) -> list[SessionSummaryResponse]:
    sessions = service.list_sessions()
    responses: list[SessionSummaryResponse] = []

    for session in sessions:
        messages = service.list_messages(session.id)
        last_message = messages[-1] if messages else None
        has_pending = any(message.status == "pending" for message in messages)
        responses.append(
            SessionSummaryResponse(
                id=session.id,
                title=session.title,
                workspace_path=session.workspace_path,
                workspace_name=session.workspace_name,
                provider_session_id=session.provider_session_id,
                created_at=session.created_at,
                updated_at=session.updated_at,
                last_message_preview=last_message.content[:120] if last_message else None,
                has_pending_messages=has_pending,
            )
        )

    return responses


@router.post("/sessions", response_model=SessionDetailResponse, status_code=201)
async def create_session(
    payload: CreateSessionRequest,
    service: MessageService = Depends(get_message_service),
) -> SessionDetailResponse:
    try:
        session = service.create_session(
            title=payload.title,
            workspace_path=payload.workspace_path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SessionDetailResponse.from_domain(session, messages=[])


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str,
    service: MessageService = Depends(get_message_service),
) -> SessionDetailResponse:
    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    messages = service.list_messages(session_id)
    jobs_by_id = {}
    for message in messages:
        if message.job_id:
            synced_job = service.get_job(message.job_id)
            if synced_job is not None:
                jobs_by_id[message.job_id] = synced_job

    return SessionDetailResponse.from_domain(
        session,
        messages=service.list_messages(session_id),
        jobs_by_id=jobs_by_id,
    )


@router.post("/sessions/{session_id}/messages", response_model=MessageAcceptedResponse, status_code=202)
async def post_session_message(
    session_id: str,
    payload: MessageRequest,
    service: MessageService = Depends(get_message_service),
) -> MessageAcceptedResponse:
    try:
        job = service.submit_message(
            payload.message,
            session_id=session_id,
            workspace_path=payload.workspace_path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MessageAcceptedResponse.from_domain(job)


@router.get("/response/{job_id}", response_model=JobResponse)
async def get_response(
    job_id: str,
    service: MessageService = Depends(get_message_service),
) -> JobResponse:
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    return JobResponse.from_domain(job)


@router.websocket("/ws/jobs/{job_id}")
async def job_updates(
    websocket: WebSocket,
    job_id: str,
    container: AppContainer = Depends(get_container),
) -> None:
    await container.job_stream_hub.stream_job(
        websocket,
        job_id=job_id,
        service=container.message_service,
    )


async def _store_uploaded_audio(
    audio: UploadFile,
    *,
    max_bytes: int,
) -> Path:
    suffix = Path(audio.filename or "voice-note.m4a").suffix or ".m4a"
    total_bytes = 0

    with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        while True:
            chunk = await audio.read(1024 * 1024)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                Path(temp_file.name).unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"Audio upload exceeds the {max_bytes} byte limit.",
                )
            temp_file.write(chunk)

    return Path(temp_file.name)
