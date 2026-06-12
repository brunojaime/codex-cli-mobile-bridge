from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from pathlib import Path


_SLEEP_PREFIX = re.compile(r"^sleep:(\d+(?:\.\d+)?):(.*)$", re.DOTALL)
_WRAPPED_USER_FAIL_PREFIX = "You are the primary builder Codex.\n\nUser request:\nfail:"


def _state_path() -> Path:
    return Path(os.environ.get("HOME", ".")).resolve() / ".codex" / "fake_mcp_state.json"


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


def _maybe_supervisor_response(prompt: str) -> str | None:
    if 'Available specialist ids:' not in prompt:
        return None
    available_specialists = ["qa", "ux", "senior_engineer", "scraper"]
    for line in prompt.splitlines():
        if line.startswith("Available specialist ids:"):
            raw_ids = line.split(":", maxsplit=1)[1]
            available_specialists = [
                candidate.strip()
                for candidate in raw_ids.split(",")
                if candidate.strip()
            ]
            break

    def choose_specialist(*preferred: str) -> str | None:
        for specialist_id in preferred:
            if specialist_id in available_specialists:
                return specialist_id
        if available_specialists:
            return available_specialists[0]
        return None

    if 'Latest specialist report agent_id: qa' in prompt:
        if "senior_engineer" not in available_specialists and prompt.count("QA review:") <= 2:
            return json.dumps(
                {
                    "status": "continue",
                    "plan": [
                        "Review implementation strategy",
                        "Validate with QA",
                        "Close the run with supervisor sign-off",
                    ],
                    "next_agent_id": "qa",
                    "instruction": "Run one more QA pass focused on regressions and missing tests.",
                    "user_response": "QA completed a first pass. One more validation round is next.",
                    "request_summary": True,
                }
            )
        return json.dumps(
            {
                "status": "complete",
                "plan": [
                    "Review implementation strategy",
                    "Validate with QA",
                    "Close the run with supervisor sign-off",
                ],
                "next_agent_id": None,
                "instruction": "",
                "user_response": "QA feedback is in. The run is complete.",
            }
        )
    if 'Latest specialist report agent_id: senior_engineer' in prompt:
        next_agent_id = choose_specialist("qa", "senior_engineer")
        return json.dumps(
            {
                "status": "continue",
                "plan": [
                    "Review implementation strategy",
                    "Validate with QA",
                    "Close the run with supervisor sign-off",
                ],
                "next_agent_id": next_agent_id,
                "instruction": (
                    "Validate the implementation and report regressions or missing tests."
                    if next_agent_id == "qa"
                    else "Review the implementation strategy and report technical risks back to the supervisor."
                ),
                "user_response": (
                    "Senior engineering review is complete. QA is next."
                    if next_agent_id == "qa"
                    else "Senior engineering review is complete. Another specialist pass is next."
                ),
                "request_summary": True,
            }
        )
    next_agent_id = choose_specialist("senior_engineer", "qa", "ux", "scraper")
    if next_agent_id is None:
        return json.dumps(
            {
                "status": "complete",
                "plan": [
                    "Review implementation strategy",
                    "Validate with QA",
                    "Close the run with supervisor sign-off",
                ],
                "next_agent_id": None,
                "instruction": "",
                "user_response": "No specialists are available. The run is complete.",
            }
        )
    return json.dumps(
        {
            "status": "continue",
            "plan": [
                "Review implementation strategy",
                "Validate with QA",
                "Close the run with supervisor sign-off",
            ],
            "next_agent_id": next_agent_id,
            "instruction": (
                "Review the implementation strategy and report technical risks back to the supervisor."
                if next_agent_id == "senior_engineer"
                else "Validate the implementation and report regressions or missing tests."
                if next_agent_id == "qa"
                else "Review the current flow and report any usability issues."
            ),
            "user_response": (
                "The plan is set. Senior engineering review is next."
                if next_agent_id == "senior_engineer"
                else "The plan is set. QA is next."
                if next_agent_id == "qa"
                else "The plan is set. Another specialist review is next."
            ),
        }
    )


