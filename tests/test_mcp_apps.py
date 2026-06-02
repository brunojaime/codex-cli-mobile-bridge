from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from backend.app.infrastructure.mcp_apps import (
    _looks_like_missing_server,
    inspect_repo_mcp_apps,
)


def test_looks_like_missing_server_matches_current_codex_cli_error_text() -> None:
    assert _looks_like_missing_server("Error: No MCP server named 'project-catalog' found.")


def test_inspect_repo_mcp_apps_reports_malformed_preview_spec() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _write_app_spec(
            repo_root,
            module_name="broken_preview",
            payload={
                "app_id": "broken-preview",
                "name": "Broken Preview",
                "description": "Broken preview config",
                "recommended_server_id": "broken-preview",
                "transport": "stdio",
                "command": "python3",
                "args": ["-c", "print('hello')"],
                "env": {},
                "preview_tool": {
                    "name": "",
                    "arguments": [],
                },
            },
        )

        apps = inspect_repo_mcp_apps(
            command=_fake_codex_command(),
            repo_root=repo_root,
            projects_root=str(repo_root),
        )

        assert len(apps) == 1
        assert apps[0].app_id == "broken-preview"
        assert apps[0].install_state == "invalid"
        assert apps[0].validation_error == (
            "Invalid app spec: `preview_tool` requires a non-empty `name` "
            "and object `arguments`."
        )
        assert apps[0].protocol_error is None


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        (
            {
                "app_id": "bad-transport",
                "name": "Bad Transport",
                "description": "Unsupported transport",
                "recommended_server_id": "bad-transport",
                "transport": "http",
                "command": "python3",
                "args": [],
                "env": {},
            },
            "Unsupported transport `http`.",
        ),
        (
            {
                "app_id": "empty-command",
                "name": "Empty Command",
                "description": "Missing command",
                "recommended_server_id": "empty-command",
                "transport": "stdio",
                "command": "   ",
                "args": [],
                "env": {},
            },
            "Invalid app spec: `command` must be a non-empty string for stdio apps.",
        ),
        (
            {
                "app_id": "unknown-placeholder",
                "name": "Unknown Placeholder",
                "description": "Unknown placeholder",
                "recommended_server_id": "unknown-placeholder",
                "transport": "stdio",
                "command": "python3",
                "args": ["{unknown_placeholder}"],
                "env": {},
            },
            "Invalid app spec template: unknown placeholder `{unknown_placeholder}`",
        ),
        (
            {
                "app_id": "bad-format",
                "name": "Bad Format",
                "description": "Bad format string",
                "recommended_server_id": "bad-format",
                "transport": "stdio",
                "command": "python3",
                "args": ["{"],
                "env": {},
            },
            "Invalid app spec template `{`. Single '{' encountered in format string",
        ),
    ],
)
def test_inspect_repo_mcp_apps_reports_basic_spec_validation_errors(
    payload: dict[str, object],
    expected_error: str,
) -> None:
    with TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _write_app_spec(
            repo_root,
            module_name="invalid_app",
            payload=payload,
        )

        apps = inspect_repo_mcp_apps(
            command=_fake_codex_command(),
            repo_root=repo_root,
            projects_root=str(repo_root),
        )

        assert len(apps) == 1
        assert apps[0].install_state == "invalid"
        assert apps[0].validation_error is not None
        assert expected_error in apps[0].validation_error


def test_inspect_repo_mcp_apps_reports_duplicate_server_id_collision() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _write_app_spec(
            repo_root,
            module_name="app_one",
            payload=_basic_app_payload(
                app_id="app-one",
                recommended_server_id="shared-server",
            ),
        )
        _write_app_spec(
            repo_root,
            module_name="app_two",
            payload=_basic_app_payload(
                app_id="app-two",
                recommended_server_id="shared-server",
            ),
        )

        apps = inspect_repo_mcp_apps(
            command=_fake_codex_command(),
            repo_root=repo_root,
            projects_root=str(repo_root),
        )

        assert len(apps) == 2
        assert all(app.install_state == "invalid" for app in apps)
        assert all(app.validation_error is not None for app in apps)
        assert all(
            "Duplicate recommended_server_id `shared-server`" in app.validation_error
            for app in apps
            if app.validation_error is not None
        )


