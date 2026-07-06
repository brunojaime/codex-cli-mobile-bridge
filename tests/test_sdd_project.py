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
