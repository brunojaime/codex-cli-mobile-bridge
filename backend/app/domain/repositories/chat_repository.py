from __future__ import annotations

from abc import ABC, abstractmethod

from backend.app.domain.entities.chat_message import ChatMessage
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.job import Job
from backend.app.domain.entities.workspace import Workspace


class ChatRepository(ABC):
    @abstractmethod
    def save_job(self, job: Job) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_job(self, job_id: str) -> Job | None:
        raise NotImplementedError

    @abstractmethod
    def save_session(self, session: ChatSession) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_session(self, session_id: str) -> ChatSession | None:
        raise NotImplementedError

    @abstractmethod
    def list_sessions(self) -> list[ChatSession]:
        raise NotImplementedError

    @abstractmethod
    def save_message(self, message: ChatMessage) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_message(self, message_id: str) -> ChatMessage | None:
        raise NotImplementedError

    @abstractmethod
    def list_messages(self, session_id: str) -> list[ChatMessage]:
        raise NotImplementedError

    @abstractmethod
    def list_workspaces(self) -> list[Workspace]:
        raise NotImplementedError
