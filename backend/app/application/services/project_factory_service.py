from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from threading import RLock, Thread
from uuid import uuid4

from backend.app.application.services.asset_depot_service import (
    AssetDepotError,
    AssetDepotItem,
    AssetDepotService,
    validate_asset_role,
)
from backend.app.application.services.project_factory_job_runner import (
    ProjectFactoryJobRunner,
    ProjectFactoryJobRunnerBlockedError,
    ProjectFactoryJobRunnerError,
    ProjectFactoryRemotePreflight,
    ProjectFactoryRunnerContext,
)
from backend.app.application.services.project_factory_manifest_service import (
    DEFAULT_BACKEND,
    DEFAULT_CREATION_GENERATOR_RUNS,
    DEFAULT_CREATION_REVIEWER_RUNS,
    DEFAULT_FIRST_RELEASE_MODE,
    DEFAULT_FRONTEND_STRATEGY,
    DEFAULT_PLATFORMS,
    FRONTEND_STRATEGIES,
    ProjectFactoryManifestInput,
    ProjectFactoryManifestPlan,
    ProjectFactoryManifestService,
    ProjectFactoryValidationError,
)
from backend.app.application.services.project_factory_generator_service import (
    ProjectFactoryGeneratedFile,
    ProjectFactoryGenerationResult,
    ProjectFactoryGeneratorService,
)
from backend.app.application.services.project_factory_reference_asset_service import (
    ProjectFactoryReferenceAsset,
    ProjectFactoryReferenceAssetService,
)


@dataclass(frozen=True, slots=True)
class ProjectFactoryDraft:
    id: str
    created_at: str
    request: ProjectFactoryManifestInput
    manifest_plan: ProjectFactoryManifestPlan
    guided_intake: "ProjectFactoryGuidedIntake"

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": "codex.projectFactoryDraft",
            "version": 1,
            "draft_id": self.id,
            "created_at": self.created_at,
            "first_release_mode": self.request.first_release_mode,
            "frontend_strategy": self.request.frontend_strategy,
            "manifest_plan": self.manifest_plan.to_payload(),
            "guided_intake": self.guided_intake.to_payload(),
            "initial_preview_release": _initial_preview_release_status(
                manifest=self.manifest_plan.manifest,
            ),
        }


@dataclass(frozen=True, slots=True)
class ProjectFactoryGuidedIntakeAnswer:
    question_id: str
    value: object
    source: str
    confidence: float
    updated_at: str

    def to_payload(self) -> dict[str, object]:
        return {
            "questionId": self.question_id,
            "value": self.value,
            "source": self.source,
            "confidence": self.confidence,
            "updatedAt": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class ProjectFactoryGuidedIntake:
    enabled: bool
    status: str
    questions: tuple[dict[str, object], ...]
    answers: tuple[ProjectFactoryGuidedIntakeAnswer, ...]
    missing_fields: tuple[dict[str, object], ...]
    assumptions: tuple[dict[str, object], ...]
    blockers: tuple[dict[str, object], ...]
    contract_preview: dict[str, object] | None
    updated_at: str
    confirmed_at: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": "codex.projectFactoryGuidedIntake",
            "version": 1,
            "enabled": self.enabled,
            "status": self.status,
            "questions": [dict(question) for question in self.questions],
            "answers": [answer.to_payload() for answer in self.answers],
            "missingFields": [dict(field) for field in self.missing_fields],
            "assumptions": [dict(item) for item in self.assumptions],
            "blockers": [dict(item) for item in self.blockers],
            "contractPreview": (
                dict(self.contract_preview) if self.contract_preview is not None else None
            ),
            "updatedAt": self.updated_at,
            "confirmedAt": self.confirmed_at,
            "readyForConfirmation": self.status == "ready_for_review",
            "buildAllowed": self.status in {"confirmed", "build_started"},
        }


@dataclass(slots=True)
class ProjectFactoryJob:
    id: str
    draft_id: str
    created_at: str
    updated_at: str
    status: str
    current_step: str
    message: str
    manifest_plan: ProjectFactoryManifestPlan
    current_phase: str = "queued"
    progress: int = 0
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    project_path: str | None = None
    step_logs: list[dict[str, object]] | None = None
    generation_result: ProjectFactoryGenerationResult | None = None

    def to_payload(self) -> dict[str, object]:
        logs = list(self.step_logs or [])
        payload: dict[str, object] = {
            "kind": "codex.projectFactoryJob",
            "version": 1,
            "job_id": self.id,
            "draft_id": self.draft_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "current_step": self.current_step,
            "current_phase": self.current_phase,
            "progress": self.progress,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "project_path": self.project_path,
            "message": self.message,
            "first_release_mode": _first_release_mode_from_manifest_plan(
                self.manifest_plan,
            ),
            "frontend_strategy": _frontend_strategy_from_manifest_plan(
                self.manifest_plan,
            ),
            "manifest_plan": self.manifest_plan.to_payload(),
            "step_logs": logs,
            "initial_preview_release": _initial_preview_release_status(
                manifest=self.manifest_plan.manifest,
                status=self.status,
                current_phase=self.current_phase,
                blocker_text=self.error if self.status == "blocked" else None,
                step_logs=logs,
            ),
        }
        if self.generation_result is not None:
            payload["generation_result"] = self.generation_result.to_payload()
        return payload


@dataclass(frozen=True, slots=True)
class ProjectFactoryDraftAsset:
    draft_id: str
    asset_id: str
    role: str
    notes: str
    linked_at: str
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    storage_path: str
    source: str

    def to_payload(self) -> dict[str, object]:
        return {
            "draft_id": self.draft_id,
            "asset_id": self.asset_id,
            "role": self.role,
            "notes": self.notes,
            "linked_at": self.linked_at,
            "original_filename": self.original_filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "storage_path": self.storage_path,
            "source": self.source,
        }

    def to_manifest_item(self) -> dict[str, object]:
        return self.to_payload()


class ProjectFactoryGenerationConflictError(RuntimeError):
    pass


