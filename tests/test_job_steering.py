import io
import json
import shlex
import sys
import threading
import time
from pathlib import Path

from backend.app.domain.entities.job import JobStatus
from backend.app.infrastructure.execution.local_provider import LocalExecutionProvider


class _FakeProcess:
    def __init__(self):
        self.stdin = io.StringIO()

    def poll(self):
        return None


def _provider():
    fixture = Path(__file__).parent / "fixtures" / "fake_claude.py"
    return LocalExecutionProvider(
        command="unused-codex",
        claude_command=f"{shlex.quote(sys.executable)} {shlex.quote(str(fixture))}",
    )


def _running_job(provider, job_id="job-1"):
    provider._set_state(job_id, status=JobStatus.RUNNING, phase="Reasoning")
    process = _FakeProcess()
    provider._processes[job_id] = process
    return process


def _handle(provider, payload):
    return provider._handle_app_server_payload(
        "job-1",
        payload,
        response_buffer_ref=lambda: "",
        set_response_buffer=lambda value: None,
        set_final_response=lambda value: None,
        mark_turn_completed=lambda: None,
        final_agent_message_item_ids=set(),
        non_final_agent_message_item_ids=set(),
    )


def _steer_in_background(provider, text):
    outcome = {}
    worker = threading.Thread(
        target=lambda: outcome.setdefault("value", provider.steer_job("job-1", text))
    )
    worker.start()
    return worker, outcome


def _wait_for_steer_request(process):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        lines = process.stdin.getvalue().strip().splitlines()
        if lines:
            return json.loads(lines[-1])
        time.sleep(0.01)
    raise AssertionError("turn/steer was not sent")


def test_steer_sends_turn_steer_for_the_active_turn_and_records_it():
    provider = _provider()
    process = _running_job(provider)
    _handle(provider, {"method": "turn/started", "params": {"threadId": "th-1", "turn": {"id": "turn-9"}}})

    worker, outcome = _steer_in_background(provider, "  usá pytest -q  ")
    sent = _wait_for_steer_request(process)
    assert sent["method"] == "turn/steer"
    assert sent["params"] == {
        "threadId": "th-1",
        "expectedTurnId": "turn-9",
        "input": [{"type": "text", "text": "usá pytest -q"}],
    }
    # Only the app-server acknowledgement makes the instruction delivered.
    _handle(provider, {"id": sent["id"], "result": {"turnId": "turn-9"}})
    worker.join(5)
    assert outcome["value"] is True
    steer = [a for a in provider.get_snapshot("job-1").activities if a["kind"] == "steer"]
    assert steer and steer[0]["title"] == "usá pytest -q"


def test_rejected_turn_steer_is_not_reported_as_delivered():
    provider = _provider()
    process = _running_job(provider)
    _handle(provider, {"method": "turn/started", "params": {"threadId": "th-1", "turn": {"id": "turn-9"}}})

    worker, outcome = _steer_in_background(provider, "cambiá de enfoque")
    sent = _wait_for_steer_request(process)
    _handle(provider, {"id": sent["id"], "error": {"message": "no active turn"}})
    worker.join(5)
    assert outcome["value"] is False
    assert not [a for a in provider.get_snapshot("job-1").activities if a["kind"] == "steer"]


def test_completed_codex_turn_no_longer_accepts_steering():
    provider = _provider()
    _running_job(provider)
    _handle(provider, {"method": "turn/started", "params": {"threadId": "th-1", "turn": {"id": "turn-9"}}})
    _handle(provider, {"method": "turn/completed", "params": {"threadId": "th-1", "turn": {"id": "turn-9"}}})
    assert provider.steer_job("job-1", "tarde") is False


def test_steer_is_refused_without_an_active_app_server_turn():
    provider = _provider()
    _running_job(provider)
    assert provider.steer_job("job-1", "hola") is False
    assert provider.steer_job("missing", "hola") is False


def test_token_usage_accumulates_per_turn_as_a_usage_activity():
    provider = _provider()
    _running_job(provider)
    for last in ({"inputTokens": 1000, "cachedInputTokens": 0, "outputTokens": 50,
                  "reasoningOutputTokens": 10, "totalTokens": 1060},
                 {"inputTokens": 1500, "cachedInputTokens": 900, "outputTokens": 80,
                  "reasoningOutputTokens": 0, "totalTokens": 1580}):
        provider._record_token_usage(
            "job-1", {"threadId": "t", "turnId": "u", "tokenUsage": {"last": last, "total": last}}
        )
    usage = [a for a in provider.get_snapshot("job-1").activities if a["kind"] == "usage"]
    assert len(usage) == 1
    assert usage[0]["title"] == "2.5k entrada · 130 salida (10 razonamiento)"
