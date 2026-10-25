from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from backend.app.domain.entities.chat_message import ChatMessage
from backend.app.domain.entities.chat_turn_summary import ChatTurnSummary
from backend.app.domain.entities.agent_run import AgentRun
from backend.app.domain.entities.agent_profile import AgentProfile
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.job import Job, JobStatus
from backend.app.domain.entities.workspace import Workspace


@dataclass(frozen=True, slots=True)
class PersistenceDiagnosticIssue:
    table: str
    row_id: str | None
    field: str | None
    code: str
    detail: str


@dataclass(frozen=True, slots=True)
class MessageCursor:
    created_at: datetime
    message_id: str


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
    def list_summary_jobs(self) -> list[Job]:
        """Status metadata for the sidebar; implementations may avoid large bodies."""
        return self.list_jobs()

    def list_session_cards(
        self,
        *,
        limit=40,
        before=None,
        archived=False,
        search="",
        workspace=None,
        known_ids=(),
    ):
        # Fallback for memory/testing adapters. SQLite projects directly in SQL.
        from backend.app.domain.session_listing import (
            CARD_FIELDS,
            finish_card,
            card_key,
        )

        cards = []
        for session in self.list_sessions():
            if archived is not None and bool(session.archived_at) != archived:
                continue
            if workspace and session.workspace_path != workspace:
                continue
            if (
                search.casefold()
                not in (session.title + " " + session.workspace_name).casefold()
            ):
                continue
            messages = self.list_messages(session.id)
            last = max(messages, key=lambda m: (m.created_at, m.id), default=None)
            card = {key: getattr(session, key) for key in CARD_FIELDS}
            configuration = session.agent_configuration.normalized()
            card["agent_labels"] = {
                key.value: agent.label for key, agent in configuration.agents.items()
            }
            card["is_multi_agent"] = configuration.preset.value != "solo" and any(
                key.value != "generator" and agent.enabled and agent.max_turns > 0
                for key, agent in configuration.agents.items()
            )
            card.update(
                last_message_at=last.created_at if last else None,
                last_message_preview=last.content[:120] if last else None,
                has_pending_messages=any(
                    m.status.value in {"reserved", "submission_pending", "pending"}
                    for m in messages
                ),
                turn_summary_count=len(self.list_turn_summaries(session.id)),
            )
            cards.append(finish_card(card))
        cards.sort(key=card_key, reverse=True)
        page = [c for c in cards if before is None or card_key(c) < before][:limit]
        ids = {c["id"] for c in page}
        return page + [c for c in cards if c["id"] in known_ids and c["id"] not in ids]

    def list_session_summary_inputs(self):
        for session in self.list_sessions():
            yield session, self.list_messages(session.id), len(self.list_turn_summaries(session.id))

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
    def list_jobs(self, *, statuses: set[JobStatus] | None = None) -> list[Job]:
        raise NotImplementedError

    @abstractmethod
    def list_jobs_for_session(self, session_id: str) -> list[Job]:
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
    def list_messages_before(
        self,
        session_id: str,
        *,
        before: MessageCursor,
        limit: int,
    ) -> list[ChatMessage]:
        raise NotImplementedError

    @abstractmethod
    def list_recent_messages(self, session_id: str, *, limit: int) -> list[ChatMessage]:
        raise NotImplementedError

    @abstractmethod
    def latest_user_message(self, session_id: str) -> ChatMessage | None:
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
