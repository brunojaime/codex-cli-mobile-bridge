from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from backend.app.domain.entities.chat_message import (
    ChatMessage,
    ChatMessageRole,
    ChatMessageStatus,
)
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.job import Job, JobStatus
from backend.app.domain.entities.workspace import Workspace
from backend.app.domain.repositories.chat_repository import ChatRepository
from backend.app.infrastructure.execution.base import ExecutionProvider


class MessageService:
    def __init__(
        self,
        *,
        repository: ChatRepository,
        execution_provider: ExecutionProvider,
        default_workspace_path: str,
    ) -> None:
        self._repository = repository
        self._execution_provider = execution_provider
        self._default_workspace_path = str(Path(default_workspace_path).resolve())

    def create_session(
        self,
        *,
        title: str | None = None,
        workspace_path: str | None = None,
    ) -> ChatSession:
        workspace = self._resolve_workspace(workspace_path)
        session = ChatSession(
            id=str(uuid4()),
            title=title or "New chat",
            workspace_path=workspace.path,
            workspace_name=workspace.name,
        )
        self._repository.save_session(session)
        return session

    def list_sessions(self) -> list[ChatSession]:
        return self._repository.list_sessions()

    def list_workspaces(self) -> list[Workspace]:
        return self._repository.list_workspaces()

    def get_session(self, session_id: str) -> ChatSession | None:
        return self._repository.get_session(session_id)

    def list_messages(self, session_id: str) -> list[ChatMessage]:
        return self._repository.list_messages(session_id)

    def submit_message(
        self,
        message: str,
        session_id: str | None = None,
        workspace_path: str | None = None,
    ) -> Job:
        session = self._resolve_session(
            message=message,
            session_id=session_id,
            workspace_path=workspace_path,
        )

        user_message = ChatMessage(
            id=str(uuid4()),
            session_id=session.id,
            role=ChatMessageRole.USER,
            content=message,
            status=ChatMessageStatus.COMPLETED,
        )
        assistant_message = ChatMessage(
            id=str(uuid4()),
            session_id=session.id,
            role=ChatMessageRole.ASSISTANT,
            content="",
            status=ChatMessageStatus.PENDING,
        )

        self._repository.save_message(user_message)
        self._repository.save_message(assistant_message)

        job_id = self._execution_provider.execute(
            message,
            provider_session_id=session.provider_session_id,
            workdir=session.workspace_path,
        )
        job = Job(
            id=job_id,
            session_id=session.id,
            message=message,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
            provider_session_id=session.provider_session_id,
        )
        assistant_message.sync(job_id=job.id)
        session.touch()

        self._repository.save_message(assistant_message)
        self._repository.save_job(job)
        self._repository.save_session(session)
        return job

    def get_job(self, job_id: str) -> Job | None:
        job = self._repository.get_job(job_id)
        if job is None:
            return None

        snapshot = self._execution_provider.get_snapshot(job_id)
        job.sync(
            status=snapshot.status,
            response=snapshot.response,
            error=snapshot.error,
            provider_session_id=snapshot.provider_session_id,
        )
        self._repository.save_job(job)
        self._sync_job_side_effects(job)
        return job

    def _resolve_session(
        self,
        *,
        message: str,
        session_id: str | None,
        workspace_path: str | None,
    ) -> ChatSession:
        if session_id:
            session = self._repository.get_session(session_id)
            if session is None:
                raise ValueError(f"Session {session_id} was not found.")
            if session.title == "New chat" and not self._repository.list_messages(session.id):
                session.title = self._derive_title(message)
            self._repository.save_session(session)
            return session

        session = self.create_session(
            title=self._derive_title(message),
            workspace_path=workspace_path,
        )
        return session

    def _sync_job_side_effects(self, job: Job) -> None:
        session = self._repository.get_session(job.session_id)
        if session and job.provider_session_id and session.provider_session_id != job.provider_session_id:
            session.provider_session_id = job.provider_session_id
            session.touch()
            self._repository.save_session(session)

        if job.assistant_message_id is None:
            return

        assistant_message = self._repository.get_message(job.assistant_message_id)
        if assistant_message is None:
            return

        if job.status == JobStatus.COMPLETED:
            assistant_message.sync(
                content=job.response or "",
                status=ChatMessageStatus.COMPLETED,
                job_id=job.id,
            )
        elif job.status == JobStatus.FAILED:
            assistant_message.sync(
                content=job.error or "Execution failed.",
                status=ChatMessageStatus.FAILED,
                job_id=job.id,
            )
        else:
            assistant_message.sync(
                status=ChatMessageStatus.PENDING,
                job_id=job.id,
            )

        self._repository.save_message(assistant_message)

        if session and job.status.is_terminal:
            session.touch()
            self._repository.save_session(session)

    def _derive_title(self, message: str) -> str:
        normalized = " ".join(message.split())
        if len(normalized) <= 48:
            return normalized or "New chat"
        return f"{normalized[:45]}..."

    def _resolve_workspace(self, workspace_path: str | None) -> Workspace:
        workspaces = self._repository.list_workspaces()
        if not workspaces:
            raise ValueError("No workspaces were found.")

        if workspace_path is None:
            for workspace in workspaces:
                if workspace.path == self._default_workspace_path:
                    return workspace
            return workspaces[0]

        for workspace in workspaces:
            if workspace.path == workspace_path:
                return workspace

        raise ValueError(f"Workspace {workspace_path} was not found.")
