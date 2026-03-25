from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from backend.app.domain.entities.agent_configuration import AgentConfiguration
from backend.app.domain.entities.job import utc_now


@dataclass(slots=True)
class ChatSession:
    id: str
    title: str
    workspace_path: str
    workspace_name: str
    title_is_placeholder: bool = False
    agent_profile_id: str = "default"
    agent_profile_name: str = "Generator"
    agent_profile_color: str = "#55D6BE"
    provider_session_id: str | None = None
    reviewer_provider_session_id: str | None = None
    agent_configuration: AgentConfiguration = field(default_factory=AgentConfiguration.default)
    active_agent_run_id: str | None = None
    active_agent_turn_index: int = 0
    auto_mode_enabled: bool = False
    auto_max_turns: int = 0
    auto_reviewer_prompt: str | None = None
    auto_turn_index: int = 0
    archived_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def touch(self) -> None:
        self.updated_at = utc_now()
