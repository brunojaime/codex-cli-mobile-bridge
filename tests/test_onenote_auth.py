from __future__ import annotations

import builtins
import io
from pathlib import Path
import stat
import sys

import pytest


_SKILL_SCRIPTS = (
    Path(__file__).resolve().parents[1] / "skills" / "onenote-connect" / "scripts"
)
if str(_SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS))

import auth  # noqa: E402


class FakeCache:
    def __init__(
        self, *, has_state_changed: bool = False, serialized: str = "serialized-cache"
    ) -> None:
        self.has_state_changed = has_state_changed
        self.serialized = serialized
        self.deserialize_calls: list[str] = []
        self.serialize_calls = 0

    def deserialize(self, raw: str) -> None:
        self.deserialize_calls.append(raw)

    def serialize(self) -> str:
        self.serialize_calls += 1
        return self.serialized


class FakeApp:
    def __init__(self) -> None:
        self.accounts = [{"username": "alice@example.com"}]
        self.silent_result = None
        self.device_flow = {"user_code": "abc123", "message": "Sign in with the code."}
        self.device_result = None
        self.interactive_result = None
        self.get_accounts_calls: list[str | None] = []
        self.silent_calls: list[tuple[list[str], dict[str, str]]] = []
        self.device_scopes: list[str] | None = None
        self.interactive_calls: list[dict[str, object]] = []

    def get_accounts(self, username: str | None = None):
        self.get_accounts_calls.append(username)
        return list(self.accounts)

    def acquire_token_silent(self, scopes: list[str], account: dict[str, str]):
        self.silent_calls.append((list(scopes), account))
        return self.silent_result

    def initiate_device_flow(self, scopes: list[str]):
        self.device_scopes = list(scopes)
        return self.device_flow

    def acquire_token_by_device_flow(self, flow):
        self.device_flow_used = flow
        return self.device_result

    def acquire_token_interactive(
        self,
        *,
        scopes: list[str],
        login_hint: str | None = None,
        port: int = 0,
    ):
        self.interactive_calls.append(
            {
                "scopes": list(scopes),
                "login_hint": login_hint,
                "port": port,
            }
        )
        return self.interactive_result


class FakeMSAL:
    def __init__(
        self, *, app: FakeApp | None = None, cache: FakeCache | None = None
    ) -> None:
        self.app = app or FakeApp()
        self.cache = cache or FakeCache()
        self.public_client_app_calls: list[dict[str, object]] = []

    def SerializableTokenCache(self):
        return self.cache

    def PublicClientApplication(
        self, client_id: str, *, authority: str, token_cache: FakeCache
    ):
        self.public_client_app_calls.append(
            {
                "client_id": client_id,
                "authority": authority,
                "token_cache": token_cache,
            }
        )
        return self.app


def _make_authenticator(
    tmp_path: Path,
    *,
    stdout: io.StringIO | None = None,
) -> auth.OneNoteAuthenticator:
    config = auth.AuthConfig(
        client_id="client-1",
        cache_path=tmp_path / "token-cache.json",
    )
    return auth.OneNoteAuthenticator(config, stdout=stdout)


def test_auth_config_from_inputs_prefers_flags_over_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ONENOTE_CLIENT_ID", "env-client")
    monkeypatch.setenv("ONENOTE_TENANT_ID", "env-tenant")
    monkeypatch.setenv("ONENOTE_AUTHORITY_BASE", "https://env.example.com")
    monkeypatch.setenv("ONENOTE_SCOPES", "Env.Scope,offline_access")
    monkeypatch.setenv("ONENOTE_TOKEN_CACHE_PATH", str(tmp_path / "env-cache.json"))

    config = auth.auth_config_from_inputs(
        client_id="flag-client",
        tenant_id="flag-tenant",
        authority_base="https://flag.example.com",
        scopes="Scope.One, Scope.Two ,",
        cache_path=tmp_path / "flag-cache.json",
    )

    assert config.client_id == "flag-client"
    assert config.tenant_id == "flag-tenant"
    assert config.authority_base == "https://flag.example.com"
    assert config.scopes == ("Scope.One", "Scope.Two")
    assert config.cache_path == tmp_path / "flag-cache.json"


def test_auth_config_from_inputs_uses_env_then_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ONENOTE_CLIENT_ID", "env-client")
    monkeypatch.setenv("ONENOTE_TENANT_ID", "env-tenant")
    monkeypatch.setenv("ONENOTE_AUTHORITY_BASE", "https://env.example.com")
    monkeypatch.setenv("ONENOTE_SCOPES", "Scope.Env , User.Read")
    monkeypatch.setenv("ONENOTE_TOKEN_CACHE_PATH", str(tmp_path / "env-cache.json"))

    config = auth.auth_config_from_inputs()

    assert config.client_id == "env-client"
    assert config.tenant_id == "env-tenant"
    assert config.authority_base == "https://env.example.com"
    assert config.scopes == ("Scope.Env", "User.Read")
    assert config.cache_path == tmp_path / "env-cache.json"

    monkeypatch.delenv("ONENOTE_TENANT_ID")
    monkeypatch.delenv("ONENOTE_AUTHORITY_BASE")
    monkeypatch.delenv("ONENOTE_SCOPES")
    monkeypatch.delenv("ONENOTE_TOKEN_CACHE_PATH")
    config_with_defaults = auth.auth_config_from_inputs()

    assert config_with_defaults.tenant_id == auth.DEFAULT_TENANT_ID
    assert config_with_defaults.authority_base == auth.DEFAULT_AUTHORITY_BASE
    assert config_with_defaults.scopes == auth.DEFAULT_SCOPES
    assert config_with_defaults.cache_path == auth.DEFAULT_CACHE_PATH


