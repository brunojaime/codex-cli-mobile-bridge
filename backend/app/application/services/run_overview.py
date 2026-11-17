"""Plain-language overview of agent runs for the dashboard.

Every run is reduced to what a person needs at a glance: what was asked,
what the agent is doing right now, whether it needs the user, and how it
ended. The heavy detail stays in the session view.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from backend.app.domain.entities.job import Job, JobStatus

WAITING = "waiting"
_HIDDEN_KINDS = {"usage", "status"}


_INLINE_MARKDOWN = re.compile(r"(\*\*|__|`)")


def _first_line(text: str | None, limit: int = 140) -> str:
    for line in (text or "").splitlines():
        line = _INLINE_MARKDOWN.sub("", line).strip().strip("#*>-• ").strip()
        if line:
            return line if len(line) <= limit else line[: limit - 1] + "…"
    return ""


def _tail(text: str | None, limit: int = 320) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[-limit:]
    space = cut.find(" ")
    return "…" + (cut[space + 1 :] if 0 <= space < 40 else cut)


def _engine(job: Job) -> str:
    native = job.provider_session_id or ""
    if native.startswith("claude:"):
        return "claude"
    if native:
        return "codex"
    return "agent"


_EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def _tool_input(activity: dict[str, Any]) -> dict[str, Any]:
    detail = (activity.get("detail") or "").strip()
    if not detail.startswith("{"):
        return {}
    try:
        decoder = json.JSONDecoder()
        value, _ = decoder.raw_decode(detail)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _name(path: Any) -> str:
    return str(path or "").rstrip("/").rsplit("/", 1)[-1]


def _is_file_change(activity: dict[str, Any]) -> bool:
    title = str(activity.get("title") or "")
    return title.startswith("Cambios en") or title in _EDIT_TOOLS


def _step_text(activity: dict[str, Any]) -> str:
    kind = activity.get("kind", "")
    title = _first_line(activity.get("title"), 110)
    detail = activity.get("detail") or ""
    if kind == "subagent":
        return f"Subagente: {title}"
    if kind == "steer":
        return f"Le indicaste: {title}"
    if kind != "tool":
        return title
    data = _tool_input(activity)
    if title == "Comando" or title == "Bash":
        command = data.get("command") if data else _first_line(detail, 100)
        return "Ejecutando " + _first_line(str(command or ""), 100).lstrip("$ ")
    if title == "Read":
        return "Leyendo " + _name(data.get("file_path"))
    if title in _EDIT_TOOLS:
        return "Editando " + _name(data.get("file_path") or data.get("notebook_path"))
    if title in {"Grep", "Glob"}:
        return "Buscando " + str(data.get("pattern") or "")
    if title in {"WebFetch", "WebSearch", "Búsqueda web"}:
        return "Buscando en la web " + str(data.get("query") or data.get("url") or "")
    if title in {"TodoWrite", "TaskCreate", "TaskUpdate"}:
        return "Actualizando su lista de tareas"
    return title


_LATEST = {
    "launching claude in the current workspace.": "Arrancando Claude…",
    "claude session connected.": "Claude conectado, pensando…",
    "claude is responding.": "Escribiendo la respuesta…",
    "codex started working on the current turn.": "Codex pensando…",
}


def _latest_text(value: str | None) -> str:
    text = _first_line(value, 140)
    if not text:
        return "Arrancando…"
    return _LATEST.get(text.lower(), text)


def _interaction(activity: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(activity.get("interaction") or "{}")
    except ValueError:
        data = {}
    return {
        "request_id": data.get("request_id") or str(activity.get("id", "")).removeprefix("interaction-"),
        "kind": activity.get("kind"),
        "title": activity.get("title", ""),
        "detail": activity.get("detail", ""),
        "tool_name": data.get("tool_name"),
        "input": data.get("input") or {},
        "suggestions": data.get("suggestions") or [],
    }


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def run_card(job: Job, *, session_title: str, workspace_name: str, now: datetime) -> dict[str, Any]:
    activities = [a for a in job.activities if a.get("kind") not in _HIDDEN_KINDS]
    # A finished run cannot be answered anymore (e.g. it was stopped while
    # waiting), so stale requests are not offered.
    pending = (
        []
        if job.status.is_terminal
        else [_interaction(a) for a in activities if a.get("status") == WAITING]
    )
    steps = [a for a in activities if a.get("kind") not in {"commentary"} and "interaction" not in a]
    files = sum(1 for a in activities if _is_file_change(a))
    failed_steps = sum(1 for a in steps if a.get("status") == "failed")
    running = [a for a in activities if a.get("status") in {"running", "pending"}]

    if job.status == JobStatus.PENDING:
        state = "queued"
    elif job.status == JobStatus.RUNNING:
        state = "needs_you" if pending else "working"
    elif job.status == JobStatus.COMPLETED:
        state = "done"
    elif job.status == JobStatus.CANCELLED:
        state = "stopped"
    else:
        state = "failed"

    if pending:
        headline = pending[0]["title"]
    elif state == "queued":
        headline = "En cola, empieza en breve"
    elif state == "working":
        current = running[-1] if running else (activities[-1] if activities else None)
        headline = _step_text(current) if current else _latest_text(job.latest_activity)
    elif state == "done":
        headline = _first_line(job.response) or "Terminó"
    elif state == "stopped":
        headline = "Lo detuviste"
    else:
        headline = _first_line(job.error) or "Falló"

    started = _as_utc(job.created_at)
    ended = _as_utc(job.completed_at) if job.status.is_terminal else None
    elapsed = int(((ended or now) - started).total_seconds()) if started else 0
    return {
        "job_id": job.id,
        "session_id": job.session_id,
        "session_title": session_title,
        "workspace_name": workspace_name,
        "engine": _engine(job),
        "state": state,
        "status": job.status.value,
        "request": _first_line(job.message, 200),
        "headline": headline,
        "output": _tail(job.response) if not job.status.is_terminal else "",
        "error": job.error if state == "failed" else None,
        "pending": pending,
        "steps": len(steps),
        "failed_steps": failed_steps,
        "files_changed": files,
        "elapsed_seconds": max(elapsed, 0),
        "created_at": started.isoformat() if started else None,
        "updated_at": _as_utc(job.updated_at).isoformat() if job.updated_at else None,
        "completed_at": ended.isoformat() if ended else None,
    }


_ORDER = {"needs_you": 0, "working": 1, "queued": 2, "failed": 3, "done": 4, "stopped": 5}


def overview(cards: list[dict[str, Any]]) -> dict[str, Any]:
    cards = sorted(
        cards,
        key=lambda c: (_ORDER.get(c["state"], 9), -(datetime.fromisoformat(c["updated_at"]).timestamp() if c["updated_at"] else 0)),
    )
    counts = {state: 0 for state in _ORDER}
    for card in cards:
        counts[card["state"]] = counts.get(card["state"], 0) + 1
    return {"counts": counts, "runs": cards}
