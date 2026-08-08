from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import shlex
import shutil
import subprocess
from threading import RLock
from typing import Any, Mapping, Protocol
from uuid import uuid4

import yaml

from backend.app.application.services.project_factory_manifest_service import (
    ProjectFactoryManifestInput,
    ProjectFactoryManifestService,
)
from backend.app.application.services.project_scaffold_providers import (
    ProviderContext,
    ProviderRegistry,
    ProviderResult,
    STACK_PRESETS,
    default_provider_registry,
    resolve_android_sdk_root,
)
from backend.app.domain.entities.project_scaffold import (
    AwsReadinessMode,
    CapabilityEvidenceState,
    CloudflareMode,
    CreationMode,
    SCAFFOLD_FORBIDDEN_CONTENT,
    SCAFFOLD_SKIPPED_PRODUCT_WORK,
    ScaffoldLifecycleState,
    TargetKind,
)


SCAFFOLD_PHASE_ORDER: tuple[str, ...] = (
    "scaffold_preflight",
    "scaffold_contract",
    "workspace_baseline",
    "target_bootstrap",
    "target_validation",
    "local_git_commit",
    "github_repository",
    "cloudflare_scaffold",
    "aws_readiness",
    "workbench_registration",
    "scaffold_context_pack",
)

_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$")
_REDACT = re.compile(
    r"(?i)(authorization|token|secret|password|api[_-]?key|account[_-]?id)([=: ]+)([^\s,;]+)"
)


class ScaffoldError(ValueError):
    pass


class ScaffoldCommandRunner(Protocol):
    def run(
        self,
        command: tuple[str, ...],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
    ) -> "ScaffoldCommandResult": ...


@dataclass(frozen=True, slots=True)
class ScaffoldCommandResult:
    command: tuple[str, ...]
    exit_code: int
    stdout: str = ""
    stderr: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "command": [_redact(item) for item in self.command],
            "exit_code": self.exit_code,
            "stdout": _redact(self.stdout[-4000:]),
            "stderr": _redact(self.stderr[-4000:]),
        }


class SubprocessScaffoldCommandRunner:
    def run(
        self,
        command: tuple[str, ...],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
    ) -> ScaffoldCommandResult:
        process_env = {**os.environ, **dict(env or {})}
        android_sdk = resolve_android_sdk_root(process_env)
        if android_sdk is not None:
            process_env.setdefault("ANDROID_HOME", str(android_sdk))
            process_env.setdefault("ANDROID_SDK_ROOT", str(android_sdk))
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=process_env,
            text=True,
            capture_output=True,
            check=False,
            timeout=1800,
        )
        return ScaffoldCommandResult(
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


@dataclass(frozen=True, slots=True)
class ScaffoldDraftInput:
    name: str
    slug: str | None = None
    stack_preset: str | None = "expo-sveltekit-fastapi"
    mobile_provider: str | None = None
    web_provider: str | None = None
    api_provider: str | None = None
    cloudflare_mode: CloudflareMode = CloudflareMode.PROVISION_SCAFFOLD
    aws_mode: AwsReadinessMode = AwsReadinessMode.NONE
    github_owner: str | None = None
    github_visibility: str = "private"
    github_mode: str = "create_or_verify"
    preview_protected: bool = False
    initial_admin_email: str | None = None


@dataclass(frozen=True, slots=True)
class ScaffoldDraft:
    id: str
    created_at: str
    updated_at: str
    status: ScaffoldLifecycleState
    request: ScaffoldDraftInput
    manifest: Mapping[str, Any]
    contract_preview: Mapping[str, Any]
    contract_hash: str
    confirmed_at: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": "codex.projectScaffoldDraft",
            "version": 2,
            "draftId": self.id,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "creationMode": CreationMode.SCAFFOLD.value,
            "status": self.status.value,
            "request": _draft_request_payload(self.request),
            "manifest": dict(self.manifest),
            "contractPreview": dict(self.contract_preview),
            "contractHash": self.contract_hash,
            "confirmedAt": self.confirmed_at,
            "readyForConfirmation": self.status is ScaffoldLifecycleState.DRAFT,
        }


@dataclass(frozen=True, slots=True)
class ScaffoldPhase:
    name: str
    status: str = "queued"
    message: str = ""
    evidence: tuple[Mapping[str, Any], ...] = ()
    blockers: tuple[Mapping[str, Any], ...] = ()
    started_at: str | None = None
    completed_at: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "evidence": [dict(item) for item in self.evidence],
            "blockers": [dict(item) for item in self.blockers],
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
        }


@dataclass(frozen=True, slots=True)
class ScaffoldJob:
    id: str
    draft_id: str
    created_at: str
    updated_at: str
    workspace_path: str
    lifecycle_state: ScaffoldLifecycleState
    phases: tuple[ScaffoldPhase, ...]
    provider_plans: tuple[Mapping[str, Any], ...] = ()
    provider_results: tuple[Mapping[str, Any], ...] = ()
    resources: tuple[Mapping[str, Any], ...] = ()
    result: Mapping[str, Any] | None = None
    domain_factory_relationship: Mapping[str, Any] | None = None
    cancelled: bool = False

    def phase(self, name: str) -> ScaffoldPhase:
        return next(item for item in self.phases if item.name == name)

    def with_phase(self, phase: ScaffoldPhase) -> "ScaffoldJob":
        return replace(
            self,
            phases=tuple(phase if item.name == phase.name else item for item in self.phases),
            updated_at=_now(),
        )

    def to_payload(self) -> dict[str, Any]:
        current = next(
            (item.name for item in self.phases if item.status in {"running", "blocked"}),
            self.phases[-1].name,
        )
        blockers = [
            dict(blocker)
            for phase in self.phases
            for blocker in phase.blockers
        ]
        return {
            "kind": "codex.projectScaffoldJob",
            "version": 2,
            "scaffoldJobId": self.id,
            "draftId": self.draft_id,
            "creationMode": CreationMode.SCAFFOLD.value,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "workspacePath": self.workspace_path,
            "status": self.lifecycle_state.value,
            "currentPhase": current,
            "phases": [item.to_payload() for item in self.phases],
            "providerPlans": [dict(item) for item in self.provider_plans],
            "providerResults": [dict(item) for item in self.provider_results],
            "resources": [dict(item) for item in self.resources],
            "blockers": blockers,
            "result": dict(self.result) if self.result is not None else None,
            "canRetry": (
                bool(blockers)
                or (
                    self.cancelled
                    and not any(item.status == "running" for item in self.phases)
                    and any(item.status == "cancelled" for item in self.phases)
                )
            )
            and self.domain_factory_relationship is None,
            "canStartProduct": self.domain_factory_relationship is None
            and self.lifecycle_state is ScaffoldLifecycleState.SCAFFOLD_READY,
            "domainFactoryRelationship": (
                dict(self.domain_factory_relationship)
                if self.domain_factory_relationship is not None
                else None
            ),
            "cancelled": self.cancelled,
        }


