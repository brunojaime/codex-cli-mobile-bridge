from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from backend.app.domain.entities.job import utc_now


class ChatMessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessageAuthorType(StrEnum):
    HUMAN = "human"
    ASSISTANT = "assistant"
    REVIEWER_CODEX = "reviewer_codex"


class ChatMessageStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class ChatMessage:
    id: str
    session_id: str
    role: ChatMessageRole
    author_type: ChatMessageAuthorType
    content: str
    status: ChatMessageStatus
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    job_id: str | None = None

    def sync(
        self,
        *,
        content: str | None = None,
        status: ChatMessageStatus | None = None,
        job_id: str | None = None,
        author_type: ChatMessageAuthorType | None = None,
    ) -> None:
        if content is not None:
            self.content = content
        if status is not None:
            self.status = status
        if job_id is not None:
            self.job_id = job_id
        if author_type is not None:
            self.author_type = author_type
        self.updated_at = utc_now()
