import copy
import json
import subprocess
import sys
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.app.api.quality_routes import router
from backend.app.api.routes import get_container
from backend.app.application.services.jev_advisor import JevAdvisor
from backend.app.application.services.pipeline_quality_service import (
    PipelineQualityService,
)


@pytest.fixture
def lab(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    (root / "app.py").write_text("def select(state): return ['A', 'B']\n")
    (root / "probe.py").write_text(
        "import json, sys\nfrom app import select\n"
        "facts = {'filter': select('active') == ['A'], 'empty': select('missing') == []}\n"
        "print('NIENFOS_OBSERVATIONS_V1 ' + json.dumps({'observations': facts}))\n"
        "sys.exit(0 if all(facts.values()) else 1)\n"
    )
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

    def model(payload):
        calls.append(payload)
        return {
            "model": "test-double",
            "answers": {
                "fulfillment": {
                    "type": "choice",
                    "choice": "fulfilled",
                    "probabilities": {
                        "fulfilled": 1,
                        "partial": 0,
                        "not_fulfilled": 0,
                        "insufficient_evidence": 0,
                    },
                }
            },
        }

    s = PipelineQualityService(
        database_path=tmp_path / "quality.sqlite",
        allowed_roots=[root],
        advisor=JevAdvisor(enabled=True, transport=model),
    )
    definition = {
        "requirement_id": "REQ-FILTER-1",
        "project_id": "app",
        "environment": "local",
        "source_ref": "spec:REQ-FILTER-1",
        "text": "PRIVATE_ORIGINAL: filtrar por estado y no incluir otros estados; vacío cuando no hay coincidencias",
        "criteria": [
            {
                "id": "filter",
                "description": "Only rows matching the requested state are returned",
            },
            {"id": "empty", "description": "No matching state returns an empty list"},
        ],
    }
    req = s.register_requirement(workspace=root, definition=definition)
    contract = {
        "project_id": "app",
        "environment": "local",
        "criteria": [
            {**c, "check_ids": ["probe"], "feedback_item_id": req["feedback_item_id"]}
            for c in definition["criteria"]
        ],
        "checks": [{"id": "probe", "argv": [sys.executable, "-B", "probe.py"]}],
    }
    packet = s.register(
        workspace=root,
        work_item_id="implement-filter",
        contract=contract,
        links={"stage_id": "stage"},
    )
    plan = {
        "packet_id": packet["id"],
        "request_digest": req["request_digest"],
        "scope": "local",
        "semantic_brief": "Filter by state, exclude other states, return empty when no matches exist",
        "observations": [
            {
                "id": c["id"],
                "criterion_id": c["id"],
                "check_id": "probe",
                "description": c["description"],
            }
            for c in definition["criteria"]
        ],
    }
    return s, root, definition, req, contract, packet, plan, calls


def test_new_requirement_failure_repair_and_review_share_existing_ledger(lab):
    s, root, definition, req, contract, packet, plan, calls = lab
    assert req["origin"] == "requirement" and not req["originals"][0]["has_image"]
    assert "expected_criteria" in s.reviewer_context(str(root))
    assert not s.stage_gate(str(root), "stage")["verified"]
    s.bind_feedback_plan(req["id"], plan)
    first = s.execute(packet["id"], attempt_key="before")
    assert first["feedback_validation"][0]["verdict"] == "not_fulfilled"
    assert calls == []  # Neither failed logs nor the original requirement went to Jev.
    (root / "app.py").write_text(
        "def select(state): return [name for name, kind in [('A', 'active'), ('B', 'inactive')] if kind == state]\n"
    )
    after = s.execute(packet["id"], attempt_key="after")
    assert after["feedback_validation"][0]["verified"]
    assert len(calls) == 1 and "PRIVATE_ORIGINAL" not in json.dumps(calls)
    assert len(s.export()["work_items"]) == 1
    assert s.stage_gate(str(root), "stage")["verified"]
    s.close(packet["id"])


def test_original_requirement_is_immutable_and_deduplicated(lab):
    s, root, definition, req, *_ = lab
    assert s.register_requirement(workspace=root, definition=definition) == req
    changed = {**definition, "text": "Less demanding requirement"}
    with pytest.raises(ValueError, match="immutable"):
        s.register_requirement(workspace=root, definition=changed)
    assert len(s.requirements(root)) == 1


@pytest.mark.parametrize("mutation", ["omit", "weaken"])
def test_plan_cannot_rewrite_original_acceptance_to_fit_implementation(lab, mutation):
    s, root, definition, req, contract, packet, plan, calls = lab
    altered = copy.deepcopy(contract)
    if mutation == "omit":
        altered["criteria"].pop()
        plan["observations"].pop()
    else:
        altered["criteria"][0]["description"] = "The app starts"
    s.register(workspace=root, work_item_id="implement-filter", contract=altered)
    with pytest.raises(ValueError, match="preserve all original"):
        s.bind_feedback_plan(req["id"], plan)
    assert not s.feedback_verdict(req["id"])["verified"] and calls == []


def test_requirement_api_requires_explicit_criteria_and_denies_prod(lab):
    s, root, definition, req, contract, packet, plan, calls = lab
    app = FastAPI()
    app.include_router(router)
    settings = SimpleNamespace(bridge_environment="dev")
    app.dependency_overrides[get_container] = lambda: SimpleNamespace(
        settings=settings, pipeline_quality_service=s
    )
    client = TestClient(app)
    body = {**definition, "workspace": str(root)}
    assert (
        client.post("/pipeline-quality/requirements", json=body).json()["id"]
        == req["id"]
    )
    assert (
        client.post(
            "/pipeline-quality/requirements", json={**body, "criteria": []}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/pipeline-quality/requirements",
            json={**body, "criteria": definition["criteria"] * 2},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/pipeline-quality/requirements", json={**body, "verified": True}
        ).status_code
        == 422
    )
    assert (
        len(
            client.get(
                "/pipeline-quality/requirements", params={"workspace": str(root)}
            ).json()
        )
        == 1
    )
    endpoint = "/pipeline-quality/requests/" + req["id"]
    assert client.put(endpoint + "/plan", json=plan).status_code == 200
    assert client.get(endpoint).json()["origin"] == "requirement"
    assert not client.post(endpoint + "/evaluate").json()["verified"] and calls == []
    settings.bridge_environment = "prod"
    assert client.post("/pipeline-quality/requirements", json=body).status_code == 403
    assert client.get(endpoint).status_code == 403
