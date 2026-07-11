from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email import policy
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import NamedTemporaryFile
import time
from typing import Any, Protocol

import yaml

from backend.app.application.services.cloudflare_preview_service import (
    CloudflareClient,
    CloudflareLookupResult,
    CloudflareProvisioningPlanner,
    HttpCloudflareClient,
)
from backend.app.infrastructure.config.settings import Settings


_SOURCE_APP_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$")
_D1_DIRECTIVE_RE = re.compile(r"^\s*--\s*codex:d1:(add-column|backfill)\s+(.+?)\s*$")
_INVITE_UPSERT_SQL = """
INSERT INTO preview_invites (
  invite_id,
  token_sha256,
  source_app,
  app_slug,
  single_use,
  email,
  role,
  created_at,
  expires_at,
  used_at,
  revoked_at
) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, NULL, ?10)
ON CONFLICT(invite_id) DO UPDATE SET
  token_sha256 = excluded.token_sha256,
  source_app = excluded.source_app,
  app_slug = excluded.app_slug,
  single_use = excluded.single_use,
  email = excluded.email,
  role = excluded.role,
  created_at = excluded.created_at,
  expires_at = excluded.expires_at,
  revoked_at = excluded.revoked_at
"""


class WebPreviewError(RuntimeError):
    def __init__(self, *, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class WebPreviewPlanInput:
    project_path: str | None = None
    manifest_path: str | None = None
    source_app: str | None = None


@dataclass(frozen=True, slots=True)
class WebPreviewDeployInput(WebPreviewPlanInput):
    confirm_apply: bool = False
    expected_plan_hash: str | None = None


@dataclass(frozen=True, slots=True)
class WebPreviewLifecycleInput:
    preview_id: str
    ttl_seconds: int | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class WebPreviewCommandResult:
    argv: tuple[str, ...]
    cwd: str | None
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    env: dict[str, str] | None = None


class WebPreviewCommandRunner(Protocol):
    def run(
        self,
        argv: tuple[str, ...],
        *,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: float = 0,
    ) -> Any: ...


class SubprocessWebPreviewCommandRunner:
    def run(
        self,
        argv: tuple[str, ...],
        *,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: float = 0,
    ) -> WebPreviewCommandResult:
        try:
            completed = subprocess.run(
                list(argv),
                cwd=str(cwd) if cwd is not None else None,
                env={**os.environ, **env} if env else None,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds if timeout_seconds > 0 else None,
            )
            return WebPreviewCommandResult(
                argv=argv,
                cwd=str(cwd) if cwd is not None else None,
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                env=env,
            )
        except FileNotFoundError as exc:
            return WebPreviewCommandResult(
                argv=argv,
                cwd=str(cwd) if cwd is not None else None,
                exit_code=127,
                stderr=str(exc),
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            return WebPreviewCommandResult(
                argv=argv,
                cwd=str(cwd) if cwd is not None else None,
                exit_code=124,
                stdout=str(exc.stdout or ""),
                stderr=str(exc.stderr or "Command timed out."),
                env=env,
            )


class WebPreviewDeployService:
    def __init__(
        self,
        *,
        settings: Settings,
        client: CloudflareClient | None = None,
        command_runner: WebPreviewCommandRunner | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._command_runner = command_runner or SubprocessWebPreviewCommandRunner()
        self._state_root = Path(settings.web_preview_state_dir).expanduser().resolve()
        self._preview_state_dir = self._state_root / "previews"
        self._invite_state_dir = self._state_root / "invites"
        self._preview_state_dir.mkdir(parents=True, exist_ok=True)
        self._invite_state_dir.mkdir(parents=True, exist_ok=True)

    def plan(self, request: WebPreviewPlanInput) -> dict[str, Any]:
        manifest_path, project_path, manifest = self._load_manifest(request)
        source_app = str(manifest.get("source_app") or request.source_app or "").strip()
        if not source_app:
            raise WebPreviewError(
                code="invalid_manifest",
                message="web preview manifest must include source_app",
            )
        if not _SOURCE_APP_RE.fullmatch(source_app):
            raise WebPreviewError(
                code="invalid_source_app",
                message="source_app must be a safe lowercase slug.",
            )
        if request.source_app and request.source_app != source_app:
            raise WebPreviewError(
                code="source_app_mismatch",
                message="requested source_app does not match manifest source_app",
            )
        planner = CloudflareProvisioningPlanner(settings=self._settings)
        cloudflare_plan = planner.plan_for_manifest(manifest)
        preview_id = _preview_id(source_app)
        worker_script_hash = _worker_script_hash(project_path)
        plan_hash = _plan_hash(manifest, cloudflare_plan, worker_script_hash)
        health_path = str(cloudflare_plan.get("health_path") or "/api/health")
        preview_url = str(manifest.get("stable_url") or "")
        now = datetime.now(UTC).replace(microsecond=0)
        expires_at = now + timedelta(
            seconds=max(1, self._settings.web_preview_default_ttl_seconds),
        )
        payload = {
            "kind": "codex.webPreview",
            "version": 1,
            "preview_id": preview_id,
            "source_app": source_app,
            "project_path": str(project_path),
            "manifest_path": str(manifest_path),
            "status": "planned",
            "preview_url": preview_url,
            "health_url": f"{preview_url.rstrip('/')}{health_path}",
            "plan_hash": plan_hash,
            "worker_script_sha256": worker_script_hash,
            "planned_resources": cloudflare_plan["resources"],
            "applied_resources": [],
            "error": None,
            "logs": [
                {
                    "level": "info",
                    "message": "Preview deploy plan created in dry-run mode.",
                },
            ],
            "created_at": _iso(now),
            "updated_at": _iso(now),
            "expires_at": _iso(expires_at),
            "disabled_at": None,
            "disabled_reason": None,
            "completed_at": None,
            "audit_events": [
                _audit_event(
                    event_type="preview_plan_created",
                    source_app=source_app,
                    actor="bridge",
                    details={"plan_hash": plan_hash},
                ),
            ],
        }
        self._persist_preview(payload)
        return payload

    def deploy(self, request: WebPreviewDeployInput) -> dict[str, Any]:
        _manifest_path, _project_path, pre_manifest = self._load_manifest(request)
        pre_source_app = str(
            pre_manifest.get("source_app") or request.source_app or ""
        ).strip()
        previous = self.get_preview(_preview_id(pre_source_app)) if pre_source_app else None
        planned = self.plan(
            WebPreviewPlanInput(
                project_path=request.project_path,
                manifest_path=request.manifest_path,
                source_app=request.source_app,
            )
        )
        if not self._settings.web_preview_apply_enabled:
            raise WebPreviewError(
                code="apply_disabled",
                message="WEB_PREVIEW_APPLY_ENABLED must be true before apply.",
                status_code=403,
            )
        if not request.confirm_apply:
            raise WebPreviewError(
                code="dry_run_required",
                message="Set confirm_apply=true after reviewing the dry-run plan.",
                status_code=400,
            )
        if not request.expected_plan_hash:
            raise WebPreviewError(
                code="plan_hash_required",
                message="expected_plan_hash is required for apply.",
                status_code=400,
            )
        if request.expected_plan_hash != planned["plan_hash"]:
            raise WebPreviewError(
                code="plan_hash_mismatch",
                message="expected_plan_hash does not match the current plan.",
                status_code=409,
            )
        if (
            previous is not None
            and previous.get("status") == "active"
            and previous.get("plan_hash") == planned["plan_hash"]
            and previous.get("applied_resources")
        ):
            try:
                health_verification = self._verify_preview_health(planned)
            except Exception as exc:
                error = _safe_error(
                    exc,
                    secrets=(
                        self._settings.cloudflare_api_token,
                        self._settings.cloudflare_dns_api_token,
                    ),
                )
                failed = {
                    **previous,
                    "status": "failed",
                    "error": error,
                    "completed_at": _now_iso(),
                    "updated_at": _now_iso(),
                    "logs": [
                        *(previous.get("logs") or []),
                        {
                            "level": "error",
                            "message": error,
                        },
                    ],
                }
                failed = self._with_audit_event(
                    failed,
                    event_type="preview_publish_failed",
                    details={"error": error, "phase": "preview_health_recovery"},
                )
                self._persist_preview(failed)
                raise WebPreviewError(
                    code="deploy_failed",
                    message=error,
                    status_code=500,
                ) from exc
            recovered = {
                **previous,
                "recovery_status": "existing_active_verified",
                "health_verification": health_verification,
                "updated_at": _now_iso(),
                "logs": [
                    *(previous.get("logs") or []),
                    {
                        "level": "info",
                        "message": "Existing active preview matches plan; treating rerun as recovered.",
                    },
                ],
            }
            recovered = self._with_audit_event(
                recovered,
                event_type="preview_recovery_verified",
                details={"plan_hash": planned["plan_hash"]},
            )
            self._persist_preview(recovered)
            return recovered
        self._assert_cloudflare_apply_configured()
        manifest_path, project_path, manifest = self._load_manifest(request)
        recovery_status = None
        if previous is not None and previous.get("status") in {
            "applying",
            "failed",
            "blocked",
        }:
            recovery_status = f"recovering_from_{previous.get('status')}"
        state = {
            **planned,
            "status": "applying",
            "recovery_status": recovery_status,
            "logs": [
                *planned["logs"],
                *(
                    [
                        {
                            "level": "info",
                            "message": (
                                "Recovering interrupted preview publication from "
                                f"{previous.get('status')} state."
                            ),
                        }
                    ]
                    if recovery_status
                    else []
                ),
                {"level": "info", "message": "Apply gate passed; validating artifact."},
            ],
        }
        if recovery_status:
            state = self._with_audit_event(
                state,
                event_type="preview_recovery_started",
                details={
                    "previous_status": previous.get("status") if previous else None,
                    "plan_hash": planned["plan_hash"],
                },
            )
        self._persist_preview(state)
        try:
            self._validate_project_for_apply(project_path, manifest)
            applied = CloudflarePreviewProvisioner(
                settings=self._settings,
                client=self._cloudflare_client(),
                command_runner=self._command_runner,
            ).apply(
                manifest=manifest,
                project_path=project_path,
            )
            health_verification = self._verify_preview_health(planned)
            state = {
                **state,
                "status": "active",
                "applied_resources": applied,
                "health_verification": health_verification,
                "worker_script_verification_status": _worker_verification_status(applied),
                "completed_at": _now_iso(),
                "updated_at": _now_iso(),
                "logs": [
                    *state["logs"],
                    {
                        "level": "info",
                        "message": "Cloudflare preview resources applied.",
                    },
                ],
            }
            state = self._with_audit_event(
                state,
                event_type="preview_publish_succeeded",
                details={"applied_resources": len(applied)},
            )
            self._persist_preview(state)
            invite_sync_summary = self.sync_invites_for_preview(
                str(state["preview_id"]),
            )
            state = {
                **state,
                "invite_sync_summary": invite_sync_summary,
                "updated_at": _now_iso(),
                "logs": [
                    *state["logs"],
                    {
                        "level": "info",
                        "message": (
                            "Invite sync completed: "
                            f"{invite_sync_summary['synced']} synced, "
                            f"{invite_sync_summary['failed']} failed, "
                            f"{invite_sync_summary['not_deployed']} not deployed."
                        ),
                    },
                ],
            }
        except Exception as exc:
            error = _safe_error(
                exc,
                secrets=(
                    self._settings.cloudflare_api_token,
                    self._settings.cloudflare_dns_api_token,
                ),
            )
            state = {
                **state,
                "status": "failed",
                "error": error,
                "completed_at": _now_iso(),
                "updated_at": _now_iso(),
                "logs": [
                    *state["logs"],
                    {
                        "level": "error",
                        "message": error,
                    },
                ],
            }
            state = self._with_audit_event(
                state,
                event_type="preview_publish_failed",
                details={"error": error},
            )
        self._persist_preview(state)
        if state["status"] == "failed":
            raise WebPreviewError(
                code="deploy_failed",
                message=str(state["error"]),
                status_code=500,
            )
        return state

    def _verify_preview_health(self, planned: dict[str, Any]) -> dict[str, Any]:
        preview_url = str(planned.get("preview_url") or "").rstrip("/")
        if not preview_url:
            raise RuntimeError("preview_health_url_missing")
        endpoints = [
            ("web", f"{preview_url}/__preview/health"),
            ("api", f"{preview_url}/api/health"),
        ]
        headers = {"User-Agent": "CodexProjectFactoryPreviewSmoke/1.0"}
        attempts: list[dict[str, Any]] = []
        client = self._cloudflare_client()
        for attempt in range(1, 4):
            current: list[dict[str, Any]] = []
            all_ok = True
            for name, url in endpoints:
                result = client.fetch_url(url, headers=headers)
                payload = result.payload if isinstance(result.payload, dict) else {}
                d1_bound = payload.get("d1_bound") is True
                assets_bound = payload.get("assets_bound") is True
                ok = bool(result.ok and d1_bound and assets_bound)
                all_ok = all_ok and ok
                current.append(
                    {
                        "name": name,
                        "url": url,
                        "ok": ok,
                        "status_code": result.status_code,
                        "d1_bound": payload.get("d1_bound"),
                        "assets_bound": payload.get("assets_bound"),
                        "error": result.error,
                    }
                )
            attempts.append({"attempt": attempt, "checks": current})
            if all_ok:
                return {
                    "status": "passed",
                    "attempts": attempts,
                    "required": {"d1_bound": True, "assets_bound": True},
                }
            if attempt < 3:
                time.sleep(0.5 * attempt)
        latest = attempts[-1]["checks"] if attempts else []
        raise RuntimeError(
            "preview_health_bindings_failed: expected d1_bound=true and "
            f"assets_bound=true from {preview_url}/__preview/health and "
            f"{preview_url}/api/health; latest={latest}"
        )

    def sync_invite(self, invite: dict[str, Any]) -> dict[str, Any]:
        preview = self.get_preview(str(invite.get("preview_id") or ""))
        if preview is None or preview.get("status") != "active":
            return {
                "sync_status": "not_deployed",
                "synced_at": None,
                "sync_error": None,
            }
        try:
            context = self._d1_sync_context(preview)
            result = self._cloudflare_client().execute_d1_sql(
                account_id=context["account_id"],
                database_id=context["database_id"],
                sql=_INVITE_UPSERT_SQL,
                params=_invite_sync_params(invite),
            )
            _raise_if_failed(result, "d1_invite_sync_failed")
            return {
                "sync_status": "synced",
                "synced_at": _now_iso(),
                "sync_error": None,
            }
        except Exception as exc:
            return {
                "sync_status": "failed",
                "synced_at": invite.get("synced_at"),
                "sync_error": _safe_error(
                    exc,
                    secrets=(
                        self._settings.cloudflare_api_token,
                        self._settings.cloudflare_dns_api_token,
                    ),
                ),
            }

    def sync_invites_for_preview(
        self,
        preview_id: str,
        *,
        invite_id: str | None = None,
    ) -> dict[str, Any]:
        summary = {
            "preview_id": preview_id,
            "total": 0,
            "synced": 0,
            "failed": 0,
            "not_deployed": 0,
            "pending": 0,
            "updated_at": _now_iso(),
        }
        for path in sorted(self._invite_state_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if payload.get("preview_id") != preview_id:
                continue
            if invite_id and payload.get("invite_id") != invite_id:
                continue
            summary["total"] += 1
            sync = self.sync_invite(payload)
            payload.update(sync)
            _atomic_write_json(path, payload)
            status = str(sync.get("sync_status") or "pending")
            if status in summary:
                summary[status] += 1
            else:
                summary["pending"] += 1
        return summary

    def get_preview(self, preview_id: str) -> dict[str, Any] | None:
        path = self._preview_state_dir / f"{_safe_id(preview_id)}.json"
        if not path.exists():
            return None
        return self._refresh_preview_lifecycle(
            json.loads(path.read_text(encoding="utf-8"))
        )

    def list_previews(self, *, limit: int = 50) -> tuple[dict[str, Any], ...]:
        previews = []
        for path in self._preview_state_dir.glob("*.json"):
            try:
                previews.append(
                    self._refresh_preview_lifecycle(
                        json.loads(path.read_text(encoding="utf-8"))
                    )
                )
            except (json.JSONDecodeError, OSError):
                continue
        previews.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return tuple(previews[: max(1, min(limit, 200))])

    def disable_preview(self, request: WebPreviewLifecycleInput) -> dict[str, Any]:
        state = self._load_preview_or_raise(request.preview_id)
        now = _now_iso()
        reason = (request.reason or "disabled by operator").strip()
        state = {
            **state,
            "status": "disabled",
            "disabled_at": state.get("disabled_at") or now,
            "disabled_reason": reason,
            "updated_at": now,
            "logs": [
                *(state.get("logs") or []),
                {"level": "warning", "message": f"Preview disabled: {reason}"},
            ],
        }
        state = self._with_audit_event(
            state,
            event_type="preview_disabled",
            details={"reason": reason},
        )
        self._persist_preview(state)
        return state

    def expire_preview(self, request: WebPreviewLifecycleInput) -> dict[str, Any]:
        state = self._load_preview_or_raise(request.preview_id)
        now = _now_iso()
        state = {
            **state,
            "status": "expired",
            "expires_at": now,
            "updated_at": now,
            "logs": [
                *(state.get("logs") or []),
                {"level": "warning", "message": "Preview expired by operator."},
            ],
        }
        state = self._with_audit_event(
            state,
            event_type="preview_expired",
            details={"reason": request.reason or "operator_expire"},
        )
        self._persist_preview(state)
        return state

    def extend_preview(self, request: WebPreviewLifecycleInput) -> dict[str, Any]:
        state = self._load_preview_or_raise(request.preview_id)
        ttl_seconds = max(
            1,
            request.ttl_seconds
            if request.ttl_seconds is not None
            else self._settings.web_preview_default_ttl_seconds,
        )
        now = datetime.now(UTC).replace(microsecond=0)
        expires_at = now + timedelta(seconds=ttl_seconds)
        next_status = "active" if state.get("status") == "expired" else state.get("status")
        state = {
            **state,
            "status": next_status,
            "expires_at": _iso(expires_at),
            "updated_at": _iso(now),
            "logs": [
                *(state.get("logs") or []),
                {"level": "info", "message": f"Preview extended by {ttl_seconds}s."},
            ],
        }
        state = self._with_audit_event(
            state,
            event_type="preview_extended",
            details={"ttl_seconds": ttl_seconds, "expires_at": _iso(expires_at)},
        )
        self._persist_preview(state)
        return state

    def record_audit_event(
        self,
        *,
        preview_id: str,
        event_type: str,
        actor: str = "bridge",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        state = self.get_preview(preview_id)
        if state is None:
            return None
        state = self._with_audit_event(
            state,
            event_type=event_type,
            actor=actor,
            details=details or {},
        )
        state["updated_at"] = _now_iso()
        self._persist_preview(state)
        return state

    def _load_manifest(
        self,
        request: WebPreviewPlanInput,
    ) -> tuple[Path, Path, dict[str, Any]]:
        if request.manifest_path:
            manifest_path = Path(request.manifest_path).expanduser().resolve()
            project_path = (
                Path(request.project_path).expanduser().resolve()
                if request.project_path
                else manifest_path.parents[2]
            )
        elif request.project_path:
            project_path = Path(request.project_path).expanduser().resolve()
            manifest_path = project_path / "deploy/web-preview/web-preview-manifest.yaml"
        else:
            raise WebPreviewError(
                code="manifest_required",
                message="project_path or manifest_path is required.",
            )
        if not manifest_path.is_file():
            raise WebPreviewError(
                code="manifest_not_found",
                message="web preview manifest was not found.",
                status_code=404,
            )
        if not manifest_path.is_relative_to(project_path):
            raise WebPreviewError(
                code="manifest_outside_project",
                message="web preview manifest must be inside project_path.",
            )
        payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise WebPreviewError(
                code="invalid_manifest",
                message="web preview manifest must be a YAML object.",
            )
        return manifest_path, project_path, payload

    def _assert_cloudflare_apply_configured(self) -> None:
        missing = [
            name
            for name, value in (
                ("CLOUDFLARE_API_TOKEN", self._settings.cloudflare_api_token),
                ("CLOUDFLARE_DNS_API_TOKEN", self._settings.cloudflare_dns_api_token),
                ("CLOUDFLARE_ACCOUNT_ID", self._settings.cloudflare_account_id),
                ("CLOUDFLARE_ZONE_ID", self._settings.cloudflare_zone_id),
            )
            if not (value or "").strip()
        ]
        if missing:
            raise WebPreviewError(
                code="cloudflare_configuration_missing",
                message=f"Missing required Cloudflare configuration: {', '.join(missing)}",
                status_code=503,
            )

    def _validate_project_for_apply(
        self,
        project_path: Path,
        manifest: dict[str, Any],
    ) -> None:
        script = project_path / "scripts/validate_web_preview.sh"
        if not script.is_file():
            raise WebPreviewError(
                code="validation_script_missing",
                message="scripts/validate_web_preview.sh is missing.",
            )
        build = manifest.get("build")
        output_dir = (
            build.get("output_dir")
            if isinstance(build, dict)
            else None
        )
        if not output_dir:
            raise WebPreviewError(
                code="build_output_missing",
                message="web preview manifest build.output_dir is missing.",
            )
        env = {
            **os.environ,
            "REQUIRE_WEB_BUILD_OUTPUT": "true",
            "APP_RUNTIME_PROFILE": "preview",
            "API_RUNTIME": "cloudflare_preview",
            "API_BASE_URL": str(
                manifest.get("runtime", {}).get("api_base_url")
                if isinstance(manifest.get("runtime"), dict)
                else "https://preview.nienfos.com"
            ),
            "APP_SLUG": str(manifest.get("source_app") or ""),
        }
        completed = subprocess.run(
            [str(script)],
            cwd=project_path,
            text=True,
            capture_output=True,
            check=False,
            shell=False,
            timeout=120,
            env=env,
        )
        if completed.returncode != 0:
            raise WebPreviewError(
                code="preview_validation_failed",
                message=_safe_error_text(completed.stderr or completed.stdout),
            )

    def _cloudflare_client(self) -> CloudflareClient:
        return self._client or HttpCloudflareClient(
            api_token=self._settings.cloudflare_api_token or "",
            dns_api_token=self._settings.cloudflare_dns_api_token,
            base_url=self._settings.cloudflare_api_base_url,
            timeout_seconds=self._settings.cloudflare_timeout_seconds,
        )

    def _persist_preview(self, payload: dict[str, Any]) -> None:
        preview_id = _safe_id(str(payload["preview_id"]))
        _atomic_write_json(self._preview_state_dir / f"{preview_id}.json", payload)

    def _load_preview_or_raise(self, preview_id: str) -> dict[str, Any]:
        state = self.get_preview(preview_id)
        if state is None:
            raise WebPreviewError(
                code="web_preview_not_found",
                message="Web preview was not found.",
                status_code=404,
            )
        return state

    def _refresh_preview_lifecycle(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("disabled_at"):
            if state.get("status") != "disabled":
                state = {
                    **state,
                    "status": "disabled",
                    "updated_at": _now_iso(),
                }
                self._persist_preview(state)
            return state
        if state.get("status") != "active":
            return state
        expires_at = _parse_iso(str(state.get("expires_at") or ""))
        if expires_at is None or expires_at > datetime.now(UTC):
            return state
        state = {
            **state,
            "status": "expired",
            "updated_at": _now_iso(),
            "logs": [
                *(state.get("logs") or []),
                {"level": "warning", "message": "Preview expired automatically."},
            ],
        }
        state = self._with_audit_event(
            state,
            event_type="preview_expired",
            details={"reason": "expires_at_elapsed"},
        )
        self._persist_preview(state)
        return state

    def _with_audit_event(
        self,
        state: dict[str, Any],
        *,
        event_type: str,
        actor: str = "bridge",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        events = list(state.get("audit_events") or [])
        events.append(
            _audit_event(
                event_type=event_type,
                source_app=str(state.get("source_app") or ""),
                actor=actor,
                details=details or {},
            )
        )
        return {**state, "audit_events": events}

    def _d1_sync_context(self, preview: dict[str, Any]) -> dict[str, str]:
        account_id = (self._settings.cloudflare_account_id or "").strip()
        if not account_id:
            raise RuntimeError("cloudflare_account_id_missing")
        database_id = ""
        for resource in preview.get("applied_resources") or ():
            if isinstance(resource, dict) and resource.get("kind") == "d1_database":
                database_id = str(resource.get("database_id") or "").strip()
                break
        if not database_id:
            raise RuntimeError("d1_database_id_missing")
        return {
            "account_id": account_id,
            "database_id": database_id,
        }


class CloudflarePreviewProvisioner:
    def __init__(
        self,
        *,
        settings: Settings,
        client: CloudflareClient,
        command_runner: WebPreviewCommandRunner | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._command_runner = command_runner or SubprocessWebPreviewCommandRunner()

    def apply(self, *, manifest: dict[str, Any], project_path: Path) -> list[dict[str, Any]]:
        cloudflare = _expect_mapping(manifest, "cloudflare")
        resources = _expect_mapping(cloudflare, "resources")
        account_id = self._settings.cloudflare_account_id or ""
        zone_id = self._settings.cloudflare_zone_id or ""
        source_app = str(manifest.get("source_app") or "")
        base_domain = str(cloudflare.get("base_domain") or "preview.nienfos.com")
        worker_name = str(resources.get("worker_name") or "nienfos-preview-runtime")
        worker_route = str(cloudflare.get("route") or f"{base_domain}/{source_app}/*")
        pages_project = str(resources.get("pages_project") or "nienfos-preview-web")
        d1_database = str(resources.get("d1_database") or "nienfos-preview")
        r2_bucket = resources.get("r2_bucket")
        access = manifest.get("access") if isinstance(manifest.get("access"), dict) else {}
        migrations_dir = str(access.get("migrations_dir") or "")
        d1_resource = self._ensure_d1(account_id=account_id, database_name=d1_database)
        applied = [
            self._ensure_dns_record(
                zone_id=zone_id,
                name=f"{base_domain}",
                target=self._settings.cloudflare_zone_name,
            ),
            d1_resource,
        ]
        if migrations_dir:
            applied.extend(
                self._apply_d1_migrations(
                    account_id=account_id,
                    database_name=d1_database,
                    database_id=str(d1_resource.get("database_id") or ""),
                    migrations_dir=project_path / migrations_dir,
                )
            )
        applied.extend(
            [
                self._ensure_worker(
                    account_id=account_id,
                    worker_name=worker_name,
                    script_path=project_path / "deploy/web-preview/worker/src/index.js",
                    project_path=project_path,
                    source_app=source_app,
                    base_domain=base_domain,
                    worker_route=worker_route,
                    d1_database_name=d1_database,
                    d1_database_id=str(d1_resource.get("database_id") or ""),
                ),
                self._ensure_worker_route(
                    zone_id=zone_id,
                    pattern=worker_route,
                    worker_name=worker_name,
                ),
            ]
        )
        applied.extend(
            [
                self._ensure_pages_project(account_id=account_id, name=pages_project),
            ]
        )
        if r2_bucket:
            applied.append(
                {
                    "kind": "r2_bucket",
                    "name": str(r2_bucket),
                    "status": "skipped",
                    "detail": "R2 apply is gated for a later persistent-assets slice.",
                }
            )
        else:
            applied.append(
                {
                    "kind": "r2_bucket",
                    "name": None,
                    "status": "skipped",
                    "detail": "R2 disabled for this preview manifest.",
                }
            )
        return applied

    def _ensure_dns_record(
        self,
        *,
        zone_id: str,
        name: str,
        target: str,
    ) -> dict[str, Any]:
        existing = self._client.list_dns_records(
            zone_id=zone_id,
            name=name,
            record_type="CNAME",
        )
        _raise_if_failed(existing, "dns_list_failed")
        records = _cloudflare_result_list(existing.payload)
        if records:
            record = records[0]
            record_id = str(record.get("id") or "")
            content = str(record.get("content") or "")
            proxied = bool(record.get("proxied"))
            if content == target and proxied:
                return {"kind": "dns_record", "name": name, "status": "existing"}
            if not record_id:
                raise RuntimeError("dns_record_id_missing")
            updated = self._client.update_dns_record(
                zone_id=zone_id,
                record_id=record_id,
                payload={
                    "type": "CNAME",
                    "name": name,
                    "content": target,
                    "proxied": True,
                },
            )
            _raise_if_failed(updated, "dns_update_failed")
            return {"kind": "dns_record", "name": name, "status": "updated"}
        created = self._client.create_dns_record(
            zone_id=zone_id,
            payload={
                "type": "CNAME",
                "name": name,
                "content": target,
                "proxied": True,
            },
        )
        _raise_if_failed(created, "dns_create_failed")
        return {"kind": "dns_record", "name": name, "status": "created"}

    def _ensure_worker(
        self,
        *,
        account_id: str,
        worker_name: str,
        script_path: Path,
        project_path: Path,
        source_app: str,
        base_domain: str,
        worker_route: str,
        d1_database_name: str,
        d1_database_id: str,
    ) -> dict[str, Any]:
        existing = self._client.get_worker_script(
            account_id=account_id,
            script_name=worker_name,
        )
        if not script_path.is_file():
            raise RuntimeError("worker script source is missing")
        script_content = script_path.read_text(encoding="utf-8")
        worker_metadata = _worker_upload_metadata(
            database_id=d1_database_id,
            api_base_url=f"https://{base_domain}/{source_app}/api",
            source_app=source_app,
        )
        if existing.ok:
            deployed = self._client.deploy_worker_script(
                account_id=account_id,
                script_name=worker_name,
                script_content=script_content,
                worker_format="module",
                metadata=worker_metadata,
            )
            _raise_if_failed(deployed, "worker_update_failed")
            wrangler_deploy = self._deploy_worker_with_wrangler(
                account_id=account_id,
                worker_name=worker_name,
                script_path=script_path,
                project_path=project_path,
                source_app=source_app,
                base_domain=base_domain,
                worker_route=worker_route,
                d1_database_name=d1_database_name,
                d1_database_id=d1_database_id,
            )
            verification = self._verify_worker_script(
                account_id=account_id,
                worker_name=worker_name,
                expected_script_content=script_content,
                allow_transformed=True,
            )
            return {
                "kind": "worker_script",
                "name": worker_name,
                "status": "updated",
                "sha256": hashlib.sha256(script_content.encode("utf-8")).hexdigest(),
                "worker_format": "module",
                "bindings": sorted({*_worker_binding_names(worker_metadata), "ASSETS"}),
                "wrangler_deploy": wrangler_deploy,
                **verification,
            }
        if existing.status_code not in (404, None):
            _raise_if_failed(existing, "worker_lookup_failed")
        deployed = self._client.deploy_worker_script(
            account_id=account_id,
            script_name=worker_name,
            script_content=script_content,
            worker_format="module",
            metadata=worker_metadata,
        )
        _raise_if_failed(deployed, "worker_deploy_failed")
        wrangler_deploy = self._deploy_worker_with_wrangler(
            account_id=account_id,
            worker_name=worker_name,
            script_path=script_path,
            project_path=project_path,
            source_app=source_app,
            base_domain=base_domain,
            worker_route=worker_route,
            d1_database_name=d1_database_name,
            d1_database_id=d1_database_id,
        )
        verification = self._verify_worker_script(
            account_id=account_id,
            worker_name=worker_name,
            expected_script_content=script_content,
            allow_transformed=True,
        )
        return {
            "kind": "worker_script",
            "name": worker_name,
            "status": "created",
            "sha256": hashlib.sha256(script_content.encode("utf-8")).hexdigest(),
            "worker_format": "module",
            "bindings": sorted({*_worker_binding_names(worker_metadata), "ASSETS"}),
            "wrangler_deploy": wrangler_deploy,
            **verification,
        }

    def _verify_worker_script(
        self,
        *,
        account_id: str,
        worker_name: str,
        expected_script_content: str,
        allow_transformed: bool = False,
    ) -> dict[str, Any]:
        expected_sha = hashlib.sha256(expected_script_content.encode("utf-8")).hexdigest()
        remote = self._client.get_worker_script(
            account_id=account_id,
            script_name=worker_name,
        )
        _raise_if_failed(remote, "worker_verify_lookup_failed")
        remote_script = _worker_script_content(remote.payload)
        if remote_script is None:
            raise RuntimeError("worker_verify_missing_remote_script")
        remote_sha = hashlib.sha256(remote_script.encode("utf-8")).hexdigest()
        if remote_sha != expected_sha:
            if allow_transformed:
                return {
                    "verified": True,
                    "verification_status": "verified_transformed",
                    "remote_sha256": remote_sha,
                    "expected_sha256": expected_sha,
                }
            raise RuntimeError(
                "worker_verify_hash_mismatch: "
                f"expected {expected_sha}, got {remote_sha}"
            )
        return {
            "verified": True,
            "verification_status": "verified",
            "remote_sha256": remote_sha,
        }

    def _deploy_worker_with_wrangler(
        self,
        *,
        account_id: str,
        worker_name: str,
        script_path: Path,
        project_path: Path,
        source_app: str,
        base_domain: str,
        worker_route: str,
        d1_database_name: str,
        d1_database_id: str,
    ) -> dict[str, Any]:
        if not d1_database_id:
            raise RuntimeError("d1_database_id_missing")
        assets_dir = project_path / "build" / "web-preview" / source_app
        if not assets_dir.is_dir():
            raise RuntimeError("worker_assets_build_missing")
        config_path = _write_generated_wrangler_config(
            project_path=project_path,
            account_id=account_id,
            worker_name=worker_name,
            script_path=script_path,
            assets_dir=assets_dir,
            source_app=source_app,
            base_domain=base_domain,
            worker_route=worker_route,
            zone_name=self._settings.cloudflare_zone_name,
            d1_database_name=d1_database_name,
            d1_database_id=d1_database_id,
        )
        env = {
            "CLOUDFLARE_API_TOKEN": self._settings.cloudflare_api_token or "",
            "CLOUDFLARE_ACCOUNT_ID": account_id,
        }
        result = self._command_runner.run(
            ("wrangler", "deploy", "--config", str(config_path)),
            cwd=project_path,
            env={key: value for key, value in env.items() if value},
            timeout_seconds=300,
        )
        exit_code = int(getattr(result, "exit_code", 1))
        if exit_code != 0:
            stderr = _summarize_text(
                _safe_error_text(
                    str(getattr(result, "stderr", "")),
                    secrets=(self._settings.cloudflare_api_token,),
                )
            )
            stdout = _summarize_text(
                _safe_error_text(
                    str(getattr(result, "stdout", "")),
                    secrets=(self._settings.cloudflare_api_token,),
                )
            )
            raise RuntimeError(
                "worker_wrangler_deploy_failed: "
                f"exit_code={exit_code} stdout={stdout} stderr={stderr}"
            )
        return {
            "status": "applied",
            "argv": list(getattr(result, "argv", ())),
            "cwd": str(getattr(result, "cwd", str(project_path)) or project_path),
            "exit_code": exit_code,
            "stdout_summary": _summarize_text(
                _safe_error_text(
                    str(getattr(result, "stdout", "")),
                    secrets=(self._settings.cloudflare_api_token,),
                )
            ),
            "stderr_summary": _summarize_text(
                _safe_error_text(
                    str(getattr(result, "stderr", "")),
                    secrets=(self._settings.cloudflare_api_token,),
                )
            ),
            "env_keys": sorted((getattr(result, "env", None) or {}).keys()),
            "config_path": str(config_path),
        }

    def _ensure_worker_route(
        self,
        *,
        zone_id: str,
        pattern: str,
        worker_name: str,
    ) -> dict[str, Any]:
        existing = self._client.list_worker_routes(zone_id=zone_id, pattern=pattern)
        _raise_if_failed(existing, "worker_route_list_failed")
        routes = _cloudflare_result_list(existing.payload)
        payload = {"pattern": pattern, "script": worker_name}
        if routes:
            route = routes[0]
            route_id = str(route.get("id") or "")
            if route.get("script") == worker_name:
                return {"kind": "worker_route", "name": pattern, "status": "existing"}
            if not route_id:
                raise RuntimeError("worker_route_id_missing")
            updated = self._client.update_worker_route(
                zone_id=zone_id,
                route_id=route_id,
                payload=payload,
            )
            _raise_if_failed(updated, "worker_route_update_failed")
            return {"kind": "worker_route", "name": pattern, "status": "updated"}
        created = self._client.create_worker_route(zone_id=zone_id, payload=payload)
        _raise_if_failed(created, "worker_route_create_failed")
        return {"kind": "worker_route", "name": pattern, "status": "created"}

    def _ensure_d1(self, *, account_id: str, database_name: str) -> dict[str, Any]:
        existing = self._client.list_d1_databases(account_id)
        _raise_if_failed(existing, "d1_list_failed")
        for item in _cloudflare_result_list(existing.payload):
            if isinstance(item, dict) and item.get("name") == database_name:
                return {
                    "kind": "d1_database",
                    "name": database_name,
                    "status": "existing",
                    "database_id": _d1_database_id(item),
                }
        created = self._client.create_d1_database(
            account_id=account_id,
            name=database_name,
        )
        _raise_if_failed(created, "d1_create_failed")
        return {
            "kind": "d1_database",
            "name": database_name,
            "status": "created",
            "database_id": _d1_database_id(_cloudflare_result(created.payload)),
        }

    def _apply_d1_migrations(
        self,
        *,
        account_id: str,
        database_name: str,
        database_id: str,
        migrations_dir: Path,
    ) -> list[dict[str, Any]]:
        if not database_id:
            raise RuntimeError("d1_database_id_missing")
        if not migrations_dir.is_dir():
            raise RuntimeError("d1_migrations_missing")
        applied: list[dict[str, Any]] = []
        for migration in sorted(migrations_dir.glob("*.sql")):
            sql = migration.read_text(encoding="utf-8")
            directive_events = self._apply_d1_schema_directives(
                account_id=account_id,
                database_id=database_id,
                sql=sql,
            )
            executable_sql = _d1_sql_without_directives(sql)
            if _d1_sql_has_executable_statements(executable_sql):
                result = self._client.execute_d1_sql(
                    account_id=account_id,
                    database_id=database_id,
                    sql=executable_sql,
                )
                _raise_if_failed(result, "d1_migration_failed")
            applied.append(
                {
                    "kind": "d1_migration",
                    "name": migration.name,
                    "database": database_name,
                    "status": "applied",
                    "schema_evolution": directive_events,
                }
            )
        if not applied:
            raise RuntimeError("d1_migrations_missing")
        return applied

    def _apply_d1_schema_directives(
        self,
        *,
        account_id: str,
        database_id: str,
        sql: str,
    ) -> list[dict[str, str]]:
        events: list[dict[str, str]] = []
        known_columns: dict[str, set[str]] = {}

        def columns_for(table: str) -> set[str]:
            if table not in known_columns:
                known_columns[table] = self._d1_table_columns(
                    account_id=account_id,
                    database_id=database_id,
                    table=table,
                )
            return known_columns[table]

        for line in sql.splitlines():
            match = _D1_DIRECTIVE_RE.match(line)
            if not match:
                continue
            action, payload = match.groups()
            if action == "add-column":
                parts = payload.split(None, 2)
                if len(parts) != 3:
                    raise RuntimeError(f"d1_invalid_add_column_directive:{payload}")
                table, column, definition = parts
                columns = columns_for(table)
                if column in columns:
                    events.append(
                        {
                            "action": "add-column",
                            "table": table,
                            "column": column,
                            "status": "skipped_existing",
                        }
                    )
                    continue
                result = self._client.execute_d1_sql(
                    account_id=account_id,
                    database_id=database_id,
                    sql=f"ALTER TABLE {table} ADD COLUMN {column} {definition}",
                )
                _raise_if_failed(result, "d1_schema_evolution_failed")
                columns.add(column)
                events.append(
                    {
                        "action": "add-column",
                        "table": table,
                        "column": column,
                        "status": "applied",
                    }
                )
                continue
            if action == "backfill":
                parts = payload.split(None, 3)
                if len(parts) != 4:
                    raise RuntimeError(f"d1_invalid_backfill_directive:{payload}")
                table, column, value, predicate = parts
                if column not in columns_for(table):
                    raise RuntimeError(f"d1_backfill_column_missing:{table}.{column}")
                result = self._client.execute_d1_sql(
                    account_id=account_id,
                    database_id=database_id,
                    sql=f"UPDATE {table} SET {column} = {value} WHERE {predicate}",
                )
                _raise_if_failed(result, "d1_schema_backfill_failed")
                events.append(
                    {
                        "action": "backfill",
                        "table": table,
                        "column": column,
                        "status": "applied",
                    }
                )
        return events

    def _d1_table_columns(
        self,
        *,
        account_id: str,
        database_id: str,
        table: str,
    ) -> set[str]:
        result = self._client.execute_d1_sql(
            account_id=account_id,
            database_id=database_id,
            sql=f"PRAGMA table_info({table})",
        )
        _raise_if_failed(result, "d1_schema_introspection_failed")
        return _d1_column_names(result.payload)

    def _ensure_pages_project(self, *, account_id: str, name: str) -> dict[str, Any]:
        existing = self._client.get_pages_project(
            account_id=account_id,
            project_name=name,
        )
        if existing.ok:
            return {"kind": "pages_project", "name": name, "status": "existing"}
        if existing.status_code not in (404, None):
            _raise_if_failed(existing, "pages_lookup_failed")
        created = self._client.create_pages_project(account_id=account_id, name=name)
        _raise_if_failed(created, "pages_create_failed")
        return {"kind": "pages_project", "name": name, "status": "created"}


def _preview_id(source_app: str) -> str:
    return f"wp-{_safe_id(source_app)}"


def _safe_id(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in value)
    return safe.strip("-") or "preview"


def _plan_hash(
    manifest: dict[str, Any],
    cloudflare_plan: dict[str, Any],
    worker_script_hash: str | None = None,
) -> str:
    material = {
        "source_app": manifest.get("source_app"),
        "stable_url": manifest.get("stable_url"),
        "runtime": manifest.get("runtime"),
        "cloudflare": manifest.get("cloudflare"),
        "resources": cloudflare_plan.get("resources"),
        "runtime_type": cloudflare_plan.get("runtime_type"),
        "health_path": cloudflare_plan.get("health_path"),
        "worker_script_sha256": worker_script_hash,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _worker_script_hash(project_path: Path) -> str | None:
    script = project_path / "deploy/web-preview/worker/src/index.js"
    if not script.is_file():
        return None
    return hashlib.sha256(script.read_bytes()).hexdigest()


def _worker_script_content(payload: dict[str, Any] | list[Any] | None) -> str | None:
    if isinstance(payload, dict):
        raw = payload.get("raw")
        if isinstance(raw, str):
            content_type = payload.get("content_type")
            if isinstance(content_type, str) and "multipart/" in content_type.lower():
                multipart_script = _worker_script_from_multipart(raw, content_type)
                if multipart_script is not None:
                    return multipart_script
            return raw
        result = payload.get("result")
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            script = result.get("script") or result.get("content")
            if isinstance(script, str):
                return script
    return None


def _worker_script_from_multipart(raw: str, content_type: str) -> str | None:
    message_bytes = (
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n{raw}"
    ).encode("utf-8")
    message = BytesParser(policy=policy.default).parsebytes(message_bytes)
    if not message.is_multipart():
        return None
    fallback: str | None = None
    for part in message.iter_parts():
        disposition = str(part.get("content-disposition") or "")
        part_content_type = str(part.get_content_type() or "")
        content = part.get_content()
        if isinstance(content, bytes):
            content = content.decode(part.get_content_charset() or "utf-8")
        if not isinstance(content, str):
            continue
        if 'name="index.js"' in disposition or 'filename="index.js"' in disposition:
            return content
        if part_content_type == "application/javascript+module":
            fallback = content
    return fallback


def _worker_verification_status(applied: list[dict[str, Any]]) -> str | None:
    for item in applied:
        if item.get("kind") == "worker_script":
            return str(item.get("verification_status") or "unverified")
    return None


def _worker_upload_metadata(
    *,
    database_id: str,
    api_base_url: str,
    source_app: str,
) -> dict[str, Any]:
    bindings: list[dict[str, Any]] = [
        {
            "type": "d1",
            "name": "PREVIEW_DB",
            "id": database_id,
        },
        {
            "type": "plain_text",
            "name": "APP_RUNTIME_PROFILE",
            "text": "preview",
        },
        {
            "type": "plain_text",
            "name": "API_RUNTIME",
            "text": "cloudflare_preview",
        },
        {
            "type": "plain_text",
            "name": "API_BASE_URL",
            "text": api_base_url,
        },
        {
            "type": "plain_text",
            "name": "APP_SLUG",
            "text": source_app,
        },
    ]
    return {
        "compatibility_date": "2026-07-01",
        "bindings": bindings,
    }


def _worker_binding_names(metadata: dict[str, Any]) -> list[str]:
    bindings = metadata.get("bindings")
    if not isinstance(bindings, list):
        return []
    return sorted(
        str(item.get("name"))
        for item in bindings
        if isinstance(item, dict) and item.get("name")
    )


def _write_generated_wrangler_config(
    *,
    project_path: Path,
    account_id: str,
    worker_name: str,
    script_path: Path,
    assets_dir: Path,
    source_app: str,
    base_domain: str,
    worker_route: str,
    zone_name: str,
    d1_database_name: str,
    d1_database_id: str,
) -> Path:
    config_path = project_path / ".codex" / "factory" / "cloudflare" / "wrangler.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(
        [
            "# Generated by deterministic Project Factory init. Do not put secrets here.",
            f'name = "{_toml_escape(worker_name)}"',
            f'account_id = "{_toml_escape(account_id)}"',
            f'main = "{_toml_escape(str(script_path.resolve()))}"',
            'compatibility_date = "2026-07-01"',
            "workers_dev = false",
            "",
            "routes = [",
            (
                f'  {{ pattern = "{_toml_escape(worker_route)}", '
                f'zone_name = "{_toml_escape(zone_name)}" }}'
            ),
            "]",
            "",
            "[[d1_databases]]",
            'binding = "PREVIEW_DB"',
            f'database_name = "{_toml_escape(d1_database_name)}"',
            f'database_id = "{_toml_escape(d1_database_id)}"',
            "",
            "[assets]",
            'binding = "ASSETS"',
            f'directory = "{_toml_escape(str(assets_dir.resolve()))}"',
            "run_worker_first = true",
            "",
            "[vars]",
            'PREVIEW_ACCESS_MODE = "invite_token"',
            'APP_RUNTIME_PROFILE = "preview"',
            'API_RUNTIME = "cloudflare_preview"',
            f'APP_SLUG = "{_toml_escape(source_app)}"',
            (
                'API_BASE_URL = '
                f'"{_toml_escape(f"https://{base_domain}/{source_app}/api")}"'
            ),
            "",
        ]
    )
    config_path.write_text(content, encoding="utf-8")
    return config_path


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _summarize_text(value: str, *, limit: int = 600) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."


def _d1_sql_without_directives(sql: str) -> str:
    return "\n".join(
        line for line in sql.splitlines() if not _D1_DIRECTIVE_RE.match(line)
    ).strip()


def _d1_sql_has_executable_statements(sql: str) -> bool:
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            return True
    return False


def _d1_column_names(payload: dict[str, Any] | list[Any] | None) -> set[str]:
    rows: Any = payload
    if isinstance(payload, dict):
        rows = payload.get("result") or payload.get("results") or []
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        first = rows[0]
        if isinstance(first.get("results"), list):
            rows = first["results"]
        elif isinstance(first.get("result"), list):
            rows = first["result"]
    if not isinstance(rows, list):
        return set()
    return {
        str(row["name"])
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    }


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _audit_event(
    *,
    event_type: str,
    source_app: str,
    actor: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    timestamp = _now_iso()
    material = json.dumps(
        {
            "event_type": event_type,
            "source_app": source_app,
            "actor": actor,
            "details": details,
            "created_at": timestamp,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "event_id": f"wpa-{hashlib.sha256(material.encode()).hexdigest()[:16]}",
        "source_app": source_app,
        "app_slug": source_app,
        "event_type": event_type,
        "actor": actor,
        "details": details,
        "created_at": timestamp,
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as tmp:
        json.dump(payload, tmp, indent=2, sort_keys=True)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _expect_mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise RuntimeError(f"manifest {key} must be an object")
    return value


def _cloudflare_result_list(payload: dict[str, Any] | list[Any] | None) -> list[Any]:
    if isinstance(payload, dict):
        result = payload.get("result")
        return result if isinstance(result, list) else []
    return payload if isinstance(payload, list) else []


def _cloudflare_result(payload: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    result = payload.get("result")
    return result if isinstance(result, dict) else {}


def _d1_database_id(payload: dict[str, Any]) -> str:
    for key in ("uuid", "id", "database_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _invite_sync_params(invite: dict[str, Any]) -> list[Any]:
    return [
        str(invite.get("invite_id") or ""),
        str(invite.get("token_sha256") or ""),
        str(invite.get("source_app") or ""),
        str(invite.get("app_slug") or invite.get("source_app") or ""),
        1 if invite.get("single_use", True) else 0,
        invite.get("email"),
        str(invite.get("role") or "admin"),
        str(invite.get("created_at") or ""),
        str(invite.get("expires_at") or ""),
        invite.get("revoked_at"),
    ]


def _raise_if_failed(result: CloudflareLookupResult, code: str) -> None:
    if result.ok:
        return
    raise RuntimeError(f"{code}: {_safe_error_text(result.error or 'Cloudflare request failed')}")


def _safe_error(
    exc: Exception,
    *,
    secrets: tuple[str | None, ...] = (),
) -> str:
    return _safe_error_text(str(exc), secrets=secrets)


def _safe_error_text(
    value: str,
    *,
    secrets: tuple[str | None, ...] = (),
) -> str:
    redacted = value.replace("Bearer ", "Bearer [redacted] ")
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[redacted]")
    for marker in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_DNS_API_TOKEN"):
        redacted = redacted.replace(marker, marker)
    return redacted[:1000]
