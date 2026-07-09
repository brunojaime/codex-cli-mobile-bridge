from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.application.services.sdd_index_service import SddIndexService
from backend.app.application.services.sdd_standard_service import (
    DEFAULT_STANDARD_ID,
    SddStandard,
    SddStandardError,
    SddInvalidStandardError,
    SddStandardService,
    parse_simple_yaml,
)


@dataclass(frozen=True, slots=True)
class SddValidationCheck:
    name: str
    status: str
    detail: str


@dataclass(frozen=True, slots=True)
class SddScaffoldDryRun:
    existing: tuple[str, ...] = ()
    would_create: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    would_overwrite: tuple[str, ...] = ()
    blocked: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SddScaffoldBootstrapResult:
    created: tuple[str, ...] = ()
    existing: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    blocked: tuple[str, ...] = ()
    would_overwrite: tuple[str, ...] = ()
    next_actions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SddTemplateDefinition:
    template_id: str
    artifact_type: str
    destination: str
    source: str
    source_path: Path


class SddPreflightValidationService:
    def __init__(self, standard_service: SddStandardService | None = None) -> None:
        self._standard_service = standard_service or SddStandardService()

    def validate_workspace(self, workspace: Path) -> list[SddValidationCheck]:
        manifest_path = workspace / "codex-bridge.yaml"
        if not manifest_path.is_file():
            return [
                SddValidationCheck(
                    "manifest_adoption",
                    "fail",
                    "Missing codex-bridge.yaml; cannot resolve Workbench SDD standard.",
                )
            ]
        try:
            manifest = parse_simple_yaml(manifest_path.read_text(encoding="utf-8"))
        except SddStandardError as exc:
            return [
                SddValidationCheck(
                    "manifest_adoption",
                    "fail",
                    f"codex-bridge.yaml is not valid supported YAML: {exc}",
                )
            ]
        if not isinstance(manifest, dict):
            return [
                SddValidationCheck(
                    "manifest_adoption",
                    "fail",
                    "codex-bridge.yaml must contain a mapping.",
                )
            ]

        sdd = manifest.get("sdd")
        if not isinstance(sdd, dict):
            return [
                SddValidationCheck(
                    "manifest_adoption",
                    "warn",
                    "Missing sdd manifest block; read-only legacy inspection allowed.",
                )
            ]

        checks: list[SddValidationCheck] = []
        standard = self._load_manifest_standard(sdd, checks)
        checks.extend(self._validate_context_rules(sdd, standard))
        checks.extend(self._validate_templates(standard))
        checks.extend(self._validate_taxonomy_and_governance(workspace, sdd, standard))
        checks.append(self._validate_index_status(workspace, standard))
        checks.append(self._scaffold_dry_run_check(workspace, standard, checks))
        return checks

    def list_templates(
        self,
        standard_id: str = DEFAULT_STANDARD_ID,
    ) -> tuple[SddTemplateDefinition, ...]:
        standard = self._standard_service.load(standard_id)
        definitions, errors = _template_definitions(standard)
        if errors:
            raise SddInvalidStandardError("; ".join(errors))
        return definitions

    def scaffold_dry_run(
        self,
        workspace: Path,
        *,
        standard: SddStandard | None,
        blocked: tuple[str, ...] = (),
    ) -> SddScaffoldDryRun:
        if blocked:
            return SddScaffoldDryRun(blocked=blocked)
        if standard is None:
            return SddScaffoldDryRun(
                blocked=("sdd.standard is required before scaffold writes.",),
            )
        expected, path_errors = _scaffold_artifact_paths(standard, workspace)
        if path_errors:
            return SddScaffoldDryRun(blocked=tuple(path_errors))
        existing: list[str] = []
        would_create: list[str] = []
        would_overwrite: list[str] = []
        for relative_path in expected:
            path = workspace / relative_path
            if path.exists():
                if _existing_matches_scaffold_contract(path, relative_path):
                    existing.append(relative_path)
                else:
                    would_overwrite.append(relative_path)
            else:
                would_create.append(relative_path)
        if would_overwrite:
            return SddScaffoldDryRun(
                existing=tuple(existing),
                would_create=tuple(would_create),
                would_overwrite=tuple(would_overwrite),
                blocked=tuple(
                    f"would overwrite incompatible existing artifact: {path}"
                    for path in would_overwrite
                ),
            )
        return SddScaffoldDryRun(
            existing=tuple(existing),
            would_create=tuple(would_create),
            skipped=(),
            would_overwrite=(),
            blocked=(),
        )

    def bootstrap_scaffold(self, workspace: Path) -> SddScaffoldBootstrapResult:
        workspace = workspace.expanduser().resolve()
        checks = self.validate_workspace(workspace)
        blockers = tuple(
            f"{check.name}: {check.detail}"
            for check in checks
            if check.status == "fail"
        )
        if blockers:
            return SddScaffoldBootstrapResult(
                blocked=blockers,
                next_actions=("Fix validation failures and rerun scaffold bootstrap.",),
            )

        standard, standard_error = self._load_workspace_standard(workspace)
        if standard is None:
            return SddScaffoldBootstrapResult(
                blocked=(standard_error or "sdd.standard is required before writes.",),
                next_actions=("Declare sdd.standard in codex-bridge.yaml.",),
            )

        dry_run = self.scaffold_dry_run(workspace, standard=standard)
        if dry_run.blocked:
            return SddScaffoldBootstrapResult(
                existing=dry_run.existing,
                skipped=dry_run.skipped,
                blocked=dry_run.blocked,
                would_overwrite=dry_run.would_overwrite,
                next_actions=("Fix scaffold dry-run blockers before writing files.",),
            )

        template_contents, template_errors = _template_contents_by_destination(standard)
        if template_errors:
            return SddScaffoldBootstrapResult(
                existing=dry_run.existing,
                skipped=dry_run.skipped,
                blocked=tuple(template_errors),
                next_actions=("Fix template metadata before writing scaffold files.",),
            )
        missing_templates = tuple(
            relative_path
            for relative_path in dry_run.would_create
            if not _expected_scaffold_directory(relative_path)
            and relative_path not in template_contents
        )
        if missing_templates:
            return SddScaffoldBootstrapResult(
                existing=dry_run.existing,
                skipped=dry_run.skipped,
                blocked=tuple(
                    f"Missing scaffold template for destination: {relative_path}"
                    for relative_path in missing_templates
                ),
                next_actions=(
                    "Add missing scaffold template metadata and source files.",
                ),
            )

        prewrite_blockers = _prewrite_blockers(workspace, dry_run)
        if prewrite_blockers:
            return SddScaffoldBootstrapResult(
                existing=dry_run.existing,
                skipped=dry_run.skipped,
                blocked=tuple(prewrite_blockers),
                would_overwrite=dry_run.would_overwrite,
                next_actions=("Resolve pre-existing output conflicts and rerun.",),
            )

        created: list[str] = []
        for relative_path in dry_run.would_create:
            target = workspace / relative_path
            if _expected_scaffold_directory(relative_path):
                target.mkdir(parents=True, exist_ok=False)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                _write_file_no_overwrite(
                    target,
                    template_contents[relative_path],
                )
            created.append(relative_path)

        next_actions = (
            (
                "Review created SDD scaffold artifacts and commit project-specific content.",
            )
            if created
            else ("No scaffold changes needed.",)
        )
        return SddScaffoldBootstrapResult(
            created=tuple(created),
            existing=dry_run.existing,
            skipped=dry_run.skipped,
            blocked=(),
            would_overwrite=(),
            next_actions=next_actions,
        )

    def _load_workspace_standard(
        self,
        workspace: Path,
    ) -> tuple[SddStandard | None, str | None]:
        manifest_path = workspace / "codex-bridge.yaml"
        if not manifest_path.is_file():
            return None, "Missing codex-bridge.yaml."
        try:
            manifest = parse_simple_yaml(manifest_path.read_text(encoding="utf-8"))
        except SddStandardError as exc:
            return None, f"codex-bridge.yaml is not valid supported YAML: {exc}"
        if not isinstance(manifest, dict):
            return None, "codex-bridge.yaml must contain a mapping."
        sdd = manifest.get("sdd")
        if not isinstance(sdd, dict):
            return None, "Missing sdd manifest block."
        raw_standard = sdd.get("standard")
        if not isinstance(raw_standard, str):
            return None, "sdd.standard must be a string such as workbench-sdd/v1."
        try:
            return self._standard_service.load(raw_standard), None
        except SddStandardError as exc:
            return None, str(exc)

    def _load_manifest_standard(
        self,
        sdd: dict[str, Any],
        checks: list[SddValidationCheck],
    ) -> SddStandard | None:
        raw_standard = sdd.get("standard")
        if raw_standard is None:
            checks.append(
                SddValidationCheck(
                    "standard",
                    "warn",
                    "sdd.standard not declared; read-only legacy inspection allowed, "
                    "write/context/scaffold flows blocked.",
                )
            )
            return None
        if not isinstance(raw_standard, str):
            checks.append(
                SddValidationCheck(
                    "standard",
                    "fail",
                    "sdd.standard must be a string such as workbench-sdd/v1.",
                )
            )
            return None
        try:
            standard = self._standard_service.load(raw_standard)
        except SddStandardError as exc:
            checks.append(SddValidationCheck("standard", "fail", str(exc)))
            return None
        checks.append(
            SddValidationCheck(
                "standard",
                "pass",
                f"Resolved {standard.requested_id} as {standard.id} from "
                f"{standard.source_path}.",
            )
        )
        return standard

    def _validate_context_rules(
        self,
        sdd: dict[str, Any],
        standard: SddStandard | None,
    ) -> list[SddValidationCheck]:
        context_rules = sdd.get("context_rules")
        if context_rules is None:
            return [
                SddValidationCheck(
                    "context_rules",
                    "pass",
                    "No project overrides; Workbench defaults apply.",
                )
            ]
        if not isinstance(context_rules, dict):
            return [
                SddValidationCheck(
                    "context_rules",
                    "fail",
                    "sdd.context_rules must be a mapping.",
                )
            ]
        allowed = set(_standard_allowed_context_keys(standard))
        unknown = sorted(set(context_rules) - allowed)
        if unknown:
            return [
                SddValidationCheck(
                    "context_rules",
                    "fail",
                    "Unsupported sdd.context_rules key(s): " + ", ".join(unknown),
                )
            ]
        errors = _context_rule_errors(context_rules, standard)
        if errors:
            return [
                SddValidationCheck(
                    "context_rules",
                    "fail",
                    "; ".join(errors),
                )
            ]
        merged = _merged_context_rules(context_rules, standard)
        candidate_limits = merged["candidate_limits"]
        return [
            SddValidationCheck(
                "context_rules",
                "pass",
                "Project overrides valid; precedence is Workbench default -> "
                "project profile -> project overrides; merged candidate_limits "
                f"related_specs={candidate_limits['related_specs']} "
                f"related_diagrams={candidate_limits['related_diagrams']}.",
            )
        ]

    def _validate_templates(
        self,
        standard: SddStandard | None,
    ) -> list[SddValidationCheck]:
        if standard is None:
            return [
                SddValidationCheck(
                    "template_metadata",
                    "warn",
                    "Template metadata skipped because no standard was resolved.",
                )
            ]
        templates = standard.payload.get("templates")
        if not isinstance(templates, dict):
            return [
                SddValidationCheck(
                    "template_metadata",
                    "fail",
                    "Standard is missing templates metadata.",
                )
            ]
        definitions, errors = _template_definitions(standard)
        if errors:
            return [
                SddValidationCheck(
                    "template_metadata",
                    "fail",
                    "; ".join(errors),
                )
            ]
        return [
            SddValidationCheck(
                "template_metadata",
                "pass",
                f"{len(definitions)} template definition(s) declared: "
                + ", ".join(definition.template_id for definition in definitions),
            )
        ]

    def _validate_taxonomy_and_governance(
        self,
        workspace: Path,
        sdd: dict[str, Any],
        standard: SddStandard | None,
    ) -> list[SddValidationCheck]:
        if standard is None:
            return [
                SddValidationCheck(
                    "taxonomy_governance",
                    "warn",
                    "Taxonomy and governance skipped because no standard was resolved.",
                )
            ]
        taxonomy_errors = _taxonomy_errors(standard)
        artifact_errors = _artifact_governance_errors(workspace, sdd, standard)
        metadata_status, metadata_detail = _diagram_metadata_status(
            workspace,
            sdd,
            standard,
        )
        mermaid_errors = _mermaid_validation_errors(workspace, standard)
        render_policy = _diagram_governance_value(
            standard,
            "render_validation_policy",
            default="not_available_without_configured_renderer",
        )
        return [
            SddValidationCheck(
                "taxonomy_governance",
                "fail" if taxonomy_errors else "pass",
                "; ".join(taxonomy_errors)
                if taxonomy_errors
                else "Diagram taxonomy, notation, ownership, and template artifact types are valid.",
            ),
            SddValidationCheck(
                "artifact_governance",
                "fail" if artifact_errors else "pass",
                "; ".join(artifact_errors)
                if artifact_errors
                else "Artifact ownership and protected baseline paths are valid.",
            ),
            SddValidationCheck(
                "diagram_metadata",
                metadata_status,
                metadata_detail,
            ),
            SddValidationCheck(
                "mermaid_validation",
                "fail" if mermaid_errors else "pass",
                "; ".join(mermaid_errors)
                if mermaid_errors
                else "Mermaid source directives are supported; render validation skipped because "
                f"{render_policy}.",
            ),
        ]

    def _validate_index_status(
        self,
        workspace: Path,
        standard: SddStandard | None,
    ) -> SddValidationCheck:
        if standard is None:
            return SddValidationCheck(
                "index_status",
                "warn",
                "Index validation skipped because no standard was resolved.",
            )
        status = SddIndexService().ensure_indexes(
            workspace,
            standard=standard,
            auto_regenerate=False,
            allow_degraded=True,
        )
        if status.state == "fresh":
            return SddValidationCheck(
                "index_status",
                "pass",
                f"index_status=fresh mode={status.mode}; {status.detail}",
            )
        return SddValidationCheck(
            "index_status",
            "warn",
            "index_status="
            f"{status.state} mode={status.mode}; missing={','.join(status.missing)} "
            f"stale={','.join(status.stale)}; {status.detail}",
        )

    def _scaffold_dry_run_check(
        self,
        workspace: Path,
        standard: SddStandard | None,
        prior_checks: list[SddValidationCheck],
    ) -> SddValidationCheck:
        blockers = tuple(
            f"{check.name}: {check.detail}"
            for check in prior_checks
            if check.status == "fail"
        )
        dry_run = self.scaffold_dry_run(
            workspace,
            standard=standard,
            blocked=blockers,
        )
        if dry_run.blocked:
            status = (
                "warn"
                if dry_run.blocked
                == ("sdd.standard is required before scaffold writes.",)
                else "fail"
            )
            return SddValidationCheck(
                "scaffold_dry_run",
                status,
                "Scaffold writes blocked: " + "; ".join(dry_run.blocked),
            )
        return SddValidationCheck(
            "scaffold_dry_run",
            "pass",
            "dry-run only; existing="
            f"{len(dry_run.existing)}, would_create={len(dry_run.would_create)}, "
            f"skipped={len(dry_run.skipped)}, "
            f"would_overwrite={len(dry_run.would_overwrite)}, blocked=0.",
        )


