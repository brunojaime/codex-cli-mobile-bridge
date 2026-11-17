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
if "COMPACT_FIXTURE" in text:
    print(json.dumps({"type": "system", "subtype": "compact_boundary", "session_id": session_id,
                      "compact_metadata": {"trigger": "manual", "pre_tokens": 22000, "post_tokens": 5800}}), flush=True)
    print(json.dumps({"type": "user", "session_id": session_id,
                      "message": {"role": "user", "content": "This session is being continued..."}}), flush=True)
    print(json.dumps({"type": "result", "session_id": session_id, "is_error": False, "result": ""}), flush=True)
    sys.exit(0)
control_answers = []
if "PERMISSION_FIXTURE" in text:
    for request_id, request in (
        ("req-bash", {"subtype": "can_use_tool", "tool_name": "Bash",
                      "input": {"command": "rm -rf build"}, "description": "Clean build",
                      "permission_suggestions": [{"type": "addRules", "behavior": "allow",
                                                  "rules": [{"toolName": "Bash", "ruleContent": "rm -rf build"}],
                                                  "destination": "localSettings"}]}),
        ("req-question", {"subtype": "can_use_tool", "tool_name": "AskUserQuestion",
                          "input": {"questions": [{"question": "Color?", "header": "Color", "multiSelect": False,
                                                   "options": [{"label": "Rojo"}, {"label": "Azul"}]}]}}),
    ):
        print(json.dumps({"type": "control_request", "request_id": request_id, "request": request}), flush=True)
        control_answers.append(json.loads(sys.stdin.readline()))
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
                "result": json.dumps({"argv": sys.argv[1:], "payload": payload, "control": control_answers}),
            }
        ),
        flush=True,
    )
