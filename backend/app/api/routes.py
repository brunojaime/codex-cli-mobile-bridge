from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, WebSocket

from backend.app.api.schemas import (
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
    return HealthResponse(
        server_name=container.settings.server_name,
        backend_mode=container.settings.effective_backend_mode,
        projects_root=container.settings.projects_root,
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

    return SessionDetailResponse.from_domain(
        session,
        messages=service.list_messages(session_id),
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
