from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from backend.app.domain.entities.job import utc_now


class ChatMessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessageStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class ChatMessage:
    id: str
    session_id: str
    role: ChatMessageRole
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
    ) -> None:
        if content is not None:
            self.content = content
        if status is not None:
            self.status = status
        if job_id is not None:
            self.job_id = job_id
        self.updated_at = utc_now()
