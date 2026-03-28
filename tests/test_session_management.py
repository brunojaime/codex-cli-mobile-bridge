from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from backend.app.application.services.message_service import MessageService
from backend.app.domain.entities.agent_configuration import AgentId
from backend.app.domain.entities.chat_session import ChatSession
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
