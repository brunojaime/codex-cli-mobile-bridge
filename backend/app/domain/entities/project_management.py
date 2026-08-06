from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import unicodedata
from typing import Mapping


PROJECT_CHARTER_STANDARD_ID = "project-charter/v1"
PROJECT_MANAGEMENT_ROOT = "docs/project-management"
PROJECT_CHARTER_SOURCE_PATH = (
    "docs/project-management/acta/current/acta.md"
)
PROJECT_CHARTER_METADATA_PATH = (
    "docs/project-management/acta/current/metadata.yaml"
)
PROJECT_CHARTER_BRAND_PATH = "docs/project-management/acta/current/brand.yaml"
PROJECT_CHARTER_RENDER_PATH = "docs/project-management/acta/current/render.html"
PROJECT_CHARTER_PDF_PATH = "docs/project-management/acta/current/acta.pdf"
PROJECT_CHARTER_RENDER_MANIFEST_PATH = (
    "docs/project-management/acta/current/render-manifest.json"
)
PROJECT_CHARTER_CHANGELOG_PATH = "docs/project-management/acta/changelog.md"
PROJECT_CHARTER_README_PATH = "docs/project-management/acta/README.md"
PROJECT_CHARTER_VALIDATION_RULES_PATH = (
    "docs/project-management/acta/validation-rules.md"
)
PROJECT_CHARTER_EXPORT_RULES_PATH = "docs/project-management/acta/export-rules.md"
PROJECT_MANAGEMENT_INDEX_PATH = "docs/project-management/index.md"
PROJECT_MANAGEMENT_GLOSSARY_PATH = "docs/project-management/glossary.md"
PROJECT_MANAGEMENT_VERSIONING_PATH = "docs/project-management/versioning.md"
PROJECT_MANAGEMENT_CONTEXT_ROUTING_PATH = "docs/project-management/context-routing.md"


class ProjectManagementModuleId(StrEnum):
    CHARTER = "charter"
    WBS = "wbs"
    ROLES = "roles"
    RISKS = "risks"
    ALTERNATIVES = "alternatives"


class ProjectManagementIntentCategory(StrEnum):
    CHARTER_IDENTITY = "charter_identity"
    EXECUTIVE_SUMMARY = "executive_summary"
    PROJECT_OBJECTIVE = "project_objective"
    PRODUCT_OBJECTIVE = "product_objective"
    BENEFITS = "benefits"
    SCOPE = "scope"
    PENDING_DEFINITIONS = "pending_definitions"
    VERSIONING = "versioning"
    RENDER_EXPORT = "render_export"
    WBS = "wbs"
    ROLES = "roles"
    RISKS = "risks"
    ALTERNATIVES = "alternatives"


class ProjectCharterDocumentState(StrEnum):
    DRAFT = "draft"
    INTERNAL_REVIEW = "internal_review"
    CLIENT_DELIVERED = "client_delivered"
    CLIENT_REVISED = "client_revised"
    SUPERSEDED = "superseded"


class ProjectCharterLogoStatus(StrEnum):
    PROVIDED = "provided"
    GENERATED = "generated"
    PENDING = "pending"
    NOT_REQUIRED = "not_required"


class ProjectCharterLogoSource(StrEnum):
    USER_UPLOAD = "user_upload"
    GENERATED = "generated"
    NONE = "none"


class ProjectCharterValidationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ProjectCharterVersionImpact(StrEnum):
    DRAFT_ONLY = "draft_only"
    MINOR = "minor"
    MAJOR = "major"


PROJECT_CHARTER_STATE_TRANSITIONS: Mapping[
    ProjectCharterDocumentState,
    frozenset[ProjectCharterDocumentState],
] = {
    ProjectCharterDocumentState.DRAFT: frozenset(
        {
            ProjectCharterDocumentState.INTERNAL_REVIEW,
            ProjectCharterDocumentState.CLIENT_DELIVERED,
        }
    ),
    ProjectCharterDocumentState.INTERNAL_REVIEW: frozenset(
        {
            ProjectCharterDocumentState.DRAFT,
            ProjectCharterDocumentState.CLIENT_DELIVERED,
        }
    ),
    ProjectCharterDocumentState.CLIENT_DELIVERED: frozenset(
        {
            ProjectCharterDocumentState.CLIENT_REVISED,
            ProjectCharterDocumentState.SUPERSEDED,
        }
    ),
    ProjectCharterDocumentState.CLIENT_REVISED: frozenset(
        {
            ProjectCharterDocumentState.DRAFT,
            ProjectCharterDocumentState.INTERNAL_REVIEW,
            ProjectCharterDocumentState.CLIENT_DELIVERED,
        }
    ),
    ProjectCharterDocumentState.SUPERSEDED: frozenset(),
}


