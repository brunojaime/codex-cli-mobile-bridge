from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from backend.app.domain.entities.agent_configuration import (
    AgentId,
    AgentTriggerSource,
    AgentType,
    AgentVisibilityMode,
)
from backend.app.domain.entities.job import utc_now


class ChatMessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessageAuthorType(StrEnum):
    HUMAN = "human"
    ASSISTANT = "assistant"
    REVIEWER_CODEX = "reviewer_codex"


class MessageRecoveryAction(StrEnum):
    RETRY = "retry"
    CANCEL = "cancel"


class ChatMessageReasonCode(StrEnum):
    SUPERSEDED_BY_NEWER_RUN = "superseded_by_newer_run"
    ORPHANED_FOLLOW_UP_CANCELLED = "orphaned_follow_up_cancelled"
    SUBMISSION_OUTCOME_UNKNOWN = "submission_outcome_unknown"
    MANUAL_RETRY_REQUESTED = "manual_retry_requested"
    MANUAL_CANCEL_REQUESTED = "manual_cancel_requested"
    FOLLOW_UP_TERMINAL_COMPLETED_RUN = "follow_up_terminal_completed_run"


class ChatMessageStatus(StrEnum):
    RESERVED = "reserved"
    SUBMISSION_PENDING = "submission_pending"
    SUBMISSION_UNKNOWN = "submission_unknown"
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


FOLLOW_UP_AGENT_IDS = frozenset(
    {
        AgentId.GENERATOR,
        AgentId.REVIEWER,
        AgentId.SUMMARY,
        AgentId.SUPERVISOR,
        AgentId.QA,
        AgentId.UX,
        AgentId.SENIOR_ENGINEER,
    }
)
FOLLOW_UP_WAITING_STATUSES = frozenset(
    {
        ChatMessageStatus.RESERVED,
        ChatMessageStatus.SUBMISSION_PENDING,
        ChatMessageStatus.PENDING,
    }
)
FOLLOW_UP_TERMINAL_FAILURE_STATUSES = frozenset(
    {
        ChatMessageStatus.CANCELLED,
        ChatMessageStatus.FAILED,
    }
)


def is_agent_follow_up(agent_id: AgentId) -> bool:
    return agent_id in FOLLOW_UP_AGENT_IDS


def is_follow_up_waiting_status(status: ChatMessageStatus) -> bool:
    return status in FOLLOW_UP_WAITING_STATUSES


def is_follow_up_terminal_failure(status: ChatMessageStatus) -> bool:
    return status in FOLLOW_UP_TERMINAL_FAILURE_STATUSES


def can_launch_reserved_follow_up(message: "ChatMessage") -> bool:
    return message.job_id is None and message.status == ChatMessageStatus.RESERVED


def orphaned_follow_up_resolution_status(
    status: ChatMessageStatus,
) -> ChatMessageStatus | None:
    if status == ChatMessageStatus.RESERVED:
        return ChatMessageStatus.CANCELLED
    if status == ChatMessageStatus.SUBMISSION_PENDING:
        return ChatMessageStatus.SUBMISSION_UNKNOWN
    return None


def normalize_recovery_metadata_fields(
    *,
    message_id: str,
    recovery_action: MessageRecoveryAction | None,
    recovered_from_message_id: str | None,
    superseded_by_message_id: str | None,
) -> tuple[MessageRecoveryAction | None, str | None, str | None]:
    if recovered_from_message_id == message_id:
        recovered_from_message_id = None
    if superseded_by_message_id == message_id:
        superseded_by_message_id = None
    if recovery_action is None:
        return None, None, None
    if recovered_from_message_id and superseded_by_message_id:
        return None, None, None
    if recovery_action == MessageRecoveryAction.CANCEL:
        return MessageRecoveryAction.CANCEL, None, None
    if not recovered_from_message_id and not superseded_by_message_id:
        return None, None, None
    return recovery_action, recovered_from_message_id, superseded_by_message_id


