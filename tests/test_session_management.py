from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from backend.app.application.services.message_service import MessageService
from backend.app.api.schemas import TurnSummaryResponse
from backend.app.domain.entities.agent_configuration import AgentId, AgentType
from backend.app.domain.entities.chat_message import (
    ChatMessage,
    ChatMessageRole,
    ChatMessageAuthorType,
    ChatMessageStatus,
)
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.chat_turn_summary import (
    ChatTurnSummary,
    ChatTurnSummarySourceMessage,
)
from backend.app.domain.entities.job import utc_now
from backend.app.domain.entities.job import JobStatus
from backend.app.infrastructure.execution.base import ExecutionProvider, ExecutionSnapshot
from backend.app.infrastructure.persistence.in_memory_chat_repository import InMemoryChatRepository
from backend.app.infrastructure.persistence.sqlite_chat_repository import SqliteChatRepository
from backend.app.infrastructure.transcription.disabled_transcriber import DisabledAudioTranscriber


class _InstantExecutionProvider(ExecutionProvider):
    def __init__(self) -> None:
        self._snapshots: dict[str, ExecutionSnapshot] = {}
        self.calls: list[tuple[str, str | None]] = []

    def execute(
        self,
        message: str,
        *,
        image_paths: list[str] | None = None,
        cleanup_paths: list[str] | None = None,
        provider_session_id: str | None = None,
        model: str | None = None,
        serial_key: str | None = None,
        submission_token: str | None = None,
        workdir: str | None = None,
    ) -> str:
        job_id = str(uuid4())
        self.calls.append((message, model))
        response = (
            "Release checklist"
            if message.startswith("Create a concise chat title")
            else f"Completed: {message}"
        )
        self._snapshots[job_id] = ExecutionSnapshot(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            response=response,
            provider_session_id=provider_session_id or f"thread-{job_id}",
            phase="Completed",
            latest_activity="Finished immediately for tests.",
        )
        return job_id

    def get_status(self, job_id: str) -> JobStatus:
        return self._snapshots[job_id].status

    def get_result(self, job_id: str) -> str | None:
        return self._snapshots[job_id].response

    def get_error(self, job_id: str) -> str | None:
        return self._snapshots[job_id].error

    def has_job(self, job_id: str) -> bool:
        return job_id in self._snapshots

    def get_snapshot(self, job_id: str) -> ExecutionSnapshot:
        return self._snapshots[job_id]

    def get_provider_session_id(self, job_id: str) -> str | None:
        return self._snapshots[job_id].provider_session_id

    def get_phase(self, job_id: str) -> str | None:
        return self._snapshots[job_id].phase

    def get_latest_activity(self, job_id: str) -> str | None:
        return self._snapshots[job_id].latest_activity


class _FailingVisibleExecutionProvider(ExecutionProvider):
    def __init__(self) -> None:
        self._snapshots: dict[str, ExecutionSnapshot] = {}
        self._job_counter = 0

    def execute(
        self,
        message: str,
        *,
        image_paths: list[str] | None = None,
        cleanup_paths: list[str] | None = None,
        provider_session_id: str | None = None,
        model: str | None = None,
        serial_key: str | None = None,
        submission_token: str | None = None,
        workdir: str | None = None,
    ) -> str:
        self._job_counter += 1
        job_id = f"job-{self._job_counter}"
        is_hidden_summary = message.startswith(
            "Summarize these recent chat updates for future context."
        )
        if is_hidden_summary:
            self._snapshots[job_id] = ExecutionSnapshot(
                job_id=job_id,
                status=JobStatus.COMPLETED,
                response="Hidden summary completed.",
                provider_session_id=provider_session_id or f"thread-{job_id}",
                phase="Completed",
                latest_activity="Hidden summary completed.",
            )
        else:
            self._snapshots[job_id] = ExecutionSnapshot(
                job_id=job_id,
                status=JobStatus.FAILED,
                error="Visible job failed.",
                provider_session_id=provider_session_id or f"thread-{job_id}",
                phase="Failed",
                latest_activity="Visible job failed.",
            )
        return job_id

    def get_status(self, job_id: str) -> JobStatus:
        return self._snapshots[job_id].status

    def get_result(self, job_id: str) -> str | None:
        return self._snapshots[job_id].response

    def get_error(self, job_id: str) -> str | None:
        return self._snapshots[job_id].error

    def has_job(self, job_id: str) -> bool:
        return job_id in self._snapshots

    def get_snapshot(self, job_id: str) -> ExecutionSnapshot:
        return self._snapshots[job_id]

    def get_provider_session_id(self, job_id: str) -> str | None:
        return self._snapshots[job_id].provider_session_id

    def get_phase(self, job_id: str) -> str | None:
        return self._snapshots[job_id].phase

    def get_latest_activity(self, job_id: str) -> str | None:
        return self._snapshots[job_id].latest_activity

