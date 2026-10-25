from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from types import SimpleNamespace
import json
from pathlib import Path
import subprocess
import sys

from test_requirement_validation import lab as lab
from backend.app.api.quality_routes import router
from backend.app.api.routes import get_container


def repair(lab):
    s, root, definition, req, contract, packet, plan, calls = lab
    s.bind_feedback_plan(req["id"], plan)
    (root / "app.py").write_text(
        "def select(state): return ['A'] if state == 'active' else []\n"
    )
    s.execute(packet["id"], attempt_key="fixed")
    return s.feedback_verdict(req["id"])


def review(evidence, outcome="confirmed"):
    return {
        "evidence_key": evidence["evidence_key"],
        "outcome": outcome,
        "note": "Repetición manual del caso de prueba",
        "decision_ref": "chat:operator-test",
        "actor_label": "Operador de prueba",
    }


def test_chat_source_preserves_text_and_cannot_be_rewritten_by_definition(lab):
    s, root, definition, *_ = lab
    context = s.chat_intake_context(
        workspace=root, source_ref="chat:one", text="Pedido original sin reescritura"
    )
    source = s.requirement_sources(root)[0]
    assert source["id"] in context and "requirement-from-source" in context
    assert "Do not register questions" in context
    payload = {k: v for k, v in definition.items() if k not in {"source_ref", "text"}}
    payload["requirement_id"] = "FROM-CHAT"
    with pytest.raises(ValueError):
        s.requirement_from_source(source["id"], {**payload, "text": "Modified"})
    req = s.requirement_from_source(source["id"], payload)
    assert req["originals"][0]["comment"] == "Pedido original sin reescritura"
    assert req["source_ref"] == "chat:one"
    assert s.requirement_from_source(source["id"], payload)["id"] == req["id"]
    s.chat_intake_context(
        workspace=root, source_ref="chat:one", text="Pedido original sin reescritura"
    )
    assert len(s.requirement_sources(root)) == 1
    with pytest.raises(ValueError):
        s.chat_intake_context(workspace=root, source_ref="chat:one", text="Changed")
    assert (
        len(s.export()["work_items"]) == 1
    )  # The source and unbound intake are not phantom packets.


def test_long_chat_source_is_not_silently_truncated(lab):
    s, root, *_ = lab
    text = s.chat_intake_context(
        workspace=root, source_ref="chat:long", text="x" * 10001
    )
    assert "exceeds" in text and s.requirement_sources(root) == []


def test_chat_intake_remains_available_while_runner_holds_workspace(lab):
    s, root, *_ = lab
    with s._workspace_lock(root):
        assert s.chat_intake_context(
            workspace=root, source_ref="chat:during-test", text="Nueva indicación"
        )
    assert len(s.requirement_sources(root)) == 1


def test_operator_cli_uses_same_original_source_and_ledger(lab, tmp_path):
    s, root, definition, *_ = lab
    s.chat_intake_context(
        workspace=root, source_ref="chat:cli", text="Original desde el teléfono"
    )
    source = s.requirement_sources(root)[0]
    payload = {k: v for k, v in definition.items() if k not in {"text", "source_ref"}}
    payload["requirement_id"] = "CLI-SOURCE"
    file = tmp_path / "criteria.json"
    file.write_text(json.dumps(payload))
    script = Path(__file__).resolve().parents[1] / "scripts/pipeline_quality.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--database",
            str(s.database_path),
            "--projects-root",
            str(root),
            "requirement-from-source",
            source["id"],
            "--file",
            str(file),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    created = json.loads(result.stdout)
    assert created["originals"][0]["comment"] == "Original desde el teléfono"
    assert len(s.requirements(root)) == 2


def test_revision_retires_only_old_scope_and_cannot_reuse_old_proof(lab):
    s, root, definition, req, contract, packet, plan, _ = lab
    repair(lab)
    new_definition = {
        **definition,
        "requirement_id": "REQ-FILTER-2",
        "text": "New explicitly requested scope",
    }
    decision = {
        "definition": new_definition,
        "reason": "Cambio de alcance pedido por el usuario",
        "decision_ref": "chat:revision",
    }
    result = s.revise_requirement(req["id"], decision)
    assert s.revise_requirement(req["id"], decision) == result
    assert s.feedback_verdict(req["id"])["lifecycle"] == "superseded"
    assert not s.feedback_verdict(result["replacement_id"])["verified"]
    assert not s.stage_gate(str(root), "stage")["verified"]
    assert s._get("packet", packet["id"])["lifecycle"] == "superseded"
    with pytest.raises(ValueError):
        s.bind_feedback_plan(req["id"], plan)
    with pytest.raises(ValueError):
        s.revise_requirement(
            result["replacement_id"], {**decision, "definition": definition}
        )
    replacement = s._get("feedback_request", result["replacement_id"])
    for criterion in contract["criteria"]:
        criterion["feedback_item_id"] = replacement["feedback_item_id"]
    p = s.register(
        workspace=root,
        work_item_id="revised-filter",
        contract=contract,
        links={"stage_id": "stage"},
    )
    s.bind_feedback_plan(
        replacement["id"],
        {**plan, "packet_id": p["id"], "request_digest": replacement["request_digest"]},
    )
    s.execute(p["id"], attempt_key="new-scope")
    assert s.stage_gate(str(root), "stage")["verified"]


def test_revision_rejects_cross_project_without_partial_records(lab):
    s, root, definition, req, *_ = lab
    with pytest.raises(ValueError):
        s.revise_requirement(
            req["id"],
            {
                "definition": {
                    **definition,
                    "project_id": "other",
                    "requirement_id": "NEW",
                },
                "reason": "change",
                "decision_ref": "chat:x",
            },
        )
    assert len(s.requirements(root)) == 1 and not s.request_replacement(req["id"])


