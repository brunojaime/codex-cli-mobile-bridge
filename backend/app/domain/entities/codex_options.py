from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CodexRunOptions:
    profile: str | None = None
    search_enabled: bool = False
    skill_ids: tuple[str, ...] = ()
    mcp_server_ids: tuple[str, ...] = ()
    config_overrides: tuple[str, ...] = ()

    def normalized(self) -> "CodexRunOptions":
        return CodexRunOptions(
            profile=_normalize_optional_text(self.profile),
            search_enabled=self.search_enabled,
            skill_ids=_normalize_string_items(self.skill_ids),
            mcp_server_ids=_normalize_string_items(self.mcp_server_ids),
            config_overrides=_normalize_string_items(self.config_overrides),
        )

    def is_empty(self) -> bool:
        normalized = self.normalized()
        return (
            normalized.profile is None
            and not normalized.search_enabled
            and not normalized.skill_ids
            and not normalized.mcp_server_ids
            and not normalized.config_overrides
        )


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_string_items(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        stripped = value.strip()
        if not stripped or stripped in seen:
            continue
        normalized.append(stripped)
        seen.add(stripped)
    return tuple(normalized)
