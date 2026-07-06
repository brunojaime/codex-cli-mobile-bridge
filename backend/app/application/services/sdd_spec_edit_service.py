from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.application.services.sdd_project_service import (
    SddProjectService,
    SddSpecMetadata,
)
from backend.app.application.services.sdd_spec_creation_service import (
    SddSpecMetadataProposal,
)
from backend.app.application.services.sdd_spec_target_service import (
    SddSpecTargetValidationService,
    SpecIntakeValidationError,
    SpecIntakeValidationInput,
)


@dataclass(frozen=True, slots=True)
class SddSpecEditDryRunPlan:
    status: str
    workspace_path: str | None
    spec_id: str | None
    spec_root: str | None
    selected_artifact: str | None
    intended_artifact_updates: tuple[str, ...]
    metadata_proposal: SddSpecMetadataProposal | None
    metadata_refresh_plan: tuple[str, ...]
    conflicts: tuple[str, ...]
    validation_errors: tuple[SpecIntakeValidationError, ...]
    next_actions: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": "codex.sddSpecEditDryRun",
            "version": 1,
            "status": self.status,
            "workspace_path": self.workspace_path,
            "spec_id": self.spec_id,
            "spec_root": self.spec_root,
            "selected_artifact": self.selected_artifact,
            "intended_artifact_updates": list(self.intended_artifact_updates),
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
            "conflicts": list(self.conflicts),
            "blocked_reasons": _blocked_reasons(
                conflicts=self.conflicts,
                validation_errors=self.validation_errors,
            ),
            "rejected_media": [
                {
                    "code": error.code,
                    "field": error.field,
                    "message": error.message,
                }
                for error in self.validation_errors
                if error.field.startswith("intake_items")
            ],
            "existing_artifacts": list(self.intended_artifact_updates),
            "validation_errors": [
                {
                    "code": error.code,
                    "field": error.field,
                    "message": error.message,
                }
                for error in self.validation_errors
            ],
            "next_actions": list(self.next_actions),
        }


@dataclass(frozen=True, slots=True)
class SddSpecEditApplyResult:
    status: str
    workspace_path: str | None
    spec_id: str | None
    spec_root: str | None
    selected_artifact: str | None
    created: tuple[str, ...]
    updated: tuple[str, ...]
    existing: tuple[str, ...]
    blocked: tuple[str, ...]
    conflicts: tuple[str, ...]
    dry_run: SddSpecEditDryRunPlan
    job: dict[str, Any] | None
    next_actions: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": "codex.sddSpecEditApply",
            "version": 1,
            "status": self.status,
            "workspace_path": self.workspace_path,
            "spec_id": self.spec_id,
            "spec_root": self.spec_root,
            "selected_artifact": self.selected_artifact,
            "created": list(self.created),
            "updated": list(self.updated),
            "existing": list(self.existing),
            "blocked": list(self.blocked),
            "conflicts": list(self.conflicts),
            "dry_run": self.dry_run.to_payload(),
            "job": self.job,
            "next_actions": list(self.next_actions),
        }


