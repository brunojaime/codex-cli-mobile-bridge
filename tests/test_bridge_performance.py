"""Local performance contracts: real API/SQLite, synthetic private data only."""

from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import statistics
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.app.api.routes import router, get_message_service
from backend.app.api.schemas import SessionDetailResponse
from backend.app.domain.entities.agent_configuration import AgentId
from backend.app.domain.entities.chat_message import (
    ChatMessage,
    ChatMessageRole,
    ChatMessageStatus,
    ChatMessageAuthorType,
)
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.job import Job, JobStatus
from backend.app.domain.entities import current_run
from backend.app.infrastructure.persistence.sqlite_chat_repository import (
    SqliteChatRepository,
)
from backend.app.infrastructure.persistence.in_memory_chat_repository import (
    InMemoryChatRepository,
)

REPORT = Path(__file__).resolve().parents[1] / "reports/bridge-performance-20261010"


class SummaryService:
    def __init__(self, repo):
        self.repo = repo

    def list_sessions(self):
        return self.repo.list_sessions()

    def list_summary_jobs(self):
        return self.repo.list_summary_jobs()

    def list_messages(self, sid):
        return self.repo.list_messages(sid)

    def list_turn_summaries(self, sid):
        return self.repo.list_turn_summaries(sid)


def test_compact_api_preserves_metadata_and_full_detail(tmp_path):
    repo = InMemoryChatRepository(projects_root=str(tmp_path))
    for i in range(40):
        session = ChatSession(
            id=str(i),
            title=f"Chat {i}",
            workspace_path=str(tmp_path),
            workspace_name="Lab",
            auto_reviewer_prompt="Reviewer instructions " * 600,
        )
        session.agent_configuration.agents[AgentId.GENERATOR] = replace(
            session.agent_configuration.agents[AgentId.GENERATOR],
            prompt="Custom instruction " * 500,
        )
        repo.save_session(session)
        repo.save_message(
            ChatMessage(
                id=f"m{i}",
                session_id=str(i),
                role=ChatMessageRole.USER,
                author_type=ChatMessageAuthorType.HUMAN,
                content=f"Question {i}",
                status=ChatMessageStatus.COMPLETED,
            )
        )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_message_service] = lambda: SummaryService(repo)
    with TestClient(app) as client:
        full = client.get("/sessions")
        compact = client.get("/sessions?compact=true")
        assert full.status_code == compact.status_code == 200
        for before, after in zip(full.json(), compact.json(), strict=True):
            assert after.pop("has_full_agent_configuration") is False
            before.pop("auto_reviewer_prompt")
            for agent in before["agent_configuration"]["agents"]:
                agent.pop("prompt")
            assert before == after
        assert len(compact.content) < len(full.content) * 0.5
        # Default endpoint and details still carry original editable instructions.
        assert client.get("/sessions").json() == full.json()
    session = repo.get_session("0")
    detail = SessionDetailResponse.from_domain(
        session, messages=repo.list_messages("0")
    ).model_dump(mode="json")
    assert (
        detail["agent_configuration"]["agents"][0]["prompt"]
        == ("Custom instruction " * 500).strip()
    )
    assert detail["auto_reviewer_prompt"] == session.auto_reviewer_prompt
    REPORT.mkdir(exist_ok=True)
    (REPORT / "payload-metrics.json").write_text(
        json.dumps(
            {
                "sessions": 40,
                "full_bytes": len(full.content),
                "compact_bytes": len(compact.content),
                "reduction_percent": round(
                    (1 - len(compact.content) / len(full.content)) * 100, 2
                ),
                "same_metadata": True,
            },
            indent=2,
        )
        + "\n"
    )


