from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from backend.app.application.services.sdd_intake_service import (
    SddIntakeDryRun,
    SddIntakeService,
)
from backend.app.application.services.sdd_index_service import SddIndexService
from backend.app.application.services.sdd_metadata_refresh_service import (
    SddMetadataRefreshService,
)
from backend.app.application.services.sdd_standard_service import (
    DEFAULT_STANDARD_ID,
    SddStandardService,
    parse_simple_yaml,
)
from backend.app.application.services.sdd_spec_target_service import (
    SddSpecTargetValidationService,
    SpecIntakeValidationError,
    SpecIntakeValidationInput,
)


@dataclass(frozen=True, slots=True)
class SddSpecMetadataProposal:
    title: str
    description: str
    generated_title: bool
    generated_description: bool
    preserve_pinned_title: bool = False
    preserve_pinned_description: bool = False


@dataclass(frozen=True, slots=True)
class SddSpecDryRunPlan:
    status: str
    workspace_path: str | None
    spec_id: str | None
    spec_root: str | None
    target_files: tuple[str, ...]
    metadata_proposal: SddSpecMetadataProposal | None
    metadata_refresh_plan: tuple[str, ...]
    intended_artifact_updates: tuple[str, ...]
    conflicts: tuple[str, ...]
    validation_errors: tuple[SpecIntakeValidationError, ...]
    intake_plan: SddIntakeDryRun | None
    next_actions: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": "codex.sddSpecCreationDryRun",
            "version": 1,
            "status": self.status,
            "workspace_path": self.workspace_path,
            "spec_id": self.spec_id,
            "spec_root": self.spec_root,
            "target_files": list(self.target_files),
            "metadata_proposal": None
            if self.metadata_proposal is None
            else {
                "title": self.metadata_proposal.title,
                "description": self.metadata_proposal.description,
                "generated_title": self.metadata_proposal.generated_title,
                "generated_description": self.metadata_proposal.generated_description,
                "preserve_pinned_title": self.metadata_proposal.preserve_pinned_title,
                "preserve_pinned_description": (
                    self.metadata_proposal.preserve_pinned_description
                ),
            },
            "metadata_refresh_plan": list(self.metadata_refresh_plan),
            "intended_artifact_updates": list(self.intended_artifact_updates),
            "conflicts": list(self.conflicts),
            "blocked_reasons": _blocked_reasons(
                conflicts=self.conflicts,
                validation_errors=self.validation_errors,
                intake_plan=self.intake_plan,
            ),
            "rejected_media": [
                {
                    "code": error.code,
                    "field": error.field,
                    "message": error.message,
                }
                for error in _rejected_media(self.validation_errors, self.intake_plan)
            ],
            "existing_artifacts": []
            if self.intake_plan is None
            else list(self.intake_plan.existing),
            "validation_errors": [
                {
                    "code": error.code,
                    "field": error.field,
                    "message": error.message,
                }
                for error in self.validation_errors
            ],
            "intake_plan": None
            if self.intake_plan is None
            else self.intake_plan.to_payload(),
            "next_actions": list(self.next_actions),
        }


@dataclass(frozen=True, slots=True)
class SddSpecApplyResult:
    status: str
    workspace_path: str | None
    spec_id: str | None
    spec_root: str | None
    created: tuple[str, ...]
    existing: tuple[str, ...]
    blocked: tuple[str, ...]
    conflicts: tuple[str, ...]
    metadata_result: SddSpecMetadataProposal | None
    intake_references: tuple[str, ...]
    post_apply_refresh: dict[str, object]
    dry_run: SddSpecDryRunPlan
    next_actions: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": "codex.sddSpecApply",
            "version": 1,
            "status": self.status,
            "workspace_path": self.workspace_path,
            "spec_id": self.spec_id,
            "spec_root": self.spec_root,
            "created": list(self.created),
            "existing": list(self.existing),
            "blocked": list(self.blocked),
            "conflicts": list(self.conflicts),
            "metadata_result": None
            if self.metadata_result is None
            else {
                "title": self.metadata_result.title,
                "description": self.metadata_result.description,
                "generated_title": self.metadata_result.generated_title,
                "generated_description": self.metadata_result.generated_description,
                "preserve_pinned_title": self.metadata_result.preserve_pinned_title,
                "preserve_pinned_description": (
                    self.metadata_result.preserve_pinned_description
                ),
            },
            "intake_references": list(self.intake_references),
            "post_apply_refresh": self.post_apply_refresh,
            "dry_run": self.dry_run.to_payload(),
            "next_actions": list(self.next_actions),
        }


