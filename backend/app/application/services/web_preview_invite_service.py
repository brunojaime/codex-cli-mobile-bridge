from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import base64
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from html import escape
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import smtplib
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
import urllib.error
import urllib.request

from backend.app.application.services.web_preview_deploy_service import (
    WebPreviewDeployService,
)
from backend.app.infrastructure.config.settings import Settings


WEB_PREVIEW_INVITE_AUDIENCE = "codex.web-preview"
WEB_PREVIEW_INVITE_SCOPE = "web_preview:access"


class WebPreviewInviteError(RuntimeError):
    def __init__(self, *, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class WebPreviewInviteCreateInput:
    preview_id: str
    ttl_seconds: int | None = None
    single_use: bool = True
    email: str | None = None
    role: str = "admin"


@dataclass(frozen=True, slots=True)
class WebPreviewInviteDeliveryResult:
    status: str
    provider: str
    delivered_at: str | None = None
    error: str | None = None
    manual_delivery_required: bool = False
    provider_message_id: str | None = None


SUPPORTED_WEB_PREVIEW_EMAIL_PROVIDERS = {
    "disabled",
    "manual",
    "smtp",
    "cloudflare_email",
}


class WebPreviewInviteService:
    def __init__(
        self,
        *,
        settings: Settings,
        preview_service: WebPreviewDeployService,
    ) -> None:
        self._settings = settings
        self._preview_service = preview_service
        self._state_root = Path(settings.web_preview_state_dir).expanduser().resolve()
        self._invite_state_dir = self._state_root / "invites"
        self._invite_state_dir.mkdir(parents=True, exist_ok=True)

    def email_delivery_preflight(self) -> dict[str, Any]:
        provider = str(self._settings.web_preview_email_provider or "").strip()
        sender = (self._settings.web_preview_email_from or "").strip()
        endpoint = (self._settings.web_preview_email_endpoint or "").strip()
        token = (self._settings.web_preview_email_api_token or "").strip()
        timeout = self._settings.web_preview_smtp_timeout_seconds
        checks: dict[str, dict[str, Any]] = {}
        errors: list[str] = []

        provider_supported = provider in SUPPORTED_WEB_PREVIEW_EMAIL_PROVIDERS
        checks["provider"] = {
            "ok": provider_supported,
            "value": provider or None,
        }
        if not provider_supported:
            errors.append(f"Unsupported web preview email provider: {provider or '<empty>'}")

        timeout_ok = timeout > 0
        checks["timeout"] = {"ok": timeout_ok, "seconds": timeout}
        if not timeout_ok:
            errors.append("WEB_PREVIEW_SMTP_TIMEOUT_SECONDS must be positive.")

        if provider in {"disabled", "manual"}:
            return {
                "kind": "codex.webPreviewInviteEmailPreflight",
                "version": 1,
                "provider": provider,
                "status": "manual_fallback",
                "ready": False,
                "manual_delivery_required": True,
                "checks": checks,
                "errors": errors,
            }

        if provider == "smtp":
            sender_ok = _is_valid_email_address(sender)
            host = (self._settings.web_preview_smtp_host or "").strip()
            checks["from_address"] = {"ok": sender_ok, "value": sender or None}
            checks["smtp_host"] = {"ok": bool(host), "configured": bool(host)}
            if not sender_ok:
                errors.append("WEB_PREVIEW_EMAIL_FROM must be a valid email address.")
            if not host:
                errors.append("WEB_PREVIEW_SMTP_HOST is required.")
            status = "ready" if not errors else "manual_fallback"
            return {
                "kind": "codex.webPreviewInviteEmailPreflight",
                "version": 1,
                "provider": provider,
                "status": status,
                "ready": status == "ready",
                "manual_delivery_required": status != "ready",
                "checks": checks,
                "errors": errors,
            }

        if provider == "cloudflare_email":
            sender_ok = _is_valid_email_address(sender)
            endpoint_ok = _is_valid_http_endpoint(endpoint)
            checks["from_address"] = {"ok": sender_ok, "value": sender or None}
            checks["endpoint"] = {
                "ok": endpoint_ok,
                "configured": bool(endpoint),
                "value": _redact_url(endpoint) if endpoint else None,
            }
            checks["api_token"] = {"ok": bool(token), "configured": bool(token)}
            if not sender:
                errors.append("WEB_PREVIEW_EMAIL_FROM is required.")
            elif not sender_ok:
                errors.append("WEB_PREVIEW_EMAIL_FROM must be a valid email address.")
            if not endpoint:
                errors.append("WEB_PREVIEW_EMAIL_ENDPOINT is required.")
            elif not endpoint_ok:
                errors.append("WEB_PREVIEW_EMAIL_ENDPOINT must be an http(s) URL.")
            if not token:
                errors.append("WEB_PREVIEW_EMAIL_API_TOKEN is required.")
            if sender and endpoint and token and (not sender_ok or not endpoint_ok or not timeout_ok):
                status = "misconfigured"
            else:
                status = "ready" if not errors else "manual_fallback"
            return {
                "kind": "codex.webPreviewInviteEmailPreflight",
                "version": 1,
                "provider": provider,
                "status": status,
                "ready": status == "ready",
                "manual_delivery_required": status != "ready",
                "checks": checks,
                "errors": errors,
            }

        return {
            "kind": "codex.webPreviewInviteEmailPreflight",
            "version": 1,
            "provider": provider,
            "status": "misconfigured",
            "ready": False,
            "manual_delivery_required": True,
            "checks": checks,
            "errors": errors,
        }

    def create_invite(self, request: WebPreviewInviteCreateInput) -> dict[str, Any]:
        secret = self._require_secret()
        preview = self._preview_service.get_preview(request.preview_id)
        if preview is None:
            raise WebPreviewInviteError(
                code="web_preview_not_found",
                message="Web preview was not found.",
                status_code=404,
            )
        self._assert_preview_accepts_invites(preview)
        email = _normalize_email(request.email)
        role = _normalize_role(request.role)
        self._assert_not_duplicate_active_invite(
            preview_id=request.preview_id,
            email=email,
        )
        ttl_seconds = self._ttl_seconds(request.ttl_seconds)
        now = datetime.now(UTC).replace(microsecond=0)
        expires_at = now + timedelta(seconds=ttl_seconds)
        invite_id = f"wpi-{secrets.token_urlsafe(12)}"
        source_app = str(preview.get("source_app") or "")
        payload = {
            "aud": WEB_PREVIEW_INVITE_AUDIENCE,
            "scope": WEB_PREVIEW_INVITE_SCOPE,
            "preview_id": str(preview.get("preview_id") or request.preview_id),
            "source_app": source_app,
            "app_slug": source_app,
            "invite_id": invite_id,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        token = sign_web_preview_invite(secret=secret, payload=payload)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        preview_url = str(preview.get("preview_url") or "").rstrip("/")
        invite_url = f"{preview_url}/__preview/access?token={quote(token)}"
        metadata = {
            "kind": "codex.webPreviewInvite",
            "version": 1,
            "invite_id": invite_id,
            "preview_id": payload["preview_id"],
            "source_app": source_app,
            "app_slug": source_app,
            "audience": WEB_PREVIEW_INVITE_AUDIENCE,
            "scope": WEB_PREVIEW_INVITE_SCOPE,
            "created_at": _iso(now),
            "expires_at": _iso(expires_at),
            "email": email,
            "role": role,
            "single_use": request.single_use,
            "used_at": None,
            "revoked_at": None,
            "expired_at": None,
            "resend_count": 0,
            "last_sent_at": None,
            "email_provider": self._settings.web_preview_email_provider,
            "email_delivery_preflight": self.email_delivery_preflight(),
            "email_delivery_status": "not_requested" if email is None else "pending",
            "email_delivery_error": None,
            "email_provider_message_id": None,
            "manual_delivery_required": email is None,
            "sync_status": "not_deployed",
            "synced_at": None,
            "sync_error": None,
            "token_sha256": token_hash,
        }
        _atomic_write_json(self._invite_state_dir / f"{invite_id}.json", metadata)
        metadata = self._sync_and_persist(metadata)
        result = {
            **metadata,
            "invite_url": invite_url,
            "token": token,
        }
        result = self._deliver_and_persist(result)
        self._preview_service.record_audit_event(
            preview_id=request.preview_id,
            event_type="invite_created",
            details={
                "invite_id": invite_id,
                "email": email,
                "role": role,
                "expires_at": _iso(expires_at),
            },
        )
        return result

    def list_invites(self, preview_id: str) -> tuple[dict[str, Any], ...]:
        invites = []
        for path in self._invite_state_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if payload.get("preview_id") == preview_id:
                invites.append(payload)
        invites.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return tuple(invites)

    def revoke_invite(self, *, preview_id: str, invite_id: str) -> dict[str, Any]:
        path = self._invite_state_dir / f"{invite_id}.json"
        if not path.is_file():
            raise WebPreviewInviteError(
                code="web_preview_invite_not_found",
                message="Web preview invite was not found.",
                status_code=404,
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("preview_id") != preview_id:
            raise WebPreviewInviteError(
                code="web_preview_invite_not_found",
                message="Web preview invite was not found.",
                status_code=404,
            )
        if payload.get("revoked_at") is None:
            payload["revoked_at"] = _iso(datetime.now(UTC))
            _atomic_write_json(path, payload)
        payload = self._sync_and_persist(payload)
        self._preview_service.record_audit_event(
            preview_id=preview_id,
            event_type="invite_revoked",
            details={"invite_id": invite_id, "revoked_at": payload.get("revoked_at")},
        )
        return payload

    def expire_invite(self, *, preview_id: str, invite_id: str) -> dict[str, Any]:
        payload = self._load_invite(preview_id=preview_id, invite_id=invite_id)
        now = _iso(datetime.now(UTC))
        payload["expires_at"] = now
        payload["expired_at"] = now
        _atomic_write_json(self._invite_state_dir / f"{invite_id}.json", payload)
        payload = self._sync_and_persist(payload)
        self._preview_service.record_audit_event(
            preview_id=preview_id,
            event_type="invite_expired",
            details={"invite_id": invite_id, "expired_at": payload.get("expired_at")},
        )
        return payload

    def resend_invite(
        self,
        *,
        preview_id: str,
        invite_id: str,
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        secret = self._require_secret()
        payload = self._load_invite(preview_id=preview_id, invite_id=invite_id)
        if payload.get("revoked_at"):
            raise WebPreviewInviteError(
                code="web_preview_invite_revoked",
                message="Revoked invites cannot be resent.",
                status_code=409,
            )
        preview = self._preview_service.get_preview(preview_id)
        if preview is None:
            raise WebPreviewInviteError(
                code="web_preview_not_found",
                message="Web preview was not found.",
                status_code=404,
            )
        self._assert_preview_accepts_invites(preview)
        now = datetime.now(UTC).replace(microsecond=0)
        expires_at = now + timedelta(seconds=self._ttl_seconds(ttl_seconds))
        source_app = str(payload.get("source_app") or preview.get("source_app") or "")
        token_payload = {
            "aud": WEB_PREVIEW_INVITE_AUDIENCE,
            "scope": WEB_PREVIEW_INVITE_SCOPE,
            "preview_id": preview_id,
            "source_app": source_app,
            "app_slug": source_app,
            "invite_id": invite_id,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        token = sign_web_preview_invite(secret=secret, payload=token_payload)
        payload.update(
            {
                "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
                "expires_at": _iso(expires_at),
                "expired_at": None,
                "resend_count": int(payload.get("resend_count") or 0) + 1,
                "last_sent_at": _iso(now),
                "email_delivery_status": (
                    "pending" if payload.get("email") else "not_requested"
                ),
                "email_delivery_error": None,
            }
        )
        payload = self._sync_and_persist(payload)
        preview_url = str(preview.get("preview_url") or "").rstrip("/")
        result = {
            **payload,
            "invite_url": f"{preview_url}/__preview/access?token={quote(token)}",
            "token": token,
        }
        result = self._deliver_and_persist(result)
        self._preview_service.record_audit_event(
            preview_id=preview_id,
            event_type="invite_resent",
            details={
                "invite_id": invite_id,
                "resend_count": result.get("resend_count"),
                "expires_at": result.get("expires_at"),
            },
        )
        return result

    def sync_invite(self, *, preview_id: str, invite_id: str) -> dict[str, Any]:
        payload = self._load_invite(preview_id=preview_id, invite_id=invite_id)
        return self._sync_and_persist(payload)

    def verify_token(
        self,
        token: str,
        *,
        source_app: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        secret = self._require_secret()
        payload = verify_web_preview_invite(
            secret=secret,
            token=token,
            source_app=source_app,
            now=now,
        )
        return payload

    def _require_secret(self) -> str:
        secret = (self._settings.web_preview_invite_secret or "").strip()
        if not secret:
            raise WebPreviewInviteError(
                code="web_preview_invite_secret_missing",
                message="WEB_PREVIEW_INVITE_SECRET must be configured to create invites.",
                status_code=503,
            )
        if len(secret) < 32:
            raise WebPreviewInviteError(
                code="web_preview_invite_secret_weak",
                message="WEB_PREVIEW_INVITE_SECRET must be at least 32 characters.",
                status_code=503,
            )
        return secret

    def _ttl_seconds(self, requested: int | None) -> int:
        ttl = (
            self._settings.web_preview_invite_default_ttl_seconds
            if requested is None
            else requested
        )
        max_ttl = self._settings.web_preview_invite_max_ttl_seconds
        if ttl <= 0:
            raise WebPreviewInviteError(
                code="invalid_invite_ttl",
                message="Invite ttl_seconds must be positive.",
            )
        if ttl > max_ttl:
            raise WebPreviewInviteError(
                code="invite_ttl_exceeds_max",
                message="Invite ttl_seconds exceeds WEB_PREVIEW_INVITE_MAX_TTL_SECONDS.",
            )
        return ttl

    def _assert_preview_accepts_invites(self, preview: dict[str, Any]) -> None:
        status = str(preview.get("status") or "")
        if status == "active" or status == "planned":
            return
        raise WebPreviewInviteError(
            code="web_preview_not_active",
            message=f"Web preview is {status or 'not active'} and cannot accept invites.",
            status_code=409,
        )

    def _load_invite(self, *, preview_id: str, invite_id: str) -> dict[str, Any]:
        path = self._invite_state_dir / f"{invite_id}.json"
        if not path.is_file():
            raise WebPreviewInviteError(
                code="web_preview_invite_not_found",
                message="Web preview invite was not found.",
                status_code=404,
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("preview_id") != preview_id:
            raise WebPreviewInviteError(
                code="web_preview_invite_not_found",
                message="Web preview invite was not found.",
                status_code=404,
            )
        return payload

    def _assert_not_duplicate_active_invite(
        self,
        *,
        preview_id: str,
        email: str | None,
    ) -> None:
        if email is None:
            return
        now = datetime.now(UTC)
        for invite in self.list_invites(preview_id):
            if invite.get("email") != email:
                continue
            if invite.get("revoked_at") or invite.get("expired_at"):
                continue
            expires_at = _parse_iso(str(invite.get("expires_at") or ""))
            if expires_at is not None and expires_at <= now:
                continue
            raise WebPreviewInviteError(
                code="duplicate_admin_invite",
                message="An active invite already exists for this admin email.",
                status_code=409,
            )

    def _sync_and_persist(self, payload: dict[str, Any]) -> dict[str, Any]:
        sync = self._preview_service.sync_invite(payload)
        updated = {**payload, **sync}
        _atomic_write_json(
            self._invite_state_dir / f"{updated['invite_id']}.json",
            updated,
        )
        return updated

    def _deliver_and_persist(self, payload: dict[str, Any]) -> dict[str, Any]:
        preflight = self.email_delivery_preflight()
        delivery = self._deliver_invite_email(payload)
        updated = {
            **payload,
            "email_delivery_preflight": preflight,
            "email_provider": delivery.provider,
            "email_delivery_status": delivery.status,
            "email_delivery_error": delivery.error,
            "email_provider_message_id": delivery.provider_message_id,
            "manual_delivery_required": delivery.manual_delivery_required,
            "last_sent_at": delivery.delivered_at or payload.get("last_sent_at"),
        }
        stored = {key: value for key, value in updated.items() if key != "token"}
        stored.pop("invite_url", None)
        _atomic_write_json(
            self._invite_state_dir / f"{updated['invite_id']}.json",
            stored,
        )
        return updated

    def _deliver_invite_email(
        self,
        invite: dict[str, Any],
    ) -> WebPreviewInviteDeliveryResult:
        email = str(invite.get("email") or "").strip()
        provider = self._settings.web_preview_email_provider
        preflight = self.email_delivery_preflight()
        if not email:
            return WebPreviewInviteDeliveryResult(
                status="manual_link_required",
                provider=provider,
                manual_delivery_required=True,
            )
        if provider in {"disabled", "manual"}:
            return WebPreviewInviteDeliveryResult(
                status="manual_link_required",
                provider=provider,
                manual_delivery_required=True,
            )
        if provider == "smtp":
            if preflight["status"] != "ready":
                return WebPreviewInviteDeliveryResult(
                    status="manual_link_required",
                    provider=provider,
                    error="; ".join(preflight.get("errors") or []),
                    manual_delivery_required=True,
                )
            return self._send_smtp_invite(invite, email=email)
        if provider == "cloudflare_email":
            if preflight["status"] == "manual_fallback":
                return WebPreviewInviteDeliveryResult(
                    status="manual_link_required",
                    provider=provider,
                    error="; ".join(preflight.get("errors") or []),
                    manual_delivery_required=True,
                )
            if preflight["status"] != "ready":
                return WebPreviewInviteDeliveryResult(
                    status="blocked_provider",
                    provider=provider,
                    error="; ".join(preflight.get("errors") or []),
                    manual_delivery_required=True,
                )
            return self._send_cloudflare_email_invite(invite, email=email)
        return WebPreviewInviteDeliveryResult(
            status="blocked_provider",
            provider=provider,
            error=f"Unsupported web preview email provider: {provider}",
            manual_delivery_required=True,
        )

    def _send_smtp_invite(
        self,
        invite: dict[str, Any],
        *,
        email: str,
    ) -> WebPreviewInviteDeliveryResult:
        sender = (self._settings.web_preview_email_from or "").strip()
        host = (self._settings.web_preview_smtp_host or "").strip()
        if not sender or not host:
            return WebPreviewInviteDeliveryResult(
                status="manual_link_required",
                provider="smtp",
                error="WEB_PREVIEW_EMAIL_FROM and WEB_PREVIEW_SMTP_HOST are required.",
                manual_delivery_required=True,
            )
        message = EmailMessage()
        message_id = make_msgid(domain="codex-mobile-bridge.local")
        message["From"] = sender
        message["To"] = email
        message["Subject"] = _invite_email_subject(invite)
        message["Date"] = formatdate(localtime=False, usegmt=True)
        message["Message-ID"] = message_id
        message.set_content(
            _invite_email_body(invite),
        )
        message.add_alternative(
            _invite_email_html_body(invite),
            subtype="html",
        )
        try:
            smtp_port = self._settings.web_preview_smtp_port
            smtp_class = (
                smtplib.SMTP_SSL
                if self._settings.web_preview_smtp_implicit_tls or smtp_port == 465
                else smtplib.SMTP
            )
            with smtp_class(
                host,
                smtp_port,
                timeout=self._settings.web_preview_smtp_timeout_seconds,
            ) as smtp:
                if smtp_class is smtplib.SMTP and self._settings.web_preview_smtp_use_tls:
                    smtp.starttls()
                username = self._settings.web_preview_smtp_username
                password = self._settings.web_preview_smtp_password
                if username and password:
                    smtp.login(username, password)
                refused = smtp.send_message(message)
                if refused:
                    refused_recipients = ", ".join(sorted(str(key) for key in refused))
                    return WebPreviewInviteDeliveryResult(
                        status="failed",
                        provider="smtp",
                        error=f"SMTP refused recipients: {refused_recipients}",
                        manual_delivery_required=True,
                        provider_message_id=message_id,
                    )
        except Exception as exc:
            return WebPreviewInviteDeliveryResult(
                status="failed",
                provider="smtp",
                error=_safe_email_error(str(exc), self._settings.web_preview_smtp_password),
                manual_delivery_required=True,
                provider_message_id=message_id,
            )
        return WebPreviewInviteDeliveryResult(
            status="sent",
            provider="smtp",
            delivered_at=_iso(datetime.now(UTC)),
            provider_message_id=message_id,
        )

    def _send_cloudflare_email_invite(
        self,
        invite: dict[str, Any],
        *,
        email: str,
    ) -> WebPreviewInviteDeliveryResult:
        sender = (self._settings.web_preview_email_from or "").strip()
        endpoint = (self._settings.web_preview_email_endpoint or "").strip()
        token = (self._settings.web_preview_email_api_token or "").strip()
        if not sender or not endpoint or not token:
            return WebPreviewInviteDeliveryResult(
                status="manual_link_required",
                provider="cloudflare_email",
                error=(
                    "WEB_PREVIEW_EMAIL_FROM, WEB_PREVIEW_EMAIL_ENDPOINT, and "
                    "WEB_PREVIEW_EMAIL_API_TOKEN are required."
                ),
                manual_delivery_required=True,
            )
        payload = {
            "from": sender,
            "to": email,
            "subject": _invite_email_subject(invite),
            "text": _invite_email_body(invite),
            "html": _invite_email_html_body(invite),
            "metadata": {
                "preview_id": invite.get("preview_id"),
                "invite_id": invite.get("invite_id"),
                "source_app": invite.get("source_app"),
            },
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "authorization": f"Bearer {token}",
                "content-type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self._settings.web_preview_smtp_timeout_seconds,
            ) as response:
                raw = response.read().decode("utf-8")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            return WebPreviewInviteDeliveryResult(
                status="failed",
                provider="cloudflare_email",
                error=_safe_email_error(str(exc), token),
                manual_delivery_required=True,
            )
        provider_message_id = None
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {}
        if isinstance(body, dict):
            provider_message_id = str(
                body.get("id")
                or body.get("message_id")
                or body.get("messageId")
                or ""
            ) or None
        return WebPreviewInviteDeliveryResult(
            status="sent",
            provider="cloudflare_email",
            delivered_at=_iso(datetime.now(UTC)),
            provider_message_id=provider_message_id,
        )


def sign_web_preview_invite(*, secret: str, payload: dict[str, Any]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _b64url_json(header)
    encoded_payload = _b64url_json(payload)
    signature = _sign(secret, f"{encoded_header}.{encoded_payload}")
    return f"{encoded_header}.{encoded_payload}.{signature}"


def verify_web_preview_invite(
    *,
    secret: str,
    token: str,
    source_app: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise WebPreviewInviteError(code="invalid_invite_token", message="Invalid invite token.")
    signing_input = f"{parts[0]}.{parts[1]}"
    expected = _sign(secret, signing_input)
    if not hmac.compare_digest(expected, parts[2]):
        raise WebPreviewInviteError(
            code="invalid_invite_token",
            message="Invalid invite token.",
            status_code=403,
        )
    try:
        payload = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        raise WebPreviewInviteError(
            code="invalid_invite_token",
            message="Invalid invite token payload.",
            status_code=403,
        ) from exc
    current = int((now or datetime.now(UTC)).timestamp())
    if payload.get("aud") != WEB_PREVIEW_INVITE_AUDIENCE:
        raise WebPreviewInviteError(
            code="invalid_invite_audience",
            message="Invite token audience mismatch.",
            status_code=403,
        )
    if payload.get("scope") != WEB_PREVIEW_INVITE_SCOPE:
        raise WebPreviewInviteError(
            code="invalid_invite_scope",
            message="Invite token scope mismatch.",
            status_code=403,
        )
    if payload.get("source_app") != source_app or payload.get("app_slug") != source_app:
        raise WebPreviewInviteError(
            code="invalid_invite_app",
            message="Invite token app mismatch.",
            status_code=403,
        )
    if int(payload.get("exp") or 0) <= current:
        raise WebPreviewInviteError(
            code="expired_invite_token",
            message="Invite token has expired.",
            status_code=403,
        )
    return payload


def _b64url_json(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _b64url_encode(encoded)


def _b64url_encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _b64url_decode(payload: str) -> bytes:
    padding = "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode((payload + padding).encode("ascii"))


def _sign(secret: str, signing_input: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64url_encode(digest)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalize_email(value: str | None) -> str | None:
    email = (value or "").strip().lower()
    if not email:
        return None
    if len(email) > 254 or "@" not in email:
        raise WebPreviewInviteError(
            code="invalid_admin_email",
            message="Admin invite email must be a valid email address.",
        )
    local, domain = email.rsplit("@", 1)
    if not local or not domain or "." not in domain:
        raise WebPreviewInviteError(
            code="invalid_admin_email",
            message="Admin invite email must be a valid email address.",
        )
    return email


def _is_valid_email_address(value: str) -> bool:
    try:
        return _normalize_email(value) is not None
    except WebPreviewInviteError:
        return False


def _is_valid_http_endpoint(value: str) -> bool:
    if not value:
        return False
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _redact_url(value: str) -> str:
    if not value:
        return value
    parsed = urlsplit(value)
    netloc = parsed.netloc
    if "@" in netloc:
        netloc = f"[redacted]@{netloc.rsplit('@', 1)[1]}"
    redacted_query = urlencode(
        [
            (
                key,
                "[redacted]"
                if any(marker in key.lower() for marker in ("token", "secret", "key"))
                else query_value,
            )
            for key, query_value in parse_qsl(parsed.query, keep_blank_values=True)
        ]
    )
    return urlunsplit(
        (parsed.scheme, netloc, parsed.path, redacted_query, parsed.fragment)
    )


def _normalize_role(value: str | None) -> str:
    role = (value or "admin").strip().lower()
    allowed = {"owner", "admin", "manager", "staff"}
    if role not in allowed:
        raise WebPreviewInviteError(
            code="invalid_admin_role",
            message="Admin invite role must be owner, admin, manager, or staff.",
        )
    return role


def _safe_email_error(message: str, *secrets_to_redact: str | None) -> str:
    safe = message
    for secret in secrets_to_redact:
        if secret:
            safe = safe.replace(secret, "[redacted]")
    return safe


def _invite_email_subject(invite: dict[str, Any]) -> str:
    source_app = str(invite.get("source_app") or "preview").replace("-", " ").title()
    return f"Invitacion al Preview de {source_app}"


def _invite_email_body(invite: dict[str, Any]) -> str:
    expires_at = str(invite.get("expires_at") or "the configured expiration time")
    return (
        "Recibiste una invitacion para acceder al Preview.\n\n"
        "Usa el boton principal del email HTML para aceptar la invitacion y crear tu contrasena.\n\n"
        f"La invitacion vence: {expires_at}\n"
        "Este Preview es una version inicial, no una version de produccion.\n"
        "Si necesitas un enlace manual, solicitalo al operador del Preview."
    )


def _invite_email_html_body(invite: dict[str, Any]) -> str:
    source_app = str(invite.get("source_app") or "preview").replace("-", " ").title()
    invite_url = str(invite.get("invite_url") or "")
    expires_at = str(invite.get("expires_at") or "the configured expiration time")
    safe_app = escape(source_app)
    safe_url = escape(invite_url, quote=True)
    safe_expires = escape(expires_at)
    return f"""<!doctype html>
<html lang="es">
  <body style="margin:0;background:#f6f7f9;color:#1f2937;font-family:Arial,sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f6f7f9;padding:24px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;">
            <tr>
              <td style="padding:28px;">
                <h1 style="margin:0 0 12px;font-size:22px;line-height:1.3;color:#111827;">Invitacion al Preview de {safe_app}</h1>
                <p style="margin:0 0 20px;font-size:15px;line-height:1.6;color:#374151;">Recibiste una invitacion para revisar una version inicial de Preview. Crea tu contrasena para ingresar.</p>
                <p style="margin:0 0 24px;">
                  <a href="{safe_url}" style="display:inline-block;background:#111827;color:#ffffff;text-decoration:none;font-size:15px;font-weight:700;padding:12px 18px;border-radius:6px;">Aceptar invitación</a>
                </p>
                <p style="margin:0 0 12px;font-size:13px;line-height:1.5;color:#6b7280;">La invitacion vence: {safe_expires}</p>
                <p style="margin:0 0 16px;font-size:13px;line-height:1.5;color:#6b7280;">Este Preview es una version inicial, no una version de produccion.</p>
                <p style="margin:0;font-size:12px;line-height:1.5;color:#6b7280;">Si el boton no funciona, pedi un enlace manual al operador del Preview.</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


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