PROJECT_CHARTER_VERSION_RULES: Mapping[str, ProjectCharterVersionImpact] = {
    "cover.project_name": ProjectCharterVersionImpact.MAJOR,
    "cover.client": ProjectCharterVersionImpact.MINOR,
    "cover.logo_decision": ProjectCharterVersionImpact.MINOR,
    "executive_summary": ProjectCharterVersionImpact.MINOR,
    "project_objective": ProjectCharterVersionImpact.MAJOR,
    "product_objective": ProjectCharterVersionImpact.MAJOR,
    "expected_benefits": ProjectCharterVersionImpact.MAJOR,
    "preliminary_scope": ProjectCharterVersionImpact.MAJOR,
    "pending_definitions": ProjectCharterVersionImpact.MINOR,
    "revision_history": ProjectCharterVersionImpact.MINOR,
}


@dataclass(frozen=True, slots=True)
class ProjectManagementModule:
    id: str
    path: str
    load_by_default: bool = False
    description: str = ""

    def to_manifest_payload(self) -> dict[str, object]:
        return {
            "path": self.path,
            "load_by_default": self.load_by_default,
            "description": self.description,
        }


DEFAULT_PROJECT_MANAGEMENT_MODULES: Mapping[str, ProjectManagementModule] = {
    ProjectManagementModuleId.CHARTER.value: ProjectManagementModule(
        id=ProjectManagementModuleId.CHARTER.value,
        path=PROJECT_CHARTER_README_PATH,
        load_by_default=True,
        description="Project Charter / Acta de Proyecto context.",
    ),
    ProjectManagementModuleId.WBS.value: ProjectManagementModule(
        id=ProjectManagementModuleId.WBS.value,
        path="docs/project-management/wbs/README.md",
        description="Work Breakdown Structure / EDT context.",
    ),
    ProjectManagementModuleId.ROLES.value: ProjectManagementModule(
        id=ProjectManagementModuleId.ROLES.value,
        path="docs/project-management/roles/README.md",
        description="Roles, responsibilities, skills, and competencies.",
    ),
    ProjectManagementModuleId.RISKS.value: ProjectManagementModule(
        id=ProjectManagementModuleId.RISKS.value,
        path="docs/project-management/risks/README.md",
        description="Risk management context.",
    ),
    ProjectManagementModuleId.ALTERNATIVES.value: ProjectManagementModule(
        id=ProjectManagementModuleId.ALTERNATIVES.value,
        path="docs/project-management/alternatives/README.md",
        description="Decision and alternative matrix context.",
    ),
}


CHARTER_ONLY_CONTEXT_PATHS: tuple[str, ...] = (
    PROJECT_MANAGEMENT_INDEX_PATH,
    PROJECT_CHARTER_README_PATH,
    PROJECT_CHARTER_SOURCE_PATH,
    PROJECT_CHARTER_METADATA_PATH,
    PROJECT_CHARTER_VALIDATION_RULES_PATH,
)

CHARTER_DELIVERY_CONTEXT_PATHS: tuple[str, ...] = (
    *CHARTER_ONLY_CONTEXT_PATHS,
    PROJECT_MANAGEMENT_VERSIONING_PATH,
    PROJECT_CHARTER_CHANGELOG_PATH,
    PROJECT_CHARTER_BRAND_PATH,
    PROJECT_CHARTER_RENDER_MANIFEST_PATH,
    PROJECT_CHARTER_EXPORT_RULES_PATH,
)

