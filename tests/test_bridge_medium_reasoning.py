import pytest
from backend.app.domain.entities.codex_options import CodexRunOptions
from backend.app.infrastructure.execution.local_provider import LocalExecutionProvider

@pytest.mark.parametrize("requested", [None, "low", "high", "xhigh"])
@pytest.mark.parametrize("configured", [None, "high", "medium"])
def test_bridge_always_uses_medium(requested, configured):
    provider = LocalExecutionProvider(command="codex", default_reasoning_effort=configured)
    overrides = ('model="example"',)
    if requested:
        overrides += (f'model_reasoning_effort="{requested}"',)
    options = CodexRunOptions(config_overrides=overrides)
    args = provider._build_codex_args(options)
    assert args == ["-c", 'model="example"', "-c", 'model_reasoning_effort="medium"']
    assert provider._reasoning_effort_for_job(options) == "medium"
    assert provider._build_codex_args(options, include_default_reasoning_effort=False) == ["-c", 'model="example"']
