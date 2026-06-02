from __future__ import annotations

import json
import sys
import uuid


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] != "exec":
        print("expected exec command", file=sys.stderr)
        return 1

    prompt = args[-1]
    thread_id = f"thread-{uuid.uuid4()}"
    response = f"json-only:{prompt}"

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
