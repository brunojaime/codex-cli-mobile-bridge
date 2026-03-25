from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from backend.app.domain.entities.agent_configuration import (
    AgentConfiguration,
    AgentDisplayMode,
    AgentId,
    AgentPreset,
    AgentTriggerSource,
    AgentType,
    AgentVisibilityMode,
    CONFIGURABLE_AGENT_IDS,
    LEGACY_AGENT_IDS,
    SUPERVISOR_MEMBER_AGENT_IDS,
    TurnBudgetMode,
    normalize_agent_enum_value,
)
from backend.app.domain.entities.agent_profile import AgentProfile
from backend.app.domain.entities.chat_message import (
    ChatMessageAuthorType,
    ChatMessage,
    ChatMessageReasonCode,
    MessageRecoveryAction,
    ChatMessageRole,
    ChatMessageStatus,
)
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.conversation_product import (
    ConversationProduct,
    derive_conversation_product,
)
from backend.app.domain.entities.job import Job, JobConversationKind, JobStatus
from backend.app.domain.entities.current_run import (
    CurrentRunExecution,
    RunStageExecution,
    RunStageId,
    RunStageState,
    derive_current_run_execution,
    derive_recent_run_executions,
)
from backend.app.domain.entities.reviewer_status import (
    ReviewerLifecycleState,
    derive_reviewer_lifecycle_state,
)
from backend.app.domain.repositories.chat_repository import PersistenceDiagnosticIssue


class MessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: str | None = None
    workspace_path: str | None = None


class MessageRecoveryRequest(BaseModel):
    action: MessageRecoveryAction


class ArchiveSessionRequest(BaseModel):
    archived: bool = False


class CreateSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    workspace_path: str | None = None
    agent_profile_id: str | None = Field(default=None, max_length=120)


class AgentProfileCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)
    description: str = Field(default="", max_length=240)
    color_hex: str = Field(..., min_length=7, max_length=7)
    configuration: "AgentConfigurationRequest"


class AgentProfileSelectionRequest(BaseModel):
    profile_id: str = Field(..., min_length=1, max_length=120)


class AgentProfileImportItem(BaseModel):
    id: str = Field(..., min_length=1, max_length=120)
    name: str = Field(..., min_length=1, max_length=40)
    description: str = Field(default="", max_length=240)
    color_hex: str = Field(..., min_length=7, max_length=7)
    prompt: str = Field(..., min_length=1, max_length=12000)
    configuration: "AgentConfigurationRequest | None" = None
    is_builtin: bool = False

    def to_domain(self) -> AgentProfile:
        configuration = self.configuration.to_domain() if self.configuration else None
        return AgentProfile(
            id=self.id,
            name=self.name,
            description=self.description,
            color_hex=self.color_hex,
            prompt=self.prompt,
            configuration=configuration,
            is_builtin=self.is_builtin,
        ).normalized()


class AgentProfileImportRequest(BaseModel):
    profiles: list[AgentProfileImportItem]


class AgentProfileResponse(BaseModel):
    id: str
    name: str
    description: str
    color_hex: str
    prompt: str
    configuration: "AgentConfigurationResponse"
    is_builtin: bool = False

    @classmethod
    def from_domain(cls, profile: AgentProfile) -> "AgentProfileResponse":
        normalized = profile.normalized()
        return cls(
            id=normalized.id,
            name=normalized.name,
            description=normalized.description,
            color_hex=normalized.color_hex,
            prompt=normalized.prompt,
            configuration=AgentConfigurationResponse.from_domain(
                normalized.resolved_configuration(),
            ),
            is_builtin=normalized.is_builtin,
        )


class AutoModeConfigRequest(BaseModel):
    enabled: bool = False
    max_turns: int = Field(default=0, ge=0)
    reviewer_prompt: str | None = Field(default=None, max_length=12000)


