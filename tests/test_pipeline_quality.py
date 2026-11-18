from __future__ import annotations

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
from backend.app.application.services.jev_advisor import JevAdvisor, redact
from backend.app.application.services.pipeline_quality_service import (
    PipelineQualityService,
    QualityError,
)


@pytest.fixture
def lab(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    (root / "app.py").write_text("value = 1\n")
    (root / "verify.py").write_text(
        "from app import value\nassert value == 2, 'persisted value mismatch'\n"
    )
    (root / ".gitignore").write_text("__pycache__/\n.env\n")
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
    contract = {
        "version": 1,
        "project_id": "app",
        "environment": "dev",
        "criteria": [
            {
                "id": "save",
                "description": "Value survives read",
                "check_ids": ["persistence"],
                "feedback_item_id": "feedback-1",
            }
        ],
        "checks": [{"id": "persistence", "argv": [sys.executable, "-B", "verify.py"]}],
        "component_ids": ["shared-storage"],
    }
    service = PipelineQualityService(
        database_path=tmp_path / "ledger.sqlite", allowed_roots=[tmp_path]
    )
    packet = service.register(
        workspace=str(root),
        work_item_id="repair-1",
        contract=contract,
        links={"stage_id": "spec-001"},
    )
    return service, root, packet["id"], contract


def repair(root):
    (root / "app.py").write_text("value = 2\n")


def test_real_failure_repair_evidence_lesson_export_and_reuse(lab, tmp_path):
    service, root, id, contract = lab
    assert not service.status(id)["verified"]
    before = service.execute(id, attempt_key="before")
    assert before["quality"]["criteria"][0]["status"] == "failed"
    assert before["diagnosis"]["advice"]["status"] == "disabled"
    repair(root)
    after = service.execute(id, attempt_key="after")
    assert after["quality"]["verified"]
    lesson = service.save_lesson(
        packet_id=id,
        failed_receipt_id=before["receipt_ids"][0],
        passed_receipt_id=after["receipt_ids"][0],
        symptom="Wrong persisted value",
        cause_hypothesis="Value initialized incorrectly",
        resolution="Correct initialization",
        conditions="Same shared storage version and assertion",
    )
    assert lesson["status"] == "verified_repair"
    assert service.stage_gate(str(root), "spec-001")["verified"]
    feedback = service.feedback_resolution(
        source_app="app", workspace=str(root), item_ids=["feedback-1", "feedback-2"]
    )
    assert (
        feedback["verified_count"] == 1 and feedback["status"] == "pending_verification"
    )
    export = service.export()
    assert export["work_items"][0]["verified"]
    assert service.export(after=export["next_cursor"])["events"] == []
    # A fresh service uses durable receipts rather than in-memory state.
    reopened = PipelineQualityService(
        database_path=service.database_path, allowed_roots=[tmp_path]
    )
    assert reopened.status(id)["verified"]
    other = copy.deepcopy(contract)
    other["project_id"] = "another-app"
    second = reopened.register(
        workspace=str(root), work_item_id="second-app", contract=other
    )
    assert reopened.lessons_for(second["id"])[0]["id"] == lesson["id"]


def test_stale_source_cannot_pass_merge_or_feedback(lab):
    service, root, id, _ = lab
    repair(root)
    service.execute(id, attempt_key="passed")
    (root / "app.py").write_text("value = 3\n")
    assert not service.status(id)["verified"]
    assert not service.stage_gate(str(root), "spec-001")["verified"]
    assert (
        service.feedback_resolution(
            source_app="app", workspace=str(root), item_ids=["feedback-1"]
        )["verified_count"]
        == 0
    )


def test_attempt_idempotency_and_revision_conflict(lab):
    service, root, id, _ = lab
    first = service.execute(id, attempt_key="same")
    second = service.execute(id, attempt_key="same")
    assert first["receipt_ids"] == second["receipt_ids"]
    assert service.status(id)["receipt_count"] == 1
    repair(root)
    with pytest.raises(QualityError, match="different revision"):
        service.execute(id, attempt_key="same")


def test_repeated_signature_triggers_diagnostic_change(lab):
    service, _, id, _ = lab
    service.execute(id, attempt_key="one")
    second = service.execute(id, attempt_key="two")
    assert second["diagnosis"]["stalled"]
    assert second["diagnosis"]["next_action"] == "change_diagnostic_or_escalate"


def test_unknown_check_and_arbitrary_result_rejected(lab):
    service, _, id, _ = lab
    with pytest.raises(QualityError, match="registered check"):
        service.execute(id, attempt_key="bad", check_ids=["echo-success"])
    client = api(service)
    response = client.post(
        f"/pipeline-quality/packets/{id}/execute",
        json={"attempt_key": "injected", "exit_code": 0},
    )
    assert response.status_code == 422


def test_contract_change_invalidates_receipts(lab):
    service, root, id, contract = lab
    repair(root)
    service.execute(id, attempt_key="old")
    contract["criteria"][0]["description"] = "Another requirement"
    service.register(workspace=str(root), work_item_id="repair-1", contract=contract)
    assert not service.status(id)["verified"]


def test_missing_mapping_and_decision_do_not_close(lab):
    service, root, _, contract = lab
    contract["criteria"][0]["check_ids"] = []
    contract["criteria"][0]["decision_pending"] = "Which role may write?"
    p = service.register(workspace=str(root), work_item_id="blocked", contract=contract)
    assert not service.status(p["id"])["verified"]
    with pytest.raises(QualityError, match="product decision"):
        service.execute(p["id"], attempt_key="one")


def test_timeout_and_source_mutation_are_not_passing(lab):
    service, root, _, contract = lab
    contract["checks"][0].update(
        argv=[sys.executable, "-c", "import time; time.sleep(10)"], timeout_seconds=1
    )
    p = service.register(workspace=str(root), work_item_id="timeout", contract=contract)
    result = service.execute(p["id"], attempt_key="one")
    assert result["quality"]["current_receipts"][0]["status"] == "timeout"
    contract["checks"][0]["argv"] = [
        sys.executable,
        "-c",
        "from pathlib import Path; Path('app.py').write_text('value=2')",
    ]
    p = service.register(
        workspace=str(root), work_item_id="mutating-check", contract=contract
    )
    result = service.execute(p["id"], attempt_key="one")
    assert not result["quality"]["verified"]
    assert service._list("receipt", p["id"])[0]["status"] == "stale"


def test_attempt_limit_and_lock(lab):
    service, root, _, contract = lab
    contract["max_attempts"] = 1
    p = service.register(workspace=str(root), work_item_id="limited", contract=contract)
    with service._workspace_lock(root):
        with pytest.raises(QualityError, match="Another quality"):
            service.execute(p["id"], attempt_key="locked")
    service.execute(p["id"], attempt_key="one")
    with pytest.raises(QualityError, match="limit"):
        service.execute(p["id"], attempt_key="two")


def test_lessons_require_actual_failed_and_current_pass(lab):
    service, root, id, _ = lab
    failed = service.execute(id, attempt_key="failed")
    with pytest.raises(QualityError, match="failure followed"):
        service.save_lesson(
            packet_id=id,
            failed_receipt_id=failed["receipt_ids"][0],
            passed_receipt_id=failed["receipt_ids"][0],
            symptom="x",
            cause_hypothesis="x",
            resolution="x",
            conditions="x",
        )
    repair(root)
    passed = service.execute(id, attempt_key="pass")
    (root / "app.py").write_text("value=9")
    with pytest.raises(QualityError, match="current source"):
        service.save_lesson(
            packet_id=id,
            failed_receipt_id=failed["receipt_ids"][0],
            passed_receipt_id=passed["receipt_ids"][0],
            symptom="x",
            cause_hypothesis="x",
            resolution="x",
            conditions="x",
        )


def test_dependency_cycle_missing_dependency_and_workspace_escape(lab, tmp_path):
    service, root, id, contract = lab
    with pytest.raises(QualityError, match="outside"):
        service.register(
            workspace=str(tmp_path.parent), work_item_id="escape", contract=contract
        )
    contract["dependencies"] = ["absent"]
    service.register(workspace=str(root), work_item_id="repair-1", contract=contract)
    assert "dependency:absent:not_verified" in service.status(id)["blockers"]
    with pytest.raises(QualityError):
        service.execute(id, attempt_key="blocked")
    contract["checks"][0]["cwd"] = ".."
    with pytest.raises(QualityError, match="inside"):
        service.register(
            workspace=str(root), work_item_id="escape-cwd", contract=contract
        )


def test_jev_advice_is_validated_redacted_and_cannot_change_acceptance(lab):
    service, _, id, _ = lab
    calls = []

    def transport(payload):
        calls.append(payload)
        return {
            "model": "typesafe/jev-fixed",
            "usage": {"cost": 0.0001},
            "answers": {
                "cause": {
                    "type": "choice",
                    "choice": "code",
                    "confidence": 0.9,
                    "probabilities": {
                        key: float(key == "code")
                        for key in payload["questions"]["cause"]["criteria"]
                    },
                },
                "same_cause": {"type": "noul", "noul": 0.9},
            },
        }

    advisor = JevAdvisor(enabled=True, transport=transport)
    result = advisor.advise(
        failure="API_KEY=not-a-real-secret Authorization: Bearer example-credential"
    )
    assert result["status"] == "answered" and result["advisory_only"]
    assert "not-a-real-secret" not in json.dumps(calls)
    service._advisor = advisor
    result = service.execute(id, attempt_key="advised")
    assert result["diagnosis"]["advice"]["status"] == "answered"
    assert not result["quality"]["verified"]


@pytest.mark.parametrize(
    "response",
    [{}, {"answers": {"cause": {"type": "choice", "choice": "execute-shell"}}}],
)
def test_jev_invalid_response_falls_back_and_opens_cooldown(response):
    calls = []

    def transport(payload):
        calls.append(payload)
        return response

    advisor = JevAdvisor(enabled=True, transport=transport)
    assert advisor.advise(failure="error")["status"] == "fallback"
    assert advisor.advise(failure="error")["reason"] == "provider_cooldown"
    assert len(calls) == 1


def api(service, environment="dev"):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_container] = lambda: SimpleNamespace(
        settings=SimpleNamespace(bridge_environment=environment),
        pipeline_quality_service=service,
    )
    return TestClient(app)