def _build_service(
    projects_root: str,
    *,
    execution_provider: ExecutionProvider | None = None,
    title_generation_model: str | None = None,
) -> MessageService:
    repository = InMemoryChatRepository(projects_root=projects_root)
    return MessageService(
        repository=repository,
        execution_provider=execution_provider or _InstantExecutionProvider(),
        default_workspace_path=projects_root,
        audio_transcriber=DisabledAudioTranscriber(),
        title_generation_model=title_generation_model,
    )


def _build_sqlite_service(
    projects_root: str,
    *,
    database_path: str,
    execution_provider: ExecutionProvider | None = None,
    title_generation_model: str | None = None,
) -> MessageService:
    repository = SqliteChatRepository(
        database_path=database_path,
        projects_root=projects_root,
    )
    return MessageService(
        repository=repository,
        execution_provider=execution_provider or _InstantExecutionProvider(),
        default_workspace_path=projects_root,
        audio_transcriber=DisabledAudioTranscriber(),
        title_generation_model=title_generation_model,
    )


def test_session_archive_can_be_toggled() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        service = _build_service(temp_dir)

        session = service.create_session(workspace_path=str(workspace))

        archived = service.set_session_archived(
            session_id=session.id,
            archived=True,
        )
        assert archived.archived_at is not None

        restored = service.set_session_archived(
            session_id=session.id,
            archived=False,
        )
        assert restored.archived_at is None


def test_sqlite_session_round_trip_preserves_optional_archived_at() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        repository = SqliteChatRepository(
            database_path=str(Path(temp_dir) / "chat.sqlite3"),
            projects_root=temp_dir,
        )
        archived_at = utc_now()
        session = ChatSession(
            id="sqlite-archived-session",
            title="Archived session",
            workspace_path=str(workspace),
            workspace_name=workspace.name,
            archived_at=archived_at,
            created_at=archived_at - timedelta(minutes=5),
            updated_at=archived_at,
        )

        repository.save_session(session)
        restored = repository.get_session(session.id)

        assert restored is not None
        assert restored.archived_at == archived_at


def test_sqlite_session_round_trip_preserves_turn_summary_checkpoint() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        repository = SqliteChatRepository(
            database_path=str(Path(temp_dir) / "chat.sqlite3"),
            projects_root=temp_dir,
        )
        timestamp = utc_now()
        session = ChatSession(
            id="sqlite-turn-summary-session",
            title="Turn summary session",
            workspace_path=str(workspace),
            workspace_name=workspace.name,
            turn_summaries_enabled=True,
            turn_summary_checkpoint_message_id="message-42",
            turn_summary_checkpoint_initialized=True,
            created_at=timestamp - timedelta(minutes=5),
            updated_at=timestamp,
        )

        repository.save_session(session)
        restored = repository.get_session(session.id)

        assert restored is not None
        assert restored.turn_summaries_enabled is True
        assert restored.turn_summary_checkpoint_message_id == "message-42"
        assert restored.turn_summary_checkpoint_initialized is True


