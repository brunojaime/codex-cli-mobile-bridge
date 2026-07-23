from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from backend.app.domain.entities.job import utc_now


class ProjectFactoryInitCompletionState(StrEnum):
    READY = "ready"
    BLOCKED_WITH_CONTEXT = "blocked_with_context"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RESUMABLE = "resumable"


class ProjectFactoryInitPhaseStatus(StrEnum):
    QUEUED = "queued"
    QUEUED_WAITING_FOR_DOMAIN_BRIEF = "queued_waiting_for_domain_brief"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"

    @property
    def is_terminal(self) -> bool:
        return self in {
            self.COMPLETED,
            self.BLOCKED,
            self.FAILED,
            self.CANCELLED,
            self.SKIPPED,
        }


class ProjectFactoryInitPhaseName(StrEnum):
    INIT_PREFLIGHT = "init_preflight"
    DRAFT_AND_SLUG = "draft_and_slug"
    BASELINE_SCAFFOLD = "baseline_scaffold"
    FLUTTER_OR_STRATEGY_BASELINE = "flutter_or_strategy_baseline"
    UX_GENERATOR = "ux_generator"
    UX_REVIEWER = "ux_reviewer"
    LOCAL_VALIDATION = "local_validation"
    LOCAL_GIT_COMMIT = "local_git_commit"
    GITHUB_REPOSITORY = "github_repository"
    CLOUDFLARE_PREVIEW_PROVISION = "cloudflare_preview_provision"
    CLOUDFLARE_PREVIEW_DEPLOY = "cloudflare_preview_deploy"
    PREVIEW_SMOKE = "preview_smoke"
    ANDROID_PREVIEW_RELEASE = "android_preview_release"
    BRIDGE_INSTALLABLE_REGISTRATION = "bridge_installable_registration"
    WORKBENCH_AND_FEEDBACK_VERIFICATION = "workbench_and_feedback_verification"
    LLM_CONTEXT_PACK = "llm_context_pack"


class ProjectFactoryInitIdempotencyRule(StrEnum):
    READ_ONLY_PREFLIGHT = "read_only_preflight"
    CREATE_OR_VERIFY = "create_or_verify"
    GENERATED_OVERWRITE = "generated_overwrite"
    RERUN_SAFE_COMMAND = "rerun_safe_command"
    WRITE_ONCE_VERIFY_HASH = "write_once_verify_hash"
    CONTEXT_REBUILD_FROM_STATE = "context_rebuild_from_state"


class ProjectFactoryInitRemoteResourceType(StrEnum):
    GITHUB_REPOSITORY = "github_repository"
    GITHUB_BRANCH = "github_branch"
    CLOUDFLARE_WORKER = "cloudflare_worker"
    CLOUDFLARE_ROUTE = "cloudflare_route"
    CLOUDFLARE_D1_DATABASE = "cloudflare_d1_database"
    GITHUB_RELEASE = "github_release"
    BRIDGE_INSTALLABLE_APP = "bridge_installable_app"
    PREVIEW_URL = "preview_url"
    API_BASE_URL = "api_base_url"


INIT_PHASE_ORDER: tuple[ProjectFactoryInitPhaseName, ...] = (
    ProjectFactoryInitPhaseName.INIT_PREFLIGHT,
    ProjectFactoryInitPhaseName.DRAFT_AND_SLUG,
    ProjectFactoryInitPhaseName.BASELINE_SCAFFOLD,
    ProjectFactoryInitPhaseName.FLUTTER_OR_STRATEGY_BASELINE,
    ProjectFactoryInitPhaseName.UX_GENERATOR,
    ProjectFactoryInitPhaseName.UX_REVIEWER,
    ProjectFactoryInitPhaseName.LOCAL_VALIDATION,
    ProjectFactoryInitPhaseName.LOCAL_GIT_COMMIT,
    ProjectFactoryInitPhaseName.GITHUB_REPOSITORY,
    ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_PROVISION,
    ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_DEPLOY,
    ProjectFactoryInitPhaseName.PREVIEW_SMOKE,
    ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
    ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION,
    ProjectFactoryInitPhaseName.WORKBENCH_AND_FEEDBACK_VERIFICATION,
    ProjectFactoryInitPhaseName.LLM_CONTEXT_PACK,
)

