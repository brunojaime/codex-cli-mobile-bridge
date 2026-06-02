from __future__ import annotations

from threading import RLock
from pathlib import Path

from backend.app.domain.entities.agent_configuration import AgentId, derive_legacy_auto_mode_fields
from backend.app.domain.entities.agent_run import AgentRun
from backend.app.domain.entities.agent_profile import AgentProfile, builtin_agent_profiles_by_id
from backend.app.domain.entities.chat_message import ChatMessage
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.chat_turn_summary import ChatTurnSummary
from backend.app.domain.entities.job import Job
from backend.app.domain.entities.workspace import Workspace
from backend.app.domain.repositories.chat_repository import (
    ChatRepository,
    PersistenceDiagnosticIssue,
)


class InMemoryChatRepository(ChatRepository):
    def __init__(self, *, projects_root: str) -> None:
        self._jobs: dict[str, Job] = {}
        self._sessions: dict[str, ChatSession] = {}
        self._agent_runs: dict[str, AgentRun] = {}
        self._agent_profiles: dict[str, AgentProfile] = {}
        self._messages: dict[str, ChatMessage] = {}
        self._turn_summaries: dict[str, ChatTurnSummary] = {}
        self._message_dedupe_keys: dict[str, str] = {}
        self._projects_root = Path(projects_root).resolve()
        self._lock = RLock()

    def reserve_message(self, message: ChatMessage) -> ChatMessage:
        with self._lock:
            if message.dedupe_key:
                existing_message_id = self._message_dedupe_keys.get(message.dedupe_key)
                if existing_message_id is not None:
                    return self._messages[existing_message_id]
            self._messages[message.id] = message
            if message.dedupe_key:
                self._message_dedupe_keys[message.dedupe_key] = message.id
            return message

    def save_job(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job

    def save_agent_run(self, agent_run: AgentRun) -> None:
        with self._lock:
            self._agent_runs[agent_run.run_id] = agent_run.normalized()

    def get_agent_run(self, run_id: str) -> AgentRun | None:
        with self._lock:
            return self._agent_runs.get(run_id)

    def list_agent_runs(self, session_id: str) -> list[AgentRun]:
        with self._lock:
            return sorted(
                (
                    agent_run
                    for agent_run in self._agent_runs.values()
                    if agent_run.session_id == session_id
                ),
                key=lambda agent_run: (agent_run.updated_at, agent_run.run_id),
                reverse=True,
            )

    def get_job(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def save_session(self, session: ChatSession) -> None:
        normalized_configuration = session.agent_configuration.normalized()
        session.agent_configuration = normalized_configuration
        (
            session.auto_mode_enabled,
            session.auto_max_turns,
            session.auto_reviewer_prompt,
            session.reviewer_provider_session_id,
        ) = derive_legacy_auto_mode_fields(normalized_configuration)
        session.provider_session_id = normalized_configuration.agents[
            AgentId.GENERATOR
        ].provider_session_id
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

    def save_turn_summary(self, summary: ChatTurnSummary) -> None:
        with self._lock:
            self._turn_summaries[summary.id] = summary

    def list_turn_summaries(self, session_id: str) -> list[ChatTurnSummary]:
        with self._lock:
            return sorted(
                (
                    summary
                    for summary in self._turn_summaries.values()
                    if summary.session_id == session_id
                ),
                key=lambda summary: (summary.created_at, summary.id),
            )

    def save_agent_profile(self, profile: AgentProfile) -> None:
        with self._lock:
            self._agent_profiles[profile.id] = profile.normalized()

    def get_agent_profile(self, profile_id: str) -> AgentProfile | None:
        with self._lock:
            return self._agent_profiles.get(profile_id)

    def list_agent_profiles(self) -> list[AgentProfile]:
        with self._lock:
            return sorted(
                self._agent_profiles.values(),
                key=lambda profile: (profile.updated_at, profile.id),
                reverse=True,
            )

    def save_message(self, message: ChatMessage) -> None:
        with self._lock:
            message.validate_recovery_metadata()
            if message.dedupe_key:
                existing_message_id = self._message_dedupe_keys.get(message.dedupe_key)
                if existing_message_id is not None and existing_message_id != message.id:
                    raise ValueError(f"Duplicate message dedupe key: {message.dedupe_key}")
            self._messages[message.id] = message
            if message.dedupe_key:
                self._message_dedupe_keys[message.dedupe_key] = message.id

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

    def validate_integrity(self) -> list[PersistenceDiagnosticIssue]:
        builtin_ids = set(builtin_agent_profiles_by_id())
        with self._lock:
            return [
                PersistenceDiagnosticIssue(
                    table="agent_profiles",
                    row_id=profile.id,
                    field="id",
                    code="reserved_builtin_id",
                    detail=(
                        f"Agent profile id {profile.id} is reserved for a builtin profile "
                        "and cannot be stored in persistence."
                    ),
                )
                for profile in self._agent_profiles.values()
                if profile.id in builtin_ids
            ]

    def save_turn(
        self,
        session: ChatSession,
        *,
        messages: list[ChatMessage],
        job: Job | None = None,
        agent_run: AgentRun | None = None,
    ) -> bool:
        try:
            self.save_session(session)
            if agent_run is not None:
                self.save_agent_run(agent_run)
            for message in messages:
                self.save_message(message)
            if job is not None:
                self.save_job(job)
            return True
        except ValueError:
            return False