MODULE_CONTEXT_PATHS: Mapping[ProjectManagementModuleId, tuple[str, ...]] = {
    ProjectManagementModuleId.CHARTER: CHARTER_ONLY_CONTEXT_PATHS,
    ProjectManagementModuleId.WBS: (
        PROJECT_MANAGEMENT_INDEX_PATH,
        "docs/project-management/wbs/README.md",
        "docs/project-management/wbs/wbs.md",
        "docs/project-management/wbs/wbs.puml",
    ),
    ProjectManagementModuleId.ROLES: (
        PROJECT_MANAGEMENT_INDEX_PATH,
        "docs/project-management/roles/README.md",
        "docs/project-management/roles/roles-responsibilities.md",
        "docs/project-management/roles/skills-competencies.md",
    ),
    ProjectManagementModuleId.RISKS: (
        PROJECT_MANAGEMENT_INDEX_PATH,
        "docs/project-management/risks/README.md",
        "docs/project-management/risks/risks.md",
    ),
    ProjectManagementModuleId.ALTERNATIVES: (
        PROJECT_MANAGEMENT_INDEX_PATH,
        "docs/project-management/alternatives/README.md",
        "docs/project-management/alternatives/decision-matrix-template.md",
    ),
}

INTENT_VERSION_FIELDS: Mapping[
    ProjectManagementIntentCategory,
    str,
] = {
    ProjectManagementIntentCategory.CHARTER_IDENTITY: "cover.client",
    ProjectManagementIntentCategory.EXECUTIVE_SUMMARY: "executive_summary",
    ProjectManagementIntentCategory.PROJECT_OBJECTIVE: "project_objective",
    ProjectManagementIntentCategory.PRODUCT_OBJECTIVE: "product_objective",
    ProjectManagementIntentCategory.BENEFITS: "expected_benefits",
    ProjectManagementIntentCategory.SCOPE: "preliminary_scope",
    ProjectManagementIntentCategory.PENDING_DEFINITIONS: "pending_definitions",
    ProjectManagementIntentCategory.VERSIONING: "revision_history",
    ProjectManagementIntentCategory.RENDER_EXPORT: "revision_history",
}

EXPLICIT_DELIVERY_TERMS = frozenset(
    {
        "entregar",
        "entrega",
        "entregable",
        "exportar",
        "exporta",
        "release",
        "liberar",
        "versionar",
        "version",
        "cliente",
        "pdf",
        "mandar",
        "enviar",
    }
)


@dataclass(frozen=True, slots=True)
class ProjectManagementValidationPolicy:
    client_export_requires_valid_charter: bool = True
    block_on_missing_required_fields: bool = True
    block_on_pending_required_logo: bool = True
    block_on_placeholders: bool = True
    block_on_stale_render: bool = True
    block_on_release_overwrite: bool = True
    require_changelog_after_delivered_version: bool = True

    def to_manifest_payload(self) -> dict[str, object]:
        return {
            "client_export_requires_valid_charter": (
                self.client_export_requires_valid_charter
            ),
            "block_on_missing_required_fields": (
                self.block_on_missing_required_fields
            ),
            "block_on_pending_required_logo": (
                self.block_on_pending_required_logo
            ),
            "block_on_placeholders": self.block_on_placeholders,
            "block_on_stale_render": self.block_on_stale_render,
            "block_on_release_overwrite": self.block_on_release_overwrite,
            "require_changelog_after_delivered_version": (
                self.require_changelog_after_delivered_version
            ),
        }


@dataclass(frozen=True, slots=True)
class ProjectManagementManifest:
    enabled: bool = True
    standard: str = PROJECT_CHARTER_STANDARD_ID
    primary_document: str = PROJECT_CHARTER_SOURCE_PATH
    latest_render: str = PROJECT_CHARTER_RENDER_PATH
    latest_release: str | None = None
    modules: Mapping[str, ProjectManagementModule] = field(
        default_factory=lambda: dict(DEFAULT_PROJECT_MANAGEMENT_MODULES)
    )
    validation_policy: ProjectManagementValidationPolicy = field(
        default_factory=ProjectManagementValidationPolicy
    )

    def to_manifest_payload(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "standard": self.standard,
            "primary_document": self.primary_document,
            "latest_render": self.latest_render,
            "latest_release": self.latest_release,
            "modules": {
                key: module.path for key, module in self.modules.items()
            },
            "module_context": {
                key: module.to_manifest_payload()
                for key, module in self.modules.items()
            },
            "validation_policy": self.validation_policy.to_manifest_payload(),
        }


