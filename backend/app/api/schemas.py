from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

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
    SummaryStrategy,
    SummaryStrategyMode,
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
from backend.app.domain.entities.chat_turn_summary import ChatTurnSummary
from backend.app.domain.entities.conversation_product import (
    ConversationProduct,
    derive_conversation_product,
)
from backend.app.domain.entities.codex_options import CodexRunOptions
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
from backend.app.domain.entities.text_sanitization import (
    sanitize_image_attachment_error_text,
)
from backend.app.domain.repositories.chat_repository import PersistenceDiagnosticIssue


class MessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: str | None = None
    workspace_path: str | None = None
    codex_options: "CodexRunOptionsRequest | None" = None


class FeedbackPointRequest(BaseModel):
    x: float
    y: float


class FeedbackQueueItemRequest(BaseModel):
    id: str | None = Field(default=None, max_length=160)
    sourceApp: str = Field(
        default="unknown",
        max_length=120,
        validation_alias=AliasChoices("sourceApp", "source_app"),
    )
    sourceDisplayName: str | None = Field(
        default=None,
        max_length=160,
        validation_alias=AliasChoices("sourceDisplayName", "source_display_name"),
    )
    comment: str = Field(..., min_length=1, max_length=10000)
    createdAt: str | None = None
    screenshotMimeType: str = Field(default="image/png", max_length=80)
    screenshotPngBase64: str | None = None
    selectionPoints: list[FeedbackPointRequest] = Field(default_factory=list)
    selectionBounds: dict[str, float] = Field(default_factory=dict)
    audioMimeType: str | None = Field(default=None, max_length=80)
    audioDurationMs: int | None = None
    audioByteLength: int | None = None
    audioBase64: str | None = None
    audioTranscript: str | None = Field(default=None, max_length=20000)


class FeedbackQueueItemResponse(BaseModel):
    id: str
    source_app: str
    source_display_name: str | None = None
    comment: str
    created_at: str
    status: str
    screenshot_mime_type: str
    has_screenshot: bool
    screenshot_png_base64: str | None = None
    selection_points: list[dict[str, float]] = Field(default_factory=list)
    selection_bounds: dict[str, float] = Field(default_factory=dict)
    audio_mime_type: str | None = None
    audio_duration_ms: int | None = None
    audio_byte_length: int | None = None
    has_audio: bool = False
    audio_base64: str | None = None
    audio_transcript: str | None = None


class FeedbackQueueStartRequest(BaseModel):
    message: str | None = Field(default=None, max_length=10000)
    session_id: str | None = None
    workspace_path: str | None = None
    target_mode: Literal["generator_only", "generator_reviewer"] = Field(
        default="generator_only",
        validation_alias=AliasChoices("target_mode", "targetMode"),
    )
    codex_options: "CodexRunOptionsRequest | None" = None


class FeedbackWorkflowPresetResponse(BaseModel):
    id: str
    name: str
    description: str
    target_mode: str = "agent_profile"
    agent_profile_id: str | None = None
    includes_reviewer: bool = False
    default: bool = False


class FeedbackWorkflowPresetsResponse(BaseModel):
    default_preset_id: str
    presets: list[FeedbackWorkflowPresetResponse]


class AppUpdateRegistryItemResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_app: str = Field(alias="sourceApp")
    display_name: str = Field(alias="displayName")
    platform: str = "android"
    enabled: bool
    required_minimum_build: int | None = Field(
        default=None,
        alias="requiredMinimumBuild",
    )


class AppUpdateRegistryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    kind: str = "codex.appUpdateRegistry"
    version: int = 1
    apps: list[AppUpdateRegistryItemResponse]


class AppUpdateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    kind: str = "codex.appUpdate"
    version: int = 1
    source_app: str = Field(alias="sourceApp")
    display_name: str | None = Field(default=None, alias="displayName")
    platform: str
    current_version: str | None = Field(default=None, alias="currentVersion")
    current_build: int | None = Field(default=None, alias="currentBuild")
    latest_version: str | None = Field(default=None, alias="latestVersion")
    latest_build: int | None = Field(default=None, alias="latestBuild")
    release_tag: str | None = Field(default=None, alias="releaseTag")
    release_url: str | None = Field(default=None, alias="releaseUrl")
    apk_url: str | None = Field(default=None, alias="apkUrl")
    apk_asset_name: str | None = Field(default=None, alias="apkAssetName")
    sha256: str | None = None
    size_bytes: int | None = Field(default=None, alias="sizeBytes")
    release_notes: str | None = Field(default=None, alias="releaseNotes")
    required: bool
    available: bool