def test_sqlite_turn_summary_round_trip_preserves_source_message_snapshot() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        repository = SqliteChatRepository(
            database_path=str(Path(temp_dir) / "chat.sqlite3"),
            projects_root=temp_dir,
        )
        session = ChatSession(
            id="sqlite-turn-summary-source-session",
            title="Turn summary source session",
            workspace_path=str(workspace),
            workspace_name=workspace.name,
        )
        repository.save_session(session)

        timestamp = utc_now()
        summary = ChatTurnSummary(
            id="summary-1",
            session_id=session.id,
            content="Stored summary",
            source_message_ids=("message-1",),
            source_messages=(
                ChatTurnSummarySourceMessage(
                    message_id="message-1",
                    role=ChatMessageRole.USER,
                    author_type=ChatMessageAuthorType.HUMAN,
                    agent_id=AgentId.USER,
                    agent_type=AgentType.HUMAN,
                    agent_label="User",
                    content="Persist this immutable source content.",
                    status=ChatMessageStatus.COMPLETED,
                    created_at=timestamp,
                ),
            ),
            created_at=timestamp,
            updated_at=timestamp,
        )

        repository.save_turn_summary(summary)
        restored = repository.list_turn_summaries(session.id)

        assert len(restored) == 1
        assert restored[0].source_messages == summary.source_messages


def test_turn_summary_response_falls_back_to_live_message_content_for_legacy_summaries() -> None:
    timestamp = utc_now()
    summary = ChatTurnSummary(
        id="legacy-summary",
        session_id="session-1",
        content="Legacy summary",
        source_message_ids=("message-1",),
        source_messages=(),
        created_at=timestamp,
        updated_at=timestamp,
    )
    live_message = ChatTurnSummarySourceMessage(
        message_id="message-1",
        role=ChatMessageRole.USER,
        author_type=ChatMessageAuthorType.HUMAN,
        agent_id=AgentId.USER,
        agent_type=AgentType.HUMAN,
        agent_label="User",
        content="Fallback live content.",
        status=ChatMessageStatus.COMPLETED,
        created_at=timestamp,
    )

    class _LegacyMessage:
        def __init__(self) -> None:
            self.id = live_message.message_id
            self.role = live_message.role
            self.author_type = live_message.author_type
            self.agent_id = live_message.agent_id
            self.agent_type = live_message.agent_type
            self.agent_label = live_message.agent_label
            self.content = live_message.content
            self.status = live_message.status
            self.created_at = live_message.created_at

    response = TurnSummaryResponse.from_domain(
        summary,
        messages_by_id={"message-1": _LegacyMessage()},
    )

    assert response.source_messages[0].content == "Fallback live content."


def test_turn_summary_response_sanitizes_stale_image_attachment_errors() -> None:
    timestamp = utc_now()
    raw_error = (
        "Codex could not read the local image at "
        "/tmp/codex-remote-retry-assets/example.jpg: "
        "failed to read image at /tmp/codex-remote-retry-assets/example.jpg: "
        "No such file or directory (os error 2)"
    )
    summary = ChatTurnSummary(
        id="summary-with-image-error",
        session_id="session-1",
        content=raw_error,
        source_message_ids=("message-1",),
        source_messages=(
            ChatTurnSummarySourceMessage(
                message_id="message-1",
                role=ChatMessageRole.ASSISTANT,
                author_type=ChatMessageAuthorType.ASSISTANT,
                agent_id=AgentId.GENERATOR,
                agent_type=AgentType.GENERATOR,
                agent_label="Generator",
                content=raw_error,
                status=ChatMessageStatus.FAILED,
                created_at=timestamp,
            ),
        ),
        created_at=timestamp,
        updated_at=timestamp,
    )

    response = TurnSummaryResponse.from_domain(summary, messages_by_id={})

    expected = (
        "The original image attachment is no longer available on this server. "
        "Reattach it to continue."
    )
    assert response.content == expected
    assert response.source_messages[0].content == expected


