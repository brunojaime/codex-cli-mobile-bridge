"""Claude permission rules saved per project (what "Permitir siempre" writes).

Claude Code stores remembered approvals in ``<project>/.claude/settings.local.json``
under ``permissions.allow``/``deny``/``ask``. This module reads them and removes
single rules without touching any other setting in the file.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

LISTS = ("allow", "ask", "deny")

CLAUDE_MODES = {
    "default": "Pregunta antes de editar archivos o ejecutar comandos.",
    "acceptEdits": "Edita archivos sin preguntar; los comandos te los pregunta.",
    "auto": "Decide solo qué es seguro; te pregunta lo riesgoso.",
    "dontAsk": "Nunca pregunta: lo que no esté permitido se rechaza.",
    "plan": "Solo planifica, no cambia nada.",
}


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise ValueError(f"No pude leer {path.name}: {exc}") from exc
    return data if isinstance(data, dict) else {}


def _rules(data: dict[str, Any]) -> dict[str, list[str]]:
    permissions = data.get("permissions") if isinstance(data.get("permissions"), dict) else {}
    return {
        name: [str(rule) for rule in permissions.get(name, []) if isinstance(rule, str)]
        for name in LISTS
    }


def codex_policy(exec_args: str) -> dict[str, str]:
    parts = shlex.split(exec_args or "")
    if "--dangerously-bypass-approvals-and-sandbox" in parts:
        return {"mode": "full-access", "description": "Acceso total sin pedir aprobación (configurado en el servidor)."}
    if "--full-auto" in parts:
        return {"mode": "full-auto", "description": "Trabaja en el proyecto y pregunta solo lo que sale de él."}
    for flag in ("-s", "--sandbox"):
        if flag in parts and parts.index(flag) + 1 < len(parts):
            mode = parts[parts.index(flag) + 1]
            return {"mode": mode, "description": f"Sandbox: {mode}."}
    return {"mode": "default", "description": "Configuración por defecto de Codex."}


def describe(workspace: str, *, claude_mode: str, codex_exec_args: str) -> dict[str, Any]:
    root = Path(workspace)
    local = root / ".claude" / "settings.local.json"
    shared = root / ".claude" / "settings.json"
    return {
        "workspace": workspace,
        "claude": {
            "mode": claude_mode,
            "description": CLAUDE_MODES.get(claude_mode, claude_mode),
        },
        "codex": codex_policy(codex_exec_args),
        "local": {"path": str(local), "rules": _rules(_read(local))},
        "shared": {"path": str(shared), "rules": _rules(_read(shared))},
    }


def remove_rule(workspace: str, list_name: str, rule: str) -> bool:
    if list_name not in LISTS:
        raise ValueError("Lista de permisos inválida.")
    path = Path(workspace) / ".claude" / "settings.local.json"
    data = _read(path)
    permissions = data.get("permissions")
    if not isinstance(permissions, dict):
        return False
    rules = permissions.get(list_name)
    if not isinstance(rules, list) or rule not in rules:
        return False
    permissions[list_name] = [item for item in rules if item != rule]
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return True
