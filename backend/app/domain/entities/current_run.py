from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from backend.app.domain.entities.agent_configuration import (
    AgentConfiguration,
    AgentId,
    AgentPreset,
    SUPERVISOR_AGENT_IDS,
    SUPERVISOR_MEMBER_AGENT_IDS,
    TurnBudgetMode,
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
    SCRAPER = "scraper"


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
    has_turn_budget: bool = False
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
    preset: AgentPreset
    turn_budget_mode: TurnBudgetMode | None
    started_at: datetime | None
    updated_at: datetime | None
    completed_at: datetime | None
    participant_agent_ids: tuple[AgentId, ...]
    call_count: int
    stages: list[RunStageExecution]


def derive_current_run_execution(
    session: ChatSession,
    *,
    messages: list[ChatMessage],
    jobs_by_id: dict[str, Job] | None = None,
    run_configurations_by_id: dict[str, AgentConfiguration] | None = None,
) -> CurrentRunExecution | None:
    run_id = session.active_agent_run_id
    if not run_id:
        return None
    return _derive_run_execution(
        session,
        run_id=run_id,
        messages=messages,
        jobs_by_id=jobs_by_id,
        run_configurations_by_id=run_configurations_by_id,
        is_active=True,
    )


def derive_recent_run_executions(
    session: ChatSession,
    *,
    messages: list[ChatMessage],
    jobs_by_id: dict[str, Job] | None = None,
    run_configurations_by_id: dict[str, AgentConfiguration] | None = None,
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
        run_configurations_by_id=run_configurations_by_id,
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
            run_configurations_by_id=run_configurations_by_id,
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
    run_configurations_by_id: dict[str, AgentConfiguration] | None,
    is_active: bool,
) -> CurrentRunExecution:
    run_messages = [message for message in messages if message.run_id == run_id]
    configuration = _configuration_for_run(
        session=session,
        run_id=run_id,
        run_messages=run_messages,
        run_configurations_by_id=run_configurations_by_id,
        is_active=is_active,
    )
    run_preset = _run_preset_for_messages(configuration=configuration, run_messages=run_messages)
    turn_budget_mode = _turn_budget_mode_for_run(
        configuration=configuration,
        run_preset=run_preset,
    )

    if run_preset == AgentPreset.SUPERVISOR:
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
    participant_agent_ids = _participant_agent_ids_for_run(
        run_messages=run_messages,
        stages=stages,
        preset=run_preset,
    )
    return CurrentRunExecution(
        run_id=run_id,
        state=state,
        is_active=is_active,
        preset=run_preset,
        turn_budget_mode=turn_budget_mode,
        started_at=min(started_candidates) if started_candidates else None,
        updated_at=max(updated_candidates) if updated_candidates else None,
        completed_at=max(completed_candidates) if completed_candidates and state in _TERMINAL_STAGE_STATES else None,
        participant_agent_ids=participant_agent_ids,
        call_count=sum(stage.attempt_count for stage in stages if stage.attempt_count > 0),
        stages=stages,
    )


def _derive_legacy_stages(
    *,
    configuration: AgentConfiguration | None,
    run_messages: list[ChatMessage],
    jobs_by_id: dict[str, Job] | None,
    is_active: bool,
) -> list[RunStageExecution]:
    generator_config = configuration.agents[AgentId.GENERATOR] if configuration else None
    generator_message = _latest_stage_message(
        run_messages,
        agent_id=AgentId.GENERATOR,
        role=ChatMessageRole.ASSISTANT,
    )
    generator_stage = _derive_stage_from_message(
        stage=RunStageId.GENERATOR,
        message=generator_message,
        attempt_count=_count_stage_messages(
            run_messages,
            agent_id=AgentId.GENERATOR,
            role=ChatMessageRole.ASSISTANT,
        ),
        configured=True,
        max_turns=max(1, generator_config.max_turns) if generator_config else 0,
        has_turn_budget=generator_config is not None and generator_config.max_turns > 0,
        jobs_by_id=jobs_by_id,
        fallback_state=RunStageState.WAITING if is_active else RunStageState.SKIPPED,
    )

    reviewer_config = configuration.agents[AgentId.REVIEWER] if configuration else None
    reviewer_message = _latest_stage_message(
        run_messages,
        agent_id=AgentId.REVIEWER,
        role=ChatMessageRole.USER,
    )
    reviewer_configured = (reviewer_config.enabled if reviewer_config else False) or reviewer_message is not None
    reviewer_stage = _derive_stage_from_message(
        stage=RunStageId.REVIEWER,
        message=reviewer_message,
        attempt_count=_count_stage_messages(
            run_messages,
            agent_id=AgentId.REVIEWER,
            role=ChatMessageRole.USER,
        ),
        configured=reviewer_configured,
        max_turns=reviewer_config.max_turns if reviewer_config and reviewer_config.enabled else 0,
        has_turn_budget=reviewer_config is not None and reviewer_config.enabled and reviewer_config.max_turns > 0,
        jobs_by_id=jobs_by_id,
        fallback_state=_missing_follow_up_stage_state(
            previous_state=generator_stage.state,
            configured=reviewer_configured,
            is_active=is_active,
        ),
    )

    summary_config = configuration.agents[AgentId.SUMMARY] if configuration else None
    summary_prerequisite = (
        reviewer_stage.state if reviewer_config and reviewer_config.enabled else generator_stage.state
    )
    summary_message = _latest_stage_message(
        run_messages,
        agent_id=AgentId.SUMMARY,
        role=ChatMessageRole.ASSISTANT,
    )
    summary_configured = (summary_config.enabled if summary_config else False) or summary_message is not None
    summary_stage = _derive_stage_from_message(
        stage=RunStageId.SUMMARY,
        message=summary_message,
        attempt_count=_count_stage_messages(
            run_messages,
            agent_id=AgentId.SUMMARY,
            role=ChatMessageRole.ASSISTANT,
        ),
        configured=summary_configured,
        max_turns=summary_config.max_turns if summary_config and summary_config.enabled else 0,
        has_turn_budget=summary_config is not None and summary_config.enabled and summary_config.max_turns > 0,
        jobs_by_id=jobs_by_id,
        fallback_state=_missing_follow_up_stage_state(
            previous_state=summary_prerequisite,
            configured=summary_configured,
            is_active=is_active,
        ),
    )

    return [generator_stage, reviewer_stage, summary_stage]


def _derive_supervisor_stages(
    *,
    configuration: AgentConfiguration | None,
    run_messages: list[ChatMessage],
    jobs_by_id: dict[str, Job] | None,
    is_active: bool,
) -> list[RunStageExecution]:
    ordered_agent_ids = _supervisor_stage_agent_ids(
        configuration=configuration,
        run_messages=run_messages,
    )
    stages: list[RunStageExecution] = []
    previous_state = RunStageState.WAITING if is_active else RunStageState.SKIPPED
    for agent_id in ordered_agent_ids:
        definition = configuration.agents[agent_id] if configuration else None
        stage_message = _latest_stage_message(
            run_messages,
            agent_id=agent_id,
            role=ChatMessageRole.ASSISTANT,
        )
        attempt_count = _count_stage_messages(
            run_messages,
            agent_id=agent_id,
            role=ChatMessageRole.ASSISTANT,
        )
        configured_for_run = (definition.enabled if definition else False) or stage_message is not None
        effective_max_turns = _effective_supervisor_stage_budget(
            agent_id=agent_id,
            configuration=configuration,
            definition=definition,
        )
        stage = _derive_stage_from_message(
            stage=_stage_id_for_agent(agent_id),
            message=stage_message,
            attempt_count=attempt_count,
            configured=configured_for_run,
            max_turns=effective_max_turns,
            has_turn_budget=effective_max_turns > 0,
            jobs_by_id=jobs_by_id,
            fallback_state=(
                RunStageState.WAITING
                if agent_id == AgentId.SUPERVISOR and is_active
                else _missing_follow_up_stage_state(
                    previous_state=previous_state,
                    configured=configured_for_run,
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
        AgentId.SCRAPER: RunStageId.SCRAPER,
    }[agent_id]


def _agent_id_for_stage(stage: RunStageId) -> AgentId:
    return {
        RunStageId.GENERATOR: AgentId.GENERATOR,
        RunStageId.REVIEWER: AgentId.REVIEWER,
        RunStageId.SUMMARY: AgentId.SUMMARY,
        RunStageId.SUPERVISOR: AgentId.SUPERVISOR,
        RunStageId.QA: AgentId.QA,
        RunStageId.UX: AgentId.UX,
        RunStageId.SENIOR_ENGINEER: AgentId.SENIOR_ENGINEER,
        RunStageId.SCRAPER: AgentId.SCRAPER,
    }[stage]


def _derive_stage_from_message(
    *,
    stage: RunStageId,
    message: ChatMessage | None,
    attempt_count: int,
    configured: bool,
    max_turns: int,
    has_turn_budget: bool,
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
            has_turn_budget=has_turn_budget,
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
        has_turn_budget=has_turn_budget,
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


def _configuration_for_run(
    *,
    session: ChatSession,
    run_id: str,
    run_messages: list[ChatMessage],
    run_configurations_by_id: dict[str, AgentConfiguration] | None,
    is_active: bool,
) -> AgentConfiguration | None:
    if run_configurations_by_id and run_id in run_configurations_by_id:
        return run_configurations_by_id[run_id].normalized()
    if is_active:
        return session.agent_configuration.normalized()
    if not run_messages:
        return None
    return None


def _run_preset_for_messages(
    *,
    configuration: AgentConfiguration | None,
    run_messages: list[ChatMessage],
) -> AgentPreset:
    if configuration is not None and configuration.preset == AgentPreset.SUPERVISOR:
        return AgentPreset.SUPERVISOR
    if any(message.agent_id in SUPERVISOR_AGENT_IDS for message in run_messages):
        return AgentPreset.SUPERVISOR
    if any(message.agent_id == AgentId.SUMMARY for message in run_messages):
        return AgentPreset.TRIAD
    if any(message.agent_id == AgentId.REVIEWER for message in run_messages):
        return AgentPreset.REVIEW
    if configuration is not None:
        return configuration.preset
    return AgentPreset.SOLO


def _turn_budget_mode_for_run(
    *,
    configuration: AgentConfiguration | None,
    run_preset: AgentPreset,
) -> TurnBudgetMode | None:
    if run_preset != AgentPreset.SUPERVISOR:
        return TurnBudgetMode.EACH_AGENT
    if configuration is None:
        return None
    return configuration.turn_budget_mode


def _supervisor_stage_agent_ids(
    *,
    configuration: AgentConfiguration | None,
    run_messages: list[ChatMessage],
) -> tuple[AgentId, ...]:
    configured_members = set(configuration.supervisor_member_ids) if configuration else set()
    observed_members = {
        message.agent_id
        for message in run_messages
        if message.agent_id in SUPERVISOR_MEMBER_AGENT_IDS
    }
    return (
        AgentId.SUPERVISOR,
        *(
            agent_id
            for agent_id in SUPERVISOR_MEMBER_AGENT_IDS
            if agent_id in configured_members or agent_id in observed_members
        ),
    )


def _participant_agent_ids_for_run(
    *,
    run_messages: list[ChatMessage],
    stages: list[RunStageExecution],
    preset: AgentPreset,
) -> tuple[AgentId, ...]:
    observed_agent_ids = tuple(
        agent_id
        for agent_id in (
            AgentId.SUPERVISOR,
            *SUPERVISOR_MEMBER_AGENT_IDS,
        )
        if any(message.agent_id == agent_id for message in run_messages)
    )
    if observed_agent_ids:
        return observed_agent_ids
    if preset == AgentPreset.SUPERVISOR:
        return tuple(
            _agent_id_for_stage(stage.stage)
            for stage in stages
            if stage.configured and _agent_id_for_stage(stage.stage) in SUPERVISOR_AGENT_IDS
        )
    return tuple(
        _agent_id_for_stage(stage.stage)
        for stage in stages
        if stage.configured and stage.attempt_count > 0
    )


def _effective_supervisor_stage_budget(
    *,
    agent_id: AgentId,
    configuration: AgentConfiguration | None,
    definition,
) -> int:
    if definition is None or not definition.enabled:
        return 0
    if agent_id == AgentId.SUPERVISOR:
        return definition.max_turns
    if configuration is None or configuration.turn_budget_mode != TurnBudgetMode.EACH_AGENT:
        return 0
    return definition.max_turns


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