def test_summary_jobs_avoid_large_bodies_preserve_states(tmp_path):
    repo = SqliteChatRepository(
        database_path=str(tmp_path / "jobs.db"), projects_root=str(tmp_path)
    )
    for i, status in enumerate(JobStatus):
        repo.save_session(
            ChatSession(
                id=f"s{i}",
                title="Lab",
                workspace_path=str(tmp_path),
                workspace_name="Lab",
            )
        )
        repo.save_job(
            Job(
                id=str(i),
                session_id=f"s{i}",
                message="private request" * 50000,
                execution_message="execution" * 50000,
                response="output" * 50000,
                image_paths=["private-image"],
                video_paths=["private-video"],
                status=status,
                latest_activity="working",
            )
        )
    original = repo.list_jobs()
    summary = repo.list_summary_jobs()
    omitted = {
        "message",
        "execution_message",
        "response",
        "error",
        "image_paths",
        "video_paths",
        "submission_token",
    }
    for before, after in zip(original, summary, strict=True):
        assert {k: v for k, v in asdict(before).items() if k not in omitted} == {
            k: v for k, v in asdict(after).items() if k not in omitted
        }
        assert (
            not after.message
            and after.execution_message is None
            and after.response is None
        )
        assert after.image_paths == after.video_paths == []

    def median_ms(fn):
        values = []
        for _ in range(9):
            start = time.perf_counter()
            fn()
            values.append((time.perf_counter() - start) * 1000)
        return round(statistics.median(values), 3)

    (REPORT / "sqlite-metrics.json").write_text(
        json.dumps(
            {
                "jobs": len(original),
                "samples": 9,
                "full_median_ms": median_ms(repo.list_jobs),
                "summary_median_ms": median_ms(repo.list_summary_jobs),
            },
            indent=2,
        )
        + "\n"
    )


def test_history_grouping_preserves_results_and_bounds_scans(monkeypatch):
    now = datetime.now(timezone.utc)
    session = ChatSession(
        id="s", title="Lab", workspace_path="/lab", workspace_name="Lab"
    )
    messages = [
        ChatMessage(
            id=str(i),
            session_id="s",
            role=ChatMessageRole.ASSISTANT,
            author_type=ChatMessageAuthorType.ASSISTANT,
            content="done",
            status=ChatMessageStatus.COMPLETED,
            run_id=f"r{i // 5}",
            created_at=now + timedelta(seconds=i),
            updated_at=now + timedelta(seconds=i),
        )
        for i in range(1500)
    ]
    derive = current_run._derive_run_execution

    def legacy():
        runs = [
            derive(
                session,
                run_id=rid,
                messages=messages,
                jobs_by_id=None,
                run_configurations_by_id=None,
                is_active=False,
            )
            for rid in {m.run_id for m in messages}
        ]
        runs.sort(
            key=lambda r: r.updated_at or r.completed_at or r.started_at, reverse=True
        )
        return runs[:5]

    def modern():
        return current_run.derive_recent_run_executions(
            session, messages=messages, limit=5
        )

    before = legacy()
    assert modern() == before
    sizes = []

    def observed(*args, **kwargs):
        sizes.append(len(kwargs["messages"]))
        return derive(*args, **kwargs)

    monkeypatch.setattr(current_run, "_derive_run_execution", observed)
    modern()
    assert sum(sizes) == len(messages)
    sizes.clear()
    session.active_agent_run_id = "r299"
    assert (
        len(
            current_run.derive_recent_run_executions(
                session, messages=messages, limit=1
            )
        )
        == 1
    )
    assert len(sizes) == 1
    session.active_agent_run_id = None
    monkeypatch.setattr(current_run, "_derive_run_execution", derive)
    timings = {}
    for name, fn in [("before", legacy), ("after", modern)]:
        values = []
        for _ in range(5):
            start = time.perf_counter()
            fn()
            values.append((time.perf_counter() - start) * 1000)
        timings[name + "_median_ms"] = round(statistics.median(values), 3)
    (REPORT / "history-metrics.json").write_text(
        json.dumps(
            dict(
                messages=1500,
                runs=300,
                scan_entries_before=450000,
                scan_entries_after=1500,
                **timings,
            ),
            indent=2,
        )
        + "\n"
    )
