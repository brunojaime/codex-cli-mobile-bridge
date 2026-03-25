from __future__ import annotations

from dataclasses import dataclass

from backend.app.domain.entities.agent_configuration import AgentId
from backend.app.domain.entities.chat_message import (
    ChatMessage,
    ChatMessageAuthorType,
    ChatMessageRole,
    ChatMessageStatus,
)
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.current_run import (
    CurrentRunExecution,
    RunStageExecution,
    RunStageId,
    RunStageState,
)


@dataclass(slots=True, frozen=True)
class ConversationProduct:
    status_line: str
    description: str
    latest_update: str | None = None
    current_focus: str | None = None
    next_step: str | None = None


_USER_FACING_AGENT_IDS = (
    AgentId.SUMMARY,
    AgentId.SUPERVISOR,
    AgentId.GENERATOR,
)
_CURRENT_FOCUS_STATE_PRIORITY = (
    RunStageState.RUNNING,
    RunStageState.FAILED,
    RunStageState.STALE,
    RunStageState.QUEUED,
    RunStageState.NOT_SCHEDULED,
    RunStageState.WAITING,
)
_NEXT_STEP_STATES = (
    RunStageState.QUEUED,
    RunStageState.NOT_SCHEDULED,
    RunStageState.WAITING,
)


def derive_conversation_product(
    session: ChatSession,
    *,
    messages: list[ChatMessage],
    current_run: CurrentRunExecution | None,
    recent_runs: list[CurrentRunExecution],
) -> ConversationProduct:
    latest_update = _latest_user_facing_update(messages)
    current_focus = _current_focus(session, current_run)
    next_step = _next_step(session, current_run)
    status_line = _status_line(session, current_run, recent_runs)
    description = _description(
        messages,
        latest_update=latest_update,
        current_focus=current_focus,
    )
    return ConversationProduct(
        status_line=status_line,
        description=description,
        latest_update=latest_update,
        current_focus=current_focus,
        next_step=next_step,
    )


def _status_line(
    session: ChatSession,
    current_run: CurrentRunExecution | None,
    recent_runs: list[CurrentRunExecution],
) -> str:
    if current_run is not None:
        focus_stage = _first_stage_by_state(current_run, _CURRENT_FOCUS_STATE_PRIORITY)
        if focus_stage is not None:
            label = _agent_label(session, _agent_id_for_stage(focus_stage.stage))
            if focus_stage.state == RunStageState.RUNNING:
                return f"{label} running"
            if focus_stage.state in {RunStageState.FAILED, RunStageState.STALE}:
                return f"{label} needs attention"
            return f"{label} queued next"
        return "Run in progress"

    latest_completed_run = next(
        (run for run in recent_runs if not run.is_active),
        None,
    )
    if latest_completed_run is None:
        return "Ready for the next turn"
    if latest_completed_run.state == RunStageState.COMPLETED:
        return "Last run completed"
    if latest_completed_run.state in {
        RunStageState.FAILED,
        RunStageState.CANCELLED,
        RunStageState.STALE,
    }:
        return "Last run needs attention"
    return "Ready for the next turn"


def _description(
    messages: list[ChatMessage],
    *,
    latest_update: str | None,
    current_focus: str | None,
) -> str:
    if latest_update and current_focus:
        return _compact_text(f"{latest_update} Now: {current_focus}", limit=220)
    if latest_update:
        return latest_update
    if current_focus:
        return current_focus

    latest_user_message = next(
        (
            _compact_text(message.content, limit=220)
            for message in reversed(messages)
            if message.role == ChatMessageRole.USER
            and message.author_type == ChatMessageAuthorType.HUMAN
            and message.content.strip()
        ),
        None,
    )
    if latest_user_message is not None:
        return latest_user_message

    latest_assistant_message = next(
        (
            _compact_text(message.content, limit=220)
            for message in reversed(messages)
            if message.role == ChatMessageRole.ASSISTANT
            and message.content.strip()
        ),
        None,
    )
    if latest_assistant_message is not None:
        return latest_assistant_message
    return "No messages yet."


def _latest_user_facing_update(messages: list[ChatMessage]) -> str | None:
    prioritized = _latest_assistant_message(
        messages,
        preferred_agents=_USER_FACING_AGENT_IDS,
    )
    if prioritized is not None:
        return prioritized
    return _latest_assistant_message(messages, preferred_agents=())


def _latest_assistant_message(
    messages: list[ChatMessage],
    *,
    preferred_agents: tuple[AgentId, ...],
) -> str | None:
    preferred_agent_set = set(preferred_agents)
    for message in reversed(messages):
        if (
            message.role != ChatMessageRole.ASSISTANT
            or message.status != ChatMessageStatus.COMPLETED
            or not message.content.strip()
        ):
            continue
        if preferred_agent_set and message.agent_id not in preferred_agent_set:
            continue
        return _compact_text(message.content, limit=220)
    return None


def _current_focus(
    session: ChatSession,
    current_run: CurrentRunExecution | None,
) -> str | None:
    if current_run is None:
        return None
    stage = _first_stage_by_state(current_run, _CURRENT_FOCUS_STATE_PRIORITY)
    if stage is None:
        return None

    label = _agent_label(session, _agent_id_for_stage(stage.stage))
    if stage.state == RunStageState.RUNNING:
        activity = _compact_text(stage.latest_activity, limit=120)
        if activity:
            return f"{label} is active: {activity}"
        return f"{label} is working now."
    if stage.state == RunStageState.FAILED:
        activity = _compact_text(stage.latest_activity, limit=120)
        if activity:
            return f"{label} failed: {activity}"
        return f"{label} failed and needs attention."
    if stage.state == RunStageState.STALE:
        return f"{label} needs recovery before the run can continue."
    if stage.state == RunStageState.QUEUED:
        return f"{label} is queued to start."
    if stage.state == RunStageState.NOT_SCHEDULED:
        return f"{label} should start next."
    if stage.state == RunStageState.WAITING:
        return f"{label} is waiting for the previous stage."
    return None


def _next_step(
    session: ChatSession,
    current_run: CurrentRunExecution | None,
) -> str | None:
    if current_run is None:
        return "Waiting for your next message."
    for state in _NEXT_STEP_STATES:
        for stage in current_run.stages:
            if stage.state != state:
                continue
            label = _agent_label(session, _agent_id_for_stage(stage.stage))
            if state == RunStageState.QUEUED:
                return f"Next expected: {label}."
            if state == RunStageState.NOT_SCHEDULED:
                return f"Next expected: {label} should start soon."
            return f"Next expected: {label} once the current stage completes."
    return None


def _first_stage_by_state(
    current_run: CurrentRunExecution,
    states: tuple[RunStageState, ...],
) -> RunStageExecution | None:
    for target_state in states:
        for stage in current_run.stages:
            if stage.state == target_state:
                return stage
    return None


def _agent_label(session: ChatSession, agent_id: AgentId) -> str:
    definition = session.agent_configuration.normalized().agents.get(agent_id)
    if definition is not None and definition.label.strip():
        return definition.label.strip()
    return {
        AgentId.USER: "User",
        AgentId.GENERATOR: "Generator",
        AgentId.REVIEWER: "Reviewer",
        AgentId.SUMMARY: "Summary",
        AgentId.SUPERVISOR: "Supervisor",
        AgentId.QA: "QA",
        AgentId.UX: "UX",
        AgentId.SENIOR_ENGINEER: "Senior Engineer",
        AgentId.SCRAPER: "Scraper",
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


def _compact_text(value: str | None, *, limit: int) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split()).strip()
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3].rstrip()}..."