class SddSpecCreationService:
    def __init__(
        self,
        *,
        projects_root: str | Path,
        workspace_aliases: dict[str, str] | None = None,
        validator: SddSpecTargetValidationService | None = None,
        intake_service: SddIntakeService | None = None,
        standard_service: SddStandardService | None = None,
        index_service: SddIndexService | None = None,
        metadata_refresh_service: SddMetadataRefreshService | None = None,
    ) -> None:
        self._projects_root = Path(projects_root).expanduser().resolve()
        self._workspace_aliases = workspace_aliases or {}
        self._validator = validator or SddSpecTargetValidationService(
            projects_root=self._projects_root,
            workspace_aliases=self._workspace_aliases,
        )
        self._intake_service = intake_service or SddIntakeService(
            projects_root=self._projects_root,
            workspace_aliases=self._workspace_aliases,
            validator=self._validator,
        )
        self._standard_service = standard_service or SddStandardService()
        self._index_service = index_service or SddIndexService()
        self._metadata_refresh_service = (
            metadata_refresh_service
            or SddMetadataRefreshService(
                projects_root=self._projects_root,
                workspace_aliases=self._workspace_aliases,
            )
        )

    def dry_run_new_spec(
        self,
        request: SpecIntakeValidationInput,
        *,
        job_id: str = "dry-run",
    ) -> SddSpecDryRunPlan:
        validation = self._validator.validate(request)
        if validation.mode != "new_spec":
            return _blocked_plan(
                validation.workspace_path,
                None,
                None,
                (
                    SpecIntakeValidationError(
                        "invalid_target_mode",
                        "spec_target.mode",
                        "new spec dry-run requires spec_target.mode new_spec.",
                    ),
                ),
            )
        if not validation.ok:
            return _blocked_plan(
                validation.workspace_path,
                validation.spec_id,
                validation.spec_root,
                validation.errors,
            )

        spec_id = validation.spec_id or _slug_from_request(request)
        workspace = Path(validation.workspace_path or "")
        spec_id = _next_available_slug(workspace, spec_id)
        spec_root = f"specs/{spec_id}"
        target_files = (
            f"{spec_root}/metadata.yaml",
            f"{spec_root}/spec.md",
            f"{spec_root}/plan.md",
            f"{spec_root}/tasks.md",
            f"{spec_root}/traceability.yaml",
            f"{spec_root}/intake/",
            f"{spec_root}/diagrams/",
        )
        conflicts = tuple(path for path in target_files if (workspace / path).exists())
        if conflicts:
            return SddSpecDryRunPlan(
                status="blocked",
                workspace_path=validation.workspace_path,
                spec_id=spec_id,
                spec_root=spec_root,
                target_files=target_files,
                metadata_proposal=_metadata_proposal(request),
                metadata_refresh_plan=(),
                intended_artifact_updates=(),
                conflicts=conflicts,
                validation_errors=(),
                intake_plan=None,
                next_actions=("Resolve target path conflicts before writing.",),
            )
        intake_request = SpecIntakeValidationInput(
            workspace_path=request.workspace_path,
            spec_target=request.spec_target.__class__(
                mode=request.spec_target.mode,
                spec_id=spec_id,
                artifact=request.spec_target.artifact,
            ),
            intake_items=request.intake_items,
            title_seed=request.title_seed,
            workbench_spec_target=request.workbench_spec_target,
            bridge_spec_target=request.bridge_spec_target,
        )
        intake_plan = self._intake_service.dry_run_storage(
            intake_request, job_id=job_id
        )
        return SddSpecDryRunPlan(
            status="dry-run" if intake_plan.status == "dry-run" else "blocked",
            workspace_path=validation.workspace_path,
            spec_id=spec_id,
            spec_root=spec_root,
            target_files=target_files,
            metadata_proposal=_metadata_proposal(request),
            metadata_refresh_plan=(
                "write metadata.yaml",
                "record source digests",
                "refresh .sdd indexes after apply",
            ),
            intended_artifact_updates=(
                "metadata.yaml",
                "spec.md",
                "plan.md",
                "tasks.md",
                "traceability.yaml",
                "intake/",
            ),
            conflicts=(),
            validation_errors=(),
            intake_plan=intake_plan,
            next_actions=("Review dry-run plan before enabling apply/write behavior.",),
        )

    def apply_new_spec(
        self,
        request: SpecIntakeValidationInput,
        *,
        job_id: str = "apply",
    ) -> SddSpecApplyResult:
        dry_run = self.dry_run_new_spec(request, job_id=job_id)
        if dry_run.status != "dry-run":
            return _blocked_apply_result(
                dry_run,
                blocked=tuple(dry_run.to_payload().get("blocked_reasons", ())),
                next_actions=("Fix dry-run blockers before applying new spec.",),
            )
        if dry_run.workspace_path is None or dry_run.spec_root is None:
            return _blocked_apply_result(
                dry_run,
                blocked=("workspace_path and spec_root are required.",),
                next_actions=("Fix dry-run output before applying new spec.",),
            )

        workspace = Path(dry_run.workspace_path)
        target_root = workspace / dry_run.spec_root
        path_errors = _validate_apply_paths(workspace, dry_run)
        if path_errors:
            return _blocked_apply_result(
                dry_run,
                blocked=path_errors,
                next_actions=("Fix unsafe planned paths before applying new spec.",),
            )
        existing = tuple(
            path
            for path in dry_run.target_files
            if not path.endswith("/") and (workspace / path).exists()
        )
        if target_root.exists():
            existing = (dry_run.spec_root, *existing)
        if existing:
            return _blocked_apply_result(
                dry_run,
                existing=existing,
                conflicts=existing,
                blocked=tuple(
                    f"would overwrite existing artifact: {path}" for path in existing
                ),
                next_actions=("Choose a different spec id or resolve existing files.",),
            )

        created: list[str] = []
        persisted_intake = None
        try:
            target_root.mkdir(parents=True, exist_ok=False)
            created.append(dry_run.spec_root)
            (target_root / "intake").mkdir()
            created.append(f"{dry_run.spec_root}/intake/")
            (target_root / "diagrams").mkdir()
            created.append(f"{dry_run.spec_root}/diagrams/")
            contents = _new_spec_contents(dry_run, request)
            for relative_path, content in contents.items():
                _write_file_no_overwrite(workspace / relative_path, content)
                created.append(relative_path)
            persisted_intake = self._intake_service.persist_storage(
                _request_with_spec_id(request, dry_run.spec_id or ""),
                job_id=job_id,
                dry_run=dry_run.intake_plan,
            )
            if persisted_intake.status != "applied":
                if target_root.exists():
                    shutil.rmtree(target_root)
                return _blocked_apply_result(
                    dry_run,
                    blocked=tuple(persisted_intake.blocked),
                    next_actions=tuple(persisted_intake.next_actions),
                )
            created.extend(
                artifact.target_path for artifact in persisted_intake.persisted
            )
            if persisted_intake.retention_manifest_path:
                created.append(persisted_intake.retention_manifest_path)
        except Exception:
            if target_root.exists():
                shutil.rmtree(target_root)
            raise

        return SddSpecApplyResult(
            status="applied",
            workspace_path=dry_run.workspace_path,
            spec_id=dry_run.spec_id,
            spec_root=dry_run.spec_root,
            created=tuple(created),
            existing=(),
            blocked=(),
            conflicts=(),
            metadata_result=dry_run.metadata_proposal,
            intake_references=tuple(
                artifact.target_path
                for artifact in (persisted_intake.persisted if persisted_intake else ())
            ),
            post_apply_refresh=_post_apply_refresh_payload(
                self._post_apply_refresh(workspace, dry_run.spec_id or "")
            ),
            dry_run=dry_run,
            next_actions=(
                "Review generated spec artifacts.",
                *(persisted_intake.next_actions if persisted_intake else ()),
                "Run SDD doctor before committing.",
            ),
        )

    def _post_apply_refresh(self, workspace: Path, spec_id: str) -> dict[str, object]:
        try:
            metadata_refresh = self._metadata_refresh_service.refresh_spec_metadata(
                workspace,
                spec_id,
            )
            standard_id = _workspace_standard_id(workspace)
            standard = self._standard_service.load(standard_id)
            index_status = self._index_service.ensure_indexes(
                workspace,
                standard=standard,
                auto_regenerate=True,
                allow_degraded=False,
            )
            return {
                "metadata_status": "written",
                "traceability_status": "written",
                "metadata_refresh": metadata_refresh.to_payload(),
                "index_status": index_status.state,
                "index_mode": index_status.mode,
                "generated_indexes": list(index_status.generated),
                "detail": index_status.detail,
            }
        except Exception as exc:
            return {
                "metadata_status": "written",
                "traceability_status": "written",
                "metadata_refresh": {
                    "status": "failed",
                    "detail": f"Post-apply metadata refresh failed: {exc}",
                },
                "index_status": "failed",
                "index_mode": "post_apply_error",
                "generated_indexes": [],
                "detail": f"Post-apply index refresh failed: {exc}",
            }