def _standard_allowed_context_keys(standard: SddStandard | None) -> tuple[str, ...]:
    if standard is None:
        return (
            "domains",
            "excluded_paths",
            "candidate_limits",
            "protected_baseline",
            "preferred_context",
        )
    context_rules = standard.payload.get("context_rules")
    if not isinstance(context_rules, dict):
        return ()
    allowed = context_rules.get("allowed_override_keys")
    if not _is_string_list(allowed):
        return ()
    return tuple(allowed)


def _context_rule_errors(
    context_rules: dict[str, Any],
    standard: SddStandard | None,
) -> list[str]:
    errors: list[str] = []
    domains = context_rules.get("domains")
    if domains is not None:
        if not isinstance(domains, dict):
            errors.append("domains must be a mapping")
        else:
            for domain_name, domain_rules in domains.items():
                if not isinstance(domain_name, str) or not isinstance(
                    domain_rules,
                    dict,
                ):
                    errors.append("each domain rule must be a mapping")
                    continue
                for key in ("modules", "preferred_context"):
                    value = domain_rules.get(key)
                    if value is not None and not _is_string_list(value):
                        errors.append(
                            f"domains.{domain_name}.{key} must be a string list"
                        )
    for key in ("excluded_paths", "protected_baseline", "preferred_context"):
        value = context_rules.get(key)
        if value is not None and not _is_string_list(value):
            errors.append(f"{key} must be a string list")
    candidate_limits = context_rules.get("candidate_limits")
    if candidate_limits is not None:
        if not isinstance(candidate_limits, dict):
            errors.append("candidate_limits must be a mapping")
        else:
            default_limits = _standard_candidate_limits(standard)
            for key, value in candidate_limits.items():
                if key not in {"related_specs", "related_diagrams"}:
                    errors.append(f"candidate_limits.{key} is unsupported")
                    continue
                if not isinstance(value, int) or value < 0:
                    errors.append(
                        f"candidate_limits.{key} must be a non-negative integer"
                    )
                    continue
                default_value = default_limits.get(key)
                if default_value is not None and value > default_value:
                    errors.append(
                        f"candidate_limits.{key} may not exceed Workbench default "
                        f"{default_value}"
                    )
    return errors


