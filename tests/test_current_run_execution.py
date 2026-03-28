from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from backend.app.api.schemas import SessionDetailResponse
from backend.app.domain.entities.agent_configuration import (
    AgentConfiguration,
    AgentId,
    AgentPreset,
    AgentTriggerSource,
    AgentType,
    TurnBudgetMode,
)
from backend.app.domain.entities.chat_message import (
    ChatMessage,
    ChatMessageAuthorType,
    ChatMessageRole,
    ChatMessageStatus,
)
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.current_run import (
    RunStageState,
    derive_recent_run_executions,
)
from backend.app.domain.entities.job import Job, JobStatus


def build_session(
    *,
    active_run_id: str | None = "run-current",
    reviewer_enabled: bool = True,
    reviewer_max_turns: int = 1,
    summary_enabled: bool = False,
    summary_max_turns: int = 1,
) -> ChatSession:
    configuration = AgentConfiguration.default()
    configuration.agents[AgentId.REVIEWER] = replace(
        configuration.agents[AgentId.REVIEWER],
        enabled=reviewer_enabled,
        max_turns=reviewer_max_turns if reviewer_enabled else 0,
    )
    configuration.agents[AgentId.SUMMARY] = replace(
        configuration.agents[AgentId.SUMMARY],
        enabled=summary_enabled,
        max_turns=summary_max_turns if summary_enabled else 0,
    )
    return ChatSession(
        id="session-1",
        title="Run execution",
        workspace_path="/workspace",
        workspace_name="Workspace",
        agent_configuration=configuration.normalized(),
        active_agent_run_id=active_run_id,
        auto_mode_enabled=reviewer_enabled,
        auto_max_turns=reviewer_max_turns if reviewer_enabled else 0,
    )


def build_message(
    *,
    message_id: str,
    run_id: str,
    agent_id: AgentId,
    role: ChatMessageRole,
    status: ChatMessageStatus,
    job_id: str | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> ChatMessage:
    return ChatMessage(
        id=message_id,
        session_id="session-1",
        role=role,
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
            AgentId.SUPERVISOR: AgentType.SUPERVISOR,
            AgentId.QA: AgentType.QA,
            AgentId.UX: AgentType.UX,
            AgentId.SENIOR_ENGINEER: AgentType.SENIOR_ENGINEER,
            AgentId.USER: AgentType.HUMAN,
        }[agent_id],
        trigger_source=(
            AgentTriggerSource.GENERATOR
            if agent_id == AgentId.REVIEWER
            else AgentTriggerSource.USER
        ),
        run_id=run_id,
        job_id=job_id,
        created_at=created_at or _ts(),
        updated_at=updated_at or created_at or _ts(),
    )


