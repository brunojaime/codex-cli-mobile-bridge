from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from backend.app.domain.entities.job import utc_now


@dataclass(slots=True)
class ChatSession:
    id: str
    title: str
    workspace_path: str
    workspace_name: str
    provider_session_id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def touch(self) -> None:
        self.updated_at = utc_now()
