import copy
import json
import subprocess
import sys

import pytest

from backend.app.application.services.feedback_validation import parse_observations
from backend.app.application.services.jev_advisor import JevAdvisor
from backend.app.application.services.pipeline_quality_service import (
    PipelineQualityService,
)


def response(verdict="fulfilled"):
    choices = ["fulfilled", "partial", "not_fulfilled", "insufficient_evidence"]
    return {
        "model": "test-double-not-a-real-Jev-call",
        "answers": {
            "fulfillment": {
                "type": "choice",
                "choice": verdict,
                "probabilities": {x: int(x == verdict) for x in choices},
                "confidence": 0.8,
            }
        },
        "usage": {"cost": 0},
    }


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    (root / "probe.py").write_text("print('not yet implemented')\n")
    for args in (
        ["init", "-q"],
        ["add", "."],
        [
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "baseline",
        ],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    calls = []

    def transport(payload):
        calls.append(payload)
        return response()

    service = PipelineQualityService(
        database_path=tmp_path / "ledger.sqlite",
        allowed_roots=[tmp_path],
        advisor=JevAdvisor(enabled=True, transport=transport),
    )
    original = {
        "id": "parent",
        "comment": "PRIVATE_BUSINESS_NAME needs save and reload",
        "context_metadata": {
            "environment": "local",
            "traceId": "trace",
            "frameIndex": 0,
        },
        "has_image": True,
    }
    items = [
        original,
        {"id": "frame-2", "context_metadata": {"traceId": "trace", "frameIndex": 1}},
        {
            "id": "note",
            "audio_transcript": "PRIVATE_AUDIO_TRANSCRIPT",
            "context_metadata": {"parentFeedbackId": "parent"},
            "has_audio": True,
        },
    ]
    request = service.capture_feedback(workspace=root, source_app="app", items=items)[0]
    contract = {
        "project_id": "app",
        "environment": "local",
        "criteria": [
            {
                "id": "persist",
                "description": "Save persists after reload",
                "check_ids": ["probe"],
                "feedback_item_id": "parent",
            }
        ],
        "checks": [{"id": "probe", "argv": [sys.executable, "-B", "probe.py"]}],
    }
    packet = service.register(
        workspace=root,
        work_item_id="feedback",
        contract=contract,
        links={"stage_id": "stage"},
    )
    plan = {
        "request_digest": request["request_digest"],
        "packet_id": packet["id"],
        "semantic_brief": "Saved item must remain visible after reload",
        "scope": "local",
        "observations": [
            {
                "id": "save",
                "criterion_id": "persist",
                "check_id": "probe",
                "description": "Saved record exists",
            },
            {
                "id": "reload",
                "criterion_id": "persist",
                "check_id": "probe",
                "description": "Record remains visible after reload",
            },
        ],
    }
    return service, root, request, packet, plan, calls, items, contract


def probe(root, observations=None, target_before=None, target_after=None):
    data = {
        "observations": observations
        if observations is not None
        else {"save": True, "reload": True}
    }
    if target_before is not None:
        data.update(target_before=target_before, target_after=target_after)
    # Simulated test facts, transported through a real child process. No product browser is exercised here.
    (root / "probe.py").write_text(
        "print(" + repr("NIENFOS_OBSERVATIONS_V1 " + json.dumps(data)) + ")\n"
    )


def test_capture_groups_trace_and_notes_without_duplicate_improvements(setup):
    s, root, request, packet, plan, calls, items, _ = setup
    assert len(s.feedback_requests(root)) == 1
    assert request["item_ids"] == ["parent", "frame-2", "note"]
    assert (
        s.capture_feedback(workspace=root, source_app="app", items=items)[0] == request
    )
    changed = copy.deepcopy(items)
    changed[0]["comment"] = "Another request"
    with pytest.raises(ValueError, match="immutable"):
        s.capture_feedback(workspace=root, source_app="app", items=changed)
    assert "PRIVATE_BUSINESS_NAME" in s.reviewer_context(str(root))
    assert "acceptance_plan_missing" in s.repair_context(str(root))
    assert calls == []


def test_complete_flow_is_cached_and_originals_do_not_go_to_model(setup):
    s, root, request, packet, plan, calls, items, _ = setup
    s.bind_feedback_plan(request["id"], plan)
    probe(root)
    result = s.execute(packet["id"], attempt_key="complete")
    assert result["feedback_validation"][0]["verified"]
    s.feedback_verdict(request["id"], evaluate=True)
    assert len(calls) == 1
    assert "PRIVATE_" not in json.dumps(calls)
    assert "output_excerpt" not in json.dumps(calls)
    assert "audio_transcript" not in json.dumps(calls)
    resolution = s.feedback_resolution(
        source_app="app", workspace=str(root), item_ids=[x["id"] for x in items]
    )
    assert resolution["validation_summary"] == {
        "total": 1,
        "fulfilled": 1,
        "pending": 0,
    }
    assert s.stage_gate(str(root), "stage")["verified"]
    assert s.gestion_payload(packet["id"], "canonical-project")["observation"][
        "verified"
    ]
    projected = s.export()["work_items"]
    assert len(projected) == 1 and projected[0]["packet_id"] == packet["id"]
    assert projected[0]["verified"]
    s.close(packet["id"])


def test_passing_exit_code_without_observations_cannot_close(setup):
    s, root, request, packet, plan, calls, _, _ = setup
    s.bind_feedback_plan(request["id"], plan)
    result = s.execute(packet["id"], attempt_key="no-facts")
    assert result["quality"][
        "verified"
    ]  # Technical command passed, acceptance did not.
    assert not result["feedback_validation"][0]["verified"]
    assert calls == []
    with pytest.raises(ValueError):
        s.close(packet["id"])
    assert not s.stage_gate(str(root), "stage")["verified"]
    assert not s.gestion_payload(packet["id"], "canonical-project")["observation"][
        "verified"
    ]
    assert not s.export()["work_items"][0]["verified"]


def test_failed_process_cannot_be_overruled_by_positive_observations(setup):
    s, root, request, packet, plan, calls, _, _ = setup
    s.bind_feedback_plan(request["id"], plan)
    probe(root)
    script = root / "probe.py"
    script.write_text(script.read_text() + "raise SystemExit(1)\n")
    verdict = s.execute(packet["id"], attempt_key="failed-process")[
        "feedback_validation"
    ][0]
    assert not verdict["verified"] and calls == []


def test_rebinding_plan_moves_index_and_does_not_close_previous_packet(setup):
    s, root, request, packet, plan, _, _, contract = setup
    s.bind_feedback_plan(request["id"], plan)
    replacement = s.register(
        workspace=root, work_item_id="replacement", contract=contract
    )
    s.bind_feedback_plan(request["id"], {**plan, "packet_id": replacement["id"]})
    assert s._list("feedback_plan", packet["id"]) == []
    assert len(s._list("feedback_plan", replacement["id"])) == 1
    probe(root)
    assert s.execute(replacement["id"], attempt_key="replacement")[
        "feedback_validation"
    ][0]["verified"]
    s.execute(packet["id"], attempt_key="previous")
    with pytest.raises(ValueError):
        s.close(packet["id"])


@pytest.mark.parametrize(
    "facts,expected",
    [
        ({"save": True, "reload": False}, "partial"),
        ({"save": False, "reload": False}, "not_fulfilled"),
        ({"save": True}, "insufficient_evidence"),
    ],
)
def test_negative_or_missing_facts_cannot_be_overridden_by_model(
    setup, facts, expected
):
    s, root, request, packet, plan, calls, _, _ = setup
    s.bind_feedback_plan(request["id"], plan)
    probe(root, facts)
    result = s.execute(packet["id"], attempt_key="facts")
    assert result["feedback_validation"][0]["verdict"] == expected
    assert not result["feedback_validation"][0]["verified"]
    assert calls == []


def test_source_and_contract_changes_invalidate_semantic_verdict(setup):
    s, root, request, packet, plan, calls, _, contract = setup
    s.bind_feedback_plan(request["id"], plan)
    probe(root)
    s.execute(packet["id"], attempt_key="first")
    (root / "new-config").write_text("changed")
    assert not s.feedback_verdict(request["id"])["verified"]
    assert len(calls) == 1
    s.execute(packet["id"], attempt_key="second")
    assert len(calls) == 2
    contract["criteria"][0]["description"] = "Changed expectation"
    s.register(workspace=root, work_item_id="feedback", contract=contract)
    assert s.feedback_verdict(request["id"])["blockers"] == [
        "contract_changed_revise_plan"
    ]


def test_source_edit_during_model_call_cannot_validate_old_evidence(setup):
    s, root, request, packet, plan, _, _, _ = setup

    def concurrent_edit(_):
        (root / "edited-during-assessment").write_text("new code")
        return response()

    s._advisor = JevAdvisor(enabled=True, transport=concurrent_edit)
    s.bind_feedback_plan(request["id"], plan)
    probe(root)
    verdict = s.execute(packet["id"], attempt_key="race")["feedback_validation"][0]
    assert not verdict["verified"]
    assert "evaluation_inputs_changed" in verdict["blockers"]


def test_api_never_accepts_client_verdicts_and_get_does_not_call_model(setup):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app.api.quality_routes import router
    from backend.app.api.routes import get_container

    s, root, request, packet, plan, calls, _, _ = setup
    app = FastAPI()
    app.include_router(router)
    settings = SimpleNamespace(bridge_environment="dev")
    app.dependency_overrides[get_container] = lambda: SimpleNamespace(
        settings=settings,
        pipeline_quality_service=s,
    )
    client = TestClient(app)
    endpoint = "/pipeline-quality/feedback/" + request["id"]
    assert (
        client.put(endpoint + "/plan", json={**plan, "verified": True}).status_code
        == 422
    )
    assert client.put(endpoint + "/plan", json=plan).status_code == 200
    assert client.get(endpoint).json()["verified"] is False and calls == []
    probe(root)
    assert (
        client.post(
            f"/pipeline-quality/packets/{packet['id']}/execute",
            json={"attempt_key": "api"},
        ).status_code
        == 200
    )
    assert client.get(endpoint).json()["verified"] and len(calls) == 1
    assert client.post(endpoint + "/evaluate").json()["verified"] and len(calls) == 1
    settings.bridge_environment = "prod"
    assert client.post(endpoint + "/evaluate").status_code == 403
    assert client.get(endpoint).status_code == 403


@pytest.mark.parametrize(
    "verdict", ["partial", "not_fulfilled", "insufficient_evidence"]
)
def test_semantic_disagreement_returns_to_repair(setup, verdict):
    s, root, request, packet, plan, _, _, _ = setup
    s._advisor = JevAdvisor(enabled=True, transport=lambda _: response(verdict))
    s.bind_feedback_plan(request["id"], plan)
    probe(root)
    result = s.execute(packet["id"], attempt_key="semantic")
    assert result["feedback_validation"][0]["verdict"] == verdict
    assert verdict in s.repair_context(str(root))
    with pytest.raises(ValueError):
        s.close(packet["id"])


def test_disabled_or_failed_model_is_pending_not_success(setup):
    s, root, request, packet, plan, _, _, _ = setup
    s._advisor = JevAdvisor(enabled=False)
    s.bind_feedback_plan(request["id"], plan)
    probe(root)
    s.execute(packet["id"], attempt_key="disabled")
    assert s.feedback_verdict(request["id"])["verdict"] == "insufficient_evidence"
    s._advisor = JevAdvisor(enabled=True, transport=lambda _: {})
    result = s.feedback_verdict(request["id"], evaluate=True)
    assert result["advice"]["status"] == "fallback" and not result["verified"]


def test_deployed_target_must_match_before_and_after(setup):
    s, root, request, packet, plan, calls, _, contract = setup
    request["environment"] = "dev"
    s._put(
        "feedback_request", request
    )  # Fixture setup only; no API can overwrite requests.
    contract["environment"] = "dev"
    s.register(
        workspace=root,
        work_item_id="feedback",
        contract=contract,
        links={"stage_id": "stage"},
    )
    with pytest.raises(ValueError):
        s.bind_feedback_plan(request["id"], plan)
    target = {
        "environment": "dev",
        "origin": "https://dev.example.invalid",
        "release_id": "build-B",
    }
    plan.update(scope="deployed", target=target)
    s.bind_feedback_plan(request["id"], plan)
    probe(root, target_before=target, target_after={**target, "release_id": "build-A"})
    failed = s.execute(packet["id"], attempt_key="wrong-version")[
        "feedback_validation"
    ][0]
    assert not failed["verified"] and calls == []
    probe(root, target_before=target, target_after=target)
    assert s.execute(packet["id"], attempt_key="right-version")["feedback_validation"][
        0
    ]["verified"]


def test_plan_cannot_omit_linked_criteria_or_rebind_request(setup):
    s, root, request, packet, plan, _, _, contract = setup
    bad = copy.deepcopy(plan)
    bad["request_digest"] = "a" * 64
    with pytest.raises(ValueError):
        s.bind_feedback_plan(request["id"], bad)
    contract["criteria"].append(
        {
            "id": "another",
            "description": "Also needed",
            "check_ids": ["probe"],
            "feedback_item_id": "parent",
        }
    )
    s.register(workspace=root, work_item_id="feedback", contract=contract)
    with pytest.raises(ValueError):
        s.bind_feedback_plan(request["id"], plan)


@pytest.mark.parametrize(
    "text",
    [
        'NIENFOS_OBSERVATIONS_V1 {"observations":{"save":"true"}}',
        "NIENFOS_OBSERVATIONS_V1 []",
        'NIENFOS_OBSERVATIONS_V1 {"observations":{"save":true},"raw_body":"private"}',
    ],
)
def test_malformed_observations_are_not_proof(text):
    assert parse_observations(text) is None
