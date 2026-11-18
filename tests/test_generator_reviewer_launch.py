from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
from pathlib import Path
import socket
import sqlite3
import sys
import threading
import time
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest
import uvicorn

from backend.app.api.agent_launch_routes import router, get_container
from backend.app.application.services.generator_reviewer_launch_service import (
    GeneratorReviewerLaunch,
    GeneratorReviewerLaunchService,
    LaunchConflict,
)
from backend.app.application.services.message_service import MessageService
from backend.app.domain.entities.agent_configuration import (
    AgentId,
    AgentType,
    AgentTriggerSource,
)
from backend.app.domain.entities.chat_message import (
    ChatMessage,
    ChatMessageRole,
    ChatMessageAuthorType,
    ChatMessageStatus,
)
from backend.app.infrastructure.persistence.sqlite_chat_repository import (
    SqliteChatRepository,
)
from backend.app.infrastructure.transcription.disabled_transcriber import (
    DisabledAudioTranscriber,
)
from test_message_flow import _ControlledExecutionProvider

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def rig(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    db = tmp_path / "chats.sqlite3"
    repo = SqliteChatRepository(database_path=str(db), projects_root=str(tmp_path))
    provider = _ControlledExecutionProvider()
    messages = MessageService(
        repository=repo,
        execution_provider=provider,
        default_workspace_path=str(workspace),
        audio_transcriber=DisabledAudioTranscriber(),
        bridge_api_port=8123,
        follow_up_reconcile_interval_seconds=None,
    )
    source = messages.create_session(title="Origin", workspace_path=str(workspace))
    human = ChatMessage(
        id=str(uuid4()),
        session_id=source.id,
        role=ChatMessageRole.USER,
        author_type=ChatMessageAuthorType.HUMAN,
        agent_id=AgentId.USER,
        agent_type=AgentType.HUMAN,
        trigger_source=AgentTriggerSource.USER,
        content="Start a separate implementation and security review.",
        status=ChatMessageStatus.COMPLETED,
    )
    repo.save_message(human)
    request = GeneratorReviewerLaunch(
        source_session_id=source.id,
        source_message_id=human.id,
        title="Implementation and security",
        generator_prompt="Implement the requested behavior and test it.",
        reviewer_prompt="Independently examine authorization and failed requests.",
        kickoff="Execute the agreed task directly here; do not delegate to another chat.",
    )
    launch = GeneratorReviewerLaunchService(
        messages, db.with_suffix(".launches.sqlite3")
    )
    app = FastAPI()
    container = SimpleNamespace(
        message_service=messages, settings=SimpleNamespace(chat_store_path=str(db))
    )
    app.dependency_overrides[get_container] = lambda: container
    app.include_router(router)
    yield SimpleNamespace(
        repo=repo,
        provider=provider,
        messages=messages,
        source=source,
        human=human,
        request=request,
        launch=launch,
        app=app,
        client=TestClient(app),
        workspace=workspace,
        db=db,
    )


def test_free_prompts_and_launch_before_kickoff_preserve_source_and_profiles(rig):
    source_before = asdict(rig.source)
    profiles_before = {
        p.id: (p.name, p.prompt, asdict(p.configuration))
        for p in rig.messages.list_agent_profiles()
    }
    original_submit = rig.messages.submit_message
    seen = []

    def check_order(message, **kwargs):
        config = rig.messages.get_session(kwargs["session_id"]).agent_configuration
        seen.append(config)
        assert config.agents[AgentId.GENERATOR].prompt == rig.request.generator_prompt
        assert config.agents[AgentId.REVIEWER].prompt == rig.request.reviewer_prompt
        return original_submit(message, **kwargs)

    rig.messages.submit_message = check_order
    result = rig.launch.launch(rig.request)
    assert result["state"] == "started", result
    assert len(seen) == 1
    target = rig.messages.get_session(result["session_id"])
    assert target.id != rig.source.id
    assert target.workspace_path == str(rig.workspace)
    assert {
        a.agent_id for a in target.agent_configuration.agents.values() if a.enabled
    } == {AgentId.GENERATOR, AgentId.REVIEWER}
    assert asdict(rig.messages.get_session(rig.source.id)) == source_before
    assert {
        p.id: (p.name, p.prompt, asdict(p.configuration))
        for p in rig.messages.list_agent_profiles()
    } == profiles_before
    assert result["source_message_id"] == rig.human.id
    assert result["chat_link"] == f"codex-bridge://chat/{target.id}"
    assert rig.provider.requests[0]["message"].startswith(rig.request.generator_prompt)
    assert rig.request.kickoff in rig.provider.requests[0]["message"]
    assert f"source_session_id={target.id}" in rig.provider.requests[0]["message"]
    assert (
        len(
            [
                m
                for m in rig.messages.list_messages(target.id)
                if m.author_type == ChatMessageAuthorType.HUMAN
            ]
        )
        == 1
    )


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({}, (25, 25)),
        ({"generator_turns": 4, "reviewer_turns": 3}, (4, 3)),
        ({"generator_turns": 4}, (4, 4)),
        ({"reviewer_turns": 3}, (4, 3)),
        ({"generator_turns": 1, "reviewer_turns": 1}, (1, 1)),
    ],
)
def test_turn_budgets_drive_existing_cycle(rig, overrides, expected):
    req = rig.request.model_copy(update=overrides)
    result = rig.launch.launch(req)
    assert result["state"] == "started"
    assert result["generator_turns"] == overrides.get("generator_turns", 25)
    assert result["reviewer_turns"] == overrides.get("reviewer_turns", 25)
    completed = set()
    counts = {AgentId.GENERATOR: 0, AgentId.REVIEWER: 0}
    for _ in range(60):
        pending = [
            j
            for j in rig.messages.list_stored_jobs_for_session(result["session_id"])
            if j.id not in completed
        ]
        if not pending:
            break
        for job in pending:
            counts[job.agent_id] += 1
            rig.provider.complete_job(
                job.id, response="Continue with another concrete test."
            )
            rig.messages.get_job(job.id)
            completed.add(job.id)
    assert (counts[AgentId.GENERATOR], counts[AgentId.REVIEWER]) == expected
    assert rig.messages.get_session(result["session_id"]).active_agent_run_id is None
    # Re-observing terminal jobs cannot buy more turns.
    for job_id in completed:
        rig.messages.get_job(job_id)
    assert len(rig.messages.list_stored_jobs_for_session(result["session_id"])) == sum(
        expected
    )


