from __future__ import annotations

import pytest

from backend.app.domain.entities.agent_configuration import AgentId
from backend.app.domain.entities.chat_message import (
    ChatMessage,
    ChatMessageAuthorType,
    ChatMessageRole,
    ChatMessageStatus,
    MessageRecoveryAction,
    can_launch_reserved_follow_up,
    is_follow_up_terminal_failure,
    is_follow_up_waiting_status,
    normalize_recovery_metadata_fields,
    orphaned_follow_up_resolution_status,
    validate_manual_recovery_candidate,
)


def build_message(
    *,
    status: ChatMessageStatus = ChatMessageStatus.SUBMISSION_UNKNOWN,
    agent_id: AgentId = AgentId.REVIEWER,
    recovery_action: MessageRecoveryAction | None = None,
    recovered_from_message_id: str | None = None,
    superseded_by_message_id: str | None = None,
    job_id: str | None = None,
) -> ChatMessage:
    return ChatMessage(
        id="message-1",
        session_id="session-1",
        role=ChatMessageRole.USER,
        author_type=ChatMessageAuthorType.REVIEWER_CODEX,
        content="follow-up",
        status=status,
        agent_id=agent_id,
        recovery_action=recovery_action,
        recovered_from_message_id=recovered_from_message_id,
        superseded_by_message_id=superseded_by_message_id,
        job_id=job_id,
    )


def test_follow_up_status_helpers_cover_expected_states() -> None:
    assert is_follow_up_waiting_status(ChatMessageStatus.RESERVED) is True
    assert is_follow_up_waiting_status(ChatMessageStatus.SUBMISSION_PENDING) is True
    assert is_follow_up_waiting_status(ChatMessageStatus.PENDING) is True
    assert is_follow_up_waiting_status(ChatMessageStatus.COMPLETED) is False

    assert is_follow_up_terminal_failure(ChatMessageStatus.CANCELLED) is True
    assert is_follow_up_terminal_failure(ChatMessageStatus.FAILED) is True
    assert is_follow_up_terminal_failure(ChatMessageStatus.SUBMISSION_UNKNOWN) is False


def test_orphaned_follow_up_resolution_status_maps_only_recoverable_placeholders() -> None:
    assert (
        orphaned_follow_up_resolution_status(ChatMessageStatus.RESERVED)
        == ChatMessageStatus.CANCELLED
    )
    assert (
        orphaned_follow_up_resolution_status(ChatMessageStatus.SUBMISSION_PENDING)
        == ChatMessageStatus.SUBMISSION_UNKNOWN
    )
    assert orphaned_follow_up_resolution_status(ChatMessageStatus.PENDING) is None
    assert orphaned_follow_up_resolution_status(ChatMessageStatus.COMPLETED) is None


def test_can_launch_reserved_follow_up_requires_reserved_status_without_job() -> None:
    assert can_launch_reserved_follow_up(build_message(status=ChatMessageStatus.RESERVED)) is True
    assert (
        can_launch_reserved_follow_up(
            build_message(status=ChatMessageStatus.RESERVED, job_id="job-1")
        )
        is False
    )
    assert (
        can_launch_reserved_follow_up(
            build_message(status=ChatMessageStatus.SUBMISSION_PENDING)
        )
        is False
    )


def test_normalize_recovery_metadata_fields_drops_impossible_combinations() -> None:
    action, recovered_from, superseded_by = normalize_recovery_metadata_fields(
        message_id="message-1",
        recovery_action=MessageRecoveryAction.RETRY,
        recovered_from_message_id="message-0",
        superseded_by_message_id="message-2",
    )
    assert action is None
    assert recovered_from is None
    assert superseded_by is None

    action, recovered_from, superseded_by = normalize_recovery_metadata_fields(
        message_id="message-1",
        recovery_action=MessageRecoveryAction.CANCEL,
        recovered_from_message_id="message-0",
        superseded_by_message_id=None,
    )
    assert action == MessageRecoveryAction.CANCEL
    assert recovered_from is None
    assert superseded_by is None


@pytest.mark.parametrize(
    ("message", "error_text"),
    [
        (
            build_message(status=ChatMessageStatus.COMPLETED),
            "Only submission_unknown follow-ups can be recovered manually.",
        ),
        (
            build_message(job_id="job-1"),
            "This follow-up already has a job attached.",
        ),
        (
            build_message(agent_id=AgentId.USER),
            "Only agent follow-ups can be recovered manually.",
        ),
        (
            build_message(superseded_by_message_id="message-2"),
            "This uncertain follow-up was already retried.",
        ),
        (
            build_message(recovery_action=MessageRecoveryAction.CANCEL),
            "This uncertain follow-up was already resolved.",
        ),
    ],
)
def test_validate_manual_recovery_candidate_rejects_invalid_messages(
    message: ChatMessage,
    error_text: str,
) -> None:
    with pytest.raises(RuntimeError, match=error_text):
        validate_manual_recovery_candidate(message)


def test_validate_manual_recovery_candidate_accepts_unresolved_unknown_agent_follow_up() -> None:
    validate_manual_recovery_candidate(build_message())