def test_acquire_session_uses_silent_token_when_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_app = FakeApp()
    fake_app.silent_result = {
        "access_token": "silent-token",
        "account": {"username": "alice@example.com"},
        "id_token_claims": {"name": "Alice Example", "tid": "tenant-1"},
    }
    fake_cache = FakeCache()
    fake_msal = FakeMSAL(app=fake_app, cache=fake_cache)
    authenticator = _make_authenticator(tmp_path)
    authenticator.config.cache_path.write_text("cached-state")
    persisted: list[FakeCache] = []

    monkeypatch.setattr(auth, "_import_msal", lambda: fake_msal)
    monkeypatch.setattr(authenticator, "_persist_cache", persisted.append)

    session = authenticator.acquire_session()

    assert session.access_token == "silent-token"
    assert session.auth_flow == "silent"
    assert fake_cache.deserialize_calls == ["cached-state"]
    assert fake_app.device_scopes is None
    assert fake_app.interactive_calls == []
    assert persisted == [fake_cache]


def test_acquire_session_auto_falls_back_from_device_code_to_interactive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_app = FakeApp()
    fake_app.silent_result = None
    fake_app.device_flow = {"error": "invalid_client"}
    fake_app.interactive_result = {
        "access_token": "interactive-token",
        "account": {"username": "alice@example.com"},
        "id_token_claims": {"name": "Alice Example", "tid": "tenant-1"},
    }
    fake_msal = FakeMSAL(app=fake_app)
    authenticator = _make_authenticator(tmp_path, stdout=io.StringIO())
    persisted: list[FakeCache] = []

    monkeypatch.setattr(auth, "_import_msal", lambda: fake_msal)
    monkeypatch.setattr(authenticator, "_persist_cache", persisted.append)

    session = authenticator.acquire_session(
        auth_flow="auto", login_hint="alice@example.com"
    )

    assert session.auth_flow == "interactive"
    assert session.access_token == "interactive-token"
    assert fake_app.interactive_calls == [
        {
            "scopes": list(auth.DEFAULT_SCOPES),
            "login_hint": "alice@example.com",
            "port": 0,
        }
    ]
    assert persisted == [fake_msal.cache]


def test_force_interactive_bypasses_silent_acquisition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_app = FakeApp()
    fake_app.silent_result = {
        "access_token": "silent-token",
        "account": {"username": "alice@example.com"},
    }
    fake_app.interactive_result = {
        "access_token": "interactive-token",
        "account": {"username": "alice@example.com"},
    }
    fake_msal = FakeMSAL(app=fake_app)
    authenticator = _make_authenticator(tmp_path)
    persisted: list[FakeCache] = []

    monkeypatch.setattr(auth, "_import_msal", lambda: fake_msal)
    monkeypatch.setattr(authenticator, "_persist_cache", persisted.append)

    session = authenticator.acquire_session(
        force_interactive=True, auth_flow="interactive"
    )

    assert session.auth_flow == "interactive"
    assert fake_app.get_accounts_calls == []
    assert fake_app.silent_calls == []
    assert len(fake_app.interactive_calls) == 1
    assert persisted == [fake_msal.cache]


def test_device_code_startup_failure_raises_readable_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_app = FakeApp()
    fake_app.silent_result = None
    fake_app.device_flow = {"error": "invalid_client"}
    fake_msal = FakeMSAL(app=fake_app)
    authenticator = _make_authenticator(tmp_path)

    monkeypatch.setattr(auth, "_import_msal", lambda: fake_msal)

    with pytest.raises(auth.AuthenticationError) as excinfo:
        authenticator.acquire_session(auth_flow="device-code")

    message = str(excinfo.value)
    assert "Device-code sign-in could not be started." in message
    assert '"error": "invalid_client"' in message


def test_interactive_failure_raises_readable_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_app = FakeApp()
    fake_app.silent_result = None
    fake_app.interactive_result = {
        "error": "access_denied",
        "error_description": "user cancelled",
    }
    fake_msal = FakeMSAL(app=fake_app)
    authenticator = _make_authenticator(tmp_path)

    monkeypatch.setattr(auth, "_import_msal", lambda: fake_msal)

    with pytest.raises(auth.AuthenticationError) as excinfo:
        authenticator.acquire_session(auth_flow="interactive")

    assert "access_denied: user cancelled" in str(excinfo.value)


def test_import_msal_raises_dependency_error_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "msal":
            raise ImportError("msal missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.delitem(sys.modules, "msal", raising=False)

    with pytest.raises(auth.AuthenticationDependencyError) as excinfo:
        auth._import_msal()

    assert "MSAL for Python is required for OneNote authentication." in str(
        excinfo.value
    )


def test_persist_cache_writes_only_when_state_changed(tmp_path: Path) -> None:
    authenticator = _make_authenticator(tmp_path)
    unchanged_cache = FakeCache(has_state_changed=False)

    authenticator._persist_cache(unchanged_cache)

    assert not authenticator.config.cache_path.exists()
    assert unchanged_cache.serialize_calls == 0

    changed_cache = FakeCache(has_state_changed=True, serialized="fresh-cache")
    authenticator._persist_cache(changed_cache)

    assert authenticator.config.cache_path.read_text() == "fresh-cache"
    assert changed_cache.serialize_calls == 1
    file_mode = stat.S_IMODE(authenticator.config.cache_path.stat().st_mode)
    assert file_mode == 0o600
