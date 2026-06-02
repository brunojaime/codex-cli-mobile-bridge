from __future__ import annotations

from dataclasses import replace

from backend.app.domain.entities.agent_configuration import (
    AgentConfiguration,
    AgentDisplayMode,
    AgentId,
    AgentPreset,
    AgentTriggerSource,
    AgentType,
    AgentVisibilityMode,
)
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
from backend.app.domain.entities.conversation_product import derive_conversation_product


def _build_session(
    *,
    preset: AgentPreset = AgentPreset.SOLO,
    display_mode: AgentDisplayMode = AgentDisplayMode.SHOW_ALL,
    reviewer_enabled: bool = False,
    summary_enabled: bool = False,
    supervisor_members: tuple[AgentId, ...] = (),
) -> ChatSession:
    configuration = AgentConfiguration.default()
    configuration.preset = preset
    configuration.display_mode = display_mode
    configuration.supervisor_member_ids = supervisor_members
    configuration.agents[AgentId.REVIEWER] = replace(
        configuration.agents[AgentId.REVIEWER],
        enabled=reviewer_enabled,
        max_turns=1 if reviewer_enabled else 0,
    )
    configuration.agents[AgentId.SUMMARY] = replace(
        configuration.agents[AgentId.SUMMARY],
        enabled=summary_enabled,
        max_turns=1 if summary_enabled else 0,
    )
    return ChatSession(
        id="session-1",
        title="Conversation product",
        workspace_path="/workspace",
        workspace_name="Workspace",
        agent_configuration=configuration.normalized(),
    )


def _message(
    *,
    message_id: str,
    role: ChatMessageRole,
    content: str,
    agent_id: AgentId,
    agent_type: AgentType,
    author_type: ChatMessageAuthorType,
    visibility: AgentVisibilityMode = AgentVisibilityMode.VISIBLE,
    status: ChatMessageStatus = ChatMessageStatus.COMPLETED,
) -> ChatMessage:
    return ChatMessage(
        id=message_id,
        session_id="session-1",
        role=role,
        author_type=author_type,
        content=content,
        status=status,
        agent_id=agent_id,
        agent_type=agent_type,
        visibility=visibility,
        trigger_source=AgentTriggerSource.USER,
    )


def _derive(session: ChatSession, *messages: ChatMessage):
    return derive_conversation_product(
        session,
        messages=list(messages),
        current_run=None,
        recent_runs=[],
    )


def test_supervisor_mode_hides_collapsed_specialist_messages_before_supervisor_reply() -> None:
    session = _build_session(
        preset=AgentPreset.SUPERVISOR,
        display_mode=AgentDisplayMode.COLLAPSE_SPECIALISTS,
        supervisor_members=(AgentId.QA,),
    )

    product = _derive(
        session,
        _message(
            message_id="user-1",
            role=ChatMessageRole.USER,
            content="Ship the dashboard safely.",
            agent_id=AgentId.USER,
            agent_type=AgentType.HUMAN,
            author_type=ChatMessageAuthorType.HUMAN,
        ),
        _message(
            message_id="qa-1",
            role=ChatMessageRole.ASSISTANT,
            content="QA found a flaky snapshot and wants more validation.",
            agent_id=AgentId.QA,
            agent_type=AgentType.QA,
            author_type=ChatMessageAuthorType.ASSISTANT,
            visibility=AgentVisibilityMode.COLLAPSED,
        ),
    )

    assert product.latest_update is None
    assert product.description == "Ship the dashboard safely."


def test_supervisor_mode_prefers_supervisor_update_over_hidden_specialist_output() -> None:
    session = _build_session(
        preset=AgentPreset.SUPERVISOR,
        display_mode=AgentDisplayMode.COLLAPSE_SPECIALISTS,
        supervisor_members=(AgentId.QA,),
    )

    product = _derive(
        session,
        _message(
            message_id="user-1",
            role=ChatMessageRole.USER,
            content="Ship the dashboard safely.",
            agent_id=AgentId.USER,
            agent_type=AgentType.HUMAN,
            author_type=ChatMessageAuthorType.HUMAN,
        ),
        _message(
            message_id="qa-1",
            role=ChatMessageRole.ASSISTANT,
            content="QA found a flaky snapshot and wants more validation.",
            agent_id=AgentId.QA,
            agent_type=AgentType.QA,
            author_type=ChatMessageAuthorType.ASSISTANT,
            visibility=AgentVisibilityMode.COLLAPSED,
        ),
        _message(
            message_id="supervisor-1",
            role=ChatMessageRole.ASSISTANT,
            content="We are fixing the flaky snapshot and validating the release.",
            agent_id=AgentId.SUPERVISOR,
            agent_type=AgentType.SUPERVISOR,
            author_type=ChatMessageAuthorType.ASSISTANT,
        ),
    )

    assert (
        product.latest_update
        == "We are fixing the flaky snapshot and validating the release."
    )
    assert product.description == product.latest_update


