from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Iterator
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, WebSocket
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response, StreamingResponse

from backend.app.api.schemas import (
    AgentConfigurationRequest,
    AgentProfileCreateRequest,
    AgentProfileImportRequest,
    AgentProfileResponse,
    AgentProfileSelectionRequest,
    ArchiveSessionRequest,
    AudioMessageAcceptedResponse,
    AutoModeConfigRequest,
    CodexConfigProfileResponse,
    CodexMcpAppInstallResponse,
    CodexMcpAppPreviewResponse,
    CodexMcpAppPromptArgumentResponse,
    CodexMcpAppPromptResponse,
    CodexMcpAppResourceResponse,
    CodexMcpAppResponse,
    CodexMcpAppToolResponse,
    CodexMcpServerResponse,
    CodexRunOptionsRequest,
    CodexSkillResponse,
    CodexStatusResponse,
    CodexToolingResponse,
    CreateSessionRequest,
    DocumentMessageAcceptedResponse,
    AppUpdateRegistryItemResponse,
    AppUpdateRegistryResponse,
    AppUpdateResponse,
    FeedbackBatchStartRequest,
    FeedbackBatchStatusResponse,
    FeedbackQueueItemRequest,
    FeedbackQueueItemResponse,
    FeedbackQueueStartRequest,
    FeedbackWorkflowPresetResponse,
    FeedbackWorkflowPresetsResponse,
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
    SpeechRequest,
    TurnSummaryConfigRequest,
    WorkspaceResponse,
)
from backend.app.application.services.app_update_service import (
    AppDisabledError,
    AppUpdateAssetNotFoundError,
    AppUpdateResult,
    GitHubReleaseError,
    UnknownAppError,
)
from backend.app.application.services.message_service import (
    AttachmentInput,
    DocumentProcessingError,
    MessageService,
    UnsupportedDocumentError,
)
from backend.app.domain.entities.chat_message import ChatMessage
from backend.app.domain.entities.agent_configuration import AgentId
from backend.app.domain.entities.job import Job, JobStatus
from backend.app.container import AppContainer
from backend.app.infrastructure.codex_tooling import (
    inspect_codex_mcp_server_selection,
    inspect_codex_tooling,
    validate_requested_mcp_server_ids,
)
from backend.app.infrastructure.mcp_apps import install_repo_mcp_app
from backend.app.infrastructure.network.tailscale import detect_tailscale_info
from backend.app.infrastructure.speech.base import (
    SpeechSynthesisError,
    SpeechSynthesisUnavailableError,
)
from backend.app.infrastructure.transcription.base import (
    AudioTranscriptionError,
    AudioTranscriptionUnavailableError,
)


router = APIRouter()

_IMAGE_CONTENT_TYPE_SUFFIXES = {
    "image/bmp": ".bmp",
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/tiff": ".tiff",
    "image/webp": ".webp",
}

_FALLBACK_FEEDBACK_WORKFLOW_PRESETS = (
    FeedbackWorkflowPresetResponse(
        id="generator_only",
        name="Generator only",
        description="Run one implementation agent for the queued app feedback.",
        target_mode="generator_only",
        includes_reviewer=False,
        default=True,
    ),
    FeedbackWorkflowPresetResponse(
        id="generator_reviewer",
        name="Generator + Reviewer",
        description="Run the implementation agent, then review the result.",
        target_mode="generator_reviewer",
        includes_reviewer=True,
    ),
)
_FEEDBACK_WORKSPACE_KEY_PATTERN = re.compile(r"[^a-z0-9]+")


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
    speech_status = container.speech_synthesizer.status()
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
        speech_synthesis_backend=speech_status.backend,
        speech_synthesis_ready=speech_status.ready,
        speech_synthesis_detail=speech_status.detail,
        speech_synthesis_voice=speech_status.voice,
        speech_synthesis_response_format=speech_status.response_format,
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
    speech_status = container.speech_synthesizer.status()
    service = container.message_service
    return ServerCapabilitiesResponse(
        supports_audio_input=audio_status.ready,
        supports_speech_output=speech_status.ready,
        supports_image_input=service.supports_image_input(),
        supports_document_input=True,
        supports_attachment_batch=True,
        supports_job_cancellation=service.supports_job_cancellation(),
        supports_job_retry=service.supports_job_retry(),
        supports_push_job_stream=True,
        speech_output_backend=speech_status.backend,
        speech_output_voice=speech_status.voice,
        speech_output_response_format=speech_status.response_format,
        audio_max_upload_bytes=container.settings.audio_max_upload_bytes,
        image_max_upload_bytes=container.settings.image_max_upload_bytes,
        document_max_upload_bytes=container.settings.document_max_upload_bytes,
        document_text_char_limit=container.settings.document_text_char_limit,
        feedback_source_workspace_aliases=(
            container.settings.feedback_source_workspace_alias_map
        ),
    )


@router.get("/app-updates", response_model=AppUpdateRegistryResponse)
async def list_app_updates(
    container: AppContainer = Depends(get_container),
) -> AppUpdateRegistryResponse:
    return AppUpdateRegistryResponse(
        apps=[
            AppUpdateRegistryItemResponse(
                source_app=config.source_app,
                display_name=config.display_name,
                enabled=config.enabled,
                required_minimum_build=config.required_minimum_build,
            )
            for config in container.app_update_service.list_apps()
        ],
    )


@router.get("/app-updates/{source_app}", response_model=AppUpdateResponse)
async def get_app_update(
    request: Request,
    source_app: str,
    platform: str = "android",
    currentVersion: str | None = None,
    currentBuild: int | None = None,
    channel: str = "stable",
    container: AppContainer = Depends(get_container),
) -> AppUpdateResponse:
    try:
        result = await run_in_threadpool(
            container.app_update_service.check_update,
            source_app=source_app,
            platform=platform,
            current_version=currentVersion,
            current_build=currentBuild,
            channel=channel,
        )
    except UnknownAppError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "unknown_source_app",
                "sourceApp": source_app,
            },
        ) from exc
    except AppDisabledError:
        result = AppUpdateResult(
            source_app=source_app,
            display_name=None,
            platform=platform,
            current_version=currentVersion,
            current_build=currentBuild,
            latest_version=currentVersion,
            latest_build=currentBuild,
            release_tag=None,
            release_url=None,
            apk_url=None,
            apk_asset_name=None,
            sha256=None,
            size_bytes=None,
            release_notes=None,
            required=False,
            available=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GitHubReleaseError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "github_unavailable",
                "message": "GitHub release metadata is unavailable.",
                "sourceApp": source_app,
            },
        ) from exc

    apk_url = None
    if result.available and result.release_tag and result.apk_asset_name:
        apk_url = str(
            request.url_for(
                "download_app_update_apk",
                source_app=result.source_app,
                release_tag=result.release_tag,
                asset_name=result.apk_asset_name,
            ).include_query_params(platform=platform, channel=channel),
        )
    return _app_update_response(result, apk_url=apk_url)


