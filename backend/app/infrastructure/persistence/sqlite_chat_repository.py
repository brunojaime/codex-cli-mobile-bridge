from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Iterator

from backend.app.domain.entities.chat_message import (
    ChatMessageAuthorType,
    ChatMessage,
    ChatMessageRole,
    ChatMessageStatus,
)
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.job import Job, JobConversationKind, JobStatus
from backend.app.domain.entities.workspace import Workspace
from backend.app.domain.repositories.chat_repository import ChatRepository


class SqliteChatRepository(ChatRepository):
    def __init__(self, *, database_path: str, projects_root: str) -> None:
        self._database_path = Path(database_path).expanduser().resolve()
        self._projects_root = Path(projects_root).resolve()
        self._lock = RLock()
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_database()

    def save_job(self, job: Job) -> None:
        with self._lock, self._connect() as connection:
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
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    session_id = excluded.session_id,
                    message = excluded.message,
                    user_message_id = excluded.user_message_id,
                    assistant_message_id = excluded.assistant_message_id,
                    provider_session_id = excluded.provider_session_id,
                    conversation_kind = excluded.conversation_kind,
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
            connection.execute(
                """
                INSERT INTO sessions (
                    id,
                    title,
                    workspace_path,
                    workspace_name,
                    provider_session_id,
                    reviewer_provider_session_id,
                    auto_mode_enabled,
                    auto_max_turns,
                    auto_reviewer_prompt,
                    auto_turn_index,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    workspace_path = excluded.workspace_path,
                    workspace_name = excluded.workspace_name,
                    provider_session_id = excluded.provider_session_id,
                    reviewer_provider_session_id = excluded.reviewer_provider_session_id,
                    auto_mode_enabled = excluded.auto_mode_enabled,
                    auto_max_turns = excluded.auto_max_turns,
                    auto_reviewer_prompt = excluded.auto_reviewer_prompt,
                    auto_turn_index = excluded.auto_turn_index,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    session.id,
                    session.title,
                    session.workspace_path,
                    session.workspace_name,
                    session.provider_session_id,
                    session.reviewer_provider_session_id,
                    1 if session.auto_mode_enabled else 0,
                    session.auto_max_turns,
                    session.auto_reviewer_prompt,
                    session.auto_turn_index,
                    self._serialize_datetime(session.created_at),
                    self._serialize_datetime(session.updated_at),
                ),
            )
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

    def save_message(self, message: ChatMessage) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO messages (
                    id,
                    session_id,
                    role,
                    author_type,
                    content,
                    status,
                    created_at,
                    updated_at,
                    job_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    session_id = excluded.session_id,
                    role = excluded.role,
                    author_type = excluded.author_type,
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
                    message.content,
                    message.status.value,
                    self._serialize_datetime(message.created_at),
                    self._serialize_datetime(message.updated_at),
                    message.job_id,
                ),
            )
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

    def _initialize_database(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    workspace_path TEXT NOT NULL,
                    workspace_name TEXT NOT NULL,
                    provider_session_id TEXT,
                    reviewer_provider_session_id TEXT,
                    auto_mode_enabled INTEGER NOT NULL DEFAULT 0,
                    auto_max_turns INTEGER NOT NULL DEFAULT 0,
                    auto_reviewer_prompt TEXT,
                    auto_turn_index INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    author_type TEXT NOT NULL DEFAULT 'human',
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

                CREATE INDEX IF NOT EXISTS idx_sessions_updated_at
                ON sessions(updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_messages_session_created_at
                ON messages(session_id, created_at ASC);
                """
            )
            self._ensure_column(connection, "jobs", "execution_message", "TEXT")
            self._ensure_column(
                connection,
                "jobs",
                "image_paths_json",
                "TEXT NOT NULL DEFAULT '[]'",
            )
            self._ensure_column(connection, "messages", "author_type", "TEXT NOT NULL DEFAULT 'human'")
            self._ensure_column(connection, "sessions", "reviewer_provider_session_id", "TEXT")
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
            self._ensure_column(
                connection,
                "jobs",
                "conversation_kind",
                "TEXT NOT NULL DEFAULT 'primary'",
            )
            self._ensure_column(
                connection,
                "jobs",
                "auto_chain_processed",
                "INTEGER NOT NULL DEFAULT 0",
            )
            connection.commit()

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
        return ChatSession(
            id=row["id"],
            title=row["title"],
            workspace_path=row["workspace_path"],
            workspace_name=row["workspace_name"],
            provider_session_id=row["provider_session_id"],
            reviewer_provider_session_id=row["reviewer_provider_session_id"],
            auto_mode_enabled=bool(row["auto_mode_enabled"]),
            auto_max_turns=row["auto_max_turns"] or 0,
            auto_reviewer_prompt=row["auto_reviewer_prompt"],
            auto_turn_index=row["auto_turn_index"] or 0,
            created_at=self._deserialize_datetime(row["created_at"]),
            updated_at=self._deserialize_datetime(row["updated_at"]),
        )

    def _message_from_row(self, row: sqlite3.Row) -> ChatMessage:
        return ChatMessage(
            id=row["id"],
            session_id=row["session_id"],
            role=ChatMessageRole(row["role"]),
            author_type=ChatMessageAuthorType(row["author_type"] or "human"),
            content=row["content"],
            status=ChatMessageStatus(row["status"]),
            created_at=self._deserialize_datetime(row["created_at"]),
            updated_at=self._deserialize_datetime(row["updated_at"]),
            job_id=row["job_id"],
        )

    def _job_from_row(self, row: sqlite3.Row) -> Job:
        return Job(
            id=row["id"],
            session_id=row["session_id"],
            message=row["message"],
            user_message_id=row["user_message_id"],
            assistant_message_id=row["assistant_message_id"],
            provider_session_id=row["provider_session_id"],
            conversation_kind=JobConversationKind(row["conversation_kind"] or "primary"),
            auto_chain_processed=bool(row["auto_chain_processed"]),
            execution_message=row["execution_message"],
            image_paths=json.loads(row["image_paths_json"] or "[]"),
            status=JobStatus(row["status"]),
            response=row["response"],
            error=row["error"],
            phase=row["phase"],
            latest_activity=row["latest_activity"],
            created_at=self._deserialize_datetime(row["created_at"]),
            updated_at=self._deserialize_datetime(row["updated_at"]),
            completed_at=self._deserialize_datetime(row["completed_at"]),
        )

    def _serialize_datetime(self, value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    def _deserialize_datetime(self, value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value is not None else None

    def _ensure_column(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        column_name: str,
        definition: str,
    ) -> None:
        existing_columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name in existing_columns:
            return
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )
