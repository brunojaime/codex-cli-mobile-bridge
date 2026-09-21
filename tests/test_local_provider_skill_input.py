from pathlib import Path

from backend.app.domain.entities.codex_options import CodexRunOptions
from backend.app.infrastructure.execution.local_provider import (
    _app_server_input_items,
    _message_with_skill_mentions,
)


def test_selected_skill_is_explicitly_mentioned_for_exec() -> None:
    options = CodexRunOptions(skill_ids=("casa-digital-authoring",))
    prompt = _message_with_skill_mentions("Mover una pared", options)
    assert prompt.startswith("$casa-digital-authoring\n\n")


def test_app_server_receives_structured_installed_skill(monkeypatch, tmp_path) -> None:
    skill = tmp_path / ".codex" / "skills" / "casa-digital-authoring" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# Test skill", encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    items = _app_server_input_items(
        "Consultar la casa",
        CodexRunOptions(skill_ids=("casa-digital-authoring",)),
        None,
    )

    assert items[0]["type"] == "text"
    assert items[1] == {
        "type": "skill",
        "name": "casa-digital-authoring",
        "path": str(skill.resolve()),
    }
