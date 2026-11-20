"""Steering protocol fixture (stream-json input); never used by a running bridge.

Mirrors what Claude Code 2.1 does with --replay-user-messages, measured with the
real CLI: a message sent mid-turn is echoed with its uuid when Claude takes it
at the next pause between tools; one sent while the final answer is being
written is answered after the first result, in the same process.
"""

import json
import sys

session_id = "steer-session"


def emit(obj):
    print(json.dumps({"session_id": session_id, **obj}), flush=True)


def text_of(payload):
    return payload["message"]["content"][0]["text"]


def replay(payload):
    emit({"type": "user", "uuid": payload.get("uuid"), "message": payload["message"]})


first = json.loads(sys.stdin.readline())
emit({"type": "system", "subtype": "init"})
replay(first)
emit({"type": "assistant", "message": {"id": "m1", "content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "sleep"}}]}})
steer = json.loads(sys.stdin.readline())
if "LATE" in text_of(first):
    # The instruction arrived while the final answer was being written.
    emit({"type": "result", "is_error": False, "result": "primera respuesta", "num_turns": 2,
          "usage": {"input_tokens": 10, "output_tokens": 5}})
    replay(steer)
    emit({"type": "result", "is_error": False, "result": "continuación: " + text_of(steer), "num_turns": 1,
          "usage": {"input_tokens": 7, "output_tokens": 3}})
else:
    replay(steer)
    emit({"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}})
    emit({"type": "result", "is_error": False, "result": "tomé en cuenta: " + text_of(steer), "num_turns": 3})
for line in sys.stdin:
    extra = json.loads(line)
    replay(extra)
    emit({"type": "result", "is_error": False, "result": "extra: " + text_of(extra)})
