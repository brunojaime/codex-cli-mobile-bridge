from __future__ import annotations

import json
import textwrap
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.application.services.sdd_project_service import SddProjectService
from backend.app.application.services.sdd_workbench_kanban_service import (
    SddWorkbenchKanbanService,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.main import create_app


def test_kanban_projection_maps_tasks_deterministically_and_persists_history(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project_path = projects_root / "demo"
    _write_kanban_project(project_path)
    project_service = SddProjectService(projects_root=str(projects_root))
    project = project_service.get_project(str(project_path))
    service = SddWorkbenchKanbanService(projects_root=projects_root)

    first = service.build_board(workspace=project_path, project=project).payload
    second = service.build_board(workspace=project_path, project=project).payload

    assert first["board"]["snapshotId"] == second["board"]["snapshotId"]
    assert second["historySummary"]["noOp"] is True
    cards = {card["id"]: card for card in first["board"]["cards"]}
    assert cards["spec-task:001-demo:T001"]["column"] == "done"
    assert cards["spec-task:001-demo:T001"]["confirmed"] is True
    assert cards["spec-task:001-demo:T002"]["column"] == "ready"
    assert cards["spec-task:001-demo:T003"]["column"] == "backlog"
    assert cards["review-finding:reviews-review-notes.md"]["column"] == "review"
    assert cards["review-finding:reviews-review-notes.md"]["inferred"] is True
    assert cards["run-step:release:preview-runtime"]["column"] == "review"
    assert (project_path / ".codex/workbench-kanban").is_dir()
    assert first["latestUpdate"]["summary"]
    history = service.history(workspace=project_path)
    assert history["count"] == 1


def test_kanban_delta_records_task_moves_without_mutating_sdd_artifacts(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project_path = projects_root / "demo"
    _write_kanban_project(project_path)
    original_tasks = (project_path / "specs/001-demo/tasks.md").read_text(
        encoding="utf-8",
    )
    project_service = SddProjectService(projects_root=str(projects_root))
    service = SddWorkbenchKanbanService(projects_root=projects_root)
    service.build_board(
        workspace=project_path,
        project=project_service.get_project(str(project_path)),
    )
    (project_path / "specs/001-demo/tasks.md").write_text(
        original_tasks.replace("- [ ] T002 Build board API", "- [x] T002 Build board API"),
        encoding="utf-8",
    )

    moved = service.build_board(
        workspace=project_path,
        project=project_service.get_project(str(project_path)),
    ).payload

    assert {
        "cardId": "spec-task:001-demo:T002",
        "from": "ready",
        "to": "done",
    } in moved["board"]["delta"]["movedCards"]
    assert (
        project_path / "specs/001-demo/tasks.md"
    ).read_text(encoding="utf-8").startswith("# Tasks")
    assert "workbench-kanban" not in (
        project_path / "specs/001-demo/tasks.md"
    ).read_text(encoding="utf-8")


def test_kanban_api_returns_board_refresh_and_history(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project_path = projects_root / "demo"
    _write_kanban_project(project_path)
    client = _client(projects_root)

    response = client.get(
        "/sdd/workbench/kanban",
        params={"workspace_path": str(project_path), "spec_id": "001-demo"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "codex.sddWorkbenchKanban"
    assert payload["scope"]["type"] == "workspace_spec"
    assert payload["board"]["refresh"]["pollingFallbackSeconds"] == 30
    assert payload["curator"]["readOnly"] is True
    update_id = payload["latestUpdate"]["id"]

    history_response = client.get(
        "/sdd/workbench/kanban/history",
        params={"workspace_path": str(project_path), "scope_id": payload["scope"]["id"]},
    )
    assert history_response.status_code == 200
    assert history_response.json()["count"] == 1

    detail_response = client.get(
        f"/sdd/workbench/kanban/history/{update_id}",
        params={"workspace_path": str(project_path), "scope_id": payload["scope"]["id"]},
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["update"]["id"] == update_id


def test_kanban_observes_project_factory_scope_without_workspace(
    tmp_path: Path,
) -> None:
    service = SddWorkbenchKanbanService(
        projects_root=tmp_path,
        project_factory_service=_FakeProjectFactoryService(),
    )

    payload = service.build_board(draft_id="draft-1", job_id="job-1").payload

    cards = {card["id"]: card for card in payload["board"]["cards"]}
    assert payload["scope"]["type"] == "project_factory_job"
    assert cards["project-factory:draft:draft-1"]["column"] == "ready"
    assert cards["project-factory:job:job-1"]["column"] == "blocked"
    phase_card = cards["project-factory:job:job-1:phase:android_preview_release"]
    assert phase_card["column"] == "blocked"
    assert phase_card["manualCommands"] == [
        "bash",
        "scripts/publish_android_preview_release.sh",
    ]


class _FakeProjectFactoryService:
    def list_drafts(self, *, limit: int = 50):
        return (
            {
                "draft_id": "draft-1",
                "name": "Demo App",
                "status": "valid",
                "ok": True,
                "primary_goal": "Book appointments",
                "first_release_mode": "preview",
            },
        )

    def list_jobs(self, *, limit: int = 50):
        return (
            {
                "job_id": "job-1",
                "draft_id": "draft-1",
                "name": "Demo App",
                "status": "blocked",
                "current_phase": "android_preview_release",
                "message": "Release upload failed",
                "error": "Missing GH token",
                "initial_preview_release": {
                    "phaseStatuses": {
                        "android_preview_release": {
                            "status": "blocked",
                            "message": "Missing GH token",
                            "command": [
                                "bash",
                                "scripts/publish_android_preview_release.sh",
                            ],
                        }
                    }
                },
            },
        )


def _client(projects_root: Path) -> TestClient:
    settings = Settings(
        codex_command="python3 tests/fixtures/fake_codex.py",
        codex_use_exec=False,
        projects_root=str(projects_root),
        chat_store_backend="memory",
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
        audio_transcription_backend="disabled",
        speech_synthesis_backend="disabled",
        project_factory_async_jobs=False,
        project_factory_publication_validation_mode="local",
    )
    return TestClient(create_app(settings))


def _write_kanban_project(project: Path) -> None:
    spec_dir = project / "specs/001-demo"
    (spec_dir / "tasks/plan-1-task-1").mkdir(parents=True)
    (spec_dir / "tasks/plan-1-task-2").mkdir(parents=True)
    (spec_dir / "tasks/plan-2-task-1").mkdir(parents=True)
    (project / ".specify/memory").mkdir(parents=True)
    (project / "reviews").mkdir(parents=True)
    (project / "release").mkdir(parents=True)
    (project / "codex-bridge.yaml").write_text(
        "kind: codex.bridge.project\nversion: 1\n",
        encoding="utf-8",
    )
    (project / ".specify/memory/constitution.md").write_text(
        "# Constitution\n",
        encoding="utf-8",
    )
    (spec_dir / "spec.md").write_text(
        "# Demo Spec\n",
        encoding="utf-8",
    )
    (spec_dir / "plan.md").write_text(
        "# Plan\n\n## Phase 1\n\n## Phase 2\n",
        encoding="utf-8",
    )
    (spec_dir / "tasks.md").write_text(
        textwrap.dedent(
            """\
            # Tasks
            - [x] T001 Define board contract
            - [ ] T002 Build board API
            - [ ] T003 Render Flutter board
            """
        ),
        encoding="utf-8",
    )
    (spec_dir / "tasks/plan-1-task-1/task.md").write_text("T001\n", encoding="utf-8")
    (spec_dir / "tasks/plan-1-task-2/task.md").write_text("T002\n", encoding="utf-8")
    (spec_dir / "tasks/plan-2-task-1/task.md").write_text("T003\n", encoding="utf-8")
    (spec_dir / "tree.json").write_text(
        json.dumps(
            {
                "spec": {"file": "spec.md"},
                "plans": [
                    {
                        "id": "plan-1",
                        "number": 1,
                        "title": "Backend",
                        "status": "planned",
                        "file": "plan.md",
                        "tasks": [
                            {
                                "id": "plan-1-task-1",
                                "number": 1,
                                "title": "T001 Define board contract",
                                "status": "completed",
                                "file": "tasks/plan-1-task-1/task.md",
                            },
                            {
                                "id": "plan-1-task-2",
                                "number": 2,
                                "title": "T002 Build board API",
                                "status": "planned",
                                "file": "tasks/plan-1-task-2/task.md",
                            },
                        ],
                    },
                    {
                        "id": "plan-2",
                        "number": 2,
                        "title": "Frontend",
                        "status": "planned",
                        "file": "plan.md",
                        "tasks": [
                            {
                                "id": "plan-2-task-1",
                                "number": 1,
                                "title": "T003 Render Flutter board",
                                "status": "planned",
                                "file": "tasks/plan-2-task-1/task.md",
                            }
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (project / "reviews/review-notes.md").write_text(
        "# Review\n\n- [ ] Finding: unresolved UI state.\n",
        encoding="utf-8",
    )
    (project / "release/preview-runtime.json").write_text(
        json.dumps(
            {
                "sourceApp": "demo",
                "previewUrl": "https://preview.nienfos.com/demo",
                "apiBaseUrl": "https://preview.nienfos.com/demo/api",
                "runtimeProfile": "preview",
                "releaseChannel": "prerelease",
                "releaseTagPattern": "android-preview-v*",
                "productionReady": False,
                "mockOrDemo": False,
            }
        ),
        encoding="utf-8",
    )
