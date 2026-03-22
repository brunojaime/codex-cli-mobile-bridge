from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in {self.COMPLETED, self.FAILED}


@dataclass(slots=True)
class Job:
    id: str
    session_id: str
    message: str
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    provider_session_id: str | None = None
    status: JobStatus = JobStatus.PENDING
    response: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    completed_at: datetime | None = None

    def sync(
        self,
        *,
        status: JobStatus,
        response: str | None = None,
        error: str | None = None,
        provider_session_id: str | None = None,
    ) -> None:
        self.status = status
        self.response = response
        self.error = error
        if provider_session_id:
            self.provider_session_id = provider_session_id
        self.updated_at = utc_now()
        self.completed_at = self.updated_at if status.is_terminal else None