class ProjectScaffoldService:
    def __init__(
        self,
        *,
        projects_root: str | Path,
        state_root: str | Path,
        provider_registry: ProviderRegistry | None = None,
        command_runner: ScaffoldCommandRunner | None = None,
        execute_commands: bool = True,
        allow_remote_writes: bool = True,
        github_owner: str | None = None,
    ) -> None:
        self._projects_root = Path(projects_root).expanduser().resolve()
        self._state_root = Path(state_root).expanduser().resolve() / "scaffolds"
        self._draft_dir = self._state_root / "drafts"
        self._job_dir = self._state_root / "jobs"
        self._registry = provider_registry or default_provider_registry()
        self._manifest = ProjectFactoryManifestService(
            projects_root=self._projects_root,
            provider_registry=self._registry,
        )
        self._runner = command_runner or SubprocessScaffoldCommandRunner()
        self._execute_commands = execute_commands
        self._allow_remote_writes = allow_remote_writes
        self._github_owner = github_owner
        self._lock = RLock()
        self._drafts: dict[str, ScaffoldDraft] = {}
        self._jobs: dict[str, ScaffoldJob] = {}
        self._draft_dir.mkdir(parents=True, exist_ok=True)
        self._job_dir.mkdir(parents=True, exist_ok=True)
        self._load()

    def create_draft(self, request: ScaffoldDraftInput) -> ScaffoldDraft:
        resolved = self._resolve_request(request)
        slug = resolved.slug or _slug(resolved.name)
        if not _SLUG.fullmatch(slug):
            raise ScaffoldError("Invalid scaffold slug.")
        if resolved.preview_protected and not _valid_email(resolved.initial_admin_email):
            raise ScaffoldError(
                "initialAdminEmail is required only for a protected scaffold preview."
            )
        if (
            resolved.preview_protected
            and resolved.cloudflare_mode is not CloudflareMode.PROVISION_SCAFFOLD
        ):
            raise ScaffoldError(
                "Protected scaffold preview requires cloudflareMode=provision_scaffold."
            )
        plan = self._manifest.plan_manifest(
            ProjectFactoryManifestInput(
                name=resolved.name,
                business_type="",
                primary_goal="",
                slug=slug,
                creation_mode=CreationMode.SCAFFOLD,
                mobile_provider=resolved.mobile_provider,
                web_provider=resolved.web_provider,
                api_provider=resolved.api_provider,
                cloudflare_mode=resolved.cloudflare_mode,
                aws_mode=resolved.aws_mode,
                stack_preset=resolved.stack_preset,
                initial_admin_emails=(resolved.initial_admin_email,)
                if resolved.initial_admin_email
                else (),
            )
        )
        if not plan.ok:
            raise ScaffoldError("; ".join(item.message for item in plan.errors))
        preview = self._contract_preview(resolved, plan.manifest)
        contract_hash = _hash(preview)
        now = _now()
        draft = ScaffoldDraft(
            id=f"scaffold-draft-{uuid4().hex[:12]}",
            created_at=now,
            updated_at=now,
            status=ScaffoldLifecycleState.DRAFT,
            request=resolved,
            manifest=plan.manifest,
            contract_preview=preview,
            contract_hash=contract_hash,
        )
        with self._lock:
            self._drafts[draft.id] = draft
            self._persist_draft(draft)
        return draft

    def get_draft(self, draft_id: str) -> ScaffoldDraft | None:
        return self._drafts.get(draft_id)

    def list_drafts(self) -> tuple[ScaffoldDraft, ...]:
        return tuple(sorted(self._drafts.values(), key=lambda item: item.created_at, reverse=True))

    def confirm_draft(self, draft_id: str, expected_hash: str) -> ScaffoldDraft:
        with self._lock:
            draft = self._require_draft(draft_id)
            if expected_hash != draft.contract_hash:
                raise ScaffoldError("Scaffold contract changed; review it again.")
            if draft.status is ScaffoldLifecycleState.SCAFFOLD_CONTRACT_READY:
                return draft
            confirmed = replace(
                draft,
                status=ScaffoldLifecycleState.SCAFFOLD_CONTRACT_READY,
                updated_at=_now(),
                confirmed_at=_now(),
            )
            self._drafts[draft_id] = confirmed
            self._persist_draft(confirmed)
            return confirmed

    def start_or_resume(self, draft_id: str) -> ScaffoldJob:
        with self._lock:
            draft = self._require_draft(draft_id)
            if draft.status is not ScaffoldLifecycleState.SCAFFOLD_CONTRACT_READY:
                raise ScaffoldError("Confirm the scaffold contract before starting.")
            existing = next((item for item in self._jobs.values() if item.draft_id == draft_id), None)
            if existing is not None:
                return existing
            slug = str(_project(draft.manifest).get("slug"))
            workspace = self._safe_workspace(slug)
            now = _now()
            job = ScaffoldJob(
                id=f"scaffold-job-{uuid4().hex[:12]}",
                draft_id=draft_id,
                created_at=now,
                updated_at=now,
                workspace_path=str(workspace),
                lifecycle_state=ScaffoldLifecycleState.SCAFFOLD_INITIALIZING,
                phases=tuple(ScaffoldPhase(name=name) for name in SCAFFOLD_PHASE_ORDER),
            )
            self._jobs[job.id] = job
            self._persist_job(job)
            return job

    def get_job(self, job_id: str) -> ScaffoldJob | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> tuple[ScaffoldJob, ...]:
        return tuple(sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True))

    def cancel(self, job_id: str) -> ScaffoldJob:
        with self._lock:
            job = self._require_job(job_id)
            cancelled = replace(job, cancelled=True, updated_at=_now())
            return self._cancel_remaining(cancelled)

    def retry(self, job_id: str) -> ScaffoldJob:
        with self._lock:
            job = self._require_job(job_id)
            if job.domain_factory_relationship is not None:
                raise ScaffoldError(
                    "A scaffold linked to Domain Factory cannot be retried."
                )
            reset_candidates = [
                index
                for index, item in enumerate(job.phases)
                if item.status in {"blocked", "cancelled"}
            ]
            if not reset_candidates:
                return job
            reset_from = min(reset_candidates)
            phases = tuple(
                replace(
                    item,
                    status="queued",
                    evidence=(),
                    blockers=(),
                    message="",
                    started_at=None,
                    completed_at=None,
                )
                if index >= reset_from
                else item
                for index, item in enumerate(job.phases)
            )
            reset = replace(
                job,
                lifecycle_state=ScaffoldLifecycleState.SCAFFOLD_INITIALIZING,
                phases=phases,
                result=None,
                cancelled=False,
                updated_at=_now(),
            )
            self._jobs[job_id] = reset
            self._persist_job(reset)
            return reset

    def run(self, job_id: str) -> ScaffoldJob:
        for name in SCAFFOLD_PHASE_ORDER:
            job = self._require_job(job_id)
            if job.cancelled:
                return self._cancel_remaining(job)
            phase = job.phase(name)
            if phase.status in {"completed", "skipped"}:
                continue
            dependency = _blocked_dependency(job, name)
            if (
                name == "cloudflare_scaffold"
                and self._require_draft(job.draft_id).request.cloudflare_mode
                is not CloudflareMode.PROVISION_SCAFFOLD
                and dependency != "scaffold_preflight"
            ):
                dependency = None
            if dependency is not None:
                job = self._finish_phase(
                    job,
                    name,
                    evidence=(),
                    blockers=(
                        _blocker(
                            "upstream_phase_blocked",
                            f"{name} was not executed because {dependency} is blocked.",
                            f"Resolve {dependency}, then retry from that phase.",
                        ),
                    ),
                )
                continue
            try:
                job = self._start_phase(job, name)
                handler = getattr(self, f"_phase_{name}")
                evidence, blockers = handler(job, self._require_draft(job.draft_id))
                job = self._finish_phase(
                    self._require_job(job_id),
                    name,
                    evidence=evidence,
                    blockers=blockers,
                )
            except Exception as exc:
                job = self._finish_phase(
                    self._require_job(job_id),
                    name,
                    evidence=(),
                    blockers=(
                        _blocker(
                            "scaffold_phase_failed",
                            _redact(str(exc)),
                            f"Fix {name} and retry the scaffold job.",
                        ),
                    ),
                )
            if name == "scaffold_context_pack":
                break
        return self._derive_completion(self._require_job(job_id))

    def start_product(self, job_id: str, *, session_id: str) -> ScaffoldJob:
        with self._lock:
            job = self._require_job(job_id)
            if job.domain_factory_relationship is not None:
                return job
            if job.lifecycle_state is not ScaffoldLifecycleState.SCAFFOLD_READY:
                raise ScaffoldError("Start Product requires scaffold_ready.")
            relationship = {
                "scaffoldJobId": job.id,
                "sessionId": session_id,
                "workspacePath": job.workspace_path,
                "sourceApp": _project(self._require_draft(job.draft_id).manifest).get("slug"),
                "status": ScaffoldLifecycleState.DOMAIN_INTAKE.value,
                "reuse": {
                    "workspace": True,
                    "github": True,
                    "cloudflare": True,
                    "workbench": True,
                    "providers": True,
                },
                "authorizedAt": _now(),
            }
            result_payload = (
                dict(job.result) if job.result is not None else None
            )
            if result_payload is not None:
                result_payload["domainFactoryRelationship"] = relationship
                result_payload["startProductAvailable"] = False
            workspace = Path(job.workspace_path)
            manifest_path = _safe_workspace_file(workspace, ".codex/project.yaml")
            result_path = _safe_workspace_file(
                workspace, ".codex/factory/scaffold-result.json"
            )
            updated = replace(
                job,
                domain_factory_relationship=relationship,
                result=result_payload,
                updated_at=_now(),
            )
            self._jobs[job_id] = updated
            self._persist_job(updated)
            if manifest_path.is_file():
                manifest = dict(_read_yaml(manifest_path))
                manifest["lifecycle"] = {
                    "state": ScaffoldLifecycleState.DOMAIN_INTAKE.value,
                    "next_action": "complete_product_intake",
                }
                _write_generated(
                    manifest_path,
                    yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True),
                )
            if result_path.is_file() and result_payload is not None:
                _write_generated(result_path, _json(result_payload))
            return updated

    def rollback_product_start(self, job_id: str, *, session_id: str) -> ScaffoldJob:
        """Undo only this transition when Domain Factory activation fails."""
        with self._lock:
            job = self._require_job(job_id)
            relationship = job.domain_factory_relationship
            if relationship is None or relationship.get("sessionId") != session_id:
                return job
            workspace = Path(job.workspace_path)
            manifest_path = _safe_workspace_file(workspace, ".codex/project.yaml")
            result_path = _safe_workspace_file(
                workspace, ".codex/factory/scaffold-result.json"
            )
            result_payload = dict(job.result) if job.result is not None else None
            if result_payload is not None:
                result_payload.pop("domainFactoryRelationship", None)
                result_payload["startProductAvailable"] = True
            if manifest_path.is_file():
                manifest = dict(_read_yaml(manifest_path))
                manifest["lifecycle"] = {
                    "state": ScaffoldLifecycleState.SCAFFOLD_READY.value,
                    "next_action": "start_product",
                }
                _write_generated(
                    manifest_path,
                    yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True),
                )
            if result_path.is_file() and result_payload is not None:
                _write_generated(result_path, _json(result_payload))
            rolled_back = replace(
                job,
                domain_factory_relationship=None,
                result=result_payload,
                updated_at=_now(),
            )
            self._jobs[job_id] = rolled_back
            self._persist_job(rolled_back)
            return rolled_back

    def _phase_scaffold_preflight(self, job: ScaffoldJob, draft: ScaffoldDraft):
        workspace = Path(job.workspace_path)
        if workspace.exists() and any(workspace.iterdir()):
            try:
                manifest_path = _safe_workspace_file(
                    workspace, ".codex/project.yaml"
                )
            except ScaffoldError:
                return (), (
                    _blocker(
                        "unsafe_workspace_symlink",
                        "The existing scaffold manifest resolves outside the workspace.",
                        "Remove the unsafe symlink or choose another project slug.",
                    ),
                )
            if not manifest_path.is_file() or not _matches_existing_scaffold(
                manifest_path,
                draft,
            ):
                return (), (_blocker("target_conflict", "Target workspace is non-empty and not the approved matching scaffold.", "Choose another slug or reconcile the existing directory."),)
            if (workspace / ".git").is_dir() and self._execute_commands:
                status = self._runner.run(("git", "status", "--porcelain"), cwd=workspace)
                if status.exit_code != 0 or status.stdout.strip():
                    return (status.to_payload(),), (
                        _blocker(
                            "existing_worktree_dirty",
                            "The existing scaffold worktree has user-owned changes.",
                            "Commit or stash those changes explicitly before retrying Scaffold.",
                        ),
                    )
        checks: list[Mapping[str, Any]] = [
            {"check": "projects_root", "ok": self._projects_root.is_dir() and os.access(self._projects_root, os.W_OK)},
            {"check": "workspace_safe", "ok": True, "path": str(workspace)},
            {"check": "terraform_apply_forbidden", "ok": True},
            {"check": "remote_writes_previewed", "ok": True, "effects": draft.contract_preview["remoteEffects"]},
        ]
        blockers: list[Mapping[str, Any]] = []
        for kind, provider_id in _selected_providers(draft.manifest).items():
            doctor = self._registry.get(kind, provider_id).doctor(self._provider_context(job, draft))
            checks.append({"check": f"provider:{kind.value}:{provider_id}", **doctor.to_payload()})
            if self._execute_commands:
                blockers.extend(
                    _blocker(item.code, item.message, item.next_action)
                    for item in doctor.blockers
                )
        return tuple(checks), tuple(blockers)

    def _phase_scaffold_contract(self, job: ScaffoldJob, draft: ScaffoldDraft):
        workspace = Path(job.workspace_path)
        workspace.mkdir(parents=True, exist_ok=True)
        contract = {
            "creationMode": "scaffold",
            "contractHash": draft.contract_hash,
            "manifest": dict(draft.manifest),
            "skippedProductWork": list(SCAFFOLD_SKIPPED_PRODUCT_WORK),
            "approvedAt": draft.confirmed_at,
        }
        path = _safe_workspace_file(
            workspace, ".codex/factory/scaffold-contract.json"
        )
        _write_generated(path, _json(contract))
        return ({"path": str(path), "sha256": _file_hash(path)},), ()

    def _phase_workspace_baseline(self, job: ScaffoldJob, draft: ScaffoldDraft):
        workspace = Path(job.workspace_path)
        files = _baseline_files(draft, self._registry, workspace)
        generated, blockers = _write_bundle(workspace, files)
        return tuple({"path": item, "sha256": _file_hash(workspace / item)} for item in generated), blockers

    def _phase_target_bootstrap(self, job: ScaffoldJob, draft: ScaffoldDraft):
        context = self._provider_context(job, draft)
        plans: list[Mapping[str, Any]] = []
        results: list[Mapping[str, Any]] = []
        blockers: list[Mapping[str, Any]] = []
        for kind, provider_id in _code_providers(draft.manifest).items():
            provider = self._registry.get(kind, provider_id)
            descriptor = provider.descriptor
            plan = provider.plan(context)
            owned_conflicts = _provider_owned_conflicts(
                job,
                provider_id=provider_id,
                target_kind=kind,
                workspace=Path(job.workspace_path),
            )
            if owned_conflicts:
                blocker = _blocker(
                    "provider_generated_file_changed",
                    (
                        f"Refusing to rerun {provider_id}; generated files changed "
                        f"after the previous attempt: {', '.join(owned_conflicts[:10])}."
                    ),
                    "Commit/reconcile those changes explicitly, then start a reviewed recovery.",
                )
                plans.append(plan.to_payload())
                results.append(
                    {
                        "provider_id": provider_id,
                        "target_kind": kind.value,
                        "status": CapabilityEvidenceState.BLOCKED.value,
                        "generated_files": owned_conflicts,
                        "generated_file_hashes": {},
                        "commands": [],
                        "capabilities": [],
                        "artifacts": [],
                        "blockers": [blocker],
                        "command_evidence": [],
                    }
                )
                blockers.append(blocker)
                continue
            before_files = _workspace_files(Path(job.workspace_path))
            result = provider.scaffold(context, plan)
            command_results: list[Mapping[str, Any]] = []
            command_blockers: list[Mapping[str, Any]] = []
            if not result.blockers:
                command_results, command_blockers = self._run_provider_commands(
                    provider_id,
                    kind,
                    result,
                    workspace=Path(job.workspace_path),
                )
            if result.commands and not self._execute_commands:
                command_blockers.append(
                    _blocker(
                        "bootstrap_commands_not_executed",
                        f"{provider_id} bootstrap commands were prepared but not executed.",
                        "Enable PROJECT_SCAFFOLD_EXECUTE_COMMANDS and retry target_bootstrap.",
                    )
                )
            elif self._execute_commands and not command_blockers:
                command_blockers.extend(
                    _artifact_blockers(
                        Path(job.workspace_path),
                        descriptor.bootstrap_artifacts,
                        provider_id=provider_id,
                        stage="bootstrap",
                    )
                )
            plans.append(plan.to_payload())
            result_payload = result.to_payload()
            generated_files = sorted(
                set(result.generated_files)
                | _owned_generated_files(
                    Path(job.workspace_path),
                    before_files,
                )
            )
            result_payload["generated_files"] = generated_files
            result_payload["generated_file_hashes"] = {
                relative: _file_hash(Path(job.workspace_path) / relative)
                for relative in generated_files
                if (Path(job.workspace_path) / relative).is_file()
            }
            result_payload["command_evidence"] = command_results
            if command_blockers:
                result_payload["status"] = CapabilityEvidenceState.BLOCKED.value
            results.append(result_payload)
            blockers.extend(
                _blocker(item.code, item.message, item.next_action)
                for item in result.blockers
            )
            blockers.extend(command_blockers)
        updated = replace(job, provider_plans=tuple(plans), provider_results=tuple(results))
        self._store_job(updated)
        return tuple(results), tuple(blockers)

    def _phase_target_validation(self, job: ScaffoldJob, draft: ScaffoldDraft):
        context = self._provider_context(job, draft)
        evidence: list[Mapping[str, Any]] = []
        blockers: list[Mapping[str, Any]] = []
        results: list[Mapping[str, Any]] = list(job.provider_results)
        for kind, provider_id in _code_providers(draft.manifest).items():
            provider = self._registry.get(kind, provider_id)
            descriptor = provider.descriptor
            plan = provider.plan(context)
            owned_conflicts = _provider_owned_conflicts(
                job,
                provider_id=provider_id,
                target_kind=kind,
                workspace=Path(job.workspace_path),
            )
            if owned_conflicts:
                blockers.append(
                    _blocker(
                        "provider_generated_file_changed",
                        (
                            f"Refusing to validate {provider_id}; generated files "
                            f"changed after bootstrap: {', '.join(owned_conflicts[:10])}."
                        ),
                        "Commit/reconcile those changes explicitly, then start a reviewed recovery.",
                    )
                )
                continue
            validation = provider.validate(context, plan)
            command_results, command_blockers = self._run_provider_commands(
                provider_id,
                kind,
                validation,
                workspace=Path(job.workspace_path),
            )
            if self._execute_commands and not command_blockers:
                command_blockers.extend(
                    _artifact_blockers(
                        Path(job.workspace_path),
                        descriptor.validation_artifacts,
                        provider_id=provider_id,
                        stage="validation",
                    )
                )
            payload = validation.to_payload()
            payload["command_evidence"] = command_results
            if command_blockers:
                payload["status"] = CapabilityEvidenceState.BLOCKED.value
            elif validation.commands and not self._execute_commands:
                payload["status"] = CapabilityEvidenceState.BLOCKED.value
                command_blockers.append(
                    _blocker(
                        "local_validation_not_executed",
                        f"{provider_id} validation commands were prepared but not executed.",
                        "Enable PROJECT_SCAFFOLD_EXECUTE_COMMANDS and retry target_validation.",
                    )
                )
            elif self._execute_commands and not validation.blockers:
                payload["status"] = CapabilityEvidenceState.LOCALLY_VERIFIED.value
                for capability in payload["capabilities"]:
                    if capability["state"] != CapabilityEvidenceState.UNSUPPORTED.value:
                        capability["state"] = (
                            CapabilityEvidenceState.LOCALLY_VERIFIED.value
                        )
            results.append(payload)
            evidence.append(payload)
            blockers.extend(
                _blocker(item.code, item.message, item.next_action)
                for item in validation.blockers
            )
            blockers.extend(command_blockers)
        forbidden = _scan_forbidden_product_content(Path(job.workspace_path))
        if forbidden:
            blockers.append(_blocker("forbidden_product_content", f"Scaffold contains forbidden product content: {', '.join(forbidden[:10])}", "Remove product/domain/UX content from generated scaffold files."))
        secrets = _scan_generated_secrets(Path(job.workspace_path))
        if secrets:
            blockers.append(
                _blocker(
                    "generated_secret_detected",
                    f"Generated scaffold contains possible secrets: {', '.join(secrets[:10])}",
                    "Remove credentials and use runtime secret injection before retrying.",
                )
            )
        updated = replace(job, provider_results=tuple(results))
        self._store_job(updated)
        return tuple(evidence), tuple(blockers)

    def _phase_local_git_commit(self, job: ScaffoldJob, draft: ScaffoldDraft):
        del draft
        workspace = Path(job.workspace_path)
        if not self._execute_commands:
            evidence = ({"status": "prepared", "commands": [["git", "init"], ["git", "add", "."], ["git", "commit", "-m", "Create composable project scaffold"]]},)
            return evidence, (
                _blocker(
                    "local_git_commit_not_executed",
                    "The clean baseline Git commit was prepared but not executed.",
                    "Enable PROJECT_SCAFFOLD_EXECUTE_COMMANDS and retry local_git_commit.",
                ),
            )
        commands = [
            ("git", "init", "-b", "main"),
            ("git", "add", "."),
            ("git", "-c", "user.name=Codex Project Factory", "-c", "user.email=codex@nienfos.com", "commit", "-m", "Create composable project scaffold"),
            ("git", "status", "--porcelain"),
        ]
        results = [self._runner.run(command, cwd=workspace) for command in commands]
        failed = next((item for item in results if item.exit_code != 0 and "nothing to commit" not in item.stdout + item.stderr), None)
        dirty = bool(results[-1].stdout.strip())
        blockers = ()
        if failed or dirty or not (workspace / ".git").is_dir():
            detail = (
                failed.stderr
                if failed
                else results[-1].stdout
                if dirty
                else "Git repository metadata was not created."
            )
            blockers = (_blocker("local_git_commit_failed", _redact(detail), "Inspect git status in the scaffold workspace and retry."),)
        return tuple(item.to_payload() for item in results), blockers

    def _phase_github_repository(self, job: ScaffoldJob, draft: ScaffoldDraft):
        request = draft.request
        if request.github_mode == "disabled":
            return ({"status": "skipped", "reason": "not requested"},), ()
        owner = request.github_owner or self._github_owner
        if not owner:
            return (), (_blocker("github_owner_missing", "GitHub owner could not be inferred.", "Set githubOwner and retry this phase."),)
        slug = str(_project(draft.manifest)["slug"])
        repo = f"{owner}/{slug}"
        url = f"https://github.com/{repo}"
        if not (self._execute_commands and self._allow_remote_writes):
            evidence = ({"status": "prepared", "repo": repo, "url": url, "remoteWrite": True},)
            return evidence, (
                _blocker(
                    "github_remote_write_not_executed",
                    f"GitHub repository {repo} was requested but not verified or pushed.",
                    "Enable scaffold command execution and authorized remote writes, authenticate gh, then retry.",
                ),
            )
        workspace = Path(job.workspace_path)
        view = self._runner.run(("gh", "repo", "view", repo, "--json", "url"), cwd=workspace)
        evidence = [view.to_payload()]
        if view.exit_code != 0:
            create = self._runner.run(("gh", "repo", "create", repo, f"--{request.github_visibility}", "--source", ".", "--remote", "origin", "--push"), cwd=workspace)
            evidence.append(create.to_payload())
            if create.exit_code != 0:
                return tuple(evidence), (_blocker("github_create_failed", _redact(create.stderr), f"Authenticate gh, verify {repo}, and retry."),)
        else:
            remote = self._runner.run(("git", "remote", "get-url", "origin"), cwd=workspace)
            if remote.exit_code == 0:
                actual_repo = _github_repo_from_remote(remote.stdout)
                if actual_repo != repo.lower():
                    evidence.append(remote.to_payload())
                    return tuple(evidence), (
                        _blocker(
                            "github_origin_mismatch",
                            f"Existing origin does not match the approved repository {repo}.",
                            "Reconcile origin explicitly, then retry without changing unrelated remotes automatically.",
                        ),
                    )
            else:
                remote = self._runner.run(("git", "remote", "add", "origin", f"https://github.com/{repo}.git"), cwd=workspace)
            push = self._runner.run(("git", "push", "-u", "origin", "main"), cwd=workspace)
            evidence.extend((remote.to_payload(), push.to_payload()))
            if push.exit_code != 0:
                return tuple(evidence), (_blocker("github_push_failed", _redact(push.stderr), f"Run git push -u origin main in {workspace}."),)
        self._append_resource(job.id, {"kind": "github_repository", "id": repo, "url": url, "status": "verified"})
        return tuple(evidence), ()

    def _phase_cloudflare_scaffold(self, job: ScaffoldJob, draft: ScaffoldDraft):
        mode = draft.request.cloudflare_mode
        if mode is CloudflareMode.DISABLED:
            return ({"status": "skipped", "mode": mode.value, "remoteWrites": 0},), ()
        workspace = Path(job.workspace_path)
        files = _cloudflare_files(draft, self._registry)
        generated, blockers = _write_bundle(workspace, files)
        evidence: list[Mapping[str, Any]] = [{"status": "generated", "mode": mode.value, "files": generated, "d1": False, "api_ready": False, "product_ready": False, "production_ready": False, "installable": False}]
        if blockers or mode is CloudflareMode.GENERATE_ONLY:
            return tuple(evidence), blockers
        if draft.request.preview_protected:
            evidence.append(
                {
                    "status": "blocked",
                    "previewProtected": True,
                    "remoteWrites": 0,
                    "d1": False,
                }
            )
            return tuple(evidence), (
                _blocker(
                    "protected_preview_access_not_configured",
                    (
                        "The D1-free scaffold cannot enforce the existing invite/access "
                        "contract, so it was not deployed publicly."
                    ),
                    (
                        "Choose an unprotected neutral scaffold, or authorize a separate "
                        "reviewed preview-access/persistence setup before retrying."
                    ),
                ),
            )
        if not (self._execute_commands and self._allow_remote_writes):
            evidence.append({"status": "prepared", "remoteWrite": True, "command": ["wrangler", "deploy", "--config", "infra/cloudflare/wrangler.toml"]})
            return tuple(evidence), (
                _blocker(
                    "cloudflare_remote_write_not_executed",
                    "Cloudflare provisioning was requested but the scaffold was not deployed.",
                    "Enable authorized remote writes, authenticate Wrangler, and retry cloudflare_scaffold.",
                ),
            )
        deploy = self._runner.run(("wrangler", "deploy", "--config", "infra/cloudflare/wrangler.toml"), cwd=workspace)
        evidence.append(deploy.to_payload())
        if deploy.exit_code != 0:
            return tuple(evidence), (_blocker("cloudflare_provision_failed", _redact(deploy.stderr), "Authenticate Wrangler and rerun cloudflare_scaffold."),)
        preview_url = _cloudflare_preview_url(draft)
        smoke = self._runner.run(
            ("curl", "--fail", "--silent", "--show-error", preview_url),
            cwd=workspace,
        )
        evidence.append(smoke.to_payload())
        if smoke.exit_code != 0:
            return tuple(evidence), (
                _blocker(
                    "cloudflare_smoke_failed",
                    _redact(smoke.stderr) or "Cloudflare scaffold smoke check failed.",
                    f"Verify {preview_url} and retry cloudflare_scaffold.",
                ),
            )
        self._append_resource(job.id, {"kind": "cloudflare_scaffold", "id": str(_project(draft.manifest)["slug"]), "url": preview_url, "d1": False, "apiReady": False, "productReady": False, "productionReady": False, "installable": False, "status": "remotely_verified"})
        return tuple(evidence), ()

    def _phase_aws_readiness(self, job: ScaffoldJob, draft: ScaffoldDraft):
        mode = draft.request.aws_mode
        if mode is AwsReadinessMode.NONE:
            return ({"status": "skipped", "mode": "none", "terraformApply": False},), ()
        workspace = Path(job.workspace_path)
        files = _aws_files(draft)
        generated, blockers = _write_bundle(workspace, files)
        evidence: list[Mapping[str, Any]] = [{"status": "generated", "mode": mode.value, "files": generated, "terraformApply": False, "resourcesCreated": 0}]
        if blockers or mode is AwsReadinessMode.ARCHITECTURE_DOCS_ONLY:
            return tuple(evidence), blockers
        if not self._execute_commands:
            return tuple(evidence), (
                _blocker(
                    "terraform_validation_not_executed",
                    "Terraform-ready files were generated but fmt/init/validate were not executed.",
                    "Enable PROJECT_SCAFFOLD_EXECUTE_COMMANDS, install Terraform, and retry; never run apply from Scaffold.",
                ),
            )
        if self._execute_commands and shutil.which("terraform"):
            for command in (("terraform", "fmt", "-check", "-recursive"), ("terraform", "-chdir=infra/aws", "init", "-backend=false"), ("terraform", "-chdir=infra/aws", "validate")):
                result = self._runner.run(command, cwd=workspace)
                evidence.append(result.to_payload())
                if result.exit_code != 0:
                    return tuple(evidence), (_blocker("terraform_validation_failed", _redact(result.stderr), "Run terraform fmt and terraform validate; never run apply from Scaffold."),)
        return tuple(evidence), ()

    def _phase_workbench_registration(self, job: ScaffoldJob, draft: ScaffoldDraft):
        workspace = Path(job.workspace_path)
        required = ["codex-bridge.yaml", ".sdd/spec-index.yaml", "specs/000-project-scaffold/spec.md"]
        missing = [item for item in required if not (workspace / item).is_file()]
        if missing:
            return (), (_blocker("workbench_registration_failed", f"Missing Workbench files: {', '.join(missing)}", "Retry workspace_baseline."),)
        source_app = _read_yaml(workspace / "codex-bridge.yaml").get("source_app")
        scope = {
            "kind": "workbench_scope",
            "id": str(_project(draft.manifest)["slug"]),
            "workspacePath": str(workspace),
            "sourceApp": source_app,
            "status": "verified",
            "ownedBy": "codex_mobile_bridge",
            "productNavigationEntry": False,
        }
        self._append_resource(job.id, scope)
        return (scope,), ()

    def _phase_scaffold_context_pack(self, job: ScaffoldJob, draft: ScaffoldDraft):
        workspace = Path(job.workspace_path)
        preflight_blocked = job.phase("scaffold_preflight").status == "blocked"
        context_root = (
            self._state_root / "contexts" / job.id
            if preflight_blocked
            else _safe_workspace_file(workspace, ".codex/factory")
        )
        previous_blockers = [dict(blocker) for phase in job.phases if phase.name != "scaffold_context_pack" for blocker in phase.blockers]
        final_state = ScaffoldLifecycleState.SCAFFOLD_BLOCKED_WITH_CONTEXT if previous_blockers else ScaffoldLifecycleState.SCAFFOLD_READY
        resources = [dict(item) for item in self._require_job(job.id).resources]
        result = _scaffold_result(job, draft, final_state, resources, previous_blockers)
        if preflight_blocked:
            result["manifestPath"] = None
            result["workspaceUntouched"] = True
        result_path = context_root / "scaffold-result.json"
        context_path = context_root / "scaffold-context.md"
        _write_generated(result_path, _json(result))
        _write_generated(context_path, _context_markdown(result))
        if not preflight_blocked:
            manifest_payload = dict(draft.manifest)
            manifest_payload["lifecycle"] = {
                "state": final_state.value,
                "next_action": (
                    "start_product"
                    if final_state is ScaffoldLifecycleState.SCAFFOLD_READY
                    else "retry_scaffold"
                ),
            }
            _write_generated(
                _safe_workspace_file(workspace, ".codex/project.yaml"),
                yaml.safe_dump(manifest_payload, sort_keys=False, allow_unicode=True),
            )
            _write_generated(
                _safe_workspace_file(workspace, "release/scaffold-status.json"),
                _json(
                    {
                        "creationMode": "scaffold",
                        "status": final_state.value,
                        "productReady": False,
                        "productionReady": False,
                        "installable": False,
                        "d1": False,
                    }
                ),
            )
        git_evidence: list[Mapping[str, Any]] = []
        context_blockers: list[Mapping[str, Any]] = []
        if not preflight_blocked and self._execute_commands and (workspace / ".git").is_dir():
            tracked_paths = (
                ".codex/project.yaml",
                ".codex/factory/scaffold-result.json",
                ".codex/factory/scaffold-context.md",
                "release/scaffold-status.json",
                *_post_commit_generated_paths(job, workspace),
            )
            git_commands = (
                ("git", "add", *tracked_paths),
                (
                    "git",
                    "-c",
                    "user.name=Codex Project Factory",
                    "-c",
                    "user.email=codex@nienfos.com",
                    "commit",
                    "-m",
                    "Record scaffold result",
                ),
                ("git", "status", "--porcelain"),
            )
            git_results = [
                self._runner.run(command, cwd=workspace) for command in git_commands
            ]
            git_evidence.extend(item.to_payload() for item in git_results)
            failed = next(
                (
                    item
                    for item in git_results
                    if item.exit_code != 0
                    and "nothing to commit" not in item.stdout + item.stderr
                ),
                None,
            )
            dirty = bool(git_results[-1].stdout.strip())
            if failed or dirty:
                context_blockers.append(
                    _blocker(
                        "scaffold_context_git_persist_failed",
                        _redact(failed.stderr if failed else git_results[-1].stdout),
                        "Commit the generated scaffold result files and retry.",
                    )
                )
            github = next(
                (item for item in resources if item.get("kind") == "github_repository"),
                None,
            )
            if not context_blockers and github is not None:
                push = self._runner.run(
                    ("git", "push", "origin", "main"),
                    cwd=workspace,
                )
                git_evidence.append(push.to_payload())
                if push.exit_code != 0:
                    context_blockers.append(
                        _blocker(
                            "scaffold_context_github_push_failed",
                            _redact(push.stderr),
                            "Push the final scaffold result commit to origin/main and retry.",
                        )
                    )
        if context_blockers:
            all_blockers = [*previous_blockers, *context_blockers]
            final_state = ScaffoldLifecycleState.SCAFFOLD_BLOCKED_WITH_CONTEXT
            result = _scaffold_result(job, draft, final_state, resources, all_blockers)
            _write_generated(result_path, _json(result))
            _write_generated(context_path, _context_markdown(result))
            if not preflight_blocked:
                manifest_payload = dict(draft.manifest)
                manifest_payload["lifecycle"] = {
                    "state": final_state.value,
                    "next_action": "retry_scaffold",
                }
                _write_generated(
                    _safe_workspace_file(workspace, ".codex/project.yaml"),
                    yaml.safe_dump(manifest_payload, sort_keys=False, allow_unicode=True),
                )
                _write_generated(
                    _safe_workspace_file(workspace, "release/scaffold-status.json"),
                    _json(
                        {
                            "creationMode": "scaffold",
                            "status": final_state.value,
                            "productReady": False,
                            "productionReady": False,
                            "installable": False,
                            "d1": False,
                        }
                    ),
                )
                amend_commands = (
                    (
                        "git",
                        "add",
                        ".codex/project.yaml",
                        ".codex/factory/scaffold-result.json",
                        ".codex/factory/scaffold-context.md",
                        "release/scaffold-status.json",
                    ),
                    (
                        "git",
                        "-c",
                        "user.name=Codex Project Factory",
                        "-c",
                        "user.email=codex@nienfos.com",
                        "commit",
                        "--amend",
                        "--no-edit",
                    ),
                    ("git", "status", "--porcelain"),
                )
                for command in amend_commands:
                    amended = self._runner.run(command, cwd=workspace)
                    git_evidence.append(amended.to_payload())
        updated = replace(self._require_job(job.id), result=result, lifecycle_state=final_state)
        self._store_job(updated)
        return (
            (
                {
                    "resultPath": str(result_path),
                    "contextPath": str(context_path),
                    "resultHash": _file_hash(result_path),
                    "status": final_state.value,
                },
                *git_evidence,
            ),
            tuple(context_blockers),
        )

    def _run_provider_commands(self, provider_id: str, kind: TargetKind, result: ProviderResult, *, workspace: Path):
        if not self._execute_commands:
            return ([{"status": "prepared", "commands": [list(item) for item in result.commands]}], [])
        descriptor = self._registry.get(kind, provider_id).descriptor
        source_root = descriptor.source_root
        cwd = workspace / source_root if source_root else workspace
        evidence: list[Mapping[str, Any]] = []
        blockers: list[Mapping[str, Any]] = []
        for command in result.commands:
            unsafe_reason = _unsafe_provider_command(command)
            if unsafe_reason:
                blockers.append(
                    _blocker(
                        "unsafe_provider_command",
                        unsafe_reason,
                        "Fix the provider command declaration before retrying.",
                    )
                )
                continue
            response = self._runner.run(
                command,
                cwd=cwd,
                env=descriptor.command_environment,
            )
            evidence.append(response.to_payload())
            if response.exit_code != 0:
                blockers.append(_blocker("provider_validation_failed", f"{provider_id} command failed: {' '.join(command)}", _redact(response.stderr) or f"Fix {provider_id} toolchain and retry."))
                break
        return evidence, blockers

    def _resolve_request(self, request: ScaffoldDraftInput) -> ScaffoldDraftInput:
        preset = next((item for item in STACK_PRESETS if item["id"] == request.stack_preset), None)
        if request.stack_preset and preset is None:
            raise ScaffoldError(f"Unknown stack preset: {request.stack_preset}")
        fallback = next(item for item in STACK_PRESETS if item.get("recommended"))
        selected = preset or fallback
        resolved = replace(
            request,
            name=request.name.strip(),
            slug=request.slug.strip() if request.slug else _slug(request.name),
            mobile_provider=request.mobile_provider or str(selected["mobile"]),
            web_provider=request.web_provider or str(selected["web"]),
            api_provider=request.api_provider or str(selected["api"]),
            github_owner=(request.github_owner or self._github_owner),
            initial_admin_email=(request.initial_admin_email.strip().lower() if request.initial_admin_email else None),
        )
        for kind, provider_id in (
            (TargetKind.MOBILE, resolved.mobile_provider),
            (TargetKind.WEB, resolved.web_provider),
            (TargetKind.API, resolved.api_provider),
        ):
            descriptor = self._registry.get(kind, str(provider_id)).descriptor
            if not descriptor.selectable_for_scaffold:
                raise ScaffoldError(
                    f"Provider {provider_id} is compatibility-only and cannot be selected for manifest v2 Scaffold."
                )
        return resolved

    def _contract_preview(self, request: ScaffoldDraftInput, manifest: Mapping[str, Any]) -> dict[str, Any]:
        remote: list[dict[str, Any]] = []
        if request.github_mode != "disabled":
            remote.append({"provider": "github", "effect": "create_or_verify_and_push", "owner": request.github_owner or "conditional"})
        if request.cloudflare_mode is CloudflareMode.PROVISION_SCAFFOLD:
            remote.append({"provider": "cloudflare", "effect": "provision_neutral_scaffold", "d1": False})
        return {
            "creationMode": "scaffold",
            "project": dict(_project(manifest)),
            "stack": {key: dict(value) for key, value in _targets(manifest).items()},
            "cloudflare": {
                "mode": request.cloudflare_mode.value,
                "d1": False,
                "previewProtected": request.preview_protected,
            },
            "aws": {"mode": request.aws_mode.value, "terraformApply": False},
            "remoteEffects": remote,
            "publishAndroid": False,
            "startDomainFactory": False,
            "startUxLane": False,
            "skippedProductWork": list(SCAFFOLD_SKIPPED_PRODUCT_WORK),
            "conditionalQuestions": {
                "githubRequired": request.github_mode != "disabled" and not bool(request.github_owner),
                "adminEmailRequired": request.preview_protected,
            },
        }

    def _provider_context(self, job: ScaffoldJob, draft: ScaffoldDraft) -> ProviderContext:
        project = _project(draft.manifest)
        return ProviderContext(
            workspace=Path(job.workspace_path),
            project_name=str(project["name"]),
            slug=str(project["slug"]),
            creation_mode="scaffold",
            cloudflare_mode=draft.request.cloudflare_mode.value,
        )

    def _safe_workspace(self, slug: str) -> Path:
        path = (self._projects_root / slug).resolve()
        try:
            path.relative_to(self._projects_root)
        except ValueError as exc:
            raise ScaffoldError("Scaffold workspace escapes PROJECTS_ROOT.") from exc
        return path

    def _start_phase(self, job: ScaffoldJob, name: str) -> ScaffoldJob:
        phase = replace(job.phase(name), status="running", started_at=_now(), blockers=())
        updated = job.with_phase(phase)
        self._store_job(updated)
        return updated

    def _finish_phase(self, job: ScaffoldJob, name: str, *, evidence, blockers) -> ScaffoldJob:
        phase = replace(
            job.phase(name),
            status="blocked" if blockers else "completed",
            message=(str(blockers[0].get("message")) if blockers else "completed"),
            evidence=tuple(evidence),
            blockers=tuple(blockers),
            completed_at=_now(),
        )
        updated = job.with_phase(phase)
        self._store_job(updated)
        return updated

    def _derive_completion(self, job: ScaffoldJob) -> ScaffoldJob:
        if job.result is not None:
            state = ScaffoldLifecycleState(str(job.result["status"]))
        elif any(item.status == "blocked" for item in job.phases):
            state = ScaffoldLifecycleState.SCAFFOLD_BLOCKED_WITH_CONTEXT
        else:
            state = ScaffoldLifecycleState.SCAFFOLD_INITIALIZING
        updated = replace(job, lifecycle_state=state, updated_at=_now())
        self._store_job(updated)
        return updated

    def _cancel_remaining(self, job: ScaffoldJob) -> ScaffoldJob:
        phases = tuple(replace(item, status="cancelled") if item.status == "queued" else item for item in job.phases)
        updated = replace(job, phases=phases, updated_at=_now())
        self._store_job(updated)
        return updated

    def _append_resource(self, job_id: str, resource: Mapping[str, Any]) -> None:
        job = self._require_job(job_id)
        resources = tuple(item for item in job.resources if not (item.get("kind") == resource.get("kind") and item.get("id") == resource.get("id"))) + (dict(resource),)
        self._store_job(replace(job, resources=resources))

    def _store_job(self, job: ScaffoldJob) -> None:
        with self._lock:
            self._jobs[job.id] = job
            self._persist_job(job)

    def _require_draft(self, draft_id: str) -> ScaffoldDraft:
        draft = self._drafts.get(draft_id)
        if draft is None:
            raise ScaffoldError("Scaffold draft not found.")
        return draft

    def _require_job(self, job_id: str) -> ScaffoldJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise ScaffoldError("Scaffold job not found.")
        return job

    def _persist_draft(self, draft: ScaffoldDraft) -> None:
        _atomic_json(self._draft_dir / f"{draft.id}.json", draft.to_payload())

    def _persist_job(self, job: ScaffoldJob) -> None:
        _atomic_json(self._job_dir / f"{job.id}.json", job.to_payload())

    def _load(self) -> None:
        for path in self._draft_dir.glob("*.json"):
            try:
                draft = _draft_from_payload(json.loads(path.read_text(encoding="utf-8")))
                self._drafts[draft.id] = draft
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                continue
        for path in self._job_dir.glob("*.json"):
            try:
                job = _job_from_payload(json.loads(path.read_text(encoding="utf-8")))
                self._jobs[job.id] = job
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                continue


