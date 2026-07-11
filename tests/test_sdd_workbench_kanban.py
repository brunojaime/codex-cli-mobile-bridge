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
    assert cards["spec-task:001-demo:T001"]["updatedAt"] == "2026-07-09T12:03:00Z"
    assert cards["spec-task:001-demo:T002"]["column"] == "ready"
    assert cards["spec-task:001-demo:T003"]["column"] == "backlog"
    assert cards["review-finding:reviews-review-notes.md"]["column"] == "review"
    assert cards["review-finding:reviews-review-notes.md"]["inferred"] is True
    assert cards["run-step:release:preview-runtime"]["column"] == "review"
    assert (project_path / ".codex/workbench-kanban").is_dir()
    assert first["latestUpdate"]["summary"]
    history = service.history(workspace=project_path)
    assert history["count"] == 1


def test_kanban_projection_treats_tree_done_as_authoritative_completion(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project_path = projects_root / "demo"
    _write_kanban_project(project_path)
    spec_dir = project_path / "specs/001-demo"
    (spec_dir / "tasks.md").write_text(
        textwrap.dedent(
            """\
            # Tasks
            - [ ] T001 Define board contract
            - [ ] T002 Build board API
            - [ ] T003 Render Flutter board
            """
        ),
        encoding="utf-8",
    )
    tree_path = spec_dir / "tree.json"
    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    for plan in tree["plans"]:
        plan["status"] = "done"
        for task in plan["tasks"]:
            task["status"] = "done"
    tree_path.write_text(json.dumps(tree), encoding="utf-8")
    project_service = SddProjectService(projects_root=str(projects_root))
    project = project_service.get_project(str(project_path))
    service = SddWorkbenchKanbanService(projects_root=projects_root)

    payload = service.build_board(workspace=project_path, project=project).payload

    cards = {
        card["id"]: card
        for card in payload["board"]["cards"]
        if card["scopeId"] == "001-demo"
    }
    assert cards["spec-task:001-demo:T001"]["column"] == "done"
    assert cards["spec-task:001-demo:T002"]["column"] == "done"
    assert cards["spec-task:001-demo:T003"]["column"] == "done"
    assert cards["plan-phase:001-demo:1"]["column"] == "done"
    assert cards["plan-phase:001-demo:2"]["column"] == "done"


def test_kanban_spec_scope_excludes_workspace_observer_cards(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project_path = projects_root / "demo"
    _write_kanban_project(project_path)
    project_service = SddProjectService(projects_root=str(projects_root))
    project = project_service.get_project(str(project_path))
    service = SddWorkbenchKanbanService(projects_root=projects_root)

    payload = service.build_board(
        workspace=project_path,
        project=project,
        spec_id="001-demo",
    ).payload

    cards = {card["id"]: card for card in payload["board"]["cards"]}
    assert "review-finding:reviews-review-notes.md" not in cards
    assert "run-step:release:preview-runtime" not in cards
    assert {card["scopeId"] for card in cards.values()} == {"001-demo"}


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
        original_tasks.replace(
            "- [ ] T002 Build board API", "- [x] T002 Build board API"
        ),
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
        (project_path / "specs/001-demo/tasks.md")
        .read_text(encoding="utf-8")
        .startswith("# Tasks")
    )
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
        params={
            "workspace_path": str(project_path),
            "scope_id": payload["scope"]["id"],
        },
    )
    assert history_response.status_code == 200
    assert history_response.json()["count"] == 1

    detail_response = client.get(
        f"/sdd/workbench/kanban/history/{update_id}",
        params={
            "workspace_path": str(project_path),
            "scope_id": payload["scope"]["id"],
        },
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["update"]["id"] == update_id

    scopes_response = client.get(
        "/sdd/workbench/kanban/scopes",
        params={"workspace_path": str(project_path)},
    )
    assert scopes_response.status_code == 200
    scopes_payload = scopes_response.json()
    assert scopes_payload["kind"] == "codex.sddWorkbenchKanbanScopes"
    assert {
        "workspace_spec",
        "workspace",
    }.issubset({scope["type"] for scope in scopes_payload["scopes"]})
    assert any(scope.get("specId") == "001-demo" for scope in scopes_payload["scopes"])


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


def test_kanban_scope_index_lists_workspace_factory_and_generated_scopes(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project_path = projects_root / "demo"
    generated_path = projects_root / "generated-demo"
    _write_kanban_project(project_path)
    generated_path.mkdir(parents=True)
    project_service = SddProjectService(projects_root=str(projects_root))
    project = project_service.get_project(str(project_path))
    service = SddWorkbenchKanbanService(
        projects_root=projects_root,
        project_factory_service=_FakeProjectFactoryService(target_path=generated_path),
    )

    payload = service.build_scopes(workspace=project_path, project=project)

    scopes = {scope["id"]: scope for scope in payload["scopes"]}
    assert payload["scopes"][0]["id"] == "project-factory:job:job-1"
    assert payload["defaultScopeId"] == "project-factory:job:job-1"
    assert scopes[f"workspace:{project.workspace_path}"]["type"] == "workspace"
    assert scopes[f"workspace:{project.workspace_path}:spec:001-demo"] == {
        "id": f"workspace:{project.workspace_path}:spec:001-demo",
        "type": "workspace_spec",
        "group": "specs",
        "title": "Demo Spec",
        "workspacePath": project.workspace_path,
        "specId": "001-demo",
        "status": "in_progress",
        "detail": "specs/001-demo",
        "priority": 401,
        "createdAt": "2026-07-08T12:00:00Z",
        "updatedAt": "2026-07-09T12:03:00Z",
    }
    assert scopes["project-factory:draft:draft-1"]["type"] == "project_factory_draft"
    assert scopes["project-factory:job:job-1"]["jobId"] == "job-1"
    assert scopes[f"workspace:{generated_path.resolve()}"]["type"] == (
        "generated_workspace"
    )

    factory_only = service.build_scopes()
    assert factory_only["defaultScopeId"] == "project-factory:job:job-1"


def test_kanban_scope_index_defaults_to_latest_workspace_spec(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project_path = projects_root / "demo"
    _write_kanban_project(project_path)
    _write_kanban_spec(
        project_path,
        spec_id="002-latest",
        title="Latest Spec",
        created_at="2026-07-09T09:00:00Z",
        updated_at="2026-07-10T12:03:00Z",
    )
    project_service = SddProjectService(projects_root=str(projects_root))
    project = project_service.get_project(str(project_path))
    service = SddWorkbenchKanbanService(projects_root=projects_root)

    payload = service.build_scopes(workspace=project_path, project=project)

    assert (
        payload["defaultScopeId"]
        == f"workspace:{project.workspace_path}:spec:002-latest"
    )
    assert payload["defaultScopeId"] != f"workspace:{project.workspace_path}"
    scopes = {scope["id"]: scope for scope in payload["scopes"]}
    latest_scope = scopes[f"workspace:{project.workspace_path}:spec:002-latest"]
    assert latest_scope["type"] == "workspace_spec"
    assert latest_scope["updatedAt"] == "2026-07-10T12:03:00Z"


def test_kanban_scope_index_ignores_historical_project_factory_job_for_default(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project_path = projects_root / "demo"
    _write_kanban_project(project_path)
    _write_kanban_spec(
        project_path,
        spec_id="002-latest",
        title="Latest Spec",
        created_at="2026-07-09T09:00:00Z",
        updated_at="2026-07-10T12:03:00Z",
    )
    project_service = SddProjectService(projects_root=str(projects_root))
    project = project_service.get_project(str(project_path))
    service = SddWorkbenchKanbanService(
        projects_root=projects_root,
        project_factory_service=_FakeProjectFactoryService(
            include_draft=False,
            job_status="ready",
            job_message="",
            job_error="",
            job_current_phase="",
        ),
    )

    payload = service.build_scopes(workspace=project_path, project=project)

    assert (
        payload["defaultScopeId"]
        == f"workspace:{project.workspace_path}:spec:002-latest"
    )
    scopes = {scope["id"]: scope for scope in payload["scopes"]}
    assert scopes["project-factory:job:job-1"]["group"] == "history"


def test_kanban_scope_index_keeps_active_creation_jobs_as_default(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project_path = projects_root / "demo"
    _write_kanban_project(project_path)
    _write_kanban_spec(
        project_path,
        spec_id="002-latest",
        title="Latest Spec",
        created_at="2026-07-09T09:00:00Z",
        updated_at="2026-07-10T12:03:00Z",
    )
    project_service = SddProjectService(projects_root=str(projects_root))
    project = project_service.get_project(str(project_path))

    for status in ("queued", "running", "blocked"):
        service = SddWorkbenchKanbanService(
            projects_root=projects_root,
            project_factory_service=_FakeProjectFactoryService(
                include_draft=False,
                job_status=status,
            ),
        )

        payload = service.build_scopes(workspace=project_path, project=project)

        assert payload["defaultScopeId"] == "project-factory:job:job-1"
        scopes = {scope["id"]: scope for scope in payload["scopes"]}
        assert scopes["project-factory:job:job-1"]["group"] == "creating"


def test_kanban_scope_index_latest_spec_tie_breaks_by_updated_created_and_id(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project_path = projects_root / "demo"
    _write_kanban_project(project_path)
    _write_kanban_spec(
        project_path,
        spec_id="002-created-only",
        title="Created Only",
        created_at="2026-07-10T12:03:00Z",
        updated_at=None,
    )
    _write_kanban_spec(
        project_path,
        spec_id="003-updated",
        title="Updated",
        created_at="2026-07-01T09:00:00Z",
        updated_at="2026-07-11T12:03:00Z",
    )
    _write_kanban_spec(
        project_path,
        spec_id="004-alpha",
        title="Alpha Tie",
        created_at="2026-07-12T12:03:00Z",
        updated_at=None,
    )
    _write_kanban_spec(
        project_path,
        spec_id="005-zeta",
        title="Zeta Tie",
        created_at="2026-07-12T12:03:00Z",
        updated_at=None,
    )
    project_service = SddProjectService(projects_root=str(projects_root))
    service = SddWorkbenchKanbanService(projects_root=projects_root)

    payload = service.build_scopes(
        workspace=project_path,
        project=project_service.get_project(str(project_path)),
    )

    assert payload["defaultScopeId"].endswith(":spec:005-zeta")


def test_kanban_scheduler_refreshes_active_scope_from_source_changes(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project_path = projects_root / "demo"
    _write_kanban_project(project_path)
    project_service = SddProjectService(projects_root=str(projects_root))
    service = SddWorkbenchKanbanService(projects_root=projects_root)

    first = service.build_board(
        workspace=project_path,
        project=project_service.get_project(str(project_path)),
    ).payload
    idle = service.run_scheduled_refreshes()

    assert idle["counts"]["refreshed"] == 0
    assert idle["skipped"][0]["reason"] == "not_due"

    tasks_path = project_path / "specs/001-demo/tasks.md"
    tasks_path.write_text(
        tasks_path.read_text(encoding="utf-8").replace(
            "- [ ] T002 Build board API",
            "- [x] T002 Build board API",
        ),
        encoding="utf-8",
    )
    refreshed = service.run_scheduled_refreshes(debounce_seconds=0)

    assert refreshed["counts"]["refreshed"] == 1
    assert refreshed["refreshed"][0]["reason"] == "source_changed"
    cache_path = next(
        (project_path / ".codex/workbench-kanban").glob("workspace-*/board-cache.json")
    )
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cache["board"]["snapshotId"] != first["board"]["snapshotId"]
    cards = {card["id"]: card for card in cache["board"]["cards"]}
    assert cards["spec-task:001-demo:T002"]["column"] == "done"


def test_kanban_preserves_project_factory_history_when_workspace_appears(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project_path = projects_root / "demo"
    _write_kanban_project(project_path)
    project_service = SddProjectService(projects_root=str(projects_root))
    service = SddWorkbenchKanbanService(
        projects_root=projects_root,
        project_factory_service=_FakeProjectFactoryService(target_path=project_path),
    )

    before_workspace = service.build_board(draft_id="draft-1", job_id="job-1").payload
    before_update_id = before_workspace["latestUpdate"]["id"]
    after_workspace = service.build_board(
        workspace=project_path,
        project=project_service.get_project(str(project_path)),
        draft_id="draft-1",
        job_id="job-1",
    ).payload

    assert {
        "fromScope": "project-factory:job:job-1",
        "toScope": f"workspace:{project_path}",
        "status": "history_migrated",
        "marker": "project_factory_history_continuity",
    } in after_workspace["continuity"]
    history = service.history(
        workspace=project_path,
        scope_id="project-factory:job:job-1",
    )
    history_ids = {item["id"] for item in history["history"]}
    assert before_update_id in history_ids


def test_kanban_generated_workspace_context_pack_matches_factory_scope(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project_path = projects_root / "demo"
    _write_kanban_project(project_path)
    factory_dir = project_path / ".codex/factory"
    factory_dir.mkdir(parents=True)
    (factory_dir / "init-result.json").write_text(
        json.dumps(
            {
                "kind": "codex.projectFactoryInitResult",
                "draftId": "draft-1",
                "initJobId": "job-1",
                "sourceApp": "demo",
                "workspacePath": str(project_path),
                "workbenchScopeId": f"workspace:{project_path}",
                "blockedWithContext": True,
                "resources": {
                    "cloudflarePreview": {
                        "previewUrl": "https://preview.nienfos.com/demo",
                        "apiBaseUrl": "https://preview.nienfos.com/demo/api",
                    }
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (factory_dir / "llm-start-context.md").write_text(
        "# Deterministic Init Context\n",
        encoding="utf-8",
    )
    project_service = SddProjectService(projects_root=str(projects_root))
    service = SddWorkbenchKanbanService(
        projects_root=projects_root,
        project_factory_service=_FakeProjectFactoryService(target_path=project_path),
    )

    payload = service.build_board(
        workspace=project_path,
        project=project_service.get_project(str(project_path)),
        draft_id="draft-1",
        job_id="job-1",
    ).payload

    cards = {card["id"]: card for card in payload["board"]["cards"]}
    assert payload["scope"]["workspacePath"] == str(project_path.resolve())
    assert cards["spec-task:001-demo:T002"]["column"] == "ready"
    phase_card = cards["project-factory:job:job-1:phase:android_preview_release"]
    assert phase_card["column"] == "blocked"
    assert phase_card["manualCommands"] == [
        "bash",
        "scripts/publish_android_preview_release.sh",
    ]
    assert {
        "fromScope": "project-factory:job:job-1",
        "toScope": f"workspace:{project_path}",
        "status": "mapped",
        "marker": "generated_repository_exists",
    } in payload["continuity"]


class _FakeProjectFactoryService:
    def __init__(
        self,
        *,
        target_path: Path | None = None,
        include_draft: bool = True,
        draft_status: str = "valid",
        job_status: str = "blocked",
        job_message: str = "Release upload failed",
        job_error: str = "Missing GH token",
        job_current_phase: str = "android_preview_release",
    ) -> None:
        self._target_path = str(target_path) if target_path is not None else ""
        self._include_draft = include_draft
        self._draft_status = draft_status
        self._job_status = job_status
        self._job_message = job_message
        self._job_error = job_error
        self._job_current_phase = job_current_phase

    def list_drafts(self, *, limit: int = 50):
        if not self._include_draft:
            return ()
        return (
            {
                "draft_id": "draft-1",
                "name": "Demo App",
                "status": self._draft_status,
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
                "status": self._job_status,
                "current_phase": self._job_current_phase,
                "message": self._job_message,
                "error": self._job_error,
                "target_path": self._target_path,
                "project_path": self._target_path,
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
    (spec_dir / "metadata.yaml").write_text(
        textwrap.dedent(
            """\
            status: active
            created_at: 2026-07-08T12:00:00Z
            updated_at: 2026-07-09T12:03:00Z
            tasks:
              total: 3
              completed: 1
              pending: 2
            """
        ),
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


def _write_kanban_spec(
    project: Path,
    *,
    spec_id: str,
    title: str,
    created_at: str,
    updated_at: str | None,
) -> None:
    spec_dir = project / f"specs/{spec_id}"
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(f"# {title}\n", encoding="utf-8")
    metadata = [
        f"title: {title}",
        "status: active",
        f"created_at: {created_at}",
    ]
    if updated_at is not None:
        metadata.append(f"updated_at: {updated_at}")
    metadata.extend(
        [
            "tasks:",
            "  total: 1",
            "  completed: 0",
            "  pending: 1",
            "",
        ]
    )
    (spec_dir / "metadata.yaml").write_text(
        "\n".join(metadata),
        encoding="utf-8",
    )
    (spec_dir / "tasks.md").write_text(
        "# Tasks\n- [ ] T001 Keep latest canvas scoped\n",
        encoding="utf-8",
    )
