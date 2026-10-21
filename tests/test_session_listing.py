from datetime import datetime, timedelta, timezone
import json
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.session_list_routes import build_session_list_router
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.chat_message import (
    ChatMessage,
    ChatMessageRole,
    ChatMessageStatus,
    ChatMessageAuthorType,
)
from backend.app.domain.entities.chat_turn_summary import ChatTurnSummary
from backend.app.infrastructure.persistence.sqlite_chat_repository import (
    SqliteChatRepository,
)
from backend.app.infrastructure.persistence.in_memory_chat_repository import (
    InMemoryChatRepository,
)
from backend.app.api.schemas import SessionSummaryResponse

DATE = datetime(2026, 10, 1, tzinfo=timezone.utc)


@pytest.fixture(params=["sqlite", "memory"])
def repository(request, tmp_path):
    if request.param == "sqlite":
        return SqliteChatRepository(
            database_path=str(tmp_path / "history.db"), projects_root=str(tmp_path)
        )
    return InMemoryChatRepository(projects_root=str(tmp_path))


def client(repo):
    app = FastAPI()
    app.include_router(build_session_list_router(lambda: repo))
    return TestClient(app)


def seed(repo, count=95):
    if isinstance(repo, SqliteChatRepository):
        with repo._connect() as connection:

            class Writer:
                def save_session(self, session):
                    repo._write_session(connection, session)

                def save_message(self, message):
                    repo._write_message(connection, message)

            seed(Writer(), count)
            connection.commit()
        return
    for i in range(count):
        date = DATE + timedelta(seconds=i)
        s = ChatSession(
            id=f"{i:04}",
            title=f"Chat {i}",
            workspace_path="/work",
            workspace_name="Work",
            created_at=date,
            updated_at=date,
            archived_at=date if i % 5 == 0 else None,
        )
        repo.save_session(s)
        repo.save_message(
            ChatMessage(
                id=f"m{i}",
                session_id=s.id,
                role=ChatMessageRole.USER,
                author_type=ChatMessageAuthorType.HUMAN,
                content="Long content " * 2000,
                status=ChatMessageStatus.COMPLETED,
                created_at=date,
                updated_at=date,
            )
        )


def test_page_entire_history_archive_search_and_bounds(repository):
    seed(repository)
    c = client(repository)
    for archived in (False, True):
        ids = []
        before = None
        while True:
            params = {"limit": 17, "archived": str(archived).lower()}
            if before:
                params["before"] = before
            response = c.get("/sessions/page", params=params)
            assert response.status_code == 200
            data = response.json()
            assert len(data["items"]) <= 17
            for item in data["items"]:
                assert "agent_configuration" not in item and "messages" not in item
                assert len(item["last_message_preview"]) <= 120
                assert item["has_full_agent_configuration"] is False
            ids.extend(x["id"] for x in data["items"])
            before = data["next_cursor"]
            if before is None:
                break
        expected = [f"{i:04}" for i in reversed(range(95)) if (i % 5 == 0) == archived]
        assert ids == expected
    assert c.get("/sessions/page?search=Chat%2094").json()["items"][0]["id"] == "0094"
    assert c.get("/sessions/page?workspace=/elsewhere").json()["items"] == []
    assert c.get("/sessions/page?before=garbage").status_code == 400
    assert c.get("/sessions/page?limit=0").status_code == 422
    assert c.get("/sessions/page?limit=101").status_code == 422


def test_refresh_only_changed_and_removed_and_new(repository):
    seed(repository)
    c = client(repository)
    page = c.get("/sessions/page").json()
    known = {x["id"]: x["revision"] for x in page["items"]}
    body = {"known": known}
    assert c.post("/sessions/changes", json=body).json() == {
        "items": [],
        "removed_ids": [],
        "gap_cursor": None,
    }
    # Message status updates without touching session.updated_at must invalidate.
    message = repository.get_message("m94")
    message.status = ChatMessageStatus.PENDING
    repository.save_message(message)
    changes = c.post("/sessions/changes", json=body).json()
    assert [x["id"] for x in changes["items"]] == ["0094"]
    assert changes["items"][0]["has_pending_messages"] is True
    session = repository.get_session("0093")
    session.archived_at = DATE
    repository.save_session(session)
    assert "0093" in c.post("/sessions/changes", json=body).json()["removed_ids"]
    repository.save_session(
        ChatSession(
            id="new", title="New", workspace_path="/work", workspace_name="Work"
        )
    )
    assert "new" in [
        x["id"] for x in c.post("/sessions/changes", json=body).json()["items"]
    ]


def test_old_loaded_rows_are_refreshed_and_cursor_does_not_duplicate(repository):
    seed(repository)
    c = client(repository)
    first = c.get("/sessions/page?limit=10").json()
    second = c.get(
        "/sessions/page", params={"limit": 10, "before": first["next_cursor"]}
    ).json()
    known = {x["id"]: x["revision"] for x in first["items"] + second["items"]}
    assert (
        c.post("/sessions/changes", json={"known": known, "limit": 10}).json()["items"]
        == []
    )
    old = repository.get_session(second["items"][-1]["id"])
    old.title = "Changed old chat"
    repository.save_session(old)
    result = c.post("/sessions/changes", json={"known": known, "limit": 10}).json()
    assert [x["id"] for x in result["items"]] == [old.id]


