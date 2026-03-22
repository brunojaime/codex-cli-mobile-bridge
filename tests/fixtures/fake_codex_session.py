from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("missing command", file=sys.stderr)
        return 1

    command = args[0]
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

    while index < len(args):
        current = args[index]
        if current == "--json":
            index += 1
            continue
        if current == "--skip-git-repo-check":
            index += 1
            continue
        if current == "--color":
            index += 2
            continue
        if current == "-o":
            output_path = Path(args[index + 1])
            index += 2
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

    if prompt.startswith("fail:"):
        print(prompt.split(":", maxsplit=1)[1], file=sys.stderr)
        return 1

    thread_id = provider_session_id or f"thread-{uuid.uuid4()}"
    response = f"{mode}:{thread_id}:{prompt}"

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