class AgentDefinitionPayload(BaseModel):
    agent_id: AgentId
    agent_type: AgentType
    enabled: bool
    label: str = Field(..., min_length=1, max_length=40)
    prompt: str = Field(default="", max_length=12000)
    model: str | None = Field(default=None, max_length=120)
    visibility: AgentVisibilityMode
    max_turns: int = Field(..., ge=0)

    @model_validator(mode="before")
    @classmethod
    def canonicalize_aliases(
        cls,
        raw: object,
    ) -> object:
        if not isinstance(raw, dict):
            return raw
        payload = dict(raw)
        for field_name in ("agent_id", "agent_type"):
            value = payload.get(field_name)
            if isinstance(value, str):
                payload[field_name] = normalize_agent_enum_value(value)
        return payload

    @model_validator(mode="after")
    def validate_prompt_requirements(self) -> "AgentDefinitionPayload":
        expected_types = {
            AgentId.GENERATOR: AgentType.GENERATOR,
            AgentId.REVIEWER: AgentType.REVIEWER,
            AgentId.SUMMARY: AgentType.SUMMARY,
            AgentId.SUPERVISOR: AgentType.SUPERVISOR,
            AgentId.QA: AgentType.QA,
            AgentId.UX: AgentType.UX,
            AgentId.SENIOR_ENGINEER: AgentType.SENIOR_ENGINEER,
            AgentId.SCRAPER: AgentType.SCRAPER,
        }
        expected_type = expected_types.get(self.agent_id)
        if expected_type is not None and self.agent_type != expected_type:
            raise ValueError(
                f"{self.agent_id.value.replace('_', ' ').title()} agent must use "
                f"{expected_type.value} type."
            )
        if self.enabled and not self.prompt.strip():
            raise ValueError(f"Enabled agent {self.agent_id.value} must have a non-empty prompt.")
        return self


class AgentConfigurationRequest(BaseModel):
    preset: AgentPreset
    display_mode: AgentDisplayMode = AgentDisplayMode.SHOW_ALL
    turn_budget_mode: TurnBudgetMode = TurnBudgetMode.EACH_AGENT
    agents: list[AgentDefinitionPayload]
    supervisor_member_ids: list[AgentId] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def canonicalize_aliases(
        cls,
        raw: object,
    ) -> object:
        if not isinstance(raw, dict):
            return raw
        payload = dict(raw)
        supervisor_member_ids = payload.get("supervisor_member_ids")
        if isinstance(supervisor_member_ids, list):
            payload["supervisor_member_ids"] = [
                normalize_agent_enum_value(item) if isinstance(item, str) else item
                for item in supervisor_member_ids
            ]
        return payload

    @model_validator(mode="after")
    def validate_agent_set(self) -> "AgentConfigurationRequest":
        ids = [agent.agent_id for agent in self.agents]
        if len(set(ids)) != len(ids):
            raise ValueError("Agent configuration cannot contain duplicate agent ids.")
        unknown_ids = set(ids) - set(CONFIGURABLE_AGENT_IDS)
        if unknown_ids:
            raise ValueError("Agent configuration contains unknown agent ids.")
        legacy_ids = set(LEGACY_AGENT_IDS)
        if not legacy_ids.issubset(set(ids)):
            raise ValueError(
                "Agent configuration must contain generator, reviewer, and summary."
            )
        selected_supervisor_members = set(self.supervisor_member_ids)
        if selected_supervisor_members - set(SUPERVISOR_MEMBER_AGENT_IDS):
            raise ValueError(
                "Supervisor member ids must reference qa, ux, senior_engineer, or scraper."
            )
        if self.preset == AgentPreset.SUPERVISOR and AgentId.SUPERVISOR not in set(ids):
            raise ValueError("Supervisor preset requires the supervisor agent definition.")
        return self

    def to_domain(self) -> AgentConfiguration:
        return AgentConfiguration.from_dict(
            {
                "preset": self.preset.value,
                "display_mode": self.display_mode.value,
                "turn_budget_mode": self.turn_budget_mode.value,
                "supervisor_member_ids": [agent_id.value for agent_id in self.supervisor_member_ids],
                "agents": {
                    agent.agent_id.value: {
                        "agent_id": agent.agent_id.value,
                        "agent_type": agent.agent_type.value,
                        "enabled": agent.enabled,
                        "label": agent.label,
                        "prompt": agent.prompt,
                        "model": agent.model,
                        "visibility": agent.visibility.value,
                        "max_turns": agent.max_turns,
                    }
                    for agent in self.agents
                },
            }
        )


class AgentDefinitionResponse(BaseModel):
    agent_id: AgentId
    agent_type: AgentType
    enabled: bool
    label: str
    prompt: str
    model: str | None = None
    visibility: AgentVisibilityMode
    max_turns: int
    provider_session_id: str | None = None