INIT_PHASE_IDEMPOTENCY_RULES: dict[
    ProjectFactoryInitPhaseName,
    ProjectFactoryInitIdempotencyRule,
] = {
    ProjectFactoryInitPhaseName.INIT_PREFLIGHT: ProjectFactoryInitIdempotencyRule.READ_ONLY_PREFLIGHT,
    ProjectFactoryInitPhaseName.DRAFT_AND_SLUG: ProjectFactoryInitIdempotencyRule.CREATE_OR_VERIFY,
    ProjectFactoryInitPhaseName.BASELINE_SCAFFOLD: ProjectFactoryInitIdempotencyRule.GENERATED_OVERWRITE,
    ProjectFactoryInitPhaseName.FLUTTER_OR_STRATEGY_BASELINE: ProjectFactoryInitIdempotencyRule.CREATE_OR_VERIFY,
    ProjectFactoryInitPhaseName.UX_GENERATOR: ProjectFactoryInitIdempotencyRule.RERUN_SAFE_COMMAND,
    ProjectFactoryInitPhaseName.UX_REVIEWER: ProjectFactoryInitIdempotencyRule.RERUN_SAFE_COMMAND,
    ProjectFactoryInitPhaseName.LOCAL_VALIDATION: ProjectFactoryInitIdempotencyRule.RERUN_SAFE_COMMAND,
    ProjectFactoryInitPhaseName.LOCAL_GIT_COMMIT: ProjectFactoryInitIdempotencyRule.CREATE_OR_VERIFY,
    ProjectFactoryInitPhaseName.GITHUB_REPOSITORY: ProjectFactoryInitIdempotencyRule.CREATE_OR_VERIFY,
    ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_PROVISION: ProjectFactoryInitIdempotencyRule.CREATE_OR_VERIFY,
    ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_DEPLOY: ProjectFactoryInitIdempotencyRule.RERUN_SAFE_COMMAND,
    ProjectFactoryInitPhaseName.PREVIEW_SMOKE: ProjectFactoryInitIdempotencyRule.RERUN_SAFE_COMMAND,
    ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE: ProjectFactoryInitIdempotencyRule.WRITE_ONCE_VERIFY_HASH,
    ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION: ProjectFactoryInitIdempotencyRule.CREATE_OR_VERIFY,
    ProjectFactoryInitPhaseName.WORKBENCH_AND_FEEDBACK_VERIFICATION: ProjectFactoryInitIdempotencyRule.RERUN_SAFE_COMMAND,
    ProjectFactoryInitPhaseName.LLM_CONTEXT_PACK: ProjectFactoryInitIdempotencyRule.CONTEXT_REBUILD_FROM_STATE,
}


@dataclass(frozen=True, slots=True)
class ProjectFactoryInitCommandEvidence:
    argv: tuple[str, ...]
    cwd: str | None = None
    exit_code: int | None = None
    stdout_summary: str = ""
    stderr_summary: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    redacted_env_keys: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "argv": list(self.argv),
            "cwd": self.cwd,
            "exitCode": self.exit_code,
            "stdoutSummary": self.stdout_summary,
            "stderrSummary": self.stderr_summary,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "redactedEnvKeys": list(self.redacted_env_keys),
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
    ) -> "ProjectFactoryInitCommandEvidence":
        return cls(
            argv=tuple(str(item) for item in _expect_list(payload.get("argv"))),
            cwd=_optional_str(payload.get("cwd")),
            exit_code=_optional_int(payload.get("exitCode")),
            stdout_summary=str(payload.get("stdoutSummary") or ""),
            stderr_summary=str(payload.get("stderrSummary") or ""),
            started_at=_optional_str(payload.get("startedAt")),
            completed_at=_optional_str(payload.get("completedAt")),
            redacted_env_keys=tuple(
                str(item) for item in _expect_list(payload.get("redactedEnvKeys"))
            ),
        )


