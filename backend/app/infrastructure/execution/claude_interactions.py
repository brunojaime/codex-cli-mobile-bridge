"""Claude Code interactive requests (stdio permission prompt protocol).

With ``--permission-prompt-tool stdio`` Claude sends ``control_request``
messages of subtype ``can_use_tool`` whenever it needs the user. They come in
three flavours, mirroring the interactive CLI:

* ``permission`` – a tool needs approval (Bash, WebFetch, MCP tools…). The CLI
  offers "Yes", "Yes, don't ask again" (``permission_suggestions``) and
  "No, tell Claude what to do differently".
* ``question`` – the ``AskUserQuestion`` tool: one or more questions with
  options (single or multi select) plus free text ("Other").
* ``plan`` – ``ExitPlanMode``: approve the plan (choosing how edits are handled
  afterwards) or keep planning with feedback.
"""

from __future__ import annotations

import json
from typing import Any

from backend.app.infrastructure.execution.activity import entry

WAITING = "waiting"
_PLAN_MODES = {"acceptEdits", "default", "auto"}


def interaction_kind(tool_name: str) -> str:
    if tool_name == "AskUserQuestion":
        return "question"
    if tool_name == "ExitPlanMode":
        return "plan"
    return "permission"


def _readable_input(tool_name: str, data: dict[str, Any]) -> str:
    if tool_name == "Bash" and data.get("command"):
        return "$ " + str(data["command"])
    for key in ("file_path", "url", "path", "pattern", "query"):
        if data.get(key):
            return str(data[key])
    try:
        return json.dumps(data, ensure_ascii=False, indent=2)[:4000]
    except (TypeError, ValueError):
        return str(data)[:4000]


def interaction_activity(request_id: str, request: dict[str, Any]) -> dict[str, str]:
    """Public activity describing a pending Claude request."""
    tool_name = str(request.get("tool_name") or "herramienta")
    tool_input = request.get("input") if isinstance(request.get("input"), dict) else {}
    kind = interaction_kind(tool_name)
    description = str(request.get("description") or tool_input.get("description") or "")
    if kind == "question":
        questions = tool_input.get("questions") or []
        first = questions[0].get("question") if questions and isinstance(questions[0], dict) else ""
        title = str(first or "Claude tiene una pregunta")
        detail = ""
    elif kind == "plan":
        title = "Claude propone un plan"
        detail = str(tool_input.get("plan") or "")
    else:
        title = f"Claude pide permiso para usar {tool_name}"
        if description:
            title += f": {description}"
        detail = _readable_input(tool_name, tool_input)
    activity = entry(f"interaction-{request_id}", kind, title, detail, WAITING)
    activity["interaction"] = json.dumps(
        {
            "request_id": request_id,
            "tool_name": tool_name,
            "kind": kind,
            "input": tool_input,
            "description": description,
            "suggestions": request.get("permission_suggestions") or [],
            "blocked_path": request.get("blocked_path"),
        },
        ensure_ascii=False,
    )
    return activity


def build_response(
    request: dict[str, Any], decision: dict[str, Any]
) -> tuple[dict[str, Any], str, str]:
    """Return (control response payload, resolution text, activity status)."""
    tool_name = str(request.get("tool_name") or "")
    tool_input = dict(request.get("input") or {})
    kind = interaction_kind(tool_name)
    action = str(decision.get("action") or "")
    message = str(decision.get("message") or "").strip()

    if action == "deny":
        default = {
            "question": "The user declined to answer.",
            "plan": "The user wants to keep planning.",
        }.get(kind, "The user denied this action.")
        payload: dict[str, Any] = {"behavior": "deny", "message": message or default}
        if decision.get("interrupt"):
            payload["interrupt"] = True
        label = {
            "question": "Sin respuesta",
            "plan": "Seguir planificando",
        }.get(kind, "Rechazado")
        return payload, label + (f": {message}" if message else ""), "failed"

    if kind == "question":
        raw = decision.get("answers")
        if not isinstance(raw, dict) or not raw:
            raise ValueError("Answers are required for a question.")
        answers = {str(key): str(value) for key, value in raw.items() if str(value).strip()}
        if not answers:
            raise ValueError("Answers are required for a question.")
        tool_input["answers"] = answers
        summary = "; ".join(answers.values())
        return {"behavior": "allow", "updatedInput": tool_input}, f"Respondiste: {summary}", "completed"

    payload = {"behavior": "allow", "updatedInput": tool_input}
    if kind == "plan":
        mode = str(decision.get("mode") or "default")
        if mode not in _PLAN_MODES:
            raise ValueError(f"Unsupported mode: {mode}")
        payload["updatedPermissions"] = [
            {"type": "setMode", "mode": mode, "destination": "session"}
        ]
        label = {
            "acceptEdits": "Plan aprobado · ediciones automáticas",
            "default": "Plan aprobado · aprobar cada edición",
            "auto": "Plan aprobado · modo automático",
        }[mode]
        return payload, label, "completed"

    if action == "allow_always":
        suggestions = request.get("permission_suggestions") or []
        if suggestions:
            payload["updatedPermissions"] = suggestions
            return payload, "Permitido (no volver a preguntar)", "completed"
    if action not in {"allow", "allow_always"}:
        raise ValueError(f"Unsupported action: {action}")
    return payload, "Permitido una vez", "completed"
