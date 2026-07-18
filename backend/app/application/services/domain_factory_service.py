from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from backend.app.application.services.sdd_standard_service import parse_simple_yaml
from backend.app.domain.entities.agent_configuration import (
    AgentConfiguration,
    AgentDisplayMode,
    AgentId,
    AgentPreset,
    AgentVisibilityMode,
    TurnBudgetMode,
)
from backend.app.domain.entities.chat_message import (
    ChatMessage,
    ChatMessageAuthorType,
    ChatMessageRole,
    ChatMessageStatus,
)
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.repositories.chat_repository import ChatRepository


_DOMAIN_FACTORY_GENERATOR_LABEL = "Domain Factory"
_DOMAIN_FACTORY_REVIEWER_LABEL = "Domain Reviewer"
_MAX_CONTEXT_MARKDOWN_CHARS = 5_000
_MAX_PROMPT_CHARS = 11_500
CRITICAL_BASELINE_FILES = (
    "codex-bridge.yaml",
    ".codex/factory/init-result.json",
    ".codex/factory/llm-start-context.md",
    "release/preview-runtime.json",
    ".codex/project.yaml",
)

PROTECTED_FOUNDATION_AREAS = (
    "generic auth flow",
    "RBAC engine and owner/admin all-access behavior",
    "generic admin shell",
    "Bridge installable plumbing",
    "Workbench plumbing",
    "app updater plumbing",
    "preview runtime profile and API runtime",
    "initial project identity, slug, repo, and baseline release",
)

ALLOWED_DOMAIN_MODIFICATION_AREAS = (
    "Flutter UI, visuals, layout, navigation, empty states, and assets",
    "domain backend modules, services, repositories, and migrations",
    "domain-specific admin modules",
    "domain roles and explicit permissions",
    "domain seed data when real preview behavior needs it",
    "tests, SDD artifacts, diagrams, and release evidence",
)

DESTRUCTIVE_OPERATION_APPROVAL_REQUIRED = (
    "force-push",
    "tag or release deletion",
    "production release",
    "repo deletion",
    "workspace deletion",
    "D1, Worker, route, or bucket deletion",
    "mock/demo/local-data conversion",
)

DOMAIN_INTAKE_FIELDS = (
    "business outcome",
    "domain user groups and roles",
    "role permissions with owner/admin override",
    "entities and relationships",
    "primary workflows",
    "persisted data",
    "domain admin modules",
    "notifications and business events",
    "integrations",
    "visual identity, colors, style, and reference images",
    "screens, navigation, mobile behavior, and empty states",
    "release acceptance criteria",
)

BASELINE_INTAKE_FIELDS_TO_AVOID = (
    "project name or slug",
    "frontend strategy",
    "backend framework",
    "GitHub repository",
    "Cloudflare preview setup",
    "D1 baseline identity",
    "initial admin emails",
    "initial APK/release setup",
    "Bridge installable setup",
    "Workbench setup",
)

DOMAIN_FOLLOW_UP_QUESTIONS = (
    {
        "id": "business_outcome",
        "field": "business outcome",
        "prompt": "What business outcome should the domain implementation optimize for?",
        "options": (
            "book/sell/manage core work",
            "track operational workflow",
            "infer from brief",
        ),
    },
    {
        "id": "domain_roles",
        "field": "domain roles",
        "prompt": "Which non-owner/admin people use the product, and what can each do?",
        "options": (
            "manager/staff/customer",
            "operator/vendor/customer",
            "infer from business",
        ),
    },
    {
        "id": "entities_workflows",
        "field": "entities and workflows",
        "prompt": "What entities, relationships, and workflows must be persisted?",
        "options": ("catalog/order/payment", "case/task/approval", "infer from brief"),
    },
    {
        "id": "visual_direction",
        "field": "visual identity",
        "prompt": "What visual direction, reference images, colors, and mobile empty states should guide the UI?",
        "options": (
            "use attached references",
            "clean operational UI",
            "infer and propose",
        ),
    },
    {
        "id": "release_acceptance",
        "field": "release acceptance criteria",
        "prompt": "What must be true before the new preview release is accepted?",
        "options": (
            "tests + preview smoke + APK install",
            "user walkthrough",
            "infer minimum",
        ),
    },
)

DOMAIN_ROLE_PERMISSION_MODEL = {
    "owner": {"allAccess": True, "permissions": ["*"]},
    "admin": {"allAccess": True, "permissions": ["*"]},
    "domainRoles": {
        "source": "inferred_from_business_brief",
        "permissionRule": (
            "Each generated domain role must receive explicit permissions "
            "scoped to domain capabilities; owner/admin always override."
        ),
        "examples": [
            "employee",
            "customer",
            "contractor",
            "cook",
            "supplier",
            "driver",
            "manager",
            "operator",
            "vendor",
            "patient",
            "teacher",
            "student",
            "tenant",
            "landlord",
        ],
    },
}

DOMAIN_RELEASE_GUARDRAILS = {
    "requiresImplementationStart": True,
    "realPreviewOnly": True,
    "forbiddenDefaults": ["mock", "demo", "localhost", "placeholder"],
    "runtime": {
        "APP_RUNTIME_PROFILE": "preview",
        "API_RUNTIME": "cloudflare_preview",
        "apiUrlPattern": "https://preview.nienfos.com/{sourceApp}/api",
    },
    "mustIncrementAfterInitialBuild": True,
    "mustNotOverwriteBuild": 1,
    "requiredEvidenceFields": [
        "commit",
        "tag",
        "releaseUrl",
        "apkUrl",
        "sha256",
        "previewUrl",
        "smokeResults",
        "bridgeRegistryPayload",
        "rollbackPointer",
        "updaterVerification",
    ],
}


@dataclass(frozen=True, slots=True)
class DomainFactoryBlockedReason:
    code: str
    message: str
    next_action: str

    def to_payload(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "nextAction": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class DomainFactoryContext:
    session_id: str
    source_app: str | None
    source_display_name: str | None
    workspace_path: str
    workspace_name: str
    baseline_commit: str | None
    git_branch: str | None
    git_remote: str | None
    git_tags: tuple[str, ...] = ()
    latest_release: dict[str, Any] = field(default_factory=dict)
    preview_url: str | None = None
    api_url: str | None = None
    runtime_profile: str | None = None
    api_runtime: str | None = None
    apk_status: dict[str, Any] = field(default_factory=dict)
    workbench_status: dict[str, Any] = field(default_factory=dict)
    feedback_status: dict[str, Any] = field(default_factory=dict)
    baseline_files: tuple[str, ...] = ()
    missing_baseline_files: tuple[str, ...] = ()
    protected_foundation_areas: tuple[str, ...] = PROTECTED_FOUNDATION_AREAS
    allowed_domain_modification_areas: tuple[str, ...] = (
        ALLOWED_DOMAIN_MODIFICATION_AREAS
    )
    destructive_operation_approval_required: tuple[str, ...] = (
        DESTRUCTIVE_OPERATION_APPROVAL_REQUIRED
    )
    first_spec_summary: str | None = None
    blockers: tuple[DomainFactoryBlockedReason, ...] = ()
    init_result: dict[str, Any] = field(default_factory=dict)
    project_manifest: dict[str, Any] = field(default_factory=dict)
    preview_runtime: dict[str, Any] = field(default_factory=dict)
    bridge_manifest: dict[str, Any] = field(default_factory=dict)
    llm_start_context_excerpt: str | None = None

    @property
    def status(self) -> str:
        return "blocked" if self.blockers else "ready"

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": "codex.domainFactoryContext",
            "version": 1,
            "status": self.status,
            "sessionId": self.session_id,
            "sourceApp": self.source_app,
            "sourceDisplayName": self.source_display_name,
            "workspacePath": self.workspace_path,
            "workspaceName": self.workspace_name,
            "baselineCommit": self.baseline_commit,
            "git": {
                "branch": self.git_branch,
                "remote": self.git_remote,
                "tags": list(self.git_tags),
                "latestRelease": self.latest_release,
            },
            "preview": {
                "url": self.preview_url,
                "apiUrl": self.api_url,
                "runtimeProfile": self.runtime_profile,
                "apiRuntime": self.api_runtime,
            },
            "apkStatus": self.apk_status,
            "workbenchStatus": self.workbench_status,
            "feedbackStatus": self.feedback_status,
            "baselineFiles": list(self.baseline_files),
            "missingBaselineFiles": list(self.missing_baseline_files),
            "protectedFoundationAreas": list(self.protected_foundation_areas),
            "allowedDomainModificationAreas": list(
                self.allowed_domain_modification_areas
            ),
            "destructiveOperationApprovalRequired": list(
                self.destructive_operation_approval_required
            ),
            "domainIntakeFields": list(DOMAIN_INTAKE_FIELDS),
            "baselineIntakeFieldsToAvoid": list(BASELINE_INTAKE_FIELDS_TO_AVOID),
            "followUpQuestions": list(DOMAIN_FOLLOW_UP_QUESTIONS),
            "rolePermissionModel": DOMAIN_ROLE_PERMISSION_MODEL,
            "releaseGuardrails": DOMAIN_RELEASE_GUARDRAILS,
            "firstSpecSummary": self.first_spec_summary,
            "blockers": [blocker.to_payload() for blocker in self.blockers],
        }


