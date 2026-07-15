from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from typing import Any, Literal

from backend.app.application.services.message_service import BackendDrainStatus


EnvironmentName = Literal["prod", "dev", "control"]


_CAPABILITIES: dict[str, list[str]] = {
    "prod_normal": ["chat", "read_current_session", "enqueue_dev_handoff"],
    "prod_slash": ["read_selected_context", "enqueue_dev_handoff"],
    "dev_stage": [
        "read_stage_worktree",
        "write_stage_worktree",
        "run_stage_agents",
        "stage_backend_lifecycle",
    ],
    "dev_integration": ["merge_stage_to_dev_main", "run_integration_validation"],
    "prod_promotion": ["request_promotion", "approve_promotion", "drain_prod"],
}

_DENIED: dict[str, list[str]] = {
    "prod_normal": [
        "write_bridge_code",
        "run_shell",
        "restart_backend",
        "deploy_release",
        "read_dev_worktrees",
        "run_dev_agents",
    ],
    "prod_slash": [
        "write_files",
        "run_shell",
        "restart_backend",
        "deploy_release",
        "start_dev_agents",
        "read_dev_worktrees",
    ],
    "dev_stage": [
        "write_other_stage_worktrees",
        "restart_prod_backend",
        "promote_to_prod",
    ],
    "dev_integration": ["restart_prod_backend", "deploy_prod_release"],
    "prod_promotion": ["ad_hoc_shell", "ad_hoc_git", "skip_approval", "skip_drain"],
}

_STATE_VERSION = 1
_SPEC_ID_PATTERN = re.compile(r"^\d{3}-[a-z0-9][a-z0-9-]*$")
_STAGE_ID_PATTERN = re.compile(r"^spec-\d{3}$")


class DevPipelineError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class EnvironmentIdentity:
    environment: EnvironmentName
    mode: str
    stage_id: str | None
    spec_id: str | None
    branch: str | None
    worktree_path: str | None
    backend_url: str
    app_channel: str
    app_label: str
    updater_channel: str
    color: str
    allowed_capabilities: list[str]
    denied_capabilities: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "codex.bridgeEnvironmentIdentity",
            "version": 1,
            "environment": self.environment,
            "mode": self.mode,
            "stage_id": self.stage_id,
            "spec_id": self.spec_id,
            "branch": self.branch,
            "worktree_path": self.worktree_path,
            "backend_url": self.backend_url,
            "app_channel": self.app_channel,
            "app_label": self.app_label,
            "updater_channel": self.updater_channel,
            "color": self.color,
            "allowed_capabilities": self.allowed_capabilities,
            "denied_capabilities": self.denied_capabilities,
            "release_policy": {
                "mock_or_demo_default": False,
                "release_builds_require_real_backend": True,
            },
        }