def _standard_candidate_limits(standard: SddStandard | None) -> dict[str, int]:
    if standard is None:
        return {"related_specs": 5, "related_diagrams": 3}
    value = standard.payload.get("candidate_limits")
    if not isinstance(value, dict):
        return {}
    return {key: item for key, item in value.items() if isinstance(item, int)}


def _merged_context_rules(
    context_rules: dict[str, Any],
    standard: SddStandard | None,
) -> dict[str, Any]:
    default_limits = {"related_specs": 5, "related_diagrams": 3}
    default_limits.update(_standard_candidate_limits(standard))
    project_limits = context_rules.get("candidate_limits")
    if isinstance(project_limits, dict):
        default_limits.update(
            {
                key: value
                for key, value in project_limits.items()
                if key in default_limits and isinstance(value, int)
            }
        )
    return {
        "precedence": [
            "workbench_default",
            "project_profile",
            "project_override",
        ],
        "candidate_limits": default_limits,
        "domains": context_rules.get("domains", {}),
        "excluded_paths": context_rules.get("excluded_paths", []),
        "protected_baseline": context_rules.get("protected_baseline", []),
        "preferred_context": context_rules.get("preferred_context", []),
    }


def _template_definitions(
    standard: SddStandard,
) -> tuple[tuple[SddTemplateDefinition, ...], list[str]]:
    templates = standard.payload.get("templates")
    if not isinstance(templates, dict):
        return (), ["Standard is missing templates metadata."]
    required_metadata = templates.get("required_metadata")
    required_templates = templates.get("required")
    catalog = templates.get("catalog")
    if not _is_string_list(required_metadata):
        return (), ["Standard templates.required_metadata must be a string list."]
    if not _is_string_list(required_templates):
        return (), ["Standard templates.required must be a string list."]
    if not isinstance(catalog, dict):
        return (), ["Standard templates.catalog must be a mapping."]

    definitions: list[SddTemplateDefinition] = []
    errors: list[str] = []
    standard_root = standard.source_path.parent.resolve()
    for template_id, metadata in catalog.items():
        if not isinstance(template_id, str) or not isinstance(metadata, dict):
            errors.append("Each templates.catalog entry must be a mapping.")
            continue
        missing_fields = [
            field
            for field in required_metadata
            if not isinstance(metadata.get(field), str) or not metadata.get(field)
        ]
        if missing_fields:
            errors.append(
                f"Template {template_id} is missing required metadata: "
                + ", ".join(missing_fields)
            )
            continue
        declared_id = metadata["template_id"]
        if declared_id != template_id:
            errors.append(
                f"Template catalog key {template_id} does not match "
                f"template_id {declared_id}."
            )
        source = metadata.get("source")
        if not isinstance(source, str) or not source:
            errors.append(
                f"Template {template_id} is missing required metadata: source"
            )
            continue
        source_path, source_error = _safe_template_source_path(standard_root, source)
        if source_error is not None:
            errors.append(f"Template {template_id} {source_error}")
            continue
        if not source_path.is_file():
            errors.append(f"Template {template_id} source file not found: {source}")
            continue
        content = source_path.read_text(encoding="utf-8")
        unresolved = _unresolved_template_markers(content)
        if unresolved:
            errors.append(
                f"Template {template_id} contains unresolved variable marker(s): "
                + ", ".join(unresolved)
            )
        definitions.append(
            SddTemplateDefinition(
                template_id=template_id,
                artifact_type=metadata["artifact_type"],
                destination=metadata["destination"],
                source=source,
                source_path=source_path,
            )
        )

    catalog_ids = set(catalog)
    missing_required = sorted(set(required_templates) - catalog_ids)
    if missing_required:
        errors.append(
            "Standard templates.catalog is missing required template(s): "
            + ", ".join(missing_required)
        )
    return tuple(definitions), errors


