from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


def _state_path() -> Path:
    return (
        Path(os.environ.get("HOME", ".")).resolve() / ".codex" / "fake_mcp_state.json"
    )


def _load_servers() -> dict[str, dict[str, object]]:
    base = {
        "github": {
            "summary": "github: GitHub connector available",
            "transport": "stdio",
            "command": "github",
            "args": [],
            "env": {},
        },
        "notion": {
            "summary": "notion: Notion docs",
            "transport": "stdio",
            "command": "notion",
            "args": [],
            "env": {},
        },
    }
    state_file = _state_path()
    if not state_file.exists():
        return base
    try:
        stored = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return base
    if not isinstance(stored, dict):
        return base
    for key, value in stored.items():
        if isinstance(key, str) and isinstance(value, dict):
            base[key] = value
    return base


def _save_servers(servers: dict[str, dict[str, object]]) -> None:
    state_file = _state_path()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(servers), encoding="utf-8")


def _server_payload(server_id: str, server: dict[str, object]) -> dict[str, object]:
    transport_type = server.get("transport", "stdio")
    if transport_type == "stdio":
        transport_payload = {
            "type": "stdio",
            "command": server.get("command"),
            "args": server.get("args", []),
            "env": server.get("env", {}),
            "env_vars": [],
            "cwd": None,
        }
    else:
        transport_payload = {
            "type": transport_type,
            "url": server.get("url"),
            "headers": server.get("headers", {}),
        }
    return {
        "name": server_id,
        "enabled": bool(server.get("enabled", True)),
        "disabled_reason": server.get("disabled_reason"),
        "transport": transport_payload,
        "enabled_tools": None,
        "disabled_tools": None,
        "startup_timeout_sec": None,
        "tool_timeout_sec": None,
    }


