"""Provider identity without changing existing Codex model identifiers."""


def is_claude_model(model: str | None) -> bool:
    return bool(model and model.startswith(("claude:", "claude-")))


def session_matches_model(session_id: str | None, model: str | None) -> bool:
    return bool(session_id) and session_id.startswith("claude:") == is_claude_model(
        model
    )
