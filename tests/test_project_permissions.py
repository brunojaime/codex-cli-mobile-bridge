import json

from backend.app.application.services import project_permissions as pp


def test_describe_and_remove_rule(tmp_path):
    settings = tmp_path / ".claude" / "settings.local.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"permissions": {"allow": ["Bash(npm test)", "Bash(ls)"]}, "other": 1}))
    info = pp.describe(str(tmp_path), claude_mode="acceptEdits",
                       codex_exec_args="--dangerously-bypass-approvals-and-sandbox")
    assert info["local"]["rules"]["allow"] == ["Bash(npm test)", "Bash(ls)"]
    assert info["codex"]["mode"] == "full-access"
    assert "sin preguntar" in info["claude"]["description"]
    assert pp.remove_rule(str(tmp_path), "allow", "Bash(ls)")
    assert not pp.remove_rule(str(tmp_path), "allow", "Bash(ls)")
    data = json.loads(settings.read_text())
    assert data == {"permissions": {"allow": ["Bash(npm test)"]}, "other": 1}


def test_missing_settings_is_empty(tmp_path):
    info = pp.describe(str(tmp_path), claude_mode="default", codex_exec_args="")
    assert info["local"]["rules"] == {"allow": [], "ask": [], "deny": []}


def test_project_mode_overrides_server_default(tmp_path):
    assert pp.effective_mode(tmp_path, "acceptEdits") == "acceptEdits"
    pp.set_mode(str(tmp_path), "default")
    info = pp.describe(str(tmp_path), claude_mode="acceptEdits", codex_exec_args="")
    assert info["claude"]["mode"] == "default"
    assert info["claude"]["source"] == "project"
    assert info["claude"]["server_default"] == "acceptEdits"
    assert [o["mode"] for o in info["claude"]["options"]][0] == "acceptEdits"
    assert pp.effective_mode(tmp_path, "acceptEdits") == "default"
    # Clearing keeps the other rules and goes back to the server default.
    pp.remove_rule(str(tmp_path), "allow", "x")
    pp.set_mode(str(tmp_path), None)
    data = json.loads((tmp_path / ".claude" / "settings.local.json").read_text())
    assert data == {"permissions": {}}
    assert pp.effective_mode(tmp_path, "acceptEdits") == "acceptEdits"


def test_invalid_mode_is_rejected(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        pp.set_mode(str(tmp_path), "bypassPermissions")
    settings = tmp_path / ".claude" / "settings.local.json"
    settings.parent.mkdir(exist_ok=True)
    settings.write_text(json.dumps({"permissions": {"defaultMode": "bypassPermissions"}}))
    # Unknown modes written by hand are ignored, never passed to Claude.
    assert pp.effective_mode(tmp_path, "acceptEdits") == "acceptEdits"