def _blocked_plan(
    workspace_path: str | None,
    spec_id: str | None,
    spec_root: str | None,
    errors: tuple[SpecIntakeValidationError, ...],
) -> SddSpecDryRunPlan:
    return SddSpecDryRunPlan(
        status="blocked",
        workspace_path=workspace_path,
        spec_id=spec_id,
        spec_root=spec_root,
        target_files=(),
        metadata_proposal=None,
        metadata_refresh_plan=(),
        intended_artifact_updates=(),
        conflicts=(),
        validation_errors=errors,
        intake_plan=None,
        next_actions=("Fix validation errors before planning spec creation.",),
    )


def _blocked_apply_result(
    dry_run: SddSpecDryRunPlan,
    *,
    blocked: tuple[str, ...],
    next_actions: tuple[str, ...],
    existing: tuple[str, ...] = (),
    conflicts: tuple[str, ...] = (),
) -> SddSpecApplyResult:
    return SddSpecApplyResult(
        status="blocked",
        workspace_path=dry_run.workspace_path,
        spec_id=dry_run.spec_id,
        spec_root=dry_run.spec_root,
        created=(),
        existing=existing,
        blocked=blocked,
        conflicts=conflicts,
        metadata_result=dry_run.metadata_proposal,
        intake_references=(),
        post_apply_refresh={
            "metadata_status": "not_run",
            "traceability_status": "not_run",
            "metadata_refresh": {
                "status": "not_run",
                "detail": "Apply was blocked before metadata refresh.",
            },
            "index_status": "not_run",
            "index_mode": "blocked",
            "generated_indexes": [],
            "detail": "Apply was blocked before post-apply refresh.",
        },
        dry_run=dry_run,
        next_actions=next_actions,
    )


