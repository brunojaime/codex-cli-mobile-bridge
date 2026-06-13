from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
from typing import Any, TextIO


DEFAULT_TENANT_ID = "common"
DEFAULT_AUTHORITY_BASE = "https://login.microsoftonline.com"
DEFAULT_SCOPES = (
    "Notes.ReadWrite",
    "User.Read",
    "offline_access",
    "openid",
    "profile",
)
DEFAULT_CACHE_PATH = (
    Path.home() / ".config" / "codex" / "onenote-connect" / "token-cache.json"
)


class AuthenticationError(RuntimeError):
    pass


class AuthenticationDependencyError(RuntimeError):
    pass


@dataclass(slots=True, frozen=True)
class AuthConfig:
    client_id: str
    tenant_id: str = DEFAULT_TENANT_ID
    authority_base: str = DEFAULT_AUTHORITY_BASE
    scopes: tuple[str, ...] = DEFAULT_SCOPES
    cache_path: Path = DEFAULT_CACHE_PATH

    @property
    def authority(self) -> str:
        return f"{self.authority_base.rstrip('/')}/{self.tenant_id}"


@dataclass(slots=True, frozen=True)
class AuthSession:
    access_token: str
    account_username: str | None
    display_name: str | None
    tenant_id: str | None
    auth_flow: str


def auth_config_from_inputs(
    *,
    client_id: str | None = None,
    tenant_id: str | None = None,
    authority_base: str | None = None,
    scopes: str | tuple[str, ...] | list[str] | None = None,
    cache_path: str | Path | None = None,
) -> AuthConfig:
    resolved_client_id = (client_id or os.getenv("ONENOTE_CLIENT_ID", "")).strip()
    if not resolved_client_id:
        raise ValueError(
            "A Microsoft Entra app client ID is required. "
            "Set ONENOTE_CLIENT_ID or pass --client-id."
        )

    resolved_scopes = _normalize_scopes(scopes or os.getenv("ONENOTE_SCOPES"))
    resolved_cache_path = resolve_cache_path(cache_path)
    resolved_authority_base = (
        authority_base
        or os.getenv("ONENOTE_AUTHORITY_BASE")
        or DEFAULT_AUTHORITY_BASE
    ).strip()
    resolved_tenant_id = (
        tenant_id
        or os.getenv("ONENOTE_TENANT_ID")
        or DEFAULT_TENANT_ID
    ).strip()

    return AuthConfig(
        client_id=resolved_client_id,
        tenant_id=resolved_tenant_id,
        authority_base=resolved_authority_base,
        scopes=resolved_scopes,
        cache_path=resolved_cache_path,
    )


def resolve_cache_path(cache_path: str | Path | None = None) -> Path:
    return Path(
        cache_path
        or os.getenv("ONENOTE_TOKEN_CACHE_PATH")
        or DEFAULT_CACHE_PATH
    ).expanduser()