def validate_recovery_metadata_fields(
    *,
    message_id: str,
    recovery_action: MessageRecoveryAction | None,
    recovered_from_message_id: str | None,
    superseded_by_message_id: str | None,
) -> None:
    if recovered_from_message_id == message_id:
        raise ValueError("A message cannot recover from itself.")
    if superseded_by_message_id == message_id:
        raise ValueError("A message cannot supersede itself.")
    if recovery_action is None:
        if recovered_from_message_id or superseded_by_message_id:
            raise ValueError("Recovery linkage requires a recovery_action.")
        return
    if recovered_from_message_id and superseded_by_message_id:
        raise ValueError(
            "A message cannot be both recovered from another message and superseded by one."
        )
    if recovery_action == MessageRecoveryAction.CANCEL:
        if recovered_from_message_id or superseded_by_message_id:
            raise ValueError("Cancelled recovery messages cannot carry lineage links.")
        return
    if not recovered_from_message_id and not superseded_by_message_id:
        raise ValueError("Retry recovery messages must link to either the old or new attempt.")


def validate_manual_recovery_candidate(message: "ChatMessage") -> None:
    if message.status != ChatMessageStatus.SUBMISSION_UNKNOWN:
        raise RuntimeError("Only submission_unknown follow-ups can be recovered manually.")
    if message.job_id is not None:
        raise RuntimeError("This follow-up already has a job attached.")
    if not is_agent_follow_up(message.agent_id):
        raise RuntimeError("Only agent follow-ups can be recovered manually.")
    if message.superseded_by_message_id is not None:
        raise RuntimeError("This uncertain follow-up was already retried.")
    if message.recovery_action is not None:
        raise RuntimeError("This uncertain follow-up was already resolved.")


@dataclass(slots=True)
class ChatMessage:
    id: str
    session_id: str
    role: ChatMessageRole
    author_type: ChatMessageAuthorType
    content: str
    status: ChatMessageStatus
    agent_id: AgentId = AgentId.GENERATOR
    agent_type: AgentType = AgentType.GENERATOR
    agent_label: str | None = None
    visibility: AgentVisibilityMode = AgentVisibilityMode.VISIBLE
    trigger_source: AgentTriggerSource = AgentTriggerSource.SYSTEM
    run_id: str | None = None
    dedupe_key: str | None = None
    submission_token: str | None = None
    reason_code: ChatMessageReasonCode | None = None
    recovery_action: MessageRecoveryAction | None = None
    recovered_from_message_id: str | None = None
    superseded_by_message_id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    job_id: str | None = None

    def normalize_recovery_metadata(self) -> None:
        (
            self.recovery_action,
            self.recovered_from_message_id,
            self.superseded_by_message_id,
        ) = normalize_recovery_metadata_fields(
            message_id=self.id,
            recovery_action=self.recovery_action,
            recovered_from_message_id=self.recovered_from_message_id,
            superseded_by_message_id=self.superseded_by_message_id,
        )

    def validate_recovery_metadata(self) -> None:
        validate_recovery_metadata_fields(
            message_id=self.id,
            recovery_action=self.recovery_action,
            recovered_from_message_id=self.recovered_from_message_id,
            superseded_by_message_id=self.superseded_by_message_id,
        )

    def sync(
        self,
        *,
        content: str | None = None,
        status: ChatMessageStatus | None = None,
        job_id: str | None = None,
        author_type: ChatMessageAuthorType | None = None,
        agent_label: str | None = None,
        submission_token: str | None = None,
        reason_code: ChatMessageReasonCode | None = None,
        recovery_action: MessageRecoveryAction | None = None,
        recovered_from_message_id: str | None = None,
        superseded_by_message_id: str | None = None,
    ) -> None:
        if content is not None:
            self.content = content
        if status is not None:
            self.status = status
        if job_id is not None:
            self.job_id = job_id
        if author_type is not None:
            self.author_type = author_type
        if agent_label is not None:
            self.agent_label = agent_label
        if submission_token is not None:
            self.submission_token = submission_token
        if reason_code is not None:
            self.reason_code = reason_code
        if recovery_action is not None:
            self.recovery_action = recovery_action
        if recovered_from_message_id is not None:
            self.recovered_from_message_id = recovered_from_message_id
        if superseded_by_message_id is not None:
            self.superseded_by_message_id = superseded_by_message_id
        self.updated_at = utc_now()