def _validate_apply_paths(
    workspace: Path,
    dry_run: SddSpecDryRunPlan,
) -> tuple[str, ...]:
    errors: list[str] = []
    for relative_path in dry_run.target_files:
        clean_path = relative_path.rstrip("/")
        if not clean_path:
            errors.append("planned path is empty")
            continue
        path = Path(clean_path)
        if path.is_absolute() or ".." in path.parts:
            errors.append(f"unsafe planned path: {relative_path}")
            continue
        resolved = (workspace / clean_path).resolve()
        if not _is_relative_to(resolved, workspace):
            errors.append(f"planned path escapes workspace: {relative_path}")
    return tuple(errors)


def _new_spec_contents(
    dry_run: SddSpecDryRunPlan,
    request: SpecIntakeValidationInput,
) -> dict[str, str]:
    if dry_run.spec_root is None or dry_run.metadata_proposal is None:
        return {}
    root = dry_run.spec_root
    proposal = dry_run.metadata_proposal
    original_request = _combined_text(request)
    return {
        f"{root}/metadata.yaml": _metadata_yaml(dry_run, proposal),
        f"{root}/spec.md": _spec_markdown(dry_run, proposal, original_request),
        f"{root}/plan.md": _plan_markdown(dry_run),
        f"{root}/tasks.md": _tasks_markdown(dry_run),
        f"{root}/traceability.yaml": _traceability_yaml(dry_run),
    }


def _metadata_yaml(
    dry_run: SddSpecDryRunPlan,
    proposal: SddSpecMetadataProposal,
) -> str:
    return (
        f"id: {dry_run.spec_id}\n"
        f"slug: {dry_run.spec_id}\n"
        f"title: {proposal.title}\n"
        f"description: {proposal.description}\n"
        "status: draft\n"
        "generated:\n"
        f"  title: {str(proposal.generated_title).lower()}\n"
        f"  description: {str(proposal.generated_description).lower()}\n"
        "  user_pinned_title: false\n"
        "  user_pinned_description: false\n"
        "tasks:\n"
        "  total: 1\n"
        "  completed: 0\n"
        "  pending: 1\n"
        "last_run_state: applied\n"
    )


def _spec_markdown(
    dry_run: SddSpecDryRunPlan,
    proposal: SddSpecMetadataProposal,
    original_request: str,
) -> str:
    return (
        "---\n"
        f"id: {dry_run.spec_id}\n"
        f"title: {proposal.title}\n"
        "status: draft\n"
        "type: feature\n"
        "---\n\n"
        f"# {proposal.title}\n\n"
        f"{proposal.description}\n\n"
        "## Source Intake\n\n"
        "- `intake/original-request.md`\n\n"
        "## Request Summary\n\n"
        f"{original_request}\n"
    )