@router.head("/app-updates/{source_app}/apk/{release_tag}/{asset_name}")
async def head_app_update_apk(
    source_app: str,
    release_tag: str,
    asset_name: str,
    platform: str = "android",
    channel: str = "stable",
    container: AppContainer = Depends(get_container),
) -> Response:
    try:
        _, asset = await run_in_threadpool(
            container.app_update_service.resolve_apk_asset,
            source_app=source_app,
            release_tag=release_tag,
            asset_name=asset_name,
            platform=platform,
            channel=channel,
        )
    except AppUpdateAssetNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "apk_asset_not_found",
                "sourceApp": source_app,
                "releaseTag": release_tag,
                "assetName": asset_name,
            },
        ) from exc
    except UnknownAppError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "unknown_source_app",
                "sourceApp": source_app,
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AppDisabledError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "unknown_source_app",
                "sourceApp": source_app,
            },
        ) from exc

    return Response(
        media_type="application/vnd.android.package-archive",
        headers=_apk_download_headers(asset.name, content_length=asset.size),
    )


@router.get("/app-updates/{source_app}/apk/{release_tag}/{asset_name}")
async def download_app_update_apk(
    source_app: str,
    release_tag: str,
    asset_name: str,
    platform: str = "android",
    channel: str = "stable",
    container: AppContainer = Depends(get_container),
) -> Response:
    try:
        asset, stream = await run_in_threadpool(
            container.app_update_service.open_apk_asset_stream,
            source_app=source_app,
            release_tag=release_tag,
            asset_name=asset_name,
            platform=platform,
            channel=channel,
        )
        iterator = stream.iter_bytes()
        initial_chunks = await run_in_threadpool(_prime_apk_stream, iterator)
    except AppUpdateAssetNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "apk_asset_not_found",
                "sourceApp": source_app,
                "releaseTag": release_tag,
                "assetName": asset_name,
            },
        ) from exc
    except UnknownAppError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "unknown_source_app",
                "sourceApp": source_app,
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AppDisabledError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "unknown_source_app",
                "sourceApp": source_app,
            },
        ) from exc
    except GitHubReleaseError as exc:
        if "stream" in locals():
            stream.close()
        raise HTTPException(
            status_code=502,
            detail={
                "code": "github_unavailable",
                "message": "GitHub release asset is unavailable.",
                "sourceApp": source_app,
            },
        ) from exc

    return StreamingResponse(
        _stream_apk_body(initial_chunks, iterator, stream),
        media_type="application/vnd.android.package-archive",
        headers=_apk_download_headers(
            asset.name,
            content_length=stream.content_length or asset.size,
        ),
    )


