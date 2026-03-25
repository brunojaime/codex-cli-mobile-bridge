from __future__ import annotations

from dataclasses import replace

from backend.app.domain.entities.agent_configuration import (
    AgentConfiguration,
    AgentId,
    AgentTriggerSource,
    AgentType,
)
from backend.app.domain.entities.chat_message import (
    ChatMessage,
    ChatMessageAuthorType,
    ChatMessageRole,
    ChatMessageStatus,
)
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.job import Job, JobStatus
from backend.app.domain.entities.reviewer_status import (
    ReviewerLifecycleState,
    derive_reviewer_lifecycle_state,
)


def build_session(
    *,
    auto_mode_enabled: bool = True,
    reviewer_enabled: bool = True,
    reviewer_max_turns: int = 1,
    active_run_id: str | None = "run-current",
) -> ChatSession:
    configuration = AgentConfiguration.default()
    configuration.agents[AgentId.REVIEWER] = replace(
        configuration.agents[AgentId.REVIEWER],
        enabled=reviewer_enabled,
        max_turns=reviewer_max_turns,
    )
    configuration.agents[AgentId.SUMMARY] = replace(
        configuration.agents[AgentId.SUMMARY],
        enabled=False,
        max_turns=0,
    )
    configuration = configuration.normalized()
    return ChatSession(
        id="session-1",
        title="Reviewer status",
        workspace_path="/workspace",
        workspace_name="Workspace",
        agent_configuration=configuration,
        auto_mode_enabled=auto_mode_enabled,
        auto_max_turns=reviewer_max_turns,
        active_agent_run_id=active_run_id,
    )


def build_message(
    *,
    message_id: str,
    run_id: str,
    agent_id: AgentId,
    status: ChatMessageStatus,
    job_id: str | None = None,
    trigger_source: AgentTriggerSource | None = None,
) -> ChatMessage:
    return ChatMessage(
        id=message_id,
        session_id="session-1",
        role=ChatMessageRole.USER if agent_id == AgentId.REVIEWER else ChatMessageRole.ASSISTANT,
        author_type=(
            ChatMessageAuthorType.REVIEWER_CODEX
            if agent_id == AgentId.REVIEWER
            else ChatMessageAuthorType.ASSISTANT
        ),
        content="message",
        status=status,
        agent_id=agent_id,
        agent_type={
            AgentId.GENERATOR: AgentType.GENERATOR,
            AgentId.REVIEWER: AgentType.REVIEWER,
            AgentId.SUMMARY: AgentType.SUMMARY,
            AgentId.USER: AgentType.HUMAN,
        }[agent_id],
        trigger_source=trigger_source
        or (
            AgentTriggerSource.GENERATOR
            if agent_id == AgentId.REVIEWER
            else AgentTriggerSource.USER
        ),
        run_id=run_id,
        job_id=job_id,
    )


def build_job(
    *,
    job_id: str,
    run_id: str,
    agent_id: AgentId,
    status: JobStatus,
) -> Job:
    return Job(
        id=job_id,
        session_id="session-1",
        message="job",
        status=status,
        run_id=run_id,
        agent_id=agent_id,
        agent_type={
            AgentId.GENERATOR: AgentType.GENERATOR,
            AgentId.REVIEWER: AgentType.REVIEWER,
            AgentId.SUMMARY: AgentType.SUMMARY,
            AgentId.USER: AgentType.HUMAN,
        }[agent_id],
    )


def test_reviewer_state_is_off_when_auto_mode_is_disabled() -> None:
    session = build_session(auto_mode_enabled=False, reviewer_enabled=True)

    state = derive_reviewer_lifecycle_state(session, messages=[])

    assert state == ReviewerLifecycleState.OFF


def test_reviewer_state_is_disabled_when_reviewer_turns_are_disabled() -> None:
    session = build_session(reviewer_enabled=False, reviewer_max_turns=0)

    state = derive_reviewer_lifecycle_state(session, messages=[])

    assert state == ReviewerLifecycleState.DISABLED