def _baseline_files(
    draft: ScaffoldDraft,
    registry: ProviderRegistry,
    workspace: Path,
) -> dict[str, str]:
    manifest = dict(draft.manifest)
    project = _project(manifest)
    slug = str(project["slug"])
    openapi = _openapi_contract(slug)
    runtime_schema = _runtime_schema()
    return {
        ".codex/project.yaml": yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True),
        "AGENTS.md": _generated_agents(),
        "README.md": _generated_readme(project, manifest),
        "codex-bridge.yaml": yaml.safe_dump({"source_app": slug, "display_name": project["name"], "workspace": ".", "workbench_owner": "codex_mobile_bridge"}, sort_keys=False),
        "contracts/openapi.yaml": yaml.safe_dump(openapi, sort_keys=False),
        "contracts/runtime.schema.json": _json(runtime_schema),
        "contracts/generated/api.ts": _typescript_client(),
        "release/scaffold-status.json": _json({"creationMode": "scaffold", "status": "scaffold_initializing", "productReady": False, "productionReady": False, "installable": False, "d1": False}),
        "release/runtime-profiles.md": "# Runtime profiles\n\nScaffold is a lifecycle state, not a runtime profile. Product releases may use preview, staging, real, or explicitly requested mock.\n",
        "release/release-contracts.yaml": yaml.safe_dump({"android": {"provider": "gradle_apk", "publish_during_scaffold": False}, "real_data_policy": {"localhost": False, "placeholder": False, "mock_or_demo": False, "seed_users": False}}, sort_keys=False),
        "scripts/validate_scaffold.sh": _validate_script(),
        "scripts/doctor_scaffold.sh": "#!/usr/bin/env sh\nset -eu\ncommand -v git\npython3 -m json.tool contracts/runtime.schema.json >/dev/null\necho scaffold_doctor_ok\n",
        "scripts/build_targets.sh": _build_targets_script(
            manifest,
            registry,
            workspace,
        ),
        ".github/workflows/scaffold-validation.yml": _workflow(
            manifest,
            registry,
            workspace,
        ),
        ".gitignore": _gitignore(),
        ".sdd/spec-index.yaml": yaml.safe_dump({"kind": "codex.sdd.index", "standard_id": "workbench-sdd/v1", "specs": {"000-project-scaffold": {"path": "specs/000-project-scaffold/spec.md", "title": "Project Scaffold", "status": "active"}}}, sort_keys=False),
        ".sdd/diagram-index.yaml": yaml.safe_dump({"kind": "codex.sdd.index", "standard_id": "workbench-sdd/v1", "diagrams": {"scaffold-components": {"path": "specs/000-project-scaffold/diagrams/components.mmd", "diagram_type": "component-impact", "scope": "infrastructure"}}}, sort_keys=False),
        "specs/000-project-scaffold/spec.md": _scaffold_spec(manifest),
        "specs/000-project-scaffold/plan.md": "# Plan\n\n1. Validate the selected technical targets.\n2. Record infrastructure readiness.\n3. Stop before product definition.\n",
        "specs/000-project-scaffold/tasks.md": "# Tasks\n\n- [x] Persist the approved technical scaffold contract.\n- [ ] Product definition is intentionally pending until Start Product.\n",
        "specs/000-project-scaffold/traceability.yaml": yaml.safe_dump({"creation_mode": "scaffold", "product_definition": "pending", "requirements": {"technical_bootstrap": {"manifest": ".codex/project.yaml", "validation": "scripts/validate_scaffold.sh"}}}, sort_keys=False),
        "specs/000-project-scaffold/metadata.yaml": yaml.safe_dump({"id": "000-project-scaffold", "title": "Project Scaffold", "status": "active", "scope": "infrastructure_only", "product_content": False}, sort_keys=False),
        "specs/000-project-scaffold/diagrams/components.mmd": "flowchart LR\n  Manifest[Manifest v2] --> Providers[Target providers]\n  Providers --> Validation[Local validation]\n  Validation --> Result[Scaffold context]\n  Result -->|explicit Start Product| Domain[Domain Factory]\n",
        "docs/project-management/index.md": "# Project documentation\n\nCreation mode: Scaffold. Product/client charter content is pending explicit Start Product.\n",
        "docs/project-management/acta/current/metadata.yaml": yaml.safe_dump({"mode": "technical_identity_only", "project": project["name"], "product_definition": "pending", "client_export_enabled": False}, sort_keys=False),
        "docs/project-management/acta/current/acta.md": f"# {project['name']} — Technical Scaffold\n\nThis document records technical identity and readiness only. Product objective, benefits, scope, brand, and client claims are intentionally undefined.\n",
    }


