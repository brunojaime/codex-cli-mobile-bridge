"""Subagents the user can launch from the front, like `@agent` in the CLI."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

BUILTIN = [
    {"name": "general-purpose", "description": "Investiga y resuelve tareas de varios pasos por su cuenta.", "source": "builtin"},
    {"name": "Explore", "description": "Busca en el código y te trae solo la conclusión (solo lectura).", "source": "builtin"},
    {"name": "Plan", "description": "Diseña un plan de implementación sin tocar archivos.", "source": "builtin"},
]

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def _parse(path: Path, source: str) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")[:8000]
    except OSError:
        return None
    meta: dict[str, str] = {}
    match = _FRONTMATTER.match(text)
    if match:
        for line in match.group(1).splitlines():
            key, sep, value = line.partition(":")
            if sep and not line.startswith((" ", "\t")):
                meta[key.strip()] = value.strip().strip("'\"")
    name = meta.get("name") or path.stem
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", name):
        return None
    return {"name": name, "description": meta.get("description", "")[:300], "source": source}


def catalog(workspace: str | None, *, home: Path | None = None) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {item["name"]: dict(item) for item in BUILTIN}
    roots = [((home or Path.home()) / ".claude" / "agents", "user")]
    if workspace:
        roots.append((Path(workspace) / ".claude" / "agents", "project"))
    for root, source in roots:  # project definitions override user ones
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.md")):
            item = _parse(path, source)
            if item:
                found[item["name"]] = item
    order = {"project": 0, "user": 1, "builtin": 2}
    return sorted(found.values(), key=lambda item: (order[item["source"]], item["name"].lower()))