def _maybe_specialist_response(prompt: str) -> str | None:
    if 'Assigned specialist id: senior_engineer' in prompt:
        return 'Senior engineering review: architecture looks sound; QA should verify tests.'
    if 'Assigned specialist id: qa' in prompt:
        return 'QA review: no blocking regressions found; test coverage looks acceptable.'
    if 'Assigned specialist id: ux' in prompt:
        return 'UX review: the current flow is acceptable.'
    return None


def main() -> int:
    args = sys.argv[1:]
    fail_get_for = os.environ.get("FAKE_CODEX_FAIL_GET_FOR", "").strip()
    malformed_get_for = os.environ.get("FAKE_CODEX_MALFORMED_GET_FOR", "").strip()
    unsupported_get_for = os.environ.get(
        "FAKE_CODEX_UNSUPPORTED_GET_SHAPE_FOR",
        "",
    ).strip()
    partial_list_error = os.environ.get("FAKE_CODEX_PARTIAL_LIST_ERROR", "").strip()
    sleep_get_for = os.environ.get("FAKE_CODEX_SLEEP_GET_FOR", "").strip()
    sleep_seconds = float(os.environ.get("FAKE_CODEX_SLEEP_SECONDS", "0.2"))
    if not args:
        print("missing command", file=sys.stderr)
        return 1

    command = args[0]
    if args == ["mcp", "list"]:
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
    if command != "exec":
        print("expected exec command", file=sys.stderr)
        return 1

    mode = "new"
    provider_session_id: str | None = None
    index = 1
    if len(args) > 1 and args[1] == "resume":
        mode = "resume"
        index = 2

    output_path: Path | None = None
    prompt: str | None = None
    attached_images: list[Path] = []

    while index < len(args):
        current = args[index]
        if current == "--json":
            index += 1
            continue
        if current == "--skip-git-repo-check":
            index += 1
            continue
        if current == "--dangerously-bypass-approvals-and-sandbox":
            index += 1
            continue
        if current == "--color":
            index += 2
            continue
        if current == "-c":
            index += 2
            continue
        if current == "-o":
            output_path = Path(args[index + 1])
            index += 2
            continue
        if current == "-i":
            index += 1
            while index < len(args) and not args[index].startswith("-"):
                attached_images.append(Path(args[index]))
                index += 1
            continue
        if mode == "resume" and provider_session_id is None:
            provider_session_id = current
            index += 1
            continue

        prompt = current
        index += 1

    if prompt is None:
        print("missing prompt", file=sys.stderr)
        return 1

    if attached_images:
        time.sleep(0.1)
        missing_images = [str(path) for path in attached_images if not path.exists()]
        if missing_images:
            print(f"missing image file(s): {', '.join(missing_images)}", file=sys.stderr)
            return 1

    if prompt.startswith("fail:"):
        print(prompt.split(":", maxsplit=1)[1], file=sys.stderr)
        return 1
    if prompt.startswith(_WRAPPED_USER_FAIL_PREFIX):
        print(prompt[len(_WRAPPED_USER_FAIL_PREFIX):], file=sys.stderr)
        return 1

    sleep_match = _SLEEP_PREFIX.match(prompt)
    if sleep_match is not None:
        time.sleep(float(sleep_match.group(1)))
        prompt = sleep_match.group(2)

    thread_id = provider_session_id or f"thread-{uuid.uuid4()}"
    response = (
        _maybe_supervisor_response(prompt)
        or _maybe_specialist_response(prompt)
        or f"{mode}:{thread_id}:{prompt}"
    )
    if attached_images:
        response = f"{response} [images: {', '.join(path.name for path in attached_images)}]"

    print(json.dumps({"type": "thread.started", "thread_id": thread_id}))
    print(json.dumps({"type": "turn.started"}))
    print(
        json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "item_0", "type": "agent_message", "text": response},
            }
        )
    )
    print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}))

    if output_path is not None:
        output_path.write_text(response, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
