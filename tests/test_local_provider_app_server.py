from backend.app.domain.entities.codex_options import CodexRunOptions
from backend.app.infrastructure.execution.local_provider import LocalExecutionProvider


def test_app_server_command_configures_process_sandbox_for_danger_full_access() -> None:
    provider = LocalExecutionProvider(
        command="codex",
        exec_args="--skip-git-repo-check --dangerously-bypass-approvals-and-sandbox",
    )

    command = provider._build_app_server_command(codex_options=None)

    assert command[:4] == [
        "codex",
        "-c",
        'sandbox_mode="danger-full-access"',
        "app-server",
    ]


def test_app_server_command_prefers_explicit_sandbox_override() -> None:
    provider = LocalExecutionProvider(
        command="codex",
        exec_args="--skip-git-repo-check --dangerously-bypass-approvals-and-sandbox",
    )

    command = provider._build_app_server_command(
        codex_options=CodexRunOptions(
            config_overrides=('sandbox_mode="read-only"',),
        ),
    )

    assert 'sandbox_mode="danger-full-access"' not in command
    assert command[:4] == [
        "codex",
        "-c",
        'sandbox_mode="read-only"',
        "app-server",
    ]