def _template_contents_by_destination(
    standard: SddStandard,
) -> tuple[dict[str, str], list[str]]:
    definitions, errors = _template_definitions(standard)
    if errors:
        return {}, errors
    by_destination: dict[str, str] = {}
    duplicate_destinations: list[str] = []
    for definition in definitions:
        if definition.destination in by_destination:
            duplicate_destinations.append(definition.destination)
            continue
        by_destination[definition.destination] = definition.source_path.read_text(
            encoding="utf-8"
        )
    if duplicate_destinations:
        errors.append(
            "Duplicate template destination(s): " + ", ".join(duplicate_destinations)
        )
    return by_destination, errors


def _taxonomy_errors(standard: SddStandard) -> list[str]:
    errors: list[str] = []
    expected_diagram_types = {
        "system-context",
        "components",
        "deployment",
        "sequence",
        "state",
        "domain-model",
        "entity-relationship",
        "component-impact",
        "domain-impact",
        "data-impact",
    }
    diagram_taxonomy = standard.payload.get("diagram_taxonomy")
    if not isinstance(diagram_taxonomy, dict):
        return ["Standard is missing diagram_taxonomy."]
    baseline = _string_list_value(diagram_taxonomy, "baseline")
    feature = _string_list_value(diagram_taxonomy, "feature")
    notation = diagram_taxonomy.get("notation")
    source_directives = diagram_taxonomy.get("source_directives")
    if baseline is None:
        errors.append("diagram_taxonomy.baseline must be a string list")
        baseline = []
    if feature is None:
        errors.append("diagram_taxonomy.feature must be a string list")
        feature = []
    declared_types = set(baseline) | set(feature)
    missing_types = sorted(expected_diagram_types - declared_types)
    if missing_types:
        errors.append("diagram_taxonomy missing type(s): " + ", ".join(missing_types))
    if not isinstance(notation, dict):
        errors.append("diagram_taxonomy.notation must be a mapping")
        notation = {}
    if not isinstance(source_directives, dict):
        errors.append("diagram_taxonomy.source_directives must be a mapping")
        source_directives = {}
    for diagram_type in sorted(declared_types):
        notation_value = notation.get(diagram_type)
        if not isinstance(notation_value, str):
            errors.append(f"diagram_taxonomy.notation.{diagram_type} is required")
            continue
        directives = source_directives.get(notation_value)
        if not _is_string_list(directives):
            errors.append(
                f"diagram_taxonomy.source_directives.{notation_value} must be a string list"
            )

    allowed_artifact_types = set(_standard_artifact_types(standard))
    if not allowed_artifact_types:
        errors.append("artifact_types.required must declare allowed artifact types")
    definitions, template_errors = _template_definitions(standard)
    errors.extend(template_errors)
    for definition in definitions:
        if definition.artifact_type not in allowed_artifact_types:
            errors.append(
                f"Template {definition.template_id} uses unsupported artifact type "
                f"{definition.artifact_type}"
            )
    allowed_owners = _allowed_owners(standard)
    if "workbench" not in allowed_owners or "project" not in allowed_owners:
        errors.append("ownership.allowed_owners must include workbench and project")
    return errors