class AgentConfigurationResponse(BaseModel):
    preset: AgentPreset
    display_mode: AgentDisplayMode
    turn_budget_mode: TurnBudgetMode
    agents: list[AgentDefinitionResponse]
    supervisor_member_ids: list[AgentId] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, configuration: AgentConfiguration) -> "AgentConfigurationResponse":
        normalized = configuration.normalized()
        return cls(
            preset=normalized.preset,
            display_mode=normalized.display_mode,
            turn_budget_mode=normalized.turn_budget_mode,
            supervisor_member_ids=list(normalized.supervisor_member_ids),
            agents=[
                AgentDefinitionResponse(
                    agent_id=agent.agent_id,
                    agent_type=agent.agent_type,
                    enabled=agent.enabled,
                    label=agent.label,
                    prompt=agent.prompt,
                    model=agent.model,
                    visibility=agent.visibility,
                    max_turns=agent.max_turns,
                    provider_session_id=agent.provider_session_id,
                )
                for agent in normalized.agents.values()
            ],
        )


class MessageAcceptedResponse(BaseModel):
    job_id: str
    session_id: str
    status: JobStatus
    provider_session_id: str | None = None
    agent_id: AgentId = AgentId.GENERATOR
    agent_type: AgentType = AgentType.GENERATOR

    @classmethod
    def from_domain(cls, job: Job) -> "MessageAcceptedResponse":
        return cls(
            job_id=job.id,
            session_id=job.session_id,
            status=job.status,
            provider_session_id=job.provider_session_id,
            agent_id=job.agent_id,
            agent_type=job.agent_type,
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
            agent_id=job.agent_id,
            agent_type=job.agent_type,
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
            agent_id=job.agent_id,
            agent_type=job.agent_type,
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
            agent_id=job.agent_id,
            agent_type=job.agent_type,
            attached_document_name=attached_document_name,
            document_kind=document_kind,
            transcript=transcript,
            extracted_text_preview=extracted_text_preview,
        )


class ChatMessageResponse(BaseModel):
    id: str
    role: ChatMessageRole
    author_type: ChatMessageAuthorType
    agent_id: AgentId
    agent_type: AgentType
    agent_label: str | None = None
    visibility: AgentVisibilityMode
    trigger_source: AgentTriggerSource
    run_id: str | None = None
    submission_token: str | None = None
    reason_code: ChatMessageReasonCode | None = None
    recovery_action: MessageRecoveryAction | None = None
    recovered_from_message_id: str | None = None
    superseded_by_message_id: str | None = None
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
            author_type=message.author_type,
            agent_id=message.agent_id,
            agent_type=message.agent_type,
            agent_label=message.agent_label,
            visibility=message.visibility,
            trigger_source=message.trigger_source,
            run_id=message.run_id,
            submission_token=message.submission_token,
            reason_code=message.reason_code,
            recovery_action=message.recovery_action,
            recovered_from_message_id=message.recovered_from_message_id,
            superseded_by_message_id=message.superseded_by_message_id,
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


class ConversationProductResponse(BaseModel):
    status_line: str
    description: str
    latest_update: str | None = None
    current_focus: str | None = None
    next_step: str | None = None

    @classmethod
    def from_domain(cls, product: ConversationProduct) -> "ConversationProductResponse":
        return cls(
            status_line=product.status_line,
            description=product.description,
            latest_update=product.latest_update,
            current_focus=product.current_focus,
            next_step=product.next_step,
        )


