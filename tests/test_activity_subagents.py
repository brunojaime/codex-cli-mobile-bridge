from backend.app.infrastructure.execution.activity import activity_item, entry


def test_claude_task_tool_becomes_subagent_node():
    item = activity_item(
        {
            "type": "tool_use",
            "id": "toolu_1",
            "name": "Task",
            "input": {
                "description": "Revisar tests",
                "subagent_type": "general-purpose",
                "prompt": "Corré los tests y resumí fallas",
            },
        },
        completed=False,
    )
    assert item is not None
    assert item["kind"] == "subagent"
    assert item["title"] == "Revisar tests"
    assert "general-purpose" in item["detail"]
    assert "Corré los tests" in item["detail"]
    assert item["status"] == "running"


def test_codex_collab_agent_call_becomes_subagent_node():
    item = activity_item(
        {
            "type": "collabAgentToolCall",
            "id": "c1",
            "tool": "spawn_agent",
            "arguments": '{"message": "Investigá el bug"}',
        },
        completed=True,
    )
    assert item is not None
    assert item["kind"] == "subagent"
    assert "Investigá el bug" in item["detail"]


def test_entry_carries_parent_only_when_present():
    assert "parent_id" not in entry("a", "tool", "t", "", "running")
    assert entry("a", "tool", "t", "", "running", parent_id="toolu_1")["parent_id"] == "toolu_1"


def test_regular_tool_use_is_still_a_tool():
    item = activity_item(
        {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "ls"}},
        completed=False,
    )
    assert item is not None and item["kind"] == "tool" and item["title"] == "Bash"


def test_claude_usage_summary_is_compact_and_public():
    from backend.app.infrastructure.execution.claude_runner import _usage_activity

    item = _usage_activity(
        {
            "usage": {
                "input_tokens": 1200,
                "cache_read_input_tokens": 30000,
                "output_tokens": 450,
            },
            "total_cost_usd": 0.0234,
            "num_turns": 3,
        }
    )
    assert item is not None
    assert item["kind"] == "usage"
    assert item["title"] == "31.2k entrada · 450 salida · US$0.023"
    assert _usage_activity({}) is None


def test_file_change_detail_keeps_unified_diffs():
    item = activity_item(
        {
            "type": "fileChange",
            "id": "f1",
            "changes": [
                {"path": "/repo/app.py", "kind": {"type": "update"}, "diff": "@@ -1 +1 @@\n-a\n+b"},
                {"path": "/repo/new.md", "kind": {"type": "add"}, "diff": "+hola"},
            ],
        },
        completed=True,
    )
    assert item["title"] == "Cambios en 2 archivos: app.py, new.md"
    assert "--- /repo/app.py (update)\n@@ -1 +1 @@\n-a\n+b" in item["detail"]
    assert "--- /repo/new.md (add)\n+hola" in item["detail"]