@router.post("/audio/speech")
async def synthesize_speech(
    payload: SpeechRequest,
    container: AppContainer = Depends(get_container),
) -> Response:
    try:
        result = await run_in_threadpool(
            container.speech_synthesizer.synthesize,
            payload.text,
        )
    except SpeechSynthesisUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SpeechSynthesisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return Response(
        content=result.audio_bytes,
        media_type=result.content_type,
        headers={"X-Response-Format": result.response_format},
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
    container: AppContainer = Depends(get_container),
) -> MessageAcceptedResponse:
    codex_options = await _validate_codex_options(
        payload.codex_options.to_domain()
        if payload.codex_options is not None
        else None,
        container=container,
    )
    try:
        job = await run_in_threadpool(
            service.submit_message,
            payload.message,
            session_id=payload.session_id,
            workspace_path=payload.workspace_path,
            codex_options=codex_options,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MessageAcceptedResponse.from_domain(job)


def _feedback_item_response(
    item,
    *,
    include_image: bool = False,
) -> FeedbackQueueItemResponse:
    return FeedbackQueueItemResponse.model_validate(
        item.to_dict(include_image=include_image)
    )


def _feedback_workflow_presets(
    service: MessageService,
) -> list[FeedbackWorkflowPresetResponse]:
    profiles = service.list_agent_profiles()
    presets: list[FeedbackWorkflowPresetResponse] = []
    for profile in profiles:
        configuration = profile.resolved_configuration().normalized()
        includes_reviewer = configuration.agents[AgentId.REVIEWER].enabled
        presets.append(
            FeedbackWorkflowPresetResponse(
                id=profile.id,
                name=profile.name,
                description=profile.description,
                target_mode=(
                    "generator_reviewer" if includes_reviewer else "generator_only"
                ),
                agent_profile_id=profile.id,
                includes_reviewer=includes_reviewer,
                default=profile.id == "default",
            )
        )
    return presets or list(_FALLBACK_FEEDBACK_WORKFLOW_PRESETS)


def _feedback_preset_by_id(
    preset_id: str,
    *,
    service: MessageService,
) -> FeedbackWorkflowPresetResponse | None:
    normalized_id = preset_id.strip()
    presets = _feedback_workflow_presets(service)
    matched_preset = next(
        (preset for preset in presets if preset.id == normalized_id),
        None,
    )
    if matched_preset is not None:
        return matched_preset
    fallback_preset = next(
        (
            preset
            for preset in _FALLBACK_FEEDBACK_WORKFLOW_PRESETS
            if preset.id == normalized_id
        ),
        None,
    )
    if fallback_preset is not None:
        return fallback_preset
    return None


def _normalize_feedback_workspace_key(value: str | None) -> str:
    raw_value = (value or "").strip().lower()
    if not raw_value:
        return ""
    parts = [
        part
        for part in _FEEDBACK_WORKSPACE_KEY_PATTERN.split(raw_value)
        if part
    ]
    return "-".join(parts)


def _feedback_batch_workspace_path(
    payload: FeedbackBatchStartRequest,
    *,
    item_payloads: list[dict],
    container: AppContainer,
) -> str | None:
    explicit_workspace_path = (payload.workspace_path or "").strip()
    if explicit_workspace_path:
        return explicit_workspace_path

    candidates = [
        payload.sourceApp,
        payload.sourceDisplayName,
    ]
    for item_payload in item_payloads:
        candidates.extend(
            [
                item_payload.get("sourceApp"),
                item_payload.get("source_app"),
                item_payload.get("sourceDisplayName"),
                item_payload.get("source_display_name"),
            ]
        )
    candidate_keys = {
        key
        for key in (
            _normalize_feedback_workspace_key(str(candidate))
            for candidate in candidates
            if candidate is not None
        )
        if key and key != "unknown"
    }
    if not candidate_keys:
        return None

    aliases = {
        _normalize_feedback_workspace_key(source_app): workspace_path
        for source_app, workspace_path in (
            container.settings.feedback_source_workspace_alias_map.items()
        )
    }
    for candidate_key in candidate_keys:
        workspace_path = aliases.get(candidate_key)
        if workspace_path:
            return workspace_path

    for workspace in container.message_service.list_workspaces():
        workspace_keys = {
            _normalize_feedback_workspace_key(workspace.name),
            _normalize_feedback_workspace_key(Path(workspace.path).name),
        }
        if candidate_keys & workspace_keys:
            return workspace.path

    return None


def _feedback_target_instruction(target_mode: str) -> str:
    if target_mode == "generator_only":
        return (
            "Generator only. Run the implementation generator for this feedback; "
            "do not run a reviewer unless the user asks later."
        )
    return (
        "Generator + Reviewer. Run the implementation generator for this "
        "feedback and then run the reviewer on the generator result."
    )


def _feedback_release_instruction(*, includes_reviewer: bool) -> str:
    if includes_reviewer:
        return (
            "\nRelease instruction: when the reviewer finishes and approves the "
            "implementation, publish the required release for the target app. "
            "Do not publish if review requests changes or validation fails."
        )
    return (
        "\nRelease instruction: after implementation and validation complete, "
        "publish the required release for the target app. Do not publish if "
        "validation fails."
    )


def _feedback_audio_note(item) -> str:
    if item.audio_mime_type or item.audio_duration_ms or item.audio_byte_length:
        return (
            "\nAudio attached: "
            f"{item.audio_mime_type or 'unknown type'}, "
            f"{item.audio_duration_ms or 0} ms, "
            f"{item.audio_byte_length or 0} bytes."
        )
    return ""


async def _feedback_audio_prompt_note(
    item,
    *,
    container: AppContainer,
) -> str:
    audio_note = _feedback_audio_note(item)
    if not item.audio_file:
        return audio_note

    try:
        transcript = (
            await run_in_threadpool(
                container.audio_transcriber.transcribe,
                Path(item.audio_file),
                filename=Path(item.audio_file).name,
                content_type=item.audio_mime_type,
            )
        ).strip()
    except AudioTranscriptionUnavailableError:
        return (
            f"{audio_note}\nAudio transcript unavailable; "
            "using audio metadata only."
        )
    except AudioTranscriptionError as exc:
        return (
            f"{audio_note}\nAudio transcript failed: {exc}; "
            "using audio metadata only."
        )

    if not transcript:
        return (
            f"{audio_note}\nAudio transcript unavailable; "
            "transcriber returned empty text."
        )

    await run_in_threadpool(
        container.feedback_queue_service.set_audio_transcript,
        item.id,
        transcript,
    )
    item.audio_transcript = transcript
    return f"{audio_note}\nAudio transcript: {transcript}"


async def _feedback_batch_status_response(
    record,
    *,
    container: AppContainer,
) -> FeedbackBatchStatusResponse:
    job = None
    if record.job_id:
        job = await run_in_threadpool(container.message_service.get_job, record.job_id)

    status, status_detail = _feedback_batch_status_from_job(record, job)
    if status in {"completed", "failed"} and not (record.summary or "").strip():
        summary = _build_feedback_final_summary(
            record,
            job=job,
            status=status,
            status_detail=status_detail,
        )
        record = await run_in_threadpool(
            container.feedback_queue_service.set_batch_summary,
            record.id,
            summary,
        )
    if status in {"completed", "failed"} and not record.notification_created_at:
        record = await run_in_threadpool(
            container.feedback_queue_service.ensure_batch_notification,
            record.id,
        )
    summary = (record.summary or "").strip() or None
    return FeedbackBatchStatusResponse(
        batch_id=record.id,
        source_app=record.source_app,
        source_display_name=record.source_display_name,
        status=status,
        status_detail=status_detail,
        workflow_preset_id=record.workflow_preset_id,
        release_when_complete=record.release_when_complete,
        item_count=record.item_count,
        item_ids=record.item_ids,
        job_id=record.job_id,
        session_id=record.session_id,
        run_id=job.run_id if job else None,
        workspace_path=record.workspace_path,
        job_status=job.status if job else None,
        summary=summary,
        summary_generated_at=record.summary_generated_at,
        summary_line_count=_non_empty_line_count(summary),
        notification_created_at=record.notification_created_at,
        notification_read_at=record.notification_read_at,
        notification_unread=bool(
            record.notification_created_at and not record.notification_read_at
        ),
        created_at=record.created_at,
        submitted_at=record.submitted_at,
    )


def _feedback_batch_status_from_job(record, job: Job | None) -> tuple[str, str | None]:
    if record.job_id and job is None:
        return "failed", "Linked job was not found."
    if job is None:
        return _normalize_feedback_batch_status(record.status), None
    if job.status == JobStatus.PENDING:
        return "pending", job.latest_activity
    if job.status == JobStatus.RUNNING:
        return "running", job.latest_activity
    if job.status == JobStatus.COMPLETED:
        return "completed", job.latest_activity
    return "failed", job.error or job.latest_activity


def _normalize_feedback_batch_status(status: str) -> str:
    normalized = (status or "").strip().lower()
    if normalized in {"pending", "running", "review", "release", "completed", "failed"}:
        return normalized
    if normalized in {"submitted", "started"}:
        return "running"
    return "pending"


def _build_feedback_final_summary(
    record,
    *,
    job: Job | None,
    status: str,
    status_detail: str | None,
) -> str:
    result = "completed successfully" if status == "completed" else "failed"
    reviewer = (
        "Reviewer was requested by the selected workflow."
        if "reviewer" in record.workflow_preset_id
        else "Reviewer was not requested by the selected workflow."
    )
    release = (
        "Release was requested after validation."
        if record.release_when_complete
        else "Release was not requested for this batch."
    )
    validation = (
        "Validation details should be read from the completed Codex response."
        if job and job.response
        else "Validation details were not reported by a completed response."
    )
    failure = status_detail or (job.error if job else None) or "No failure detail."
    return "\n".join(
        [
            f"1. Request: process developer feedback batch {record.id}.",
            f"2. Source app: {record.source_app}.",
            f"3. Source display name: {record.source_display_name or 'not provided'}.",
            f"4. Screenshots/comments used: {record.item_count} item(s).",
            f"5. Feedback item ids: {', '.join(record.item_ids) or 'none recorded'}.",
            "6. Selected areas and bounds are recorded in the batch prompt.",
            f"7. Workflow preset: {record.workflow_preset_id}.",
            f"8. Reviewer: {reviewer}",
            f"9. Release: {release}",
            "10. Implementation: see the linked Codex job response for changed areas.",
            f"11. Validation: {validation}",
            f"12. Final result: workflow {result}.",
            f"13. Remaining risk or next step: {failure if status == 'failed' else 'review the app build before publishing.'}",
        ]
    )


def _non_empty_line_count(value: str | None) -> int:
    return len([line for line in (value or "").splitlines() if line.strip()])


def _validate_feedback_base64(value: str, *, field_name: str, item_index: int) -> None:
    try:
        base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Feedback batch item {item_index} has invalid {field_name}.",
        ) from exc


