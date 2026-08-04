from __future__ import annotations

from backend.app.domain.entities.project_management import (
    PROJECT_CHARTER_TRACEABILITY,
    CharterFieldSource,
    ProjectCharterBrandMetadata,
    ProjectCharterDocumentState,
    ProjectCharterLogoSource,
    ProjectCharterLogoStatus,
    ProjectCharterMetadata,
    ProjectCharterValidationIssue,
    ProjectCharterValidationResult,
    ProjectCharterValidationSeverity,
    ProjectCharterVersionImpact,
    can_transition_charter_state,
    default_project_management_manifest,
    recommend_delivered_version_impact,
)


def test_default_manifest_payload_defines_project_charter_contract() -> None:
    payload = default_project_management_manifest().to_manifest_payload()

    assert payload["enabled"] is True
    assert payload["standard"] == "project-charter/v1"
    assert payload["primary_document"] == (
        "docs/project-management/acta/current/acta.md"
    )
    assert payload["latest_render"] == (
        "docs/project-management/acta/current/render.html"
    )
    assert payload["latest_release"] is None
    assert payload["modules"] == {
        "charter": "docs/project-management/acta/README.md",
        "wbs": "docs/project-management/wbs/README.md",
        "roles": "docs/project-management/roles/README.md",
        "risks": "docs/project-management/risks/README.md",
        "alternatives": "docs/project-management/alternatives/README.md",
    }
    assert payload["module_context"]["charter"]["load_by_default"] is True
    assert payload["module_context"]["wbs"]["load_by_default"] is False
    assert payload["validation_policy"] == {
        "client_export_requires_valid_charter": True,
        "block_on_missing_required_fields": True,
        "block_on_pending_required_logo": True,
        "block_on_placeholders": True,
        "block_on_stale_render": True,
        "block_on_release_overwrite": True,
        "require_changelog_after_delivered_version": True,
    }


def test_charter_metadata_payload_contains_required_yaml_schema_fields() -> None:
    metadata = ProjectCharterMetadata(
        title="Acta de Proyecto",
        project_name="Moldegom",
        client="Moldegom SA",
        author="Codex",
        status=ProjectCharterDocumentState.INTERNAL_REVIEW,
        draft_version="v0.2",
        delivered_version="v1.0",
        source_hash="source-sha",
        render_hash="render-sha",
        created_at="2026-08-01T10:00:00Z",
        updated_at="2026-08-01T11:00:00Z",
        field_sources={
            "project_objective": CharterFieldSource(
                source="ProjectFactoryManifestInput.primary_goal",
                confidence=0.9,
                notes="Inferred from intake.",
            )
        },
    )

    payload = metadata.to_metadata_payload()

    assert payload["schema_version"] == 1
    assert payload["standard"] == "project-charter/v1"
    assert payload["document"]["type"] == "project_charter"
    assert payload["project"] == {"name": "Moldegom", "client": "Moldegom SA"}
    assert payload["author"] == "Codex"
    assert payload["status"] == "internal_review"
    assert payload["versions"] == {"draft": "v0.2", "delivered": "v1.0"}
    assert payload["hashes"] == {"source": "source-sha", "render": "render-sha"}
    assert payload["timestamps"]["created_at"] == "2026-08-01T10:00:00Z"
    assert payload["field_sources"]["project_objective"] == {
        "source": "ProjectFactoryManifestInput.primary_goal",
        "confidence": 0.9,
        "notes": "Inferred from intake.",
    }


def test_brand_metadata_blocks_export_only_when_required_logo_is_pending() -> None:
    pending = ProjectCharterBrandMetadata(
        logo_status=ProjectCharterLogoStatus.PENDING,
        logo_source=ProjectCharterLogoSource.NONE,
    )
    provided = ProjectCharterBrandMetadata(
        logo_status=ProjectCharterLogoStatus.PROVIDED,
        logo_source=ProjectCharterLogoSource.USER_UPLOAD,
    )
    not_required = ProjectCharterBrandMetadata(
        logo_status=ProjectCharterLogoStatus.PENDING,
        logo_source=ProjectCharterLogoSource.NONE,
        client_pdf_requires_logo=False,
        logo_path=None,
    )

    assert pending.blocks_client_export is True
    assert provided.blocks_client_export is False
    assert not_required.blocks_client_export is False
    assert pending.to_metadata_payload()["logo_status"] == "pending"
    assert pending.to_metadata_payload()["client_pdf_requires_logo"] is True


def test_charter_state_machine_allows_only_explicit_delivery_flow() -> None:
    assert can_transition_charter_state(
        ProjectCharterDocumentState.DRAFT,
        ProjectCharterDocumentState.INTERNAL_REVIEW,
    )
    assert can_transition_charter_state(
        ProjectCharterDocumentState.INTERNAL_REVIEW,
        ProjectCharterDocumentState.CLIENT_DELIVERED,
    )
    assert can_transition_charter_state(
        ProjectCharterDocumentState.CLIENT_DELIVERED,
        ProjectCharterDocumentState.CLIENT_REVISED,
    )
    assert not can_transition_charter_state(
        ProjectCharterDocumentState.SUPERSEDED,
        ProjectCharterDocumentState.DRAFT,
    )
    assert not can_transition_charter_state(
        ProjectCharterDocumentState.CLIENT_DELIVERED,
        ProjectCharterDocumentState.DRAFT,
    )


def test_version_impact_rules_separate_minor_and_major_delivered_changes() -> None:
    assert recommend_delivered_version_impact(set()) == (
        ProjectCharterVersionImpact.DRAFT_ONLY
    )
    assert recommend_delivered_version_impact({"revision_history"}) == (
        ProjectCharterVersionImpact.MINOR
    )
    assert recommend_delivered_version_impact({"product_objective"}) == (
        ProjectCharterVersionImpact.MAJOR
    )
    assert recommend_delivered_version_impact(
        {"revision_history", "project_objective"}
    ) == ProjectCharterVersionImpact.MAJOR


def test_validation_result_payload_exposes_blocking_issue_shape() -> None:
    issue = ProjectCharterValidationIssue(
        severity=ProjectCharterValidationSeverity.ERROR,
        code="missing_product_objective",
        field="product_objective",
        message="Product objective is required before client delivery.",
        next_action="Define the product objective or add a pending definition.",
        blocking=True,
        affected_file="docs/project-management/acta/current/acta.md",
    )

    result = ProjectCharterValidationResult(
        issues=(issue,),
        generated_at="2026-08-01T12:00:00Z",
    )

    payload = result.to_payload()
    assert result.ok is False
    assert payload["kind"] == "codex.projectCharterValidationResult"
    assert payload["blocking_count"] == 1
    assert payload["issues"] == [
        {
            "severity": "error",
            "code": "missing_product_objective",
            "field": "product_objective",
            "message": "Product objective is required before client delivery.",
            "next_action": (
                "Define the product objective or add a pending definition."
            ),
            "blocking": True,
            "affected_file": "docs/project-management/acta/current/acta.md",
        }
    ]


def test_project_factory_traceability_covers_initial_charter_fields() -> None:
    covered = {item.charter_field for item in PROJECT_CHARTER_TRACEABILITY}

    assert {
        "cover.project_name",
        "cover.client",
        "cover.logo_decision",
        "project_objective",
        "product_objective",
        "expected_benefits",
        "preliminary_scope",
        "pending_definitions",
    }.issubset(covered)
    assert all(item.source_field for item in PROJECT_CHARTER_TRACEABILITY)
    assert all(item.metadata_field for item in PROJECT_CHARTER_TRACEABILITY)
