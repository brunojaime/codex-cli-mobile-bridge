import hashlib
import json

import httpx
import pytest

from scripts.activate_nightly_recovery import activate, configure_recovery


def test_prod_activation_requires_explicit_restart_authorization(tmp_path):
    assert activate({"environment": "prod"}, tmp_path, tmp_path, tmp_path / "state.json")
    assert json.loads((tmp_path / "state.json").read_text())["state"] == "prepared_requires_prod_restart_authorization"


def test_configuring_recovery_preserves_pause_and_never_creates_missing_procedures():
    updates = []
    def respond(request):
        if request.method == "GET":
            return httpx.Response(200, json={"projects": [
                {"name": "active", "policy": {"enabled": True}},
                {"name": "paused", "policy": {"enabled": False}},
                {"name": "missing", "policy": None}]})
        updates.append(json.loads(request.content))
        return httpx.Response(200, json={})
    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(respond)) as client:
        configured = configure_recovery(client)
    assert [p["enabled"] for p in updates] == [True, False]
    assert all(p["automatic_recovery"] for p in updates)
    assert len(configured) == 2


@pytest.mark.parametrize("condition", ["busy", "changed", "drain_race", "healthy"])
def test_activation_preserves_accepted_work_and_checks_hashes(tmp_path, condition):
    runtime, stage = tmp_path / "runtime", tmp_path / "stage"
    runtime.mkdir(); stage.mkdir()
    (runtime / "module.py").write_text("before" if condition != "changed" else "foreign change")
    (stage / "module.py").write_text("after")
    target = {"environment": "dev", "runtime": str(runtime), "files": {"module.py": {
        "before": hashlib.sha256(b"before").hexdigest(), "after": hashlib.sha256(b"after").hexdigest()}}}
    calls, restarts = [], []
    def respond(request):
        calls.append((request.method, request.url.path))
        if request.url.path == "/maintenance/drain":
            return httpx.Response(200, json={"requested": False, "active_job_count": int(condition == "busy"),
                "active_session_count": 0, "in_flight_message_count": 0,
                "ready_to_restart": condition != "drain_race"})
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/openapi.json":
            return httpx.Response(200, json={"components": {"schemas": {"WorkPolicy": {"properties": {"automatic_recovery": {}}}}}})
        pytest.fail(str(request.url))
    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(respond)) as client:
        done = activate(target, stage, tmp_path / "private", tmp_path / "report.json", client=client,
                        run=lambda argv, **kw: restarts.append(argv))
    if condition == "healthy":
        assert done
        assert (runtime / "module.py").read_text() == "after"
        assert len(restarts) == 1
        assert json.loads((tmp_path / "report.json").read_text())["files_verified"]
    else:
        assert not restarts
        assert (runtime / "module.py").read_text() == ("foreign change" if condition == "changed" else "before")
    if condition in {"busy", "changed"}:
        assert all(method != "POST" for method, _ in calls)
    if condition in {"drain_race", "healthy"}:
        assert calls[-1] == ("POST", "/maintenance/drain")
