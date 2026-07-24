from __future__ import annotations

from backend.app.api.schemas import ChatMessageResponse
from backend.app.domain.entities.agent_configuration import AgentId, AgentType
from backend.app.domain.entities.chat_message import (
    ChatMessage,
    ChatMessageAuthorType,
    ChatMessageRole,
    ChatMessageStatus,
)


def test_chat_response_compacts_legacy_automatic_ux_message() -> None:
    message = ChatMessage(
        id="message-1",
        session_id="session-1",
        role=ChatMessageRole.ASSISTANT,
        author_type=ChatMessageAuthorType.ASSISTANT,
        agent_id=AgentId.UX,
        agent_type=AgentType.UX,
        agent_label="UX Generator",
        status=ChatMessageStatus.COMPLETED,
        content=(
            "# UX Generator pass 1\n\n"
            "Status: completed\n\n"
            "Created a branded logo and tightened the app shell.\n"
            + ("full markdown detail\n" * 10_000)
        ),
    )

    response = ChatMessageResponse.from_domain(message)

    assert "UX Generator pass 1" in response.content
    assert "Status: completed" in response.content
    assert "Evidence: `.codex/ux/ux-generator-report.md`" in response.content
    assert "Created a branded logo" in response.content
    assert "Full UX output is stored in the evidence file, not in chat." in (
        response.content
    )
    assert "full markdown detail" not in response.content
    assert len(response.content) < 800