class SessionSummaryResponse(BaseModel):
    id: str
    title: str
    archived_at: datetime | None = None
    workspace_path: str
    workspace_name: str
    agent_profile_id: str
    agent_profile_name: str
    agent_profile_color: str
    provider_session_id: str | None = None
    reviewer_provider_session_id: str | None = None
    active_agent_run_id: str | None = None
    active_agent_turn_index: int = 0
    agent_configuration: AgentConfigurationResponse
    auto_mode_enabled: bool = False
    auto_max_turns: int = 0
    auto_reviewer_prompt: str | None = None
    auto_turn_index: int = 0
    reviewer_state: ReviewerLifecycleState = ReviewerLifecycleState.OFF
    conversation_product: ConversationProductResponse
    created_at: datetime
    updated_at: datetime
    last_message_preview: str | None = None
    has_pending_messages: bool = False

    @classmethod
    def from_domain(
        cls,
        session: ChatSession,
        *,
        messages: list[ChatMessage],
        jobs_by_id: dict[str, Job] | None = None,
    ) -> "SessionSummaryResponse":
        last_message = messages[-1] if messages else None
        has_pending = any(
            message.status in {
                ChatMessageStatus.RESERVED,
                ChatMessageStatus.SUBMISSION_PENDING,
                ChatMessageStatus.PENDING,
            }
            for message in messages
        )
        current_run = derive_current_run_execution(
            session,
            messages=messages,
            jobs_by_id=jobs_by_id,
        )
        recent_runs = derive_recent_run_executions(
            session,
            messages=messages,
            jobs_by_id=jobs_by_id,
            limit=1,
        )
        return cls(
            id=session.id,
            title=session.title,
            archived_at=session.archived_at,
            workspace_path=session.workspace_path,
            workspace_name=session.workspace_name,
            agent_profile_id=session.agent_profile_id,
            agent_profile_name=session.agent_profile_name,
            agent_profile_color=session.agent_profile_color,
            provider_session_id=session.provider_session_id,
            reviewer_provider_session_id=session.reviewer_provider_session_id,
            active_agent_run_id=session.active_agent_run_id,
            active_agent_turn_index=session.active_agent_turn_index,
            agent_configuration=AgentConfigurationResponse.from_domain(
                session.agent_configuration,
            ),
            auto_mode_enabled=session.auto_mode_enabled,
            auto_max_turns=session.auto_max_turns,
            auto_reviewer_prompt=session.auto_reviewer_prompt,
            auto_turn_index=session.auto_turn_index,
            reviewer_state=derive_reviewer_lifecycle_state(
                session,
                messages=messages,
                jobs_by_id=jobs_by_id,
            ),
            conversation_product=ConversationProductResponse.from_domain(
                derive_conversation_product(
                    session,
                    messages=messages,
                    current_run=current_run,
                    recent_runs=recent_runs,
                )
            ),
            created_at=session.created_at,
            updated_at=session.updated_at,
            last_message_preview=last_message.content[:120] if last_message else None,
            has_pending_messages=has_pending,
        )


