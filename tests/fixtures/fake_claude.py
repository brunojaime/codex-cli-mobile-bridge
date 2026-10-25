"""Protocol fixture; never used by a release or running bridge."""

import json
import sys
import time

payload = json.loads(sys.stdin.readline())
text = payload["message"]["content"][0]["text"]
session_id = (
    sys.argv[sys.argv.index("--resume") + 1]
    if "--resume" in sys.argv
    else "fixture-session"
)
print(
    json.dumps({"type": "system", "subtype": "init", "session_id": session_id}),
    flush=True,
)
if "SLEEP_FIXTURE" in text:
    time.sleep(10)
print(
    json.dumps(
        {
            "type": "assistant",
            "session_id": session_id,
            "message": {"content": [{"type": "tool_use", "name": "Read"}]},
        }
    ),
    flush=True,
)
if "MISSING_RESULT_FIXTURE" not in text:
    print(
        json.dumps(
            {
                "type": "result",
                "session_id": session_id,
                "is_error": "ERROR_FIXTURE" in text,
                "permission_denials": [{"tool_name": "Bash"}]
                if "DENIED_FIXTURE" in text
                else [],
                "result": json.dumps({"argv": sys.argv[1:], "payload": payload}),
            }
        ),
        flush=True,
    )
