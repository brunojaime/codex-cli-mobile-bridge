from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
from secrets import token_urlsafe
import shlex
import shutil
import signal
import subprocess
from threading import RLock
from typing import Protocol
from urllib.parse import urlparse
from uuid import uuid4

import yaml

from backend.app.application.services.cloudflare_preview_service import (
    CloudflareClient,
    CloudflarePreviewDoctorService,
)
from backend.app.application.services.project_factory_generator_service import (
    ProjectFactoryGeneratorError,
    ProjectFactoryGeneratorService,
)
from backend.app.application.services.project_factory_job_runner import (
    _MAX_AUTOMATIC_UX_ITERATIONS,
    _codex_argv,
    _load_visual_ux_skill_context,
    _ux_iteration_prompt_path,
    _ux_reviewer_is_complete,
    _write_ux_evidence_index,
    ProjectFactoryUxSkillUnavailableError,
)
from backend.app.application.services.project_factory_manifest_service import (
    FRONTEND_STRATEGIES,
    ProjectFactoryManifestInput,
    ProjectFactoryManifestService,
)
from backend.app.application.services.web_preview_deploy_service import (
    WebPreviewDeployInput,
    WebPreviewDeployService,
    WebPreviewError,
    WebPreviewPlanInput,
)
from backend.app.application.services.web_preview_invite_service import (
    WebPreviewInviteCreateInput,
    WebPreviewInviteError,
    WebPreviewInviteService,
)
from backend.app.domain.entities.project_factory_init import (
    INIT_PHASE_ORDER,
    ProjectFactoryInitArtifact,
    ProjectFactoryInitBlocker,
    ProjectFactoryInitCommandEvidence,
    ProjectFactoryInitCompletionState,
    ProjectFactoryInitContextPack,
    ProjectFactoryInitJob,
    ProjectFactoryInitPhase,
    ProjectFactoryInitPhaseName,
    ProjectFactoryInitPhaseStatus,
    ProjectFactoryInitRelationships,
    ProjectFactoryInitRemoteResource,
    ProjectFactoryInitRemoteResourceType,
    _phases_in_current_order,
)
from backend.app.domain.entities.agent_configuration import (
    AgentId,
    AgentTriggerSource,
    AgentType,
    AgentVisibilityMode,
)
from backend.app.domain.entities.chat_message import (
    ChatMessage,
    ChatMessageAuthorType,
    ChatMessageRole,
    ChatMessageStatus,
)
from backend.app.domain.repositories.chat_repository import ChatRepository
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.network.tailscale import detect_tailscale_info

INIT_PHASES: tuple[str, ...] = tuple(phase.value for phase in INIT_PHASE_ORDER)
_GITHUB_PHASE = ProjectFactoryInitPhaseName.GITHUB_REPOSITORY
_TERMINAL_ACTIVE_STATES = {
    ProjectFactoryInitCompletionState.READY,
    ProjectFactoryInitCompletionState.BLOCKED_WITH_CONTEXT,
    ProjectFactoryInitCompletionState.FAILED,
    ProjectFactoryInitCompletionState.CANCELLED,
}
_VERIFIED_FOUNDATION_TASK_IDS = frozenset({"plan-1-task-10", "plan-1-task-11"})
_SENSITIVE_ENV_KEYS = frozenset(
    {
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "GITHUB_PAT",
        "GITHUB_APP_PRIVATE_KEY",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_DNS_API_TOKEN",
        "INSTALLABLE_APPS_REGISTRATION_TOKEN",
        "BRIDGE_REGISTRATION_TOKEN",
        "ANDROID_STORE_PASSWORD",
        "ANDROID_KEY_PASSWORD",
        "ANDROID_KEYSTORE_BASE64",
    }
)
_MISSING_REPO_MARKERS = ("could not resolve", "not found", "repository not found")
_DEFAULT_PROJECT_NAME = "New Project"
_DEFAULT_FRONTEND_STRATEGY = "flutter"
_DEFAULT_GITHUB_VISIBILITY = "private"
_DEFAULT_GITHUB_BRANCH = "main"
_CLOUDFLARE_PROVISION_PHASE = ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_PROVISION
_CLOUDFLARE_DEPLOY_PHASE = ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_DEPLOY
_PREVIEW_SMOKE_PHASE = ProjectFactoryInitPhaseName.PREVIEW_SMOKE
_FRONTEND_BASELINE_PHASE = ProjectFactoryInitPhaseName.FLUTTER_OR_STRATEGY_BASELINE
_AUTOMATIC_UX_COMMAND_TIMEOUT_SECONDS = 300.0
_AUTOMATIC_UX_SKILL_CONTEXT_MAX_CHARS = 8000


@dataclass(frozen=True, slots=True)
class ProjectFactoryInitCommandResult:
    argv: tuple[str, ...]
    cwd: str | None
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    env: dict[str, str] | None = None


class ProjectFactoryInitCommandRunner(Protocol):
    def run(
        self,
        argv: tuple[str, ...],
        *,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: float = 0,
    ) -> ProjectFactoryInitCommandResult: ...