class ProjectFactoryService:
    def __init__(
        self,
        *,
        projects_root: str | Path,
        reference_asset_storage_root: str | Path,
        asset_depot_service: AssetDepotService | None = None,
        max_reference_asset_bytes: int,
        state_root: str | Path | None = None,
        codex_command: str = "codex",
        timeout_seconds: int = 0,
        generator_runs_override: int | None = None,
        reviewer_runs_override: int | None = None,
        run_generated_validation: bool = False,
        publication_validation_mode: str = "remote",
        runner: ProjectFactoryJobRunner | None = None,
        remote_publication_preflight: ProjectFactoryRemotePreflight | None = None,
        async_jobs: bool = True,
    ) -> None:
        self._projects_root = Path(projects_root).expanduser().resolve()
        self._state_root = (
            Path(state_root).expanduser().resolve()
            if state_root is not None
            else Path(reference_asset_storage_root).expanduser().resolve().parent
            / "project_factory_state"
        )
        self._draft_state_dir = self._state_root / "drafts"
        self._job_state_dir = self._state_root / "jobs"
        self._draft_asset_state_dir = self._state_root / "draft_assets"
        self._manifest_service = ProjectFactoryManifestService(
            projects_root=self._projects_root,
        )
        self._reference_asset_service = ProjectFactoryReferenceAssetService(
            storage_root=reference_asset_storage_root,
            max_image_bytes=max_reference_asset_bytes,
        )
        self._asset_depot_service = asset_depot_service
        self._generator_service = ProjectFactoryGeneratorService(
            reference_asset_service=self._reference_asset_service,
            asset_depot_service=self._asset_depot_service,
        )
        self._runner = runner or ProjectFactoryJobRunner(
            generator_service=self._generator_service,
            remote_preflight=remote_publication_preflight,
        )
        self._codex_command = codex_command
        self._timeout_seconds = timeout_seconds
        self._generator_runs_override = generator_runs_override
        self._reviewer_runs_override = reviewer_runs_override
        self._run_generated_validation = run_generated_validation
        self._publication_validation_mode = publication_validation_mode
        self._async_jobs = async_jobs
        self._lock = RLock()
        self._drafts: dict[str, ProjectFactoryDraft] = {}
        self._jobs: dict[str, ProjectFactoryJob] = {}
        self._draft_assets: dict[str, list[ProjectFactoryDraftAsset]] = {}
        self._state_root.mkdir(parents=True, exist_ok=True)
        self._draft_state_dir.mkdir(parents=True, exist_ok=True)
        self._job_state_dir.mkdir(parents=True, exist_ok=True)
        self._draft_asset_state_dir.mkdir(parents=True, exist_ok=True)
        self._load_state()

    def options(self) -> dict[str, object]:
        return {
            "kind": "codex.projectFactoryOptions",
            "version": 1,
            "default_platforms": list(DEFAULT_PLATFORMS),
            "platforms": ["ios", "android", "web"],
            "default_backend": DEFAULT_BACKEND,
            "backends": ["fastapi", "go", "none"],
            "default_frontend_strategy": DEFAULT_FRONTEND_STRATEGY,
            "frontend_strategies": [dict(FRONTEND_STRATEGIES[key]) for key in sorted(FRONTEND_STRATEGIES)],
            "logo_modes": ["generate", "upload", "placeholder"],
            "business_types": [
                "restaurant",
                "medical_appointments",
                "ecommerce",
                "professional_services",
                "education",
                "real_estate",
                "fitness",
                "logistics",
                "cars",
                "clothing_catalog",
                "community_membership",
                "other",
            ],
            "creation_workflow": {
                "runner": "codex_cli",
                "mode": "generator_reviewer_pairs",
                "generator_runs": DEFAULT_CREATION_GENERATOR_RUNS,
                "reviewer_runs": DEFAULT_CREATION_REVIEWER_RUNS,
            },
        }

    def doctor(self) -> dict[str, object]:
        effective_generator_runs = (
            self._generator_runs_override
            if self._generator_runs_override is not None
            else DEFAULT_CREATION_GENERATOR_RUNS
        )
        effective_reviewer_runs = (
            self._reviewer_runs_override
            if self._reviewer_runs_override is not None
            else DEFAULT_CREATION_REVIEWER_RUNS
        )
        checks = [
            _doctor_check(
                "projects_root_exists",
                self._projects_root.is_dir(),
                f"PROJECTS_ROOT is {self._projects_root}",
            ),
            _doctor_check(
                "projects_root_writable",
                os.access(self._projects_root, os.W_OK)
                if self._projects_root.exists()
                else False,
                "PROJECTS_ROOT must be writable for new project creation.",
            ),
            _doctor_check(
                "default_creation_workflow",
                DEFAULT_CREATION_GENERATOR_RUNS == 20
                and DEFAULT_CREATION_REVIEWER_RUNS == 20,
                "Default creation workflow must stay 20 generator/reviewer pairs.",
            ),
            _doctor_check(
                "effective_creation_workflow",
                effective_generator_runs == effective_reviewer_runs,
                (
                    "Effective creation workflow must use matching "
                    "generator/reviewer pair counts. "
                    f"generator={effective_generator_runs} "
                    f"reviewer={effective_reviewer_runs}."
                ),
            ),
            _doctor_check(
                "local_generator_available",
                True,
                "Local foundation generator is available.",
            ),
        ]
        ok = all(bool(check["ok"]) for check in checks)
        return {
            "kind": "codex.projectFactoryDoctor",
            "version": 1,
            "ok": ok,
            "status": "ready" if ok else "blocked",
            "projects_root": str(self._projects_root),
            "checks": checks,
            "toolchain": _toolchain_report(self._codex_command),
        }

    def create_draft(
        self,
        request: ProjectFactoryManifestInput,
    ) -> ProjectFactoryDraft:
        manifest_plan = self._manifest_service.plan_manifest(request)
        draft = ProjectFactoryDraft(
            id=_new_id("pf-draft"),
            created_at=_now_iso(),
            request=request,
            manifest_plan=manifest_plan,
            guided_intake=_build_guided_intake(
                request=request,
                manifest_plan=manifest_plan,
                draft_assets=(),
                enabled=request.guided_intake_enabled,
            ),
        )
        with self._lock:
            self._drafts[draft.id] = draft
            self._persist_draft(draft)
        return draft

    def create_reference_asset(
        self,
        *,
        draft_id: str,
        filename: str,
        content_type: str | None,
        content: bytes,
    ) -> ProjectFactoryReferenceAsset | None:
        with self._lock:
            draft_exists = draft_id in self._drafts
        if not draft_exists:
            return None
        return self._reference_asset_service.create_asset(
            draft_id=draft_id,
            filename=filename,
            content_type=content_type,
            content=content,
        )

    def list_reference_assets(
        self,
        draft_id: str,
    ) -> tuple[ProjectFactoryReferenceAsset, ...] | None:
        with self._lock:
            draft_exists = draft_id in self._drafts
        if not draft_exists:
            return None
        return self._reference_asset_service.list_assets(draft_id)

    def delete_reference_asset(self, *, draft_id: str, asset_id: str) -> bool | None:
        with self._lock:
            draft_exists = draft_id in self._drafts
        if not draft_exists:
            return None
        return self._reference_asset_service.delete_asset(
            draft_id=draft_id,
            asset_id=asset_id,
        )

    def link_asset_to_draft(
        self,
        *,
        draft_id: str,
        asset_id: str,
        role: str,
        notes: str = "",
    ) -> ProjectFactoryDraftAsset | None:
        if self._asset_depot_service is None:
            raise AssetDepotError("Asset Depot is not configured.")
        normalized_role = validate_asset_role(role)
        with self._lock:
            draft_exists = draft_id in self._drafts
        if not draft_exists:
            return None
        asset = self._asset_depot_service.get_asset(asset_id)
        if asset is None:
            raise AssetDepotError("Asset not found.")
        linked = _draft_asset_from_depot_item(
            draft_id=draft_id,
            asset=asset,
            role=normalized_role,
            notes=notes,
        )
        with self._lock:
            existing = [
                item
                for item in self._draft_assets.get(draft_id, [])
                if not (item.asset_id == asset_id and item.role == normalized_role)
            ]
            existing.append(linked)
            self._draft_assets[draft_id] = existing
            self._persist_draft_assets(draft_id)
        return linked

    def list_draft_assets(
        self,
        draft_id: str,
    ) -> tuple[ProjectFactoryDraftAsset, ...] | None:
        with self._lock:
            if draft_id not in self._drafts:
                return None
            return tuple(self._draft_assets.get(draft_id, []))

    def get_draft(self, draft_id: str) -> ProjectFactoryDraft | None:
        with self._lock:
            return self._drafts.get(draft_id)

    def list_drafts(self, *, limit: int = 50) -> tuple[dict[str, object], ...]:
        normalized_limit = _normalize_limit(limit)
        with self._lock:
            drafts = sorted(
                self._drafts.values(),
                key=lambda draft: draft.created_at,
                reverse=True,
            )
            return tuple(_draft_summary(draft) for draft in drafts[:normalized_limit])

    def dry_run(self, draft_id: str) -> ProjectFactoryManifestPlan | None:
        draft = self.get_draft(draft_id)
        if draft is None:
            return None
        return self._manifest_plan_for_draft(draft)

    def get_guided_intake(self, draft_id: str) -> dict[str, object] | None:
        with self._lock:
            draft = self._drafts.get(draft_id)
            if draft is None:
                return None
            refreshed = self._refresh_guided_intake(draft)
            return refreshed.guided_intake.to_payload()

    def answer_guided_intake_question(
        self,
        draft_id: str,
        *,
        question_id: str,
        value: object,
        source: str = "user",
        confidence: float = 1.0,
    ) -> dict[str, object] | None:
        with self._lock:
            draft = self._drafts.get(draft_id)
            if draft is None:
                return None
            updated_request = _apply_guided_answer_to_request(
                draft.request,
                question_id=question_id,
                value=value,
            )
            answers = [
                answer
                for answer in draft.guided_intake.answers
                if answer.question_id != question_id
            ]
            answers.append(
                ProjectFactoryGuidedIntakeAnswer(
                    question_id=question_id,
                    value=value,
                    source=_normalize_answer_source(source),
                    confidence=max(0.0, min(float(confidence), 1.0)),
                    updated_at=_now_iso(),
                )
            )
            manifest_plan = self._manifest_service.plan_manifest(updated_request)
            intake = _build_guided_intake(
                request=updated_request,
                manifest_plan=manifest_plan,
                draft_assets=tuple(self._draft_assets.get(draft_id, [])),
                enabled=True,
                answers=tuple(answers),
                previous_status=draft.guided_intake.status,
            )
            updated = replace(
                draft,
                request=updated_request,
                manifest_plan=manifest_plan,
                guided_intake=intake,
            )
            self._drafts[draft_id] = updated
            self._persist_draft(updated)
            return intake.to_payload()

    def preview_guided_intake_contract(
        self,
        draft_id: str,
    ) -> dict[str, object] | None:
        with self._lock:
            draft = self._drafts.get(draft_id)
            if draft is None:
                return None
            refreshed = self._refresh_guided_intake(draft)
            preview = _guided_contract_preview(
                request=refreshed.request,
                manifest_plan=refreshed.manifest_plan,
                draft_assets=tuple(self._draft_assets.get(draft_id, [])),
                intake=refreshed.guided_intake,
            )
            status = (
                "blocked"
                if _has_local_intake_blockers(refreshed.guided_intake)
                else (
                    "ready_for_review"
                    if not refreshed.guided_intake.missing_fields
                    else "collecting"
                )
            )
            intake = replace(
                refreshed.guided_intake,
                status=status,
                contract_preview=preview,
                updated_at=_now_iso(),
            )
            updated = replace(refreshed, guided_intake=intake)
            self._drafts[draft_id] = updated
            self._persist_draft(updated)
            return intake.to_payload()

    def confirm_guided_intake_contract(
        self,
        draft_id: str,
    ) -> dict[str, object] | None:
        with self._lock:
            draft = self._drafts.get(draft_id)
            if draft is None:
                return None
            refreshed = self._refresh_guided_intake(draft)
            preview = refreshed.guided_intake.contract_preview or _guided_contract_preview(
                request=refreshed.request,
                manifest_plan=refreshed.manifest_plan,
                draft_assets=tuple(self._draft_assets.get(draft_id, [])),
                intake=refreshed.guided_intake,
            )
            if refreshed.guided_intake.missing_fields or _has_local_intake_blockers(refreshed.guided_intake):
                intake = replace(
                    refreshed.guided_intake,
                    status="blocked" if _has_local_intake_blockers(refreshed.guided_intake) else "collecting",
                    contract_preview=preview,
                    updated_at=_now_iso(),
                )
            else:
                now = _now_iso()
                intake = replace(
                    refreshed.guided_intake,
                    status="confirmed",
                    contract_preview=preview,
                    confirmed_at=now,
                    updated_at=now,
                )
            updated = replace(refreshed, guided_intake=intake)
            self._drafts[draft_id] = updated
            self._persist_draft(updated)
            return intake.to_payload()

    def start_generation(self, draft_id: str) -> ProjectFactoryJob | None:
        with self._lock:
            draft = self._drafts.get(draft_id)
            if draft is None:
                return None
            if draft.guided_intake.enabled and draft.guided_intake.status not in {
                "confirmed",
                "build_started",
            }:
                now = _now_iso()
                manifest_plan = self._manifest_plan_for_draft(draft)
                job = ProjectFactoryJob(
                    id=_new_id("pf-job"),
                    draft_id=draft.id,
                    created_at=now,
                    updated_at=now,
                    status="blocked",
                    current_step="guided_intake_confirmation",
                    message="Confirm the guided New Project contract before generation.",
                    manifest_plan=manifest_plan,
                    current_phase="guided_intake_confirmation",
                    progress=0,
                    completed_at=now,
                    error="Guided intake contract is not confirmed.",
                    step_logs=[],
                )
                self._jobs[job.id] = job
                self._persist_job(job)
                return job
            existing = self._job_for_draft(draft_id)
            if existing is not None:
                if (
                    existing.status == "blocked"
                    and existing.current_phase == "guided_intake_confirmation"
                ):
                    self._jobs.pop(existing.id, None)
                    try:
                        (self._job_state_dir / f"{existing.id}.json").unlink()
                    except FileNotFoundError:
                        pass
                else:
                    raise ProjectFactoryGenerationConflictError(
                        f"Project generation already exists for draft {draft_id}: "
                        f"{existing.id} is {existing.status}."
                    )
            existing = self._job_for_draft(draft_id)
            if existing is not None:
                raise ProjectFactoryGenerationConflictError(
                    f"Project generation already exists for draft {draft_id}: "
                    f"{existing.id} is {existing.status}."
                )
        manifest_plan = self._manifest_plan_for_draft(draft)
        now = _now_iso()
        if not manifest_plan.ok:
            job = ProjectFactoryJob(
                id=_new_id("pf-job"),
                draft_id=draft.id,
                created_at=now,
                updated_at=now,
                status="blocked",
                current_step="validation",
                message="Fix validation errors before starting project generation.",
                manifest_plan=manifest_plan,
                current_phase="validation",
                progress=0,
                completed_at=now,
                error="Manifest validation failed.",
                step_logs=[],
            )
            with self._lock:
                self._jobs[job.id] = job
                self._persist_job(job)
            return job

        workflow_error = _creation_workflow_error(
            generator_runs=_effective_generator_runs(self, manifest_plan),
            reviewer_runs=_effective_reviewer_runs(self, manifest_plan),
        )
        if workflow_error is not None:
            job = ProjectFactoryJob(
                id=_new_id("pf-job"),
                draft_id=draft.id,
                created_at=now,
                updated_at=now,
                status="failed",
                current_step="creation_workflow",
                message=workflow_error,
                manifest_plan=manifest_plan,
                current_phase="creation_workflow",
                progress=0,
                completed_at=now,
                error=workflow_error,
                step_logs=[],
            )
            with self._lock:
                self._jobs[job.id] = job
                self._persist_job(job)
            return job

        if draft.guided_intake.enabled and draft.guided_intake.status == "confirmed":
            draft = replace(
                draft,
                guided_intake=replace(
                    draft.guided_intake,
                    status="build_started",
                    updated_at=_now_iso(),
                ),
            )
            with self._lock:
                self._drafts[draft_id] = draft
                self._persist_draft(draft)

        job = ProjectFactoryJob(
            id=_new_id("pf-job"),
            draft_id=draft.id,
            created_at=now,
            updated_at=now,
            status="queued",
            current_step="queued",
            message="Project Factory job queued.",
            manifest_plan=manifest_plan,
            current_phase="queued",
            progress=0,
            step_logs=[],
        )
        with self._lock:
            self._jobs[job.id] = job
            self._persist_job(job)
        if self._async_jobs:
            Thread(
                target=self._run_generation_job,
                args=(job.id, draft.id),
                daemon=True,
            ).start()
        else:
            self._run_generation_job(job.id, draft.id)
        return job

    def get_job(self, job_id: str) -> ProjectFactoryJob | None:
        self._audit_ready_job_publication(job_id)
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(
        self,
        *,
        status: str | None = None,
        draft_id: str | None = None,
        limit: int = 50,
    ) -> tuple[dict[str, object], ...]:
        normalized_limit = _normalize_limit(limit)
        normalized_status = status.strip() if status else None
        normalized_draft_id = draft_id.strip() if draft_id else None
        self._audit_ready_jobs_for_publication()
        with self._lock:
            jobs = sorted(
                self._jobs.values(),
                key=lambda job: job.created_at,
                reverse=True,
            )
            filtered = []
            for job in jobs:
                if normalized_status and job.status != normalized_status:
                    continue
                if normalized_draft_id and job.draft_id != normalized_draft_id:
                    continue
                filtered.append(_job_summary(job))
                if len(filtered) >= normalized_limit:
                    break
            return tuple(filtered)

    def _audit_ready_jobs_for_publication(self) -> None:
        if self._publication_validation_mode != "remote":
            return
        with self._lock:
            ready_job_ids = [
                job.id
                for job in self._jobs.values()
                if job.status == "ready"
            ]
        for job_id in ready_job_ids:
            self._audit_ready_job_publication(job_id)

    def _audit_ready_job_publication(self, job_id: str) -> None:
        if self._publication_validation_mode != "remote":
            return
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != "ready":
                return
            project_path_value = job.project_path or job.manifest_plan.target_path
        if not project_path_value:
            return
        project_path = Path(project_path_value).expanduser().resolve()
        initial_preview_script = (
            project_path / "scripts/validate_initial_preview_release.sh"
        )
        command = (
            "bash",
            "scripts/validate_initial_preview_release.sh"
            if initial_preview_script.is_file()
            else "scripts/validate_publication_ready.sh",
        )
        script = project_path / command[1]
        if not script.is_file():
            self._block_ready_job_publication(
                job_id=job_id,
                command=command,
                message=(
                    "Existing ready job is missing "
                    f"`{command[1]}`; publication cannot "
                    "be verified."
                ),
                stdout="",
                stderr="publication validation script is missing",
                exit_code=127,
            )
            return
        try:
            result = subprocess.run(
                list(command),
                cwd=project_path,
                env={
                    **os.environ,
                    "PUBLICATION_VALIDATION_MODE": "remote",
                },
                timeout=self._timeout_seconds if self._timeout_seconds > 0 else None,
                text=True,
                capture_output=True,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            self._block_ready_job_publication(
                job_id=job_id,
                command=command,
                message="Existing ready job publication verification timed out.",
                stdout=getattr(exc, "stdout", "") or "",
                stderr=str(exc),
                exit_code=None,
            )
            return
        if result.returncode == 0:
            return
        self._block_ready_job_publication(
            job_id=job_id,
            command=command,
            message=(
                "Existing ready job is missing verified GitHub release or "
                "Bridge registration artifacts."
            ),
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.returncode,
        )

    def _block_ready_job_publication(
        self,
        *,
        job_id: str,
        command: tuple[str, ...],
        message: str,
        stdout: str,
        stderr: str,
        exit_code: int | None,
    ) -> None:
        event = {
            "phase": "publish_verification",
            "status": "blocked",
            "message": message,
            "progress": 100,
            "command": list(command),
            "stdout": _truncate_summary(stdout, limit=4000) or "",
            "stderr": _truncate_summary(stderr, limit=4000) or "",
            "exit_code": exit_code,
        }
        self._record_event(job_id, event)
        self._update_job(
            job_id,
            status="blocked",
            current_phase="publish_verification",
            current_step="publish_verification",
            progress=100,
            message=message,
            error=message,
            completed_at=_now_iso(),
        )

    def _run_generation_job(self, job_id: str, draft_id: str) -> None:
        draft = self.get_draft(draft_id)
        if draft is None:
            return
        manifest_plan = self._manifest_plan_for_draft(draft)
        reference_assets = self._reference_asset_service.list_assets(draft.id)
        project_assets = tuple(self._draft_assets.get(draft.id, []))
        workflow = manifest_plan.manifest.get("codex", {}).get("creation_workflow", {})
        generator_runs = (
            self._generator_runs_override
            if self._generator_runs_override is not None
            else int(workflow.get("generator_runs", DEFAULT_CREATION_GENERATOR_RUNS))
        )
        reviewer_runs = (
            self._reviewer_runs_override
            if self._reviewer_runs_override is not None
            else int(workflow.get("reviewer_runs", DEFAULT_CREATION_REVIEWER_RUNS))
        )
        workflow_error = _creation_workflow_error(
            generator_runs=generator_runs,
            reviewer_runs=reviewer_runs,
        )
        if workflow_error is not None:
            self._update_job(
                job_id,
                status="failed",
                current_phase="creation_workflow",
                current_step="creation_workflow",
                progress=0,
                message=workflow_error,
                error=workflow_error,
                completed_at=_now_iso(),
            )
            return
        context = ProjectFactoryRunnerContext(
            draft_id=draft.id,
            manifest_plan=manifest_plan,
            reference_assets=reference_assets,
            project_assets=project_assets,
            generator_runs=generator_runs,
            reviewer_runs=reviewer_runs,
            codex_command=self._codex_command,
            timeout_seconds=self._timeout_seconds,
            run_generated_validation=self._run_generated_validation,
            publication_validation_mode=self._publication_validation_mode,
        )
        self._update_job(
            job_id,
            status="running",
            current_phase="scaffold",
            current_step="scaffold",
            message="Project Factory job started.",
            started_at=_now_iso(),
        )
        try:
            result = self._runner.run(
                context,
                event_sink=lambda event: self._record_event(job_id, event),
            )
        except ProjectFactoryJobRunnerBlockedError as exc:
            self._update_job(
                job_id,
                status="blocked",
                current_step="blocked",
                message=str(exc),
                error=str(exc),
                completed_at=_now_iso(),
            )
            return
        except ProjectFactoryJobRunnerError as exc:
            self._update_job(
                job_id,
                status="failed",
                current_step="failed",
                message=str(exc),
                error=str(exc),
                completed_at=_now_iso(),
            )
            return
        except Exception as exc:
            self._update_job(
                job_id,
                status="failed",
                current_step="failed",
                message=str(exc),
                error=str(exc),
                completed_at=_now_iso(),
            )
            return
        self._update_job(
            job_id,
            status="ready",
            current_phase="ready",
            current_step="ready",
            progress=100,
            message=_ready_message(
                result.generation_result.message,
                publication_validation_mode=self._publication_validation_mode,
                frontend_strategy=_frontend_strategy_from_manifest_plan(
                    manifest_plan,
                ),
            ),
            project_path=result.generation_result.target_path,
            generation_result=result.generation_result,
            completed_at=_now_iso(),
        )

    def _record_event(self, job_id: str, event: dict[str, object]) -> None:
        phase = str(event.get("phase") or "running")
        status = str(event.get("status") or "running")
        message = str(event.get("message") or "")
        progress = int(event.get("progress") or 0)
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if job.step_logs is None:
                job.step_logs = []
            job.step_logs.append({**event, "at": _now_iso()})
            job.current_phase = phase
            job.current_step = phase
            job.message = message
            job.progress = progress
            job.updated_at = _now_iso()
            if status == "failed":
                job.status = "failed"
                job.error = message
            elif status == "blocked":
                job.status = "blocked"
                job.error = message
            self._persist_job(job)

    def _update_job(self, job_id: str, **changes: object) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in changes.items():
                setattr(job, key, value)
            job.updated_at = _now_iso()
            self._persist_job(job)

    def _manifest_plan_for_draft(
        self,
        draft: ProjectFactoryDraft,
    ) -> ProjectFactoryManifestPlan:
        assets = self._reference_asset_service.list_assets(draft.id)
        project_assets = tuple(self._draft_assets.get(draft.id, []))
        request = ProjectFactoryManifestInput(
            name=draft.request.name,
            business_type=draft.request.business_type,
            primary_goal=draft.request.primary_goal,
            slug=draft.request.slug,
            platforms=draft.request.platforms,
            backend=draft.request.backend,
            frontend_strategy=draft.request.frontend_strategy,
            logo_mode=draft.request.logo_mode,
            first_release_mode=draft.request.first_release_mode,
            initial_admin_emails=draft.request.initial_admin_emails,
            visual_reference_paths=draft.request.visual_reference_paths,
            visual_reference_assets=tuple(
                asset.to_manifest_item() for asset in assets
            ),
            project_assets=tuple(asset.to_manifest_item() for asset in project_assets),
            guided_intake_enabled=draft.request.guided_intake_enabled,
        )
        return self._manifest_service.plan_manifest(request)

    def _refresh_guided_intake(
        self,
        draft: ProjectFactoryDraft,
    ) -> ProjectFactoryDraft:
        manifest_plan = self._manifest_plan_for_draft(draft)
        intake = _build_guided_intake(
            request=draft.request,
            manifest_plan=manifest_plan,
            draft_assets=tuple(self._draft_assets.get(draft.id, [])),
            enabled=draft.guided_intake.enabled,
            answers=draft.guided_intake.answers,
            previous_status=draft.guided_intake.status,
            contract_preview=draft.guided_intake.contract_preview,
            confirmed_at=draft.guided_intake.confirmed_at,
        )
        updated = replace(
            draft,
            manifest_plan=manifest_plan,
            guided_intake=intake,
        )
        self._drafts[draft.id] = updated
        self._persist_draft(updated)
        return updated

    def _job_for_draft(self, draft_id: str) -> ProjectFactoryJob | None:
        for job in self._jobs.values():
            if job.draft_id == draft_id:
                return job
        return None

    def _load_state(self) -> None:
        for draft_path in sorted(self._draft_state_dir.glob("*.json")):
            try:
                draft = _draft_from_storage_payload(
                    _read_json(draft_path),
                )
            except Exception:
                continue
            self._drafts[draft.id] = draft
        for draft_assets_path in sorted(self._draft_asset_state_dir.glob("*.json")):
            try:
                payload = _read_json(draft_assets_path)
                draft_id = str(payload["draft_id"])
                self._draft_assets[draft_id] = [
                    _draft_asset_from_payload(item)
                    for item in payload.get("assets", [])
                    if isinstance(item, dict)
                ]
            except Exception:
                continue
        recovered_jobs = False
        for job_path in sorted(self._job_state_dir.glob("*.json")):
            try:
                job = _job_from_storage_payload(_read_json(job_path))
            except Exception:
                continue
            if job.status in {"queued", "running"}:
                now = _now_iso()
                job.status = "interrupted"
                job.current_step = "interrupted"
                job.current_phase = "interrupted"
                job.completed_at = now
                job.updated_at = now
                job.error = "Project Factory job was interrupted by backend restart."
                job.message = job.error
                if job.step_logs is None:
                    job.step_logs = []
                job.step_logs.append(
                    {
                        "phase": "interrupted",
                        "status": "interrupted",
                        "message": job.error,
                        "progress": job.progress,
                        "command": [],
                        "stdout": "",
                        "stderr": "",
                        "exit_code": None,
                        "at": now,
                    }
                )
                recovered_jobs = True
            self._jobs[job.id] = job
        if recovered_jobs:
            for job in self._jobs.values():
                if job.status == "interrupted":
                    self._persist_job(job)

    def _persist_draft(self, draft: ProjectFactoryDraft) -> None:
        _atomic_write_json(
            self._draft_state_dir / f"{draft.id}.json",
            _draft_storage_payload(draft),
        )

    def _persist_job(self, job: ProjectFactoryJob) -> None:
        _atomic_write_json(
            self._job_state_dir / f"{job.id}.json",
            _job_storage_payload(job),
        )

    def _persist_draft_assets(self, draft_id: str) -> None:
        _atomic_write_json(
            self._draft_asset_state_dir / f"{draft_id}.json",
            {
                "kind": "codex.projectFactoryDraftAssets.storage",
                "version": 1,
                "draft_id": draft_id,
                "assets": [
                    item.to_payload() for item in self._draft_assets.get(draft_id, [])
                ],
            },
        )


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _doctor_check(code: str, ok: bool, detail: str) -> dict[str, object]:
    return {
        "code": code,
        "ok": ok,
        "detail": detail,
    }


def _effective_generator_runs(
    service: ProjectFactoryService,
    manifest_plan: ProjectFactoryManifestPlan,
) -> int:
    workflow = manifest_plan.manifest.get("codex", {}).get("creation_workflow", {})
    return (
        service._generator_runs_override
        if service._generator_runs_override is not None
        else int(workflow.get("generator_runs", DEFAULT_CREATION_GENERATOR_RUNS))
    )


def _effective_reviewer_runs(
    service: ProjectFactoryService,
    manifest_plan: ProjectFactoryManifestPlan,
) -> int:
    workflow = manifest_plan.manifest.get("codex", {}).get("creation_workflow", {})
    return (
        service._reviewer_runs_override
        if service._reviewer_runs_override is not None
        else int(workflow.get("reviewer_runs", DEFAULT_CREATION_REVIEWER_RUNS))
    )


def _creation_workflow_error(
    *,
    generator_runs: int,
    reviewer_runs: int,
) -> str | None:
    if generator_runs == reviewer_runs:
        return None
    return (
        "Paired generator/reviewer workflow requires matching run counts: "
        f"generator={generator_runs}, reviewer={reviewer_runs}."
    )


def _draft_summary(draft: ProjectFactoryDraft) -> dict[str, object]:
    manifest = draft.manifest_plan.manifest
    return {
        "id": draft.id,
        "draft_id": draft.id,
        "name": draft.request.name,
        "slug": manifest.get("slug") or draft.request.slug,
        "business_type": draft.request.business_type,
        "primary_goal": draft.request.primary_goal,
        "status": draft.manifest_plan.status,
        "ok": draft.manifest_plan.ok,
        "created_at": draft.created_at,
        "target_path": draft.manifest_plan.target_path,
        "error": _summary_error(draft.manifest_plan.errors),
        "first_release_mode": draft.request.first_release_mode,
        "frontend_strategy": draft.request.frontend_strategy,
        "guided_intake": draft.guided_intake.to_payload(),
        "initial_preview_release": _initial_preview_release_status(
            manifest=manifest,
        ),
    }


def _job_summary(job: ProjectFactoryJob) -> dict[str, object]:
    manifest = job.manifest_plan.manifest
    target_path = job.project_path
    if not target_path and job.generation_result is not None:
        target_path = job.generation_result.target_path
    if not target_path:
        target_path = job.manifest_plan.target_path
    return {
        "id": job.id,
        "job_id": job.id,
        "draft_id": job.draft_id,
        "name": manifest.get("name"),
        "slug": manifest.get("slug"),
        "status": job.status,
        "current_phase": job.current_phase,
        "progress": job.progress,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "project_path": target_path if job.status == "ready" else job.project_path,
        "target_path": target_path,
        "error": _truncate_summary(job.error),
        "message": _truncate_summary(job.message),
        "manual_next_step": _manual_next_step(job),
        "first_release_mode": _first_release_mode_from_manifest_plan(job.manifest_plan),
        "frontend_strategy": _frontend_strategy_from_manifest_plan(job.manifest_plan),
        "initial_preview_release": _initial_preview_release_status(
            manifest=manifest,
            status=job.status,
            current_phase=job.current_phase,
            blocker_text=job.error if job.status == "blocked" else None,
            step_logs=list(job.step_logs or []),
        ),
    }


def _build_guided_intake(
    *,
    request: ProjectFactoryManifestInput,
    manifest_plan: ProjectFactoryManifestPlan,
    draft_assets: tuple[ProjectFactoryDraftAsset, ...],
    enabled: bool,
    answers: tuple[ProjectFactoryGuidedIntakeAnswer, ...] = (),
    previous_status: str | None = None,
    contract_preview: dict[str, object] | None = None,
    confirmed_at: str | None = None,
) -> ProjectFactoryGuidedIntake:
    now = _now_iso()
    if not enabled:
        return ProjectFactoryGuidedIntake(
            enabled=False,
            status="confirmed",
            questions=(),
            answers=answers,
            missing_fields=(),
            assumptions=(),
            blockers=(),
            contract_preview=contract_preview,
            confirmed_at=confirmed_at or now,
            updated_at=now,
        )
    missing_fields = _guided_missing_fields(request, manifest_plan)
    questions = _guided_questions(request, missing_fields)
    assumptions = _guided_assumptions(request, draft_assets)
    blockers = _guided_blockers(request, manifest_plan)
    if any(not bool(blocker.get("external")) for blocker in blockers):
        status = "blocked"
    elif confirmed_at and previous_status in {"confirmed", "build_started"}:
        status = previous_status or "confirmed"
    elif not missing_fields:
        status = "ready_for_review"
    else:
        status = "collecting"
    return ProjectFactoryGuidedIntake(
        enabled=True,
        status=status,
        questions=tuple(questions),
        answers=answers,
        missing_fields=tuple(missing_fields),
        assumptions=tuple(assumptions),
        blockers=tuple(blockers),
        contract_preview=contract_preview,
        confirmed_at=confirmed_at,
        updated_at=now,
    )


def _guided_missing_fields(
    request: ProjectFactoryManifestInput,
    manifest_plan: ProjectFactoryManifestPlan,
) -> list[dict[str, object]]:
    missing: list[dict[str, object]] = []
    if not request.name.strip():
        missing.append(_missing_field("name", "Project name is required.", "local"))
    if not request.business_type.strip():
        missing.append(_missing_field("business_type", "Business type is required.", "local"))
    if not request.primary_goal.strip():
        missing.append(_missing_field("primary_goal", "Primary goal is required.", "local"))
    if not request.platforms:
        missing.append(_missing_field("platforms", "At least one platform is required.", "local"))
    if request.first_release_mode == "preview" and not request.initial_admin_emails:
        missing.append(
            _missing_field(
                "initial_admin_emails",
                "Initial admin email is required before web-preview invite delivery.",
                "release",
            )
        )
    for error in manifest_plan.errors:
        if not any(item["field"] == error.field for item in missing):
            missing.append(_missing_field(error.field, error.message, "local"))
    return missing


def _missing_field(field: str, message: str, scope: str) -> dict[str, object]:
    return {"field": field, "message": message, "scope": scope}


def _guided_questions(
    request: ProjectFactoryManifestInput,
    missing_fields: list[dict[str, object]],
) -> list[dict[str, object]]:
    questions: list[dict[str, object]] = []
    missing = {str(item["field"]) for item in missing_fields}
    if "initial_admin_emails" in missing:
        questions.append(
            {
                "id": "initial_admin_emails",
                "field": "initial_admin_emails",
                "title": "Initial admin emails",
                "prompt": "Who should receive the first preview admin invite?",
                "answerType": "email_list",
                "required": True,
                "options": [
                    {
                        "id": "owner-email",
                        "label": "Use owner/admin email",
                        "value": "",
                        "recommended": True,
                    }
                ],
            }
        )
    if "platforms" in missing:
        questions.append(
            {
                "id": "platforms",
                "field": "platforms",
                "title": "Platforms",
                "prompt": "Which platforms should the first project target?",
                "answerType": "string_list",
                "required": True,
                "options": [
                    {
                        "id": "flutter-default",
                        "label": "iOS, Android, and Web",
                        "value": ["ios", "android", "web"],
                        "recommended": True,
                    },
                    {
                        "id": "web-only",
                        "label": "Web only",
                        "value": ["web"],
                        "recommended": False,
                    },
                ],
            }
        )
    if "frontend_strategy" in missing or request.frontend_strategy == "svelte":
        questions.append(
            {
                "id": "frontend_strategy",
                "field": "frontend_strategy",
                "title": "Frontend strategy",
                "prompt": "Choose Flutter for APK/installable preview or Svelte for web-only preview.",
                "answerType": "single_choice",
                "required": True,
                "options": [
                    {
                        "id": "flutter",
                        "label": "Flutter APK + Web",
                        "value": "flutter",
                        "recommended": request.frontend_strategy != "svelte",
                    },
                    {
                        "id": "svelte",
                        "label": "Svelte web only",
                        "value": "svelte",
                        "recommended": request.frontend_strategy == "svelte",
                    },
                ],
            }
        )
    return questions


def _guided_assumptions(
    request: ProjectFactoryManifestInput,
    draft_assets: tuple[ProjectFactoryDraftAsset, ...],
) -> list[dict[str, object]]:
    assumptions = [
        {
            "field": "runtime_profile",
            "value": "preview",
            "source": "default",
            "confidence": 1.0,
        },
        {
            "field": "first_release_mode",
            "value": request.first_release_mode,
            "source": "default" if request.first_release_mode == "preview" else "user",
            "confidence": 0.9,
        },
    ]
    for asset in draft_assets:
        assumptions.append(
            {
                "field": f"asset:{asset.asset_id}",
                "value": asset.role,
                "source": "asset_role",
                "confidence": 1.0,
                "notes": asset.notes,
            }
        )
    return assumptions


def _guided_blockers(
    request: ProjectFactoryManifestInput,
    manifest_plan: ProjectFactoryManifestPlan,
) -> list[dict[str, object]]:
    blockers: list[dict[str, object]] = []
    if not manifest_plan.ok:
        blockers.append(
            {
                "scope": "local_planning",
                "code": "manifest_validation",
                "message": "Fix manifest validation before confirming the contract.",
            }
        )
    if request.first_release_mode == "preview":
        blockers.extend(
            [
                {
                    "scope": "release",
                    "code": "cloudflare_credentials",
                    "message": "Cloudflare preview credentials must pass doctor before remote publication.",
                    "external": True,
                },
                {
                    "scope": "release",
                    "code": "email_delivery",
                    "message": "Email provider may use manual-link fallback until SMTP/sender domain is configured.",
                    "external": True,
                },
                {
                    "scope": "installable_app",
                    "code": "bridge_registration",
                    "message": "Bridge installable-app registration is verified during Initial Preview Release.",
                    "external": True,
                },
            ]
        )
    return blockers


def _guided_contract_preview(
    *,
    request: ProjectFactoryManifestInput,
    manifest_plan: ProjectFactoryManifestPlan,
    draft_assets: tuple[ProjectFactoryDraftAsset, ...],
    intake: ProjectFactoryGuidedIntake,
) -> dict[str, object]:
    manifest = manifest_plan.manifest
    slug = manifest.get("slug") or request.slug
    return {
        "status": "blocked" if _has_local_intake_blockers(intake) else "ready_for_review",
        "decisions": {
            "name": request.name,
            "slug": slug,
            "businessType": request.business_type,
            "primaryGoal": request.primary_goal,
            "platforms": list(request.platforms),
            "backend": request.backend,
            "frontendStrategy": request.frontend_strategy,
            "firstReleaseMode": request.first_release_mode,
            "initialAdminEmails": list(request.initial_admin_emails),
        },
        "defaults": {
            "runtimeProfile": "preview",
            "apiRuntime": "cloudflare_preview",
            "previewUrl": f"https://preview.nienfos.com/{slug}" if slug else None,
            "apiBaseUrl": f"https://preview.nienfos.com/{slug}/api" if slug else None,
        },
        "assumptions": [dict(item) for item in intake.assumptions],
        "missingFields": [dict(item) for item in intake.missing_fields],
        "blockers": [dict(item) for item in intake.blockers],
        "assets": [asset.to_payload() for asset in draft_assets],
        "manifestPlan": manifest_plan.to_payload(),
    }


def _apply_guided_answer_to_request(
    request: ProjectFactoryManifestInput,
    *,
    question_id: str,
    value: object,
) -> ProjectFactoryManifestInput:
    if question_id == "initial_admin_emails":
        emails = _coerce_string_list(value)
        return replace(request, initial_admin_emails=tuple(emails), guided_intake_enabled=True)
    if question_id == "platforms":
        platforms = _coerce_string_list(value)
        return replace(request, platforms=tuple(platforms), guided_intake_enabled=True)
    if question_id == "frontend_strategy":
        return replace(request, frontend_strategy=str(value), guided_intake_enabled=True)
    if question_id == "primary_goal":
        return replace(request, primary_goal=str(value), guided_intake_enabled=True)
    if question_id == "business_type":
        return replace(request, business_type=str(value), guided_intake_enabled=True)
    if question_id == "name":
        return replace(request, name=str(value), guided_intake_enabled=True)
    return replace(request, guided_intake_enabled=True)


def _coerce_string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _normalize_answer_source(source: str) -> str:
    normalized = source.strip().lower()
    return normalized if normalized in {"user", "inference", "default", "asset", "system"} else "user"


def _has_local_intake_blockers(intake: ProjectFactoryGuidedIntake) -> bool:
    return any(not bool(blocker.get("external")) for blocker in intake.blockers)


def _summary_error(errors: tuple[ProjectFactoryValidationError, ...]) -> str | None:
    if not errors:
        return None
    return _truncate_summary("; ".join(error.message for error in errors))


def _first_release_mode_from_manifest_plan(plan: ProjectFactoryManifestPlan) -> str:
    release = plan.manifest.get("release")
    if isinstance(release, dict):
        mode = release.get("first_release_mode")
        if isinstance(mode, str) and mode.strip():
            return mode
    runtime = plan.manifest.get("runtime_profiles")
    if isinstance(runtime, dict):
        mode = runtime.get("first_release_mode")
        if isinstance(mode, str) and mode.strip():
            return mode
    return DEFAULT_FIRST_RELEASE_MODE


def _frontend_strategy_from_manifest_plan(plan: ProjectFactoryManifestPlan) -> str:
    strategy = plan.manifest.get("frontend_strategy")
    if isinstance(strategy, str) and strategy.strip():
        return strategy
    frontend = plan.manifest.get("frontend")
    if isinstance(frontend, dict):
        strategy = frontend.get("strategy")
        if isinstance(strategy, str) and strategy.strip():
            return strategy
    return DEFAULT_FRONTEND_STRATEGY


def _manual_next_step(job: ProjectFactoryJob) -> str | None:
    if job.status == "ready":
        return None
    if job.status == "blocked":
        return (
            "Open job details, inspect the blocked publication phase, provide the "
            "missing GitHub/release/Bridge configuration, then rerun generation or "
            "execute the logged command manually from the generated project."
        )
    if job.status in {"failed", "interrupted", "blocked"}:
        return "Open job details, inspect step logs, and create a new draft if regeneration is required."
    return "Reopen this job to continue watching progress."


def _initial_preview_release_status(
    *,
    manifest: dict[str, object],
    status: str | None = None,
    current_phase: str | None = None,
    blocker_text: str | None = None,
    step_logs: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    slug = str(manifest.get("slug") or "")
    frontend_strategy = str(manifest.get("frontend_strategy") or DEFAULT_FRONTEND_STRATEGY)
    frontend = manifest.get("frontend") if isinstance(manifest.get("frontend"), dict) else {}
    capabilities = (
        frontend.get("strategy_capabilities")
        if isinstance(frontend, dict)
        else {}
    )
    supports_android_installable = bool(
        isinstance(capabilities, dict)
        and capabilities.get("supports_android_preview_apk") is True
        and capabilities.get("supports_bridge_installable_app") is True
    )
    if not capabilities:
        supports_android_installable = frontend_strategy == "flutter"
    preview_url = f"https://preview.nienfos.com/{slug}" if slug else None
    api_url = f"{preview_url}/api" if preview_url else None
    phases = [
        "cloudflare_preview_preflight",
        "github_publish",
        "cloudflare_preview_apply",
        "web_preview_smoke",
        "preview_api_smoke",
    ]
    if supports_android_installable:
        phases.extend(
            [
                "android_preview_release",
                "installable_app_registration",
            ]
        )
    phases.append("publish_verification")
    phase_statuses: dict[str, dict[str, object]] = {
        phase: {
            "status": "pending",
            "message": "",
            "command": _manual_command_for_phase(phase),
        }
        for phase in phases
    }
    for event in step_logs or []:
        phase = str(event.get("phase") or "")
        if phase not in phase_statuses:
            continue
        phase_statuses[phase] = {
            "status": str(event.get("status") or "pending"),
            "message": _truncate_summary(str(event.get("message") or "")) or "",
            "command": list(event.get("command") or _manual_command_for_phase(phase)),
            "exit_code": event.get("exit_code"),
        }
    if status == "ready":
        for phase in phases:
            phase_statuses[phase]["status"] = "completed"
    return {
        "sourceApp": slug,
        "previewUrl": preview_url,
        "apiBaseUrl": api_url,
        "frontendStrategy": frontend_strategy,
        "strategyCapabilities": dict(capabilities) if isinstance(capabilities, dict) else {},
        "installableAndroid": supports_android_installable,
        "bridgeRegistrationRequired": supports_android_installable,
        "runtimeProfile": "preview",
        "apiRuntime": "cloudflare_preview",
        "releaseChannel": "prerelease",
        "releaseTagPattern": "android-preview-v*" if supports_android_installable else None,
        "productionReady": False,
        "mockOrDemo": False,
        "status": status or "draft",
        "currentPhase": current_phase or "draft",
        "phaseStatuses": phase_statuses,
        "blockerText": _truncate_summary(blocker_text, limit=1000),
        "manualCommandHints": [
            "GET /project-factory/doctor",
            "scripts/apply_cloudflare_preview.sh",
            "scripts/smoke_web_preview.sh",
            "scripts/smoke_preview_api.sh",
            "scripts/validate_initial_preview_release.sh",
        ]
        + (
            [
                "scripts/publish_android_preview_release.sh --push --watch",
                "scripts/register_installable_app.sh",
            ]
            if supports_android_installable
            else []
        ),
    }


def _manual_command_for_phase(phase: str) -> list[str]:
    commands = {
        "cloudflare_preview_preflight": ["GET", "/project-factory/doctor"],
        "github_publish": ["bash", "scripts/publish_project.sh"],
        "cloudflare_preview_apply": ["bash", "scripts/apply_cloudflare_preview.sh"],
        "web_preview_smoke": ["bash", "scripts/smoke_web_preview.sh"],
        "preview_api_smoke": ["bash", "scripts/smoke_preview_api.sh"],
        "android_preview_release": [
            "bash",
            "scripts/publish_android_preview_release.sh",
            "--push",
            "--watch",
        ],
        "installable_app_registration": ["bash", "scripts/register_installable_app.sh"],
        "publish_verification": ["bash", "scripts/validate_initial_preview_release.sh"],
    }
    return commands.get(phase, [])


def _ready_message(
    local_message: str,
    *,
    publication_validation_mode: str,
    frontend_strategy: str = DEFAULT_FRONTEND_STRATEGY,
) -> str:
    if publication_validation_mode == "remote":
        if frontend_strategy == "svelte":
            return (
                "Project published to GitHub and Cloudflare web/API preview "
                "verified. Android installability is not part of the Svelte "
                "strategy."
            )
        return (
            "Project published to GitHub, Android release verified, and "
            "installable app registration completed."
        )
    return local_message


def _draft_asset_from_depot_item(
    *,
    draft_id: str,
    asset: AssetDepotItem,
    role: str,
    notes: str,
) -> ProjectFactoryDraftAsset:
    return ProjectFactoryDraftAsset(
        draft_id=draft_id,
        asset_id=asset.id,
        role=role,
        notes=notes.strip()[:1000],
        linked_at=_now_iso(),
        original_filename=asset.original_filename,
        content_type=asset.content_type,
        size_bytes=asset.size_bytes,
        sha256=asset.sha256,
        storage_path=asset.storage_path,
        source=asset.source,
    )


def _draft_asset_from_payload(payload: dict[str, object]) -> ProjectFactoryDraftAsset:
    return ProjectFactoryDraftAsset(
        draft_id=str(payload["draft_id"]),
        asset_id=str(payload["asset_id"]),
        role=str(payload["role"]),
        notes=str(payload.get("notes") or ""),
        linked_at=str(payload["linked_at"]),
        original_filename=str(payload["original_filename"]),
        content_type=str(payload["content_type"]),
        size_bytes=int(payload["size_bytes"]),
        sha256=str(payload["sha256"]),
        storage_path=str(payload["storage_path"]),
        source=str(payload["source"]),
    )


def _truncate_summary(value: str | None, limit: int = 300) -> str | None:
    if not value:
        return None
    return value if len(value) <= limit else value[:limit] + "..."


def _normalize_limit(limit: int) -> int:
    return max(1, min(limit, 200))


def _draft_storage_payload(draft: ProjectFactoryDraft) -> dict[str, object]:
    return {
        "kind": "codex.projectFactoryDraft.storage",
        "version": 1,
        "id": draft.id,
        "created_at": draft.created_at,
        "request": {
            "name": draft.request.name,
            "business_type": draft.request.business_type,
            "primary_goal": draft.request.primary_goal,
            "slug": draft.request.slug,
            "platforms": list(draft.request.platforms),
            "backend": draft.request.backend,
            "frontend_strategy": draft.request.frontend_strategy,
            "logo_mode": draft.request.logo_mode,
            "first_release_mode": draft.request.first_release_mode,
            "initial_admin_emails": list(draft.request.initial_admin_emails),
            "visual_reference_paths": list(draft.request.visual_reference_paths),
            "visual_reference_assets": [
                dict(item) for item in draft.request.visual_reference_assets
            ],
            "guided_intake_enabled": draft.request.guided_intake_enabled,
        },
        "manifest_plan": draft.manifest_plan.to_payload(),
        "guided_intake": draft.guided_intake.to_payload(),
    }


def _job_storage_payload(job: ProjectFactoryJob) -> dict[str, object]:
    return {
        "kind": "codex.projectFactoryJob.storage",
        "version": 1,
        "payload": job.to_payload(),
    }


def _draft_from_storage_payload(payload: dict[str, object]) -> ProjectFactoryDraft:
    request_payload = payload["request"]
    if not isinstance(request_payload, dict):
        raise ValueError("Invalid draft request payload.")
    return ProjectFactoryDraft(
        id=str(payload["id"]),
        created_at=str(payload["created_at"]),
        request=_request_from_payload(request_payload),
        manifest_plan=_manifest_plan_from_payload(
            _expect_mapping(payload["manifest_plan"]),
        ),
        guided_intake=_guided_intake_from_payload(
            payload.get("guided_intake"),
            request=_request_from_payload(request_payload),
            manifest_plan=_manifest_plan_from_payload(
                _expect_mapping(payload["manifest_plan"]),
            ),
        ),
    )


def _job_from_storage_payload(payload: dict[str, object]) -> ProjectFactoryJob:
    job_payload = _expect_mapping(payload["payload"])
    generation_result_payload = job_payload.get("generation_result")
    return ProjectFactoryJob(
        id=str(job_payload["job_id"]),
        draft_id=str(job_payload["draft_id"]),
        created_at=str(job_payload["created_at"]),
        updated_at=str(job_payload["updated_at"]),
        status=str(job_payload["status"]),
        current_step=str(job_payload["current_step"]),
        current_phase=str(job_payload.get("current_phase") or "queued"),
        progress=int(job_payload.get("progress") or 0),
        started_at=_optional_str(job_payload.get("started_at")),
        completed_at=_optional_str(job_payload.get("completed_at")),
        error=_optional_str(job_payload.get("error")),
        project_path=_optional_str(job_payload.get("project_path")),
        message=str(job_payload.get("message") or ""),
        manifest_plan=_manifest_plan_from_payload(
            _expect_mapping(job_payload["manifest_plan"]),
        ),
        step_logs=[
            dict(item)
            for item in job_payload.get("step_logs", [])
            if isinstance(item, dict)
        ],
        generation_result=(
            _generation_result_from_payload(_expect_mapping(generation_result_payload))
            if isinstance(generation_result_payload, dict)
            else None
        ),
    )


def _request_from_payload(payload: dict[str, object]) -> ProjectFactoryManifestInput:
    return ProjectFactoryManifestInput(
        name=str(payload["name"]),
        business_type=str(payload["business_type"]),
        primary_goal=str(payload["primary_goal"]),
        slug=_optional_str(payload.get("slug")),
        platforms=tuple(
            str(item)
            for item in payload.get("platforms", DEFAULT_PLATFORMS)
            if isinstance(item, str)
        ),
        backend=str(payload.get("backend") or DEFAULT_BACKEND),
        frontend_strategy=str(
            payload.get("frontend_strategy") or DEFAULT_FRONTEND_STRATEGY
        ),
        logo_mode=str(payload.get("logo_mode") or "generate"),
        first_release_mode=str(
            payload.get("first_release_mode") or DEFAULT_FIRST_RELEASE_MODE
        ),
        initial_admin_emails=tuple(
            str(item)
            for item in payload.get("initial_admin_emails", [])
            if isinstance(item, str)
        ),
        visual_reference_paths=tuple(
            str(item)
            for item in payload.get("visual_reference_paths", [])
            if isinstance(item, str)
        ),
        visual_reference_assets=tuple(
            dict(item)
            for item in payload.get("visual_reference_assets", [])
            if isinstance(item, dict)
        ),
        guided_intake_enabled=bool(payload.get("guided_intake_enabled") or False),
    )


def _guided_intake_from_payload(
    value: object,
    *,
    request: ProjectFactoryManifestInput,
    manifest_plan: ProjectFactoryManifestPlan,
) -> ProjectFactoryGuidedIntake:
    if not isinstance(value, dict):
        return _build_guided_intake(
            request=replace(request, guided_intake_enabled=False),
            manifest_plan=manifest_plan,
            draft_assets=(),
            enabled=False,
        )
    answers = tuple(
        ProjectFactoryGuidedIntakeAnswer(
            question_id=str(item.get("questionId") or item.get("question_id") or ""),
            value=item.get("value"),
            source=str(item.get("source") or "user"),
            confidence=float(item.get("confidence") or 1.0),
            updated_at=str(item.get("updatedAt") or item.get("updated_at") or _now_iso()),
        )
        for item in value.get("answers", [])
        if isinstance(item, dict)
    )
    enabled = bool(value.get("enabled"))
    return ProjectFactoryGuidedIntake(
        enabled=enabled,
        status=str(value.get("status") or ("collecting" if enabled else "confirmed")),
        questions=tuple(
            dict(item) for item in value.get("questions", []) if isinstance(item, dict)
        ),
        answers=answers,
        missing_fields=tuple(
            dict(item)
            for item in (value.get("missingFields") or value.get("missing_fields") or [])
            if isinstance(item, dict)
        ),
        assumptions=tuple(
            dict(item) for item in value.get("assumptions", []) if isinstance(item, dict)
        ),
        blockers=tuple(
            dict(item) for item in value.get("blockers", []) if isinstance(item, dict)
        ),
        contract_preview=(
            dict(value["contractPreview"])
            if isinstance(value.get("contractPreview"), dict)
            else (
                dict(value["contract_preview"])
                if isinstance(value.get("contract_preview"), dict)
                else None
            )
        ),
        confirmed_at=_optional_str(value.get("confirmedAt") or value.get("confirmed_at")),
        updated_at=str(value.get("updatedAt") or value.get("updated_at") or _now_iso()),
    )


def _manifest_plan_from_payload(payload: dict[str, object]) -> ProjectFactoryManifestPlan:
    return ProjectFactoryManifestPlan(
        ok=bool(payload["ok"]),
        status=str(payload["status"]),
        target_path=_optional_str(payload.get("target_path")),
        manifest_path=_optional_str(payload.get("manifest_path")),
        manifest=dict(_expect_mapping(payload.get("manifest", {}))),
        errors=tuple(
            ProjectFactoryValidationError(
                code=str(error["code"]),
                field=str(error["field"]),
                message=str(error["message"]),
            )
            for error in payload.get("errors", [])
            if isinstance(error, dict)
        ),
        next_actions=tuple(
            str(item) for item in payload.get("next_actions", []) if isinstance(item, str)
        ),
    )


def _generation_result_from_payload(
    payload: dict[str, object],
) -> ProjectFactoryGenerationResult:
    return ProjectFactoryGenerationResult(
        ok=bool(payload["ok"]),
        status=str(payload["status"]),
        target_path=str(payload["target_path"]),
        generated_files=tuple(
            ProjectFactoryGeneratedFile(
                path=str(item["path"]),
                size_bytes=int(item["size_bytes"]),
            )
            for item in payload.get("generated_files", [])
            if isinstance(item, dict)
        ),
        git_status=str(payload["git_status"]),
        message=str(payload["message"]),
    )


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temp_path, path)


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON payload must be an object.")
    return payload


def _expect_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Expected object payload.")
    return dict(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _toolchain_report(codex_command: str) -> dict[str, dict[str, object]]:
    codex_parts = shlex.split(codex_command.strip() or "codex")
    codex_binary = codex_parts[0] if codex_parts else "codex"
    return {
        "python": {
            "available": True,
            "command": sys.executable,
            "version": sys.version.split()[0],
        },
        "pytest": _command_report((sys.executable, "-m", "pytest", "--version")),
        "flutter": _command_report(("flutter", "--version")),
        "dart": _command_report(("dart", "--version")),
        "codex_cli": _command_report((codex_binary, "--version")),
    }


def _command_report(argv: tuple[str, ...]) -> dict[str, object]:
    binary = argv[0]
    resolved = shutil.which(binary) if os.path.sep not in binary else binary
    if resolved is None:
        return {
            "available": False,
            "command": binary,
            "version": None,
            "error": "Command not found on PATH.",
        }
    try:
        completed = subprocess.run(
            list(argv),
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
            shell=False,
        )
    except Exception as exc:
        return {
            "available": True,
            "command": resolved,
            "version": None,
            "error": str(exc),
        }
    output = (completed.stdout or completed.stderr).strip().splitlines()
    return {
        "available": completed.returncode == 0,
        "command": resolved,
        "version": output[0] if output else None,
        "exit_code": completed.returncode,
    }
