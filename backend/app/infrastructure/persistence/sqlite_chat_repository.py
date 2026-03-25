from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Iterator, TypeVar

from backend.app.domain.entities.chat_message import (
    ChatMessageAuthorType,
    ChatMessage,
    ChatMessageReasonCode,
    MessageRecoveryAction,
    ChatMessageRole,
    ChatMessageStatus,
)
from backend.app.domain.entities.agent_configuration import (
    AgentConfiguration,
    AgentId,
    AgentTriggerSource,
    AgentType,
    AgentVisibilityMode,
    derive_legacy_auto_mode_fields,
)
from backend.app.domain.entities.agent_profile import AgentProfile, builtin_agent_profiles_by_id
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.job import Job, JobConversationKind, JobStatus
from backend.app.domain.entities.workspace import Workspace
from backend.app.domain.repositories.chat_repository import (
    ChatRepository,
    PersistenceDataError,
    PersistenceDiagnosticIssue,
)


_SQLITE_SCHEMA_VERSION = 1
EnumT = TypeVar("EnumT", bound=Enum)


class SqliteChatRepository(ChatRepository):
    def __init__(self, *, database_path: str, projects_root: str) -> None:
        self._database_path = Path(database_path).expanduser().resolve()
        self._projects_root = Path(projects_root).resolve()
        self._lock = RLock()
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_database()

    def reserve_message(self, message: ChatMessage) -> ChatMessage:
        if not message.dedupe_key:
            self.save_message(message)
            return message

        with self._lock, self._connect() as connection:
            existing = self._get_message_by_dedupe_key(
                connection,
                message.dedupe_key,
            )
            if existing is not None:
                return existing
            try:
                self._write_message(connection, message)
                connection.commit()
                return message
            except sqlite3.IntegrityError:
                connection.rollback()
                existing = self._get_message_by_dedupe_key(
                    connection,
                    message.dedupe_key,
                )
                if existing is not None:
                    return existing
                raise

    def save_job(self, job: Job) -> None:
        with self._lock, self._connect() as connection:
            self._write_job(connection, job)
            connection.commit()

    def get_job(self, job_id: str) -> Job | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        return self._job_from_row(row) if row is not None else None

    def save_session(self, session: ChatSession) -> None:
        with self._lock, self._connect() as connection:
            self._write_session(connection, session)
            connection.commit()

    def get_session(self, session_id: str) -> ChatSession | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return self._session_from_row(row) if row is not None else None

    def list_sessions(self) -> list[ChatSession]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC",
            ).fetchall()
        return [self._session_from_row(row) for row in rows]

    def save_agent_profile(self, profile: AgentProfile) -> None:
        with self._lock, self._connect() as connection:
            self._write_agent_profile(connection, profile)
            connection.commit()

    def get_agent_profile(self, profile_id: str) -> AgentProfile | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM agent_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
        return self._agent_profile_from_row(row) if row is not None else None

    def list_agent_profiles(self) -> list[AgentProfile]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_profiles ORDER BY updated_at DESC, id ASC",
            ).fetchall()
        return [self._agent_profile_from_row(row) for row in rows]

    def save_message(self, message: ChatMessage) -> None:
        with self._lock, self._connect() as connection:
            self._write_message(connection, message)
            connection.commit()

    def get_message(self, message_id: str) -> ChatMessage | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM messages WHERE id = ?",
                (message_id,),
            ).fetchone()
        return self._message_from_row(row) if row is not None else None

    def list_messages(self, session_id: str) -> list[ChatMessage]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM messages
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
        return [self._message_from_row(row) for row in rows]

    def list_workspaces(self) -> list[Workspace]:
        if not self._projects_root.exists():
            return []

        return [
            Workspace(name=path.name, path=str(path))
            for path in sorted(self._projects_root.iterdir())
            if path.is_dir() and not path.name.startswith(".")
        ]

    def validate_integrity(self) -> list[PersistenceDiagnosticIssue]:
        issues: list[PersistenceDiagnosticIssue] = []
        with self._lock, self._connect() as connection:
            issues.extend(self._collect_low_level_integrity_issues(connection))
            if issues:
                return issues
            for row in connection.execute("SELECT * FROM sessions").fetchall():
                try:
                    self._session_from_row(row)
                except PersistenceDataError as exc:
                    issues.append(exc.to_issue())
            for row in connection.execute("SELECT * FROM agent_profiles").fetchall():
                try:
                    profile = self._agent_profile_from_row(row)
                except PersistenceDataError as exc:
                    issues.append(exc.to_issue())
                    continue
                reserved_issue = self._reserved_builtin_agent_profile_issue(profile.id)
                if reserved_issue is not None:
                    issues.append(reserved_issue)
            for row in connection.execute("SELECT * FROM messages").fetchall():
                try:
                    self._message_from_row(row)
                except PersistenceDataError as exc:
                    issues.append(exc.to_issue())
            for row in connection.execute("SELECT * FROM jobs").fetchall():
                try:
                    self._job_from_row(row)
                except PersistenceDataError as exc:
                    issues.append(exc.to_issue())
        return issues

    def _reserved_builtin_agent_profile_issue(
        self,
        profile_id: str,
    ) -> PersistenceDiagnosticIssue | None:
        if profile_id not in builtin_agent_profiles_by_id():
            return None
        return PersistenceDiagnosticIssue(
            table="agent_profiles",
            row_id=profile_id,
            field="id",
            code="reserved_builtin_id",
            detail=(
                f"Agent profile id {profile_id} is reserved for a builtin profile "
                "and cannot be stored in persistence."
            ),
        )

    def save_turn(
        self,
        session: ChatSession,
        *,
        messages: list[ChatMessage],
        job: Job | None = None,
    ) -> bool:
        with self._lock, self._connect() as connection:
            try:
                self._write_session(connection, session)
                for message in messages:
                    self._write_message(connection, message)
                if job is not None:
                    self._write_job(connection, job)
                connection.commit()
                return True
            except sqlite3.IntegrityError:
                connection.rollback()
                return False

    def _initialize_database(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    title_is_placeholder INTEGER NOT NULL DEFAULT 0,
                    workspace_path TEXT NOT NULL,
                    workspace_name TEXT NOT NULL,
                    agent_profile_id TEXT NOT NULL DEFAULT 'default',
                    agent_profile_name TEXT NOT NULL DEFAULT 'Generator',
                    agent_profile_color TEXT NOT NULL DEFAULT '#55D6BE',
                    provider_session_id TEXT,
                    reviewer_provider_session_id TEXT,
                    agent_configuration_json TEXT,
                    active_agent_run_id TEXT,
                    active_agent_turn_index INTEGER NOT NULL DEFAULT 0,
                    auto_mode_enabled INTEGER NOT NULL DEFAULT 0,
                    auto_max_turns INTEGER NOT NULL DEFAULT 0,
                    auto_reviewer_prompt TEXT,
                    auto_turn_index INTEGER NOT NULL DEFAULT 0,
                    archived_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    author_type TEXT NOT NULL DEFAULT 'human',
                    agent_id TEXT NOT NULL DEFAULT 'generator',
                    agent_type TEXT NOT NULL DEFAULT 'generator',
                    agent_label TEXT,
                    visibility TEXT NOT NULL DEFAULT 'visible',
                    trigger_source TEXT NOT NULL DEFAULT 'system',
                    run_id TEXT,
                    dedupe_key TEXT,
                    submission_token TEXT,
                    reason_code TEXT,
                    recovery_action TEXT,
                    recovered_from_message_id TEXT,
                    superseded_by_message_id TEXT,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    job_id TEXT,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    user_message_id TEXT,
                    assistant_message_id TEXT,
                    provider_session_id TEXT,
                    conversation_kind TEXT NOT NULL DEFAULT 'primary',
                    agent_id TEXT NOT NULL DEFAULT 'generator',
                    agent_type TEXT NOT NULL DEFAULT 'generator',
                    trigger_source TEXT NOT NULL DEFAULT 'user',
                    run_id TEXT,
                    submission_token TEXT,
                    auto_chain_processed INTEGER NOT NULL DEFAULT 0,
                    execution_message TEXT,
                    image_paths_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL,
                    response TEXT,
                    error TEXT,
                    phase TEXT,
                    latest_activity TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS agent_profiles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    color_hex TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    configuration_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_updated_at
                ON sessions(updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_messages_session_created_at
                ON messages(session_id, created_at ASC);

                """
            )
            self._migrate_database(connection)
            connection.commit()

    def _migrate_database(self, connection: sqlite3.Connection) -> None:
        self._ensure_column(
            connection,
            "sessions",
            "title_is_placeholder",
            "INTEGER NOT NULL DEFAULT 0",
        )
        self._ensure_column(connection, "sessions", "agent_profile_id", "TEXT NOT NULL DEFAULT 'default'")
        self._ensure_column(connection, "sessions", "agent_profile_name", "TEXT NOT NULL DEFAULT 'Generator'")
        self._ensure_column(connection, "sessions", "agent_profile_color", "TEXT NOT NULL DEFAULT '#55D6BE'")
        self._ensure_column(connection, "sessions", "provider_session_id", "TEXT")
        self._ensure_column(connection, "sessions", "reviewer_provider_session_id", "TEXT")
        self._ensure_column(connection, "sessions", "agent_configuration_json", "TEXT")
        self._ensure_column(connection, "sessions", "active_agent_run_id", "TEXT")
        self._ensure_column(
            connection,
            "sessions",
            "active_agent_turn_index",
            "INTEGER NOT NULL DEFAULT 0",
        )
        self._ensure_column(
            connection,
            "sessions",
            "auto_mode_enabled",
            "INTEGER NOT NULL DEFAULT 0",
        )
        self._ensure_column(
            connection,
            "sessions",
            "auto_max_turns",
            "INTEGER NOT NULL DEFAULT 0",
        )
        self._ensure_column(connection, "sessions", "auto_reviewer_prompt", "TEXT")
        self._ensure_column(
            connection,
            "sessions",
            "auto_turn_index",
            "INTEGER NOT NULL DEFAULT 0",
        )
        self._ensure_column(connection, "sessions", "archived_at", "TEXT")

        self._ensure_column(connection, "jobs", "execution_message", "TEXT")
        self._ensure_column(connection, "jobs", "user_message_id", "TEXT")
        self._ensure_column(connection, "jobs", "assistant_message_id", "TEXT")
        self._ensure_column(connection, "jobs", "provider_session_id", "TEXT")
        self._ensure_column(
            connection,
            "jobs",
            "image_paths_json",
            "TEXT NOT NULL DEFAULT '[]'",
        )
        self._ensure_column(connection, "jobs", "response", "TEXT")
        self._ensure_column(connection, "jobs", "error", "TEXT")
        self._ensure_column(connection, "jobs", "phase", "TEXT")
        self._ensure_column(connection, "jobs", "latest_activity", "TEXT")
        self._ensure_column(connection, "jobs", "completed_at", "TEXT")
        self._ensure_column(connection, "messages", "author_type", "TEXT NOT NULL DEFAULT 'human'")
        self._ensure_column(connection, "messages", "agent_id", "TEXT NOT NULL DEFAULT 'generator'")
        self._ensure_column(connection, "messages", "agent_type", "TEXT NOT NULL DEFAULT 'generator'")
        self._ensure_column(connection, "messages", "agent_label", "TEXT")
        self._ensure_column(connection, "messages", "visibility", "TEXT NOT NULL DEFAULT 'visible'")
        self._ensure_column(connection, "messages", "trigger_source", "TEXT NOT NULL DEFAULT 'system'")
        self._ensure_column(connection, "messages", "run_id", "TEXT")
        self._ensure_column(connection, "messages", "dedupe_key", "TEXT")
        self._ensure_column(connection, "messages", "submission_token", "TEXT")
        self._ensure_column(connection, "messages", "reason_code", "TEXT")
        self._ensure_column(connection, "messages", "recovery_action", "TEXT")
        self._ensure_column(connection, "messages", "recovered_from_message_id", "TEXT")
        self._ensure_column(connection, "messages", "superseded_by_message_id", "TEXT")
        self._ensure_column(
            connection,
            "jobs",
            "conversation_kind",
            "TEXT NOT NULL DEFAULT 'primary'",
        )
        self._ensure_column(connection, "jobs", "agent_id", "TEXT NOT NULL DEFAULT 'generator'")
        self._ensure_column(connection, "jobs", "agent_type", "TEXT NOT NULL DEFAULT 'generator'")
        self._ensure_column(connection, "jobs", "trigger_source", "TEXT NOT NULL DEFAULT 'user'")
        self._ensure_column(connection, "jobs", "run_id", "TEXT")
        self._ensure_column(connection, "jobs", "submission_token", "TEXT")
        self._ensure_column(
            connection,
            "jobs",
            "auto_chain_processed",
            "INTEGER NOT NULL DEFAULT 0",
        )
        self._ensure_column(connection, "agent_profiles", "configuration_json", "TEXT")
        self._repair_duplicate_message_dedupe_keys(connection)
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_dedupe_key
            ON messages(dedupe_key)
            WHERE dedupe_key IS NOT NULL
            """
        )
        current_version = connection.execute("PRAGMA user_version").fetchone()[0]
        if current_version < _SQLITE_SCHEMA_VERSION:
            connection.execute(f"PRAGMA user_version = {_SQLITE_SCHEMA_VERSION}")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        try:
            yield connection
        finally:
            connection.close()

    def _session_from_row(self, row: sqlite3.Row) -> ChatSession:
        agent_configuration = self._load_agent_configuration(row)
        session_id = self._read_required_text(
            row["id"],
            table="sessions",
            row_id=None,
            field="id",
        )
        return ChatSession(
            id=session_id,
            title=self._read_required_text(
                row["title"],
                table="sessions",
                row_id=session_id,
                field="title",
            ),
            title_is_placeholder=bool(row["title_is_placeholder"]),
            workspace_path=self._read_required_text(
                row["workspace_path"],
                table="sessions",
                row_id=session_id,
                field="workspace_path",
            ),
            workspace_name=self._read_required_text(
                row["workspace_name"],
                table="sessions",
                row_id=session_id,
                field="workspace_name",
            ),
            agent_profile_id=self._read_required_text(
                row["agent_profile_id"],
                table="sessions",
                row_id=session_id,
                field="agent_profile_id",
            ),
            agent_profile_name=self._read_required_text(
                row["agent_profile_name"],
                table="sessions",
                row_id=session_id,
                field="agent_profile_name",
            ),
            agent_profile_color=self._read_required_text(
                row["agent_profile_color"],
                table="sessions",
                row_id=session_id,
                field="agent_profile_color",
            ),
            provider_session_id=row["provider_session_id"],
            reviewer_provider_session_id=row["reviewer_provider_session_id"],
            agent_configuration=agent_configuration,
            active_agent_run_id=row["active_agent_run_id"],
            active_agent_turn_index=row["active_agent_turn_index"] or 0,
            auto_mode_enabled=bool(row["auto_mode_enabled"]),
            auto_max_turns=row["auto_max_turns"] or 0,
            auto_reviewer_prompt=row["auto_reviewer_prompt"],
            auto_turn_index=row["auto_turn_index"] or 0,
            archived_at=self._deserialize_optional_datetime(
                row["archived_at"],
                table="sessions",
                row_id=session_id,
                field="archived_at",
            ),
            created_at=self._deserialize_required_datetime(
                row["created_at"],
                table="sessions",
                row_id=session_id,
                field="created_at",
            ),
            updated_at=self._deserialize_required_datetime(
                row["updated_at"],
                table="sessions",
                row_id=session_id,
                field="updated_at",
            ),
        )

    def _agent_profile_from_row(self, row: sqlite3.Row) -> AgentProfile:
        profile_id = self._read_required_text(
            row["id"],
            table="agent_profiles",
            row_id=None,
            field="id",
        )
        return AgentProfile(
            id=profile_id,
            name=self._read_required_text(
                row["name"],
                table="agent_profiles",
                row_id=profile_id,
                field="name",
            ),
            description=row["description"] or "",
            color_hex=self._read_required_text(
                row["color_hex"],
                table="agent_profiles",
                row_id=profile_id,
                field="color_hex",
            ),
            prompt=self._read_required_text(
                row["prompt"],
                table="agent_profiles",
                row_id=profile_id,
                field="prompt",
            ),
            configuration=self._load_agent_profile_configuration(
                row=row,
                profile_id=profile_id,
            ),
            created_at=self._deserialize_required_datetime(
                row["created_at"],
                table="agent_profiles",
                row_id=profile_id,
                field="created_at",
            ),
            updated_at=self._deserialize_required_datetime(
                row["updated_at"],
                table="agent_profiles",
                row_id=profile_id,
                field="updated_at",
            ),
        ).normalized()

    def _load_agent_profile_configuration(
        self,
        *,
        row: sqlite3.Row,
        profile_id: str,
    ) -> AgentConfiguration | None:
        configuration_json = row["configuration_json"]
        if not isinstance(configuration_json, str) or not configuration_json.strip():
            return None
        try:
            payload = json.loads(configuration_json)
            if not isinstance(payload, dict):
                raise ValueError("Expected configuration_json to decode to an object.")
            return AgentConfiguration.from_dict(payload)
        except (json.JSONDecodeError, ValueError) as exc:
            raise PersistenceDataError(
                table="agent_profiles",
                row_id=profile_id,
                field="configuration_json",
                code="invalid_configuration_json",
                detail=str(exc),
            ) from exc

    def _message_from_row(self, row: sqlite3.Row) -> ChatMessage:
        message_id = self._read_required_text(
            row["id"],
            table="messages",
            row_id=None,
            field="id",
        )
        role = self._read_required_enum(
            row["role"],
            ChatMessageRole,
            table="messages",
            row_id=message_id,
            field="role",
        )
        default_author_type = (
            ChatMessageAuthorType.ASSISTANT
            if role == ChatMessageRole.ASSISTANT
            else ChatMessageAuthorType.HUMAN
        )
        default_agent_id = (
            AgentId.GENERATOR
            if role == ChatMessageRole.ASSISTANT
            else AgentId.USER
        )
        default_agent_type = (
            AgentType.GENERATOR
            if role == ChatMessageRole.ASSISTANT
            else AgentType.HUMAN
        )
        default_trigger_source = (
            AgentTriggerSource.SYSTEM
            if role == ChatMessageRole.ASSISTANT
            else AgentTriggerSource.USER
        )
        author_type = self._read_enum(
            row["author_type"],
            ChatMessageAuthorType,
            default_author_type,
        )
        agent_id = self._read_enum(
            row["agent_id"],
            AgentId,
            default_agent_id,
        )
        agent_type = self._read_enum(
            row["agent_type"],
            AgentType,
            default_agent_type,
        )
        trigger_source = self._read_enum(
            row["trigger_source"],
            AgentTriggerSource,
            default_trigger_source,
        )

        if role == ChatMessageRole.ASSISTANT and author_type == ChatMessageAuthorType.HUMAN:
            author_type = ChatMessageAuthorType.ASSISTANT
        if (
            role == ChatMessageRole.USER
            and author_type == ChatMessageAuthorType.HUMAN
            and agent_id == AgentId.GENERATOR
            and agent_type == AgentType.GENERATOR
        ):
            agent_id = AgentId.USER
            agent_type = AgentType.HUMAN
        if (
            role == ChatMessageRole.USER
            and author_type == ChatMessageAuthorType.HUMAN
            and trigger_source == AgentTriggerSource.SYSTEM
        ):
            trigger_source = AgentTriggerSource.USER

        message = ChatMessage(
            id=message_id,
            session_id=self._read_required_text(
                row["session_id"],
                table="messages",
                row_id=message_id,
                field="session_id",
            ),
            role=role,
            author_type=author_type,
            agent_id=agent_id,
            agent_type=agent_type,
            agent_label=row["agent_label"],
            visibility=self._read_enum(
                row["visibility"],
                AgentVisibilityMode,
                AgentVisibilityMode.VISIBLE,
            ),
            trigger_source=trigger_source,
            run_id=row["run_id"],
            dedupe_key=row["dedupe_key"],
            submission_token=row["submission_token"],
            reason_code=self._read_optional_enum(
                row["reason_code"],
                ChatMessageReasonCode,
            ),
            recovery_action=self._read_optional_enum(
                row["recovery_action"],
                MessageRecoveryAction,
            ),
            recovered_from_message_id=row["recovered_from_message_id"],
            superseded_by_message_id=row["superseded_by_message_id"],
            content=row["content"],
            status=self._read_required_enum(
                row["status"],
                ChatMessageStatus,
                table="messages",
                row_id=message_id,
                field="status",
            ),
            created_at=self._deserialize_required_datetime(
                row["created_at"],
                table="messages",
                row_id=message_id,
                field="created_at",
            ),
            updated_at=self._deserialize_required_datetime(
                row["updated_at"],
                table="messages",
                row_id=message_id,
                field="updated_at",
            ),
            job_id=row["job_id"],
        )
        message.normalize_recovery_metadata()
        return message

    def _job_from_row(self, row: sqlite3.Row) -> Job:
        job_id = self._read_required_text(
            row["id"],
            table="jobs",
            row_id=None,
            field="id",
        )
        return Job(
            id=job_id,
            session_id=self._read_required_text(
                row["session_id"],
                table="jobs",
                row_id=job_id,
                field="session_id",
            ),
            message=row["message"],
            user_message_id=row["user_message_id"],
            assistant_message_id=row["assistant_message_id"],
            provider_session_id=row["provider_session_id"],
            conversation_kind=self._read_enum(
                row["conversation_kind"],
                JobConversationKind,
                JobConversationKind.PRIMARY,
            ),
            agent_id=self._read_enum(
                row["agent_id"],
                AgentId,
                AgentId.GENERATOR,
            ),
            agent_type=self._read_enum(
                row["agent_type"],
                AgentType,
                AgentType.GENERATOR,
            ),
            trigger_source=self._read_enum(
                row["trigger_source"],
                AgentTriggerSource,
                AgentTriggerSource.USER,
            ),
            run_id=row["run_id"],
            submission_token=row["submission_token"],
            auto_chain_processed=bool(row["auto_chain_processed"]),
            execution_message=row["execution_message"],
            image_paths=json.loads(row["image_paths_json"] or "[]"),
            status=self._read_required_enum(
                row["status"],
                JobStatus,
                table="jobs",
                row_id=job_id,
                field="status",
            ),
            response=row["response"],
            error=row["error"],
            phase=row["phase"],
            latest_activity=row["latest_activity"],
            created_at=self._deserialize_required_datetime(
                row["created_at"],
                table="jobs",
                row_id=job_id,
                field="created_at",
            ),
            updated_at=self._deserialize_required_datetime(
                row["updated_at"],
                table="jobs",
                row_id=job_id,
                field="updated_at",
            ),
            completed_at=self._deserialize_datetime(row["completed_at"]),
        )

    def _serialize_datetime(self, value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    def _deserialize_datetime(self, value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value is not None else None

    def _deserialize_required_datetime(
        self,
        value: object,
        *,
        table: str,
        row_id: str | None,
        field: str,
    ) -> datetime:
        if not isinstance(value, str) or not value.strip():
            raise PersistenceDataError(
                table=table,
                row_id=row_id,
                field=field,
                code="missing_datetime",
                detail="Expected a non-empty ISO datetime string.",
            )
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise PersistenceDataError(
                table=table,
                row_id=row_id,
                field=field,
                code="invalid_datetime",
                detail=f"Invalid ISO datetime value: {value}",
            ) from exc

    def _deserialize_optional_datetime(
        self,
        value: object,
        *,
        table: str,
        row_id: str | None,
        field: str,
    ) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise PersistenceDataError(
                table=table,
                row_id=row_id,
                field=field,
                code="invalid_datetime",
                detail="Expected an ISO datetime string or null.",
            )
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise PersistenceDataError(
                table=table,
                row_id=row_id,
                field=field,
                code="invalid_datetime",
                detail=f"Invalid ISO datetime value: {value}",
            ) from exc

    def _ensure_column(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        column_name: str,
        definition: str,
    ) -> None:
        existing_columns = self._table_columns(connection, table_name)
        if column_name in existing_columns:
            return
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )

    def _repair_duplicate_message_dedupe_keys(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        if "dedupe_key" not in self._table_columns(connection, "messages"):
            return
        duplicate_keys = connection.execute(
            """
            SELECT dedupe_key
            FROM messages
            WHERE dedupe_key IS NOT NULL
            GROUP BY dedupe_key
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        for row in duplicate_keys:
            dedupe_key = row["dedupe_key"]
            duplicate_rows = connection.execute(
                """
                SELECT id
                FROM messages
                WHERE dedupe_key = ?
                ORDER BY created_at ASC, id ASC
                """,
                (dedupe_key,),
            ).fetchall()
            for duplicate_row in duplicate_rows[1:]:
                connection.execute(
                    "UPDATE messages SET dedupe_key = NULL WHERE id = ?",
                    (duplicate_row["id"],),
                )

    def _collect_low_level_integrity_issues(
        self,
        connection: sqlite3.Connection,
    ) -> list[PersistenceDiagnosticIssue]:
        try:
            rows = self._execute_integrity_check(connection)
        except sqlite3.DatabaseError as exc:
            return [
                PersistenceDiagnosticIssue(
                    table="database",
                    row_id=None,
                    field=None,
                    code="sqlite_database_error",
                    detail=str(exc),
                )
            ]

        issues = [
            PersistenceDiagnosticIssue(
                table="database",
                row_id=None,
                field=None,
                code="sqlite_integrity_check_failed",
                detail=row,
            )
            for row in rows
            if row != "ok"
        ]
        return issues

    def _execute_integrity_check(
        self,
        connection: sqlite3.Connection,
    ) -> list[str]:
        return [
            row[0]
            for row in connection.execute("PRAGMA integrity_check").fetchall()
        ]

    def _table_columns(
        self,
        connection: sqlite3.Connection,
        table_name: str,
    ) -> set[str]:
        return {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }

    def _read_enum(
        self,
        value: object,
        enum_type: type[EnumT],
        default: EnumT,
    ) -> EnumT:
        if not isinstance(value, str):
            return default
        try:
            return enum_type(value)
        except ValueError:
            return default

    def _read_required_enum(
        self,
        value: object,
        enum_type: type[EnumT],
        *,
        table: str,
        row_id: str | None,
        field: str,
    ) -> EnumT:
        if not isinstance(value, str) or not value.strip():
            raise PersistenceDataError(
                table=table,
                row_id=row_id,
                field=field,
                code="missing_enum",
                detail=f"Expected a non-empty {enum_type.__name__} value.",
            )
        try:
            return enum_type(value)
        except ValueError as exc:
            raise PersistenceDataError(
                table=table,
                row_id=row_id,
                field=field,
                code=f"invalid_{field}",
                detail=f"Unexpected {field} value: {value}",
            ) from exc

    def _read_optional_enum(
        self,
        value: object,
        enum_type: type[EnumT],
    ) -> EnumT | None:
        if not isinstance(value, str):
            return None
        try:
            return enum_type(value)
        except ValueError:
            return None

    def _read_required_text(
        self,
        value: object,
        *,
        table: str,
        row_id: str | None,
        field: str,
    ) -> str:
        if not isinstance(value, str) or not value.strip():
            raise PersistenceDataError(
                table=table,
                row_id=row_id,
                field=field,
                code=f"missing_{field}",
                detail=f"Expected a non-empty {field} value.",
            )
        return value

    def _load_agent_configuration(self, row: sqlite3.Row) -> AgentConfiguration:
        configuration_json = row["agent_configuration_json"]
        if configuration_json:
            try:
                payload = json.loads(configuration_json)
                return AgentConfiguration.from_dict(payload)
            except (json.JSONDecodeError, ValueError):
                pass
        return AgentConfiguration.from_legacy_auto_mode(
            enabled=bool(row["auto_mode_enabled"]),
            max_turns=row["auto_max_turns"] or 0,
            reviewer_prompt=row["auto_reviewer_prompt"],
            reviewer_provider_session_id=row["reviewer_provider_session_id"],
            generator_provider_session_id=row["provider_session_id"],
        )

    def _write_job(
        self,
        connection: sqlite3.Connection,
        job: Job,
    ) -> None:
        connection.execute(
            """
            INSERT INTO jobs (
                id,
                session_id,
                message,
                user_message_id,
                assistant_message_id,
                provider_session_id,
                conversation_kind,
                agent_id,
                agent_type,
                trigger_source,
                run_id,
                submission_token,
                auto_chain_processed,
                execution_message,
                image_paths_json,
                status,
                response,
                error,
                phase,
                latest_activity,
                created_at,
                updated_at,
                completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                session_id = excluded.session_id,
                message = excluded.message,
                user_message_id = excluded.user_message_id,
                assistant_message_id = excluded.assistant_message_id,
                provider_session_id = excluded.provider_session_id,
                conversation_kind = excluded.conversation_kind,
                agent_id = excluded.agent_id,
                agent_type = excluded.agent_type,
                trigger_source = excluded.trigger_source,
                run_id = excluded.run_id,
                submission_token = excluded.submission_token,
                auto_chain_processed = excluded.auto_chain_processed,
                execution_message = excluded.execution_message,
                image_paths_json = excluded.image_paths_json,
                status = excluded.status,
                response = excluded.response,
                error = excluded.error,
                phase = excluded.phase,
                latest_activity = excluded.latest_activity,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                completed_at = excluded.completed_at
            """,
            (
                job.id,
                job.session_id,
                job.message,
                job.user_message_id,
                job.assistant_message_id,
                job.provider_session_id,
                job.conversation_kind.value,
                job.agent_id.value,
                job.agent_type.value,
                job.trigger_source.value,
                job.run_id,
                job.submission_token,
                1 if job.auto_chain_processed else 0,
                job.execution_message,
                json.dumps(job.image_paths),
                job.status.value,
                job.response,
                job.error,
                job.phase,
                job.latest_activity,
                self._serialize_datetime(job.created_at),
                self._serialize_datetime(job.updated_at),
                self._serialize_datetime(job.completed_at),
            ),
        )

    def _write_session(
        self,
        connection: sqlite3.Connection,
        session: ChatSession,
    ) -> None:
        normalized_configuration = session.agent_configuration.normalized()
        session.agent_configuration = normalized_configuration
        (
            auto_mode_enabled,
            auto_max_turns,
            auto_reviewer_prompt,
            reviewer_provider_session_id,
        ) = derive_legacy_auto_mode_fields(normalized_configuration)
        generator_provider_session_id = normalized_configuration.agents[
            AgentId.GENERATOR
        ].provider_session_id
        reviewer_provider_session_id = (
            reviewer_provider_session_id
            or normalized_configuration.agents[AgentId.REVIEWER].provider_session_id
        )
        session.provider_session_id = generator_provider_session_id
        session.reviewer_provider_session_id = reviewer_provider_session_id
        session.auto_mode_enabled = auto_mode_enabled
        session.auto_max_turns = auto_max_turns
        session.auto_reviewer_prompt = auto_reviewer_prompt
        connection.execute(
            """
            INSERT INTO sessions (
                id,
                title,
                title_is_placeholder,
                workspace_path,
                workspace_name,
                agent_profile_id,
                agent_profile_name,
                agent_profile_color,
                provider_session_id,
                reviewer_provider_session_id,
                agent_configuration_json,
                active_agent_run_id,
                active_agent_turn_index,
                auto_mode_enabled,
                auto_max_turns,
                auto_reviewer_prompt,
                auto_turn_index,
                archived_at,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                title_is_placeholder = excluded.title_is_placeholder,
                workspace_path = excluded.workspace_path,
                workspace_name = excluded.workspace_name,
                agent_profile_id = excluded.agent_profile_id,
                agent_profile_name = excluded.agent_profile_name,
                agent_profile_color = excluded.agent_profile_color,
                provider_session_id = excluded.provider_session_id,
                reviewer_provider_session_id = excluded.reviewer_provider_session_id,
                agent_configuration_json = excluded.agent_configuration_json,
                active_agent_run_id = excluded.active_agent_run_id,
                active_agent_turn_index = excluded.active_agent_turn_index,
                auto_mode_enabled = excluded.auto_mode_enabled,
                auto_max_turns = excluded.auto_max_turns,
                auto_reviewer_prompt = excluded.auto_reviewer_prompt,
                auto_turn_index = excluded.auto_turn_index,
                archived_at = excluded.archived_at,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            (
                session.id,
                session.title,
                1 if session.title_is_placeholder else 0,
                session.workspace_path,
                session.workspace_name,
                session.agent_profile_id,
                session.agent_profile_name,
                session.agent_profile_color,
                generator_provider_session_id,
                reviewer_provider_session_id,
                json.dumps(normalized_configuration.to_dict()),
                session.active_agent_run_id,
                session.active_agent_turn_index,
                1 if auto_mode_enabled else 0,
                auto_max_turns,
                auto_reviewer_prompt,
                session.auto_turn_index,
                self._serialize_datetime(session.archived_at),
                self._serialize_datetime(session.created_at),
                self._serialize_datetime(session.updated_at),
            ),
        )

    def _write_agent_profile(
        self,
        connection: sqlite3.Connection,
        profile: AgentProfile,
    ) -> None:
        normalized = profile.normalized()
        connection.execute(
            """
            INSERT INTO agent_profiles (
                id,
                name,
                description,
                color_hex,
                prompt,
                configuration_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                color_hex = excluded.color_hex,
                prompt = excluded.prompt,
                configuration_json = excluded.configuration_json,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            (
                normalized.id,
                normalized.name,
                normalized.description,
                normalized.color_hex,
                normalized.prompt,
                json.dumps(normalized.resolved_configuration().to_dict()),
                self._serialize_datetime(normalized.created_at),
                self._serialize_datetime(normalized.updated_at),
            ),
        )

    def _write_message(
        self,
        connection: sqlite3.Connection,
        message: ChatMessage,
    ) -> None:
        message.validate_recovery_metadata()
        connection.execute(
            """
            INSERT INTO messages (
                id,
                session_id,
                role,
                author_type,
                agent_id,
                agent_type,
                agent_label,
                visibility,
                trigger_source,
                run_id,
                dedupe_key,
                submission_token,
                reason_code,
                recovery_action,
                recovered_from_message_id,
                superseded_by_message_id,
                content,
                status,
                created_at,
                updated_at,
                job_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                session_id = excluded.session_id,
                role = excluded.role,
                author_type = excluded.author_type,
                agent_id = excluded.agent_id,
                agent_type = excluded.agent_type,
                agent_label = excluded.agent_label,
                visibility = excluded.visibility,
                trigger_source = excluded.trigger_source,
                run_id = excluded.run_id,
                dedupe_key = excluded.dedupe_key,
                submission_token = excluded.submission_token,
                reason_code = excluded.reason_code,
                recovery_action = excluded.recovery_action,
                recovered_from_message_id = excluded.recovered_from_message_id,
                superseded_by_message_id = excluded.superseded_by_message_id,
                content = excluded.content,
                status = excluded.status,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                job_id = excluded.job_id
            """,
            (
                message.id,
                message.session_id,
                message.role.value,
                message.author_type.value,
                message.agent_id.value,
                message.agent_type.value,
                message.agent_label,
                message.visibility.value,
                message.trigger_source.value,
                message.run_id,
                message.dedupe_key,
                message.submission_token,
                message.reason_code.value if message.reason_code is not None else None,
                message.recovery_action.value if message.recovery_action is not None else None,
                message.recovered_from_message_id,
                message.superseded_by_message_id,
                message.content,
                message.status.value,
                self._serialize_datetime(message.created_at),
                self._serialize_datetime(message.updated_at),
                message.job_id,
            ),
        )

    def _get_message_by_dedupe_key(
        self,
        connection: sqlite3.Connection,
        dedupe_key: str,
    ) -> ChatMessage | None:
        row = connection.execute(
            "SELECT * FROM messages WHERE dedupe_key = ?",
            (dedupe_key,),
        ).fetchone()
        return self._message_from_row(row) if row is not None else None
