from __future__ import annotations

from enum import StrEnum

from backend.app.domain.entities.agent_configuration import AgentId, AgentTriggerSource
from backend.app.domain.entities.chat_message import (
    ChatMessage,
    ChatMessageRole,
    ChatMessageStatus,
)
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.job import Job, JobStatus


class ReviewerLifecycleState(StrEnum):
    OFF = "off"
    DISABLED = "disabled"
    IDLE = "idle"
    WAITING_ON_GENERATOR = "waiting_on_generator"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


def derive_reviewer_lifecycle_state(
    session: ChatSession,
    *,
    messages: list[ChatMessage],
    jobs_by_id: dict[str, Job] | None = None,
) -> ReviewerLifecycleState:
    configuration = session.agent_configuration.normalized()
    reviewer = configuration.agents[AgentId.REVIEWER]
    if not session.auto_mode_enabled:
        return ReviewerLifecycleState.OFF
    if not reviewer.enabled or reviewer.max_turns <= 0:
        return ReviewerLifecycleState.DISABLED

    target_run_id = session.active_agent_run_id or _latest_run_id(messages)
    if not target_run_id:
        return ReviewerLifecycleState.IDLE

    run_messages = [message for message in messages if message.run_id == target_run_id]
    reviewer_message = _latest_message(run_messages, agent_id=AgentId.REVIEWER)
    if reviewer_message is not None:
        generator_follow_up = _latest_message(
            run_messages,
            agent_id=AgentId.GENERATOR,
            role=ChatMessageRole.ASSISTANT,
        )
        if _reviewer_waiting_on_follow_up_generator(
            reviewer_message=reviewer_message,
            generator_message=generator_follow_up,
            jobs_by_id=jobs_by_id,
        ):
            return ReviewerLifecycleState.WAITING_ON_GENERATOR
        return _reviewer_state_from_message(reviewer_message, jobs_by_id=jobs_by_id)

    generator_message = _latest_message(
        run_messages,
        agent_id=AgentId.GENERATOR,
        role=ChatMessageRole.ASSISTANT,
    )
    generator_job = _job_for_message(generator_message, jobs_by_id=jobs_by_id)
    if generator_job is not None:
        return _state_from_generator_job(generator_job.status)
    if generator_message is not None:
        return _state_from_generator_message(generator_message.status)

    if session.active_agent_run_id == target_run_id:
        return ReviewerLifecycleState.WAITING_ON_GENERATOR
    return ReviewerLifecycleState.IDLE


def _latest_run_id(messages: list[ChatMessage]) -> str | None:
    for message in reversed(messages):
        if message.run_id:
            return message.run_id
    return None


def _latest_message(
    messages: list[ChatMessage],
    *,
    agent_id: AgentId,
    role: ChatMessageRole | None = None,
) -> ChatMessage | None:
    for message in reversed(messages):
        if message.agent_id != agent_id:
            continue
        if role is not None and message.role != role:
            continue
        return message
    return None


def _job_for_message(
    message: ChatMessage | None,
    *,
    jobs_by_id: dict[str, Job] | None,
) -> Job | None:
    if message is None or jobs_by_id is None or message.job_id is None:
        return None
    return jobs_by_id.get(message.job_id)


def _reviewer_state_from_message(
    message: ChatMessage,
    *,
    jobs_by_id: dict[str, Job] | None,
) -> ReviewerLifecycleState:
    reviewer_job = _job_for_message(message, jobs_by_id=jobs_by_id)
    if reviewer_job is not None:
        return _state_from_reviewer_job(reviewer_job.status)

    return _state_from_reviewer_message(message.status)


def _reviewer_waiting_on_follow_up_generator(
    *,
    reviewer_message: ChatMessage,
    generator_message: ChatMessage | None,
    jobs_by_id: dict[str, Job] | None,
) -> bool:
    if generator_message is None:
        return False
    if generator_message.trigger_source != AgentTriggerSource.REVIEWER:
        return False
    if generator_message.created_at <= reviewer_message.created_at:
        return False

    generator_job = _job_for_message(generator_message, jobs_by_id=jobs_by_id)
    if generator_job is not None:
        return generator_job.status in {
            JobStatus.PENDING,
            JobStatus.RUNNING,
        }

    return generator_message.status in {
        ChatMessageStatus.RESERVED,
        ChatMessageStatus.SUBMISSION_PENDING,
        ChatMessageStatus.PENDING,
    }


def _state_from_reviewer_job(status: JobStatus) -> ReviewerLifecycleState:
    return {
        JobStatus.PENDING: ReviewerLifecycleState.QUEUED,
        JobStatus.RUNNING: ReviewerLifecycleState.RUNNING,
        JobStatus.COMPLETED: ReviewerLifecycleState.COMPLETED,
        JobStatus.FAILED: ReviewerLifecycleState.FAILED,
        JobStatus.CANCELLED: ReviewerLifecycleState.FAILED,
    }[status]


def _state_from_reviewer_message(status: ChatMessageStatus) -> ReviewerLifecycleState:
    return {
        ChatMessageStatus.RESERVED: ReviewerLifecycleState.QUEUED,
        ChatMessageStatus.SUBMISSION_PENDING: ReviewerLifecycleState.QUEUED,
        ChatMessageStatus.PENDING: ReviewerLifecycleState.RUNNING,
        ChatMessageStatus.COMPLETED: ReviewerLifecycleState.COMPLETED,
        ChatMessageStatus.FAILED: ReviewerLifecycleState.FAILED,
        ChatMessageStatus.CANCELLED: ReviewerLifecycleState.FAILED,
        ChatMessageStatus.SUBMISSION_UNKNOWN: ReviewerLifecycleState.FAILED,
    }[status]


def _state_from_generator_job(status: JobStatus) -> ReviewerLifecycleState:
    return {
        JobStatus.PENDING: ReviewerLifecycleState.WAITING_ON_GENERATOR,
        JobStatus.RUNNING: ReviewerLifecycleState.WAITING_ON_GENERATOR,
        JobStatus.COMPLETED: ReviewerLifecycleState.SKIPPED,
        JobStatus.FAILED: ReviewerLifecycleState.SKIPPED,
        JobStatus.CANCELLED: ReviewerLifecycleState.SKIPPED,
    }[status]


def _state_from_generator_message(status: ChatMessageStatus) -> ReviewerLifecycleState:
    return {
        ChatMessageStatus.RESERVED: ReviewerLifecycleState.WAITING_ON_GENERATOR,
        ChatMessageStatus.SUBMISSION_PENDING: ReviewerLifecycleState.WAITING_ON_GENERATOR,
        ChatMessageStatus.PENDING: ReviewerLifecycleState.WAITING_ON_GENERATOR,
        ChatMessageStatus.COMPLETED: ReviewerLifecycleState.SKIPPED,
        ChatMessageStatus.FAILED: ReviewerLifecycleState.SKIPPED,
        ChatMessageStatus.CANCELLED: ReviewerLifecycleState.SKIPPED,
        ChatMessageStatus.SUBMISSION_UNKNOWN: ReviewerLifecycleState.SKIPPED,
    }[status]
