from __future__ import annotations

import base64
import binascii
import json
import os
import re
import secrets
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Thread
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    Header,
)
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
    BackendDrainRequest,
    BackendDrainStatusResponse,
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
    DevPipelineBackfillRequest,
    DevPipelineClaimRequest,
    DevPipelineHandoffDraftRequest,
    DevPipelineHandoffRequest,
    DevPipelineMaterializeRequest,
    DevPipelineMergeApplyRequest,
    DevPipelineMergeRequest,
    DevPipelineProdUpdateRequest,
    DevPipelineProdUpdateAcknowledgeRequest,
    DevPipelineProdUpdateForceRequest,
    DevPipelineProdUpdatePrepareRequest,
    DevPipelinePromotionAdvanceRequest,
    DevPipelinePromotionRequest,
    DevPipelineReleaseChannelValidationRequest,
    DevPipelineResponse,
    DevPipelineSessionBindRequest,
    DevPipelineStageLifecycleRequest,
    DevPipelineStageRegisterRequest,
    DevPipelineStageRunControlRequest,
    DevPipelineStageRunRequest,
    DevPipelineStageSessionRequest,
    AssetDepotDeleteResponse,
    AssetDepotFromJobAttachmentRequest,
    AssetDepotItemResponse,
    AssetDepotListResponse,
    AppUpdateRegistryItemResponse,
    AppUpdateRegistryResponse,
    AppUpdateResponse,
    InstallableAppRegistrationRequest,
    InstallableAppResponse,
    InstallableAppsResponse,
    FeedbackBatchStartRequest,
    FeedbackBatchStatusResponse,
    FeedbackQuickAskAcceptedResponse,
    FeedbackQuickAskRequest,
    FeedbackQuickAskResponse,
    FeedbackQueueItemRequest,
    FeedbackQueueItemResponse,
    FeedbackQueueStartRequest,
    FeedbackWorkflowPresetResponse,
    FeedbackWorkflowPresetsResponse,
    GenerateSessionTitleRequest,
    HealthResponse,
    ImageMessageAcceptedResponse,
    JobResponse,
    MessageAcceptedResponse,
    MessageRecoveryRequest,
    MessageRequest,
    PersistenceIntegrityIssueResponse,
    PersistenceIntegrityResponse,
    DomainFactoryCompletionEvidenceResponse,
    DomainFactoryImplementationResponse,
    DomainFactoryIntakeRequest,
    DomainFactoryIntakeResponse,
    DomainFactoryReleaseEvidenceValidationRequest,
    DomainFactoryReleaseEvidenceValidationResponse,
    DomainFactoryStartRequest,
    DomainFactoryStartResponse,
    ProjectFactoryDraftRequest,
    ProjectFactoryDraftAssetLinkRequest,
    ProjectFactoryDraftAssetResponse,
    ProjectFactoryDraftAssetsResponse,
    ProjectFactoryDraftResponse,
    ProjectFactoryDraftsResponse,
    ProjectFactoryDoctorResponse,
    ProjectFactoryDryRunResponse,
    ProjectFactoryGuidedIntakeAnswerRequest,
    ProjectFactoryGuidedIntakeResponse,
    ProjectFactoryInitJobResponse,
    ProjectFactoryInitStartRequest,
    ProjectFactoryJobResponse,
    ProjectFactoryJobsResponse,
    ProjectFactoryOptionsResponse,
    ProjectFactoryReferenceAssetDeleteResponse,
    ProjectFactoryReferenceAssetResponse,
    ProjectFactoryReferenceAssetsResponse,
    RenameSessionRequest,
    ServerCapabilitiesResponse,
    SessionDetailResponse,
    SessionSummaryResponse,
    SpeechRequest,
    SddActivityResponse,
    SddBridgeCaptureIntakeRequest,
    SddBridgeCaptureIntakeResponse,
    SddCodexJobApplyResponse,
    SddCodexJobReviewResponse,
    SddCodexJobResponse,
    SddCodexJobRetryResponse,
    SddDiagramResponse,
    SddDoctorResponse,
    SddFileResponse,
    SddRenderedDiagramExportRequest,
    SddRenderedDiagramExportResponse,
    SddMediaCleanupRequest,
    SddMediaDeleteRequest,
    SddMediaLifecycleResponse,
    SddMediaUploadResponse,
    SddPlanNodeResponse,
    SddProjectDiagramsResponse,
    SddProjectLazySummaryResponse,
    SddProjectResponse,
    SddProjectSpecResponse,
    SddProjectsResponse,
    SddProjectSummaryResponse,
    SddSpecApplyResponse,
    SddSpecCreationDryRunResponse,
    SddSpecDryRunRequest,
    SddSpecEditApplyResponse,
    SddSpecEditDryRunResponse,
    SddSpecResponse,
    SddSpecTreeResponse,
    SddTaskNodeResponse,
    SddWorkbenchKanbanHistoryItemResponse,
    SddWorkbenchKanbanHistoryResponse,
    SddWorkbenchKanbanResponse,
    SddWorkbenchKanbanScopesResponse,
    SddWorkbenchViewResponse,
    TurnSummaryConfigRequest,
    WebPreviewDeployRequest,
    WebPreviewInviteCreateRequest,
    WebPreviewInviteListResponse,
    WebPreviewInviteResendRequest,
    WebPreviewInviteResponse,
    WebPreviewLifecycleRequest,
    WebPreviewListResponse,
    WebPreviewPlanRequest,
    WebPreviewResponse,
    WorkspaceResponse,
)
from backend.app.application.services.asset_depot_service import AssetDepotError
from backend.app.application.services.project_factory_manifest_service import (
    ProjectFactoryManifestInput,
)
from backend.app.application.services.project_factory_service import (
    ProjectFactoryGenerationConflictError,
)
from backend.app.application.services.project_factory_reference_asset_service import (
    ProjectFactoryReferenceAssetError,
)
from backend.app.application.services.web_preview_deploy_service import (
    WebPreviewDeployInput,
    WebPreviewError,
    WebPreviewLifecycleInput,
    WebPreviewPlanInput,
)
from backend.app.application.services.web_preview_invite_service import (
    WebPreviewInviteCreateInput,
    WebPreviewInviteError,
)
from backend.app.application.services.app_update_service import (
    AppDisabledError,
    AppUpdateConfig,
    AppUpdateAssetNotFoundError,
    AppUpdateResult,
    GitHubReleaseError,
    UnknownAppError,
)
from backend.app.application.services.dev_pipeline_service import DevPipelineError
from backend.app.application.services.message_service import (
    AttachmentInput,
    DocumentProcessingError,
    MaintenanceModeError,
    MessageService,
    UnsupportedDocumentError,
)
from backend.app.application.services.sdd_project_service import (
    SddDiagram,
    SddFile,
    SddPlanNode,
    SddProject,
    SddProjectError,
    SddProjectSummary,
    SddRenderedDiagramExport,
    SddSpec,
    SddSpecNotFoundError,
    SddSpecTree,
    SddTaskNode,
    SddWorkspacePathError,
)
from backend.app.application.services.sdd_media_upload_service import (
    SddMediaUploadService,
)
from backend.app.application.services.sdd_bridge_capture_service import (
    SddBridgeCaptureService,
)
from backend.app.application.services.sdd_spec_creation_service import (
    SddSpecCreationService,
)
from backend.app.application.services.sdd_spec_edit_service import SddSpecEditService
from backend.app.application.services.sdd_spec_target_service import (
    SpecIntakeMediaItemInput,
    SpecIntakeValidationInput,
    SpecTargetInput,
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

_TRANSPARENT_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/"
    "x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)

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
_BACKEND_FEATURES = {
    "project_factory": True,
    "domain_factory": True,
    "sdd": True,
    "feedback_bridge": True,
    "app_updates": True,
}


def get_container() -> AppContainer:
    raise RuntimeError("Container dependency was not configured.")


def get_message_service(
    container: AppContainer = Depends(get_container),
) -> MessageService:
    return container.message_service


@lru_cache(maxsize=1)
def _backend_commit() -> str | None:
    env_sha = os.environ.get("GITHUB_SHA") or os.environ.get("SOURCE_VERSION")
    if env_sha:
        return env_sha[:12]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    commit = result.stdout.strip()
    return commit or None


@router.get("/health", response_model=HealthResponse)
async def healthcheck(
    container: AppContainer = Depends(get_container),
) -> HealthResponse:
    tailscale = detect_tailscale_info(
        container.settings.tailscale_socket,
        api_port=container.settings.api_port,
    )
    audio_status = container.audio_transcriber.status()
    speech_status = container.speech_synthesizer.status()
    persistence_issue = container.persistence_startup_issue
    return HealthResponse(
        server_name=container.settings.server_name,
        backend_version="bridge-local",
        backend_commit=_backend_commit(),
        features=_BACKEND_FEATURES,
        backend_mode=container.settings.effective_backend_mode,
        projects_root=container.settings.projects_root,
        persistence_available=container.message_service.is_persistence_available(),
        persistence_error_code=persistence_issue.code if persistence_issue else None,
        persistence_error_detail=persistence_issue.detail
        if persistence_issue
        else None,
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
        preferred_client_url=tailscale.preferred_client_url,
        public_base_urls=tailscale.public_base_urls,
        environment_identity=container.dev_pipeline_service.identity_payload(),
    )


def _dev_pipeline_response(data: dict[str, Any] | list[Any]) -> DevPipelineResponse:
    return DevPipelineResponse(
        kind="codex.devPipelineResponse",
        version=1,
        data=data,
    )


def _raise_dev_pipeline_error(exc: DevPipelineError) -> None:
    status_code = 403 if exc.code.endswith("_environment_required") else 409
    raise HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.message},
    )


def _project_stage_run(container: AppContainer, run: dict[str, Any]) -> dict[str, Any]:
    projection: dict[str, Any] = {}
    job_id = run.get("job_id")
    job = container.message_service.get_job(str(job_id)) if job_id else None
    if run.get("status") in {"pause_requested", "paused", "resume_requested"}:
        projection["status"] = run["status"]
        projection["blocker_reason"] = run.get("blocker_reason")
    elif job is None:
        if job_id:
            projection["status"] = "blocked"
            projection["blocker_reason"] = "stage_run_job_missing"
        else:
            projection.setdefault("status", run.get("status") or "planned")
            projection.setdefault("blocker_reason", "stage_run_has_no_job")
    else:
        status_map = {
            "pending": "queued",
            "running": "running",
            "completed": "completed",
            "failed": "failed",
            "cancelled": "cancelled",
        }
        projection["status"] = status_map.get(str(job.status), str(job.status))
        projection["job_id"] = job.id
        projection["agent_run_id"] = job.run_id
        projection["started_at"] = job.created_at.isoformat()
        projection["finished_at"] = (
            job.completed_at.isoformat() if job.completed_at else None
        )
    evidence = dict(run.get("evidence") or {})
    evidence["changed_files"] = _stage_run_changed_files(run)
    messages = container.message_service.list_messages(str(run["session_id"]))
    run_messages = [
        message for message in messages if message.run_id == run.get("agent_run_id")
    ]
    message_text = "\n".join(message.content for message in run_messages)
    evidence["tests_declared"] = _stage_run_test_lines(message_text)
    evidence["tests_executed"] = _stage_run_test_lines(message_text, executed=True)
    reviewer_messages = [
        message
        for message in run_messages
        if _enum_value(message.agent_id) == "reviewer" and message.content.strip()
    ]
    reviewer_evidence = dict(evidence.get("reviewer") or {})
    if reviewer_messages:
        latest = reviewer_messages[-1].content.strip()
        contract = _stage_run_reviewer_contract(latest)
        reviewer_evidence.update(contract)
        if contract["status"] == "complete":
            evidence["final_summary"] = _stage_run_final_summary(
                run=run,
                reviewer=contract,
                changed_files=evidence["changed_files"],
                tests=evidence["tests_executed"] or evidence["tests_declared"],
            )
            projection.setdefault("status", "completed")
            projection.setdefault("finished_at", _utc_now_iso())
        elif contract["status"] == "continue":
            projection.setdefault("status", run.get("status") or "running")
        else:
            evidence.setdefault("blockers", []).append("reviewer_contract_invalid")
    evidence["reviewer"] = reviewer_evidence
    assistant_messages = [
        message
        for message in run_messages
        if _enum_value(message.role) == "assistant" and message.content.strip()
    ]
    if assistant_messages:
        evidence["final_summary"] = assistant_messages[-1].content.strip()[:2000]
    projection["evidence"] = evidence
    if projection:
        try:
            return container.dev_pipeline_service.update_stage_run_projection(
                run_id=str(run["id"]),
                projection=projection,
            )
        except DevPipelineError:
            return {**run, **projection}
    return run


