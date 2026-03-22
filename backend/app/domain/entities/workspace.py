from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Workspace:
    name: str
    path: str
