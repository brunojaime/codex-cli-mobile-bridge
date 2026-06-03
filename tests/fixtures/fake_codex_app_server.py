from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
import uuid


STATE_FILE = Path(tempfile.gettempdir()) / "fake_codex_app_server_threads.json"


def _load_threads() -> dict[str, dict[str, object]]:
    if not STATE_FILE.exists():
        return {}
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    threads = payload.get("threads")
    return threads if isinstance(threads, dict) else {}


def _save_threads(threads: dict[str, dict[str, object]]) -> None:
    STATE_FILE.write_text(
        json.dumps({"threads": threads}),
        encoding="utf-8",
    )


def _thread_payload(thread_id: str, turn_count: int) -> dict[str, object]:
    return {
        "id": thread_id,
        "preview": "",
        "ephemeral": False,
        "modelProvider": "openai",
        "createdAt": 0,
        "updatedAt": 0,
        "status": {"type": "idle"},
        "path": f"/tmp/{thread_id}.jsonl",
        "cwd": str(Path.cwd()),
        "cliVersion": "fake",
        "source": "vscode",
        "agentNickname": None,
        "agentRole": None,
        "gitInfo": None,
        "name": None,
        "turns": [
            {
                "id": f"turn-{index}",
                "items": [],
                "status": "completed",
                "error": None,
            }
            for index in range(turn_count)
        ],
    }


def _print(payload: dict[str, object]) -> None:
    print(json.dumps(payload), flush=True)


def _turn_response(turn_number: int, prompt: str) -> str:
    return f"turn {turn_number}: {prompt}"


