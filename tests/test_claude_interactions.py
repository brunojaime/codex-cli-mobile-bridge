import json
import time

import pytest

from backend.app.domain.entities.job import JobStatus
from tests.test_claude_bridge import provider, wait


def _wait_for_waiting(p, job, activity_id):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        snapshot = p.get_snapshot(job)
        item = next((a for a in snapshot.activities if a["id"] == activity_id), None)
        if item is not None and item["status"] == "waiting":
            return snapshot, item
        time.sleep(0.01)
    pytest.fail(f"{activity_id} never waited")


def test_permission_and_question_round_trip():
    p = provider()
    job = p.execute("PERMISSION_FIXTURE", model="claude:sonnet")

    snapshot, item = _wait_for_waiting(p, job, "interaction-req-bash")
    assert snapshot.phase == "Waiting for you"
    assert item["kind"] == "permission"
    data = json.loads(item["interaction"])
    assert data["tool_name"] == "Bash" and data["suggestions"]
    assert "$ rm -rf build" in item["detail"]
    with pytest.raises(ValueError):
        p.respond_interaction(job, "req-bash", {"action": "bogus"})
    assert p.respond_interaction(job, "req-bash", {"action": "allow_always"})
    assert not p.respond_interaction(job, "req-bash", {"action": "allow"})

    _, question = _wait_for_waiting(p, job, "interaction-req-question")
    assert question["kind"] == "question" and question["title"] == "Color?"
    assert p.respond_interaction(job, "req-question", {"action": "allow", "answers": {"Color?": "Azul"}})

    result = wait(p, job)
    assert result.status == JobStatus.COMPLETED
    argv = json.loads(result.response)["argv"]
    assert argv[argv.index("--permission-prompt-tool") + 1] == "stdio"
    bash, answer = json.loads(result.response)["control"]
    assert bash["response"]["request_id"] == "req-bash"
    assert bash["response"]["response"]["updatedPermissions"][0]["type"] == "addRules"
    assert answer["response"]["response"]["updatedInput"]["answers"] == {"Color?": "Azul"}
    resolved = {a["id"]: a for a in result.activities}
    assert resolved["interaction-req-bash"]["resolution"] == "Permitido (no volver a preguntar)"
    assert resolved["interaction-req-question"]["resolution"] == "Respondiste: Azul"


def test_deny_sends_message_and_cancel_unblocks():
    p = provider()
    job = p.execute("PERMISSION_FIXTURE", model="claude:sonnet")
    _wait_for_waiting(p, job, "interaction-req-bash")
    assert p.respond_interaction(job, "req-bash", {"action": "deny", "message": "usá git clean"})
    _wait_for_waiting(p, job, "interaction-req-question")
    assert p.cancel_job(job)
    assert wait(p, job).status == JobStatus.CANCELLED
    assert not p.respond_interaction(job, "req-question", {"action": "deny"})


def test_plan_approval_sets_mode():
    from backend.app.infrastructure.execution.claude_interactions import build_response

    request = {"tool_name": "ExitPlanMode", "input": {"plan": "1. x"}}
    payload, label, status = build_response(request, {"action": "allow", "mode": "acceptEdits"})
    assert payload["updatedPermissions"] == [{"type": "setMode", "mode": "acceptEdits", "destination": "session"}]
    assert status == "completed" and "ediciones automáticas" in label
    payload, label, status = build_response(request, {"action": "deny", "message": "agregá tests"})
    assert payload == {"behavior": "deny", "message": "agregá tests"} and status == "failed"


def test_slash_commands_reach_the_cli_verbatim():
    from backend.app.infrastructure.execution.local_provider import (
        _message_with_mobile_file_context as wrap,
    )

    assert wrap("/compact") == "/compact"
    assert wrap("  /cost ") == "/cost"
    assert wrap("/compact\nmás texto").startswith("Mobile client context")
    assert wrap("hola").startswith("Mobile client context")


def test_compaction_with_string_content_completes_with_summary():
    p = provider()
    result = wait(p, p.execute("COMPACT_FIXTURE", model="claude:sonnet"))
    assert result.status == JobStatus.COMPLETED
    assert result.response == "Conversación compactada: 22.0k → 5.8k tokens de contexto."
