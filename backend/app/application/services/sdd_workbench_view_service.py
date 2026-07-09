from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

from backend.app.application.services.sdd_llm_instruction_service import (
    SddLlmInstructionService,
)
from backend.app.application.services.sdd_context_pack_service import SddContextPack
from backend.app.application.services.sdd_project_service import (
    SddDiagram,
    SddProject,
    SddSpec,
)
from backend.app.application.services.sdd_standard_service import (
    SddStandardError,
    parse_simple_yaml,
)
from backend.app.application.services.sdd_validation_service import (
    SddPreflightValidationService,
    SddValidationCheck,
)


@dataclass(frozen=True, slots=True)
class SddWorkbenchHealth:
    status: str
    spec_count: int
    diagram_count: int
    missing_required: tuple[str, ...]
    checks: tuple[SddValidationCheck, ...]
    next_actions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SddWorkbenchStandardsCompliance:
    status: str
    standard_id: str | None
    checks: tuple[SddValidationCheck, ...]


@dataclass(frozen=True, slots=True)
class SddWorkbenchContextCandidate:
    path: str
    reason: str
    rank: int


@dataclass(frozen=True, slots=True)
class SddWorkbenchContextPreview:
    status: str
    preset: str
    mode: str
    index_status: str
    error: str | None
    prompt: str
    required_files: tuple[str, ...]
    related_specs: tuple[SddWorkbenchContextCandidate, ...]
    related_diagrams: tuple[SddWorkbenchContextCandidate, ...]
    blocked_reads: tuple[str, ...]
    routing_decisions: tuple[str, ...]
    next_actions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SddWorkbenchFeatureSpecView:
    id: str
    title: str
    description: str
    path: str
    lifecycle_status: str
    traceability_status: str
    created_at: str | None
    updated_at: str | None
    generated_title: bool
    generated_description: bool
    user_pinned_title: bool
    user_pinned_description: bool
    task_total: int
    task_completed: int
    task_pending: int
    last_run_state: str | None
    metadata_status: str
    metadata_warnings: tuple[str, ...]
    metadata_stale_paths: tuple[str, ...]
    available_files: tuple[str, ...]
    missing: tuple[str, ...]
    plan_count: int
    task_file_count: int
    diagram_count: int


@dataclass(frozen=True, slots=True)
class SddWorkbenchBaselineView:
    artifact_type: str
    path: str
    title: str
    status: str
    protected: bool
    diagram_type: str | None = None


@dataclass(frozen=True, slots=True)
class SddWorkbenchTraceabilityRow:
    spec_id: str
    spec_path: str
    status: str
    requirement_count: int
    task_count: int
    diagram_count: int
    missing_links: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SddWorkbenchImpactQueueItem:
    scope: str
    artifact_path: str
    artifact_type: str
    impact_type: str
    status: str
    requires_review: bool
    reason: str


@dataclass(frozen=True, slots=True)
class SddWorkbenchView:
    workspace_name: str
    workspace_path: str
    health: SddWorkbenchHealth
    standards_compliance: SddWorkbenchStandardsCompliance
    context_preview: SddWorkbenchContextPreview
    feature_specs: tuple[SddWorkbenchFeatureSpecView, ...]
    baselines: tuple[SddWorkbenchBaselineView, ...]
    traceability_matrix: tuple[SddWorkbenchTraceabilityRow, ...]
    impact_queue: tuple[SddWorkbenchImpactQueueItem, ...]
    preview_readiness: dict[str, object]

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": "codex.sddWorkbenchView",
            "version": 1,
            "workspace_name": self.workspace_name,
            "workspace_path": self.workspace_path,
            "health": asdict(self.health),
            "standards_compliance": asdict(self.standards_compliance),
            "context_preview": asdict(self.context_preview),
            "feature_specs": [asdict(item) for item in self.feature_specs],
            "baselines": [asdict(item) for item in self.baselines],
            "traceability_matrix": [asdict(item) for item in self.traceability_matrix],
            "impact_queue": [asdict(item) for item in self.impact_queue],
            "preview_readiness": self.preview_readiness,
        }