def _plan_markdown(dry_run: SddSpecDryRunPlan) -> str:
    return (
        "# Plan\n\n"
        "## Implementation Notes\n\n"
        f"- Spec root: `{dry_run.spec_root}`\n"
        "- This plan was scaffolded by the Workbench SCM intake apply flow.\n"
    )


def _tasks_markdown(dry_run: SddSpecDryRunPlan) -> str:
    return (
        "# Tasks\n\n"
        "- [ ] T001 Review generated spec, plan, tasks, and traceability before implementation.\n"
    )


def _traceability_yaml(dry_run: SddSpecDryRunPlan) -> str:
    return (
        f"spec_id: {dry_run.spec_id}\n"
        "status: draft\n"
        "requirements: {}\n"
        "implementation:\n"
        "  status: planned\n"
    )


def _combined_text(request: SpecIntakeValidationInput) -> str:
    parts = [
        item.text.strip()
        for item in request.intake_items
        if item.kind == "text" and item.text and item.text.strip()
    ]
    return "\n\n".join(parts) or (request.title_seed or "").strip()


def _request_with_spec_id(
    request: SpecIntakeValidationInput,
    spec_id: str,
) -> SpecIntakeValidationInput:
    return SpecIntakeValidationInput(
        workspace_path=request.workspace_path,
        spec_target=request.spec_target.__class__(
            mode=request.spec_target.mode,
            spec_id=spec_id,
            artifact=request.spec_target.artifact,
        ),
        intake_items=request.intake_items,
        title_seed=request.title_seed,
        workbench_spec_target=request.workbench_spec_target,
        bridge_spec_target=request.bridge_spec_target,
    )


def _write_file_no_overwrite(path: Path, content: str) -> None:
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temp_path.open("x", encoding="utf-8") as handle:
            handle.write(content)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _workspace_standard_id(workspace: Path) -> str:
    manifest_path = workspace / "codex-bridge.yaml"
    if not manifest_path.is_file():
        return DEFAULT_STANDARD_ID
    manifest = parse_simple_yaml(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        return DEFAULT_STANDARD_ID
    sdd = manifest.get("sdd")
    if not isinstance(sdd, dict):
        return DEFAULT_STANDARD_ID
    return str(sdd.get("standard") or DEFAULT_STANDARD_ID)


def _post_apply_refresh_payload(payload: dict[str, object]) -> dict[str, object]:
    return payload


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _metadata_proposal(request: SpecIntakeValidationInput) -> SddSpecMetadataProposal:
    raw_title = request.title_seed or _first_text(request) or "New spec"
    title = _human_title(raw_title)
    description_source = _first_text(request) or request.title_seed or title
    description = " ".join(description_source.strip().split())[:180]
    return SddSpecMetadataProposal(
        title=title,
        description=description,
        generated_title=request.title_seed is None,
        generated_description=True,
    )


def _slug_from_request(request: SpecIntakeValidationInput) -> str:
    return _slugify(request.title_seed or _first_text(request) or "new-spec")


def _next_available_slug(workspace: Path, base_slug: str) -> str:
    slug = base_slug
    counter = 2
    while (workspace / "specs" / slug).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


def _first_text(request: SpecIntakeValidationInput) -> str | None:
    for item in request.intake_items:
        if item.text and item.text.strip():
            return item.text.strip()
        if item.transcript and item.transcript.strip():
            return item.transcript.strip()
    return None


def _human_title(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        return "New spec"
    first_sentence = re.split(r"[.!?]", normalized, maxsplit=1)[0]
    words = first_sentence.split()[:8]
    return " ".join(word.capitalize() for word in words)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80].strip("-") or "new-spec"


def _rejected_media(
    validation_errors: tuple[SpecIntakeValidationError, ...],
    intake_plan: SddIntakeDryRun | None,
) -> tuple[SpecIntakeValidationError, ...]:
    errors = [
        error for error in validation_errors if error.field.startswith("intake_items")
    ]
    if intake_plan is not None:
        errors.extend(intake_plan.rejected_media)
    return tuple(errors)


def _blocked_reasons(
    *,
    conflicts: tuple[str, ...],
    validation_errors: tuple[SpecIntakeValidationError, ...],
    intake_plan: SddIntakeDryRun | None,
) -> list[str]:
    reasons = [f"conflict: {path}" for path in conflicts]
    reasons.extend(f"{error.field}: {error.code}" for error in validation_errors)
    if intake_plan is not None:
        reasons.extend(intake_plan.blocked)
    return reasons
