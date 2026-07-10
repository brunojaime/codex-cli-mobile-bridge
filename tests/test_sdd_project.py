from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.infrastructure.config.settings import Settings


def test_sdd_endpoints_return_project_snapshot_and_capabilities(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_sdd_project(project)
    (project / "architecture/ignored.txt").write_text("not allowed")
    (project / "specs/001-demo/diagrams/ignored.txt").write_text("not allowed")

    client = _client(projects_root, codex_workdir=str(project))

    capabilities = client.get("/capabilities")
    projects = client.get("/sdd/projects")
    snapshot = client.get("/sdd/project", params={"workspace_path": str(project)})
    diagrams = client.get(
        "/api/v1/sdd/project/diagrams",
        params={"workspace_path": str(project)},
    )

    assert capabilities.status_code == 200
    assert capabilities.json()["supports_sdd"] is True
    assert projects.status_code == 200
    assert projects.json()["kind"] == "codex.sddProjects"
    assert projects.json()["default_workspace_path"] == str(project)
    assert projects.json()["projects"][0]["workspace_name"] == "demo"
    assert snapshot.status_code == 200
    payload = snapshot.json()
    assert payload["kind"] == "codex.sddProject"
    assert payload["required"] is True
    assert payload["manifest"]["path"] == "codex-bridge.yaml"
    assert payload["constitution"]["path"] == ".specify/memory/constitution.md"
    assert payload["specs"][0]["id"] == "001-demo"
    assert payload["specs"][0]["description"] == ""
    assert payload["specs"][0]["lifecycle_status"] == "draft"
    assert payload["specs"][0]["traceability_status"] == "linked"
    assert payload["specs"][0]["metadata_status"] == "missing"
    assert payload["specs"][0]["task_total"] == 0
    assert payload["specs"][0]["missing"] == []
    assert [item["path"] for item in payload["specs"][0]["plan_files"]] == [
        "specs/001-demo/plan.md",
        "specs/001-demo/plan-review.md",
        "specs/001-demo/plans/02-implementation.md",
    ]
    assert [item["path"] for item in payload["specs"][0]["task_files"]] == [
        "specs/001-demo/tasks.md",
        "specs/001-demo/tasks-review.md",
        "specs/001-demo/tasks/02-implementation.md",
    ]
    assert payload["specs"][0]["slice_docs"][0]["path"] == (
        "specs/001-demo/slices/01-demo-slice.md"
    )
    assert diagrams.status_code == 200
    diagram_paths = {item["path"] for item in diagrams.json()["diagrams"]}
    assert "architecture/context.mmd" in diagram_paths
    assert "specs/001-demo/diagrams/sequence.mmd" in diagram_paths
    assert "architecture/ignored.txt" not in diagram_paths
    assert "specs/001-demo/diagrams/ignored.txt" not in diagram_paths


def test_sdd_project_returns_explicit_spec_plan_task_tree(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_sdd_project(project)
    spec_dir = project / "specs/001-demo"
    (spec_dir / "plans/01-foundation").mkdir(parents=True)
    (spec_dir / "plans/02-checkout").mkdir(parents=True)
    (spec_dir / "tasks/plan-1-task-1").mkdir(parents=True)
    (spec_dir / "tasks/plan-1-task-2").mkdir(parents=True)
    (spec_dir / "tasks/plan-2-task-1").mkdir(parents=True)
    (spec_dir / "tasks/plan-2-task-2").mkdir(parents=True)
    (spec_dir / "tasks/plan-2-task-3").mkdir(parents=True)
    (spec_dir / "plans/01-foundation/plan.md").write_text("# Foundation Plan\n")
    (spec_dir / "plans/02-checkout/plan.md").write_text("# Checkout Plan\n")
    for path, title in (
        ("tasks/plan-1-task-1/task.md", "Catalog import"),
        ("tasks/plan-1-task-2/task.md", "Size normalization"),
        ("tasks/plan-2-task-1/task.md", "Cart reservation"),
        ("tasks/plan-2-task-2/task.md", "Checkout validation"),
        ("tasks/plan-2-task-3/task.md", "Audit trail"),
    ):
        (spec_dir / path).write_text(f"# {title}\n")
    (spec_dir / "plans/02-checkout/checkout-flow.mmd").write_text(
        "flowchart LR\nCart --> Order\n"
    )
    (spec_dir / "tree.json").write_text(
        json.dumps(
            {
                "spec": {"file": "spec.md", "diagrams": ["diagrams/sequence.mmd"]},
                "plans": [
                    {
                        "id": "plan-1",
                        "number": 1,
                        "title": "Foundation",
                        "status": "done",
                        "file": "plans/01-foundation/plan.md",
                        "tasks": [
                            {
                                "id": "plan-1-task-1",
                                "number": 1,
                                "title": "Catalog import",
                                "status": "done",
                                "file": "tasks/plan-1-task-1/task.md",
                            },
                            {
                                "id": "plan-1-task-2",
                                "number": 2,
                                "title": "Size normalization",
                                "status": "done",
                                "file": "tasks/plan-1-task-2/task.md",
                            },
                        ],
                    },
                    {
                        "id": "plan-2",
                        "number": 2,
                        "title": "Checkout",
                        "status": "in_progress",
                        "file": "plans/02-checkout/plan.md",
                        "diagrams": ["plans/02-checkout/checkout-flow.mmd"],
                        "tasks": [
                            {
                                "id": "plan-2-task-1",
                                "number": 1,
                                "title": "Cart reservation",
                                "status": "in_progress",
                                "file": "tasks/plan-2-task-1/task.md",
                            },
                            {
                                "id": "plan-2-task-2",
                                "number": 2,
                                "title": "Checkout validation",
                                "status": "planned",
                                "file": "tasks/plan-2-task-2/task.md",
                            },
                            {
                                "id": "plan-2-task-3",
                                "number": 3,
                                "title": "Audit trail",
                                "status": "planned",
                                "file": "tasks/plan-2-task-3/task.md",
                            },
                        ],
                    },
                ],
            }
        )
    )
    client = _client(projects_root)

    response = client.get("/sdd/project", params={"workspace_path": str(project)})

    assert response.status_code == 200
    spec = response.json()["specs"][0]
    assert spec["traceability_status"] == "linked"
    assert spec["tree"]["plans"][0]["tasks"][0]["number"] == 1
    assert spec["tree"]["plans"][1]["tasks"][0]["number"] == 1
    assert [task["title"] for task in spec["tree"]["plans"][1]["tasks"]] == [
        "Cart reservation",
        "Checkout validation",
        "Audit trail",
    ]
    assert "specs/001-demo/plans/02-checkout/checkout-flow.mmd" in {
        diagram["path"] for diagram in spec["diagrams"]
    }


def test_sdd_project_lazy_summary_and_spec_detail(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_sdd_project(project)
    spec_dir = project / "specs/001-demo"
    (spec_dir / "plans/01-foundation").mkdir(parents=True)
    (spec_dir / "tasks/plan-1-task-1").mkdir(parents=True)
    (spec_dir / "plans/01-foundation/plan.md").write_text("# Foundation Plan\n")
    (spec_dir / "tasks/plan-1-task-1/task.md").write_text("# Foundation Task\n")
    (spec_dir / "tree.json").write_text(
        json.dumps(
            {
                "spec": {"file": "spec.md"},
                "plans": [
                    {
                        "id": "plan-1",
                        "number": 1,
                        "title": "Foundation",
                        "file": "plans/01-foundation/plan.md",
                        "tasks": [
                            {
                                "id": "plan-1-task-1",
                                "number": 1,
                                "title": "Foundation Task",
                                "file": "tasks/plan-1-task-1/task.md",
                            }
                        ],
                    }
                ],
            }
        )
    )
    client = _client(projects_root)

    summary = client.get(
        "/sdd/project/summary",
        params={"workspace_path": str(project)},
    )
    detail = client.get(
        "/sdd/project/spec",
        params={"workspace_path": str(project), "spec_id": "001-demo"},
    )
    missing = client.get(
        "/sdd/project/spec",
        params={"workspace_path": str(project), "spec_id": "../001-demo"},
    )

    assert summary.status_code == 200
    summary_payload = summary.json()
    assert summary_payload["kind"] == "codex.sddProjectSummary"
    summary_spec = summary_payload["specs"][0]
    assert summary_spec["id"] == "001-demo"
    assert summary_spec["tree"]["plans"][0]["title"] == "Foundation"
    assert summary_spec["tree"]["plans"][0]["file"]["content"] is None
    assert summary_spec["tree"]["plans"][0]["tasks"][0]["file"]["content"] is None
    assert summary_spec["task_files"][0]["content"] is None

    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["kind"] == "codex.sddProjectSpec"
    detail_spec = detail_payload["spec"]
    assert detail_spec["id"] == "001-demo"
    assert detail_spec["tree"]["plans"][0]["file"]["content"] == "# Foundation Plan\n"
    assert (
        detail_spec["tree"]["plans"][0]["tasks"][0]["file"]["content"]
        == "# Foundation Task\n"
    )
    assert missing.status_code == 404


def test_sdd_project_tree_reports_missing_plan_file(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_sdd_project(project)
    spec_dir = project / "specs/001-demo"
    (spec_dir / "tasks/plan-1-task-1").mkdir(parents=True)
    (spec_dir / "tasks/plan-1-task-1/task.md").write_text("# Task\n")
    (spec_dir / "tree.json").write_text(
        json.dumps(
            {
                "spec": {"file": "spec.md"},
                "plans": [
                    {
                        "id": "plan-1",
                        "number": 1,
                        "title": "Missing plan file",
                        "file": "plans/missing/plan.md",
                        "tasks": [
                            {
                                "id": "plan-1-task-1",
                                "number": 1,
                                "title": "Task",
                                "file": "tasks/plan-1-task-1/task.md",
                            }
                        ],
                    }
                ],
            }
        )
    )
    client = _client(projects_root)

    response = client.get("/sdd/project", params={"workspace_path": str(project)})

    assert response.status_code == 200
    spec = response.json()["specs"][0]
    assert spec["traceability_status"] != "linked"
    assert "specs/001-demo/plans/missing/plan.md" in spec["missing"]
    assert spec["tree"]["complete"] is False
    assert "specs/001-demo/plans/missing/plan.md" in spec["tree"]["missing"]


def test_sdd_project_tree_reports_missing_task_file(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_sdd_project(project)
    spec_dir = project / "specs/001-demo"
    (spec_dir / "plans/01-foundation").mkdir(parents=True)
    (spec_dir / "plans/01-foundation/plan.md").write_text("# Plan\n")
    (spec_dir / "tree.json").write_text(
        json.dumps(
            {
                "spec": {"file": "spec.md"},
                "plans": [
                    {
                        "id": "plan-1",
                        "number": 1,
                        "title": "Plan",
                        "file": "plans/01-foundation/plan.md",
                        "tasks": [
                            {
                                "id": "plan-1-task-1",
                                "number": 1,
                                "title": "Missing task file",
                                "file": "tasks/plan-1-task-1/task.md",
                            }
                        ],
                    }
                ],
            }
        )
    )
    client = _client(projects_root)

    response = client.get("/sdd/project", params={"workspace_path": str(project)})

    assert response.status_code == 200
    spec = response.json()["specs"][0]
    assert spec["traceability_status"] != "linked"
    assert "specs/001-demo/tasks/plan-1-task-1/task.md" in spec["missing"]
    assert spec["tree"]["complete"] is False


def test_sdd_project_tree_reports_plan_without_tasks(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_sdd_project(project)
    spec_dir = project / "specs/001-demo"
    (spec_dir / "plans/01-foundation").mkdir(parents=True)
    (spec_dir / "plans/01-foundation/plan.md").write_text("# Plan\n")
    (spec_dir / "tree.json").write_text(
        json.dumps(
            {
                "spec": {"file": "spec.md"},
                "plans": [
                    {
                        "id": "plan-1",
                        "number": 1,
                        "title": "Plan",
                        "file": "plans/01-foundation/plan.md",
                        "tasks": [],
                    }
                ],
            }
        )
    )
    client = _client(projects_root)

    response = client.get("/sdd/project", params={"workspace_path": str(project)})

    assert response.status_code == 200
    spec = response.json()["specs"][0]
    assert spec["traceability_status"] != "linked"
    assert "plan 1: tasks" in spec["missing"]
    assert spec["tree"]["complete"] is False


def test_sdd_project_rejects_traversal_and_symlink_escape(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    outside = tmp_path / "outside"
    _write_sdd_project(outside)
    symlink = projects_root / "linked-outside"
    symlink.symlink_to(outside, target_is_directory=True)

    client = _client(projects_root)

    outside_response = client.get(
        "/sdd/project",
        params={"workspace_path": str(outside)},
    )
    symlink_response = client.get(
        "/sdd/project",
        params={"workspace_path": str(symlink)},
    )

    assert outside_response.status_code == 400
    assert symlink_response.status_code == 400


def test_sdd_project_rejects_explicit_parent_traversal(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    outside = tmp_path / "outside"
    _write_sdd_project(outside)
    client = _client(projects_root)

    response = client.get(
        "/sdd/project",
        params={"workspace_path": "../outside"},
    )

    assert response.status_code == 400


def test_sdd_project_skips_architecture_dir_symlink_escape(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    outside = tmp_path / "outside"
    _write_sdd_project(project)
    _write_sdd_project(outside)
    _replace_with_symlink(project / "architecture", outside / "architecture")
    client = _client(projects_root)

    response = client.get("/sdd/project", params={"workspace_path": str(project)})
    projects = client.get("/sdd/projects")

    assert response.status_code == 200
    assert response.json()["architecture_diagrams"] == []
    assert projects.status_code == 200
    assert projects.json()["projects"][0]["diagram_count"] == 1


def test_sdd_project_skips_architecture_file_symlink_escape(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    outside = tmp_path / "outside"
    _write_sdd_project(project)
    outside.mkdir()
    outside_diagram = outside / "outside.mmd"
    outside_diagram.write_text("flowchart LR\nX --> Y\n")
    architecture_diagram = project / "architecture/context.mmd"
    architecture_diagram.unlink()
    architecture_diagram.symlink_to(outside_diagram)
    client = _client(projects_root)

    response = client.get("/sdd/project", params={"workspace_path": str(project)})
    diagrams = client.get(
        "/sdd/project/diagrams",
        params={"workspace_path": str(project)},
    )

    assert response.status_code == 200
    assert response.json()["architecture_diagrams"] == []
    assert diagrams.status_code == 200
    assert "architecture/context.mmd" not in {
        item["path"] for item in diagrams.json()["diagrams"]
    }


def test_sdd_project_skips_specs_root_symlink_escape(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    outside = tmp_path / "outside"
    _write_sdd_project(project)
    _write_sdd_project(outside)
    _replace_with_symlink(project / "specs", outside / "specs")
    client = _client(projects_root)

    response = client.get("/sdd/project", params={"workspace_path": str(project)})
    projects = client.get("/sdd/projects")

    assert response.status_code == 200
    assert response.json()["specs"] == []
    assert "specs/<feature>/spec.md" in response.json()["missing_required"]
    assert projects.status_code == 200
    assert projects.json()["projects"][0]["spec_count"] == 0


def test_sdd_project_skips_feature_dir_symlink_escape(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    outside = tmp_path / "outside"
    _write_sdd_project(project)
    _write_sdd_project(outside)
    feature_dir = project / "specs/001-demo"
    _replace_with_symlink(feature_dir, outside / "specs/001-demo")
    client = _client(projects_root)

    response = client.get("/sdd/project", params={"workspace_path": str(project)})

    assert response.status_code == 200
    assert response.json()["specs"] == []
    assert "specs/<feature>/spec.md" in response.json()["missing_required"]


def test_sdd_project_skips_archived_spec_directories(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_sdd_project(project)
    archived = project / "specs/_archive-002-old-factory"
    archived.mkdir()
    (archived / "spec.md").write_text("# Archived Factory Spec\n")
    (archived / "plan.md").write_text("# Archived Plan\n")
    (archived / "tasks.md").write_text("# Archived Tasks\n")
    client = _client(projects_root)

    response = client.get("/sdd/project", params={"workspace_path": str(project)})
    projects = client.get("/sdd/projects")

    assert response.status_code == 200
    assert [spec["id"] for spec in response.json()["specs"]] == ["001-demo"]
    assert projects.status_code == 200
    assert projects.json()["projects"][0]["spec_count"] == 1


def test_sdd_project_allows_known_workspace_alias_outside_projects_root(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    alias_project = tmp_path / "external-demo"
    _write_sdd_project(alias_project)
    client = _client(
        projects_root,
        feedback_source_workspace_aliases=f"external-demo:{alias_project}",
    )

    response = client.get(
        "/sdd/project",
        params={"workspace_path": "external-demo"},
    )

    assert response.status_code == 200
    assert response.json()["workspace_path"] == str(alias_project.resolve())


def test_sdd_project_handles_whitespace_only_mermaid_diagrams(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_sdd_project(project)
    (project / "architecture/context.mmd").write_text(" \n\t\n")
    client = _client(projects_root)

    snapshot = client.get("/sdd/project", params={"workspace_path": str(project)})
    diagrams = client.get(
        "/sdd/project/diagrams",
        params={"workspace_path": str(project)},
    )
    projects = client.get("/sdd/projects")

    assert snapshot.status_code == 200
    assert snapshot.json()["architecture_diagrams"][0]["diagram_type"] == "unknown"
    assert diagrams.status_code == 200
    assert diagrams.json()["diagrams"][0]["diagram_type"] == "unknown"
    assert projects.status_code == 200
    assert projects.json()["projects"][0]["diagram_count"] == 2


def test_sdd_project_discovers_rendered_svg_diagrams_with_metadata(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_sdd_project(project)
    svg_path = project / "specs/001-demo/diagrams/browser-gateway.svg"
    svg_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 40">'
        '<g id="node-browser" data-node-id="browser"></g>'
        '<path id="connector-browser_gateway" '
        'data-connection-id="browser_gateway" d="M0 0 L10 10"/>'
        "</svg>\n"
    )
    (project / "specs/001-demo/diagrams/browser-gateway.yaml").write_text(
        "\n".join(
            [
                "diagram_id: browser-gateway",
                "diagram_type: uml-component-svg",
                "title: Browser Gateway",
                "source_format: svg",
                "rendered_format: svg",
                "renderer: diagram-mcp-rendering-engine",
                "source: specs/001-demo/diagrams/browser-gateway.svg",
            ]
        )
        + "\n"
    )
    (project / "specs/001-demo/diagrams/arbitrary.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"></svg>\n'
    )
    client = _client(projects_root)

    response = client.get("/sdd/project/diagrams", params={"workspace_path": str(project)})

    assert response.status_code == 200
    diagrams = response.json()["diagrams"]
    svg = next(
        item
        for item in diagrams
        if item["path"] == "specs/001-demo/diagrams/browser-gateway.svg"
    )
    assert svg["title"] == "Browser Gateway"
    assert svg["diagram_id"] == "browser-gateway"
    assert svg["spec_id"] == "001-demo"
    assert svg["source_format"] == "svg"
    assert svg["rendered_format"] == "svg"
    assert svg["content_type"].startswith("image/svg+xml")
    assert svg["digest"]
    assert svg["updated_at"]
    assert svg["metadata_path"] == "specs/001-demo/diagrams/browser-gateway.yaml"
    assert svg["renderer"] == "diagram-mcp-rendering-engine"
    assert "data-node-id=\"browser\"" in svg["content"]
    assert "specs/001-demo/diagrams/arbitrary.svg" not in {
        item["path"] for item in diagrams
    }


def test_sdd_project_serves_only_safe_rendered_svg_assets(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_sdd_project(project)
    svg_path = project / "specs/001-demo/diagrams/component.svg"
    svg_path.write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>\n')
    (project / "specs/001-demo/diagrams/component.yaml").write_text(
        "diagram_id: component\nsource_format: svg\nrendered_format: svg\n"
    )
    unsafe_path = project / "specs/001-demo/diagrams/unsafe.svg"
    unsafe_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>\n'
    )
    (project / "specs/001-demo/diagrams/unsafe.yaml").write_text(
        "diagram_id: unsafe\nsource_format: svg\nrendered_format: svg\n"
    )
    client = _client(projects_root)

    ok = client.get(
        "/sdd/project/diagrams/asset",
        params={
            "workspace_path": str(project),
            "diagram_path": "specs/001-demo/diagrams/component.svg",
        },
    )
    traversal = client.get(
        "/sdd/project/diagrams/asset",
        params={
            "workspace_path": str(project),
            "diagram_path": "../outside.svg",
        },
    )
    unsafe = client.get(
        "/sdd/project/diagrams/asset",
        params={
            "workspace_path": str(project),
            "diagram_path": "specs/001-demo/diagrams/unsafe.svg",
        },
    )

    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("image/svg+xml")
    assert ok.headers["etag"]
    assert ok.text.startswith("<svg")
    assert traversal.status_code == 404
    assert unsafe.status_code == 404


def test_sdd_project_persists_rendered_diagram_exports(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_sdd_project(project)
    client = _client(projects_root)

    response = client.post(
        "/sdd/project/diagrams/rendered-export",
        json={
            "workspace_path": str(project),
            "spec_id": "001-demo",
            "diagram_id": "browser gateway",
            "title": "Browser Gateway",
            "diagram_type": "uml-component-svg",
            "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"></svg>',
            "renderer": "diagram-mcp-rendering-engine",
            "diagram_spec_id": "diagram_123",
        },
    )
    unsafe = client.post(
        "/sdd/project/diagrams/rendered-export",
        json={
            "workspace_path": str(project),
            "spec_id": "001-demo",
            "diagram_id": "../escape",
            "diagram_type": "uml-component-svg",
            "svg": '<svg xmlns="http://www.w3.org/2000/svg"><script>x</script></svg>',
        },
    )

    assert response.status_code == 200
    diagram = response.json()["diagram"]
    assert diagram["path"] == "specs/001-demo/diagrams/browser-gateway.svg"
    assert diagram["metadata_path"] == "specs/001-demo/diagrams/browser-gateway.yaml"
    assert diagram["renderer"] == "diagram-mcp-rendering-engine"
    assert (project / "specs/001-demo/diagrams/browser-gateway.svg").is_file()
    assert "diagram_spec_id: diagram_123" in (
        project / "specs/001-demo/diagrams/browser-gateway.yaml"
    ).read_text()
    assert unsafe.status_code == 400


def test_sdd_project_reports_oversized_allowed_files_without_content(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_sdd_project(project)
    (project / "architecture/context.mmd").write_text("flowchart LR\nA --> B\n")
    client = _client(projects_root, sdd_file_max_bytes=8)

    response = client.get("/sdd/project", params={"workspace_path": str(project)})

    assert response.status_code == 200
    diagram = response.json()["architecture_diagrams"][0]
    assert diagram["path"] == "architecture/context.mmd"
    assert diagram["content"] is None
    assert diagram["error"] == "file_too_large"


def test_sdd_projects_listing_survives_unreadable_optional_files(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    first = projects_root / "first"
    second = projects_root / "second"
    _write_sdd_project(first)
    _write_sdd_project(second)
    unreadable = first / "architecture/context.mmd"
    unreadable.chmod(0)
    oversized = first / "specs/001-demo/diagrams/oversized.mmd"
    oversized.write_text("flowchart LR\n" + ("A --> B\n" * 1000))
    try:
        client = _client(projects_root, sdd_file_max_bytes=8)

        response = client.get("/sdd/projects")

        assert response.status_code == 200
        names = {project["workspace_name"] for project in response.json()["projects"]}
        assert names == {"first", "second"}
    finally:
        unreadable.chmod(0o644)


def test_sdd_doctor_reports_contract_json(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_sdd_project(project)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/codex_bridge_sdd_doctor.py",
            "--workspace",
            str(project),
            "--projects-root",
            str(projects_root),
            "--json",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert {check["name"] for check in payload["checks"]} >= {
        "manifest",
        "constitution",
        "specs",
        "diagrams",
    }


def test_sdd_doctor_endpoint_reports_summary(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_sdd_project(project)
    client = _client(projects_root)

    response = client.get("/sdd/doctor", params={"workspace_path": str(project)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "codex.sddDoctorReport"
    assert payload["workspace"] == str(project.resolve())
    assert payload["ok"] is True
    assert {check["name"] for check in payload["checks"]} >= {
        "manifest",
        "constitution",
        "specs",
        "diagrams",
    }


def _client(projects_root: Path, **overrides: object) -> TestClient:
    overrides.setdefault("feedback_source_workspace_aliases", "")
    settings = Settings(
        codex_command="python3 tests/fixtures/fake_codex.py",
        codex_use_exec=False,
        projects_root=str(projects_root),
        chat_store_backend="memory",
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
        audio_transcription_backend="disabled",
        speech_synthesis_backend="disabled",
        **overrides,
    )
    return TestClient(create_app(settings))


def _write_sdd_project(project: Path) -> None:
    (project / ".specify/memory").mkdir(parents=True)
    (project / "architecture").mkdir(parents=True)
    (project / "specs/001-demo/diagrams").mkdir(parents=True)
    (project / "specs/001-demo/slices").mkdir(parents=True)
    (project / "codex-bridge.yaml").write_text(
        "kind: codex.bridge.project\nversion: 1\n"
    )
    (project / ".specify/memory/constitution.md").write_text("# Constitution\n")
    (project / "architecture/context.mmd").write_text("flowchart LR\nA --> B\n")
    (project / "specs/001-demo/spec.md").write_text("# Demo Spec\n")
    (project / "specs/001-demo/plan.md").write_text("# Demo Plan\n")
    (project / "specs/001-demo/tasks.md").write_text("# Demo Tasks\n")
    (project / "specs/001-demo/plans").mkdir()
    (project / "specs/001-demo/tasks").mkdir()
    (project / "specs/001-demo/plan-review.md").write_text("# Review Plan\n")
    (project / "specs/001-demo/tasks-review.md").write_text("# Review Tasks\n")
    (project / "specs/001-demo/plans/02-implementation.md").write_text(
        "# Implementation Plan\n"
    )
    (project / "specs/001-demo/tasks/02-implementation.md").write_text(
        "# Implementation Tasks\n"
    )
    (project / "specs/001-demo/slices/01-demo-slice.md").write_text("# Demo Slice\n")
    (project / "specs/001-demo/diagrams/sequence.mmd").write_text(
        "sequenceDiagram\nA->>B: hi\n"
    )


def _replace_with_symlink(path: Path, target: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)
    path.symlink_to(target, target_is_directory=True)
