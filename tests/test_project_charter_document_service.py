from __future__ import annotations

import hashlib
import json
from pathlib import Path

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
    PROJECT_CHARTER_METADATA_PATH,
    PROJECT_CHARTER_RENDER_MANIFEST_PATH,
    PROJECT_CHARTER_SOURCE_PATH,
    PROJECT_CHARTER_PDF_PATH,
    ProjectCharterVersionImpact,
)


def test_valid_generated_charter_passes_validation(tmp_path: Path) -> None:
    project = _generated_project(tmp_path)

    result = ProjectCharterDocumentService(workspace_root=project).validate()

    assert result.ok is True
    assert result.blocking_issues == ()


def test_validation_blocks_internal_tooling_language_in_client_charter(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    service = ProjectCharterDocumentService(workspace_root=project)
    source_path = project / PROJECT_CHARTER_SOURCE_PATH
    source = source_path.read_text(encoding="utf-8")
    source = source.replace(
        "## Resumen ejecutivo",
        (
            "## Nota interna\n\n"
            "El Project Factory sincroniza Workbench y tareas SDD.\n\n"
            "## Resumen ejecutivo"
        ),
    )
    service.update_current_charter(
        source,
        changed_fields={"executive_summary"},
    )

    result = service.validate(client_export=False)

    codes = {issue.code for issue in result.blocking_issues}
    assert "internal_implementation_language" in codes


def test_validation_blocks_missing_fields_status_revision_logo_and_placeholders(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    metadata_path = project / PROJECT_CHARTER_METADATA_PATH
    metadata = _yaml(metadata_path)
    metadata["project"]["name"] = ""
    metadata["status"] = "not_a_state"
    _write_yaml(metadata_path, metadata)

    brand_path = project / PROJECT_CHARTER_BRAND_PATH
    brand = _yaml(brand_path)
    brand["logo_status"] = "pending"
    brand["logo_source"] = "none"
    brand["client_pdf_requires_logo"] = True
    _write_yaml(brand_path, brand)

    source_path = project / PROJECT_CHARTER_SOURCE_PATH
    source_path.write_text(
        "# Acta de Proyecto\n\nTODO lorem ipsum\n",
        encoding="utf-8",
    )

    result = ProjectCharterDocumentService(workspace_root=project).validate()

    codes = {issue.code for issue in result.blocking_issues}
    assert "missing_metadata_field" in codes
    assert "invalid_status" in codes
    assert "required_logo_pending" in codes
    assert "missing_revision_history" in codes
    assert "placeholder_marker" in codes
    assert "source_hash_mismatch" in codes


def test_validation_blocks_stale_render_and_render_hash_mismatch(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    metadata_path = project / PROJECT_CHARTER_METADATA_PATH
    metadata = _yaml(metadata_path)
    metadata["hashes"]["render"] = "render-from-metadata"
    _write_yaml(metadata_path, metadata)
    render_manifest_path = project / PROJECT_CHARTER_RENDER_MANIFEST_PATH
    render_manifest = json.loads(render_manifest_path.read_text(encoding="utf-8"))
    render_manifest["source_hash"] = "stale-source"
    render_manifest["render_hash"] = "render-from-manifest"
    render_manifest_path.write_text(
        json.dumps(render_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = ProjectCharterDocumentService(workspace_root=project).validate()

    codes = {issue.code for issue in result.blocking_issues}
    assert "stale_render" in codes
    assert "render_hash_mismatch" in codes


def test_draft_edit_updates_hash_without_bumping_delivered_version(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    service = ProjectCharterDocumentService(workspace_root=project)
    metadata_before = _yaml(project / PROJECT_CHARTER_METADATA_PATH)
    manifest_before = _yaml(project / ".codex/project.yaml")
    updated_source = (
        (project / PROJECT_CHARTER_SOURCE_PATH).read_text(encoding="utf-8")
        + "\n## Nota interna\n\nSe agregan beneficios para revisar.\n"
    )

    result = service.update_current_charter(
        updated_source,
        changed_fields={"expected_benefits"},
    )

    metadata_after = _yaml(project / PROJECT_CHARTER_METADATA_PATH)
    manifest_after = _yaml(project / ".codex/project.yaml")
    assert result.delivered_version == metadata_before["versions"]["delivered"]
    assert result.latest_release == manifest_before["project_management"]["latest_release"]
    assert metadata_after["versions"]["delivered"] is None
    assert manifest_after["project_management"]["latest_release"] is None
    assert metadata_after["hashes"]["source"] == _sha256(updated_source)
    assert metadata_after["status"] == "draft"


def test_first_release_creates_immutable_v1_snapshot(tmp_path: Path) -> None:
    project = _generated_project(tmp_path)
    service = ProjectCharterDocumentService(workspace_root=project)
    assert service.export_pdf().ok is True

    result = service.release("v1.0")

    assert result.ok is True
    release_dir = project / "docs/project-management/acta/releases/v1.0"
    assert release_dir.is_dir()
    assert (release_dir / "acta.md").is_file()
    assert (release_dir / "metadata.yaml").is_file()
    released_source = (release_dir / "acta.md").read_text(encoding="utf-8")
    released_metadata = _yaml(release_dir / "metadata.yaml")
    assert "- Version entregada: v1.0" in released_source
    assert "- Estado: client_delivered" in released_source
    assert "| v1.0 | client_delivered |" in released_source
    assert released_metadata["status"] == "client_delivered"
    assert released_metadata["versions"]["delivered"] == "v1.0"
    assert (release_dir / "acta.pdf").read_bytes().startswith(b"%PDF-")
    assert (release_dir / "source-hash.txt").read_text(encoding="utf-8").strip()
    manifest = json.loads(
        (release_dir / "release-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["version"] == "v1.0"
    assert _yaml(project / PROJECT_CHARTER_METADATA_PATH)["versions"][
        "delivered"
    ] == "v1.0"
    assert _yaml(project / ".codex/project.yaml")["project_management"][
        "latest_release"
    ] == "v1.0"

    repeated = service.release("v1.0")
    assert repeated.ok is False
    assert repeated.validation.blocking_issues[0].code == "release_already_exists"


def test_minor_and_major_release_recommendations_are_deterministic(
    tmp_path: Path,
) -> None:
    service = ProjectCharterDocumentService(workspace_root=_generated_project(tmp_path))

    assert service.recommend_release_impact({"revision_history"}) == (
        ProjectCharterVersionImpact.MINOR
    )
    assert service.recommend_release_impact({"product_objective"}) == (
        ProjectCharterVersionImpact.MAJOR
    )
    assert service.recommend_release_impact({"revision_history", "scope"}) == (
        ProjectCharterVersionImpact.MINOR
    )
    assert service.recommend_release_impact(
        {"revision_history", "preliminary_scope"}
    ) == ProjectCharterVersionImpact.MAJOR


def test_changelog_is_required_after_previous_delivered_release(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    service = ProjectCharterDocumentService(workspace_root=project)
    assert service.export_pdf().ok is True
    assert service.release("v1.0").ok is True
    updated_source = (
        (project / PROJECT_CHARTER_SOURCE_PATH).read_text(encoding="utf-8")
        + "\n## Beneficios nuevos\n\n- Reducir tiempos operativos.\n"
    )
    service.update_current_charter(
        updated_source,
        changed_fields={"expected_benefits"},
    )
    _sync_render_source_hash(project, updated_source)

    blocked = service.release("v1.1", changed_fields={"expected_benefits"})

    assert blocked.ok is False
    assert {issue.code for issue in blocked.validation.blocking_issues} == {
        "missing_changelog_entry",
        "missing_client_pdf",
    }
    assert service.export_pdf().ok is True
    released = service.release(
        "v1.1",
        changed_fields={"expected_benefits"},
        changelog_entry="Se agregan beneficios esperados.",
    )
    assert released.ok is True
    assert "Se agregan beneficios esperados." in (
        project / "docs/project-management/acta/changelog.md"
    ).read_text(encoding="utf-8")


def test_source_render_hash_mismatch_blocks_client_export(tmp_path: Path) -> None:
    project = _generated_project(tmp_path)
    render_manifest_path = project / PROJECT_CHARTER_RENDER_MANIFEST_PATH
    render_manifest = json.loads(render_manifest_path.read_text(encoding="utf-8"))
    render_manifest["source_hash"] = "wrong"
    render_manifest_path.write_text(
        json.dumps(render_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = ProjectCharterDocumentService(workspace_root=project).validate(
        client_export=True,
    )

    assert "stale_render" in {issue.code for issue in result.blocking_issues}


def test_render_refresh_creates_sanitized_html_and_fresh_manifest(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    service = ProjectCharterDocumentService(workspace_root=project)
    source = (
        (project / PROJECT_CHARTER_SOURCE_PATH).read_text(encoding="utf-8")
        + "\n## Seguridad\n\n<script>alert(1)</script>\n"
    )
    service.update_current_charter(source, changed_fields={"executive_summary"})

    stale = service.validate_export()
    assert "stale_render" in {issue.code for issue in stale.blocking_issues}

    rendered = service.refresh_render()
    html = (project / "docs/project-management/acta/current/render.html").read_text(
        encoding="utf-8"
    )
    manifest = json.loads(
        (project / PROJECT_CHARTER_RENDER_MANIFEST_PATH).read_text(
            encoding="utf-8"
        )
    )

    assert rendered.html == html
    assert len(html) > 500
    assert "<script" not in html.lower()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "@page" in html
    assert ".document-page" in html
    assert ".logo-slot" in html
    assert manifest["source_hash"] == _sha256(source)
    assert manifest["render_hash"] == _sha256(html)
    assert manifest["renderer"] == "charter-markdown-html/v1"
    assert manifest["output_path"] == "docs/project-management/acta/current/render.html"
    assert manifest["validation"]["blocking_issue_count"] == 0
    assert service.validate_export().ok is True


def test_render_manifest_is_stable_except_timestamp(tmp_path: Path) -> None:
    project = _generated_project(tmp_path)
    service = ProjectCharterDocumentService(workspace_root=project)

    service.refresh_render()
    first = json.loads(
        (project / PROJECT_CHARTER_RENDER_MANIFEST_PATH).read_text(
            encoding="utf-8"
        )
    )
    service.refresh_render()
    second = json.loads(
        (project / PROJECT_CHARTER_RENDER_MANIFEST_PATH).read_text(
            encoding="utf-8"
        )
    )

    first_without_time = dict(first)
    second_without_time = dict(second)
    first_without_time.pop("generated_at", None)
    second_without_time.pop("generated_at", None)
    assert first_without_time == second_without_time
    assert first["generated_at"]
    assert second["generated_at"]


def test_pdf_export_generates_valid_traced_pdf_without_mutating_source(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    service = ProjectCharterDocumentService(workspace_root=project)
    before = (project / PROJECT_CHARTER_SOURCE_PATH).read_text(encoding="utf-8")

    result = service.export_pdf()

    after = (project / PROJECT_CHARTER_SOURCE_PATH).read_text(encoding="utf-8")
    assert result.ok is True
    assert result.status == "generated"
    assert result.output_path == PROJECT_CHARTER_PDF_PATH
    assert result.page_count > 0
    assert result.sha256
    assert (project / PROJECT_CHARTER_PDF_PATH).read_bytes().startswith(b"%PDF-")
    manifest = json.loads(
        (project / PROJECT_CHARTER_RENDER_MANIFEST_PATH).read_text(encoding="utf-8")
    )
    assert manifest["pdf"]["sha256"] == result.sha256
    assert after == before


def test_export_validation_blocks_render_and_charter_validation_issues(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    brand_path = project / PROJECT_CHARTER_BRAND_PATH
    brand = _yaml(brand_path)
    brand["logo_status"] = "pending"
    brand["logo_source"] = "none"
    brand["client_pdf_requires_logo"] = True
    _write_yaml(brand_path, brand)
    render_manifest_path = project / PROJECT_CHARTER_RENDER_MANIFEST_PATH
    render_manifest = json.loads(render_manifest_path.read_text(encoding="utf-8"))
    render_manifest["source_hash"] = "stale"
    render_manifest_path.write_text(
        json.dumps(render_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = ProjectCharterDocumentService(workspace_root=project).validate_export()

    codes = {issue.code for issue in result.blocking_issues}
    assert "required_logo_pending" in codes
    assert "stale_render" in codes


def _generated_project(tmp_path: Path) -> Path:
    manifest_plan = ProjectFactoryManifestService(
        projects_root=tmp_path,
    ).plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
        )
    )
    ProjectFactoryGeneratorService().generate(manifest_plan)
    project = tmp_path / "clinica-norte"
    brand_path = project / PROJECT_CHARTER_BRAND_PATH
    brand = _yaml(brand_path)
    brand["logo_status"] = "not_required"
    brand["logo_source"] = "none"
    brand["client_pdf_requires_logo"] = False
    brand["logo_path"] = None
    _write_yaml(brand_path, brand)
    return project


def _yaml(path: Path) -> dict[str, object]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    assert isinstance(payload, dict)
    return payload


def _write_yaml(path: Path, payload: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sync_render_source_hash(project: Path, source: str) -> None:
    render_manifest_path = project / PROJECT_CHARTER_RENDER_MANIFEST_PATH
    render_manifest = json.loads(render_manifest_path.read_text(encoding="utf-8"))
    render_manifest["source_hash"] = _sha256(source)
    render_manifest_path.write_text(
        json.dumps(render_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
