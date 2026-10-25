"""Backend-owned routing; legacy model hints cannot select another provider."""
from dataclasses import dataclass
from typing import Literal

from backend.app.domain.engine import is_claude_model


@dataclass(frozen=True)
class AiRuntimePolicy:
    provider: Literal["auto", "codex", "claude"] = "auto"
    model: str | None = None
    effort: str = "medium"

    def __post_init__(self):
        if self.provider not in {"auto", "codex", "claude"}:
            raise ValueError("Unknown AI provider")
        if self.model and self.provider != "auto":
            if is_claude_model(self.model) != (self.provider == "claude"):
                raise ValueError("AI_MODEL does not belong to AI_PROVIDER")
        if self.effort not in {"low", "medium", "high", "xhigh", "max"}:
            raise ValueError("Unsupported AI effort")

    def resolve_model(self, requested: str | None = None) -> str | None:
        if self.provider == "auto":
            return requested or self.model
        if self.model:
            return self.model
        if self.provider == "claude":
            return "claude-opus-5-5"
        return requested if not is_claude_model(requested) else None

    @property
    def engine(self) -> str:
        return "claude" if is_claude_model(self.resolve_model()) else "codex"