@dataclass(frozen=True, slots=True)
class CharterFieldSource:
    source: str
    confidence: float
    notes: str = ""

    def to_metadata_payload(self) -> dict[str, object]:
        return {
            "source": self.source,
            "confidence": self.confidence,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class ProjectCharterMetadata:
    title: str
    project_name: str
    client: str | None
    author: str
    status: ProjectCharterDocumentState = ProjectCharterDocumentState.DRAFT
    draft_version: str = "v0.1"
    delivered_version: str | None = None
    source_hash: str | None = None
    render_hash: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    field_sources: Mapping[str, CharterFieldSource] = field(default_factory=dict)

    def to_metadata_payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "standard": PROJECT_CHARTER_STANDARD_ID,
            "document": {
                "type": "project_charter",
                "title": self.title,
                "source_path": PROJECT_CHARTER_SOURCE_PATH,
                "render_path": PROJECT_CHARTER_RENDER_PATH,
            },
            "project": {
                "name": self.project_name,
                "client": self.client,
            },
            "author": self.author,
            "status": self.status.value,
            "versions": {
                "draft": self.draft_version,
                "delivered": self.delivered_version,
            },
            "hashes": {
                "source": self.source_hash,
                "render": self.render_hash,
            },
            "timestamps": {
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            },
            "field_sources": {
                field: source.to_metadata_payload()
                for field, source in self.field_sources.items()
            },
        }


@dataclass(frozen=True, slots=True)
class ProjectCharterBrandMetadata:
    logo_status: ProjectCharterLogoStatus
    logo_source: ProjectCharterLogoSource
    client_pdf_requires_logo: bool = True
    logo_path: str | None = "assets/brand/logo.png"
    notes: str = ""

    @property
    def blocks_client_export(self) -> bool:
        return (
            self.client_pdf_requires_logo
            and self.logo_status == ProjectCharterLogoStatus.PENDING
        )

    def to_metadata_payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "standard": PROJECT_CHARTER_STANDARD_ID,
            "logo_status": self.logo_status.value,
            "logo_source": self.logo_source.value,
            "client_pdf_requires_logo": self.client_pdf_requires_logo,
            "logo_path": self.logo_path,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class ProjectCharterValidationIssue:
    severity: ProjectCharterValidationSeverity
    code: str
    field: str
    message: str
    next_action: str
    blocking: bool
    affected_file: str

    def to_payload(self) -> dict[str, object]:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "field": self.field,
            "message": self.message,
            "next_action": self.next_action,
            "blocking": self.blocking,
            "affected_file": self.affected_file,
        }