def _artifact_governance_errors(
    workspace: Path,
    sdd: dict[str, Any],
    standard: SddStandard,
) -> list[str]:
    errors: list[str] = []
    protected_baseline = _protected_baseline_paths(sdd)
    if protected_baseline is None:
        return ["sdd.protected_baseline must be a string list when declared"]
    workspace_root = workspace.expanduser().resolve()
    for relative_path in protected_baseline:
        path_errors = _governed_project_path_errors(relative_path, workspace_root)
        if path_errors:
            errors.extend(path_errors)
            continue
        if relative_path.endswith(".mmd") and not relative_path.startswith(
            tuple(_diagram_governance_list(standard, "baseline_path_prefixes"))
        ):
            errors.append(
                f"Protected baseline diagram must live under a baseline path: {relative_path}"
            )
    return errors


def _diagram_metadata_status(
    workspace: Path,
    sdd: dict[str, Any],
    standard: SddStandard,
) -> tuple[str, str]:
    metadata_errors: list[str] = []
    missing_metadata: list[str] = []
    workspace_root = workspace.expanduser().resolve()
    for diagram_path in _diagram_paths(workspace_root):
        metadata_path = diagram_path.with_suffix(".yaml")
        relative_diagram = diagram_path.relative_to(workspace_root).as_posix()
        if not metadata_path.is_file():
            missing_metadata.append(relative_diagram)
            continue
        try:
            metadata = parse_simple_yaml(metadata_path.read_text(encoding="utf-8"))
        except SddStandardError as exc:
            metadata_errors.append(
                f"{metadata_path.name}: invalid metadata YAML: {exc}"
            )
            continue
        if not isinstance(metadata, dict):
            metadata_errors.append(f"{metadata_path.name}: metadata must be a mapping")
            continue
        metadata_errors.extend(
            _diagram_metadata_errors(
                metadata,
                relative_diagram=relative_diagram,
                standard=standard,
                protected_baseline=_protected_baseline_paths(sdd) or (),
            )
        )
    if metadata_errors:
        return "fail", "; ".join(metadata_errors)
    if missing_metadata:
        return (
            "warn",
            f"{len(missing_metadata)} diagram metadata sidecar(s) missing; "
            "diagram metadata validation is degraded: "
            + ", ".join(missing_metadata[:5]),
        )
    return "pass", "All diagram metadata sidecars are present and valid."


