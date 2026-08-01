from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient
import yaml

from backend.app.application.services.project_charter_document_service import (
    ProjectCharterDocumentService,
)
from backend.app.application.services.project_factory_generator_service import (
    ProjectFactoryGeneratorService,
)
from backend.app.application.services.project_factory_manifest_service import (
    ProjectFactoryManifestInput,
    ProjectFactoryManifestService,
)
from backend.app.domain.entities.project_management import (
    PROJECT_CHARTER_BRAND_PATH,
    PROJECT_CHARTER_SOURCE_PATH,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.main import create_app


def test_project_documents_list_returns_generated_modules(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = _generated_project(projects_root)
    client = _client(projects_root, codex_workdir=str(project))

    response = client.get(
        "/project-documents",
        params={"workspacePath": str(project)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "codex.projectDocuments"
    assert payload["workspace_path"] == str(project)
    assert {module["id"] for module in payload["modules"]} == {
        "charter",
        "wbs",
        "roles",
        "risks",
        "alternatives",
    }
    assert payload["charter"]["path"] == PROJECT_CHARTER_SOURCE_PATH
    assert payload["charter"]["render"]["exists"] is True
    assert payload["charter"]["validation"]["ok"] is True


def test_charter_detail_returns_metadata_summary_render_and_validation(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = _generated_project(projects_root)
    client = _client(projects_root, codex_workdir=str(project))

    response = client.get(
        "/project-documents/charter",
        params={"workspace_path": str(project)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["project"]["name"] == "Clinica Norte"
    assert payload["source_summary"]["title"] == "Acta de Proyecto"
    assert "Proyecto: Clinica Norte" in payload["source_summary"]["excerpt"]
    assert payload["render"]["exists"] is True
    assert "<!doctype html>" in payload["render"]["content"]
    assert payload["render_manifest"]["source_hash"]
    assert payload["validation"]["ok"] is True
    assert payload["latest_release"] is None


def test_validate_render_release_and_releases_endpoints_are_stable(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = _generated_project(projects_root)
    client = _client(projects_root, codex_workdir=str(project))

    validate = client.post(
        "/project-documents/charter/validate",
        json={"workspacePath": str(project)},
    )
    assert validate.status_code == 200
    assert validate.json()["validation"]["ok"] is True

    source_path = project / PROJECT_CHARTER_SOURCE_PATH
    updated_source = (
        source_path.read_text(encoding="utf-8")
        + "\n## Revision interna\n\nSe ajusta el resumen para validar render.\n"
    )
    ProjectCharterDocumentService(workspace_root=project).update_current_charter(
        updated_source,
        changed_fields={"executive_summary"},
    )
    render = client.post(
        "/project-documents/charter/render",
        json={"workspacePath": str(project)},
    )
    assert render.status_code == 200
    render_payload = render.json()
    assert render_payload["render"]["exists"] is True
    assert render_payload["render_manifest"]["source_hash"] == render_payload[
        "render"
    ]["source_hash"]

    release = client.post(
        "/project-documents/charter/release",
        json={
            "workspacePath": str(project),
            "version": "v1.0",
            "changedFields": ["executive_summary"],
        },
    )
    assert release.status_code == 200
    assert release.json()["ok"] is True
    assert release.json()["release_path"].endswith("/v1.0")

    repeated = client.post(
        "/project-documents/charter/release",
        json={"workspacePath": str(project), "version": "v1.0"},
    )
    assert repeated.status_code == 409
    assert repeated.json()["detail"]["validation"]["issues"][0]["code"] == (
        "release_already_exists"
    )

    releases = client.get(
        "/project-documents/charter/releases",
        params={"workspace_path": str(project)},
    )
    assert releases.status_code == 200
    assert [item["version"] for item in releases.json()["releases"]] == ["v1.0"]

    release_detail = client.get(
        "/project-documents/charter/releases/v1.0",
        params={"workspacePath": str(project)},
    )
    assert release_detail.status_code == 200
    assert release_detail.json()["release"]["version"] == "v1.0"
    assert "Proyecto: Clinica Norte" in release_detail.json()["release"][
        "source"
    ]["content"]


def test_project_documents_can_resolve_project_factory_draft_and_job(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    draft = client.post(
        "/project-factory/drafts",
        json={
            "name": "Turnos Medicos Norte",
            "businessType": "medical_appointments",
            "primaryGoal": "Pacientes reservan turnos",
        },
    ).json()
    draft_id = draft["draft_id"]
    generated = client.post(f"/project-factory/drafts/{draft_id}/generate")
    assert generated.status_code == 200
    job_id = generated.json()["job_id"]

    by_job = client.get("/project-documents", params={"jobId": job_id})
    assert by_job.status_code == 200
    assert by_job.json()["evidence"]["jobId"] == job_id

    by_draft = client.get("/project-documents/charter", params={"draftId": draft_id})
    assert by_draft.status_code == 200
    assert by_draft.json()["metadata"]["project"]["name"] == "Turnos Medicos Norte"


def test_project_documents_reject_unknown_draft_and_job_context(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)

    unknown_job = client.get("/project-documents", params={"jobId": "pf-job-missing"})
    assert unknown_job.status_code == 400
    assert "workspace_path, draft_id, or job_id" in unknown_job.json()["detail"]

    unknown_draft = client.get(
        "/project-documents/charter",
        params={"draftId": "pf-draft-missing"},
    )
    assert unknown_draft.status_code == 400
    assert "workspace_path, draft_id, or job_id" in unknown_draft.json()["detail"]

    unknown_release_context = client.get(
        "/project-documents/charter/releases",
        params={"jobId": "pf-job-missing"},
    )
    assert unknown_release_context.status_code == 400


def test_project_documents_release_blocks_stale_render_and_logo_export_gate(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = _generated_project(projects_root)
    client = _client(projects_root, codex_workdir=str(project))
    source_path = project / PROJECT_CHARTER_SOURCE_PATH
    updated_source = (
        source_path.read_text(encoding="utf-8")
        + "\n## Ajuste sin render\n\nCambio que deja obsoleto el render.\n"
    )
    ProjectCharterDocumentService(workspace_root=project).update_current_charter(
        updated_source,
        changed_fields={"executive_summary"},
    )

    stale_release = client.post(
        "/project-documents/charter/release",
        json={"workspacePath": str(project), "version": "v1.0"},
    )

    assert stale_release.status_code == 409
    stale_codes = {
        issue["code"]
        for issue in stale_release.json()["detail"]["validation"]["issues"]
    }
    assert "stale_render" in stale_codes

    render = client.post(
        "/project-documents/charter/render",
        json={"workspacePath": str(project)},
    )
    assert render.status_code == 200
    brand_path = project / PROJECT_CHARTER_BRAND_PATH
    brand = _read_yaml(brand_path)
    brand["logo_status"] = "pending"
    brand["logo_source"] = "none"
    brand["client_pdf_requires_logo"] = True
    _write_yaml(brand_path, brand)

    export_validation = client.post(
        "/project-documents/charter/validate",
        json={"workspacePath": str(project), "clientExport": True},
    )
    assert export_validation.status_code == 200
    export_codes = {
        issue["code"] for issue in export_validation.json()["validation"]["issues"]
    }
    assert "required_logo_pending" in export_codes

    logo_blocked_release = client.post(
        "/project-documents/charter/release",
        json={"workspacePath": str(project), "version": "v1.0"},
    )
    assert logo_blocked_release.status_code == 409
    logo_codes = {
        issue["code"]
        for issue in logo_blocked_release.json()["detail"]["validation"]["issues"]
    }
    assert "required_logo_pending" in logo_codes


def test_project_documents_block_workspace_escape_and_release_path_traversal(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = _generated_project(projects_root)
    outside = tmp_path / "outside"
    outside.mkdir()
    client = _client(projects_root, codex_workdir=str(project))

    missing_workspace = client.get("/project-documents")
    assert missing_workspace.status_code == 400

    absolute_escape = client.get(
        "/project-documents",
        params={"workspacePath": str(outside)},
    )
    assert absolute_escape.status_code == 400

    traversal_escape = client.get(
        "/project-documents",
        params={"workspacePath": "../outside"},
    )
    assert traversal_escape.status_code == 400

    unsafe_release = client.get(
        "/project-documents/charter/releases/not-safe",
        params={"workspacePath": str(project)},
    )
    assert unsafe_release.status_code == 400


def test_workbench_discovery_includes_documents_not_charter_feature_spec(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = _generated_project(projects_root)
    client = _client(projects_root, codex_workdir=str(project))

    response = client.get(
        "/sdd/workbench/view",
        params={"workspace_path": str(project)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["documents"]["available"] is True
    assert payload["documents"]["charter"]["path"] == PROJECT_CHARTER_SOURCE_PATH
    assert {module["id"] for module in payload["documents"]["modules"]} >= {
        "charter",
        "wbs",
        "roles",
        "risks",
        "alternatives",
    }
    assert all("charter" not in spec["id"] for spec in payload["feature_specs"])
    assert payload["feature_specs"][0]["id"] == "001-product-foundation"


def _client(projects_root: Path, **overrides: object) -> TestClient:
    overrides.setdefault("feedback_source_workspace_aliases", "")
    fake_codex = _fake_codex(projects_root)
    os.environ["VISUAL_UX_POLISH_SKILL_PATH"] = str(
        _visual_ux_skill_fixture(projects_root)
    )
    values: dict[str, object] = {
        "projects_root": str(projects_root),
        "codex_workdir": str(projects_root),
        "chat_store_backend": "memory",
        "audio_transcription_backend": "disabled",
        "speech_synthesis_backend": "disabled",
        "codex_command": str(fake_codex),
        "execution_timeout_seconds": 10,
        "poll_interval_seconds": 0,
        "project_factory_reference_asset_dir": str(projects_root / ".assets"),
        "project_factory_state_dir": str(projects_root / ".state"),
        "project_factory_async_jobs": False,
        "project_factory_generator_runs_override": 0,
        "project_factory_reviewer_runs_override": 0,
        "project_factory_publication_validation_mode": "local",
    }
    values.update(overrides)
    settings = Settings(**values)
    return TestClient(create_app(settings))


def _generated_project(projects_root: Path) -> Path:
    projects_root.mkdir(parents=True, exist_ok=True)
    manifest_plan = ProjectFactoryManifestService(
        projects_root=projects_root,
    ).plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
        )
    )
    ProjectFactoryGeneratorService().generate(manifest_plan)
    return projects_root / "clinica-norte"


def _read_yaml(path: Path) -> dict[str, object]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    assert isinstance(payload, dict)
    return payload


def _write_yaml(path: Path, payload: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _fake_codex(projects_root: Path) -> Path:
    script = projects_root / ".data" / "fake-codex"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        """#!/usr/bin/env bash
prompt="${@: -1}"
case "$prompt" in
  *"Lightweight UX Brief"*)
    mkdir -p .codex/ux
    printf '# Pre-project UX brief\\n\\nFake brief.\\n' > .codex/ux/pre-project-ux-brief.md
    ;;
  *"Senior UX Generator"*)
    mkdir -p .codex/ux
    printf '# UX generator report\\n\\nFake UX pass.\\n' > .codex/ux/ux-generator-report.md
    ;;
  *"Senior UX Reviewer"*)
    mkdir -p .codex/ux
    printf '# UX reviewer report\\n\\nstatus: complete\\n' > .codex/ux/ux-reviewer-report.md
    ;;
esac
printf 'fake codex ok\\n'
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def _visual_ux_skill_fixture(projects_root: Path) -> Path:
    root = projects_root / ".data" / "skill-fixtures" / "visual-ux-polish"
    references = root / "references"
    references.mkdir(parents=True, exist_ok=True)
    root.joinpath("SKILL.md").write_text(
        "# Visual UX Polish\n\nUse this skill for professional UX polish.\n",
        encoding="utf-8",
    )
    for relative_path in (
        "visual-quality-checklist.md",
        "product-category-playbooks.md",
        "visual-validation-protocol.md",
        "accessibility-performance-polish.md",
    ):
        references.joinpath(relative_path).write_text(
            f"# {relative_path}\n\nRequired UX reference content.\n",
            encoding="utf-8",
        )
    return root / "SKILL.md"