class FeedbackBatchStartRequest(BaseModel):
    sourceApp: str = Field(
        default="unknown",
        max_length=120,
        validation_alias=AliasChoices("sourceApp", "source_app"),
    )
    sourceDisplayName: str | None = Field(
        default=None,
        max_length=160,
        validation_alias=AliasChoices("sourceDisplayName", "source_display_name"),
    )
    items: list[FeedbackQueueItemRequest] = Field(default_factory=list)
    workflow_preset_id: str = Field(
        default="generator_only",
        max_length=120,
        validation_alias=AliasChoices("workflow_preset_id", "workflowPresetId"),
    )
    release_when_complete: bool = Field(
        default=False,
        validation_alias=AliasChoices("release_when_complete", "releaseWhenComplete"),
    )
    quick_ask_id: str | None = Field(
        default=None,
        max_length=160,
        validation_alias=AliasChoices("quick_ask_id", "quickAskId"),
    )
    message: str | None = Field(default=None, max_length=10000)
    session_id: str | None = None
    workspace_path: str | None = None
    codex_options: "CodexRunOptionsRequest | None" = None


class FeedbackQuickAskRequest(BaseModel):
    sourceApp: str = Field(
        default="unknown",
        max_length=120,
        validation_alias=AliasChoices("sourceApp", "source_app"),
    )
    sourceDisplayName: str | None = Field(
        default=None,
        max_length=160,
        validation_alias=AliasChoices("sourceDisplayName", "source_display_name"),
    )
    question: str = Field(..., min_length=1, max_length=4000)
    screenshotMimeType: str = Field(
        default="image/png",
        max_length=80,
        validation_alias=AliasChoices("screenshotMimeType", "screenshot_mime_type"),
    )
    screenshotPngBase64: str = Field(
        ...,
        validation_alias=AliasChoices("screenshotPngBase64", "screenshot_png_base64"),
    )
    selectionPoints: list[FeedbackPointRequest] = Field(default_factory=list)
    selectionBounds: dict[str, float] = Field(default_factory=dict)
    session_id: str | None = None
    workspace_path: str | None = None
    codex_options: "CodexRunOptionsRequest | None" = None


class FeedbackQuickAskAcceptedResponse(BaseModel):
    job_id: str
    session_id: str
    status: JobStatus
    provider_session_id: str | None = None
    agent_id: AgentId
    agent_type: AgentType
    quick_ask_id: str

    @classmethod
    def from_domain(
        cls,
        job: Job,
        *,
        quick_ask_id: str,
    ) -> "FeedbackQuickAskAcceptedResponse":
        return cls(
            job_id=job.id,
            session_id=job.session_id,
            status=job.status,
            provider_session_id=job.provider_session_id,
            agent_id=job.agent_id,
            agent_type=job.agent_type,
            quick_ask_id=quick_ask_id,
        )


class FeedbackQuickAskResponse(BaseModel):
    quick_ask_id: str
    source_app: str
    source_display_name: str | None = None
    question: str
    status: str
    status_detail: str | None = None
    answer: str | None = None
    answered_at: str | None = None
    screenshot_mime_type: str
    has_screenshot: bool
    screenshot_png_base64: str | None = None
    selection_points: list[dict[str, float]] = Field(default_factory=list)
    selection_bounds: dict[str, float] = Field(default_factory=dict)
    job_id: str | None = None
    session_id: str | None = None
    run_id: str | None = None
    workspace_path: str | None = None
    created_at: str


class CodexRunOptionsRequest(BaseModel):
    profile: str | None = Field(default=None, max_length=120)
    search_enabled: bool = False
    skill_ids: list[str] = Field(default_factory=list)
    mcp_server_ids: list[str] = Field(default_factory=list)
    config_overrides: list[str] = Field(default_factory=list)

    def to_domain(self) -> CodexRunOptions:
        return CodexRunOptions(
            profile=self.profile,
            search_enabled=self.search_enabled,
            skill_ids=tuple(self.skill_ids),
            mcp_server_ids=tuple(self.mcp_server_ids),
            config_overrides=tuple(self.config_overrides),
        ).normalized()


class CodexSkillResponse(BaseModel):
    skill_id: str
    name: str
    description: str
    source: str
    path: str


class CodexConfigProfileResponse(BaseModel):
    name: str


