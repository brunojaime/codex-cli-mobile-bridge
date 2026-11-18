"""Paginated history and conditional refresh; compatible with the legacy API."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.domain.session_listing import decode_cursor, encode_cursor, card_key


class SessionChangesRequest(BaseModel):
    known: dict[str, str] = Field(default_factory=dict, max_length=10000)
    archived: bool = False
    search: str = Field(default="", max_length=200)
    workspace: str | None = Field(default=None, max_length=4096)
    limit: int = Field(default=40, ge=1, le=100)


class TrackedSessionsRequest(BaseModel):
    ids: list[str] = Field(max_length=1000)


def build_session_list_router(get_service):
    router = APIRouter()

    @router.get("/sessions/page")
    def page(
        service=Depends(get_service),
        limit: int = Query(40, ge=1, le=100),
        before: str | None = Query(None, max_length=1024),
        archived: bool = False,
        search: str = Query("", max_length=200),
        workspace: str | None = Query(None, max_length=4096),
    ):
        try:
            cursor = decode_cursor(before)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        cards = service.list_session_cards(
            limit=limit + 1,
            before=cursor,
            archived=archived,
            search=search.strip(),
            workspace=workspace,
        )
        cards.sort(key=card_key, reverse=True)
        items = cards[:limit]
        return {
            "items": items,
            "next_cursor": encode_cursor(items[-1]) if len(cards) > limit else None,
        }

    @router.post("/sessions/cards")
    def tracked_cards(payload: TrackedSessionsRequest, service=Depends(get_service)):
        # Background runs remain observable when the user searches or switches
        # to archived history; these cards do not populate the visible sidebar.
        if not payload.ids:
            return {"items": []}
        cards = service.list_session_cards(
            limit=0, archived=None, known_ids=tuple(payload.ids)
        )
        return {"items": cards}

    @router.post("/sessions/changes")
    def changes(payload: SessionChangesRequest, service=Depends(get_service)):
        # Refresh the recent page plus only rows already loaded by this client.
        # Fingerprints include derived pending state, so status changes do not
        # rely on the session's updated_at being touched by every write path.
        cards = service.list_session_cards(
            limit=payload.limit + 1,
            archived=payload.archived,
            search=payload.search.strip(),
            workspace=payload.workspace,
            known_ids=tuple(payload.known),
        )
        cards.sort(key=card_key, reverse=True)
        recent = cards[: payload.limit]
        # If more than a page arrived between refreshes, expose a new boundary
        # rather than silently skipping the gap before the older loaded pages.
        gap = (
            len(cards) > payload.limit
            and cards[payload.limit]["id"] not in payload.known
            and recent[-1]["id"] not in payload.known
        )
        recent_ids = {c["id"] for c in recent}
        cards = [c for c in cards if c["id"] in recent_ids or c["id"] in payload.known]
        current = {c["id"]: c for c in cards}
        return {
            "gap_cursor": encode_cursor(recent[-1]) if gap and recent else None,
            "items": [c for c in cards if payload.known.get(c["id"]) != c["revision"]],
            "removed_ids": [sid for sid in payload.known if sid not in current],
        }

    return router
