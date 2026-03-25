from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from backend.app.domain.entities.agent_configuration import AgentConfiguration
from backend.app.domain.entities.job import utc_now


@dataclass(slots=True)
class AgentRun:
    run_id: str
    session_id: str
    configuration: AgentConfiguration
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def normalized(self) -> "AgentRun":
        return AgentRun(
            run_id=self.run_id.strip(),
            session_id=self.session_id.strip(),
            configuration=self.configuration.normalized(),
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