class SddWorkbenchViewService:
    def __init__(
        self,
        *,
        validation_service: SddPreflightValidationService | None = None,
        llm_instruction_service: SddLlmInstructionService | None = None,
    ) -> None:
        self._validation_service = validation_service or SddPreflightValidationService()
        self._llm_instruction_service = (
            llm_instruction_service or SddLlmInstructionService()
        )

    def build_view(
        self,
        *,
        workspace: Path,
        project: SddProject,
        preset: str,
        selected_artifact: str | None = None,
        query: str = "",
        auto_regenerate_indexes: bool = True,
        allow_degraded: bool = True,
    ) -> SddWorkbenchView:
        checks = tuple(self._validation_service.validate_workspace(workspace))
        instruction = self._llm_instruction_service.build_prompt(
            workspace,
            preset=preset,
            selected_artifact=selected_artifact,
            query=query,
            auto_regenerate_indexes=auto_regenerate_indexes,
            allow_degraded=allow_degraded,
        )
        return SddWorkbenchView(
            workspace_name=project.workspace_name,
            workspace_path=project.workspace_path,
            health=_health(project, checks),
            standards_compliance=_standards_compliance(checks),
            context_preview=_context_preview(
                preset=preset,
                prompt=instruction.prompt,
                status=instruction.status,
                error=instruction.error,
                context_pack=instruction.context_pack,
            ),
            feature_specs=_feature_specs(project, workspace),
            baselines=_baselines(project, workspace),
            traceability_matrix=_traceability_matrix(project, workspace),
            impact_queue=_impact_queue(project, workspace),
            preview_readiness=_preview_readiness(workspace),
        )


def _preview_readiness(workspace: Path) -> dict[str, object]:
    runtime_path = workspace / "release" / "preview-runtime.json"
    if not runtime_path.is_file():
        return {
            "available": False,
            "status": "missing",
            "runtimeContractPath": "release/preview-runtime.json",
            "blockers": [
                "release/preview-runtime.json is missing.",
            ],
            "nextActions": [
                "Generate or restore release/preview-runtime.json before reporting Initial Preview readiness."
            ],
        }
    try:
        payload = json.loads(runtime_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "available": False,
            "status": "invalid",
            "runtimeContractPath": "release/preview-runtime.json",
            "error": str(exc),
            "blockers": [
                "release/preview-runtime.json could not be parsed.",
            ],
            "nextActions": [
                "Fix release/preview-runtime.json so Workbench can read preview readiness."
            ],
        }
    if not isinstance(payload, dict):
        return {
            "available": False,
            "status": "invalid",
            "runtimeContractPath": "release/preview-runtime.json",
            "error": "Runtime contract must be a JSON object.",
            "blockers": [
                "release/preview-runtime.json must contain a JSON object.",
            ],
            "nextActions": [
                "Fix release/preview-runtime.json so Workbench can read preview readiness."
            ],
        }
    bridge = payload.get("bridge") if isinstance(payload.get("bridge"), dict) else {}
    frontend_strategy = str(payload.get("frontendStrategy") or "flutter")
    installable_android = payload.get("installableAndroid")
    bridge_registration_required = payload.get("bridgeRegistrationRequired")
    workbench_apk_entry_required = payload.get("workbenchApkEntryRequired")
    production_ready_value = payload.get("productionReady")
    mock_or_demo_value = payload.get("mockOrDemo")
    production_ready = production_ready_value is True
    mock_or_demo = mock_or_demo_value is True
    blockers: list[str] = []
    if payload.get("runtimeProfile") != "preview":
        blockers.append("Initial Preview Release runtimeProfile must be preview.")
    if payload.get("apiRuntime") != "cloudflare_preview":
        blockers.append(
            "Initial Preview Release apiRuntime must be cloudflare_preview.",
        )
    if payload.get("releaseChannel") != "prerelease":
        blockers.append("Initial Preview Release releaseChannel must be prerelease.")
    if payload.get("releaseTagPattern") != "android-preview-v*":
        if frontend_strategy == "svelte" and payload.get("releaseTagPattern") is None:
            pass
        else:
            blockers.append(
                "Initial Preview Release releaseTagPattern must be android-preview-v*.",
            )
    if frontend_strategy == "svelte":
        if installable_android is not False:
            blockers.append("Svelte preview must declare installableAndroid=false.")
        if bridge_registration_required is not False:
            blockers.append(
                "Svelte preview must declare bridgeRegistrationRequired=false.",
            )
        if workbench_apk_entry_required is not False:
            blockers.append(
                "Svelte preview must declare workbenchApkEntryRequired=false.",
            )
        if bridge.get("requiresApkUrl") is True:
            blockers.append("Svelte preview must not require a Bridge APK URL.")
    elif installable_android is False or bridge_registration_required is False:
        blockers.append(
            "Flutter preview must keep Android APK and Bridge registration enabled.",
        )
    if production_ready_value is not False:
        blockers.append("Initial Preview Release productionReady must be false.")
    if mock_or_demo_value is not False:
        blockers.append("Initial Preview Release mockOrDemo must be false.")
    return {
        "available": True,
        "status": "ready" if not blockers else "blocked",
        "runtimeContractPath": "release/preview-runtime.json",
        "sourceApp": payload.get("sourceApp"),
        "previewUrl": payload.get("previewUrl"),
        "apiBaseUrl": payload.get("apiBaseUrl"),
        "frontendStrategy": frontend_strategy,
        "frontendSourceRoot": payload.get("frontendSourceRoot"),
        "frontendProjectKind": payload.get("frontendProjectKind"),
        "installableAndroid": installable_android,
        "runtimeProfile": payload.get("runtimeProfile"),
        "apiRuntime": payload.get("apiRuntime"),
        "releaseChannel": payload.get("releaseChannel"),
        "releaseTagPattern": payload.get("releaseTagPattern"),
        "apkAssetPattern": payload.get("apkAssetPattern"),
        "latestAssetName": payload.get("latestAssetName"),
        "androidPreviewApk": payload.get("latestAssetName")
        or payload.get("apkAssetPattern")
        or "android-preview-v*.apk",
        "bridgeRegistrationRequired": (
            bridge_registration_required
            if isinstance(bridge_registration_required, bool)
            else frontend_strategy != "svelte"
        ),
        "workbenchApkEntryRequired": workbench_apk_entry_required,
        "productionReady": production_ready,
        "mockOrDemo": mock_or_demo,
        "bridge": bridge,
        "blockers": blockers,
        "nextActions": [
            "Run scripts/validate_preview_release_profiles.sh.",
            "Run scripts/validate_initial_preview_release.sh before marking release ready.",
        ],
    }