class CodexMcpServerResponse(BaseModel):
    server_id: str
    summary: str
    source: str = "external"
    backing_app_id: str | None = None
    status: str | None = None
    selectable: bool = True
    selectable_reason: str | None = None
    disabled_reason: str | None = None
    lookup_error: str | None = None


class CodexMcpAppToolResponse(BaseModel):
    name: str
    title: str | None = None
    description: str | None = None
    read_only: bool
    destructive: bool
    idempotent: bool
    open_world: bool
    input_schema: dict[str, Any] = Field(default_factory=dict)


class CodexMcpAppResourceResponse(BaseModel):
    name: str
    title: str | None = None
    uri: str
    description: str | None = None
    mime_type: str | None = None


class CodexMcpAppPromptArgumentResponse(BaseModel):
    name: str
    description: str | None = None
    required: bool


class CodexMcpAppPromptResponse(BaseModel):
    name: str
    title: str | None = None
    description: str | None = None
    arguments: list[CodexMcpAppPromptArgumentResponse] = Field(default_factory=list)


class CodexMcpAppPreviewResponse(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any | None = None
    is_error: bool
    error: str | None = None


class CodexMcpAppResponse(BaseModel):
    app_id: str
    name: str
    description: str
    recommended_server_id: str
    transport: str
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    supports_ui_extension: bool = False
    ui_entry_uri: str | None = None
    spec_path: str
    installed: bool = False
    install_state: str
    server_present: bool = False
    server_presence_known: bool = False
    config_matches: bool | None = None
    tools: list[CodexMcpAppToolResponse] = Field(default_factory=list)
    resources: list[CodexMcpAppResourceResponse] = Field(default_factory=list)
    prompts: list[CodexMcpAppPromptResponse] = Field(default_factory=list)
    preview: CodexMcpAppPreviewResponse | None = None
    drift_summary: str | None = None
    disabled_reason: str | None = None
    lookup_error: str | None = None
    validation_error: str | None = None
    protocol_error: str | None = None


class CodexMcpAppInstallResponse(BaseModel):
    app_id: str
    server_id: str
    already_installed: bool
    reconciled: bool
    command: str
    summary: str


class CodexStatusResponse(BaseModel):
    cli_available: bool
    command: str
    version: str | None = None
    logged_in: bool = False
    auth_mode: str | None = None
    status_summary: str
    raw_status: str | None = None
    usage_available: bool = False
    usage_label: str | None = None
    usage_summary: str | None = None
    error: str | None = None


class CodexToolingResponse(BaseModel):
    status: CodexStatusResponse
    profiles: list[CodexConfigProfileResponse] = Field(default_factory=list)
    skills: list[CodexSkillResponse] = Field(default_factory=list)
    mcp_servers: list[CodexMcpServerResponse] = Field(default_factory=list)
    mcp_apps: list[CodexMcpAppResponse] = Field(default_factory=list)
    mcp_server_inventory_complete: bool = True
    mcp_raw_output: str | None = None
    mcp_error: str | None = None
    config_path: str | None = None


class MessageRecoveryRequest(BaseModel):
    action: MessageRecoveryAction


class ArchiveSessionRequest(BaseModel):
    archived: bool = False


class CreateSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    workspace_path: str | None = None
    agent_profile_id: str | None = Field(default=None, max_length=120)
    turn_summaries_enabled: bool = False


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


class TurnSummaryConfigRequest(BaseModel):
    enabled: bool = False


class AgentDefinitionPayload(BaseModel):
    agent_id: AgentId
    agent_type: AgentType
    enabled: bool
    label: str = Field(..., min_length=1, max_length=40)
    prompt: str = Field(default="", max_length=12000)
    model: str | None = Field(default=None, max_length=120)
    visibility: AgentVisibilityMode
    max_turns: int = Field(..., ge=0)
    trigger_interval: int = Field(default=0, ge=0)

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
    summary_strategy: "SummaryStrategyPayload | None" = None
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
                "summary_strategy": (
                    self.summary_strategy.to_domain().to_dict()
                    if self.summary_strategy is not None
                    else None
                ),
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
                        "trigger_interval": agent.trigger_interval,
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
    trigger_interval: int = 0
    provider_session_id: str | None = None


class SummaryStrategyPayload(BaseModel):
    mode: SummaryStrategyMode
    deterministic_interval: int = Field(default=4, ge=1)
    supervisor_window_start: int = Field(default=3, ge=1)
    supervisor_window_end: int = Field(default=6, ge=1)

    @model_validator(mode="after")
    def validate_window(self) -> "SummaryStrategyPayload":
        if self.supervisor_window_end < self.supervisor_window_start:
            raise ValueError("Summary strategy window end must be >= window start.")
        return self

    def to_domain(self) -> SummaryStrategy:
        return SummaryStrategy(
            mode=self.mode,
            deterministic_interval=self.deterministic_interval,
            supervisor_window_start=self.supervisor_window_start,
            supervisor_window_end=self.supervisor_window_end,
        )

    @classmethod
    def from_domain(cls, strategy: SummaryStrategy) -> "SummaryStrategyPayload":
        return cls(
            mode=strategy.mode,
            deterministic_interval=strategy.deterministic_interval,
            supervisor_window_start=strategy.supervisor_window_start,
            supervisor_window_end=strategy.supervisor_window_end,
        )


class AgentConfigurationResponse(BaseModel):
    preset: AgentPreset
    display_mode: AgentDisplayMode
    turn_budget_mode: TurnBudgetMode
    summary_strategy: SummaryStrategyPayload
    agents: list[AgentDefinitionResponse]
    supervisor_member_ids: list[AgentId] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, configuration: AgentConfiguration) -> "AgentConfigurationResponse":
        normalized = configuration.normalized()
        return cls(
            preset=normalized.preset,
            display_mode=normalized.display_mode,
            turn_budget_mode=normalized.turn_budget_mode,
            summary_strategy=SummaryStrategyPayload.from_domain(normalized.summary_strategy),
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
                    trigger_interval=agent.trigger_interval,
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
    feedback_batch_id: str | None = None

    @classmethod
    def from_domain(
        cls,
        job: Job,
        *,
        feedback_batch_id: str | None = None,
    ) -> "MessageAcceptedResponse":
        return cls(
            job_id=job.id,
            session_id=job.session_id,
            status=job.status,
            provider_session_id=job.provider_session_id,
            agent_id=job.agent_id,
            agent_type=job.agent_type,
            feedback_batch_id=feedback_batch_id,
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


class FeedbackBatchStatusResponse(BaseModel):
    batch_id: str
    source_app: str
    source_display_name: str | None = None
    status: str
    status_detail: str | None = None
    workflow_preset_id: str
    release_when_complete: bool
    item_count: int
    item_ids: list[str] = Field(default_factory=list)
    job_id: str | None = None
    session_id: str | None = None
    run_id: str | None = None
    workspace_path: str | None = None
    quick_ask_id: str | None = None
    job_status: JobStatus | None = None
    summary: str | None = None
    summary_generated_at: str | None = None
    summary_line_count: int = 0
    notification_created_at: str | None = None
    notification_read_at: str | None = None
    notification_unread: bool = False
    created_at: str
    submitted_at: str


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


def _summary_turn_range_payload(message: ChatMessage) -> dict[str, int | None]:
    dedupe_key = (message.dedupe_key or "").strip()
    if ":summary:" not in dedupe_key:
        return {
            "summary_turn_start": None,
            "summary_turn_end": None,
        }
    raw_suffix = dedupe_key.rsplit(":summary:", maxsplit=1)[-1].strip()
    parts = raw_suffix.split(":")
    if len(parts) == 2 and all(part.isdigit() for part in parts):
        start_turn = max(1, int(parts[0]))
        end_turn = max(start_turn, int(parts[1]))
        return {
            "summary_turn_start": start_turn,
            "summary_turn_end": end_turn,
        }
    if len(parts) == 1 and parts[0].isdigit():
        end_turn = max(1, int(parts[0]))
        return {
            "summary_turn_start": 1,
            "summary_turn_end": end_turn,
        }
    return {
        "summary_turn_start": None,
        "summary_turn_end": None,
    }


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
    summary_turn_start: int | None = None
    summary_turn_end: int | None = None
    attachments: list["ChatMessageAttachmentResponse"] = Field(default_factory=list)

    @classmethod
    def from_domain(
        cls,
        message: ChatMessage,
        *,
        job: Job | None = None,
        expose_attachments: bool = False,
    ) -> "ChatMessageResponse":
        return cls(
            **_summary_turn_range_payload(message),
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
            attachments=ChatMessageAttachmentResponse.from_job(job)
            if expose_attachments
            else [],
        )


class ChatMessageAttachmentResponse(BaseModel):
    id: str
    kind: Literal["image"]
    job_id: str
    index: int
    download_url: str

    @classmethod
    def from_job(cls, job: Job | None) -> list["ChatMessageAttachmentResponse"]:
        if job is None or not job.image_paths:
            return []
        return [
            cls(
                id=f"{job.id}:image:{index}",
                kind="image",
                job_id=job.id,
                index=index,
                download_url=f"/jobs/{job.id}/attachments/{index}",
            )
            for index, _path in enumerate(job.image_paths)
        ]


class TurnSummarySourceMessageResponse(BaseModel):
    message_id: str
    role: ChatMessageRole
    author_type: ChatMessageAuthorType
    agent_id: AgentId
    agent_type: AgentType
    agent_label: str | None = None
    content: str | None = None
    status: ChatMessageStatus
    created_at: datetime

    @classmethod
    def from_domain(
        cls,
        message: ChatMessage,
    ) -> "TurnSummarySourceMessageResponse":
        return cls(
            message_id=message.id,
            role=message.role,
            author_type=message.author_type,
            agent_id=message.agent_id,
            agent_type=message.agent_type,
            agent_label=message.agent_label,
            content=sanitize_image_attachment_error_text(message.content),
            status=message.status,
            created_at=message.created_at,
        )


class TurnSummaryResponse(BaseModel):
    id: str
    content: str
    source_message_ids: list[str] = Field(default_factory=list)
    source_messages: list[TurnSummarySourceMessageResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(
        cls,
        summary: ChatTurnSummary,
        *,
        messages_by_id: dict[str, ChatMessage],
    ) -> "TurnSummaryResponse":
        source_messages = (
            [
                TurnSummarySourceMessageResponse(
                    message_id=message.message_id,
                    role=message.role,
                    author_type=message.author_type,
                    agent_id=message.agent_id,
                    agent_type=message.agent_type,
                    agent_label=message.agent_label,
                    content=sanitize_image_attachment_error_text(message.content),
                    status=message.status,
                    created_at=message.created_at,
                )
                for message in summary.source_messages
            ]
            if summary.source_messages
            else [
                TurnSummarySourceMessageResponse.from_domain(message)
                for message_id in summary.source_message_ids
                if (message := messages_by_id.get(message_id)) is not None
            ]
        )
        return cls(
            id=summary.id,
            content=sanitize_image_attachment_error_text(summary.content) or "",
            source_message_ids=list(summary.source_message_ids),
            source_messages=source_messages,
            created_at=summary.created_at,
            updated_at=summary.updated_at,
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
    turn_summaries_enabled: bool = False
    turn_summary_count: int = 0
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
        turn_summaries: list[ChatTurnSummary] | None = None,
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
            turn_summaries_enabled=session.turn_summaries_enabled,
            turn_summary_count=len(turn_summaries or []),
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
    turn_summaries_enabled: bool = False
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
    turn_summaries: list[TurnSummaryResponse] = Field(default_factory=list)

    @classmethod
    def from_domain(
        cls,
        session: ChatSession,
        *,
        messages: list[ChatMessage],
        turn_summaries: list[ChatTurnSummary] | None = None,
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
        messages_by_id = {message.id: message for message in messages}
        jobs_by_user_message_id = {
            job.user_message_id: job
            for job in (jobs_by_id or {}).values()
            if job.user_message_id is not None
        }
        return cls(
            id=session.id,
            title=session.title,
            archived_at=session.archived_at,
            workspace_path=session.workspace_path,
            workspace_name=session.workspace_name,
            turn_summaries_enabled=session.turn_summaries_enabled,
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
                    job=(
                        jobs_by_id.get(message.job_id)
                        if jobs_by_id and message.job_id
                        else jobs_by_user_message_id.get(message.id)
                    ),
                    expose_attachments=message.id in jobs_by_user_message_id,
                )
                for message in messages
            ],
            turn_summaries=[
                TurnSummaryResponse.from_domain(
                    summary,
                    messages_by_id=messages_by_id,
                )
                for summary in (turn_summaries or [])
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
    supports_feedback_batches: bool = True
    speech_output_backend: str
    speech_output_voice: str | None = None
    speech_output_response_format: str | None = None
    audio_max_upload_bytes: int
    image_max_upload_bytes: int
    document_max_upload_bytes: int
    document_text_char_limit: int
    feedback_source_workspace_aliases: dict[str, str] = Field(default_factory=dict)


class SpeechRequest(BaseModel):
    text: str