def test_turn_summary_prompt_sanitizes_stale_image_attachment_errors() -> None:
    with TemporaryDirectory() as temp_dir:
        service = _build_service(temp_dir)
        prompt = service._build_turn_summary_prompt(
            [
                ChatMessage(
                    id="message-1",
                    session_id="session-1",
                    role=ChatMessageRole.ASSISTANT,
                    author_type=ChatMessageAuthorType.ASSISTANT,
                    content=(
                        "Codex could not read the local image at "
                        "/tmp/codex-remote-retry-assets/example.jpg"
                    ),
                    status=ChatMessageStatus.FAILED,
                    agent_id=AgentId.GENERATOR,
                    agent_type=AgentType.GENERATOR,
                ),
            ]
        )

        assert "codex-remote-retry-assets" not in prompt
        assert (
            "The original image attachment is no longer available on this server. "
            "Reattach it to continue."
        ) in prompt


def test_placeholder_session_title_is_generated_after_four_user_turns() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        service = _build_service(temp_dir)

        session = service.create_session(workspace_path=str(workspace))
        assert session.title_is_placeholder is True

        for index in range(4):
            service.submit_message(
                f"Turn {index + 1}: investigate the release checklist flow",
                session_id=session.id,
            )

        updated = service.get_session(session.id)
        assert updated is not None
        assert updated.title == "Release checklist"
        assert updated.title_is_placeholder is False


def test_manual_session_title_is_not_replaced_by_auto_generation() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        service = _build_service(temp_dir)

        session = service.create_session(
            title="Manual title",
            workspace_path=str(workspace),
        )

        for index in range(4):
            service.submit_message(
                f"Turn {index + 1}: discuss the manual title behavior",
                session_id=session.id,
            )

        updated = service.get_session(session.id)
        assert updated is not None
        assert updated.title == "Manual title"
        assert updated.title_is_placeholder is False


def test_placeholder_title_generation_uses_configured_title_model() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        provider = _InstantExecutionProvider()
        service = _build_service(
            temp_dir,
            execution_provider=provider,
            title_generation_model="gpt-5.4-mini",
        )

        session = service.create_session(workspace_path=str(workspace))
        for index in range(4):
            service.submit_message(
                f"Turn {index + 1}: investigate the release checklist flow",
                session_id=session.id,
            )

        title_calls = [
            model
            for message, model in provider.calls
            if message.startswith("Create a concise chat title")
        ]
        assert title_calls == ["gpt-5.4-mini"]


def test_submit_message_uses_agent_model_override() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        provider = _InstantExecutionProvider()
        service = _build_service(
            temp_dir,
            execution_provider=provider,
        )

        session = service.create_session(workspace_path=str(workspace))
        configuration = session.agent_configuration.normalized()
        configuration.agents[AgentId.GENERATOR] = replace(
            configuration.agents[AgentId.GENERATOR],
            model="gpt-5.4",
        )
        service.update_agent_configuration(
            session_id=session.id,
            configuration=configuration,
        )

        service.submit_message(
            "Implement the dynamic title pipeline",
            session_id=session.id,
        )

        assert provider.calls[0] == (
            "Implement the dynamic title pipeline",
            "gpt-5.4",
        )


def test_turn_summary_toggle_can_be_updated() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        service = _build_service(temp_dir)

        session = service.create_session(
            workspace_path=str(workspace),
            turn_summaries_enabled=False,
        )
        assert session.turn_summaries_enabled is False

        updated = service.update_turn_summaries(
            session_id=session.id,
            enabled=True,
        )

        assert updated.turn_summaries_enabled is True
        assert updated.turn_summary_checkpoint_message_id is None
        assert updated.turn_summary_checkpoint_initialized is True


