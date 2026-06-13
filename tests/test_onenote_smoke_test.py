from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import sys

_SKILL_SCRIPTS = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "onenote-connect"
    / "scripts"
)
if str(_SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS))

from graph_client import GraphRequestError  # noqa: E402

_SMOKE_SPEC = importlib.util.spec_from_file_location(
    "onenote_smoke_test_impl",
    _SKILL_SCRIPTS / "onenote_smoke_test.py",
)
assert _SMOKE_SPEC is not None
assert _SMOKE_SPEC.loader is not None
_SMOKE_MODULE = importlib.util.module_from_spec(_SMOKE_SPEC)
sys.modules[_SMOKE_SPEC.name] = _SMOKE_MODULE
_SMOKE_SPEC.loader.exec_module(_SMOKE_MODULE)
main = _SMOKE_MODULE.main


class _FakeAuthenticator:
    instances: list["_FakeAuthenticator"] = []

    def __init__(self, config, *, stdout) -> None:
        self.config = config
        self.stdout = stdout
        self.calls: list[tuple[str, str | None, bool]] = []
        self.__class__.instances.append(self)

    def acquire_session(
        self,
        *,
        auth_flow: str,
        login_hint: str | None,
        force_interactive: bool,
    ):
        self.calls.append((auth_flow, login_hint, force_interactive))
        return type(
            "Session",
            (),
            {
                "access_token": "token-123",
                "account_username": "user@example.com",
                "display_name": "Example User",
                "tenant_id": "tenant-123",
                "auth_flow": auth_flow,
            },
        )()


class _FakeGraphClient:
    instances: list["_FakeGraphClient"] = []

    def __init__(self, *, access_token: str) -> None:
        self.access_token = access_token
        self.calls: list[tuple[str, object]] = []
        self.create_calls: list[dict[str, object]] = []
        self.append_calls: list[dict[str, object]] = []
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def get_me(self):
        self.calls.append(("get_me", None))
        return {
            "id": "user-1",
            "displayName": "Example User",
            "userPrincipalName": "user@example.com",
        }

    def list_notebooks(self):
        self.calls.append(("list_notebooks", None))
        return [{"id": "nb-1", "displayName": "Notebook"}]

    def list_sections(self):
        self.calls.append(("list_sections", None))
        return [{"id": "sec-1", "displayName": "Section"}]

    def list_pages(self, *, section_id=None):
        self.calls.append(("list_pages", section_id))
        return [{"id": "page-1", "title": "Page"}]

    def create_page(self, **kwargs):
        self.create_calls.append(kwargs)
        return {"id": "created-1", "title": kwargs["title"]}

    def append_page(self, **kwargs):
        self.append_calls.append(kwargs)


class _FailingGraphClient(_FakeGraphClient):
    def list_notebooks(self):
        raise GraphRequestError(status_code=503, code="serviceUnavailable", message="backend down")


def test_smoke_test_fails_fast_when_client_id_is_missing(monkeypatch) -> None:
    monkeypatch.delenv("ONENOTE_CLIENT_ID", raising=False)

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = main(
        [],
        authenticator_cls=_FakeAuthenticator,
        graph_client_cls=_FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 1
    assert "Smoke test: FAIL" in stderr.getvalue()
    assert "client ID is required" in stderr.getvalue()


def test_smoke_test_read_only_orchestrates_auth_and_discovery(monkeypatch) -> None:
    monkeypatch.delenv("ONENOTE_CLIENT_ID", raising=False)
    _FakeAuthenticator.instances.clear()
    _FakeGraphClient.instances.clear()

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = main(
        ["--client-id", "client-123"],
        authenticator_cls=_FakeAuthenticator,
        graph_client_cls=_FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "Smoke test: PASS" in stdout.getvalue()
    assert "- auth: PASS" in stdout.getvalue()
    assert "- notebooks: PASS (count=1 first_id=nb-1 first_displayName=Notebook)" in stdout.getvalue()
    assert _FakeAuthenticator.instances[0].calls == [("auto", None, False)]
    assert _FakeGraphClient.instances[0].calls == [
        ("get_me", None),
        ("list_notebooks", None),
        ("list_sections", None),
        ("list_pages", "sec-1"),
    ]
    assert _FakeGraphClient.instances[0].create_calls == []
    assert _FakeGraphClient.instances[0].append_calls == []


def test_smoke_test_refuses_write_targets_without_explicit_write(monkeypatch) -> None:
    monkeypatch.delenv("ONENOTE_CLIENT_ID", raising=False)

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = main(
        ["--client-id", "client-123", "--write-section", "sec-1"],
        authenticator_cls=_FakeAuthenticator,
        graph_client_cls=_FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert "Refusing write-target arguments without --write" in stderr.getvalue()


def test_smoke_test_write_mode_runs_mutations_only_when_explicitly_enabled(monkeypatch) -> None:
    monkeypatch.delenv("ONENOTE_CLIENT_ID", raising=False)
    _FakeGraphClient.instances.clear()

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = main(
        [
            "--client-id",
            "client-123",
            "--write",
            "--write-section",
            "sec-1",
            "--write-page",
            "page-9",
        ],
        authenticator_cls=_FakeAuthenticator,
        graph_client_cls=_FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    graph = _FakeGraphClient.instances[0]
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "Write mode enabled" in stdout.getvalue()
    assert graph.create_calls[0]["section_id"] == "sec-1"
    assert graph.create_calls[0]["treat_as_plain_text"] is True
    assert graph.append_calls == [
        {
            "page_id": "page-9",
            "html_or_text": "Codex OneNote smoke test append path.",
            "treat_as_plain_text": True,
        }
    ]


def test_smoke_test_reports_graph_failures_cleanly(monkeypatch) -> None:
    monkeypatch.delenv("ONENOTE_CLIENT_ID", raising=False)

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = main(
        ["--client-id", "client-123"],
        authenticator_cls=_FakeAuthenticator,
        graph_client_cls=_FailingGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert "Smoke test: FAIL" in stderr.getvalue()
    assert "Graph API 503 serviceUnavailable: backend down" in stderr.getvalue()


def test_smoke_test_json_output_for_success(monkeypatch) -> None:
    monkeypatch.delenv("ONENOTE_CLIENT_ID", raising=False)

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = main(
        ["--client-id", "client-123", "--json"],
        authenticator_cls=_FakeAuthenticator,
        graph_client_cls=_FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["status"] == "passed"
    assert payload["mode"] == "read-only"
    assert payload["error"] is None
    assert payload["checks"][0]["name"] == "auth"
    assert payload["checks"][0]["resource"]["auth_flow"] == "auto"
    assert payload["checks"][1]["resource"]["display_name"] == "Example User"
    assert payload["checks"][2]["resource"]["first_id"] == "nb-1"
    assert payload["checks"][3]["resource"]["first_displayName"] == "Section"
    assert payload["checks"][4]["resource"]["first_title"] == "Page"
    assert stderr.getvalue() == ""


def test_smoke_test_json_output_for_failure(monkeypatch) -> None:
    monkeypatch.delenv("ONENOTE_CLIENT_ID", raising=False)

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = main(
        ["--client-id", "client-123", "--json"],
        authenticator_cls=_FakeAuthenticator,
        graph_client_cls=_FailingGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    payload = json.loads(stdout.getvalue())
    assert exit_code == 1
    assert payload["ok"] is False
    assert payload["status"] == "failed"
    assert payload["mode"] == "read-only"
    assert payload["checks"] == []
    assert payload["error"] == {
        "type": "GraphRequestError",
        "message": "Graph API 503 serviceUnavailable: backend down",
    }
    assert stderr.getvalue() == ""