def test_turn_budgets_allow_early_completion(rig):
    result = rig.launch.launch(rig.request)
    rig.provider.complete_job(result["job_id"], response="Implemented and tested.")
    rig.messages.get_job(result["job_id"])
    reviewer = next(
        j
        for j in rig.messages.list_stored_jobs_for_session(result["session_id"])
        if j.agent_id == AgentId.REVIEWER
    )
    rig.provider.complete_job(
        reviewer.id,
        response=json.dumps({"status": "complete", "prompt": "", "reason": "Verified"}),
    )
    rig.messages.get_job(reviewer.id)
    assert len(rig.messages.list_stored_jobs_for_session(result["session_id"])) == 2


def test_idempotency_across_concurrent_services_and_restart(rig):
    def call(_):
        return GeneratorReviewerLaunchService(rig.messages, rig.launch.database).launch(
            rig.request
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(call, range(8)))
    assert {r["state"] for r in results} == {"started"}
    assert len({r["session_id"] for r in results}) == 1
    assert sum(not r["reused"] for r in results) == 1
    assert len(rig.messages.list_sessions()) == 2
    assert len(rig.provider.requests) == 1
    reopened = GeneratorReviewerLaunchService(rig.messages, rig.launch.database).launch(
        rig.request
    )
    assert reopened["job_id"] == results[0]["job_id"]
    with pytest.raises(LaunchConflict):
        rig.launch.launch(rig.request.model_copy(update={"kickoff": "Different task"}))
    assert len(rig.provider.requests) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("generator_turns", 0),
        ("reviewer_turns", -1),
        ("generator_turns", True),
        ("reviewer_turns", "3"),
        ("generator_turns", 2**64),
        ("generator_prompt", "  "),
        ("reviewer_prompt", "x" * 12001),
        ("kickoff", ""),
        ("source_session_id", str(uuid4())),
        ("source_message_id", str(uuid4())),
        ("workspace_path", "/tmp"),
    ],
)
def test_idempotency_invalid_input_has_no_side_effect(rig, field, value):
    data = rig.request.model_dump(mode="json")
    data[field] = value
    response = rig.client.post("/agent-launches/generator-reviewer", json=data)
    assert response.status_code == 422
    assert len(rig.messages.list_sessions()) == 1
    assert not rig.provider.requests