@dataclass(frozen=True, slots=True)
class ProjectCharterValidationResult:
    issues: tuple[ProjectCharterValidationIssue, ...] = ()
    generated_at: str | None = None

    @property
    def blocking_issues(self) -> tuple[ProjectCharterValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.blocking)

    @property
    def ok(self) -> bool:
        return not self.blocking_issues

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": "codex.projectCharterValidationResult",
            "version": 1,
            "ok": self.ok,
            "generated_at": self.generated_at,
            "blocking_count": len(self.blocking_issues),
            "issues": [issue.to_payload() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class ProjectCharterTraceability:
    source_field: str
    charter_field: str
    metadata_field: str
    required_for_initial_charter: bool
    pending_definition_when_missing: bool
    notes: str = ""

    def to_payload(self) -> dict[str, object]:
        return {
            "source_field": self.source_field,
            "charter_field": self.charter_field,
            "metadata_field": self.metadata_field,
            "required_for_initial_charter": self.required_for_initial_charter,
            "pending_definition_when_missing": (
                self.pending_definition_when_missing
            ),
            "notes": self.notes,
        }


PROJECT_CHARTER_TRACEABILITY: tuple[ProjectCharterTraceability, ...] = (
    ProjectCharterTraceability(
        source_field="ProjectFactoryManifestInput.name",
        charter_field="cover.project_name",
        metadata_field="project.name",
        required_for_initial_charter=True,
        pending_definition_when_missing=False,
    ),
    ProjectCharterTraceability(
        source_field="ProjectFactoryManifestInput.business_type",
        charter_field="executive_summary.business_context",
        metadata_field="field_sources.business_context",
        required_for_initial_charter=False,
        pending_definition_when_missing=True,
        notes="Used as context only; it is not the product objective.",
    ),
    ProjectCharterTraceability(
        source_field="ProjectFactoryManifestInput.primary_goal",
        charter_field="project_objective",
        metadata_field="field_sources.project_objective",
        required_for_initial_charter=True,
        pending_definition_when_missing=True,
    ),
    ProjectCharterTraceability(
        source_field="ProjectFactoryManifestInput.logo_mode",
        charter_field="cover.logo_decision",
        metadata_field="brand.logo_status",
        required_for_initial_charter=True,
        pending_definition_when_missing=True,
    ),
    ProjectCharterTraceability(
        source_field="ProjectFactoryManifestInput.project_assets[role=logo]",
        charter_field="cover.logo",
        metadata_field="brand.logo_path",
        required_for_initial_charter=False,
        pending_definition_when_missing=True,
    ),
    ProjectCharterTraceability(
        source_field="guided_intake.contractPreview.client",
        charter_field="cover.client",
        metadata_field="project.client",
        required_for_initial_charter=True,
        pending_definition_when_missing=True,
    ),
    ProjectCharterTraceability(
        source_field="guided_intake.contractPreview.productObjective",
        charter_field="product_objective",
        metadata_field="field_sources.product_objective",
        required_for_initial_charter=True,
        pending_definition_when_missing=True,
    ),
    ProjectCharterTraceability(
        source_field="guided_intake.contractPreview.benefits",
        charter_field="expected_benefits",
        metadata_field="field_sources.expected_benefits",
        required_for_initial_charter=True,
        pending_definition_when_missing=True,
    ),
    ProjectCharterTraceability(
        source_field="guided_intake.contractPreview.scope",
        charter_field="preliminary_scope",
        metadata_field="field_sources.preliminary_scope",
        required_for_initial_charter=False,
        pending_definition_when_missing=True,
    ),
    ProjectCharterTraceability(
        source_field="guided_intake.missingFields",
        charter_field="pending_definitions",
        metadata_field="field_sources.pending_definitions",
        required_for_initial_charter=True,
        pending_definition_when_missing=False,
    ),
)


@dataclass(frozen=True, slots=True)
class ProjectManagementRoutingResult:
    intent: ProjectManagementIntentCategory
    modules: tuple[ProjectManagementModuleId, ...]
    context_paths: tuple[str, ...]
    charter_content_impacted: bool
    explicit_release_intent: bool
    delivery_action_allowed: bool
    version_impact: ProjectCharterVersionImpact

    def to_payload(self) -> dict[str, object]:
        return {
            "intent": self.intent.value,
            "modules": [module.value for module in self.modules],
            "context_paths": list(self.context_paths),
            "charter_content_impacted": self.charter_content_impacted,
            "explicit_release_intent": self.explicit_release_intent,
            "delivery_action_allowed": self.delivery_action_allowed,
            "version_impact": self.version_impact.value,
        }


def default_project_management_manifest() -> ProjectManagementManifest:
    return ProjectManagementManifest()


def can_transition_charter_state(
    source: ProjectCharterDocumentState,
    target: ProjectCharterDocumentState,
) -> bool:
    if source == target:
        return True
    return target in PROJECT_CHARTER_STATE_TRANSITIONS[source]


def recommend_delivered_version_impact(
    changed_fields: set[str] | frozenset[str],
) -> ProjectCharterVersionImpact:
    impacts = {
        PROJECT_CHARTER_VERSION_RULES[field]
        for field in changed_fields
        if field in PROJECT_CHARTER_VERSION_RULES
    }
    if ProjectCharterVersionImpact.MAJOR in impacts:
        return ProjectCharterVersionImpact.MAJOR
    if ProjectCharterVersionImpact.MINOR in impacts:
        return ProjectCharterVersionImpact.MINOR
    return ProjectCharterVersionImpact.DRAFT_ONLY


def classify_project_management_request(
    text: str,
) -> ProjectManagementRoutingResult:
    normalized = _normalize_intent_text(text)
    explicit_release_intent = _has_any_term(normalized, EXPLICIT_DELIVERY_TERMS)
    intent = _intent_for_text(normalized)
    modules = _modules_for_intent(intent)
    context_paths = _context_paths_for_intent(
        intent,
        explicit_release_intent=explicit_release_intent,
    )
    charter_content_impacted = ProjectManagementModuleId.CHARTER in modules
    version_field = INTENT_VERSION_FIELDS.get(intent)
    version_impact = (
        recommend_delivered_version_impact({version_field})
        if version_field is not None
        else ProjectCharterVersionImpact.DRAFT_ONLY
    )
    delivery_action_allowed = (
        explicit_release_intent
        if intent
        in {
            ProjectManagementIntentCategory.VERSIONING,
            ProjectManagementIntentCategory.RENDER_EXPORT,
        }
        else False
    )
    return ProjectManagementRoutingResult(
        intent=intent,
        modules=modules,
        context_paths=context_paths,
        charter_content_impacted=charter_content_impacted,
        explicit_release_intent=explicit_release_intent,
        delivery_action_allowed=delivery_action_allowed,
        version_impact=version_impact,
    )


def _intent_for_text(text: str) -> ProjectManagementIntentCategory:
    if _has_any_term(text, {"wbs", "edt", "work breakdown", "desglose"}):
        return ProjectManagementIntentCategory.WBS
    if _has_any_term(text, {"alternativa", "alternativas", "matriz", "comparar opciones"}):
        return ProjectManagementIntentCategory.ALTERNATIVES
    if _has_any_term(text, {"riesgo", "riesgos", "risk", "risks"}):
        return ProjectManagementIntentCategory.RISKS
    if _has_any_term(
        text,
        {
            "roles",
            "rol",
            "responsabilidades",
            "responsabilidad",
            "habilidades",
            "competencias",
        },
    ):
        return ProjectManagementIntentCategory.ROLES
    if _has_any_term(text, {"render", "visualizar", "ver como queda", "preview"}):
        return ProjectManagementIntentCategory.RENDER_EXPORT
    if _has_any_term(text, {"entregar", "exportar", "versionar", "release", "pdf"}):
        return ProjectManagementIntentCategory.VERSIONING
    if _has_any_term(text, {"beneficio", "beneficios"}):
        return ProjectManagementIntentCategory.BENEFITS
    if _has_any_term(
        text,
        {"objetivo del producto", "product objective", "producto"},
    ):
        return ProjectManagementIntentCategory.PRODUCT_OBJECTIVE
    if _has_any_term(
        text,
        {"objetivo del proyecto", "project objective", "primary goal"},
    ):
        return ProjectManagementIntentCategory.PROJECT_OBJECTIVE
    if _has_any_term(text, {"alcance", "scope", "incluido", "no incluido"}):
        return ProjectManagementIntentCategory.SCOPE
    if _has_any_term(text, {"pendiente", "pendientes", "definicion", "definiciones"}):
        return ProjectManagementIntentCategory.PENDING_DEFINITIONS
    if _has_any_term(text, {"resumen", "summary", "ejecutivo"}):
        return ProjectManagementIntentCategory.EXECUTIVE_SUMMARY
    return ProjectManagementIntentCategory.CHARTER_IDENTITY


def _modules_for_intent(
    intent: ProjectManagementIntentCategory,
) -> tuple[ProjectManagementModuleId, ...]:
    if intent == ProjectManagementIntentCategory.WBS:
        return (ProjectManagementModuleId.WBS,)
    if intent == ProjectManagementIntentCategory.ROLES:
        return (ProjectManagementModuleId.ROLES,)
    if intent == ProjectManagementIntentCategory.RISKS:
        return (ProjectManagementModuleId.RISKS,)
    if intent == ProjectManagementIntentCategory.ALTERNATIVES:
        return (ProjectManagementModuleId.ALTERNATIVES,)
    return (ProjectManagementModuleId.CHARTER,)


def _context_paths_for_intent(
    intent: ProjectManagementIntentCategory,
    *,
    explicit_release_intent: bool,
) -> tuple[str, ...]:
    if intent in {
        ProjectManagementIntentCategory.VERSIONING,
        ProjectManagementIntentCategory.RENDER_EXPORT,
    }:
        return CHARTER_DELIVERY_CONTEXT_PATHS
    modules = _modules_for_intent(intent)
    if modules == (ProjectManagementModuleId.CHARTER,):
        return CHARTER_ONLY_CONTEXT_PATHS
    paths: list[str] = []
    for module in modules:
        paths.extend(MODULE_CONTEXT_PATHS[module])
    return tuple(dict.fromkeys(paths))


def _normalize_intent_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return " ".join(ascii_text.lower().split())


def _has_any_term(text: str, terms: frozenset[str] | set[str]) -> bool:
    return any(term in text for term in terms)
