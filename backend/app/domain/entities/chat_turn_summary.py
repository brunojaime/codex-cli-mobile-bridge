from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from backend.app.domain.entities.agent_configuration import AgentId, AgentType
from backend.app.domain.entities.chat_message import (
    ChatMessage,
    ChatMessageAuthorType,
    ChatMessageRole,
    ChatMessageStatus,
)

from backend.app.domain.entities.job import utc_now


@dataclass(frozen=True, slots=True)
class ChatTurnSummarySourceMessage:
    message_id: str
    role: ChatMessageRole
    author_type: ChatMessageAuthorType
    agent_id: AgentId
    agent_type: AgentType
    agent_label: str | None
    content: str | None
    status: ChatMessageStatus
    created_at: datetime

    @classmethod
    def from_message(cls, message: ChatMessage) -> "ChatTurnSummarySourceMessage":
        return cls(
            message_id=message.id,
            role=message.role,
            author_type=message.author_type,
            agent_id=message.agent_id,
            agent_type=message.agent_type,
            agent_label=message.agent_label,
            content=message.content,
            status=message.status,
            created_at=message.created_at,
        )


@dataclass(slots=True)
class ChatTurnSummary:
    id: str
    session_id: str
    content: str
    source_message_ids: tuple[str, ...] = ()
    source_messages: tuple[ChatTurnSummarySourceMessage, ...] = ()
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