def _health(
    project: SddProject,
    checks: tuple[SddValidationCheck, ...],
) -> SddWorkbenchHealth:
    status = _status_from_checks(checks)
    next_actions = tuple(
        f"{check.name}: {check.detail}"
        for check in checks
        if check.status in {"fail", "warn"}
    )
    diagram_count = len(project.architecture_diagrams) + sum(
        len(spec.diagrams) for spec in project.specs
    )
    return SddWorkbenchHealth(
        status=status,
        spec_count=len(project.specs),
        diagram_count=diagram_count,
        missing_required=project.missing_required,
        checks=checks,
        next_actions=next_actions,
    )


def _standards_compliance(
    checks: tuple[SddValidationCheck, ...],
) -> SddWorkbenchStandardsCompliance:
    compliance_checks = tuple(
        check
        for check in checks
        if check.name
        in {
            "standard",
            "context_rules",
            "template_metadata",
            "taxonomy_governance",
            "artifact_governance",
            "index_status",
        }
    )
    standard_check = next(
        (check for check in compliance_checks if check.name == "standard"),
        None,
    )
    return SddWorkbenchStandardsCompliance(
        status=_status_from_checks(compliance_checks),
        standard_id=_standard_id_from_detail(standard_check.detail)
        if standard_check is not None and standard_check.status == "pass"
        else None,
        checks=compliance_checks,
    )


