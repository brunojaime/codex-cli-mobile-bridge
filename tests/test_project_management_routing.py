from __future__ import annotations

from backend.app.domain.entities.project_management import (
    CHARTER_DELIVERY_CONTEXT_PATHS,
    CHARTER_ONLY_CONTEXT_PATHS,
    ProjectCharterVersionImpact,
    ProjectManagementIntentCategory,
    ProjectManagementModuleId,
    classify_project_management_request,
)


def test_benefits_request_routes_to_charter_only_context() -> None:
    result = classify_project_management_request("agreguemos beneficios al acta")

    assert result.intent == ProjectManagementIntentCategory.BENEFITS
    assert result.modules == (ProjectManagementModuleId.CHARTER,)
    assert result.context_paths == CHARTER_ONLY_CONTEXT_PATHS
    assert result.charter_content_impacted is True
    assert result.explicit_release_intent is False
    assert result.delivery_action_allowed is False


def test_product_objective_change_recommends_major_without_delivery() -> None:
    result = classify_project_management_request(
        "cambiemos el objetivo del producto"
    )

    assert result.intent == ProjectManagementIntentCategory.PRODUCT_OBJECTIVE
    assert result.modules == (ProjectManagementModuleId.CHARTER,)
    assert result.context_paths == CHARTER_ONLY_CONTEXT_PATHS
    assert result.version_impact == ProjectCharterVersionImpact.MAJOR
    assert result.explicit_release_intent is False
    assert result.delivery_action_allowed is False


def test_client_version_request_has_explicit_delivery_context() -> None:
    result = classify_project_management_request(
        "preparemos una version para entregar al cliente en PDF"
    )

    assert result.intent == ProjectManagementIntentCategory.VERSIONING
    assert result.modules == (ProjectManagementModuleId.CHARTER,)
    assert result.context_paths == CHARTER_DELIVERY_CONTEXT_PATHS
    assert result.explicit_release_intent is True
    assert result.delivery_action_allowed is True
    assert "docs/project-management/versioning.md" in result.context_paths
    assert "docs/project-management/acta/export-rules.md" in result.context_paths
    assert "docs/project-management/acta/validation-rules.md" in (
        result.context_paths
    )


def test_wbs_request_loads_wbs_without_alternatives() -> None:
    result = classify_project_management_request("arranquemos la WBS del proyecto")

    assert result.intent == ProjectManagementIntentCategory.WBS
    assert result.modules == (ProjectManagementModuleId.WBS,)
    assert "docs/project-management/index.md" in result.context_paths
    assert "docs/project-management/wbs/README.md" in result.context_paths
    assert "docs/project-management/wbs/wbs.md" in result.context_paths
    assert "docs/project-management/alternatives/README.md" not in (
        result.context_paths
    )
    assert result.charter_content_impacted is False


def test_module_requests_do_not_load_unrelated_modules() -> None:
    alternatives = classify_project_management_request(
        "creemos una matriz de alternativas"
    )
    risks = classify_project_management_request("identifiquemos riesgos")
    roles = classify_project_management_request("armemos roles y responsabilidades")

    assert alternatives.modules == (ProjectManagementModuleId.ALTERNATIVES,)
    assert "docs/project-management/risks/README.md" not in (
        alternatives.context_paths
    )
    assert risks.modules == (ProjectManagementModuleId.RISKS,)
    assert "docs/project-management/roles/README.md" not in risks.context_paths
    assert roles.modules == (ProjectManagementModuleId.ROLES,)
    assert "docs/project-management/alternatives/README.md" not in (
        roles.context_paths
    )
