from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from backend.app.domain.entities.chat_message import ChatMessage
from backend.app.domain.entities.chat_turn_summary import ChatTurnSummary
from backend.app.domain.entities.agent_run import AgentRun
from backend.app.domain.entities.agent_profile import AgentProfile
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.job import Job
from backend.app.domain.entities.workspace import Workspace


@dataclass(frozen=True, slots=True)
class PersistenceDiagnosticIssue:
    table: str
    row_id: str | None
    field: str | None
    code: str
    detail: str


class PersistenceDataError(RuntimeError):
    def __init__(
        self,
        *,
        table: str,
        row_id: str | None,
        field: str | None,
        code: str,
        detail: str,
    ) -> None:
        self.table = table
        self.row_id = row_id
        self.field = field
        self.code = code
        self.detail = detail
        super().__init__(
            f"{table} row {row_id or '<unknown>'} has invalid {field or 'data'}: {detail}"
        )

    def to_issue(self) -> PersistenceDiagnosticIssue:
        return PersistenceDiagnosticIssue(
            table=self.table,
            row_id=self.row_id,
            field=self.field,
            code=self.code,
            detail=self.detail,
        )


class PersistenceUnavailableError(RuntimeError):
    def __init__(self, issue: PersistenceDiagnosticIssue) -> None:
        self.issue = issue
        super().__init__(issue.detail)


class ChatRepository(ABC):
    def is_available(self) -> bool:
        return True

    def startup_issue(self) -> PersistenceDiagnosticIssue | None:
        return None

    @abstractmethod
    def reserve_message(self, message: ChatMessage) -> ChatMessage:
        raise NotImplementedError

    @abstractmethod
    def save_job(self, job: Job) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_agent_run(self, agent_run: AgentRun) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_agent_run(self, run_id: str) -> AgentRun | None:
        raise NotImplementedError

    @abstractmethod
    def list_agent_runs(self, session_id: str) -> list[AgentRun]:
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
    def save_turn_summary(self, summary: ChatTurnSummary) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_turn_summaries(self, session_id: str) -> list[ChatTurnSummary]:
        raise NotImplementedError

    @abstractmethod
    def save_agent_profile(self, profile: AgentProfile) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_agent_profile(self, profile_id: str) -> AgentProfile | None:
        raise NotImplementedError

    @abstractmethod
    def list_agent_profiles(self) -> list[AgentProfile]:
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

    @abstractmethod
    def validate_integrity(self) -> list[PersistenceDiagnosticIssue]:
        raise NotImplementedError

    @abstractmethod
    def save_turn(
        self,
        session: ChatSession,
        *,
        messages: list[ChatMessage],
        job: Job | None = None,
        agent_run: AgentRun | None = None,
    ) -> bool:
        raise NotImplementedError