@dataclass(frozen=True, slots=True)
class DomainFactoryStartResult:
    status: str
    context: DomainFactoryContext
    session: ChatSession
    first_message_id: str | None
    state_path: str | None
    spec_root: str | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": "codex.domainFactoryStart",
            "version": 1,
            "status": self.status,
            "context": self.context.to_payload(),
            "sessionId": self.session.id,
            "firstMessageId": self.first_message_id,
            "statePath": self.state_path,
            "specRoot": self.spec_root,
        }


@dataclass(frozen=True, slots=True)
class DomainFactoryIntakeResult:
    status: str
    session: ChatSession
    spec_root: str
    brief_path: str
    media_references_path: str
    contract_preview_path: str
    contract_preview: dict[str, Any]
    message_id: str
    assistant_message: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": "codex.domainFactoryIntake",
            "version": 1,
            "status": self.status,
            "sessionId": self.session.id,
            "specRoot": self.spec_root,
            "briefPath": self.brief_path,
            "mediaReferencesPath": self.media_references_path,
            "contractPreviewPath": self.contract_preview_path,
            "contractPreview": self.contract_preview,
            "messageId": self.message_id,
            "assistantMessage": self.assistant_message,
        }


@dataclass(frozen=True, slots=True)
class DomainFactoryImplementationResult:
    status: str
    session: ChatSession
    spec_root: str
    workflow_evidence_path: str
    message_id: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": "codex.domainFactoryImplementation",
            "version": 1,
            "status": self.status,
            "sessionId": self.session.id,
            "specRoot": self.spec_root,
            "workflowEvidencePath": self.workflow_evidence_path,
            "messageId": self.message_id,
        }


