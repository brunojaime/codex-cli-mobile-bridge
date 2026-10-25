"""Small, versioned sidebar cards. No prompts or transcript bodies on the wire."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime

CARD_FIELDS = (
    "id",
    "title",
    "workspace_path",
    "workspace_name",
    "archived_at",
    "created_at",
    "updated_at",
    "agent_profile_id",
    "agent_profile_name",
    "agent_profile_color",
    "active_agent_run_id",
    "active_agent_turn_index",
    "turn_summaries_enabled",
)


def finish_card(card):
    card = dict(card)
    for key in ("created_at", "updated_at", "archived_at", "last_message_at"):
        if card.get(key) is not None:
            value = card[key]
            if not isinstance(value, datetime):
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            card[key] = value.isoformat()
    card["turn_summaries_enabled"] = bool(card["turn_summaries_enabled"])
    card["has_pending_messages"] = bool(card["has_pending_messages"])
    if isinstance(card.get("agent_labels"), str):
        card["agent_labels"] = json.loads(card["agent_labels"])
    card["is_multi_agent"] = bool(card.get("is_multi_agent"))
    card["has_full_agent_configuration"] = False
    card["revision"] = hashlib.sha256(
        json.dumps(card, sort_keys=True).encode()
    ).hexdigest()[:24]
    return card


def card_key(card):
    return (
        card["last_message_at"] or card["created_at"],
        card["created_at"],
        card["id"],
    )


def encode_cursor(card):
    return base64.urlsafe_b64encode(json.dumps(card_key(card)).encode()).decode()


def decode_cursor(value):
    if value is None:
        return None
    try:
        values = json.loads(base64.b64decode(value, altchars=b"-_", validate=True))
        if (
            not isinstance(values, list)
            or len(values) != 3
            or not all(isinstance(x, str) for x in values)
        ):
            raise ValueError()
        datetime.fromisoformat(values[0])
        datetime.fromisoformat(values[1])
        return tuple(values)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ValueError("Invalid session cursor") from exc