@dataclass(frozen=True, slots=True)
class ProjectFactoryInitBlocker:
    code: str
    message: str
    phase: ProjectFactoryInitPhaseName
    next_action: str
    command: tuple[str, ...] = ()
    recoverable: bool = True

    def to_payload(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "phase": self.phase.value,
            "nextAction": self.next_action,
            "command": list(self.command),
            "recoverable": self.recoverable,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "ProjectFactoryInitBlocker":
        return cls(
            code=str(payload["code"]),
            message=str(payload["message"]),
            phase=ProjectFactoryInitPhaseName(str(payload["phase"])),
            next_action=str(payload.get("nextAction") or ""),
            command=tuple(str(item) for item in _expect_list(payload.get("command"))),
            recoverable=bool(payload.get("recoverable", True)),
        )


@dataclass(frozen=True, slots=True)
class ProjectFactoryInitArtifact:
    kind: str
    path: str | None = None
    url: str | None = None
    sha256: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "path": self.path,
            "url": self.url,
            "sha256": self.sha256,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "ProjectFactoryInitArtifact":
        metadata = payload.get("metadata")
        return cls(
            kind=str(payload["kind"]),
            path=_optional_str(payload.get("path")),
            url=_optional_str(payload.get("url")),
            sha256=_optional_str(payload.get("sha256")),
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
        )


@dataclass(frozen=True, slots=True)
class ProjectFactoryInitRemoteResource:
    type: ProjectFactoryInitRemoteResourceType
    identifier: str
    display_name: str
    url: str | None = None
    provider: str | None = None
    status: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return {
            "type": self.type.value,
            "identifier": self.identifier,
            "displayName": self.display_name,
            "url": self.url,
            "provider": self.provider,
            "status": self.status,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
    ) -> "ProjectFactoryInitRemoteResource":
        metadata = payload.get("metadata")
        return cls(
            type=ProjectFactoryInitRemoteResourceType(str(payload["type"])),
            identifier=str(payload["identifier"]),
            display_name=str(payload.get("displayName") or payload["identifier"]),
            url=_optional_str(payload.get("url")),
            provider=_optional_str(payload.get("provider")),
            status=str(payload.get("status") or "unknown"),
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
        )


@dataclass(frozen=True, slots=True)
class ProjectFactoryInitRelationships:
    draft_id: str
    chat_session_id: str | None = None
    init_job_id: str | None = None
    generated_workspace_path: str | None = None
    workbench_scope_id: str | None = None
    first_chat_message_id: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "draftId": self.draft_id,
            "chatSessionId": self.chat_session_id,
            "initJobId": self.init_job_id,
            "generatedWorkspacePath": self.generated_workspace_path,
            "workbenchScopeId": self.workbench_scope_id,
            "firstChatMessageId": self.first_chat_message_id,
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
    ) -> "ProjectFactoryInitRelationships":
        return cls(
            draft_id=str(payload["draftId"]),
            chat_session_id=_optional_str(payload.get("chatSessionId")),
            init_job_id=_optional_str(payload.get("initJobId")),
            generated_workspace_path=_optional_str(
                payload.get("generatedWorkspacePath")
            ),
            workbench_scope_id=_optional_str(payload.get("workbenchScopeId")),
            first_chat_message_id=_optional_str(payload.get("firstChatMessageId")),
        )


@dataclass(frozen=True, slots=True)
class ProjectFactoryInitContextPack:
    init_result_path: str
    llm_start_context_path: str
    content_sha256: str
    attached_to_chat: bool = False
    attached_message_id: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "initResultPath": self.init_result_path,
            "llmStartContextPath": self.llm_start_context_path,
            "contentSha256": self.content_sha256,
            "attachedToChat": self.attached_to_chat,
            "attachedMessageId": self.attached_message_id,
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
    ) -> "ProjectFactoryInitContextPack":
        return cls(
            init_result_path=str(payload["initResultPath"]),
            llm_start_context_path=str(payload["llmStartContextPath"]),
            content_sha256=str(payload["contentSha256"]),
            attached_to_chat=bool(payload.get("attachedToChat", False)),
            attached_message_id=_optional_str(payload.get("attachedMessageId")),
        )


