from __future__ import annotations

import io
from pathlib import Path
import sys
from types import SimpleNamespace


_SKILL_SCRIPTS = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "onenote-connect"
    / "scripts"
)
if str(_SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS))

from onenote_cli import _item_name_contains, _parse_page_timestamp, main  # noqa: E402
from graph_client import GraphRequestError  # noqa: E402


class FakeAuthenticator:
    def __init__(self, config, *, stdout=None) -> None:
        self.config = config
        self.stdout = stdout

    def acquire_session(
        self,
        *,
        auth_flow: str = "auto",
        login_hint: str | None = None,
        force_interactive: bool = False,
    ):
        return SimpleNamespace(
            access_token="token",
            account_username="alice@example.com",
            display_name="Alice Example",
            tenant_id="tenant-1",
            auth_flow=auth_flow,
        )

    def clear_cache(self) -> bool:
        return True

    def list_cached_accounts(self):
        return [
            {"username": "alice@example.com", "name": "Alice Example"},
            {"username": "bob@example.com", "name": "Bob Example"},
        ]


class FakeGraphClient:
    last_instance = None

    def __init__(self, *, access_token: str) -> None:
        self.access_token = access_token
        self.created_calls = []
        self.attached_calls = []
        FakeGraphClient.last_instance = self

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None

    def get_me(self):
        return {
            "displayName": "Alice Example",
            "userPrincipalName": "alice@example.com",
        }

    def list_notebooks(self):
        return [
            {"id": "nb-1", "displayName": "Team Notes", "isDefault": True},
            {"id": "nb-2", "displayName": "Personal Archive", "isDefault": False},
            {"id": "nb-3", "displayName": "Research", "isDefault": False},
        ]

    def list_sections(self, *, notebook_id: str | None = None):
        return [
            {
                "id": "sec-1",
                "displayName": "Sprint",
                "parentNotebook": {"displayName": "Team Notes"},
                "isDefault": False,
            },
            {
                "id": "sec-2",
                "displayName": "Meeting Notes",
                "parentNotebook": {"displayName": "Team Notes"},
                "isDefault": True,
            },
            {
                "id": "sec-3",
                "displayName": "Archive",
                "parentNotebook": {"displayName": "Personal Archive"},
                "isDefault": False,
            },
        ]

    def list_pages(self, *, section_id: str | None = None):
        return [
            {
                "id": "page-1",
                "title": "Release Notes",
                "createdDateTime": "2024-01-03T10:00:00Z",
                "lastModifiedDateTime": "2024-01-09T12:00:00Z",
                "links": {
                    "oneNoteWebUrl": {
                        "href": "https://example.com/page-1",
                    }
                },
            },
            {
                "id": "page-2",
                "title": "Sprint Plan",
                "createdDateTime": "2024-01-01T08:00:00Z",
                "lastModifiedDateTime": "2024-01-10T07:00:00Z",
                "links": {
                    "oneNoteWebUrl": {
                        "href": "https://example.com/page-2",
                    }
                },
            },
            {
                "id": "page-3",
                "title": "Architecture Notes",
                "createdDateTime": "2024-01-02T09:00:00Z",
                "lastModifiedDateTime": "2024-01-05T06:00:00Z",
                "links": {
                    "oneNoteWebUrl": {
                        "href": "https://example.com/page-3",
                    }
                },
            }
        ]

    def get_page_content(self, *, page_id: str, include_ids: bool = True):
        self.page_content_call = {
            "page_id": page_id,
            "include_ids": include_ids,
        }
        return "<html><body><p>Page body</p></body></html>"

    def create_page(
        self,
        *,
        section_id: str,
        title: str,
        html_or_text: str,
        asset_paths=None,
        treat_as_plain_text: bool = False,
    ):
        self.created_calls.append(
            {
                "section_id": section_id,
                "title": title,
                "html_or_text": html_or_text,
                "asset_paths": list(asset_paths or []),
                "treat_as_plain_text": treat_as_plain_text,
            }
        )
        return {"id": "page-1", "title": title}

    def append_page(
        self,
        *,
        page_id: str,
        html_or_text: str,
        target: str = "body",
        treat_as_plain_text: bool = False,
    ) -> None:
        self.appended = {
            "page_id": page_id,
            "html_or_text": html_or_text,
            "target": target,
            "treat_as_plain_text": treat_as_plain_text,
        }

    def replace_page_content(
        self,
        *,
        page_id: str,
        target: str,
        html_or_text: str,
        treat_as_plain_text: bool = False,
    ) -> None:
        self.replaced = {
            "page_id": page_id,
            "target": target,
            "html_or_text": html_or_text,
            "treat_as_plain_text": treat_as_plain_text,
        }

    def replace_page_with_assets(
        self,
        *,
        page_id: str,
        target: str,
        asset_paths: list[str],
        html_or_text: str | None = None,
        treat_as_plain_text: bool = False,
    ) -> None:
        self.replaced_with_assets = {
            "page_id": page_id,
            "target": target,
            "asset_paths": list(asset_paths),
            "html_or_text": html_or_text,
            "treat_as_plain_text": treat_as_plain_text,
        }

    def attach_to_page(self, *, page_id: str, asset_paths: list[str], target: str = "body") -> None:
        self.attached_calls.append(
            {"page_id": page_id, "asset_paths": list(asset_paths), "target": target}
        )