@router.get(
    "/feedback-workflow-presets",
    response_model=FeedbackWorkflowPresetsResponse,
)
async def list_feedback_workflow_presets(
    service: MessageService = Depends(get_message_service),
) -> FeedbackWorkflowPresetsResponse:
    presets = _feedback_workflow_presets(service)
    default_preset = next(
        (preset for preset in presets if preset.default),
        presets[0],
    )
    return FeedbackWorkflowPresetsResponse(
        default_preset_id=default_preset.id,
        presets=presets,
    )


@router.get("/feedback-queue", response_model=list[FeedbackQueueItemResponse])
async def list_feedback_queue(
    include_images: bool = False,
    container: AppContainer = Depends(get_container),
) -> list[FeedbackQueueItemResponse]:
    items = await run_in_threadpool(
        container.feedback_queue_service.list_items,
        include_images=include_images,
    )
    return [
        _feedback_item_response(item, include_image=include_images)
        for item in items
    ]


@router.post(
    "/feedback-queue",
    response_model=FeedbackQueueItemResponse,
    status_code=201,
)
async def create_feedback_queue_item(
    payload: FeedbackQueueItemRequest,
    container: AppContainer = Depends(get_container),
) -> FeedbackQueueItemResponse:
    try:
        item = await run_in_threadpool(
            container.feedback_queue_service.create_item,
            payload.model_dump(by_alias=False, exclude_none=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _feedback_item_response(item, include_image=True)


@router.delete("/feedback-queue/{item_id}", status_code=204)
async def delete_feedback_queue_item(
    item_id: str,
    container: AppContainer = Depends(get_container),
) -> Response:
    try:
        await run_in_threadpool(container.feedback_queue_service.delete_item, item_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Feedback item not found.") from exc
    return Response(status_code=204)


@router.delete("/feedback-queue", status_code=204)
async def clear_feedback_queue(
    container: AppContainer = Depends(get_container),
) -> Response:
    await run_in_threadpool(container.feedback_queue_service.clear)
    return Response(status_code=204)


@router.post(
    "/feedback-queue/{item_id}/start-session",
    response_model=ImageMessageAcceptedResponse,
    status_code=202,
)
async def start_feedback_queue_session(
    item_id: str,
    payload: FeedbackQueueStartRequest,
    container: AppContainer = Depends(get_container),
) -> ImageMessageAcceptedResponse:
    try:
        item = await run_in_threadpool(
            container.feedback_queue_service.get_item,
            item_id,
            include_image=False,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Feedback item not found.") from exc

    if item.screenshot_file is None:
        raise HTTPException(status_code=422, detail="Feedback item has no screenshot.")
    source_image_path = Path(item.screenshot_file)
    if not source_image_path.exists():
        raise HTTPException(status_code=422, detail="Feedback screenshot is missing.")
    with NamedTemporaryFile(delete=False, suffix=".png") as temp_image:
        temp_image.write(source_image_path.read_bytes())
        temp_image_path = Path(temp_image.name)

    codex_options = await _validate_codex_options(
        payload.codex_options.to_domain()
        if payload.codex_options is not None
        else None,
        container=container,
    )
    audio_note = _feedback_audio_note(item)
    target_instruction = _feedback_target_instruction(payload.target_mode)
    source_label = _feedback_source_label(
        source_display_name=item.source_display_name,
        source_app=item.source_app,
        workspace_path=payload.workspace_path,
    )
    message = payload.message or (
        f"Use this {source_label} feedback screenshot and note to make "
        "the requested UI/app change.\n\n"
        f"Run target: {target_instruction}\n"
        f"Feedback: {item.comment}\n"
        f"Selection bounds: {item.selection_bounds}"
        f"{audio_note}"
    )
    should_cleanup_temp_image = True
    try:
        submission = await run_in_threadpool(
            container.message_service.submit_image_message,
            str(temp_image_path),
            filename=f"{item.id}.png",
            content_type=item.screenshot_mime_type,
            message=message,
            session_id=payload.session_id,
            workspace_path=payload.workspace_path,
            codex_options=codex_options,
        )
        should_cleanup_temp_image = False
        await run_in_threadpool(container.feedback_queue_service.mark_submitted, item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    finally:
        if should_cleanup_temp_image:
            temp_image_path.unlink(missing_ok=True)

    return ImageMessageAcceptedResponse.from_domain(
        submission.job,
        attached_image_name=submission.attached_image_name,
    )


@router.post(
    "/feedback-batches/start-session",
    response_model=MessageAcceptedResponse,
    status_code=202,
)
async def start_feedback_batch_session(
    payload: FeedbackBatchStartRequest,
    container: AppContainer = Depends(get_container),
) -> MessageAcceptedResponse:
    if not payload.items:
        raise HTTPException(status_code=422, detail="Feedback batch has no items.")
    preset = _feedback_preset_by_id(
        payload.workflow_preset_id,
        service=container.message_service,
    )
    if preset is None:
        raise HTTPException(status_code=422, detail="Unknown feedback workflow preset.")

    item_payloads = []
    for index, item_request in enumerate(payload.items, start=1):
        item_payload = item_request.model_dump(by_alias=False, exclude_none=True)
        if not str(item_payload.get("screenshotPngBase64") or "").strip():
            raise HTTPException(
                status_code=422,
                detail=f"Feedback batch item {index} has no screenshot.",
            )
        _validate_feedback_base64(
            str(item_payload["screenshotPngBase64"]),
            field_name="screenshotPngBase64",
            item_index=index,
        )
        if str(item_payload.get("audioBase64") or "").strip():
            _validate_feedback_base64(
                str(item_payload["audioBase64"]),
                field_name="audioBase64",
                item_index=index,
            )
        source_app = str(item_payload.get("sourceApp") or "").strip().lower()
        if not source_app or source_app == "unknown":
            item_payload["sourceApp"] = payload.sourceApp
        if (
            not str(item_payload.get("sourceDisplayName") or "").strip()
            and payload.sourceDisplayName
        ):
            item_payload["sourceDisplayName"] = payload.sourceDisplayName
        item_payloads.append(item_payload)
    workspace_path = _feedback_batch_workspace_path(
        payload,
        item_payloads=item_payloads,
        container=container,
    )

    stored_items = []
    try:
        for item_payload in item_payloads:
            stored_items.append(
                await run_in_threadpool(
                    container.feedback_queue_service.create_item,
                    item_payload,
                )
            )
    except ValueError as exc:
        for item in stored_items:
            await run_in_threadpool(container.feedback_queue_service.delete_item, item.id)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    temp_image_paths: list[Path] = []
    attachments: list[AttachmentInput] = []
    try:
        for index, item in enumerate(stored_items, start=1):
            if item.screenshot_file is None:
                raise HTTPException(
                    status_code=422,
                    detail="Feedback item has no screenshot.",
                )
            source_image_path = Path(item.screenshot_file)
            if not source_image_path.exists():
                raise HTTPException(
                    status_code=422,
                    detail="Feedback screenshot is missing.",
                )
            suffix = _IMAGE_CONTENT_TYPE_SUFFIXES.get(item.screenshot_mime_type, ".png")
            with NamedTemporaryFile(delete=False, suffix=suffix) as temp_image:
                temp_image.write(source_image_path.read_bytes())
                temp_image_path = Path(temp_image.name)
            temp_image_paths.append(temp_image_path)
            attachments.append(
                AttachmentInput(
                    path=str(temp_image_path),
                    filename=f"{index:02d}-{item.id}{suffix}",
                    content_type=item.screenshot_mime_type,
                )
            )
    except HTTPException:
        for temp_image_path in temp_image_paths:
            temp_image_path.unlink(missing_ok=True)
        for item in stored_items:
            await run_in_threadpool(container.feedback_queue_service.delete_item, item.id)
        raise

    should_keep_stored_items = False
    should_cleanup_temp_images = True
    try:
        codex_options = await _validate_codex_options(
            payload.codex_options.to_domain()
            if payload.codex_options is not None
            else None,
            container=container,
        )
        first_item = stored_items[0]
        source_label = _feedback_source_label(
            source_display_name=payload.sourceDisplayName
            or first_item.source_display_name,
            source_app=payload.sourceApp or first_item.source_app,
            workspace_path=workspace_path,
        )
        target_session_id = payload.session_id
        if target_session_id is None and preset.agent_profile_id:
            try:
                session = await run_in_threadpool(
                    container.message_service.create_session,
                    title=f"{source_label} feedback",
                    workspace_path=workspace_path,
                    agent_profile_id=preset.agent_profile_id,
                    title_is_placeholder=False,
                )
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            target_session_id = session.id
        item_sections = []
        for index, item in enumerate(stored_items, start=1):
            audio_note = await _feedback_audio_prompt_note(item, container=container)
            item_sections.append(
                f"Item {index} ({item.id}):\n"
                f"Feedback: {item.comment}\n"
                f"Selection bounds: {item.selection_bounds}"
                f"{audio_note}"
            )
        release_note = (
            _feedback_release_instruction(includes_reviewer=preset.includes_reviewer)
            if payload.release_when_complete
            else ""
        )
        message = payload.message or (
            f"Use these {source_label} feedback screenshots and notes as one "
            "batch to make the requested UI/app changes.\n\n"
            f"Run target: {_feedback_target_instruction(preset.target_mode)}\n"
            f"Workflow preset: {preset.name}\n"
            f"Batch size: {len(stored_items)} feedback items.\n\n"
            + "\n\n".join(item_sections)
            + release_note
        )
        job = await run_in_threadpool(
            container.message_service.submit_attachment_message,
            attachments,
            message=message,
            session_id=target_session_id,
            workspace_path=workspace_path,
            codex_options=codex_options,
        )
        should_cleanup_temp_images = False
        for item in stored_items:
            await run_in_threadpool(
                container.feedback_queue_service.mark_submitted,
                item.id,
            )
        batch_record = await run_in_threadpool(
            container.feedback_queue_service.create_batch_record,
            batch_id=None,
            source_app=payload.sourceApp or first_item.source_app,
            source_display_name=payload.sourceDisplayName
            or first_item.source_display_name,
            workflow_preset_id=payload.workflow_preset_id,
            release_when_complete=payload.release_when_complete,
            items=stored_items,
            job_id=job.id,
            session_id=job.session_id,
            workspace_path=workspace_path,
            message=message,
        )
        should_keep_stored_items = True
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    finally:
        if should_cleanup_temp_images:
            for temp_image_path in temp_image_paths:
                temp_image_path.unlink(missing_ok=True)
        if not should_keep_stored_items:
            for item in stored_items:
                await run_in_threadpool(
                    container.feedback_queue_service.delete_item,
                    item.id,
                )

    return MessageAcceptedResponse.from_domain(
        job,
        feedback_batch_id=batch_record.id,
    )


@router.get(
    "/feedback-batches",
    response_model=list[FeedbackBatchStatusResponse],
)
async def list_feedback_batches(
    source_app: str | None = Query(default=None, alias="sourceApp"),
    container: AppContainer = Depends(get_container),
) -> list[FeedbackBatchStatusResponse]:
    records = await run_in_threadpool(
        container.feedback_queue_service.list_batches,
        source_app=source_app,
    )
    return [
        await _feedback_batch_status_response(record, container=container)
        for record in records
    ]


@router.get(
    "/feedback-batches/{batch_id}",
    response_model=FeedbackBatchStatusResponse,
)
async def get_feedback_batch_status(
    batch_id: str,
    container: AppContainer = Depends(get_container),
) -> FeedbackBatchStatusResponse:
    try:
        record = await run_in_threadpool(
            container.feedback_queue_service.get_batch,
            batch_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Feedback batch not found.") from exc

    return await _feedback_batch_status_response(record, container=container)


def _feedback_source_label(
    *,
    source_display_name: str | None,
    source_app: str | None,
    workspace_path: str | None,
) -> str:
    display_name = (source_display_name or "").strip()
    if display_name:
        return display_name
    source_value = (source_app or "").strip()
    if source_value and source_value.lower() != "unknown":
        return _humanize_feedback_source(source_value)
    if workspace_path:
        path_name = Path(workspace_path).name.strip()
        if path_name:
            return _humanize_feedback_source(path_name)
    return "app"


def _humanize_feedback_source(value: str) -> str:
    return " ".join(part.capitalize() for part in value.replace("_", "-").split("-"))


@router.get("/codex/tooling", response_model=CodexToolingResponse)
async def codex_tooling(
    workspace_path: str | None = None,
    container: AppContainer = Depends(get_container),
) -> CodexToolingResponse:
    repo_root = Path(workspace_path).resolve() if workspace_path else Path(
        container.settings.codex_workdir
    ).resolve()
    snapshot = await run_in_threadpool(
        inspect_codex_tooling,
        container.settings.codex_command,
        repo_root=repo_root,
        apps_repo_root=Path(container.settings.codex_workdir).resolve(),
        projects_root=container.settings.projects_root,
    )
    return CodexToolingResponse(
        status=CodexStatusResponse(
            cli_available=snapshot.status.cli_available,
            command=snapshot.status.command,
            version=snapshot.status.version,
            logged_in=snapshot.status.logged_in,
            auth_mode=snapshot.status.auth_mode,
            status_summary=snapshot.status.status_summary,
            raw_status=snapshot.status.raw_status,
            usage_available=snapshot.status.usage_available,
            usage_label=snapshot.status.usage_label,
            usage_summary=snapshot.status.usage_summary,
            error=snapshot.status.error,
        ),
        profiles=[
            CodexConfigProfileResponse(name=profile.name)
            for profile in snapshot.profiles
        ],
        skills=[
            CodexSkillResponse(
                skill_id=skill.skill_id,
                name=skill.name,
                description=skill.description,
                source=skill.source,
                path=skill.path,
            )
            for skill in snapshot.skills
        ],
        mcp_servers=[
            CodexMcpServerResponse(
                server_id=server.server_id,
                summary=server.summary,
                source=server.source,
                backing_app_id=server.backing_app_id,
                status=server.status,
                selectable=server.selectable,
                selectable_reason=server.selectable_reason,
                disabled_reason=server.disabled_reason,
                lookup_error=server.lookup_error,
            )
            for server in snapshot.mcp_servers
        ],
        mcp_apps=[
            CodexMcpAppResponse(
                app_id=app.app_id,
                name=app.name,
                description=app.description,
                recommended_server_id=app.recommended_server_id,
                transport=app.transport,
                command=app.command,
                args=list(app.args),
                env=dict(app.env),
                tags=list(app.tags),
                supports_ui_extension=app.supports_ui_extension,
                ui_entry_uri=app.ui_entry_uri,
                spec_path=app.spec_path,
                installed=app.installed,
                install_state=app.install_state,
                server_present=app.server_present,
                server_presence_known=app.server_presence_known,
                config_matches=app.config_matches,
                tools=[
                    CodexMcpAppToolResponse(
                        name=tool.name,
                        title=tool.title,
                        description=tool.description,
                        read_only=tool.read_only,
                        destructive=tool.destructive,
                        idempotent=tool.idempotent,
                        open_world=tool.open_world,
                        input_schema=tool.input_schema,
                    )
                    for tool in app.tools
                ],
                resources=[
                    CodexMcpAppResourceResponse(
                        name=resource.name,
                        title=resource.title,
                        uri=resource.uri,
                        description=resource.description,
                        mime_type=resource.mime_type,
                    )
                    for resource in app.resources
                ],
                prompts=[
                    CodexMcpAppPromptResponse(
                        name=prompt.name,
                        title=prompt.title,
                        description=prompt.description,
                        arguments=[
                            CodexMcpAppPromptArgumentResponse(
                                name=argument.name,
                                description=argument.description,
                                required=argument.required,
                            )
                            for argument in prompt.arguments
                        ],
                    )
                    for prompt in app.prompts
                ],
                preview=(
                    CodexMcpAppPreviewResponse(
                        tool_name=app.preview.tool_name,
                        arguments=app.preview.arguments,
                        result=app.preview.result,
                        is_error=app.preview.is_error,
                        error=app.preview.error,
                    )
                    if app.preview is not None
                    else None
                ),
                drift_summary=app.drift_summary,
                disabled_reason=app.disabled_reason,
                lookup_error=app.lookup_error,
                validation_error=app.validation_error,
                protocol_error=app.protocol_error,
            )
            for app in snapshot.mcp_apps
        ],
        mcp_server_inventory_complete=snapshot.mcp_server_inventory_complete,
        mcp_raw_output=snapshot.mcp_raw_output,
        mcp_error=snapshot.mcp_error,
        config_path=snapshot.config_path,
    )


@router.post(
    "/codex/mcp-apps/{app_id}/install",
    response_model=CodexMcpAppInstallResponse,
)
async def install_codex_mcp_app(
    app_id: str,
    container: AppContainer = Depends(get_container),
) -> CodexMcpAppInstallResponse:
    try:
        result = await run_in_threadpool(
            install_repo_mcp_app,
            container.settings.codex_command,
            repo_root=Path(container.settings.codex_workdir).resolve(),
            projects_root=container.settings.projects_root,
            app_id=app_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return CodexMcpAppInstallResponse(
        app_id=result.app_id,
        server_id=result.server_id,
        already_installed=result.already_installed,
        reconciled=result.reconciled,
        command=result.command,
        summary=result.summary,
    )


@router.post("/message/audio", response_model=AudioMessageAcceptedResponse, status_code=202)
async def post_audio_message(
    audio: UploadFile = File(...),
    session_id: str | None = Form(default=None),
    workspace_path: str | None = Form(default=None),
    language: str | None = Form(default=None),
    codex_options_json: str | None = Form(default=None),
    container: AppContainer = Depends(get_container),
) -> AudioMessageAcceptedResponse:
    temp_path = await _store_uploaded_audio(
        audio,
        max_bytes=container.settings.audio_max_upload_bytes,
    )

    try:
        codex_options = await _parse_and_validate_codex_options_json(
            codex_options_json,
            container=container,
        )
        submission = await run_in_threadpool(
            container.message_service.submit_audio_message,
            str(temp_path),
            filename=audio.filename or temp_path.name,
            content_type=audio.content_type,
            session_id=session_id,
            workspace_path=workspace_path,
            language=language,
            codex_options=codex_options,
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
    codex_options_json: str | None = Form(default=None),
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
        codex_options = await _parse_and_validate_codex_options_json(
            codex_options_json,
            container=container,
        )
        submission = await run_in_threadpool(
            container.message_service.submit_image_message,
            str(temp_path),
            filename=image.filename or temp_path.name,
            content_type=image.content_type,
            message=message,
            session_id=session_id,
            workspace_path=workspace_path,
            codex_options=codex_options,
        )
        should_cleanup_immediately = False
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    finally:
        if should_cleanup_immediately:
            temp_path.unlink(missing_ok=True)
        await image.close()

    return ImageMessageAcceptedResponse.from_domain(
        submission.job,
        attached_image_name=submission.attached_image_name,
    )


@router.post("/message/document", response_model=DocumentMessageAcceptedResponse, status_code=202)
async def post_document_message(
    document: UploadFile = File(...),
    message: str | None = Form(default=None),
    session_id: str | None = Form(default=None),
    workspace_path: str | None = Form(default=None),
    language: str | None = Form(default=None),
    codex_options_json: str | None = Form(default=None),
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
        codex_options = await _parse_and_validate_codex_options_json(
            codex_options_json,
            container=container,
        )
        submission = await run_in_threadpool(
            container.message_service.submit_document_message,
            str(temp_path),
            filename=document.filename or temp_path.name,
            content_type=document.content_type,
            message=message,
            session_id=session_id,
            workspace_path=workspace_path,
            language=language,
            codex_options=codex_options,
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
    codex_options_json: str | None = Form(default=None),
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
        codex_options = await _parse_and_validate_codex_options_json(
            codex_options_json,
            container=container,
        )
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
            codex_options=codex_options,
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
    *,
    sync_jobs: bool = True,
) -> dict[str, Job]:
    jobs_by_id: dict[str, Job] = {}
    terminal_sync_seen = False
    for message in messages:
        if not message.job_id:
            continue
        synced_job = (
            service.get_job(message.job_id)
            if sync_jobs
            else service.get_stored_job(message.job_id)
        )
        if synced_job is not None:
            jobs_by_id[message.job_id] = synced_job
            if synced_job.status.is_terminal:
                terminal_sync_seen = True
    if sync_jobs and terminal_sync_seen and messages:
        messages[:] = service.list_messages(messages[0].session_id)
    return jobs_by_id


def _run_configurations_by_id_for_session(
    service: MessageService,
    session_id: str,
) -> dict[str, object]:
    return {
        agent_run.run_id: agent_run.configuration
        for agent_run in service.list_agent_runs(session_id)
    }


@router.get("/sessions", response_model=list[SessionSummaryResponse])
async def list_sessions(
    service: MessageService = Depends(get_message_service),
) -> list[SessionSummaryResponse]:
    sessions = service.list_sessions()
    responses: list[SessionSummaryResponse] = []

    for session in sessions:
        messages = service.list_messages(session.id)
        jobs_by_id = _jobs_by_id_for_messages(service, messages, sync_jobs=False)
        responses.append(
            SessionSummaryResponse.from_domain(
                session,
                messages=messages,
                turn_summaries=service.list_turn_summaries(session.id),
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
            turn_summaries_enabled=payload.turn_summaries_enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SessionDetailResponse.from_domain(
        session,
        messages=[],
        turn_summaries=[],
    )


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str,
    service: MessageService = Depends(get_message_service),
) -> SessionDetailResponse:
    session = service.refresh_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    initial_messages = service.list_messages(session_id)
    for message in initial_messages:
        if message.job_id:
            service.get_job(message.job_id)

    messages = service.list_messages(session_id)
    jobs_by_id = _jobs_by_id_for_messages(service, messages)

    refreshed_session = service.refresh_session(session_id) or session

    return SessionDetailResponse.from_domain(
        refreshed_session,
        messages=messages,
        turn_summaries=service.list_turn_summaries(session_id),
        jobs_by_id=jobs_by_id,
        run_configurations_by_id=_run_configurations_by_id_for_session(service, session_id),
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
        turn_summaries=service.list_turn_summaries(session_id),
        jobs_by_id=_jobs_by_id_for_messages(service, messages),
        run_configurations_by_id=_run_configurations_by_id_for_session(service, session_id),
    )


@router.post("/sessions/{session_id}/messages", response_model=MessageAcceptedResponse, status_code=202)
async def post_session_message(
    session_id: str,
    payload: MessageRequest,
    service: MessageService = Depends(get_message_service),
    container: AppContainer = Depends(get_container),
) -> MessageAcceptedResponse:
    codex_options = await _validate_codex_options(
        payload.codex_options.to_domain()
        if payload.codex_options is not None
        else None,
        container=container,
    )
    try:
        job = await run_in_threadpool(
            service.submit_message,
            payload.message,
            session_id=session_id,
            workspace_path=payload.workspace_path,
            codex_options=codex_options,
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
        turn_summaries=service.list_turn_summaries(session_id),
        jobs_by_id=_jobs_by_id_for_messages(service, messages),
        run_configurations_by_id=_run_configurations_by_id_for_session(service, session_id),
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
        turn_summaries=service.list_turn_summaries(session_id),
        jobs_by_id=_jobs_by_id_for_messages(service, messages),
        run_configurations_by_id=_run_configurations_by_id_for_session(service, session_id),
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
        turn_summaries=service.list_turn_summaries(session_id),
        jobs_by_id=_jobs_by_id_for_messages(service, messages),
        run_configurations_by_id=_run_configurations_by_id_for_session(service, session_id),
    )


@router.put("/sessions/{session_id}/turn-summaries", response_model=SessionDetailResponse)
async def update_turn_summaries(
    session_id: str,
    payload: TurnSummaryConfigRequest,
    service: MessageService = Depends(get_message_service),
) -> SessionDetailResponse:
    try:
        session = await run_in_threadpool(
            service.update_turn_summaries,
            session_id=session_id,
            enabled=payload.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    messages = service.list_messages(session_id)
    return SessionDetailResponse.from_domain(
        session,
        messages=messages,
        turn_summaries=service.list_turn_summaries(session_id),
        jobs_by_id=_jobs_by_id_for_messages(service, messages),
        run_configurations_by_id=_run_configurations_by_id_for_session(service, session_id),
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
        turn_summaries=service.list_turn_summaries(session_id),
        jobs_by_id=_jobs_by_id_for_messages(service, messages),
        run_configurations_by_id=_run_configurations_by_id_for_session(service, session_id),
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


@router.get("/jobs/{job_id}/attachments/{attachment_index}")
async def get_job_attachment(
    job_id: str,
    attachment_index: int,
    service: MessageService = Depends(get_message_service),
) -> FileResponse:
    attachment = await run_in_threadpool(
        service.get_job_image_attachment_file,
        job_id,
        attachment_index,
    )
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    return FileResponse(
        attachment.path,
        media_type=attachment.media_type,
    )


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
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
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


def _app_update_response(
    result: AppUpdateResult,
    *,
    apk_url: str | None = None,
) -> AppUpdateResponse:
    return AppUpdateResponse(
        source_app=result.source_app,
        display_name=result.display_name,
        platform=result.platform,
        current_version=result.current_version,
        current_build=result.current_build,
        latest_version=result.latest_version,
        latest_build=result.latest_build,
        release_tag=result.release_tag,
        release_url=result.release_url,
        apk_url=apk_url if apk_url is not None else result.apk_url,
        apk_asset_name=result.apk_asset_name,
        sha256=result.sha256,
        size_bytes=result.size_bytes,
        release_notes=result.release_notes,
        required=result.required,
        available=result.available,
    )


def _apk_download_headers(
    file_name: str,
    *,
    content_length: int | None,
) -> dict[str, str]:
    headers = {
        "Content-Disposition": f'attachment; filename="{file_name}"',
        "Cache-Control": "private, max-age=300",
    }
    if content_length is not None:
        headers["Content-Length"] = str(content_length)
    return headers


def _prime_apk_stream(iterator: Iterator[bytes]) -> list[bytes]:
    chunks: list[bytes] = []
    sample = b""
    for chunk in iterator:
        if not chunk:
            continue
        chunks.append(chunk)
        sample += chunk
        if len(sample) >= 4:
            break
    if not sample.startswith(b"PK\x03\x04"):
        raise GitHubReleaseError("Downloaded asset is not an APK archive.")
    return chunks


def _stream_apk_body(
    initial_chunks: list[bytes],
    iterator: Iterator[bytes],
    stream,
) -> Iterator[bytes]:
    try:
        yield from initial_chunks
        yield from iterator
    finally:
        stream.close()


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
    suffix = _safe_upload_suffix(upload, default_filename=default_filename)
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


def _safe_upload_suffix(upload: UploadFile, *, default_filename: str) -> str:
    suffix = Path(upload.filename or "").suffix or Path(default_filename).suffix
    normalized_content_type = (
        (upload.content_type or "").split(";", maxsplit=1)[0].strip().lower()
    )
    if (not suffix or suffix.lower() == ".bin") and normalized_content_type:
        image_suffix = _IMAGE_CONTENT_TYPE_SUFFIXES.get(normalized_content_type)
        if image_suffix is not None:
            return image_suffix
    return suffix or ".bin"


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


def _parse_codex_options_json(raw_json: str | None):
    if raw_json is None or not raw_json.strip():
        return None
    try:
        return CodexRunOptionsRequest.model_validate_json(raw_json).to_domain()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid codex_options_json: {exc}") from exc


async def _parse_and_validate_codex_options_json(
    raw_json: str | None,
    *,
    container: AppContainer,
):
    codex_options = _parse_codex_options_json(raw_json)
    return await _validate_codex_options(
        codex_options,
        container=container,
    )


async def _validate_codex_options(
    codex_options,
    *,
    container: AppContainer,
):
    if codex_options is None or not codex_options.mcp_server_ids:
        return codex_options

    selection_snapshot = await run_in_threadpool(
        inspect_codex_mcp_server_selection,
        container.settings.codex_command,
        repo_root=Path(container.settings.codex_workdir).resolve(),
        projects_root=container.settings.projects_root,
    )
    if selection_snapshot.error is not None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Cannot validate requested MCP server selections because "
                f"`codex mcp list` failed. {selection_snapshot.error}"
            ),
        )

    issues = validate_requested_mcp_server_ids(
        selection_snapshot,
        codex_options.mcp_server_ids,
    )
    if issues:
        joined = "; ".join(
            f"`{issue.server_id}` {issue.reason}"
            for issue in issues
        )
        raise HTTPException(
            status_code=422,
            detail=f"Rejected MCP server selections: {joined}",
        )
    return codex_options