def _cloudflare_files(
    draft: ScaffoldDraft,
    registry: ProviderRegistry,
) -> dict[str, str]:
    slug = str(_project(draft.manifest)["slug"])
    web = _targets(draft.manifest)["web"]
    provider = str(web.get("provider") or "none")
    output = registry.get(TargetKind.WEB, provider).descriptor.outputs.get(
        "cloudflare",
        "infra/cloudflare/static",
    )
    # Wrangler resolves asset directories from the directory containing its
    # config, while provider outputs are intentionally workspace-relative.
    wrangler_output = posixpath.relpath(output, "infra/cloudflare")
    files = {
        "infra/cloudflare/scaffold-plan.json": _json({"mode": draft.request.cloudflare_mode.value, "sourceApp": slug, "webProvider": provider, "webOutput": output, "d1": False, "apiReady": False, "productReady": False, "productionReady": False, "remoteWrites": draft.request.cloudflare_mode is CloudflareMode.PROVISION_SCAFFOLD}),
        "infra/cloudflare/wrangler.toml": f'name = "{slug}-scaffold"\ncompatibility_date = "2026-08-01"\nassets = {{ directory = "{wrangler_output}" }}\n[vars]\nSOURCE_APP = "{slug}"\nSCAFFOLD_STATUS = "ready"\nAPI_READY = "false"\nPRODUCT_READY = "false"\nD1_ENABLED = "false"\n',
        "infra/cloudflare/README.md": "# Cloudflare scaffold\n\nThis is an operational neutral preview. D1, API readiness, product readiness, production readiness, and installability are false. Generate-only performs zero remote calls.\n",
    }
    if not bool(web.get("enabled")):
        files["infra/cloudflare/static/index.html"] = f"<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"robots\" content=\"noindex\"><title>Scaffold ready</title><main><h1>Scaffold ready</h1><p>Technical status for {slug}.</p><dl><dt>API ready</dt><dd>false</dd><dt>Product ready</dt><dd>false</dd><dt>D1</dt><dd>false</dd></dl></main></html>\n"
    return files