def test_inspect_repo_mcp_apps_reports_duplicate_app_id_collision() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _write_app_spec(
            repo_root,
            module_name="first",
            payload=_basic_app_payload(
                app_id="shared-app",
                recommended_server_id="server-one",
            ),
        )
        _write_app_spec(
            repo_root,
            module_name="second",
            payload=_basic_app_payload(
                app_id="shared-app",
                recommended_server_id="server-two",
            ),
        )

        apps = inspect_repo_mcp_apps(
            command=_fake_codex_command(),
            repo_root=repo_root,
            projects_root=str(repo_root),
        )

        assert len(apps) == 2
        assert all(app.install_state == "invalid" for app in apps)
        assert all(app.validation_error is not None for app in apps)
        assert all(
            "Duplicate app_id `shared-app`" in app.validation_error
            for app in apps
            if app.validation_error is not None
        )


def test_inspect_repo_mcp_apps_reports_matching_installed_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        home_dir = temp_root / "home"
        repo_root = temp_root / "repo"
        monkeypatch.setenv("HOME", str(home_dir))
        server_path = _write_simple_stdio_server(repo_root)
        _write_app_spec(
            repo_root,
            module_name="matching_app",
            payload=_simple_server_payload(
                app_id="matching-app",
                recommended_server_id="matching-app",
                server_path=server_path,
                env={"PROJECTS_ROOT": str(repo_root)},
            ),
        )
        _write_fake_codex_state(
            home_dir,
            {
                "matching-app": {
                    "summary": f"matching-app: uv run python {server_path}",
                    "transport": "stdio",
                    "command": "uv",
                    "args": ["run", "python", str(server_path)],
                    "env": {"PROJECTS_ROOT": str(repo_root)},
                },
            },
        )

        apps = inspect_repo_mcp_apps(
            command=_fake_codex_command(),
            repo_root=repo_root,
            projects_root=str(repo_root),
        )

        assert len(apps) == 1
        app = apps[0]
        assert app.install_state == "matching"
        assert app.installed is True
        assert app.server_present is True
        assert app.server_presence_known is True
        assert app.config_matches is True
        assert app.drift_summary is None


def test_inspect_repo_mcp_apps_reports_matching_but_disabled_stdio_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        home_dir = temp_root / "home"
        repo_root = temp_root / "repo"
        monkeypatch.setenv("HOME", str(home_dir))
        server_path = _write_simple_stdio_server(repo_root)
        _write_app_spec(
            repo_root,
            module_name="disabled_matching_app",
            payload=_simple_server_payload(
                app_id="disabled-matching-app",
                recommended_server_id="disabled-matching-app",
                server_path=server_path,
                env={"PROJECTS_ROOT": str(repo_root)},
            ),
        )
        _write_fake_codex_state(
            home_dir,
            {
                "disabled-matching-app": {
                    "summary": f"disabled-matching-app: uv run python {server_path}",
                    "enabled": False,
                    "disabled_reason": "Authorization: Bearer secret",
                    "transport": "stdio",
                    "command": "uv",
                    "args": ["run", "python", str(server_path)],
                    "env": {"PROJECTS_ROOT": str(repo_root)},
                },
            },
        )

        apps = inspect_repo_mcp_apps(
            command=_fake_codex_command(),
            repo_root=repo_root,
            projects_root=str(repo_root),
        )

        assert len(apps) == 1
        app = apps[0]
        assert app.install_state == "disabled"
        assert app.installed is False
        assert app.server_present is True
        assert app.server_presence_known is True
        assert app.config_matches is True
        assert app.drift_summary is None
        assert app.disabled_reason == "Authorization: [redacted]"
        assert "Bearer secret" not in app.disabled_reason


