"""Normalize public provider activity; never include private reasoning blocks."""

from __future__ import annotations

import json
from datetime import datetime, timezone


def activity_item(item: dict, *, completed: bool) -> dict[str, str] | None:
    kind = str(item.get("type", "")).replace("_", "").lower()
    item_id = str(item.get("id") or "")
    if not item_id:
        return None
    status = "completed" if completed else "running"
    raw_status = str(item.get("status", "")).lower()
    if (
        raw_status in {"failed", "declined", "cancelled"}
        or item.get("error")
        or item.get("exitCode", item.get("exit_code", 0)) not in (None, 0)
    ):
        status = "failed" if raw_status != "cancelled" else "cancelled"
    detail = ""
    if kind == "agentmessage":
        # Final responses already have their own place in the conversation.
        if item.get("phase") != "commentary":
            return None
        title = str(item.get("text") or "")
        if not title:
            return None
        return entry(item_id, "commentary", title, "", status)
    if kind == "commandexecution":
        title = "Comando"
        command = item.get("command", "")
        if isinstance(command, list):
            command = " ".join(str(part) for part in command)
        detail = str(command)
        output = item.get("aggregatedOutput", item.get("aggregated_output"))
        if output:
            detail += "\n\n" + str(output)
        code = item.get("exitCode", item.get("exit_code"))
        if completed and code is not None:
            detail += f"\n\nSalida: {code}"
    elif kind == "filechange":
        title = "Cambios en archivos"
        detail = "\n".join(
            str(change.get("path", ""))
            for change in item.get("changes", [])
            if isinstance(change, dict)
        )
    elif kind in {
        "mcptoolcall",
        "dynamictoolcall",
        "collabagenttoolcall",
        "tooluse",
        "websearch",
    }:
        title = str(
            item.get("tool")
            or item.get("name")
            or ("Búsqueda web" if kind == "websearch" else "Herramienta")
        )
        detail_value = item.get("arguments", item.get("input", item.get("query", "")))
        detail = (
            detail_value
            if isinstance(detail_value, str)
            else json.dumps(detail_value, ensure_ascii=False)
        )
        # Tool results can contain binary attachments; only display plain text.
        result = item.get("result")
        if isinstance(result, dict):
            for block in result.get("content", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    detail += "\n\n" + str(block.get("text", ""))
        if item.get("error"):
            detail += "\n\n" + str(item["error"])
    else:
        return None
    return entry(item_id, "tool", title, detail, status)


def entry(
    item_id: str, kind: str, title: str, detail: str, status: str
) -> dict[str, str]:
    return {
        "id": item_id,
        "kind": kind,
        "title": title[:12000],
        "detail": detail[:16000],
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
