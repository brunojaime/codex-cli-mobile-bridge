from __future__ import annotations

from urllib.parse import urlsplit
from uuid import UUID

import httpx
from pydantic import StrictInt
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from backend.app.application.services.generator_reviewer_launch_service import (
    GeneratorReviewerLaunch,
)

mcp = FastMCP(
    "Generator + Reviewer",
    instructions=(
        "Start a new project chat only when the user requests it. Compose free prompts "
        "and a self-contained kickoff. Use the Bridge handoff metadata from the current "
        "human turn; never guess source IDs or a backend. Return the optional chat link."
    ),
    log_level="WARNING",
)
READ = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True
)


def _bridge_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username
        or parsed.password
        or not parsed.port
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Usá la URL loopback exacta del Bridge handoff context de este turno"
        )
    return f"http://127.0.0.1:{parsed.port}"


def _request(bridge_url: str, method: str, path: str, payload=None) -> dict:
    url = _bridge_url(bridge_url) + path
    try:
        with httpx.Client(
            timeout=60, trust_env=False, follow_redirects=False
        ) as client:
            response = client.request(method, url, json=payload)
        if response.is_error or response.is_redirect:
            return {
                "state": "error",
                "http_status": response.status_code,
                "detail": response.json().get("detail", "Bridge rechazó la solicitud"),
            }
        return response.json()
    except (httpx.HTTPError, ValueError):
        return {
            "state": "unconfirmed",
            "detail": (
                "Sin confirmación del Bridge. Consultá get_launch o repetí exactamente "
                "el mismo pedido; no cambies IDs ni abras otro chat para reintentar."
            ),
        }


@mcp.tool(annotations=READ)
def get_app_manifest() -> dict:
    """Read-only capabilities; does not create chats, jobs or model calls."""
    return {
        "app_id": "generator-reviewer",
        "default_turns": {"generator": 25, "reviewer": 25},
        "prompts": "free",
        "navigation": "optional chat link, never automatic",
        "source": "Bridge handoff context from the current human message",
        "requires_backend_route": "/agent-launches/generator-reviewer",
    }


@mcp.tool(annotations=WRITE)
def start_generator_reviewer(
    bridge_url: str,
    source_session_id: str,
    source_message_id: str,
    title: str,
    generator_prompt: str,
    reviewer_prompt: str,
    kickoff: str,
    generator_turns: StrictInt = 25,
    reviewer_turns: StrictInt = 25,
) -> dict:
    """Configure and start one new chat in the source project with free prompts.

    Each omitted agent limit is 25 independently. Limits are ceilings, not a
    requirement to spend all turns. Same human source and identical payload are
    idempotent; changed payload conflicts. A started result confirms submission,
    not task completion. Leave the user in the source chat and return chat_link.
    """
    payload = GeneratorReviewerLaunch(
        source_session_id=source_session_id,
        source_message_id=source_message_id,
        title=title,
        generator_prompt=generator_prompt,
        reviewer_prompt=reviewer_prompt,
        kickoff=kickoff,
        generator_turns=generator_turns,
        reviewer_turns=reviewer_turns,
    )
    return _request(
        bridge_url,
        "POST",
        "/agent-launches/generator-reviewer",
        payload.model_dump(mode="json"),
    )


@mcp.tool(annotations=READ)
def get_launch(bridge_url: str, launch_id: str) -> dict:
    """Inspect a previous launch without submitting another kickoff."""
    return _request(bridge_url, "GET", f"/agent-launches/{UUID(launch_id)}")


if __name__ == "__main__":
    mcp.run(transport="stdio")