def test_api_executes_real_check_and_production_denies_all_operations(lab):
    service, root, id, _ = lab
    client = api(service)
    repair(root)
    response = client.post(
        f"/pipeline-quality/packets/{id}/execute", json={"attempt_key": "http"}
    )
    assert response.status_code == 200 and response.json()["quality"]["verified"]
    assert (
        client.get("/pipeline-quality/export").json()["schema"]
        == "nienfos.pipeline-evidence/v1"
    )
    production = api(service, "prod")
    assert production.get("/pipeline-quality/packets").status_code == 403
    assert (
        production.post(
            f"/pipeline-quality/packets/{id}/execute", json={"attempt_key": "prod"}
        ).status_code
        == 403
    )


def test_redaction():
    assert "abc123" not in redact("password=abc123")
    assert "private content" not in redact(
        "-----BEGIN PRIVATE KEY-----\nprivate content\n-----END PRIVATE KEY-----"
    )


def test_independent_reviewer_omits_generator_story_and_uses_fresh_session(lab):
    from backend.app.application.services.message_service import MessageService
    from backend.app.domain.entities.agent_configuration import AgentId

    quality, root, id, _ = lab
    service = MessageService.__new__(MessageService)
    service._quality_service = quality
    prompt = service._build_reviewer_execution_message(
        reviewer_prompt="Check behavior",
        primary_response="AUTHOR_SAYS_EVERYTHING_IS_FINE",
        workspace_path=str(root),
    )
    assert "AUTHOR_SAYS_EVERYTHING_IS_FINE" not in prompt
    assert '"status": "unverified"' in prompt
    assert (
        service._provider_session_id_for_agent(
            SimpleNamespace(workspace_path=str(root)), AgentId.REVIEWER
        )
        is None
    )
    with pytest.raises(QualityError):
        quality.close(id)
    repair(root)
    quality.execute(id, attempt_key="pass")
    quality.close(id)
    assert quality.reviewer_context(str(root)) is None


