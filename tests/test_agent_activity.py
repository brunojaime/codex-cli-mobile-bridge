import json

from backend.app.api.schemas import ChatMessageResponse, JobResponse
from backend.app.domain.entities.chat_message import (
    ChatMessage,
    ChatMessageRole,
    ChatMessageAuthorType,
    ChatMessageStatus,
)
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.job import Job, JobStatus
from backend.app.infrastructure.execution.activity import activity_item, entry
from backend.app.infrastructure.execution.local_provider import LocalExecutionProvider
from backend.app.infrastructure.persistence.sqlite_chat_repository import (
    SqliteChatRepository,
)


def test_tool_history_updates_in_place_and_snapshots_are_isolated():
    provider = LocalExecutionProvider(command="unused")
    provider._set_state("job", status=JobStatus.RUNNING)
    events = []
    unsubscribe = provider.watch_job("job", events.append)
    start = {
        "type": "item.started",
        "item": {"id": "cmd", "type": "command_execution", "command": "pytest"},
    }
    provider._handle_stdout_line("job", json.dumps(start))
    before = provider.get_snapshot("job")
    provider._handle_stdout_line(
        "job",
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    **start["item"],
                    "exit_code": 1,
                    "aggregated_output": "1 failed",
                },
            }
        ),
    )
    after = provider.get_snapshot("job")
    assert len(after.activities) == 1
    assert after.activities[0]["status"] == "failed"
    assert "1 failed" in after.activities[0]["detail"]
    assert before.activities[0]["status"] == "running"
    assert before.activities[0]["created_at"] == after.activities[0]["created_at"]
    assert events[-1].activities == after.activities
    unsubscribe()


def test_app_server_streams_commentary_and_tools_without_private_reasoning():
    provider = LocalExecutionProvider(command="unused")
    provider._set_state("job", status=JobStatus.RUNNING)
    response = []
    kwargs = dict(
        response_buffer_ref=lambda: "",
        set_response_buffer=response.append,
        set_final_response=response.append,
        mark_turn_completed=lambda: None,
        final_agent_message_item_ids=set(),
        non_final_agent_message_item_ids=set(),
    )
    for method, params in [
        (
            "item/started",
            {
                "item": {
                    "id": "progress",
                    "type": "agentMessage",
                    "phase": "commentary",
                    "text": "",
                }
            },
        ),
        (
            "item/agentMessage/delta",
            {"itemId": "progress", "delta": "Revisando archivos"},
        ),
        (
            "item/completed",
            {
                "item": {
                    "id": "progress",
                    "type": "agentMessage",
                    "phase": "commentary",
                    "text": "Revisando archivos",
                }
            },
        ),
        (
            "item/completed",
            {
                "item": {
                    "id": "private",
                    "type": "reasoning",
                    "text": "private reasoning",
                }
            },
        ),
        (
            "item/started",
            {
                "item": {
                    "id": "tool",
                    "type": "mcpToolCall",
                    "tool": "search",
                    "arguments": {"q": "bridge"},
                }
            },
        ),
        (
            "item/completed",
            {
                "item": {
                    "id": "tool",
                    "type": "mcpToolCall",
                    "tool": "search",
                    "result": {"content": [{"type": "text", "text": "Found it"}]},
                }
            },
        ),
    ]:
        provider._handle_app_server_payload(
            "job", {"method": method, "params": params}, **kwargs
        )
    items = provider.get_snapshot("job").activities
    assert [item["id"] for item in items] == ["progress", "tool"]
    assert items[0]["title"] == "Revisando archivos"
    assert "Found it" in items[1]["detail"]
    assert response == []
    assert "private reasoning" not in json.dumps(items)


def test_terminal_execution_does_not_invent_tool_success_or_restart():
    provider = LocalExecutionProvider(command="unused")
    provider._set_state("job", status=JobStatus.RUNNING)
    provider._record_activity(
        "job",
        activity_item(
            {"id": "tool", "type": "commandExecution", "command": "test"},
            completed=False,
        ),
    )
    provider._set_state("job", status=JobStatus.COMPLETED)
    provider._set_state("job", status=JobStatus.RUNNING)
    snapshot = provider.get_snapshot("job")
    assert snapshot.status == JobStatus.COMPLETED
    assert snapshot.activities[0]["status"] == "unknown"


def test_activity_survives_database_reopen_and_is_in_chat_and_job_api(tmp_path):
    path = str(tmp_path / "chat.db")
    repo = SqliteChatRepository(database_path=path, projects_root=str(tmp_path))
    repo.save_session(
        ChatSession(
            id="session",
            title="Chat",
            workspace_path=str(tmp_path),
            workspace_name="Project",
        )
    )
    activity = entry("tool", "tool", "Comando", "pytest\n\nPassed", "completed")
    job = Job(
        id="job",
        session_id="session",
        message="work",
        activities=[activity],
        status=JobStatus.COMPLETED,
    )
    repo.save_job(job)
    reopened = SqliteChatRepository(database_path=path, projects_root=str(tmp_path))
    stored = reopened.get_job("job")
    assert stored.activities == [activity]
    assert JobResponse.from_domain(stored).activities == [activity]
    message = ChatMessage(
        id="message",
        session_id="session",
        role=ChatMessageRole.ASSISTANT,
        author_type=ChatMessageAuthorType.ASSISTANT,
        status=ChatMessageStatus.COMPLETED,
        content="Done",
    )
    assert ChatMessageResponse.from_domain(message, job=stored).job_activities == [
        activity
    ]
    # Activity payloads are deliberately omitted from lightweight session listings.
    assert reopened.list_summary_jobs()[0].activities == []


def test_reasoning_and_final_answer_do_not_become_activity_entries():
    for kind in ("reasoning", "Reasoning", "thinking", "agentMessage"):
        assert (
            activity_item(
                {"id": "private", "type": kind, "text": "hidden"}, completed=True
            )
            is None
        )


def test_public_plan_steps_keep_their_identity_when_updated():
    provider = LocalExecutionProvider(command="unused")
    provider._set_state("job", status=JobStatus.RUNNING)
    kwargs = dict(
        response_buffer_ref=lambda: "",
        set_response_buffer=lambda _: None,
        set_final_response=lambda _: None,
        mark_turn_completed=lambda: None,
        final_agent_message_item_ids=set(),
        non_final_agent_message_item_ids=set(),
    )
    for status in ["pending", "inProgress", "completed"]:
        provider._handle_app_server_payload(
            "job",
            {
                "method": "turn/plan/updated",
                "params": {"plan": [{"step": "Revisar archivos", "status": status}]},
            },
            **kwargs,
        )
        expected = "running" if status == "inProgress" else status
        assert provider.get_snapshot("job").activities[0]["status"] == expected
    activities = provider.get_snapshot("job").activities
    assert len(activities) == 1
    assert activities[0]["kind"] == "plan"
    assert activities[0]["status"] == "completed"