class SessionDetailResponse(BaseModel):
    id: str
    title: str
    archived_at: datetime | None = None
    workspace_path: str
    workspace_name: str
    agent_profile_id: str
    agent_profile_name: str
    agent_profile_color: str
    provider_session_id: str | None = None
    reviewer_provider_session_id: str | None = None
    active_agent_run_id: str | None = None
    active_agent_turn_index: int = 0
    agent_configuration: AgentConfigurationResponse
    auto_mode_enabled: bool = False
    auto_max_turns: int = 0
    auto_reviewer_prompt: str | None = None
    auto_turn_index: int = 0
    reviewer_state: ReviewerLifecycleState = ReviewerLifecycleState.OFF
    conversation_product: ConversationProductResponse
    current_run: "CurrentRunExecutionResponse | None" = None
    recent_runs: list["CurrentRunExecutionResponse"] = Field(default_factory=list)
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
        run_configurations_by_id: dict[str, AgentConfiguration] | None = None,
    ) -> "SessionDetailResponse":
        current_run = derive_current_run_execution(
            session,
            messages=messages,
            jobs_by_id=jobs_by_id,
            run_configurations_by_id=run_configurations_by_id,
        )
        recent_runs = derive_recent_run_executions(
            session,
            messages=messages,
            jobs_by_id=jobs_by_id,
            run_configurations_by_id=run_configurations_by_id,
        )
        return cls(
            id=session.id,
            title=session.title,
            archived_at=session.archived_at,
            workspace_path=session.workspace_path,
            workspace_name=session.workspace_name,
            agent_profile_id=session.agent_profile_id,
            agent_profile_name=session.agent_profile_name,
            agent_profile_color=session.agent_profile_color,
            provider_session_id=session.provider_session_id,
            reviewer_provider_session_id=session.reviewer_provider_session_id,
            active_agent_run_id=session.active_agent_run_id,
            active_agent_turn_index=session.active_agent_turn_index,
            agent_configuration=AgentConfigurationResponse.from_domain(session.agent_configuration),
            auto_mode_enabled=session.auto_mode_enabled,
            auto_max_turns=session.auto_max_turns,
            auto_reviewer_prompt=session.auto_reviewer_prompt,
            auto_turn_index=session.auto_turn_index,
            reviewer_state=derive_reviewer_lifecycle_state(
                session,
                messages=messages,
                jobs_by_id=jobs_by_id,
            ),
            conversation_product=ConversationProductResponse.from_domain(
                derive_conversation_product(
                    session,
                    messages=messages,
                    current_run=current_run,
                    recent_runs=recent_runs,
                )
            ),
            current_run=CurrentRunExecutionResponse.from_domain(current_run)
            if current_run is not None
            else None,
            recent_runs=[
                CurrentRunExecutionResponse.from_domain(run)
                for run in recent_runs
            ],
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


class RunStageExecutionResponse(BaseModel):
    stage: RunStageId
    state: RunStageState
    configured: bool
    attempt_count: int = 0
    max_turns: int = 0
    has_turn_budget: bool = False
    message_id: str | None = None
    job_id: str | None = None
    job_status: JobStatus | None = None
    latest_activity: str | None = None
    started_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None

    @classmethod
    def from_domain(cls, stage: RunStageExecution) -> "RunStageExecutionResponse":
        return cls(
            stage=stage.stage,
            state=stage.state,
            configured=stage.configured,
            attempt_count=stage.attempt_count,
            max_turns=stage.max_turns,
            has_turn_budget=stage.has_turn_budget,
            message_id=stage.message_id,
            job_id=stage.job_id,
            job_status=stage.job_status,
            latest_activity=stage.latest_activity,
            started_at=stage.started_at,
            updated_at=stage.updated_at,
            completed_at=stage.completed_at,
        )


class CurrentRunExecutionResponse(BaseModel):
    run_id: str
    state: RunStageState
    is_active: bool
    preset: AgentPreset
    turn_budget_mode: TurnBudgetMode | None = None
    started_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    participant_agent_ids: list[AgentId] = Field(default_factory=list)
    call_count: int = 0
    stages: list[RunStageExecutionResponse]

    @classmethod
    def from_domain(cls, run: CurrentRunExecution) -> "CurrentRunExecutionResponse":
        return cls(
            run_id=run.run_id,
            state=run.state,
            is_active=run.is_active,
            preset=run.preset,
            turn_budget_mode=run.turn_budget_mode,
            started_at=run.started_at,
            updated_at=run.updated_at,
            completed_at=run.completed_at,
            participant_agent_ids=list(run.participant_agent_ids),
            call_count=run.call_count,
            stages=[RunStageExecutionResponse.from_domain(stage) for stage in run.stages],
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
    conversation_kind: JobConversationKind = JobConversationKind.PRIMARY
    agent_id: AgentId = AgentId.GENERATOR
    agent_type: AgentType = AgentType.GENERATOR
    trigger_source: AgentTriggerSource = AgentTriggerSource.USER
    run_id: str | None = None
    submission_token: str | None = None
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
            conversation_kind=job.conversation_kind,
            agent_id=job.agent_id,
            agent_type=job.agent_type,
            trigger_source=job.trigger_source,
            run_id=job.run_id,
            submission_token=job.submission_token,
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
    persistence_available: bool
    persistence_error_code: str | None = None
    persistence_error_detail: str | None = None
    audio_transcription_backend: str
    audio_transcription_resolved_backend: str
    audio_transcription_ready: bool
    audio_transcription_detail: str | None = None
    speech_synthesis_backend: str
    speech_synthesis_ready: bool
    speech_synthesis_detail: str | None = None
    speech_synthesis_voice: str | None = None
    speech_synthesis_response_format: str | None = None
    tailscale_installed: bool
    tailscale_online: bool
    tailscale_tailnet_name: str | None = None
    tailscale_device_name: str | None = None
    tailscale_magic_dns_name: str | None = None
    tailscale_ipv4: str | None = None
    tailscale_suggested_url: str | None = None


class PersistenceIntegrityIssueResponse(BaseModel):
    table: str
    row_id: str | None = None
    field: str | None = None
    code: str
    detail: str

    @classmethod
    def from_domain(
        cls,
        issue: PersistenceDiagnosticIssue,
    ) -> "PersistenceIntegrityIssueResponse":
        return cls(
            table=issue.table,
            row_id=issue.row_id,
            field=issue.field,
            code=issue.code,
            detail=issue.detail,
        )


class PersistenceIntegrityResponse(BaseModel):
    backend: str
    is_healthy: bool
    issues: list[PersistenceIntegrityIssueResponse]


class ServerCapabilitiesResponse(BaseModel):
    supports_audio_input: bool
    supports_speech_output: bool
    supports_image_input: bool
    supports_document_input: bool
    supports_attachment_batch: bool
    supports_job_cancellation: bool
    supports_job_retry: bool
    supports_push_job_stream: bool
    speech_output_backend: str
    speech_output_voice: str | None = None
    speech_output_response_format: str | None = None
    audio_max_upload_bytes: int
    image_max_upload_bytes: int
    document_max_upload_bytes: int
    document_text_char_limit: int


class SpeechRequest(BaseModel):
    text: str