def _diagram_metadata_errors(
    metadata: dict[str, Any],
    *,
    relative_diagram: str,
    standard: SddStandard,
    protected_baseline: tuple[str, ...],
) -> list[str]:
    errors: list[str] = []
    diagram_taxonomy = standard.payload.get("diagram_taxonomy")
    required_metadata = (
        diagram_taxonomy.get("required_metadata")
        if isinstance(diagram_taxonomy, dict)
        else None
    )
    if not _is_string_list(required_metadata):
        return ["diagram_taxonomy.required_metadata must be a string list"]
    missing = [
        field
        for field in required_metadata
        if not isinstance(metadata.get(field), str) or not metadata.get(field)
    ]
    if missing:
        errors.append(
            f"{relative_diagram}: missing required diagram metadata: "
            + ", ".join(missing)
        )
        return errors
    diagram_type = metadata["diagram_type"]
    scope = metadata["scope"]
    owner = metadata["owner"]
    source = metadata["source"]
    allowed_types = set(_diagram_types(standard))
    if diagram_type not in allowed_types:
        errors.append(f"{relative_diagram}: unsupported diagram_type {diagram_type}")
    if owner not in _allowed_owners(standard):
        errors.append(f"{relative_diagram}: invalid owner {owner}")
    source_errors = _governed_project_path_errors(source, Path("/workspace"))
    if source_errors:
        errors.append(f"{relative_diagram}: invalid metadata source {source}")
    elif source != relative_diagram:
        errors.append(
            f"{relative_diagram}: metadata source {source} must match diagram path"
        )
    baseline_scope = _diagram_governance_value(
        standard,
        "baseline_scope",
        default="baseline",
    )
    feature_scope = _diagram_governance_value(
        standard,
        "feature_scope",
        default="feature",
    )
    baseline_types = set(_diagram_taxonomy_list(standard, "baseline"))
    feature_types = set(_diagram_taxonomy_list(standard, "feature"))
    if scope == baseline_scope:
        if diagram_type not in baseline_types:
            errors.append(
                f"{relative_diagram}: baseline diagram_type {diagram_type} is not allowed"
            )
        if not relative_diagram.startswith(
            tuple(_diagram_governance_list(standard, "baseline_path_prefixes"))
        ):
            errors.append(f"{relative_diagram}: baseline diagram path is invalid")
    elif scope == feature_scope:
        if diagram_type not in feature_types:
            errors.append(
                f"{relative_diagram}: feature diagram_type {diagram_type} is not allowed"
            )
        if not relative_diagram.startswith(
            tuple(_diagram_governance_list(standard, "feature_path_prefixes"))
        ):
            errors.append(f"{relative_diagram}: feature diagram path is invalid")
    else:
        errors.append(f"{relative_diagram}: invalid scope {scope}")
    if scope == baseline_scope or relative_diagram in protected_baseline:
        expected_policy = _diagram_governance_value(
            standard,
            "protected_baseline_policy",
            default="baseline_impact_required",
        )
        if metadata.get("change_policy") != expected_policy:
            errors.append(
                f"{relative_diagram}: protected baseline metadata must declare "
                f"change_policy {expected_policy}"
            )
    return errors