def test_inspect_repo_mcp_apps_reports_drifted_installed_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        home_dir = temp_root / "home"
        repo_root = temp_root / "repo"
        monkeypatch.setenv("HOME", str(home_dir))
        server_path = _write_simple_stdio_server(repo_root)
        _write_app_spec(
            repo_root,
            module_name="drifted_app",
            payload=_simple_server_payload(
                app_id="drifted-app",
                recommended_server_id="drifted-app",
                server_path=server_path,
                env={"PROJECTS_ROOT": str(repo_root)},
            ),
        )
        _write_fake_codex_state(
            home_dir,
            {
                "drifted-app": {
                    "summary": "drifted-app: uv run python /tmp/server.py",
                    "transport": "stdio",
                    "command": "uv",
                    "args": [
                        "run",
                        "python",
                        "/tmp/server.py",
                    ],
                    "env": {"PROJECTS_ROOT": "/other"},
                },
            },
        )

        apps = inspect_repo_mcp_apps(
            command=_fake_codex_command(),
            repo_root=repo_root,
            projects_root=str(repo_root),
        )

        assert len(apps) == 1
        app = apps[0]
        assert app.install_state == "drifted"
        assert app.installed is False
        assert app.server_present is True
        assert app.server_presence_known is True
        assert app.config_matches is False
        assert app.drift_summary is not None
        assert "command stored as `uv` but repo app expects `uv`" not in app.drift_summary
        assert "args differ" in app.drift_summary
        assert "env differs" in app.drift_summary


def test_inspect_repo_mcp_apps_reports_non_stdio_installed_config_as_drifted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        home_dir = temp_root / "home"
        repo_root = temp_root / "repo"
        monkeypatch.setenv("HOME", str(home_dir))
        server_path = _write_simple_stdio_server(repo_root)
        _write_app_spec(
            repo_root,
            module_name="non_stdio_drifted_app",
            payload=_simple_server_payload(
                app_id="non-stdio-drifted-app",
                recommended_server_id="non-stdio-drifted-app",
                server_path=server_path,
                env={"PROJECTS_ROOT": str(repo_root)},
            ),
        )
        _write_fake_codex_state(
            home_dir,
            {
                "non-stdio-drifted-app": {
                    "summary": "non-stdio-drifted-app: https://mcp.example.test/sse",
                    "transport": "sse",
                    "url": "https://mcp.example.test/sse",
                    "headers": {"Authorization": "Bearer secret"},
                },
            },
        )

        apps = inspect_repo_mcp_apps(
            command=_fake_codex_command(),
            repo_root=repo_root,
            projects_root=str(repo_root),
        )

        assert len(apps) == 1
        app = apps[0]
        assert app.install_state == "drifted"
        assert app.installed is False
        assert app.server_present is True
        assert app.server_presence_known is True
        assert app.config_matches is False
        assert app.drift_summary == (
            "transport stored as `sse` but repo app expects `stdio`"
        )
        assert "Authorization" not in app.drift_summary
        assert "Bearer secret" not in app.drift_summary
        assert "secret" not in app.drift_summary


def test_inspect_repo_mcp_apps_reports_disabled_non_stdio_config_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        home_dir = temp_root / "home"
        repo_root = temp_root / "repo"
        monkeypatch.setenv("HOME", str(home_dir))
        server_path = _write_simple_stdio_server(repo_root)
        _write_app_spec(
            repo_root,
            module_name="disabled_non_stdio_app",
            payload=_simple_server_payload(
                app_id="disabled-non-stdio-app",
                recommended_server_id="disabled-non-stdio-app",
                server_path=server_path,
                env={"PROJECTS_ROOT": str(repo_root)},
            ),
        )
        _write_fake_codex_state(
            home_dir,
            {
                "disabled-non-stdio-app": {
                    "summary": "disabled-non-stdio-app: https://mcp.example.test/sse",
                    "enabled": False,
                    "disabled_reason": '{"Authorization":"Bearer secret"}',
                    "transport": "sse",
                    "url": "https://mcp.example.test/sse",
                    "headers": {"Authorization": "Bearer secret"},
                },
            },
        )

        apps = inspect_repo_mcp_apps(
            command=_fake_codex_command(),
            repo_root=repo_root,
            projects_root=str(repo_root),
        )

        assert len(apps) == 1
        app = apps[0]
        assert app.install_state == "disabled"
        assert app.installed is False
        assert app.server_present is True
        assert app.server_presence_known is True
        assert app.config_matches is False
        assert app.drift_summary == (
            "transport stored as `sse` but repo app expects `stdio`"
        )
        assert app.disabled_reason == '{"Authorization":"[redacted]"}'
        assert "Bearer secret" not in app.disabled_reason
        assert "secret" not in app.disabled_reason


