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
