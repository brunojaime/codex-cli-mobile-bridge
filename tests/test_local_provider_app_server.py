import pytest

from backend.app.domain.entities.codex_options import CodexRunOptions
from backend.app.domain.entities.job import JobStatus
from backend.app.infrastructure.execution.local_provider import (
    _AppServerRequiredMcpAuthError,
    LocalExecutionProvider,
)


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


def test_optional_google_calendar_mcp_auth_failure_records_warning() -> None:
    provider = LocalExecutionProvider(command="codex")
    payload = _google_calendar_auth_failure_payload()

    handled = provider._handle_app_server_payload(
        "job-1",
        payload,
        response_buffer_ref=lambda: "",
        set_response_buffer=lambda _value: None,
        set_final_response=lambda _value: None,
        mark_turn_completed=lambda: None,
        final_agent_message_item_ids=set(),
        non_final_agent_message_item_ids=set(),
        required_mcp_server_ids=set(),
    )

    snapshot = provider.get_snapshot("job-1")
    assert handled is False
    assert snapshot.status == JobStatus.RUNNING
    assert snapshot.phase == "Running tools"
    assert snapshot.latest_activity is not None
    assert "tool_unavailable/auth_required" in snapshot.latest_activity
    assert "optional MCP `ludmilo` requires authentication" in snapshot.latest_activity
    assert "rmcp::transport::worker" not in snapshot.latest_activity


def test_required_google_calendar_mcp_auth_failure_is_actionable_blocker() -> None:
    provider = LocalExecutionProvider(command="codex")
    payload = _google_calendar_auth_failure_payload()

    with pytest.raises(_AppServerRequiredMcpAuthError) as exc_info:
        provider._handle_app_server_payload(
            "job-1",
            payload,
            response_buffer_ref=lambda: "",
            set_response_buffer=lambda _value: None,
            set_final_response=lambda _value: None,
            mark_turn_completed=lambda: None,
            final_agent_message_item_ids=set(),
            non_final_agent_message_item_ids=set(),
            required_mcp_server_ids={"ludmilo"},
        )

    message = str(exc_info.value)
    assert "google_calendar_auth_required" in message
    assert "authenticate or disable that required integration" in message
    assert "rmcp::transport::worker" not in message
    assert "Transport channel closed" not in message


def _google_calendar_auth_failure_payload() -> dict[str, object]:
    return {
        "method": "codex/event/mcp_startup_update",
        "params": {
            "msg": {
                "server": "ludmilo",
                "status": {
                    "state": "failed",
                    "error": (
                        "rmcp::transport::worker: worker quit with fatal: "
                        "Transport channel closed, when "
                        "AuthRequired(AuthRequiredError { "
                        'www_authenticate_header: "Bearer '
                        "resource_metadata=\\"
                        "https://google-calendar-mcp-worker.nienfos.workers.dev/"
                        ".well-known/oauth-protected-resource\\\", "
                        'error=\\"missing_bearer_token\\"" })'
                    ),
                },
            }
        },
    }