def _mermaid_validation_errors(workspace: Path, standard: SddStandard) -> list[str]:
    errors: list[str] = []
    workspace_root = workspace.expanduser().resolve()
    supported_directives = _supported_mermaid_directives(standard)
    for diagram_path in _diagram_paths(workspace_root):
        relative_diagram = diagram_path.relative_to(workspace_root).as_posix()
        content = diagram_path.read_text(encoding="utf-8", errors="replace")
        first_line = _first_nonempty_line(content)
        if first_line is None:
            errors.append(f"{relative_diagram}: Mermaid source is empty")
            continue
        directive = first_line.split(maxsplit=1)[0]
        if directive.lower() not in supported_directives:
            errors.append(
                f"{relative_diagram}: unsupported Mermaid directive {directive}"
            )
    return errors


def _safe_template_source_path(
    standard_root: Path,
    source: str,
) -> tuple[Path, str | None]:
    source_path = Path(source)
    if source_path.is_absolute():
        return standard_root, f"source must be relative: {source}"
    if ".." in source_path.parts:
        return standard_root, f"source traversal is not allowed: {source}"
    resolved = (standard_root / source_path).resolve()
    if not _is_relative_to(resolved, standard_root):
        return standard_root, f"source escapes standard root: {source}"
    return resolved, None


def _unresolved_template_markers(content: str) -> tuple[str, ...]:
    markers = []
    for marker in ("{{", "}}", "${", "<TODO_TEMPLATE>"):
        if marker in content:
            markers.append(marker)
    return tuple(markers)


def _scaffold_artifact_paths(
    standard: SddStandard,
    workspace: Path,
) -> tuple[tuple[str, ...], list[str]]:
    scaffold = standard.payload.get("scaffold")
    if not isinstance(scaffold, dict):
        return (), ["Standard is missing scaffold.required_artifacts metadata."]
    required_artifacts = scaffold.get("required_artifacts")
    if not _is_string_list(required_artifacts):
        return (), ["Standard scaffold.required_artifacts must be a string list."]

    workspace_root = workspace.expanduser().resolve()
    specs_root = (workspace_root / "specs").resolve()
    normalized: list[str] = []
    seen_targets: dict[Path, str] = {}
    errors: list[str] = []
    for relative_path in required_artifacts:
        path_errors = _scaffold_path_errors(relative_path, workspace_root, specs_root)
        if path_errors:
            errors.extend(path_errors)
            continue
        target = (workspace_root / relative_path).resolve()
        previous = seen_targets.get(target)
        if previous is not None:
            errors.append(
                f"Duplicate scaffold target path: {relative_path} conflicts with "
                f"{previous}"
            )
            continue
        seen_targets[target] = relative_path
        normalized.append(relative_path)
    return tuple(normalized), errors


def _scaffold_path_errors(
    relative_path: str,
    workspace_root: Path,
    specs_root: Path,
) -> list[str]:
    errors: list[str] = []
    path = Path(relative_path)
    if not relative_path.strip() or relative_path in {".", "./"}:
        return ["Scaffold target path must not be empty."]
    if path.is_absolute():
        return [f"Scaffold target path must be relative: {relative_path}"]
    if ".." in path.parts:
        return [f"Scaffold target path traversal is not allowed: {relative_path}"]
    target = (workspace_root / path).resolve()
    if not _is_relative_to(target, workspace_root):
        errors.append(f"Scaffold target path escapes workspace: {relative_path}")
    if (
        path.parts
        and path.parts[0] == "specs"
        and not _is_relative_to(
            target,
            specs_root,
        )
    ):
        errors.append(f"Scaffold target path escapes specs root: {relative_path}")
    return errors


def _existing_matches_scaffold_contract(path: Path, relative_path: str) -> bool:
    if _expected_scaffold_directory(relative_path):
        return path.is_dir()
    return path.is_file()


