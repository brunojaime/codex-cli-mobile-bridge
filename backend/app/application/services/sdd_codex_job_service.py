from __future__ import annotations

import difflib
import json
import os
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from backend.app.application.services.sdd_context_pack_service import (
    SddContextPack,
    SddContextPackService,
)
from backend.app.application.services.sdd_index_service import SddIndexService
from backend.app.application.services.sdd_intake_service import SddIntakeService
from backend.app.application.services.sdd_metadata_refresh_service import (
    SddMetadataRefreshService,
)
from backend.app.application.services.sdd_standard_service import (
    DEFAULT_STANDARD_ID,
    SddStandardService,
    parse_simple_yaml,
)
from backend.app.application.services.sdd_spec_edit_service import SddSpecEditDryRunPlan
from backend.app.application.services.sdd_spec_target_service import (
    SpecIntakeValidationInput,
)


TERMINAL_STATUSES = frozenset(
    {"completed", "failed", "blocked", "cancelled", "timed_out"}
)
RETRYABLE_STATUSES = frozenset({"failed", "timed_out", "cancelled"})
ALLOWED_ENV_KEYS = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "CODEX_HOME",
        "HOME",
        "LANG",
        "LC_ALL",
        "LOGNAME",
        "OPENAI_API_KEY",
        "PATH",
        "TERM",
        "USER",
    }
)


