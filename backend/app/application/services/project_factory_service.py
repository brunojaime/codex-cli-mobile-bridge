from __future__ import annotations

from dataclasses import dataclass
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
    ProjectFactoryJobRunnerError,
    ProjectFactoryRunnerContext,
)
from backend.app.application.services.project_factory_manifest_service import (
    DEFAULT_BACKEND,
    DEFAULT_CREATION_GENERATOR_RUNS,
    DEFAULT_CREATION_REVIEWER_RUNS,
    DEFAULT_PLATFORMS,
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

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": "codex.projectFactoryDraft",
            "version": 1,
            "draft_id": self.id,
            "created_at": self.created_at,
            "manifest_plan": self.manifest_plan.to_payload(),
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
            "manifest_plan": self.manifest_plan.to_payload(),
            "step_logs": logs,
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
                "mode": "generator_reviewer_batches",
                "generator_runs": DEFAULT_CREATION_GENERATOR_RUNS,
                "reviewer_runs": DEFAULT_CREATION_REVIEWER_RUNS,
            },
        }

    def doctor(self) -> dict[str, object]:
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
                "Default creation workflow must stay 20 generator and 20 reviewer runs.",
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

    def start_generation(self, draft_id: str) -> ProjectFactoryJob | None:
        with self._lock:
            draft = self._drafts.get(draft_id)
            if draft is None:
                return None
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
            message=result.generation_result.message,
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
            logo_mode=draft.request.logo_mode,
            visual_reference_paths=draft.request.visual_reference_paths,
            visual_reference_assets=tuple(
                asset.to_manifest_item() for asset in assets
            ),
            project_assets=tuple(asset.to_manifest_item() for asset in project_assets),
        )
        return self._manifest_service.plan_manifest(request)

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
    }


def _summary_error(errors: tuple[ProjectFactoryValidationError, ...]) -> str | None:
    if not errors:
        return None
    return _truncate_summary("; ".join(error.message for error in errors))


def _manual_next_step(job: ProjectFactoryJob) -> str | None:
    if job.status == "ready":
        return None
    if job.status in {"failed", "interrupted", "blocked"}:
        return "Open job details, inspect step logs, and create a new draft if regeneration is required."
    return "Reopen this job to continue watching progress."


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
            "logo_mode": draft.request.logo_mode,
            "visual_reference_paths": list(draft.request.visual_reference_paths),
            "visual_reference_assets": [
                dict(item) for item in draft.request.visual_reference_assets
            ],
        },
        "manifest_plan": draft.manifest_plan.to_payload(),
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
        logo_mode=str(payload.get("logo_mode") or "generate"),
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