def test_inspect_repo_mcp_apps_reports_lookup_failure_as_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        home_dir = temp_root / "home"
        repo_root = temp_root / "repo"
        monkeypatch.setenv("HOME", str(home_dir))
        monkeypatch.setenv("FAKE_CODEX_FAIL_GET_FOR", "lookup-failure-app")
        server_path = _write_simple_stdio_server(repo_root)
        _write_app_spec(
            repo_root,
            module_name="lookup_failure_app",
            payload=_simple_server_payload(
                app_id="lookup-failure-app",
                recommended_server_id="lookup-failure-app",
                server_path=server_path,
                env={"PROJECTS_ROOT": str(repo_root)},
            ),
        )
        _write_fake_codex_state(
            home_dir,
            {
                "lookup-failure-app": {
                    "summary": f"lookup-failure-app: uv run python {server_path}",
                    "transport": "stdio",
                    "command": "uv",
                    "args": ["run", "python", str(server_path)],
                    "env": {"PROJECTS_ROOT": str(repo_root)},
                },
            },
        )

        apps = inspect_repo_mcp_apps(
            command=_fake_codex_command(),
            repo_root=repo_root,
            projects_root=str(repo_root),
        )

        assert len(apps) == 1
        app = apps[0]
        assert app.install_state == "unreadable"
        assert app.installed is False
        assert app.server_present is False
        assert app.server_presence_known is False
        assert app.config_matches is None
        assert (
            app.lookup_error
            == "`codex mcp get --json` failed while checking the existing server config."
        )
        assert app.drift_summary is None


@pytest.mark.parametrize(
    ("env_key", "app_id", "expected_error"),
    [
        (
            "FAKE_CODEX_MALFORMED_GET_FOR",
            "malformed-get-app",
            "`codex mcp get --json` returned malformed JSON.",
        ),
        (
            "FAKE_CODEX_UNSUPPORTED_GET_SHAPE_FOR",
            "unsupported-get-app",
            "`codex mcp get --json` returned an unsupported payload shape.",
        ),
    ],
)
def test_inspect_repo_mcp_apps_reports_unreadable_get_payloads(
    monkeypatch: pytest.MonkeyPatch,
    env_key: str,
    app_id: str,
    expected_error: str,
) -> None:
    with TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        home_dir = temp_root / "home"
        repo_root = temp_root / "repo"
        monkeypatch.setenv("HOME", str(home_dir))
        monkeypatch.setenv(env_key, app_id)
        server_path = _write_simple_stdio_server(repo_root)
        _write_app_spec(
            repo_root,
            module_name=app_id.replace("-", "_"),
            payload=_simple_server_payload(
                app_id=app_id,
                recommended_server_id=app_id,
                server_path=server_path,
                env={"PROJECTS_ROOT": str(repo_root)},
            ),
        )
        _write_fake_codex_state(
            home_dir,
            {
                app_id: {
                    "summary": f"{app_id}: uv run python {server_path}",
                    "transport": "stdio",
                    "command": "uv",
                    "args": ["run", "python", str(server_path)],
                    "env": {"PROJECTS_ROOT": str(repo_root)},
                },
            },
        )

        apps = inspect_repo_mcp_apps(
            command=_fake_codex_command(),
            repo_root=repo_root,
            projects_root=str(repo_root),
        )

        assert len(apps) == 1
        app = apps[0]
        assert app.install_state == "unreadable"
        assert app.installed is False
        assert app.server_present is True
        assert app.server_presence_known is True
        assert app.config_matches is None
        assert app.lookup_error == expected_error
        assert app.drift_summary is None