def main() -> int:
    args = sys.argv[1:]
    fail_add_for = os.environ.get("FAKE_CODEX_FAIL_ADD_FOR", "").strip()
    fail_add_if_arg_contains = os.environ.get(
        "FAKE_CODEX_FAIL_ADD_IF_ARG_CONTAINS",
        "",
    ).strip()
    fail_get_for = os.environ.get("FAKE_CODEX_FAIL_GET_FOR", "").strip()
    malformed_get_for = os.environ.get("FAKE_CODEX_MALFORMED_GET_FOR", "").strip()
    unsupported_get_for = os.environ.get(
        "FAKE_CODEX_UNSUPPORTED_GET_SHAPE_FOR",
        "",
    ).strip()
    fail_remove_for = os.environ.get("FAKE_CODEX_FAIL_REMOVE_FOR", "").strip()
    partial_list_error = os.environ.get("FAKE_CODEX_PARTIAL_LIST_ERROR", "").strip()
    sleep_get_for = os.environ.get("FAKE_CODEX_SLEEP_GET_FOR", "").strip()
    sleep_add_for = os.environ.get("FAKE_CODEX_SLEEP_ADD_FOR", "").strip()
    sleep_remove_for = os.environ.get("FAKE_CODEX_SLEEP_REMOVE_FOR", "").strip()
    sleep_seconds = float(os.environ.get("FAKE_CODEX_SLEEP_SECONDS", "0.2"))
    if args == ["--version"]:
        print("codex 9.9.9-test")
        return 0
    if args == ["login", "status"]:
        print("Logged in using ChatGPT")
        return 0
    if args == ["mcp", "list"]:
        if os.environ.get("FAKE_CODEX_MCP_LIST_TABLE", "").strip():
            print(
                "Name             Command  Args                                                                                                   Env                  Cwd  Status   Auth       "
            )
        for server in _load_servers().values():
            summary = server.get("summary")
            if isinstance(summary, str):
                print(summary)
        if partial_list_error:
            print(partial_list_error, file=sys.stderr)
            return 2
        return 0
    if len(args) == 4 and args[:2] == ["mcp", "get"] and args[3] == "--json":
        server_id = args[2]
        server = _load_servers().get(server_id)
        if server is None:
            print(f"Unknown MCP server: {server_id}", file=sys.stderr)
            return 1
        if sleep_get_for and server_id == sleep_get_for:
            time.sleep(sleep_seconds)
        if fail_get_for and server_id == fail_get_for:
            print(f"Failed to inspect server: {server_id}", file=sys.stderr)
            return 2
        if malformed_get_for and server_id == malformed_get_for:
            print("{not-json")
            return 0
        if unsupported_get_for and server_id == unsupported_get_for:
            print(
                json.dumps(
                    {
                        "name": server_id,
                        "enabled": True,
                        "disabled_reason": None,
                        "transport": {
                            "command": "uv",
                        },
                    }
                )
            )
            return 0
        print(json.dumps(_server_payload(server_id, server)))
        return 0
    if len(args) >= 4 and args[:2] == ["mcp", "add"]:
        server_id = args[2]
        if "--" not in args:
            print("Missing -- separator", file=sys.stderr)
            return 1
        separator_index = args.index("--")
        flags = args[3:separator_index]
        command_parts = args[separator_index + 1 :]
        if not command_parts:
            print("Missing MCP server command", file=sys.stderr)
            return 1
        if fail_add_for and server_id == fail_add_for:
            print(f"Failed to add server: {server_id}", file=sys.stderr)
            return 1
        if sleep_add_for and server_id == sleep_add_for:
            time.sleep(sleep_seconds)
        if fail_add_if_arg_contains and any(
            fail_add_if_arg_contains in str(part) for part in command_parts
        ):
            print(
                f"Failed to add server because launch args matched `{fail_add_if_arg_contains}`: {server_id}",
                file=sys.stderr,
            )
            return 1
        servers = _load_servers()
        if server_id in servers:
            print(f"Server already exists: {server_id}", file=sys.stderr)
            return 1
        env: dict[str, str] = {}
        index = 0
        while index < len(flags):
            if flags[index] != "--env" or index + 1 >= len(flags):
                print(f"Unsupported args: {flags}", file=sys.stderr)
                return 1
            key, _, value = flags[index + 1].partition("=")
            env[key] = value
            index += 2
        servers[server_id] = {
            "summary": f"{server_id}: {' '.join(command_parts)}",
            "enabled": True,
            "disabled_reason": None,
            "transport": "stdio",
            "command": command_parts[0],
            "args": command_parts[1:],
            "env": env,
        }
        _save_servers(servers)
        print(f"Added MCP server {server_id}")
        return 0
    if len(args) == 3 and args[:2] == ["mcp", "remove"]:
        server_id = args[2]
        servers = _load_servers()
        if server_id not in servers:
            print(f"Unknown MCP server: {server_id}", file=sys.stderr)
            return 1
        if sleep_remove_for and server_id == sleep_remove_for:
            time.sleep(sleep_seconds)
        if fail_remove_for and server_id == fail_remove_for:
            print(f"Failed to remove server: {server_id}", file=sys.stderr)
            return 2
        servers.pop(server_id, None)
        _save_servers(servers)
        print(f"Removed MCP server {server_id}")
        return 0
    if args == [
        "-c",
        'sandbox_mode="danger-full-access"',
        "app-server",
        "--listen",
        "stdio://",
    ]:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            message_id = payload.get("id")
            method = payload.get("method")
            if method == "initialize":
                print(
                    json.dumps(
                        {
                            "id": message_id,
                            "result": {
                                "userAgent": "fake-codex/9.9.9-test",
                                "codexHome": "/tmp/fake-codex-home",
                                "platformFamily": "unix",
                                "platformOs": "linux",
                            },
                        }
                    )
                )
                continue
            if method == "account/rateLimits/read":
                print(
                    json.dumps(
                        {
                            "id": message_id,
                            "result": {
                                "rateLimits": {
                                    "limitId": "codex",
                                    "limitName": None,
                                    "primary": {
                                        "usedPercent": 17,
                                        "windowDurationMins": 300,
                                        "resetsAt": 1779044601,
                                    },
                                    "secondary": {
                                        "usedPercent": 42,
                                        "windowDurationMins": 10080,
                                        "resetsAt": 1779585206,
                                    },
                                    "credits": {
                                        "hasCredits": False,
                                        "unlimited": False,
                                        "balance": "0",
                                    },
                                    "planType": "pro",
                                    "rateLimitReachedType": None,
                                },
                                "rateLimitsByLimitId": None,
                            },
                        }
                    )
                )
                continue
        return 0
    print(f"unsupported args: {args}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