def test_reviewer_state_prefers_the_active_run_over_previous_completed_runs() -> None:
    session = build_session(active_run_id="run-current")
    messages = [
        build_message(
            message_id="reviewer-old",
            run_id="run-old",
            agent_id=AgentId.REVIEWER,
            status=ChatMessageStatus.COMPLETED,
        ),
        build_message(
            message_id="generator-current",
            run_id="run-current",
            agent_id=AgentId.GENERATOR,
            status=ChatMessageStatus.PENDING,
        ),
    ]

    state = derive_reviewer_lifecycle_state(session, messages=messages)

    assert state == ReviewerLifecycleState.WAITING_ON_GENERATOR


def test_reviewer_state_uses_job_status_to_distinguish_queued_and_running() -> None:
    session = build_session(active_run_id="run-current")
    queued_message = build_message(
        message_id="reviewer-queued",
        run_id="run-current",
        agent_id=AgentId.REVIEWER,
        status=ChatMessageStatus.RESERVED,
        job_id="job-reviewer",
    )

    queued_state = derive_reviewer_lifecycle_state(
        session,
        messages=[queued_message],
        jobs_by_id={
            "job-reviewer": build_job(
                job_id="job-reviewer",
                run_id="run-current",
                agent_id=AgentId.REVIEWER,
                status=JobStatus.PENDING,
            )
        },
    )
    running_state = derive_reviewer_lifecycle_state(
        session,
        messages=[queued_message],
        jobs_by_id={
            "job-reviewer": build_job(
                job_id="job-reviewer",
                run_id="run-current",
                agent_id=AgentId.REVIEWER,
                status=JobStatus.RUNNING,
            )
        },
    )

    assert queued_state == ReviewerLifecycleState.QUEUED
    assert running_state == ReviewerLifecycleState.RUNNING


def test_reviewer_state_marks_missing_reviewer_after_generator_completion_as_skipped() -> None:
    session = build_session(active_run_id="run-current")

    completed_state = derive_reviewer_lifecycle_state(
        session,
        messages=[
            build_message(
                message_id="generator-complete",
                run_id="run-current",
                agent_id=AgentId.GENERATOR,
                status=ChatMessageStatus.COMPLETED,
            )
        ],
    )
    failed_state = derive_reviewer_lifecycle_state(
        session,
        messages=[
            build_message(
                message_id="generator-failed",
                run_id="run-current",
                agent_id=AgentId.GENERATOR,
                status=ChatMessageStatus.FAILED,
            )
        ],
    )
    cancelled_state = derive_reviewer_lifecycle_state(
        session,
        messages=[
            build_message(
                message_id="generator-cancelled",
                run_id="run-current",
                agent_id=AgentId.GENERATOR,
                status=ChatMessageStatus.CANCELLED,
            )
        ],
    )

    assert completed_state == ReviewerLifecycleState.SKIPPED
    assert failed_state == ReviewerLifecycleState.SKIPPED
    assert cancelled_state == ReviewerLifecycleState.SKIPPED


def test_reviewer_state_defaults_to_waiting_when_active_run_has_no_messages_yet() -> None:
    session = build_session(active_run_id="run-current")

    state = derive_reviewer_lifecycle_state(session, messages=[])

    assert state == ReviewerLifecycleState.WAITING_ON_GENERATOR


def test_reviewer_state_waits_on_generator_after_a_completed_reviewer_turn() -> None:
    session = build_session(
        active_run_id="run-current",
        reviewer_max_turns=2,
    )

    state = derive_reviewer_lifecycle_state(
        session,
        messages=[
            build_message(
                message_id="reviewer-complete",
                run_id="run-current",
                agent_id=AgentId.REVIEWER,
                status=ChatMessageStatus.COMPLETED,
            ),
            build_message(
                message_id="generator-follow-up",
                run_id="run-current",
                agent_id=AgentId.GENERATOR,
                status=ChatMessageStatus.PENDING,
                trigger_source=AgentTriggerSource.REVIEWER,
            ),
        ],
    )

    assert state == ReviewerLifecycleState.WAITING_ON_GENERATOR
