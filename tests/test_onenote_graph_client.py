from __future__ import annotations

from pathlib import Path
import sys

import httpx


_SKILL_SCRIPTS = (
    Path(__file__).resolve().parents[1] / "skills" / "onenote-connect" / "scripts"
)
if str(_SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS))

from graph_client import GraphRequestError, OneNoteGraphClient  # noqa: E402


class RecordingClient:
    def __init__(self, responses: list[httpx.Response] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.responses = list(responses or [])

    def request(self, method: str, path: str, headers=None, **kwargs):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "headers": dict(headers or {}),
                "kwargs": kwargs,
            }
        )
        request_url = (
            path
            if str(path).startswith("http")
            else f"https://graph.microsoft.com{path}"
        )
        request = httpx.Request(method, request_url)
        if self.responses:
            response = self.responses.pop(0)
            return response
        return httpx.Response(
            201, request=request, json={"id": "page-1", "title": "Example"}
        )

    def close(self) -> None:
        return None


class RaisingClient:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls: list[dict[str, object]] = []

    def request(self, method: str, path: str, headers=None, **kwargs):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "headers": dict(headers or {}),
                "kwargs": kwargs,
            }
        )
        raise self.exc

    def close(self) -> None:
        return None


def _json_response(
    method: str, path: str, payload: dict, status_code: int = 200, headers=None
) -> httpx.Response:
    request_url = (
        path if str(path).startswith("http") else f"https://graph.microsoft.com{path}"
    )
    request = httpx.Request(method, request_url)
    return httpx.Response(status_code, request=request, json=payload, headers=headers)


def test_injected_client_receives_bearer_auth_header() -> None:
    client = RecordingClient(
        responses=[
            _json_response(
                "GET",
                "/me",
                {"displayName": "Alice Example"},
            )
        ]
    )

    with OneNoteGraphClient(access_token="token-123", client=client) as graph:
        graph.get_me()

    call = client.calls[0]
    headers = call["headers"]
    assert headers["Authorization"] == "Bearer token-123"
    assert headers["Accept"] == "application/json"


def test_create_page_with_body_document_does_not_nest_body_tags() -> None:
    client = RecordingClient()

    with OneNoteGraphClient(access_token="token", client=client) as graph:
        graph.create_page(
            section_id="section-1",
            title="Body Input",
            html_or_text="<body><p>Wrapped once</p></body>",
        )

    call = client.calls[0]
    content = call["kwargs"]["content"].decode("utf-8")
    assert content.count("<body>") == 1
    assert content.count("</body>") == 1
    assert "<body><body>" not in content
    assert "<p>Wrapped once</p>" in content


def test_create_page_plain_text_escapes_literal_html_markers() -> None:
    client = RecordingClient()

    with OneNoteGraphClient(access_token="token", client=client) as graph:
        graph.create_page(
            section_id="section-1",
            title="Literal Markup",
            html_or_text="<html>literal</html>\n<body>literal</body>",
            treat_as_plain_text=True,
        )

    call = client.calls[0]
    content = call["kwargs"]["content"].decode("utf-8")
    assert "&lt;html&gt;literal&lt;/html&gt;" in content
    assert "&lt;body&gt;literal&lt;/body&gt;" in content
    assert "<html>literal</html>" not in content


def test_list_notebooks_follows_odata_next_link() -> None:
    client = RecordingClient(
        responses=[
            _json_response(
                "GET",
                "/me/onenote/notebooks",
                {
                    "value": [{"id": "nb-1", "displayName": "One"}],
                    "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/onenote/notebooks?$skiptoken=abc",
                },
            ),
            _json_response(
                "GET",
                "https://graph.microsoft.com/v1.0/me/onenote/notebooks?$skiptoken=abc",
                {
                    "value": [{"id": "nb-2", "displayName": "Two"}],
                },
            ),
        ]
    )

    with OneNoteGraphClient(access_token="token", client=client) as graph:
        notebooks = graph.list_notebooks()

    assert [notebook["id"] for notebook in notebooks] == ["nb-1", "nb-2"]
    assert client.calls[0]["path"] == "/me/onenote/notebooks"
    assert (
        client.calls[1]["path"]
        == "https://graph.microsoft.com/v1.0/me/onenote/notebooks?$skiptoken=abc"
    )