def test_feedback_requires_all_mapped_criteria_and_snapshot_sequence_advances(lab):
    service, root, id, contract = lab
    repair(root)
    service.execute(id, attempt_key="first")
    first = service.gestion_payload(id, "canonical-project")
    contract["criteria"].append(
        {
            "id": "another",
            "description": "Additional condition",
            "check_ids": [],
            "feedback_item_id": "feedback-1",
        }
    )
    service.register(workspace=str(root), work_item_id="repair-1", contract=contract)
    service.execute(id, attempt_key="second")
    feedback = service.feedback_resolution(
        source_app="app", item_ids=["feedback-1"], workspace=str(root)
    )
    assert feedback["verified_count"] == 0
    second = service.gestion_payload(id, "canonical-project")
    assert second["sequence"] > first["sequence"]
    assert not second["observation"]["verified"]


def test_observation_sequence_advances_when_source_returns_to_previous_state(lab):
    service, root, id, _ = lab
    repair(root)
    service.execute(id, attempt_key="verified")
    first = service.gestion_payload(id, "canonical-project")
    assert service.gestion_payload(id, "canonical-project") == first
    (root / "app.py").write_text("value = 3\n")
    second = service.gestion_payload(id, "canonical-project")
    repair(root)
    third = service.gestion_payload(id, "canonical-project")
    assert first["observation"] == third["observation"]
    assert first["sequence"] < second["sequence"] < third["sequence"]