def test_new_session_created_enabled_still_summarizes_first_four_terminal_messages() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        database_path = str(Path(temp_dir) / "chat.sqlite3")
        provider = _InstantExecutionProvider()
        service = _build_sqlite_service(
            temp_dir,
            database_path=database_path,
            execution_provider=provider,
        )

        session = service.create_session(
            workspace_path=str(workspace),
            turn_summaries_enabled=True,
        )
        assert session.turn_summary_checkpoint_initialized is True
        assert session.turn_summary_checkpoint_message_id is None

        first_job = service.submit_message(
            "Enabled from creation turn one",
            session_id=session.id,
        )
        service.get_job(first_job.id)

        restarted_service = _build_sqlite_service(
            temp_dir,
            database_path=database_path,
            execution_provider=provider,
        )
        restarted_session = restarted_service.get_session(session.id)
        assert restarted_session is not None
        assert restarted_session.turn_summary_checkpoint_initialized is True
        assert restarted_session.turn_summary_checkpoint_message_id is None

        second_job = restarted_service.submit_message(
            "Enabled from creation turn two",
            session_id=session.id,
        )
        restarted_service.get_job(second_job.id)

        summaries = restarted_service.list_turn_summaries(session.id)
        assert len(summaries) == 1
        summary_message_ids = set(summaries[0].source_message_ids)
        all_messages = restarted_service.list_messages(session.id)
        assert {
            message.content
            for message in all_messages
            if message.id in summary_message_ids
        } == {
            "Enabled from creation turn one",
            "Completed: Enabled from creation turn one",
            "Enabled from creation turn two",
            "Completed: Enabled from creation turn two",
        }


def test_failed_visible_jobs_still_trigger_turn_summary_after_four_terminal_messages() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        provider = _FailingVisibleExecutionProvider()
        service = _build_service(
            temp_dir,
            execution_provider=provider,
        )

        session = service.create_session(
            workspace_path=str(workspace),
            turn_summaries_enabled=True,
        )

        first_job = service.submit_message("Failed turn one", session_id=session.id)
        service.get_job(first_job.id)
        assert service.list_turn_summaries(session.id) == []

        second_job = service.submit_message("Failed turn two", session_id=session.id)
        service.get_job(second_job.id)

        summaries = service.list_turn_summaries(session.id)
        assert len(summaries) == 1
        assert summaries[0].content == "Hidden summary completed."

        summary_message_ids = set(summaries[0].source_message_ids)
        all_messages = service.list_messages(session.id)
        summarized_messages = [
            message
            for message in all_messages
            if message.id in summary_message_ids
        ]
        assert {message.content for message in summarized_messages} == {
            "Failed turn one",
            "Visible job failed.",
            "Failed turn two",
            "Visible job failed.",
        }
        assert sum(message.status == ChatMessageStatus.FAILED for message in summarized_messages) == 2


def test_turn_summary_provenance_snapshot_is_immutable_after_source_message_mutation() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        repository = InMemoryChatRepository(projects_root=temp_dir)
        service = MessageService(
            repository=repository,
            execution_provider=_InstantExecutionProvider(),
            default_workspace_path=temp_dir,
            audio_transcriber=DisabledAudioTranscriber(),
        )

        session = service.create_session(
            workspace_path=str(workspace),
            turn_summaries_enabled=True,
        )

        first_job = service.submit_message("Immutable snapshot turn one", session_id=session.id)
        service.get_job(first_job.id)
        second_job = service.submit_message("Immutable snapshot turn two", session_id=session.id)
        service.get_job(second_job.id)

        summaries = service.list_turn_summaries(session.id)
        assert len(summaries) == 1
        original_summary = summaries[0]
        original_response = TurnSummaryResponse.from_domain(
            original_summary,
            messages_by_id={message.id: message for message in service.list_messages(session.id)},
        )

        mutated_message_id = original_summary.source_message_ids[-1]
        mutated_message = repository.get_message(mutated_message_id)
        assert mutated_message is not None
        mutated_message.sync(
            content="This message was mutated later.",
            status=ChatMessageStatus.CANCELLED,
            agent_label="Mutated label",
        )
        repository.save_message(mutated_message)

        updated_summary = service.list_turn_summaries(session.id)[0]
        updated_response = TurnSummaryResponse.from_domain(
            updated_summary,
            messages_by_id={message.id: message for message in service.list_messages(session.id)},
        )

        assert updated_response.source_messages == original_response.source_messages