def _context_preview(
    *,
    preset: str,
    prompt: str,
    status: str,
    error: str | None,
    context_pack: SddContextPack | None,
) -> SddWorkbenchContextPreview:
    if context_pack is None:
        return SddWorkbenchContextPreview(
            status=status,
            preset=preset,
            mode="hard_failure",
            index_status="not_checked",
            error=error,
            prompt=prompt,
            required_files=(),
            related_specs=(),
            related_diagrams=(),
            blocked_reads=("broad_reads_blocked_until_context_pack_is_available",),
            routing_decisions=(error or "Context pack unavailable.",),
            next_actions=("Fix the blocking condition before launching Codex.",),
        )
    return SddWorkbenchContextPreview(
        status=context_pack.status,
        preset=context_pack.preset,
        mode=context_pack.mode,
        index_status=context_pack.index_status,
        error=error,
        prompt=prompt,
        required_files=context_pack.required_files,
        related_specs=tuple(
            SddWorkbenchContextCandidate(
                path=candidate.path,
                reason=candidate.reason,
                rank=candidate.rank,
            )
            for candidate in context_pack.related_specs
        ),
        related_diagrams=tuple(
            SddWorkbenchContextCandidate(
                path=candidate.path,
                reason=candidate.reason,
                rank=candidate.rank,
            )
            for candidate in context_pack.related_diagrams
        ),
        blocked_reads=context_pack.blocked_reads,
        routing_decisions=context_pack.routing_decisions,
        next_actions=context_pack.next_actions,
    )


def _status_from_checks(checks: tuple[SddValidationCheck, ...]) -> str:
    statuses = {check.status for check in checks}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


def _standard_id_from_detail(detail: str) -> str | None:
    marker = "Resolved "
    if not detail.startswith(marker):
        return None
    remainder = detail[len(marker) :]
    return remainder.split(" ", maxsplit=1)[0] or None


def _feature_specs(
    project: SddProject,
    workspace: Path,
) -> tuple[SddWorkbenchFeatureSpecView, ...]:
    return tuple(
        SddWorkbenchFeatureSpecView(
            id=spec.id,
            title=spec.metadata.title,
            description=spec.metadata.description,
            path=spec.path,
            lifecycle_status=spec.metadata.lifecycle_status
            or _spec_lifecycle_status(spec),
            traceability_status=_traceability_status(workspace, spec),
            created_at=spec.metadata.created_at,
            updated_at=spec.metadata.updated_at,
            generated_title=spec.metadata.generated.title,
            generated_description=spec.metadata.generated.description,
            user_pinned_title=spec.metadata.generated.user_pinned_title,
            user_pinned_description=(spec.metadata.generated.user_pinned_description),
            task_total=spec.metadata.tasks.total,
            task_completed=spec.metadata.tasks.completed,
            task_pending=spec.metadata.tasks.pending,
            last_run_state=spec.metadata.last_run_state,
            metadata_status=spec.metadata.metadata_status,
            metadata_warnings=spec.metadata.metadata_warnings,
            metadata_stale_paths=spec.metadata.metadata_stale_paths,
            available_files=spec.metadata.available_files,
            missing=spec.missing,
            plan_count=len(spec.plan_files)
            if spec.plan_files
            else int(spec.plan is not None),
            task_file_count=len(spec.task_files)
            if spec.task_files
            else int(spec.tasks is not None),
            diagram_count=len(spec.diagrams),
        )
        for spec in project.specs
    )


def _baselines(
    project: SddProject,
    workspace: Path,
) -> tuple[SddWorkbenchBaselineView, ...]:
    protected = _protected_baseline_paths(workspace)
    baselines: list[SddWorkbenchBaselineView] = []
    baselines.extend(
        _baseline_from_diagram(diagram, protected)
        for diagram in project.architecture_diagrams
    )
    for artifact_type, paths in {
        "domain": ("domain/glossary.md", "domain/model.md"),
        "data": (
            "data/persistence-model.md",
            "data/model.md",
            "data/entity-relationship.md",
        ),
    }.items():
        for path in paths:
            if (workspace / path).is_file():
                baselines.append(
                    SddWorkbenchBaselineView(
                        artifact_type=artifact_type,
                        path=path,
                        title=Path(path).name,
                        status="present",
                        protected=path in protected,
                    )
                )
    return tuple(baselines)


def _baseline_from_diagram(
    diagram: SddDiagram,
    protected: set[str],
) -> SddWorkbenchBaselineView:
    return SddWorkbenchBaselineView(
        artifact_type="architecture",
        path=diagram.path,
        title=diagram.title or Path(diagram.path).name,
        status="present" if diagram.content or diagram.error is None else "degraded",
        protected=diagram.path in protected,
        diagram_type=diagram.diagram_type,
    )