def test_list_sections_follows_odata_next_link() -> None:
    client = RecordingClient(
        responses=[
            _json_response(
                "GET",
                "/me/onenote/sections",
                {
                    "value": [{"id": "sec-1", "displayName": "One"}],
                    "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/onenote/sections?$skiptoken=def",
                },
            ),
            _json_response(
                "GET",
                "https://graph.microsoft.com/v1.0/me/onenote/sections?$skiptoken=def",
                {
                    "value": [{"id": "sec-2", "displayName": "Two"}],
                },
            ),
        ]
    )

    with OneNoteGraphClient(access_token="token", client=client) as graph:
        sections = graph.list_sections()

    assert [section["id"] for section in sections] == ["sec-1", "sec-2"]


def test_list_pages_uses_section_endpoint_and_follows_odata_next_link() -> None:
    client = RecordingClient(
        responses=[
            _json_response(
                "GET",
                "/me/onenote/sections/section-1/pages",
                {
                    "value": [
                        {
                            "id": "page-1",
                            "title": "First",
                            "links": {
                                "oneNoteWebUrl": {"href": "https://example.com/page-1"}
                            },
                        }
                    ],
                    "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/onenote/sections/section-1/pages?$skiptoken=ghi",
                },
            ),
            _json_response(
                "GET",
                "https://graph.microsoft.com/v1.0/me/onenote/sections/section-1/pages?$skiptoken=ghi",
                {
                    "value": [
                        {
                            "id": "page-2",
                            "title": "Second",
                            "links": {
                                "oneNoteWebUrl": {"href": "https://example.com/page-2"}
                            },
                        }
                    ],
                },
            ),
        ]
    )

    with OneNoteGraphClient(access_token="token", client=client) as graph:
        pages = graph.list_pages(section_id="section-1")

    assert [page["id"] for page in pages] == ["page-1", "page-2"]
    assert client.calls[0]["path"] == "/me/onenote/sections/section-1/pages"
    assert (
        client.calls[1]["path"]
        == "https://graph.microsoft.com/v1.0/me/onenote/sections/section-1/pages?$skiptoken=ghi"
    )
    assert client.calls[0]["kwargs"]["params"] == {
        "$select": "id,title,createdDateTime,lastModifiedDateTime,links",
        "$top": "100",
    }


def test_request_retries_on_429_then_succeeds(monkeypatch) -> None:
    client = RecordingClient(
        responses=[
            _json_response(
                "GET",
                "/me",
                {"error": {"code": "TooManyRequests", "message": "slow down"}},
                status_code=429,
                headers={"Retry-After": "0"},
            ),
            _json_response(
                "GET",
                "/me",
                {"displayName": "Alice Example"},
            ),
        ]
    )
    sleep_calls: list[float] = []
    monkeypatch.setattr("graph_client.time.sleep", sleep_calls.append)

    with OneNoteGraphClient(access_token="token", client=client) as graph:
        payload = graph.get_me()

    assert payload["displayName"] == "Alice Example"
    assert len(client.calls) == 2
    assert sleep_calls == [0.0]


def test_request_wraps_transport_failures() -> None:
    request = httpx.Request("GET", "https://graph.microsoft.com/me")
    client = RaisingClient(httpx.ConnectError("connection refused", request=request))

    with OneNoteGraphClient(access_token="token", client=client) as graph:
        try:
            graph.get_me()
        except GraphRequestError as exc:
            assert exc.code == "transport_error"
            assert "GET /me failed" in str(exc)
        else:
            raise AssertionError("Expected GraphRequestError")


def test_request_wraps_invalid_json_success_response() -> None:
    request = httpx.Request("GET", "https://graph.microsoft.com/me")
    response = httpx.Response(200, request=request, text="not-json")
    client = RecordingClient(responses=[response])

    with OneNoteGraphClient(access_token="token", client=client) as graph:
        try:
            graph.get_me()
        except GraphRequestError as exc:
            assert exc.code == "invalid_json"
            assert "GET /me returned invalid JSON." in str(exc)
        else:
            raise AssertionError("Expected GraphRequestError")


def test_get_page_content_includes_include_ids_query_by_default() -> None:
    client = RecordingClient(
        responses=[
            httpx.Response(
                200,
                request=httpx.Request(
                    "GET", "https://graph.microsoft.com/me/onenote/pages/page-1/content"
                ),
                text="<html><body>Page</body></html>",
            )
        ]
    )

    with OneNoteGraphClient(access_token="token", client=client) as graph:
        content = graph.get_page_content(page_id="page-1")

    assert content == "<html><body>Page</body></html>"
    assert client.calls[0]["kwargs"]["params"] == {"includeIDs": "true"}


