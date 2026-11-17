from backend.app.application.services.subagent_catalog import catalog


def test_catalog_merges_builtin_user_and_project(tmp_path):
    home = tmp_path / "home"
    (home / ".claude/agents").mkdir(parents=True)
    (home / ".claude/agents/tester.md").write_text("---\nname: tester\ndescription: Corre tests\n---\nbody")
    ws = tmp_path / "ws"
    (ws / ".claude/agents").mkdir(parents=True)
    (ws / ".claude/agents/tester.md").write_text("---\nname: tester\ndescription: Del proyecto\n---\n")
    (ws / ".claude/agents/bad name.md").write_text("---\nname: bad name\n---\n")
    items = catalog(str(ws), home=home)
    assert items[0] == {"name": "tester", "description": "Del proyecto", "source": "project"}
    assert {"general-purpose", "Explore", "Plan"} <= {i["name"] for i in items}
    assert all(i["name"] != "bad name" for i in items)
