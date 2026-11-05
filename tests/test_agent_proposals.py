from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.app.api.agent_proposal_routes import router, get_container
from backend.app.application.services.agent_proposal_service import (
    AgentProposalService,
    ProposalConflict,
    ProposalDecision,
    ProposalDraft,
    ProposalRevision,
)
from backend.app.domain.entities.agent_configuration import AgentId
from test_generator_reviewer_launch import rig as base_rig


@pytest.fixture
def rig(tmp_path):
    yield from base_rig.__wrapped__(tmp_path)


def draft(rig, **changes):
    return ProposalDraft(
        **{
            "dedupe_key": "connection-recovery",
            "workspace_path": str(rig.workspace),
            "title": "Improve connection recovery",
            "summary": "Preserve the draft across reconnects.",
            "rationale": "Users should not lose their message.",
            "evidence": ["docs/reconnect.md"],
            "generator_prompt": "Implement the approved recovery behavior.",
            "reviewer_prompt": "Check reconnection, duplicates and preservation.",
            "kickoff": "Inspect the flow, implement recovery and test it.",
            "generator_turns": 3,
            "reviewer_turns": 2,
            **changes,
        }
    )


def service_and_draft(rig):
    # The test rig's container shape intentionally matches route dependencies.
    return AgentProposalService(
        rig.messages, rig.db.with_suffix(".proposals.sqlite3")
    ), draft(rig)


def test_create_is_silent_durable_and_deduplicated(rig):
    service, request = service_and_draft(rig)
    assert service.list()["items"] == []
    first = service.create(request)
    assert service.create(request) == first
    assert not rig.provider.requests
    restored = AgentProposalService(rig.messages, service.database)
    assert restored.list()["unread_count"] == 1
    restored.read(first["id"], 1)
    assert restored.list()["unread_count"] == 0
    with pytest.raises(ProposalConflict):
        restored.create(draft(rig, summary="Different scope"))


def test_observations_require_a_new_revision_and_stale_actions_fail(rig):
    service, request = service_and_draft(rig)
    item = service.create(request)
    decision = ProposalDecision(
        revision=1, action="observations", observations="Only one form first."
    )
    assert service.decide(item["id"], decision)["status"] == "needs_revision"
    assert service.decide(item["id"], decision)["status"] == "needs_revision"
    with pytest.raises(ProposalConflict):
        service.decide(item["id"], ProposalDecision(revision=1, action="execute"))
    revised = service.revise(
        item["id"],
        ProposalRevision(
            revision=1,
            proposal=draft(
                rig,
                summary="Preserve only the main form.",
                kickoff="Only the main form.",
            ),
        ),
    )
    assert revised["revision"] == 2 and revised["unread"]
    assert revised["observations"] == decision.observations
    with pytest.raises(ProposalConflict):
        service.read(item["id"], 1)
    assert not rig.provider.requests


def test_rejection_is_final_and_survives_repeated_create(rig):
    service, request = service_and_draft(rig)
    item = service.create(request)
    reject = ProposalDecision(revision=1, action="reject")
    assert service.decide(item["id"], reject)["status"] == "rejected"
    assert service.decide(item["id"], reject)["status"] == "rejected"
    assert service.create(request)["status"] == "rejected"
    with pytest.raises(ProposalConflict):
        service.decide(item["id"], ProposalDecision(revision=1, action="execute"))
    assert not rig.provider.requests


def test_execute_exactly_once_under_concurrent_taps_and_keeps_budget(rig):
    service, request = service_and_draft(rig)
    item = service.create(request)
    action = ProposalDecision(revision=1, action="execute")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.decide(item["id"], action), range(2)))
    assert all(r["status"] == "started" for r in results), results
    assert results[0]["session_id"] == results[1]["session_id"]
    assert len(rig.provider.requests) == 1
    target = rig.messages.get_session(results[0]["session_id"])
    enabled = {
        a.agent_id for a in target.agent_configuration.agents.values() if a.enabled
    }
    assert enabled == {AgentId.GENERATOR, AgentId.REVIEWER}
    assert target.workspace_path == str(rig.workspace)
    assert target.agent_configuration.agents[AgentId.GENERATOR].max_turns == 3
    assert target.agent_configuration.agents[AgentId.REVIEWER].max_turns == 2
    assert request.kickoff in rig.provider.requests[0]["message"]
    assert service.get(item["id"])["status"] == "started"


def test_workspace_busy_prevents_launch_without_losing_proposal(rig):
    service, request = service_and_draft(rig)
    item = service.create(request)
    rig.messages.submit_message("Already running", session_id=rig.source.id)
    with pytest.raises(ProposalConflict):
        service.decide(item["id"], ProposalDecision(revision=1, action="execute"))
    assert service.get(item["id"])["status"] == "pending"
    assert len(rig.provider.requests) == 1


def test_lost_submission_response_recovers_without_resubmission(rig):
    service, request = service_and_draft(rig)
    item = service.create(request)
    original = rig.messages.submit_message

    def lost(*args, **kwargs):
        original(*args, **kwargs)
        raise TimeoutError("response lost")

    rig.messages.submit_message = lost
    result = service.decide(item["id"], ProposalDecision(revision=1, action="execute"))
    assert result["status"] == "uncertain"
    assert service.get(item["id"])["status"] == "started"
    assert (
        service.decide(item["id"], ProposalDecision(revision=1, action="execute"))[
            "status"
        ]
        == "started"
    )
    assert len(rig.provider.requests) == 1


def test_unknown_submission_does_not_retry_blindly(rig):
    service, request = service_and_draft(rig)
    item = service.create(request)
    rig.messages.submit_message = lambda *args, **kwargs: (_ for _ in ()).throw(
        TimeoutError()
    )
    assert (
        service.decide(item["id"], ProposalDecision(revision=1, action="execute"))[
            "status"
        ]
        == "uncertain"
    )
    assert (
        service.decide(item["id"], ProposalDecision(revision=1, action="execute"))[
            "status"
        ]
        == "uncertain"
    )
    assert not rig.provider.requests


def test_routes_validation_revision_and_project_boundary(rig):
    app = FastAPI()
    app.dependency_overrides[get_container] = lambda: SimpleNamespace(
        message_service=rig.messages,
        settings=SimpleNamespace(chat_store_path=str(rig.db)),
    )
    app.include_router(router)
    with TestClient(app) as client:
        assert (
            client.post(
                "/agent-proposals",
                json=draft(rig, workspace_path="/missing").model_dump(),
            ).status_code
            == 422
        )
        created = client.post("/agent-proposals", json=draft(rig).model_dump())
        assert created.status_code == 201
        proposal_id = created.json()["id"]
        assert (
            client.post(
                f"/agent-proposals/{proposal_id}/decisions",
                json={"revision": 2, "action": "execute"},
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"/agent-proposals/{proposal_id}/decisions",
                json={"revision": 1, "action": "observations", "observations": "  "},
            ).status_code
            == 422
        )
        assert client.get("/agent-proposals?limit=0").status_code == 422
        assert client.get("/agent-proposals").json()["unread_count"] == 1
        assert (
            client.post(
                f"/agent-proposals/{proposal_id}/read", json={"revision": 1}
            ).status_code
            == 200
        )
        assert client.get("/agent-proposals").json()["unread_count"] == 0
