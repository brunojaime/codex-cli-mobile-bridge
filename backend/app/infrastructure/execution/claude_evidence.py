"""Verify Claude's reported runtime against the backend request; never trust prompts."""
from __future__ import annotations

from datetime import datetime, timezone
import threading

_lock = threading.Lock()
_latest: dict[str, dict] = {}


class ClaudeRuntimeMismatch(RuntimeError):
    pass


def requested_flag(argv, flag: str) -> str | None:
    """Last occurrence wins, matching the CLI's own parsing of repeated flags."""
    values = [argv[i + 1] for i, item in enumerate(argv[:-1]) if item == flag]
    return values[-1] if values else None


def verify_init(init: dict | None, *, argv, source: str) -> dict:
    """Fail closed when the CLI reports another model or permission mode."""
    if not isinstance(init, dict):
        raise ClaudeRuntimeMismatch("Claude did not report its runtime; execution was not verified.")
    mode = requested_flag(argv, "--permission-mode")
    model = requested_flag(argv, "--model")
    reported_mode = init.get("permissionMode")
    reported_model = init.get("model") or ""
    if mode and reported_mode != mode:
        raise ClaudeRuntimeMismatch(
            f"Claude reported permission mode {reported_mode!r}, expected {mode!r}.")
    # Aliases (sonnet/opus) resolve to dated IDs; only full IDs are compared.
    if model and model.startswith("claude-") and not reported_model.startswith(model):
        raise ClaudeRuntimeMismatch(
            f"Claude reported model {reported_model!r}, expected {model!r}.")
    evidence = {
        "source": source,
        "model": reported_model,
        "permission_mode": reported_mode,
        "cli_version": init.get("claude_code_version"),
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        _latest[source] = evidence
    return evidence


def latest() -> dict[str, dict]:
    with _lock:
        return {key: dict(value) for key, value in _latest.items()}