def _aws_files(draft: ScaffoldDraft) -> dict[str, str]:
    project = _project(draft.manifest)
    base = {
        "infra/aws/README.md": "# AWS readiness\n\nNo AWS resources are selected or created by Scaffold. Service, account, region, cost, security, and state decisions remain product/deployment gates. Never run terraform apply from Scaffold.\n",
        "infra/aws/architecture-decisions.md": "# Pending decisions\n\n- Compute: undecided\n- Database: undecided\n- Network: undecided\n- DNS/certificates: undecided\n- State backend: requires a separate reviewed bootstrap\n",
    }
    if draft.request.aws_mode is not AwsReadinessMode.TERRAFORM_READY:
        return base
    base.update(
        {
            "infra/aws/versions.tf": '''terraform {
  required_version = ">= 1.12.2, < 2.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.8.0"
    }
  }
}
''',
            "infra/aws/providers.tf": '''provider "aws" {
  region = var.aws_region
  default_tags {
    tags = local.tags
  }
}
''',
            "infra/aws/variables.tf": '''variable "aws_region" {
  type = string
}
variable "environment" {
  type = string
}
variable "owner" {
  type = string
}
''',
            "infra/aws/locals.tf": f'''locals {{
  tags = {{
    Project     = "{project["slug"]}"
    Owner       = var.owner
    Environment = var.environment
    ManagedBy   = "terraform"
  }}
}}
''',
            "infra/aws/outputs.tf": '''output "readiness" {
  value = {
    resources_declared = 0
    apply_authorized   = false
  }
}
''',
            "infra/aws/main.tf": "# Resource-neutral foundation. Add reviewed modules only after Start Product.\n",
            "infra/aws/environments/example.tfvars": 'aws_region  = "us-east-1"\nenvironment = "preview"\nowner       = "replace-during-reviewed-plan"\n',
            "infra/aws/backend-bootstrap.md": "# State bootstrap\n\nChoose and create remote state infrastructure only through a separate approved operation. Scaffold does not create buckets or lock tables.\n",
            "infra/aws/.gitignore": ".terraform/\n*.tfstate\n*.tfstate.*\n.terraform.lock.hcl\n*.tfvars.local\n",
        }
    )
    return base