def _stage_run_reviewer_contract(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {
            "status": "invalid_contract",
            "raw": text[:1000],
            "blocker": "reviewer_response_must_be_json",
        }
    if not isinstance(parsed, dict):
        return {
            "status": "invalid_contract",
            "raw": text[:1000],
            "blocker": "reviewer_response_must_be_json_object",
        }
    status = str(parsed.get("status") or "").strip().lower()
    if status == "complete":
        summary = str(parsed.get("summary") or "").strip()
        if not summary:
            return {
                "status": "invalid_contract",
                "payload": parsed,
                "blocker": "reviewer_complete_requires_summary",
            }
        return {"status": "complete", "completion": summary, "payload": parsed}
    if status == "continue":
        prompt = str(parsed.get("prompt") or parsed.get("message") or "").strip()
        if not prompt:
            return {
                "status": "invalid_contract",
                "payload": parsed,
                "blocker": "reviewer_continue_requires_prompt",
            }
        return {"status": "continue", "continue": prompt, "payload": parsed}
    return {
        "status": "invalid_contract",
        "payload": parsed,
        "blocker": "reviewer_status_must_be_complete_or_continue",
    }


def _stage_run_final_summary(
    *,
    run: dict[str, Any],
    reviewer: dict[str, Any],
    changed_files: list[str],
    tests: list[str],
) -> str:
    files = "\n".join(f"- {item}" for item in changed_files) or "- Not reported"
    tests_text = "\n".join(f"- {item}" for item in tests) or "- Not reported"
    return "\n".join(
        [
            "Termine.",
            "",
            "Que cambio",
            reviewer.get("completion") or "Reviewer marked the stage complete.",
            "",
            "Archivos tocados",
            files,
            "",
            "Tests ejecutados",
            tests_text,
            "",
            "Riesgos",
            "- Review generated from DEV stage evidence; operator should verify.",
            "",
            "Que deberias probar",
            f"- Stage {run.get('stage_id')} on {run.get('branch')}",
            "",
            "Resultado final",
            "Reviewer JSON contract returned complete.",
        ]
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _stage_run_changed_files(run: dict[str, Any]) -> list[str]:
    stage = run.get("stage") or {}
    worktree_path = run.get("worktree_path") or stage.get("worktree_path")
    if not worktree_path:
        return []
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=worktree_path,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ][:200]


def _stage_run_test_lines(text: str, *, executed: bool = False) -> list[str]:
    patterns = ("pytest", "ruff", "flutter test", "flutter analyze")
    lines = []
    for line in text.splitlines():
        lowered = line.lower()
        if any(pattern in lowered for pattern in patterns):
            if not executed or any(
                marker in lowered for marker in ("pass", "passed", "ran", "executed")
            ):
                lines.append(line.strip())
    return lines[:50]


@router.get("/dev-pipeline", response_model=DevPipelineResponse)
async def get_dev_pipeline_snapshot(
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        snapshot = container.dev_pipeline_service.snapshot()
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(snapshot)


@router.get("/dev-pipeline/projection", response_model=DevPipelineResponse)
async def get_dev_pipeline_projection(
    stage_id: str | None = Query(default=None, max_length=80),
    spec_id: str | None = Query(default=None, max_length=160),
    handoff_id: str | None = Query(default=None, max_length=120),
    status: str | None = Query(default=None, max_length=80),
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        projection = container.dev_pipeline_service.pipeline_projection(
            stage_id=stage_id,
            spec_id=spec_id,
            handoff_id=handoff_id,
            status=status,
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(projection)


@router.get("/dev-pipeline/identity", response_model=DevPipelineResponse)
async def get_dev_pipeline_identity(
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    return _dev_pipeline_response(container.dev_pipeline_service.identity_payload())


@router.get("/dev-pipeline/permissions", response_model=DevPipelineResponse)
async def get_dev_pipeline_permissions(
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    return _dev_pipeline_response(container.dev_pipeline_service.permission_matrix())


@router.post("/dev-pipeline/handoffs/draft", response_model=DevPipelineResponse)
async def draft_dev_handoff(
    payload: DevPipelineHandoffDraftRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    session = None
    messages: list[dict[str, Any]] = []
    if payload.session_id:
        session = container.message_service.get_session(payload.session_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "unknown_session",
                    "message": f"Session {payload.session_id} was not found.",
                },
            )
        messages = [
            {
                "id": message.id,
                "role": str(message.role),
                "agent_label": message.agent_label,
                "content": message.content,
                "created_at": message.created_at.isoformat(),
            }
            for message in container.message_service.list_messages(session.id)
        ]
    try:
        draft = container.dev_pipeline_service.draft_handoff(
            session_id=session.id if session else payload.session_id,
            session_title=session.title if session else None,
            workspace_path=session.workspace_path if session else None,
            messages=messages,
            title=payload.title,
            problem=payload.problem,
            context=payload.context,
            acceptance_criteria=payload.acceptance_criteria,
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(draft)


@router.post("/dev-pipeline/handoffs", response_model=DevPipelineResponse)
async def enqueue_dev_handoff(
    payload: DevPipelineHandoffRequest,
    x_idempotency_key: str | None = Header(default=None),
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    selected_context = dict(payload.selected_context)
    selected_context.setdefault(
        "created_from_session_id", payload.created_from_session_id
    )
    selected_context.setdefault("created_by_action", payload.created_by_action)
    try:
        handoff = container.dev_pipeline_service.enqueue_handoff(
            payload.model_dump(),
            idempotency_key=x_idempotency_key or payload.idempotency_key,
            selected_context=selected_context,
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(handoff)


@router.post("/dev-pipeline/backlog/claim", response_model=DevPipelineResponse)
async def claim_dev_backlog(
    payload: DevPipelineClaimRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        item = container.dev_pipeline_service.claim_backlog_item(
            worker_id=payload.worker_id,
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(item)


@router.post(
    "/dev-pipeline/backlog/{handoff_id}/materialize",
    response_model=DevPipelineResponse,
)
async def materialize_dev_backlog(
    handoff_id: str,
    payload: DevPipelineMaterializeRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        item = container.dev_pipeline_service.materialize_backlog_item(
            handoff_id=handoff_id,
            worker_id=payload.worker_id,
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(item)


@router.post("/dev-pipeline/backfill/stages", response_model=DevPipelineResponse)
async def dry_run_dev_stage_backfill(
    payload: DevPipelineBackfillRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        result = container.dev_pipeline_service.backfill_stage_candidates(
            dry_run=payload.dry_run,
            spec_ids=payload.spec_ids,
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(result)


@router.post("/dev-pipeline/stages", response_model=DevPipelineResponse)
async def register_dev_stage(
    payload: DevPipelineStageRegisterRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        stage = container.dev_pipeline_service.register_stage(
            spec_id=payload.spec_id,
            stage_id=payload.stage_id,
            branch=payload.branch,
            worktree_path=payload.worktree_path,
            backend_url=payload.backend_url,
            owner=payload.owner,
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(stage)


@router.post("/dev-pipeline/sessions/bind", response_model=DevPipelineResponse)
async def bind_dev_stage_session(
    payload: DevPipelineSessionBindRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        binding = container.dev_pipeline_service.bind_session(
            session_id=payload.session_id,
            stage_id=payload.stage_id,
            workspace_path=payload.workspace_path,
            branch=payload.branch,
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(binding)


@router.post(
    "/dev-pipeline/stages/{stage_id}/sessions",
    response_model=DevPipelineResponse,
)
async def bind_or_create_dev_stage_session(
    stage_id: str,
    payload: DevPipelineStageSessionRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        stage = container.dev_pipeline_service.get_stage(stage_id)
        if payload.session_id:
            session = container.message_service.get_session(payload.session_id)
            if session is None:
                raise DevPipelineError(
                    "unknown_session", f"Session {payload.session_id} was not found."
                )
            session_id = session.id
        else:
            session = container.message_service.create_session(
                title=payload.title or f"{stage_id} DEV Stage",
                workspace_path=stage["worktree_path"],
            )
            session_id = session.id
        container.message_service.update_auto_mode(
            session_id=session_id,
            enabled=True,
            max_turns=1,
            reviewer_prompt="Return the next implementation prompt for the generator.",
        )
        binding = container.dev_pipeline_service.bind_stage_session(
            session_id=session_id,
            stage_id=stage_id,
        )
    except (DevPipelineError, RuntimeError, ValueError) as exc:
        if isinstance(exc, DevPipelineError):
            _raise_dev_pipeline_error(exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _dev_pipeline_response(binding)


@router.get(
    "/dev-pipeline/sessions/{session_id}/binding",
    response_model=DevPipelineResponse,
)
async def get_dev_stage_session_binding(
    session_id: str,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        binding = container.dev_pipeline_service.get_stage_session_binding(
            session_id=session_id,
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(binding)


@router.post(
    "/dev-pipeline/stages/{stage_id}/runs/start",
    response_model=DevPipelineResponse,
)
async def start_dev_stage_run(
    stage_id: str,
    payload: DevPipelineStageRunRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        prepared = container.dev_pipeline_service.prepare_stage_run_start(
            stage_id=stage_id,
            session_id=payload.session_id,
            backend_url=container.settings.api_base_url,
            initial_prompt=payload.initial_prompt,
        )
        container.message_service.update_auto_mode(
            session_id=payload.session_id,
            enabled=True,
            max_turns=1,
            reviewer_prompt="Return the next implementation prompt for the generator.",
        )
        job = container.message_service.submit_message(
            prepared["prompt"],
            session_id=payload.session_id,
            workspace_path=prepared["stage"]["worktree_path"],
        )
        run = container.dev_pipeline_service.record_stage_run_start(
            stage_id=stage_id,
            session_id=payload.session_id,
            requested_by=payload.requested_by,
            prompt=prepared["prompt"],
            job_id=job.id,
            agent_run_id=job.run_id,
        )
    except (DevPipelineError, RuntimeError, ValueError) as exc:
        if isinstance(exc, DevPipelineError):
            _raise_dev_pipeline_error(exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    projected = _project_stage_run(container, run)
    return _dev_pipeline_response(projected)


@router.get(
    "/dev-pipeline/stage-runs/{run_id}",
    response_model=DevPipelineResponse,
)
async def get_dev_stage_run(
    run_id: str,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        run = container.dev_pipeline_service.stage_run_status(run_id=run_id)
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(_project_stage_run(container, run))


@router.post(
    "/dev-pipeline/stage-runs/{run_id}/cancel",
    response_model=DevPipelineResponse,
)
async def cancel_dev_stage_run(
    run_id: str,
    payload: DevPipelineStageRunControlRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        run = container.dev_pipeline_service.stage_run_status(run_id=run_id)
        if run.get("job_id"):
            container.message_service.cancel_job(str(run["job_id"]))
        run = container.dev_pipeline_service.control_stage_run(
            run_id=run_id,
            action="cancel",
            requested_by=payload.requested_by,
        )
    except (DevPipelineError, RuntimeError, ValueError) as exc:
        if isinstance(exc, DevPipelineError):
            _raise_dev_pipeline_error(exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _dev_pipeline_response(_project_stage_run(container, run))


@router.post(
    "/dev-pipeline/stage-runs/{run_id}/retry",
    response_model=DevPipelineResponse,
)
async def retry_dev_stage_run(
    run_id: str,
    payload: DevPipelineStageRunControlRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        run = container.dev_pipeline_service.stage_run_status(run_id=run_id)
        retry_job = None
        if run.get("job_id"):
            retry_job = container.message_service.retry_job(str(run["job_id"]))
        run = container.dev_pipeline_service.control_stage_run(
            run_id=run_id,
            action="retry",
            requested_by=payload.requested_by,
        )
        if retry_job is not None:
            run = container.dev_pipeline_service.update_stage_run_projection(
                run_id=run_id,
                projection={
                    "job_id": retry_job.id,
                    "agent_run_id": retry_job.run_id,
                    "status": "queued",
                    "started_at": retry_job.created_at.isoformat(),
                    "finished_at": None,
                },
            )
    except (DevPipelineError, RuntimeError, ValueError) as exc:
        if isinstance(exc, DevPipelineError):
            _raise_dev_pipeline_error(exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _dev_pipeline_response(_project_stage_run(container, run))


@router.post(
    "/dev-pipeline/stage-runs/{run_id}/pause",
    response_model=DevPipelineResponse,
)
async def pause_dev_stage_run(
    run_id: str,
    payload: DevPipelineStageRunControlRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        run = container.dev_pipeline_service.control_stage_run(
            run_id=run_id,
            action="pause",
            requested_by=payload.requested_by,
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(_project_stage_run(container, run))


@router.post(
    "/dev-pipeline/stage-runs/{run_id}/resume",
    response_model=DevPipelineResponse,
)
async def resume_dev_stage_run(
    run_id: str,
    payload: DevPipelineStageRunControlRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        run = container.dev_pipeline_service.control_stage_run(
            run_id=run_id,
            action="resume",
            requested_by=payload.requested_by,
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(_project_stage_run(container, run))


@router.post(
    "/dev-pipeline/stages/{stage_id}/lifecycle", response_model=DevPipelineResponse
)
async def run_dev_stage_lifecycle(
    stage_id: str,
    payload: DevPipelineStageLifecycleRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        result = container.dev_pipeline_service.stage_lifecycle(
            stage_id=stage_id,
            action=payload.action,
            apply=payload.apply,
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(result)


@router.post("/dev-pipeline/merge-queue", response_model=DevPipelineResponse)
async def queue_dev_stage_merge(
    payload: DevPipelineMergeRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        item = container.dev_pipeline_service.queue_merge(
            stage_id=payload.stage_id,
            requested_by=payload.requested_by,
            approved=payload.approved,
            evidence_validated=payload.evidence_validated,
            validation_passed=payload.validation_passed,
            validation_log=payload.validation_log,
            tests_executed=payload.tests_executed,
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(item)


@router.get("/dev-pipeline/merge-queue/{merge_id}", response_model=DevPipelineResponse)
async def get_dev_stage_merge_status(
    merge_id: str,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        item = container.dev_pipeline_service.merge_status(merge_id=merge_id)
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(item)


@router.post(
    "/dev-pipeline/merge-queue/{merge_id}/apply",
    response_model=DevPipelineResponse,
)
async def apply_dev_stage_merge(
    merge_id: str,
    payload: DevPipelineMergeApplyRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        item = container.dev_pipeline_service.apply_merge(
            merge_id=merge_id,
            requested_by=payload.requested_by,
            evidence_validated=payload.evidence_validated,
            validation_passed=payload.validation_passed,
            validation_log=payload.validation_log,
            tests_executed=payload.tests_executed,
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(item)


@router.post("/dev-pipeline/promotions", response_model=DevPipelineResponse)
async def request_dev_pipeline_promotion(
    payload: DevPipelinePromotionRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        item = container.dev_pipeline_service.request_promotion(
            requested_by=payload.requested_by,
            target=payload.target,
            release_tag=payload.release_tag,
            user_approved=payload.user_approved,
            dry_run=payload.dry_run,
            drain_status=container.message_service.backend_drain_status(),
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(item)


@router.get("/dev-pipeline/promotions/{promotion_id}", response_model=DevPipelineResponse)
async def get_dev_pipeline_promotion(
    promotion_id: str,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        item = container.dev_pipeline_service.promotion_status(
            promotion_id=promotion_id,
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(item)


@router.post(
    "/dev-pipeline/promotions/{promotion_id}/advance",
    response_model=DevPipelineResponse,
)
async def advance_dev_pipeline_promotion(
    promotion_id: str,
    payload: DevPipelinePromotionAdvanceRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        item = container.dev_pipeline_service.advance_promotion(
            promotion_id=promotion_id,
            requested_by=payload.requested_by,
            user_approved=payload.user_approved,
            dry_run=payload.dry_run,
            drain_status=container.message_service.backend_drain_status(),
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(item)


@router.post("/dev-pipeline/prod-update/status", response_model=DevPipelineResponse)
async def get_prod_update_gate_status(
    payload: DevPipelineProdUpdateRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        item = container.dev_pipeline_service.prod_update_status(
            prepared_update_id=payload.prepared_update_id,
            update_version=payload.update_version,
            force_requested=payload.force_requested,
            acknowledged=payload.acknowledged,
            requested_by=payload.requested_by,
            strong_confirmation=payload.strong_confirmation,
            drain_status=container.message_service.backend_drain_status(),
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(item)


@router.get("/dev-pipeline/prod-update/status", response_model=DevPipelineResponse)
async def read_prod_update_gate_status(
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        item = container.dev_pipeline_service.prod_update_status(
            prepared_update_id=None,
            drain_status=container.message_service.backend_drain_status(),
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(item)


@router.post("/dev-pipeline/prod-update/prepare", response_model=DevPipelineResponse)
async def prepare_prod_update_gate(
    payload: DevPipelineProdUpdatePrepareRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        item = container.dev_pipeline_service.prod_update_status(
            prepared_update_id=payload.prepared_update_id,
            update_version=payload.update_version,
            requested_by=payload.requested_by,
            drain_status=container.message_service.backend_drain_status(),
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(item)


@router.post(
    "/dev-pipeline/prod-update/acknowledge",
    response_model=DevPipelineResponse,
)
async def acknowledge_prod_update_gate(
    payload: DevPipelineProdUpdateAcknowledgeRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        item = container.dev_pipeline_service.prod_update_status(
            prepared_update_id=None,
            acknowledged=True,
            requested_by=payload.acknowledged_by,
            drain_status=container.message_service.backend_drain_status(),
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(item)


@router.post("/dev-pipeline/prod-update/force", response_model=DevPipelineResponse)
async def force_prod_update_gate(
    payload: DevPipelineProdUpdateForceRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        item = container.dev_pipeline_service.prod_update_status(
            prepared_update_id=None,
            force_requested=True,
            requested_by=payload.requested_by,
            strong_confirmation=payload.strong_confirmation,
            drain_status=container.message_service.backend_drain_status(),
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(item)


@router.post(
    "/dev-pipeline/release-channels/validate", response_model=DevPipelineResponse
)
async def validate_dev_pipeline_release_channels(
    payload: DevPipelineReleaseChannelValidationRequest,
    container: AppContainer = Depends(get_container),
) -> DevPipelineResponse:
    try:
        result = container.dev_pipeline_service.validate_release_channels(
            payload.configs,
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
    return _dev_pipeline_response(result)


@router.get("/capabilities", response_model=ServerCapabilitiesResponse)
async def capabilities(
    container: AppContainer = Depends(get_container),
) -> ServerCapabilitiesResponse:
    audio_status = container.audio_transcriber.status()
    speech_status = container.speech_synthesizer.status()
    service = container.message_service
    tailscale = detect_tailscale_info(
        container.settings.tailscale_socket,
        api_port=container.settings.api_port,
    )
    return ServerCapabilitiesResponse(
        supports_audio_input=audio_status.ready,
        supports_speech_output=speech_status.ready,
        supports_image_input=service.supports_image_input(),
        supports_document_input=True,
        supports_attachment_batch=True,
        supports_job_cancellation=service.supports_job_cancellation(),
        supports_job_retry=service.supports_job_retry(),
        supports_push_job_stream=True,
        supports_sdd=True,
        supports_project_factory=True,
        supports_domain_factory=True,
        backend_version="bridge-local",
        backend_commit=_backend_commit(),
        features=_BACKEND_FEATURES,
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
        preferred_client_url=tailscale.preferred_client_url,
        public_base_urls=tailscale.public_base_urls,
    )


@router.get("/assets", response_model=AssetDepotListResponse)
async def list_asset_depot_assets(
    limit: int = 100,
    container: AppContainer = Depends(get_container),
) -> AssetDepotListResponse:
    assets = await run_in_threadpool(
        container.asset_depot_service.list_assets,
        limit=limit,
    )
    return AssetDepotListResponse(
        assets=[AssetDepotItemResponse(**asset.to_payload()) for asset in assets],
    )


@router.post("/assets", response_model=AssetDepotItemResponse)
async def upload_asset_depot_asset(
    asset: UploadFile = File(...),
    source: str = Form(default="manual_upload"),
    container: AppContainer = Depends(get_container),
) -> AssetDepotItemResponse:
    temp_path = await _store_uploaded_file(
        asset,
        max_bytes=container.settings.asset_depot_max_upload_bytes,
        default_filename="asset-upload.bin",
        size_limit_label="Asset",
    )
    try:
        content = temp_path.read_bytes()
        created = await run_in_threadpool(
            container.asset_depot_service.create_asset,
            filename=asset.filename or temp_path.name,
            content_type=asset.content_type,
            content=content,
            source=source,
        )
    except AssetDepotError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        temp_path.unlink(missing_ok=True)
        await asset.close()
    return AssetDepotItemResponse(**created.to_payload())


@router.post("/assets/from-job-attachment", response_model=AssetDepotItemResponse)
async def create_asset_from_job_attachment(
    request: AssetDepotFromJobAttachmentRequest,
    container: AppContainer = Depends(get_container),
) -> AssetDepotItemResponse:
    attachment = await run_in_threadpool(
        container.message_service.get_job_image_attachment_file,
        request.job_id,
        request.attachment_index,
    )
    if attachment is None:
        raise HTTPException(status_code=404, detail="Job attachment not found.")
    try:
        created = await run_in_threadpool(
            container.asset_depot_service.import_file,
            path=attachment.path,
            filename=attachment.path.name,
            content_type=attachment.media_type,
            source=request.source,
        )
    except AssetDepotError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AssetDepotItemResponse(**created.to_payload())


@router.get("/assets/{asset_id}", response_model=AssetDepotItemResponse)
async def get_asset_depot_asset(
    asset_id: str,
    container: AppContainer = Depends(get_container),
) -> AssetDepotItemResponse:
    try:
        asset = await run_in_threadpool(
            container.asset_depot_service.get_asset,
            asset_id,
        )
    except AssetDepotError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found.")
    return AssetDepotItemResponse(**asset.to_payload())


@router.get("/assets/{asset_id}/download")
async def download_asset_depot_asset(
    asset_id: str,
    container: AppContainer = Depends(get_container),
) -> FileResponse:
    try:
        asset = await run_in_threadpool(
            container.asset_depot_service.get_asset,
            asset_id,
        )
    except AssetDepotError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found.")
    return FileResponse(
        container.asset_depot_service.asset_file_path(asset),
        media_type=asset.content_type,
        filename=asset.original_filename,
    )


@router.delete("/assets/{asset_id}", response_model=AssetDepotDeleteResponse)
async def delete_asset_depot_asset(
    asset_id: str,
    container: AppContainer = Depends(get_container),
) -> AssetDepotDeleteResponse:
    try:
        deleted = await run_in_threadpool(
            container.asset_depot_service.delete_asset,
            asset_id,
        )
    except AssetDepotError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Asset not found.")
    return AssetDepotDeleteResponse(asset_id=asset_id, deleted=True)


@router.get("/project-factory/options", response_model=ProjectFactoryOptionsResponse)
async def project_factory_options(
    container: AppContainer = Depends(get_container),
) -> ProjectFactoryOptionsResponse:
    return ProjectFactoryOptionsResponse(
        **container.project_factory_service.options(),
    )


@router.post("/project-factory/drafts", response_model=ProjectFactoryDraftResponse)
async def create_project_factory_draft(
    request: ProjectFactoryDraftRequest,
    container: AppContainer = Depends(get_container),
) -> ProjectFactoryDraftResponse:
    draft = await run_in_threadpool(
        container.project_factory_service.create_draft,
        _project_factory_manifest_input(request),
    )
    return ProjectFactoryDraftResponse(**draft.to_payload())


@router.get("/project-factory/drafts", response_model=ProjectFactoryDraftsResponse)
async def list_project_factory_drafts(
    limit: int = 50,
    container: AppContainer = Depends(get_container),
) -> ProjectFactoryDraftsResponse:
    drafts = await run_in_threadpool(
        container.project_factory_service.list_drafts,
        limit=limit,
    )
    return ProjectFactoryDraftsResponse(drafts=list(drafts))


@router.get(
    "/project-factory/drafts/{draft_id}",
    response_model=ProjectFactoryDraftResponse,
)
async def get_project_factory_draft(
    draft_id: str,
    container: AppContainer = Depends(get_container),
) -> ProjectFactoryDraftResponse:
    draft = await run_in_threadpool(
        container.project_factory_service.get_draft,
        draft_id,
    )
    if draft is None:
        raise HTTPException(status_code=404, detail="Project factory draft not found.")
    return ProjectFactoryDraftResponse(**draft.to_payload())


@router.post(
    "/project-factory/drafts/{draft_id}/dry-run",
    response_model=ProjectFactoryDryRunResponse,
)
async def project_factory_dry_run(
    draft_id: str,
    container: AppContainer = Depends(get_container),
) -> ProjectFactoryDryRunResponse:
    manifest_plan = await run_in_threadpool(
        container.project_factory_service.dry_run,
        draft_id,
    )
    if manifest_plan is None:
        raise HTTPException(status_code=404, detail="Project factory draft not found.")
    return ProjectFactoryDryRunResponse(**manifest_plan.to_payload())


@router.get(
    "/project-factory/drafts/{draft_id}/intake",
    response_model=ProjectFactoryGuidedIntakeResponse,
)
async def get_project_factory_guided_intake(
    draft_id: str,
    container: AppContainer = Depends(get_container),
) -> ProjectFactoryGuidedIntakeResponse:
    payload = await run_in_threadpool(
        container.project_factory_service.get_guided_intake,
        draft_id,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Project factory draft not found.")
    return ProjectFactoryGuidedIntakeResponse(**payload)


@router.post(
    "/project-factory/drafts/{draft_id}/intake/answers",
    response_model=ProjectFactoryGuidedIntakeResponse,
)
async def answer_project_factory_guided_intake(
    draft_id: str,
    request: ProjectFactoryGuidedIntakeAnswerRequest,
    container: AppContainer = Depends(get_container),
) -> ProjectFactoryGuidedIntakeResponse:
    payload = await run_in_threadpool(
        container.project_factory_service.answer_guided_intake_question,
        draft_id,
        question_id=request.question_id,
        value=request.value,
        source=request.source,
        confidence=request.confidence,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Project factory draft not found.")
    return ProjectFactoryGuidedIntakeResponse(**payload)


@router.post(
    "/project-factory/drafts/{draft_id}/intake/preview",
    response_model=ProjectFactoryGuidedIntakeResponse,
)
async def preview_project_factory_guided_intake_contract(
    draft_id: str,
    container: AppContainer = Depends(get_container),
) -> ProjectFactoryGuidedIntakeResponse:
    payload = await run_in_threadpool(
        container.project_factory_service.preview_guided_intake_contract,
        draft_id,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Project factory draft not found.")
    return ProjectFactoryGuidedIntakeResponse(**payload)


@router.post(
    "/project-factory/drafts/{draft_id}/intake/confirm",
    response_model=ProjectFactoryGuidedIntakeResponse,
)
async def confirm_project_factory_guided_intake_contract(
    draft_id: str,
    container: AppContainer = Depends(get_container),
) -> ProjectFactoryGuidedIntakeResponse:
    payload = await run_in_threadpool(
        container.project_factory_service.confirm_guided_intake_contract,
        draft_id,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Project factory draft not found.")
    return ProjectFactoryGuidedIntakeResponse(**payload)


@router.post(
    "/project-factory/drafts/{draft_id}/init",
    response_model=ProjectFactoryInitJobResponse,
)
async def start_project_factory_deterministic_init(
    draft_id: str,
    request: ProjectFactoryInitStartRequest,
    container: AppContainer = Depends(get_container),
) -> ProjectFactoryInitJobResponse:
    draft = await run_in_threadpool(
        container.project_factory_service.get_draft,
        draft_id,
    )
    if draft is None:
        raise HTTPException(status_code=404, detail="Project factory draft not found.")
    project_slug = draft.request.slug or _project_factory_slug(
        draft.request.name or draft_id,
    )
    job = await run_in_threadpool(
        container.project_factory_init_service.start_or_resume,
        draft_id=draft_id,
        chat_session_id=request.chat_session_id,
        workspace_path=str(
            (Path(container.settings.projects_root) / project_slug).resolve()
        ),
        project_name=draft.request.name,
        slug=project_slug,
        frontend_strategy=draft.request.frontend_strategy,
    )
    if container.settings.project_factory_async_jobs:
        Thread(
            target=container.project_factory_init_service.run_pipeline,
            args=(job.id,),
            daemon=True,
        ).start()
    return ProjectFactoryInitJobResponse(
        **container.project_factory_init_service.to_response_payload(job)
    )


@router.get(
    "/project-factory/init-jobs/{init_job_id}",
    response_model=ProjectFactoryInitJobResponse,
)
async def get_project_factory_deterministic_init(
    init_job_id: str,
    container: AppContainer = Depends(get_container),
) -> ProjectFactoryInitJobResponse:
    job = await run_in_threadpool(
        container.project_factory_init_service.get_job,
        init_job_id,
    )
    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Project factory init job not found.",
        )
    return ProjectFactoryInitJobResponse(
        **container.project_factory_init_service.to_response_payload(job)
    )


@router.post(
    "/project-factory/drafts/{draft_id}/reference-assets",
    response_model=ProjectFactoryReferenceAssetResponse,
)
async def upload_project_factory_reference_asset(
    draft_id: str,
    asset: UploadFile = File(...),
    container: AppContainer = Depends(get_container),
) -> ProjectFactoryReferenceAssetResponse:
    content = await asset.read()
    try:
        created_asset = await run_in_threadpool(
            container.project_factory_service.create_reference_asset,
            draft_id=draft_id,
            filename=asset.filename or "",
            content_type=asset.content_type,
            content=content,
        )
    except ProjectFactoryReferenceAssetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if created_asset is None:
        raise HTTPException(status_code=404, detail="Project factory draft not found.")
    return ProjectFactoryReferenceAssetResponse(**created_asset.to_payload())


@router.get(
    "/project-factory/drafts/{draft_id}/reference-assets",
    response_model=ProjectFactoryReferenceAssetsResponse,
)
async def list_project_factory_reference_assets(
    draft_id: str,
    container: AppContainer = Depends(get_container),
) -> ProjectFactoryReferenceAssetsResponse:
    assets = await run_in_threadpool(
        container.project_factory_service.list_reference_assets,
        draft_id,
    )
    if assets is None:
        raise HTTPException(status_code=404, detail="Project factory draft not found.")
    return ProjectFactoryReferenceAssetsResponse(
        draft_id=draft_id,
        assets=[
            ProjectFactoryReferenceAssetResponse(**asset.to_payload())
            for asset in assets
        ],
    )


@router.delete(
    "/project-factory/drafts/{draft_id}/reference-assets/{asset_id}",
    response_model=ProjectFactoryReferenceAssetDeleteResponse,
)
async def delete_project_factory_reference_asset(
    draft_id: str,
    asset_id: str,
    container: AppContainer = Depends(get_container),
) -> ProjectFactoryReferenceAssetDeleteResponse:
    try:
        deleted = await run_in_threadpool(
            container.project_factory_service.delete_reference_asset,
            draft_id=draft_id,
            asset_id=asset_id,
        )
    except ProjectFactoryReferenceAssetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if deleted is None:
        raise HTTPException(status_code=404, detail="Project factory draft not found.")
    if not deleted:
        raise HTTPException(status_code=404, detail="Reference asset not found.")
    return ProjectFactoryReferenceAssetDeleteResponse(
        draft_id=draft_id,
        asset_id=asset_id,
        deleted=True,
    )


@router.post(
    "/project-factory/drafts/{draft_id}/assets",
    response_model=ProjectFactoryDraftAssetResponse,
)
async def link_project_factory_draft_asset(
    draft_id: str,
    request: ProjectFactoryDraftAssetLinkRequest,
    container: AppContainer = Depends(get_container),
) -> ProjectFactoryDraftAssetResponse:
    try:
        linked = await run_in_threadpool(
            container.project_factory_service.link_asset_to_draft,
            draft_id=draft_id,
            asset_id=request.asset_id,
            role=request.role,
            notes=request.notes,
        )
    except AssetDepotError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if linked is None:
        raise HTTPException(status_code=404, detail="Project factory draft not found.")
    return ProjectFactoryDraftAssetResponse(**linked.to_payload())


@router.get(
    "/project-factory/drafts/{draft_id}/assets",
    response_model=ProjectFactoryDraftAssetsResponse,
)
async def list_project_factory_draft_assets(
    draft_id: str,
    container: AppContainer = Depends(get_container),
) -> ProjectFactoryDraftAssetsResponse:
    assets = await run_in_threadpool(
        container.project_factory_service.list_draft_assets,
        draft_id,
    )
    if assets is None:
        raise HTTPException(status_code=404, detail="Project factory draft not found.")
    return ProjectFactoryDraftAssetsResponse(
        draft_id=draft_id,
        assets=[
            ProjectFactoryDraftAssetResponse(**asset.to_payload()) for asset in assets
        ],
    )


@router.post(
    "/project-factory/drafts/{draft_id}/generate",
    response_model=ProjectFactoryJobResponse,
)
async def start_project_factory_generation(
    draft_id: str,
    container: AppContainer = Depends(get_container),
) -> ProjectFactoryJobResponse:
    try:
        job = await run_in_threadpool(
            container.project_factory_service.start_generation,
            draft_id,
        )
    except ProjectFactoryGenerationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if job is None:
        raise HTTPException(status_code=404, detail="Project factory draft not found.")
    return ProjectFactoryJobResponse(**job.to_payload())


@router.get("/project-factory/jobs", response_model=ProjectFactoryJobsResponse)
async def list_project_factory_jobs(
    status: str | None = None,
    draft_id: str | None = None,
    limit: int = 50,
    container: AppContainer = Depends(get_container),
) -> ProjectFactoryJobsResponse:
    jobs = await run_in_threadpool(
        container.project_factory_service.list_jobs,
        status=status,
        draft_id=draft_id,
        limit=limit,
    )
    return ProjectFactoryJobsResponse(jobs=list(jobs))


@router.get(
    "/project-factory/jobs/{job_id}",
    response_model=ProjectFactoryJobResponse,
)
async def get_project_factory_job(
    job_id: str,
    container: AppContainer = Depends(get_container),
) -> ProjectFactoryJobResponse:
    job = await run_in_threadpool(container.project_factory_service.get_job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Project factory job not found.")
    return ProjectFactoryJobResponse(**job.to_payload())


@router.get(
    "/project-factory/doctor",
    response_model=ProjectFactoryDoctorResponse,
)
async def project_factory_doctor(
    container: AppContainer = Depends(get_container),
) -> ProjectFactoryDoctorResponse:
    payload = await run_in_threadpool(container.project_factory_service.doctor)
    payload["web_preview"] = await run_in_threadpool(
        container.cloudflare_preview_doctor_service.doctor,
    )
    return ProjectFactoryDoctorResponse(**payload)


@router.post("/web-previews/plan", response_model=WebPreviewResponse)
async def plan_web_preview(
    request: WebPreviewPlanRequest,
    container: AppContainer = Depends(get_container),
) -> WebPreviewResponse:
    try:
        payload = await run_in_threadpool(
            container.web_preview_deploy_service.plan,
            WebPreviewPlanInput(
                project_path=request.project_path,
                manifest_path=request.manifest_path,
                source_app=request.source_app,
            ),
        )
    except WebPreviewError as exc:
        raise _web_preview_http_error(exc) from exc
    return await _web_preview_response(payload, container)


@router.post("/web-previews/deploy", response_model=WebPreviewResponse)
async def deploy_web_preview(
    request: WebPreviewDeployRequest,
    container: AppContainer = Depends(get_container),
) -> WebPreviewResponse:
    try:
        payload = await run_in_threadpool(
            container.web_preview_deploy_service.deploy,
            WebPreviewDeployInput(
                project_path=request.project_path,
                manifest_path=request.manifest_path,
                source_app=request.source_app,
                confirm_apply=request.confirm_apply,
                expected_plan_hash=request.expected_plan_hash,
            ),
        )
    except WebPreviewError as exc:
        raise _web_preview_http_error(exc) from exc
    return await _web_preview_response(payload, container)


@router.get("/web-previews", response_model=WebPreviewListResponse)
async def list_web_previews(
    limit: int = Query(default=50, ge=1, le=200),
    container: AppContainer = Depends(get_container),
) -> WebPreviewListResponse:
    previews = await run_in_threadpool(
        container.web_preview_deploy_service.list_previews,
        limit=limit,
    )
    email_preflight = await run_in_threadpool(
        container.web_preview_invite_service.email_delivery_preflight,
    )
    return WebPreviewListResponse(
        previews=[
            WebPreviewResponse(**{**preview, "invite_email_delivery": email_preflight})
            for preview in previews
        ],
    )


@router.get("/web-previews/invite-email-preflight")
async def web_preview_invite_email_preflight(
    container: AppContainer = Depends(get_container),
) -> dict[str, Any]:
    return await run_in_threadpool(
        container.web_preview_invite_service.email_delivery_preflight,
    )


@router.get("/web-previews/{preview_id}", response_model=WebPreviewResponse)
async def get_web_preview(
    preview_id: str,
    container: AppContainer = Depends(get_container),
) -> WebPreviewResponse:
    preview = await run_in_threadpool(
        container.web_preview_deploy_service.get_preview,
        preview_id,
    )
    if preview is None:
        raise HTTPException(status_code=404, detail={"code": "web_preview_not_found"})
    return await _web_preview_response(preview, container)


@router.post("/web-previews/{preview_id}/disable", response_model=WebPreviewResponse)
async def disable_web_preview(
    preview_id: str,
    request: WebPreviewLifecycleRequest = Body(
        default_factory=WebPreviewLifecycleRequest,
    ),
    container: AppContainer = Depends(get_container),
) -> WebPreviewResponse:
    try:
        payload = await run_in_threadpool(
            container.web_preview_deploy_service.disable_preview,
            WebPreviewLifecycleInput(
                preview_id=preview_id,
                reason=request.reason,
            ),
        )
    except WebPreviewError as exc:
        raise _web_preview_http_error(exc) from exc
    return await _web_preview_response(payload, container)


@router.post("/web-previews/{preview_id}/expire", response_model=WebPreviewResponse)
async def expire_web_preview(
    preview_id: str,
    request: WebPreviewLifecycleRequest = Body(
        default_factory=WebPreviewLifecycleRequest,
    ),
    container: AppContainer = Depends(get_container),
) -> WebPreviewResponse:
    try:
        payload = await run_in_threadpool(
            container.web_preview_deploy_service.expire_preview,
            WebPreviewLifecycleInput(
                preview_id=preview_id,
                reason=request.reason,
            ),
        )
    except WebPreviewError as exc:
        raise _web_preview_http_error(exc) from exc
    return await _web_preview_response(payload, container)


@router.post("/web-previews/{preview_id}/extend", response_model=WebPreviewResponse)
async def extend_web_preview(
    preview_id: str,
    request: WebPreviewLifecycleRequest = Body(
        default_factory=WebPreviewLifecycleRequest,
    ),
    container: AppContainer = Depends(get_container),
) -> WebPreviewResponse:
    try:
        payload = await run_in_threadpool(
            container.web_preview_deploy_service.extend_preview,
            WebPreviewLifecycleInput(
                preview_id=preview_id,
                ttl_seconds=request.ttl_seconds,
                reason=request.reason,
            ),
        )
    except WebPreviewError as exc:
        raise _web_preview_http_error(exc) from exc
    return await _web_preview_response(payload, container)


@router.post(
    "/web-previews/{preview_id}/invites",
    response_model=WebPreviewInviteResponse,
)
async def create_web_preview_invite(
    preview_id: str,
    request: WebPreviewInviteCreateRequest = Body(
        default_factory=WebPreviewInviteCreateRequest,
    ),
    container: AppContainer = Depends(get_container),
) -> WebPreviewInviteResponse:
    try:
        payload = await run_in_threadpool(
            container.web_preview_invite_service.create_invite,
            WebPreviewInviteCreateInput(
                preview_id=preview_id,
                ttl_seconds=request.ttl_seconds,
                single_use=request.single_use,
                email=request.email,
                role=request.role,
            ),
        )
    except WebPreviewInviteError as exc:
        raise _web_preview_invite_http_error(exc) from exc
    return WebPreviewInviteResponse(**payload)


@router.post(
    "/web-previews/{preview_id}/invites/{invite_id}/resend",
    response_model=WebPreviewInviteResponse,
)
async def resend_web_preview_invite(
    preview_id: str,
    invite_id: str,
    request: WebPreviewInviteResendRequest = Body(
        default_factory=WebPreviewInviteResendRequest,
    ),
    container: AppContainer = Depends(get_container),
) -> WebPreviewInviteResponse:
    try:
        payload = await run_in_threadpool(
            container.web_preview_invite_service.resend_invite,
            preview_id=preview_id,
            invite_id=invite_id,
            ttl_seconds=request.ttl_seconds,
        )
    except WebPreviewInviteError as exc:
        raise _web_preview_invite_http_error(exc) from exc
    return WebPreviewInviteResponse(**payload)


@router.post(
    "/web-previews/{preview_id}/invites/{invite_id}/expire",
    response_model=WebPreviewInviteResponse,
)
async def expire_web_preview_invite(
    preview_id: str,
    invite_id: str,
    container: AppContainer = Depends(get_container),
) -> WebPreviewInviteResponse:
    try:
        payload = await run_in_threadpool(
            container.web_preview_invite_service.expire_invite,
            preview_id=preview_id,
            invite_id=invite_id,
        )
    except WebPreviewInviteError as exc:
        raise _web_preview_invite_http_error(exc) from exc
    return WebPreviewInviteResponse(**payload)


@router.get(
    "/web-previews/{preview_id}/invites",
    response_model=WebPreviewInviteListResponse,
)
async def list_web_preview_invites(
    preview_id: str,
    container: AppContainer = Depends(get_container),
) -> WebPreviewInviteListResponse:
    if (
        await run_in_threadpool(
            container.web_preview_deploy_service.get_preview,
            preview_id,
        )
        is None
    ):
        raise HTTPException(status_code=404, detail={"code": "web_preview_not_found"})
    invites = await run_in_threadpool(
        container.web_preview_invite_service.list_invites,
        preview_id,
    )
    return WebPreviewInviteListResponse(
        invites=[WebPreviewInviteResponse(**invite) for invite in invites],
    )


@router.delete(
    "/web-previews/{preview_id}/invites/{invite_id}",
    response_model=WebPreviewInviteResponse,
)
async def revoke_web_preview_invite(
    preview_id: str,
    invite_id: str,
    container: AppContainer = Depends(get_container),
) -> WebPreviewInviteResponse:
    try:
        payload = await run_in_threadpool(
            container.web_preview_invite_service.revoke_invite,
            preview_id=preview_id,
            invite_id=invite_id,
        )
    except WebPreviewInviteError as exc:
        raise _web_preview_invite_http_error(exc) from exc
    return WebPreviewInviteResponse(**payload)


@router.post(
    "/web-previews/{preview_id}/invites/{invite_id}/sync",
    response_model=WebPreviewInviteResponse,
)
async def sync_web_preview_invite(
    preview_id: str,
    invite_id: str,
    container: AppContainer = Depends(get_container),
) -> WebPreviewInviteResponse:
    try:
        payload = await run_in_threadpool(
            container.web_preview_invite_service.sync_invite,
            preview_id=preview_id,
            invite_id=invite_id,
        )
    except WebPreviewInviteError as exc:
        raise _web_preview_invite_http_error(exc) from exc
    return WebPreviewInviteResponse(**payload)


@router.get("/sdd/projects", response_model=SddProjectsResponse)
async def list_sdd_projects(
    container: AppContainer = Depends(get_container),
) -> SddProjectsResponse:
    projects = await run_in_threadpool(container.sdd_project_service.list_projects)
    return SddProjectsResponse(
        default_workspace_path=container.settings.codex_workdir,
        projects=[_sdd_project_summary_response(project) for project in projects],
    )


@router.get("/sdd/project", response_model=SddProjectResponse)
async def get_sdd_project(
    workspace_path: str = Query(...),
    container: AppContainer = Depends(get_container),
) -> SddProjectResponse:
    try:
        project = await run_in_threadpool(
            container.sdd_project_service.get_project,
            workspace_path,
        )
    except SddWorkspacePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _sdd_project_response(project)


@router.get("/sdd/project/summary", response_model=SddProjectLazySummaryResponse)
async def get_sdd_project_summary(
    workspace_path: str = Query(...),
    container: AppContainer = Depends(get_container),
) -> SddProjectLazySummaryResponse:
    try:
        project = await run_in_threadpool(
            container.sdd_project_service.get_project_summary,
            workspace_path,
        )
    except SddWorkspacePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = _sdd_project_response(project).model_dump()
    payload["kind"] = "codex.sddProjectSummary"
    return SddProjectLazySummaryResponse(**payload)


@router.get("/sdd/project/spec", response_model=SddProjectSpecResponse)
async def get_sdd_project_spec(
    workspace_path: str = Query(...),
    spec_id: str = Query(...),
    container: AppContainer = Depends(get_container),
) -> SddProjectSpecResponse:
    try:
        spec = await run_in_threadpool(
            container.sdd_project_service.get_spec,
            workspace_path,
            spec_id,
        )
    except SddWorkspacePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SddSpecNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SddProjectSpecResponse(
        workspace_path=str(Path(workspace_path).expanduser()),
        spec=_sdd_spec_response(spec),
    )


@router.get("/sdd/project/diagrams", response_model=SddProjectDiagramsResponse)
async def get_sdd_project_diagrams(
    workspace_path: str = Query(...),
    container: AppContainer = Depends(get_container),
) -> SddProjectDiagramsResponse:
    try:
        diagrams = await run_in_threadpool(
            container.sdd_project_service.get_diagrams,
            workspace_path,
        )
    except SddWorkspacePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SddProjectDiagramsResponse(
        workspace_path=workspace_path,
        diagrams=[_sdd_diagram_response(diagram) for diagram in diagrams],
    )


@router.get("/sdd/project/diagrams/asset")
async def get_sdd_project_diagram_asset(
    workspace_path: str = Query(...),
    diagram_path: str = Query(...),
    container: AppContainer = Depends(get_container),
) -> Response:
    try:
        asset = await run_in_threadpool(
            container.sdd_project_service.get_diagram_asset,
            workspace_path,
            diagram_path,
        )
    except SddWorkspacePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SddProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=asset.content,
        media_type=asset.content_type,
        headers={
            "ETag": asset.digest,
            "Last-Modified": asset.updated_at,
            "X-SDD-Diagram-Path": asset.path,
        },
    )


@router.post(
    "/sdd/project/diagrams/rendered-export",
    response_model=SddRenderedDiagramExportResponse,
)
async def persist_sdd_rendered_diagram_export(
    request: SddRenderedDiagramExportRequest,
    container: AppContainer = Depends(get_container),
) -> SddRenderedDiagramExportResponse:
    try:
        diagram = await run_in_threadpool(
            container.sdd_project_service.persist_rendered_diagram,
            SddRenderedDiagramExport(
                workspace_path=request.workspace_path,
                spec_id=request.spec_id,
                diagram_id=request.diagram_id,
                title=request.title,
                diagram_type=request.diagram_type,
                svg=request.svg,
                renderer=request.renderer,
                diagram_spec_id=request.diagram_spec_id,
            ),
        )
    except SddWorkspacePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SddSpecNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SddProjectError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SddRenderedDiagramExportResponse(
        workspace_path=request.workspace_path,
        diagram=_sdd_diagram_response(diagram),
    )


@router.get("/sdd/doctor", response_model=SddDoctorResponse)
async def run_sdd_doctor(
    workspace_path: str = Query(...),
    strict: bool = Query(default=False),
    selected_artifact: str | None = Query(default=None),
    query: str = Query(default=""),
    container: AppContainer = Depends(get_container),
) -> SddDoctorResponse:
    try:
        workspace = Path(workspace_path).expanduser().resolve()
        await run_in_threadpool(
            container.sdd_project_service.get_project,
            str(workspace),
        )
    except SddWorkspacePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    command = [
        sys.executable,
        str(Path(__file__).resolve().parents[3] / "scripts/codex_bridge_sdd_doctor.py"),
        "--workspace",
        str(workspace),
        "--projects-root",
        container.settings.projects_root,
        "--json",
    ]
    if strict:
        command.append("--strict")
    if selected_artifact:
        command.extend(["--selected-artifact", selected_artifact])
    if query:
        command.extend(["--query", query])
    result = await run_in_threadpool(
        subprocess.run,
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        detail = result.stderr.strip() or result.stdout.strip() or str(exc)
        raise HTTPException(status_code=500, detail=detail) from exc
    return SddDoctorResponse(**payload)


@router.get("/sdd/workbench/view", response_model=SddWorkbenchViewResponse)
async def get_sdd_workbench_view(
    workspace_path: str = Query(...),
    preset: str = Query("new-feature"),
    selected_artifact: str | None = Query(default=None),
    query: str = Query(default=""),
    auto_regenerate_indexes: bool = Query(default=True),
    allow_degraded: bool = Query(default=True),
    container: AppContainer = Depends(get_container),
) -> SddWorkbenchViewResponse:
    try:
        project = await run_in_threadpool(
            container.sdd_project_service.get_project,
            workspace_path,
        )
    except SddWorkspacePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    view = await run_in_threadpool(
        container.sdd_workbench_view_service.build_view,
        workspace=Path(project.workspace_path),
        project=project,
        preset=preset,
        selected_artifact=selected_artifact,
        query=query,
        auto_regenerate_indexes=auto_regenerate_indexes,
        allow_degraded=allow_degraded,
    )
    return SddWorkbenchViewResponse(**view.to_payload())


@router.get("/sdd/workbench/kanban", response_model=SddWorkbenchKanbanResponse)
async def get_sdd_workbench_kanban(
    workspace_path: str | None = Query(default=None),
    spec_id: str | None = Query(default=None),
    draft_id: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    container: AppContainer = Depends(get_container),
) -> SddWorkbenchKanbanResponse:
    project: SddProject | None = None
    workspace: Path | None = None
    if workspace_path:
        try:
            project = await run_in_threadpool(
                container.sdd_project_service.get_project,
                workspace_path,
            )
            workspace = Path(project.workspace_path)
        except SddWorkspacePathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if workspace is None and not (draft_id or job_id):
        raise HTTPException(
            status_code=400,
            detail="workspace_path, draft_id, or job_id is required.",
        )
    result = await run_in_threadpool(
        container.sdd_workbench_kanban_service.build_board,
        workspace=workspace,
        project=project,
        spec_id=spec_id,
        draft_id=draft_id,
        job_id=job_id,
    )
    return SddWorkbenchKanbanResponse(**result.payload)


@router.get(
    "/sdd/workbench/kanban/scopes",
    response_model=SddWorkbenchKanbanScopesResponse,
)
async def get_sdd_workbench_kanban_scopes(
    workspace_path: str | None = Query(default=None),
    container: AppContainer = Depends(get_container),
) -> SddWorkbenchKanbanScopesResponse:
    project: SddProject | None = None
    workspace: Path | None = None
    if workspace_path:
        try:
            project = await run_in_threadpool(
                container.sdd_project_service.get_project,
                workspace_path,
            )
            workspace = Path(project.workspace_path)
        except SddWorkspacePathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = await run_in_threadpool(
        container.sdd_workbench_kanban_service.build_scopes,
        workspace=workspace,
        project=project,
    )
    return SddWorkbenchKanbanScopesResponse(**payload)


@router.post("/sdd/workbench/kanban/refresh", response_model=SddWorkbenchKanbanResponse)
async def refresh_sdd_workbench_kanban(
    workspace_path: str | None = Query(default=None),
    spec_id: str | None = Query(default=None),
    draft_id: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
    container: AppContainer = Depends(get_container),
) -> SddWorkbenchKanbanResponse:
    project: SddProject | None = None
    workspace: Path | None = None
    if workspace_path:
        try:
            project = await run_in_threadpool(
                container.sdd_project_service.get_project,
                workspace_path,
            )
            workspace = Path(project.workspace_path)
        except SddWorkspacePathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if workspace is None and not (draft_id or job_id):
        raise HTTPException(
            status_code=400,
            detail="workspace_path, draft_id, or job_id is required.",
        )
    result = await run_in_threadpool(
        container.sdd_workbench_kanban_service.build_board,
        workspace=workspace,
        project=project,
        spec_id=spec_id,
        draft_id=draft_id,
        job_id=job_id,
        force_refresh=True,
    )
    return SddWorkbenchKanbanResponse(**result.payload)


@router.get(
    "/sdd/workbench/kanban/history",
    response_model=SddWorkbenchKanbanHistoryResponse,
)
async def get_sdd_workbench_kanban_history(
    workspace_path: str | None = Query(default=None),
    scope_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=80),
    container: AppContainer = Depends(get_container),
) -> SddWorkbenchKanbanHistoryResponse:
    workspace: Path | None = None
    if workspace_path:
        try:
            project = await run_in_threadpool(
                container.sdd_project_service.get_project_summary,
                workspace_path,
            )
            workspace = Path(project.workspace_path)
        except SddWorkspacePathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = await run_in_threadpool(
        container.sdd_workbench_kanban_service.history,
        workspace=workspace,
        scope_id=scope_id,
        limit=limit,
    )
    return SddWorkbenchKanbanHistoryResponse(**payload)


@router.get(
    "/sdd/workbench/kanban/history/{update_id}",
    response_model=SddWorkbenchKanbanHistoryItemResponse,
)
async def get_sdd_workbench_kanban_history_item(
    update_id: str,
    workspace_path: str | None = Query(default=None),
    scope_id: str | None = Query(default=None),
    container: AppContainer = Depends(get_container),
) -> SddWorkbenchKanbanHistoryItemResponse:
    workspace: Path | None = None
    if workspace_path:
        try:
            project = await run_in_threadpool(
                container.sdd_project_service.get_project_summary,
                workspace_path,
            )
            workspace = Path(project.workspace_path)
        except SddWorkspacePathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = await run_in_threadpool(
        container.sdd_workbench_kanban_service.history_item,
        update_id=update_id,
        workspace=workspace,
        scope_id=scope_id,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Curator update not found.")
    return SddWorkbenchKanbanHistoryItemResponse(**payload)


@router.post("/sdd/specs/dry-run", response_model=SddSpecCreationDryRunResponse)
async def dry_run_sdd_spec_creation(
    request: SddSpecDryRunRequest,
    container: AppContainer = Depends(get_container),
) -> SddSpecCreationDryRunResponse:
    service = SddSpecCreationService(
        projects_root=container.settings.projects_root,
        workspace_aliases=container.settings.feedback_source_workspace_alias_map,
    )
    plan = await run_in_threadpool(
        service.dry_run_new_spec,
        _spec_intake_validation_input(request),
        job_id=request.job_id,
    )
    return SddSpecCreationDryRunResponse(**plan.to_payload())


@router.post("/sdd/specs/apply", response_model=SddSpecApplyResponse)
async def apply_sdd_spec_creation(
    request: SddSpecDryRunRequest,
    container: AppContainer = Depends(get_container),
) -> SddSpecApplyResponse:
    service = SddSpecCreationService(
        projects_root=container.settings.projects_root,
        workspace_aliases=container.settings.feedback_source_workspace_alias_map,
    )
    result = await run_in_threadpool(
        service.apply_new_spec,
        _spec_intake_validation_input(request),
        job_id=request.job_id,
    )
    return SddSpecApplyResponse(**result.to_payload())


@router.post(
    "/sdd/specs/edit/dry-run",
    response_model=SddSpecEditDryRunResponse,
)
async def dry_run_sdd_spec_edit(
    request: SddSpecDryRunRequest,
    container: AppContainer = Depends(get_container),
) -> SddSpecEditDryRunResponse:
    service = SddSpecEditService(
        projects_root=container.settings.projects_root,
        workspace_aliases=container.settings.feedback_source_workspace_alias_map,
    )
    plan = await run_in_threadpool(
        service.dry_run_existing_spec_edit,
        _spec_intake_validation_input(request),
    )
    return SddSpecEditDryRunResponse(**plan.to_payload())


@router.post(
    "/sdd/specs/edit/apply",
    response_model=SddSpecEditApplyResponse,
)
async def apply_sdd_spec_edit(
    request: SddSpecDryRunRequest,
    container: AppContainer = Depends(get_container),
) -> SddSpecEditApplyResponse:
    service = SddSpecEditService(
        projects_root=container.settings.projects_root,
        workspace_aliases=container.settings.feedback_source_workspace_alias_map,
        codex_job_service=container.sdd_codex_job_service,
    )
    result = await run_in_threadpool(
        service.apply_existing_spec_edit,
        _spec_intake_validation_input(request),
    )
    return SddSpecEditApplyResponse(**result.to_payload())


@router.get("/sdd/codex-jobs/{job_id}", response_model=SddCodexJobResponse)
async def get_sdd_codex_job(
    job_id: str,
    container: AppContainer = Depends(get_container),
) -> SddCodexJobResponse:
    job = await run_in_threadpool(container.sdd_codex_job_service.get_job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="SDD Codex job not found.")
    return SddCodexJobResponse(**job.to_payload())


@router.get(
    "/sdd/codex-jobs/{job_id}/activity",
    response_model=SddActivityResponse,
)
async def get_sdd_codex_job_activity(
    job_id: str,
    container: AppContainer = Depends(get_container),
) -> SddActivityResponse:
    job = await run_in_threadpool(container.sdd_codex_job_service.get_job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="SDD Codex job not found.")
    return SddActivityResponse(**job.to_payload()["activity"])


@router.post("/sdd/codex-jobs/{job_id}/run", response_model=SddCodexJobResponse)
async def run_sdd_codex_job(
    job_id: str,
    container: AppContainer = Depends(get_container),
) -> SddCodexJobResponse:
    try:
        job = await run_in_threadpool(container.sdd_codex_job_service.run_job, job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="SDD Codex job not found.") from exc
    return SddCodexJobResponse(**job.to_payload())


@router.post("/sdd/codex-jobs/{job_id}/cancel", response_model=SddCodexJobResponse)
async def cancel_sdd_codex_job(
    job_id: str,
    container: AppContainer = Depends(get_container),
) -> SddCodexJobResponse:
    try:
        job = await run_in_threadpool(
            container.sdd_codex_job_service.cancel_job,
            job_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="SDD Codex job not found.") from exc
    return SddCodexJobResponse(**job.to_payload())


@router.post(
    "/sdd/codex-jobs/{job_id}/retry",
    response_model=SddCodexJobRetryResponse,
)
async def retry_sdd_codex_job(
    job_id: str,
    container: AppContainer = Depends(get_container),
) -> SddCodexJobRetryResponse:
    try:
        result = await run_in_threadpool(
            container.sdd_codex_job_service.retry_job,
            job_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="SDD Codex job not found.") from exc
    return SddCodexJobRetryResponse(**result.to_payload())


@router.get(
    "/sdd/codex-jobs/{job_id}/review",
    response_model=SddCodexJobReviewResponse,
)
async def review_sdd_codex_job(
    job_id: str,
    container: AppContainer = Depends(get_container),
) -> SddCodexJobReviewResponse:
    try:
        review = await run_in_threadpool(
            container.sdd_codex_job_service.review_job,
            job_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="SDD Codex job not found.") from exc
    return SddCodexJobReviewResponse(**review.to_payload())


@router.post(
    "/sdd/codex-jobs/{job_id}/apply",
    response_model=SddCodexJobApplyResponse,
)
async def apply_sdd_codex_job(
    job_id: str,
    container: AppContainer = Depends(get_container),
) -> SddCodexJobApplyResponse:
    try:
        result = await run_in_threadpool(
            container.sdd_codex_job_service.apply_reviewed_job,
            job_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="SDD Codex job not found.") from exc
    return SddCodexJobApplyResponse(**result.to_payload())


@router.post(
    "/sdd/specs/intake/media",
    response_model=SddMediaUploadResponse,
)
async def upload_sdd_spec_intake_media(
    media: UploadFile = File(...),
    workspace_path: str = Form(...),
    kind: str = Form(default="image"),
    mime_type: str | None = Form(default=None),
    sha256: str | None = Form(default=None),
    duration_ms: int | None = Form(default=None),
    source_ref: str | None = Form(default=None),
    region: str | None = Form(default=None),
    container: AppContainer = Depends(get_container),
) -> SddMediaUploadResponse:
    content = await media.read()
    region_payload = _parse_region_form(region)
    service = SddMediaUploadService(
        projects_root=container.settings.projects_root,
        workspace_aliases=container.settings.feedback_source_workspace_alias_map,
    )
    result = await run_in_threadpool(
        service.stage_media,
        workspace_path=workspace_path,
        kind=kind,
        filename=media.filename or "image.png",
        mime_type=mime_type or media.content_type,
        content=content,
        sha256=sha256,
        duration_ms=duration_ms,
        source_ref=source_ref,
        region=region_payload,
    )
    return SddMediaUploadResponse(**result.to_payload())


@router.post(
    "/sdd/specs/intake/media/delete",
    response_model=SddMediaLifecycleResponse,
)
async def delete_sdd_spec_intake_media(
    request: SddMediaDeleteRequest,
    container: AppContainer = Depends(get_container),
) -> SddMediaLifecycleResponse:
    service = SddMediaUploadService(
        projects_root=container.settings.projects_root,
        workspace_aliases=container.settings.feedback_source_workspace_alias_map,
    )
    result = await run_in_threadpool(
        service.delete_staged_media,
        workspace_path=request.workspace_path,
        staged_path=request.staged_path,
    )
    return SddMediaLifecycleResponse(**result.to_payload())


@router.post(
    "/sdd/specs/intake/media/cleanup",
    response_model=SddMediaLifecycleResponse,
)
async def cleanup_sdd_spec_intake_media(
    request: SddMediaCleanupRequest,
    container: AppContainer = Depends(get_container),
) -> SddMediaLifecycleResponse:
    service = SddMediaUploadService(
        projects_root=container.settings.projects_root,
        workspace_aliases=container.settings.feedback_source_workspace_alias_map,
    )
    result = await run_in_threadpool(
        service.cleanup_staged_media,
        workspace_path=request.workspace_path,
        dry_run=request.dry_run,
        older_than_hours=request.older_than_hours,
    )
    return SddMediaLifecycleResponse(**result.to_payload())


async def _feedback_items_for_sdd_capture(
    item_ids: list[str],
    *,
    container: AppContainer,
):
    items = []
    for item_id in item_ids:
        try:
            items.append(
                await run_in_threadpool(
                    container.feedback_queue_service.get_item,
                    item_id,
                    include_image=False,
                )
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"Feedback item not found: {item_id}",
            ) from exc
    return tuple(items)


def _resolve_sdd_bridge_capture_target(
    request_target: object | None,
    feedback_items: tuple[object, ...],
) -> tuple[SpecTargetInput | None, list[str]]:
    embedded_targets = [
        _spec_target_from_payload(getattr(item, "spec_target", {}))
        for item in feedback_items
    ]
    embedded_targets = [
        target
        for target in embedded_targets
        if target is not None and target.mode != "none"
    ]
    unique_embedded = {_spec_target_key(target) for target in embedded_targets}
    if len(unique_embedded) > 1:
        return (
            None,
            [
                "spec_target_conflict: feedback items contain different embedded spec_target values"
            ],
        )

    embedded_target = embedded_targets[0] if embedded_targets else None
    explicit_target = (
        _spec_target_input(request_target) if request_target is not None else None
    )
    if explicit_target is None or explicit_target.mode == "none":
        return (embedded_target or explicit_target or SpecTargetInput(mode="none"), [])
    if embedded_target is not None and _spec_target_key(
        explicit_target
    ) != _spec_target_key(embedded_target):
        return (
            explicit_target,
            [
                "spec_target_conflict: request spec_target does not match embedded feedback spec_target"
            ],
        )
    return (explicit_target, [])


def _spec_target_from_payload(payload: object) -> SpecTargetInput | None:
    if not isinstance(payload, dict) or not payload:
        return None
    return SpecTargetInput(
        mode=str(payload.get("mode") or "none"),
        spec_id=(
            str(payload.get("spec_id") or payload.get("specId"))
            if payload.get("spec_id") or payload.get("specId")
            else None
        ),
        artifact=str(payload.get("artifact") or "auto"),
    )


def _spec_target_key(target: SpecTargetInput) -> tuple[str, str, str]:
    return (
        target.mode,
        target.spec_id or "",
        target.artifact or "auto",
    )


def _blocked_sdd_bridge_capture_payload(
    *,
    request: SddBridgeCaptureIntakeRequest,
    target: SpecTargetInput | None,
    errors: list[str],
) -> dict[str, object]:
    return {
        "kind": "codex.sddBridgeCaptureIntake",
        "version": 1,
        "status": "blocked",
        "workspace_path": request.workspace_path,
        "target_mode": (target.mode if target is not None else "unknown"),
        "feedback_item_ids": list(request.feedback_item_ids),
        "intake_items": [],
        "staged_media": [],
        "dry_run": None,
        "apply_result": None,
        "blocked": errors,
        "next_actions": ["Resolve spec_target conflicts before SDD intake."],
    }


@router.post(
    "/sdd/bridge-captures/dry-run",
    response_model=SddBridgeCaptureIntakeResponse,
)
async def dry_run_sdd_bridge_capture(
    request: SddBridgeCaptureIntakeRequest,
    container: AppContainer = Depends(get_container),
) -> SddBridgeCaptureIntakeResponse:
    feedback_items = await _feedback_items_for_sdd_capture(
        request.feedback_item_ids,
        container=container,
    )
    resolved_target, target_errors = _resolve_sdd_bridge_capture_target(
        request.spec_target,
        feedback_items,
    )
    if target_errors:
        return SddBridgeCaptureIntakeResponse(
            **_blocked_sdd_bridge_capture_payload(
                request=request,
                target=resolved_target,
                errors=target_errors,
            )
        )
    service = SddBridgeCaptureService(
        projects_root=container.settings.projects_root,
        workspace_aliases=container.settings.feedback_source_workspace_alias_map,
        codex_job_service=container.sdd_codex_job_service,
    )
    result = await run_in_threadpool(
        service.dry_run_capture,
        workspace_path=request.workspace_path,
        spec_target=resolved_target or SpecTargetInput(mode="none"),
        feedback_items=feedback_items,
        artifact=None if request.artifact == "auto" else request.artifact,
        job_id=request.job_id,
    )
    return SddBridgeCaptureIntakeResponse(**result.to_payload())


@router.post(
    "/sdd/bridge-captures/apply",
    response_model=SddBridgeCaptureIntakeResponse,
)
async def apply_sdd_bridge_capture(
    request: SddBridgeCaptureIntakeRequest,
    container: AppContainer = Depends(get_container),
) -> SddBridgeCaptureIntakeResponse:
    feedback_items = await _feedback_items_for_sdd_capture(
        request.feedback_item_ids,
        container=container,
    )
    resolved_target, target_errors = _resolve_sdd_bridge_capture_target(
        request.spec_target,
        feedback_items,
    )
    if target_errors:
        return SddBridgeCaptureIntakeResponse(
            **_blocked_sdd_bridge_capture_payload(
                request=request,
                target=resolved_target,
                errors=target_errors,
            )
        )
    service = SddBridgeCaptureService(
        projects_root=container.settings.projects_root,
        workspace_aliases=container.settings.feedback_source_workspace_alias_map,
        codex_job_service=container.sdd_codex_job_service,
    )
    result = await run_in_threadpool(
        service.apply_capture,
        workspace_path=request.workspace_path,
        spec_target=resolved_target or SpecTargetInput(mode="none"),
        feedback_items=feedback_items,
        artifact=None if request.artifact == "auto" else request.artifact,
        job_id=request.job_id,
    )
    return SddBridgeCaptureIntakeResponse(**result.to_payload())


def _spec_intake_validation_input(
    request: SddSpecDryRunRequest,
) -> SpecIntakeValidationInput:
    return SpecIntakeValidationInput(
        workspace_path=request.workspace_path,
        spec_target=_spec_target_input(request.spec_target),
        intake_items=tuple(
            _spec_intake_item_input(item) for item in request.intake_items
        ),
        title_seed=request.title_seed,
        workbench_spec_target=_spec_target_input(request.workbench_spec_target)
        if request.workbench_spec_target is not None
        else None,
        bridge_spec_target=_spec_target_input(request.bridge_spec_target)
        if request.bridge_spec_target is not None
        else None,
    )


def _parse_region_form(region: str | None) -> dict[str, object] | None:
    if region is None or not region.strip():
        return None
    try:
        payload = json.loads(region)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400, detail="Invalid crop region JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Crop region must be an object.")
    return payload


def _spec_target_input(target: object) -> SpecTargetInput:
    return SpecTargetInput(
        mode=getattr(target, "mode"),
        spec_id=getattr(target, "spec_id"),
        artifact=getattr(target, "artifact"),
    )


def _spec_intake_item_input(item: object) -> SpecIntakeMediaItemInput:
    region = getattr(item, "region", None)
    return SpecIntakeMediaItemInput(
        kind=getattr(item, "kind"),
        mime_type=getattr(item, "mime_type"),
        byte_size=getattr(item, "byte_size"),
        filename=getattr(item, "filename"),
        sha256=getattr(item, "sha256"),
        text=getattr(item, "text"),
        transcript=getattr(item, "transcript"),
        duration_ms=getattr(item, "duration_ms"),
        source_ref=getattr(item, "source_ref"),
        payload_ref=getattr(item, "payload_ref"),
        region=region.model_dump() if region is not None else None,
        image_count=getattr(item, "image_count"),
        frame_count=getattr(item, "frame_count"),
        audio_track_count=getattr(item, "audio_track_count"),
        timeline_ms=tuple(getattr(item, "timeline_ms")),
        references=tuple(getattr(item, "references")),
    )


def _sdd_file_response(file_value: SddFile | None) -> SddFileResponse | None:
    if file_value is None:
        return None
    return SddFileResponse(
        path=file_value.path,
        title=file_value.title,
        size_bytes=file_value.size_bytes,
        content=file_value.content,
        error=file_value.error,
    )


def _sdd_diagram_response(diagram: SddDiagram) -> SddDiagramResponse:
    return SddDiagramResponse(
        path=diagram.path,
        title=diagram.title,
        size_bytes=diagram.size_bytes,
        content=diagram.content,
        error=diagram.error,
        diagram_type=diagram.diagram_type,
        scope=diagram.scope,
        spec_id=diagram.spec_id,
        diagram_id=diagram.diagram_id,
        source_format=diagram.source_format,
        rendered_format=diagram.rendered_format,
        content_type=diagram.content_type,
        digest=diagram.digest,
        updated_at=diagram.updated_at,
        metadata_path=diagram.metadata_path,
        renderer=diagram.renderer,
    )


def _sdd_task_node_response(task: SddTaskNode) -> SddTaskNodeResponse:
    return SddTaskNodeResponse(
        id=task.id,
        title=task.title,
        number=task.number,
        status=task.status,
        description=task.description,
        file=_sdd_file_response(task.file),
        diagrams=[_sdd_diagram_response(diagram) for diagram in task.diagrams],
    )


def _sdd_plan_node_response(plan: SddPlanNode) -> SddPlanNodeResponse:
    return SddPlanNodeResponse(
        id=plan.id,
        title=plan.title,
        number=plan.number,
        status=plan.status,
        description=plan.description,
        file=_sdd_file_response(plan.file),
        diagrams=[_sdd_diagram_response(diagram) for diagram in plan.diagrams],
        tasks=[_sdd_task_node_response(task) for task in plan.tasks],
    )


def _sdd_spec_tree_response(tree: SddSpecTree | None) -> SddSpecTreeResponse | None:
    if tree is None:
        return None
    return SddSpecTreeResponse(
        file=_sdd_file_response(tree.file),
        diagrams=[_sdd_diagram_response(diagram) for diagram in tree.diagrams],
        plans=[_sdd_plan_node_response(plan) for plan in tree.plans],
        complete=tree.complete,
        missing=list(tree.missing),
    )


def _sdd_spec_response(spec: SddSpec) -> SddSpecResponse:
    metadata = spec.metadata
    tree_linked = spec.tree is not None and spec.tree.complete
    return SddSpecResponse(
        id=spec.id,
        title=spec.title,
        description=metadata.description,
        path=spec.path,
        lifecycle_status=metadata.lifecycle_status,
        traceability_status=(
            "incomplete"
            if (
                spec.missing
                or (not tree_linked and spec.spec is None)
                or (not tree_linked and spec.plan is None)
                or (not tree_linked and spec.tasks is None)
            )
            else "linked"
        ),
        created_at=metadata.created_at,
        updated_at=metadata.updated_at,
        generated_title=metadata.generated.title,
        generated_description=metadata.generated.description,
        user_pinned_title=metadata.generated.user_pinned_title,
        user_pinned_description=metadata.generated.user_pinned_description,
        task_total=metadata.tasks.total,
        task_completed=metadata.tasks.completed,
        task_pending=metadata.tasks.pending,
        last_run_state=metadata.last_run_state,
        metadata_status=metadata.metadata_status,
        metadata_warnings=list(metadata.metadata_warnings),
        metadata_stale_paths=list(metadata.metadata_stale_paths),
        spec=_sdd_file_response(spec.spec),
        plan=_sdd_file_response(spec.plan),
        tasks=_sdd_file_response(spec.tasks),
        spec_files=[
            file_response
            for file_value in spec.spec_files
            if (file_response := _sdd_file_response(file_value)) is not None
        ],
        plan_files=[
            file_response
            for file_value in spec.plan_files
            if (file_response := _sdd_file_response(file_value)) is not None
        ],
        task_files=[
            file_response
            for file_value in spec.task_files
            if (file_response := _sdd_file_response(file_value)) is not None
        ],
        slice_docs=[
            file_response
            for file_value in spec.slice_docs
            if (file_response := _sdd_file_response(file_value)) is not None
        ],
        diagrams=[_sdd_diagram_response(diagram) for diagram in spec.diagrams],
        tree=_sdd_spec_tree_response(spec.tree),
        missing=list(spec.missing),
    )


def _sdd_project_summary_response(
    project: SddProjectSummary,
) -> SddProjectSummaryResponse:
    return SddProjectSummaryResponse(
        workspace_name=project.workspace_name,
        workspace_path=project.workspace_path,
        has_manifest=project.has_manifest,
        has_constitution=project.has_constitution,
        spec_count=project.spec_count,
        diagram_count=project.diagram_count,
        missing_required=list(project.missing_required),
    )


def _sdd_project_response(
    project: SddProject,
) -> SddProjectResponse:
    return SddProjectResponse(
        workspace_name=project.workspace_name,
        workspace_path=project.workspace_path,
        required=project.required,
        manifest=_sdd_file_response(project.manifest),
        constitution=_sdd_file_response(project.constitution),
        architecture_diagrams=[
            _sdd_diagram_response(diagram) for diagram in project.architecture_diagrams
        ],
        specs=[_sdd_spec_response(spec) for spec in project.specs],
        missing_required=list(project.missing_required),
    )


@router.get("/maintenance/drain", response_model=BackendDrainStatusResponse)
async def get_backend_drain_status(
    service: MessageService = Depends(get_message_service),
) -> BackendDrainStatusResponse:
    status = await run_in_threadpool(service.backend_drain_status)
    return BackendDrainStatusResponse.from_domain(status)


@router.post("/maintenance/drain", response_model=BackendDrainStatusResponse)
async def set_backend_drain(
    payload: BackendDrainRequest,
    service: MessageService = Depends(get_message_service),
) -> BackendDrainStatusResponse:
    status = await run_in_threadpool(service.set_backend_drain, payload.requested)
    return BackendDrainStatusResponse.from_domain(status)


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
                release_channel=config.release_channel,
                release_tag_pattern=config.release_tag_pattern,
                apk_asset_pattern=config.apk_asset_pattern,
                latest_asset_name=config.latest_asset_name,
                private_install=config.release_channel == "private-install",
                expected_package_id=config.expected_package_id,
                preview_url=config.preview_url,
                runtime_profile=config.runtime_profile,
                production_ready=config.production_ready,
                mock_or_demo=config.mock_or_demo,
                release_metadata=config.release_metadata or {},
            )
            for config in container.app_update_service.list_apps()
        ],
    )


@router.get("/installable-apps", response_model=InstallableAppsResponse)
async def list_installable_apps(
    request: Request,
    platform: str = "android",
    channel: str = "stable",
    container: AppContainer = Depends(get_container),
) -> InstallableAppsResponse:
    apps = []
    for config in await run_in_threadpool(container.app_update_service.list_apps):
        apps.append(
            await _installable_app_for_config(
                request=request,
                config=config,
                platform=platform,
                channel=channel,
                container=container,
            )
        )
    return InstallableAppsResponse(apps=apps)


@router.post(
    "/installable-apps",
    response_model=AppUpdateRegistryItemResponse,
    status_code=201,
)
async def register_installable_app(
    payload: InstallableAppRegistrationRequest,
    authorization: str | None = Header(default=None),
    x_bridge_registration_token: str | None = Header(default=None),
    container: AppContainer = Depends(get_container),
) -> AppUpdateRegistryItemResponse:
    _authorize_installable_app_registration(
        container=container,
        authorization=authorization,
        registration_token=x_bridge_registration_token,
    )
    try:
        config = await run_in_threadpool(
            container.app_update_service.register_app,
            source_app=payload.source_app,
            display_name=payload.display_name,
            repo=payload.repo,
            release_tag_pattern=payload.release_tag_pattern,
            apk_asset_pattern=payload.apk_asset_pattern,
            latest_asset_name=payload.latest_asset_name,
            required_minimum_build=payload.required_minimum_build,
            enabled=payload.enabled,
            release_channel=payload.release_channel,
            expected_package_id=payload.expected_package_id,
            verified_package_ids=payload.verified_package_ids,
            preview_url=payload.preview_url,
            runtime_profile=payload.runtime_profile,
            production_ready=payload.production_ready,
            mock_or_demo=payload.mock_or_demo,
            release_metadata=payload.release_metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AppUpdateRegistryItemResponse(
        source_app=config.source_app,
        display_name=config.display_name,
        enabled=config.enabled,
        required_minimum_build=config.required_minimum_build,
        release_channel=config.release_channel,
        release_tag_pattern=config.release_tag_pattern,
        apk_asset_pattern=config.apk_asset_pattern,
        latest_asset_name=config.latest_asset_name,
        private_install=config.release_channel == "private-install",
        expected_package_id=config.expected_package_id,
        preview_url=config.preview_url,
        runtime_profile=config.runtime_profile,
        production_ready=config.production_ready,
        mock_or_demo=config.mock_or_demo,
        release_metadata=config.release_metadata or {},
    )


@router.get(
    "/installable-apps/{source_app}",
    response_model=InstallableAppResponse,
)
async def get_installable_app(
    request: Request,
    source_app: str,
    platform: str = "android",
    channel: str = "stable",
    container: AppContainer = Depends(get_container),
) -> InstallableAppResponse:
    configs = {
        config.source_app: config
        for config in await run_in_threadpool(container.app_update_service.list_apps)
    }
    config = configs.get(source_app)
    if config is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "unknown_source_app",
                "sourceApp": source_app,
            },
        )
    return await _installable_app_for_config(
        request=request,
        config=config,
        platform=platform,
        channel=channel,
        container=container,
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
            release_channel="stable",
            release_prerelease=False,
            private_install=False,
            package_id=None,
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
    response_channel = result.release_channel or channel
    if result.available and result.release_tag and result.apk_asset_name:
        apk_url = _app_update_apk_proxy_url(
            request=request,
            container=container,
            source_app=result.source_app,
            release_tag=result.release_tag,
            asset_name=result.apk_asset_name,
            platform=platform,
            channel=response_channel,
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
            PersistenceIntegrityIssueResponse.from_domain(issue) for issue in issues
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
    if payload.session_id:
        try:
            container.dev_pipeline_service.validate_stage_session_execution(
                session_id=payload.session_id,
                workspace_path=payload.workspace_path,
                backend_url=container.settings.api_base_url,
            )
        except DevPipelineError as exc:
            _raise_dev_pipeline_error(exc)
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
    parts = [part for part in _FEEDBACK_WORKSPACE_KEY_PATTERN.split(raw_value) if part]
    return "-".join(parts)


def _feedback_batch_workspace_path(
    payload: FeedbackBatchStartRequest,
    *,
    item_payloads: list[dict],
    container: AppContainer,
) -> str | None:
    return _feedback_workspace_path_for_source(
        source_app=payload.sourceApp,
        source_display_name=payload.sourceDisplayName,
        workspace_path=payload.workspace_path,
        item_payloads=item_payloads,
        container=container,
    )


def _feedback_batch_release_target(
    payload: FeedbackBatchStartRequest,
    *,
    item_payloads: list[dict],
    workspace_path: str | None,
    container: AppContainer,
) -> dict[str, Any]:
    raw_target = (
        payload.release_target if isinstance(payload.release_target, dict) else {}
    )
    source_app = _feedback_first_text(
        raw_target.get("sourceApp"),
        raw_target.get("source_app"),
        payload.sourceApp,
        *(item.get("sourceApp") for item in item_payloads),
        *(item.get("source_app") for item in item_payloads),
    )
    source_display_name = _feedback_first_text(
        raw_target.get("sourceDisplayName"),
        raw_target.get("source_display_name"),
        raw_target.get("workspaceLabel"),
        raw_target.get("workspace_label"),
        payload.sourceDisplayName,
        *(item.get("sourceDisplayName") for item in item_payloads),
        *(item.get("source_display_name") for item in item_payloads),
    )
    explicit_target_workspace = _feedback_first_text(
        raw_target.get("workspacePath"),
        raw_target.get("workspace_path"),
    )
    target_workspace_path = (
        _resolve_explicit_feedback_workspace_path(
            explicit_target_workspace,
            container=container,
        )
        if explicit_target_workspace
        else _feedback_workspace_path_for_source(
            source_app=source_app,
            source_display_name=source_display_name,
            workspace_path=None,
            item_payloads=item_payloads,
            container=container,
        )
    )
    if target_workspace_path is None and not source_app and workspace_path:
        target_workspace_path = workspace_path

    target: dict[str, Any] = {
        "kind": _feedback_first_text(raw_target.get("kind")) or "app",
    }
    if source_app:
        target["sourceApp"] = source_app
    if source_display_name:
        target["sourceDisplayName"] = source_display_name
        target["workspaceLabel"] = source_display_name
    elif source_app or target_workspace_path:
        target["workspaceLabel"] = _feedback_source_label(
            source_display_name=None,
            source_app=source_app,
            workspace_path=target_workspace_path,
        )
    if target_workspace_path:
        target["workspacePath"] = target_workspace_path
    return target


def _feedback_first_text(*values: object | None) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text and text.lower() != "unknown":
            return text
    return None


def _feedback_workspace_path_for_source(
    *,
    source_app: str | None,
    source_display_name: str | None,
    workspace_path: str | None,
    item_payloads: list[dict],
    container: AppContainer,
) -> str | None:
    explicit_workspace_path = (workspace_path or "").strip()
    if explicit_workspace_path:
        return _resolve_explicit_feedback_workspace_path(
            explicit_workspace_path,
            container=container,
        )

    candidates = [
        source_app,
        source_display_name,
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
        configured_workspace_path = aliases.get(candidate_key)
        if configured_workspace_path:
            workspace_path = _known_feedback_workspace_path(
                configured_workspace_path,
                container=container,
            )
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


def _resolve_explicit_feedback_workspace_path(
    workspace_path: str,
    *,
    container: AppContainer,
) -> str:
    known_workspace_path = _known_feedback_workspace_path(
        workspace_path,
        container=container,
    )
    if known_workspace_path:
        return known_workspace_path

    try:
        candidate = Path(workspace_path).expanduser()
        if not candidate.is_absolute():
            candidate = Path(container.settings.projects_root).expanduser() / candidate
        resolved_workspace_path = str(candidate.resolve())
    except (OSError, RuntimeError):
        return workspace_path

    known_workspace_path = _known_feedback_workspace_path(
        resolved_workspace_path,
        container=container,
    )
    return known_workspace_path or workspace_path


def _known_feedback_workspace_path(
    workspace_path: str,
    *,
    container: AppContainer,
) -> str | None:
    workspaces = container.message_service.list_workspaces()
    for workspace in workspaces:
        if workspace.path == workspace_path:
            return workspace.path

    try:
        candidate = Path(workspace_path).expanduser()
        if not candidate.is_absolute():
            candidate = Path(container.settings.projects_root).expanduser() / candidate
        resolved = candidate.resolve()
    except (OSError, RuntimeError):
        return None

    for workspace in workspaces:
        try:
            if Path(workspace.path).resolve() == resolved:
                return workspace.path
        except (OSError, RuntimeError):
            continue
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


def _feedback_context_note(context_metadata: dict[str, Any] | None) -> str:
    if not context_metadata:
        return ""
    return f"\nScreen/context metadata: {context_metadata}"


_FEEDBACK_PROMPT_BINARY_KEYS = {
    "audiobase64",
    "audio_base64",
    "base64",
    "bytesbase64",
    "bytes_base64",
    "dataurl",
    "data_url",
    "screenshotpngbase64",
    "screenshot_png_base64",
}
_FEEDBACK_PROMPT_MAX_LIST_ITEMS = 50
_FEEDBACK_PROMPT_MAX_STRING_CHARS = 2000


def _feedback_prompt_safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, nested_value in value.items():
            key_text = str(key)
            normalized_key = key_text.replace("-", "_").lower()
            if normalized_key in _FEEDBACK_PROMPT_BINARY_KEYS:
                safe[key_text] = (
                    f"<omitted binary payload; "
                    f"{len(str(nested_value or ''))} encoded chars>"
                )
                continue
            safe[key_text] = _feedback_prompt_safe_value(nested_value)
        return safe
    if isinstance(value, list):
        safe_items = [
            _feedback_prompt_safe_value(item)
            for item in value[:_FEEDBACK_PROMPT_MAX_LIST_ITEMS]
        ]
        omitted_count = len(value) - len(safe_items)
        if omitted_count > 0:
            safe_items.append({"omittedItems": omitted_count})
        return safe_items
    if isinstance(value, str) and len(value) > _FEEDBACK_PROMPT_MAX_STRING_CHARS:
        return (
            value[:_FEEDBACK_PROMPT_MAX_STRING_CHARS]
            + f"... <truncated; {len(value)} chars total>"
        )
    return value


def _feedback_live_feedback_note(item) -> str:
    parts: list[str] = []
    if item.feedback_kind:
        parts.append(f"Feedback contract: {item.feedback_kind}")
    if item.image_capture:
        parts.append(
            "Image capture schema: "
            + json.dumps(
                _feedback_prompt_safe_value(item.image_capture),
                ensure_ascii=False,
                default=str,
            )
        )
    if item.guided_trace:
        parts.append(
            "Guided trace schema: "
            + json.dumps(
                _feedback_prompt_safe_value(item.guided_trace),
                ensure_ascii=False,
                default=str,
            )
        )
    if not parts:
        return ""
    return "\n" + "\n".join(parts)


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
        return f"{audio_note}\nAudio transcript unavailable; using audio metadata only."
    except AudioTranscriptionError as exc:
        return (
            f"{audio_note}\nAudio transcript failed: {exc}; using audio metadata only."
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
    notification_unread = bool(
        record.notification_created_at and not record.notification_read_at
    )
    return FeedbackBatchStatusResponse(
        batch_id=record.id,
        batchId=record.id,
        source_app=record.source_app,
        source_display_name=record.source_display_name,
        status=status,
        workflowStatus=status,
        status_detail=status_detail,
        workflow_preset_id=record.workflow_preset_id,
        workflowPresetId=record.workflow_preset_id,
        release_when_complete=record.release_when_complete,
        releaseWhenComplete=record.release_when_complete,
        item_count=record.item_count,
        itemCount=record.item_count,
        item_ids=record.item_ids,
        job_id=record.job_id,
        jobId=record.job_id,
        session_id=record.session_id,
        sessionId=record.session_id,
        run_id=job.run_id if job else None,
        runId=job.run_id if job else None,
        workspace_path=record.workspace_path,
        release_target=record.release_target,
        releaseTarget=record.release_target,
        quick_ask_id=record.quick_ask_id,
        quickAskId=record.quick_ask_id,
        job_status=job.status if job else None,
        summary=summary,
        finalSummary=summary,
        summary_generated_at=record.summary_generated_at,
        summary_line_count=_non_empty_line_count(summary),
        notification_created_at=record.notification_created_at,
        notification_read_at=record.notification_read_at,
        notification_unread=notification_unread,
        notificationUnread=notification_unread,
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


def _quick_ask_implementation_comment(record) -> str:
    answer = (record.answer or "").strip()
    lines = [
        f"Act from quick ask {record.id}.",
        f"Question: {record.question}",
    ]
    if answer:
        lines.append(f"Prior quick ask answer: {answer}")
    return "\n".join(lines)


def _quick_ask_batch_context(record) -> str:
    answer = (record.answer or "").strip() or "not answered yet"
    return (
        "Quick ask provenance for this implementation batch:\n"
        f"- Quick ask id: {record.id}\n"
        f"- Original question: {record.question}\n"
        f"- Prior answer: {answer}\n"
        f"- Original selection bounds: {record.selection_bounds}\n"
        f"- Original screen/context metadata: {record.context_metadata}\n\n"
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


def _feedback_image_value(payload: dict[str, Any], *keys: str) -> str:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return str(current or "").strip()


def _feedback_trace_frame_image(payload: dict[str, Any]) -> str:
    trace = payload.get("guidedTrace") or payload.get("guided_trace") or {}
    if not isinstance(trace, dict):
        return ""
    frames = trace.get("frames") or []
    if not isinstance(frames, list):
        return ""
    for frame in reversed(frames):
        if not isinstance(frame, dict):
            continue
        screenshot = str(
            frame.get("screenshotPngBase64") or frame.get("screenshot_png_base64") or ""
        ).strip()
        if screenshot:
            return screenshot
    return ""


def _ensure_feedback_batch_image(payload: dict[str, Any], *, item_index: int) -> None:
    screenshot = str(
        payload.get("screenshotPngBase64") or payload.get("screenshot_png_base64") or ""
    ).strip()
    if screenshot:
        _validate_feedback_base64(
            screenshot,
            field_name="screenshotPngBase64",
            item_index=item_index,
        )
        payload["screenshotPngBase64"] = screenshot
        return

    derived_screenshot = (
        _feedback_image_value(payload, "imageCapture", "screenshotPngBase64")
        or _feedback_image_value(payload, "image_capture", "screenshot_png_base64")
        or _feedback_image_value(
            payload,
            "imageCapture",
            "screenshot",
            "screenshotPngBase64",
        )
        or _feedback_image_value(
            payload,
            "image_capture",
            "screenshot",
            "screenshot_png_base64",
        )
        or _feedback_trace_frame_image(payload)
    )
    if derived_screenshot:
        _validate_feedback_base64(
            derived_screenshot,
            field_name="derived screenshot",
            item_index=item_index,
        )
        payload["screenshotPngBase64"] = derived_screenshot
        payload.setdefault("screenshotMimeType", "image/png")
        return

    payload["screenshotPngBase64"] = _TRANSPARENT_PNG_BASE64
    payload.setdefault("screenshotMimeType", "image/png")


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
        _feedback_item_response(item, include_image=include_images) for item in items
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
        f"{_feedback_context_note(item.context_metadata)}"
        f"{_feedback_live_feedback_note(item)}"
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
        await run_in_threadpool(
            container.feedback_queue_service.mark_submitted, item_id
        )
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
    quick_ask_record = None
    if payload.quick_ask_id:
        try:
            quick_ask_record = await run_in_threadpool(
                container.feedback_queue_service.get_quick_ask,
                payload.quick_ask_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Quick ask not found.") from exc
    quick_ask_item_payload = None
    if quick_ask_record is not None and not payload.items:
        screenshot_base64 = _quick_ask_screenshot_base64(quick_ask_record)
        if not screenshot_base64:
            raise HTTPException(
                status_code=422,
                detail="Quick ask screenshot is missing.",
            )
        quick_ask_item_payload = {
            "id": f"{quick_ask_record.id}-implementation",
            "sourceApp": quick_ask_record.source_app,
            "sourceDisplayName": quick_ask_record.source_display_name,
            "comment": _quick_ask_implementation_comment(quick_ask_record),
            "screenshotMimeType": quick_ask_record.screenshot_mime_type,
            "screenshotPngBase64": screenshot_base64,
            "selectionPoints": quick_ask_record.selection_points,
            "selectionBounds": quick_ask_record.selection_bounds,
            "contextMetadata": quick_ask_record.context_metadata,
        }
    if not payload.items:
        if quick_ask_item_payload is None:
            raise HTTPException(status_code=422, detail="Feedback batch has no items.")
    preset = _feedback_preset_by_id(
        payload.workflow_preset_id,
        service=container.message_service,
    )
    if preset is None:
        raise HTTPException(status_code=422, detail="Unknown feedback workflow preset.")

    item_payloads = []
    raw_item_payloads = (
        [quick_ask_item_payload]
        if quick_ask_item_payload is not None
        else [
            item.model_dump(by_alias=False, exclude_none=True) for item in payload.items
        ]
    )
    for index, item_payload in enumerate(raw_item_payloads, start=1):
        _ensure_feedback_batch_image(item_payload, item_index=index)
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
    release_target = _feedback_batch_release_target(
        payload,
        item_payloads=item_payloads,
        workspace_path=workspace_path,
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
            await run_in_threadpool(
                container.feedback_queue_service.delete_item, item.id
            )
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
            await run_in_threadpool(
                container.feedback_queue_service.delete_item, item.id
            )
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
                f"{_feedback_context_note(item.context_metadata)}"
                f"{_feedback_live_feedback_note(item)}"
                f"{audio_note}"
            )
        release_note = (
            _feedback_release_instruction(includes_reviewer=preset.includes_reviewer)
            if payload.release_when_complete
            else ""
        )
        release_target_note = _feedback_release_target_note(release_target)
        quick_ask_context = (
            _quick_ask_batch_context(quick_ask_record)
            if quick_ask_record is not None
            else ""
        )
        message = payload.message or (
            f"Use these {source_label} feedback screenshots and notes as one "
            "batch to make the requested UI/app changes.\n\n"
            f"Run target: {_feedback_target_instruction(preset.target_mode)}\n"
            f"Workflow preset: {preset.name}\n"
            f"Batch size: {len(stored_items)} feedback items.\n\n"
            f"{release_target_note}"
            f"{quick_ask_context}" + "\n\n".join(item_sections) + release_note
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
            batch_id=payload.batch_id,
            source_app=payload.sourceApp or first_item.source_app,
            source_display_name=payload.sourceDisplayName
            or first_item.source_display_name,
            workflow_preset_id=payload.workflow_preset_id,
            release_when_complete=payload.release_when_complete,
            items=stored_items,
            job_id=job.id,
            session_id=job.session_id,
            workspace_path=workspace_path,
            release_target=release_target,
            message=message,
            quick_ask_id=payload.quick_ask_id,
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
        source_app=batch_record.source_app,
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
        raise HTTPException(
            status_code=404, detail="Feedback batch not found."
        ) from exc

    return await _feedback_batch_status_response(record, container=container)


@router.patch(
    "/feedback-batches/{batch_id}/notification",
    response_model=FeedbackBatchStatusResponse,
)
async def update_feedback_batch_notification(
    batch_id: str,
    read: bool = True,
    container: AppContainer = Depends(get_container),
) -> FeedbackBatchStatusResponse:
    try:
        record = await run_in_threadpool(
            container.feedback_queue_service.mark_batch_notification_read,
            batch_id,
            read=read,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail="Feedback batch not found."
        ) from exc

    return await _feedback_batch_status_response(record, container=container)


@router.post(
    "/feedback-quick-asks/ask",
    response_model=FeedbackQuickAskAcceptedResponse,
    status_code=202,
)
async def ask_feedback_quick_question(
    payload: FeedbackQuickAskRequest,
    container: AppContainer = Depends(get_container),
) -> FeedbackQuickAskAcceptedResponse:
    _validate_feedback_base64(
        payload.screenshotPngBase64,
        field_name="screenshotPngBase64",
        item_index=1,
    )
    workspace_path = _feedback_workspace_path_for_source(
        source_app=payload.sourceApp,
        source_display_name=payload.sourceDisplayName,
        workspace_path=payload.workspace_path,
        item_payloads=[],
        container=container,
    )
    source_label = _feedback_source_label(
        source_display_name=payload.sourceDisplayName,
        source_app=payload.sourceApp,
        workspace_path=workspace_path,
    )
    message = _feedback_quick_ask_prompt(
        source_label=source_label,
        question=payload.question,
        selection_bounds=payload.selectionBounds,
        context_metadata=payload.contextMetadata,
    )
    suffix = _IMAGE_CONTENT_TYPE_SUFFIXES.get(payload.screenshotMimeType, ".png")
    temp_image_path: Path | None = None
    should_cleanup_temp_image = True
    try:
        with NamedTemporaryFile(delete=False, suffix=suffix) as temp_image:
            temp_image.write(base64.b64decode(payload.screenshotPngBase64))
            temp_image_path = Path(temp_image.name)
        codex_options = await _validate_codex_options(
            payload.codex_options.to_domain()
            if payload.codex_options is not None
            else None,
            container=container,
        )
        job = await run_in_threadpool(
            container.message_service.submit_attachment_message,
            [
                AttachmentInput(
                    path=str(temp_image_path),
                    filename=f"quick-ask{suffix}",
                    content_type=payload.screenshotMimeType,
                )
            ],
            message=message,
            session_id=payload.session_id,
            workspace_path=workspace_path,
            codex_options=codex_options,
        )
        should_cleanup_temp_image = False
        record = await run_in_threadpool(
            container.feedback_queue_service.create_quick_ask_record,
            quick_ask_id=None,
            source_app=payload.sourceApp,
            source_display_name=payload.sourceDisplayName,
            question=payload.question,
            screenshot_mime_type=payload.screenshotMimeType,
            screenshot_png_base64=payload.screenshotPngBase64,
            selection_points=[point.model_dump() for point in payload.selectionPoints],
            selection_bounds=payload.selectionBounds,
            context_metadata=payload.contextMetadata,
            job_id=job.id,
            session_id=job.session_id,
            workspace_path=workspace_path,
            message=message,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    finally:
        if should_cleanup_temp_image and temp_image_path is not None:
            temp_image_path.unlink(missing_ok=True)

    return FeedbackQuickAskAcceptedResponse.from_domain(
        job,
        quick_ask_id=record.id,
    )


@router.get(
    "/feedback-quick-asks",
    response_model=list[FeedbackQuickAskResponse],
)
async def list_feedback_quick_asks(
    source_app: str | None = Query(default=None, alias="sourceApp"),
    container: AppContainer = Depends(get_container),
) -> list[FeedbackQuickAskResponse]:
    records = await run_in_threadpool(
        container.feedback_queue_service.list_quick_asks,
        source_app=source_app,
    )
    return [
        await _feedback_quick_ask_response(record, container=container)
        for record in records
    ]


@router.get(
    "/feedback-quick-asks/{quick_ask_id}",
    response_model=FeedbackQuickAskResponse,
)
async def get_feedback_quick_ask(
    quick_ask_id: str,
    container: AppContainer = Depends(get_container),
) -> FeedbackQuickAskResponse:
    try:
        record = await run_in_threadpool(
            container.feedback_queue_service.get_quick_ask,
            quick_ask_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Quick ask not found.") from exc

    return await _feedback_quick_ask_response(
        record,
        container=container,
        include_screenshot=True,
    )


def _feedback_quick_ask_prompt(
    *,
    source_label: str,
    question: str,
    selection_bounds: dict[str, float],
    context_metadata: dict[str, Any],
) -> str:
    return (
        f"Quick ask about a selected {source_label} screen area.\n\n"
        "Answer-only instructions:\n"
        "- Do not edit files.\n"
        "- Do not implement changes.\n"
        "- Do not run commands or tools that modify files.\n"
        "- Explain what may be happening.\n"
        "- Be concise but useful.\n"
        "- Suggest likely causes.\n"
        "- Suggest possible next steps without executing them.\n\n"
        f"Question: {question}\n"
        f"Selection bounds: {selection_bounds}"
        f"{_feedback_context_note(context_metadata)}"
    )


async def _feedback_quick_ask_response(
    record,
    *,
    container: AppContainer,
    include_screenshot: bool = False,
) -> FeedbackQuickAskResponse:
    job: Job | None = None
    status = "pending"
    status_detail: str | None = None
    answer = record.answer
    answered_at = record.answered_at
    run_id: str | None = None
    if record.job_id:
        job = await run_in_threadpool(container.message_service.get_job, record.job_id)
        if job is None:
            status = "failed"
            status_detail = "Linked job was not found."
        elif job.status == JobStatus.COMPLETED:
            status = "completed"
            answer = job.response or answer
            run_id = job.run_id
            if answer and answer != record.answer:
                record = await run_in_threadpool(
                    container.feedback_queue_service.set_quick_ask_answer,
                    record.id,
                    answer,
                )
                answered_at = record.answered_at
        elif job.status == JobStatus.FAILED:
            status = "failed"
            status_detail = job.error or "Quick ask failed."
            run_id = job.run_id
        else:
            status = "running"
            run_id = job.run_id
    return FeedbackQuickAskResponse(
        quick_ask_id=record.id,
        quickAskId=record.id,
        source_app=record.source_app,
        source_display_name=record.source_display_name,
        question=record.question,
        status=status,
        status_detail=status_detail,
        answer=answer,
        answered_at=answered_at,
        screenshot_mime_type=record.screenshot_mime_type,
        has_screenshot=record.screenshot_file is not None,
        screenshot_png_base64=_quick_ask_screenshot_base64(record)
        if include_screenshot
        else None,
        selection_points=record.selection_points,
        selection_bounds=record.selection_bounds,
        context_metadata=record.context_metadata,
        job_id=record.job_id,
        jobId=record.job_id,
        session_id=record.session_id,
        sessionId=record.session_id,
        run_id=run_id,
        runId=run_id,
        workspace_path=record.workspace_path,
        provenance={
            "quickAskId": record.id,
            "sourceApp": record.source_app,
            "sourceDisplayName": record.source_display_name,
            "selectionPoints": record.selection_points,
            "selectionBounds": record.selection_bounds,
            "contextMetadata": record.context_metadata,
            "jobId": record.job_id,
            "sessionId": record.session_id,
            "runId": run_id,
            "createdAt": record.created_at,
        },
        created_at=record.created_at,
    )


def _quick_ask_screenshot_base64(record) -> str | None:
    if not record.screenshot_file:
        return None
    path = Path(record.screenshot_file)
    if not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _feedback_release_target_note(release_target: dict[str, Any]) -> str:
    if not release_target:
        return ""
    source_app = str(release_target.get("sourceApp") or "").strip()
    workspace_path = str(release_target.get("workspacePath") or "").strip()
    workspace_label = str(release_target.get("workspaceLabel") or "").strip()
    if not source_app and not workspace_path and not workspace_label:
        return ""
    lines = ["Delivery/release target context:"]
    if source_app:
        lines.append(f"- source_app: {source_app}")
    if workspace_label:
        lines.append(f"- workspace_label: {workspace_label}")
    if workspace_path:
        lines.append(f"- workspace_path: {workspace_path}")
    lines.append(
        "- Use this as the app/repo that should consume shared Workbench changes "
        "and receive any requested release; executionTarget/workspace_path only "
        "selects where Codex runs."
    )
    return "\n".join(lines) + "\n\n"


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
    repo_root = (
        Path(workspace_path).resolve()
        if workspace_path
        else Path(container.settings.codex_workdir).resolve()
    )
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


@router.post(
    "/message/audio", response_model=AudioMessageAcceptedResponse, status_code=202
)
async def post_audio_message(
    audio: UploadFile = File(...),
    message: str | None = Form(default=None),
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
            message=message,
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


@router.post(
    "/message/image", response_model=ImageMessageAcceptedResponse, status_code=202
)
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


@router.post(
    "/message/document", response_model=DocumentMessageAcceptedResponse, status_code=202
)
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


@router.post(
    "/message/attachments", response_model=MessageAcceptedResponse, status_code=202
)
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
    return [AgentProfileResponse.from_domain(profile) for profile in profiles]


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
    before: str | None = Query(default=None),
    limit: int = Query(default=40, ge=1, le=200),
    transcript: str = Query(default="full"),
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
    try:
        transcript_window = service.get_transcript_window(
            session_id,
            before=before,
            limit=limit,
            full=transcript == "full" and before is None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SessionDetailResponse.from_domain(
        refreshed_session,
        messages=transcript_window.messages,
        metadata_messages=messages,
        transcript_window=transcript_window,
        turn_summaries=service.list_turn_summaries(session_id),
        jobs_by_id=jobs_by_id,
        run_configurations_by_id=_run_configurations_by_id_for_session(
            service, session_id
        ),
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
        run_configurations_by_id=_run_configurations_by_id_for_session(
            service, session_id
        ),
    )


@router.put("/sessions/{session_id}/title", response_model=SessionDetailResponse)
async def rename_session(
    session_id: str,
    payload: RenameSessionRequest,
    service: MessageService = Depends(get_message_service),
) -> SessionDetailResponse:
    try:
        session = await run_in_threadpool(
            service.rename_session,
            session_id=session_id,
            title=payload.title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    messages = service.list_messages(session_id)
    return SessionDetailResponse.from_domain(
        session,
        messages=messages,
        turn_summaries=service.list_turn_summaries(session_id),
        jobs_by_id=_jobs_by_id_for_messages(service, messages),
        run_configurations_by_id=_run_configurations_by_id_for_session(
            service, session_id
        ),
    )


@router.post(
    "/sessions/{session_id}/title/generate", response_model=SessionDetailResponse
)
async def generate_session_title(
    session_id: str,
    payload: GenerateSessionTitleRequest,
    service: MessageService = Depends(get_message_service),
) -> SessionDetailResponse:
    try:
        session = await run_in_threadpool(
            service.generate_session_title,
            session_id=session_id,
            instructions=payload.instructions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    messages = service.list_messages(session_id)
    return SessionDetailResponse.from_domain(
        session,
        messages=messages,
        turn_summaries=service.list_turn_summaries(session_id),
        jobs_by_id=_jobs_by_id_for_messages(service, messages),
        run_configurations_by_id=_run_configurations_by_id_for_session(
            service, session_id
        ),
    )


@router.post(
    "/sessions/{session_id}/title/generate/audio",
    response_model=SessionDetailResponse,
)
async def generate_session_title_from_audio(
    session_id: str,
    audio: UploadFile = File(...),
    instructions: str | None = Form(default=None),
    language: str | None = Form(default=None),
    service: MessageService = Depends(get_message_service),
    container: AppContainer = Depends(get_container),
) -> SessionDetailResponse:
    temp_path = await _store_uploaded_audio(
        audio,
        max_bytes=container.settings.audio_max_upload_bytes,
    )

    try:
        session, _transcript = await run_in_threadpool(
            service.generate_session_title_from_audio,
            str(temp_path),
            session_id=session_id,
            filename=audio.filename or temp_path.name,
            content_type=audio.content_type,
            instructions=instructions,
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

    messages = service.list_messages(session_id)
    return SessionDetailResponse.from_domain(
        session,
        messages=messages,
        turn_summaries=service.list_turn_summaries(session_id),
        jobs_by_id=_jobs_by_id_for_messages(service, messages),
        run_configurations_by_id=_run_configurations_by_id_for_session(
            service, session_id
        ),
    )


@router.post(
    "/sessions/{session_id}/messages",
    response_model=MessageAcceptedResponse,
    status_code=202,
)
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
        container.dev_pipeline_service.validate_stage_session_execution(
            session_id=session_id,
            workspace_path=payload.workspace_path,
            backend_url=container.settings.api_base_url,
        )
    except DevPipelineError as exc:
        _raise_dev_pipeline_error(exc)
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


@router.post(
    "/sessions/{session_id}/domain-factory/start",
    response_model=DomainFactoryStartResponse,
)
async def start_domain_factory_mode(
    session_id: str,
    payload: DomainFactoryStartRequest,
    service: MessageService = Depends(get_message_service),
    container: AppContainer = Depends(get_container),
) -> DomainFactoryStartResponse:
    try:
        result = await run_in_threadpool(
            container.domain_factory_service.start,
            session_id=session_id,
            workspace_path=payload.workspace_path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    messages = service.list_messages(session_id)
    payload_data = result.to_payload()
    return DomainFactoryStartResponse(
        **payload_data,
        session=SessionDetailResponse.from_domain(
            result.session,
            messages=messages,
            turn_summaries=service.list_turn_summaries(session_id),
            jobs_by_id=_jobs_by_id_for_messages(service, messages),
            run_configurations_by_id=_run_configurations_by_id_for_session(
                service, session_id
            ),
        ),
    )


@router.post(
    "/sessions/{session_id}/domain-factory/intake",
    response_model=DomainFactoryIntakeResponse,
)
async def submit_domain_factory_intake(
    session_id: str,
    payload: DomainFactoryIntakeRequest,
    service: MessageService = Depends(get_message_service),
    container: AppContainer = Depends(get_container),
) -> DomainFactoryIntakeResponse:
    try:
        result = await run_in_threadpool(
            container.domain_factory_service.submit_intake,
            session_id=session_id,
            brief=payload.brief,
            media_references=tuple(
                item.model_dump(by_alias=True, exclude_none=True)
                for item in payload.media_references
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    messages = service.list_messages(session_id)
    return DomainFactoryIntakeResponse(
        **result.to_payload(),
        session=SessionDetailResponse.from_domain(
            result.session,
            messages=messages,
            turn_summaries=service.list_turn_summaries(session_id),
            jobs_by_id=_jobs_by_id_for_messages(service, messages),
            run_configurations_by_id=_run_configurations_by_id_for_session(
                service, session_id
            ),
        ),
    )


@router.post(
    "/sessions/{session_id}/domain-factory/implementation/confirm",
    response_model=DomainFactoryImplementationResponse,
)
async def confirm_domain_factory_implementation(
    session_id: str,
    service: MessageService = Depends(get_message_service),
    container: AppContainer = Depends(get_container),
) -> DomainFactoryImplementationResponse:
    try:
        result = await run_in_threadpool(
            container.domain_factory_service.confirm_implementation,
            session_id=session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    messages = service.list_messages(session_id)
    return DomainFactoryImplementationResponse(
        **result.to_payload(),
        session=SessionDetailResponse.from_domain(
            result.session,
            messages=messages,
            turn_summaries=service.list_turn_summaries(session_id),
            jobs_by_id=_jobs_by_id_for_messages(service, messages),
            run_configurations_by_id=_run_configurations_by_id_for_session(
                service, session_id
            ),
        ),
    )


@router.get(
    "/sessions/{session_id}/domain-factory/completion-evidence",
    response_model=DomainFactoryCompletionEvidenceResponse,
)
async def domain_factory_completion_evidence(
    session_id: str,
    container: AppContainer = Depends(get_container),
) -> DomainFactoryCompletionEvidenceResponse:
    try:
        payload = await run_in_threadpool(
            container.domain_factory_service.validate_completion_evidence,
            session_id=session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return DomainFactoryCompletionEvidenceResponse(**payload)


@router.post(
    "/domain-factory/release-evidence/validate",
    response_model=DomainFactoryReleaseEvidenceValidationResponse,
)
async def validate_domain_factory_release_evidence(
    payload: DomainFactoryReleaseEvidenceValidationRequest,
    container: AppContainer = Depends(get_container),
) -> DomainFactoryReleaseEvidenceValidationResponse:
    result = await run_in_threadpool(
        container.domain_factory_service.validate_release_evidence,
        source_app=payload.source_app,
        evidence=payload.evidence,
        initial_build=payload.initial_build,
    )
    return DomainFactoryReleaseEvidenceValidationResponse(**result)


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
        run_configurations_by_id=_run_configurations_by_id_for_session(
            service, session_id
        ),
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
        run_configurations_by_id=_run_configurations_by_id_for_session(
            service, session_id
        ),
    )


@router.put(
    "/sessions/{session_id}/agent-profile", response_model=SessionDetailResponse
)
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
        run_configurations_by_id=_run_configurations_by_id_for_session(
            service, session_id
        ),
    )


@router.put(
    "/sessions/{session_id}/turn-summaries", response_model=SessionDetailResponse
)
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
        run_configurations_by_id=_run_configurations_by_id_for_session(
            service, session_id
        ),
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
    except MaintenanceModeError:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    messages = service.list_messages(session_id)
    return SessionDetailResponse.from_domain(
        session,
        messages=messages,
        turn_summaries=service.list_turn_summaries(session_id),
        jobs_by_id=_jobs_by_id_for_messages(service, messages),
        run_configurations_by_id=_run_configurations_by_id_for_session(
            service, session_id
        ),
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
    except MaintenanceModeError:
        raise
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
        release_channel=result.release_channel,
        release_prerelease=result.release_prerelease,
        private_install=result.private_install,
        package_id=result.package_id,
        required=result.required,
        available=result.available,
    )


async def _installable_app_for_config(
    *,
    request: Request,
    config: AppUpdateConfig,
    platform: str,
    channel: str,
    container: AppContainer,
) -> InstallableAppResponse:
    if not config.enabled:
        return _installable_app_response_from_config(
            config,
            enabled=False,
            install_status_hint="disabled",
        )
    try:
        result = await run_in_threadpool(
            container.app_update_service.check_update,
            source_app=config.source_app,
            platform=platform,
            current_version="0.0.0",
            current_build=0,
            channel=channel,
        )
    except AppDisabledError:
        return _installable_app_response_from_config(
            config,
            enabled=False,
            install_status_hint="disabled",
        )
    except GitHubReleaseError:
        return _installable_app_response_from_config(
            config,
            enabled=True,
            install_status_hint="release_metadata_unavailable",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    apk_url = None
    install_status_hint = "available" if result.available else "no_release_available"
    response_channel = result.release_channel or channel
    if result.available and result.release_tag and result.apk_asset_name:
        apk_url = _app_update_apk_proxy_url(
            request=request,
            container=container,
            source_app=result.source_app,
            release_tag=result.release_tag,
            asset_name=result.apk_asset_name,
            platform=platform,
            channel=response_channel,
        )
    elif result.release_tag and not result.apk_asset_name:
        install_status_hint = "missing_apk_asset"

    return InstallableAppResponse(
        source_app=result.source_app,
        display_name=result.display_name or config.display_name,
        repo=config.repo,
        release_channel=result.release_channel,
        release_tag_pattern=config.release_tag_pattern,
        apk_asset_pattern=config.apk_asset_pattern,
        latest_asset_name=config.latest_asset_name,
        latest_version=result.latest_version,
        latest_build=result.latest_build,
        release_tag=result.release_tag,
        apk_url=apk_url,
        apk_asset_name=result.apk_asset_name,
        size_bytes=result.size_bytes,
        sha256=result.sha256,
        available=bool(apk_url),
        enabled=True,
        package_id=result.package_id or config.expected_package_id,
        install_status_hint=install_status_hint,
        preview_url=config.preview_url,
        runtime_profile=config.runtime_profile,
        production_ready=config.production_ready,
        mock_or_demo=config.mock_or_demo,
        release_metadata=config.release_metadata or {},
    )


def _installable_app_response_from_config(
    config: AppUpdateConfig,
    *,
    enabled: bool,
    install_status_hint: str,
) -> InstallableAppResponse:
    return InstallableAppResponse(
        source_app=config.source_app,
        display_name=config.display_name,
        repo=config.repo,
        release_channel=config.release_channel,
        release_tag_pattern=config.release_tag_pattern,
        apk_asset_pattern=config.apk_asset_pattern,
        latest_asset_name=config.latest_asset_name,
        latest_version=None,
        latest_build=None,
        release_tag=None,
        apk_url=None,
        apk_asset_name=None,
        size_bytes=None,
        sha256=None,
        available=False,
        enabled=enabled,
        package_id=config.expected_package_id,
        install_status_hint=install_status_hint,
        preview_url=config.preview_url,
        runtime_profile=config.runtime_profile,
        production_ready=config.production_ready,
        mock_or_demo=config.mock_or_demo,
        release_metadata=config.release_metadata or {},
    )


def _authorize_installable_app_registration(
    *,
    container: AppContainer,
    authorization: str | None,
    registration_token: str | None,
) -> None:
    expected = (container.settings.installable_apps_registration_token or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "installable_app_registration_disabled",
                "message": "Installable app registration token is not configured.",
            },
        )
    provided = (registration_token or "").strip()
    if not provided and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer":
            provided = value.strip()
    if not provided:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "missing_registration_token",
                "message": "Registration token is required.",
            },
        )
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "invalid_registration_token",
                "message": "Registration token is invalid.",
            },
        )


def _web_preview_http_error(exc: WebPreviewError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
        },
    )


def _web_preview_invite_http_error(exc: WebPreviewInviteError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
        },
    )


async def _web_preview_response(
    payload: dict[str, Any],
    container: AppContainer,
) -> WebPreviewResponse:
    email_preflight = await run_in_threadpool(
        container.web_preview_invite_service.email_delivery_preflight,
    )
    return WebPreviewResponse(**{**payload, "invite_email_delivery": email_preflight})


def _preserve_api_v1_prefix(request: Request, url: str) -> str:
    if not request.url.path.startswith("/api/v1/"):
        return url
    origin = str(request.base_url).rstrip("/")
    root_path = f"{origin}/app-updates/"
    if url.startswith(root_path):
        return f"{origin}/api/v1/app-updates/{url[len(root_path) :]}"
    return url


def _app_update_apk_proxy_url(
    *,
    request: Request,
    container: AppContainer,
    source_app: str,
    release_tag: str,
    asset_name: str,
    platform: str,
    channel: str,
) -> str:
    generated_apk_url = request.url_for(
        "download_app_update_apk",
        source_app=source_app,
        release_tag=release_tag,
        asset_name=asset_name,
    ).include_query_params(platform=platform, channel=channel)
    apk_url = _preserve_api_v1_prefix(request, str(generated_apk_url))
    public_base_url = (container.settings.app_update_public_base_url or "").strip()
    if not public_base_url or not _should_use_public_app_update_base(request):
        return apk_url
    return _replace_url_origin(apk_url, public_base_url)


def _should_use_public_app_update_base(request: Request) -> bool:
    host = (request.url.hostname or "").strip().lower()
    return host in {
        "",
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "10.0.2.2",
        "::1",
        "testserver",
    }


def _replace_url_origin(url: str, public_base_url: str) -> str:
    parsed_url = urlsplit(url)
    parsed_base = urlsplit(public_base_url)
    if not parsed_base.scheme or not parsed_base.netloc:
        return url
    return urlunsplit(
        (
            parsed_base.scheme,
            parsed_base.netloc,
            parsed_url.path,
            parsed_url.query,
            parsed_url.fragment,
        )
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


def _project_factory_manifest_input(
    request: ProjectFactoryDraftRequest,
) -> ProjectFactoryManifestInput:
    return ProjectFactoryManifestInput(
        name=request.name,
        business_type=request.business_type,
        primary_goal=request.primary_goal,
        slug=request.slug,
        platforms=tuple(request.platforms),
        backend=request.backend,
        frontend_strategy=request.frontend_strategy,
        logo_mode=request.logo_mode,
        first_release_mode=request.first_release_mode,
        initial_admin_emails=tuple(request.initial_admin_emails),
        visual_reference_paths=tuple(request.visual_reference_paths),
        guided_intake_enabled=request.guided_intake_enabled,
    )


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


def _project_factory_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "new-project"


def _parse_codex_options_json(raw_json: str | None):
    if raw_json is None or not raw_json.strip():
        return None
    try:
        return CodexRunOptionsRequest.model_validate_json(raw_json).to_domain()
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"Invalid codex_options_json: {exc}"
        ) from exc


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
        joined = "; ".join(f"`{issue.server_id}` {issue.reason}" for issue in issues)
        raise HTTPException(
            status_code=422,
            detail=f"Rejected MCP server selections: {joined}",
        )
    return codex_options