@dataclass(frozen=True, slots=True)
class SddCodexProcessResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class SddCodexProcessRunner(Protocol):
    def run(
        self,
        *,
        argv: tuple[str, ...],
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> SddCodexProcessResult: ...


class SubprocessCodexRunner:
    def run(
        self,
        *,
        argv: tuple[str, ...],
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> SddCodexProcessResult:
        completed = subprocess.run(
            list(argv),
            cwd=cwd,
            env=env,
            timeout=timeout_seconds if timeout_seconds > 0 else None,
            text=True,
            capture_output=True,
            check=False,
            shell=False,
        )
        return SddCodexProcessResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


@dataclass(frozen=True, slots=True)
class SddCodexJob:
    id: str
    status: str
    process_state: str
    workspace_path: str
    job_root: str
    sandbox_root: str
    target_spec_id: str
    target_artifact: str | None
    context_pack_id: str
    command_argv: tuple[str, ...]
    redacted_argv: tuple[str, ...]
    env_keys: tuple[str, ...]
    intake_references: tuple[str, ...]
    media_persistence: dict[str, object]
    required_files: tuple[str, ...]
    blocked_reads: tuple[str, ...]
    routing_decisions: tuple[str, ...]
    logs: tuple[str, ...]
    stdout: str
    stderr: str
    exit_code: int | None
    timeout_seconds: int
    created_at_epoch: int
    started_at_epoch: int | None
    completed_at_epoch: int | None
    blocked_reasons: tuple[str, ...]
    next_actions: tuple[str, ...]
    retry_source_job_id: str | None = None

    def to_payload(self) -> dict[str, object]:
        activity = _job_activity(self)
        return {
            "kind": "codex.sddCodexJob",
            "version": 1,
            "job_id": self.id,
            "jobId": self.id,
            "status": self.status,
            "activity_state": activity["state"],
            "activity": activity,
            "process_state": self.process_state,
            "workspace_path": self.workspace_path,
            "job_root": self.job_root,
            "sandbox_root": self.sandbox_root,
            "target_spec_id": self.target_spec_id,
            "target_artifact": self.target_artifact,
            "context_pack_id": self.context_pack_id,
            "command_argv": list(self.command_argv),
            "redacted_argv": list(self.redacted_argv),
            "env_keys": list(self.env_keys),
            "intake_references": list(self.intake_references),
            "media_persistence": self.media_persistence,
            "required_files": list(self.required_files),
            "blocked_reads": list(self.blocked_reads),
            "routing_decisions": list(self.routing_decisions),
            "logs": list(self.logs),
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "timeout_seconds": self.timeout_seconds,
            "created_at_epoch": self.created_at_epoch,
            "started_at_epoch": self.started_at_epoch,
            "completed_at_epoch": self.completed_at_epoch,
            "blocked_reasons": list(self.blocked_reasons),
            "next_actions": list(self.next_actions),
            "retry_source_job_id": self.retry_source_job_id,
        }


@dataclass(frozen=True, slots=True)
class SddCodexJobRetryResult:
    kind: str
    version: int
    status: str
    original_job_id: str
    retry_job_id: str | None
    retry_eligible: bool
    copied_references: tuple[str, ...]
    blocked_reasons: tuple[str, ...]
    job: SddCodexJob | None
    next_actions: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        activity = _retry_activity(self)
        return {
            "kind": self.kind,
            "version": self.version,
            "status": self.status,
            "activity_state": activity["state"],
            "activity": activity,
            "original_job_id": self.original_job_id,
            "retry_job_id": self.retry_job_id,
            "retry_eligible": self.retry_eligible,
            "copied_references": list(self.copied_references),
            "blocked_reasons": list(self.blocked_reasons),
            "job": self.job.to_payload() if self.job is not None else None,
            "next_actions": list(self.next_actions),
        }


@dataclass(frozen=True, slots=True)
class SddCodexGeneratedChange:
    path: str
    change_type: str
    patch_path: str | None
    staged_path: str | None
    byte_size: int
    sha256: str | None
    blocked_reason: str | None
    protected_baseline: bool
    conflict: str | None

    def to_payload(self) -> dict[str, object]:
        return {
            "path": self.path,
            "change_type": self.change_type,
            "patch_path": self.patch_path,
            "staged_path": self.staged_path,
            "byte_size": self.byte_size,
            "sha256": self.sha256,
            "blocked_reason": self.blocked_reason,
            "protected_baseline": self.protected_baseline,
            "conflict": self.conflict,
        }


@dataclass(frozen=True, slots=True)
class SddCodexJobReview:
    kind: str
    version: int
    status: str
    job_id: str
    workspace_path: str
    job_root: str
    sandbox_root: str
    target_spec_id: str
    target_artifact: str | None
    changed_files: tuple[SddCodexGeneratedChange, ...]
    patch_references: tuple[str, ...]
    blocked_paths: tuple[str, ...]
    protected_baseline_impacts: tuple[str, ...]
    conflicts: tuple[str, ...]
    validation_status: str
    next_actions: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        activity = _review_activity(self)
        return {
            "kind": self.kind,
            "version": self.version,
            "status": self.status,
            "activity_state": activity["state"],
            "activity": activity,
            "job_id": self.job_id,
            "jobId": self.job_id,
            "workspace_path": self.workspace_path,
            "job_root": self.job_root,
            "sandbox_root": self.sandbox_root,
            "target_spec_id": self.target_spec_id,
            "target_artifact": self.target_artifact,
            "changed_files": [change.to_payload() for change in self.changed_files],
            "patch_references": list(self.patch_references),
            "blocked_paths": list(self.blocked_paths),
            "protected_baseline_impacts": list(self.protected_baseline_impacts),
            "conflicts": list(self.conflicts),
            "validation_status": self.validation_status,
            "next_actions": list(self.next_actions),
        }


@dataclass(frozen=True, slots=True)
class SddCodexJobApplyResult:
    kind: str
    version: int
    status: str
    job_id: str
    workspace_path: str
    target_spec_id: str
    target_artifact: str | None
    applied: tuple[str, ...]
    blocked: tuple[str, ...]
    conflicts: tuple[str, ...]
    post_apply_refresh: dict[str, object]
    review: SddCodexJobReview
    next_actions: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        activity = _apply_activity(self)
        return {
            "kind": self.kind,
            "version": self.version,
            "status": self.status,
            "activity_state": activity["state"],
            "activity": activity,
            "job_id": self.job_id,
            "jobId": self.job_id,
            "workspace_path": self.workspace_path,
            "target_spec_id": self.target_spec_id,
            "target_artifact": self.target_artifact,
            "applied": list(self.applied),
            "blocked": list(self.blocked),
            "conflicts": list(self.conflicts),
            "post_apply_refresh": self.post_apply_refresh,
            "review": self.review.to_payload(),
            "next_actions": list(self.next_actions),
        }


class SddCodexJobService:
    def __init__(
        self,
        *,
        projects_root: str | Path,
        codex_command: str = "codex",
        timeout_seconds: int = 0,
        workspace_aliases: dict[str, str] | None = None,
        standard_service: SddStandardService | None = None,
        context_pack_service: SddContextPackService | None = None,
        intake_service: SddIntakeService | None = None,
        metadata_refresh_service: SddMetadataRefreshService | None = None,
        index_service: SddIndexService | None = None,
        runner: SddCodexProcessRunner | None = None,
        env: dict[str, str] | None = None,
        max_active_jobs_per_workspace: int = 1,
    ) -> None:
        self._projects_root = Path(projects_root).expanduser().resolve()
        self._codex_command = codex_command
        self._timeout_seconds = timeout_seconds
        self._workspace_aliases = {
            key: Path(value).expanduser().resolve()
            for key, value in (workspace_aliases or {}).items()
            if key.strip() and str(value).strip()
        }
        self._standard_service = standard_service or SddStandardService()
        self._context_pack_service = context_pack_service or SddContextPackService()
        self._intake_service = intake_service or SddIntakeService(
            projects_root=self._projects_root,
            workspace_aliases={
                key: str(value) for key, value in self._workspace_aliases.items()
            },
        )
        self._metadata_refresh_service = (
            metadata_refresh_service
            or SddMetadataRefreshService(
                projects_root=self._projects_root,
                workspace_aliases={
                    key: str(value) for key, value in self._workspace_aliases.items()
                },
            )
        )
        self._index_service = index_service or SddIndexService()
        self._runner = runner or SubprocessCodexRunner()
        self._env_source = env if env is not None else dict(os.environ)
        self._max_active_jobs_per_workspace = max_active_jobs_per_workspace
        self._jobs: dict[str, SddCodexJob] = {}

    def preview_existing_spec_edit_job(
        self,
        *,
        request: SpecIntakeValidationInput,
        dry_run: SddSpecEditDryRunPlan,
    ) -> SddCodexJob:
        return self._build_existing_spec_edit_job(
            request=request,
            dry_run=dry_run,
            persist=False,
        )

    def start_existing_spec_edit_job(
        self,
        *,
        request: SpecIntakeValidationInput,
        dry_run: SddSpecEditDryRunPlan,
    ) -> SddCodexJob:
        job = self._build_existing_spec_edit_job(
            request=request,
            dry_run=dry_run,
            persist=True,
        )
        if job.status == "queued":
            self._jobs[job.id] = job
        return job

    def get_job(self, job_id: str) -> SddCodexJob | None:
        return self._jobs.get(job_id)

    def cancel_job(self, job_id: str) -> SddCodexJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if job.status in TERMINAL_STATUSES:
            return job
        updated = _replace_job(
            job,
            status="cancelled",
            process_state="cancelled",
            completed_at_epoch=_now(),
            logs=(*job.logs, "Job cancelled before safe completion."),
            next_actions=("Submit a new job when ready.",),
        )
        self._jobs[job_id] = updated
        return updated

    def retry_job(self, job_id: str) -> SddCodexJobRetryResult:
        original = self._jobs.get(job_id)
        if original is None:
            raise KeyError(job_id)
        if original.status not in RETRYABLE_STATUSES:
            return _blocked_retry(
                original,
                reason=f"Only failed, timed_out, or cancelled jobs can be retried; current status is {original.status}.",
            )
        workspace = self._validate_workspace(original.workspace_path)
        active = self._active_jobs_for_workspace(str(workspace))
        if active >= self._max_active_jobs_per_workspace:
            return _blocked_retry(
                original,
                reason="Another SDD Codex job is already active for this workspace.",
            )
        stale_reason = _retry_stale_reason(workspace=workspace, job=original)
        if stale_reason is not None:
            return _blocked_retry(original, reason=stale_reason)
        retry_job_id = _retry_job_id(original, tuple(self._jobs))
        retry_job_root = workspace / ".codex-bridge" / "sdd-jobs" / retry_job_id
        retry_sandbox_root = retry_job_root / "sandbox"
        prompt_path = retry_sandbox_root / ".codex-job" / "prompt.md"
        argv = _codex_argv(self._codex_command, prompt_path)
        copied_references = _write_retry_handoff(
            workspace=workspace,
            original=original,
            retry_job_root=retry_job_root,
            retry_sandbox_root=retry_sandbox_root,
            argv=argv,
        )
        retry_job = SddCodexJob(
            id=retry_job_id,
            status="queued",
            process_state="queued",
            workspace_path=str(workspace),
            job_root=retry_job_root.relative_to(workspace).as_posix(),
            sandbox_root=retry_sandbox_root.relative_to(workspace).as_posix(),
            target_spec_id=original.target_spec_id,
            target_artifact=original.target_artifact,
            context_pack_id=original.context_pack_id,
            command_argv=argv,
            redacted_argv=_redacted_argv(argv),
            env_keys=tuple(sorted(_filtered_env(self._env_source))),
            intake_references=original.intake_references,
            media_persistence=original.media_persistence,
            required_files=original.required_files,
            blocked_reads=original.blocked_reads,
            routing_decisions=(
                *original.routing_decisions,
                f"retry_of={original.id}",
            ),
            logs=(
                f"Retry job queued from terminal job {original.id}.",
                "Original sandbox was not reused; handoff was copied to a clean sandbox.",
            ),
            stdout="",
            stderr="",
            exit_code=None,
            timeout_seconds=original.timeout_seconds,
            created_at_epoch=_now(),
            started_at_epoch=None,
            completed_at_epoch=None,
            blocked_reasons=(),
            next_actions=(
                "Run the retry job, then review generated changes before apply.",
            ),
            retry_source_job_id=original.id,
        )
        self._jobs[retry_job.id] = retry_job
        return SddCodexJobRetryResult(
            kind="codex.sddCodexJobRetry",
            version=1,
            status="queued",
            original_job_id=original.id,
            retry_job_id=retry_job.id,
            retry_eligible=True,
            copied_references=copied_references,
            blocked_reasons=(),
            job=retry_job,
            next_actions=("Run the retry job when ready.",),
        )

    def run_job(self, job_id: str) -> SddCodexJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if job.status == "cancelled" or job.status in TERMINAL_STATUSES:
            return job
        if job.status != "queued":
            updated = _replace_job(
                job,
                status="blocked",
                process_state="blocked",
                blocked_reasons=("Only queued jobs can be run.",),
                completed_at_epoch=_now(),
            )
            self._jobs[job_id] = updated
            return updated
        running = _replace_job(
            job,
            status="running",
            process_state="running",
            started_at_epoch=_now(),
            logs=(*job.logs, "Codex CLI process started."),
        )
        self._jobs[job_id] = running
        try:
            result = self._runner.run(
                argv=running.command_argv,
                cwd=Path(running.workspace_path) / running.sandbox_root,
                env=_filtered_env(self._env_source),
                timeout_seconds=running.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            updated = _replace_job(
                running,
                status="timed_out",
                process_state="timed_out",
                stderr=str(exc),
                completed_at_epoch=_now(),
                logs=(*running.logs, "Codex CLI process timed out."),
                blocked_reasons=("Codex CLI process timed out.",),
                next_actions=(
                    "Review process logs and retry with a narrower request.",
                ),
            )
            self._jobs[job_id] = updated
            return updated
        except Exception as exc:
            updated = _replace_job(
                running,
                status="failed",
                process_state="failed",
                stderr=str(exc),
                completed_at_epoch=_now(),
                logs=(*running.logs, "Codex CLI process failed before completion."),
                blocked_reasons=(f"Codex CLI process failed: {exc}",),
                next_actions=("Fix the process failure before applying changes.",),
            )
            self._jobs[job_id] = updated
            return updated
        status = "completed" if result.returncode == 0 else "failed"
        updated = _replace_job(
            running,
            status=status,
            process_state=status,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.returncode,
            completed_at_epoch=_now(),
            logs=(
                *running.logs,
                "Codex CLI process completed."
                if result.returncode == 0
                else "Codex CLI process exited non-zero.",
            ),
            blocked_reasons=()
            if result.returncode == 0
            else (f"Codex CLI exited with code {result.returncode}.",),
            next_actions=(
                "Review generated changes before applying metadata refresh."
                if result.returncode == 0
                else "Review process stderr and retry after fixing the request.",
            ),
        )
        self._jobs[job_id] = updated
        return updated

    def review_job(self, job_id: str) -> SddCodexJobReview:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if job.status != "completed":
            return _blocked_review(
                job,
                reason="Only completed Codex jobs can be reviewed.",
            )
        return _review_job_changes(job)

    def apply_reviewed_job(self, job_id: str) -> SddCodexJobApplyResult:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        review = self.review_job(job_id)
        if review.status != "ready":
            return _blocked_apply(
                job,
                review,
                blocked=("Review is not ready for apply.",),
                conflicts=review.conflicts,
            )
        workspace = Path(job.workspace_path)
        originals: dict[Path, bytes | None] = {}
        applied: list[str] = []
        try:
            for change in review.changed_files:
                if change.path != job.target_artifact:
                    return _blocked_apply(
                        job,
                        review,
                        blocked=(
                            f"generated change outside target artifact: {change.path}",
                        ),
                        conflicts=(),
                    )
                if change.change_type not in {"created", "modified"}:
                    return _blocked_apply(
                        job,
                        review,
                        blocked=(
                            f"unsupported generated change type: {change.change_type}",
                        ),
                        conflicts=(),
                    )
                target_path = (workspace / change.path).resolve()
                staged_path = (workspace / job.sandbox_root / change.path).resolve()
                if not _is_relative_to(target_path, workspace):
                    return _blocked_apply(
                        job,
                        review,
                        blocked=(f"generated change escapes workspace: {change.path}",),
                        conflicts=(),
                    )
                if not _is_relative_to(staged_path, workspace / job.sandbox_root):
                    return _blocked_apply(
                        job,
                        review,
                        blocked=(f"staged change escapes sandbox: {change.path}",),
                        conflicts=(),
                    )
                originals[target_path] = (
                    target_path.read_bytes() if target_path.is_file() else None
                )
                _write_atomic_bytes(target_path, staged_path.read_bytes())
                applied.append(change.path)
            post_apply_refresh = self._post_apply_refresh(
                workspace,
                job.target_spec_id,
            )
        except Exception as exc:
            _restore_originals(originals)
            return _blocked_apply(
                job,
                review,
                blocked=(f"Apply failed without partial writes: {exc}",),
                conflicts=(),
            )
        updated_job = _replace_job(
            job,
            logs=(*job.logs, "Reviewed Codex output applied to target artifact."),
            next_actions=("Run SDD doctor and review the applied diff.",),
        )
        self._jobs[job_id] = updated_job
        return SddCodexJobApplyResult(
            kind="codex.sddCodexJobApply",
            version=1,
            status="applied",
            job_id=job.id,
            workspace_path=job.workspace_path,
            target_spec_id=job.target_spec_id,
            target_artifact=job.target_artifact,
            applied=tuple(applied),
            blocked=(),
            conflicts=(),
            post_apply_refresh=post_apply_refresh,
            review=review,
            next_actions=("Run SDD doctor and review the applied diff.",),
        )

    def _build_existing_spec_edit_job(
        self,
        *,
        request: SpecIntakeValidationInput,
        dry_run: SddSpecEditDryRunPlan,
        persist: bool,
    ) -> SddCodexJob:
        if dry_run.status != "dry-run":
            return _blocked_job(
                workspace_path=dry_run.workspace_path,
                spec_id=dry_run.spec_id,
                target_artifact=dry_run.selected_artifact,
                reason="Spec edit dry-run is blocked.",
            )
        workspace = self._validate_workspace(dry_run.workspace_path or "")
        active = self._active_jobs_for_workspace(str(workspace))
        if persist and active >= self._max_active_jobs_per_workspace:
            return _blocked_job(
                workspace_path=str(workspace),
                spec_id=dry_run.spec_id,
                target_artifact=dry_run.selected_artifact,
                reason="Another SDD Codex job is already active for this workspace.",
            )
        selected_artifact = _selected_artifact(dry_run)
        standard_id = _workspace_standard_id(workspace)
        standard = self._standard_service.load(standard_id)
        context_pack = self._context_pack_service.build_pack(
            workspace,
            standard=standard,
            preset="modify-existing-feature",
            selected_artifact=selected_artifact,
            query=_intake_text(request),
            auto_regenerate_indexes=True,
            allow_degraded=False,
        )
        if context_pack.status != "ready":
            return _blocked_job(
                workspace_path=str(workspace),
                spec_id=dry_run.spec_id,
                target_artifact=dry_run.selected_artifact,
                reason="Context pack is not ready: "
                + "; ".join(context_pack.routing_decisions),
            )
        job_id = _job_id(workspace, request, dry_run)
        job_root = workspace / ".codex-bridge" / "sdd-jobs" / job_id
        sandbox_root = job_root / "sandbox"
        prompt_path = sandbox_root / ".codex-job" / "prompt.md"
        argv = _codex_argv(self._codex_command, prompt_path)
        env = _filtered_env(self._env_source)
        media_persistence = None
        if persist:
            media_persistence = self._intake_service.persist_storage(
                request,
                job_id=job_id,
            )
            if media_persistence.status != "applied":
                return _blocked_job(
                    workspace_path=str(workspace),
                    spec_id=dry_run.spec_id,
                    target_artifact=dry_run.selected_artifact,
                    reason="Media persistence failed: "
                    + "; ".join(media_persistence.blocked),
                )
        job = SddCodexJob(
            id=job_id,
            status="queued",
            process_state="queued",
            workspace_path=str(workspace),
            job_root=job_root.relative_to(workspace).as_posix(),
            sandbox_root=sandbox_root.relative_to(workspace).as_posix(),
            target_spec_id=dry_run.spec_id or "",
            target_artifact=selected_artifact,
            context_pack_id=_context_pack_id(context_pack),
            command_argv=argv,
            redacted_argv=_redacted_argv(argv),
            env_keys=tuple(sorted(env)),
            intake_references=tuple(
                artifact.target_path for artifact in media_persistence.persisted
            )
            if media_persistence is not None
            else (),
            media_persistence=media_persistence.to_payload()
            if media_persistence is not None
            else {"status": "not_run"},
            required_files=context_pack.required_files,
            blocked_reads=context_pack.blocked_reads,
            routing_decisions=context_pack.routing_decisions,
            logs=("Job queued; deterministic intake handoff has been persisted.",),
            stdout="",
            stderr="",
            exit_code=None,
            timeout_seconds=self._timeout_seconds,
            created_at_epoch=_now(),
            started_at_epoch=None,
            completed_at_epoch=None,
            blocked_reasons=(),
            next_actions=("Run the queued Codex job, then review generated changes.",),
        )
        if persist:
            _write_job_handoff(
                workspace=workspace,
                job_root=job_root,
                request=request,
                dry_run=dry_run,
                context_pack=context_pack,
                argv=argv,
                media_persistence=media_persistence.to_payload()
                if media_persistence is not None
                else {"status": "not_run"},
                sandbox_root=sandbox_root,
            )
        return job

    def _post_apply_refresh(
        self,
        workspace: Path,
        spec_id: str,
    ) -> dict[str, object]:
        metadata = self._metadata_refresh_service.refresh_spec_metadata(
            workspace,
            spec_id,
        )
        standard = self._standard_service.load(_workspace_standard_id(workspace))
        index_status = self._index_service.ensure_indexes(
            workspace,
            standard=standard,
            auto_regenerate=True,
            allow_degraded=False,
        )
        return {
            "metadata_refresh": metadata.to_payload(),
            "index_status": {
                "state": index_status.state,
                "mode": index_status.mode,
                "generated": list(index_status.generated),
                "failed": list(index_status.failed),
                "detail": index_status.detail,
            },
        }

    def _active_jobs_for_workspace(self, workspace_path: str) -> int:
        return sum(
            1
            for job in self._jobs.values()
            if job.workspace_path == workspace_path
            and job.status not in TERMINAL_STATUSES
        )

    def _validate_workspace(self, workspace_path: str) -> Path:
        raw = workspace_path.strip()
        if not raw:
            raise ValueError("workspace_path is required.")
        alias_path = self._workspace_aliases.get(raw)
        candidate = alias_path if alias_path is not None else Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = self._projects_root / candidate
        resolved = candidate.resolve()
        if not _is_relative_to(resolved, self._projects_root) and not any(
            resolved == alias for alias in self._workspace_aliases.values()
        ):
            raise ValueError(
                "workspace_path must resolve under PROJECTS_ROOT or a known alias."
            )
        if not resolved.is_dir():
            raise ValueError("workspace_path must point to a directory.")
        return resolved


def _blocked_retry(job: SddCodexJob, *, reason: str) -> SddCodexJobRetryResult:
    return SddCodexJobRetryResult(
        kind="codex.sddCodexJobRetry",
        version=1,
        status="blocked",
        original_job_id=job.id,
        retry_job_id=None,
        retry_eligible=False,
        copied_references=(),
        blocked_reasons=(reason,),
        job=None,
        next_actions=("Create a new edit request when retry is not eligible.",),
    )


def _retry_stale_reason(*, workspace: Path, job: SddCodexJob) -> str | None:
    job_root = workspace / job.job_root
    base = _read_json(job_root / "base-manifest.json")
    selected = str(base.get("selected_artifact") or job.target_artifact or "")
    if not selected:
        return "Retry is blocked because the original target artifact is missing."
    target_path = (workspace / selected).resolve()
    if not _is_relative_to(target_path, workspace):
        return f"Retry is blocked because target artifact escapes workspace: {selected}"
    files = base.get("files")
    if not isinstance(files, dict):
        return "Retry is blocked because the original base manifest is missing file digests."
    entry = files.get(selected)
    if not isinstance(entry, dict):
        return (
            f"Retry is blocked because the original base digest is missing: {selected}"
        )
    existed = bool(entry.get("exists"))
    expected_digest = (
        entry.get("sha256") if isinstance(entry.get("sha256"), str) else None
    )
    if existed and not target_path.is_file():
        return f"Retry is blocked because target artifact changed since original job: {selected}"
    if not existed and target_path.exists():
        return f"Retry is blocked because target artifact appeared since original job: {selected}"
    if existed and _file_sha256(target_path) != expected_digest:
        return f"Retry is blocked because target artifact changed since original job: {selected}"
    return None


def _retry_job_id(original: SddCodexJob, existing_ids: tuple[str, ...]) -> str:
    base = f"{original.id}-retry"
    attempt = 1
    existing = set(existing_ids)
    while f"{base}-{attempt:02d}" in existing:
        attempt += 1
    return f"{base}-{attempt:02d}"


def _write_retry_handoff(
    *,
    workspace: Path,
    original: SddCodexJob,
    retry_job_root: Path,
    retry_sandbox_root: Path,
    argv: tuple[str, ...],
) -> tuple[str, ...]:
    original_job_root = workspace / original.job_root
    if not _is_relative_to(retry_job_root.resolve(), workspace):
        raise ValueError("retry job root escapes workspace.")
    if not _is_relative_to(retry_sandbox_root.resolve(), retry_job_root.resolve()):
        raise ValueError("retry sandbox root escapes job root.")
    if retry_job_root.exists():
        shutil.rmtree(retry_job_root)
    retry_job_root.mkdir(parents=True, exist_ok=False)
    retry_sandbox_root.mkdir(parents=True, exist_ok=False)

    context_payload = _read_json(original_job_root / "context-pack.json")
    request_payload = _read_json(original_job_root / "request.json")
    base_manifest = _read_json(original_job_root / "base-manifest.json")
    paths = {
        "codex-bridge.yaml",
        ".specify/memory/constitution.md",
        ".sdd",
        f"specs/{original.target_spec_id}",
        original.target_artifact or "",
    }
    paths.update(original.required_files)
    paths.update(_candidate_paths_from_payload(context_payload, "related_specs"))
    paths.update(_candidate_paths_from_payload(context_payload, "related_diagrams"))
    paths.update(original.intake_references)
    for relative_path in sorted(path for path in paths if path):
        _copy_relative_path(workspace, retry_sandbox_root, relative_path)

    copied = (
        "request.json",
        "context-pack.json",
        "prompt.md",
        "command.json",
        "base-manifest.json",
    )
    prompt = _prompt_text(
        request_payload=request_payload,
        context_payload=context_payload,
    )
    _write_json(retry_job_root / "request.json", request_payload)
    _write_json(retry_job_root / "context-pack.json", context_payload)
    _write_text(retry_job_root / "prompt.md", prompt)
    _write_json(retry_job_root / "command.json", {"argv": list(argv)})
    _write_json(retry_job_root / "base-manifest.json", base_manifest)
    handoff_root = retry_sandbox_root / ".codex-job"
    _write_json(handoff_root / "request.json", request_payload)
    _write_json(handoff_root / "context-pack.json", context_payload)
    _write_text(handoff_root / "prompt.md", prompt)
    _write_json(handoff_root / "command.json", {"argv": list(argv)})
    return copied


def _candidate_paths_from_payload(
    context_payload: dict[str, object], key: str
) -> tuple[str, ...]:
    raw = context_payload.get(key)
    if not isinstance(raw, list):
        return ()
    paths: list[str] = []
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            paths.append(item["path"])
    return tuple(paths)


def _write_job_handoff(
    *,
    workspace: Path,
    job_root: Path,
    sandbox_root: Path,
    request: SpecIntakeValidationInput,
    dry_run: SddSpecEditDryRunPlan,
    context_pack: SddContextPack,
    argv: tuple[str, ...],
    media_persistence: dict[str, object],
) -> None:
    if not _is_relative_to(job_root.resolve(), workspace):
        raise ValueError("job root escapes workspace.")
    if not _is_relative_to(sandbox_root.resolve(), job_root.resolve()):
        raise ValueError("sandbox root escapes job root.")
    job_root.mkdir(parents=True, exist_ok=True)
    _prepare_sandbox_workspace(
        workspace=workspace,
        sandbox_root=sandbox_root,
        dry_run=dry_run,
        context_pack=context_pack,
        media_persistence=media_persistence,
    )
    request_payload = {
        "workspace_path": ".",
        "target_workspace_path": "<isolated>",
        "spec_target": {
            "mode": request.spec_target.mode,
            "spec_id": request.spec_target.spec_id,
            "artifact": request.spec_target.artifact,
        },
        "title_seed": request.title_seed,
        "intake_items": [
            {
                "kind": item.kind,
                "text": item.text,
                "transcript": item.transcript,
                "source_ref": item.source_ref,
                "payload_ref": item.payload_ref,
                "references": list(item.references),
            }
            for item in request.intake_items
        ],
        "dry_run": dry_run.to_payload(),
        "media_persistence": media_persistence,
    }
    context_payload = {
        "preset": context_pack.preset,
        "status": context_pack.status,
        "index_status": context_pack.index_status,
        "required_files": list(context_pack.required_files),
        "related_specs": [
            _candidate_payload(candidate) for candidate in context_pack.related_specs
        ],
        "related_diagrams": [
            _candidate_payload(candidate) for candidate in context_pack.related_diagrams
        ],
        "blocked_reads": list(context_pack.blocked_reads),
        "routing_decisions": list(context_pack.routing_decisions),
    }
    _write_json(job_root / "request.json", request_payload)
    _write_json(job_root / "context-pack.json", context_payload)
    _write_text(
        job_root / "prompt.md",
        _prompt_text(request_payload=request_payload, context_payload=context_payload),
    )
    _write_json(job_root / "command.json", {"argv": list(argv)})
    _write_json(
        job_root / "base-manifest.json",
        _base_manifest(workspace=workspace, dry_run=dry_run),
    )
    handoff_root = sandbox_root / ".codex-job"
    _write_json(handoff_root / "request.json", request_payload)
    _write_json(handoff_root / "context-pack.json", context_payload)
    _write_text(
        handoff_root / "prompt.md",
        _prompt_text(request_payload=request_payload, context_payload=context_payload),
    )
    _write_json(handoff_root / "command.json", {"argv": list(argv)})


def _prompt_text(
    *,
    request_payload: dict[str, object],
    context_payload: dict[str, object],
) -> str:
    return (
        "# Workbench SCM Existing Spec Edit\n\n"
        "Use the provided request and context-pack files. Do not read every spec. "
        "Work only inside this isolated sandbox. Do not write to the original "
        "repository path. Generated changes will be reviewed and applied by "
        "Workbench after validation.\n\n"
        "## Request\n\n"
        f"```json\n{json.dumps(request_payload, indent=2, sort_keys=True)}\n```\n\n"
        "## Context Pack\n\n"
        f"```json\n{json.dumps(context_payload, indent=2, sort_keys=True)}\n```\n"
    )


def _prepare_sandbox_workspace(
    *,
    workspace: Path,
    sandbox_root: Path,
    dry_run: SddSpecEditDryRunPlan,
    context_pack: SddContextPack,
    media_persistence: dict[str, object],
) -> None:
    if sandbox_root.exists():
        shutil.rmtree(sandbox_root)
    sandbox_root.mkdir(parents=True, exist_ok=False)
    paths = {
        "codex-bridge.yaml",
        dry_run.spec_root or "",
        dry_run.selected_artifact or "",
        ".specify/memory/constitution.md",
        ".sdd",
    }
    paths.update(context_pack.required_files)
    paths.update(str(candidate.path) for candidate in context_pack.related_specs)
    paths.update(str(candidate.path) for candidate in context_pack.related_diagrams)
    for reference in _persisted_intake_references(media_persistence):
        paths.add(reference)
    for relative_path in sorted(path for path in paths if path):
        _copy_relative_path(workspace, sandbox_root, relative_path)


def _copy_relative_path(
    workspace: Path, sandbox_root: Path, relative_path: str
) -> None:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        return
    source = (workspace / relative).resolve()
    if not _is_relative_to(source, workspace) or not source.exists():
        return
    target = sandbox_root / relative
    if source.is_symlink():
        return
    if source.is_dir():
        for file_path in source.rglob("*"):
            if not file_path.is_file() or file_path.is_symlink():
                continue
            resolved = file_path.resolve()
            if not _is_relative_to(resolved, workspace):
                continue
            destination = sandbox_root / resolved.relative_to(workspace)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(resolved, destination)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _persisted_intake_references(
    media_persistence: dict[str, object],
) -> tuple[str, ...]:
    persisted = media_persistence.get("persisted")
    if not isinstance(persisted, list):
        return ()
    references: list[str] = []
    for item in persisted:
        if isinstance(item, dict) and isinstance(item.get("target_path"), str):
            references.append(item["target_path"])
    return tuple(references)


def _base_manifest(
    *,
    workspace: Path,
    dry_run: SddSpecEditDryRunPlan,
) -> dict[str, object]:
    selected = _selected_artifact(dry_run)
    files: dict[str, object] = {}
    if selected:
        path = workspace / selected
        files[selected] = {
            "exists": path.is_file(),
            "sha256": _file_sha256(path) if path.is_file() else None,
        }
    return {
        "selected_artifact": selected,
        "files": files,
    }


def _review_job_changes(job: SddCodexJob) -> SddCodexJobReview:
    workspace = Path(job.workspace_path)
    job_root = workspace / job.job_root
    sandbox_root = workspace / job.sandbox_root
    if not sandbox_root.is_dir():
        return _blocked_review(job, reason="Job sandbox is missing.")
    review_root = job_root / "review"
    patch_root = review_root / "patches"
    if patch_root.exists():
        shutil.rmtree(patch_root)
    patch_root.mkdir(parents=True, exist_ok=True)
    changes = _collect_generated_changes(
        workspace=workspace,
        sandbox_root=sandbox_root,
        job_root=job_root,
        patch_root=patch_root,
        target_artifact=job.target_artifact,
    )
    blocked_paths = tuple(
        change.path for change in changes if change.blocked_reason is not None
    )
    protected = tuple(change.path for change in changes if change.protected_baseline)
    conflicts = tuple(change.conflict for change in changes if change.conflict)
    patches = tuple(
        change.patch_path for change in changes if change.patch_path is not None
    )
    if not changes:
        status = "no_changes"
        validation_status = "no_changes"
        next_actions = ("No generated changes were found in the isolated sandbox.",)
    elif blocked_paths or conflicts:
        status = "blocked"
        validation_status = "fail"
        next_actions = ("Resolve blocked generated paths or conflicts before apply.",)
    else:
        status = "ready"
        validation_status = "pass"
        next_actions = ("Apply reviewed generated changes when ready.",)
    return SddCodexJobReview(
        kind="codex.sddCodexJobReview",
        version=1,
        status=status,
        job_id=job.id,
        workspace_path=job.workspace_path,
        job_root=job.job_root,
        sandbox_root=job.sandbox_root,
        target_spec_id=job.target_spec_id,
        target_artifact=job.target_artifact,
        changed_files=changes,
        patch_references=patches,
        blocked_paths=blocked_paths,
        protected_baseline_impacts=protected,
        conflicts=conflicts,
        validation_status=validation_status,
        next_actions=next_actions,
    )


def _collect_generated_changes(
    *,
    workspace: Path,
    sandbox_root: Path,
    job_root: Path,
    patch_root: Path,
    target_artifact: str | None,
) -> tuple[SddCodexGeneratedChange, ...]:
    paths: set[str] = set()
    for file_path in sandbox_root.rglob("*"):
        if not file_path.is_file():
            continue
        relative = file_path.relative_to(sandbox_root)
        if relative.parts and relative.parts[0] == ".codex-job":
            continue
        paths.add(relative.as_posix())
    base = _read_json(job_root / "base-manifest.json")
    selected = str(base.get("selected_artifact") or target_artifact or "")
    if (
        selected
        and _base_file_exists(base, selected)
        and not (sandbox_root / selected).is_file()
    ):
        paths.add(selected)
    changes: list[SddCodexGeneratedChange] = []
    for relative_path in sorted(paths):
        sandbox_path = sandbox_root / relative_path
        target_path = workspace / relative_path
        target_exists = target_path.is_file()
        sandbox_exists = sandbox_path.is_file()
        if (
            sandbox_exists
            and target_exists
            and sandbox_path.read_bytes() == target_path.read_bytes()
        ):
            continue
        change_type = (
            "deleted"
            if not sandbox_exists
            else "created"
            if not target_exists
            else "modified"
        )
        protected = _is_protected_baseline(relative_path)
        blocked_reason = _blocked_change_reason(
            relative_path,
            target_artifact=target_artifact,
            change_type=change_type,
            protected=protected,
        )
        conflict = _change_conflict(
            workspace=workspace,
            base=base,
            relative_path=relative_path,
            target_artifact=target_artifact,
        )
        patch_path = _write_patch_file(
            workspace=workspace,
            sandbox_root=sandbox_root,
            patch_root=patch_root,
            relative_path=relative_path,
            change_type=change_type,
        )
        staged_path = (
            sandbox_path.relative_to(workspace).as_posix() if sandbox_exists else None
        )
        changes.append(
            SddCodexGeneratedChange(
                path=relative_path,
                change_type=change_type,
                patch_path=patch_path,
                staged_path=staged_path,
                byte_size=sandbox_path.stat().st_size if sandbox_exists else 0,
                sha256=_file_sha256(sandbox_path) if sandbox_exists else None,
                blocked_reason=blocked_reason,
                protected_baseline=protected,
                conflict=conflict,
            )
        )
    return tuple(changes)


def _blocked_change_reason(
    relative_path: str,
    *,
    target_artifact: str | None,
    change_type: str,
    protected: bool,
) -> str | None:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        return "generated path is unsafe."
    if protected:
        return "generated path targets a protected baseline artifact."
    if change_type == "deleted":
        return "generated deletions are not supported by reviewed apply."
    if not target_artifact or relative_path != target_artifact:
        return "generated path is outside the selected target artifact."
    return None


def _change_conflict(
    *,
    workspace: Path,
    base: dict[str, object],
    relative_path: str,
    target_artifact: str | None,
) -> str | None:
    if relative_path != target_artifact:
        return None
    files = base.get("files")
    if not isinstance(files, dict):
        return "base manifest is missing."
    entry = files.get(relative_path)
    if not isinstance(entry, dict):
        return "base digest is missing."
    target_path = workspace / relative_path
    existed = bool(entry.get("exists"))
    expected_digest = (
        entry.get("sha256") if isinstance(entry.get("sha256"), str) else None
    )
    if existed and not target_path.is_file():
        return f"target artifact changed since job started: {relative_path}"
    if not existed and target_path.exists():
        return f"target artifact appeared since job started: {relative_path}"
    if existed and _file_sha256(target_path) != expected_digest:
        return f"target artifact changed since job started: {relative_path}"
    return None


def _write_patch_file(
    *,
    workspace: Path,
    sandbox_root: Path,
    patch_root: Path,
    relative_path: str,
    change_type: str,
) -> str:
    target_path = workspace / relative_path
    sandbox_path = sandbox_root / relative_path
    old_text = _read_text_for_diff(target_path) if target_path.is_file() else ""
    new_text = _read_text_for_diff(sandbox_path) if sandbox_path.is_file() else ""
    if old_text is None or new_text is None:
        diff = (
            f"Binary or non-UTF-8 generated change: {relative_path} ({change_type}).\n"
        )
    else:
        diff = "".join(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"a/{relative_path}",
                tofile=f"b/{relative_path}",
            )
        )
    patch_path = patch_root / (_safe_patch_name(relative_path) + ".diff")
    _write_text(patch_path, diff)
    return patch_path.relative_to(workspace).as_posix()


def _blocked_review(job: SddCodexJob, *, reason: str) -> SddCodexJobReview:
    return SddCodexJobReview(
        kind="codex.sddCodexJobReview",
        version=1,
        status="blocked",
        job_id=job.id,
        workspace_path=job.workspace_path,
        job_root=job.job_root,
        sandbox_root=job.sandbox_root,
        target_spec_id=job.target_spec_id,
        target_artifact=job.target_artifact,
        changed_files=(),
        patch_references=(),
        blocked_paths=(),
        protected_baseline_impacts=(),
        conflicts=(),
        validation_status="not_run",
        next_actions=(reason,),
    )


def _blocked_apply(
    job: SddCodexJob,
    review: SddCodexJobReview,
    *,
    blocked: tuple[str, ...],
    conflicts: tuple[str, ...],
) -> SddCodexJobApplyResult:
    return SddCodexJobApplyResult(
        kind="codex.sddCodexJobApply",
        version=1,
        status="blocked",
        job_id=job.id,
        workspace_path=job.workspace_path,
        target_spec_id=job.target_spec_id,
        target_artifact=job.target_artifact,
        applied=(),
        blocked=blocked,
        conflicts=conflicts,
        post_apply_refresh={"status": "not_run"},
        review=review,
        next_actions=("Resolve review/apply blockers before retrying.",),
    )


def _write_json(path: Path, payload: dict[str, object]) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temp_path.open("xb") as handle:
            handle.write(content)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _restore_originals(originals: dict[Path, bytes | None]) -> None:
    for path, content in originals.items():
        if content is None:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            continue
        _write_atomic_bytes(path, content)


def _read_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _base_file_exists(base: dict[str, object], relative_path: str) -> bool:
    files = base.get("files")
    if not isinstance(files, dict):
        return False
    entry = files.get(relative_path)
    return isinstance(entry, dict) and bool(entry.get("exists"))


def _is_protected_baseline(relative_path: str) -> bool:
    return (
        relative_path.startswith("architecture/")
        or relative_path == ".specify/memory/constitution.md"
        or relative_path == "codex-bridge.yaml"
    )


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _read_text_for_diff(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _safe_patch_name(relative_path: str) -> str:
    return relative_path.replace("/", "__").replace("\\", "__")


def _blocked_job(
    *,
    workspace_path: str | None,
    spec_id: str | None,
    target_artifact: str | None,
    reason: str,
) -> SddCodexJob:
    now = _now()
    return SddCodexJob(
        id="",
        status="blocked",
        process_state="blocked",
        workspace_path=workspace_path or "",
        job_root="",
        sandbox_root="",
        target_spec_id=spec_id or "",
        target_artifact=target_artifact,
        context_pack_id="",
        command_argv=(),
        redacted_argv=(),
        env_keys=(),
        intake_references=(),
        media_persistence={"status": "not_run"},
        required_files=(),
        blocked_reads=(),
        routing_decisions=(),
        logs=(),
        stdout="",
        stderr="",
        exit_code=None,
        timeout_seconds=0,
        created_at_epoch=now,
        started_at_epoch=None,
        completed_at_epoch=now,
        blocked_reasons=(reason,),
        next_actions=("Fix blockers before creating a Codex job.",),
    )


def _codex_argv(codex_command: str, prompt_path: Path) -> tuple[str, ...]:
    parts = tuple(part for part in shlex.split(codex_command) if part)
    if not parts:
        raise ValueError("codex_command is required.")
    return (
        *parts,
        "exec",
        "--skip-git-repo-check",
        "--color",
        "never",
        "--input",
        str(prompt_path),
    )


def _filtered_env(source: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in source.items() if key in ALLOWED_ENV_KEYS}


def _redacted_argv(argv: tuple[str, ...]) -> tuple[str, ...]:
    redacted: list[str] = []
    skip_next = False
    for item in argv:
        if skip_next:
            redacted.append("<redacted>")
            skip_next = False
            continue
        redacted.append(item)
        if item in {"--api-key", "--token"}:
            skip_next = True
    return tuple(redacted)


def _job_activity(job: SddCodexJob) -> dict[str, object]:
    events: list[dict[str, object]] = [
        _activity_event(
            "received",
            "completed",
            "Request received",
            job.created_at_epoch,
            "Spec edit request accepted by Workbench.",
        )
    ]
    if job.retry_source_job_id is not None:
        events.append(
            _activity_event(
                "retry-created",
                "completed",
                "Retry job created",
                job.created_at_epoch,
                f"Created from terminal job {job.retry_source_job_id}; original sandbox was not reused.",
            )
        )
    media_status = str(job.media_persistence.get("status", "not_run"))
    if media_status == "applied":
        events.append(
            _activity_event(
                "media-consumed",
                "completed",
                "Media consumed",
                job.created_at_epoch,
                "Intake media was persisted for the target spec/job handoff.",
            )
        )
    elif media_status == "blocked":
        events.append(
            _activity_event(
                "processing-media",
                "blocked",
                "Media blocked",
                job.created_at_epoch,
                "Media persistence blocked before Codex execution.",
            )
        )
    events.append(
        _activity_event(
            "preparing-context",
            "completed",
            "Context prepared",
            job.created_at_epoch,
            "Context pack resolved from indexes.",
        )
    )
    events.append(
        _activity_event(
            "queued",
            "completed" if job.status != "queued" else "active",
            "Job queued",
            job.created_at_epoch,
            "Codex job is queued in the sandbox.",
        )
    )
    if job.started_at_epoch is not None:
        events.append(
            _activity_event(
                "running-codex",
                "completed" if job.status in TERMINAL_STATUSES else "active",
                "Codex running",
                job.started_at_epoch,
                "Codex CLI is running in the isolated sandbox.",
            )
        )
    if job.status == "completed":
        events.append(
            _activity_event(
                "ready",
                "active",
                "Review required",
                job.completed_at_epoch,
                "Generated output is ready for explicit review; nothing has been applied.",
            )
        )
    elif job.status in {"failed", "timed_out", "cancelled", "blocked"}:
        events.append(
            _activity_event(
                job.status,
                "blocked" if job.status == "blocked" else "failed",
                job.status.replace("_", " ").title(),
                job.completed_at_epoch,
                "; ".join(job.blocked_reasons) or job.stderr or job.status,
            )
        )
    state = _activity_state_from_events(events)
    return {
        "kind": "codex.sddActivity",
        "version": 1,
        "state": state,
        "job_id": job.id,
        "events": events,
        "next_actions": list(job.next_actions),
    }


def _review_activity(review: SddCodexJobReview) -> dict[str, object]:
    state = "review-ready" if review.status == "ready" else "blocked"
    event_status = "active" if review.status == "ready" else "blocked"
    detail = (
        "Generated output is review-ready; explicit apply is still required."
        if review.status == "ready"
        else "; ".join((*review.blocked_paths, *review.conflicts))
        or "Review is blocked."
    )
    return {
        "kind": "codex.sddActivity",
        "version": 1,
        "state": state,
        "job_id": review.job_id,
        "events": [
            _activity_event(
                "review-ready" if review.status == "ready" else "review-blocked",
                event_status,
                "Review ready" if review.status == "ready" else "Review blocked",
                None,
                detail,
            )
        ],
        "next_actions": list(review.next_actions),
    }


def _apply_activity(result: SddCodexJobApplyResult) -> dict[str, object]:
    status = "completed" if result.status == "applied" else "blocked"
    events = [
        _activity_event(
            "applying-changes",
            status,
            "Applying reviewed changes",
            None,
            "Only reviewed generated output is eligible for apply.",
        )
    ]
    if result.status == "applied":
        events.append(
            _activity_event(
                "refreshing-metadata",
                "completed",
                "Metadata refreshed",
                None,
                "Metadata and indexes refreshed after reviewed apply.",
            )
        )
        events.append(
            _activity_event(
                "reviewed-apply-completed",
                "completed",
                "Reviewed apply completed",
                None,
                ", ".join(result.applied),
            )
        )
    else:
        events.append(
            _activity_event(
                "reviewed-apply-blocked",
                "blocked",
                "Reviewed apply blocked",
                None,
                "; ".join((*result.blocked, *result.conflicts)),
            )
        )
    return {
        "kind": "codex.sddActivity",
        "version": 1,
        "state": "applied" if result.status == "applied" else "blocked",
        "job_id": result.job_id,
        "events": events,
        "next_actions": list(result.next_actions),
    }


def _retry_activity(result: SddCodexJobRetryResult) -> dict[str, object]:
    if result.status == "queued":
        events = [
            _activity_event(
                "retry-created",
                "completed",
                "Retry job created",
                None,
                f"Retry job {result.retry_job_id} was created from {result.original_job_id}.",
            ),
            _activity_event(
                "queued",
                "active",
                "Retry queued",
                None,
                "Run the retry job, then review generated changes before apply.",
            ),
        ]
        state = "queued"
    else:
        events = [
            _activity_event(
                "retry-blocked",
                "blocked",
                "Retry blocked",
                None,
                "; ".join(result.blocked_reasons),
            )
        ]
        state = "blocked"
    return {
        "kind": "codex.sddActivity",
        "version": 1,
        "state": state,
        "job_id": result.retry_job_id or result.original_job_id,
        "events": events,
        "next_actions": list(result.next_actions),
    }


def _activity_event(
    state: str,
    status: str,
    label: str,
    epoch: int | None,
    detail: str,
) -> dict[str, object]:
    return {
        "state": state,
        "status": status,
        "label": label,
        "epoch": epoch,
        "detail": detail,
    }


def _activity_state_from_events(events: list[dict[str, object]]) -> str:
    if not events:
        return "received"
    last = str(events[-1]["state"])
    return last


def _replace_job(job: SddCodexJob, **changes: object) -> SddCodexJob:
    payload = job.to_payload()
    payload.update(changes)
    return SddCodexJob(
        id=str(payload["job_id"]),
        status=str(payload["status"]),
        process_state=str(payload["process_state"]),
        workspace_path=str(payload["workspace_path"]),
        job_root=str(payload["job_root"]),
        sandbox_root=str(payload["sandbox_root"]),
        target_spec_id=str(payload["target_spec_id"]),
        target_artifact=payload["target_artifact"]
        if isinstance(payload["target_artifact"], str)
        else None,
        context_pack_id=str(payload["context_pack_id"]),
        command_argv=tuple(str(item) for item in payload["command_argv"]),
        redacted_argv=tuple(str(item) for item in payload["redacted_argv"]),
        env_keys=tuple(str(item) for item in payload["env_keys"]),
        intake_references=tuple(str(item) for item in payload["intake_references"]),
        media_persistence=payload["media_persistence"]
        if isinstance(payload["media_persistence"], dict)
        else {},
        required_files=tuple(str(item) for item in payload["required_files"]),
        blocked_reads=tuple(str(item) for item in payload["blocked_reads"]),
        routing_decisions=tuple(str(item) for item in payload["routing_decisions"]),
        logs=tuple(str(item) for item in payload["logs"]),
        stdout=str(payload["stdout"]),
        stderr=str(payload["stderr"]),
        exit_code=payload["exit_code"]
        if isinstance(payload["exit_code"], int)
        else None,
        timeout_seconds=int(payload["timeout_seconds"]),
        created_at_epoch=int(payload["created_at_epoch"]),
        started_at_epoch=payload["started_at_epoch"]
        if isinstance(payload["started_at_epoch"], int)
        else None,
        completed_at_epoch=payload["completed_at_epoch"]
        if isinstance(payload["completed_at_epoch"], int)
        else None,
        blocked_reasons=tuple(str(item) for item in payload["blocked_reasons"]),
        next_actions=tuple(str(item) for item in payload["next_actions"]),
        retry_source_job_id=str(payload["retry_source_job_id"])
        if isinstance(payload.get("retry_source_job_id"), str)
        else None,
    )


def _selected_artifact(dry_run: SddSpecEditDryRunPlan) -> str:
    for artifact in dry_run.intended_artifact_updates:
        if not artifact.endswith("metadata.yaml"):
            return artifact
    return dry_run.spec_root + "/spec.md" if dry_run.spec_root else ""


def _workspace_standard_id(workspace: Path) -> str:
    manifest_path = workspace / "codex-bridge.yaml"
    if not manifest_path.is_file():
        return DEFAULT_STANDARD_ID
    payload = parse_simple_yaml(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return DEFAULT_STANDARD_ID
    sdd = payload.get("sdd")
    if not isinstance(sdd, dict):
        return DEFAULT_STANDARD_ID
    return str(sdd.get("standard") or DEFAULT_STANDARD_ID)


def _context_pack_id(context_pack: SddContextPack) -> str:
    payload = {
        "preset": context_pack.preset,
        "required_files": context_pack.required_files,
        "related_specs": [
            _candidate_payload(candidate) for candidate in context_pack.related_specs
        ],
        "related_diagrams": [
            _candidate_payload(candidate) for candidate in context_pack.related_diagrams
        ],
    }
    return (
        "ctx-" + sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    )


def _candidate_payload(candidate: object) -> dict[str, object]:
    return {
        "path": getattr(candidate, "path"),
        "reason": getattr(candidate, "reason"),
        "rank": getattr(candidate, "rank"),
    }


def _job_id(
    workspace: Path,
    request: SpecIntakeValidationInput,
    dry_run: SddSpecEditDryRunPlan,
) -> str:
    payload = {
        "workspace": str(workspace),
        "spec_id": dry_run.spec_id,
        "artifact": dry_run.selected_artifact,
        "intake": _intake_text(request),
    }
    return (
        "sddjob-"
        + sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    )


def _intake_text(request: SpecIntakeValidationInput) -> str:
    return "\n".join(
        value
        for item in request.intake_items
        for value in (item.text or item.transcript or "",)
        if value.strip()
    )


def _now() -> int:
    return int(time.time())


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
