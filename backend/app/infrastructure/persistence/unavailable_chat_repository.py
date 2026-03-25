from __future__ import annotations

from backend.app.domain.entities.agent_profile import AgentProfile
from backend.app.domain.entities.chat_message import ChatMessage
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.job import Job
from backend.app.domain.entities.workspace import Workspace
from backend.app.domain.repositories.chat_repository import (
    ChatRepository,
    PersistenceDiagnosticIssue,
    PersistenceUnavailableError,
)


class UnavailableChatRepository(ChatRepository):
    def __init__(self, issue: PersistenceDiagnosticIssue) -> None:
        self._issue = issue

    def is_available(self) -> bool:
        return False

    def startup_issue(self) -> PersistenceDiagnosticIssue | None:
        return self._issue

    def reserve_message(self, message: ChatMessage) -> ChatMessage:
        raise PersistenceUnavailableError(self._issue)

    def save_job(self, job: Job) -> None:
        raise PersistenceUnavailableError(self._issue)

    def get_job(self, job_id: str) -> Job | None:
        raise PersistenceUnavailableError(self._issue)

    def save_session(self, session: ChatSession) -> None:
        raise PersistenceUnavailableError(self._issue)

    def get_session(self, session_id: str) -> ChatSession | None:
        raise PersistenceUnavailableError(self._issue)

    def list_sessions(self) -> list[ChatSession]:
        raise PersistenceUnavailableError(self._issue)

    def save_agent_profile(self, profile: AgentProfile) -> None:
        raise PersistenceUnavailableError(self._issue)

    def get_agent_profile(self, profile_id: str) -> AgentProfile | None:
        raise PersistenceUnavailableError(self._issue)

    def list_agent_profiles(self) -> list[AgentProfile]:
        raise PersistenceUnavailableError(self._issue)

    def save_message(self, message: ChatMessage) -> None:
        raise PersistenceUnavailableError(self._issue)

    def get_message(self, message_id: str) -> ChatMessage | None:
        raise PersistenceUnavailableError(self._issue)

    def list_messages(self, session_id: str) -> list[ChatMessage]:
        raise PersistenceUnavailableError(self._issue)

    def list_workspaces(self) -> list[Workspace]:
        raise PersistenceUnavailableError(self._issue)

    def validate_integrity(self) -> list[PersistenceDiagnosticIssue]:
        return [self._issue]

    def save_turn(
        self,
        session: ChatSession,
        *,
        messages: list[ChatMessage],
        job: Job | None = None,
    ) -> bool:
        raise PersistenceUnavailableError(self._issue)