def test_runner_interruption_is_recorded_and_never_accepted(lab, monkeypatch):
    service, _, id, _ = lab

    def interrupted(*args):
        raise RuntimeError("simulated runner interruption")

    monkeypatch.setattr(service, "_run_check", interrupted)
    with pytest.raises(RuntimeError):
        service.execute(id, attempt_key="interrupted")
    retry = service.execute(id, attempt_key="interrupted")
    assert retry["status"] == "interrupted"
    assert not service.status(id)["verified"]


def test_scoped_service_lists_only_its_workspace(lab, tmp_path):
    service, root, id, _ = lab
    other = tmp_path / "other"
    other.mkdir()
    assert service.scoped(allowed_roots=[other]).packets() == []
    assert service.scoped(allowed_roots=[root]).packets()[0]["id"] == id


def test_snapshot_byte_budget_fails_closed_without_accepting_old_receipts(
    lab, monkeypatch
):
    service, root, packet_id, _ = lab
    repair(root)
    service.execute(packet_id, attempt_key="passing-before-limit")
    assert service.status(packet_id)["verified"]
    monkeypatch.setattr(service, "SNAPSHOT_MAX_BYTES", 1)
    with pytest.raises(QualityError, match="byte budget"):
        service.snapshot(root)
    state = service.status(packet_id)
    assert state["source"] is None
    assert not state["verified"]
    assert state["current_receipts"] == []
    assert "source_snapshot_unavailable" in state["blockers"]
    assert "source_snapshot_unavailable" in service.reviewer_context(str(root))


def test_snapshot_deadline_bounds_file_hashing(lab, monkeypatch):
    service, root, _, _ = lab
    import backend.app.application.services.pipeline_quality_service as module

    real_run = module.subprocess.run
    clock = [0.0]

    def run(*args, **kwargs):
        result = real_run(*args, **kwargs)
        if "ls-files" in args[0]:
            clock[0] = 3.0
        return result

    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(QualityError, match="time budget"):
        service.snapshot(root)


def test_snapshot_git_timeout_is_a_quality_error(lab, monkeypatch):
    service, root, _, _ = lab

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(QualityError, match="time budget"):
        service.snapshot(root)