class DomainFactoryService:
    def __init__(
        self,
        *,
        projects_root: str | Path,
        chat_repository: ChatRepository,
        app_update_registry_path: str | Path | None = None,
    ) -> None:
        self._projects_root = Path(projects_root).expanduser().resolve()
        self._chat_repository = chat_repository
        self._app_update_registry_path = (
            Path(app_update_registry_path).expanduser()
            if app_update_registry_path is not None
            else None
        )

    def build_context(
        self,
        *,
        session_id: str,
        workspace_path: str | None = None,
    ) -> DomainFactoryContext:
        session = self._require_session(session_id)
        workspace = self._validate_workspace_path(
            workspace_path or session.workspace_path
        )
        bridge_manifest = _read_yaml(workspace / "codex-bridge.yaml")
        init_result = _read_json(workspace / ".codex/factory/init-result.json")
        project_manifest = _read_yaml(workspace / ".codex/project.yaml")
        preview_runtime = _read_json(workspace / "release/preview-runtime.json")
        llm_start_context = _read_text(
            workspace / ".codex/factory/llm-start-context.md",
            max_chars=_MAX_CONTEXT_MARKDOWN_CHARS,
        )
        baseline_files, missing_baseline_files = _baseline_file_status(workspace)

        source_app = _first_text(
            init_result.get("sourceApp"),
            bridge_manifest.get("source_app"),
            bridge_manifest.get("sourceApp"),
            project_manifest.get("source_app"),
            project_manifest.get("sourceApp"),
            preview_runtime.get("sourceApp"),
            workspace.name,
        )
        source_display_name = _first_text(
            init_result.get("displayName"),
            bridge_manifest.get("display_name"),
            bridge_manifest.get("displayName"),
            project_manifest.get("name"),
            project_manifest.get("displayName"),
            source_app,
        )
        preview = _nested_dict(init_result, "resources", "cloudflarePreview")
        android = _nested_dict(init_result, "resources", "androidPreviewRelease")
        bridge_installable = _nested_dict(init_result, "resources", "bridgeInstallable")

        git_state = _git_state(workspace)
        app_update_detail = self._app_update_detail(source_app)
        apk_status = {
            "installable": bool(bridge_installable or app_update_detail),
            "sourceApp": source_app,
            "latestBuild": _first_text(
                android.get("buildNumber"),
                android.get("build"),
                app_update_detail.get("current_build"),
                app_update_detail.get("currentBuild"),
            ),
            "releaseTag": _first_text(
                android.get("releaseTag"),
                app_update_detail.get("release_tag"),
                app_update_detail.get("releaseTag"),
            ),
            "registry": app_update_detail,
        }
        preview_url = _first_text(
            preview.get("previewUrl"),
            preview_runtime.get("previewUrl"),
            preview_runtime.get("preview_url"),
        )
        api_url = _first_text(
            preview.get("apiBaseUrl"),
            preview_runtime.get("apiBaseUrl"),
            preview_runtime.get("api_url"),
        )
        runtime_profile = _first_text(
            preview_runtime.get("runtimeProfile"),
            preview_runtime.get("APP_RUNTIME_PROFILE"),
            preview_runtime.get("app_runtime_profile"),
        )
        api_runtime = _first_text(
            preview_runtime.get("apiRuntime"),
            preview_runtime.get("API_RUNTIME"),
            preview_runtime.get("api_runtime"),
        )
        blockers = _context_blockers(
            missing_baseline_files=missing_baseline_files,
            init_result=init_result,
            llm_start_context=llm_start_context,
            runtime_profile=runtime_profile,
            api_runtime=api_runtime,
            api_url=api_url,
            source_app=source_app,
            preview_runtime=preview_runtime,
        )

        return DomainFactoryContext(
            session_id=session.id,
            source_app=source_app,
            source_display_name=source_display_name,
            workspace_path=str(workspace),
            workspace_name=workspace.name,
            baseline_commit=_first_text(
                init_result.get("commit"),
                init_result.get("baselineCommit"),
                git_state.get("commit"),
            ),
            git_branch=_first_text(git_state.get("branch")),
            git_remote=_first_text(git_state.get("remote")),
            git_tags=tuple(git_state.get("tags", ())),
            latest_release=_nested_dict(
                init_result, "resources", "androidPreviewRelease"
            ),
            preview_url=preview_url,
            api_url=api_url,
            runtime_profile=runtime_profile,
            api_runtime=api_runtime,
            apk_status=apk_status,
            workbench_status=_workbench_status(workspace),
            feedback_status={
                "sourceApp": source_app,
                "bridgeInstallable": bridge_installable,
            },
            baseline_files=baseline_files,
            missing_baseline_files=missing_baseline_files,
            first_spec_summary=_first_spec_summary(workspace),
            blockers=blockers,
            init_result=init_result,
            project_manifest=project_manifest,
            preview_runtime=preview_runtime,
            bridge_manifest=bridge_manifest,
            llm_start_context_excerpt=llm_start_context,
        )

    def start(
        self,
        *,
        session_id: str,
        workspace_path: str | None = None,
    ) -> DomainFactoryStartResult:
        session = self._require_session(session_id)
        if session.active_agent_run_id is not None:
            raise RuntimeError(
                "Domain Factory cannot reconfigure a chat while an agent run is active."
            )
        context = self.build_context(
            session_id=session_id,
            workspace_path=workspace_path,
        )
        if context.blockers:
            first_message_id = self._attach_first_message(session, context)
            return DomainFactoryStartResult(
                status="blocked",
                context=context,
                session=self._require_session(session_id),
                first_message_id=first_message_id,
                state_path=None,
                spec_root=None,
            )

        session.agent_configuration = self._domain_agent_configuration(
            session.agent_configuration,
            context=context,
        )
        session.agent_profile_id = "domain-factory"
        session.agent_profile_name = "Domain Factory"
        session.agent_profile_color = "#2F80ED"
        session.active_agent_run_id = None
        session.active_agent_turn_index = 0
        session.auto_turn_index = 0
        session.touch()
        self._chat_repository.save_session(session)

        spec_root = self._ensure_sdd_spec(context)
        state_path = self._write_state(context, spec_root=spec_root)
        first_message_id = self._attach_first_message(
            session, context, spec_root=spec_root
        )
        return DomainFactoryStartResult(
            status="ready",
            context=context,
            session=self._require_session(session_id),
            first_message_id=first_message_id,
            state_path=state_path,
            spec_root=spec_root,
        )

    def submit_intake(
        self,
        *,
        session_id: str,
        brief: str,
        media_references: tuple[dict[str, Any], ...] = (),
        emit_chat_message: bool = True,
    ) -> DomainFactoryIntakeResult:
        session = self._require_session(session_id)
        context = self.build_context(session_id=session_id)
        if context.blockers:
            raise RuntimeError("Domain Factory intake requires ready baseline context.")
        normalized_brief = brief.strip()
        if not normalized_brief:
            raise ValueError("Domain Factory intake brief cannot be empty.")

        spec_root = self._require_state_spec_root(context)
        workspace = Path(context.workspace_path)
        spec_path = workspace / spec_root
        intake_dir = spec_path / "intake"
        intake_dir.mkdir(parents=True, exist_ok=True)
        brief_path = intake_dir / "original-brief.md"
        media_path = intake_dir / "media-references.json"
        contract_json_path = spec_path / "contract-preview.json"
        contract_md_path = spec_path / "contract-preview.md"

        brief_path.write_text(
            _original_brief_content(context, normalized_brief),
            encoding="utf-8",
        )
        media_payload = _media_references_payload(media_references)
        media_path.write_text(
            json.dumps(media_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        contract_preview = _build_contract_preview(
            context,
            brief=normalized_brief,
            media_references=media_payload["items"],
        )
        contract_json_path.write_text(
            json.dumps(contract_preview, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        contract_md_path.write_text(
            _contract_preview_markdown(contract_preview),
            encoding="utf-8",
        )
        state = self._read_state(context)
        state.update(
            {
                "modeStatus": "implementation_ready",
                "intakeStatus": "contract_preview_ready",
                "briefPath": str(brief_path.relative_to(workspace)),
                "mediaReferencesPath": str(media_path.relative_to(workspace)),
                "contractPreviewPath": str(contract_json_path.relative_to(workspace)),
                "updatedAt": _now_iso(),
            }
        )
        self._write_state_payload(context, state)
        assistant_message = _contract_preview_chat_message(contract_preview)
        message_id = f"domain-factory-contract-{session.id}"
        if emit_chat_message:
            message_id = self._attach_completed_message(
                session,
                content=assistant_message,
                dedupe_key=f"domain-factory:contract-preview:{session.id}",
                message_id=message_id,
            )
        return DomainFactoryIntakeResult(
            status="implementation_ready",
            session=self._require_session(session_id),
            spec_root=spec_root,
            brief_path=str(brief_path.relative_to(workspace)),
            media_references_path=str(media_path.relative_to(workspace)),
            contract_preview_path=str(contract_json_path.relative_to(workspace)),
            contract_preview=contract_preview,
            message_id=message_id,
            assistant_message=assistant_message,
        )

    def should_consume_chat_intake(self, *, session_id: str) -> bool:
        session = self._require_session(session_id)
        if session.agent_profile_id != "domain-factory":
            return False
        context = self.build_context(session_id=session_id)
        if context.blockers:
            return False
        state = self._read_state(context)
        return (
            state.get("modeStatus") == "intake"
            and not str(state.get("contractPreviewPath") or "").strip()
        )

    def confirm_implementation(
        self, *, session_id: str
    ) -> DomainFactoryImplementationResult:
        session = self._require_session(session_id)
        context = self.build_context(session_id=session_id)
        if context.blockers:
            raise RuntimeError(
                "Domain Factory implementation requires ready baseline context."
            )
        spec_root = self._require_state_spec_root(context)
        workspace = Path(context.workspace_path)
        spec_path = workspace / spec_root
        contract_path = spec_path / "contract-preview.json"
        if not contract_path.exists():
            raise RuntimeError("Domain Factory contract preview is required first.")
        session.agent_configuration = self._domain_agent_configuration(
            session.agent_configuration,
            context=context,
        )
        session.touch()
        self._chat_repository.save_session(session)
        workflow_path = spec_path / "workflow-evidence.json"
        workflow_payload = {
            "kind": "codex.domainFactoryWorkflowEvidence",
            "version": 1,
            "status": "implementing",
            "mode": "generator_reviewer_paired",
            "sessionId": session.id,
            "reviewerFeedbackBecomesNextGeneratorPrompt": True,
            "agentPreset": "review",
            "updatedAt": _now_iso(),
        }
        workflow_path.write_text(
            json.dumps(workflow_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        state = self._read_state(context)
        state.update(
            {
                "modeStatus": "implementing",
                "workflowEvidencePath": str(workflow_path.relative_to(workspace)),
                "updatedAt": _now_iso(),
            }
        )
        self._write_state_payload(context, state)
        message_id = self._attach_completed_message(
            session,
            content=(
                "Domain Factory implementation mode is active. Generator and "
                "reviewer are configured as a paired workflow; reviewer output "
                "is treated as the next generator prompt until release readiness."
            ),
            dedupe_key=f"domain-factory:implementing:{session.id}",
            message_id=f"domain-factory-implementing-{session.id}",
        )
        return DomainFactoryImplementationResult(
            status="implementing",
            session=self._require_session(session_id),
            spec_root=spec_root,
            workflow_evidence_path=str(workflow_path.relative_to(workspace)),
            message_id=message_id,
        )

    def validate_completion_evidence(self, *, session_id: str) -> dict[str, Any]:
        context = self.build_context(session_id=session_id)
        spec_root = self._require_state_spec_root(context)
        workspace = Path(context.workspace_path)
        spec_path = workspace / spec_root
        required = {
            "implementation": spec_path / "implementation-evidence.json",
            "validation": spec_path / "validation-evidence.json",
            "release": spec_path / "release-evidence.json",
        }
        blocked_release = spec_path / "blocked-release.json"
        missing = [
            name
            for name, path in required.items()
            if not path.exists()
            and not (name == "release" and blocked_release.exists())
        ]
        return {
            "kind": "codex.domainFactoryCompletionEvidence",
            "version": 1,
            "status": "ready" if not missing else "blocked",
            "canCompleteTasks": not missing,
            "specRoot": spec_root,
            "missingEvidence": missing,
            "requiredEvidence": {
                name: str(path.relative_to(workspace))
                for name, path in required.items()
            },
            "blockedReleasePath": str(blocked_release.relative_to(workspace)),
        }

    def validate_release_evidence(
        self,
        *,
        source_app: str,
        evidence: dict[str, Any],
        initial_build: int = 1,
    ) -> dict[str, Any]:
        return _validate_release_evidence(
            source_app=source_app,
            evidence=evidence,
            initial_build=initial_build,
        )

    def persist_release_evidence(
        self,
        *,
        session_id: str,
        evidence: dict[str, Any],
        initial_build: int = 1,
    ) -> dict[str, Any]:
        context = self.build_context(session_id=session_id)
        if context.blockers:
            raise RuntimeError(
                "Domain Factory release evidence requires ready baseline context."
            )
        spec_root = self._require_state_spec_root(context)
        validation = _validate_release_evidence(
            source_app=context.source_app or Path(context.workspace_path).name,
            evidence=evidence,
            initial_build=initial_build,
        )
        workspace = Path(context.workspace_path)
        release_path = workspace / spec_root / "release-evidence.json"
        state_path = workspace / ".codex/factory/domain-factory-state.json"
        if not validation["ok"]:
            return {
                "kind": "codex.domainFactoryReleaseEvidence",
                "version": 1,
                "status": "blocked",
                "ok": False,
                "sessionId": context.session_id,
                "sourceApp": context.source_app,
                "specRoot": spec_root,
                "releaseEvidencePath": str(release_path.relative_to(workspace)),
                "statePath": str(state_path.relative_to(workspace)),
                "validation": validation,
                "errors": validation["errors"],
            }

        release_payload = {
            "kind": "codex.domainFactoryReleaseEvidence",
            "version": 1,
            "status": "ready",
            "sessionId": context.session_id,
            "sourceApp": context.source_app,
            "specRoot": spec_root,
            "initialBuild": initial_build,
            "build": validation["build"],
            "persistedAt": _now_iso(),
            "evidence": evidence,
            "updaterVerification": _updater_verification_payload(evidence),
            "validation": validation,
        }
        release_path.write_text(
            json.dumps(release_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        state = self._read_state(context)
        state.update(
            {
                "modeStatus": "release_evidence_ready",
                "releaseEvidencePath": str(release_path.relative_to(workspace)),
                "releaseEvidenceValidation": validation,
                "updatedAt": _now_iso(),
            }
        )
        self._write_state_payload(context, state)
        return {
            "kind": "codex.domainFactoryReleaseEvidence",
            "version": 1,
            "status": "ready",
            "ok": True,
            "sessionId": context.session_id,
            "sourceApp": context.source_app,
            "specRoot": spec_root,
            "releaseEvidencePath": str(release_path.relative_to(workspace)),
            "statePath": str(state_path.relative_to(workspace)),
            "validation": validation,
            "errors": [],
        }

    def _require_session(self, session_id: str) -> ChatSession:
        session = self._chat_repository.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} was not found.")
        return session

    def _validate_workspace_path(self, workspace_path: str) -> Path:
        workspace = Path(workspace_path).expanduser().resolve()
        try:
            workspace.relative_to(self._projects_root)
        except ValueError as exc:
            raise ValueError("Workspace path must be under PROJECTS_ROOT.") from exc
        if not workspace.is_dir():
            raise ValueError(f"Workspace path does not exist: {workspace}")
        return workspace

    def _app_update_detail(self, source_app: str | None) -> dict[str, Any]:
        if (
            not source_app
            or self._app_update_registry_path is None
            or not self._app_update_registry_path.exists()
        ):
            return {}
        payload = _read_json(self._app_update_registry_path)
        apps = payload.get("apps")
        if isinstance(apps, list):
            for item in apps:
                if isinstance(item, dict) and item.get("source_app") == source_app:
                    return item
                if isinstance(item, dict) and item.get("sourceApp") == source_app:
                    return item
        if isinstance(apps, dict):
            item = apps.get(source_app)
            return item if isinstance(item, dict) else {}
        item = payload.get(source_app)
        return item if isinstance(item, dict) else {}

    def _domain_agent_configuration(
        self,
        current: AgentConfiguration,
        *,
        context: DomainFactoryContext,
    ) -> AgentConfiguration:
        normalized = current.normalized()
        generator_prompt = _trim_prompt(_domain_generator_prompt(context))
        reviewer_prompt = _trim_prompt(_domain_reviewer_prompt(context))
        for agent_id, definition in normalized.agents.items():
            if agent_id == AgentId.GENERATOR:
                definition.enabled = True
                definition.label = _DOMAIN_FACTORY_GENERATOR_LABEL
                definition.prompt = generator_prompt
                definition.visibility = AgentVisibilityMode.VISIBLE
                definition.max_turns = max(definition.max_turns, 20)
                definition.trigger_interval = 0
            elif agent_id == AgentId.REVIEWER:
                definition.enabled = True
                definition.label = _DOMAIN_FACTORY_REVIEWER_LABEL
                definition.prompt = reviewer_prompt
                definition.visibility = AgentVisibilityMode.COLLAPSED
                definition.max_turns = max(definition.max_turns, 20)
                definition.trigger_interval = 0
            else:
                definition.enabled = False
                definition.max_turns = 0
                definition.trigger_interval = 0
        return AgentConfiguration(
            preset=AgentPreset.REVIEW,
            display_mode=AgentDisplayMode.SHOW_ALL,
            turn_budget_mode=TurnBudgetMode.EACH_AGENT,
            agents=normalized.agents,
            supervisor_member_ids=normalized.supervisor_member_ids,
            summary_strategy=normalized.summary_strategy,
        ).normalized()

    def _attach_first_message(
        self,
        session: ChatSession,
        context: DomainFactoryContext,
        *,
        spec_root: str | None = None,
    ) -> str:
        dedupe_key = f"domain-factory:start:{session.id}:{context.workspace_path}"
        message = ChatMessage(
            id=f"domain-factory-start-{session.id}",
            session_id=session.id,
            role=ChatMessageRole.ASSISTANT,
            author_type=ChatMessageAuthorType.ASSISTANT,
            content=_first_context_message(context, spec_root=spec_root),
            status=ChatMessageStatus.COMPLETED,
            agent_id=AgentId.GENERATOR,
            agent_label=_DOMAIN_FACTORY_GENERATOR_LABEL,
            dedupe_key=dedupe_key,
        )
        reserved = self._chat_repository.reserve_message(message)
        if reserved.content != message.content or reserved.status != message.status:
            reserved.sync(content=message.content, status=ChatMessageStatus.COMPLETED)
            self._chat_repository.save_message(reserved)
        return reserved.id

    def _write_state(self, context: DomainFactoryContext, *, spec_root: str) -> str:
        workspace = Path(context.workspace_path)
        state_path = workspace / ".codex/factory/domain-factory-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "kind": "codex.domainFactoryState",
            "version": 1,
            "status": context.status,
            "modeStatus": "intake",
            "sessionId": context.session_id,
            "sourceApp": context.source_app,
            "workspacePath": context.workspace_path,
            "baselineCommit": context.baseline_commit,
            "latestReleaseBaseline": context.apk_status,
            "specRoot": spec_root,
            "updatedAt": _now_iso(),
            "guardrails": {
                "protectedFoundationAreas": list(PROTECTED_FOUNDATION_AREAS),
                "allowedDomainModificationAreas": list(
                    ALLOWED_DOMAIN_MODIFICATION_AREAS
                ),
                "destructiveOperationApprovalRequired": list(
                    DESTRUCTIVE_OPERATION_APPROVAL_REQUIRED
                ),
                "mockDemoRequiresExplicitUserRequest": True,
            },
            "intake": _domain_intake_contract_payload(),
            "rolePermissionModel": DOMAIN_ROLE_PERMISSION_MODEL,
            "releaseGuardrails": DOMAIN_RELEASE_GUARDRAILS,
        }
        state_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return str(state_path.relative_to(workspace))

    def _read_state(self, context: DomainFactoryContext) -> dict[str, Any]:
        state_path = (
            Path(context.workspace_path) / ".codex/factory/domain-factory-state.json"
        )
        payload = _read_json(state_path)
        if not payload:
            raise RuntimeError("Domain Factory state is missing. Start the mode first.")
        return payload

    def _write_state_payload(
        self,
        context: DomainFactoryContext,
        payload: dict[str, Any],
    ) -> None:
        state_path = (
            Path(context.workspace_path) / ".codex/factory/domain-factory-state.json"
        )
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _require_state_spec_root(self, context: DomainFactoryContext) -> str:
        state = self._read_state(context)
        spec_root = _first_text(state.get("specRoot"))
        if not spec_root:
            raise RuntimeError("Domain Factory state does not reference an SDD spec.")
        spec_path = Path(context.workspace_path) / spec_root
        if not spec_path.is_dir():
            raise RuntimeError("Domain Factory SDD spec is missing.")
        return spec_root

    def _ensure_sdd_spec(self, context: DomainFactoryContext) -> str:
        workspace = Path(context.workspace_path)
        spec_id = f"019-domain-factory-{_slug_suffix(context.session_id)}"
        spec_root = workspace / "specs" / spec_id
        (spec_root / "intake").mkdir(parents=True, exist_ok=True)
        (spec_root / "diagrams").mkdir(parents=True, exist_ok=True)
        _write_if_missing(
            spec_root / "metadata.yaml",
            _domain_metadata(context, spec_id),
        )
        _write_if_missing(spec_root / "spec.md", _domain_spec(context))
        _write_if_missing(spec_root / "plan.md", _domain_plan())
        _write_if_missing(spec_root / "tasks.md", _domain_tasks())
        _write_if_missing(spec_root / "traceability.yaml", _domain_traceability())
        _write_if_missing(
            spec_root / "intake" / "domain-brief.md",
            _domain_intake_template(context),
        )
        _write_if_missing(
            spec_root / "intake" / "domain-intake-contract.json",
            json.dumps(_domain_intake_contract_payload(), indent=2, sort_keys=True)
            + "\n",
        )
        _write_if_missing(
            spec_root / "intake" / "media-references.json",
            json.dumps(
                {
                    "kind": "codex.domainFactoryMediaReferences",
                    "version": 1,
                    "status": "pending_user_attachments",
                    "items": [],
                    "storageRule": (
                        "Chat image/file/audio references remain attached to the "
                        "current session and exact assets should be copied or linked "
                        "under this intake directory during implementation."
                    ),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        _write_if_missing(
            spec_root / "release-guardrails.json",
            json.dumps(DOMAIN_RELEASE_GUARDRAILS, indent=2, sort_keys=True) + "\n",
        )
        diagrams = {
            "entity-relationship.mmd": "erDiagram\n    DOMAIN_ENTITY ||--o{ RELATED_ENTITY : relates_to\n",
            "class.mmd": "classDiagram\n    class DomainRole\n    class DomainPermission\n    DomainRole --> DomainPermission\n",
            "sequence.mmd": "sequenceDiagram\n    participant User\n    participant App\n    participant API\n    User->>App: Submit domain workflow\n    App->>API: Persist real preview data\n",
            "component.mmd": "flowchart LR\n    App[Flutter App] --> API[Preview API]\n    API --> DB[(Preview D1)]\n    Admin[Admin Shell] --> API\n",
            "deployment.mmd": "flowchart LR\n    APK[Preview APK] --> Preview[preview.nienfos.com]\n    Preview --> Worker[Cloudflare Worker]\n    Worker --> D1[(Cloudflare D1)]\n",
        }
        for filename, content in diagrams.items():
            _write_if_missing(spec_root / "diagrams" / filename, content)
        return str(spec_root.relative_to(workspace))

    def _attach_completed_message(
        self,
        session: ChatSession,
        *,
        content: str,
        dedupe_key: str,
        message_id: str,
    ) -> str:
        message = ChatMessage(
            id=message_id,
            session_id=session.id,
            role=ChatMessageRole.ASSISTANT,
            author_type=ChatMessageAuthorType.ASSISTANT,
            content=content,
            status=ChatMessageStatus.COMPLETED,
            agent_id=AgentId.GENERATOR,
            agent_label=_DOMAIN_FACTORY_GENERATOR_LABEL,
            dedupe_key=dedupe_key,
        )
        reserved = self._chat_repository.reserve_message(message)
        if (
            reserved.content != content
            or reserved.status != ChatMessageStatus.COMPLETED
        ):
            reserved.sync(content=content, status=ChatMessageStatus.COMPLETED)
            self._chat_repository.save_message(reserved)
        return reserved.id


def _domain_generator_prompt(context: DomainFactoryContext) -> str:
    context_json = json.dumps(context.to_payload(), indent=2, sort_keys=True)
    return f"""
You are the Domain Factory generator for the current initialized project.

You are not creating a new project. Work only in the current workspace:
{context.workspace_path}

Baseline context:
{context_json}

Rules:
- Consume the baseline context before editing.
- Implement business/domain behavior on top of the initialized baseline.
- Do not recreate New Project deterministic init, GitHub setup, Cloudflare preview setup, D1 baseline identity, Bridge installable setup, Workbench setup, or the initial preview release.
- Preserve generic auth, the RBAC engine, the admin shell, updater plumbing, Bridge plumbing, and Workbench plumbing.
- Add domain-specific roles and explicit permissions as required by the business. Owner/admin must retain access to every domain capability.
- Ask only missing domain/product questions. Do not ask for baseline setup fields: {", ".join(BASELINE_INTAKE_FIELDS_TO_AVOID)}.
- Intake must cover: {", ".join(DOMAIN_INTAKE_FIELDS)}.
- Generate follow-up questions only from the Domain Factory intake fields and include recommended/default/inferred options.
- Produce a domain contract preview before implementation using the role permission model where owner/admin have all access and domain roles get explicit permissions.
- Visual implementation is first-class: prioritize real product look and feel, mobile ergonomics, empty states, navigation, and reference-image fidelity.
- You may modify UI, colors, layout, navigation, backend domain code, migrations, tests, SDD artifacts, diagrams, and release evidence.
- Never switch to mock/demo/local/placeholder data unless the user explicitly asks for a demo/mock release.
- Keep preview runtime real: APP_RUNTIME_PROFILE=preview, API_RUNTIME=cloudflare_preview, API URL {context.api_url or "https://preview.nienfos.com/<slug>/api"}.
- Before implementation, produce a domain contract preview with roles, permissions, entities, workflows, screens, visual direction, backend scope, tests, SDD/diagram requirements, and release target.
- Once implementation starts, finish by preparing a new real preview release after the initial build. Do not overwrite build 1.
- Remote destructive operations need explicit approval: {", ".join(DESTRUCTIVE_OPERATION_APPROVAL_REQUIRED)}.
- Update SDD evidence before claiming readiness: spec, plan, tasks, traceability, DER/ERD, class, sequence, component, and deployment diagrams.
""".strip()


def _domain_reviewer_prompt(context: DomainFactoryContext) -> str:
    context_json = json.dumps(context.to_payload(), indent=2, sort_keys=True)
    return f"""
You are the Domain Factory reviewer for the current initialized project.

Review with the same baseline context:
{context_json}

Return only the next concrete prompt for the generator unless the work is truly release-ready.

Verify:
- Generator did not recreate New Project baseline infrastructure.
- Generic auth, RBAC engine, admin shell, Bridge plumbing, Workbench plumbing, updater plumbing, preview runtime, and initial project identity are intact.
- Domain roles and permissions match the requested business and are testable.
- Owner/admin retain all access across domain capabilities.
- Domain intake avoided baseline setup questions and produced a contract preview before implementation.
- UI quality, visual hierarchy, mobile ergonomics, empty states, navigation, and reference-image fidelity are strong.
- Backend domain behavior, persistence, migrations, and seed data are real preview paths, not mock/demo/local defaults.
- SDD spec, plan, tasks, traceability, DER/ERD, class, sequence, component, and deployment diagrams are updated.
- Relevant tests pass and release evidence exists for the new preview release.
- The release increments after the initial preview build and Bridge/app updater metadata points at the new build.

If anything is missing, produce an actionable next generator prompt with exact files, tests, and evidence to fix.
""".strip()


def _first_context_message(
    context: DomainFactoryContext,
    *,
    spec_root: str | None,
) -> str:
    if context.blockers:
        blockers = "\n".join(
            f"- {blocker.code}: {blocker.message} Next: {blocker.next_action}"
            for blocker in context.blockers
        )
        return f"""Domain Factory could not start yet for this project.

Workspace: {context.workspace_path}
Source app: {context.source_app or "unknown"}

Blocked context:
{blockers}

Domain Factory only runs after the deterministic baseline context exists. Fix the blocked baseline context, then start Domain Factory again from this same chat.
"""
    return f"""Domain Factory mode is active for the current project.

Workspace: {context.workspace_path}
Source app: {context.source_app or "unknown"}
Preview: {context.preview_url or "unknown"}
Preview API: {context.api_url or "unknown"}
Baseline commit: {context.baseline_commit or "unknown"}
SDD run: {spec_root or "pending"}

Send the business/domain brief here. You can paste a long description and attach visual references, logo/icon ideas, screenshots, or exact assets.

I will ask only for missing domain decisions: roles and permissions, entities, workflows, screens, visual direction, integrations, notifications, persisted data, admin modules, and release acceptance criteria. I will not ask again for project slug, GitHub, Cloudflare, D1, initial APK, Bridge, or Workbench setup.
"""


def _original_brief_content(context: DomainFactoryContext, brief: str) -> str:
    return f"""# Original Domain Brief

Session: `{context.session_id}`
Workspace: `{context.workspace_path}`
Source app: `{context.source_app or "unknown"}`
Captured at: `{_now_iso()}`

## Brief

{brief.strip()}
"""


def _media_references_payload(
    media_references: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for index, item in enumerate(media_references, start=1):
        if not isinstance(item, dict):
            continue
        normalized = {
            "id": _first_text(item.get("id"), item.get("assetId"), f"media-{index}"),
            "role": _first_text(item.get("role"), "visual_reference"),
            "kind": _first_text(item.get("kind"), item.get("mediaType"), "reference"),
            "filename": _first_text(item.get("filename"), item.get("originalFilename")),
            "assetId": _first_text(item.get("assetId"), item.get("asset_id")),
            "path": _first_text(
                item.get("path"), item.get("copyPath"), item.get("url")
            ),
            "mimeType": _first_text(item.get("mimeType"), item.get("contentType")),
            "sha256": _first_text(item.get("sha256")),
            "source": _first_text(item.get("source"), "chat_intake"),
        }
        normalized = {key: value for key, value in normalized.items() if value}
        items.append(normalized)
    return {
        "kind": "codex.domainFactoryMediaReferences",
        "version": 1,
        "status": "captured" if items else "no_media_references",
        "items": items,
        "updatedAt": _now_iso(),
    }


def _build_contract_preview(
    context: DomainFactoryContext,
    *,
    brief: str,
    media_references: list[dict[str, Any]],
) -> dict[str, Any]:
    roles = _infer_terms(
        brief,
        (
            "manager",
            "staff",
            "employee",
            "customer",
            "supplier",
            "driver",
            "operator",
            "vendor",
            "patient",
            "teacher",
            "student",
            "tenant",
            "landlord",
            "contractor",
        ),
    )
    entities = _infer_terms(
        brief,
        (
            "order",
            "booking",
            "appointment",
            "customer",
            "product",
            "inventory",
            "invoice",
            "payment",
            "task",
            "case",
            "property",
            "class",
            "patient",
            "supplier",
        ),
    )
    screens = _infer_terms(
        brief,
        (
            "dashboard",
            "calendar",
            "catalog",
            "orders",
            "profile",
            "admin",
            "reports",
            "checkout",
            "inventory",
        ),
    )
    if not roles:
        roles = ["domain_user"]
    if not entities:
        entities = ["domain_entity"]
    if not screens:
        screens = ["dashboard", "domain workflow", "admin"]
    permissions = {
        role: [
            f"domain.{role}.read",
            f"domain.{role}.write",
        ]
        for role in roles
    }
    return {
        "kind": "codex.domainFactoryContractPreview",
        "version": 1,
        "status": "ready_for_implementation_confirmation",
        "sourceApp": context.source_app,
        "workspacePath": context.workspace_path,
        "summary": _brief_summary(brief),
        "roles": {
            "owner": DOMAIN_ROLE_PERMISSION_MODEL["owner"],
            "admin": DOMAIN_ROLE_PERMISSION_MODEL["admin"],
            "domain": [
                {
                    "id": role,
                    "permissions": permissions[role],
                    "ownerAdminOverride": True,
                }
                for role in roles
            ],
        },
        "entities": entities,
        "relationships": [
            {"from": entities[0], "to": entity, "type": "domain_relationship"}
            for entity in entities[1:]
        ],
        "workflows": _infer_workflows(brief),
        "screens": screens,
        "visualDirection": _infer_visual_direction(brief, media_references),
        "backendScope": [
            "domain services",
            "domain repositories",
            "domain persistence/migrations",
            "domain admin modules",
            "role permission records",
        ],
        "tests": [
            "domain role permission tests",
            "owner/admin all-access tests",
            "domain workflow persistence tests",
            "preview runtime/no mock guardrail tests",
        ],
        "diagramUpdates": [
            "DER/ERD",
            "class",
            "sequence",
            "component",
            "deployment",
        ],
        "releaseTarget": {
            "previewUrl": context.preview_url,
            "apiUrl": context.api_url,
            "runtimeProfile": "preview",
            "apiRuntime": "cloudflare_preview",
            "nextBuildMustBeGreaterThan": _initial_build(context),
            "mockOrDemo": False,
        },
        "mediaReferences": media_references,
        "baselineFieldsAsked": [],
        "updatedAt": _now_iso(),
    }


def _contract_preview_markdown(contract: dict[str, Any]) -> str:
    domain_roles = [
        item.get("id", "")
        for item in _list_of_dicts(_nested_dict(contract, "roles").get("domain"))
    ]
    return f"""# Domain Contract Preview

Status: `{contract.get("status")}`

## Summary

{contract.get("summary", "")}

## Roles

- owner: all access
- admin: all access
- domain: {", ".join(role for role in domain_roles if role) or "domain_user"}

## Entities

{_markdown_list(contract.get("entities"))}

## Workflows

{_markdown_list(contract.get("workflows"))}

## Screens

{_markdown_list(contract.get("screens"))}

## Release Target

- Preview: `{_nested_dict(contract, "releaseTarget").get("previewUrl")}`
- API: `{_nested_dict(contract, "releaseTarget").get("apiUrl")}`
- Runtime: `preview` / `cloudflare_preview`
"""


def _contract_preview_chat_message(contract: dict[str, Any]) -> str:
    release_target = _nested_dict(contract, "releaseTarget")
    return (
        "Domain Factory contract preview is ready.\n\n"
        f"Summary: {contract.get('summary', '')}\n"
        f"Roles: owner/admin all-access plus "
        f"{len(_nested_dict(contract, 'roles').get('domain', []))} domain role(s).\n"
        f"Entities: {', '.join(str(item) for item in contract.get('entities', []))}.\n"
        f"Preview API: {release_target.get('apiUrl')}.\n\n"
        "Confirm implementation to move into paired generator/reviewer mode."
    )


def _infer_terms(brief: str, candidates: tuple[str, ...]) -> list[str]:
    normalized = brief.lower()
    return [candidate for candidate in candidates if candidate in normalized]


def _infer_workflows(brief: str) -> list[str]:
    workflows = _infer_terms(
        brief,
        ("approval", "booking", "checkout", "assignment", "delivery", "reporting"),
    )
    if workflows:
        return [f"{workflow} workflow" for workflow in workflows]
    return ["primary domain workflow", "admin management workflow"]


def _infer_visual_direction(
    brief: str,
    media_references: list[dict[str, Any]],
) -> dict[str, Any]:
    colors = _infer_terms(
        brief,
        ("blue", "green", "red", "black", "white", "yellow", "purple"),
    )
    return {
        "style": "derived_from_brief_and_references",
        "colors": colors,
        "hasMediaReferences": bool(media_references),
        "referenceCount": len(media_references),
        "mobileFirst": True,
        "emptyStatesRequired": True,
    }


def _brief_summary(brief: str) -> str:
    normalized = " ".join(brief.split())
    if len(normalized) <= 240:
        return normalized
    return normalized[:237].rstrip() + "..."


def _initial_build(context: DomainFactoryContext) -> int:
    raw = context.apk_status.get("latestBuild")
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        return 1


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _markdown_list(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "- pending"
    return "\n".join(f"- {item}" for item in value)


def _validate_release_evidence(
    *,
    source_app: str,
    evidence: dict[str, Any],
    initial_build: int,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    required_fields = DOMAIN_RELEASE_GUARDRAILS["requiredEvidenceFields"]
    for field_name in required_fields:
        if not _evidence_field_present(evidence.get(field_name)):
            errors.append(
                {
                    "code": "missing_release_evidence_field",
                    "field": field_name,
                    "message": f"Release evidence field {field_name} is required.",
                }
            )
    build = evidence.get("build") or evidence.get("buildNumber")
    try:
        build_number = int(str(build))
    except (TypeError, ValueError):
        build_number = 0
    if build_number <= initial_build:
        errors.append(
            {
                "code": "release_build_not_incremented",
                "field": "build",
                "message": f"Release build must be greater than {initial_build}.",
            }
        )
    runtime_profile = _first_text(
        evidence.get("runtimeProfile"),
        evidence.get("APP_RUNTIME_PROFILE"),
    )
    api_runtime = _first_text(evidence.get("apiRuntime"), evidence.get("API_RUNTIME"))
    api_url = _first_text(evidence.get("apiUrl"), evidence.get("api_url"))
    if runtime_profile != "preview":
        errors.append(
            {
                "code": "invalid_release_runtime_profile",
                "field": "runtimeProfile",
                "message": "Release runtime profile must be preview.",
            }
        )
    if api_runtime != "cloudflare_preview":
        errors.append(
            {
                "code": "invalid_release_api_runtime",
                "field": "apiRuntime",
                "message": "Release API runtime must be cloudflare_preview.",
            }
        )
    expected_api_url = f"https://preview.nienfos.com/{source_app}/api"
    if api_url != expected_api_url:
        errors.append(
            {
                "code": "invalid_release_api_url",
                "field": "apiUrl",
                "message": f"Release API URL must be {expected_api_url}.",
            }
        )
    updater = _updater_verification_payload(evidence)
    if updater.get("previousBuildSeesNewBuild") is not True:
        errors.append(
            {
                "code": "updater_previous_build_missing_new_build",
                "field": "updaterVerification.previousBuildSeesNewBuild",
                "message": "Previous preview build must see the new updater build.",
            }
        )
    if updater.get("newBuildHasPendingSelfUpdate") is not False:
        errors.append(
            {
                "code": "updater_new_build_has_pending_self_update",
                "field": "updaterVerification.newBuildHasPendingSelfUpdate",
                "message": "The newly installed build must not report a pending self-update.",
            }
        )
    for forbidden in DOMAIN_RELEASE_GUARDRAILS["forbiddenDefaults"]:
        if _contains_forbidden_value(evidence, str(forbidden)):
            errors.append(
                {
                    "code": "forbidden_release_default",
                    "field": "evidence",
                    "message": f"Release evidence contains forbidden value {forbidden}.",
                }
            )
    return {
        "kind": "codex.domainFactoryReleaseEvidenceValidation",
        "version": 1,
        "status": "valid" if not errors else "blocked",
        "ok": not errors,
        "errors": errors,
        "initialBuild": initial_build,
        "build": build_number,
    }


def _evidence_field_present(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    if isinstance(value, bool):
        return True
    return value is not None


def _updater_verification_payload(evidence: dict[str, Any]) -> dict[str, Any]:
    nested = evidence.get("updaterVerification")
    updater = dict(nested) if isinstance(nested, dict) else {}
    if "previousBuildSeesNewBuild" not in updater:
        updater["previousBuildSeesNewBuild"] = evidence.get(
            "previousBuildSeesNewBuild"
        )
    if "newBuildHasPendingSelfUpdate" not in updater:
        updater["newBuildHasPendingSelfUpdate"] = evidence.get(
            "newBuildHasPendingSelfUpdate"
        )
    return updater


def _contains_forbidden_value(value: Any, forbidden: str) -> bool:
    if isinstance(value, str):
        return forbidden.lower() in value.lower()
    if isinstance(value, dict):
        return any(
            _contains_forbidden_value(item, forbidden) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_value(item, forbidden) for item in value)
    return False


def _trim_prompt(prompt: str) -> str:
    if len(prompt) <= _MAX_PROMPT_CHARS:
        return prompt
    suffix = "\n\n[Domain Factory context trimmed to fit agent prompt limit.]"
    return prompt[: _MAX_PROMPT_CHARS - len(suffix)].rstrip() + suffix


def _context_blockers(
    *,
    missing_baseline_files: tuple[str, ...],
    init_result: dict[str, Any],
    llm_start_context: str | None,
    runtime_profile: str | None,
    api_runtime: str | None,
    api_url: str | None,
    source_app: str | None,
    preview_runtime: dict[str, Any],
) -> tuple[DomainFactoryBlockedReason, ...]:
    blockers: list[DomainFactoryBlockedReason] = []
    missing_codes = {
        "codex-bridge.yaml": (
            "missing_bridge_manifest",
            "The Bridge project manifest is missing.",
            "Restore codex-bridge.yaml from deterministic init.",
        ),
        ".codex/factory/init-result.json": (
            "missing_init_result",
            "The deterministic baseline init result is missing.",
            "Run or repair New Project deterministic init for this workspace.",
        ),
        ".codex/factory/llm-start-context.md": (
            "missing_llm_start_context",
            "The baseline LLM start context is missing.",
            "Run the Project Factory LLM context pack phase again.",
        ),
        "release/preview-runtime.json": (
            "missing_preview_runtime",
            "The real preview runtime descriptor is missing.",
            "Restore release/preview-runtime.json with preview/cloudflare_preview values.",
        ),
        ".codex/project.yaml": (
            "missing_project_manifest",
            "The deterministic project manifest is missing.",
            "Restore .codex/project.yaml from deterministic init.",
        ),
    }
    for missing_file in missing_baseline_files:
        code, message, next_action = missing_codes[missing_file]
        blockers.append(
            DomainFactoryBlockedReason(
                code=code,
                message=message,
                next_action=next_action,
            )
        )
    if (
        not init_result
        and ".codex/factory/init-result.json" not in missing_baseline_files
    ):
        blockers.append(
            DomainFactoryBlockedReason(
                code="invalid_init_result",
                message="The deterministic baseline init result is unreadable or empty.",
                next_action="Regenerate .codex/factory/init-result.json.",
            )
        )
    if (
        not llm_start_context
        and ".codex/factory/llm-start-context.md" not in missing_baseline_files
    ):
        blockers.append(
            DomainFactoryBlockedReason(
                code="invalid_llm_start_context",
                message="The baseline LLM start context is unreadable or empty.",
                next_action="Regenerate .codex/factory/llm-start-context.md.",
            )
        )
    if (
        not preview_runtime
        and "release/preview-runtime.json" not in missing_baseline_files
    ):
        blockers.append(
            DomainFactoryBlockedReason(
                code="invalid_preview_runtime",
                message="The preview runtime descriptor is unreadable or empty.",
                next_action="Regenerate release/preview-runtime.json.",
            )
        )
    ready = init_result.get("readyForBusinessLlm")
    blocked_with_context = init_result.get("blockedWithContext")
    if ready is False and blocked_with_context is not True:
        blockers.append(
            DomainFactoryBlockedReason(
                code="baseline_not_ready_for_business_llm",
                message="Baseline context says it is not ready for business/domain LLM work.",
                next_action="Resolve deterministic init blockers or produce blocked-with-context baseline evidence.",
            )
        )
    if not runtime_profile:
        blockers.append(
            DomainFactoryBlockedReason(
                code="missing_runtime_profile",
                message="APP_RUNTIME_PROFILE/runtimeProfile is required for readiness.",
                next_action="Set runtimeProfile or APP_RUNTIME_PROFILE to preview in release/preview-runtime.json.",
            )
        )
    elif runtime_profile != "preview":
        blockers.append(
            DomainFactoryBlockedReason(
                code="invalid_runtime_profile",
                message=f"Preview runtime profile must be preview, got {runtime_profile}.",
                next_action="Restore APP_RUNTIME_PROFILE=preview before Domain Factory implementation.",
            )
        )
    if not api_runtime:
        blockers.append(
            DomainFactoryBlockedReason(
                code="missing_api_runtime",
                message="API_RUNTIME/apiRuntime is required for readiness.",
                next_action="Set apiRuntime or API_RUNTIME to cloudflare_preview in release/preview-runtime.json.",
            )
        )
    elif api_runtime != "cloudflare_preview":
        blockers.append(
            DomainFactoryBlockedReason(
                code="invalid_api_runtime",
                message=f"Preview API runtime must be cloudflare_preview, got {api_runtime}.",
                next_action="Restore API_RUNTIME=cloudflare_preview before Domain Factory implementation.",
            )
        )
    if not api_url:
        blockers.append(
            DomainFactoryBlockedReason(
                code="missing_preview_api_url",
                message="Preview API URL is required for readiness.",
                next_action="Set apiBaseUrl/api_url to https://preview.nienfos.com/{slug}/api.",
            )
        )
    elif source_app and f"https://preview.nienfos.com/{source_app}/api" != api_url:
        blockers.append(
            DomainFactoryBlockedReason(
                code="invalid_preview_api_url",
                message="Preview API URL does not match the required preview.nienfos.com/{slug}/api pattern.",
                next_action="Fix release/preview-runtime.json or init context before Domain Factory implementation.",
            )
        )
    return tuple(blockers)


def _baseline_file_status(workspace: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    present = tuple(
        path for path in CRITICAL_BASELINE_FILES if (workspace / path).exists()
    )
    missing = tuple(
        path for path in CRITICAL_BASELINE_FILES if not (workspace / path).exists()
    )
    return present, missing


def _git_state(workspace: Path) -> dict[str, Any]:
    return {
        "commit": _git(workspace, "rev-parse", "HEAD"),
        "branch": _git(workspace, "rev-parse", "--abbrev-ref", "HEAD"),
        "remote": _git(workspace, "remote", "get-url", "origin"),
        "tags": tuple(
            line
            for line in (
                _git(workspace, "tag", "--points-at", "HEAD") or ""
            ).splitlines()
            if line.strip()
        ),
    }


def _git(workspace: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ("git", *args),
            cwd=workspace,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _workbench_status(workspace: Path) -> dict[str, Any]:
    specs_root = workspace / "specs"
    specs = []
    if specs_root.is_dir():
        specs = [
            child.name
            for child in sorted(specs_root.iterdir())
            if child.is_dir() and not child.name.startswith(".")
        ]
    return {
        "hasSpecs": bool(specs),
        "specCount": len(specs),
        "specs": specs[:20],
    }


def _first_spec_summary(workspace: Path) -> str | None:
    specs_root = workspace / "specs"
    if not specs_root.is_dir():
        return None
    for spec in sorted(specs_root.iterdir(), key=lambda item: item.name):
        spec_file = spec / "spec.md"
        if spec_file.exists():
            return _read_text(spec_file, max_chars=1_500)
    return None


def _nested_dict(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = parse_simple_yaml(path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_text(path: Path, *, max_chars: int) -> str | None:
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n[truncated]"
    return text


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _slug_suffix(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (normalized or "run")[:12]


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_if_missing(path: Path, content: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _domain_metadata(context: DomainFactoryContext, spec_id: str) -> str:
    now = _now_iso()
    return f"""id: {spec_id}
title: Domain Factory Implementation
status: draft
owner: domain-factory
created_at: {now}
updated_at: {now}
source_app: {context.source_app or ""}
workspace_path: {context.workspace_path}
baseline_commit: {context.baseline_commit or ""}
lifecycle_status: intake
"""


def _domain_spec(context: DomainFactoryContext) -> str:
    return f"""# Domain Factory Implementation

## Intent

Implement the real business/domain layer on top of the initialized baseline for `{context.source_app or context.workspace_name}`.

Domain Factory is project-scoped. It must not create a new project, recreate deterministic init, replace preview infrastructure, or switch to mock/demo data unless explicitly requested.

## Baseline

- Workspace: `{context.workspace_path}`
- Baseline commit: `{context.baseline_commit or "unknown"}`
- Preview URL: `{context.preview_url or "unknown"}`
- Preview API: `{context.api_url or "unknown"}`
- Runtime profile: `{context.runtime_profile or "unknown"}`
- API runtime: `{context.api_runtime or "unknown"}`

## Domain Contract Status

Pending user domain brief and follow-up intake.

The intake contract is stored in `intake/domain-intake-contract.json`. It
contains the only allowed follow-up fields, baseline setup fields to avoid,
owner/admin all-access role rules, and the release guardrails required before
implementation can claim readiness.

## Guardrails

- Preserve generic auth, RBAC, admin shell, Bridge, Workbench, updater, preview runtime, and initial project identity.
- Add domain roles and explicit permissions as required by the business.
- Owner/admin retain access to all domain capabilities.
- Require SDD evidence and a new real preview release before readiness.
"""


def _domain_plan() -> str:
    return """# Plan

## Plan 1: Domain Intake And Contract

Status: pending

Collect domain brief, references, roles, entities, workflows, visual direction, and release acceptance criteria.

Read `intake/domain-intake-contract.json` before asking follow-up questions.
Ask only for missing domain decisions and include recommended/default/inferred options.

## Plan 2: Domain Implementation

Status: pending

Implement UI, navigation, backend domain model, persistence, admin modules, permissions, and tests while preserving baseline foundation.

Use owner/admin all-access as a fixed invariant. Generate domain roles with explicit permissions derived from the business brief.

## Plan 3: Evidence And Preview Release

Status: pending

Update SDD artifacts and diagrams, run validation, publish the next real preview release, smoke test, and record release evidence.

Do not overwrite build 1. Release evidence must include commit, tag, release URL, APK URL, SHA-256, preview URL, smoke results, Bridge registry payload, and rollback pointer.
"""


def _domain_tasks() -> str:
    return """# Tasks

- [ ] T001 Capture original domain brief and visual references.
- [ ] T002 Produce domain contract preview with roles, permissions, entities, workflows, screens, visual direction, backend scope, tests, and release target.
- [ ] T003 Implement domain roles and explicit permissions while preserving owner/admin all-access.
- [ ] T004 Implement domain UI, navigation, empty states, visual styling, and reference asset fidelity.
- [ ] T005 Implement domain backend behavior, persistence, migrations, admin modules, notifications, and integrations.
- [ ] T006 Update DER/ERD, class, sequence, component, and deployment diagrams.
- [ ] T007 Run relevant frontend/backend tests and preview smoke checks.
- [ ] T008 Publish a new real preview release after build 1 and record APK/updater/Bridge evidence.
"""


def _domain_traceability() -> str:
    return """spec_id: domain-factory
requirements:
  domain_intake:
    tasks: [T001, T002]
  domain_roles_permissions:
    tasks: [T003]
  visual_implementation:
    tasks: [T004]
  backend_domain:
    tasks: [T005]
  sdd_diagrams:
    tasks: [T006]
  validation_release:
    tasks: [T007, T008]
"""


def _domain_intake_contract_payload() -> dict[str, Any]:
    return {
        "kind": "codex.domainFactoryIntakeContract",
        "version": 1,
        "status": "pending_domain_brief",
        "intakeFields": list(DOMAIN_INTAKE_FIELDS),
        "baselineFieldsToAvoid": list(BASELINE_INTAKE_FIELDS_TO_AVOID),
        "followUpQuestions": list(DOMAIN_FOLLOW_UP_QUESTIONS),
        "contractPreviewRequiredBeforeImplementation": True,
        "contractPreviewSections": [
            "roles",
            "permissions",
            "entities",
            "relationships",
            "workflows",
            "visualDirection",
            "screensNavigation",
            "backendScope",
            "tests",
            "releaseTarget",
        ],
        "rolePermissionModel": DOMAIN_ROLE_PERMISSION_MODEL,
        "pairedWorkflow": {
            "afterIntakeReady": True,
            "generatorReviewerMode": "paired",
            "reviewerFeedbackBecomesNextGeneratorPrompt": True,
        },
        "mediaPersistence": {
            "status": "pending_user_attachments",
            "intakeDirectory": "intake/",
            "rule": "Persist original brief and media references in the domain spec intake directory before implementation.",
        },
        "completionRules": {
            "domainTasksRemainPendingUntil": [
                "implementation evidence exists",
                "validation evidence exists",
                "new preview release evidence exists",
            ]
        },
        "releaseGuardrails": DOMAIN_RELEASE_GUARDRAILS,
    }


def _domain_intake_template(context: DomainFactoryContext) -> str:
    return f"""# Domain Factory Intake

Session: `{context.session_id}`
Workspace: `{context.workspace_path}`
Source app: `{context.source_app or "unknown"}`

Paste or attach the original business brief in the chat. Domain Factory intake should collect only domain/product information and must avoid baseline setup questions.
"""
