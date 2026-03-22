from __future__ import annotations

from threading import RLock
from pathlib import Path

from backend.app.domain.entities.chat_message import ChatMessage
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.job import Job
from backend.app.domain.entities.workspace import Workspace
from backend.app.domain.repositories.chat_repository import ChatRepository


class InMemoryChatRepository(ChatRepository):
    def __init__(self, *, projects_root: str) -> None:
        self._jobs: dict[str, Job] = {}
        self._sessions: dict[str, ChatSession] = {}
        self._messages: dict[str, ChatMessage] = {}
        self._projects_root = Path(projects_root).resolve()
        self._lock = RLock()

    def save_job(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job

    def get_job(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def save_session(self, session: ChatSession) -> None:
        with self._lock:
            self._sessions[session.id] = session

    def get_session(self, session_id: str) -> ChatSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def list_sessions(self) -> list[ChatSession]:
        with self._lock:
            return sorted(
                self._sessions.values(),
                key=lambda session: session.updated_at,
                reverse=True,
            )

    def save_message(self, message: ChatMessage) -> None:
        with self._lock:
            self._messages[message.id] = message

    def get_message(self, message_id: str) -> ChatMessage | None:
        with self._lock:
            return self._messages.get(message_id)

    def list_messages(self, session_id: str) -> list[ChatMessage]:
        with self._lock:
            return sorted(
                (
                    message
                    for message in self._messages.values()
                    if message.session_id == session_id
                ),
                key=lambda message: message.created_at,
            )

    def list_workspaces(self) -> list[Workspace]:
        if not self._projects_root.exists():
            return []

        workspaces = [
            Workspace(name=path.name, path=str(path))
            for path in sorted(self._projects_root.iterdir())
            if path.is_dir() and not path.name.startswith(".")
        ]
        return workspaces