def _traceability_matrix(
    project: SddProject,
    workspace: Path,
) -> tuple[SddWorkbenchTraceabilityRow, ...]:
    return tuple(_traceability_row(workspace, spec) for spec in project.specs)


def _traceability_row(
    workspace: Path,
    spec: SddSpec,
) -> SddWorkbenchTraceabilityRow:
    traceability_path = workspace / spec.path / "traceability.yaml"
    payload = _read_yaml_mapping(traceability_path)
    requirements = payload.get("requirements") if isinstance(payload, dict) else None
    requirement_count = len(requirements) if isinstance(requirements, dict) else 0
    task_count = 0
    diagram_count = 0
    missing_links: list[str] = []
    if not traceability_path.is_file():
        missing_links.append("traceability.yaml")
    if isinstance(requirements, dict):
        for requirement_id, raw_requirement in requirements.items():
            if not isinstance(raw_requirement, dict):
                missing_links.append(f"{requirement_id}: requirement mapping")
                continue
            tasks = raw_requirement.get("tasks")
            diagrams = raw_requirement.get("diagrams")
            if isinstance(tasks, list):
                task_count += len(tasks)
            else:
                missing_links.append(f"{requirement_id}: tasks")
            if isinstance(diagrams, list):
                diagram_count += len(diagrams)
    elif traceability_path.is_file():
        missing_links.append("requirements")
    status = "linked" if not missing_links and requirement_count else "incomplete"
    return SddWorkbenchTraceabilityRow(
        spec_id=spec.id,
        spec_path=spec.path,
        status=status,
        requirement_count=requirement_count,
        task_count=task_count,
        diagram_count=diagram_count,
        missing_links=tuple(missing_links),
    )


def _impact_queue(
    project: SddProject,
    workspace: Path,
) -> tuple[SddWorkbenchImpactQueueItem, ...]:
    protected = _protected_baseline_paths(workspace)
    items: list[SddWorkbenchImpactQueueItem] = []
    for diagram in project.architecture_diagrams:
        if diagram.path in protected:
            items.append(
                SddWorkbenchImpactQueueItem(
                    scope="architecture",
                    artifact_path=diagram.path,
                    artifact_type="diagram",
                    impact_type="protected-baseline",
                    status="review-required",
                    requires_review=True,
                    reason="Protected baseline artifact requires impact review before edits.",
                )
            )
    for spec in project.specs:
        for diagram in spec.diagrams:
            if diagram.diagram_type in {
                "component-impact",
                "domain-impact",
                "data-impact",
            }:
                items.append(
                    SddWorkbenchImpactQueueItem(
                        scope=spec.id,
                        artifact_path=diagram.path,
                        artifact_type="diagram",
                        impact_type=diagram.diagram_type,
                        status="pending-review",
                        requires_review=True,
                        reason="Feature-local impact diagram is pending baseline review.",
                    )
                )
    return tuple(items)


def _spec_lifecycle_status(spec: SddSpec) -> str:
    content = spec.spec.content if spec.spec is not None else None
    return _front_matter_value(content or "", "status") or "unknown"


def _traceability_status(workspace: Path, spec: SddSpec) -> str:
    row = _traceability_row(workspace, spec)
    return row.status


def _protected_baseline_paths(workspace: Path) -> set[str]:
    manifest = _read_yaml_mapping(workspace / "codex-bridge.yaml")
    sdd = manifest.get("sdd") if isinstance(manifest, dict) else None
    protected = sdd.get("protected_baseline") if isinstance(sdd, dict) else None
    if not isinstance(protected, list):
        return set()
    return {item for item in protected if isinstance(item, str)}


def _read_yaml_mapping(path: Path) -> dict[str, object]:
    try:
        payload = parse_simple_yaml(path.read_text(encoding="utf-8"))
    except (OSError, SddStandardError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _front_matter_value(content: str, key: str) -> str | None:
    if not content.startswith("---"):
        return None
    lines = content.splitlines()
    for line in lines[1:]:
        if line.strip() == "---":
            break
        raw_key, separator, value = line.partition(":")
        if separator and raw_key.strip() == key:
            stripped = value.strip()
            return stripped or None
    return None
