from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi.concurrency import run_in_threadpool
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, WebSocket

from backend.app.api.schemas import (
    AgentConfigurationRequest,
    AgentProfileCreateRequest,
    AgentProfileImportRequest,
    AgentProfileResponse,
    AgentProfileSelectionRequest,
    ArchiveSessionRequest,
    AudioMessageAcceptedResponse,
    AutoModeConfigRequest,
    CreateSessionRequest,
    DocumentMessageAcceptedResponse,
    HealthResponse,
    ImageMessageAcceptedResponse,
    JobResponse,
    MessageAcceptedResponse,
    MessageRecoveryRequest,
    MessageRequest,
    PersistenceIntegrityIssueResponse,
    PersistenceIntegrityResponse,
    ServerCapabilitiesResponse,
    SessionDetailResponse,
    SessionSummaryResponse,
    WorkspaceResponse,
)
from backend.app.application.services.message_service import (
    AttachmentInput,
    DocumentProcessingError,
    MessageService,
    UnsupportedDocumentError,
)
from backend.app.domain.entities.chat_message import ChatMessage, ChatMessageStatus
from backend.app.domain.entities.job import Job
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
    persistence_issue = container.persistence_startup_issue
    return HealthResponse(
        server_name=container.settings.server_name,
        backend_mode=container.settings.effective_backend_mode,
        projects_root=container.settings.projects_root,
        persistence_available=container.message_service.is_persistence_available(),
        persistence_error_code=persistence_issue.code if persistence_issue else None,
        persistence_error_detail=persistence_issue.detail if persistence_issue else None,
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


@router.get("/capabilities", response_model=ServerCapabilitiesResponse)
async def capabilities(
    container: AppContainer = Depends(get_container),
) -> ServerCapabilitiesResponse:
    audio_status = container.audio_transcriber.status()
    service = container.message_service
    return ServerCapabilitiesResponse(
        supports_audio_input=audio_status.ready,
        supports_image_input=True,
        supports_document_input=True,
        supports_attachment_batch=True,
        supports_job_cancellation=service.supports_job_cancellation(),
        supports_job_retry=service.supports_job_retry(),
        supports_push_job_stream=True,
        audio_max_upload_bytes=container.settings.audio_max_upload_bytes,
        image_max_upload_bytes=container.settings.image_max_upload_bytes,
        document_max_upload_bytes=container.settings.document_max_upload_bytes,
        document_text_char_limit=container.settings.document_text_char_limit,
    )


@router.get("/debug/persistence/integrity", response_model=PersistenceIntegrityResponse)
async def persistence_integrity(
    container: AppContainer = Depends(get_container),
) -> PersistenceIntegrityResponse:
    issues = await run_in_threadpool(
        container.message_service.validate_persistence_integrity,
    )
    return PersistenceIntegrityResponse(
        backend=container.settings.chat_store_backend,
        is_healthy=not issues,
        issues=[
            PersistenceIntegrityIssueResponse.from_domain(issue)
            for issue in issues
        ],
    )


@router.post("/message", response_model=MessageAcceptedResponse, status_code=202)
async def post_message(
    payload: MessageRequest,
    service: MessageService = Depends(get_message_service),
) -> MessageAcceptedResponse:
    try:
        job = await run_in_threadpool(
            service.submit_message,
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
        submission = await run_in_threadpool(
            container.message_service.submit_audio_message,
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


@router.post("/message/image", response_model=ImageMessageAcceptedResponse, status_code=202)
async def post_image_message(
    image: UploadFile = File(...),
    message: str | None = Form(default=None),
    session_id: str | None = Form(default=None),
    workspace_path: str | None = Form(default=None),
    container: AppContainer = Depends(get_container),
) -> ImageMessageAcceptedResponse:
    temp_path = await _store_uploaded_file(
        image,
        max_bytes=container.settings.image_max_upload_bytes,
        default_filename="image-upload.bin",
        size_limit_label="Image",
    )
    should_cleanup_immediately = True

    try:
        prompt = (message or "").strip() or "Please analyze the attached image."
        job = await run_in_threadpool(
            container.message_service.submit_message,
            prompt,
            session_id=session_id,
            workspace_path=workspace_path,
            image_paths=[str(temp_path)],
            cleanup_paths=[str(temp_path)],
        )
        should_cleanup_immediately = False
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        if should_cleanup_immediately:
            temp_path.unlink(missing_ok=True)
        await image.close()

    return ImageMessageAcceptedResponse.from_domain(
        job,
        attached_image_name=image.filename or temp_path.name,
    )


@router.post("/message/document", response_model=DocumentMessageAcceptedResponse, status_code=202)
async def post_document_message(
    document: UploadFile = File(...),
    message: str | None = Form(default=None),
    session_id: str | None = Form(default=None),
    workspace_path: str | None = Form(default=None),
    language: str | None = Form(default=None),
    container: AppContainer = Depends(get_container),
) -> DocumentMessageAcceptedResponse:
    temp_path = await _store_uploaded_file(
        document,
        max_bytes=container.settings.document_max_upload_bytes,
        default_filename="document-upload.bin",
        size_limit_label="Document",
    )
    should_cleanup_immediately = True

    try:
        submission = await run_in_threadpool(
            container.message_service.submit_document_message,
            str(temp_path),
            filename=document.filename or temp_path.name,
            content_type=document.content_type,
            message=message,
            session_id=session_id,
            workspace_path=workspace_path,
            language=language,
        )
        should_cleanup_immediately = False
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except AudioTranscriptionUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (AudioTranscriptionError, DocumentProcessingError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        if should_cleanup_immediately:
            temp_path.unlink(missing_ok=True)
        await document.close()

    return DocumentMessageAcceptedResponse.from_domain(
        submission.job,
        attached_document_name=submission.attached_document_name,
        document_kind=submission.document_kind,
        transcript=submission.transcript,
        extracted_text_preview=submission.extracted_text_preview,
    )


@router.post("/message/attachments", response_model=MessageAcceptedResponse, status_code=202)
async def post_attachment_message(
    attachments: list[UploadFile] = File(...),
    message: str | None = Form(default=None),
    session_id: str | None = Form(default=None),
    workspace_path: str | None = Form(default=None),
    language: str | None = Form(default=None),
    container: AppContainer = Depends(get_container),
) -> MessageAcceptedResponse:
    stored_files = await _store_uploaded_files(
        attachments,
        max_bytes=container.settings.document_max_upload_bytes,
        default_filename="attachment-upload.bin",
        size_limit_label="Attachment",
    )
    should_cleanup_immediately = True

    try:
        job = await run_in_threadpool(
            container.message_service.submit_attachment_message,
            [
                AttachmentInput(
                    path=str(stored.path),
                    filename=stored.filename,
                    content_type=stored.content_type,
                )
                for stored in stored_files
            ],
            message=message,
            session_id=session_id,
            workspace_path=workspace_path,
            language=language,
        )
        should_cleanup_immediately = False
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except AudioTranscriptionUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (AudioTranscriptionError, DocumentProcessingError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        if should_cleanup_immediately:
            _cleanup_stored_uploads(stored_files)
        for attachment in attachments:
            await attachment.close()

    return MessageAcceptedResponse.from_domain(job)


@router.get("/workspaces", response_model=list[WorkspaceResponse])
async def list_workspaces(
    service: MessageService = Depends(get_message_service),
) -> list[WorkspaceResponse]:
    return [
        WorkspaceResponse(name=workspace.name, path=workspace.path)
        for workspace in service.list_workspaces()
    ]


@router.get("/agent-profiles", response_model=list[AgentProfileResponse])
async def list_agent_profiles(
    service: MessageService = Depends(get_message_service),
) -> list[AgentProfileResponse]:
    return [
        AgentProfileResponse.from_domain(profile)
        for profile in service.list_agent_profiles()
    ]


@router.post("/agent-profiles", response_model=AgentProfileResponse, status_code=201)
async def create_agent_profile(
    payload: AgentProfileCreateRequest,
    service: MessageService = Depends(get_message_service),
) -> AgentProfileResponse:
    try:
        profile = await run_in_threadpool(
            service.create_agent_profile,
            name=payload.name,
            description=payload.description,
            color_hex=payload.color_hex,
            configuration=payload.configuration.to_domain(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AgentProfileResponse.from_domain(profile)


@router.get("/agent-profiles/export", response_model=list[AgentProfileResponse])
async def export_agent_profiles(
    service: MessageService = Depends(get_message_service),
) -> list[AgentProfileResponse]:
    return [
        AgentProfileResponse.from_domain(profile)
        for profile in service.export_agent_profiles()
    ]


@router.post("/agent-profiles/import", response_model=list[AgentProfileResponse])
async def import_agent_profiles(
    payload: AgentProfileImportRequest,
    service: MessageService = Depends(get_message_service),
) -> list[AgentProfileResponse]:
    try:
        profiles = await run_in_threadpool(
            service.import_agent_profiles,
            profiles=[item.to_domain() for item in payload.profiles],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [
        AgentProfileResponse.from_domain(profile)
        for profile in profiles
    ]


def _jobs_by_id_for_messages(
    service: MessageService,
    messages: list[ChatMessage],
) -> dict[str, Job]:
    jobs_by_id: dict[str, Job] = {}
    for message in messages:
        if not message.job_id:
            continue
        synced_job = service.get_job(message.job_id)
        if synced_job is not None:
            jobs_by_id[message.job_id] = synced_job
    return jobs_by_id


@router.get("/sessions", response_model=list[SessionSummaryResponse])
async def list_sessions(
    service: MessageService = Depends(get_message_service),
) -> list[SessionSummaryResponse]:
    sessions = service.list_sessions()
    responses: list[SessionSummaryResponse] = []

    for session in sessions:
        messages = service.list_messages(session.id)
        jobs_by_id = _jobs_by_id_for_messages(service, messages)
        responses.append(
            SessionSummaryResponse.from_domain(
                session,
                messages=messages,
                jobs_by_id=jobs_by_id,
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
            agent_profile_id=payload.agent_profile_id,
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

    initial_messages = service.list_messages(session_id)
    for message in initial_messages:
        if message.job_id:
            service.get_job(message.job_id)

    messages = service.list_messages(session_id)
    jobs_by_id = _jobs_by_id_for_messages(service, messages)

    refreshed_session = service.get_session(session_id) or session

    return SessionDetailResponse.from_domain(
        refreshed_session,
        messages=messages,
        jobs_by_id=jobs_by_id,
    )


@router.put("/sessions/{session_id}/archive", response_model=SessionDetailResponse)
async def update_session_archive_state(
    session_id: str,
    payload: ArchiveSessionRequest,
    service: MessageService = Depends(get_message_service),
) -> SessionDetailResponse:
    try:
        session = await run_in_threadpool(
            service.set_session_archived,
            session_id=session_id,
            archived=payload.archived,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    messages = service.list_messages(session_id)
    return SessionDetailResponse.from_domain(
        session,
        messages=messages,
        jobs_by_id=_jobs_by_id_for_messages(service, messages),
    )


@router.post("/sessions/{session_id}/messages", response_model=MessageAcceptedResponse, status_code=202)
async def post_session_message(
    session_id: str,
    payload: MessageRequest,
    service: MessageService = Depends(get_message_service),
) -> MessageAcceptedResponse:
    try:
        job = await run_in_threadpool(
            service.submit_message,
            payload.message,
            session_id=session_id,
            workspace_path=payload.workspace_path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MessageAcceptedResponse.from_domain(job)


@router.put("/sessions/{session_id}/auto-mode", response_model=SessionDetailResponse)
async def update_auto_mode(
    session_id: str,
    payload: AutoModeConfigRequest,
    service: MessageService = Depends(get_message_service),
) -> SessionDetailResponse:
    try:
        session = await run_in_threadpool(
            service.update_auto_mode,
            session_id=session_id,
            enabled=payload.enabled,
            max_turns=payload.max_turns,
            reviewer_prompt=payload.reviewer_prompt,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    messages = service.list_messages(session_id)
    return SessionDetailResponse.from_domain(
        session,
        messages=messages,
        jobs_by_id=_jobs_by_id_for_messages(service, messages),
    )


@router.put("/sessions/{session_id}/agents", response_model=SessionDetailResponse)
async def update_agent_configuration(
    session_id: str,
    payload: AgentConfigurationRequest,
    service: MessageService = Depends(get_message_service),
) -> SessionDetailResponse:
    try:
        session = await run_in_threadpool(
            service.update_agent_configuration,
            session_id=session_id,
            configuration=payload.to_domain(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    messages = service.list_messages(session_id)
    return SessionDetailResponse.from_domain(
        session,
        messages=messages,
        jobs_by_id=_jobs_by_id_for_messages(service, messages),
    )


@router.put("/sessions/{session_id}/agent-profile", response_model=SessionDetailResponse)
async def apply_agent_profile_to_session(
    session_id: str,
    payload: AgentProfileSelectionRequest,
    service: MessageService = Depends(get_message_service),
) -> SessionDetailResponse:
    try:
        session = await run_in_threadpool(
            service.apply_agent_profile_to_session,
            session_id=session_id,
            profile_id=payload.profile_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    messages = service.list_messages(session_id)
    return SessionDetailResponse.from_domain(
        session,
        messages=messages,
        jobs_by_id=_jobs_by_id_for_messages(service, messages),
    )


@router.post(
    "/sessions/{session_id}/messages/{message_id}/recovery",
    response_model=SessionDetailResponse,
)
async def recover_message(
    session_id: str,
    message_id: str,
    payload: MessageRecoveryRequest,
    service: MessageService = Depends(get_message_service),
) -> SessionDetailResponse:
    try:
        session = await run_in_threadpool(
            service.recover_submission_unknown_message,
            session_id=session_id,
            message_id=message_id,
            action=payload.action,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    messages = service.list_messages(session_id)
    return SessionDetailResponse.from_domain(
        session,
        messages=messages,
        jobs_by_id=_jobs_by_id_for_messages(service, messages),
    )


@router.get("/response/{job_id}", response_model=JobResponse)
async def get_response(
    job_id: str,
    service: MessageService = Depends(get_message_service),
) -> JobResponse:
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    return JobResponse.from_domain(job)


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(
    job_id: str,
    service: MessageService = Depends(get_message_service),
) -> JobResponse:
    try:
        job = service.cancel_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return JobResponse.from_domain(job)


@router.post("/jobs/{job_id}/retry", response_model=JobResponse, status_code=202)
async def retry_job(
    job_id: str,
    service: MessageService = Depends(get_message_service),
) -> JobResponse:
    try:
        job = service.retry_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

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
    return await _store_uploaded_file(
        audio,
        max_bytes=max_bytes,
        default_filename="voice-note.m4a",
        size_limit_label="Audio",
    )


async def _store_uploaded_file(
    upload: UploadFile,
    *,
    max_bytes: int,
    default_filename: str,
    size_limit_label: str,
) -> Path:
    suffix = Path(upload.filename or default_filename).suffix or Path(default_filename).suffix
    total_bytes = 0

    with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                Path(temp_file.name).unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"{size_limit_label} upload exceeds the {max_bytes} byte limit.",
                )
            temp_file.write(chunk)

    return Path(temp_file.name)


class _StoredUpload:
    def __init__(
        self,
        *,
        path: Path,
        filename: str,
        content_type: str | None,
    ) -> None:
        self.path = path
        self.filename = filename
        self.content_type = content_type


async def _store_uploaded_files(
    uploads: list[UploadFile],
    *,
    max_bytes: int,
    default_filename: str,
    size_limit_label: str,
) -> list[_StoredUpload]:
    stored_uploads: list[_StoredUpload] = []
    try:
        for upload in uploads:
            path = await _store_uploaded_file(
                upload,
                max_bytes=max_bytes,
                default_filename=default_filename,
                size_limit_label=size_limit_label,
            )
            stored_uploads.append(
                _StoredUpload(
                    path=path,
                    filename=upload.filename or path.name,
                    content_type=upload.content_type,
                )
            )
    except Exception:
        _cleanup_stored_uploads(stored_uploads)
        raise
    return stored_uploads


def _cleanup_stored_uploads(stored_uploads: list[_StoredUpload]) -> None:
    for stored in stored_uploads:
        stored.path.unlink(missing_ok=True)