def test_ties_and_empty_sessions(repository):
    for i in range(8):
        repository.save_session(
            ChatSession(
                id=str(i),
                title=str(i),
                workspace_path="/work",
                workspace_name="Work",
                created_at=DATE,
                updated_at=DATE,
            )
        )
    c = client(repository)
    first = c.get("/sessions/page?limit=4").json()
    second = c.get(
        "/sessions/page", params={"limit": 4, "before": first["next_cursor"]}
    ).json()
    assert [x["id"] for x in first["items"] + second["items"]] == list("76543210")


def test_sqlite_projection_bounded_queries_and_no_transcript_hydration(
    tmp_path, monkeypatch
):
    repo = SqliteChatRepository(
        database_path=str(tmp_path / "history.db"), projects_root=str(tmp_path)
    )
    seed(repo, 150)
    statements = []
    original = repo._connect

    @contextmanager
    def traced():
        with original() as c:
            c.set_trace_callback(statements.append)
            yield c

    monkeypatch.setattr(repo, "_connect", traced)

    def forbidden(*args, **kwargs):
        raise AssertionError("Full history/configuration must not be read")

    monkeypatch.setattr(repo, "list_messages", forbidden)
    monkeypatch.setattr(repo, "_message_from_row", forbidden)
    monkeypatch.setattr(repo, "_session_from_row", forbidden)
    page = client(repo).get("/sessions/page").json()
    assert len(page["items"]) == 40
    assert len(statements) == 1
    assert len(json.dumps(page).encode()) < 60000


def test_legacy_batch_preserves_fields_and_summary_counts(repository):
    seed(repository, 10)
    repository.save_turn_summary(
        ChatTurnSummary(
            id="summary",
            session_id="0001",
            content="Summary",
            source_message_ids=("m1",),
        )
    )
    batch = list(repository.list_session_summary_inputs())
    assert len(batch) == 10
    for session, messages, count in batch:
        expected = SessionSummaryResponse.from_domain(
            session,
            messages=repository.list_messages(session.id),
            turn_summaries=repository.list_turn_summaries(session.id),
        )
        actual = SessionSummaryResponse.from_domain(
            session, messages=messages, turn_summary_count=count
        )
        assert actual.model_dump() == expected.model_dump()


def test_refresh_exposes_gap_after_many_new_chats(repository):
    seed(repository, 10)
    c = client(repository)
    first = c.get("/sessions/page?limit=5").json()
    known = {x["id"]: x["revision"] for x in first["items"]}
    for i in range(8):
        repository.save_session(
            ChatSession(
                id=f"new{i}",
                title="Información",
                workspace_path="/work",
                workspace_name="Work",
            )
        )
    change = c.post("/sessions/changes", json={"known": known, "limit": 5}).json()
    assert change["gap_cursor"] is not None
    remaining = c.get("/sessions/page", params={"before": change["gap_cursor"]}).json()
    seen = {x["id"] for x in change["items"] + remaining["items"]}
    assert {f"new{i}" for i in range(8)} <= seen
    assert (
        len(c.get("/sessions/page", params={"search": "INFORMACIÓN"}).json()["items"])
        == 8
    )


def test_main_router_legacy_and_new_paths_coexist(repository):
    from backend.app.api.routes import router, get_message_service

    class Service:
        def list_session_cards(self, **kwargs):
            return repository.list_session_cards(**kwargs)

        def list_session_summary_inputs(self):
            return repository.list_session_summary_inputs()

        def list_summary_jobs(self):
            return repository.list_summary_jobs()

    seed(repository, 10)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_message_service] = lambda: Service()
    c = TestClient(app)
    legacy = c.get("/sessions?compact=true")
    assert legacy.status_code == 200 and len(legacy.json()) == 10
    page = c.get("/sessions/page?limit=3")
    assert page.status_code == 200 and len(page.json()["items"]) == 3
    assert "agent_configuration" in legacy.json()[0]
    assert "agent_configuration" not in page.json()["items"][0]


def test_legacy_stream_does_not_hydrate_all_history_before_first_card(
    tmp_path, monkeypatch
):
    repo = SqliteChatRepository(
        database_path=str(tmp_path / "stream.db"), projects_root=str(tmp_path)
    )
    seed(repo, 50)
    reads = []
    original = repo._message_from_row

    def track(row):
        reads.append(row["id"])
        return original(row)

    monkeypatch.setattr(repo, "_message_from_row", track)
    stream = repo.list_session_summary_inputs()
    first = next(stream)
    assert len(reads) == 1
    assert len(first[1]) == 1
    stream.close()


def test_running_cards_are_available_outside_current_archive_filter(repository):
    seed(repository, 10)
    c = client(repository)
    result = c.post("/sessions/cards", json={"ids": ["0000", "0001", "absent"]})
    assert result.status_code == 200
    assert {x["id"] for x in result.json()["items"]} == {"0000", "0001"}
    assert c.post("/sessions/cards", json={"ids": []}).json()["items"] == []