def test_connect_emits_json() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        ["connect", "--client-id", "client-1", "--json"],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert '"connected": true' in stdout.getvalue().lower()
    assert stderr.getvalue() == ""


def test_list_cached_accounts_formats_human_output_without_graph_client() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    class UnusedGraphClient:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("list-cached-accounts should not construct the Graph client")

    exit_code = main(
        ["list-cached-accounts", "--client-id", "client-1"],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=UnusedGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stdout.getvalue() == "alice@example.com  Alice Example\nbob@example.com  Bob Example\n"
    assert stderr.getvalue() == ""


def test_list_cached_accounts_json_output_and_empty_cache() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    class EmptyAuthenticator(FakeAuthenticator):
        def list_cached_accounts(self):
            return []

    exit_code = main(
        ["list-cached-accounts", "--client-id", "client-1", "--json"],
        authenticator_cls=EmptyAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stdout.getvalue() == "[]\n"
    assert stderr.getvalue() == ""


def test_list_cached_accounts_empty_human_output() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    class EmptyAuthenticator(FakeAuthenticator):
        def list_cached_accounts(self):
            return []

    exit_code = main(
        ["list-cached-accounts", "--client-id", "client-1"],
        authenticator_cls=EmptyAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stdout.getvalue() == "No cached accounts found.\n"
    assert stderr.getvalue() == ""


def test_clear_auth_succeeds_without_client_id(tmp_path: Path) -> None:
    cache_path = tmp_path / "token-cache.json"
    cache_path.write_text("cached-token")
    stdout = io.StringIO()
    stderr = io.StringIO()

    class UnusedAuthenticator:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("clear-auth should not construct the authenticator")

    exit_code = main(
        [
            "clear-auth",
            "--cache-path",
            str(cache_path),
            "--json",
        ],
        authenticator_cls=UnusedAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert '"removed": true' in stdout.getvalue().lower()
    assert not cache_path.exists()
    assert stderr.getvalue() == ""


def test_create_page_with_assets_uses_plain_text_file(tmp_path: Path) -> None:
    text_path = tmp_path / "summary.txt"
    asset_path = tmp_path / "report.pdf"
    text_path.write_text("Daily update")
    asset_path.write_text("placeholder")
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        [
            "create-page-with-assets",
            "--client-id",
            "client-1",
            "--section",
            "section-1",
            "--title",
            "Daily update",
            "--text-file",
            str(text_path),
            "--asset",
            str(asset_path),
            "--json",
        ],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert FakeGraphClient.last_instance is not None
    assert FakeGraphClient.last_instance.created_calls == [
        {
            "section_id": "section-1",
            "title": "Daily update",
            "html_or_text": "Daily update",
            "asset_paths": [str(asset_path)],
            "treat_as_plain_text": True,
        }
    ]
    assert stderr.getvalue() == ""


def test_attach_to_page_tracks_files(tmp_path: Path) -> None:
    asset_a = tmp_path / "a.png"
    asset_b = tmp_path / "b.pdf"
    asset_a.write_text("a")
    asset_b.write_text("b")
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        [
            "attach-to-page",
            "--client-id",
            "client-1",
            "--page",
            "page-7",
            "--file",
            str(asset_a),
            "--file",
            str(asset_b),
            "--json",
        ],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert FakeGraphClient.last_instance is not None
    assert FakeGraphClient.last_instance.attached_calls == [
        {
            "page_id": "page-7",
            "asset_paths": [str(asset_a), str(asset_b)],
            "target": "body",
        }
    ]
    assert stderr.getvalue() == ""


def test_list_pages_formats_human_readable_output() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        ["list-pages", "--client-id", "client-1", "--section", "section-1"],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    rendered = stdout.getvalue()
    assert "page-1  Release Notes  https://example.com/page-1" in rendered
    assert "page-2  Sprint Plan  https://example.com/page-2" in rendered
    assert "page-3  Architecture Notes  https://example.com/page-3" in rendered
    assert stderr.getvalue() == ""


def test_list_notebooks_name_filter_human_output_and_limit() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        [
            "list-notebooks",
            "--client-id",
            "client-1",
            "--name-contains",
            "te",
            "--limit",
            "1",
        ],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stdout.getvalue() == "nb-1  Team Notes [default]\n"
    assert stderr.getvalue() == ""


def test_list_notebooks_name_filter_json_output() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        [
            "list-notebooks",
            "--client-id",
            "client-1",
            "--name-contains",
            "ARCH",
            "--json",
        ],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    rendered = stdout.getvalue()
    assert '"displayName": "Personal Archive"' in rendered
    assert '"displayName": "Team Notes"' not in rendered
    assert stderr.getvalue() == ""


def test_list_notebooks_name_filter_empty_result() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        [
            "list-notebooks",
            "--client-id",
            "client-1",
            "--name-contains",
            "missing notebook",
        ],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stdout.getvalue() == "No notebooks found.\n"
    assert stderr.getvalue() == ""


def test_list_sections_name_filter_human_output_and_limit() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        [
            "list-sections",
            "--client-id",
            "client-1",
            "--name-contains",
            "note",
            "--limit",
            "1",
        ],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stdout.getvalue() == "sec-2  Meeting Notes (Team Notes) [default]\n"
    assert stderr.getvalue() == ""


def test_list_sections_name_filter_json_output() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        [
            "list-sections",
            "--client-id",
            "client-1",
            "--name-contains",
            "ARC",
            "--json",
        ],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    rendered = stdout.getvalue()
    assert '"displayName": "Archive"' in rendered
    assert '"displayName": "Sprint"' not in rendered
    assert stderr.getvalue() == ""


def test_list_sections_name_filter_empty_result() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        [
            "list-sections",
            "--client-id",
            "client-1",
            "--name-contains",
            "missing section",
        ],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stdout.getvalue() == "No sections found.\n"
    assert stderr.getvalue() == ""


def test_list_pages_json_output() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        ["list-pages", "--client-id", "client-1", "--json"],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    rendered = stdout.getvalue()
    assert '"id": "page-1"' in rendered
    assert '"title": "Release Notes"' in rendered
    assert '"href": "https://example.com/page-1"' in rendered
    assert '"title": "Sprint Plan"' in rendered
    assert '"title": "Architecture Notes"' in rendered
    assert stderr.getvalue() == ""


def test_list_pages_title_filter_human_output() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        [
            "list-pages",
            "--client-id",
            "client-1",
            "--title-contains",
            "release",
        ],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stdout.getvalue() == "page-1  Release Notes  https://example.com/page-1\n"
    assert stderr.getvalue() == ""


def test_list_pages_title_filter_json_output() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        [
            "list-pages",
            "--client-id",
            "client-1",
            "--title-contains",
            "SPRINT",
            "--json",
        ],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    rendered = stdout.getvalue()
    assert '"title": "Sprint Plan"' in rendered
    assert '"title": "Release Notes"' not in rendered
    assert stderr.getvalue() == ""


def test_list_pages_title_filter_empty_result() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        [
            "list-pages",
            "--client-id",
            "client-1",
            "--title-contains",
            "missing title",
        ],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stdout.getvalue() == "No pages found.\n"
    assert stderr.getvalue() == ""


def test_list_pages_sorts_by_title() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        ["list-pages", "--client-id", "client-1", "--sort", "title"],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stdout.getvalue().splitlines() == [
        "page-3  Architecture Notes  https://example.com/page-3",
        "page-1  Release Notes  https://example.com/page-1",
        "page-2  Sprint Plan  https://example.com/page-2",
    ]


def test_list_pages_sorts_by_created_timestamp() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        ["list-pages", "--client-id", "client-1", "--sort", "created"],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stdout.getvalue().splitlines() == [
        "page-2  Sprint Plan  created 2024-01-01T08:00:00+00:00  https://example.com/page-2",
        "page-3  Architecture Notes  created 2024-01-02T09:00:00+00:00  https://example.com/page-3",
        "page-1  Release Notes  created 2024-01-03T10:00:00+00:00  https://example.com/page-1",
    ]


def test_list_pages_sorts_by_modified_descending_and_limits_after_filter() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        [
            "list-pages",
            "--client-id",
            "client-1",
            "--sort",
            "modified",
            "--descending",
            "--limit",
            "2",
        ],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stdout.getvalue().splitlines() == [
        "page-2  Sprint Plan  modified 2024-01-10T07:00:00+00:00  https://example.com/page-2",
        "page-1  Release Notes  modified 2024-01-09T12:00:00+00:00  https://example.com/page-1",
    ]
    assert stderr.getvalue() == ""


def test_parse_page_timestamp_returns_none_for_invalid_values() -> None:
    assert _parse_page_timestamp("not-a-timestamp") is None


def test_item_name_contains_uses_case_insensitive_matching() -> None:
    assert _item_name_contains(
        {"displayName": "Team Notes"},
        needle="notes",
        name_keys=("displayName",),
    )
    assert _item_name_contains(
        {"title": "Release Notes"},
        needle="release",
        name_keys=("title", "displayName"),
    )
    assert not _item_name_contains(
        {"displayName": "Team Notes"},
        needle="archive",
        name_keys=("displayName",),
    )


def test_get_page_content_writes_raw_html_to_stdout() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        ["get-page-content", "--client-id", "client-1", "--page", "page-1"],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stdout.getvalue() == "<html><body><p>Page body</p></body></html>\n"
    assert FakeGraphClient.last_instance.page_content_call == {
        "page_id": "page-1",
        "include_ids": True,
    }
    assert stderr.getvalue() == ""


def test_get_page_content_writes_file_when_output_is_provided(tmp_path: Path) -> None:
    output_path = tmp_path / "page-content.html"
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        [
            "get-page-content",
            "--client-id",
            "client-1",
            "--page",
            "page-1",
            "--no-include-ids",
            "--output",
            str(output_path),
        ],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert output_path.read_text() == "<html><body><p>Page body</p></body></html>"
    assert stdout.getvalue() == f"Wrote page content to {output_path}\n"
    assert FakeGraphClient.last_instance.page_content_call == {
        "page_id": "page-1",
        "include_ids": False,
    }
    assert stderr.getvalue() == ""


def test_replace_page_content_reports_success() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        [
            "replace-page-content",
            "--client-id",
            "client-1",
            "--page",
            "page-1",
            "--target",
            "element-42",
            "--content",
            "<p>Updated</p>",
        ],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stdout.getvalue() == "Replaced content at target element-42 on page page-1.\n"
    assert FakeGraphClient.last_instance.replaced == {
        "page_id": "page-1",
        "target": "element-42",
        "html_or_text": "<p>Updated</p>",
        "treat_as_plain_text": False,
    }
    assert stderr.getvalue() == ""


def test_replace_page_content_plain_text_sets_flag_and_json_output() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        [
            "replace-page-content",
            "--client-id",
            "client-1",
            "--page",
            "page-1",
            "--target",
            "element-42",
            "--content",
            "<body>literal</body>",
            "--plain-text",
            "--json",
        ],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert '"action": "replace"' in stdout.getvalue()
    assert FakeGraphClient.last_instance.replaced == {
        "page_id": "page-1",
        "target": "element-42",
        "html_or_text": "<body>literal</body>",
        "treat_as_plain_text": True,
    }
    assert stderr.getvalue() == ""


def test_replace_page_with_assets_accepts_mixed_content_and_assets(tmp_path: Path) -> None:
    asset_path = tmp_path / "diagram.png"
    asset_path.write_text("placeholder")
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        [
            "replace-page-with-assets",
            "--client-id",
            "client-1",
            "--page",
            "page-1",
            "--target",
            "element-42",
            "--content",
            "<p>Updated</p>",
            "--asset",
            str(asset_path),
        ],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stdout.getvalue() == (
        f"Replaced content at target element-42 on page page-1 with 1 asset(s).\n"
    )
    assert FakeGraphClient.last_instance.replaced_with_assets == {
        "page_id": "page-1",
        "target": "element-42",
        "asset_paths": [str(asset_path)],
        "html_or_text": "<p>Updated</p>",
        "treat_as_plain_text": False,
    }
    assert stderr.getvalue() == ""


def test_replace_page_with_assets_supports_asset_only_json_output(tmp_path: Path) -> None:
    asset_path = tmp_path / "attachment.pdf"
    asset_path.write_text("placeholder")
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        [
            "replace-page-with-assets",
            "--client-id",
            "client-1",
            "--page",
            "page-1",
            "--target",
            "element-42",
            "--asset",
            str(asset_path),
            "--json",
        ],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FakeGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert '"action": "replace"' in stdout.getvalue()
    assert FakeGraphClient.last_instance.replaced_with_assets == {
        "page_id": "page-1",
        "target": "element-42",
        "asset_paths": [str(asset_path)],
        "html_or_text": None,
        "treat_as_plain_text": False,
    }
    assert stderr.getvalue() == ""


def test_cli_returns_one_for_graph_transport_failure() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    class FailingGraphClient:
        def __init__(self, *, access_token: str) -> None:
            self.access_token = access_token

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _tb) -> None:
            return None

        def get_me(self):
            raise GraphRequestError(
                status_code=0,
                code="transport_error",
                message="GET /me failed: connection refused",
            )

    exit_code = main(
        ["whoami", "--client-id", "client-1"],
        authenticator_cls=FakeAuthenticator,
        graph_client_cls=FailingGraphClient,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 1
    assert "Graph transport_error: GET /me failed: connection refused" in stderr.getvalue()
