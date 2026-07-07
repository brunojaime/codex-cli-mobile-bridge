from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.application.services.project_factory_manifest_service import (
    ProjectFactoryManifestInput,
    ProjectFactoryManifestService,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.main import create_app


def test_project_factory_options_exposes_ten_by_ten_creation_workflow(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)

    response = client.get("/project-factory/options")

    assert response.status_code == 200
    payload = response.json()
    assert payload["default_platforms"] == ["ios", "android", "web"]
    assert payload["default_backend"] == "fastapi"
    assert payload["creation_workflow"] == {
        "runner": "codex_cli",
        "mode": "generator_reviewer_batches",
        "generator_runs": 10,
        "reviewer_runs": 10,
    }


def test_project_factory_doctor_is_non_mutating_and_checks_defaults(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    response = client.get("/project-factory/doctor")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["status"] == "ready"
    assert payload["projects_root"] == str(tmp_path)
    checks = {item["code"]: item for item in payload["checks"]}
    assert checks["projects_root_exists"]["ok"] is True
    assert checks["projects_root_writable"]["ok"] is True
    assert checks["default_creation_workflow"]["ok"] is True
    assert checks["local_generator_available"]["ok"] is True
    toolchain = payload["toolchain"]
    assert toolchain["python"]["available"] is True
    assert toolchain["python"]["version"]
    assert "pytest" in toolchain
    assert "flutter" in toolchain
    assert "dart" in toolchain
    assert "codex_cli" in toolchain
    assert toolchain["codex_cli"]["available"] is True
    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert after == before


def test_project_factory_draft_and_dry_run_are_write_free(tmp_path: Path) -> None:
    client = _client(tmp_path)

    draft_response = client.post(
        "/project-factory/drafts",
        json={
            "name": "Clinica Norte",
            "businessType": "Turnos medicos",
            "primaryGoal": "Pacientes reservan turnos",
            "visualReferencePaths": ["assets/reference/uploaded/home.png"],
        },
    )

    assert draft_response.status_code == 200
    draft = draft_response.json()
    draft_id = draft["draft_id"]
    assert draft["manifest_plan"]["ok"] is True
    assert draft["manifest_plan"]["manifest"]["codex"]["creation_workflow"][
        "generator_runs"
    ] == 10
    assert not (tmp_path / "clinica-norte").exists()

    dry_run_response = client.post(f"/project-factory/drafts/{draft_id}/dry-run")

    assert dry_run_response.status_code == 200
    dry_run = dry_run_response.json()
    assert dry_run["ok"] is True
    assert dry_run["target_path"] == str(tmp_path / "clinica-norte")
    assert not (tmp_path / "clinica-norte").exists()


def test_project_factory_persists_draft_and_finished_job_across_clients(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    draft_id = _create_draft(client, "Clinica Norte")

    restarted_client = _client(tmp_path)
    dry_run_response = restarted_client.post(
        f"/project-factory/drafts/{draft_id}/dry-run",
    )

    assert dry_run_response.status_code == 200
    assert dry_run_response.json()["ok"] is True

    generate_response = restarted_client.post(
        f"/project-factory/drafts/{draft_id}/generate",
    )
    assert generate_response.status_code == 200
    job_id = generate_response.json()["job_id"]

    second_restart_client = _client(tmp_path)
    job_response = second_restart_client.get(f"/project-factory/jobs/{job_id}")

    assert job_response.status_code == 200
    recovered_job = job_response.json()
    assert recovered_job["status"] == "ready"
    assert recovered_job["generation_result"]["status"] == "ready"


def test_project_factory_lists_drafts_and_jobs_with_filters(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    draft_id = _create_draft(client, "Clinica Norte")
    generate_response = client.post(f"/project-factory/drafts/{draft_id}/generate")
    job = generate_response.json()

    drafts_response = client.get("/project-factory/drafts")
    draft_detail_response = client.get(f"/project-factory/drafts/{draft_id}")
    jobs_response = client.get("/project-factory/jobs")
    ready_jobs_response = client.get("/project-factory/jobs", params={"status": "ready"})
    draft_jobs_response = client.get(
        "/project-factory/jobs",
        params={"draft_id": draft_id, "limit": 1},
    )

    assert drafts_response.status_code == 200
    drafts = drafts_response.json()["drafts"]
    assert drafts[0]["draft_id"] == draft_id
    assert drafts[0]["name"] == "Clinica Norte"
    assert drafts[0]["slug"] == "clinica-norte"
    assert draft_detail_response.status_code == 200
    assert draft_detail_response.json()["draft_id"] == draft_id
    assert jobs_response.status_code == 200
    assert jobs_response.json()["jobs"][0]["job_id"] == job["job_id"]
    assert jobs_response.json()["jobs"][0]["project_path"] == str(
        tmp_path / "clinica-norte"
    )
    assert ready_jobs_response.json()["jobs"][0]["status"] == "ready"
    assert len(draft_jobs_response.json()["jobs"]) == 1


def test_project_factory_history_detail_404s_are_consistent(tmp_path: Path) -> None:
    client = _client(tmp_path)

    assert client.get("/project-factory/drafts/missing").status_code == 404
    assert client.get("/project-factory/jobs/missing").status_code == 404


def test_project_factory_recovers_running_job_as_interrupted(
    tmp_path: Path,
) -> None:
    state_dir = _state_dir(tmp_path)
    jobs_dir = state_dir / "jobs"
    jobs_dir.mkdir(parents=True)
    job_id = "pf-job-running001"
    jobs_dir.joinpath(f"{job_id}.json").write_text(
        _json_dumps(
            {
                "kind": "codex.projectFactoryJob.storage",
                "version": 1,
                "payload": {
                    "kind": "codex.projectFactoryJob",
                    "version": 1,
                    "job_id": job_id,
                    "draft_id": "pf-draft-running1",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:01Z",
                    "status": "running",
                    "current_step": "generator_batch",
                    "current_phase": "generator_batch",
                    "progress": 50,
                    "started_at": "2026-01-01T00:00:01Z",
                    "completed_at": None,
                    "error": None,
                    "project_path": None,
                    "message": "Generator running.",
                    "manifest_plan": _manifest_plan_payload(tmp_path, "Clinica Norte"),
                    "step_logs": [],
                },
            }
        ),
        encoding="utf-8",
    )

    response = _client(tmp_path).get(f"/project-factory/jobs/{job_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "interrupted"
    assert payload["current_phase"] == "interrupted"
    assert "backend restart" in payload["error"]
    assert payload["step_logs"][-1]["status"] == "interrupted"

    list_response = _client(tmp_path).get(
        "/project-factory/jobs",
        params={"status": "interrupted"},
    )
    assert list_response.status_code == 200
    listed = list_response.json()["jobs"]
    assert listed[0]["job_id"] == job_id
    assert listed[0]["manual_next_step"]


def test_project_factory_reference_asset_upload_is_listed_and_copied(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    draft_id = _create_draft(client, "Clinica Norte")
    asset_dir = _asset_dir(tmp_path)

    upload_response = client.post(
        f"/project-factory/drafts/{draft_id}/reference-assets",
        files={"asset": ("home.png", b"reference-image", "image/png")},
    )

    assert upload_response.status_code == 200
    asset = upload_response.json()
    assert asset["original_filename"] == "home.png"
    assert asset["content_type"] == "image/png"
    assert asset["size_bytes"] == len(b"reference-image")
    assert asset["storage_path"].startswith(f"{draft_id}/")
    assert (asset_dir / asset["storage_path"]).read_bytes() == b"reference-image"

    list_response = client.get(
        f"/project-factory/drafts/{draft_id}/reference-assets",
    )
    assert list_response.status_code == 200
    assert list_response.json()["assets"] == [asset]

    dry_run_response = client.post(f"/project-factory/drafts/{draft_id}/dry-run")
    reference_assets = dry_run_response.json()["manifest"]["visual_references"][
        "reference_assets"
    ]
    assert reference_assets[0]["id"] == asset["id"]
    assert reference_assets[0]["storage_path"] == asset["storage_path"]

    generate_response = client.post(f"/project-factory/drafts/{draft_id}/generate")

    assert generate_response.status_code == 200
    project = tmp_path / "clinica-norte"
    copied_images = list((project / "references/images").glob("*.png"))
    assert len(copied_images) == 1
    assert copied_images[0].read_bytes() == b"reference-image"
    index = (project / "references/reference-assets.md").read_text(
        encoding="utf-8",
    )
    assert "home.png" in index
    assert asset["id"] in index
    manifest = (project / ".codex/project.yaml").read_text(encoding="utf-8")
    assert "reference_assets:" in manifest
    assert asset["id"] in manifest


def test_project_factory_reference_asset_delete_removes_file_and_metadata(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    draft_id = _create_draft(client, "Catalogo Ropa")
    asset_dir = _asset_dir(tmp_path)
    upload_response = client.post(
        f"/project-factory/drafts/{draft_id}/reference-assets",
        files={"asset": ("catalog.webp", b"image", "image/webp")},
    )
    asset = upload_response.json()

    delete_response = client.delete(
        f"/project-factory/drafts/{draft_id}/reference-assets/{asset['id']}",
    )

    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
    assert not (asset_dir / asset["storage_path"]).exists()
    list_response = client.get(
        f"/project-factory/drafts/{draft_id}/reference-assets",
    )
    assert list_response.status_code == 200
    assert list_response.json()["assets"] == []


def test_project_factory_reference_asset_upload_validation(tmp_path: Path) -> None:
    client = _client(tmp_path)
    draft_id = _create_draft(client, "Resto Norte")

    invalid_type = client.post(
        f"/project-factory/drafts/{draft_id}/reference-assets",
        files={"asset": ("notes.txt", b"text", "text/plain")},
    )
    assert invalid_type.status_code == 422

    unsafe_name = client.post(
        f"/project-factory/drafts/{draft_id}/reference-assets",
        files={"asset": ("../outside.png", b"image", "image/png")},
    )
    assert unsafe_name.status_code == 422
    assert not (tmp_path.parent / "outside.png").exists()

    missing_draft = client.post(
        "/project-factory/drafts/pf-draft-000000000000/reference-assets",
        files={"asset": ("home.png", b"image", "image/png")},
    )
    assert missing_draft.status_code == 404


def test_project_factory_slug_traversal_is_blocked_without_writing_outside_root(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/project-factory/drafts",
        json={
            "name": "Unsafe",
            "businessType": "medical",
            "primaryGoal": "Do not write outside root",
            "slug": "../outside",
        },
    )

    assert response.status_code == 200
    plan = response.json()["manifest_plan"]
    assert plan["ok"] is False
    assert [error["code"] for error in plan["errors"]] == [
        "invalid_slug",
        "unsafe_target_path",
    ]
    assert not (tmp_path.parent / "outside").exists()


def test_project_factory_generate_creates_local_project_foundation(tmp_path: Path) -> None:
    client = _client(tmp_path)
    draft_response = client.post(
        "/project-factory/drafts",
        json={
            "name": "Catalogo Autos",
            "businessType": "autos",
            "primaryGoal": "Gestionar autos y consultas",
        },
    )
    draft_id = draft_response.json()["draft_id"]

    generate_response = client.post(f"/project-factory/drafts/{draft_id}/generate")

    assert generate_response.status_code == 200
    job = generate_response.json()
    assert job["status"] == "ready"
    assert job["current_step"] == "ready"
    assert job["current_phase"] == "ready"
    assert job["progress"] == 100
    assert job["completed_at"] is not None
    assert [entry["phase"] for entry in job["step_logs"]] == [
        "scaffold",
        "scaffold",
        "research_planning",
        "research_planning",
        "finalize_validation",
        "finalize_validation",
    ]
    assert job["step_logs"][-1]["command"] == [
        "bash",
        "scripts/validate_generated_project.sh",
    ]
    assert "validation skipped" in job["step_logs"][-1]["message"]
    assert job["generation_result"]["status"] == "ready"

    job_response = client.get(f"/project-factory/jobs/{job['job_id']}")
    assert job_response.status_code == 200
    assert job_response.json() == job

    project = tmp_path / "catalogo-autos"
    assert project.is_dir()
    assert (project / ".codex/project.yaml").is_file()
    assert (project / "AGENTS.md").is_file()
    assert (project / "README.md").is_file()
    assert (project / "specs/001-product-foundation/spec.md").is_file()
    assert (project / "specs/001-product-foundation/plan.md").is_file()
    assert (project / "specs/001-product-foundation/tasks.md").is_file()
    assert (project / "docs/research/typical-apps.md").is_file()
    assert (project / "design/tokens.yaml").is_file()
    assert (project / "infra/aws/deploy-plan.md").is_file()
    assert (project / "release/play-store-checklist.md").is_file()
    assert (project / ".git").is_dir() or job["generation_result"][
        "git_status"
    ] == "pending_git"

    manifest_text = (project / ".codex/project.yaml").read_text(encoding="utf-8")
    spec_text = (project / "specs/001-product-foundation/spec.md").read_text(
        encoding="utf-8",
    )
    assert "generator_runs: 10" in manifest_text
    assert "reviewer_runs: 10" in manifest_text
    assert "generator runs: 10" in spec_text
    assert "reviewer runs: 10" in spec_text
    assert "Nienfoadmin1994" not in _read_all_text(project)


def test_project_factory_generate_duplicate_returns_conflict(tmp_path: Path) -> None:
    client = _client(tmp_path)
    draft_id = _create_draft(client, "Duplicado Norte")

    first = client.post(f"/project-factory/drafts/{draft_id}/generate")
    second = client.post(f"/project-factory/drafts/{draft_id}/generate")

    assert first.status_code == 200
    assert second.status_code == 409
    assert "already exists" in second.json()["detail"]


def test_project_factory_existing_project_folder_blocks_without_overwrite(
    tmp_path: Path,
) -> None:
    project = tmp_path / "clinica-norte"
    project.mkdir()
    sentinel = project / "sentinel.txt"
    sentinel.write_text("keep me", encoding="utf-8")
    client = _client(tmp_path)
    draft_id = _create_draft(client, "Clinica Norte")

    response = client.post(f"/project-factory/drafts/{draft_id}/generate")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["error"] == "Manifest validation failed."
    assert sentinel.read_text(encoding="utf-8") == "keep me"
    assert not (project / ".codex").exists()


def test_project_factory_unknown_draft_and_job_return_404(tmp_path: Path) -> None:
    client = _client(tmp_path)

    assert client.post("/project-factory/drafts/missing/dry-run").status_code == 404
    assert client.post("/project-factory/drafts/missing/generate").status_code == 404
    assert client.get("/project-factory/jobs/missing").status_code == 404


def test_generated_project_is_discoverable_by_sdd_workbench(tmp_path: Path) -> None:
    client = _client(tmp_path)
    draft_response = client.post(
        "/project-factory/drafts",
        json={
            "name": "Turnos Medicos Norte",
            "businessType": "medical_appointments",
            "primaryGoal": "Pacientes reservan turnos",
        },
    )
    draft_id = draft_response.json()["draft_id"]

    generate_response = client.post(f"/project-factory/drafts/{draft_id}/generate")

    assert generate_response.status_code == 200
    project_path = tmp_path / "turnos-medicos-norte"
    projects_response = client.get("/sdd/projects")
    assert projects_response.status_code == 200
    projects = projects_response.json()["projects"]
    assert any(project["workspace_path"] == str(project_path) for project in projects)

    project_response = client.get(
        "/sdd/project",
        params={"workspace_path": str(project_path)},
    )
    assert project_response.status_code == 200
    project_payload = project_response.json()
    assert project_payload["workspace_path"] == str(project_path)
    assert project_payload["specs"][0]["id"] == "001-product-foundation"


def _client(projects_root: Path) -> TestClient:
    fake_codex = _fake_codex(projects_root)
    settings = Settings(
        projects_root=str(projects_root),
        chat_store_backend="memory",
        audio_transcription_backend="disabled",
        speech_synthesis_backend="disabled",
        project_factory_reference_asset_dir=str(_asset_dir(projects_root)),
        project_factory_state_dir=str(_state_dir(projects_root)),
        codex_command=str(fake_codex),
        project_factory_async_jobs=False,
        project_factory_generator_runs_override=0,
        project_factory_reviewer_runs_override=0,
    )
    return TestClient(create_app(settings))


def _asset_dir(projects_root: Path) -> Path:
    return projects_root / ".data" / "project_factory_reference_assets"


def _state_dir(projects_root: Path) -> Path:
    return projects_root / ".data" / "project_factory_state"


def _fake_codex(projects_root: Path) -> Path:
    script = projects_root / ".data" / "fake-codex"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "#!/usr/bin/env sh\nprintf 'fake codex ok\\n'\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def _create_draft(client: TestClient, name: str) -> str:
    response = client.post(
        "/project-factory/drafts",
        json={
            "name": name,
            "businessType": "medical_appointments",
            "primaryGoal": "Pacientes reservan turnos",
        },
    )
    assert response.status_code == 200
    return response.json()["draft_id"]


def _manifest_plan_payload(projects_root: Path, name: str) -> dict[str, object]:
    return ProjectFactoryManifestService(projects_root=projects_root).plan_manifest(
        ProjectFactoryManifestInput(
            name=name,
            business_type="medical",
            primary_goal="Reservar turnos",
        )
    ).to_payload()


def _json_dumps(payload: dict[str, object]) -> str:
    import json

    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _read_all_text(project: Path) -> str:
    chunks: list[str] = []
    for path in project.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)