def test_enable_mid_chat_does_not_summarize_old_history_and_waits_for_new_window() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        provider = _InstantExecutionProvider()
        service = _build_service(
            temp_dir,
            execution_provider=provider,
        )

        session = service.create_session(workspace_path=str(workspace))

        history_job_1 = service.submit_message(
            "History turn one",
            session_id=session.id,
        )
        service.get_job(history_job_1.id)
        history_job_2 = service.submit_message(
            "History turn two",
            session_id=session.id,
        )
        service.get_job(history_job_2.id)

        updated = service.update_turn_summaries(
            session_id=session.id,
            enabled=True,
        )
        assert updated.turn_summary_checkpoint_message_id is not None
        assert service.list_turn_summaries(session.id) == []

        first_new_job = service.submit_message(
            "New turn after enabling",
            session_id=session.id,
        )
        service.get_job(first_new_job.id)

        summaries = service.list_turn_summaries(session.id)
        assert summaries == []

        second_new_job = service.submit_message(
            "Second new turn after enabling",
            session_id=session.id,
        )
        service.get_job(second_new_job.id)

        summaries = service.list_turn_summaries(session.id)
        assert len(summaries) == 1
        assert len(summaries[0].source_message_ids) == 4
        assert any(
            call[0].startswith("Summarize these recent chat updates for future context.")
            for call in provider.calls
        )

        summary_message_ids = set(summaries[0].source_message_ids)
        all_messages = service.list_messages(session.id)
        assert {
            message.content
            for message in all_messages
            if message.id in summary_message_ids
        } == {
            "New turn after enabling",
            "Completed: New turn after enabling",
            "Second new turn after enabling",
            "Completed: Second new turn after enabling",
        }


def test_disable_then_reenable_turn_summaries_resets_window() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        provider = _InstantExecutionProvider()
        service = _build_service(
            temp_dir,
            execution_provider=provider,
        )

        session = service.create_session(
            workspace_path=str(workspace),
            turn_summaries_enabled=True,
        )

        first_job = service.submit_message(
            "Initial enabled turn one",
            session_id=session.id,
        )
        service.get_job(first_job.id)

        service.update_turn_summaries(
            session_id=session.id,
            enabled=False,
        )
        disabled_window_job = service.submit_message(
            "While disabled",
            session_id=session.id,
        )
        service.get_job(disabled_window_job.id)
        assert service.list_turn_summaries(session.id) == []

        reenabled = service.update_turn_summaries(
            session_id=session.id,
            enabled=True,
        )
        assert reenabled.turn_summary_checkpoint_message_id is not None

        reenabled_job_1 = service.submit_message(
            "After re-enable turn one",
            session_id=session.id,
        )
        service.get_job(reenabled_job_1.id)
        assert service.list_turn_summaries(session.id) == []

        reenabled_job_2 = service.submit_message(
            "After re-enable turn two",
            session_id=session.id,
        )
        service.get_job(reenabled_job_2.id)

        summaries = service.list_turn_summaries(session.id)
        assert len(summaries) == 1

        summary_message_ids = set(summaries[0].source_message_ids)
        all_messages = service.list_messages(session.id)
        assert {
            message.content
            for message in all_messages
            if message.id in summary_message_ids
        } == {
            "After re-enable turn one",
            "Completed: After re-enable turn one",
            "After re-enable turn two",
            "Completed: After re-enable turn two",
        }