def build_job(
    *,
    job_id: str,
    run_id: str,
    agent_id: AgentId,
    status: JobStatus,
    latest_activity: str | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> Job:
    return Job(
        id=job_id,
        session_id="session-1",
        message="job",
        run_id=run_id,
        status=status,
        latest_activity=latest_activity,
        agent_id=agent_id,
        agent_type={
            AgentId.GENERATOR: AgentType.GENERATOR,
            AgentId.REVIEWER: AgentType.REVIEWER,
            AgentId.SUMMARY: AgentType.SUMMARY,
            AgentId.SUPERVISOR: AgentType.SUPERVISOR,
            AgentId.QA: AgentType.QA,
            AgentId.UX: AgentType.UX,
            AgentId.SENIOR_ENGINEER: AgentType.SENIOR_ENGINEER,
            AgentId.USER: AgentType.HUMAN,
        }[agent_id],
        created_at=created_at or _ts(),
        updated_at=updated_at or created_at or _ts(),
        completed_at=completed_at,
    )


def test_session_detail_response_exposes_current_run_stages() -> None:
    session = build_session(summary_enabled=False)
    generator_message = build_message(
        message_id="generator-1",
        run_id="run-current",
        agent_id=AgentId.GENERATOR,
        role=ChatMessageRole.ASSISTANT,
        status=ChatMessageStatus.PENDING,
        job_id="job-generator",
    )
    response = SessionDetailResponse.from_domain(
        session,
        messages=[generator_message],
        jobs_by_id={
            "job-generator": build_job(
                job_id="job-generator",
                run_id="run-current",
                agent_id=AgentId.GENERATOR,
                status=JobStatus.RUNNING,
                latest_activity="Streaming output",
            )
        },
    )

    assert response.current_run is not None
    assert response.current_run.run_id == "run-current"
    assert response.current_run.state == RunStageState.RUNNING
    assert response.current_run.is_active is True
    assert [stage.stage for stage in response.current_run.stages] == [
        "generator",
        "reviewer",
        "summary",
    ]
    assert response.current_run.stages[0].state == RunStageState.RUNNING
    assert response.current_run.stages[0].job_id == "job-generator"
    assert response.current_run.stages[1].state == RunStageState.WAITING
    assert response.current_run.stages[2].state == RunStageState.DISABLED
    assert response.recent_runs[0].run_id == "run-current"
    assert response.conversation_product.status_line == "Generator running"
    assert (
        response.conversation_product.current_focus
        == "Generator is active: Streaming output"
    )
    assert (
        response.conversation_product.next_step
        == "Next expected: Reviewer once the current stage completes."
    )


def test_current_run_marks_missing_reviewer_after_completed_generator_as_not_scheduled() -> None:
    session = build_session(summary_enabled=False)
    messages = [
        build_message(
            message_id="generator-1",
            run_id="run-current",
            agent_id=AgentId.GENERATOR,
            role=ChatMessageRole.ASSISTANT,
            status=ChatMessageStatus.COMPLETED,
            job_id="job-generator-1",
        ),
        build_message(
            message_id="generator-2",
            run_id="run-current",
            agent_id=AgentId.GENERATOR,
            role=ChatMessageRole.ASSISTANT,
            status=ChatMessageStatus.COMPLETED,
            job_id="job-generator-2",
        ),
    ]
    response = SessionDetailResponse.from_domain(
        session,
        messages=messages,
        jobs_by_id={
            "job-generator-1": build_job(
                job_id="job-generator-1",
                run_id="run-current",
                agent_id=AgentId.GENERATOR,
                status=JobStatus.COMPLETED,
            ),
            "job-generator-2": build_job(
                job_id="job-generator-2",
                run_id="run-current",
                agent_id=AgentId.GENERATOR,
                status=JobStatus.COMPLETED,
            ),
        },
    )

    assert response.current_run is not None
    generator_stage = response.current_run.stages[0]
    reviewer_stage = response.current_run.stages[1]
    assert generator_stage.attempt_count == 2
    assert reviewer_stage.state == RunStageState.NOT_SCHEDULED
    assert generator_stage.max_turns == session.agent_configuration.agents[AgentId.GENERATOR].max_turns


def test_current_run_uses_stale_state_for_uncertain_follow_up_messages() -> None:
    session = build_session(summary_enabled=True)
    messages = [
        build_message(
            message_id="generator-1",
            run_id="run-current",
            agent_id=AgentId.GENERATOR,
            role=ChatMessageRole.ASSISTANT,
            status=ChatMessageStatus.COMPLETED,
        ),
        build_message(
            message_id="reviewer-1",
            run_id="run-current",
            agent_id=AgentId.REVIEWER,
            role=ChatMessageRole.USER,
            status=ChatMessageStatus.SUBMISSION_UNKNOWN,
        ),
    ]

    response = SessionDetailResponse.from_domain(
        session,
        messages=messages,
        jobs_by_id={},
    )

    assert response.current_run is not None
    assert response.current_run.stages[1].state == RunStageState.STALE
    assert response.current_run.stages[2].state == RunStageState.SKIPPED


def test_current_run_is_omitted_when_there_is_no_active_run() -> None:
    session = build_session(active_run_id=None)
    old_run_messages = [
        build_message(
            message_id="reviewer-old",
            run_id="run-old",
            agent_id=AgentId.REVIEWER,
            role=ChatMessageRole.USER,
            status=ChatMessageStatus.COMPLETED,
        )
    ]

    response = SessionDetailResponse.from_domain(session, messages=old_run_messages)

    assert response.current_run is None
    assert response.recent_runs[0].run_id == "run-old"
    assert response.recent_runs[0].is_active is False


def test_recent_runs_keep_completed_review_runs_visible_after_active_run_clears() -> None:
    session = build_session(active_run_id=None, reviewer_enabled=True)
    base = _ts()
    messages = [
        build_message(
            message_id="generator-old",
            run_id="run-old",
            agent_id=AgentId.GENERATOR,
            role=ChatMessageRole.ASSISTANT,
            status=ChatMessageStatus.COMPLETED,
            job_id="job-generator-old",
            created_at=base,
            updated_at=base + timedelta(minutes=1),
        ),
        build_message(
            message_id="reviewer-old",
            run_id="run-old",
            agent_id=AgentId.REVIEWER,
            role=ChatMessageRole.USER,
            status=ChatMessageStatus.COMPLETED,
            job_id="job-reviewer-old",
            created_at=base + timedelta(minutes=2),
            updated_at=base + timedelta(minutes=3),
        ),
    ]
    jobs = {
        "job-generator-old": build_job(
            job_id="job-generator-old",
            run_id="run-old",
            agent_id=AgentId.GENERATOR,
            status=JobStatus.COMPLETED,
            created_at=base,
            updated_at=base + timedelta(minutes=1),
            completed_at=base + timedelta(minutes=1),
        ),
        "job-reviewer-old": build_job(
            job_id="job-reviewer-old",
            run_id="run-old",
            agent_id=AgentId.REVIEWER,
            status=JobStatus.COMPLETED,
            created_at=base + timedelta(minutes=2),
            updated_at=base + timedelta(minutes=3),
            completed_at=base + timedelta(minutes=3),
        ),
    }

    response = SessionDetailResponse.from_domain(
        session,
        messages=messages,
        jobs_by_id=jobs,
    )

    assert response.current_run is None
    assert len(response.recent_runs) == 1
    assert response.recent_runs[0].run_id == "run-old"
    assert response.recent_runs[0].state == RunStageState.COMPLETED
    assert response.recent_runs[0].completed_at == base + timedelta(minutes=3)
    assert response.recent_runs[0].stages[0].attempt_count == 1
    assert response.recent_runs[0].stages[1].attempt_count == 1


def test_recent_runs_preserve_solo_runs_with_disabled_follow_up_stages() -> None:
    session = build_session(
        active_run_id=None,
        reviewer_enabled=False,
        summary_enabled=False,
    )
    messages = [
        build_message(
            message_id="generator-solo",
            run_id="run-solo",
            agent_id=AgentId.GENERATOR,
            role=ChatMessageRole.ASSISTANT,
            status=ChatMessageStatus.COMPLETED,
        ),
    ]

    runs = derive_recent_run_executions(session, messages=messages, jobs_by_id={})

    assert len(runs) == 1
    assert runs[0].run_id == "run-solo"
    assert runs[0].state == RunStageState.COMPLETED
    assert runs[0].stages[1].state == RunStageState.DISABLED
    assert runs[0].stages[2].state == RunStageState.DISABLED


def test_recent_runs_preserve_multi_turn_reviewer_loop_counters() -> None:
    session = build_session(
        active_run_id=None,
        reviewer_enabled=True,
        reviewer_max_turns=6,
    )
    base = _ts()
    messages = [
        build_message(
            message_id="generator-1",
            run_id="run-review",
            agent_id=AgentId.GENERATOR,
            role=ChatMessageRole.ASSISTANT,
            status=ChatMessageStatus.COMPLETED,
            job_id="job-generator-1",
            created_at=base,
            updated_at=base + timedelta(minutes=1),
        ),
        build_message(
            message_id="reviewer-1",
            run_id="run-review",
            agent_id=AgentId.REVIEWER,
            role=ChatMessageRole.USER,
            status=ChatMessageStatus.COMPLETED,
            job_id="job-reviewer-1",
            created_at=base + timedelta(minutes=2),
            updated_at=base + timedelta(minutes=3),
        ),
        build_message(
            message_id="generator-2",
            run_id="run-review",
            agent_id=AgentId.GENERATOR,
            role=ChatMessageRole.ASSISTANT,
            status=ChatMessageStatus.COMPLETED,
            job_id="job-generator-2",
            created_at=base + timedelta(minutes=4),
            updated_at=base + timedelta(minutes=5),
        ),
        build_message(
            message_id="reviewer-2",
            run_id="run-review",
            agent_id=AgentId.REVIEWER,
            role=ChatMessageRole.USER,
            status=ChatMessageStatus.COMPLETED,
            job_id="job-reviewer-2",
            created_at=base + timedelta(minutes=6),
            updated_at=base + timedelta(minutes=7),
        ),
    ]

    runs = derive_recent_run_executions(
        session,
        messages=messages,
        jobs_by_id={},
        run_configurations_by_id={"run-review": session.agent_configuration},
    )

    assert len(runs) == 1
    generator_stage = runs[0].stages[0]
    reviewer_stage = runs[0].stages[1]
    assert runs[0].state == RunStageState.COMPLETED
    assert generator_stage.attempt_count == 2
    assert generator_stage.max_turns == session.agent_configuration.agents[AgentId.GENERATOR].max_turns
    assert reviewer_stage.attempt_count == 2
    assert reviewer_stage.max_turns == 6


def test_recent_runs_derive_failed_cancelled_and_skipped_stage_states() -> None:
    session = build_session(
        active_run_id=None,
        reviewer_enabled=True,
        summary_enabled=True,
    )
    base = _ts()
    messages = [
        build_message(
            message_id="generator-complete",
            run_id="run-skipped",
            agent_id=AgentId.GENERATOR,
            role=ChatMessageRole.ASSISTANT,
            status=ChatMessageStatus.COMPLETED,
            created_at=base,
            updated_at=base + timedelta(minutes=1),
        ),
        build_message(
            message_id="generator-failed",
            run_id="run-failed",
            agent_id=AgentId.GENERATOR,
            role=ChatMessageRole.ASSISTANT,
            status=ChatMessageStatus.COMPLETED,
            created_at=base + timedelta(minutes=2),
            updated_at=base + timedelta(minutes=3),
        ),
        build_message(
            message_id="reviewer-failed",
            run_id="run-failed",
            agent_id=AgentId.REVIEWER,
            role=ChatMessageRole.USER,
            status=ChatMessageStatus.FAILED,
            created_at=base + timedelta(minutes=4),
            updated_at=base + timedelta(minutes=5),
        ),
        build_message(
            message_id="generator-cancelled",
            run_id="run-cancelled",
            agent_id=AgentId.GENERATOR,
            role=ChatMessageRole.ASSISTANT,
            status=ChatMessageStatus.CANCELLED,
            created_at=base + timedelta(minutes=6),
            updated_at=base + timedelta(minutes=7),
        ),
    ]

    runs = derive_recent_run_executions(
        session,
        messages=messages,
        jobs_by_id={},
        run_configurations_by_id={
            "run-skipped": session.agent_configuration,
            "run-failed": session.agent_configuration,
            "run-cancelled": session.agent_configuration,
        },
    )
    runs_by_id = {run.run_id: run for run in runs}

    assert runs_by_id["run-skipped"].state == RunStageState.COMPLETED
    assert runs_by_id["run-skipped"].stages[1].state == RunStageState.SKIPPED
    assert runs_by_id["run-skipped"].stages[2].state == RunStageState.SKIPPED

    assert runs_by_id["run-failed"].state == RunStageState.FAILED
    assert runs_by_id["run-failed"].stages[1].state == RunStageState.FAILED
    assert runs_by_id["run-failed"].stages[2].state == RunStageState.SKIPPED

    assert runs_by_id["run-cancelled"].state == RunStageState.CANCELLED
    assert runs_by_id["run-cancelled"].stages[0].state == RunStageState.CANCELLED
    assert runs_by_id["run-cancelled"].stages[1].state == RunStageState.SKIPPED


def test_supervisor_runs_report_participants_and_supervisor_only_budget_mode() -> None:
    configuration = AgentConfiguration.default()
    configuration.preset = AgentPreset.SUPERVISOR
    configuration.turn_budget_mode = TurnBudgetMode.SUPERVISOR_ONLY
    configuration.supervisor_member_ids = (AgentId.QA, AgentId.SENIOR_ENGINEER)
    configuration.agents[AgentId.SUPERVISOR] = replace(
        configuration.agents[AgentId.SUPERVISOR],
        enabled=True,
        max_turns=3,
    )
    configuration.agents[AgentId.QA] = replace(
        configuration.agents[AgentId.QA],
        enabled=True,
        max_turns=0,
    )
    configuration.agents[AgentId.SENIOR_ENGINEER] = replace(
        configuration.agents[AgentId.SENIOR_ENGINEER],
        enabled=True,
        max_turns=0,
    )
    configuration.agents[AgentId.UX] = replace(
        configuration.agents[AgentId.UX],
        enabled=False,
        max_turns=0,
    )
    session = ChatSession(
        id="session-supervisor",
        title="Supervisor history",
        workspace_path="/workspace",
        workspace_name="Workspace",
        agent_configuration=configuration.normalized(),
        active_agent_run_id=None,
    )

    messages = [
        build_message(
            message_id="supervisor-1",
            run_id="run-supervisor",
            agent_id=AgentId.SUPERVISOR,
            role=ChatMessageRole.ASSISTANT,
            status=ChatMessageStatus.COMPLETED,
        ),
        build_message(
            message_id="qa-1",
            run_id="run-supervisor",
            agent_id=AgentId.QA,
            role=ChatMessageRole.ASSISTANT,
            status=ChatMessageStatus.COMPLETED,
        ),
        build_message(
            message_id="supervisor-2",
            run_id="run-supervisor",
            agent_id=AgentId.SUPERVISOR,
            role=ChatMessageRole.ASSISTANT,
            status=ChatMessageStatus.COMPLETED,
        ),
        build_message(
            message_id="qa-2",
            run_id="run-supervisor",
            agent_id=AgentId.QA,
            role=ChatMessageRole.ASSISTANT,
            status=ChatMessageStatus.COMPLETED,
        ),
        build_message(
            message_id="supervisor-3",
            run_id="run-supervisor",
            agent_id=AgentId.SUPERVISOR,
            role=ChatMessageRole.ASSISTANT,
            status=ChatMessageStatus.COMPLETED,
        ),
    ]

    response = SessionDetailResponse.from_domain(
        session,
        messages=messages,
        jobs_by_id={},
        run_configurations_by_id={"run-supervisor": session.agent_configuration},
    )

    assert len(response.recent_runs) == 1
    run = response.recent_runs[0]
    assert run.preset == AgentPreset.SUPERVISOR
    assert run.turn_budget_mode == TurnBudgetMode.SUPERVISOR_ONLY
    assert run.participant_agent_ids == [
        AgentId.SUPERVISOR,
        AgentId.QA,
    ]
    assert run.call_count == 5

    qa_stage = next(stage for stage in run.stages if stage.stage == "qa")
    assert qa_stage.attempt_count == 2
    assert qa_stage.max_turns == 0
    assert qa_stage.has_turn_budget is False


def _ts() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)