def main() -> int:
    threads = _load_threads()

    for raw_line in iter(input, ""):
        line = raw_line.strip()
        if not line:
            continue

        payload = json.loads(line)
        method = payload.get("method")
        request_id = payload.get("id")

        if method == "initialize":
            _print(
                {
                    "id": request_id,
                    "result": {
                        "userAgent": "fake-codex-app-server/0.1",
                    },
                }
            )
            continue

        if method == "initialized":
            continue

        if method == "thread/start":
            thread_id = f"thread-{uuid.uuid4()}"
            threads[thread_id] = {"turn_count": 0}
            _save_threads(threads)
            _print(
                {
                    "id": request_id,
                    "result": {
                        "thread": _thread_payload(thread_id, 0),
                        "model": "gpt-5.4",
                        "modelProvider": "openai",
                        "cwd": str(Path.cwd()),
                        "approvalPolicy": "never",
                        "sandbox": {"type": "danger-full-access"},
                        "reasoningEffort": "high",
                    },
                }
            )
            continue

        if method == "thread/resume":
            params = payload.get("params") or {}
            thread_id = params.get("threadId")
            if not isinstance(thread_id, str) or thread_id not in threads:
                _print(
                    {
                        "id": request_id,
                        "error": {
                            "code": -32600,
                            "message": f"thread not found: {thread_id}",
                        },
                    }
                )
                continue

            turn_count = int(threads[thread_id].get("turn_count", 0))
            _print(
                {
                    "id": request_id,
                    "result": {
                        "thread": _thread_payload(thread_id, turn_count),
                        "model": "gpt-5.4",
                        "modelProvider": "openai",
                        "cwd": str(Path.cwd()),
                        "approvalPolicy": "never",
                        "sandbox": {"type": "danger-full-access"},
                        "reasoningEffort": "high",
                    },
                }
            )
            continue

        if method == "turn/start":
            params = payload.get("params") or {}
            thread_id = params.get("threadId")
            if not isinstance(thread_id, str) or thread_id not in threads:
                _print(
                    {
                        "id": request_id,
                        "error": {
                            "code": -32600,
                            "message": f"thread not found: {thread_id}",
                        },
                    }
                )
                continue

            input_items = params.get("input") or []
            prompt = ""
            if (
                isinstance(input_items, list)
                and input_items
                and isinstance(input_items[0], dict)
            ):
                prompt = str(input_items[0].get("text") or "")

            turn_count = int(threads[thread_id].get("turn_count", 0)) + 1
            threads[thread_id]["turn_count"] = turn_count
            _save_threads(threads)
            turn_id = f"turn-{turn_count}-{uuid.uuid4()}"
            item_id = f"msg-{uuid.uuid4()}"
            response_text = _turn_response(turn_count, prompt)

            _print(
                {
                    "id": request_id,
                    "result": {
                        "turn": {
                            "id": turn_id,
                            "items": [],
                            "status": "inProgress",
                            "error": None,
                        }
                    },
                }
            )
            _print(
                {
                    "method": "turn/started",
                    "params": {
                        "threadId": thread_id,
                        "turn": {
                            "id": turn_id,
                            "items": [],
                            "status": "inProgress",
                            "error": None,
                        },
                    },
                }
            )
            _print(
                {
                    "method": "item/started",
                    "params": {
                        "item": {
                            "type": "agentMessage",
                            "id": item_id,
                            "text": "",
                            "phase": "final_answer",
                        },
                        "threadId": thread_id,
                        "turnId": turn_id,
                    },
                }
            )

            if os.environ.get("FAKE_CODEX_TOOL_AND_REASONING_EVENTS", "").strip():
                reasoning_item_id = f"reasoning-{uuid.uuid4()}"
                commentary_item_id = f"commentary-{uuid.uuid4()}"
                tool_item_id = f"tool-{uuid.uuid4()}"
                _print(
                    {
                        "method": "item/started",
                        "params": {
                            "item": {
                                "type": "reasoning",
                                "id": reasoning_item_id,
                                "summary": [],
                                "content": [],
                            },
                            "threadId": thread_id,
                            "turnId": turn_id,
                        },
                    }
                )
                _print(
                    {
                        "method": "item/reasoning/textDelta",
                        "params": {
                            "threadId": thread_id,
                            "turnId": turn_id,
                            "itemId": reasoning_item_id,
                            "delta": "internal reasoning should not stream as response",
                            "contentIndex": 0,
                        },
                    }
                )
                _print(
                    {
                        "method": "item/completed",
                        "params": {
                            "item": {
                                "type": "reasoning",
                                "id": reasoning_item_id,
                                "summary": ["considered tools"],
                                "content": ["internal reasoning"],
                            },
                            "threadId": thread_id,
                            "turnId": turn_id,
                        },
                    }
                )
                _print(
                    {
                        "method": "item/started",
                        "params": {
                            "item": {
                                "type": "mcpToolCall",
                                "id": tool_item_id,
                                "server": "project-catalog",
                                "tool": "list_projects",
                                "status": "inProgress",
                                "arguments": {},
                                "pluginId": None,
                                "result": None,
                                "error": None,
                                "durationMs": None,
                            },
                            "threadId": thread_id,
                            "turnId": turn_id,
                        },
                    }
                )
                _print(
                    {
                        "method": "item/mcpToolCall/progress",
                        "params": {
                            "threadId": thread_id,
                            "turnId": turn_id,
                            "itemId": tool_item_id,
                            "message": "Reading project catalog.",
                        },
                    }
                )
                _print(
                    {
                        "method": "item/completed",
                        "params": {
                            "item": {
                                "type": "mcpToolCall",
                                "id": tool_item_id,
                                "server": "project-catalog",
                                "tool": "list_projects",
                                "status": "completed",
                                "arguments": {},
                                "pluginId": None,
                                "result": {"content": []},
                                "error": None,
                                "durationMs": 12,
                            },
                            "threadId": thread_id,
                            "turnId": turn_id,
                        },
                    }
                )
                _print(
                    {
                        "method": "item/started",
                        "params": {
                            "item": {
                                "type": "agentMessage",
                                "id": commentary_item_id,
                                "text": "",
                                "phase": "commentary",
                            },
                            "threadId": thread_id,
                            "turnId": turn_id,
                        },
                    }
                )
                _print(
                    {
                        "method": "item/agentMessage/delta",
                        "params": {
                            "threadId": thread_id,
                            "turnId": turn_id,
                            "itemId": commentary_item_id,
                            "delta": "call-mcp-tool",
                        },
                    }
                )
                _print(
                    {
                        "method": "item/completed",
                        "params": {
                            "item": {
                                "type": "agentMessage",
                                "id": commentary_item_id,
                                "text": "call-mcp-tool",
                                "phase": "commentary",
                            },
                            "threadId": thread_id,
                            "turnId": turn_id,
                        },
                    }
                )

            midpoint = max(1, len(response_text) // 2)
            use_legacy_delta = os.environ.get("FAKE_CODEX_LEGACY_DELTA", "").strip()
            for chunk in (response_text[:midpoint], response_text[midpoint:]):
                if use_legacy_delta:
                    _print(
                        {
                            "method": "codex/event/agent_message_content_delta",
                            "params": {
                                "id": turn_id,
                                "msg": {
                                    "type": "agent_message_content_delta",
                                    "thread_id": thread_id,
                                    "turn_id": turn_id,
                                    "item_id": item_id,
                                    "delta": chunk,
                                },
                                "conversationId": thread_id,
                            },
                        }
                    )
                else:
                    _print(
                        {
                            "method": "item/agentMessage/delta",
                            "params": {
                                "threadId": thread_id,
                                "turnId": turn_id,
                                "itemId": item_id,
                                "delta": chunk,
                            },
                        }
                    )
                time.sleep(0.05)

            _print(
                {
                    "method": "item/completed",
                    "params": {
                        "item": {
                            "type": "agentMessage",
                            "id": item_id,
                            "text": response_text,
                            "phase": "final_answer",
                        },
                        "threadId": thread_id,
                        "turnId": turn_id,
                    },
                }
            )
            _print(
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": thread_id,
                        "turn": {
                            "id": turn_id,
                            "items": [],
                            "status": "completed",
                            "error": None,
                        },
                    },
                }
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
