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
    reviewer_provider_session_id: str | None = None
    auto_mode_enabled: bool = False
    auto_max_turns: int = 0
    auto_reviewer_prompt: str | None = None
    auto_turn_index: int = 0
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def touch(self) -> None:
        self.updated_at = utc_now()