def _openapi_contract(slug: str) -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Scaffold API", "version": "0.1.0"},
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "responses": {
                        "200": {
                            "description": "Technical health",
                            "headers": {"X-Correlation-Id": {"schema": {"type": "string"}}},
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Health"}}},
                        }
                    },
                }
            },
            "/version": {
                "get": {
                    "operationId": "getVersion",
                    "responses": {
                        "200": {
                            "description": "Build version metadata",
                            "headers": {"X-Correlation-Id": {"schema": {"type": "string"}}},
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Version"}}},
                        }
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "Health": {"type": "object", "required": ["status", "source_app", "version"], "properties": {"status": {"const": "ok"}, "source_app": {"type": "string", "default": slug}, "version": {"type": "string"}}},
                "Version": {"type": "object", "required": ["source_app", "version"], "properties": {"source_app": {"type": "string", "default": slug}, "version": {"type": "string"}}},
                "Error": {"type": "object", "required": ["error"], "properties": {"error": {"type": "object", "required": ["code", "message", "correlation_id"], "properties": {"code": {"type": "string"}, "message": {"type": "string"}, "correlation_id": {"type": "string"}}}}},
            }
        },
    }


def _runtime_schema() -> dict[str, Any]:
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "Logical runtime configuration", "type": "object", "properties": {"api_base_url": {"type": ["string", "null"]}, "runtime_profile": {"enum": ["preview", "staging", "real", "mock"]}, "source_app": {"type": "string"}, "version": {"type": "string"}}, "required": ["source_app", "runtime_profile"], "additionalProperties": False}


def _typescript_client() -> str:
    return r"""// Generated from contracts/openapi.yaml. Do not add UI here.
export type Health = { status: 'ok'; source_app: string; version: string };
export type Version = { source_app: string; version: string };
export type ApiError = { error: { code: string; message: string; correlation_id: string } };
export const getHealth = async (baseUrl: string): Promise<Health> => {
  const response = await fetch(`${baseUrl.replace(/\/$/, '')}/health`);
  if (!response.ok) throw await response.json() as ApiError;
  return await response.json() as Health;
};
export const getVersion = async (baseUrl: string): Promise<Version> => {
  const response = await fetch(`${baseUrl.replace(/\/$/, '')}/version`);
  if (!response.ok) throw await response.json() as ApiError;
  return await response.json() as Version;
};
"""


def _generated_agents() -> str:
    return """# Generated Project Agent Rules

This workspace is in `creation.mode=scaffold` until an explicit Start Product action.

- Keep bootstraps technical, buildable, and visually neutral.
- Do not infer or add product domain, entities, roles, workflows, screens, navigation, colors, logo, UX, auth, RBAC, admin, notifications, persistence, seeds, mock/demo data, or analytics.
- Workbench is Bridge-owned and must not appear in product navigation.
- Do not publish or register Android artifacts during Scaffold.
- D1 is disabled until a post-scaffold persistence decision.
- Terraform may be formatted and validated; never run `terraform apply`.
- Production releases require real non-local, non-placeholder data paths.
"""


def _generated_readme(project: Mapping[str, Any], manifest: Mapping[str, Any]) -> str:
    targets = _targets(manifest)
    return f"# {project['name']}\n\nComposable technical scaffold. Product definition is intentionally pending.\n\n## Targets\n\n- Mobile: `{targets['mobile']['provider']}`\n- Web: `{targets['web']['provider']}`\n- API: `{targets['api']['provider']}`\n\nRun `scripts/doctor_scaffold.sh` and `scripts/validate_scaffold.sh`. Start Product explicitly before adding domain or UX.\n"


def _scaffold_spec(manifest: Mapping[str, Any]) -> str:
    targets = _targets(manifest)
    return f"# Project Scaffold\n\n## Scope\n\nInfrastructure-only technical foundation.\n\n## Providers\n\n- mobile: `{targets['mobile']['provider']}`\n- web: `{targets['web']['provider']}`\n- api: `{targets['api']['provider']}`\n\n## Explicitly pending\n\nProduct objective, domain, roles, workflows, persistence, screens, navigation, brand, UX, releases, and production architecture.\n"


def _validate_script() -> str:
    return """#!/usr/bin/env sh
set -eu
test -f .codex/project.yaml
test -f contracts/openapi.yaml
test -f contracts/runtime.schema.json
test -f specs/000-project-scaffold/spec.md
python3 -m json.tool contracts/runtime.schema.json >/dev/null
if grep -R -i -E 'localhost|example\\.com|seed[_ -]?user|mock[_ -]?data|terraform[[:space:]]+apply' apps services --exclude='*.lock' --exclude='package-lock.json'; then
  echo forbidden scaffold or release content >&2; exit 1
fi
echo scaffold_contract_valid
"""