class OneNoteAuthenticator:
    def __init__(
        self,
        config: AuthConfig,
        *,
        stdout: TextIO | None = None,
    ) -> None:
        self._config = config
        self._stdout = stdout or sys.stdout

    @property
    def config(self) -> AuthConfig:
        return self._config

    def acquire_session(
        self,
        *,
        auth_flow: str = "auto",
        login_hint: str | None = None,
        force_interactive: bool = False,
    ) -> AuthSession:
        msal = _import_msal()
        cache = self._load_cache(msal)
        app = msal.PublicClientApplication(
            self._config.client_id,
            authority=self._config.authority,
            token_cache=cache,
        )

        if not force_interactive:
            cached = self._try_silent(app, login_hint=login_hint)
            if cached is not None:
                self._persist_cache(cache)
                return cached

        normalized_flow = auth_flow.strip().lower()
        if normalized_flow not in {"auto", "device-code", "interactive"}:
            raise ValueError(
                "Unsupported auth flow. Expected auto, device-code, or interactive."
            )

        errors: list[str] = []
        if normalized_flow in {"auto", "device-code"}:
            try:
                session = self._acquire_by_device_code(app)
                self._persist_cache(cache)
                return session
            except AuthenticationError as exc:
                errors.append(str(exc))
                if normalized_flow == "device-code":
                    raise

        if normalized_flow in {"auto", "interactive"}:
            try:
                session = self._acquire_interactive(app, login_hint=login_hint)
                self._persist_cache(cache)
                return session
            except AuthenticationError as exc:
                errors.append(str(exc))

        detail = "\n".join(error for error in errors if error)
        raise AuthenticationError(
            "Failed to acquire a Microsoft Graph token."
            + (f"\n{detail}" if detail else "")
        )

    def clear_cache(self) -> bool:
        if self._config.cache_path.exists():
            self._config.cache_path.unlink()
            return True
        return False

    def list_cached_accounts(self) -> list[dict[str, Any]]:
        msal = _import_msal()
        cache = self._load_cache(msal)
        app = msal.PublicClientApplication(
            self._config.client_id,
            authority=self._config.authority,
            token_cache=cache,
        )
        return list(app.get_accounts())

    def _try_silent(
        self,
        app: Any,
        *,
        login_hint: str | None,
    ) -> AuthSession | None:
        accounts = (
            app.get_accounts(username=login_hint)
            if login_hint
            else app.get_accounts()
        )
        for account in accounts:
            result = app.acquire_token_silent(list(self._config.scopes), account=account)
            if result and "access_token" in result:
                return _session_from_result(result, auth_flow="silent")
        return None

    def _acquire_by_device_code(self, app: Any) -> AuthSession:
        flow = app.initiate_device_flow(scopes=list(self._config.scopes))
        if "user_code" not in flow:
            raise AuthenticationError(
                "Device-code sign-in could not be started.\n"
                + json.dumps(flow, indent=2)
            )
        message = flow.get("message", "").strip()
        if message:
            print(message, file=self._stdout)
            self._stdout.flush()
        result = app.acquire_token_by_device_flow(flow)
        if not result or "access_token" not in result:
            raise AuthenticationError(_format_auth_error(result))
        return _session_from_result(result, auth_flow="device-code")

    def _acquire_interactive(self, app: Any, *, login_hint: str | None) -> AuthSession:
        result = app.acquire_token_interactive(
            scopes=list(self._config.scopes),
            login_hint=login_hint,
            port=0,
        )
        if not result or "access_token" not in result:
            raise AuthenticationError(_format_auth_error(result))
        return _session_from_result(result, auth_flow="interactive")

    def _load_cache(self, msal: Any) -> Any:
        cache = msal.SerializableTokenCache()
        if self._config.cache_path.exists():
            cache.deserialize(self._config.cache_path.read_text())
        return cache

    def _persist_cache(self, cache: Any) -> None:
        if not getattr(cache, "has_state_changed", False):
            return
        self._config.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._config.cache_path.write_text(cache.serialize())
        try:
            self._config.cache_path.chmod(0o600)
        except OSError:
            pass


def _import_msal() -> Any:
    try:
        import msal
    except ImportError as exc:
        raise AuthenticationDependencyError(
            "MSAL for Python is required for OneNote authentication. "
            "Run the CLI with `uv run --with msal` or install `msal`."
        ) from exc
    return msal


def _normalize_scopes(
    raw_scopes: str | tuple[str, ...] | list[str] | None,
) -> tuple[str, ...]:
    if raw_scopes is None:
        return DEFAULT_SCOPES
    if isinstance(raw_scopes, (tuple, list)):
        scopes = [scope.strip() for scope in raw_scopes if scope and scope.strip()]
        return tuple(scopes) or DEFAULT_SCOPES
    scopes = [scope.strip() for scope in raw_scopes.split(",") if scope.strip()]
    return tuple(scopes) or DEFAULT_SCOPES


def _session_from_result(result: dict[str, Any], *, auth_flow: str) -> AuthSession:
    account = result.get("account") or {}
    id_token_claims = result.get("id_token_claims") or {}
    username = (
        account.get("username")
        or id_token_claims.get("preferred_username")
        or id_token_claims.get("upn")
    )
    display_name = id_token_claims.get("name") or account.get("name")
    tenant_id = id_token_claims.get("tid")
    return AuthSession(
        access_token=result["access_token"],
        account_username=username,
        display_name=display_name,
        tenant_id=tenant_id,
        auth_flow=auth_flow,
    )


def _format_auth_error(result: dict[str, Any] | None) -> str:
    if not result:
        return "Authentication failed with an empty response."
    error = result.get("error")
    description = result.get("error_description")
    if error and description:
        return f"{error}: {description}"
    if error:
        return str(error)
    return json.dumps(result, indent=2)