def test_manual_confirmation_is_evidence_bound_and_reopened_on_failure(lab):
    s, root, definition, req, contract, packet, plan, _ = lab
    evidence = repair(lab)
    assert evidence["human_review"]["status"] == "pending_retest"
    s.record_manual_review(req["id"], review(evidence))
    assert s.feedback_verdict(req["id"])["human_review"]["status"] == "confirmed"
    s.close(packet["id"])
    s.record_manual_review(req["id"], review(evidence, "still_failing"))
    assert s._get("packet", packet["id"])["lifecycle"] == "active"
    verdict = s.feedback_verdict(req["id"])
    assert verdict["technical_verified"] and not verdict["verified"]
    assert "human_retest_required" in verdict["blockers"]
    assert not s.gestion_payload(packet["id"], "canonical")["observation"]["verified"]
    with pytest.raises(ValueError):
        s.close(packet["id"])
    s.record_manual_review(req["id"], review(evidence, "inconclusive"))
    assert not s.feedback_verdict(req["id"])["verified"]
    (root / "app.py").write_text(
        (root / "app.py").read_text() + "# repair after manual report\n"
    )
    with pytest.raises(ValueError, match="does not match"):
        s.record_manual_review(req["id"], review(evidence))
    s.execute(packet["id"], attempt_key="after-manual-failure")
    current = s.feedback_verdict(req["id"])
    assert current["technical_verified"] and not current["verified"]
    s.record_manual_review(req["id"], review(current))
    assert s.feedback_verdict(req["id"])["verified"]


def test_manual_confirm_cannot_replace_failed_tests(lab):
    s, root, definition, req, contract, packet, plan, _ = lab
    s.bind_feedback_plan(req["id"], plan)
    s.execute(packet["id"], attempt_key="failing")
    with pytest.raises(ValueError, match="cannot replace"):
        s.record_manual_review(req["id"], review(s.feedback_verdict(req["id"])))


def test_manual_failure_blocks_dependent_work_even_if_its_own_checks_pass(lab):
    s, root, definition, req, contract, packet, plan, _ = lab
    evidence = repair(lab)
    dependent = s.register(
        workspace=root,
        work_item_id="dependent",
        contract={
            "project_id": "app",
            "environment": "local",
            "dependencies": [packet["id"]],
            "criteria": [
                {
                    "id": "ready",
                    "description": "Required prerequisite is accepted",
                    "check_ids": ["ready"],
                }
            ],
            "checks": [
                {"id": "ready", "argv": [sys.executable, "-B", "-c", "print('ready')"]}
            ],
        },
    )
    assert s.execute(dependent["id"], attempt_key="ready")["quality"]["verified"]
    s.record_manual_review(req["id"], review(evidence, "still_failing"))
    assert not s.status(dependent["id"])["verified"]
    with pytest.raises(ValueError):
        s.close(dependent["id"])
    assert (
        s.acceptance_history(req["id"])["manual_reviews"][-1]["outcome"]
        == "still_failing"
    )


def test_manual_deployed_retest_requires_matching_release(lab):
    s, root, definition, req, contract, packet, plan, _ = lab
    req["environment"] = "dev"
    s._put("feedback_request", req)  # Fixture setup, not an exposed mutation API.
    contract["environment"] = "dev"
    s.register(workspace=root, work_item_id="implement-filter", contract=contract)
    target = {
        "environment": "dev",
        "origin": "https://dev.example.invalid",
        "release_id": "build-B",
    }
    plan.update(scope="deployed", target=target)
    probe = root / "probe.py"
    probe.write_text(
        probe.read_text().replace(
            "json.dumps({'observations': facts})",
            "json.dumps({'observations': facts, 'target_before': "
            + repr(target)
            + ", 'target_after': "
            + repr(target)
            + "})",
        )
    )
    evidence = repair(lab)
    assert evidence["technical_verified"]
    with pytest.raises(ValueError, match="same environment"):
        s.record_manual_review(req["id"], review(evidence))
    with pytest.raises(ValueError, match="same environment"):
        s.record_manual_review(
            req["id"],
            {
                **review(evidence),
                "observed_target": {**target, "release_id": "build-A"},
            },
        )
    s.record_manual_review(req["id"], {**review(evidence), "observed_target": target})
    assert s.feedback_verdict(req["id"])["human_review"]["status"] == "confirmed"


def test_new_workflow_endpoints_respect_dev_and_current_evidence(lab):
    s, root, definition, req, contract, packet, plan, _ = lab
    app = FastAPI()
    app.include_router(router)
    settings = SimpleNamespace(bridge_environment="dev")
    app.dependency_overrides[get_container] = lambda: SimpleNamespace(
        settings=settings, pipeline_quality_service=s
    )
    client = TestClient(app)
    s.chat_intake_context(workspace=root, source_ref="chat:api", text="API source")
    source = client.get(
        "/pipeline-quality/sources", params={"workspace": str(root)}
    ).json()[0]
    body = {k: v for k, v in definition.items() if k not in {"text", "source_ref"}}
    body["requirement_id"] = "API-SOURCE"
    assert (
        client.post(
            f"/pipeline-quality/sources/{source['id']}/requirements", json=body
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/pipeline-quality/sources/{source['id']}/requirements",
            json={**body, "text": "fake"},
        ).status_code
        == 422
    )
    evidence = repair(lab)
    endpoint = f"/pipeline-quality/requests/{req['id']}/manual-review"
    assert client.post(endpoint, json=review(evidence)).status_code == 200
    settings.bridge_environment = "prod"
    assert client.post(endpoint, json=review(evidence)).status_code == 403
    assert (
        client.get(
            "/pipeline-quality/sources", params={"workspace": str(root)}
        ).status_code
        == 403
    )
