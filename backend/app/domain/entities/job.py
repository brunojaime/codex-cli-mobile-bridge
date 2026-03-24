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
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {self.COMPLETED, self.FAILED, self.CANCELLED}


@dataclass(slots=True)
class Job:
    id: str
    session_id: str
    message: str
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    provider_session_id: str | None = None
    execution_message: str | None = None
    image_paths: list[str] = field(default_factory=list)
    status: JobStatus = JobStatus.PENDING
    response: str | None = None
    error: str | None = None
    phase: str | None = None
    latest_activity: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    completed_at: datetime | None = None

    @property
    def elapsed_seconds(self) -> int:
        end = self.completed_at or self.updated_at
        return max(0, int((end - self.created_at).total_seconds()))

    def sync(
        self,
        *,
        status: JobStatus,
        response: str | None = None,
        error: str | None = None,
        provider_session_id: str | None = None,
        phase: str | None = None,
        latest_activity: str | None = None,
    ) -> None:
        self.status = status
        self.response = response
        self.error = error
        if provider_session_id:
            self.provider_session_id = provider_session_id
        self.phase = phase
        self.latest_activity = latest_activity
        self.updated_at = utc_now()
        self.completed_at = self.updated_at if status.is_terminal else None