class SddSpecEditService:
    def __init__(
        self,
        *,
        projects_root: str | Path,
        workspace_aliases: dict[str, str] | None = None,
        validator: SddSpecTargetValidationService | None = None,
        project_service: SddProjectService | None = None,
        codex_job_service: object | None = None,
    ) -> None:
        self._projects_root = Path(projects_root).expanduser().resolve()
        self._workspace_aliases = workspace_aliases or {}
        self._validator = validator or SddSpecTargetValidationService(
            projects_root=self._projects_root,
            workspace_aliases=self._workspace_aliases,
        )
        self._project_service = project_service or SddProjectService(
            projects_root=str(self._projects_root),
            workspace_aliases=self._workspace_aliases,
        )
        self._codex_job_service = codex_job_service

    def dry_run_existing_spec_edit(
        self,
        request: SpecIntakeValidationInput,
    ) -> SddSpecEditDryRunPlan:
        validation = self._validator.validate(request)
        if validation.mode != "existing_spec":
            return _blocked_edit_plan(
                validation.workspace_path,
                validation.spec_id,
                validation.spec_root,
                validation.artifact,
                (
                    SpecIntakeValidationError(
                        "invalid_target_mode",
                        "spec_target.mode",
                        "edit dry-run requires spec_target.mode existing_spec.",
                    ),
                ),
            )
        if not validation.ok:
            return _blocked_edit_plan(
                validation.workspace_path,
                validation.spec_id,
                validation.spec_root,
                validation.artifact,
                validation.errors,
            )

        metadata = self._project_service.get_spec_metadata(
            validation.workspace_path or "",
            validation.spec_id or "",
        )
        intended_updates = _intended_updates(validation.artifact or "auto", metadata)
        conflicts = tuple(
            path
            for path in intended_updates
            if not (Path(validation.workspace_path or "") / path).exists()
            and not path.endswith("metadata.yaml")
        )
        if conflicts:
            return SddSpecEditDryRunPlan(
                status="blocked",
                workspace_path=validation.workspace_path,
                spec_id=validation.spec_id,
                spec_root=validation.spec_root,
                selected_artifact=validation.artifact,
                intended_artifact_updates=intended_updates,
                metadata_proposal=_metadata_proposal_for_edit(metadata, request),
                metadata_refresh_plan=(),
                conflicts=conflicts,
                validation_errors=(),
                next_actions=("Selected artifact is missing; choose another target.",),
            )
        return SddSpecEditDryRunPlan(
            status="dry-run",
            workspace_path=validation.workspace_path,
            spec_id=validation.spec_id,
            spec_root=validation.spec_root,
            selected_artifact=validation.artifact,
            intended_artifact_updates=intended_updates,
            metadata_proposal=_metadata_proposal_for_edit(metadata, request),
            metadata_refresh_plan=(
                "recompute task summary",
                "record source digests",
                "preserve pinned title/description fields",
                "refresh .sdd indexes after apply",
            ),
            conflicts=(),
            validation_errors=(),
            next_actions=("Review dry-run plan before enabling apply/write behavior.",),
        )

    def apply_existing_spec_edit(
        self,
        request: SpecIntakeValidationInput,
    ) -> SddSpecEditApplyResult:
        dry_run = self.dry_run_existing_spec_edit(request)
        if dry_run.status != "dry-run":
            return SddSpecEditApplyResult(
                status="blocked",
                workspace_path=dry_run.workspace_path,
                spec_id=dry_run.spec_id,
                spec_root=dry_run.spec_root,
                selected_artifact=dry_run.selected_artifact,
                created=(),
                updated=(),
                existing=(),
                blocked=tuple(dry_run.to_payload().get("blocked_reasons", ())),
                conflicts=dry_run.conflicts,
                dry_run=dry_run,
                job=None,
                next_actions=("Fix dry-run blockers before applying spec edit.",),
            )
        if self._codex_job_service is not None:
            job = self._codex_job_service.start_existing_spec_edit_job(
                request=request,
                dry_run=dry_run,
            )
            job_payload = job.to_payload()
            if job.status == "blocked":
                return SddSpecEditApplyResult(
                    status="blocked",
                    workspace_path=dry_run.workspace_path,
                    spec_id=dry_run.spec_id,
                    spec_root=dry_run.spec_root,
                    selected_artifact=dry_run.selected_artifact,
                    created=(),
                    updated=(),
                    existing=dry_run.intended_artifact_updates,
                    blocked=tuple(job.blocked_reasons),
                    conflicts=(),
                    dry_run=dry_run,
                    job=job_payload,
                    next_actions=tuple(job.next_actions),
                )
            return SddSpecEditApplyResult(
                status="queued",
                workspace_path=dry_run.workspace_path,
                spec_id=dry_run.spec_id,
                spec_root=dry_run.spec_root,
                selected_artifact=dry_run.selected_artifact,
                created=(),
                updated=(),
                existing=dry_run.intended_artifact_updates,
                blocked=(),
                conflicts=(),
                dry_run=dry_run,
                job=job_payload,
                next_actions=(
                    "Codex job queued; poll the job status before applying changes.",
                ),
            )
        return SddSpecEditApplyResult(
            status="blocked",
            workspace_path=dry_run.workspace_path,
            spec_id=dry_run.spec_id,
            spec_root=dry_run.spec_root,
            selected_artifact=dry_run.selected_artifact,
            created=(),
            updated=(),
            existing=dry_run.intended_artifact_updates,
            blocked=(
                "existing-spec edit apply requires Codex CLI synthesis for content changes",
            ),
            conflicts=(),
            dry_run=dry_run,
            job=None,
            next_actions=(
                "Run the Codex CLI orchestration phase before applying existing-spec edits.",
            ),
        )


def _blocked_edit_plan(
    workspace_path: str | None,
    spec_id: str | None,
    spec_root: str | None,
    artifact: str | None,
    errors: tuple[SpecIntakeValidationError, ...],
) -> SddSpecEditDryRunPlan:
    return SddSpecEditDryRunPlan(
        status="blocked",
        workspace_path=workspace_path,
        spec_id=spec_id,
        spec_root=spec_root,
        selected_artifact=artifact,
        intended_artifact_updates=(),
        metadata_proposal=None,
        metadata_refresh_plan=(),
        conflicts=(),
        validation_errors=errors,
        next_actions=("Fix validation errors before planning spec edit.",),
    )


def _intended_updates(artifact: str, metadata: SddSpecMetadata) -> tuple[str, ...]:
    base = f"specs/{metadata.id}"
    if artifact == "spec":
        return (f"{base}/spec.md", f"{base}/metadata.yaml")
    if artifact == "plan":
        return (f"{base}/plan.md", f"{base}/metadata.yaml")
    if artifact == "tasks":
        return (f"{base}/tasks.md", f"{base}/metadata.yaml")
    if artifact == "diagram":
        return metadata.diagrams + (f"{base}/metadata.yaml",)
    return (
        f"{base}/spec.md",
        f"{base}/plan.md",
        f"{base}/tasks.md",
        f"{base}/metadata.yaml",
    )


def _metadata_proposal_for_edit(
    metadata: SddSpecMetadata,
    request: SpecIntakeValidationInput,
) -> SddSpecMetadataProposal:
    description_source = _first_text(request) or metadata.description or metadata.title
    return SddSpecMetadataProposal(
        title=metadata.title,
        description=" ".join(description_source.strip().split())[:180],
        generated_title=False,
        generated_description=True,
        preserve_pinned_title=metadata.generated.user_pinned_title,
        preserve_pinned_description=metadata.generated.user_pinned_description,
    )


def _first_text(request: SpecIntakeValidationInput) -> str | None:
    for item in request.intake_items:
        if item.text and item.text.strip():
            return item.text.strip()
        if item.transcript and item.transcript.strip():
            return item.transcript.strip()
    return None


def _blocked_reasons(
    *,
    conflicts: tuple[str, ...],
    validation_errors: tuple[SpecIntakeValidationError, ...],
) -> list[str]:
    reasons = [f"conflict: {path}" for path in conflicts]
    reasons.extend(f"{error.field}: {error.code}" for error in validation_errors)
    return reasons