def test_sqlite_legacy_enabled_session_is_repaired_without_backfilling_history() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        database_path = str(Path(temp_dir) / "chat.sqlite3")
        provider = _InstantExecutionProvider()
        service = _build_sqlite_service(
            temp_dir,
            database_path=database_path,
            execution_provider=provider,
        )

        session = service.create_session(workspace_path=str(workspace))
        history_job_1 = service.submit_message("Legacy history turn one", session_id=session.id)
        service.get_job(history_job_1.id)
        history_job_2 = service.submit_message("Legacy history turn two", session_id=session.id)
        service.get_job(history_job_2.id)

        repository = SqliteChatRepository(
            database_path=database_path,
            projects_root=temp_dir,
        )
        with repository._connect() as connection:
            connection.execute(
                """
                UPDATE sessions
                SET turn_summaries_enabled = 1,
                    turn_summary_checkpoint_message_id = NULL,
                    turn_summary_checkpoint_initialized = 0
                WHERE id = ?
                """,
                (session.id,),
            )
            connection.commit()

        upgraded_service = _build_sqlite_service(
            temp_dir,
            database_path=database_path,
            execution_provider=provider,
        )
        repaired_session = upgraded_service.get_session(session.id)
        assert repaired_session is not None
        assert repaired_session.turn_summaries_enabled is True
        assert repaired_session.turn_summary_checkpoint_initialized is True
        assert repaired_session.turn_summary_checkpoint_message_id is not None

        first_new_job = upgraded_service.submit_message(
            "Post-upgrade turn one",
            session_id=session.id,
        )
        upgraded_service.get_job(first_new_job.id)
        assert upgraded_service.list_turn_summaries(session.id) == []

        second_new_job = upgraded_service.submit_message(
            "Post-upgrade turn two",
            session_id=session.id,
        )
        upgraded_service.get_job(second_new_job.id)

        summaries = upgraded_service.list_turn_summaries(session.id)
        assert len(summaries) == 1
        summary_message_ids = set(summaries[0].source_message_ids)
        all_messages = upgraded_service.list_messages(session.id)
        assert {
            message.content
            for message in all_messages
            if message.id in summary_message_ids
        } == {
            "Post-upgrade turn one",
            "Completed: Post-upgrade turn one",
            "Post-upgrade turn two",
            "Completed: Post-upgrade turn two",
        }


def test_sqlite_legacy_enabled_session_with_existing_summary_keeps_unsummarized_tail() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir) / "repo"
        workspace.mkdir()
        database_path = str(Path(temp_dir) / "chat.sqlite3")
        provider = _InstantExecutionProvider()
        service = _build_sqlite_service(
            temp_dir,
            database_path=database_path,
            execution_provider=provider,
        )

        session = service.create_session(
            workspace_path=str(workspace),
            turn_summaries_enabled=True,
        )

        first_job = service.submit_message("First summary turn one", session_id=session.id)
        service.get_job(first_job.id)
        second_job = service.submit_message("First summary turn two", session_id=session.id)
        service.get_job(second_job.id)
        initial_summaries = service.list_turn_summaries(session.id)
        assert len(initial_summaries) == 1

        tail_job = service.submit_message("Unsummarized tail turn", session_id=session.id)
        service.get_job(tail_job.id)
        assert len(service.list_turn_summaries(session.id)) == 1

        repository = SqliteChatRepository(
            database_path=database_path,
            projects_root=temp_dir,
        )
        with repository._connect() as connection:
            connection.execute(
                """
                UPDATE sessions
                SET turn_summary_checkpoint_message_id = NULL,
                    turn_summary_checkpoint_initialized = 0
                WHERE id = ?
                """,
                (session.id,),
            )
            connection.commit()

        upgraded_service = _build_sqlite_service(
            temp_dir,
            database_path=database_path,
            execution_provider=provider,
        )
        repaired_session = upgraded_service.get_session(session.id)
        assert repaired_session is not None
        assert repaired_session.turn_summary_checkpoint_initialized is True
        assert (
            repaired_session.turn_summary_checkpoint_message_id
            == initial_summaries[0].source_message_ids[-1]
        )

        post_upgrade_job = upgraded_service.submit_message(
            "Post-upgrade new turn",
            session_id=session.id,
        )
        upgraded_service.get_job(post_upgrade_job.id)

        summaries = upgraded_service.list_turn_summaries(session.id)
        assert len(summaries) == 2
        summary_message_ids = set(summaries[-1].source_message_ids)
        all_messages = upgraded_service.list_messages(session.id)
        assert {
            message.content
            for message in all_messages
            if message.id in summary_message_ids
        } == {
            "Unsummarized tail turn",
            "Completed: Unsummarized tail turn",
            "Post-upgrade new turn",
            "Completed: Post-upgrade new turn",
        }