def _expected_scaffold_directory(relative_path: str) -> bool:
    return relative_path in {"specs", ".sdd"} or not Path(relative_path).suffix


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _prewrite_blockers(
    workspace: Path,
    dry_run: SddScaffoldDryRun,
) -> list[str]:
    blockers: list[str] = []
    workspace_root = workspace.expanduser().resolve()
    specs_root = (workspace_root / "specs").resolve()
    for relative_path in dry_run.would_create:
        path_errors = _scaffold_path_errors(relative_path, workspace_root, specs_root)
        if path_errors:
            blockers.extend(path_errors)
            continue
        target = workspace_root / relative_path
        if target.exists():
            blockers.append(
                f"Refusing to overwrite existing scaffold target: {relative_path}"
            )
            continue
        parent = target.parent
        if parent.exists() and not parent.is_dir():
            blockers.append(
                f"Scaffold target parent is not a directory: {parent.relative_to(workspace_root)}"
            )
    return blockers


def _standard_artifact_types(standard: SddStandard) -> tuple[str, ...]:
    artifact_types = standard.payload.get("artifact_types")
    if not isinstance(artifact_types, dict):
        return ()
    required = _string_list_value(artifact_types, "required") or []
    optional = _string_list_value(artifact_types, "optional") or []
    return tuple(required + optional)


def _allowed_owners(standard: SddStandard) -> tuple[str, ...]:
    ownership = standard.payload.get("ownership")
    if not isinstance(ownership, dict):
        return ()
    return tuple(_string_list_value(ownership, "allowed_owners") or ())


def _diagram_types(standard: SddStandard) -> tuple[str, ...]:
    return tuple(
        _diagram_taxonomy_list(standard, "baseline")
        + _diagram_taxonomy_list(standard, "feature")
    )


def _diagram_taxonomy_list(standard: SddStandard, key: str) -> list[str]:
    diagram_taxonomy = standard.payload.get("diagram_taxonomy")
    if not isinstance(diagram_taxonomy, dict):
        return []
    return _string_list_value(diagram_taxonomy, key) or []


def _diagram_governance_list(standard: SddStandard, key: str) -> list[str]:
    governance = standard.payload.get("diagram_governance")
    if not isinstance(governance, dict):
        return []
    return _string_list_value(governance, key) or []


def _diagram_governance_value(
    standard: SddStandard,
    key: str,
    *,
    default: str,
) -> str:
    governance = standard.payload.get("diagram_governance")
    if not isinstance(governance, dict):
        return default
    value = governance.get(key)
    return value if isinstance(value, str) and value else default


def _protected_baseline_paths(sdd: dict[str, Any]) -> tuple[str, ...] | None:
    protected = sdd.get("protected_baseline")
    if protected is None:
        context_rules = sdd.get("context_rules")
        if isinstance(context_rules, dict):
            protected = context_rules.get("protected_baseline")
    if protected is None:
        return ()
    if not _is_string_list(protected):
        return None
    return tuple(protected)


def _governed_project_path_errors(
    relative_path: str,
    workspace_root: Path,
) -> list[str]:
    path = Path(relative_path)
    if not relative_path.strip() or relative_path in {".", "./"}:
        return ["Governed path must not be empty."]
    if path.is_absolute():
        return [f"Governed path must be relative: {relative_path}"]
    if ".." in path.parts:
        return [f"Governed path traversal is not allowed: {relative_path}"]
    target = (workspace_root / path).resolve()
    if not _is_relative_to(target, workspace_root):
        return [f"Governed path escapes workspace: {relative_path}"]
    return []


def _diagram_paths(workspace: Path) -> tuple[Path, ...]:
    candidates = [
        *workspace.glob("architecture/*.mmd"),
        *workspace.glob("specs/*/diagrams/*.mmd"),
    ]
    return tuple(
        sorted(
            (
                path.resolve()
                for path in candidates
                if path.is_file() and _is_relative_to(path.resolve(), workspace)
            ),
            key=lambda item: item.as_posix(),
        )
    )


def _supported_mermaid_directives(standard: SddStandard) -> set[str]:
    diagram_taxonomy = standard.payload.get("diagram_taxonomy")
    if not isinstance(diagram_taxonomy, dict):
        return set()
    source_directives = diagram_taxonomy.get("source_directives")
    if not isinstance(source_directives, dict):
        return set()
    directives: set[str] = set()
    for values in source_directives.values():
        if _is_string_list(values):
            directives.update(value.lower() for value in values)
    return directives


def _first_nonempty_line(content: str) -> str | None:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _string_list_value(mapping: dict[str, Any], key: str) -> list[str] | None:
    value = mapping.get(key)
    if not _is_string_list(value):
        return None
    return value


def _write_file_no_overwrite(path: Path, content: str) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
        ) as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.link(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _is_string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)