class DevPipelineService:
    def __init__(
        self,
        *,
        state_path: str,
        runtime_root: str,
        repository_root: str,
        environment: EnvironmentName,
        backend_url: str,
        app_channel: str,
        app_label: str,
        updater_channel: str,
        color: str,
        stage_id: str | None = None,
        spec_id: str | None = None,
        branch: str | None = None,
        worktree_path: str | None = None,
        dev_main_branch: str = "dev/main",
        enabled: bool = True,
        prod_handoff_enabled: bool = False,
        promotion_enabled: bool = False,
        app_update_registry_path: str | None = None,
        app_update_public_base_url: str | None = None,
        app_update_github_token_present: bool = False,
        prod_update_executor_enabled: bool = False,
    ) -> None:
        self._state_path = Path(state_path)
        self._runtime_root = Path(runtime_root)
        self._repository_root = Path(repository_root)
        self._environment = environment
        self._backend_url = backend_url
        self._app_channel = app_channel
        self._app_label = app_label
        self._updater_channel = updater_channel
        self._color = color
        self._stage_id = stage_id
        self._spec_id = spec_id
        self._branch = branch
        self._worktree_path = worktree_path
        self._dev_main_branch = dev_main_branch
        self._enabled = enabled
        self._prod_handoff_enabled = prod_handoff_enabled
        self._promotion_enabled = promotion_enabled
        self._app_update_registry_path = app_update_registry_path
        self._app_update_public_base_url = app_update_public_base_url
        self._app_update_github_token_present = app_update_github_token_present
        self._prod_update_executor_enabled = prod_update_executor_enabled

    def identity(self) -> EnvironmentIdentity:
        mode = "normal"
        if self._environment == "dev" and self._stage_id:
            mode = "stage"
        elif self._environment == "control":
            mode = "control"
        capability_key = {
            "prod": "prod_normal",
            "dev": "dev_stage" if mode == "stage" else "dev_integration",
            "control": "prod_promotion",
        }[self._environment]
        return EnvironmentIdentity(
            environment=self._environment,
            mode=mode,
            stage_id=self._stage_id,
            spec_id=self._spec_id,
            branch=self._branch,
            worktree_path=self._worktree_path,
            backend_url=self._backend_url,
            app_channel=self._app_channel,
            app_label=self._app_label,
            updater_channel=self._updater_channel,
            color=self._color,
            allowed_capabilities=self._allowed_capabilities(capability_key),
            denied_capabilities=self._denied_capabilities(capability_key),
        )

    def permission_matrix(self) -> dict[str, Any]:
        if self._environment == "prod":
            allowed_modes = ["prod_normal"]
            if self._prod_handoff_enabled:
                allowed_modes.append("prod_slash")
        elif self._environment == "dev":
            allowed_modes = ["dev_stage", "dev_integration"]
        else:
            allowed_modes = ["prod_promotion"]
        return {
            "kind": "codex.devPipelinePermissionMatrix",
            "version": 1,
            "modes": {
                key: {
                    "allowed_capabilities": self._allowed_capabilities(key),
                    "denied_capabilities": self._denied_capabilities(key),
                }
                for key in allowed_modes
            },
            "rules": [
                "prod_normal_can_enqueue_only",
                "dev_stage_is_bound_to_one_stage_worktree",
                "dev_main_integration_is_serialized",
                "promotion_requires_deterministic_tooling",
                "prod_backend_update_requires_quiescence",
            ],
        }

    def identity_payload(self) -> dict[str, Any]:
        payload = self.identity().to_dict()
        if self._environment == "dev" and self._stage_id:
            state = self._read_state()
            stage = state["stages"].get(self._stage_id)
            if stage and stage.get("runtime"):
                payload["stage_runtime"] = stage["runtime"]
        return payload

    def snapshot(self) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("dev")
        state = self._read_state()
        return {
            "kind": "codex.devPipelineSnapshot",
            "version": 1,
            "enabled": self._enabled,
            "prod_handoff_enabled": self._prod_handoff_enabled,
            "promotion_enabled": self._promotion_enabled,
            "identity": self.identity().to_dict(),
            "handoffs": list(state["handoffs"].values()),
            "backlog": list(state["backlog"].values()),
            "specs": list(state["specs"].values()),
            "stages": list(state["stages"].values()),
            "sessions": list(state["sessions"].values()),
            "runs": list(state["runs"].values()),
            "merge_queue": list(state["merge_queue"].values()),
            "promotions": list(state["promotions"].values()),
            "release_validations": list(state["release_validations"].values()),
            "prod_updates": list(state["prod_updates"].values()),
            "events": state["events"][-200:],
        }

    def pipeline_projection(
        self,
        *,
        stage_id: str | None = None,
        spec_id: str | None = None,
        handoff_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        self._require_enabled()
        self._require_dev_or_control_environment()
        state = self._read_state()
        filters = {
            "stage_id": stage_id,
            "spec_id": spec_id,
            "handoff_id": handoff_id,
            "status": status,
        }
        backlog = self._filtered_items(state["backlog"].values(), filters)
        specs = self._filtered_items(state["specs"].values(), filters)
        stages = self._filtered_items(state["stages"].values(), filters)
        sessions = self._filtered_items(state["sessions"].values(), filters)
        runs = self._filtered_items(state["runs"].values(), filters)
        merges = self._filtered_items(state["merge_queue"].values(), filters)
        promotions = self._filtered_items(state["promotions"].values(), filters)
        release_validations = self._filtered_items(
            state["release_validations"].values(), filters
        )
        prod_updates = self._filtered_items(state["prod_updates"].values(), filters)
        events = self._filtered_items(state["events"], filters)[-200:]
        return {
            "kind": "codex.devPipelineProjection",
            "version": 1,
            "identity": self.identity().to_dict(),
            "filters": {key: value for key, value in filters.items() if value},
            "backlog": backlog,
            "specs": specs,
            "stages": stages,
            "sessions": sessions,
            "runs": runs,
            "merge_queue": merges,
            "promotions": promotions,
            "release_validations": release_validations,
            "prod_updates": prod_updates,
            "events": events,
            "workbench": self._workbench_projection(
                backlog=backlog,
                specs=specs,
                stages=stages,
                runs=runs,
                merges=merges,
                promotions=promotions,
            ),
        }

    def backfill_stage_candidates(
        self,
        *,
        dry_run: bool = True,
        spec_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        self._require_enabled()
        self._require_dev_or_control_environment()
        if not dry_run:
            raise DevPipelineError(
                "backfill_apply_not_supported",
                "Backfill currently supports dry-run candidate detection only.",
            )
        requested = {self._validate_spec_id(spec_id) for spec_id in spec_ids or []}
        specs_root = self._repository_root / "specs"
        candidates: list[dict[str, Any]] = []
        if specs_root.exists():
            for spec_path in sorted(specs_root.iterdir()):
                if not spec_path.is_dir():
                    continue
                spec_id = spec_path.name
                if requested and spec_id not in requested:
                    continue
                try:
                    self._validate_spec_id(spec_id)
                except DevPipelineError:
                    continue
                candidates.append(self._backfill_candidate(spec_id=spec_id))
        missing_requested = sorted(
            spec_id for spec_id in requested if spec_id not in {c["spec_id"] for c in candidates}
        )
        return {
            "kind": "codex.devPipelineBackfillDryRun",
            "version": 1,
            "dry_run": True,
            "repository_root": str(self._repository_root),
            "candidates": candidates,
            "missing_requested_specs": missing_requested,
            "summary": {
                "total": len(candidates),
                "ready": sum(1 for item in candidates if item["status"] == "ready"),
                "blocked": sum(
                    1 for item in candidates if item["status"] == "blocked"
                ),
            },
        }

    def enqueue_handoff(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None,
        selected_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("prod")
        if not self._prod_handoff_enabled:
            raise DevPipelineError(
                "prod_handoff_disabled",
                "PROD handoff is disabled by rollout flag.",
            )
        payload = dict(payload)
        draft_token = str(payload.pop("draft_token", "") or "").strip()
        self._validate_handoff_payload(payload)
        idem = (idempotency_key or payload.get("idempotency_key") or "").strip()
        if not idem:
            idem = self._stable_hash(payload)
        payload_hash = self._handoff_payload_hash(payload)
        state = self._read_state()
        for item in state["handoffs"].values():
            if item["idempotency_key"] == idem:
                existing_hash = item.get("payload_hash") or self._handoff_payload_hash(
                    item.get("payload") or {}
                )
                if existing_hash != payload_hash:
                    raise DevPipelineError(
                        "idempotency_conflict",
                        "Idempotency key was already used with a different handoff payload.",
                    )
                return item
        if self._requires_draft_grant(payload):
            self._consume_handoff_draft_grant(
                state,
                draft_token=draft_token,
                payload_hash=payload_hash,
                session_id=str(payload.get("created_from_session_id") or "").strip()
                or None,
            )
        now = _utc_iso()
        handoff_id = f"handoff-{now.replace(':', '').replace('-', '')}-{idem[:12]}"
        item = {
            "id": handoff_id,
            "kind": "bridge.devHandoff",
            "version": 1,
            "status": "queued",
            "immutable": True,
            "idempotency_key": idem,
            "payload_hash": payload_hash,
            "source_environment": "prod",
            "target_environment": "dev",
            "operation": "enqueue_only",
            "title": payload["title"].strip(),
            "problem": payload["problem"].strip(),
            "payload": payload,
            "created_at": now,
            "updated_at": now,
        }
        state["handoffs"][handoff_id] = item
        state["backlog"][handoff_id] = {
            "id": handoff_id,
            "handoff_id": handoff_id,
            "status": "queued",
            "attempts": 0,
            "locked_by": None,
            "locked_at": None,
            "spec_id": payload.get("proposed_spec"),
            "stage_id": None,
            "branch": None,
            "worktree_path": None,
            "spec_path": None,
            "blocker_reason": None,
            "blocker_detail": None,
            "materialize_attempts": 0,
            "materialized_by": None,
            "materialized_at": None,
            "created_at": now,
            "updated_at": now,
        }
        state["events"].append(
            {
                "type": "handoff.enqueued",
                "created_at": now,
                "handoff_id": handoff_id,
                "source_session_id": payload.get("created_from_session_id"),
                "selected_context": self._redact_context(
                    {
                        **(selected_context or {}),
                        "context": payload.get("context"),
                    }
                ),
                "evidence": self._redact_context(payload.get("evidence") or []),
            }
        )
        self._write_state(state)
        return item

    def draft_handoff(
        self,
        *,
        session_id: str | None,
        session_title: str | None,
        workspace_path: str | None,
        messages: list[dict[str, Any]],
        title: str | None = None,
        problem: str | None = None,
        context: str | None = None,
        acceptance_criteria: str | None = None,
    ) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("prod")
        if not self._prod_handoff_enabled:
            raise DevPipelineError(
                "prod_handoff_disabled",
                "PROD handoff is disabled by rollout flag.",
            )
        recent_messages = messages[-12:]
        derived_title = self._derive_handoff_title(title, recent_messages)
        derived_problem = self._derive_handoff_problem(problem, recent_messages)
        derived_context = self._derive_handoff_context(
            context,
            session_id=session_id,
            session_title=session_title,
            workspace_path=workspace_path,
            messages=recent_messages,
        )
        derived_acceptance = self._derive_handoff_acceptance(
            acceptance_criteria,
            derived_title,
        )
        slug = self._slugify(derived_title or "dev-handoff")
        proposed_spec = self._next_proposed_spec_id(slug)
        draft_token = secrets.token_urlsafe(32)
        token_hash = self._stable_hash({"draft_token": draft_token})
        now = _utc_iso()
        expires_at = (
            datetime.now(timezone.utc) + timedelta(hours=2)
        ).isoformat().replace("+00:00", "Z")
        state = self._read_state()
        state["handoff_drafts"][token_hash] = {
            "kind": "bridge.devHandoffDraftGrant",
            "version": 1,
            "status": "active",
            "source_environment": "prod",
            "target_environment": "dev",
            "session_id": session_id,
            "created_at": now,
            "expires_at": expires_at,
            "consumed_at": None,
            "payload_hash": None,
        }
        state["events"].append(
            {
                "type": "handoff.draft_created",
                "created_at": now,
                "source_session_id": session_id,
                "expires_at": expires_at,
            }
        )
        self._write_state(state)
        return {
            "kind": "bridge.devHandoff",
            "version": 1,
            "source_environment": "prod",
            "target_environment": "dev",
            "operation": "enqueue_only",
            "title": derived_title,
            "problem": derived_problem,
            "context": derived_context,
            "selected_context": {
                **({"session_id": session_id} if session_id else {}),
                "source": "mobile_chat",
                "context": derived_context,
            },
            "evidence": [],
            "proposed_spec": proposed_spec,
            "proposed_plan": f"01-{slug[:80]}",
            "proposed_tasks": [
                "Confirm the PROD chat context and acceptance criteria in the DEV stage.",
                "Implement the isolated repository/runtime changes in the DEV worktree only.",
                "Run targeted backend and mobile regression tests for the handoff flow.",
                "Report materialization, validation results, and any promotion blockers.",
            ],
            "acceptance_criteria": derived_acceptance,
            "regression_tests": [
                "Backend tests cover draft creation, one-shot grant consumption, and mobile enqueue rejection without a grant.",
                "Flutter tests cover the prefilled /dev-handoff review dialog and queued payload.",
            ],
            "risks": [
                "Accidentally allowing PROD to mutate bridge code outside the DEV queue.",
                "Materializing a spec ID that collides with existing DEV work.",
            ],
            "created_from_session_id": session_id,
            "created_by_action": "mobile_dev_handoff",
            "draft_token": draft_token,
        }

    def claim_backlog_item(self, *, worker_id: str) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("dev")
        worker_id = worker_id.strip()
        if not worker_id:
            raise DevPipelineError("invalid_worker_id", "worker_id is required.")
        state = self._read_state()
        now = _utc_iso()
        for item in state["backlog"].values():
            if item["status"] == "queued":
                item["status"] = "claimed"
                item["attempts"] += 1
                item["locked_by"] = worker_id
                item["locked_at"] = now
                item["updated_at"] = now
                state["events"].append(
                    {
                        "type": "backlog.claimed",
                        "created_at": now,
                        "handoff_id": item["handoff_id"],
                        "worker_id": worker_id,
                    }
                )
                self._write_state(state)
                return item
            if item["status"] in {"claimed", "materializing"}:
                continue
        raise DevPipelineError(
            "no_claimable_backlog", "No queued handoff is claimable."
        )

    def materialize_backlog_item(
        self,
        *,
        handoff_id: str,
        worker_id: str,
    ) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("dev")
        handoff_id = handoff_id.strip()
        worker_id = worker_id.strip()
        if not handoff_id:
            raise DevPipelineError("invalid_handoff_id", "handoff_id is required.")
        if not worker_id:
            raise DevPipelineError("invalid_worker_id", "worker_id is required.")
        state = self._read_state()
        item = state["backlog"].get(handoff_id)
        if not item:
            raise DevPipelineError(
                "unknown_backlog_item", f"Backlog item {handoff_id} was not found."
            )
        handoff = state["handoffs"].get(handoff_id)
        if not handoff:
            raise DevPipelineError(
                "unknown_handoff", f"Handoff {handoff_id} was not found."
            )
        if item.get("status") == "materialized":
            if item.get("materialized_by") not in {None, worker_id}:
                raise DevPipelineError(
                    "handoff_materialized_by_other_worker",
                    "This handoff was materialized by another worker.",
                )
            return self._materialize_response(item, handoff, state)
        if item.get("status") in {"cancelled"}:
            raise DevPipelineError(
                "backlog_item_cancelled", "Cancelled backlog items cannot materialize."
            )
        if item.get("locked_by") != worker_id:
            raise DevPipelineError(
                "backlog_lock_mismatch",
                "Backlog item must be claimed by the materializing worker.",
            )
        if item.get("status") not in {"claimed", "materializing", "blocked"}:
            raise DevPipelineError(
                "invalid_backlog_state",
                "Backlog item must be claimed before materialization.",
            )

        now = _utc_iso()
        item["status"] = "materializing"
        item["locked_by"] = worker_id
        item["locked_at"] = item.get("locked_at") or now
        item["materialize_attempts"] = int(item.get("materialize_attempts") or 0) + 1
        item["updated_at"] = now
        state["events"].append(
            {
                "type": "backlog.materializing",
                "created_at": now,
                "handoff_id": handoff_id,
                "worker_id": worker_id,
                "attempt": item["materialize_attempts"],
            }
        )

        payload = handoff.get("payload") or {}
        spec_id = str(payload.get("proposed_spec") or "").strip()
        try:
            spec_id = self._validate_spec_id(spec_id)
        except DevPipelineError:
            return self._block_materialization(
                state=state,
                item=item,
                handoff_id=handoff_id,
                worker_id=worker_id,
                reason="invalid_or_missing_proposed_spec",
                detail="proposed_spec must look like 018-dev-prod-stage-promotion-pipeline.",
            )

        number = spec_id.split("-", 1)[0]
        stage_id = f"spec-{number}"
        branch = self._stage_branch(spec_id=spec_id, stage_id=stage_id)
        worktree_path = str(
            (
                self._repository_root.parent
                / f"{self._repository_root.name}-{stage_id}"
            )
            .expanduser()
            .resolve()
        )
        spec_exists_in_base = (self._repository_root / "specs" / spec_id).is_dir()
        worktree_existed_before = Path(worktree_path).exists()
        partial_artifacts: list[dict[str, str]] = []

        blocker = self._materialization_git_blocker(
            spec_id=spec_id,
            branch=branch,
            worktree_path=worktree_path,
        )
        if blocker:
            return self._block_materialization(
                state=state,
                item=item,
                handoff_id=handoff_id,
                worker_id=worker_id,
                reason=blocker["reason"],
                detail=blocker["detail"],
            )
        if not worktree_existed_before and Path(worktree_path).exists():
            partial_artifacts.append({"kind": "git_worktree", "path": worktree_path})

        worktree_spec_dir = Path(worktree_path) / "specs" / spec_id
        if spec_exists_in_base:
            if not worktree_spec_dir.is_dir():
                return self._block_materialization(
                    state=state,
                    item=item,
                    handoff_id=handoff_id,
                    worker_id=worker_id,
                    reason="spec_missing_in_worktree",
                    detail=f"Expected existing spec in {worktree_spec_dir}.",
                    partial_artifacts=partial_artifacts,
                )
            spec_mode = "attached"
        else:
            if worktree_spec_dir.exists() and any(worktree_spec_dir.iterdir()):
                return self._block_materialization(
                    state=state,
                    item=item,
                    handoff_id=handoff_id,
                    worker_id=worker_id,
                    reason="spec_path_incompatible",
                    detail=f"Spec path already exists with unexpected content: {worktree_spec_dir}.",
                    partial_artifacts=partial_artifacts,
                )
            try:
                skeleton_paths = self._write_sdd_skeleton(worktree_spec_dir, payload)
            except OSError as exc:
                return self._block_materialization(
                    state=state,
                    item=item,
                    handoff_id=handoff_id,
                    worker_id=worker_id,
                    reason="skeleton_write_failed",
                    detail=str(exc),
                    partial_artifacts=partial_artifacts,
                )
            partial_artifacts.extend(
                {"kind": "sdd_skeleton_file", "path": path}
                for path in skeleton_paths
            )
            spec_mode = "created"

        try:
            stage = self._upsert_materialized_stage(
                state=state,
                spec_id=spec_id,
                stage_id=stage_id,
                branch=branch,
                worktree_path=worktree_path,
                owner=worker_id,
            )
        except DevPipelineError as exc:
            return self._block_materialization(
                state=state,
                item=item,
                handoff_id=handoff_id,
                worker_id=worker_id,
                reason=exc.code,
                detail=exc.message,
                partial_artifacts=partial_artifacts,
            )
        state["specs"][spec_id] = {
            "spec_id": spec_id,
            "path": str(worktree_spec_dir),
            "status": spec_mode,
            "handoff_id": handoff_id,
            "stage_id": stage_id,
            "branch": branch,
            "worktree_path": worktree_path,
            "updated_at": now,
        }
        item.update(
            {
                "status": "materialized",
                "blocker_reason": None,
                "blocker_detail": None,
                "partial_artifacts": [],
                "spec_id": spec_id,
                "spec_path": str(worktree_spec_dir),
                "stage_id": stage_id,
                "branch": branch,
                "worktree_path": worktree_path,
                "materialized_by": worker_id,
                "materialized_at": now,
                "updated_at": now,
            }
        )
        handoff.update(
            {
                "status": "materialized",
                "spec_id": spec_id,
                "stage_id": stage_id,
                "branch": branch,
                "worktree_path": worktree_path,
                "updated_at": now,
            }
        )
        state["events"].append(
            {
                "type": "backlog.materialized",
                "created_at": now,
                "handoff_id": handoff_id,
                "worker_id": worker_id,
                "spec_id": spec_id,
                "stage_id": stage_id,
                "branch": branch,
                "worktree_path": worktree_path,
                "spec_mode": spec_mode,
            }
        )
        self._write_state(state)
        response = self._materialize_response(item, handoff, state)
        response["stage"] = stage
        response["spec"] = state["specs"][spec_id]
        return response

    def register_stage(
        self,
        *,
        spec_id: str,
        stage_id: str | None = None,
        branch: str | None = None,
        worktree_path: str | None = None,
        backend_url: str | None = None,
        owner: str | None = None,
    ) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("dev")
        spec_id = self._validate_spec_id(spec_id)
        number = spec_id.split("-", 1)[0]
        resolved_stage_id = stage_id or f"spec-{number}"
        if not _STAGE_ID_PATTERN.match(resolved_stage_id):
            raise DevPipelineError(
                "invalid_stage_id", "stage_id must look like spec-018."
            )
        expected_branch = self._stage_branch(
            spec_id=spec_id,
            stage_id=resolved_stage_id,
        )
        resolved_branch = branch or expected_branch
        if resolved_branch != expected_branch:
            raise DevPipelineError(
                "stage_branch_invalid",
                f"Stage branch must be {expected_branch}.",
            )
        resolved_worktree = worktree_path or str(
            self._repository_root.parent
            / f"{self._repository_root.name}-{resolved_stage_id}"
        )
        resolved_worktree = self._validate_stage_worktree_path(
            stage_id=resolved_stage_id,
            worktree_path=resolved_worktree,
        )
        port = self.allocate_stage_port(resolved_stage_id)
        resolved_backend_url = backend_url or f"http://127.0.0.1:{port}"
        now = _utc_iso()
        runtime = self._runtime_record(resolved_stage_id, port, resolved_backend_url)
        stage = {
            "stage_id": resolved_stage_id,
            "environment": "dev",
            "spec_id": spec_id,
            "branch": resolved_branch,
            "base_branch": self._dev_main_branch,
            "worktree_path": resolved_worktree,
            "backend_url": resolved_backend_url,
            "app_channel": "dev",
            "status": "active",
            "owner": owner,
            "runtime": runtime,
            "created_at": now,
            "updated_at": now,
        }
        state = self._read_state()
        existing = state["stages"].get(resolved_stage_id)
        if existing:
            immutable_fields = ["spec_id", "branch", "worktree_path"]
            mismatches = [
                field
                for field in immutable_fields
                if existing.get(field) != stage.get(field)
            ]
            if mismatches:
                raise DevPipelineError(
                    "stage_identity_mismatch",
                    f"Registered stage differs in immutable fields: {', '.join(mismatches)}.",
                )
            existing.update(
                {
                    "backend_url": resolved_backend_url,
                    "runtime": runtime,
                    "updated_at": now,
                    "status": existing.get("status") or "active",
                }
            )
            stage = existing
        else:
            state["stages"][resolved_stage_id] = stage
        state["events"].append(
            {
                "type": "stage.registered",
                "created_at": now,
                "stage_id": resolved_stage_id,
                "spec_id": spec_id,
            }
        )
        self._write_state(state)
        return stage

    def bind_session(
        self,
        *,
        session_id: str,
        stage_id: str,
        workspace_path: str,
        branch: str,
    ) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("dev")
        state = self._read_state()
        stage = self._require_stage(state, stage_id)
        if Path(workspace_path).resolve() != Path(stage["worktree_path"]).resolve():
            raise DevPipelineError(
                "stage_worktree_mismatch",
                "workspace_path is not the registered stage worktree.",
            )
        if branch != stage["branch"]:
            raise DevPipelineError(
                "stage_branch_mismatch", "branch is not the registered stage branch."
            )
        existing = state["sessions"].get(session_id)
        if existing and existing["stage_id"] != stage_id:
            raise DevPipelineError(
                "session_stage_mismatch", "Session is already bound to another stage."
            )
        now = _utc_iso()
        binding = {
            "session_id": session_id,
            "stage_id": stage_id,
            "spec_id": stage["spec_id"],
            "branch": branch,
            "worktree_path": workspace_path,
            "backend_url": stage["backend_url"],
            "created_at": existing["created_at"] if existing else now,
            "updated_at": now,
        }
        state["sessions"][session_id] = binding
        state["events"].append(
            {
                "type": "session.bound",
                "created_at": now,
                "session_id": session_id,
                "stage_id": stage_id,
            }
        )
        self._write_state(state)
        return binding

    def get_stage(self, stage_id: str) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("dev")
        state = self._read_state()
        return self._require_stage(state, stage_id)

    def bind_stage_session(
        self,
        *,
        session_id: str,
        stage_id: str,
    ) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("dev")
        session_id = session_id.strip()
        if not session_id:
            raise DevPipelineError("invalid_session_id", "session_id is required.")
        state = self._read_state()
        stage = self._require_stage(state, stage_id)
        if stage.get("status") != "active":
            raise DevPipelineError("stage_not_active", "Stage must be active.")
        return self._bind_stage_session_in_state(
            state=state,
            session_id=session_id,
            stage=stage,
        )

    def get_stage_session_binding(self, *, session_id: str) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("dev")
        state = self._read_state()
        binding = state["sessions"].get(session_id)
        if not binding:
            raise DevPipelineError(
                "unknown_stage_session_binding",
                f"Session {session_id} is not bound to a DEV stage.",
            )
        return binding

    def validate_stage_session_execution(
        self,
        *,
        session_id: str,
        workspace_path: str | None,
        backend_url: str,
    ) -> None:
        state = self._read_state()
        binding = state["sessions"].get(session_id)
        if not binding:
            return
        self._require_enabled()
        self._require_environment("dev")
        expected_workspace = Path(binding["worktree_path"]).resolve()
        requested_workspace = (
            Path(workspace_path).expanduser().resolve()
            if workspace_path
            else expected_workspace
        )
        if requested_workspace != expected_workspace:
            raise DevPipelineError(
                "stage_workspace_mismatch",
                "Stage-bound sessions can only run in their stage worktree.",
            )
        if backend_url.rstrip("/") != str(binding["backend_url"]).rstrip("/"):
            raise DevPipelineError(
                "stage_backend_url_mismatch",
                "Stage-bound sessions can only run against their stage backend.",
            )
        branch = self._git_run(
            expected_workspace,
            ["rev-parse", "--abbrev-ref", "HEAD"],
        )
        if branch.returncode != 0 or branch.stdout.strip() != binding["branch"]:
            raise DevPipelineError(
                "stage_branch_mismatch",
                "Stage-bound sessions can only run on their stage branch.",
            )

    def prepare_stage_run_start(
        self,
        *,
        stage_id: str,
        session_id: str,
        backend_url: str,
        initial_prompt: str | None = None,
    ) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("dev")
        state = self._read_state()
        stage = self._require_stage(state, stage_id)
        if stage.get("status") != "active":
            raise DevPipelineError("stage_not_active", "Stage must be active.")
        binding = state["sessions"].get(session_id)
        if not binding or binding["stage_id"] != stage_id:
            raise DevPipelineError(
                "stage_session_binding_required",
                "Stage run requires a session bound to the target stage.",
            )
        self.validate_stage_session_execution(
            session_id=session_id,
            workspace_path=stage["worktree_path"],
            backend_url=backend_url,
        )
        for run in state["runs"].values():
            if (
                run.get("stage_id") == stage_id
                and run.get("session_id") == session_id
                and run.get("status") in {"queued", "running", "planned"}
            ):
                raise DevPipelineError(
                    "stage_run_active",
                    "A stage run is already active for this session and stage.",
                )
        prompt = (initial_prompt or "").strip() or self._default_stage_run_prompt(
            state=state,
            stage=stage,
        )
        return {"stage": stage, "binding": binding, "prompt": prompt}

    def record_stage_run_start(
        self,
        *,
        stage_id: str,
        session_id: str,
        requested_by: str,
        prompt: str,
        job_id: str | None,
        agent_run_id: str | None,
    ) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("dev")
        requested_by = requested_by.strip() or "dev-worker"
        state = self._read_state()
        stage = self._require_stage(state, stage_id)
        now = _utc_iso()
        run_id = f"stage-run-{stage_id}-{now.replace(':', '').replace('-', '')}"
        run = {
            "id": run_id,
            "stage_id": stage_id,
            "session_id": session_id,
            "spec_id": stage["spec_id"],
            "branch": stage["branch"],
            "worktree_path": stage["worktree_path"],
            "backend_url": stage["backend_url"],
            "status": "queued" if job_id else "planned",
            "control": "start",
            "requested_by": requested_by,
            "job_id": job_id,
            "agent_run_id": agent_run_id,
            "prompt": prompt,
            "preset": "DEV Stage Generator/Reviewer",
            "auto_chain": {
                "preset": "review",
                "generator": "enabled",
                "reviewer": "enabled",
                "reviewer_feedback_becomes_next_generator_prompt": True,
            },
            "evidence": {
                "changed_files": [],
                "tests_declared": [],
                "tests_executed": [],
                "reviewer": {
                    "completion": None,
                    "continue": None,
                    "status": "planned",
                },
                "risks": ["agent execution is not started by this control yet"],
                "final_summary": None,
            },
            "started_at": now if job_id else None,
            "finished_at": None,
            "created_at": now,
            "updated_at": now,
        }
        state["runs"][run_id] = run
        state["events"].append(
            {
                "type": "stage_run.planned",
                "created_at": now,
                "run_id": run_id,
                "stage_id": stage_id,
                "session_id": session_id,
            }
        )
        self._write_state(state)
        return run

    def update_stage_run_projection(
        self,
        *,
        run_id: str,
        projection: dict[str, Any],
    ) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("dev")
        state = self._read_state()
        run = state["runs"].get(run_id)
        if not run:
            raise DevPipelineError("unknown_stage_run", f"Run {run_id} was not found.")
        run.update(projection)
        run["updated_at"] = _utc_iso()
        state["runs"][run_id] = run
        self._write_state(state)
        return run

    def stage_run_status(self, *, run_id: str) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("dev")
        state = self._read_state()
        run = state["runs"].get(run_id)
        if not run:
            raise DevPipelineError("unknown_stage_run", f"Run {run_id} was not found.")
        return run

    def control_stage_run(
        self,
        *,
        run_id: str,
        action: Literal["cancel", "retry", "pause", "resume"],
        requested_by: str,
    ) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("dev")
        state = self._read_state()
        run = state["runs"].get(run_id)
        if not run:
            raise DevPipelineError("unknown_stage_run", f"Run {run_id} was not found.")
        now = _utc_iso()
        if action == "cancel":
            if run["status"] in {"completed", "cancelled"}:
                return run
            run["status"] = "cancelled"
            run["finished_at"] = now
        elif action == "retry":
            run["status"] = "planned"
            run["retry_requested_by"] = requested_by
            run["retry_requested_at"] = now
        elif action == "pause":
            if run["status"] in {"paused", "pause_requested"}:
                return run
            if run["status"] in {"completed", "cancelled", "failed"}:
                raise DevPipelineError(
                    "stage_run_terminal",
                    "Terminal stage runs cannot be paused.",
                )
            run["status"] = "pause_requested"
            run["pause_requested_by"] = requested_by
            run["pause_requested_at"] = now
            run["blocker_reason"] = "message_service_pause_not_supported"
            run["control_blockers"] = [
                "pause is recorded for operator coordination; MessageService has no real pause primitive"
            ]
        else:
            if run["status"] == "resume_requested":
                return run
            if run["status"] in {"queued", "running"}:
                return run
            if run["status"] not in {"pause_requested", "paused", "planned"}:
                raise DevPipelineError(
                    "stage_run_not_paused",
                    "Only paused or pause-requested stage runs can be resumed.",
                )
            run["status"] = "resume_requested"
            run["resume_requested_by"] = requested_by
            run["resume_requested_at"] = now
            run["blocker_reason"] = "message_service_resume_not_supported"
            run["control_blockers"] = [
                "resume is recorded for operator coordination; retry starts a new executable job"
            ]
        run["control"] = action
        run["updated_at"] = now
        state["events"].append(
            {
                "type": f"stage_run.{action}",
                "created_at": now,
                "run_id": run_id,
                "requested_by": requested_by,
            }
        )
        self._write_state(state)
        return run

    def _default_stage_run_prompt(
        self,
        *,
        state: dict[str, Any],
        stage: dict[str, Any],
    ) -> str:
        handoff_payload: dict[str, Any] = {}
        for backlog in state["backlog"].values():
            if backlog.get("stage_id") == stage["stage_id"]:
                handoff = state["handoffs"].get(backlog["handoff_id"]) or {}
                handoff_payload = handoff.get("payload") or {}
                break
        title = str(handoff_payload.get("title") or stage["spec_id"]).strip()
        problem = str(handoff_payload.get("problem") or "").strip()
        context = str(handoff_payload.get("context") or "").strip()
        acceptance = str(handoff_payload.get("acceptance_criteria") or "").strip()
        return "\n\n".join(
            part
            for part in [
                f"Implement DEV stage `{stage['stage_id']}` for spec `{stage['spec_id']}`.",
                f"Title: {title}",
                f"Problem: {problem}" if problem else "",
                f"Context: {context}" if context else "",
                f"Acceptance criteria: {acceptance}" if acceptance else "",
                f"Workspace: {stage['worktree_path']}",
                f"Branch: {stage['branch']}",
            ]
            if part
        )

    def stage_lifecycle(
        self,
        *,
        stage_id: str,
        action: Literal["start", "stop", "restart", "status", "logs", "healthcheck"],
        apply: bool = False,
    ) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("dev")
        state = self._read_state()
        stage = self._require_stage(state, stage_id)
        now = _utc_iso()
        runtime = dict(stage["runtime"])
        commands = self._stage_commands(stage, action)
        result = {
            "kind": "codex.stageLifecycleCommand",
            "version": 1,
            "stage_id": stage_id,
            "action": action,
            "status": "planned",
            "apply": apply,
            "command": commands[0] if commands else [],
            "commands": commands,
            "runtime": runtime,
            "created_at": now,
        }
        if apply and action in {"start", "stop", "restart"}:
            self._prepare_stage_runtime(stage)
            completed_runs = []
            for command in commands:
                completed_runs.append(
                    subprocess.run(
                        command,
                        cwd=stage["worktree_path"],
                        capture_output=True,
                        text=True,
                        timeout=120,
                        check=False,
                    )
                )
                if completed_runs[-1].returncode != 0:
                    break
            return_code = completed_runs[-1].returncode if completed_runs else 1
            result.update(
                {
                    "status": "completed" if return_code == 0 else "failed",
                    "return_code": return_code,
                    "stdout": "\n".join(run.stdout for run in completed_runs)[-4000:],
                    "stderr": "\n".join(run.stderr for run in completed_runs)[-4000:],
                }
            )
            runtime["last_restart_at"] = (
                now
                if action in {"start", "restart"}
                else runtime.get("last_restart_at")
            )
            runtime["health"] = (
                "running"
                if return_code == 0 and action in {"start", "restart"}
                else runtime.get("health", "unknown")
            )
            stage["runtime"] = runtime
            stage["updated_at"] = now
        elif action == "status":
            result["status"] = "reported"
            result["process"] = self._stage_process_status(runtime)
        elif action == "logs":
            result["status"] = "reported"
            result["logs_dir"] = runtime["logs_dir"]
            result["log_file"] = str(Path(runtime["logs_dir"]) / "backend.log")
        elif action == "healthcheck":
            health = self._stage_healthcheck(runtime)
            runtime["health"] = "healthy" if health["ok"] else "unhealthy"
            runtime["last_healthcheck_at"] = now
            runtime["last_healthcheck"] = health
            stage["runtime"] = runtime
            stage["updated_at"] = now
            result["status"] = "healthy" if health["ok"] else "unhealthy"
            result["healthcheck"] = health
            result["runtime"] = runtime
        state["events"].append(
            {
                "type": f"stage.{action}",
                "created_at": now,
                "stage_id": stage_id,
                "applied": apply,
                "status": result["status"],
            }
        )
        self._write_state(state)
        return result

    def queue_merge(
        self,
        *,
        stage_id: str,
        requested_by: str,
        approved: bool,
        evidence_validated: bool = False,
        validation_passed: bool | None = None,
        validation_log: str | None = None,
        tests_executed: list[str] | None = None,
    ) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("dev")
        state = self._read_state()
        stage = self._require_stage(state, stage_id)
        now = _utc_iso()
        evidence = self._merge_evidence(
            evidence_validated=evidence_validated,
            validation_passed=validation_passed,
            validation_log=validation_log,
            tests_executed=tests_executed,
        )
        preflight = self._merge_preflight(
            state=state,
            stage=stage,
            approved=approved,
            evidence=evidence,
        )
        merge_id = f"merge-{stage_id}-{now.replace(':', '').replace('-', '')}"
        item = {
            "id": merge_id,
            "stage_id": stage_id,
            "spec_id": stage["spec_id"],
            "source_branch": stage["branch"],
            "target_branch": self._dev_main_branch,
            "requested_by": requested_by,
            "approved": approved,
            "status": "queued" if preflight["ok"] else "blocked",
            "preflight": preflight,
            "blockers": preflight["blockers"],
            "remediation_hints": preflight["remediation_hints"],
            "evidence": evidence,
            "commit_ids": {},
            "partial_artifacts": [],
            "created_at": now,
            "updated_at": now,
        }
        state["merge_queue"][merge_id] = item
        state["events"].append(
            {
                "type": "merge.queued" if preflight["ok"] else "merge.blocked",
                "created_at": now,
                "merge_id": merge_id,
                "stage_id": stage_id,
            }
        )
        self._write_state(state)
        return item

    def merge_status(self, *, merge_id: str) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("dev")
        state = self._read_state()
        item = state["merge_queue"].get(merge_id)
        if not item:
            raise DevPipelineError("unknown_merge", f"Merge {merge_id} was not found.")
        return item

    def apply_merge(
        self,
        *,
        merge_id: str,
        requested_by: str,
        evidence_validated: bool = False,
        validation_passed: bool | None = None,
        validation_log: str | None = None,
        tests_executed: list[str] | None = None,
    ) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("dev")
        state = self._read_state()
        item = state["merge_queue"].get(merge_id)
        if not item:
            raise DevPipelineError("unknown_merge", f"Merge {merge_id} was not found.")
        stage = self._require_stage(state, str(item["stage_id"]))
        evidence = self._merge_evidence(
            evidence_validated=bool(
                evidence_validated or item.get("evidence", {}).get("validated")
            ),
            validation_passed=(
                validation_passed
                if validation_passed is not None
                else item.get("evidence", {}).get("validation_passed")
            ),
            validation_log=validation_log or item.get("evidence", {}).get("validation_log"),
            tests_executed=[
                *list(item.get("evidence", {}).get("tests_executed") or []),
                *(tests_executed or []),
            ],
        )
        preflight = self._merge_preflight(
            state=state,
            stage=stage,
            approved=bool(item.get("approved")),
            evidence=evidence,
            current_merge_id=merge_id,
        )
        now = _utc_iso()
        item.update(
            {
                "evidence": evidence,
                "preflight": preflight,
                "blockers": preflight["blockers"],
                "remediation_hints": preflight["remediation_hints"],
                "updated_at": now,
                "apply_requested_by": requested_by,
            }
        )
        if not preflight["ok"]:
            item["status"] = "blocked"
            state["events"].append(
                {
                    "type": "merge.blocked",
                    "created_at": now,
                    "merge_id": merge_id,
                    "stage_id": stage["stage_id"],
                    "blockers": preflight["blockers"],
                }
            )
            self._write_state(state)
            return item

        doctor = self._run_merge_sdd_doctor()
        evidence["sdd_doctor"] = doctor
        item["evidence"] = evidence
        if not doctor["ok"]:
            item["status"] = "blocked"
            item["blockers"] = list(
                dict.fromkeys([*item.get("blockers", []), "sdd_doctor_failed"])
            )
            item["remediation_hints"] = list(
                dict.fromkeys(
                    [
                        *item.get("remediation_hints", []),
                        "Fix SDD doctor failures before applying the merge.",
                    ]
                )
            )
            item["updated_at"] = _utc_iso()
            state["merge_queue"][merge_id] = item
            state["events"].append(
                {
                    "type": "merge.blocked",
                    "created_at": item["updated_at"],
                    "merge_id": merge_id,
                    "stage_id": stage["stage_id"],
                    "blockers": item["blockers"],
                }
            )
            self._write_state(state)
            return item

        item["status"] = "applying"
        item["started_at"] = now
        state["events"].append(
            {
                "type": "merge.applying",
                "created_at": now,
                "merge_id": merge_id,
                "stage_id": stage["stage_id"],
            }
        )
        self._write_state(state)

        result = self._apply_git_merge(stage=stage, merge_id=merge_id)
        state = self._read_state()
        item = state["merge_queue"][merge_id]
        stage = self._require_stage(state, str(item["stage_id"]))
        now = _utc_iso()
        item.update(
            {
                **result,
                "evidence": self._merge_evidence_with_stage_state(
                    stage=stage,
                    evidence=evidence,
                ),
                "updated_at": now,
                "finished_at": now,
            }
        )
        if result["status"] == "merged":
            commit_sha = result["commit_ids"]["merge_commit"]
            stage["integration_status"] = "merged_to_dev_main"
            stage["dev_main_commit"] = commit_sha
            stage["merged_at"] = now
            stage["updated_at"] = now
            for backlog in state["backlog"].values():
                if backlog.get("stage_id") == stage["stage_id"]:
                    backlog["integration_status"] = "merged_to_dev_main"
                    backlog["dev_main_commit"] = commit_sha
                    backlog["updated_at"] = now
            spec = state["specs"].get(stage["spec_id"])
            if spec:
                spec["integration_status"] = "merged_to_dev_main"
                spec["dev_main_commit"] = commit_sha
                spec["updated_at"] = now
            event_type = "merge.merged"
        else:
            event_type = "merge.failed"
        state["events"].append(
            {
                "type": event_type,
                "created_at": now,
                "merge_id": merge_id,
                "stage_id": stage["stage_id"],
                "status": result["status"],
                "blockers": result.get("blockers", []),
            }
        )
        self._write_state(state)
        return item

    def request_promotion(
        self,
        *,
        requested_by: str,
        target: Literal["prod"],
        release_tag: str | None,
        user_approved: bool,
        dry_run: bool = True,
        drain_status: BackendDrainStatus,
    ) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("control")
        if not self._promotion_enabled:
            raise DevPipelineError(
                "promotion_disabled", "Promotion is disabled by rollout flag."
            )
        now = _utc_iso()
        plan = self._promotion_plan(
            target=target,
            release_tag=release_tag,
            user_approved=user_approved,
            dry_run=dry_run,
            drain_status=drain_status,
        )
        promotion_id = f"promotion-{now.replace(':', '').replace('-', '')}"
        item = {
            "kind": "codex.prodPromotionOrchestrator",
            "version": 1,
            "id": promotion_id,
            "state": plan["state"],
            "target": target,
            "requested_by": requested_by,
            "release_tag": release_tag,
            "dry_run": dry_run,
            "user_approved": user_approved,
            "steps": self._promotion_steps(),
            "transitions": ["requested", "preflight", "validation", plan["state"]],
            "blockers": plan["blockers"],
            "remediation_hints": plan["remediation_hints"],
            "evidence": plan["evidence"],
            "planned_commands": plan["planned_commands"],
            "rollback_hints": self._promotion_rollback_hints(),
            "next_required_action": plan["next_required_action"],
            "deployed": False,
            "release_published": False,
            "created_at": now,
            "updated_at": now,
        }
        state = self._read_state()
        state["promotions"][promotion_id] = item
        state["events"].append(
            {
                "type": "promotion.requested",
                "created_at": now,
                "promotion_id": promotion_id,
                "state": item["state"],
            }
        )
        self._write_state(state)
        return item

    def promotion_status(self, *, promotion_id: str) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("control")
        state = self._read_state()
        item = state["promotions"].get(promotion_id)
        if not item:
            raise DevPipelineError(
                "unknown_promotion", f"Promotion {promotion_id} was not found."
            )
        return item

    def advance_promotion(
        self,
        *,
        promotion_id: str,
        requested_by: str,
        user_approved: bool,
        dry_run: bool,
        drain_status: BackendDrainStatus,
    ) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("control")
        state = self._read_state()
        item = state["promotions"].get(promotion_id)
        if not item:
            raise DevPipelineError(
                "unknown_promotion", f"Promotion {promotion_id} was not found."
            )
        now = _utc_iso()
        if item.get("state") == "rollback_ready":
            item["next_required_action"] = "await_explicit_real_promotion_instruction"
            item["updated_at"] = now
            self._write_state(state)
            return item
        approved = bool(item.get("user_approved") or user_approved)
        item["user_approved"] = approved
        plan = self._promotion_plan(
            target=item.get("target") or "prod",
            release_tag=item.get("release_tag"),
            user_approved=approved,
            dry_run=dry_run,
            drain_status=drain_status,
        )
        next_state = plan["state"]
        if item.get("state") == "dry_run_passed" and plan["state"] == "dry_run_passed":
            next_state = "rollback_ready"
            plan["next_required_action"] = "await_explicit_real_promotion_instruction"
            plan["planned_commands"] = [
                *plan["planned_commands"],
                self._promotion_command(
                    name="android_release_workflow",
                    argv=["scripts/publish_android_release.sh"],
                    status="blocked_real_release",
                    reason="Real Android release publishing is disabled in dry-run.",
                ),
            ]
        item.update(
            {
                "state": next_state,
                "dry_run": dry_run,
                "blockers": plan["blockers"],
                "remediation_hints": plan["remediation_hints"],
                "evidence": plan["evidence"],
                "planned_commands": plan["planned_commands"],
                "next_required_action": plan["next_required_action"],
                "updated_at": now,
                "last_advanced_by": requested_by,
                "deployed": False,
                "release_published": False,
            }
        )
        item.setdefault("transitions", []).append(next_state)
        state["events"].append(
            {
                "type": "promotion.advanced",
                "created_at": now,
                "promotion_id": promotion_id,
                "state": next_state,
                "requested_by": requested_by,
            }
        )
        self._write_state(state)
        return item

    def prod_update_status(
        self,
        *,
        prepared_update_id: str | None,
        drain_status: BackendDrainStatus,
        force_requested: bool = False,
        acknowledged: bool = False,
        update_version: str | None = None,
        requested_by: str | None = None,
        strong_confirmation: str | None = None,
        execute: bool = False,
        executor_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_enabled()
        self._require_prod_update_environment()
        if self._environment != "control" and (prepared_update_id or force_requested):
            raise DevPipelineError(
                "control_environment_required",
                "Prepared updates and force requests must come from CONTROL.",
            )
        now = _utc_iso()
        state = self._read_state()
        update_id = prepared_update_id or self._latest_prod_update_id(state)
        existing = state["prod_updates"].get(update_id) if update_id else None
        if not update_id:
            item = self._prod_update_record(
                update_id=None,
                update_version=None,
                state_name="acknowledged" if acknowledged else "idle",
                drain_status=drain_status,
                now=now,
                requested_by=requested_by,
            )
            return item
        item = existing or self._prod_update_record(
            update_id=update_id,
            update_version=update_version,
            state_name="update_available",
            drain_status=drain_status,
            now=now,
            requested_by=requested_by,
        )
        item["prepared_update_id"] = update_id
        item["update_version"] = update_version or item.get("update_version")
        item["updated_at"] = now
        item["evidence"]["drain"] = self._prod_update_drain_snapshot(drain_status)

        blockers = self._prod_update_blockers(drain_status)
        if acknowledged:
            item["state"] = "acknowledged"
            item["notification"] = False
            item["acknowledgement"] = {
                "acknowledged_by": requested_by or "operator",
                "acknowledged_at": now,
            }
            item["next_required_action"] = "none"
        elif force_requested:
            if strong_confirmation != self._force_update_confirmation(update_id):
                item["state"] = "blocked"
                item["blockers"] = ["strong_confirmation_required"]
                item["next_required_action"] = (
                    f"type {self._force_update_confirmation(update_id)}"
                )
            else:
                item["state"] = "force_requested"
                item["notification"] = True
                item["blockers"] = blockers
                item["interruption_evidence"] = {
                    "requested_by": requested_by or "operator",
                    "requested_at": now,
                    "drain": self._prod_update_drain_snapshot(drain_status),
                    "recovery_summary": "Resume or retry interrupted sessions after update.",
                    "post_validation_plan": self._prod_update_post_validation_plan(),
                }
                item["next_required_action"] = "manual_update_executor_required"
        elif blockers:
            item["state"] = "waiting_for_idle"
            item["notification"] = True
            item["blockers"] = blockers
            item["next_required_action"] = "wait_for_idle"
        else:
            item["state"] = "auto_update_eligible"
            item["notification"] = True
            item["blockers"] = []
            item["next_required_action"] = "executor_disabled"
            item["executor"] = self._prod_update_executor_plan(
                update_id=update_id,
                execute=execute,
                executor_result=executor_result,
            )
            if item["executor"]["status"] == "failed":
                item["state"] = "failed"
                item["blockers"] = ["executor_failed"]
                item["next_required_action"] = "inspect_executor_result"
            elif item["executor"]["status"] == "completed":
                item["state"] = "updated_pending_ack"
                item["next_required_action"] = "acknowledge_update"
        item["quiescence"] = item["evidence"]["drain"]
        item["action_history"].append(
            {
                "action": self._prod_update_action_name(
                    prepared=prepared_update_id is not None,
                    acknowledged=acknowledged,
                    force_requested=force_requested,
                    execute=execute,
                ),
                "created_at": now,
                "requested_by": requested_by,
                "state": item["state"],
            }
        )
        state["prod_updates"][update_id] = item
        state["events"].append(
            {
                "type": "prod_update.status",
                "created_at": now,
                "prepared_update_id": update_id,
                "state": item["state"],
            }
        )
        self._write_state(state)
        return item

    def validate_release_channels(
        self, configs: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self._require_enabled()
        self._require_environment("control")
        contract = self._release_channel_contract()
        backend_config = self._backend_release_channel_config()
        errors: list[dict[str, str]] = []
        validated_configs: list[dict[str, Any]] = []
        seen_channels: set[str] = set()
        for config in [*configs, backend_config]:
            channel = str(config.get("channel") or "").strip()
            source = str(config.get("source") or "payload")
            if source == "payload":
                if channel in seen_channels:
                    errors.append({"code": "duplicate_channel", "channel": channel})
                seen_channels.add(channel)
            config_errors = self._validate_release_channel_config(
                config=config,
                contract=contract,
            )
            errors.extend(config_errors)
            validated_configs.append(
                {
                    "source": source,
                    "channel": channel,
                    "ok": not config_errors,
                    "errors": config_errors,
                    "evidence": self._release_channel_config_evidence(config),
                }
            )
        required = {"dev", "prod"}
        missing = sorted(required - seen_channels)
        for channel in missing:
            errors.append({"code": "missing_channel", "channel": channel})
        result = {
            "kind": "codex.releaseChannelValidation",
            "version": 1,
            "ok": not errors,
            "contract": contract,
            "backend_config": self._release_channel_config_evidence(backend_config),
            "configs": validated_configs,
            "errors": errors,
        }
        state = self._read_state()
        now = _utc_iso()
        validation_id = f"release-validation-{now.replace(':', '').replace('.', '')}"
        record = {
            "id": validation_id,
            "created_at": now,
            "status": "passed" if result["ok"] else "blocked",
            "ok": result["ok"],
            "errors": errors,
            "backend_config": result["backend_config"],
        }
        state["release_validations"][validation_id] = record
        state["events"].append(
            {
                "type": "release_channels.validated",
                "created_at": now,
                "id": validation_id,
                "status": record["status"],
            }
        )
        self._write_state(state)
        return result

    def _prod_update_record(
        self,
        *,
        update_id: str | None,
        update_version: str | None,
        state_name: str,
        drain_status: BackendDrainStatus,
        now: str,
        requested_by: str | None,
    ) -> dict[str, Any]:
        return {
            "kind": "codex.prodBackendUpdateGate",
            "version": 2,
            "prepared_update_id": update_id,
            "update_version": update_version,
            "state": state_name,
            "notification": state_name
            in {
                "waiting_for_idle",
                "auto_update_eligible",
                "updating",
                "updated_pending_ack",
                "failed",
            },
            "blockers": [],
            "quiescence": self._prod_update_drain_snapshot(drain_status),
            "evidence": {
                "drain": self._prod_update_drain_snapshot(drain_status),
                "prepared_by": requested_by,
                "prepared_at": now if update_id else None,
            },
            "action_history": [],
            "executor": self._prod_update_executor_plan(
                update_id=update_id or "none",
                execute=False,
                executor_result=None,
            ),
            "post_validation": {
                "status": "planned",
                "plan": self._prod_update_post_validation_plan(),
            },
            "force_restart_requires_strong_confirmation": True,
            "next_required_action": "none" if state_name == "idle" else "prepare",
            "created_at": now,
            "updated_at": now,
        }

    def _prod_update_drain_snapshot(
        self,
        drain_status: BackendDrainStatus,
    ) -> dict[str, Any]:
        return {
            "requested": drain_status.requested,
            "ready_to_restart": drain_status.ready_to_restart,
            "active_job_count": drain_status.active_job_count,
            "active_session_count": drain_status.active_session_count,
            "in_flight_message_count": drain_status.in_flight_message_count,
            "active_session_ids": drain_status.active_session_ids,
            "active_agent_run_ids": drain_status.active_agent_run_ids or [],
            "in_flight_message_ids": drain_status.in_flight_message_ids,
            "pending_follow_up_message_ids": (
                drain_status.pending_follow_up_message_ids or []
            ),
            "sdd_codex_job_ids": drain_status.sdd_codex_job_ids or [],
            "project_factory_job_ids": drain_status.project_factory_job_ids or [],
            "domain_factory_job_ids": drain_status.domain_factory_job_ids or [],
            "unknown_blockers": drain_status.unknown_blockers or [],
        }

    def _prod_update_blockers(self, drain_status: BackendDrainStatus) -> list[str]:
        blockers: list[str] = []
        if not drain_status.requested:
            blockers.append("drain_not_requested")
        if drain_status.active_job_count:
            blockers.append("active_jobs")
        if drain_status.active_session_count:
            blockers.append("active_sessions")
        if drain_status.in_flight_message_count:
            blockers.append("in_flight_messages")
        if drain_status.active_agent_run_ids:
            blockers.append("active_agent_runs")
        if drain_status.pending_follow_up_message_ids:
            blockers.append("pending_follow_ups")
        if drain_status.sdd_codex_job_ids:
            blockers.append("sdd_codex_jobs")
        if drain_status.project_factory_job_ids:
            blockers.append("project_factory_jobs")
        if drain_status.domain_factory_job_ids:
            blockers.append("domain_factory_jobs")
        for blocker in drain_status.unknown_blockers or []:
            blockers.append(f"unknown:{blocker}")
        return list(dict.fromkeys(blockers))

    def _prod_update_executor_plan(
        self,
        *,
        update_id: str,
        execute: bool,
        executor_result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        command = {
            "name": "prod_backend_update",
            "argv": ["scripts/prod_backend_update.sh", "--update-id", update_id],
            "allowlisted": True,
        }
        if not execute:
            return {
                "status": "planned",
                "command": command,
                "reason": "Execution was not requested.",
            }
        if not self._prod_update_executor_enabled:
            return {
                "status": "blocked",
                "command": command,
                "reason": "PROD update executor flag is disabled.",
            }
        if executor_result:
            return {
                "status": executor_result.get("status") or "completed",
                "command": command,
                "stdout": str(executor_result.get("stdout") or "")[-4000:],
                "stderr": str(executor_result.get("stderr") or "")[-4000:],
            }
        return {
            "status": "completed",
            "command": command,
            "stdout": "fake executor completed",
            "stderr": "",
        }

    def _prod_update_action_name(
        self,
        *,
        prepared: bool,
        acknowledged: bool,
        force_requested: bool,
        execute: bool,
    ) -> str:
        if acknowledged:
            return "acknowledge"
        if force_requested:
            return "force"
        if execute:
            return "execute"
        if prepared:
            return "prepare"
        return "status"

    def _prod_update_post_validation_plan(self) -> list[str]:
        return [
            "GET /health returns ok",
            "GET /project-factory/options returns deterministic options",
            "mobile app reconnects to the same real PROD API_BASE_URL",
        ]

    def _force_update_confirmation(self, update_id: str) -> str:
        return f"FORCE PROD UPDATE {update_id}"

    def _latest_prod_update_id(self, state: dict[str, Any]) -> str | None:
        if not state["prod_updates"]:
            return None
        items = list(state["prod_updates"].values())
        items.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""))
        return items[-1].get("prepared_update_id")

    def _promotion_plan(
        self,
        *,
        target: str,
        release_tag: str | None,
        user_approved: bool,
        dry_run: bool,
        drain_status: BackendDrainStatus,
    ) -> dict[str, Any]:
        blockers: list[str] = []
        hints: list[str] = []
        evidence: dict[str, Any] = {
            "dry_run": dry_run,
            "merge": self._promotion_merge_evidence(),
            "git": self._promotion_git_evidence(),
            "drain": self._promotion_drain_evidence(drain_status),
            "release_config": self._promotion_release_config_snapshot(),
            "release_channel_validation": self._release_channel_validation_evidence(
                release_tag=release_tag,
            ),
            "release_builds_require_real_backend": True,
        }
        if target != "prod":
            blockers.append("target_must_be_prod")
            hints.append("Promotion orchestrator only targets PROD.")
        if not release_tag or not release_tag.startswith("android-v"):
            blockers.append("invalid_or_missing_prod_release_tag")
            hints.append("Use an android-v* release tag for PROD promotion.")
        merge = evidence["merge"]
        if not merge.get("validated"):
            blockers.append("missing_validated_dev_main_merge")
            hints.append("Merge a validated DEV stage into dev/main first.")
        git = evidence["git"]
        if git.get("dirty"):
            blockers.append("dirty_repository")
            hints.append("Clean the repository before promotion dry-run.")
        if git.get("branch") != self._dev_main_branch:
            blockers.append("wrong_repository_branch")
            hints.append(f"Check out {self._dev_main_branch} before promotion.")
        config_errors = self._promotion_release_config_errors(
            evidence["release_config"]
        )
        blockers.extend(config_errors)
        release_channel_validation = evidence["release_channel_validation"]
        if not release_channel_validation.get("ok"):
            blockers.append("release_channel_validation_failed")
            for error in release_channel_validation.get("errors") or []:
                if isinstance(error, dict):
                    code = str(error.get("code") or "").strip()
                    if code:
                        blockers.append(code)
        if config_errors:
            hints.append("Fix PROD release configuration before promotion.")
        if not release_channel_validation.get("ok"):
            hints.append("Fix release channel validation before promotion.")
        if not user_approved:
            blockers.append("missing_user_approval")
            hints.append("Record explicit user approval before promotion.")
        if not drain_status.ready_to_restart:
            blockers.append("prod_not_quiescent")
            hints.append("Request drain and wait until PROD has no active work.")
        blockers = list(dict.fromkeys(blockers))
        state = self._promotion_state_from_blockers(blockers)
        planned_commands = self._promotion_planned_commands(
            release_tag=release_tag,
            dry_run=dry_run,
            state=state,
        )
        return {
            "state": state,
            "blockers": blockers,
            "remediation_hints": list(dict.fromkeys(hints)),
            "evidence": evidence,
            "planned_commands": planned_commands,
            "next_required_action": self._promotion_next_action(state),
        }

    def _promotion_state_from_blockers(self, blockers: list[str]) -> str:
        if not blockers:
            return "dry_run_passed"
        hard_blockers = [
            blocker
            for blocker in blockers
            if blocker not in {"missing_user_approval", "prod_not_quiescent"}
        ]
        if hard_blockers:
            return "blocked"
        if "missing_user_approval" in blockers:
            return "approval_required"
        return "drain_waiting"

    def _promotion_next_action(self, state: str) -> str:
        return {
            "approval_required": "collect_user_approval",
            "drain_waiting": "wait_for_backend_drain",
            "blocked": "resolve_preflight_blockers",
            "failed": "inspect_failure_logs",
            "dry_run_passed": "prepare_rollback_plan",
            "rollback_ready": "await_explicit_real_promotion_instruction",
        }.get(state, "run_preflight")

    def _promotion_steps(self) -> list[str]:
        return [
            "requested",
            "preflight",
            "validation",
            "approval_required",
            "drain_waiting",
            "ready_to_promote",
            "dry_run_passed",
            "rollback_ready",
        ]

    def _promotion_rollback_hints(self) -> list[str]:
        return [
            "restore previous backend service version",
            "republish previous app update registry item",
            "revert release tag only through the explicit release workflow",
        ]

    def _promotion_merge_evidence(self) -> dict[str, Any]:
        state = self._read_state()
        current = self._git_run(
            self._repository_root,
            ["rev-parse", self._dev_main_branch],
        )
        current_sha = current.stdout.strip() if current.returncode == 0 else None
        candidates = [
            item
            for item in state["merge_queue"].values()
            if item.get("target_branch") == self._dev_main_branch
            and item.get("status") in {"merged", "validated"}
        ]
        candidates.sort(key=lambda item: str(item.get("updated_at") or ""))
        latest = candidates[-1] if candidates else None
        commit_ids = latest.get("commit_ids") if latest else {}
        merge_commit = (
            (commit_ids or {}).get("target_after")
            or (commit_ids or {}).get("merge_commit")
        )
        return {
            "validated": bool(latest and merge_commit and merge_commit == current_sha),
            "merge_id": latest.get("id") if latest else None,
            "merge_commit": merge_commit,
            "source_sha": (commit_ids or {}).get("source"),
            "dev_main_sha": current_sha,
        }

    def _promotion_git_evidence(self) -> dict[str, Any]:
        branch = self._git_run(
            self._repository_root,
            ["rev-parse", "--abbrev-ref", "HEAD"],
        )
        sha = self._git_run(self._repository_root, ["rev-parse", "HEAD"])
        return {
            "branch": branch.stdout.strip() if branch.returncode == 0 else None,
            "head_sha": sha.stdout.strip() if sha.returncode == 0 else None,
            "dirty": self._git_dirty(self._repository_root),
        }

    def _promotion_drain_evidence(
        self,
        drain_status: BackendDrainStatus,
    ) -> dict[str, Any]:
        return {
            "requested": drain_status.requested,
            "ready_to_restart": drain_status.ready_to_restart,
            "active_job_count": drain_status.active_job_count,
            "active_session_count": drain_status.active_session_count,
            "in_flight_message_count": drain_status.in_flight_message_count,
            "active_session_ids": drain_status.active_session_ids,
            "in_flight_message_ids": drain_status.in_flight_message_ids,
        }

    def _promotion_release_config_snapshot(self) -> dict[str, Any]:
        registry_path = self._app_update_registry_path or ""
        return {
            "api_base_url": self._backend_url,
            "app_channel": self._app_channel,
            "updater_channel": self._updater_channel,
            "app_label": self._app_label,
            "environment_color": self._color,
            "app_update_registry_path": registry_path,
            "app_update_registry_exists": bool(
                registry_path and Path(registry_path).exists()
            ),
            "app_update_public_base_url": self._app_update_public_base_url or "",
            "app_update_github_token": (
                "[present]" if self._app_update_github_token_present else "[missing]"
            ),
        }

    def _promotion_release_config_errors(
        self,
        config: dict[str, Any],
    ) -> list[str]:
        errors: list[str] = []
        api_base_url = str(config.get("api_base_url") or "").strip()
        lowered_url = api_base_url.lower()
        if not api_base_url.startswith(("http://", "https://")):
            errors.append("invalid_prod_api_base_url")
        if any(
            marker in lowered_url
            for marker in ["localhost", "127.0.0.1", "0.0.0.0", "mock", "demo", "local"]
        ):
            errors.append("prod_api_placeholder")
        if config.get("updater_channel") != "prod":
            errors.append("invalid_prod_updater_channel")
        label = str(config.get("app_label") or "")
        if not label or "dev" in label.lower():
            errors.append("invalid_prod_app_label")
        if not config.get("app_update_registry_exists"):
            errors.append("missing_app_updates_registry")
        if config.get("app_update_github_token") != "[present]":
            errors.append("missing_app_update_github_token")
        return errors

    def _release_channel_contract(self) -> dict[str, Any]:
        return {
            "prod": {
                "channel": "prod",
                "app_channel": "prod",
                "updater_channel": "prod",
                "app_label": "Codex Mobile Bridge",
                "api_base_url": "real non-local bridge URL",
                "release_tag_pattern": "android-v*",
                "forbid_url_markers": [
                    "localhost",
                    "127.0.0.1",
                    "0.0.0.0",
                    "mock",
                    "demo",
                    "local",
                ],
            },
            "dev": {
                "channel": "dev",
                "app_channel": "dev",
                "updater_channel": "dev",
                "app_label_contains": "DEV",
                "api_base_url": "DEV stage/backend URL",
                "release_tag_pattern": "android-dev-v*",
                "stage_identity_visible": True,
            },
        }

    def _backend_release_channel_config(self) -> dict[str, Any]:
        return {
            "source": "backend",
            "channel": self._app_channel,
            "api_base_url": self._backend_url,
            "app_channel": self._app_channel,
            "updater_channel": self._updater_channel,
            "app_label": self._app_label,
            "color": self._color,
            "environment": self._environment,
            "stage_id": self._stage_id,
            "branch": self._branch,
            "backend_url": self._backend_url,
            "app_update_registry_path": self._app_update_registry_path or "",
            "app_update_registry_exists": bool(
                self._app_update_registry_path
                and Path(self._app_update_registry_path).exists()
            ),
            "app_update_public_base_url": self._app_update_public_base_url or "",
            "release_tag_pattern": (
                "android-dev-v*" if self._app_channel == "dev" else "android-v*"
            ),
        }

    def _release_channel_config_evidence(
        self,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "source": str(config.get("source") or "payload"),
            "channel": str(config.get("channel") or ""),
            "api_base_url": str(config.get("api_base_url") or ""),
            "app_channel": str(config.get("app_channel") or ""),
            "updater_channel": str(config.get("updater_channel") or ""),
            "app_label": str(config.get("app_label") or ""),
            "color": str(config.get("color") or ""),
            "environment": str(config.get("environment") or ""),
            "stage_id": config.get("stage_id"),
            "branch": config.get("branch"),
            "backend_url": str(config.get("backend_url") or ""),
            "release_tag_pattern": str(config.get("release_tag_pattern") or ""),
            "release_tag": str(config.get("release_tag") or ""),
            "app_update_registry_path": str(
                config.get("app_update_registry_path") or ""
            ),
            "app_update_registry_exists": bool(
                config.get("app_update_registry_exists")
            ),
            "app_update_public_base_url": str(
                config.get("app_update_public_base_url") or ""
            ),
        }

    def _release_channel_validation_evidence(
        self,
        *,
        release_tag: str | None,
    ) -> dict[str, Any]:
        config = self._backend_release_channel_config()
        config["release_tag"] = release_tag or ""
        errors = self._validate_release_channel_config(
            config=config,
            contract=self._release_channel_contract(),
        )
        return {
            "ok": not errors,
            "errors": errors,
            "evidence": self._release_channel_config_evidence(config),
        }

    def _validate_release_channel_config(
        self,
        *,
        config: dict[str, Any],
        contract: dict[str, Any],
    ) -> list[dict[str, str]]:
        errors: list[dict[str, str]] = []
        source = str(config.get("source") or "payload")
        channel = str(config.get("channel") or "").strip()
        api_base_url = str(config.get("api_base_url") or "").strip()
        app_channel = str(config.get("app_channel") or channel).strip()
        label = str(config.get("app_label") or "").strip()
        updater_channel = str(config.get("updater_channel") or "").strip()
        color = str(config.get("color") or "").strip()
        release_tag_pattern = str(config.get("release_tag_pattern") or "").strip()
        release_tag = str(config.get("release_tag") or "").strip()
        if channel not in contract:
            errors.append({"code": "invalid_channel", "channel": channel, "source": source})
            return errors
        if app_channel != channel:
            errors.append(
                {"code": "mixed_app_channel", "channel": channel, "source": source}
            )
        if not api_base_url.startswith(("http://", "https://")):
            errors.append(
                {"code": "invalid_api_base_url", "channel": channel, "source": source}
            )
        if not label or not updater_channel or not color:
            errors.append(
                {
                    "code": "missing_release_identity",
                    "channel": channel,
                    "source": source,
                }
            )
        if not color.startswith("#") or len(color) != 7:
            errors.append(
                {
                    "code": "invalid_environment_color",
                    "channel": channel,
                    "source": source,
                }
            )
        if channel == "prod":
            lowered_url = api_base_url.lower()
            if any(
                marker in lowered_url
                for marker in contract["prod"]["forbid_url_markers"]
            ):
                errors.append(
                    {
                        "code": "prod_api_cannot_be_mock_demo_or_local",
                        "channel": channel,
                        "source": source,
                    }
                )
            if updater_channel != "prod":
                errors.append(
                    {
                        "code": "invalid_prod_updater_channel",
                        "channel": channel,
                        "source": source,
                    }
                )
            if "dev" in label.lower():
                errors.append(
                    {
                        "code": "invalid_prod_app_label",
                        "channel": channel,
                        "source": source,
                    }
                )
            if release_tag and not release_tag.startswith("android-v"):
                errors.append(
                    {"code": "invalid_release_tag", "channel": channel, "source": source}
                )
            if release_tag_pattern and release_tag_pattern != "android-v*":
                errors.append(
                    {
                        "code": "invalid_release_tag_pattern",
                        "channel": channel,
                        "source": source,
                    }
                )
        if channel == "dev":
            if updater_channel != "dev":
                errors.append(
                    {
                        "code": "invalid_dev_updater_channel",
                        "channel": channel,
                        "source": source,
                    }
                )
            if "dev" not in label.lower():
                errors.append(
                    {
                        "code": "invalid_dev_app_label",
                        "channel": channel,
                        "source": source,
                    }
                )
            if release_tag and not release_tag.startswith("android-dev-v"):
                errors.append(
                    {"code": "invalid_release_tag", "channel": channel, "source": source}
                )
            if release_tag_pattern and release_tag_pattern != "android-dev-v*":
                errors.append(
                    {
                        "code": "invalid_release_tag_pattern",
                        "channel": channel,
                        "source": source,
                    }
                )
            if not (config.get("stage_id") or config.get("branch")) and source == "backend":
                errors.append(
                    {
                        "code": "missing_dev_stage_identity",
                        "channel": channel,
                        "source": source,
                    }
                )
        if source == "backend":
            if not config.get("app_update_registry_exists"):
                errors.append(
                    {
                        "code": "missing_app_updates_registry",
                        "channel": channel,
                        "source": source,
                    }
                )
        return errors

    def _promotion_planned_commands(
        self,
        *,
        release_tag: str | None,
        dry_run: bool,
        state: str,
    ) -> list[dict[str, Any]]:
        return [
            self._promotion_command(
                name="sdd_doctor",
                argv=[
                    ".venv/bin/python",
                    "scripts/codex_bridge_sdd_doctor.py",
                    "--workspace",
                    str(self._repository_root),
                    "--projects-root",
                    str(self._repository_root.parent),
                    "--json",
                ],
                status="planned_safe_dry_run" if dry_run else "blocked_real_execution",
            ),
            self._promotion_command(
                name="release_channel_validation",
                argv=["internal", "validate_release_channels"],
                status="completed",
            ),
            self._promotion_command(
                name="android_release_channel_dry_run",
                argv=[
                    ".venv/bin/python",
                    "scripts/validate_android_release_channel.py",
                    "--channel",
                    self._app_channel,
                    "--api-base-url",
                    self._backend_url,
                    "--app-label",
                    self._app_label,
                    "--updater-channel",
                    self._updater_channel,
                    "--environment-color",
                    self._color,
                    "--release-tag",
                    release_tag or "",
                    "--app-updates-registry",
                    self._app_update_registry_path or "",
                ],
                status="planned_safe_dry_run",
            ),
            self._promotion_command(
                name="backend_post_release_validation",
                argv=["scripts/validate_backend_post_release.sh"],
                status="planned_safe_dry_run" if state == "dry_run_passed" else "planned",
            ),
            self._promotion_command(
                name="android_release_workflow",
                argv=[
                    "scripts/publish_android_release.sh",
                    "--tag",
                    release_tag or "",
                ],
                status="blocked_real_release",
                reason="Publishing Android releases requires a separate explicit instruction.",
            ),
        ]

    def _promotion_command(
        self,
        *,
        name: str,
        argv: list[str],
        status: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        item: dict[str, Any] = {
            "name": name,
            "argv": argv,
            "status": status,
            "allowlisted": True,
        }
        if reason:
            item["reason"] = reason
        return item

    def allocate_stage_port(self, stage_id: str) -> int:
        if not _STAGE_ID_PATTERN.match(stage_id):
            raise DevPipelineError(
                "invalid_stage_id", "stage_id must look like spec-018."
            )
        return 8100 + int(stage_id.rsplit("-", 1)[1])

    def _runtime_record(
        self, stage_id: str, port: int, backend_url: str
    ) -> dict[str, Any]:
        root = self._runtime_root / "stages" / stage_id
        return {
            "stage_id": stage_id,
            "backend": {
                "url": backend_url,
                "port": port,
                "data_dir": str(root / "data"),
                "logs_dir": str(root / "logs"),
                "pid_file": str(root / "backend.pid"),
                "env_file": str(root / ".env.stage"),
                "health": "unknown",
                "last_restart_at": None,
            },
            "url": backend_url,
            "port": port,
            "data_dir": str(root / "data"),
            "logs_dir": str(root / "logs"),
            "pid_file": str(root / "backend.pid"),
            "env_file": str(root / ".env.stage"),
            "health": "unknown",
            "last_restart_at": None,
            "restart_policy": "manual",
        }

    def _stage_commands(self, stage: dict[str, Any], action: str) -> list[list[str]]:
        runtime = stage["runtime"]
        base = [
            "--env-file",
            runtime["env_file"],
            "--pid-file",
            runtime["pid_file"],
        ]
        start = [
            "scripts/run_backend_detached.sh",
            *base,
            "--runtime-dir",
            str(Path(runtime["logs_dir"]).parent),
            "--log-file",
            str(Path(runtime["logs_dir"]) / "backend.log"),
        ]
        stop = ["scripts/stop_backend.sh", *base]
        if action == "start":
            return [start]
        if action == "stop":
            return [stop]
        if action == "restart":
            return [stop, start]
        return []

    def _prepare_stage_runtime(self, stage: dict[str, Any]) -> None:
        runtime = stage["runtime"]
        for key in ["data_dir", "logs_dir"]:
            Path(runtime[key]).mkdir(parents=True, exist_ok=True)
        Path(runtime["env_file"]).parent.mkdir(parents=True, exist_ok=True)
        env_lines = {
            "API_PORT": str(runtime["port"]),
            "API_BASE_URL": runtime["url"],
            "CODEX_WORKDIR": stage["worktree_path"],
            "PROJECTS_ROOT": str(Path(stage["worktree_path"]).parent),
            "CHAT_STORE_PATH": str(Path(runtime["data_dir"]) / "chat_store.sqlite3"),
            "FEEDBACK_QUEUE_PATH": str(
                Path(runtime["data_dir"]) / "feedback_queue.json"
            ),
            "FEEDBACK_IMAGE_DIR": str(Path(runtime["data_dir"]) / "feedback_images"),
            "FEEDBACK_AUDIO_DIR": str(Path(runtime["data_dir"]) / "feedback_audio"),
            "ASSET_DEPOT_DIR": str(Path(runtime["data_dir"]) / "asset_depot"),
            "PROJECT_FACTORY_STATE_DIR": str(
                Path(runtime["data_dir"]) / "project_factory_state"
            ),
            "BRIDGE_ENVIRONMENT": "dev",
            "BRIDGE_STAGE_ID": stage["stage_id"],
            "BRIDGE_SPEC_ID": stage["spec_id"],
            "BRIDGE_STAGE_BRANCH": stage["branch"],
            "BRIDGE_STAGE_WORKTREE_PATH": stage["worktree_path"],
            "BRIDGE_APP_CHANNEL": "dev",
            "BRIDGE_UPDATER_CHANNEL": "dev",
            "BRIDGE_APP_LABEL": "Codex Mobile Bridge DEV",
            "DEV_PIPELINE_STATE_PATH": str(self._state_path),
            "DEV_PIPELINE_RUNTIME_ROOT": str(self._runtime_root),
        }
        Path(runtime["env_file"]).write_text(
            "\n".join(f"{key}={value}" for key, value in env_lines.items()) + "\n",
            encoding="utf-8",
        )

    def _stage_process_status(self, runtime: dict[str, Any]) -> dict[str, Any]:
        pid_file = Path(runtime["pid_file"])
        if not pid_file.exists():
            return {"running": False, "pid": None, "pid_file": str(pid_file)}
        raw_pid = pid_file.read_text(encoding="utf-8").strip()
        try:
            pid = int(raw_pid)
        except ValueError:
            return {"running": False, "pid": raw_pid, "pid_file": str(pid_file)}
        try:
            os.kill(pid, 0)
        except OSError:
            return {"running": False, "pid": pid, "pid_file": str(pid_file)}
        return {"running": True, "pid": pid, "pid_file": str(pid_file)}

    def _stage_healthcheck(self, runtime: dict[str, Any]) -> dict[str, Any]:
        base_url = str(runtime.get("url") or "").rstrip("/")
        url = f"{base_url}/health" if base_url else ""
        started_at = _utc_iso()
        if not url:
            return {
                "ok": False,
                "url": url,
                "status_code": None,
                "error": "missing_stage_backend_url",
                "checked_at": started_at,
            }
        try:
            with urlopen(url, timeout=1.0) as response:  # noqa: S310 - stage URL only
                body = response.read(8192).decode("utf-8", errors="replace")
                status_code = int(response.status)
        except HTTPError as exc:
            body = exc.read(8192).decode("utf-8", errors="replace")
            return {
                "ok": False,
                "url": url,
                "status_code": int(exc.code),
                "body": body[:1000],
                "error": str(exc)[:500],
                "checked_at": started_at,
            }
        except (OSError, TimeoutError, URLError) as exc:
            return {
                "ok": False,
                "url": url,
                "status_code": None,
                "error": str(exc)[:500],
                "checked_at": started_at,
            }
        parsed: Any = None
        try:
            parsed = json.loads(body) if body.strip() else None
        except json.JSONDecodeError:
            parsed = None
        return {
            "ok": 200 <= status_code < 300,
            "url": url,
            "status_code": status_code,
            "body": body[:1000],
            "json": parsed,
            "checked_at": started_at,
        }

    def _run_merge_sdd_doctor(self) -> dict[str, Any]:
        script = self._repository_root / "scripts" / "codex_bridge_sdd_doctor.py"
        argv = [
            sys.executable,
            str(script),
            "--workspace",
            str(self._repository_root),
            "--projects-root",
            str(self._repository_root.parent),
            "--json",
        ]
        if not script.exists():
            return {
                "ok": True,
                "status": "skipped",
                "reason": "sdd_doctor_script_missing",
                "argv": argv,
                "allowlisted": True,
                "blockers": [],
            }
        result = subprocess.run(
            argv,
            cwd=self._repository_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        parsed: dict[str, Any] = {}
        try:
            value = json.loads(result.stdout or "{}")
            if isinstance(value, dict):
                parsed = value
        except json.JSONDecodeError:
            parsed = {}
        ok = result.returncode == 0 and bool(parsed.get("ok", result.returncode == 0))
        blockers: list[str] = []
        if not ok:
            blockers.append("sdd_doctor_failed")
        if parsed.get("errors"):
            blockers.append("sdd_doctor_errors")
        return {
            "ok": ok,
            "status": "passed" if ok else "failed",
            "argv": argv,
            "allowlisted": True,
            "return_code": result.returncode,
            "stdout": result.stdout[-12000:],
            "stderr": result.stderr[-12000:],
            "summary": parsed.get("summary") or {},
            "blockers": list(dict.fromkeys(blockers)),
        }

    def _materialization_git_blocker(
        self,
        *,
        spec_id: str,
        branch: str,
        worktree_path: str,
    ) -> dict[str, str] | None:
        if self._git_dirty(self._repository_root):
            return {
                "reason": "dirty_repository",
                "detail": "Repository must be clean before backlog materialization.",
            }
        base = self._git_run(
            self._repository_root,
            ["rev-parse", "--verify", self._dev_main_branch],
        )
        if base.returncode != 0:
            return {
                "reason": "missing_base_branch",
                "detail": f"Base branch {self._dev_main_branch} is required.",
            }
        expected_path = Path(worktree_path)
        if expected_path.exists():
            if not expected_path.is_dir():
                return {
                    "reason": "incompatible_worktree_path",
                    "detail": f"Expected worktree path is not a directory: {worktree_path}.",
                }
            top = self._git_run(expected_path, ["rev-parse", "--show-toplevel"])
            if top.returncode != 0 or Path(top.stdout.strip()).resolve() != expected_path:
                return {
                    "reason": "incompatible_worktree_path",
                    "detail": f"Expected path is not the stage git worktree: {worktree_path}.",
                }
            current_branch = self._git_run(
                expected_path, ["rev-parse", "--abbrev-ref", "HEAD"]
            )
            if current_branch.returncode != 0 or current_branch.stdout.strip() != branch:
                return {
                    "reason": "incompatible_worktree_branch",
                    "detail": f"Worktree must be on {branch}.",
                }
            if self._git_dirty(expected_path):
                return {
                    "reason": "dirty_worktree",
                    "detail": f"Worktree must be clean before reuse: {worktree_path}.",
                }
            return None

        branch_exists = (
            self._git_run(self._repository_root, ["rev-parse", "--verify", branch])
            .returncode
            == 0
        )
        if branch_exists:
            add = self._git_run(
                self._repository_root,
                ["worktree", "add", worktree_path, branch],
                timeout=30,
            )
        else:
            add = self._git_run(
                self._repository_root,
                ["worktree", "add", "-b", branch, worktree_path, self._dev_main_branch],
                timeout=30,
            )
        if add.returncode != 0:
            return {
                "reason": "git_worktree_add_failed",
                "detail": (add.stderr or add.stdout or "git worktree add failed.")[
                    -1000:
                ],
            }
        spec_dir = Path(worktree_path) / "specs" / spec_id
        if spec_dir.exists() and not spec_dir.is_dir():
            return {
                "reason": "spec_path_incompatible",
                "detail": f"Spec path is not a directory: {spec_dir}.",
            }
        return None

    def _upsert_materialized_stage(
        self,
        *,
        state: dict[str, Any],
        spec_id: str,
        stage_id: str,
        branch: str,
        worktree_path: str,
        owner: str,
    ) -> dict[str, Any]:
        resolved_worktree = self._validate_stage_worktree_path(
            stage_id=stage_id,
            worktree_path=worktree_path,
        )
        port = self.allocate_stage_port(stage_id)
        backend_url = f"http://127.0.0.1:{port}"
        now = _utc_iso()
        runtime = self._runtime_record(stage_id, port, backend_url)
        stage = {
            "stage_id": stage_id,
            "environment": "dev",
            "spec_id": spec_id,
            "branch": branch,
            "base_branch": self._dev_main_branch,
            "worktree_path": resolved_worktree,
            "backend_url": backend_url,
            "app_channel": "dev",
            "status": "active",
            "owner": owner,
            "runtime": runtime,
            "created_at": now,
            "updated_at": now,
        }
        existing = state["stages"].get(stage_id)
        if existing:
            mismatches = [
                field
                for field in ["spec_id", "branch", "worktree_path"]
                if existing.get(field) != stage[field]
            ]
            if mismatches:
                raise DevPipelineError(
                    "stage_identity_mismatch",
                    f"Registered stage differs in immutable fields: {', '.join(mismatches)}.",
                )
            existing.update(
                {
                    "backend_url": backend_url,
                    "runtime": runtime,
                    "updated_at": now,
                    "status": existing.get("status") or "active",
                }
            )
            return existing
        state["stages"][stage_id] = stage
        return stage

    def _bind_stage_session_in_state(
        self,
        *,
        state: dict[str, Any],
        session_id: str,
        stage: dict[str, Any],
    ) -> dict[str, Any]:
        existing = state["sessions"].get(session_id)
        if existing and existing["stage_id"] != stage["stage_id"]:
            raise DevPipelineError(
                "session_stage_mismatch", "Session is already bound to another stage."
            )
        now = _utc_iso()
        binding = {
            "session_id": session_id,
            "stage_id": stage["stage_id"],
            "spec_id": stage["spec_id"],
            "branch": stage["branch"],
            "worktree_path": stage["worktree_path"],
            "backend_url": stage["backend_url"],
            "status": "bound",
            "created_at": existing["created_at"] if existing else now,
            "updated_at": now,
        }
        state["sessions"][session_id] = binding
        state["events"].append(
            {
                "type": "stage_session.bound",
                "created_at": now,
                "session_id": session_id,
                "stage_id": stage["stage_id"],
            }
        )
        self._write_state(state)
        return binding

    def _block_materialization(
        self,
        *,
        state: dict[str, Any],
        item: dict[str, Any],
        handoff_id: str,
        worker_id: str,
        reason: str,
        detail: str,
        partial_artifacts: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        now = _utc_iso()
        item.update(
            {
                "status": "blocked",
                "blocker_reason": reason,
                "blocker_detail": detail,
                "partial_artifacts": list(partial_artifacts or []),
                "updated_at": now,
            }
        )
        state["events"].append(
            {
                "type": "backlog.blocked",
                "created_at": now,
                "handoff_id": handoff_id,
                "worker_id": worker_id,
                "reason": reason,
                "detail": detail,
                "partial_artifacts": list(partial_artifacts or []),
            }
        )
        self._write_state(state)
        handoff = state["handoffs"].get(handoff_id, {})
        return self._materialize_response(item, handoff, state)

    def _materialize_response(
        self,
        item: dict[str, Any],
        handoff: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        spec_id = item.get("spec_id")
        stage_id = item.get("stage_id")
        return {
            "kind": "codex.devBacklogMaterialization",
            "version": 1,
            "handoff": handoff,
            "backlog": item,
            "spec": state["specs"].get(spec_id) if spec_id else None,
            "stage": state["stages"].get(stage_id) if stage_id else None,
        }

    def _write_sdd_skeleton(
        self,
        spec_dir: Path,
        payload: dict[str, Any],
    ) -> list[str]:
        spec_dir.mkdir(parents=True, exist_ok=True)
        title = str(payload.get("title") or "DEV handoff").strip()
        problem = str(payload.get("problem") or "").strip()
        context = str(payload.get("context") or "").strip()
        acceptance = str(payload.get("acceptance_criteria") or "").strip()
        spec_path = spec_dir.joinpath("spec.md")
        plan_path = spec_dir.joinpath("plan.md")
        tasks_path = spec_dir.joinpath("tasks.md")
        spec_path.write_text(
            f"# {title}\n\n"
            "## Problem\n\n"
            f"{problem}\n\n"
            "## Context\n\n"
            f"{context}\n\n"
            "## Acceptance Criteria\n\n"
            f"{acceptance}\n",
            encoding="utf-8",
        )
        plan_path.write_text(
            f"# Implementation Plan: {title}\n\n"
            "## Scope\n\n"
            "Materialized from a PROD to DEV handoff.\n\n"
            "## Validation\n\n"
            f"{acceptance}\n",
            encoding="utf-8",
        )
        tasks_path.write_text(
            f"# Tasks: {title}\n\n"
            "- [ ] Confirm handoff context and acceptance criteria\n"
            "- [ ] Implement the isolated DEV stage changes\n"
            "- [ ] Run targeted regression validation\n",
            encoding="utf-8",
        )
        return [str(spec_path), str(plan_path), str(tasks_path)]

    def _git_run(
        self,
        cwd: Path,
        args: list[str],
        *,
        timeout: int = 10,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["git", *args],
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return subprocess.CompletedProcess(
                ["git", *args],
                returncode=1,
                stdout="",
                stderr=str(exc),
            )

    def _merge_evidence(
        self,
        *,
        evidence_validated: bool,
        validation_passed: bool | None,
        validation_log: str | None,
        tests_executed: list[str] | None,
    ) -> dict[str, Any]:
        tests = [
            str(item).strip()
            for item in (tests_executed or [])
            if str(item).strip()
        ]
        return {
            "validated": bool(evidence_validated),
            "validation_passed": validation_passed,
            "validation_log": (validation_log or "")[-10000:],
            "tests_executed": list(dict.fromkeys(tests)),
        }

    def _merge_evidence_with_stage_state(
        self,
        *,
        stage: dict[str, Any],
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(evidence)
        status = self._git_run(
            Path(stage["worktree_path"]),
            ["status", "--porcelain"],
        )
        merged["changed_files"] = (
            status.stdout.splitlines() if status.returncode == 0 else []
        )
        return merged

    def _merge_preflight(
        self,
        *,
        state: dict[str, Any],
        stage: dict[str, Any],
        approved: bool,
        evidence: dict[str, Any],
        current_merge_id: str | None = None,
    ) -> dict[str, Any]:
        blockers: list[str] = []
        hints: list[str] = []
        running_merge = self._running_merge(state, current_merge_id=current_merge_id)
        if running_merge:
            blockers.append("serialized_queue_busy")
            hints.append(f"Wait for merge {running_merge['id']} to finish.")
        if not approved:
            blockers.append("stage_not_approved")
            hints.append("Request explicit DEV/user approval before integration.")
        stage_id = str(stage.get("stage_id") or "")
        materialized = [
            item
            for item in state["backlog"].values()
            if item.get("stage_id") == stage_id and item.get("status") == "materialized"
        ]
        if not materialized:
            blockers.append("stage_not_materialized")
            hints.append("Materialize the handoff into a DEV stage before merging.")
        if stage.get("status") != "active":
            blockers.append("stage_not_active")
            hints.append("Resolve the stage blocker or reactivate the DEV stage.")
        active_runs = [
            run
            for run in state["runs"].values()
            if run.get("stage_id") == stage_id
            and run.get("status") in {"queued", "running", "planned"}
        ]
        if active_runs:
            blockers.append("stage_run_active")
            hints.append("Wait for active stage runs to complete or cancel them.")
        completed_runs = [
            run
            for run in state["runs"].values()
            if run.get("stage_id") == stage_id and run.get("status") == "completed"
        ]
        terminal_failed_runs = [
            run
            for run in state["runs"].values()
            if run.get("stage_id") == stage_id
            and run.get("status") in {"cancelled", "failed"}
        ]
        if evidence.get("validation_passed") is False:
            blockers.append("validation_failed")
            hints.append("Fix validation failures before applying the merge.")
        if not completed_runs and not evidence.get("validated"):
            blockers.append(
                "stage_run_not_completed"
                if terminal_failed_runs or active_runs
                else "missing_validation_evidence"
            )
            hints.append(
                "Complete at least one stage run or explicitly mark evidence validated."
            )
        if not self._merge_has_required_evidence(
            completed_runs=completed_runs,
            evidence=evidence,
        ):
            blockers.append("missing_validation_evidence")
            hints.append("Attach tests executed or validated evidence for the merge.")
        worktree = Path(stage["worktree_path"])
        if not worktree.exists():
            blockers.append("missing_worktree")
            hints.append("Restore or rematerialize the stage worktree.")
        elif self._git_dirty(worktree):
            blockers.append("dirty_worktree")
            hints.append("Commit, stash, or discard stage worktree changes intentionally.")
        else:
            current_branch = self._git_run(
                worktree,
                ["rev-parse", "--abbrev-ref", "HEAD"],
            )
            if (
                current_branch.returncode != 0
                or current_branch.stdout.strip() != stage["branch"]
            ):
                blockers.append("stage_branch_mismatch")
                hints.append(f"Check out {stage['branch']} in the stage worktree.")
        if self._git_dirty(self._repository_root):
            blockers.append("dirty_repository")
            hints.append("Clean the base repository before integration.")
        base_branch = self._git_run(
            self._repository_root,
            ["rev-parse", "--verify", self._dev_main_branch],
        )
        source_branch = self._git_run(
            self._repository_root,
            ["rev-parse", "--verify", stage["branch"]],
        )
        if base_branch.returncode != 0:
            blockers.append("missing_base_branch")
            hints.append(f"Create or fetch {self._dev_main_branch}.")
        if source_branch.returncode != 0:
            blockers.append("missing_stage_branch")
            hints.append(f"Restore stage branch {stage['branch']}.")
        root_branch = self._git_run(
            self._repository_root,
            ["rev-parse", "--abbrev-ref", "HEAD"],
        )
        if root_branch.returncode == 0 and root_branch.stdout.strip() == self._dev_main_branch:
            blockers.append("target_branch_checked_out")
            hints.append(
                "Check out a non-target branch in the base worktree before applying."
            )
        if base_branch.returncode == 0 and source_branch.returncode == 0:
            ancestor = self._git_run(
                self._repository_root,
                ["merge-base", "--is-ancestor", self._dev_main_branch, stage["branch"]],
            )
            if ancestor.returncode != 0:
                blockers.append("stale_branch")
                hints.append(
                    f"Rebase or merge {self._dev_main_branch} into {stage['branch']}."
                )
            trial_merge = self._git_run(
                self._repository_root,
                ["merge-tree", "--write-tree", self._dev_main_branch, stage["branch"]],
                timeout=30,
            )
            if trial_merge.returncode != 0:
                blockers.append("merge_conflict")
                hints.append(
                    f"Resolve conflicts on {stage['branch']} against {self._dev_main_branch}."
                )
        blockers = list(dict.fromkeys(blockers))
        return {
            "ok": not blockers,
            "blockers": blockers,
            "remediation_hints": list(dict.fromkeys(hints)),
        }

    def _running_merge(
        self,
        state: dict[str, Any],
        *,
        current_merge_id: str | None = None,
    ) -> dict[str, Any] | None:
        for item in state["merge_queue"].values():
            if item.get("id") == current_merge_id:
                continue
            if item.get("status") in {"running", "applying"}:
                return item
        return None

    def _merge_has_required_evidence(
        self,
        *,
        completed_runs: list[dict[str, Any]],
        evidence: dict[str, Any],
    ) -> bool:
        if evidence.get("validated") or evidence.get("tests_executed"):
            return True
        for run in completed_runs:
            run_evidence = run.get("evidence") or {}
            if run_evidence.get("tests_executed") or run_evidence.get("tests_declared"):
                return True
            if run_evidence.get("final_summary") or run_evidence.get("changed_files"):
                return True
            reviewer = run_evidence.get("reviewer") or {}
            if reviewer.get("completion") or reviewer.get("continue"):
                return True
        return False

    def _apply_git_merge(
        self,
        *,
        stage: dict[str, Any],
        merge_id: str,
    ) -> dict[str, Any]:
        target_ref = self._dev_main_branch
        source_ref = str(stage["branch"])
        target_sha = self._git_run(
            self._repository_root,
            ["rev-parse", target_ref],
        )
        source_sha = self._git_run(
            self._repository_root,
            ["rev-parse", source_ref],
        )
        merge_base = self._git_run(
            self._repository_root,
            ["merge-base", target_ref, source_ref],
        )
        commit_ids = {
            "target_before": target_sha.stdout.strip(),
            "source": source_sha.stdout.strip(),
            "merge_base": merge_base.stdout.strip(),
        }
        merge_tree = self._git_run(
            self._repository_root,
            ["merge-tree", "--write-tree", target_ref, source_ref],
            timeout=30,
        )
        if merge_tree.returncode != 0:
            return {
                "status": "failed",
                "blockers": ["merge_conflict"],
                "remediation_hints": [
                    f"Resolve conflicts on {source_ref} against {target_ref}."
                ],
                "stdout": merge_tree.stdout[-12000:],
                "stderr": merge_tree.stderr[-12000:],
                "commit_ids": commit_ids,
                "partial_artifacts": [],
            }
        tree_sha = merge_tree.stdout.strip().splitlines()[0]
        commit_message = f"Merge {source_ref} into {target_ref}\n\nMerge queue: {merge_id}"
        commit = self._git_run(
            self._repository_root,
            [
                "commit-tree",
                tree_sha,
                "-p",
                commit_ids["target_before"],
                "-p",
                commit_ids["source"],
                "-m",
                commit_message,
            ],
            timeout=30,
        )
        if commit.returncode != 0:
            return {
                "status": "failed",
                "blockers": ["commit_tree_failed"],
                "remediation_hints": ["Inspect git commit-tree output and retry."],
                "stdout": commit.stdout[-12000:],
                "stderr": commit.stderr[-12000:],
                "commit_ids": commit_ids,
                "partial_artifacts": [],
            }
        merge_commit = commit.stdout.strip()
        update = self._git_run(
            self._repository_root,
            [
                "update-ref",
                f"refs/heads/{target_ref}",
                merge_commit,
                commit_ids["target_before"],
            ],
            timeout=30,
        )
        if update.returncode != 0:
            return {
                "status": "failed",
                "blockers": ["update_ref_failed"],
                "remediation_hints": ["Re-run preflight and retry integration."],
                "stdout": update.stdout[-12000:],
                "stderr": update.stderr[-12000:],
                "commit_ids": {**commit_ids, "merge_commit": merge_commit},
                "partial_artifacts": [
                    {"kind": "git_commit_object", "sha": merge_commit}
                ],
            }
        return {
            "status": "merged",
            "blockers": [],
            "remediation_hints": [],
            "stdout": "\n".join(
                part
                for part in [merge_tree.stdout.strip(), commit.stdout.strip()]
                if part
            )[-12000:],
            "stderr": "\n".join(
                part
                for part in [merge_tree.stderr.strip(), commit.stderr.strip()]
                if part
            )[-12000:],
            "commit_ids": {
                **commit_ids,
                "tree": tree_sha,
                "merge_commit": merge_commit,
                "target_after": merge_commit,
            },
            "source_branch": source_ref,
            "target_branch": target_ref,
            "partial_artifacts": [],
        }

    def _git_dirty(self, cwd: Path) -> bool:
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return True
        return result.returncode != 0 or bool(result.stdout.strip())

    def _backfill_candidate(self, *, spec_id: str) -> dict[str, Any]:
        stage_id = f"spec-{spec_id.split('-', 1)[0]}"
        branch = self._stage_branch(spec_id=spec_id, stage_id=stage_id)
        worktree_path = (
            self._repository_root.parent / f"{self._repository_root.name}-{stage_id}"
        ).resolve()
        blockers: list[str] = []
        warnings: list[str] = []
        branch_check = self._git_run(
            self._repository_root,
            ["rev-parse", "--verify", branch],
        )
        if branch_check.returncode != 0:
            blockers.append("missing_branch")
        if worktree_path.exists():
            worktree_branch = self._worktree_branch(worktree_path)
            if worktree_branch is None:
                blockers.append("incompatible_worktree")
            elif worktree_branch != branch:
                blockers.append("worktree_branch_mismatch")
            if self._git_dirty(worktree_path):
                blockers.append("dirty_worktree")
        else:
            warnings.append("missing_worktree")
        return {
            "spec_id": spec_id,
            "stage_id": stage_id,
            "expected_branch": branch,
            "expected_worktree": str(worktree_path),
            "status": "blocked" if blockers else "ready",
            "blockers": blockers,
            "warnings": warnings,
            "would_create": {
                "backlog_candidate": not blockers,
                "stage_candidate": not blockers,
            },
        }

    def _worktree_branch(self, worktree_path: Path) -> str | None:
        result = self._git_run(
            worktree_path,
            ["rev-parse", "--abbrev-ref", "HEAD"],
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def _filtered_items(
        self,
        items: Any,
        filters: dict[str, str | None],
    ) -> list[dict[str, Any]]:
        return [
            dict(item)
            for item in items
            if isinstance(item, dict) and self._item_matches_filters(item, filters)
        ]

    def _item_matches_filters(
        self,
        item: dict[str, Any],
        filters: dict[str, str | None],
    ) -> bool:
        for key in ["stage_id", "spec_id", "handoff_id"]:
            expected = filters.get(key)
            if expected and item.get(key) != expected:
                return False
        expected_status = filters.get("status")
        if expected_status:
            actual = item.get("status") or item.get("state")
            if actual != expected_status:
                return False
        return True

    def _workbench_projection(
        self,
        *,
        backlog: list[dict[str, Any]],
        specs: list[dict[str, Any]],
        stages: list[dict[str, Any]],
        runs: list[dict[str, Any]],
        merges: list[dict[str, Any]],
        promotions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "kind": "codex.devPipelineWorkbenchProjection",
            "version": 1,
            "backlog_items": backlog,
            "materialized_specs": [
                item
                for item in specs
                if item.get("stage_id") or item.get("status") == "materialized"
            ],
            "blocked_imports": [
                item for item in backlog if item.get("status") == "blocked"
            ],
            "active_stages": [
                item for item in stages if item.get("status") == "active"
            ],
            "stage_runs": runs,
            "merge_status": merges,
            "promotion_status": promotions,
        }

    def _require_stage(self, state: dict[str, Any], stage_id: str) -> dict[str, Any]:
        stage = state["stages"].get(stage_id)
        if not stage:
            raise DevPipelineError(
                "unknown_stage", f"Stage {stage_id} is not registered."
            )
        return stage

    def _require_enabled(self) -> None:
        if not self._enabled:
            raise DevPipelineError(
                "dev_pipeline_disabled",
                "The DEV/PROD stage pipeline is disabled by rollout flag.",
            )

    def _require_environment(self, expected: EnvironmentName) -> None:
        if self._environment != expected:
            raise DevPipelineError(
                f"{expected}_environment_required",
                f"This operation is allowed only from {expected.upper()}.",
            )

    def _require_dev_or_control_environment(self) -> None:
        if self._environment not in {"dev", "control"}:
            raise DevPipelineError(
                "dev_or_control_environment_required",
                "This operation is allowed only from DEV or CONTROL.",
            )

    def _require_prod_update_environment(self) -> None:
        if self._environment not in {"prod", "control"}:
            raise DevPipelineError(
                "prod_or_control_environment_required",
                "PROD update gate is allowed only from PROD or CONTROL.",
            )

    def _stage_branch(self, *, spec_id: str, stage_id: str) -> str:
        spec_slug = spec_id.split("-", 1)[1]
        return f"dev/{stage_id}-{spec_slug}"

    def _validate_stage_worktree_path(
        self,
        *,
        stage_id: str,
        worktree_path: str,
    ) -> str:
        resolved = Path(worktree_path).expanduser().resolve()
        expected = (
            (self._repository_root.parent / f"{self._repository_root.name}-{stage_id}")
            .expanduser()
            .resolve()
        )
        configured = (
            Path(self._worktree_path).expanduser().resolve()
            if self._worktree_path
            else None
        )
        if resolved != expected and resolved != configured:
            raise DevPipelineError(
                "unsafe_stage_worktree",
                f"Stage worktree must be {expected}.",
            )
        return str(resolved)

    def _validate_spec_id(self, spec_id: str) -> str:
        spec_id = spec_id.strip()
        if not _SPEC_ID_PATTERN.match(spec_id):
            raise DevPipelineError(
                "invalid_spec_id",
                "spec_id must look like 018-dev-prod-stage-promotion-pipeline.",
            )
        return spec_id

    def _validate_handoff_payload(self, payload: dict[str, Any]) -> None:
        if payload.get("kind") not in {None, "bridge.devHandoff"}:
            raise DevPipelineError(
                "invalid_handoff_kind", "Handoff kind must be bridge.devHandoff."
            )
        expected = {
            "source_environment": "prod",
            "target_environment": "dev",
            "operation": "enqueue_only",
        }
        for key, value in expected.items():
            if payload.get(key) != value:
                raise DevPipelineError(f"invalid_{key}", f"{key} must be {value}.")
        for key in ["title", "problem", "context", "acceptance_criteria"]:
            if not str(payload.get(key) or "").strip():
                raise DevPipelineError(f"missing_{key}", f"{key} is required.")

    def _requires_draft_grant(self, payload: dict[str, Any]) -> bool:
        return True

    def _consume_handoff_draft_grant(
        self,
        state: dict[str, Any],
        *,
        draft_token: str,
        payload_hash: str,
        session_id: str | None,
    ) -> None:
        if not draft_token:
            raise DevPipelineError(
                "dev_handoff_draft_grant_required",
                "Mobile DEV handoff enqueue requires an active /dev-handoff draft grant.",
            )
        token_hash = self._stable_hash({"draft_token": draft_token})
        grant = state["handoff_drafts"].get(token_hash)
        if not grant:
            raise DevPipelineError(
                "dev_handoff_draft_grant_required",
                "Mobile DEV handoff enqueue requires an active /dev-handoff draft grant.",
            )
        if grant.get("status") != "active":
            raise DevPipelineError(
                "dev_handoff_draft_grant_consumed",
                "This /dev-handoff draft grant has already been used.",
            )
        expires_at = str(grant.get("expires_at") or "").strip()
        if expires_at:
            try:
                expires_dt = datetime.fromisoformat(
                    expires_at.replace("Z", "+00:00")
                )
            except ValueError:
                expires_dt = datetime.now(timezone.utc)
            if datetime.now(timezone.utc) > expires_dt:
                grant["status"] = "expired"
                raise DevPipelineError(
                    "dev_handoff_draft_grant_expired",
                    "This /dev-handoff draft grant expired. Run /dev-handoff again.",
                )
        grant_session_id = str(grant.get("session_id") or "").strip() or None
        if grant_session_id and session_id and grant_session_id != session_id:
            raise DevPipelineError(
                "dev_handoff_draft_session_mismatch",
                "This /dev-handoff draft grant belongs to a different session.",
            )
        grant["status"] = "consumed"
        grant["consumed_at"] = _utc_iso()
        grant["payload_hash"] = payload_hash

    def _derive_handoff_title(
        self,
        title: str | None,
        messages: list[dict[str, Any]],
    ) -> str:
        explicit = str(title or "").strip()
        if explicit:
            return explicit[:240]
        latest_user = self._latest_user_text(messages)
        if latest_user:
            compact = " ".join(latest_user.split())
            return compact[:96].rstrip(". ") or "DEV handoff"
        return "DEV handoff"

    def _derive_handoff_problem(
        self,
        problem: str | None,
        messages: list[dict[str, Any]],
    ) -> str:
        explicit = str(problem or "").strip()
        if explicit:
            return explicit[:5000]
        latest_user = self._latest_user_text(messages)
        if latest_user:
            return latest_user[:1200]
        return "PROD needs to pass a reviewed change request into the DEV queue."

    def _derive_handoff_context(
        self,
        context: str | None,
        *,
        session_id: str | None,
        session_title: str | None,
        workspace_path: str | None,
        messages: list[dict[str, Any]],
    ) -> str:
        explicit = str(context or "").strip()
        if explicit:
            return explicit[:20000]
        lines = [
            "Generated by /dev-handoff from PROD for review before queueing to DEV.",
        ]
        if session_id:
            lines.append(f"Session: {session_id}")
        if session_title:
            lines.append(f"Session title: {session_title}")
        if workspace_path:
            lines.append(f"Workspace: {workspace_path}")
        if messages:
            lines.append("")
            lines.append("Recent transcript:")
            for message in messages:
                role = str(message.get("role") or "message").strip()
                label = str(message.get("agent_label") or role).strip()
                content = " ".join(str(message.get("content") or "").split())
                if content:
                    lines.append(f"- {label}: {content[:700]}")
        return "\n".join(lines)[:20000]

    def _derive_handoff_acceptance(
        self,
        acceptance_criteria: str | None,
        title: str,
    ) -> str:
        explicit = str(acceptance_criteria or "").strip()
        if explicit:
            return explicit[:10000]
        return (
            f"- DEV materializes a spec for {title} from this handoff.\n"
            "- The implementation happens only in the DEV stage/worktree.\n"
            "- PROD chat, reading, project/factory creation, and non-bridge repository work continue to function.\n"
            "- Strong bridge modifications remain blocked in PROD and enter DEV through the queue.\n"
            "- Targeted backend and mobile tests pass before promotion is considered."
        )

    def _latest_user_text(self, messages: list[dict[str, Any]]) -> str:
        for message in reversed(messages):
            if str(message.get("role") or "").lower() == "user":
                content = str(message.get("content") or "").strip()
                if content:
                    return content
        return ""

    def _next_proposed_spec_id(self, slug: str) -> str:
        state = self._read_state()
        numbers: list[int] = []
        specs_root = self._repository_root / "specs"
        if specs_root.is_dir():
            for spec_path in specs_root.iterdir():
                if spec_path.is_dir():
                    match = re.match(r"^(\d{3})-", spec_path.name)
                    if match:
                        numbers.append(int(match.group(1)))
        for spec_id in state["specs"]:
            match = re.match(r"^(\d{3})-", str(spec_id))
            if match:
                numbers.append(int(match.group(1)))
        for handoff in state["handoffs"].values():
            payload = handoff.get("payload") or {}
            match = re.match(r"^(\d{3})-", str(payload.get("proposed_spec") or ""))
            if match:
                numbers.append(int(match.group(1)))
        number = max(numbers, default=0) + 1
        return f"{number:03d}-{slug[:80]}"

    def _slugify(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
        slug = re.sub(r"-{2,}", "-", slug)
        return slug or "dev-handoff"

    def _allowed_capabilities(self, capability_key: str) -> list[str]:
        capabilities = list(_CAPABILITIES[capability_key])
        if self._environment == "prod" and not self._prod_handoff_enabled:
            capabilities = [
                item for item in capabilities if item != "enqueue_dev_handoff"
            ]
        return capabilities

    def _denied_capabilities(self, capability_key: str) -> list[str]:
        capabilities = list(_DENIED[capability_key])
        if (
            self._environment == "prod"
            and not self._prod_handoff_enabled
            and "enqueue_dev_handoff" not in capabilities
        ):
            capabilities.append("enqueue_dev_handoff")
        return capabilities

    def _read_state(self) -> dict[str, Any]:
        if not self._state_path.exists():
            return _empty_state()
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _empty_state()
        state = _empty_state()
        state.update({key: raw.get(key, value) for key, value in state.items()})
        return state

    def _write_state(self, state: dict[str, Any]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._state_path.with_suffix(f"{self._state_path.suffix}.tmp")
        tmp_path.write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp_path, self._state_path)

    def _stable_hash(self, payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _handoff_payload_hash(self, payload: dict[str, Any]) -> str:
        comparable = dict(payload)
        comparable.pop("idempotency_key", None)
        return self._stable_hash(comparable)

    def _redact_context(self, value: Any, *, key_name: str | None = None) -> Any:
        if key_name and any(
            marker in key_name.lower() for marker in ["token", "secret", "password"]
        ):
            return "[redacted]"
        if isinstance(value, dict):
            return {
                str(key): self._redact_context(item, key_name=str(key))
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._redact_context(item) for item in value]
        if isinstance(value, str):
            return value[:1000]
        return value


def _empty_state() -> dict[str, Any]:
    return {
        "kind": "codex.devPipelineState",
        "version": _STATE_VERSION,
        "handoffs": {},
        "handoff_drafts": {},
        "backlog": {},
        "specs": {},
        "stages": {},
        "sessions": {},
        "runs": {},
        "merge_queue": {},
        "promotions": {},
        "release_validations": {},
        "prod_updates": {},
        "events": [],
    }


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
