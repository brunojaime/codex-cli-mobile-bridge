from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from backend.app.domain.entities.chat_message import (
    ChatMessage,
    ChatMessageRole,
    ChatMessageStatus,
)
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.job import Job, JobStatus


class MessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: str | None = None
    workspace_path: str | None = None


class CreateSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    workspace_path: str | None = None


class MessageAcceptedResponse(BaseModel):
    job_id: str
    session_id: str
    status: JobStatus
    provider_session_id: str | None = None

    @classmethod
    def from_domain(cls, job: Job) -> "MessageAcceptedResponse":
        return cls(
            job_id=job.id,
            session_id=job.session_id,
            status=job.status,
            provider_session_id=job.provider_session_id,
        )


class AudioMessageAcceptedResponse(MessageAcceptedResponse):
    transcript: str

    @classmethod
    def from_domain(
        cls,
        job: Job,
        *,
        transcript: str,
    ) -> "AudioMessageAcceptedResponse":
        return cls(
            job_id=job.id,
            session_id=job.session_id,
            status=job.status,
            provider_session_id=job.provider_session_id,
            transcript=transcript,
        )


class ImageMessageAcceptedResponse(MessageAcceptedResponse):
    attached_image_name: str

    @classmethod
    def from_domain(
        cls,
        job: Job,
        *,
        attached_image_name: str,
    ) -> "ImageMessageAcceptedResponse":
        return cls(
            job_id=job.id,
            session_id=job.session_id,
            status=job.status,
            provider_session_id=job.provider_session_id,
            attached_image_name=attached_image_name,
        )


class DocumentMessageAcceptedResponse(MessageAcceptedResponse):
    attached_document_name: str
    document_kind: str
    transcript: str | None = None
    extracted_text_preview: str | None = None

    @classmethod
    def from_domain(
        cls,
        job: Job,
        *,
        attached_document_name: str,
        document_kind: str,
        transcript: str | None = None,
        extracted_text_preview: str | None = None,
    ) -> "DocumentMessageAcceptedResponse":
        return cls(
            job_id=job.id,
            session_id=job.session_id,
            status=job.status,
            provider_session_id=job.provider_session_id,
            attached_document_name=attached_document_name,
            document_kind=document_kind,
            transcript=transcript,
            extracted_text_preview=extracted_text_preview,
        )


class ChatMessageResponse(BaseModel):
    id: str
    role: ChatMessageRole
    content: str
    status: ChatMessageStatus
    created_at: datetime
    updated_at: datetime
    job_id: str | None = None
    job_status: JobStatus | None = None
    job_phase: str | None = None
    job_latest_activity: str | None = None
    job_elapsed_seconds: int | None = None
    provider_session_id: str | None = None
    completed_at: datetime | None = None

    @classmethod
    def from_domain(
        cls,
        message: ChatMessage,
        *,
        job: Job | None = None,
    ) -> "ChatMessageResponse":
        return cls(
            id=message.id,
            role=message.role,
            content=message.content,
            status=message.status,
            created_at=message.created_at,
            updated_at=message.updated_at,
            job_id=message.job_id,
            job_status=job.status if job else None,
            job_phase=job.phase if job else None,
            job_latest_activity=job.latest_activity if job else None,
            job_elapsed_seconds=job.elapsed_seconds if job else None,
            provider_session_id=job.provider_session_id if job else None,
            completed_at=job.completed_at if job else None,
        )


class SessionSummaryResponse(BaseModel):
    id: str
    title: str
    workspace_path: str
    workspace_name: str
    provider_session_id: str | None = None
    created_at: datetime
    updated_at: datetime
    last_message_preview: str | None = None
    has_pending_messages: bool = False


class SessionDetailResponse(BaseModel):
    id: str
    title: str
    workspace_path: str
    workspace_name: str
    provider_session_id: str | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageResponse]

    @classmethod
    def from_domain(
        cls,
        session: ChatSession,
        *,
        messages: list[ChatMessage],
        jobs_by_id: dict[str, Job] | None = None,
    ) -> "SessionDetailResponse":
        return cls(
            id=session.id,
            title=session.title,
            workspace_path=session.workspace_path,
            workspace_name=session.workspace_name,
            provider_session_id=session.provider_session_id,
            created_at=session.created_at,
            updated_at=session.updated_at,
            messages=[
                ChatMessageResponse.from_domain(
                    message,
                    job=jobs_by_id.get(message.job_id) if jobs_by_id and message.job_id else None,
                )
                for message in messages
            ],
        )


class WorkspaceResponse(BaseModel):
    name: str
    path: str


class JobResponse(BaseModel):
    job_id: str
    session_id: str
    message: str
    status: JobStatus
    response: str | None = None
    error: str | None = None
    provider_session_id: str | None = None
    phase: str | None = None
    latest_activity: str | None = None
    elapsed_seconds: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    @classmethod
    def from_domain(cls, job: Job) -> "JobResponse":
        return cls(
            job_id=job.id,
            session_id=job.session_id,
            message=job.message,
            status=job.status,
            response=job.response,
            error=job.error,
            provider_session_id=job.provider_session_id,
            phase=job.phase,
            latest_activity=job.latest_activity,
            elapsed_seconds=job.elapsed_seconds,
            created_at=job.created_at,
            updated_at=job.updated_at,
            completed_at=job.completed_at,
        )


class HealthResponse(BaseModel):
    status: str = "ok"
    server_name: str
    backend_mode: str
    projects_root: str
    audio_transcription_backend: str
    audio_transcription_resolved_backend: str
    audio_transcription_ready: bool
    audio_transcription_detail: str | None = None
    tailscale_installed: bool
    tailscale_online: bool
    tailscale_tailnet_name: str | None = None
    tailscale_device_name: str | None = None
    tailscale_magic_dns_name: str | None = None
    tailscale_ipv4: str | None = None
    tailscale_suggested_url: str | None = None


class ServerCapabilitiesResponse(BaseModel):
    supports_audio_input: bool
    supports_image_input: bool
    supports_document_input: bool
    supports_attachment_batch: bool
    supports_job_cancellation: bool
    supports_job_retry: bool
    supports_push_job_stream: bool
    audio_max_upload_bytes: int
    image_max_upload_bytes: int
    document_max_upload_bytes: int
    document_text_char_limit: int
