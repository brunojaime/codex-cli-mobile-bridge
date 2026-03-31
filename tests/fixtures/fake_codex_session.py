from __future__ import annotations

import json
import re
import sys
import time
import uuid
from pathlib import Path


_SLEEP_PREFIX = re.compile(r"^sleep:(\d+(?:\.\d+)?):(.*)$", re.DOTALL)
_WRAPPED_USER_FAIL_PREFIX = "You are the primary builder Codex.\n\nUser request:\nfail:"


def _maybe_supervisor_response(prompt: str) -> str | None:
    if 'Available specialist ids:' not in prompt:
        return None
    if 'Latest specialist report agent_id: qa' in prompt:
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
        return json.dumps(
            {
                "status": "continue",
                "plan": [
                    "Review implementation strategy",
                    "Validate with QA",
                    "Close the run with supervisor sign-off",
                ],
                "next_agent_id": "qa",
                "instruction": "Validate the implementation and report regressions or missing tests.",
                "user_response": "Senior engineering review is complete. QA is next.",
                "request_summary": True,
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
            "next_agent_id": "senior_engineer",
            "instruction": "Review the implementation strategy and report technical risks back to the supervisor.",
            "user_response": "The plan is set. Senior engineering review is next.",
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