@dataclass(frozen=True, slots=True)
class ProjectFactoryInitPhase:
    name: ProjectFactoryInitPhaseName
    status: ProjectFactoryInitPhaseStatus = ProjectFactoryInitPhaseStatus.QUEUED
    idempotency: ProjectFactoryInitIdempotencyRule | None = None
    message: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    command_evidence: tuple[ProjectFactoryInitCommandEvidence, ...] = ()
    blockers: tuple[ProjectFactoryInitBlocker, ...] = ()
    artifacts: tuple[ProjectFactoryInitArtifact, ...] = ()

    def __post_init__(self) -> None:
        if self.idempotency is None:
            object.__setattr__(
                self,
                "idempotency",
                INIT_PHASE_IDEMPOTENCY_RULES[self.name],
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name.value,
            "status": self.status.value,
            "idempotency": self.idempotency.value if self.idempotency else None,
            "message": self.message,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "commandEvidence": [
                evidence.to_payload() for evidence in self.command_evidence
            ],
            "blockers": [blocker.to_payload() for blocker in self.blockers],
            "artifacts": [artifact.to_payload() for artifact in self.artifacts],
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "ProjectFactoryInitPhase":
        return cls(
            name=ProjectFactoryInitPhaseName(str(payload["name"])),
            status=ProjectFactoryInitPhaseStatus(
                str(payload.get("status") or ProjectFactoryInitPhaseStatus.QUEUED)
            ),
            idempotency=ProjectFactoryInitIdempotencyRule(str(payload["idempotency"]))
            if payload.get("idempotency")
            else None,
            message=str(payload.get("message") or ""),
            started_at=_optional_str(payload.get("startedAt")),
            completed_at=_optional_str(payload.get("completedAt")),
            command_evidence=tuple(
                ProjectFactoryInitCommandEvidence.from_payload(_expect_mapping(item))
                for item in _expect_list(payload.get("commandEvidence"))
            ),
            blockers=tuple(
                ProjectFactoryInitBlocker.from_payload(_expect_mapping(item))
                for item in _expect_list(payload.get("blockers"))
            ),
            artifacts=tuple(
                ProjectFactoryInitArtifact.from_payload(_expect_mapping(item))
                for item in _expect_list(payload.get("artifacts"))
            ),
        )


def _phases_in_current_order(
    phases: tuple[ProjectFactoryInitPhase, ...],
) -> tuple[ProjectFactoryInitPhase, ...]:
    by_name = {phase.name: phase for phase in phases}
    ordered: list[ProjectFactoryInitPhase] = []
    for index, name in enumerate(INIT_PHASE_ORDER):
        existing = by_name.get(name)
        if existing is not None:
            ordered.append(existing)
            continue
        later_phases = (
            by_name.get(later_name) for later_name in INIT_PHASE_ORDER[index + 1 :]
        )
        later_started = any(
            phase is not None
            and phase.status
            not in {
                ProjectFactoryInitPhaseStatus.QUEUED,
                ProjectFactoryInitPhaseStatus.QUEUED_WAITING_FOR_DOMAIN_BRIEF,
            }
            for phase in later_phases
        )
        if later_started:
            ordered.append(
                ProjectFactoryInitPhase(
                    name=name,
                    status=ProjectFactoryInitPhaseStatus.SKIPPED,
                    message="Phase added after this init job had already advanced.",
                )
            )
        else:
            ordered.append(ProjectFactoryInitPhase(name=name))
    return tuple(ordered)


@dataclass(frozen=True, slots=True)
class ProjectFactoryInitJob:
    id: str
    relationships: ProjectFactoryInitRelationships
    created_at: str
    updated_at: str
    project_name: str
    slug: str
    frontend_strategy: str
    phases: tuple[ProjectFactoryInitPhase, ...] = field(
        default_factory=lambda: tuple(
            ProjectFactoryInitPhase(name=phase) for phase in INIT_PHASE_ORDER
        )
    )
    remote_resources: tuple[ProjectFactoryInitRemoteResource, ...] = ()
    context_pack: ProjectFactoryInitContextPack | None = None
    completion_state: ProjectFactoryInitCompletionState = (
        ProjectFactoryInitCompletionState.RESUMABLE
    )

    @classmethod
    def new(
        cls,
        *,
        id: str,
        draft_id: str,
        project_name: str,
        slug: str,
        frontend_strategy: str,
        chat_session_id: str | None = None,
    ) -> "ProjectFactoryInitJob":
        now = utc_now().isoformat()
        return cls(
            id=id,
            relationships=ProjectFactoryInitRelationships(
                draft_id=draft_id,
                chat_session_id=chat_session_id,
                init_job_id=id,
            ),
            created_at=now,
            updated_at=now,
            project_name=project_name,
            slug=slug,
            frontend_strategy=frontend_strategy,
        ).with_derived_completion_state()

    def phase(self, name: ProjectFactoryInitPhaseName) -> ProjectFactoryInitPhase:
        for phase in self.phases:
            if phase.name == name:
                return phase
        raise KeyError(name.value)

    def with_phase(self, updated_phase: ProjectFactoryInitPhase) -> "ProjectFactoryInitJob":
        phases = _phases_in_current_order(
            tuple(
                updated_phase if phase.name == updated_phase.name else phase
                for phase in self.phases
            )
            if any(phase.name == updated_phase.name for phase in self.phases)
            else (*self.phases, updated_phase)
        )
        return ProjectFactoryInitJob(
            id=self.id,
            relationships=self.relationships,
            created_at=self.created_at,
            updated_at=utc_now().isoformat(),
            project_name=self.project_name,
            slug=self.slug,
            frontend_strategy=self.frontend_strategy,
            phases=phases,
            remote_resources=self.remote_resources,
            context_pack=self.context_pack,
        ).with_derived_completion_state()

    def with_derived_completion_state(self) -> "ProjectFactoryInitJob":
        state = derive_init_completion_state(self.phases)
        if state == self.completion_state:
            return self
        return ProjectFactoryInitJob(
            id=self.id,
            relationships=self.relationships,
            created_at=self.created_at,
            updated_at=self.updated_at,
            project_name=self.project_name,
            slug=self.slug,
            frontend_strategy=self.frontend_strategy,
            phases=self.phases,
            remote_resources=self.remote_resources,
            context_pack=self.context_pack,
            completion_state=state,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": "codex.projectFactoryInitJob",
            "version": 1,
            "jobId": self.id,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "projectName": self.project_name,
            "slug": self.slug,
            "frontendStrategy": self.frontend_strategy,
            "completionState": self.completion_state.value,
            "relationships": self.relationships.to_payload(),
            "phases": [phase.to_payload() for phase in self.phases],
            "remoteResources": [
                resource.to_payload() for resource in self.remote_resources
            ],
            "contextPack": (
                self.context_pack.to_payload()
                if self.context_pack is not None
                else None
            ),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "ProjectFactoryInitJob":
        context_pack_payload = payload.get("contextPack")
        job = cls(
            id=str(payload["jobId"]),
            relationships=ProjectFactoryInitRelationships.from_payload(
                _expect_mapping(payload["relationships"])
            ),
            created_at=str(payload["createdAt"]),
            updated_at=str(payload["updatedAt"]),
            project_name=str(payload["projectName"]),
            slug=str(payload["slug"]),
            frontend_strategy=str(payload["frontendStrategy"]),
            phases=_phases_in_current_order(
                tuple(
                    ProjectFactoryInitPhase.from_payload(_expect_mapping(item))
                    for item in _expect_list(payload.get("phases"))
                )
            ),
            remote_resources=tuple(
                ProjectFactoryInitRemoteResource.from_payload(_expect_mapping(item))
                for item in _expect_list(payload.get("remoteResources"))
            ),
            context_pack=(
                ProjectFactoryInitContextPack.from_payload(
                    _expect_mapping(context_pack_payload)
                )
                if isinstance(context_pack_payload, dict)
                else None
            ),
            completion_state=ProjectFactoryInitCompletionState(
                str(
                    payload.get("completionState")
                    or ProjectFactoryInitCompletionState.RESUMABLE
                )
            ),
        )
        return job.with_derived_completion_state()


def derive_init_completion_state(
    phases: tuple[ProjectFactoryInitPhase, ...],
) -> ProjectFactoryInitCompletionState:
    statuses = {phase.status for phase in phases}
    if ProjectFactoryInitPhaseStatus.CANCELLED in statuses:
        return ProjectFactoryInitCompletionState.CANCELLED
    if ProjectFactoryInitPhaseStatus.FAILED in statuses:
        return ProjectFactoryInitCompletionState.FAILED
    if ProjectFactoryInitPhaseStatus.BLOCKED in statuses:
        return ProjectFactoryInitCompletionState.BLOCKED_WITH_CONTEXT
    if all(
        phase.status
        in {
            ProjectFactoryInitPhaseStatus.COMPLETED,
            ProjectFactoryInitPhaseStatus.SKIPPED,
        }
        for phase in phases
    ):
        return ProjectFactoryInitCompletionState.READY
    return ProjectFactoryInitCompletionState.RESUMABLE


def _expect_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Expected mapping payload.")
    return value


def _expect_list(value: object) -> list[object]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Expected list payload.")
    return value


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)