def test_inspect_repo_mcp_apps_reports_protocol_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        script_path = repo_root / "hang_server.py"
        script_path.write_text(
            "import time\n"
            "time.sleep(30)\n",
            encoding="utf-8",
        )
        _write_app_spec(
            repo_root,
            module_name="slow_app",
            payload={
                "app_id": "slow-app",
                "name": "Slow App",
                "description": "Slow init",
                "recommended_server_id": "slow-app",
                "transport": "stdio",
                "command": "python3",
                "args": [str(script_path)],
                "env": {},
            },
        )
        monkeypatch.setattr(
            "backend.app.infrastructure.mcp_apps._MCP_APP_STEP_TIMEOUT_SECONDS",
            0.1,
        )
        monkeypatch.setattr(
            "backend.app.infrastructure.mcp_apps._MCP_APP_TOTAL_INSPECTION_TIMEOUT_SECONDS",
            0.3,
        )

        apps = inspect_repo_mcp_apps(
            command=_fake_codex_command(),
            repo_root=repo_root,
            projects_root=str(repo_root),
        )

        assert len(apps) == 1
        assert apps[0].validation_error is None
        assert apps[0].install_state == "protocol-broken"
        assert apps[0].protocol_error is not None
        assert "Timed out" in apps[0].protocol_error


def test_inspect_repo_mcp_apps_formats_protocol_errors_cleanly() -> None:
    with TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        _write_app_spec(
            repo_root,
            module_name="broken_protocol",
            payload={
                "app_id": "broken-protocol",
                "name": "Broken Protocol",
                "description": "Broken server",
                "recommended_server_id": "broken-protocol",
                "transport": "stdio",
                "command": "python3",
                "args": ["-m", "no.such.module"],
                "env": {},
            },
        )

        apps = inspect_repo_mcp_apps(
            command=_fake_codex_command(),
            repo_root=repo_root,
            projects_root=str(repo_root),
        )

        assert len(apps) == 1
        assert apps[0].validation_error is None
        assert apps[0].install_state == "protocol-broken"
        assert apps[0].protocol_error is not None
        assert "no.such.module" in apps[0].protocol_error
        assert "TaskGroup" not in apps[0].protocol_error
        assert "sub-exception" not in apps[0].protocol_error


def _basic_app_payload(
    *,
    app_id: str,
    recommended_server_id: str,
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    return {
        "app_id": app_id,
        "name": app_id,
        "description": "Test app",
        "recommended_server_id": recommended_server_id,
        "transport": "stdio",
        "command": "python3",
        "args": ["-c", "import sys; sys.exit(0)"],
        "env": env or {},
    }


def _simple_server_payload(
    *,
    app_id: str,
    recommended_server_id: str,
    server_path: Path,
    env: dict[str, str],
) -> dict[str, object]:
    return {
        "app_id": app_id,
        "name": app_id,
        "description": "Test app",
        "recommended_server_id": recommended_server_id,
        "transport": "stdio",
        "command": "uv",
        "args": [
            "run",
            "python",
            str(server_path),
        ],
        "env": env,
    }


def _write_app_spec(
    repo_root: Path,
    *,
    module_name: str,
    payload: dict[str, object],
) -> None:
    app_dir = repo_root / "mcp_apps" / module_name
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "app.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_fake_codex_state(
    home_dir: Path,
    servers: dict[str, dict[str, object]],
) -> None:
    state_file = home_dir / ".codex" / "fake_mcp_state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(servers), encoding="utf-8")


def _fake_codex_command() -> str:
    return "python3 tests/fixtures/fake_codex_tooling.py"


def _write_simple_stdio_server(repo_root: Path) -> Path:
    server_path = repo_root / "simple_server.py"
    server_path.parent.mkdir(parents=True, exist_ok=True)
    server_path.write_text(
        "from __future__ import annotations\n"
        "\n"
        "from mcp.server.fastmcp import FastMCP\n"
        "from mcp.types import ToolAnnotations\n"
        "\n"
        "_ANNOTATIONS = ToolAnnotations(\n"
        "    readOnlyHint=True,\n"
        "    destructiveHint=False,\n"
        "    idempotentHint=True,\n"
        "    openWorldHint=False,\n"
        ")\n"
        "\n"
        "mcp = FastMCP('Test App', json_response=True, log_level='WARNING')\n"
        "\n"
        "@mcp.tool(name='ping', annotations=_ANNOTATIONS)\n"
        "def ping() -> dict[str, str]:\n"
        "    return {'ok': 'true'}\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    mcp.run(transport='stdio')\n",
        encoding="utf-8",
    )
    return server_path