def _provider_validation_entries(
    manifest: Mapping[str, Any],
    registry: ProviderRegistry,
    workspace: Path,
):
    project = _project(manifest)
    context = ProviderContext(
        workspace=workspace,
        project_name=str(project["name"]),
        slug=str(project["slug"]),
        creation_mode="scaffold",
        cloudflare_mode=str(
            manifest.get("infrastructure", {})
            .get("web_edge", {})
            .get("mode", "disabled")
        ),
    )
    for kind, provider_id in _code_providers(manifest).items():
        provider = registry.get(kind, provider_id)
        validation = provider.validate(context, provider.plan(context))
        yield provider.descriptor, validation.commands


def _build_targets_script(
    manifest: Mapping[str, Any],
    registry: ProviderRegistry,
    workspace: Path,
) -> str:
    commands = [
        "#!/usr/bin/env sh",
        "set -eu",
        "if [ -z \"${ANDROID_HOME:-}\" ] && [ -d \"${HOME}/.local/share/android-sdk/platform-tools\" ]; then",
        "  export ANDROID_HOME=\"${HOME}/.local/share/android-sdk\"",
        "  export ANDROID_SDK_ROOT=\"${ANDROID_HOME}\"",
        "fi",
    ]
    for descriptor, provider_commands in _provider_validation_entries(
        manifest,
        registry,
        workspace,
    ):
        environment = " ".join(
            f"{key}={shlex.quote(value)}"
            for key, value in descriptor.command_environment.items()
        )
        rendered = " && ".join(
            f"{environment} {shlex.join(command)}".strip()
            for command in provider_commands
        )
        if rendered and descriptor.source_root:
            commands.append(
                f"(cd {shlex.quote(descriptor.source_root)} && {rendered})"
            )
    return "\n".join(commands) + "\n"


def _workflow(
    manifest: Mapping[str, Any],
    registry: ProviderRegistry,
    workspace: Path,
) -> str:
    steps: list[dict[str, Any]] = [
        {"uses": "actions/checkout@v4"},
        {"run": "scripts/validate_scaffold.sh"},
    ]
    seen_setup: set[str] = set()
    entries = list(_provider_validation_entries(manifest, registry, workspace))
    for descriptor, _ in entries:
        for setup in descriptor.ci_steps:
            payload = dict(setup)
            key = json.dumps(payload, sort_keys=True)
            if key not in seen_setup:
                seen_setup.add(key)
                steps.append(payload)
    for descriptor, provider_commands in entries:
        for command in provider_commands:
            step: dict[str, Any] = {"run": shlex.join(command)}
            if descriptor.source_root:
                step["working-directory"] = descriptor.source_root
            if descriptor.command_environment:
                step["env"] = dict(descriptor.command_environment)
            steps.append(step)
    steps.append({"run": "git diff --exit-code"})
    jobs = {"targets": {"runs-on": "ubuntu-latest", "steps": steps}}
    return yaml.safe_dump(
        {
            "name": "Scaffold validation",
            "on": {"push": None, "pull_request": None},
            "permissions": {"contents": "read"},
            "jobs": jobs,
        },
        sort_keys=False,
    )


def _gitignore() -> str:
    return """.env
.env.*
!.env.example
node_modules/
.svelte-kit/
.expo/
.dart_tool/
build/
dist/
coverage/
.gradle/
.idea/
*.iml
.cxx/
local.properties
.venv/
__pycache__/
.terraform/
*.tfstate
*.tfstate.*
android/app/*.jks
android/app/*.keystore
**/android/app/*.jks
**/android/app/*.keystore
**/android/key.properties
"""


def _workspace_files(workspace: Path) -> set[str]:
    if not workspace.exists():
        return set()
    files: set[str] = set()
    for current_root, directory_names, file_names in os.walk(workspace):
        current = Path(current_root)
        directory_names[:] = [
            name
            for name in directory_names
            if not _ignored_generated_path(
                (current / name).relative_to(workspace)
            )
            and name != ".git"
        ]
        files.update(
            str((current / name).relative_to(workspace)) for name in file_names
        )
    return files


def _artifact_blockers(
    workspace: Path,
    required_paths: tuple[str, ...],
    *,
    provider_id: str,
    stage: str,
) -> list[Mapping[str, Any]]:
    missing = [
        relative
        for relative in required_paths
        if not (workspace / relative).exists()
    ]
    if not missing:
        return []
    return [
        _blocker(
            f"provider_{stage}_artifact_missing",
            f"{provider_id} did not produce required {stage} artifacts: {', '.join(missing)}.",
            f"Inspect the {provider_id} {stage} command evidence and retry.",
        )
    ]


def _owned_generated_files(workspace: Path, before: set[str]) -> set[str]:
    return {
        relative
        for relative in _workspace_files(workspace) - before
        if not _ignored_generated_path(Path(relative))
        and not relative.endswith(".iml")
        and Path(relative).name != "local.properties"
    }


def _provider_owned_conflicts(
    job: ScaffoldJob,
    *,
    provider_id: str,
    target_kind: TargetKind,
    workspace: Path,
) -> list[str]:
    previous = next(
        (
            item
            for item in job.provider_results
            if item.get("provider_id") == provider_id
            and item.get("target_kind") == target_kind.value
            and isinstance(item.get("generated_file_hashes"), Mapping)
            and item.get("generated_file_hashes")
        ),
        None,
    )
    if previous is None:
        return []
    hashes = previous["generated_file_hashes"]
    assert isinstance(hashes, Mapping)
    changed: list[str] = []
    root = workspace.resolve()
    for raw_relative, raw_digest in hashes.items():
        relative = str(raw_relative)
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            changed.append(relative)
            continue
        if not path.is_file() or _file_hash(path) != str(raw_digest):
            changed.append(relative)
    return sorted(changed)


def _ignored_generated_path(path: Path) -> bool:
    return not {
        ".cxx",
        ".dart_tool",
        ".expo",
        ".gradle",
        ".idea",
        ".svelte-kit",
        ".terraform",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
    }.isdisjoint(path.parts)


def _scan_forbidden_product_content(workspace: Path) -> list[str]:
    findings: list[str] = []
    roots = [workspace / "apps", workspace / "services/api"]
    allowed_technical = {"authentication": False}
    del allowed_technical
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            relative = path.relative_to(workspace)
            if (
                not path.is_file()
                or _ignored_generated_path(relative)
                or path.stat().st_size > 512_000
                or path.suffix.lower() in {".lock", ".png", ".jpg", ".jar"}
            ):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            for term in SCAFFOLD_FORBIDDEN_CONTENT:
                if term in {"auth", "notification"} and path.name in {"package-lock.json", "pubspec.lock"}:
                    continue
                if _forbidden_term_present(term, text):
                    findings.append(f"{path.relative_to(workspace)}:{term}")
    return sorted(set(findings))


def _forbidden_term_present(term: str, text: str) -> bool:
    if term == "auth":
        return bool(re.search(r"\bauth(?:entication|orization)?\b", text))
    if term == "notification":
        return bool(re.search(r"\bnotifications?\b", text))
    escaped = re.escape(term).replace(r"\ ", r"[\s_-]+")
    return bool(re.search(rf"(?<![a-z0-9_]){escaped}(?![a-z0-9_])", text))