def test_review_mode_prefers_generator_output_over_reviewer_prompt() -> None:
    session = _build_session(
        preset=AgentPreset.REVIEW,
        display_mode=AgentDisplayMode.SHOW_ALL,
        reviewer_enabled=True,
    )

    product = _derive(
        session,
        _message(
            message_id="user-1",
            role=ChatMessageRole.USER,
            content="Patch the auth bug.",
            agent_id=AgentId.USER,
            agent_type=AgentType.HUMAN,
            author_type=ChatMessageAuthorType.HUMAN,
        ),
        _message(
            message_id="generator-1",
            role=ChatMessageRole.ASSISTANT,
            content="Generator implemented the auth patch.",
            agent_id=AgentId.GENERATOR,
            agent_type=AgentType.GENERATOR,
            author_type=ChatMessageAuthorType.ASSISTANT,
        ),
        _message(
            message_id="reviewer-1",
            role=ChatMessageRole.ASSISTANT,
            content="Ask the generator to add regression tests before merge.",
            agent_id=AgentId.REVIEWER,
            agent_type=AgentType.REVIEWER,
            author_type=ChatMessageAuthorType.ASSISTANT,
            visibility=AgentVisibilityMode.COLLAPSED,
        ),
    )

    assert product.latest_update == "Generator implemented the auth patch."
    assert product.description == "Generator implemented the auth patch."


def test_summary_only_mode_falls_back_to_latest_user_message_until_summary_exists() -> None:
    session = _build_session(
        preset=AgentPreset.TRIAD,
        display_mode=AgentDisplayMode.SUMMARY_ONLY,
        reviewer_enabled=True,
        summary_enabled=True,
    )

    product = _derive(
        session,
        _message(
            message_id="user-1",
            role=ChatMessageRole.USER,
            content="Refactor the auth flow.",
            agent_id=AgentId.USER,
            agent_type=AgentType.HUMAN,
            author_type=ChatMessageAuthorType.HUMAN,
        ),
        _message(
            message_id="generator-1",
            role=ChatMessageRole.ASSISTANT,
            content="Generator refactored the auth flow.",
            agent_id=AgentId.GENERATOR,
            agent_type=AgentType.GENERATOR,
            author_type=ChatMessageAuthorType.ASSISTANT,
        ),
        _message(
            message_id="reviewer-1",
            role=ChatMessageRole.ASSISTANT,
            content="Ask the generator to add coverage before shipping.",
            agent_id=AgentId.REVIEWER,
            agent_type=AgentType.REVIEWER,
            author_type=ChatMessageAuthorType.ASSISTANT,
            visibility=AgentVisibilityMode.COLLAPSED,
        ),
    )

    assert product.latest_update is None
    assert product.description == "Refactor the auth flow."


def test_plain_chat_uses_generator_output_as_user_facing_update() -> None:
    session = _build_session()

    product = _derive(
        session,
        _message(
            message_id="generator-1",
            role=ChatMessageRole.ASSISTANT,
            content="Generator drafted the first implementation.",
            agent_id=AgentId.GENERATOR,
            agent_type=AgentType.GENERATOR,
            author_type=ChatMessageAuthorType.ASSISTANT,
        ),
    )

    assert product.latest_update == "Generator drafted the first implementation."


def test_product_sanitizes_image_attachment_failures() -> None:
    session = _build_session()

    current_run = CurrentRunExecution(
        run_id="run-1",
        state=RunStageState.FAILED,
        is_active=True,
        preset=AgentPreset.SOLO,
        turn_budget_mode=None,
        started_at=None,
        updated_at=None,
        completed_at=None,
        participant_agent_ids=(AgentId.GENERATOR,),
        call_count=1,
        stages=[
            RunStageExecution(
                stage=RunStageId.GENERATOR,
                state=RunStageState.FAILED,
                configured=True,
                latest_activity=(
                    "Codex could not read the local image at "
                    "/tmp/codex-remote-retry-assets/example.jpg"
                ),
            ),
        ],
    )
    product = derive_conversation_product(
        session,
        messages=[],
        current_run=current_run,
        recent_runs=[],
    )

    assert product.latest_update is None
    assert product.current_focus == (
        "Generator failed: The original image attachment is no longer available on this server. Reattach it to continue."
    )
    assert product.description == product.current_focus


def test_empty_session_uses_no_messages_fallback() -> None:
    session = _build_session()

    product = _derive(session)

    assert product.latest_update is None
    assert product.description == "No messages yet."
    assert product.next_step == "Waiting for your next message."
