from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from backend.app.domain.entities.agent_configuration import (
    AgentId,
    AgentPreset,
    SUPERVISOR_MEMBER_AGENT_IDS,
)
from backend.app.domain.entities.chat_message import (
    ChatMessage,
    ChatMessageRole,
    ChatMessageStatus,
)
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.job import Job, JobStatus


class RunStageId(StrEnum):
    GENERATOR = "generator"
    REVIEWER = "reviewer"
    SUMMARY = "summary"
    SUPERVISOR = "supervisor"
    QA = "qa"
    UX = "ux"
    SENIOR_ENGINEER = "senior_engineer"


class RunStageState(StrEnum):
    DISABLED = "disabled"
    WAITING = "waiting"
    NOT_SCHEDULED = "not_scheduled"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STALE = "stale"
    SKIPPED = "skipped"


@dataclass(slots=True)
class RunStageExecution:
    stage: RunStageId
    state: RunStageState
    configured: bool
    attempt_count: int = 0
    max_turns: int = 0
    message_id: str | None = None
    job_id: str | None = None
    job_status: JobStatus | None = None
    latest_activity: str | None = None
    started_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass(slots=True)
class CurrentRunExecution:
    run_id: str
    state: RunStageState
    is_active: bool
    started_at: datetime | None
    updated_at: datetime | None
    completed_at: datetime | None
    stages: list[RunStageExecution]


def derive_current_run_execution(
    session: ChatSession,
    *,
    messages: list[ChatMessage],
    jobs_by_id: dict[str, Job] | None = None,
) -> CurrentRunExecution | None:
    run_id = session.active_agent_run_id
    if not run_id:
        return None
    return _derive_run_execution(
        session,
        run_id=run_id,
        messages=messages,
        jobs_by_id=jobs_by_id,
        is_active=True,
    )


def derive_recent_run_executions(
    session: ChatSession,
    *,
    messages: list[ChatMessage],
    jobs_by_id: dict[str, Job] | None = None,
    limit: int = 5,
) -> list[CurrentRunExecution]:
    if limit <= 0:
        return []

    runs: list[CurrentRunExecution] = []
    seen_run_ids: set[str] = set()
    active_run = derive_current_run_execution(
        session,
        messages=messages,
        jobs_by_id=jobs_by_id,
    )
    if active_run is not None:
        runs.append(active_run)
        seen_run_ids.add(active_run.run_id)

    historical_run_ids = {
        message.run_id
        for message in messages
        if message.run_id and message.run_id not in seen_run_ids
    }
    historical_runs = [
        _derive_run_execution(
            session,
            run_id=run_id,
            messages=messages,
            jobs_by_id=jobs_by_id,
            is_active=False,
        )
        for run_id in historical_run_ids
    ]
    historical_runs.sort(
        key=lambda run: (
            run.updated_at
            or run.completed_at
            or run.started_at
            or datetime.min.replace(tzinfo=timezone.utc)
        ),
        reverse=True,
    )
    runs.extend(historical_runs)
    return runs[:limit]


def _derive_run_execution(
    session: ChatSession,
    *,
    run_id: str,
    messages: list[ChatMessage],
    jobs_by_id: dict[str, Job] | None,
    is_active: bool,
) -> CurrentRunExecution:
    configuration = session.agent_configuration.normalized()
    run_messages = [message for message in messages if message.run_id == run_id]

    if configuration.preset == AgentPreset.SUPERVISOR:
        stages = _derive_supervisor_stages(
            configuration=configuration,
            run_messages=run_messages,
            jobs_by_id=jobs_by_id,
            is_active=is_active,
        )
    else:
        stages = _derive_legacy_stages(
            configuration=configuration,
            run_messages=run_messages,
            jobs_by_id=jobs_by_id,
            is_active=is_active,
        )

    state = _derive_run_state(stages, is_active=is_active)
    started_candidates = [
        stage.started_at or stage.updated_at
        for stage in stages
        if stage.started_at or stage.updated_at
    ]
    updated_candidates = [
        stage.completed_at or stage.updated_at or stage.started_at
        for stage in stages
        if stage.completed_at or stage.updated_at or stage.started_at
    ]
    completed_candidates = [
        stage.completed_at or stage.updated_at
        for stage in stages
        if stage.state in _TERMINAL_STAGE_STATES and (stage.completed_at or stage.updated_at)
    ]
    return CurrentRunExecution(
        run_id=run_id,
        state=state,
        is_active=is_active,
        started_at=min(started_candidates) if started_candidates else None,
        updated_at=max(updated_candidates) if updated_candidates else None,
        completed_at=max(completed_candidates) if completed_candidates and state in _TERMINAL_STAGE_STATES else None,
        stages=stages,
    )