def _scan_generated_secrets(workspace: Path) -> list[str]:
    findings: list[str] = []
    assignment = re.compile(
        r"(?i)(api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*[\"'][^\"'\s$<{]{8,}[\"']"
    )
    for path in workspace.rglob("*"):
        relative = path.relative_to(workspace)
        if (
            not path.is_file()
            or _ignored_generated_path(relative)
            or path.stat().st_size > 512_000
            or path.name in {"package-lock.json", ".terraform.lock.hcl"}
            or ".git" in path.parts
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "-----BEGIN PRIVATE KEY-----" in text or assignment.search(text):
            findings.append(str(relative))
    return sorted(findings)


def _scaffold_result(job: ScaffoldJob, draft: ScaffoldDraft, status: ScaffoldLifecycleState, resources: list[dict[str, Any]], blockers: list[dict[str, Any]]) -> dict[str, Any]:
    project = _project(draft.manifest)
    github = next((item for item in resources if item.get("kind") == "github_repository"), None)
    cloudflare = next((item for item in resources if item.get("kind") == "cloudflare_scaffold"), None)
    workbench_phase = job.phase("workbench_registration")
    workbench_status = (
        "verified" if workbench_phase.status == "completed" else "blocked"
    )
    return {"kind": "codex.projectScaffoldResult", "version": 2, "status": status.value, "creationMode": "scaffold", "scaffoldJobId": job.id, "project": dict(project), "workspacePath": job.workspace_path, "manifestPath": f"{job.workspace_path}/.codex/project.yaml", "github": github or {"status": "not_verified"}, "cloudflare": cloudflare or {"status": draft.request.cloudflare_mode.value, "d1": False, "apiReady": False, "productReady": False, "productionReady": False, "installable": False}, "workbench": {"status": workbench_status, "workspacePath": job.workspace_path, "ownedBy": "codex_mobile_bridge", "productNavigationEntry": False}, "validation": {"providerResults": [dict(item) for item in job.provider_results]}, "apiDeployment": {"provider": _targets(draft.manifest)["api"]["provider"], "status": _api_deployment_status(job, draft)}, "awsReadiness": {"mode": draft.request.aws_mode.value, "terraformApply": False}, "pendingProduct": list(SCAFFOLD_SKIPPED_PRODUCT_WORK), "android": {"publishDuringScaffold": False, "installableRegistered": False}, "blockers": blockers, "nextActions": [item["nextAction"] for item in blockers] if blockers else ["Open the workspace or choose Start Product explicitly."], "startProductAvailable": status is ScaffoldLifecycleState.SCAFFOLD_READY}


def _api_deployment_status(job: ScaffoldJob, draft: ScaffoldDraft) -> str:
    api_target = _targets(draft.manifest)["api"]
    if not api_target["enabled"]:
        return "not_requested"
    api_provider = api_target["provider"]
    if any(
        item.get("provider_id") == api_provider
        and item.get("target_kind") == TargetKind.API.value
        and item.get("status") == CapabilityEvidenceState.BLOCKED.value
        for item in job.provider_results
    ):
        return "blocked"
    return "prepared"


def _context_markdown(result: Mapping[str, Any]) -> str:
    blockers = result.get("blockers") or []
    blocker_lines = "\n".join(f"- {item.get('message')}: {item.get('nextAction')}" for item in blockers) or "- None"
    return f"# Scaffold context\n\n- Status: `{result['status']}`\n- Workspace: `{result['workspacePath']}`\n- Creation mode: `scaffold`\n- Product work: intentionally pending\n- Android publication: disabled\n- D1: disabled\n- Terraform apply: forbidden\n\n## Blockers\n\n{blocker_lines}\n\nDomain Factory and UX must start only after the explicit Start Product action and must reuse this workspace and provider context.\n"


def _draft_request_payload(request: ScaffoldDraftInput) -> dict[str, Any]:
    return {"name": request.name, "slug": request.slug, "stackPreset": request.stack_preset, "mobileProvider": request.mobile_provider, "webProvider": request.web_provider, "apiProvider": request.api_provider, "cloudflareMode": request.cloudflare_mode.value, "awsReadinessMode": request.aws_mode.value, "githubOwner": request.github_owner, "githubVisibility": request.github_visibility, "githubMode": request.github_mode, "previewProtected": request.preview_protected, "initialAdminEmail": request.initial_admin_email}


def _draft_from_payload(payload: Mapping[str, Any]) -> ScaffoldDraft:
    request = payload["request"]
    return ScaffoldDraft(id=str(payload["draftId"]), created_at=str(payload["createdAt"]), updated_at=str(payload["updatedAt"]), status=ScaffoldLifecycleState(str(payload["status"])), request=ScaffoldDraftInput(name=str(request["name"]), slug=request.get("slug"), stack_preset=request.get("stackPreset"), mobile_provider=request.get("mobileProvider"), web_provider=request.get("webProvider"), api_provider=request.get("apiProvider"), cloudflare_mode=CloudflareMode(str(request.get("cloudflareMode") or "disabled")), aws_mode=AwsReadinessMode(str(request.get("awsReadinessMode") or "none")), github_owner=request.get("githubOwner"), github_visibility=str(request.get("githubVisibility") or "private"), github_mode=str(request.get("githubMode") or "create_or_verify"), preview_protected=bool(request.get("previewProtected")), initial_admin_email=request.get("initialAdminEmail")), manifest=dict(payload["manifest"]), contract_preview=dict(payload["contractPreview"]), contract_hash=str(payload["contractHash"]), confirmed_at=payload.get("confirmedAt"))


def _job_from_payload(payload: Mapping[str, Any]) -> ScaffoldJob:
    phases = tuple(ScaffoldPhase(name=str(item["name"]), status=str(item.get("status") or "queued"), message=str(item.get("message") or ""), evidence=tuple(dict(value) for value in item.get("evidence", [])), blockers=tuple(dict(value) for value in item.get("blockers", [])), started_at=item.get("startedAt"), completed_at=item.get("completedAt")) for item in payload["phases"])
    return ScaffoldJob(id=str(payload["scaffoldJobId"]), draft_id=str(payload["draftId"]), created_at=str(payload["createdAt"]), updated_at=str(payload["updatedAt"]), workspace_path=str(payload["workspacePath"]), lifecycle_state=ScaffoldLifecycleState(str(payload["status"])), phases=phases, provider_plans=tuple(dict(item) for item in payload.get("providerPlans", [])), provider_results=tuple(dict(item) for item in payload.get("providerResults", [])), resources=tuple(dict(item) for item in payload.get("resources", [])), result=dict(payload["result"]) if isinstance(payload.get("result"), dict) else None, domain_factory_relationship=dict(payload["domainFactoryRelationship"]) if isinstance(payload.get("domainFactoryRelationship"), dict) else None, cancelled=bool(payload.get("cancelled", False)))


def _blocked_dependency(job: ScaffoldJob, phase_name: str) -> str | None:
    guarded = {
        "scaffold_contract": ("scaffold_preflight",),
        "workspace_baseline": ("scaffold_preflight",),
        "target_bootstrap": ("scaffold_preflight",),
        "target_validation": ("scaffold_preflight", "target_bootstrap"),
        "local_git_commit": ("scaffold_preflight", "scaffold_contract", "workspace_baseline", "target_bootstrap", "target_validation"),
        "github_repository": ("scaffold_preflight", "scaffold_contract", "workspace_baseline", "target_bootstrap", "target_validation", "local_git_commit"),
        "cloudflare_scaffold": ("scaffold_preflight", "scaffold_contract", "workspace_baseline", "target_bootstrap", "target_validation", "local_git_commit"),
        "aws_readiness": ("scaffold_preflight",),
        "workbench_registration": ("scaffold_preflight",),
    }
    for dependency in guarded.get(phase_name, ()):
        dependency_phase = job.phase(dependency)
        if dependency_phase.status == "blocked" and _phase_has_fatal_blocker(
            dependency_phase
        ):
            return dependency
    return None


def _phase_has_fatal_blocker(phase: ScaffoldPhase) -> bool:
    deferred_codes = {
        "bootstrap_commands_not_executed",
        "local_validation_not_executed",
        "local_git_commit_not_executed",
        "github_remote_write_not_executed",
        "cloudflare_remote_write_not_executed",
        "terraform_validation_not_executed",
    }
    return any(
        str(blocker.get("code") or "") not in deferred_codes
        for blocker in phase.blockers
    )


def _matches_existing_scaffold(path: Path, draft: ScaffoldDraft) -> bool:
    try:
        manifest = _read_yaml(path)
        creation = manifest.get("creation")
        project = manifest.get("project")
        targets = manifest.get("targets")
        infrastructure = manifest.get("infrastructure")
        expected_project = _project(draft.manifest)
        expected_targets = _targets(draft.manifest)
        expected_infrastructure = draft.manifest.get("infrastructure")
        return (
            manifest.get("schema_version") == 2
            and isinstance(creation, Mapping)
            and creation.get("mode") == CreationMode.SCAFFOLD.value
            and isinstance(project, Mapping)
            and project.get("slug") == expected_project.get("slug")
            and project.get("name") == expected_project.get("name")
            and isinstance(targets, Mapping)
            and all(
                isinstance(targets.get(kind), Mapping)
                and targets[kind].get("provider") == expected_targets[kind].get("provider")
                for kind in ("mobile", "web", "api")
            )
            and isinstance(infrastructure, Mapping)
            and isinstance(expected_infrastructure, Mapping)
            and infrastructure.get("web_edge")
            == expected_infrastructure.get("web_edge")
            and infrastructure.get("aws") == expected_infrastructure.get("aws")
        )
    except (OSError, ValueError, TypeError, yaml.YAMLError):
        return False


def _github_repo_from_remote(value: str) -> str | None:
    remote = value.strip().removesuffix(".git")
    match = re.fullmatch(
        r"(?:https://github\.com/|ssh://git@github\.com/|git@github\.com:)([^/]+/[^/]+)",
        remote,
        flags=re.IGNORECASE,
    )
    return match.group(1).lower() if match else None


def _selected_providers(manifest: Mapping[str, Any]) -> dict[TargetKind, str]:
    selected = _code_providers(manifest)
    infrastructure = manifest.get("infrastructure") if isinstance(manifest.get("infrastructure"), Mapping) else {}
    web_edge = infrastructure.get("web_edge") if isinstance(infrastructure.get("web_edge"), Mapping) else {}
    aws = infrastructure.get("aws") if isinstance(infrastructure.get("aws"), Mapping) else {}
    selected[TargetKind.WEB_EDGE] = str(web_edge.get("provider") or "none")
    selected[TargetKind.AWS_READINESS] = str(aws.get("provider") or "none")
    return selected


def _code_providers(manifest: Mapping[str, Any]) -> dict[TargetKind, str]:
    targets = _targets(manifest)
    result: dict[TargetKind, str] = {}
    for kind in (TargetKind.MOBILE, TargetKind.WEB, TargetKind.API):
        provider = str(targets[kind.value].get("provider") or "none")
        if provider != "none":
            result[kind] = provider
    return result


def _project(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    value = manifest.get("project")
    if not isinstance(value, Mapping):
        raise ScaffoldError("Manifest v2 project identity is missing.")
    return value


def _targets(manifest: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    value = manifest.get("targets")
    if not isinstance(value, Mapping):
        raise ScaffoldError("Manifest v2 targets are missing.")
    return value  # type: ignore[return-value]


def _write_bundle(workspace: Path, files: Mapping[str, str]):
    generated: list[str] = []
    blockers: list[Mapping[str, Any]] = []
    for relative, content in files.items():
        path = (workspace / relative).resolve()
        try:
            path.relative_to(workspace.resolve())
        except ValueError:
            blockers.append(_blocker("unsafe_generated_path", relative, "Fix the provider generated-file declaration."))
            continue
        if path.exists() and path.read_text(encoding="utf-8", errors="ignore") != content:
            blockers.append(_blocker("generated_file_conflict", f"Refusing to overwrite {relative}.", "Reconcile the user-owned file and retry."))
            continue
        _write_generated(path, content)
        generated.append(relative)
    return generated, tuple(blockers)


def _safe_workspace_file(workspace: Path, relative: str) -> Path:
    root = workspace.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ScaffoldError(f"Scaffold path escapes workspace: {relative}")
    return path


def _post_commit_generated_paths(job: ScaffoldJob, workspace: Path) -> tuple[str, ...]:
    """Return only declared phase-owned files created after local_git_commit."""
    allowed_roots = ("infra/cloudflare/", "infra/aws/")
    root = workspace.resolve()
    generated: set[str] = set()
    for phase_name in ("cloudflare_scaffold", "aws_readiness"):
        for evidence in job.phase(phase_name).evidence:
            values = evidence.get("files")
            if not isinstance(values, list):
                continue
            for value in values:
                relative = str(value)
                path = (root / relative).resolve()
                if (
                    relative.startswith(allowed_roots)
                    and path.is_relative_to(root)
                    and path.is_file()
                ):
                    generated.add(relative)
    return tuple(sorted(generated))


def _write_generated(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8", errors="ignore") == content:
        return
    path.write_text(content, encoding="utf-8")
    if path.suffix == ".sh":
        path.chmod(0o755)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(_json(payload), encoding="utf-8")
    temporary.replace(path)


def _read_yaml(path: Path) -> Mapping[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    return value if isinstance(value, Mapping) else {}


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _blocker(code: str, message: str, next_action: str) -> dict[str, Any]:
    return {"code": code, "message": _redact(message), "nextAction": _redact(next_action), "recoverable": True}


def _redact(value: str) -> str:
    return _REDACT.sub(r"\1\2<redacted>", value)


def _unsafe_provider_command(command: tuple[str, ...]) -> str | None:
    if not command:
        return "Provider declared an empty command."
    executable = command[0]
    allowed = {
        "dart",
        "flutter",
        "go",
        "gofmt",
        "npm",
        "python3",
        ".venv/bin/python",
        "terraform",
        "./android/gradlew",
    }
    if executable not in allowed:
        return f"Provider executable is not allowlisted: {executable}"
    lowered = [item.lower() for item in command]
    if executable == "terraform" and "apply" in lowered:
        return "terraform apply is forbidden in Scaffold."
    if any(
        item in {"..", "/", "~"}
        or item.startswith("../")
        or Path(item).is_absolute()
        for item in command[1:]
    ):
        return "Provider command contains an unsafe path."
    return None


def _slug(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def _valid_email(value: str | None) -> bool:
    return bool(value and "@" in value and "." in value.rsplit("@", 1)[-1])


def _cloudflare_preview_url(draft: ScaffoldDraft) -> str:
    return f"https://preview.nienfos.com/{_project(draft.manifest)['slug']}"


def _now() -> str:
    return datetime.now(UTC).isoformat()
