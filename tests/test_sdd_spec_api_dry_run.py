from __future__ import annotations

import textwrap
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.infrastructure.config.settings import Settings
from backend.app.main import create_app


def test_new_spec_dry_run_api_happy_path_is_deterministic_and_read_only(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    client = _client(tmp_path / "projects")
    body = {
        "workspacePath": str(project),
        "specTarget": {"mode": "new_spec", "specId": "favorites"},
        "titleSeed": "Product favorites",
        "jobId": "job-1",
        "intakeItems": [{"kind": "text", "text": "Users save favorite products."}],
    }

    first = client.post("/sdd/specs/dry-run", json=body)
    second = client.post("/sdd/specs/dry-run", json=body)

    assert first.status_code == 200
    assert first.json() == second.json()
    payload = first.json()
    assert payload["kind"] == "codex.sddSpecCreationDryRun"
    assert payload["status"] == "dry-run"
    assert payload["spec_id"] == "favorites"
    assert payload["target_files"][0] == "specs/favorites/metadata.yaml"
    assert payload["metadata_proposal"]["title"] == "Product Favorites"
    assert payload["intake_plan"]["status"] == "dry-run"
    assert payload["blocked_reasons"] == []
    assert payload["next_actions"]
    assert not (project / "specs/favorites").exists()


def test_new_spec_dry_run_api_blocks_slug_collision_unsafe_path_and_invalid_media(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    (project / "specs/favorites").mkdir(parents=True)
    client = _client(tmp_path / "projects")

    collision = client.post(
        "/sdd/specs/dry-run",
        json={
            "workspacePath": str(project),
            "specTarget": {"mode": "new_spec", "specId": "favorites"},
            "titleSeed": "Favorites",
            "intakeItems": [{"kind": "text", "text": "Favorites"}],
        },
    ).json()
    unsafe = client.post(
        "/sdd/specs/dry-run",
        json={
            "workspacePath": str(tmp_path / "outside"),
            "specTarget": {"mode": "new_spec"},
            "titleSeed": "Unsafe",
            "intakeItems": [{"kind": "text", "text": "Unsafe"}],
        },
    ).json()
    invalid_media = client.post(
        "/sdd/specs/dry-run",
        json={
            "workspacePath": str(project),
            "specTarget": {"mode": "new_spec"},
            "titleSeed": "Audio",
            "intakeItems": [
                {
                    "kind": "audio",
                    "mimeType": "audio/ogg",
                    "byteSize": 10,
                    "durationMs": 100,
                    "sha256": "not-a-digest",
                }
            ],
        },
    ).json()

    assert collision["status"] == "blocked"
    assert collision["validation_errors"][0]["code"] == "spec_slug_collision"
    assert unsafe["status"] == "blocked"
    assert unsafe["validation_errors"][0]["code"] == "unsafe_workspace_path"
    assert invalid_media["status"] == "blocked"
    assert [item["code"] for item in invalid_media["rejected_media"]] == [
        "invalid_sha256",
        "unsupported_audio_format",
    ]
    assert not (project / "specs/favorites/intake").exists()


def test_existing_spec_edit_dry_run_api_preserves_pinned_metadata_and_is_read_only(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path, spec_id="001-existing", metadata=True)
    client = _client(tmp_path / "projects")

    response = client.post(
        "/sdd/specs/edit/dry-run",
        json={
            "workspacePath": str(project),
            "specTarget": {
                "mode": "existing_spec",
                "specId": "001-existing",
                "artifact": "tasks",
            },
            "intakeItems": [{"kind": "text", "text": "Update tasks"}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "codex.sddSpecEditDryRun"
    assert payload["status"] == "dry-run"
    assert payload["selected_artifact"] == "tasks"
    assert payload["intended_artifact_updates"] == [
        "specs/001-existing/tasks.md",
        "specs/001-existing/metadata.yaml",
    ]
    assert payload["metadata_proposal"]["preserve_pinned_title"] is True
    assert payload["metadata_proposal"]["preserve_pinned_description"] is True
    assert payload["existing_artifacts"] == payload["intended_artifact_updates"]
    assert (project / "specs/001-existing/tasks.md").read_text() == "- [ ] Existing\n"


def test_existing_spec_edit_dry_run_api_blocks_invalid_target_and_artifact_mismatch(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path, spec_id="001-existing", include_plan=False)
    client = _client(tmp_path / "projects")

    invalid_target = client.post(
        "/sdd/specs/edit/dry-run",
        json={
            "workspacePath": str(project),
            "specTarget": {"mode": "existing_spec", "specId": "../outside"},
            "intakeItems": [{"kind": "text", "text": "Edit"}],
        },
    ).json()
    artifact_mismatch = client.post(
        "/sdd/specs/edit/dry-run",
        json={
            "workspacePath": str(project),
            "specTarget": {
                "mode": "existing_spec",
                "specId": "001-existing",
                "artifact": "plan",
            },
            "intakeItems": [{"kind": "text", "text": "Edit"}],
        },
    ).json()

    assert invalid_target["status"] == "blocked"
    assert invalid_target["validation_errors"][0]["code"] == "invalid_spec_id"
    assert artifact_mismatch["status"] == "blocked"
    assert artifact_mismatch["conflicts"] == ["specs/001-existing/plan.md"]
    assert artifact_mismatch["blocked_reasons"] == [
        "conflict: specs/001-existing/plan.md"
    ]
    assert not (project / "specs/001-existing/plan.md").exists()


def test_existing_spec_edit_apply_api_queues_codex_job_for_synthesis(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path, spec_id="001-existing", metadata=True)
    client = _client(tmp_path / "projects")

    response = client.post(
        "/sdd/specs/edit/apply",
        json={
            "workspacePath": str(project),
            "specTarget": {
                "mode": "existing_spec",
                "specId": "001-existing",
                "artifact": "tasks",
            },
            "intakeItems": [{"kind": "text", "text": "Update tasks"}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "codex.sddSpecEditApply"
    assert payload["status"] == "queued"
    assert payload["dry_run"]["status"] == "dry-run"
    assert payload["existing"] == [
        "specs/001-existing/tasks.md",
        "specs/001-existing/metadata.yaml",
    ]
    assert payload["created"] == []
    assert payload["updated"] == []
    assert payload["blocked"] == []
    assert payload["job"]["status"] == "queued"
    assert payload["job"]["target_spec_id"] == "001-existing"
    assert payload["job"]["target_artifact"] == "specs/001-existing/tasks.md"
    assert "read_all_specs_without_context_pack" in payload["job"]["blocked_reads"]
    job_id = payload["job"]["job_id"]
    job_response = client.get(f"/sdd/codex-jobs/{job_id}")
    cancel_response = client.post(f"/sdd/codex-jobs/{job_id}/cancel")
    assert job_response.status_code == 200
    assert job_response.json()["status"] == "queued"
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"
    assert payload["next_actions"] == [
        "Codex job queued; poll the job status before applying changes."
    ]
    assert (project / "specs/001-existing/tasks.md").read_text() == "- [ ] Existing\n"


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
        feedback_source_workspace_aliases="",
    )
    return TestClient(create_app(settings))


def _write_project(
    tmp_path: Path,
    *,
    spec_id: str | None = None,
    metadata: bool = False,
    include_plan: bool = True,
) -> Path:
    project = tmp_path / "projects/demo"
    project.mkdir(parents=True)
    (project / "codex-bridge.yaml").write_text("sdd:\n  standard: workbench-sdd/v1\n")
    if spec_id is None:
        return project
    spec_root = project / "specs" / spec_id
    spec_root.mkdir(parents=True)
    (spec_root / "spec.md").write_text("# Existing Spec\n")
    if include_plan:
        (spec_root / "plan.md").write_text("# Plan\n")
    (spec_root / "tasks.md").write_text("- [ ] Existing\n")
    if metadata:
        (spec_root / "metadata.yaml").write_text(
            textwrap.dedent(
                """\
                title: Pinned Existing Title
                description: Pinned existing description.
                status: draft
                generated:
                  user_pinned_title: true
                  user_pinned_description: true
                """
            )
        )
    return project