def test_get_page_content_omits_include_ids_query_when_disabled() -> None:
    client = RecordingClient(
        responses=[
            httpx.Response(
                200,
                request=httpx.Request(
                    "GET", "https://graph.microsoft.com/me/onenote/pages/page-1/content"
                ),
                text="<html><body>Page</body></html>",
            )
        ]
    )

    with OneNoteGraphClient(access_token="token", client=client) as graph:
        graph.get_page_content(page_id="page-1", include_ids=False)

    assert client.calls[0]["kwargs"]["params"] is None


def test_replace_page_content_uses_replace_action_for_html_fragment() -> None:
    request = httpx.Request(
        "PATCH", "https://graph.microsoft.com/me/onenote/pages/page-1/content"
    )
    client = RecordingClient(responses=[httpx.Response(204, request=request)])

    with OneNoteGraphClient(access_token="token", client=client) as graph:
        graph.replace_page_content(
            page_id="page-1",
            target="element-42",
            html_or_text="<html><body><p>Updated</p></body></html>",
        )

    call = client.calls[0]
    assert call["method"] == "PATCH"
    assert call["path"] == "/me/onenote/pages/page-1/content"
    assert call["headers"]["Content-Type"] == "application/json"
    assert (
        call["kwargs"]["content"].decode("utf-8")
        == '[{"target": "element-42", "action": "replace", "content": "<p>Updated</p>"}]'
    )


def test_replace_page_content_escapes_plain_text_before_patch() -> None:
    request = httpx.Request(
        "PATCH", "https://graph.microsoft.com/me/onenote/pages/page-1/content"
    )
    client = RecordingClient(responses=[httpx.Response(204, request=request)])

    with OneNoteGraphClient(access_token="token", client=client) as graph:
        graph.replace_page_content(
            page_id="page-1",
            target="element-42",
            html_or_text="<body>literal</body>",
            treat_as_plain_text=True,
        )

    assert (
        client.calls[0]["kwargs"]["content"].decode("utf-8")
        == '[{"target": "element-42", "action": "replace", "content": "<p>&lt;body&gt;literal&lt;/body&gt;</p>"}]'
    )


def test_replace_page_with_assets_uses_multipart_patch_with_replace_action(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"binary-image")
    request = httpx.Request(
        "PATCH", "https://graph.microsoft.com/me/onenote/pages/page-1/content"
    )
    client = RecordingClient(responses=[httpx.Response(204, request=request)])

    with OneNoteGraphClient(access_token="token", client=client) as graph:
        graph.replace_page_with_assets(
            page_id="page-1",
            target="element-42",
            asset_paths=[str(image_path)],
            html_or_text="Replacement text",
            treat_as_plain_text=True,
        )

    call = client.calls[0]
    assert call["method"] == "PATCH"
    assert call["path"] == "/me/onenote/pages/page-1/content"
    files = call["kwargs"]["files"]
    assert files[0][0] == "Commands"
    assert (
        files[0][1][1].decode("utf-8")
        == '[{"target": "element-42", "action": "replace", "content": "<div><p>Replacement text</p><p><img src=\\"name:imageBlock1\\" alt=\\"image.png\\" /></p></div>"}]'
    )
    assert files[1][0] == "imageBlock1"
    assert files[1][1][0] == "image.png"


def test_replace_page_with_assets_supports_asset_only_patch(tmp_path: Path) -> None:
    file_path = tmp_path / "attachment.pdf"
    file_path.write_bytes(b"binary-pdf")
    request = httpx.Request(
        "PATCH", "https://graph.microsoft.com/me/onenote/pages/page-1/content"
    )
    client = RecordingClient(responses=[httpx.Response(204, request=request)])

    with OneNoteGraphClient(access_token="token", client=client) as graph:
        graph.replace_page_with_assets(
            page_id="page-1",
            target="element-42",
            asset_paths=[str(file_path)],
        )

    files = client.calls[0]["kwargs"]["files"]
    assert (
        files[0][1][1].decode("utf-8")
        == '[{"target": "element-42", "action": "replace", "content": "<div><p><object data-attachment=\\"attachment.pdf\\" data=\\"name:fileBlock1\\" type=\\"application/pdf\\"></object></p></div>"}]'
    )
    assert files[1][0] == "fileBlock1"
