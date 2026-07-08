from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import base64
import hashlib
import hmac
import json
from pathlib import Path
import secrets
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.parse import quote

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

    def create_invite(self, request: WebPreviewInviteCreateInput) -> dict[str, Any]:
        secret = self._require_secret()
        preview = self._preview_service.get_preview(request.preview_id)
        if preview is None:
            raise WebPreviewInviteError(
                code="web_preview_not_found",
                message="Web preview was not found.",
                status_code=404,
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
            "single_use": request.single_use,
            "used_at": None,
            "revoked_at": None,
            "token_sha256": token_hash,
        }
        _atomic_write_json(self._invite_state_dir / f"{invite_id}.json", metadata)
        return {
            **metadata,
            "invite_url": invite_url,
            "token": token,
        }

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
        return payload

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