class SubprocessProjectFactoryInitCommandRunner:
    def run(
        self,
        argv: tuple[str, ...],
        *,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: float = 0,
    ) -> ProjectFactoryInitCommandResult:
        started_at = _now_iso()
        try:
            process = subprocess.Popen(
                list(argv),
                cwd=str(cwd) if cwd is not None else None,
                env={**os.environ, **env} if env else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                start_new_session=True,
            )
            stdout, stderr = process.communicate(
                timeout=timeout_seconds if timeout_seconds > 0 else None
            )
            return ProjectFactoryInitCommandResult(
                argv=argv,
                cwd=str(cwd) if cwd is not None else None,
                exit_code=process.returncode,
                stdout=stdout,
                stderr=stderr,
                started_at=started_at,
                completed_at=_now_iso(),
                env=env,
            )
        except FileNotFoundError as exc:
            return ProjectFactoryInitCommandResult(
                argv=argv,
                cwd=str(cwd) if cwd is not None else None,
                exit_code=127,
                stderr=str(exc),
                started_at=started_at,
                completed_at=_now_iso(),
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except (NameError, ProcessLookupError, PermissionError):
                pass
            try:
                stdout, stderr = process.communicate(timeout=5)
            except (NameError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except (NameError, ProcessLookupError, PermissionError):
                    pass
                try:
                    stdout, stderr = process.communicate(timeout=5)
                except Exception:
                    stdout, stderr = "", ""
            timeout_message = "Command timed out."
            stderr_text = str(stderr or exc.stderr or "").strip()
            stderr_text = (
                f"{stderr_text}\n{timeout_message}" if stderr_text else timeout_message
            )
            return ProjectFactoryInitCommandResult(
                argv=argv,
                cwd=str(cwd) if cwd is not None else None,
                exit_code=124,
                stdout=str(stdout or exc.stdout or ""),
                stderr=stderr_text,
                started_at=started_at,
                completed_at=_now_iso(),
                env=env,
            )


class ProjectFactoryInitConflictError(RuntimeError):
    pass


class ProjectFactoryInitService:
    def __init__(
        self,
        *,
        state_root: str | Path,
        command_runner: ProjectFactoryInitCommandRunner | None = None,
        github_owner: str | None = None,
        github_visibility: str = _DEFAULT_GITHUB_VISIBILITY,
        github_default_branch: str = _DEFAULT_GITHUB_BRANCH,
        command_env: dict[str, str] | None = None,
        command_timeout_seconds: float = 0,
        settings: Settings | None = None,
        cloudflare_client: CloudflareClient | None = None,
        cloudflare_doctor_service: CloudflarePreviewDoctorService | None = None,
        web_preview_deploy_service: WebPreviewDeployService | None = None,
        chat_repository: ChatRepository | None = None,
    ) -> None:
        self._state_root = Path(state_root).expanduser().resolve()
        self._init_state_dir = self._state_root / "init_jobs"
        self._command_runner = (
            command_runner or SubprocessProjectFactoryInitCommandRunner()
        )
        self._github_owner = _optional_clean(github_owner)
        self._github_visibility = github_visibility or _DEFAULT_GITHUB_VISIBILITY
        self._github_default_branch = github_default_branch or _DEFAULT_GITHUB_BRANCH
        self._command_env = dict(command_env or {})
        self._command_timeout_seconds = command_timeout_seconds
        self._settings = settings
        self._cloudflare_client = cloudflare_client
        self._cloudflare_doctor_service = cloudflare_doctor_service
        self._web_preview_deploy_service = web_preview_deploy_service
        self._chat_repository = chat_repository
        self._lock = RLock()
        self._jobs: dict[str, ProjectFactoryInitJob] = {}
        self._init_state_dir.mkdir(parents=True, exist_ok=True)
        self._load_state()

    def start_or_resume(
        self,
        *,
        draft_id: str,
        chat_session_id: str | None = None,
        workspace_path: str | None = None,
        project_name: str = _DEFAULT_PROJECT_NAME,
        slug: str | None = None,
        frontend_strategy: str = _DEFAULT_FRONTEND_STRATEGY,
    ) -> ProjectFactoryInitJob:
        with self._lock:
            existing = self._active_or_latest_job_for_draft(draft_id)
            if existing is not None:
                updated = existing
                relationships = existing.relationships
                if chat_session_id and relationships.chat_session_id != chat_session_id:
                    relationships = replace(
                        relationships, chat_session_id=chat_session_id
                    )
                if (
                    workspace_path
                    and relationships.generated_workspace_path != workspace_path
                ):
                    relationships = replace(
                        relationships,
                        generated_workspace_path=workspace_path,
                    )
                if relationships != existing.relationships:
                    updated = replace(
                        updated,
                        relationships=relationships,
                        updated_at=_now_iso(),
                    ).with_derived_completion_state()
                    self._jobs[updated.id] = updated
                    self._persist_job(updated)
                return updated

            job = ProjectFactoryInitJob.new(
                id=_new_id("pf-init"),
                draft_id=draft_id,
                chat_session_id=chat_session_id,
                project_name=project_name or _DEFAULT_PROJECT_NAME,
                slug=slug or _slug_from_name(project_name or draft_id),
                frontend_strategy=frontend_strategy or _DEFAULT_FRONTEND_STRATEGY,
            )
            if workspace_path:
                job = replace(
                    job,
                    relationships=replace(
                        job.relationships,
                        generated_workspace_path=workspace_path,
                    ),
                    updated_at=_now_iso(),
                ).with_derived_completion_state()
            self._jobs[job.id] = job
            self._persist_job(job)
            return job

    def run_pipeline(self, init_job_id: str) -> ProjectFactoryInitJob:
        """Run the deterministic init phases for a queued/resumable job."""

        try:
            self.queue_retry(init_job_id)
            job = self.complete_phase(
                init_job_id,
                ProjectFactoryInitPhaseName.INIT_PREFLIGHT.value,
                message="Deterministic init preflight accepted.",
            )
            job = self.complete_phase(
                job.id,
                ProjectFactoryInitPhaseName.DRAFT_AND_SLUG.value,
                message=f"Draft and slug verified: {job.slug}.",
            )
            job = self.complete_phase(
                job.id,
                ProjectFactoryInitPhaseName.BASELINE_SCAFFOLD.value,
                message="Baseline scaffold phase delegated to frontend strategy generator.",
            )
            job = self.run_frontend_baseline_phase(job.id)
            if not _has_blocking_phase(job):
                job = self.run_automatic_ux_phases(job.id)
            if _has_waiting_phase(job):
                return job
            if not _has_blocking_phase(job):
                job = self.complete_phase(
                    job.id,
                    ProjectFactoryInitPhaseName.LOCAL_VALIDATION.value,
                    message="Generated baseline contracts verified locally.",
                )
                job = self._run_local_git_commit_phase(job.id)
            if not _has_blocking_phase(job):
                job = self.run_github_repository_phase(job.id)
            if not _has_blocking_phase(job):
                job = self.run_cloudflare_preview_phases(job.id)
            if not _has_blocking_phase(job):
                job = self.run_android_preview_release_phases(job.id)
            job = self._complete_workbench_feedback_phase(job.id)
            return self.run_llm_context_pack_phase(job.id)
        except Exception as exc:
            current = self.get_job(init_job_id)
            if current is None:
                raise
            failed = self.fail_phase(
                current.id,
                self._current_phase_name(current).value,
                message=f"Deterministic init pipeline failed: {exc}",
            )
            try:
                return self.run_llm_context_pack_phase(failed.id)
            except Exception:
                return failed

    def run_automatic_ux_phases(
        self,
        init_job_id: str,
        *,
        project_path: str | Path | None = None,
    ) -> ProjectFactoryInitJob:
        """Run the New Project UX generator/reviewer lane before validation."""

        with self._lock:
            job = self._require_job(init_job_id)
            generator_phase = job.phase(ProjectFactoryInitPhaseName.UX_GENERATOR)
            reviewer_phase = job.phase(ProjectFactoryInitPhaseName.UX_REVIEWER)
            if (
                generator_phase.status == ProjectFactoryInitPhaseStatus.COMPLETED
                and reviewer_phase.status == ProjectFactoryInitPhaseStatus.COMPLETED
            ):
                return job

            target = self._frontend_target_path(job, project_path)
            if not target.exists():
                return self.block_phase(
                    job.id,
                    ProjectFactoryInitPhaseName.UX_GENERATOR.value,
                    blocker=_automatic_ux_blocker(
                        phase=ProjectFactoryInitPhaseName.UX_GENERATOR,
                        code="automatic_ux_workspace_missing",
                        message="Automatic UX cannot run because the generated workspace is missing.",
                        next_action="Restore the generated workspace, then rerun deterministic init.",
                    ),
                    context_available=False,
                )
            domain_brief = self._domain_brief_for_automatic_ux(job, target)
            if not domain_brief:
                return self.wait_for_domain_brief_phase(job.id)

            try:
                visual_ux_skill_context = _load_visual_ux_skill_context(None)
            except ProjectFactoryUxSkillUnavailableError as exc:
                return self.block_phase(
                    job.id,
                    ProjectFactoryInitPhaseName.UX_GENERATOR.value,
                    blocker=_automatic_ux_blocker(
                        phase=ProjectFactoryInitPhaseName.UX_GENERATOR,
                        code="automatic_ux_skill_missing",
                        message="Automatic UX requires the visual-ux-polish skill.",
                        next_action=(
                            "Install or restore the visual-ux-polish skill on the "
                            "bridge host, then rerun deterministic init."
                        ),
                        detail=str(exc),
                    ),
                    context_available=True,
                )

            prompt_root = target / ".codex" / "factory" / "prompts"
            prompt_root.mkdir(parents=True, exist_ok=True)
            _write_automatic_ux_domain_brief(target, domain_brief)
            generator_base, reviewer_base = _automatic_ux_prompts(
                job,
                target=target,
                domain_brief=domain_brief,
                visual_ux_prompt_section=visual_ux_skill_context.prompt_section,
            )
            (prompt_root / "ux-generator.md").write_text(
                generator_base,
                encoding="utf-8",
            )
            (prompt_root / "ux-reviewer.md").write_text(
                reviewer_base,
                encoding="utf-8",
            )

            job = self.begin_phase(
                job.id,
                ProjectFactoryInitPhaseName.UX_GENERATOR.value,
                message=(
                    "Running automatic UX generator and reviewer lane before "
                    "validation and release."
                ),
            )
            generator_evidence: list[ProjectFactoryInitCommandEvidence] = []
            reviewer_evidence: list[ProjectFactoryInitCommandEvidence] = []
            reviewer_feedback = ""
            completed_iterations = 0
            completed_by_reviewer = False
            codex_command = self._settings.codex_command if self._settings else "codex"
            codex_exec_args = self._settings.codex_exec_args if self._settings else None

            for iteration in range(1, _MAX_AUTOMATIC_UX_ITERATIONS + 1):
                generator_prompt_path = _ux_iteration_prompt_path(
                    prompt_root,
                    "ux-generator",
                    iteration,
                )
                reviewer_prompt_path = _ux_iteration_prompt_path(
                    prompt_root,
                    "ux-reviewer",
                    iteration,
                )
                if iteration > 1:
                    generator_prompt_path.write_text(
                        generator_base
                        + "\n\n# UX Reviewer Continuation\n\n"
                        + reviewer_feedback.strip()
                        + "\n",
                        encoding="utf-8",
                    )
                    reviewer_prompt_path.write_text(
                        reviewer_base
                        + f"\n\nReview UX iteration {iteration}. Return `status=complete` "
                        "only when the UX gate is ready; otherwise include the next "
                        "UX-only continuation prompt.\n",
                        encoding="utf-8",
                    )

                generator_report_path = (
                    target / ".codex" / "ux" / "ux-generator-report.md"
                )
                generator_result = self._run(
                    _codex_argv_with_output_report(
                        codex_command,
                        _automatic_ux_prompt_file_instruction(
                            generator_prompt_path,
                            cwd=target,
                        ),
                        report_path=generator_report_path,
                        exec_args=codex_exec_args,
                    ),
                    cwd=target,
                    timeout_seconds=_AUTOMATIC_UX_COMMAND_TIMEOUT_SECONDS,
                )
                generator_evidence.append(self._evidence(generator_result))
                _ensure_automatic_ux_report(
                    target=target,
                    role="generator",
                    result=generator_result,
                )
                self._attach_automatic_ux_message(
                    job,
                    role="generator",
                    iteration=iteration,
                    result=generator_result,
                )
                if _automatic_ux_result_failed(
                    generator_result,
                    target=target,
                    role="generator",
                ):
                    return self.block_phase(
                        job.id,
                        ProjectFactoryInitPhaseName.UX_GENERATOR.value,
                        blocker=_automatic_ux_command_blocker(
                            phase=ProjectFactoryInitPhaseName.UX_GENERATOR,
                            code="automatic_ux_generator_failed",
                            message="Automatic UX generator failed.",
                            result=generator_result,
                        ),
                        context_available=True,
                        command_evidence=tuple(generator_evidence),
                    )

                reviewer_report_path = (
                    target / ".codex" / "ux" / "ux-reviewer-report.md"
                )
                reviewer_result = self._run(
                    _codex_argv_with_output_report(
                        codex_command,
                        _automatic_ux_prompt_file_instruction(
                            reviewer_prompt_path,
                            cwd=target,
                        ),
                        report_path=reviewer_report_path,
                        exec_args=codex_exec_args,
                    ),
                    cwd=target,
                    timeout_seconds=_AUTOMATIC_UX_COMMAND_TIMEOUT_SECONDS,
                )
                reviewer_evidence.append(self._evidence(reviewer_result))
                _ensure_automatic_ux_report(
                    target=target,
                    role="reviewer",
                    result=reviewer_result,
                )
                self._attach_automatic_ux_message(
                    job,
                    role="reviewer",
                    iteration=iteration,
                    result=reviewer_result,
                )
                if _automatic_ux_result_failed(
                    reviewer_result,
                    target=target,
                    role="reviewer",
                ):
                    job = self.complete_phase(
                        job.id,
                        ProjectFactoryInitPhaseName.UX_GENERATOR.value,
                        message=(
                            "Automatic UX generator completed before reviewer failure."
                        ),
                        command_evidence=tuple(generator_evidence),
                    )
                    return self.block_phase(
                        job.id,
                        ProjectFactoryInitPhaseName.UX_REVIEWER.value,
                        blocker=_automatic_ux_command_blocker(
                            phase=ProjectFactoryInitPhaseName.UX_REVIEWER,
                            code="automatic_ux_reviewer_failed",
                            message="Automatic UX reviewer failed.",
                            result=reviewer_result,
                        ),
                        context_available=True,
                        command_evidence=tuple(reviewer_evidence),
                    )

                completed_iterations = iteration
                reviewer_feedback = _automatic_ux_reviewer_feedback(
                    target=target,
                    result=reviewer_result,
                )
                if _ux_reviewer_is_complete(reviewer_feedback):
                    completed_by_reviewer = True
                    break

            _write_ux_evidence_index(target)
            artifacts = (
                ProjectFactoryInitArtifact(
                    kind="automatic_ux_evidence",
                    path=str(target / ".codex/ux/evidence-index.json"),
                    metadata={
                        "iterations": completed_iterations,
                        "maxIterations": _MAX_AUTOMATIC_UX_ITERATIONS,
                        "completedByReviewer": completed_by_reviewer,
                    },
                ),
            )
            job = self.complete_phase(
                job.id,
                ProjectFactoryInitPhaseName.UX_GENERATOR.value,
                message=(
                    "Automatic UX generator completed after "
                    f"{completed_iterations} of {_MAX_AUTOMATIC_UX_ITERATIONS} pass(es)."
                ),
                artifacts=artifacts,
                command_evidence=tuple(generator_evidence),
            )
            reviewer_message = (
                "Automatic UX reviewer completed after "
                f"{completed_iterations} of {_MAX_AUTOMATIC_UX_ITERATIONS} pass(es)."
                if completed_by_reviewer
                else "Automatic UX reviewer reached the maximum "
                f"{_MAX_AUTOMATIC_UX_ITERATIONS} pass(es)."
            )
            return self.complete_phase(
                job.id,
                ProjectFactoryInitPhaseName.UX_REVIEWER.value,
                message=reviewer_message,
                artifacts=artifacts,
                command_evidence=tuple(reviewer_evidence),
            )

    def queue_retry(self, init_job_id: str) -> ProjectFactoryInitJob:
        """Prepare a blocked or failed deterministic init job for another pass."""

        return self._reset_blocked_or_failed_phase_for_retry(init_job_id)

    def wait_for_domain_brief_phase(self, init_job_id: str) -> ProjectFactoryInitJob:
        """Mark automatic UX as visible but gated on the first domain brief."""

        message = (
            "queued_waiting_for_domain_brief: Automatic UX baseline will start "
            "after the first Domain Factory brief is captured."
        )
        with self._lock:
            job = self._require_job(init_job_id)
            updated = job
            for phase_name in (
                ProjectFactoryInitPhaseName.UX_GENERATOR,
                ProjectFactoryInitPhaseName.UX_REVIEWER,
            ):
                phase = updated.phase(phase_name)
                if phase.status == ProjectFactoryInitPhaseStatus.COMPLETED:
                    continue
                updated_phase = replace(
                    phase,
                    status=ProjectFactoryInitPhaseStatus.QUEUED_WAITING_FOR_DOMAIN_BRIEF,
                    message=message,
                    started_at=None,
                    completed_at=None,
                    blockers=(),
                )
                updated = updated.with_phase(updated_phase)
            self._jobs[updated.id] = updated
            self._persist_job(updated)
            return updated

    def _reset_blocked_or_failed_phase_for_retry(
        self,
        init_job_id: str,
    ) -> ProjectFactoryInitJob:
        with self._lock:
            job = self._require_job(init_job_id)
            for phase_name in INIT_PHASE_ORDER:
                phase = job.phase(phase_name)
                if phase.status not in {
                    ProjectFactoryInitPhaseStatus.BLOCKED,
                    ProjectFactoryInitPhaseStatus.FAILED,
                }:
                    continue
                retry_phase = replace(
                    phase,
                    status=ProjectFactoryInitPhaseStatus.QUEUED,
                    message="",
                    started_at=None,
                    completed_at=None,
                    blockers=(),
                )
                updated = job.with_phase(retry_phase).with_derived_completion_state()
                self._jobs[updated.id] = updated
                self._persist_job(updated)
                return updated
            return job

    def get_job(self, init_job_id: str) -> ProjectFactoryInitJob | None:
        with self._lock:
            return self._jobs.get(init_job_id)

    def list_jobs(
        self,
        *,
        draft_id: str | None = None,
        limit: int = 50,
    ) -> tuple[ProjectFactoryInitJob, ...]:
        with self._lock:
            jobs = sorted(
                self._jobs.values(),
                key=lambda item: item.created_at,
                reverse=True,
            )
            if draft_id is not None:
                jobs = [job for job in jobs if job.relationships.draft_id == draft_id]
            return tuple(jobs[: max(1, min(limit, 200))])

    def begin_phase(
        self,
        init_job_id: str,
        phase_name: str,
        *,
        message: str = "",
    ) -> ProjectFactoryInitJob:
        with self._lock:
            job = self._require_job(init_job_id)
            phase = self._phase(job, phase_name)
            if phase.status == ProjectFactoryInitPhaseStatus.COMPLETED:
                return job
            now = _now_iso()
            updated_phase = replace(
                phase,
                status=ProjectFactoryInitPhaseStatus.RUNNING,
                message=message or phase.message,
                started_at=phase.started_at or now,
                completed_at=None,
            )
            return self._update_job_phase(job, updated_phase)

    def complete_phase(
        self,
        init_job_id: str,
        phase_name: str,
        *,
        message: str = "",
        artifacts: tuple[ProjectFactoryInitArtifact, ...] = (),
        command_evidence: tuple[ProjectFactoryInitCommandEvidence, ...] = (),
    ) -> ProjectFactoryInitJob:
        with self._lock:
            job = self._require_job(init_job_id)
            phase = self._phase(job, phase_name)
            if phase.status == ProjectFactoryInitPhaseStatus.COMPLETED:
                return job
            now = _now_iso()
            updated_phase = replace(
                phase,
                status=ProjectFactoryInitPhaseStatus.COMPLETED,
                message=message or phase.message,
                started_at=phase.started_at or now,
                completed_at=now,
                artifacts=_merge_artifacts(phase.artifacts, artifacts),
                command_evidence=phase.command_evidence + tuple(command_evidence),
                blockers=(),
            )
            return self._update_job_phase(job, updated_phase)

    def block_phase(
        self,
        init_job_id: str,
        phase_name: str,
        *,
        blocker: ProjectFactoryInitBlocker,
        context_available: bool,
        message: str = "",
        command_evidence: tuple[ProjectFactoryInitCommandEvidence, ...] = (),
    ) -> ProjectFactoryInitJob:
        del context_available
        with self._lock:
            job = self._require_job(init_job_id)
            phase = self._phase(job, phase_name)
            now = _now_iso()
            updated_phase = replace(
                phase,
                status=ProjectFactoryInitPhaseStatus.BLOCKED,
                message=message or blocker.message,
                started_at=phase.started_at or now,
                completed_at=now,
                blockers=_merge_blockers(phase.blockers, (blocker,)),
                command_evidence=phase.command_evidence + tuple(command_evidence),
            )
            return self._update_job_phase(job, updated_phase)

    def fail_phase(
        self,
        init_job_id: str,
        phase_name: str,
        *,
        message: str,
    ) -> ProjectFactoryInitJob:
        with self._lock:
            job = self._require_job(init_job_id)
            phase = self._phase(job, phase_name)
            now = _now_iso()
            updated_phase = replace(
                phase,
                status=ProjectFactoryInitPhaseStatus.FAILED,
                message=message,
                started_at=phase.started_at or now,
                completed_at=now,
            )
            return self._update_job_phase(job, updated_phase)

    def cancel(
        self,
        init_job_id: str,
        *,
        message: str = "Init cancelled.",
    ) -> ProjectFactoryInitJob:
        with self._lock:
            job = self._require_job(init_job_id)
            current_phase = self._current_phase_name(job)
            phase = self._phase(job, current_phase.value)
            if phase.status in {
                ProjectFactoryInitPhaseStatus.QUEUED,
                ProjectFactoryInitPhaseStatus.RUNNING,
                ProjectFactoryInitPhaseStatus.BLOCKED,
            }:
                phase = replace(
                    phase,
                    status=ProjectFactoryInitPhaseStatus.CANCELLED,
                    message=message,
                    completed_at=_now_iso(),
                )
                job = job.with_phase(phase)
            self._jobs[job.id] = job
            self._persist_job(job)
            return job

    def _domain_brief_for_automatic_ux(
        self,
        job: ProjectFactoryInitJob,
        target: Path,
    ) -> str:
        domain_factory_brief = _read_domain_factory_brief(target)
        if domain_factory_brief:
            return domain_factory_brief
        session_id = job.relationships.chat_session_id
        if not session_id or self._chat_repository is None:
            return ""
        try:
            messages = self._chat_repository.list_messages(session_id)
        except Exception:
            return ""
        return _project_factory_chat_domain_brief(messages)

    def record_remote_resource(
        self,
        init_job_id: str,
        *,
        resource: ProjectFactoryInitRemoteResource,
    ) -> ProjectFactoryInitJob:
        with self._lock:
            job = self._require_job(init_job_id)
            updated = self._replace_remote_resource(job, resource)
            self._jobs[updated.id] = updated
            self._persist_job(updated)
            return updated

    def attach_context_pack(
        self,
        init_job_id: str,
        *,
        context_pack: ProjectFactoryInitContextPack,
    ) -> ProjectFactoryInitJob:
        with self._lock:
            job = self._require_job(init_job_id)
            updated = replace(
                job,
                context_pack=context_pack,
                updated_at=_now_iso(),
            ).with_derived_completion_state()
            self._jobs[updated.id] = updated
            self._persist_job(updated)
            return updated

    def run_frontend_baseline_phase(
        self,
        init_job_id: str,
        *,
        project_path: str | Path | None = None,
    ) -> ProjectFactoryInitJob:
        with self._lock:
            job = self._require_job(init_job_id)
            strategy = job.frontend_strategy or _DEFAULT_FRONTEND_STRATEGY
            strategy_contract = FRONTEND_STRATEGIES.get(strategy)
            if strategy_contract is None:
                return self._block_frontend_baseline(
                    job,
                    blocker=_frontend_blocker(
                        code="frontend_strategy_unknown",
                        message=f"Unknown frontend strategy: {strategy}",
                        next_action="Choose a supported frontend strategy and rerun deterministic init.",
                    ),
                    evidence=(),
                )
            target = self._frontend_target_path(job, project_path)
            self._mark_frontend_running(
                job,
                "Generating or verifying frontend baseline, Workbench, feedback, updater, and runtime contracts.",
            )
            evidence: list[ProjectFactoryInitCommandEvidence] = []
            generated = False
            if not target.exists():
                generated_result = self._generate_frontend_baseline(
                    job,
                    target=target,
                    strategy=strategy,
                )
                generated = True
                evidence.append(
                    ProjectFactoryInitCommandEvidence(
                        argv=(
                            "project-factory-generator",
                            "generate",
                            strategy,
                            job.slug,
                        ),
                        cwd=str(target.parent),
                        exit_code=0,
                        stdout_summary=(
                            f"generated {len(generated_result.get('files', []))} files"
                        ),
                        started_at=_now_iso(),
                        completed_at=_now_iso(),
                    )
                )
                job = self._require_job(init_job_id)
                job = replace(
                    job,
                    relationships=replace(
                        job.relationships,
                        generated_workspace_path=str(target),
                    ),
                    updated_at=_now_iso(),
                ).with_derived_completion_state()
                self._jobs[job.id] = job
                self._persist_job(job)
            else:
                evidence.append(
                    ProjectFactoryInitCommandEvidence(
                        argv=(
                            "project-factory-generator",
                            "verify-existing",
                            strategy,
                            job.slug,
                        ),
                        cwd=str(target),
                        exit_code=0,
                        stdout_summary="existing workspace verification",
                        started_at=_now_iso(),
                        completed_at=_now_iso(),
                    )
                )
                refreshed = self._refresh_existing_managed_baseline_files(
                    job,
                    target=target,
                    strategy=strategy,
                )
                if refreshed:
                    evidence.append(
                        ProjectFactoryInitCommandEvidence(
                            argv=(
                                "project-factory-generator",
                                "refresh-managed-files",
                                strategy,
                                job.slug,
                            ),
                            cwd=str(target),
                            exit_code=0,
                            stdout_summary=(
                                "refreshed managed files: " + ", ".join(refreshed)
                            ),
                            started_at=_now_iso(),
                            completed_at=_now_iso(),
                        )
                    )

            repaired_ignores = _ensure_generated_artifact_ignores(target)
            if repaired_ignores:
                evidence.append(
                    ProjectFactoryInitCommandEvidence(
                        argv=(
                            "project-factory-generator",
                            "repair-gitignore",
                            strategy,
                            job.slug,
                        ),
                        cwd=str(target),
                        exit_code=0,
                        stdout_summary=(
                            "added generated artifact ignores: "
                            + ", ".join(repaired_ignores)
                        ),
                        started_at=_now_iso(),
                        completed_at=_now_iso(),
                    )
                )

            verification = _verify_frontend_baseline(
                target=target,
                slug=job.slug,
                project_name=job.project_name,
                strategy=strategy,
                strategy_contract=strategy_contract,
            )
            evidence.append(
                ProjectFactoryInitCommandEvidence(
                    argv=(
                        "project-factory-generator",
                        "verify-contracts",
                        strategy,
                        job.slug,
                    ),
                    cwd=str(target),
                    exit_code=0 if verification["ok"] else 1,
                    stdout_summary=json.dumps(
                        verification,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    started_at=_now_iso(),
                    completed_at=_now_iso(),
                )
            )
            if not verification["ok"]:
                return self._block_frontend_baseline(
                    job,
                    blocker=_frontend_blocker_from_verification(verification),
                    evidence=tuple(evidence),
                    artifacts=(
                        ProjectFactoryInitArtifact(
                            kind="frontend_baseline_verification",
                            path=str(target),
                            metadata=verification,
                        ),
                    ),
                )
            android_evidence, android_blocker = self._ensure_flutter_android_project(
                target=target,
                strategy=strategy,
            )
            evidence.extend(android_evidence)
            if android_blocker is not None:
                return self._block_frontend_baseline(
                    job,
                    blocker=android_blocker,
                    evidence=tuple(evidence),
                )
            completed = self._complete_frontend_baseline(
                job,
                target=target,
                strategy=strategy,
                strategy_contract=strategy_contract,
                verification=verification,
                generated=generated,
                evidence=tuple(evidence),
            )
            if not bool(strategy_contract.get("supports_android_preview_apk")):
                completed = self._skip_future_phase(
                    completed,
                    ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                    message=(
                        f"{strategy} strategy is web-only; Android preview release is skipped."
                    ),
                )
            if not bool(strategy_contract.get("supports_bridge_installable_app")):
                completed = self._skip_future_phase(
                    completed,
                    ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION,
                    message=(
                        f"{strategy} strategy is not Bridge-installable; registration is skipped."
                    ),
                )
            return completed

    def run_android_preview_release_phases(
        self,
        init_job_id: str,
        *,
        project_path: str | Path | None = None,
        bridge_url: str | None = None,
    ) -> ProjectFactoryInitJob:
        with self._lock:
            job = self._require_job(init_job_id)
            strategy_contract = FRONTEND_STRATEGIES.get(job.frontend_strategy)
            if not strategy_contract or not bool(
                strategy_contract.get("supports_android_preview_apk")
            ):
                return self._preserve_or_skip_android_installable(job)
            target = self._frontend_target_path(job, project_path)
            runtime = _read_json_file(target / "release/preview-runtime.json")
            runtime_blocker = _android_runtime_blocker(runtime, slug=job.slug)
            if runtime_blocker is not None:
                return self._block_android_phase(
                    job,
                    phase_name=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                    blocker=runtime_blocker,
                    evidence=(),
                )
            version = _read_flutter_version(target / "apps/mobile/pubspec.yaml")
            if not version:
                return self._block_android_phase(
                    job,
                    phase_name=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                    blocker=_android_blocker(
                        phase=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                        code="android_preview_flutter_version_missing",
                        message="Flutter pubspec version is missing for Android preview release.",
                        next_action="Restore apps/mobile/pubspec.yaml with a version, then rerun deterministic init.",
                        command=("project-factory", "init", "baseline", "repair"),
                    ),
                    evidence=(),
                )
            release_tag = _android_preview_tag(version)
            apk_name = f"{job.slug}.apk"
            preview_api = f"https://preview.nienfos.com/{job.slug}/api"
            bridge_base_url = (
                bridge_url or (self._settings.api_base_url if self._settings else "")
            ).rstrip("/")
            bridge_public_url = _resolve_bridge_public_url(
                bridge_base_url,
                settings=self._settings,
                command_env=self._command_env,
            )
            bridge_registration_url = _resolve_bridge_registration_url(
                bridge_base_url,
                settings=self._settings,
                command_env=self._command_env,
            )
            env = {
                "APP_RUNTIME_PROFILE": "preview",
                "API_RUNTIME": "cloudflare_preview",
                "API_BASE_URL": preview_api,
                "PREVIEW_API_BASE_URL": preview_api,
                "APP_SLUG": job.slug,
                "SOURCE_APP": job.slug,
                "APP_RELEASE_TAG": release_tag,
                "APP_ANDROID_PREVIEW_RELEASE_TAG": release_tag,
                "ANDROID_PREVIEW_RELEASE_MODE": "bridge_local",
                "BRIDGE_URL": bridge_base_url,
                "BRIDGE_PUBLIC_URL": bridge_public_url,
                "BRIDGE_REGISTRATION_URL": bridge_registration_url,
                "CODEX_MOBILE_BRIDGE_ROOT": str(
                    self._bridge_root_for_generated_scripts()
                ),
            }
            preview_admin_email = self._preview_admin_email_for_generated_scripts(
                job=job,
                target=target,
            )
            if preview_admin_email:
                env["PREVIEW_ADMIN_EMAIL"] = preview_admin_email
            if self._settings and self._settings.installable_apps_registration_token:
                env["INSTALLABLE_APPS_REGISTRATION_TOKEN"] = (
                    self._settings.installable_apps_registration_token
                )
                env["BRIDGE_REGISTRATION_TOKEN"] = (
                    self._settings.installable_apps_registration_token
                )

            signing_evidence, signing_blocker = self._ensure_android_preview_signing(
                job.slug,
                cwd=target,
            )
            if signing_blocker is not None:
                return self._block_android_phase(
                    job,
                    phase_name=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                    blocker=signing_blocker,
                    evidence=signing_evidence,
                )
            actions_evidence, actions_blocker = (
                self._ensure_android_github_actions_config(
                    job.slug,
                    cwd=target,
                    preview_api=preview_api,
                    bridge_public_url=bridge_public_url,
                )
            )
            if actions_blocker is not None:
                return self._block_android_phase(
                    job,
                    phase_name=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                    blocker=actions_blocker,
                    evidence=(*signing_evidence, *actions_evidence),
                )
            release_view = self._run_env(
                (
                    "gh",
                    "release",
                    "view",
                    release_tag,
                    "--json",
                    "tagName,url,isPrerelease,assets",
                ),
                cwd=target,
                env=env,
            )
            release_evidence = [
                *signing_evidence,
                *actions_evidence,
                self._evidence(release_view),
            ]
            release_payload = _parse_json_object(release_view.stdout)
            release_valid = release_view.exit_code == 0 and _valid_android_release(
                release_payload,
                release_tag=release_tag,
                apk_name=apk_name,
            )
            if not release_valid:
                publish = self._run_env(
                    (
                        "bash",
                        "scripts/publish_android_preview_release.sh",
                        "--push",
                        "--watch",
                    ),
                    cwd=target,
                    env=env,
                )
                release_evidence.append(self._evidence(publish))
                if publish.exit_code != 0:
                    if _release_failed_due_generated_gitignore_repair(publish):
                        repair_evidence, repair_blocker = (
                            self._commit_generated_artifact_ignore_repair(
                                job=job,
                                target=target,
                                env=env,
                            )
                        )
                        release_evidence.extend(repair_evidence)
                        if repair_blocker is None:
                            publish = self._run_env(
                                (
                                    "bash",
                                    "scripts/publish_android_preview_release.sh",
                                    "--push",
                                    "--watch",
                                ),
                                cwd=target,
                                env=env,
                            )
                            release_evidence.append(self._evidence(publish))
                        else:
                            return self._block_android_phase(
                                job,
                                phase_name=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                                blocker=repair_blocker,
                                evidence=tuple(release_evidence),
                            )
                    elif _release_failed_due_android_platform_repair(publish):
                        repair_evidence, repair_blocker = (
                            self._commit_generated_android_platform_repair(
                                job=job,
                                target=target,
                                env=env,
                            )
                        )
                        release_evidence.extend(repair_evidence)
                        if repair_blocker is None:
                            publish = self._run_env(
                                (
                                    "bash",
                                    "scripts/publish_android_preview_release.sh",
                                    "--push",
                                    "--watch",
                                ),
                                cwd=target,
                                env=env,
                            )
                            release_evidence.append(self._evidence(publish))
                        else:
                            return self._block_android_phase(
                                job,
                                phase_name=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                                blocker=repair_blocker,
                                evidence=tuple(release_evidence),
                            )
                if publish.exit_code != 0:
                    return self._block_android_phase(
                        job,
                        phase_name=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                        blocker=_android_blocker_from_command(
                            code="android_preview_release_publish_failed",
                            message="Android preview APK release publish failed.",
                            phase=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                            result=publish,
                            command=(
                                "bash",
                                "scripts/publish_android_preview_release.sh",
                                "--push",
                                "--watch",
                            ),
                        ),
                        evidence=tuple(release_evidence),
                    )
                release_view = self._run_env(
                    (
                        "gh",
                        "release",
                        "view",
                        release_tag,
                        "--json",
                        "tagName,url,isPrerelease,assets",
                    ),
                    cwd=target,
                    env=env,
                )
                release_evidence.append(self._evidence(release_view))
                release_payload = _parse_json_object(release_view.stdout)
                release_valid = release_view.exit_code == 0 and _valid_android_release(
                    release_payload,
                    release_tag=release_tag,
                    apk_name=apk_name,
                )
            if not release_valid:
                return self._block_android_phase(
                    job,
                    phase_name=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                    blocker=_android_release_payload_blocker(
                        release_payload, release_tag, apk_name
                    ),
                    evidence=tuple(release_evidence),
                )
            apk_path = _find_apk(target, job.slug)
            apk_sha = _sha256_file(apk_path) if apk_path else None
            released = self._complete_android_release(
                job,
                target=target,
                release_tag=release_tag,
                release_payload=release_payload,
                apk_path=apk_path,
                apk_sha=apk_sha,
                evidence=tuple(release_evidence),
            )

            lookup = self._run_env(
                _bridge_installable_lookup_command(
                    bridge_registration_url,
                    bridge_public_url,
                    job.slug,
                ),
                cwd=target,
                env=env,
            )
            installable_evidence = [self._evidence(lookup)]
            installable_payload = _parse_json_object(lookup.stdout)
            installable_valid = lookup.exit_code == 0 and _valid_installable_payload(
                installable_payload,
                slug=job.slug,
                release_tag=release_tag,
                preview_api=preview_api,
            )
            if not installable_valid:
                if "INSTALLABLE_APPS_REGISTRATION_TOKEN" not in env:
                    return self._block_android_phase(
                        released,
                        phase_name=ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION,
                        blocker=_android_blocker(
                            phase=ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION,
                            code="bridge_installable_registration_token_missing",
                            message="Bridge installable registration token is missing.",
                            next_action="Set INSTALLABLE_APPS_REGISTRATION_TOKEN on the bridge host, then rerun deterministic init.",
                            command=(
                                "export",
                                "INSTALLABLE_APPS_REGISTRATION_TOKEN=<token>",
                            ),
                        ),
                        evidence=tuple(installable_evidence),
                    )
                register = self._run_env(
                    ("bash", "scripts/register_installable_app.sh"),
                    cwd=target,
                    env=env,
                )
                installable_evidence.append(self._evidence(register))
                if register.exit_code != 0:
                    return self._block_android_phase(
                        released,
                        phase_name=ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION,
                        blocker=_android_blocker_from_command(
                            code="bridge_installable_registration_failed",
                            message="Bridge installable registration failed.",
                            phase=ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION,
                            result=register,
                            command=("bash", "scripts/register_installable_app.sh"),
                        ),
                        evidence=tuple(installable_evidence),
                    )
                lookup = self._run_env(
                    _bridge_installable_lookup_command(
                        bridge_registration_url,
                        bridge_public_url,
                        job.slug,
                    ),
                    cwd=target,
                    env=env,
                )
                installable_evidence.append(self._evidence(lookup))
                installable_payload = _parse_json_object(lookup.stdout)
                installable_valid = (
                    lookup.exit_code == 0
                    and _valid_installable_payload(
                        installable_payload,
                        slug=job.slug,
                        release_tag=release_tag,
                        preview_api=preview_api,
                    )
                )
            if not installable_valid:
                return self._block_android_phase(
                    released,
                    phase_name=ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION,
                    blocker=_installable_payload_blocker(
                        installable_payload, release_tag
                    ),
                    evidence=tuple(installable_evidence),
                )
            return self._complete_bridge_installable(
                released,
                target=target,
                release_tag=release_tag,
                installable_payload=installable_payload,
                evidence=tuple(installable_evidence),
            )

    def run_llm_context_pack_phase(
        self,
        init_job_id: str,
        *,
        project_path: str | Path | None = None,
    ) -> ProjectFactoryInitJob:
        with self._lock:
            sensitive_values = self._service_sensitive_values(self._command_env)
            job = _redacted_init_job(
                self._require_job(init_job_id),
                sensitive_values=sensitive_values,
            )
            target = self._frontend_target_path(job, project_path)
            factory_dir = target / ".codex/factory"
            init_result_path = factory_dir / "init-result.json"
            llm_context_path = factory_dir / "llm-start-context.md"
            phase = job.phase(ProjectFactoryInitPhaseName.LLM_CONTEXT_PACK)
            now = _now_iso()
            phase_started_at = phase.started_at or now
            phase_completed_at = phase.completed_at or now
            phase_job = job.with_phase(
                replace(
                    phase,
                    status=ProjectFactoryInitPhaseStatus.COMPLETED,
                    message="LLM start context pack written.",
                    started_at=phase_started_at,
                    completed_at=phase_completed_at,
                    blockers=(),
                    command_evidence=(),
                    artifacts=(),
                )
            )
            result_payload = _context_pack_result_payload(
                phase_job,
                target=target,
                sensitive_values=sensitive_values,
            )
            init_result_text = _json_dumps_stable(result_payload)
            markdown = _context_pack_markdown(result_payload)
            content_sha = _sha256_text(f"{init_result_text}\n{markdown}")
            _write_text_if_changed(init_result_path, init_result_text)
            _write_text_if_changed(llm_context_path, markdown)

            attached_message_id = self._attach_context_pack_message(
                phase_job,
                content=markdown,
                content_sha=content_sha,
            )
            context_pack = ProjectFactoryInitContextPack(
                init_result_path=str(init_result_path),
                llm_start_context_path=str(llm_context_path),
                content_sha256=content_sha,
                attached_to_chat=attached_message_id is not None,
                attached_message_id=attached_message_id,
            )
            updated_phase = replace(
                phase_job.phase(ProjectFactoryInitPhaseName.LLM_CONTEXT_PACK),
                command_evidence=(
                    ProjectFactoryInitCommandEvidence(
                        argv=("project-factory-init", "write-context-pack"),
                        cwd=str(target),
                        exit_code=0,
                        stdout_summary=(
                            f"init-result.json and llm-start-context.md written; "
                            f"sha256={content_sha}"
                        ),
                        stderr_summary="",
                        started_at=now,
                        completed_at=_now_iso(),
                        redacted_env_keys=_redacted_env_keys(self._command_env),
                    ),
                ),
                artifacts=(
                    ProjectFactoryInitArtifact(
                        kind="init_result",
                        path=str(init_result_path),
                        sha256=_sha256_text(init_result_text),
                    ),
                    ProjectFactoryInitArtifact(
                        kind="llm_start_context",
                        path=str(llm_context_path),
                        sha256=_sha256_text(markdown),
                        metadata={
                            "contentSha256": content_sha,
                            "attachedMessageId": attached_message_id,
                        },
                    ),
                ),
            )
            updated = replace(
                phase_job.with_phase(updated_phase),
                context_pack=context_pack,
                updated_at=_now_iso(),
            ).with_derived_completion_state()
            self._jobs[updated.id] = updated
            self._persist_job(updated)
            return updated

    def _run_local_git_commit_phase(self, init_job_id: str) -> ProjectFactoryInitJob:
        with self._lock:
            job = self._require_job(init_job_id)
            target = self._frontend_target_path(job, None)
            phase = job.phase(ProjectFactoryInitPhaseName.LOCAL_GIT_COMMIT)
            if phase.status == ProjectFactoryInitPhaseStatus.COMPLETED:
                return job
            evidence: list[ProjectFactoryInitCommandEvidence] = []
            inside = self._run(
                ("git", "rev-parse", "--is-inside-work-tree"), cwd=target
            )
            evidence.append(self._evidence(inside))
            if inside.exit_code != 0 or inside.stdout.strip().lower() != "true":
                init = self._run(("git", "init"), cwd=target)
                evidence.append(self._evidence(init))
                if init.exit_code != 0:
                    return self.block_phase(
                        job.id,
                        ProjectFactoryInitPhaseName.LOCAL_GIT_COMMIT.value,
                        blocker=_local_git_blocker(
                            code="local_git_init_failed",
                            message="Could not initialize git in the generated workspace.",
                            command=("git", "init"),
                        ),
                        context_available=False,
                        command_evidence=tuple(evidence),
                    )

            branch = self._run(
                ("git", "checkout", "-B", self._github_default_branch), cwd=target
            )
            evidence.append(self._evidence(branch))
            add = self._run(("git", "add", "-A"), cwd=target)
            evidence.append(self._evidence(add))
            if add.exit_code != 0:
                return self.block_phase(
                    job.id,
                    ProjectFactoryInitPhaseName.LOCAL_GIT_COMMIT.value,
                    blocker=_local_git_blocker(
                        code="local_git_add_failed",
                        message="Could not stage generated baseline files.",
                        command=("git", "add", "-A"),
                    ),
                    context_available=False,
                    command_evidence=tuple(evidence),
                )

            commit = self._run(
                (
                    "git",
                    "-c",
                    "user.name=Codex Project Factory",
                    "-c",
                    "user.email=codex-project-factory@local",
                    "commit",
                    "--allow-empty",
                    "-m",
                    "Initial deterministic baseline",
                ),
                cwd=target,
            )
            evidence.append(self._evidence(commit))
            if (
                commit.exit_code != 0
                and "nothing to commit" not in commit.stderr.lower()
            ):
                return self.block_phase(
                    job.id,
                    ProjectFactoryInitPhaseName.LOCAL_GIT_COMMIT.value,
                    blocker=_local_git_blocker(
                        code="local_git_commit_failed",
                        message="Could not create the deterministic baseline commit.",
                        command=(
                            "git",
                            "commit",
                            "--allow-empty",
                            "-m",
                            "Initial deterministic baseline",
                        ),
                    ),
                    context_available=False,
                    command_evidence=tuple(evidence),
                )
            return self.complete_phase(
                job.id,
                ProjectFactoryInitPhaseName.LOCAL_GIT_COMMIT.value,
                message="Local git repository and baseline commit verified.",
                command_evidence=tuple(evidence),
            )

    def _complete_workbench_feedback_phase(
        self,
        init_job_id: str,
    ) -> ProjectFactoryInitJob:
        with self._lock:
            job = self._require_job(init_job_id)
            phase = job.phase(
                ProjectFactoryInitPhaseName.WORKBENCH_AND_FEEDBACK_VERIFICATION
            )
            if phase.status in {
                ProjectFactoryInitPhaseStatus.COMPLETED,
                ProjectFactoryInitPhaseStatus.SKIPPED,
            }:
                return job
            target = self._frontend_target_path(job, None)
            command_evidence: tuple[ProjectFactoryInitCommandEvidence, ...] = ()
            artifacts: tuple[ProjectFactoryInitArtifact, ...] = ()
            if _verified_foundation_tasks_ready(job):
                changed_paths = _align_verified_foundation_tasks(target)
                if changed_paths:
                    command_evidence, blocker = self._commit_verified_task_alignment(
                        job=job,
                        target=target,
                        changed_paths=changed_paths,
                    )
                    if blocker is not None:
                        return self.block_phase(
                            job.id,
                            ProjectFactoryInitPhaseName.WORKBENCH_AND_FEEDBACK_VERIFICATION.value,
                            blocker=blocker,
                            context_available=False,
                            command_evidence=command_evidence,
                        )
                    artifacts = (
                        ProjectFactoryInitArtifact(
                            kind="verified_foundation_task_alignment",
                            path=str(target / "specs/001-product-foundation"),
                            metadata={
                                "taskIds": sorted(_VERIFIED_FOUNDATION_TASK_IDS),
                                "changedPaths": [
                                    str(path.relative_to(target))
                                    for path in changed_paths
                                ],
                            },
                        ),
                    )
            return self.complete_phase(
                job.id,
                ProjectFactoryInitPhaseName.WORKBENCH_AND_FEEDBACK_VERIFICATION.value,
                message="Workbench, SDD, feedback, updater, and sourceApp routing verified with the frontend baseline.",
                artifacts=artifacts,
                command_evidence=command_evidence,
            )

    def _commit_verified_task_alignment(
        self,
        *,
        job: ProjectFactoryInitJob,
        target: Path,
        changed_paths: tuple[Path, ...],
    ) -> tuple[
        tuple[ProjectFactoryInitCommandEvidence, ...],
        ProjectFactoryInitBlocker | None,
    ]:
        del job
        rel_paths = tuple(str(path.relative_to(target)) for path in changed_paths)
        evidence: list[ProjectFactoryInitCommandEvidence] = []
        add = self._run(("git", "add", *rel_paths), cwd=target)
        evidence.append(self._evidence(add))
        if add.exit_code != 0:
            return tuple(evidence), _task_alignment_blocker(
                code="verified_task_alignment_git_add_failed",
                message="Could not stage verified Project Factory task status alignment.",
                command=("git", "add", *rel_paths),
            )
        commit = self._run(
            (
                "git",
                "-c",
                "user.name=Codex Project Factory",
                "-c",
                "user.email=codex-project-factory@local",
                "commit",
                "-m",
                "Align verified Project Factory task status",
            ),
            cwd=target,
        )
        evidence.append(self._evidence(commit))
        nothing_to_commit = "nothing to commit" in commit.stderr.lower()
        if commit.exit_code != 0 and not nothing_to_commit:
            return tuple(evidence), _task_alignment_blocker(
                code="verified_task_alignment_git_commit_failed",
                message="Could not commit verified Project Factory task status alignment.",
                command=(
                    "git",
                    "commit",
                    "-m",
                    "Align verified Project Factory task status",
                ),
            )
        if nothing_to_commit:
            return tuple(evidence), None
        branch = self._run(("git", "rev-parse", "--abbrev-ref", "HEAD"), cwd=target)
        evidence.append(self._evidence(branch))
        push_branch = (
            branch.stdout.strip()
            if branch.exit_code == 0 and branch.stdout.strip() != "HEAD"
            else self._github_default_branch
        )
        push = self._run(("git", "push", "origin", push_branch), cwd=target)
        evidence.append(self._evidence(push))
        if push.exit_code != 0:
            return tuple(evidence), _task_alignment_blocker(
                code="verified_task_alignment_git_push_failed",
                message="Could not push verified Project Factory task status alignment.",
                command=("git", "push", "origin", push_branch),
            )
        return tuple(evidence), None

    def run_github_repository_phase(
        self,
        init_job_id: str,
        *,
        project_path: str | Path | None = None,
        owner: str | None = None,
        repo_name: str | None = None,
        visibility: str | None = None,
        default_branch: str | None = None,
    ) -> ProjectFactoryInitJob:
        with self._lock:
            job = self._require_job(init_job_id)
            workdir = Path(
                project_path
                or job.relationships.generated_workspace_path
                or job.relationships.draft_id
            ).expanduser()
            repo_owner = _optional_clean(owner) or self._github_owner
            name = _optional_clean(repo_name) or job.slug
            repo_visibility = visibility or self._github_visibility
            branch = default_branch or self._github_default_branch
            if not repo_owner:
                return self._block_github(
                    job,
                    blocker=_github_blocker(
                        code="github_owner_missing",
                        message="GitHub owner is not configured for deterministic init.",
                        next_action="Set PROJECT_FACTORY_GITHUB_OWNER and rerun the GitHub init phase.",
                        command=("export", "PROJECT_FACTORY_GITHUB_OWNER=<owner>"),
                    ),
                    evidence=(),
                )
            if not name:
                return self._block_github(
                    job,
                    blocker=_github_blocker(
                        code="github_repo_name_missing",
                        message="GitHub repository name is empty.",
                        next_action="Set a project slug before rerunning deterministic init.",
                    ),
                    evidence=(),
                )

            evidence: list[ProjectFactoryInitCommandEvidence] = []
            self._mark_github_running(
                job, "Checking GitHub CLI, auth, repository, and git remote."
            )

            gh_version = self._run(("gh", "--version"), cwd=workdir)
            evidence.append(self._evidence(gh_version))
            if gh_version.exit_code == 127:
                return self._block_github(
                    job,
                    blocker=_github_blocker(
                        code="github_cli_missing",
                        message="GitHub CLI is not installed or is not on PATH.",
                        next_action="Install GitHub CLI, then rerun deterministic init.",
                        command=("gh", "--version"),
                    ),
                    evidence=tuple(evidence),
                )
            if gh_version.exit_code != 0:
                return self._block_github(
                    job,
                    blocker=_github_blocker(
                        code="github_cli_unavailable",
                        message="GitHub CLI is installed but failed its version check.",
                        next_action="Fix gh CLI availability, then rerun deterministic init.",
                        command=("gh", "--version"),
                    ),
                    evidence=tuple(evidence),
                )

            auth = self._run(("gh", "auth", "status"), cwd=workdir)
            evidence.append(self._evidence(auth))
            if auth.exit_code != 0:
                return self._block_github(
                    job,
                    blocker=_github_blocker(
                        code="github_auth_required",
                        message="GitHub CLI is not authenticated for repository creation/push.",
                        next_action="Authenticate GitHub CLI, then rerun deterministic init.",
                        command=("gh", "auth", "login"),
                    ),
                    evidence=tuple(evidence),
                )

            repo_ref = f"{repo_owner}/{name}"
            view = self._view_repo(repo_ref, cwd=workdir)
            evidence.append(self._evidence(view))
            repo_payload: dict[str, object] | None = None
            if view.exit_code == 0:
                repo_payload = _parse_repo_payload(view.stdout)
                if not _repo_identity_matches(repo_payload, repo_owner, name):
                    return self._block_github(
                        job,
                        blocker=_github_blocker(
                            code="github_repo_conflict",
                            message=f"GitHub repository {repo_ref} resolved to unexpected metadata.",
                            next_action="Choose a different slug or verify the existing GitHub repository owner/name.",
                            command=("gh", "repo", "view", repo_ref),
                        ),
                        evidence=tuple(evidence),
                    )
            elif _is_missing_repo(view):
                create = self._create_repo(repo_ref, repo_visibility, cwd=workdir)
                evidence.append(self._evidence(create))
                if create.exit_code != 0:
                    return self._block_github(
                        job,
                        blocker=_github_blocker(
                            code="github_repo_create_failed",
                            message=f"GitHub repository {repo_ref} could not be created.",
                            next_action="Fix GitHub owner permissions or choose an available repository name.",
                            command=(
                                "gh",
                                "repo",
                                "create",
                                repo_ref,
                                f"--{repo_visibility}",
                            ),
                        ),
                        evidence=tuple(evidence),
                    )
                verify = self._view_repo(repo_ref, cwd=workdir)
                evidence.append(self._evidence(verify))
                if verify.exit_code != 0:
                    return self._block_github(
                        job,
                        blocker=_github_blocker(
                            code="github_repo_verify_failed",
                            message=f"GitHub repository {repo_ref} was created but could not be verified.",
                            next_action="Verify repository access, then rerun deterministic init.",
                            command=("gh", "repo", "view", repo_ref),
                        ),
                        evidence=tuple(evidence),
                    )
                repo_payload = _parse_repo_payload(verify.stdout)
            else:
                return self._block_github(
                    job,
                    blocker=_github_blocker(
                        code="github_repo_permission_blocked",
                        message=f"GitHub repository {repo_ref} cannot be inspected with current permissions.",
                        next_action="Grant repository access or authenticate with an account that can view/create it.",
                        command=("gh", "repo", "view", repo_ref),
                    ),
                    evidence=tuple(evidence),
                )

            repo_url = _repo_url(repo_payload, repo_ref)
            repo_default_branch = _repo_default_branch(repo_payload) or branch
            repo_visibility = _repo_visibility(repo_payload) or repo_visibility

            inside = self._run(
                ("git", "rev-parse", "--is-inside-work-tree"), cwd=workdir
            )
            evidence.append(self._evidence(inside))
            if inside.exit_code != 0 or inside.stdout.strip().lower() != "true":
                return self._block_github(
                    job,
                    blocker=_github_blocker(
                        code="github_local_git_missing",
                        message="Project workspace is not a git repository.",
                        next_action="Initialize git and create the baseline commit, then rerun deterministic init.",
                        command=("git", "init"),
                    ),
                    evidence=tuple(evidence),
                )

            current_branch = self._run(
                ("git", "rev-parse", "--abbrev-ref", "HEAD"), cwd=workdir
            )
            evidence.append(self._evidence(current_branch))
            push_branch = (
                current_branch.stdout.strip()
                if current_branch.exit_code == 0
                else repo_default_branch
            )
            if not push_branch or push_branch == "HEAD":
                push_branch = repo_default_branch

            head = self._run(("git", "rev-parse", "HEAD"), cwd=workdir)
            evidence.append(self._evidence(head))
            if head.exit_code != 0 or not head.stdout.strip():
                return self._block_github(
                    job,
                    blocker=_github_blocker(
                        code="github_baseline_commit_missing",
                        message="Project workspace does not have a baseline commit to push.",
                        next_action="Create the baseline commit, then rerun deterministic init.",
                        command=(
                            "git",
                            "commit",
                            "--allow-empty",
                            "-m",
                            "Initial deterministic baseline",
                        ),
                    ),
                    evidence=tuple(evidence),
                )
            commit_sha = head.stdout.strip()

            origin = self._run(("git", "remote", "get-url", "origin"), cwd=workdir)
            evidence.append(self._evidence(origin))
            if origin.exit_code == 0:
                origin_url = origin.stdout.strip()
                if not _remote_matches(origin_url, repo_owner, name, repo_url):
                    return self._block_github(
                        job,
                        blocker=_github_blocker(
                            code="github_origin_conflict",
                            message=f"Existing origin points to {origin_url}, not {repo_url}.",
                            next_action="Review the existing origin before changing it, then rerun deterministic init.",
                            command=("git", "remote", "set-url", "origin", repo_url),
                        ),
                        evidence=tuple(evidence),
                    )
            else:
                add_origin = self._run(
                    ("git", "remote", "add", "origin", repo_url), cwd=workdir
                )
                evidence.append(self._evidence(add_origin))
                if add_origin.exit_code != 0:
                    return self._block_github(
                        job,
                        blocker=_github_blocker(
                            code="github_origin_add_failed",
                            message="Could not configure git origin for the GitHub repository.",
                            next_action="Set the origin remote manually, then rerun deterministic init.",
                            command=("git", "remote", "add", "origin", repo_url),
                        ),
                        evidence=tuple(evidence),
                    )

            push = self._run(("git", "push", "-u", "origin", push_branch), cwd=workdir)
            evidence.append(self._evidence(push))
            if push.exit_code != 0:
                stderr = push.stderr.lower()
                if "protected" in stderr or "permission" in stderr or "403" in stderr:
                    code = "github_branch_policy_or_permission_failure"
                    next_action = "Update branch protection/permissions or push with an authorized account, then rerun deterministic init."
                else:
                    code = "github_push_failed"
                    next_action = "Fix git push access or network state, then rerun deterministic init."
                return self._block_github(
                    job,
                    blocker=_github_blocker(
                        code=code,
                        message=f"Baseline branch {push_branch} could not be pushed to {repo_ref}.",
                        next_action=next_action,
                        command=("git", "push", "-u", "origin", push_branch),
                    ),
                    evidence=tuple(evidence),
                )

            completed_job = self._complete_github(
                job,
                repo_ref=repo_ref,
                repo_url=repo_url,
                owner=repo_owner,
                repo_name=name,
                visibility=repo_visibility,
                default_branch=repo_default_branch,
                pushed_branch=push_branch,
                commit_sha=commit_sha,
                evidence=tuple(evidence),
            )
            return completed_job

    def run_cloudflare_preview_phases(
        self,
        init_job_id: str,
        *,
        project_path: str | Path | None = None,
    ) -> ProjectFactoryInitJob:
        with self._lock:
            job = self._require_job(init_job_id)
            workdir = Path(
                project_path
                or job.relationships.generated_workspace_path
                or job.relationships.draft_id
            ).expanduser()
            settings = self._settings
            if settings is None:
                return self._block_cloudflare(
                    job,
                    phase_name=_CLOUDFLARE_PROVISION_PHASE,
                    blocker=_cloudflare_blocker(
                        phase=_CLOUDFLARE_PROVISION_PHASE,
                        code="cloudflare_settings_missing",
                        message="Cloudflare settings are not available to deterministic init.",
                        next_action="Start the bridge with Cloudflare settings loaded, then rerun deterministic init.",
                    ),
                    evidence=(),
                )

            preview_url = _preview_url(settings.preview_base_domain, job.slug)
            api_base_url = f"{preview_url}/api" if preview_url else ""
            job = self._record_cloudflare_url_resources(
                job,
                preview_url=preview_url,
                api_base_url=api_base_url,
                status="planned",
            )
            self._mark_cloudflare_running(
                job,
                _CLOUDFLARE_PROVISION_PHASE,
                "Checking Cloudflare configuration and preview provisioning access.",
            )

            doctor = self._cloudflare_doctor(settings).doctor()
            doctor_evidence = self._api_evidence(
                ("cloudflare", "doctor"),
                doctor,
                exit_code=0 if doctor.get("ok") is True else 1,
                cwd=workdir,
            )
            if doctor.get("ok") is not True:
                return self._block_cloudflare(
                    job,
                    phase_name=_CLOUDFLARE_PROVISION_PHASE,
                    blocker=_cloudflare_doctor_blocker(doctor),
                    evidence=(doctor_evidence,),
                    artifacts=(
                        ProjectFactoryInitArtifact(
                            kind="cloudflare_doctor",
                            metadata=_safe_json_object(doctor),
                        ),
                    ),
                )

            wrangler = self._run(("wrangler", "--version"), cwd=workdir)
            wrangler_evidence = self._evidence(wrangler)
            if wrangler.exit_code == 127:
                return self._block_cloudflare(
                    job,
                    phase_name=_CLOUDFLARE_PROVISION_PHASE,
                    blocker=_cloudflare_blocker(
                        phase=_CLOUDFLARE_PROVISION_PHASE,
                        code="cloudflare_wrangler_missing",
                        message="wrangler is not installed or is not on PATH.",
                        next_action="Install wrangler on the bridge host, then rerun deterministic init.",
                        command=("wrangler", "--version"),
                    ),
                    evidence=(doctor_evidence, wrangler_evidence),
                )
            if wrangler.exit_code != 0:
                return self._block_cloudflare(
                    job,
                    phase_name=_CLOUDFLARE_PROVISION_PHASE,
                    blocker=_cloudflare_blocker(
                        phase=_CLOUDFLARE_PROVISION_PHASE,
                        code="cloudflare_wrangler_unavailable",
                        message="wrangler failed its version check.",
                        next_action="Fix wrangler availability, then rerun deterministic init.",
                        command=("wrangler", "--version"),
                    ),
                    evidence=(doctor_evidence, wrangler_evidence),
                )

            build_env = {
                "APP_SLUG": job.slug,
                "SOURCE_APP": job.slug,
                "APP_RUNTIME_PROFILE": "preview",
                "API_RUNTIME": "cloudflare_preview",
                "API_BASE_URL": api_base_url,
                "WEB_PREVIEW_BUILD_DIR": str(
                    workdir / "build" / "web-preview" / job.slug
                ),
            }
            build = self._run_env(
                ("bash", "scripts/build_web_preview.sh"),
                cwd=workdir,
                env=build_env,
            )
            build_evidence = self._evidence(build)
            if build.exit_code != 0:
                return self._block_cloudflare(
                    job,
                    phase_name=_CLOUDFLARE_PROVISION_PHASE,
                    blocker=_cloudflare_blocker(
                        phase=_CLOUDFLARE_PROVISION_PHASE,
                        code="cloudflare_web_preview_build_failed",
                        message="Web preview artifact build failed before Cloudflare deploy.",
                        next_action=(
                            "Fix the generated frontend web build, then rerun "
                            "deterministic init."
                        ),
                        command=("bash", "scripts/build_web_preview.sh"),
                    ),
                    evidence=(doctor_evidence, wrangler_evidence, build_evidence),
                )

            deploy_service = self._web_preview_service(settings)
            try:
                plan = deploy_service.plan(
                    WebPreviewPlanInput(
                        project_path=str(workdir),
                        source_app=job.slug,
                    )
                )
                plan_evidence = self._api_evidence(
                    ("web-preview", "plan", job.slug),
                    plan,
                    exit_code=0,
                    cwd=workdir,
                )
                deployed = deploy_service.deploy(
                    WebPreviewDeployInput(
                        project_path=str(workdir),
                        source_app=job.slug,
                        confirm_apply=True,
                        expected_plan_hash=str(plan["plan_hash"]),
                    )
                )
            except WebPreviewError as exc:
                evidence = (
                    doctor_evidence,
                    wrangler_evidence,
                    build_evidence,
                    *(() if "plan_evidence" not in locals() else (plan_evidence,)),
                )
                return self._block_cloudflare_exception(
                    job,
                    exc=exc,
                    evidence=evidence,
                )

            deploy_evidence = self._api_evidence(
                ("web-preview", "deploy", job.slug),
                deployed,
                exit_code=0,
                cwd=workdir,
            )
            provision_completed = self._complete_cloudflare_provision(
                job,
                preview_url=preview_url,
                api_base_url=api_base_url,
                plan=plan,
                deployed=deployed,
                evidence=(
                    doctor_evidence,
                    wrangler_evidence,
                    build_evidence,
                    plan_evidence,
                ),
            )
            deploy_completed = self._complete_cloudflare_deploy(
                provision_completed,
                deployed=deployed,
                evidence=(deploy_evidence,),
            )
            smoke_completed = self._complete_preview_smoke(
                deploy_completed,
                preview_url=preview_url,
                api_base_url=api_base_url,
                deployed=deployed,
                evidence=(deploy_evidence,),
            )
            return self._complete_initial_admin_invites(
                smoke_completed,
                target=workdir,
                deploy_service=deploy_service,
            )

    def to_response_payload(self, job: ProjectFactoryInitJob) -> dict[str, object]:
        status = self._status_for_response(job)
        current_phase = self._current_phase_name(job).value
        blockers = [
            blocker.to_payload() for phase in job.phases for blocker in phase.blockers
        ]
        retry_available = any(
            blocker.recoverable
            for phase in job.phases
            if phase.status == ProjectFactoryInitPhaseStatus.BLOCKED
            for blocker in phase.blockers
        ) or any(
            phase.status == ProjectFactoryInitPhaseStatus.FAILED
            for phase in job.phases
        )
        workspace_path = job.relationships.generated_workspace_path
        context_pack = job.context_pack.to_payload() if job.context_pack else None
        if context_pack is not None:
            context_pack = {
                **context_pack,
                "sha256": job.context_pack.content_sha256,
                "attachedSessionId": job.relationships.chat_session_id
                if job.context_pack.attached_to_chat
                else None,
            }
        return {
            "kind": "codex.projectFactoryInitJob",
            "version": 1,
            "initJobId": job.id,
            "draftId": job.relationships.draft_id,
            "chatSessionId": job.relationships.chat_session_id,
            "createdAt": job.created_at,
            "updatedAt": job.updated_at,
            "status": status,
            "currentPhase": current_phase,
            "projectPath": workspace_path,
            "workspacePath": workspace_path,
            "generatedWorkspacePath": job.relationships.generated_workspace_path,
            "phases": [phase.to_payload() for phase in job.phases],
            "remoteResources": [
                _remote_resource_response_payload(resource)
                for resource in job.remote_resources
            ],
            "contextPack": context_pack,
            "blockers": blockers,
            "readyForBusinessLlm": status == "ready",
            "canContinueWithBlockedContext": status == "blocked_with_context",
            "retryAvailable": retry_available,
        }

    def _active_or_latest_job_for_draft(
        self,
        draft_id: str,
    ) -> ProjectFactoryInitJob | None:
        matches = [
            job for job in self._jobs.values() if job.relationships.draft_id == draft_id
        ]
        if not matches:
            return None
        active = [
            job
            for job in matches
            if job.completion_state not in _TERMINAL_ACTIVE_STATES
        ]
        candidates = active or matches
        return max(candidates, key=lambda item: item.created_at)

    def _phase(
        self,
        job: ProjectFactoryInitJob,
        phase_name: str,
    ) -> ProjectFactoryInitPhase:
        try:
            return job.phase(ProjectFactoryInitPhaseName(phase_name))
        except ValueError as exc:
            raise ProjectFactoryInitConflictError(
                f"Unknown init phase: {phase_name}"
            ) from exc
        except KeyError as exc:
            raise ProjectFactoryInitConflictError(
                f"Unknown init phase: {phase_name}"
            ) from exc

    def _update_job_phase(
        self,
        job: ProjectFactoryInitJob,
        phase: ProjectFactoryInitPhase,
    ) -> ProjectFactoryInitJob:
        updated = job.with_phase(phase)
        self._jobs[updated.id] = updated
        self._persist_job(updated)
        return updated

    def _replace_remote_resource(
        self,
        job: ProjectFactoryInitJob,
        resource: ProjectFactoryInitRemoteResource,
    ) -> ProjectFactoryInitJob:
        resources = {
            (item.type, item.identifier): item for item in job.remote_resources
        }
        resources[(resource.type, resource.identifier)] = resource
        updated = replace(
            job,
            remote_resources=tuple(resources.values()),
            updated_at=_now_iso(),
        ).with_derived_completion_state()
        return updated

    def _require_job(self, init_job_id: str) -> ProjectFactoryInitJob:
        job = self._jobs.get(init_job_id)
        if job is None:
            raise ProjectFactoryInitConflictError(
                f"Project Factory init job not found: {init_job_id}"
            )
        return job

    def _mark_github_running(self, job: ProjectFactoryInitJob, message: str) -> None:
        phase = job.phase(_GITHUB_PHASE)
        if phase.status != ProjectFactoryInitPhaseStatus.COMPLETED:
            now = _now_iso()
            updated = job.with_phase(
                replace(
                    phase,
                    status=ProjectFactoryInitPhaseStatus.RUNNING,
                    message=message,
                    started_at=phase.started_at or now,
                    completed_at=None,
                )
            )
            self._jobs[updated.id] = updated
            self._persist_job(updated)

    def _complete_github(
        self,
        job: ProjectFactoryInitJob,
        *,
        repo_ref: str,
        repo_url: str,
        owner: str,
        repo_name: str,
        visibility: str,
        default_branch: str,
        pushed_branch: str,
        commit_sha: str,
        evidence: tuple[ProjectFactoryInitCommandEvidence, ...],
    ) -> ProjectFactoryInitJob:
        current = self._require_job(job.id)
        phase = current.phase(_GITHUB_PHASE)
        now = _now_iso()
        completed_phase = replace(
            phase,
            status=ProjectFactoryInitPhaseStatus.COMPLETED,
            message="GitHub repository verified and baseline branch pushed.",
            started_at=phase.started_at or now,
            completed_at=now,
            blockers=(),
            command_evidence=tuple(evidence),
            artifacts=(
                ProjectFactoryInitArtifact(
                    kind="github_repository_state",
                    url=repo_url,
                    metadata={
                        "owner": owner,
                        "name": repo_name,
                        "visibility": visibility,
                        "defaultBranch": default_branch,
                        "pushedBranch": pushed_branch,
                        "commitSha": commit_sha,
                    },
                ),
            ),
        )
        updated = current.with_phase(completed_phase)
        updated = self._replace_remote_resource(
            updated,
            ProjectFactoryInitRemoteResource(
                type=ProjectFactoryInitRemoteResourceType.GITHUB_REPOSITORY,
                identifier=repo_ref,
                display_name=repo_ref,
                url=repo_url,
                provider="github",
                status="ready",
                metadata={
                    "owner": owner,
                    "name": repo_name,
                    "visibility": visibility,
                    "defaultBranch": default_branch,
                    "pushedBranch": pushed_branch,
                    "commitSha": commit_sha,
                },
            ),
        )
        updated = self._replace_remote_resource(
            updated,
            ProjectFactoryInitRemoteResource(
                type=ProjectFactoryInitRemoteResourceType.GITHUB_BRANCH,
                identifier=f"{repo_ref}:{pushed_branch}",
                display_name=f"{repo_ref}:{pushed_branch}",
                url=f"{repo_url}/tree/{pushed_branch}",
                provider="github",
                status="pushed",
                metadata={"commitSha": commit_sha, "branch": pushed_branch},
            ),
        )
        self._jobs[updated.id] = updated
        self._persist_job(updated)
        return updated

    def _block_github(
        self,
        job: ProjectFactoryInitJob,
        *,
        blocker: ProjectFactoryInitBlocker,
        evidence: tuple[ProjectFactoryInitCommandEvidence, ...],
    ) -> ProjectFactoryInitJob:
        current = self._jobs.get(job.id, job)
        phase = current.phase(_GITHUB_PHASE)
        now = _now_iso()
        updated_phase = replace(
            phase,
            status=ProjectFactoryInitPhaseStatus.BLOCKED,
            message=blocker.message,
            started_at=phase.started_at or now,
            completed_at=now,
            blockers=_merge_blockers(phase.blockers, (blocker,)),
            command_evidence=tuple(evidence),
        )
        updated = current.with_phase(updated_phase)
        self._jobs[updated.id] = updated
        self._persist_job(updated)
        return updated

    def _cloudflare_doctor(self, settings: Settings) -> CloudflarePreviewDoctorService:
        return self._cloudflare_doctor_service or CloudflarePreviewDoctorService(
            settings=settings,
            client=self._cloudflare_client,
        )

    def _web_preview_service(self, settings: Settings) -> WebPreviewDeployService:
        return self._web_preview_deploy_service or WebPreviewDeployService(
            settings=settings,
            client=self._cloudflare_client,
            command_runner=self._command_runner,
        )

    def _record_cloudflare_url_resources(
        self,
        job: ProjectFactoryInitJob,
        *,
        preview_url: str,
        api_base_url: str,
        status: str,
        metadata: dict[str, object] | None = None,
    ) -> ProjectFactoryInitJob:
        updated = job
        if preview_url:
            updated = self._replace_remote_resource(
                updated,
                ProjectFactoryInitRemoteResource(
                    type=ProjectFactoryInitRemoteResourceType.PREVIEW_URL,
                    identifier=preview_url,
                    display_name=preview_url,
                    url=preview_url,
                    provider="cloudflare",
                    status=status,
                    metadata={"slug": job.slug, **(metadata or {})},
                ),
            )
        if api_base_url:
            updated = self._replace_remote_resource(
                updated,
                ProjectFactoryInitRemoteResource(
                    type=ProjectFactoryInitRemoteResourceType.API_BASE_URL,
                    identifier=api_base_url,
                    display_name=api_base_url,
                    url=api_base_url,
                    provider="cloudflare",
                    status=status,
                    metadata={"slug": job.slug, **(metadata or {})},
                ),
            )
        self._jobs[updated.id] = updated
        self._persist_job(updated)
        return updated

    def _ensure_android_preview_signing(
        self,
        slug: str,
        *,
        cwd: Path,
    ) -> tuple[
        tuple[ProjectFactoryInitCommandEvidence, ...],
        ProjectFactoryInitBlocker | None,
    ]:
        bridge_root = self._bridge_root_for_generated_scripts()
        secrets_dir = bridge_root / "secrets"
        signing_env = secrets_dir / f"{slug}-preview-signing.env"
        keystore = secrets_dir / f"{slug}-preview-upload-keystore.jks"
        if signing_env.is_file() and keystore.is_file():
            return (), None

        secrets_dir.mkdir(parents=True, exist_ok=True)
        store_password = token_urlsafe(36)
        key_password = token_urlsafe(36)
        keytool = _keytool_executable()
        command = (
            keytool,
            "-genkeypair",
            "-v",
            "-keystore",
            str(keystore),
            "-storetype",
            "JKS",
            "-keyalg",
            "RSA",
            "-keysize",
            "2048",
            "-validity",
            "10000",
            "-alias",
            "preview",
            "-storepass:env",
            "ANDROID_STORE_PASSWORD",
            "-keypass:env",
            "ANDROID_KEY_PASSWORD",
            "-dname",
            f"CN={slug} Preview,O=Codex Project Factory,C=US",
        )
        result = self._command_runner.run(
            command,
            cwd=cwd,
            env={
                **self._command_env,
                "ANDROID_STORE_PASSWORD": store_password,
                "ANDROID_KEY_PASSWORD": key_password,
            },
            timeout_seconds=self._command_timeout_seconds,
        )
        evidence = self._evidence(result)
        if result.exit_code != 0:
            if keystore.exists():
                keystore.unlink()
            return (
                (evidence,),
                _android_blocker(
                    phase=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                    code="android_preview_signing_generation_failed",
                    message="Android preview signing generation failed.",
                    next_action=(
                        "Install keytool or create Bridge preview signing files, "
                        "then rerun deterministic init."
                    ),
                    command=(
                        "keytool",
                        "-genkeypair",
                        "-keystore",
                        str(keystore),
                    ),
                ),
            )

        signing_env.write_text(
            "\n".join(
                [
                    "# Generated by Project Factory deterministic init.",
                    "ANDROID_KEY_ALIAS=preview",
                    f"ANDROID_STORE_PASSWORD={shlex.quote(store_password)}",
                    f"ANDROID_KEY_PASSWORD={shlex.quote(key_password)}",
                    "ANDROID_STORE_TYPE=JKS",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        os.chmod(signing_env, 0o600)
        os.chmod(keystore, 0o600)
        return (evidence,), None

    def _bridge_root_for_generated_scripts(self) -> Path:
        configured = self._command_env.get(
            "CODEX_MOBILE_BRIDGE_ROOT"
        ) or os.environ.get("CODEX_MOBILE_BRIDGE_ROOT")
        return Path(configured).expanduser().resolve() if configured else Path.cwd()

    def _preview_admin_email_for_generated_scripts(
        self,
        *,
        job: ProjectFactoryInitJob,
        target: Path,
    ) -> str | None:
        configured = (
            self._command_env.get("PREVIEW_ADMIN_EMAIL")
            or os.environ.get("PREVIEW_ADMIN_EMAIL")
            or ""
        ).strip()
        if configured:
            return configured
        config = self._initial_admin_invite_config(job=job, target=target)
        emails = config.get("emails")
        if not isinstance(emails, tuple | list) or not emails:
            return None
        email = str(emails[0] or "").strip().lower()
        return email or None

    def _ensure_flutter_android_project(
        self,
        *,
        target: Path,
        strategy: str,
    ) -> tuple[
        tuple[ProjectFactoryInitCommandEvidence, ...],
        ProjectFactoryInitBlocker | None,
    ]:
        if strategy != "flutter":
            return (), None
        mobile = target / "apps/mobile"
        build_gradle = mobile / "android/app/build.gradle.kts"
        evidence: list[ProjectFactoryInitCommandEvidence] = []
        if not build_gradle.is_file():
            create = self._run(
                ("flutter", "create", "--platforms=android", "."), cwd=mobile
            )
            evidence.append(self._evidence(create))
            if create.exit_code != 0:
                return (
                    tuple(evidence),
                    _frontend_blocker(
                        code="frontend_flutter_android_create_failed",
                        message="Flutter Android project creation failed.",
                        next_action=(
                            "Install or repair Flutter Android tooling, then rerun "
                            "deterministic init."
                        ),
                    ),
                )
            widget_test = mobile / "test/widget_test.dart"
            if widget_test.is_file() and "MyApp" in widget_test.read_text(
                encoding="utf-8"
            ):
                widget_test.unlink()
            analysis_options = mobile / "analysis_options.yaml"
            if analysis_options.is_file() and "flutter_lints/flutter.yaml" in (
                analysis_options.read_text(encoding="utf-8")
            ):
                analysis_options.unlink()
        if build_gradle.is_file():
            _patch_flutter_android_release_signing(build_gradle)
        _ensure_flutter_android_bridge_network_config(mobile)
        return tuple(evidence), None

    def _ensure_android_github_actions_config(
        self,
        slug: str,
        *,
        cwd: Path,
        preview_api: str,
        bridge_public_url: str,
    ) -> tuple[
        tuple[ProjectFactoryInitCommandEvidence, ...],
        ProjectFactoryInitBlocker | None,
    ]:
        origin = self._run(("git", "remote", "get-url", "origin"), cwd=cwd)
        evidence = [self._evidence(origin)]
        repo_ref = _github_repo_ref_from_origin(origin.stdout.strip())
        if origin.exit_code != 0 or not repo_ref:
            return (
                tuple(evidence),
                _android_blocker(
                    phase=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                    code="android_preview_github_origin_missing",
                    message="GitHub origin is required before Android preview release.",
                    next_action="Configure the GitHub origin, then rerun deterministic init.",
                    command=("git", "remote", "get-url", "origin"),
                ),
            )
        if not _non_local_http_url(bridge_public_url):
            return (
                tuple(evidence),
                _android_blocker(
                    phase=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                    code="android_preview_bridge_public_url_missing",
                    message=(
                        "A non-local Bridge public URL is required before "
                        "building the Android preview APK with Workbench enabled."
                    ),
                    next_action=(
                        "Configure APP_UPDATE_PUBLIC_BASE_URL or BRIDGE_PUBLIC_URL "
                        "with the reachable Codex Mobile Bridge URL, then rerun "
                        "deterministic init."
                    ),
                    command=("gh", "variable", "set", "CODEX_BRIDGE_WORKBENCH_URL"),
                ),
            )
        bridge_public_url = bridge_public_url.rstrip("/")
        android_bridge_url = _android_preview_bridge_url(bridge_public_url)
        variable_values = {
            "API_BASE_URL": preview_api,
            "CODEX_BRIDGE_DEV_MODE": "true",
            "CODEX_BRIDGE_WORKBENCH_URL": android_bridge_url,
            "CODEX_FEEDBACK_ENABLED": "true",
            "CODEX_FEEDBACK_BRIDGE_URL": android_bridge_url,
            "CODEX_APP_UPDATER_BRIDGE_URL": android_bridge_url,
        }
        for variable_name, variable_value in variable_values.items():
            variable = self._run(
                (
                    "gh",
                    "variable",
                    "set",
                    variable_name,
                    "--body",
                    variable_value,
                    "--repo",
                    repo_ref,
                ),
                cwd=cwd,
            )
            evidence.append(self._evidence(variable))
            if variable.exit_code != 0:
                return (
                    tuple(evidence),
                    _android_blocker(
                        phase=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                        code="android_preview_github_variable_failed",
                        message=(
                            "Could not configure GitHub Actions "
                            f"{variable_name} variable."
                        ),
                        next_action=(
                            "Fix GitHub variable permissions, then rerun "
                            "deterministic init."
                        ),
                        command=(
                            "gh",
                            "variable",
                            "set",
                            variable_name,
                            "--repo",
                            repo_ref,
                        ),
                    ),
                )
        signing = _read_preview_signing_files(
            self._bridge_root_for_generated_scripts(),
            slug,
        )
        secret_values = {
            "ANDROID_KEYSTORE_BASE64": base64.b64encode(
                signing["keystore_bytes"]
            ).decode("ascii"),
            "ANDROID_KEY_ALIAS": signing["ANDROID_KEY_ALIAS"],
            "ANDROID_KEY_PASSWORD": signing["ANDROID_KEY_PASSWORD"],
            "ANDROID_STORE_PASSWORD": signing["ANDROID_STORE_PASSWORD"],
            "ANDROID_STORE_TYPE": signing.get("ANDROID_STORE_TYPE", "JKS"),
        }
        temp_paths: list[Path] = []
        try:
            env_file = (
                self._bridge_root_for_generated_scripts()
                / "secrets"
                / f".{slug}-android-preview-secrets.env"
            )
            env_file.write_text(
                "".join(
                    f"{name}={shlex.quote(str(value))}\n"
                    for name, value in secret_values.items()
                ),
                encoding="utf-8",
            )
            os.chmod(env_file, 0o600)
            temp_paths.append(env_file)
            secret = self._run(
                (
                    "gh",
                    "secret",
                    "set",
                    "--env-file",
                    str(env_file),
                    "--repo",
                    repo_ref,
                ),
                cwd=cwd,
            )
            evidence.append(self._evidence(secret))
            if secret.exit_code != 0:
                return (
                    tuple(evidence),
                    _android_blocker(
                        phase=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                        code="android_preview_github_secret_failed",
                        message="Could not configure GitHub Actions signing secrets.",
                        next_action=(
                            "Fix GitHub secret permissions, then rerun "
                            "deterministic init."
                        ),
                        command=("gh", "secret", "set", "--repo", repo_ref),
                    ),
                )
        finally:
            for temp_path in temp_paths:
                if temp_path.exists():
                    temp_path.unlink()
        return tuple(evidence), None

    def _mark_cloudflare_running(
        self,
        job: ProjectFactoryInitJob,
        phase_name: ProjectFactoryInitPhaseName,
        message: str,
    ) -> None:
        current = self._jobs.get(job.id, job)
        phase = current.phase(phase_name)
        if phase.status != ProjectFactoryInitPhaseStatus.COMPLETED:
            now = _now_iso()
            updated = current.with_phase(
                replace(
                    phase,
                    status=ProjectFactoryInitPhaseStatus.RUNNING,
                    message=message,
                    started_at=phase.started_at or now,
                    completed_at=None,
                )
            )
            self._jobs[updated.id] = updated
            self._persist_job(updated)

    def _complete_cloudflare_provision(
        self,
        job: ProjectFactoryInitJob,
        *,
        preview_url: str,
        api_base_url: str,
        plan: dict[str, object],
        deployed: dict[str, object],
        evidence: tuple[ProjectFactoryInitCommandEvidence, ...],
    ) -> ProjectFactoryInitJob:
        current = self._jobs.get(job.id, job)
        phase = current.phase(_CLOUDFLARE_PROVISION_PHASE)
        now = _now_iso()
        applied = _expect_sequence(deployed.get("applied_resources"))
        updated_phase = replace(
            phase,
            status=ProjectFactoryInitPhaseStatus.COMPLETED,
            message="Cloudflare preview resources verified or created.",
            started_at=phase.started_at or now,
            completed_at=now,
            blockers=(),
            command_evidence=evidence,
            artifacts=(
                ProjectFactoryInitArtifact(
                    kind="cloudflare_preview_plan",
                    metadata=_safe_json_object(plan),
                ),
                *tuple(_cloudflare_migration_artifacts(applied)),
            ),
        )
        updated = current.with_phase(updated_phase)
        updated = self._record_cloudflare_url_resources(
            updated,
            preview_url=preview_url,
            api_base_url=api_base_url,
            status="ready",
            metadata={"previewId": deployed.get("preview_id")},
        )
        for resource in _cloudflare_remote_resources(applied):
            updated = self._replace_remote_resource(updated, resource)
        self._jobs[updated.id] = updated
        self._persist_job(updated)
        return updated

    def _complete_cloudflare_deploy(
        self,
        job: ProjectFactoryInitJob,
        *,
        deployed: dict[str, object],
        evidence: tuple[ProjectFactoryInitCommandEvidence, ...],
    ) -> ProjectFactoryInitJob:
        phase = job.phase(_CLOUDFLARE_DEPLOY_PHASE)
        now = _now_iso()
        updated = job.with_phase(
            replace(
                phase,
                status=ProjectFactoryInitPhaseStatus.COMPLETED,
                message="Cloudflare preview deploy verified.",
                started_at=phase.started_at or now,
                completed_at=now,
                blockers=(),
                command_evidence=evidence,
                artifacts=(
                    ProjectFactoryInitArtifact(
                        kind="cloudflare_deploy_verification",
                        metadata={
                            "status": deployed.get("status"),
                            "workerScriptVerificationStatus": deployed.get(
                                "worker_script_verification_status"
                            ),
                            "healthVerification": _safe_json_object(
                                deployed.get("health_verification")
                            ),
                        },
                    ),
                ),
            )
        )
        self._jobs[updated.id] = updated
        self._persist_job(updated)
        return updated

    def _complete_preview_smoke(
        self,
        job: ProjectFactoryInitJob,
        *,
        preview_url: str,
        api_base_url: str,
        deployed: dict[str, object],
        evidence: tuple[ProjectFactoryInitCommandEvidence, ...],
    ) -> ProjectFactoryInitJob:
        health = _safe_json_object(deployed.get("health_verification"))
        smoke_metadata = {
            "previewUrl": preview_url,
            "apiBaseUrl": api_base_url,
            "checks": _latest_health_checks(health),
            "required": health.get("required") if isinstance(health, dict) else None,
        }
        phase = job.phase(_PREVIEW_SMOKE_PHASE)
        now = _now_iso()
        updated = job.with_phase(
            replace(
                phase,
                status=ProjectFactoryInitPhaseStatus.COMPLETED,
                message="Preview web and API smoke checks passed.",
                started_at=phase.started_at or now,
                completed_at=now,
                blockers=(),
                command_evidence=evidence,
                artifacts=(
                    ProjectFactoryInitArtifact(
                        kind="cloudflare_preview_smoke",
                        metadata=smoke_metadata,
                    ),
                ),
            )
        )
        updated = self._record_cloudflare_url_resources(
            updated,
            preview_url=preview_url,
            api_base_url=api_base_url,
            status="smoke_passed",
            metadata={"smoke": smoke_metadata},
        )
        self._jobs[updated.id] = updated
        self._persist_job(updated)
        return updated

    def _complete_initial_admin_invites(
        self,
        job: ProjectFactoryInitJob,
        *,
        target: Path,
        deploy_service: WebPreviewDeployService,
    ) -> ProjectFactoryInitJob:
        config = self._initial_admin_invite_config(job=job, target=target)
        emails = tuple(config["emails"])
        if not emails:
            return job
        settings = self._settings
        if settings is None:
            return job

        invite_service = WebPreviewInviteService(
            settings=settings,
            preview_service=deploy_service,
        )
        preview_id = f"wp-{job.slug}"
        existing_invites = invite_service.list_invites(preview_id)
        existing_active_emails = {
            str(invite.get("email") or "").strip().lower()
            for invite in existing_invites
            if _is_active_invite(invite)
        }
        results: list[dict[str, object]] = []
        failures: list[dict[str, object]] = []
        for email in emails:
            if email in existing_active_emails:
                results.append(
                    {
                        "email": email,
                        "status": "existing_active",
                        "manualDeliveryRequired": False,
                    }
                )
                continue
            try:
                invite = invite_service.create_invite(
                    WebPreviewInviteCreateInput(
                        preview_id=preview_id,
                        email=email,
                        role=str(config["role"]),
                        single_use=True,
                    )
                )
            except WebPreviewInviteError as exc:
                if exc.code == "duplicate_admin_invite":
                    results.append(
                        {
                            "email": email,
                            "status": "existing_active",
                            "manualDeliveryRequired": False,
                        }
                    )
                    continue
                failures.append(
                    {
                        "email": email,
                        "code": exc.code,
                        "message": exc.message,
                    }
                )
                continue
            results.append(_safe_invite_result(invite))

        phase = job.phase(_PREVIEW_SMOKE_PHASE)
        evidence = self._api_evidence(
            ("web-preview", "initial-admin-invites", job.slug),
            {
                "preview_id": preview_id,
                "emails": list(emails),
                "role": str(config["role"]),
                "source": str(config["source"]),
                "results": results,
                "failures": failures,
            },
            exit_code=0 if not failures else 1,
            cwd=target,
        )
        artifact = ProjectFactoryInitArtifact(
            kind="web_preview_initial_admin_invites",
            metadata={
                "previewId": preview_id,
                "count": len(emails),
                "source": str(config["source"]),
                "results": results,
                "failures": failures,
            },
        )
        if failures:
            return self._block_cloudflare(
                job,
                phase_name=_PREVIEW_SMOKE_PHASE,
                blocker=_cloudflare_blocker(
                    phase=_PREVIEW_SMOKE_PHASE,
                    code="web_preview_initial_admin_invites_failed",
                    message=(
                        "Initial admin web preview invites could not be created."
                    ),
                    next_action=(
                        "Fix Web Preview invite configuration, then rerun "
                        "deterministic init."
                    ),
                ),
                evidence=(*phase.command_evidence, evidence),
                artifacts=(artifact,),
            )
        updated = job.with_phase(
            replace(
                phase,
                command_evidence=(*phase.command_evidence, evidence),
                artifacts=(*phase.artifacts, artifact),
                message=(
                    "Preview smoke passed and initial admin invites were created."
                    if not failures
                    else "Preview smoke passed but initial admin invite creation needs attention."
                ),
            )
        )
        self._jobs[updated.id] = updated
        self._persist_job(updated)
        return updated

    def _initial_admin_invite_config(
        self,
        *,
        job: ProjectFactoryInitJob,
        target: Path,
    ) -> dict[str, object]:
        draft_config = self._initial_admin_invite_config_from_draft(job)
        if draft_config["emails"]:
            return draft_config
        manifest_config = _initial_admin_invite_config_from_manifest(target)
        if manifest_config["emails"]:
            return manifest_config
        return draft_config if draft_config["required"] else manifest_config

    def _initial_admin_invite_config_from_draft(
        self,
        job: ProjectFactoryInitJob,
    ) -> dict[str, object]:
        path = self._state_root / "drafts" / f"{job.relationships.draft_id}.json"
        try:
            payload = _read_json(path)
        except Exception:
            return _empty_initial_admin_invite_config("missing")
        request = payload.get("request")
        manifest_plan = payload.get("manifest_plan")
        manifest = (
            manifest_plan.get("manifest") if isinstance(manifest_plan, dict) else None
        )
        admin = manifest.get("admin") if isinstance(manifest, dict) else None
        initial_invites = (
            admin.get("initial_invites") if isinstance(admin, dict) else None
        )
        emails = _normalize_invite_emails(
            request.get("initial_admin_emails") if isinstance(request, dict) else None
        )
        if not emails and isinstance(initial_invites, dict):
            emails = _normalize_invite_emails(initial_invites.get("emails"))
        return {
            "emails": emails,
            "role": _invite_role(initial_invites),
            "required": _invite_required(initial_invites),
            "source": "draft",
        }

    def _block_cloudflare_exception(
        self,
        job: ProjectFactoryInitJob,
        *,
        exc: WebPreviewError,
        evidence: tuple[ProjectFactoryInitCommandEvidence, ...],
    ) -> ProjectFactoryInitJob:
        message = _summarize_output(exc.message, self._service_sensitive_values())
        phase_name = _cloudflare_error_phase(exc.code, message)
        return self._block_cloudflare(
            job,
            phase_name=phase_name,
            blocker=_cloudflare_blocker(
                phase=phase_name,
                code=_cloudflare_error_code(exc.code, message),
                message=message,
                next_action=_cloudflare_error_next_action(exc.code, message),
                command=_cloudflare_error_command(exc.code, message, self._settings),
            ),
            evidence=evidence,
            artifacts=(
                ProjectFactoryInitArtifact(
                    kind="cloudflare_error",
                    metadata={"code": exc.code, "message": message},
                ),
            ),
        )

    def _block_cloudflare(
        self,
        job: ProjectFactoryInitJob,
        *,
        phase_name: ProjectFactoryInitPhaseName,
        blocker: ProjectFactoryInitBlocker,
        evidence: tuple[ProjectFactoryInitCommandEvidence, ...],
        artifacts: tuple[ProjectFactoryInitArtifact, ...] = (),
    ) -> ProjectFactoryInitJob:
        current = self._jobs.get(job.id, job)
        if phase_name == _PREVIEW_SMOKE_PHASE:
            current = self._settle_cloudflare_phases_before_smoke_block(
                current,
                evidence=evidence,
            )
        phase = current.phase(phase_name)
        now = _now_iso()
        updated_phase = replace(
            phase,
            status=ProjectFactoryInitPhaseStatus.BLOCKED,
            message=blocker.message,
            started_at=phase.started_at or now,
            completed_at=now,
            blockers=_merge_blockers(phase.blockers, (blocker,)),
            command_evidence=tuple(evidence),
            artifacts=_merge_artifacts(phase.artifacts, artifacts),
        )
        updated = current.with_phase(updated_phase)
        self._jobs[updated.id] = updated
        self._persist_job(updated)
        return updated

    def _settle_cloudflare_phases_before_smoke_block(
        self,
        job: ProjectFactoryInitJob,
        *,
        evidence: tuple[ProjectFactoryInitCommandEvidence, ...],
    ) -> ProjectFactoryInitJob:
        now = _now_iso()
        updated = job
        for phase_name, message in (
            (
                _CLOUDFLARE_PROVISION_PHASE,
                "Cloudflare preview provisioning reached smoke verification.",
            ),
            (
                _CLOUDFLARE_DEPLOY_PHASE,
                "Cloudflare preview deploy reached smoke verification.",
            ),
        ):
            phase = updated.phase(phase_name)
            if phase.status in {
                ProjectFactoryInitPhaseStatus.COMPLETED,
                ProjectFactoryInitPhaseStatus.BLOCKED,
                ProjectFactoryInitPhaseStatus.FAILED,
                ProjectFactoryInitPhaseStatus.CANCELLED,
            }:
                continue
            updated = updated.with_phase(
                replace(
                    phase,
                    status=ProjectFactoryInitPhaseStatus.COMPLETED,
                    message=message,
                    started_at=phase.started_at or now,
                    completed_at=now,
                    blockers=(),
                    command_evidence=tuple(evidence),
                )
            )
        return updated

    def _frontend_target_path(
        self,
        job: ProjectFactoryInitJob,
        project_path: str | Path | None,
    ) -> Path:
        if project_path is not None:
            return Path(project_path).expanduser().resolve()
        if job.relationships.generated_workspace_path:
            return (
                Path(job.relationships.generated_workspace_path).expanduser().resolve()
            )
        if self._settings is not None:
            return (
                Path(self._settings.projects_root).expanduser() / job.slug
            ).resolve()
        return (self._state_root.parent / job.slug).resolve()

    def _generate_frontend_baseline(
        self,
        job: ProjectFactoryInitJob,
        *,
        target: Path,
        strategy: str,
    ) -> dict[str, object]:
        if self._settings is None:
            raise ProjectFactoryInitConflictError(
                "Settings are required to generate frontend baseline."
            )
        projects_root = target.parent
        projects_root.mkdir(parents=True, exist_ok=True)
        platforms = ("web",) if strategy == "svelte" else ("ios", "android", "web")
        manifest_plan = ProjectFactoryManifestService(
            projects_root=projects_root,
        ).plan_manifest(
            ProjectFactoryManifestInput(
                name=job.project_name,
                business_type="project",
                primary_goal="Generated deterministic baseline",
                slug=job.slug,
                platforms=platforms,
                frontend_strategy=strategy,
            ),
            allow_existing=True,
        )
        try:
            result = ProjectFactoryGeneratorService().generate(manifest_plan)
        except ProjectFactoryGeneratorError as exc:
            raise ProjectFactoryInitConflictError(str(exc)) from exc
        return result.to_payload()

    def _refresh_existing_managed_baseline_files(
        self,
        job: ProjectFactoryInitJob,
        *,
        target: Path,
        strategy: str,
    ) -> tuple[str, ...]:
        if self._settings is None:
            return ()
        projects_root = target.parent
        platforms = ("web",) if strategy == "svelte" else ("ios", "android", "web")
        manifest_plan = ProjectFactoryManifestService(
            projects_root=projects_root,
        ).plan_manifest(
            ProjectFactoryManifestInput(
                name=job.project_name,
                business_type="project",
                primary_goal="Generated deterministic baseline",
                slug=job.slug,
                platforms=platforms,
                frontend_strategy=strategy,
            ),
            allow_existing=True,
        )
        try:
            result = ProjectFactoryGeneratorService().refresh_managed_files(
                manifest_plan,
                relative_paths=_EXISTING_BASELINE_MANAGED_REFRESH_FILES,
            )
        except ProjectFactoryGeneratorError as exc:
            raise ProjectFactoryInitConflictError(str(exc)) from exc
        return tuple(item.path for item in result.generated_files)

    def _mark_frontend_running(self, job: ProjectFactoryInitJob, message: str) -> None:
        current = self._jobs.get(job.id, job)
        phase = current.phase(_FRONTEND_BASELINE_PHASE)
        if phase.status != ProjectFactoryInitPhaseStatus.COMPLETED:
            now = _now_iso()
            updated = current.with_phase(
                replace(
                    phase,
                    status=ProjectFactoryInitPhaseStatus.RUNNING,
                    message=message,
                    started_at=phase.started_at or now,
                    completed_at=None,
                )
            )
            self._jobs[updated.id] = updated
            self._persist_job(updated)

    def _complete_frontend_baseline(
        self,
        job: ProjectFactoryInitJob,
        *,
        target: Path,
        strategy: str,
        strategy_contract: dict[str, object],
        verification: dict[str, object],
        generated: bool,
        evidence: tuple[ProjectFactoryInitCommandEvidence, ...],
    ) -> ProjectFactoryInitJob:
        current = self._jobs.get(job.id, job)
        phase = current.phase(_FRONTEND_BASELINE_PHASE)
        now = _now_iso()
        updated_phase = replace(
            phase,
            status=ProjectFactoryInitPhaseStatus.COMPLETED,
            message="Frontend baseline, Workbench, feedback, updater, and runtime contracts verified.",
            started_at=phase.started_at or now,
            completed_at=now,
            blockers=(),
            command_evidence=evidence,
            artifacts=(
                ProjectFactoryInitArtifact(
                    kind="frontend_baseline",
                    path=str(target),
                    metadata={
                        "status": "generated" if generated else "verified_existing",
                        "strategy": strategy,
                        "sourceRoot": strategy_contract.get("source_root"),
                        "files": verification.get("files"),
                    },
                ),
                ProjectFactoryInitArtifact(
                    kind="workbench_sdd_metadata",
                    path=str(target / "codex-bridge.yaml"),
                    metadata=verification.get("workbench", {}),
                ),
                ProjectFactoryInitArtifact(
                    kind="feedback_updater_wiring",
                    path=str(target),
                    metadata=verification.get("feedbackUpdater", {}),
                ),
                ProjectFactoryInitArtifact(
                    kind="preview_runtime_guardrails",
                    path=str(target / "release/preview-runtime.json"),
                    metadata=verification.get("runtime", {}),
                ),
                ProjectFactoryInitArtifact(
                    kind="frontend_strategy_capabilities",
                    metadata=verification.get("capabilities", {}),
                ),
            ),
        )
        relationships = replace(
            current.relationships,
            generated_workspace_path=str(target),
            workbench_scope_id=f"workspace:{target}",
        )
        updated = replace(
            current.with_phase(updated_phase),
            relationships=relationships,
            updated_at=_now_iso(),
        ).with_derived_completion_state()
        self._jobs[updated.id] = updated
        self._persist_job(updated)
        return updated

    def _block_frontend_baseline(
        self,
        job: ProjectFactoryInitJob,
        *,
        blocker: ProjectFactoryInitBlocker,
        evidence: tuple[ProjectFactoryInitCommandEvidence, ...],
        artifacts: tuple[ProjectFactoryInitArtifact, ...] = (),
    ) -> ProjectFactoryInitJob:
        current = self._jobs.get(job.id, job)
        phase = current.phase(_FRONTEND_BASELINE_PHASE)
        now = _now_iso()
        updated_phase = replace(
            phase,
            status=ProjectFactoryInitPhaseStatus.BLOCKED,
            message=blocker.message,
            started_at=phase.started_at or now,
            completed_at=now,
            blockers=_merge_blockers(phase.blockers, (blocker,)),
            command_evidence=evidence,
            artifacts=_merge_artifacts(phase.artifacts, artifacts),
        )
        updated = current.with_phase(updated_phase)
        self._jobs[updated.id] = updated
        self._persist_job(updated)
        return updated

    def _skip_future_phase(
        self,
        job: ProjectFactoryInitJob,
        phase_name: ProjectFactoryInitPhaseName,
        *,
        message: str,
    ) -> ProjectFactoryInitJob:
        phase = job.phase(phase_name)
        if phase.status == ProjectFactoryInitPhaseStatus.COMPLETED:
            return job
        updated = job.with_phase(
            replace(
                phase,
                status=ProjectFactoryInitPhaseStatus.SKIPPED,
                message=message,
                completed_at=_now_iso(),
            )
        )
        self._jobs[updated.id] = updated
        self._persist_job(updated)
        return updated

    def _preserve_or_skip_android_installable(
        self,
        job: ProjectFactoryInitJob,
    ) -> ProjectFactoryInitJob:
        updated = self._skip_future_phase(
            job,
            ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
            message=(
                f"{job.frontend_strategy} strategy does not support Android preview APK."
            ),
        )
        return self._skip_future_phase(
            updated,
            ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION,
            message=(
                f"{job.frontend_strategy} strategy does not support Bridge installable registration."
            ),
        )

    def _block_android_phase(
        self,
        job: ProjectFactoryInitJob,
        *,
        phase_name: ProjectFactoryInitPhaseName,
        blocker: ProjectFactoryInitBlocker,
        evidence: tuple[ProjectFactoryInitCommandEvidence, ...],
    ) -> ProjectFactoryInitJob:
        current = self._jobs.get(job.id, job)
        phase = current.phase(phase_name)
        now = _now_iso()
        updated_phase = replace(
            phase,
            status=ProjectFactoryInitPhaseStatus.BLOCKED,
            message=blocker.message,
            started_at=phase.started_at or now,
            completed_at=now,
            blockers=_merge_blockers(phase.blockers, (blocker,)),
            command_evidence=evidence,
        )
        updated = current.with_phase(updated_phase)
        self._jobs[updated.id] = updated
        self._persist_job(updated)
        return updated

    def _complete_android_release(
        self,
        job: ProjectFactoryInitJob,
        *,
        target: Path,
        release_tag: str,
        release_payload: dict[str, object],
        apk_path: Path | None,
        apk_sha: str | None,
        evidence: tuple[ProjectFactoryInitCommandEvidence, ...],
    ) -> ProjectFactoryInitJob:
        phase = job.phase(ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE)
        now = _now_iso()
        asset = _release_asset(release_payload, f"{job.slug}.apk")
        release_url = _optional_str(
            release_payload.get("url") or release_payload.get("htmlUrl")
        )
        artifacts = [
            ProjectFactoryInitArtifact(
                kind="android_preview_release",
                url=release_url,
                metadata={
                    "releaseTag": release_tag,
                    "releaseChannel": "prerelease",
                    "prerelease": release_payload.get("isPrerelease"),
                    "asset": asset,
                    "mockOrDemo": False,
                    "productionReady": False,
                },
            )
        ]
        if apk_path is not None:
            artifacts.append(
                ProjectFactoryInitArtifact(
                    kind="android_preview_apk",
                    path=str(apk_path),
                    sha256=apk_sha,
                    metadata={
                        "assetName": apk_path.name,
                        "releaseTag": release_tag,
                    },
                )
            )
        updated = job.with_phase(
            replace(
                phase,
                status=ProjectFactoryInitPhaseStatus.COMPLETED,
                message="Android preview APK prerelease verified.",
                started_at=phase.started_at or now,
                completed_at=now,
                blockers=(),
                command_evidence=evidence,
                artifacts=tuple(artifacts),
            )
        )
        updated = self._replace_remote_resource(
            updated,
            ProjectFactoryInitRemoteResource(
                type=ProjectFactoryInitRemoteResourceType.GITHUB_RELEASE,
                identifier=release_tag,
                display_name=release_tag,
                url=release_url,
                provider="github",
                status="prerelease_verified",
                metadata={
                    "releaseTag": release_tag,
                    "asset": asset,
                    "apkSha256": apk_sha,
                    "workspacePath": str(target),
                },
            ),
        )
        self._jobs[updated.id] = updated
        self._persist_job(updated)
        return updated

    def _complete_bridge_installable(
        self,
        job: ProjectFactoryInitJob,
        *,
        target: Path,
        release_tag: str,
        installable_payload: dict[str, object],
        evidence: tuple[ProjectFactoryInitCommandEvidence, ...],
    ) -> ProjectFactoryInitJob:
        phase = job.phase(ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION)
        now = _now_iso()
        updated = job.with_phase(
            replace(
                phase,
                status=ProjectFactoryInitPhaseStatus.COMPLETED,
                message="Bridge installable app registration verified.",
                started_at=phase.started_at or now,
                completed_at=now,
                blockers=(),
                command_evidence=evidence,
                artifacts=(
                    ProjectFactoryInitArtifact(
                        kind="bridge_installable_app",
                        url=_optional_str(installable_payload.get("apkUrl")),
                        metadata=_safe_json_object(installable_payload),
                    ),
                ),
            )
        )
        updated = self._replace_remote_resource(
            updated,
            ProjectFactoryInitRemoteResource(
                type=ProjectFactoryInitRemoteResourceType.BRIDGE_INSTALLABLE_APP,
                identifier=job.slug,
                display_name=str(
                    installable_payload.get("displayName") or job.project_name
                ),
                url=_optional_str(installable_payload.get("apkUrl")),
                provider="codex-mobile-bridge",
                status="available",
                metadata={
                    **_safe_json_object(installable_payload),
                    "workspacePath": str(target),
                    "releaseTag": release_tag,
                },
            ),
        )
        self._jobs[updated.id] = updated
        self._persist_job(updated)
        return updated

    def _attach_context_pack_message(
        self,
        job: ProjectFactoryInitJob,
        *,
        content: str,
        content_sha: str,
    ) -> str | None:
        del content_sha
        if self._chat_repository is None or not job.relationships.chat_session_id:
            return None
        session_id = job.relationships.chat_session_id
        try:
            if self._chat_repository.get_session(session_id) is None:
                return None
            dedupe_key = f"project-factory-init-context-pack:{job.id}"
            message = ChatMessage(
                id=f"pf-init-context-{job.id}",
                session_id=session_id,
                role=ChatMessageRole.ASSISTANT,
                author_type=ChatMessageAuthorType.ASSISTANT,
                content=content,
                status=ChatMessageStatus.COMPLETED,
                dedupe_key=dedupe_key,
                agent_label="Project Factory Init",
                run_id=job.id,
            )
            reserved = self._chat_repository.reserve_message(message)
            if (
                reserved.content != content
                or reserved.status != ChatMessageStatus.COMPLETED
            ):
                reserved.sync(content=content, status=ChatMessageStatus.COMPLETED)
                reserved.updated_at = datetime.now(UTC)
                self._chat_repository.save_message(reserved)
            return reserved.id
        except Exception:
            return None

    def _attach_automatic_ux_message(
        self,
        job: ProjectFactoryInitJob,
        *,
        role: str,
        iteration: int,
        result: ProjectFactoryInitCommandResult,
    ) -> str | None:
        if self._chat_repository is None or not job.relationships.chat_session_id:
            return None
        session_id = job.relationships.chat_session_id
        label = "UX Generator" if role == "generator" else "UX Reviewer"
        message_status = (
            ChatMessageStatus.COMPLETED
            if result.exit_code == 0
            else ChatMessageStatus.FAILED
        )
        content = _automatic_ux_chat_content(
            label=label,
            iteration=iteration,
            result=result,
        )
        try:
            if self._chat_repository.get_session(session_id) is None:
                return None
            dedupe_key = f"project-factory-init-ux:{job.id}:{role}:{iteration}"
            message = ChatMessage(
                id=f"pf-init-ux-{role}-{job.id}-{iteration}",
                session_id=session_id,
                role=ChatMessageRole.ASSISTANT,
                author_type=ChatMessageAuthorType.ASSISTANT,
                content=content,
                status=message_status,
                dedupe_key=dedupe_key,
                agent_id=AgentId.UX,
                agent_type=AgentType.UX,
                agent_label=label,
                visibility=AgentVisibilityMode.VISIBLE,
                trigger_source=AgentTriggerSource.SYSTEM,
                run_id=job.id,
            )
            reserved = self._chat_repository.reserve_message(message)
            if (
                reserved.content != content
                or reserved.status != message_status
                or reserved.agent_label != label
            ):
                reserved.sync(
                    content=content,
                    status=message_status,
                    agent_label=label,
                )
                reserved.updated_at = datetime.now(UTC)
                self._chat_repository.save_message(reserved)
            return reserved.id
        except Exception:
            return None

    def _run(
        self,
        argv: tuple[str, ...],
        *,
        cwd: Path,
        timeout_seconds: float | None = None,
    ) -> ProjectFactoryInitCommandResult:
        return self._command_runner.run(
            argv,
            cwd=cwd,
            env=dict(self._command_env),
            timeout_seconds=(
                timeout_seconds
                if timeout_seconds is not None
                else self._command_timeout_seconds
            ),
        )

    def _run_env(
        self,
        argv: tuple[str, ...],
        *,
        cwd: Path,
        env: dict[str, str],
    ) -> ProjectFactoryInitCommandResult:
        merged = {
            **self._command_env,
            **{key: value for key, value in env.items() if value},
        }
        return self._command_runner.run(
            argv,
            cwd=cwd,
            env=merged,
            timeout_seconds=self._command_timeout_seconds,
        )

    def _commit_generated_artifact_ignore_repair(
        self,
        *,
        job: ProjectFactoryInitJob,
        target: Path,
        env: dict[str, str],
    ) -> tuple[
        tuple[ProjectFactoryInitCommandEvidence, ...],
        ProjectFactoryInitBlocker | None,
    ]:
        _ensure_generated_artifact_ignores(target)
        evidence: list[ProjectFactoryInitCommandEvidence] = []
        diff = self._run_env(("git", "diff", "--", ".gitignore"), cwd=target, env=env)
        evidence.append(self._evidence(diff))
        if diff.exit_code != 0:
            return (
                tuple(evidence),
                _android_blocker_from_command(
                    code="android_preview_gitignore_repair_failed",
                    message="Generated artifact .gitignore repair could not be inspected.",
                    phase=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                    result=diff,
                    command=("git", "diff", "--", ".gitignore"),
                ),
            )
        if not diff.stdout.strip():
            return tuple(evidence), None
        if not _gitignore_repair_diff_is_safe(diff.stdout):
            return (
                tuple(evidence),
                _android_blocker(
                    phase=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                    code="android_preview_gitignore_repair_unsafe",
                    message="Generated artifact .gitignore repair is mixed with unrelated changes.",
                    next_action=(
                        "Review .gitignore manually, commit only the generated artifact "
                        "ignore repair, then rerun deterministic init."
                    ),
                    command=("git", "diff", "--", ".gitignore"),
                ),
            )
        add = self._run_env(("git", "add", ".gitignore"), cwd=target, env=env)
        evidence.append(self._evidence(add))
        if add.exit_code != 0:
            return (
                tuple(evidence),
                _android_blocker_from_command(
                    code="android_preview_gitignore_repair_failed",
                    message="Generated artifact .gitignore repair could not be staged.",
                    phase=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                    result=add,
                    command=("git", "add", ".gitignore"),
                ),
            )
        commit = self._run_env(
            ("git", "commit", "-m", "Ignore generated Project Factory artifacts"),
            cwd=target,
            env=env,
        )
        evidence.append(self._evidence(commit))
        if commit.exit_code != 0:
            return (
                tuple(evidence),
                _android_blocker_from_command(
                    code="android_preview_gitignore_repair_failed",
                    message="Generated artifact .gitignore repair could not be committed.",
                    phase=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                    result=commit,
                    command=(
                        "git",
                        "commit",
                        "-m",
                        "Ignore generated Project Factory artifacts",
                    ),
                ),
            )
        push = self._run_env(("git", "push"), cwd=target, env=env)
        evidence.append(self._evidence(push))
        if push.exit_code != 0:
            return (
                tuple(evidence),
                _android_blocker_from_command(
                    code="android_preview_gitignore_repair_failed",
                    message="Generated artifact .gitignore repair could not be pushed.",
                    phase=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                    result=push,
                    command=("git", "push"),
                ),
            )
        return tuple(evidence), None

    def _commit_generated_android_platform_repair(
        self,
        *,
        job: ProjectFactoryInitJob,
        target: Path,
        env: dict[str, str],
    ) -> tuple[
        tuple[ProjectFactoryInitCommandEvidence, ...],
        ProjectFactoryInitBlocker | None,
    ]:
        del job
        evidence: list[ProjectFactoryInitCommandEvidence] = []
        status = self._run_env(("git", "status", "--porcelain"), cwd=target, env=env)
        evidence.append(self._evidence(status))
        if status.exit_code != 0:
            return (
                tuple(evidence),
                _android_blocker_from_command(
                    code="android_preview_android_platform_repair_failed",
                    message="Generated Android platform repair could not inspect git status.",
                    phase=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                    result=status,
                    command=("git", "status", "--porcelain"),
                ),
            )
        paths = _safe_generated_android_platform_paths(status.stdout)
        if not paths:
            return (
                tuple(evidence),
                _android_blocker(
                    phase=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                    code="android_preview_android_platform_repair_unsafe",
                    message="Generated Android platform repair is mixed with unrelated changes.",
                    next_action=(
                        "Review the generated workspace, commit only Flutter Android "
                        "platform files, then rerun deterministic init."
                    ),
                    command=("git", "status", "--porcelain"),
                ),
            )
        add = self._run_env(("git", "add", *paths), cwd=target, env=env)
        evidence.append(self._evidence(add))
        if add.exit_code != 0:
            return (
                tuple(evidence),
                _android_blocker_from_command(
                    code="android_preview_android_platform_repair_failed",
                    message="Generated Android platform files could not be staged.",
                    phase=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                    result=add,
                    command=("git", "add", *paths),
                ),
            )
        commit = self._run_env(
            ("git", "commit", "-m", "Generate Flutter Android platform"),
            cwd=target,
            env=env,
        )
        evidence.append(self._evidence(commit))
        if commit.exit_code != 0:
            return (
                tuple(evidence),
                _android_blocker_from_command(
                    code="android_preview_android_platform_repair_failed",
                    message="Generated Android platform files could not be committed.",
                    phase=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                    result=commit,
                    command=("git", "commit", "-m", "Generate Flutter Android platform"),
                ),
            )
        push = self._run_env(("git", "push"), cwd=target, env=env)
        evidence.append(self._evidence(push))
        if push.exit_code != 0:
            return (
                tuple(evidence),
                _android_blocker_from_command(
                    code="android_preview_android_platform_repair_failed",
                    message="Generated Android platform commit could not be pushed.",
                    phase=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                    result=push,
                    command=("git", "push"),
                ),
            )
        return tuple(evidence), None

    def _view_repo(
        self, repo_ref: str, *, cwd: Path
    ) -> ProjectFactoryInitCommandResult:
        return self._run(
            (
                "gh",
                "repo",
                "view",
                repo_ref,
                "--json",
                "name,owner,url,defaultBranchRef,visibility",
            ),
            cwd=cwd,
        )

    def _create_repo(
        self,
        repo_ref: str,
        visibility: str,
        *,
        cwd: Path,
    ) -> ProjectFactoryInitCommandResult:
        visibility_arg = (
            f"--{visibility}"
            if visibility in {"private", "public", "internal"}
            else "--private"
        )
        return self._run(("gh", "repo", "create", repo_ref, visibility_arg), cwd=cwd)

    def _evidence(
        self,
        result: ProjectFactoryInitCommandResult,
    ) -> ProjectFactoryInitCommandEvidence:
        sensitive_values = self._service_sensitive_values(result.env)
        return ProjectFactoryInitCommandEvidence(
            argv=result.argv,
            cwd=result.cwd,
            exit_code=result.exit_code,
            stdout_summary=_summarize_output(result.stdout, sensitive_values),
            stderr_summary=_summarize_output(result.stderr, sensitive_values),
            started_at=result.started_at,
            completed_at=result.completed_at,
            redacted_env_keys=_redacted_env_keys(result.env),
        )

    def _api_evidence(
        self,
        argv: tuple[str, ...],
        payload: object,
        *,
        exit_code: int,
        cwd: Path,
    ) -> ProjectFactoryInitCommandEvidence:
        summary = json.dumps(
            _safe_json_object(payload),
            sort_keys=True,
            separators=(",", ":"),
        )
        return ProjectFactoryInitCommandEvidence(
            argv=argv,
            cwd=str(cwd),
            exit_code=exit_code,
            stdout_summary=_summarize_output(
                summary,
                self._service_sensitive_values(),
            ),
            stderr_summary="" if exit_code == 0 else "blocked",
            started_at=_now_iso(),
            completed_at=_now_iso(),
            redacted_env_keys=_redacted_env_keys(self._command_env),
        )

    def _service_sensitive_values(
        self,
        env: dict[str, str] | None = None,
    ) -> tuple[str, ...]:
        values = list(_sensitive_values(env))
        settings = self._settings
        if settings is not None:
            for value in (
                settings.cloudflare_api_token,
                settings.cloudflare_dns_api_token,
                settings.web_preview_invite_secret,
                settings.web_preview_email_api_token,
                settings.web_preview_smtp_password,
                settings.installable_apps_registration_token,
            ):
                if value:
                    values.append(value)
        return tuple(values)

    def _load_state(self) -> None:
        recovered = False
        for path in sorted(self._init_state_dir.glob("*.json")):
            try:
                job = _job_from_storage_payload(_read_json(path))
            except Exception:
                continue
            recovered_job = _recover_running_phases(job)
            if recovered_job != job:
                recovered = True
                job = recovered_job
            self._jobs[job.id] = job
        if recovered:
            for job in self._jobs.values():
                self._persist_job(job)

    def _persist_job(self, job: ProjectFactoryInitJob) -> None:
        _atomic_write_json(
            self._init_state_dir / f"{job.id}.json",
            _job_storage_payload(job),
        )

    def _status_for_response(self, job: ProjectFactoryInitJob) -> str:
        if any(
            phase.status == ProjectFactoryInitPhaseStatus.RUNNING
            for phase in job.phases
        ):
            return "running"
        if any(
            phase.status == ProjectFactoryInitPhaseStatus.QUEUED_WAITING_FOR_DOMAIN_BRIEF
            for phase in job.phases
        ):
            return "waiting_for_domain_brief"
        if all(
            phase.status
            in {
                ProjectFactoryInitPhaseStatus.QUEUED,
                ProjectFactoryInitPhaseStatus.QUEUED_WAITING_FOR_DOMAIN_BRIEF,
            }
            for phase in job.phases
        ):
            return "queued"
        return job.completion_state.value

    def _current_phase_name(
        self, job: ProjectFactoryInitJob
    ) -> ProjectFactoryInitPhaseName:
        for phase in job.phases:
            if phase.status in {
                ProjectFactoryInitPhaseStatus.RUNNING,
                ProjectFactoryInitPhaseStatus.BLOCKED,
                ProjectFactoryInitPhaseStatus.FAILED,
                ProjectFactoryInitPhaseStatus.CANCELLED,
                ProjectFactoryInitPhaseStatus.QUEUED_WAITING_FOR_DOMAIN_BRIEF,
            }:
                return phase.name
        for phase in job.phases:
            if phase.status in {
                ProjectFactoryInitPhaseStatus.QUEUED,
                ProjectFactoryInitPhaseStatus.QUEUED_WAITING_FOR_DOMAIN_BRIEF,
            }:
                return phase.name
        return job.phases[-1].name


# Backward-compatible import alias for older service tests/callers.
ProjectFactoryRemoteResource = ProjectFactoryInitRemoteResource


def _cloudflare_blocker(
    *,
    phase: ProjectFactoryInitPhaseName,
    code: str,
    message: str,
    next_action: str,
    command: tuple[str, ...] = (),
) -> ProjectFactoryInitBlocker:
    return ProjectFactoryInitBlocker(
        code=code,
        message=message,
        phase=phase,
        next_action=next_action,
        command=command,
        recoverable=True,
    )


def _frontend_blocker(
    *,
    code: str,
    message: str,
    next_action: str,
    command: tuple[str, ...] = (),
) -> ProjectFactoryInitBlocker:
    return ProjectFactoryInitBlocker(
        code=code,
        message=message,
        phase=_FRONTEND_BASELINE_PHASE,
        next_action=next_action,
        command=command,
        recoverable=True,
    )


def _frontend_blocker_from_verification(
    verification: dict[str, object],
) -> ProjectFactoryInitBlocker:
    blockers = verification.get("blockers")
    first = blockers[0] if isinstance(blockers, list) and blockers else {}
    if not isinstance(first, dict):
        first = {}
    code = str(first.get("code") or "frontend_baseline_invalid")
    message = str(first.get("message") or "Frontend baseline verification failed.")
    return _frontend_blocker(
        code=code,
        message=message,
        next_action=str(
            first.get("nextAction")
            or "Regenerate or repair the deterministic frontend baseline, then rerun init."
        ),
        command=tuple(str(part) for part in first.get("command", ()))
        if isinstance(first.get("command"), list | tuple)
        else ("project-factory", "init", "baseline", "repair"),
    )


def _verify_frontend_baseline(
    *,
    target: Path,
    slug: str,
    project_name: str,
    strategy: str,
    strategy_contract: dict[str, object],
) -> dict[str, object]:
    blockers: list[dict[str, object]] = []
    files = _frontend_expected_files(strategy)
    missing = [path for path in files if not (target / path).exists()]
    if missing:
        blockers.append(
            {
                "code": "frontend_baseline_missing",
                "message": f"Missing frontend baseline files: {', '.join(missing)}",
                "nextAction": "Restore or regenerate the generated frontend baseline, then rerun deterministic init.",
                "command": ["project-factory", "init", "baseline", "repair"],
            }
        )
    preview_url = f"https://preview.nienfos.com/{slug}"
    api_base_url = f"{preview_url}/api"
    runtime = _read_json_file(target / "release/preview-runtime.json")
    manifest_text = _read_text(target / "deploy/web-preview/web-preview-manifest.yaml")
    bridge_text = _read_text(target / "codex-bridge.yaml")
    pubspec_text = (
        _read_text(target / "apps/mobile/pubspec.yaml") if strategy == "flutter" else ""
    )
    main_text = (
        _read_text(target / "apps/mobile/lib/main.dart")
        if strategy == "flutter"
        else ""
    )
    svelte_config = (
        _read_text(target / "apps/web/src/config.ts") if strategy == "svelte" else ""
    )

    _validate_preview_runtime_contract(
        blockers,
        runtime=runtime,
        slug=slug,
        strategy=strategy,
        api_base_url=api_base_url,
        preview_url=preview_url,
    )
    _validate_no_mock_or_local_defaults(
        blockers,
        runtime=runtime,
        manifest_text=manifest_text,
    )
    if "workbench-sdd/v1" not in bridge_text or f"sourceApp: {slug}" not in bridge_text:
        blockers.append(
            {
                "code": "workbench_sdd_metadata_missing",
                "message": "codex-bridge.yaml must declare sourceApp and workbench-sdd/v1.",
                "nextAction": "Restore codex-bridge.yaml Workbench metadata and rerun init.",
                "command": ["project-factory", "init", "baseline", "repair"],
            }
        )
    if strategy == "flutter":
        _validate_flutter_feedback_updater(
            blockers, pubspec_text=pubspec_text, main_text=main_text, slug=slug
        )
        if "APP_RUNTIME_PROFILE" not in main_text or "API_RUNTIME" not in main_text:
            blockers.append(
                {
                    "code": "flutter_runtime_defines_missing",
                    "message": "Flutter main.dart must read APP_RUNTIME_PROFILE and API_RUNTIME.",
                    "nextAction": "Restore Flutter runtime profile wiring and rerun init.",
                    "command": ["project-factory", "init", "baseline", "repair"],
                }
            )
    else:
        if (
            "VITE_API_BASE_URL" not in svelte_config
            or api_base_url not in svelte_config
        ):
            blockers.append(
                {
                    "code": "svelte_preview_api_wiring_missing",
                    "message": "Svelte config must default to the real preview API URL.",
                    "nextAction": "Restore Svelte preview runtime config and rerun init.",
                    "command": ["project-factory", "init", "baseline", "repair"],
                }
            )
    capabilities = {
        "strategy": strategy,
        "supportsAndroidPreviewApk": bool(
            strategy_contract.get("supports_android_preview_apk")
        ),
        "supportsBridgeInstallableApp": bool(
            strategy_contract.get("supports_bridge_installable_app")
        ),
        "supportsWorkbenchApkEntry": bool(
            strategy_contract.get("supports_workbench_apk_entry")
        ),
        "sourceRoot": strategy_contract.get("source_root"),
    }
    return {
        "ok": not blockers,
        "target": str(target),
        "sourceApp": slug,
        "displayName": project_name,
        "strategy": strategy,
        "files": {"expected": files, "missing": missing},
        "runtime": {
            "previewUrl": runtime.get("previewUrl")
            if isinstance(runtime, dict)
            else None,
            "apiBaseUrl": runtime.get("apiBaseUrl")
            if isinstance(runtime, dict)
            else None,
            "runtimeProfile": runtime.get("runtimeProfile")
            if isinstance(runtime, dict)
            else None,
            "apiRuntime": runtime.get("apiRuntime")
            if isinstance(runtime, dict)
            else None,
            "dataPersistence": runtime.get("dataPersistence")
            if isinstance(runtime, dict)
            else None,
            "mockOrDemo": runtime.get("mockOrDemo")
            if isinstance(runtime, dict)
            else None,
        },
        "workbench": {
            "sourceApp": slug,
            "workspacePath": str(target),
            "workbenchScopeId": f"workspace:{target}",
            "sddStandard": "workbench-sdd/v1"
            if "workbench-sdd/v1" in bridge_text
            else None,
            "bridgeOwnedWorkbench": True,
        },
        "feedbackUpdater": _feedback_updater_evidence(
            strategy, pubspec_text, main_text
        ),
        "capabilities": capabilities,
        "blockers": blockers,
    }


def _frontend_expected_files(strategy: str) -> list[str]:
    common = [
        ".codex/project.yaml",
        "codex-bridge.yaml",
        "deploy/web-preview/web-preview-manifest.yaml",
        "release/preview-runtime.json",
        "scripts/build_web_preview.sh",
        "scripts/validate_web_preview.sh",
        "specs/001-product-foundation/spec.md",
        "specs/001-product-foundation/tasks.md",
        "specs/001-product-foundation/tree.json",
    ]
    if strategy == "svelte":
        return [
            *common,
            "apps/web/package.json",
            "apps/web/src/config.ts",
            "apps/web/src/main.ts",
        ]
    return [
        *common,
        "apps/mobile/pubspec.yaml",
        "apps/mobile/lib/main.dart",
        "apps/mobile/lib/src/config.dart",
        "apps/mobile/android/app/src/main/AndroidManifest.xml",
        "apps/mobile/web/index.html",
        "apps/mobile/web/manifest.json",
    ]


def _validate_preview_runtime_contract(
    blockers: list[dict[str, object]],
    *,
    runtime: object,
    slug: str,
    strategy: str,
    api_base_url: str,
    preview_url: str,
) -> None:
    if not isinstance(runtime, dict):
        blockers.append(
            {
                "code": "preview_runtime_contract_missing",
                "message": "release/preview-runtime.json is missing or invalid.",
                "nextAction": "Restore release/preview-runtime.json and rerun init.",
                "command": ["project-factory", "init", "baseline", "repair"],
            }
        )
        return
    expected = {
        "sourceApp": slug,
        "frontendStrategy": strategy,
        "previewUrl": preview_url,
        "apiBaseUrl": api_base_url,
        "runtimeProfile": "preview",
        "apiRuntime": "cloudflare_preview",
        "mockOrDemo": False,
        "dataPersistence": "cloudflare_d1",
        "d1PreviewRequired": True,
    }
    for key, value in expected.items():
        if runtime.get(key) != value:
            blockers.append(
                {
                    "code": "preview_runtime_contract_invalid",
                    "message": f"preview runtime {key} must be {value!r}.",
                    "nextAction": "Restore real Cloudflare preview runtime contract and rerun init.",
                    "command": ["project-factory", "init", "baseline", "repair"],
                }
            )
            return


_GENERATED_ARTIFACT_GITIGNORE_ENTRIES = (
    ".generated-validation/",
    "backend/.venv/",
    "backend/*.egg-info/",
)

_EXISTING_BASELINE_MANAGED_REFRESH_FILES = (
    "scripts/publish_android_preview_release.sh",
    "scripts/register_installable_app.sh",
)


def _ensure_generated_artifact_ignores(target: Path) -> tuple[str, ...]:
    gitignore = target / ".gitignore"
    existing_text = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    existing_entries = {
        line.strip()
        for line in existing_text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    missing = tuple(
        entry
        for entry in _GENERATED_ARTIFACT_GITIGNORE_ENTRIES
        if entry not in existing_entries
    )
    if not missing:
        return ()
    prefix = existing_text
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    gitignore.write_text(prefix + "\n".join(missing) + "\n", encoding="utf-8")
    return missing


def _release_failed_due_generated_gitignore_repair(
    result: ProjectFactoryInitCommandResult,
) -> bool:
    output = f"{result.stdout}\n{result.stderr}"
    return (
        result.exit_code != 0
        and "working tree must be clean before tagging the preview release" in output
        and "M .gitignore" in output
    )


def _release_failed_due_android_platform_repair(
    result: ProjectFactoryInitCommandResult,
) -> bool:
    output = f"{result.stdout}\n{result.stderr}"
    return (
        result.exit_code != 0
        and "working tree must be clean before tagging the preview release" in output
        and (
            "apps/mobile/android/" in output
            or "apps/mobile/.metadata" in output
            or "apps/mobile/analysis_options.yaml" in output
        )
    )


def _safe_generated_android_platform_paths(status: str) -> tuple[str, ...]:
    paths: list[str] = []
    for line in status.splitlines():
        if len(line) < 4:
            return ()
        state = line[:2]
        path = line[3:].strip()
        if not path or state.strip() not in {"??", "M"}:
            return ()
        if not _is_generated_android_platform_path(path):
            return ()
        paths.append(path)
    return tuple(paths)


def _is_generated_android_platform_path(path: str) -> bool:
    if path.startswith("apps/mobile/android/"):
        return True
    if path.startswith("apps/mobile/.idea/"):
        return True
    if path.startswith("apps/mobile/") and path.endswith(".iml"):
        return True
    return path in {
        "apps/mobile/.gitignore",
        "apps/mobile/.metadata",
    }


def _gitignore_repair_diff_is_safe(diff: str) -> bool:
    added: list[str] = []
    for line in diff.splitlines():
        if line.startswith(("diff --git", "index ", "@@ ", "+++ ", "--- ")):
            continue
        if line.startswith("-"):
            return False
        if line.startswith("+"):
            value = line[1:].strip()
            if value:
                added.append(value)
            continue
    return bool(added) and all(
        value in _GENERATED_ARTIFACT_GITIGNORE_ENTRIES for value in added
    )


def _validate_no_mock_or_local_defaults(
    blockers: list[dict[str, object]],
    *,
    runtime: object,
    manifest_text: str,
) -> None:
    runtime_blob = (
        json.dumps(runtime, sort_keys=True) if isinstance(runtime, dict) else ""
    )
    combined = "\n".join([runtime_blob, manifest_text]).lower()
    forbidden = [
        "http://localhost",
        "https://localhost",
        "127.0.0.1",
        "10.0.2.2",
        "example.com",
        "placeholder",
        'mockordemo": true',
        "mock_or_demo: true",
        "runtime_profile: mock",
        "app_runtime_profile=mock",
    ]
    for marker in forbidden:
        if marker in combined:
            blockers.append(
                {
                    "code": "preview_runtime_mock_or_local_blocked",
                    "message": f"Preview runtime default contains forbidden marker: {marker}",
                    "nextAction": "Replace mock/local/placeholder defaults with the real Cloudflare preview API and D1 contract.",
                    "command": ["project-factory", "init", "baseline", "repair"],
                }
            )
            return


def _validate_flutter_feedback_updater(
    blockers: list[dict[str, object]],
    *,
    pubspec_text: str,
    main_text: str,
    slug: str,
) -> None:
    required_pubspec = [
        "codex_developer_feedback_template:",
        "codex_app_updater:",
        "codex_bridge_workbench:",
    ]
    required_main = [
        "DeveloperFeedbackTemplate",
        "CodexAppUpdater",
        "CodexBridgeDevModeWrapper",
        "CODEX_FEEDBACK_BRIDGE_URL",
        "CODEX_BRIDGE_WORKBENCH_URL",
        "CODEX_APP_UPDATER_BRIDGE_URL",
        "sourceApp: config.appSlug",
        "bridgeUrl: config.feedbackBridgeUrl",
        "bridgeUrl: config.updaterBridgeUrl",
        "workspacePath: config.appSlug",
    ]
    missing = [
        item
        for item in [*required_pubspec, *required_main]
        if item not in (pubspec_text if item.endswith(":") else main_text)
    ]
    if missing:
        blockers.append(
            {
                "code": "feedback_updater_wiring_missing",
                "message": f"Missing feedback/updater/workbench wiring for {slug}: {', '.join(missing)}",
                "nextAction": "Restore generated Flutter feedback/updater/workbench wiring and rerun init.",
                "command": ["project-factory", "init", "baseline", "repair"],
            }
        )


def _feedback_updater_evidence(
    strategy: str,
    pubspec_text: str,
    main_text: str,
) -> dict[str, object]:
    if strategy != "flutter":
        return {
            "feedbackTemplate": "not_applicable",
            "appUpdater": "not_applicable",
            "bridgeWorkbench": "not_applicable",
        }
    return {
        "feedbackTemplate": "codex_developer_feedback_template:" in pubspec_text
        and "DeveloperFeedbackTemplate" in main_text,
        "appUpdater": "codex_app_updater:" in pubspec_text
        and "CodexAppUpdater" in main_text,
        "bridgeWorkbench": "codex_bridge_workbench:" in pubspec_text
        and "CodexBridgeDevModeWrapper" in main_text,
        "bridgeUrlSeparatedFromBusinessApi": (
            "CODEX_FEEDBACK_BRIDGE_URL" in main_text
            and "CODEX_APP_UPDATER_BRIDGE_URL" in main_text
            and "workbenchBridgeUrl: apiBaseUrl" not in main_text
        ),
    }


def _cloudflare_doctor_blocker(payload: dict[str, object]) -> ProjectFactoryInitBlocker:
    checks = _expect_sequence(payload.get("checks"))
    failed = next(
        (
            item
            for item in checks
            if isinstance(item, dict) and item.get("ok") is not True
        ),
        {},
    )
    code = str(failed.get("code") or payload.get("status") or "cloudflare_blocked")
    detail = str(
        failed.get("detail") or failed.get("message") or "Cloudflare is blocked."
    )
    return _cloudflare_blocker(
        phase=_CLOUDFLARE_PROVISION_PHASE,
        code=f"cloudflare_{code}",
        message=detail,
        next_action=_cloudflare_doctor_next_action(code, detail),
        command=_cloudflare_doctor_command(code),
    )


def _cloudflare_doctor_next_action(code: str, detail: str) -> str:
    if "token" in code:
        return "Configure the required Cloudflare token on the bridge host, then rerun deterministic init."
    if "account_id" in code:
        return "Set CLOUDFLARE_ACCOUNT_ID on the bridge host, then rerun deterministic init."
    if "zone_id" in code:
        return (
            "Set CLOUDFLARE_ZONE_ID on the bridge host, then rerun deterministic init."
        )
    if code == "web_preview_apply_enabled":
        return "Set WEB_PREVIEW_APPLY_ENABLED=true after confirming Cloudflare apply is allowed."
    if code == "preview_dns_record":
        return (
            "Create or repair the preview CNAME record, then rerun deterministic init."
        )
    if "workers" in code or "worker" in code:
        return "Grant Cloudflare Workers and Routes permissions, then rerun deterministic init."
    if "d1" in code:
        return (
            "Grant Cloudflare D1 read/write permissions, then rerun deterministic init."
        )
    return detail or "Fix the Cloudflare blocker, then rerun deterministic init."


def _cloudflare_doctor_command(code: str) -> tuple[str, ...]:
    commands = {
        "cloudflare_platform_token_configured": (
            "export",
            "CLOUDFLARE_API_TOKEN=<token>",
        ),
        "cloudflare_dns_token_configured": (
            "export",
            "CLOUDFLARE_DNS_API_TOKEN=<token>",
        ),
        "cloudflare_account_id_configured": (
            "export",
            "CLOUDFLARE_ACCOUNT_ID=<account-id>",
        ),
        "cloudflare_zone_id_configured": (
            "export",
            "CLOUDFLARE_ZONE_ID=<zone-id>",
        ),
        "web_preview_apply_enabled": (
            "export",
            "WEB_PREVIEW_APPLY_ENABLED=true",
        ),
    }
    return commands.get(code, ())


def _github_blocker(
    *,
    code: str,
    message: str,
    next_action: str,
    command: tuple[str, ...] = (),
) -> ProjectFactoryInitBlocker:
    return ProjectFactoryInitBlocker(
        code=code,
        message=message,
        phase=_GITHUB_PHASE,
        next_action=next_action,
        command=command,
        recoverable=True,
    )


def _preview_url(base_domain: str, slug: str) -> str:
    domain = (base_domain or "").strip().strip("/")
    if not domain:
        return ""
    return f"https://{domain}/{slug.strip('/')}"


def _cloudflare_remote_resources(
    applied: list[object],
) -> tuple[ProjectFactoryInitRemoteResource, ...]:
    resources: list[ProjectFactoryInitRemoteResource] = []
    for raw in applied:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or "")
        name = str(raw.get("name") or "")
        status = str(raw.get("status") or "unknown")
        metadata = _safe_json_object(raw)
        if kind == "worker_script" and name:
            resources.append(
                ProjectFactoryInitRemoteResource(
                    type=ProjectFactoryInitRemoteResourceType.CLOUDFLARE_WORKER,
                    identifier=name,
                    display_name=name,
                    provider="cloudflare",
                    status=status,
                    metadata=metadata,
                )
            )
        elif kind == "worker_route" and name:
            resources.append(
                ProjectFactoryInitRemoteResource(
                    type=ProjectFactoryInitRemoteResourceType.CLOUDFLARE_ROUTE,
                    identifier=name,
                    display_name=name,
                    provider="cloudflare",
                    status=status,
                    metadata=metadata,
                )
            )
        elif kind == "d1_database" and name:
            resources.append(
                ProjectFactoryInitRemoteResource(
                    type=ProjectFactoryInitRemoteResourceType.CLOUDFLARE_D1_DATABASE,
                    identifier=name,
                    display_name=name,
                    provider="cloudflare",
                    status=status,
                    metadata=metadata,
                )
            )
    return tuple(resources)


def _cloudflare_migration_artifacts(
    applied: list[object],
) -> tuple[ProjectFactoryInitArtifact, ...]:
    artifacts: list[ProjectFactoryInitArtifact] = []
    for raw in applied:
        if isinstance(raw, dict) and raw.get("kind") == "d1_migration":
            artifacts.append(
                ProjectFactoryInitArtifact(
                    kind="cloudflare_d1_migration",
                    path=str(raw.get("name") or ""),
                    metadata=_safe_json_object(raw),
                )
            )
    return tuple(artifacts)


def _latest_health_checks(health: object) -> list[object]:
    if not isinstance(health, dict):
        return []
    attempts = health.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        return []
    latest = attempts[-1]
    if not isinstance(latest, dict):
        return []
    checks = latest.get("checks")
    return checks if isinstance(checks, list) else []


def _cloudflare_error_phase(code: str, message: str) -> ProjectFactoryInitPhaseName:
    text = f"{code} {message}".lower()
    if "preview_health" in text or "smoke" in text:
        return _PREVIEW_SMOKE_PHASE
    if "health" in text or "mime" in text or "cache" in text:
        return _CLOUDFLARE_DEPLOY_PHASE
    return _CLOUDFLARE_PROVISION_PHASE


def _cloudflare_error_code(code: str, message: str) -> str:
    text = f"{code} {message}".lower()
    if "preview_health" in text or "smoke" in text:
        return "cloudflare_smoke_blocked"
    if "d1" in text:
        return "cloudflare_d1_blocked"
    if "worker_route" in text or "route" in text:
        return "cloudflare_route_blocked"
    if "worker" in text:
        return "cloudflare_worker_blocked"
    if code == "cloudflare_configuration_missing":
        return "cloudflare_configuration_missing"
    return f"cloudflare_{code}"


def _cloudflare_error_next_action(code: str, message: str) -> str:
    text = f"{code} {message}".lower()
    if "d1" in text:
        return "Fix D1 access, database identity, or migration SQL, then rerun deterministic init."
    if "route" in text:
        return "Fix Cloudflare Worker route access/configuration, then rerun deterministic init."
    if "worker" in text:
        return "Fix Worker script access/deploy permissions, then rerun deterministic init."
    if "health" in text or "smoke" in text:
        return "Open the preview health URLs, fix failed bindings or runtime health, then rerun deterministic init."
    if code == "cloudflare_configuration_missing":
        return "Configure Cloudflare credentials and WEB_PREVIEW_APPLY_ENABLED=true, then rerun deterministic init."
    return "Fix the Cloudflare preview deploy blocker, then rerun deterministic init."


def _cloudflare_error_command(
    code: str,
    message: str,
    settings: Settings | None,
) -> tuple[str, ...]:
    text = f"{code} {message}".lower()
    if "d1" in text:
        database = settings.preview_d1_database_name if settings else "<database>"
        return (
            "wrangler",
            "d1",
            "execute",
            database,
            "--remote",
            "--file",
            "deploy/web-preview/d1/migrations/<migration>.sql",
        )
    if "health" in text or "smoke" in text:
        base = settings.preview_base_domain if settings else "preview.example.com"
        return ("curl", "-fsS", f"https://{base}/<slug>/api/health")
    if "worker" in text or "route" in text:
        return ("wrangler", "deploy", "deploy/web-preview/wrangler.toml")
    if code == "cloudflare_configuration_missing":
        return ("export", "WEB_PREVIEW_APPLY_ENABLED=true")
    return ()


def _safe_json_object(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return {str(key): _safe_json_value(item) for key, item in value.items()}
    return {"value": _safe_json_value(value)}


def _safe_json_value(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _safe_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_safe_json_value(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _empty_initial_admin_invite_config(source: str) -> dict[str, object]:
    return {"emails": (), "role": "owner", "required": False, "source": source}


def _initial_admin_invite_config_from_manifest(target: Path) -> dict[str, object]:
    path = target / ".codex" / "project.yaml"
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return _empty_initial_admin_invite_config("manifest")
    if not isinstance(payload, dict):
        return _empty_initial_admin_invite_config("manifest")
    admin = payload.get("admin")
    initial_invites = admin.get("initial_invites") if isinstance(admin, dict) else None
    return {
        "emails": _normalize_invite_emails(
            initial_invites.get("emails") if isinstance(initial_invites, dict) else None
        ),
        "role": _invite_role(initial_invites),
        "required": _invite_required(initial_invites),
        "source": "manifest",
    }


def _normalize_invite_emails(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    emails: list[str] = []
    seen: set[str] = set()
    for item in value:
        email = str(item or "").strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        emails.append(email)
    return tuple(emails)


def _invite_role(initial_invites: object) -> str:
    if not isinstance(initial_invites, dict):
        return "owner"
    role = str(initial_invites.get("default_role") or "owner").strip().lower()
    return role or "owner"


def _invite_required(initial_invites: object) -> bool:
    return (
        isinstance(initial_invites, dict)
        and initial_invites.get("required_for_web_preview") is True
    )


def _is_active_invite(invite: dict[str, object]) -> bool:
    if invite.get("revoked_at") or invite.get("expired_at"):
        return False
    expires_at = _parse_optional_iso_datetime(invite.get("expires_at"))
    return expires_at is None or expires_at > datetime.now(UTC)


def _parse_optional_iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _safe_invite_result(invite: dict[str, object]) -> dict[str, object]:
    return {
        "inviteId": str(invite.get("invite_id") or ""),
        "email": str(invite.get("email") or ""),
        "role": str(invite.get("role") or ""),
        "status": str(invite.get("email_delivery_status") or ""),
        "provider": str(invite.get("email_provider") or ""),
        "manualDeliveryRequired": bool(invite.get("manual_delivery_required")),
        "syncStatus": str(invite.get("sync_status") or ""),
        "syncedAt": invite.get("synced_at"),
    }


def _expect_sequence(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _recover_running_phases(job: ProjectFactoryInitJob) -> ProjectFactoryInitJob:
    updated = job
    for phase in updated.phases:
        if phase.status == ProjectFactoryInitPhaseStatus.RUNNING:
            updated = updated.with_phase(
                replace(
                    phase,
                    status=ProjectFactoryInitPhaseStatus.QUEUED,
                    message=phase.message or "Recovered interrupted init phase.",
                    completed_at=None,
                )
            )
    return updated.with_derived_completion_state()


def _merge_artifacts(
    existing: tuple[ProjectFactoryInitArtifact, ...],
    new_items: tuple[ProjectFactoryInitArtifact, ...],
) -> tuple[ProjectFactoryInitArtifact, ...]:
    items = {(item.kind, item.path, item.url): item for item in existing}
    for item in new_items:
        items[(item.kind, item.path, item.url)] = item
    return tuple(items.values())


def _merge_blockers(
    existing: tuple[ProjectFactoryInitBlocker, ...],
    new_items: tuple[ProjectFactoryInitBlocker, ...],
) -> tuple[ProjectFactoryInitBlocker, ...]:
    items = {(item.phase, item.code): item for item in existing}
    for item in new_items:
        items[(item.phase, item.code)] = item
    return tuple(items.values())


def _job_storage_payload(job: ProjectFactoryInitJob) -> dict[str, object]:
    return {
        "kind": "codex.projectFactoryInitJob.storage",
        "version": 2,
        "payload": job.to_payload(),
    }


def _job_from_storage_payload(payload: dict[str, object]) -> ProjectFactoryInitJob:
    job_payload = _expect_mapping(payload["payload"])
    if "jobId" in job_payload:
        return ProjectFactoryInitJob.from_payload(job_payload)
    return _legacy_job_from_payload(job_payload)


def _legacy_job_from_payload(payload: dict[str, object]) -> ProjectFactoryInitJob:
    relationships = ProjectFactoryInitRelationships(
        draft_id=str(payload["draftId"]),
        chat_session_id=_optional_str(payload.get("chatSessionId")),
        init_job_id=str(payload["initJobId"]),
        generated_workspace_path=_optional_str(
            payload.get("generatedWorkspacePath") or payload.get("workspacePath")
        ),
    )
    phases = _phases_in_current_order(
        tuple(
            _legacy_phase_from_payload(_expect_mapping(item))
            for item in payload.get("phases", [])
            if isinstance(item, dict)
        )
        or tuple(ProjectFactoryInitPhase(name=phase) for phase in INIT_PHASE_ORDER)
    )
    job = ProjectFactoryInitJob(
        id=str(payload["initJobId"]),
        relationships=relationships,
        created_at=str(payload["createdAt"]),
        updated_at=str(payload["updatedAt"]),
        project_name=_DEFAULT_PROJECT_NAME,
        slug=_slug_from_name(str(payload.get("draftId") or "new-project")),
        frontend_strategy=_DEFAULT_FRONTEND_STRATEGY,
        phases=phases,
        remote_resources=tuple(
            _legacy_remote_resource_from_payload(_expect_mapping(item))
            for item in payload.get("remoteResources", [])
            if isinstance(item, dict)
        ),
        context_pack=_legacy_context_pack_from_payload(
            _expect_mapping(payload["contextPack"])
        )
        if isinstance(payload.get("contextPack"), dict)
        else None,
    )
    return job.with_derived_completion_state()


def _legacy_phase_from_payload(payload: dict[str, object]) -> ProjectFactoryInitPhase:
    status = str(payload.get("status") or "queued")
    if status == "pending":
        status = ProjectFactoryInitPhaseStatus.QUEUED.value
    return ProjectFactoryInitPhase(
        name=ProjectFactoryInitPhaseName(str(payload["name"])),
        status=ProjectFactoryInitPhaseStatus(status),
        message=str(payload.get("message") or ""),
        started_at=_optional_str(payload.get("startedAt")),
        completed_at=_optional_str(payload.get("completedAt")),
        command_evidence=tuple(
            ProjectFactoryInitCommandEvidence(
                argv=tuple(str(part) for part in item.get("argv", [])),
                cwd=_optional_str(item.get("cwd")),
                exit_code=int(item["exitCode"])
                if item.get("exitCode") is not None
                else None,
                stdout_summary=str(
                    item.get("stdoutSummary") or item.get("stdout") or ""
                ),
                stderr_summary=str(
                    item.get("stderrSummary") or item.get("stderr") or ""
                ),
                started_at=_optional_str(item.get("startedAt")),
                completed_at=_optional_str(item.get("completedAt")),
            )
            for item in (
                _expect_mapping(raw)
                for raw in payload.get("commandEvidence", [])
                if isinstance(raw, dict)
            )
        ),
        blockers=tuple(
            ProjectFactoryInitBlocker(
                code=str(item["code"]),
                message=str(item.get("message") or ""),
                phase=ProjectFactoryInitPhaseName(str(payload["name"])),
                next_action=str(
                    item.get("nextAction")
                    or " ".join(
                        shlex.join(tuple(command))
                        for command in item.get("retryCommands", [])
                    )
                ),
                command=tuple(str(part) for part in item.get("command", [])),
            )
            for item in (
                _expect_mapping(raw)
                for raw in payload.get("blockers", [])
                if isinstance(raw, dict)
            )
        ),
        artifacts=tuple(
            ProjectFactoryInitArtifact(
                kind=str(item["kind"]),
                path=_optional_str(item.get("path")),
                sha256=_optional_str(item.get("sha256")),
                metadata={"description": str(item.get("description") or "")},
            )
            for item in (
                _expect_mapping(raw)
                for raw in payload.get("artifacts", [])
                if isinstance(raw, dict)
            )
        ),
    )


def _legacy_remote_resource_from_payload(
    payload: dict[str, object],
) -> ProjectFactoryInitRemoteResource:
    raw_type = str(payload.get("type") or payload.get("kind") or "github_repository")
    resource_type = ProjectFactoryInitRemoteResourceType(raw_type)
    metadata = payload.get("metadata")
    return ProjectFactoryInitRemoteResource(
        type=resource_type,
        identifier=str(payload["identifier"]),
        display_name=str(payload.get("displayName") or payload["identifier"]),
        url=_optional_str(payload.get("url")),
        provider="github" if resource_type.name.startswith("GITHUB") else None,
        status=str(payload.get("status") or "unknown"),
        metadata=dict(metadata) if isinstance(metadata, dict) else {},
    )


def _legacy_context_pack_from_payload(
    payload: dict[str, object],
) -> ProjectFactoryInitContextPack:
    return ProjectFactoryInitContextPack(
        init_result_path=str(payload["initResultPath"]),
        llm_start_context_path=str(payload["llmStartContextPath"]),
        content_sha256=str(payload.get("contentSha256") or payload.get("sha256") or ""),
        attached_to_chat=bool(payload.get("attachedSessionId")),
    )


def _remote_resource_response_payload(
    resource: ProjectFactoryInitRemoteResource,
) -> dict[str, object]:
    payload = resource.to_payload()
    payload["kind"] = resource.type.value
    return payload


def _redacted_init_job(
    job: ProjectFactoryInitJob,
    *,
    sensitive_values: tuple[str, ...],
) -> ProjectFactoryInitJob:
    phases = tuple(
        replace(
            phase,
            message=_redact_context_text(phase.message, sensitive_values),
            command_evidence=tuple(
                replace(
                    evidence,
                    stdout_summary=_redact_context_text(
                        evidence.stdout_summary,
                        sensitive_values,
                    ),
                    stderr_summary=_redact_context_text(
                        evidence.stderr_summary,
                        sensitive_values,
                    ),
                )
                for evidence in phase.command_evidence
            ),
            blockers=tuple(
                replace(
                    blocker,
                    message=_redact_context_text(blocker.message, sensitive_values),
                    next_action=_redact_context_text(
                        blocker.next_action,
                        sensitive_values,
                    ),
                    command=tuple(
                        _redact_context_text(part, sensitive_values)
                        for part in blocker.command
                    ),
                )
                for blocker in phase.blockers
            ),
            artifacts=tuple(
                replace(
                    artifact,
                    path=_redact_optional_text(artifact.path, sensitive_values),
                    url=_redact_optional_text(artifact.url, sensitive_values),
                    metadata=_redact_context_value(
                        artifact.metadata,
                        sensitive_values,
                    ),
                )
                for artifact in phase.artifacts
            ),
        )
        for phase in job.phases
    )
    resources = tuple(
        replace(
            resource,
            identifier=_redact_context_text(resource.identifier, sensitive_values),
            display_name=_redact_context_text(resource.display_name, sensitive_values),
            url=_redact_optional_text(resource.url, sensitive_values),
            metadata=_redact_context_value(resource.metadata, sensitive_values),
        )
        for resource in job.remote_resources
    )
    return replace(job, phases=phases, remote_resources=resources)


def _context_pack_result_payload(
    job: ProjectFactoryInitJob,
    *,
    target: Path,
    sensitive_values: tuple[str, ...],
) -> dict[str, object]:
    blockers = [
        {
            **blocker.to_payload(),
            "phaseStatus": phase.status.value,
        }
        for phase in job.phases
        for blocker in phase.blockers
    ]
    phases = [_context_phase_payload(phase) for phase in job.phases]
    pending_work = _context_pending_work(job)
    llm_guidance = _llm_operational_guidance()
    remote_resources = [
        _remote_resource_response_payload(resource) for resource in job.remote_resources
    ]
    payload: dict[str, object] = {
        "kind": "codex.projectFactoryInitResult",
        "version": 1,
        "draftId": job.relationships.draft_id,
        "initJobId": job.id,
        "chatSessionId": job.relationships.chat_session_id,
        "projectName": job.project_name,
        "slug": job.slug,
        "sourceApp": job.slug,
        "frontendStrategy": job.frontend_strategy,
        "projectPath": str(target),
        "workspacePath": job.relationships.generated_workspace_path or str(target),
        "workbenchScopeId": job.relationships.workbench_scope_id,
        "completionState": job.completion_state.value,
        "currentPhase": _context_current_phase(job).value,
        "readyForBusinessLlm": _context_ready_for_business_llm(job),
        "canContinueWithBlockedContext": bool(blockers),
        "blockedWithContext": bool(blockers),
        "hasBlockers": bool(blockers),
        "relationships": job.relationships.to_payload(),
        "phases": phases,
        "phaseStatuses": {phase.name.value: phase.status.value for phase in job.phases},
        "pendingDeterministicWork": pending_work,
        "llmOperationalGuidance": llm_guidance,
        "blockers": blockers,
        "remoteResources": remote_resources,
        "artifacts": [
            {
                "phase": phase.name.value,
                **artifact.to_payload(),
            }
            for phase in job.phases
            for artifact in phase.artifacts
        ],
        "resources": _context_resource_summary(job),
        "businessPhaseRules": _business_phase_rules(),
    }
    return _redact_context_value(payload, sensitive_values)


def _context_phase_payload(phase: ProjectFactoryInitPhase) -> dict[str, object]:
    return {
        "name": phase.name.value,
        "status": phase.status.value,
        "message": phase.message,
        "startedAt": phase.started_at,
        "completedAt": phase.completed_at,
        "commandEvidence": [
            {
                "argv": list(evidence.argv),
                "cwd": evidence.cwd,
                "exitCode": evidence.exit_code,
                "stdoutSummary": evidence.stdout_summary,
                "stderrSummary": evidence.stderr_summary,
                "redactedEnvKeys": list(evidence.redacted_env_keys),
            }
            for evidence in phase.command_evidence
        ],
        "blockers": [blocker.to_payload() for blocker in phase.blockers],
        "artifacts": [artifact.to_payload() for artifact in phase.artifacts],
    }


def _context_current_phase(job: ProjectFactoryInitJob) -> ProjectFactoryInitPhaseName:
    for phase in job.phases:
        if phase.status in {
            ProjectFactoryInitPhaseStatus.RUNNING,
            ProjectFactoryInitPhaseStatus.BLOCKED,
            ProjectFactoryInitPhaseStatus.FAILED,
            ProjectFactoryInitPhaseStatus.CANCELLED,
            ProjectFactoryInitPhaseStatus.QUEUED_WAITING_FOR_DOMAIN_BRIEF,
        }:
            return phase.name
    for phase in job.phases:
        if phase.status in {
            ProjectFactoryInitPhaseStatus.QUEUED,
            ProjectFactoryInitPhaseStatus.QUEUED_WAITING_FOR_DOMAIN_BRIEF,
        }:
            return phase.name
    return job.phases[-1].name


def _context_ready_for_business_llm(job: ProjectFactoryInitJob) -> bool:
    terminal = {
        ProjectFactoryInitPhaseStatus.COMPLETED,
        ProjectFactoryInitPhaseStatus.SKIPPED,
    }
    for phase in job.phases:
        if phase.name == ProjectFactoryInitPhaseName.LLM_CONTEXT_PACK:
            return phase.status in terminal
        if phase.status not in terminal:
            return False
    return False


def _context_pending_work(job: ProjectFactoryInitJob) -> list[dict[str, object]]:
    pending_statuses = {
        ProjectFactoryInitPhaseStatus.QUEUED,
        ProjectFactoryInitPhaseStatus.QUEUED_WAITING_FOR_DOMAIN_BRIEF,
        ProjectFactoryInitPhaseStatus.RUNNING,
    }
    current_phase = _context_current_phase(job)
    pending: list[dict[str, object]] = []
    for phase in job.phases:
        if phase.name == ProjectFactoryInitPhaseName.LLM_CONTEXT_PACK:
            continue
        if phase.status not in pending_statuses:
            continue
        pending.append(
            {
                "phase": phase.name.value,
                "status": phase.status.value,
                "current": phase.name == current_phase,
                "message": phase.message,
                "llmDisposition": "wait_for_deterministic_init",
                "isBlocker": False,
            }
        )
    return pending


def _llm_operational_guidance() -> list[str]:
    return [
        "Only treat entries in blockers[] as user-actionable blockers.",
        "Do not infer blockers from missing remote resources while the owning deterministic phase is queued or running.",
        "For github_repository, a missing GitHub repository before gh repo create completes is expected pending work, not a blocker.",
        "Ask the user for GitHub help only when blockers[] contains an explicit github_* blocker such as github_owner_missing, github_auth_required, github_repo_create_failed, or github_push_failed.",
    ]


def _context_resource_summary(job: ProjectFactoryInitJob) -> dict[str, object]:
    resources = job.remote_resources
    github_repo = _first_resource(
        resources, ProjectFactoryInitRemoteResourceType.GITHUB_REPOSITORY
    )
    github_branch = _first_resource(
        resources, ProjectFactoryInitRemoteResourceType.GITHUB_BRANCH
    )
    preview_url = _first_resource(
        resources, ProjectFactoryInitRemoteResourceType.PREVIEW_URL
    )
    api_base_url = _first_resource(
        resources, ProjectFactoryInitRemoteResourceType.API_BASE_URL
    )
    worker = _first_resource(
        resources, ProjectFactoryInitRemoteResourceType.CLOUDFLARE_WORKER
    )
    route = _first_resource(
        resources, ProjectFactoryInitRemoteResourceType.CLOUDFLARE_ROUTE
    )
    d1 = _first_resource(
        resources, ProjectFactoryInitRemoteResourceType.CLOUDFLARE_D1_DATABASE
    )
    release = _first_resource(
        resources, ProjectFactoryInitRemoteResourceType.GITHUB_RELEASE
    )
    installable = _first_resource(
        resources, ProjectFactoryInitRemoteResourceType.BRIDGE_INSTALLABLE_APP
    )
    frontend_phase = job.phase(ProjectFactoryInitPhaseName.FLUTTER_OR_STRATEGY_BASELINE)
    artifacts = {artifact.kind: artifact for artifact in frontend_phase.artifacts}
    return {
        "github": {
            "repoUrl": github_repo.url if github_repo else None,
            "ownerName": github_repo.display_name if github_repo else None,
            "branch": github_branch.identifier if github_branch else None,
            "status": github_branch.status if github_branch else None,
        },
        "cloudflarePreview": {
            "previewUrl": preview_url.url if preview_url else None,
            "apiBaseUrl": api_base_url.url if api_base_url else None,
            "worker": worker.to_payload() if worker else None,
            "route": route.to_payload() if route else None,
            "d1": d1.to_payload() if d1 else None,
        },
        "androidPreviewRelease": {
            "releaseTag": release.identifier if release else None,
            "releaseUrl": release.url if release else None,
            "status": release.status if release else None,
            "apkSha256": release.metadata.get("apkSha256") if release else None,
            "asset": release.metadata.get("asset") if release else None,
        },
        "bridgeInstallable": {
            "sourceApp": installable.identifier if installable else None,
            "url": installable.url if installable else None,
            "status": installable.status if installable else None,
            "metadata": installable.metadata if installable else None,
        },
        "workbenchAndFeedback": {
            "workbenchStatus": artifacts.get("workbench_sdd_metadata").metadata
            if artifacts.get("workbench_sdd_metadata")
            else None,
            "feedbackUpdaterStatus": artifacts.get("feedback_updater_wiring").metadata
            if artifacts.get("feedback_updater_wiring")
            else None,
        },
    }


def _first_resource(
    resources: tuple[ProjectFactoryInitRemoteResource, ...],
    resource_type: ProjectFactoryInitRemoteResourceType,
) -> ProjectFactoryInitRemoteResource | None:
    for resource in resources:
        if resource.type == resource_type:
            return resource
    return None


def _has_blocking_phase(job: ProjectFactoryInitJob) -> bool:
    return any(
        phase.status
        in {
            ProjectFactoryInitPhaseStatus.BLOCKED,
            ProjectFactoryInitPhaseStatus.FAILED,
            ProjectFactoryInitPhaseStatus.CANCELLED,
        }
        for phase in job.phases
    )


def _has_waiting_phase(job: ProjectFactoryInitJob) -> bool:
    return any(
        phase.status == ProjectFactoryInitPhaseStatus.QUEUED_WAITING_FOR_DOMAIN_BRIEF
        for phase in job.phases
    )


def _read_domain_factory_brief(target: Path) -> str:
    state_path = target / ".codex" / "factory" / "domain-factory-state.json"
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
        brief_path = str(state.get("briefPath") or "").strip()
        if brief_path:
            candidate = target / brief_path
            if candidate.is_file() and candidate.read_text(encoding="utf-8").strip():
                return candidate.read_text(encoding="utf-8").strip()
    for candidate in (target / "specs").glob("*/intake/original-brief.md"):
        if candidate.is_file() and candidate.read_text(encoding="utf-8").strip():
            return candidate.read_text(encoding="utf-8").strip()
    return ""


def _project_factory_chat_domain_brief(messages: list[ChatMessage]) -> str:
    completed = [
        message
        for message in messages
        if message.status == ChatMessageStatus.COMPLETED and message.content.strip()
    ]
    if not completed:
        return ""
    ready_seen = any(
        "PROJECT_FACTORY_READY_FOR_BUILD" in message.content for message in completed
    )
    if not ready_seen:
        return ""
    relevant = [
        message
        for message in completed
        if message.role in {ChatMessageRole.USER, ChatMessageRole.ASSISTANT}
        and message.agent_id in {AgentId.USER, AgentId.GENERATOR}
    ]
    if not relevant:
        return ""
    lines = [
        "# Approved Project Factory Domain Brief",
        "",
        "This brief was captured in the Project Factory chat before deterministic init resumed.",
        "",
    ]
    for message in relevant[-8:]:
        author = "User" if message.role == ChatMessageRole.USER else (
            message.agent_label or "Project Factory"
        )
        lines.append(f"## {author}")
        lines.append("")
        lines.append(message.content.strip())
        lines.append("")
    return "\n".join(lines).strip()


def _write_automatic_ux_domain_brief(target: Path, domain_brief: str) -> Path:
    brief_path = target / ".codex" / "ux" / "domain-brief.md"
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(domain_brief.strip() + "\n", encoding="utf-8")
    return brief_path


def _markdown_excerpt(text: str, *, max_chars: int) -> str:
    normalized = text.strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars].rstrip() + "\n\n[excerpt truncated]"


def _verified_foundation_tasks_ready(job: ProjectFactoryInitJob) -> bool:
    required = (
        ProjectFactoryInitPhaseName.FLUTTER_OR_STRATEGY_BASELINE,
        ProjectFactoryInitPhaseName.LOCAL_VALIDATION,
        ProjectFactoryInitPhaseName.PREVIEW_SMOKE,
        ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
        ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION,
    )
    ready_statuses = {
        ProjectFactoryInitPhaseStatus.COMPLETED,
        ProjectFactoryInitPhaseStatus.SKIPPED,
    }
    return all(
        job.phase(phase_name).status in ready_statuses for phase_name in required
    )


def _align_verified_foundation_tasks(target: Path) -> tuple[Path, ...]:
    spec_dir = target / "specs/001-product-foundation"
    tree_path = spec_dir / "tree.json"
    if not tree_path.is_file():
        return ()
    tree = _read_json_file(tree_path)
    plans = tree.get("plans") if isinstance(tree, dict) else None
    if not isinstance(plans, list):
        return ()
    changed_paths: list[Path] = []
    changed_tree = False
    for plan in plans:
        if not isinstance(plan, dict):
            continue
        tasks = plan.get("tasks")
        if not isinstance(tasks, list):
            continue
        for task in tasks:
            if not isinstance(task, dict):
                continue
            if str(task.get("id") or "") in _VERIFIED_FOUNDATION_TASK_IDS:
                if task.get("status") != "done":
                    task["status"] = "done"
                    changed_tree = True
    if changed_tree:
        _write_text_if_changed(tree_path, _json_dumps_stable(tree))
        changed_paths.append(tree_path)
    tasks = _foundation_tasks_from_tree(tree)
    tasks_path = spec_dir / "tasks.md"
    if tasks and tasks_path.is_file():
        tasks_text = _foundation_tasks_markdown(tasks)
        if tasks_path.read_text(encoding="utf-8") != tasks_text:
            tasks_path.write_text(tasks_text, encoding="utf-8")
            changed_paths.append(tasks_path)
    for task in tasks:
        task_path = spec_dir / str(task.get("file") or "")
        if task_path.is_file():
            text = task_path.read_text(encoding="utf-8")
            updated = _replace_task_status_line(text, str(task.get("status") or ""))
            if updated != text:
                task_path.write_text(updated, encoding="utf-8")
                changed_paths.append(task_path)
    metadata_path = spec_dir / "metadata.yaml"
    if metadata_path.is_file() and tasks:
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8")) or {}
        if isinstance(metadata, dict):
            completed = sum(1 for task in tasks if task.get("status") == "done")
            pending = len(tasks) - completed
            task_counts = metadata.get("tasks")
            if not isinstance(task_counts, dict):
                task_counts = {}
            task_counts.update(
                {
                    "total": len(tasks),
                    "completed": completed,
                    "pending": pending,
                }
            )
            metadata["tasks"] = task_counts
            metadata_text = yaml.safe_dump(
                metadata,
                sort_keys=False,
                allow_unicode=True,
            )
            if metadata_path.read_text(encoding="utf-8") != metadata_text:
                metadata_path.write_text(metadata_text, encoding="utf-8")
                changed_paths.append(metadata_path)
    return tuple(dict.fromkeys(changed_paths))


def _foundation_tasks_from_tree(tree: dict[str, object]) -> list[dict[str, object]]:
    tasks: list[dict[str, object]] = []
    plans = tree.get("plans")
    if not isinstance(plans, list):
        return tasks
    for plan in plans:
        if not isinstance(plan, dict):
            continue
        plan_tasks = plan.get("tasks")
        if isinstance(plan_tasks, list):
            tasks.extend(task for task in plan_tasks if isinstance(task, dict))
    return tasks


def _foundation_tasks_markdown(tasks: list[dict[str, object]]) -> str:
    lines = ["# Tasks", ""]
    for task in tasks:
        status = "x" if task.get("status") == "done" else " "
        title = str(task.get("title") or "").strip()
        if title and not title.endswith("."):
            title = f"{title}."
        lines.append(f"- [{status}] {title}")
    return "\n".join(lines) + "\n"


def _replace_task_status_line(text: str, status: str) -> str:
    replacement = f"Status: {status}"
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("Status: "):
            lines[index] = replacement
            return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    return text


def _task_alignment_blocker(
    *,
    code: str,
    message: str,
    command: tuple[str, ...],
) -> ProjectFactoryInitBlocker:
    return ProjectFactoryInitBlocker(
        code=code,
        message=message,
        phase=ProjectFactoryInitPhaseName.WORKBENCH_AND_FEEDBACK_VERIFICATION,
        next_action="Fix git publish access for the generated workspace, then rerun deterministic init.",
        command=command,
    )


def _automatic_ux_prompts(
    job: ProjectFactoryInitJob,
    *,
    target: Path,
    domain_brief: str,
    visual_ux_prompt_section: str,
) -> tuple[str, str]:
    preview_url = f"https://preview.nienfos.com/{job.slug}"
    preview_api = f"{preview_url}/api"
    bounded_skill_context = _markdown_excerpt(
        visual_ux_prompt_section,
        max_chars=_AUTOMATIC_UX_SKILL_CONTEXT_MAX_CHARS,
    )
    base = f"""You are working inside a newly generated Project Factory baseline.

Workspace: `{target}`
Project: `{job.project_name}`
Source app: `{job.slug}`
Frontend strategy: `{job.frontend_strategy}`
Preview URL: `{preview_url}`
Preview API: `{preview_api}`

Required domain brief:
- Read `.codex/ux/domain-brief.md` before making UX decisions.
- Base the early UX baseline on that approved Project Factory/domain contract.
- Do not invent another product category when the brief already defines one.

Domain brief excerpt:
{_markdown_excerpt(domain_brief, max_chars=6000)}

Hard constraints:
- Do not recreate the project, GitHub repository, Cloudflare resources, Android
  release wiring, Bridge installable registration, Workbench metadata, feedback,
  updater, auth, RBAC, persistence, or backend contracts.
- Do not enable mock/demo mode, seeded demo data, localhost API URLs, or
  placeholder runtime URLs.
- Keep changes scoped to visible UX, user-facing copy, layout, responsive fit,
  accessibility, and frontend polish.
- Save concise evidence under `.codex/ux/`.
- Treat product identity as part of UX: inspect `assets/brand/` and
  `apps/mobile/assets/brand/`. If an uploaded logo or app icon source exists,
  preserve and use it as the visual identity. If no logo was supplied, create a
  simple project-specific logo/source mark under `assets/brand/logo.svg` and
  `apps/mobile/assets/brand/app_icon_source.svg`, then make sure Android keeps a
  non-Flutter launcher icon. Never leave the generated preview using the Flutter
  default logo.

Automatic UX execution budget:
- This is a bounded early UX baseline for deterministic init. Finish in one
  short Codex turn and do not wait for release, APK, preview, emulator, browser,
  or long-running build output.
- Do not run package managers, Flutter/Gradle builds, APK publishing, preview
  deploys, persistent dev servers, broad binary reads, or commands that dump
  screenshots/assets into stdout.
- Inspect only the domain brief, nearby project metadata, and the smallest
  frontend files needed to make safe visible UX improvements.
- If deeper visual validation is needed, record it as follow-up for the final UX
  polish lane instead of continuing until timeout.
- Always write the requested `.codex/ux/` report before exiting.
"""
    generator_prompt = (
        base
        + "\n# Required visual-ux-polish Skill Context Excerpt\n\n"
        + bounded_skill_context
        + """
# Automatic New Project UX Generator

This is the automatic early UX baseline pass for New Project. Improve the
generated UI enough for the first installable preview to have a coherent visual
direction for the requested product category.

Do not perform full visual QA here. Do not benchmark live products, do not start
the app, do not capture screenshots, and do not wait for the Android preview
release. Make small scoped UI/copy/theme adjustments when they are obvious from
the brief and source files; otherwise write concise direction and leave deeper
polish for the final UX lane.

If reviewer feedback is provided below in a later iteration, address only that
UX feedback. Write `.codex/ux/ux-generator-report.md` with what changed,
files inspected, any small edits made, the logo/app icon decision, and any
remaining UX concerns.
"""
    )
    reviewer_prompt = (
        base
        + "\n# Required visual-ux-polish Skill Context Excerpt\n\n"
        + bounded_skill_context
        + """
# Automatic New Project UX Reviewer

Review only the UX generator changes and evidence. Check hierarchy, layout,
spacing, typography, contrast, responsive/mobile fit, empty/loading/error
states, accessibility, logo/app icon identity, and scope discipline. Do not ask
for backend, auth, schema, release, business-logic changes, builds, screenshots,
previews, or APK validation in this early lane.

Early-lane reviewer decision rules:
- Do not return `continue`, `blocked`, or `release_gate=fail` only because
  screenshots, live preview, APK, emulator/browser validation, long-running
  builds, or broad tests were not run.
- Do not ask the next generator to capture screenshots or run builds in this
  early lane.
- Treat missing heavy visual validation as final-polish follow-up unless there
  is a concrete visible regression in inspected source files.
- Return `complete` with `release_gate=pass` when the generator made bounded
  UX progress or left clear follow-up and did not violate scope.
- Return `continue` only for one or two small, source-only UX/copy fixes that
  are required before deterministic init can proceed.
- Return `continue` if the UI still depends on the Flutter default logo or if
  the generator ignored a supplied `logo`/`app_icon` asset.

This automatic UX lane can run up to 10 generator/reviewer passes. Stop early
when the UI is good enough for the first installable preview. If more UX-only
work is required, write `.codex/ux/ux-reviewer-report.md` with the exact next
prompt for the UX generator.

End your response, and the report when possible, with this machine-readable
decision:

```json
{"status":"complete|continue|blocked","summary":"short UX readiness summary","continuation_prompt":"next UX-only prompt when status is continue","release_gate":"pass|fail"}
```
"""
    )
    return generator_prompt, reviewer_prompt


def _automatic_ux_reviewer_feedback(
    *,
    target: Path,
    result: ProjectFactoryInitCommandResult,
) -> str:
    report_path = target / ".codex/ux/ux-reviewer-report.md"
    report = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    return "\n\n".join(
        item.strip()
        for item in (result.stdout, result.stderr, report)
        if item and item.strip()
    )


def _automatic_ux_chat_content(
    *,
    label: str,
    iteration: int,
    result: ProjectFactoryInitCommandResult,
) -> str:
    status = "completed" if result.exit_code == 0 else "failed"
    body_parts = [
        part.strip()
        for part in (result.stdout, result.stderr)
        if part and part.strip()
    ]
    body = "\n\n".join(body_parts) or "No textual output was captured."
    return (
        f"# {label} pass {iteration}\n\n"
        f"Status: {status}\n\n"
        f"{body.strip()}\n"
    )


def _ensure_automatic_ux_report(
    *,
    target: Path,
    role: str,
    result: ProjectFactoryInitCommandResult,
) -> Path:
    report_path = target / ".codex" / "ux" / f"ux-{role}-report.md"
    if report_path.is_file() and report_path.read_text(encoding="utf-8").strip():
        return report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    status = "completed" if result.exit_code == 0 else "failed"
    body = "\n\n".join(
        part.strip()
        for part in (result.stdout, result.stderr)
        if part and part.strip()
    )
    if not body:
        body = "No textual output was captured."
    report_path.write_text(
        f"# Automatic UX {role.title()} Report\n\n"
        f"Status: {status}\n\n"
        f"Exit code: {result.exit_code}\n\n"
        "## Captured Output\n\n"
        f"{body.strip()}\n",
        encoding="utf-8",
    )
    return report_path


def _automatic_ux_prompt_file_instruction(prompt_path: Path, *, cwd: Path) -> str:
    try:
        display_path = prompt_path.relative_to(cwd)
    except ValueError:
        display_path = prompt_path
    return (
        "Read and follow the full automatic UX prompt from this workspace file: "
        f"`{display_path}`.\n\n"
        "Do not ask for the prompt contents. Open the file, execute its "
        "instructions exactly, and write the requested `.codex/ux/` evidence."
    )


def _codex_argv_with_output_report(
    command: str,
    prompt: str,
    *,
    report_path: Path,
    exec_args: str | None = None,
) -> tuple[str, ...]:
    argv = _codex_argv(command, prompt, exec_args=exec_args)
    if not argv:
        return argv
    return (*argv[:-1], "--output-last-message", str(report_path), argv[-1])


def _automatic_ux_result_failed(
    result: ProjectFactoryInitCommandResult,
    *,
    target: Path,
    role: str,
) -> bool:
    if result.exit_code != 0:
        return True
    output = "\n".join(part for part in (result.stdout, result.stderr) if part).lower()
    blocked_markers = (
        "bwrap:",
        "failed rtm_newaddr",
        "operation not permitted",
        "current sandbox",
        "execution sandbox",
        "workspace tools are blocked",
        "workspace is mounted read-only",
        "filesystem is also configured as read-only",
        "could not execute the ux prompt",
        "could not open `.codex/factory/prompts/",
        "could not read the required `visual-ux-polish`",
        "could not read the prompt",
        "could not write evidence",
        "cannot write the requested `.codex/ux/` evidence",
        "no files were changed",
    )
    if any(marker in output for marker in blocked_markers):
        return True
    expected_report = target / ".codex" / "ux" / f"ux-{role}-report.md"
    return not expected_report.is_file() or not expected_report.read_text(
        encoding="utf-8"
    ).strip()


def _automatic_ux_blocker(
    *,
    phase: ProjectFactoryInitPhaseName,
    code: str,
    message: str,
    next_action: str,
    detail: str = "",
) -> ProjectFactoryInitBlocker:
    full_message = f"{message} Detail: {detail}" if detail else message
    return ProjectFactoryInitBlocker(
        code=code,
        message=full_message,
        phase=phase,
        next_action=next_action,
        command=("project-factory", "init", "retry"),
    )


def _automatic_ux_command_blocker(
    *,
    phase: ProjectFactoryInitPhaseName,
    code: str,
    message: str,
    result: ProjectFactoryInitCommandResult,
) -> ProjectFactoryInitBlocker:
    detail = _summarize_output(
        "\n".join(part for part in (result.stdout, result.stderr) if part),
        (),
    )
    return _automatic_ux_blocker(
        phase=phase,
        code=code,
        message=message,
        next_action=(
            "Fix the automatic UX agent/tooling issue, then rerun deterministic init."
        ),
        detail=detail,
    )


def _local_git_blocker(
    *,
    code: str,
    message: str,
    command: tuple[str, ...],
) -> ProjectFactoryInitBlocker:
    return ProjectFactoryInitBlocker(
        code=code,
        message=message,
        phase=ProjectFactoryInitPhaseName.LOCAL_GIT_COMMIT,
        next_action="Fix the generated workspace git state, then rerun deterministic init.",
        command=command,
    )


def _business_phase_rules() -> list[str]:
    return [
        "Keep preview runtime real: APP_RUNTIME_PROFILE=preview, API_RUNTIME=cloudflare_preview, and API_BASE_URL must stay on https://preview.nienfos.com/{slug}/api.",
        "Do not switch to mock, demo, localhost, placeholder, or seeded local data unless the user explicitly asks for a demo/mock build.",
        "Do not recreate GitHub, Cloudflare Worker/route/D1, Android prerelease, Bridge installable, feedback, updater, or Workbench plumbing manually.",
        "Implement only product and business work on top of the initialized deterministic baseline.",
        "Update specs, tasks, tests, and release evidence whenever product work changes behavior.",
    ]


def _context_pack_markdown(payload: dict[str, object]) -> str:
    resources = (
        payload.get("resources") if isinstance(payload.get("resources"), dict) else {}
    )
    github = resources.get("github") if isinstance(resources, dict) else {}
    preview = resources.get("cloudflarePreview") if isinstance(resources, dict) else {}
    android = (
        resources.get("androidPreviewRelease") if isinstance(resources, dict) else {}
    )
    bridge = resources.get("bridgeInstallable") if isinstance(resources, dict) else {}
    blockers = (
        payload.get("blockers") if isinstance(payload.get("blockers"), list) else []
    )
    pending_work = (
        payload.get("pendingDeterministicWork")
        if isinstance(payload.get("pendingDeterministicWork"), list)
        else []
    )
    pending_lines = _markdown_pending_work_lines(pending_work)
    llm_guidance = payload.get("llmOperationalGuidance")
    guidance_lines = (
        [f"- {rule}" for rule in llm_guidance if isinstance(rule, str)]
        if isinstance(llm_guidance, list)
        else []
    )
    blocker_lines = _markdown_blocker_lines(blockers)
    rules = payload.get("businessPhaseRules")
    rule_lines = (
        [f"- {rule}" for rule in rules if isinstance(rule, str)]
        if isinstance(rules, list)
        else []
    )
    readiness = (
        "ready"
        if payload.get("readyForBusinessLlm") is True
        else "blocked_with_context"
        if payload.get("blockedWithContext") is True
        else "resumable"
    )
    return "\n".join(
        [
            "# Deterministic Init Context",
            "",
            f"Project: {payload.get('projectName')} (`{payload.get('slug')}`)",
            f"Draft id: `{payload.get('draftId')}`",
            f"Init job id: `{payload.get('initJobId')}`",
            f"Chat session id: `{payload.get('chatSessionId')}`",
            f"Workspace: `{payload.get('workspacePath')}`",
            f"Frontend strategy: `{payload.get('frontendStrategy')}`",
            f"Context status: `{readiness}`",
            "",
            "## Initialized Baseline",
            "",
            f"- GitHub repo: {_markdown_value(github, 'repoUrl')}",
            f"- GitHub branch: {_markdown_value(github, 'branch')}",
            f"- Preview URL: {_markdown_value(preview, 'previewUrl')}",
            f"- Preview API: {_markdown_value(preview, 'apiBaseUrl')}",
            f"- Cloudflare Worker: {_markdown_nested_name(preview, 'worker')}",
            f"- Cloudflare route: {_markdown_nested_name(preview, 'route')}",
            f"- D1 database: {_markdown_nested_name(preview, 'd1')}",
            f"- Android prerelease: {_markdown_value(android, 'releaseTag')}",
            f"- Android APK sha256: {_markdown_value(android, 'apkSha256')}",
            f"- Bridge installable status: {_markdown_value(bridge, 'status')}",
            "",
            "## Business Phase Rules",
            "",
            *rule_lines,
            "",
            "## Pending Deterministic Work",
            "",
            *(pending_lines or ["- None."]),
            "",
            "## LLM Operational Guidance",
            "",
            *guidance_lines,
            "",
            "## Current Blockers",
            "",
            *(blocker_lines or ["- None."]),
            "",
            "Use `.codex/factory/init-result.json` as the structured source of truth.",
            "",
        ]
    )


def _markdown_pending_work_lines(pending_work: list[object]) -> list[str]:
    lines: list[str] = []
    for item in pending_work:
        if not isinstance(item, dict):
            continue
        phase = item.get("phase")
        status = item.get("status")
        current = " current" if item.get("current") is True else ""
        lines.append(
            f"- `{phase}` is `{status}`{current}; wait for deterministic init before asking the user for setup help."
        )
    return lines


def _markdown_blocker_lines(blockers: list[object]) -> list[str]:
    lines: list[str] = []
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        command = blocker.get("command")
        command_text = (
            shlex.join(tuple(str(part) for part in command))
            if isinstance(command, list)
            else ""
        )
        suffix = f" Retry: `{command_text}`." if command_text else ""
        lines.append(
            f"- `{blocker.get('phase')}` / `{blocker.get('code')}`: "
            f"{blocker.get('message')} Next: {blocker.get('nextAction')}.{suffix}"
        )
    return lines


def _markdown_value(mapping: object, key: str) -> str:
    if not isinstance(mapping, dict):
        return "`not_available`"
    value = mapping.get(key)
    return f"`{value}`" if value else "`not_available`"


def _markdown_nested_name(mapping: object, key: str) -> str:
    if not isinstance(mapping, dict):
        return "`not_available`"
    nested = mapping.get(key)
    if not isinstance(nested, dict):
        return "`not_available`"
    value = nested.get("displayName") or nested.get("identifier") or nested.get("url")
    return f"`{value}`" if value else "`not_available`"


def _json_dumps_stable(payload: dict[str, object]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _write_text_if_changed(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8")


def _sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _redact_context_value(
    value: object,
    sensitive_values: tuple[str, ...],
) -> object:
    if isinstance(value, dict):
        redacted: dict[str, object] = {}
        for key, item in value.items():
            text_key = str(key)
            redacted[text_key] = (
                "[redacted]"
                if _is_sensitive_context_key(text_key)
                else _redact_context_value(item, sensitive_values)
            )
        return redacted
    if isinstance(value, list):
        return [_redact_context_value(item, sensitive_values) for item in value]
    if isinstance(value, tuple):
        return [_redact_context_value(item, sensitive_values) for item in value]
    if isinstance(value, str):
        redacted_text = value
        for secret in sensitive_values:
            if secret:
                redacted_text = redacted_text.replace(secret, "[redacted]")
        return redacted_text
    return value


def _redact_optional_text(
    value: str | None,
    sensitive_values: tuple[str, ...],
) -> str | None:
    if value is None:
        return None
    return _redact_context_text(value, sensitive_values)


def _redact_context_text(
    value: str,
    sensitive_values: tuple[str, ...],
) -> str:
    redacted_text = value
    for secret in sensitive_values:
        if secret:
            redacted_text = redacted_text.replace(secret, "[redacted]")
    return redacted_text


def _is_sensitive_context_key(key: str) -> bool:
    lowered = key.lower()
    return any(
        marker in lowered
        for marker in ("token", "secret", "password", "private_key", "keystore")
    )


def _android_runtime_blocker(
    runtime: object,
    *,
    slug: str,
) -> ProjectFactoryInitBlocker | None:
    expected_api = f"https://preview.nienfos.com/{slug}/api"
    expected_preview = f"https://preview.nienfos.com/{slug}"
    if not isinstance(runtime, dict):
        return _android_blocker(
            phase=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
            code="android_preview_runtime_contract_missing",
            message="release/preview-runtime.json is missing or invalid.",
            next_action="Restore the deterministic frontend baseline, then rerun Android preview init.",
            command=("project-factory", "init", "baseline", "repair"),
        )
    expected = {
        "sourceApp": slug,
        "previewUrl": expected_preview,
        "apiBaseUrl": expected_api,
        "runtimeProfile": "preview",
        "apiRuntime": "cloudflare_preview",
        "releaseChannel": "prerelease",
        "productionReady": False,
        "mockOrDemo": False,
        "dataPersistence": "cloudflare_d1",
        "d1PreviewRequired": True,
        "installableAndroid": True,
        "bridgeRegistrationRequired": True,
        "releaseTagPattern": "android-preview-v*",
        "latestAssetName": f"{slug}.apk",
    }
    for key, value in expected.items():
        if runtime.get(key) != value:
            return _android_blocker(
                phase=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
                code="android_preview_runtime_contract_invalid",
                message=f"Android preview runtime {key} must be {value!r}.",
                next_action="Restore real Cloudflare preview Android runtime metadata, then rerun init.",
                command=("project-factory", "init", "baseline", "repair"),
            )
    if _has_forbidden_runtime_marker(runtime):
        return _android_blocker(
            phase=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
            code="android_preview_runtime_mock_or_local_blocked",
            message="Android preview runtime contains mock, demo, local, or placeholder defaults.",
            next_action="Replace mock/local defaults with the real Cloudflare preview API and D1 contract.",
            command=("project-factory", "init", "baseline", "repair"),
        )
    return None


def _read_flutter_version(path: Path) -> str | None:
    for line in _read_text(path).splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip() == "version":
            version = value.strip()
            return version or None
    return None


def _android_preview_tag(version: str) -> str:
    normalized = version.strip().replace("+", "-build.")
    return f"android-preview-v{normalized}"


def _parse_json_object(stdout: str) -> dict[str, object]:
    try:
        payload = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _valid_android_release(
    payload: dict[str, object],
    *,
    release_tag: str,
    apk_name: str,
) -> bool:
    if not payload:
        return False
    tag = _optional_str(payload.get("tagName") or payload.get("tag_name"))
    prerelease = payload.get("isPrerelease")
    if prerelease is None:
        prerelease = payload.get("prerelease")
    return (
        tag == release_tag
        and release_tag.startswith("android-preview-v")
        and prerelease is True
        and _release_asset(payload, apk_name) is not None
    )


def _release_asset(
    payload: dict[str, object],
    apk_name: str,
) -> dict[str, object] | None:
    assets = payload.get("assets")
    if not isinstance(assets, list):
        return None
    for raw in assets:
        if not isinstance(raw, dict):
            continue
        name = _optional_str(raw.get("name"))
        if name == apk_name:
            return _safe_json_object(raw)
    return None


def _find_apk(target: Path, slug: str) -> Path | None:
    candidates = (
        target / "apps/mobile/build/app/outputs/flutter-apk" / f"{slug}.apk",
        target / "apps/mobile/build/app/outputs/flutter-apk/app-release.apk",
        target / "release" / f"{slug}.apk",
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _keytool_executable() -> str:
    keytool = shutil.which("keytool")
    if keytool:
        return keytool
    java = shutil.which("java")
    if java:
        sibling = Path(java).resolve().parent / "keytool"
        if sibling.is_file():
            return str(sibling)
    fallback = Path.home() / ".local/share/java/jdk-17/bin/keytool"
    if fallback.is_file():
        return str(fallback)
    return "keytool"


def _github_repo_ref_from_origin(origin_url: str) -> str | None:
    value = origin_url.strip().removesuffix(".git")
    if value.startswith("https://github.com/"):
        value = value.removeprefix("https://github.com/")
    elif value.startswith("git@github.com:"):
        value = value.removeprefix("git@github.com:")
    else:
        return None
    return value if "/" in value else None


def _read_preview_signing_files(bridge_root: Path, slug: str) -> dict[str, object]:
    secrets_dir = bridge_root / "secrets"
    signing_env = secrets_dir / f"{slug}-preview-signing.env"
    keystore = secrets_dir / f"{slug}-preview-upload-keystore.jks"
    values: dict[str, object] = {}
    for line in signing_env.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = shlex.split(value)[0] if value else ""
    values["keystore_bytes"] = keystore.read_bytes()
    return values


def _patch_flutter_android_release_signing(build_gradle: Path) -> None:
    text = build_gradle.read_text(encoding="utf-8")
    if "keystoreProperties" not in text:
        text = text.replace(
            "plugins {\n",
            "import java.util.Properties\n\nplugins {\n",
            1,
        )
        marker = "\nandroid {\n"
        text = text.replace(
            marker,
            (
                "\nval keystoreProperties = Properties()\n"
                'val keystorePropertiesFile = rootProject.file("key.properties")\n'
                "if (keystorePropertiesFile.exists()) {\n"
                "    keystorePropertiesFile.inputStream().use { "
                "keystoreProperties.load(it) }\n"
                "}\n"
                "\nandroid {\n"
            ),
            1,
        )
    if 'create("release")' not in text:
        text = text.replace(
            "    buildTypes {\n",
            (
                "    signingConfigs {\n"
                '        create("release") {\n'
                '            keyAlias = keystoreProperties["keyAlias"] as String?\n'
                '            keyPassword = keystoreProperties["keyPassword"] as String?\n'
                '            storeFile = keystoreProperties["storeFile"]?.let { '
                "rootProject.file(it) }\n"
                '            storePassword = keystoreProperties["storePassword"] as String?\n'
                '            storeType = (keystoreProperties["storeType"] as String?) '
                '?: "JKS"\n'
                "        }\n"
                "    }\n"
                "\n"
                "    buildTypes {\n"
            ),
            1,
        )
    text = text.replace(
        'signingConfig = signingConfigs.getByName("debug")',
        'signingConfig = signingConfigs.getByName("release")',
    )
    build_gradle.write_text(text, encoding="utf-8")


def _ensure_flutter_android_bridge_network_config(mobile: Path) -> None:
    manifest = mobile / "android/app/src/main/AndroidManifest.xml"
    if manifest.is_file():
        text = manifest.read_text(encoding="utf-8")
        if "android:networkSecurityConfig=" not in text:
            text = text.replace(
                'android:icon="@mipmap/ic_launcher"',
                (
                    'android:icon="@mipmap/ic_launcher"\n'
                    '        android:networkSecurityConfig="@xml/network_security_config"'
                ),
                1,
            )
            manifest.write_text(text, encoding="utf-8")
    network_config = (
        mobile / "android/app/src/main/res/xml/network_security_config.xml"
    )
    network_config.parent.mkdir(parents=True, exist_ok=True)
    network_config.write_text(
        _android_bridge_network_security_config(),
        encoding="utf-8",
    )


def _android_bridge_network_security_config() -> str:
    return """<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <domain-config cleartextTrafficPermitted="true">
        <domain includeSubdomains="true">tail0302c4.ts.net</domain>
    </domain-config>
</network-security-config>
"""


def _android_blocker(
    *,
    phase: ProjectFactoryInitPhaseName,
    code: str,
    message: str,
    next_action: str,
    command: tuple[str, ...] = (),
) -> ProjectFactoryInitBlocker:
    return ProjectFactoryInitBlocker(
        code=code,
        message=message,
        phase=phase,
        next_action=next_action,
        command=command,
        recoverable=True,
    )


def _android_blocker_from_command(
    *,
    code: str,
    message: str,
    phase: ProjectFactoryInitPhaseName,
    result: ProjectFactoryInitCommandResult,
    command: tuple[str, ...],
) -> ProjectFactoryInitBlocker:
    output = f"{result.stdout}\n{result.stderr}".lower()
    resolved_code = code
    resolved_message = message
    if any(
        marker in output
        for marker in ("flutter", "java", "jdk", "signing", "keystore", "apksigner")
    ):
        resolved_code = "android_preview_tooling_or_signing_missing"
        resolved_message = (
            "Android preview release tooling or signing configuration is missing."
        )
    elif "permission" in output or "protected" in output:
        resolved_code = "android_preview_release_permission_blocked"
        resolved_message = "Android preview release publish is blocked by GitHub permissions or policy."
    detail = _summarize_output(result.stderr or result.stdout, ())
    if detail and detail not in resolved_message:
        resolved_message = f"{resolved_message} Detail: {detail}"
    return _android_blocker(
        phase=phase,
        code=resolved_code,
        message=resolved_message,
        next_action=f"Run {shlex.join(command)} after fixing the reported release blocker, then rerun deterministic init.",
        command=command,
    )


def _android_release_payload_blocker(
    payload: dict[str, object],
    release_tag: str,
    apk_name: str,
) -> ProjectFactoryInitBlocker:
    tag = _optional_str(payload.get("tagName") or payload.get("tag_name"))
    prerelease = payload.get("isPrerelease")
    if prerelease is None:
        prerelease = payload.get("prerelease")
    if tag and not tag.startswith("android-preview-v"):
        code = "android_preview_release_bad_tag"
        message = (
            f"Android preview release tag must start with android-preview-v, got {tag}."
        )
    elif tag != release_tag:
        code = "android_preview_release_missing"
        message = f"GitHub prerelease {release_tag} was not found after publish."
    elif prerelease is not True:
        code = "android_preview_release_channel_invalid"
        message = f"GitHub release {release_tag} must be a prerelease."
    else:
        code = "android_preview_release_asset_missing"
        message = f"GitHub prerelease {release_tag} is missing APK asset {apk_name}."
    return _android_blocker(
        phase=ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
        code=code,
        message=message,
        next_action="Publish or repair the Android Initial Preview prerelease, then rerun deterministic init.",
        command=(
            "bash",
            "scripts/publish_android_preview_release.sh",
            "--push",
            "--watch",
        ),
    )


def _valid_installable_payload(
    payload: dict[str, object],
    *,
    slug: str,
    release_tag: str,
    preview_api: str,
) -> bool:
    if not payload:
        return False
    preview_url = preview_api.removesuffix("/api")
    latest_build = payload.get("latestBuild")
    latest_build_tag = (
        latest_build.get("releaseTag") if isinstance(latest_build, dict) else None
    )
    sha256 = _optional_str(payload.get("sha256"))
    apk_url = _optional_str(payload.get("apkUrl"))
    release_tag_value = _optional_str(payload.get("releaseTag") or latest_build_tag)
    return (
        payload.get("sourceApp") == slug
        and payload.get("releaseChannel") == "prerelease"
        and payload.get("releaseTagPattern") == "android-preview-v*"
        and release_tag_value == release_tag
        and release_tag.startswith("android-preview-v")
        and payload.get("available") is True
        and bool(apk_url and apk_url.startswith(("https://", "http://")))
        and payload.get("previewUrl") == preview_url
        and payload.get("runtimeProfile") == "preview"
        and payload.get("productionReady") is False
        and payload.get("mockOrDemo") is False
        and not _has_forbidden_runtime_marker(payload)
        and (sha256 is None or _is_sha256(sha256))
    )


_LOCAL_BRIDGE_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "10.0.2.2"}


def _resolve_bridge_public_url(
    bridge_base_url: str,
    *,
    settings: Settings | None,
    command_env: dict[str, str],
) -> str:
    candidates = (
        getattr(settings, "app_update_public_base_url", None),
        command_env.get("BRIDGE_PUBLIC_URL"),
        command_env.get("CODEX_APP_UPDATER_BRIDGE_URL"),
        command_env.get("API_BASE_URL"),
        os.environ.get("BRIDGE_PUBLIC_URL"),
        os.environ.get("CODEX_APP_UPDATER_BRIDGE_URL"),
    )
    for candidate in candidates:
        public_url = _non_local_http_url(candidate)
        if public_url and not _is_preview_app_public_url(public_url, settings=settings):
            return public_url
    if not _is_local_bridge_url(bridge_base_url):
        return bridge_base_url.rstrip("/")
    if settings is not None:
        tailscale = detect_tailscale_info(
            settings.tailscale_socket,
            api_port=settings.api_port,
        )
        for candidate in tailscale.public_base_urls:
            public_url = _non_local_http_url(candidate)
            if public_url and not _is_preview_app_public_url(
                public_url,
                settings=settings,
            ):
                return public_url
    return bridge_base_url.rstrip("/")


def _resolve_bridge_registration_url(
    bridge_base_url: str,
    *,
    settings: Settings | None,
    command_env: dict[str, str],
) -> str:
    explicit = (
        command_env.get("BRIDGE_REGISTRATION_URL")
        or os.environ.get("BRIDGE_REGISTRATION_URL")
        or ""
    ).strip().rstrip("/")
    if explicit:
        return explicit
    if settings is not None and getattr(settings, "api_port", None):
        return f"http://127.0.0.1:{settings.api_port}"
    if _is_local_bridge_url(bridge_base_url):
        return bridge_base_url.rstrip("/")
    parsed = urlparse((bridge_base_url or "").strip())
    if parsed.port:
        return f"http://127.0.0.1:{parsed.port}"
    return bridge_base_url.rstrip("/")


def _non_local_http_url(value: str | None) -> str | None:
    url = (value or "").strip().rstrip("/")
    if not url or _is_local_bridge_url(url):
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return url


def _is_preview_app_public_url(value: str, *, settings: Settings | None) -> bool:
    parsed = urlparse((value or "").strip())
    preview_base_domain = (
        getattr(settings, "preview_base_domain", None) or "preview.nienfos.com"
    ).lower()
    host = (parsed.hostname or "").lower()
    if host != preview_base_domain:
        return False
    return bool(parsed.path.strip("/"))


def _android_preview_bridge_url(value: str) -> str:
    url = value.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme == "https" and (
        parsed.hostname or ""
    ).lower().endswith(".ts.net"):
        return parsed._replace(scheme="http").geturl().rstrip("/")
    return url


def _is_local_bridge_url(value: str | None) -> bool:
    parsed = urlparse((value or "").strip())
    host = (parsed.hostname or "").lower()
    return host in _LOCAL_BRIDGE_HOSTS


def _bridge_installable_lookup_command(
    bridge_base_url: str,
    bridge_public_url: str,
    slug: str,
) -> tuple[str, ...]:
    command: list[str] = ["curl", "-fsS"]
    if bridge_public_url.rstrip("/") != bridge_base_url.rstrip("/"):
        parsed = urlparse(bridge_public_url)
        if parsed.netloc:
            command.extend(["-H", f"Host: {parsed.netloc}"])
        if parsed.scheme:
            command.extend(["-H", f"X-Forwarded-Proto: {parsed.scheme}"])
    command.append(f"{bridge_base_url.rstrip('/')}/installable-apps/{slug}")
    return tuple(command)


def _installable_payload_blocker(
    payload: dict[str, object],
    release_tag: str,
) -> ProjectFactoryInitBlocker:
    if not payload:
        code = "bridge_installable_lookup_failed"
        message = "Bridge installable app lookup did not return a valid payload."
    elif payload.get("mockOrDemo") is not False or _has_forbidden_runtime_marker(
        payload
    ):
        code = "bridge_installable_mock_or_local_blocked"
        message = "Bridge installable registration contains mock, demo, local, or placeholder runtime metadata."
    elif payload.get("releaseChannel") != "prerelease":
        code = "bridge_installable_release_channel_invalid"
        message = "Bridge installable app must use releaseChannel=prerelease."
    elif _optional_str(payload.get("releaseTag")) != release_tag:
        code = "bridge_installable_release_tag_invalid"
        message = f"Bridge installable app must point to {release_tag}."
    elif not payload.get("apkUrl"):
        code = "bridge_installable_apk_url_missing"
        message = "Bridge installable app lookup is missing an APK URL."
    else:
        code = "bridge_installable_payload_invalid"
        message = "Bridge installable app payload does not match Android preview release requirements."
    return _android_blocker(
        phase=ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION,
        code=code,
        message=message,
        next_action="Repair Bridge installable registration, then rerun deterministic init.",
        command=("bash", "scripts/register_installable_app.sh"),
    )


def _has_forbidden_runtime_marker(value: object) -> bool:
    blob = json.dumps(_safe_json_value(value), sort_keys=True).lower()
    forbidden = (
        "http://localhost",
        "https://localhost",
        "127.0.0.1",
        "10.0.2.2",
        "example.com",
        "placeholder",
        '"mockordemo": true',
        '"mock_or_demo": true',
        "mock://",
        "demo://",
        "mock_mode",
        "demo_mode",
        "local_demo",
    )
    return any(marker in blob for marker in forbidden)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdefABCDEF" for char in value)


def _parse_repo_payload(stdout: str) -> dict[str, object]:
    try:
        payload = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _repo_identity_matches(
    payload: dict[str, object], owner: str, repo_name: str
) -> bool:
    name = str(payload.get("name") or "")
    owner_payload = payload.get("owner")
    if isinstance(owner_payload, dict):
        resolved_owner = str(
            owner_payload.get("login") or owner_payload.get("name") or ""
        )
    else:
        resolved_owner = str(owner_payload or "")
    return name == repo_name and (
        not resolved_owner or resolved_owner.lower() == owner.lower()
    )


def _repo_url(payload: dict[str, object] | None, repo_ref: str) -> str:
    if payload:
        url = _optional_str(payload.get("url"))
        if url:
            return url
    return f"https://github.com/{repo_ref}"


def _repo_default_branch(payload: dict[str, object] | None) -> str | None:
    if not payload:
        return None
    branch = payload.get("defaultBranchRef")
    if isinstance(branch, dict):
        return _optional_str(branch.get("name"))
    return _optional_str(branch)


def _repo_visibility(payload: dict[str, object] | None) -> str | None:
    if not payload:
        return None
    visibility = _optional_str(payload.get("visibility"))
    return visibility.lower() if visibility else None


def _is_missing_repo(result: ProjectFactoryInitCommandResult) -> bool:
    output = f"{result.stdout}\n{result.stderr}".lower()
    return any(marker in output for marker in _MISSING_REPO_MARKERS)


def _remote_matches(origin_url: str, owner: str, name: str, repo_url: str) -> bool:
    normalized = origin_url.rstrip("/")
    candidates = {
        repo_url.rstrip("/"),
        f"https://github.com/{owner}/{name}".rstrip("/"),
        f"https://github.com/{owner}/{name}.git".rstrip("/"),
        f"git@github.com:{owner}/{name}.git".rstrip("/"),
    }
    return normalized in candidates


def _redacted_env_keys(env: dict[str, str] | None) -> tuple[str, ...]:
    keys = set(env or {}) | {key for key in os.environ if key in _SENSITIVE_ENV_KEYS}
    return tuple(sorted(key for key in keys if key in _SENSITIVE_ENV_KEYS))


def _sensitive_values(env: dict[str, str] | None) -> tuple[str, ...]:
    values: list[str] = []
    for source in (env or {}, os.environ):
        for key, value in source.items():
            if key in _SENSITIVE_ENV_KEYS and value:
                values.append(value)
    return tuple(values)


def _summarize_output(text: str, sensitive_values: tuple[str, ...]) -> str:
    summary = (text or "").strip()
    for value in sensitive_values:
        summary = summary.replace(value, "[redacted]")
    if len(summary) > 500:
        return f"{summary[:497]}..."
    return summary


def _expect_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Expected object payload.")
    return value


def _optional_clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _slug_from_name(name: str) -> str:
    slug = "-".join(
        "".join(char.lower() if char.isalnum() else " " for char in name).split()
    )
    return slug or "new-project"


def _read_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Expected JSON object.")
    return payload


def _read_json_file(path: Path) -> object:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    temp_path.replace(path)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"