def _derive_legacy_stages(
    *,
    configuration,
    run_messages: list[ChatMessage],
    jobs_by_id: dict[str, Job] | None,
    is_active: bool,
) -> list[RunStageExecution]:
    generator_config = configuration.agents[AgentId.GENERATOR]
    generator_stage = _derive_stage_from_message(
        stage=RunStageId.GENERATOR,
        message=_latest_stage_message(
            run_messages,
            agent_id=AgentId.GENERATOR,
            role=ChatMessageRole.ASSISTANT,
        ),
        attempt_count=_count_stage_messages(
            run_messages,
            agent_id=AgentId.GENERATOR,
            role=ChatMessageRole.ASSISTANT,
        ),
        configured=True,
        max_turns=max(1, generator_config.max_turns),
        jobs_by_id=jobs_by_id,
        fallback_state=RunStageState.WAITING if is_active else RunStageState.SKIPPED,
    )

    reviewer_config = configuration.agents[AgentId.REVIEWER]
    reviewer_stage = _derive_stage_from_message(
        stage=RunStageId.REVIEWER,
        message=_latest_stage_message(
            run_messages,
            agent_id=AgentId.REVIEWER,
            role=ChatMessageRole.USER,
        ),
        attempt_count=_count_stage_messages(
            run_messages,
            agent_id=AgentId.REVIEWER,
            role=ChatMessageRole.USER,
        ),
        configured=reviewer_config.enabled,
        max_turns=reviewer_config.max_turns if reviewer_config.enabled else 0,
        jobs_by_id=jobs_by_id,
        fallback_state=_missing_follow_up_stage_state(
            previous_state=generator_stage.state,
            configured=reviewer_config.enabled,
            is_active=is_active,
        ),
    )

    summary_config = configuration.agents[AgentId.SUMMARY]
    summary_prerequisite = (
        reviewer_stage.state if reviewer_config.enabled else generator_stage.state
    )
    summary_stage = _derive_stage_from_message(
        stage=RunStageId.SUMMARY,
        message=_latest_stage_message(
            run_messages,
            agent_id=AgentId.SUMMARY,
            role=ChatMessageRole.ASSISTANT,
        ),
        attempt_count=_count_stage_messages(
            run_messages,
            agent_id=AgentId.SUMMARY,
            role=ChatMessageRole.ASSISTANT,
        ),
        configured=summary_config.enabled,
        max_turns=summary_config.max_turns if summary_config.enabled else 0,
        jobs_by_id=jobs_by_id,
        fallback_state=_missing_follow_up_stage_state(
            previous_state=summary_prerequisite,
            configured=summary_config.enabled,
            is_active=is_active,
        ),
    )

    return [generator_stage, reviewer_stage, summary_stage]


def _derive_supervisor_stages(
    *,
    configuration,
    run_messages: list[ChatMessage],
    jobs_by_id: dict[str, Job] | None,
    is_active: bool,
) -> list[RunStageExecution]:
    ordered_agent_ids = (AgentId.SUPERVISOR, *configuration.supervisor_member_ids)
    stages: list[RunStageExecution] = []
    previous_state = RunStageState.WAITING if is_active else RunStageState.SKIPPED
    for agent_id in ordered_agent_ids:
        definition = configuration.agents[agent_id]
        stage = _derive_stage_from_message(
            stage=_stage_id_for_agent(agent_id),
            message=_latest_stage_message(
                run_messages,
                agent_id=agent_id,
                role=ChatMessageRole.ASSISTANT,
            ),
            attempt_count=_count_stage_messages(
                run_messages,
                agent_id=agent_id,
                role=ChatMessageRole.ASSISTANT,
            ),
            configured=definition.enabled,
            max_turns=definition.max_turns if definition.enabled else 0,
            jobs_by_id=jobs_by_id,
            fallback_state=(
                RunStageState.WAITING
                if agent_id == AgentId.SUPERVISOR and is_active
                else _missing_follow_up_stage_state(
                    previous_state=previous_state,
                    configured=definition.enabled,
                    is_active=is_active,
                )
            ),
        )
        stages.append(stage)
        previous_state = stage.state
    return stages


def _stage_id_for_agent(agent_id: AgentId) -> RunStageId:
    return {
        AgentId.GENERATOR: RunStageId.GENERATOR,
        AgentId.REVIEWER: RunStageId.REVIEWER,
        AgentId.SUMMARY: RunStageId.SUMMARY,
        AgentId.SUPERVISOR: RunStageId.SUPERVISOR,
        AgentId.QA: RunStageId.QA,
        AgentId.UX: RunStageId.UX,
        AgentId.SENIOR_ENGINEER: RunStageId.SENIOR_ENGINEER,
    }[agent_id]