def test_idempotency_failed_configuration_is_visible_without_retry(rig, monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("configuration unavailable")

    monkeypatch.setattr(rig.messages, "update_agent_configuration", fail)
    first = rig.launch.launch(rig.request)
    assert first["state"] == "failed"
    assert first["problem"]
    assert rig.launch.launch(rig.request)["state"] == "failed"
    assert not rig.provider.requests


def test_idempotency_uncertain_provider_submission_never_repeats(rig, monkeypatch):
    def uncertain(message, **kwargs):
        rig.provider.execute(message, workdir=str(rig.workspace))
        raise RuntimeError("connection lost after enqueue")

    monkeypatch.setattr(rig.messages, "submit_message", uncertain)
    first = rig.launch.launch(rig.request)
    assert first["state"] == "uncertain"
    assert rig.launch.launch(rig.request)["state"] == "uncertain"
    assert rig.launch.get(first["launch_id"])["state"] == "uncertain"
    assert len(rig.provider.requests) == 1


def test_idempotency_recovers_persisted_submission_after_lost_receipt(rig):
    first = rig.launch.launch(rig.request)
    with sqlite3.connect(rig.launch.database) as db:
        db.execute("UPDATE launches SET state='starting', job_id=NULL")
    recovered = rig.launch.launch(rig.request)
    assert recovered["state"] == "started"
    assert recovered["job_id"] == first["job_id"]
    assert len(rig.provider.requests) == 1


def test_launch_http_and_conflict_status(rig):
    response = rig.client.post(
        "/agent-launches/generator-reviewer", json=rig.request.model_dump(mode="json")
    )
    assert response.status_code == 200
    result = response.json()
    assert result["state"] == "started"
    assert (
        rig.client.get("/agent-launches/" + result["launch_id"]).json()["job_id"]
        == result["job_id"]
    )
    data = rig.request.model_dump(mode="json")
    data["reviewer_turns"] = 3
    assert (
        rig.client.post("/agent-launches/generator-reviewer", json=data).status_code
        == 409
    )
    assert rig.client.get("/agent-launches/" + str(uuid4())).status_code == 404


def test_free_prompts_mcp_protocol_launches_from_another_workspace(rig, tmp_path):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(rig.app, log_level="error", lifespan="off"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_apps.generator_reviewer.server"],
            cwd=str(tmp_path),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                tools = (await client.list_tools()).tools
                tool = next(t for t in tools if t.name == "start_generator_reviewer")
                assert (
                    tool.inputSchema["properties"]["generator_turns"]["default"] == 25
                )
                assert tool.inputSchema["properties"]["reviewer_turns"]["default"] == 25
                manifest = await client.call_tool("get_app_manifest", {})
                assert not manifest.isError
                assert len(rig.messages.list_sessions()) == 1
                args = rig.request.model_dump(mode="json")
                args.update(
                    bridge_url=f"http://127.0.0.1:{port}",
                    generator_turns=4,
                    reviewer_turns=3,
                )
                first = await client.call_tool("start_generator_reviewer", args)
                assert not first.isError, first
                result = json.loads(first.content[0].text)
                assert result["state"] == "started", result
                repeated = await client.call_tool("start_generator_reviewer", args)
                assert (
                    json.loads(repeated.content[0].text)["job_id"] == result["job_id"]
                )
                assert len(rig.provider.requests) == 1
                # Same tool carries another arbitrary focus; there is no preset enum.
                assert "enum" not in tool.inputSchema["properties"]["generator_prompt"]
                invalid = await client.call_tool(
                    "start_generator_reviewer",
                    {**args, "bridge_url": "https://example.com"},
                )
                assert invalid.isError
                invalid_budget = await client.call_tool(
                    "start_generator_reviewer", {**args, "generator_turns": True}
                )
                assert invalid_budget.isError

    try:
        asyncio.run(exercise())
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()


def test_idempotency_recovers_creation_crash_without_second_chat(rig, monkeypatch):
    create = rig.messages.create_session

    def crash(**kwargs):
        create(**kwargs)
        raise SystemExit("simulated process death")

    monkeypatch.setattr(rig.messages, "create_session", crash)
    with pytest.raises(SystemExit):
        rig.launch.launch(rig.request)
    assert len(rig.messages.list_sessions()) == 2
    assert not rig.provider.requests
    monkeypatch.setattr(rig.messages, "create_session", create)
    assert rig.launch.launch(rig.request)["state"] == "started"
    assert len(rig.messages.list_sessions()) == 2
    assert len(rig.provider.requests) == 1


def test_idempotency_recovers_receipt_after_reviewer_has_started(rig):
    first = rig.launch.launch(rig.request)
    rig.provider.complete_job(first["job_id"], response="Done, please review")
    rig.messages.get_job(first["job_id"])
    assert len(rig.messages.list_stored_jobs_for_session(first["session_id"])) == 2
    with sqlite3.connect(rig.launch.database) as db:
        db.execute("UPDATE launches SET state='starting', job_id=NULL")
    recovered = rig.launch.get(first["launch_id"])
    assert recovered["state"] == "started"
    assert recovered["job_id"] == first["job_id"]
    assert len(rig.provider.requests) == 2


def test_free_prompts_shared_skill_discovery_from_two_projects(tmp_path):
    from backend.app.infrastructure.codex_tooling import discover_codex_skills
    import shutil
    import yaml

    home = tmp_path / "home"
    destination = home / ".codex/skills/generator-reviewer"
    shutil.copytree(ROOT / "codex-skills/generator-reviewer", destination)
    skill_text = (destination / "SKILL.md").read_text()
    metadata = yaml.safe_load(skill_text.split("---")[1])
    assert metadata["name"] == "generator-reviewer"
    for name in ("project-a", "project-b"):
        project = tmp_path / name
        project.mkdir()
        skills = discover_codex_skills(home, repo_root=project)
        assert any(skill.skill_id == "generator-reviewer" for skill in skills)
        assert not (project / "codex-skills").exists()
    shared = Path.home() / ".codex/skills/generator-reviewer/SKILL.md"
    assert shared.read_text() == skill_text
