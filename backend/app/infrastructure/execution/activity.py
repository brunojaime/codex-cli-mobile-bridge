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
        changes = [c for c in item.get("changes", []) if isinstance(c, dict)]
        names = [str(c.get("path", "")).rsplit("/", 1)[-1] for c in changes]
        title = (
            f"Cambios en {len(changes)} archivo{'s' if len(changes) != 1 else ''}: "
            + ", ".join(names[:4])
            + ("…" if len(names) > 4 else "")
            if changes
            else "Cambios en archivos"
        )
        blocks = []
        for change in changes:
            path = str(change.get("path", ""))
            change_kind = change.get("kind")
            label = (
                change_kind.get("type")
                if isinstance(change_kind, dict)
                else str(change_kind or "update")
            )
            diff = str(change.get("diff") or "").rstrip()
            header = f"--- {path} ({label})"
            blocks.append(header + ("\n" + diff if diff else ""))
        detail = "\n\n".join(blocks)
    elif kind == "collabagenttoolcall" or (
        kind == "tooluse" and str(item.get("name", "")) in {"Task", "Agent"}
    ):
        payload = item.get("input") or item.get("arguments") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                payload = {"prompt": payload}
        if not isinstance(payload, dict):
            payload = {}
        label = str(
            payload.get("description")
            or payload.get("subagent_type")
            or item.get("tool")
            or "Subagente"
        )
        prompt = str(payload.get("prompt") or payload.get("message") or "")
        subtype = payload.get("subagent_type")
        detail = (f"Tipo: {subtype}\n\n" if subtype else "") + prompt
        result = item.get("result")
        if isinstance(result, dict):
            for block in result.get("content", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    detail += "\n\n" + str(block.get("text", ""))
        return entry(item_id, "subagent", label, detail, status)
    elif kind in {
        "mcptoolcall",
        "dynamictoolcall",
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
    item_id: str,
    kind: str,
    title: str,
    detail: str,
    status: str,
    *,
    parent_id: str | None = None,
) -> dict[str, str]:
    result = {
        "id": item_id,
        "kind": kind,
        "title": title[:12000],
        "detail": detail[:16000],
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if parent_id:
        result["parent_id"] = str(parent_id)
    return result