def _derive_stage_from_message(
    *,
    stage: RunStageId,
    message: ChatMessage | None,
    attempt_count: int,
    configured: bool,
    max_turns: int,
    jobs_by_id: dict[str, Job] | None,
    fallback_state: RunStageState,
) -> RunStageExecution:
    if message is None:
        return RunStageExecution(
            stage=stage,
            state=RunStageState.DISABLED if not configured else fallback_state,
            configured=configured,
            attempt_count=attempt_count,
            max_turns=max_turns,
        )

    job = _job_for_message(message, jobs_by_id=jobs_by_id)
    state = _stage_state_from_job(job.status) if job is not None else _stage_state_from_message(
        message.status
    )
    started_at = job.created_at if job is not None else message.created_at
    updated_at = job.updated_at if job is not None else message.updated_at
    completed_at = job.completed_at if job is not None else (
        message.updated_at if state in _TERMINAL_STAGE_STATES else None
    )
    return RunStageExecution(
        stage=stage,
        state=state,
        configured=configured,
        attempt_count=max(1, attempt_count),
        max_turns=max_turns,
        message_id=message.id,
        job_id=message.job_id,
        job_status=job.status if job is not None else None,
        latest_activity=job.latest_activity if job is not None else None,
        started_at=started_at,
        updated_at=updated_at,
        completed_at=completed_at,
    )


def _missing_follow_up_stage_state(
    *,
    previous_state: RunStageState,
    configured: bool,
    is_active: bool,
) -> RunStageState:
    if not configured:
        return RunStageState.DISABLED
    if is_active:
        if previous_state in {
            RunStageState.WAITING,
            RunStageState.NOT_SCHEDULED,
            RunStageState.QUEUED,
            RunStageState.RUNNING,
        }:
            return RunStageState.WAITING
        if previous_state == RunStageState.COMPLETED:
            return RunStageState.NOT_SCHEDULED
    return RunStageState.SKIPPED


def _derive_run_state(
    stages: list[RunStageExecution],
    *,
    is_active: bool,
) -> RunStageState:
    states = [stage.state for stage in stages]
    if RunStageState.RUNNING in states:
        return RunStageState.RUNNING
    if RunStageState.QUEUED in states:
        return RunStageState.QUEUED
    if RunStageState.FAILED in states:
        return RunStageState.FAILED
    if RunStageState.CANCELLED in states:
        return RunStageState.CANCELLED
    if RunStageState.STALE in states:
        return RunStageState.STALE
    if is_active:
        if RunStageState.NOT_SCHEDULED in states:
            return RunStageState.NOT_SCHEDULED
        if RunStageState.WAITING in states:
            return RunStageState.WAITING
    if RunStageState.COMPLETED in states:
        return RunStageState.COMPLETED
    return RunStageState.SKIPPED


def _latest_stage_message(
    messages: list[ChatMessage],
    *,
    agent_id: AgentId,
    role: ChatMessageRole,
) -> ChatMessage | None:
    for message in reversed(messages):
        if message.agent_id == agent_id and message.role == role:
            return message
    return None


def _count_stage_messages(
    messages: list[ChatMessage],
    *,
    agent_id: AgentId,
    role: ChatMessageRole,
) -> int:
    return sum(
        1
        for message in messages
        if message.agent_id == agent_id and message.role == role
    )


def _job_for_message(
    message: ChatMessage,
    *,
    jobs_by_id: dict[str, Job] | None,
) -> Job | None:
    if jobs_by_id is None or message.job_id is None:
        return None
    return jobs_by_id.get(message.job_id)


def _stage_state_from_job(job_status: JobStatus) -> RunStageState:
    return {
        JobStatus.PENDING: RunStageState.QUEUED,
        JobStatus.RUNNING: RunStageState.RUNNING,
        JobStatus.COMPLETED: RunStageState.COMPLETED,
        JobStatus.FAILED: RunStageState.FAILED,
        JobStatus.CANCELLED: RunStageState.CANCELLED,
    }[job_status]


def _stage_state_from_message(message_status: ChatMessageStatus) -> RunStageState:
    return {
        ChatMessageStatus.RESERVED: RunStageState.QUEUED,
        ChatMessageStatus.SUBMISSION_PENDING: RunStageState.QUEUED,
        ChatMessageStatus.SUBMISSION_UNKNOWN: RunStageState.STALE,
        ChatMessageStatus.PENDING: RunStageState.RUNNING,
        ChatMessageStatus.COMPLETED: RunStageState.COMPLETED,
        ChatMessageStatus.FAILED: RunStageState.FAILED,
        ChatMessageStatus.CANCELLED: RunStageState.CANCELLED,
    }[message_status]


_TERMINAL_STAGE_STATES = {
    RunStageState.COMPLETED,
    RunStageState.FAILED,
    RunStageState.CANCELLED,
    RunStageState.STALE,
    RunStageState.SKIPPED,
    RunStageState.DISABLED,
}
