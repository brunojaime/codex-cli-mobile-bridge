from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any

import httpx

from html_builder import (
    build_append_fragment,
    build_create_page_parts,
    build_replace_fragment,
    build_update_page_parts,
    merge_document_with_assets,
    normalize_onenote_markup,
    prepare_asset_parts,
)


@dataclass(slots=True, frozen=True)
class GraphRequestError(RuntimeError):
    status_code: int
    code: str | None
    message: str

    def __str__(self) -> str:
        if self.status_code <= 0:
            if self.code:
                return f"Graph {self.code}: {self.message}"
            return f"Graph error: {self.message}"
        if self.code:
            return f"Graph API {self.status_code} {self.code}: {self.message}"
        return f"Graph API {self.status_code}: {self.message}"


class OneNoteGraphClient:
    def __init__(
        self,
        *,
        access_token: str,
        base_url: str = "https://graph.microsoft.com/v1.0",
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        client: httpx.Client | None = None,
    ) -> None:
        self._default_headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=self._default_headers,
            timeout=timeout_seconds,
        )
        self._owns_client = client is None
        self._max_retries = max_retries

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "OneNoteGraphClient":
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        self.close()

    def get_me(self) -> dict[str, Any]:
        return self._request("GET", "/me")

    def list_notebooks(self) -> list[dict[str, Any]]:
        return self._collect_paged_values(
            "/me/onenote/notebooks",
            params={
                "$select": "id,displayName,isDefault,createdDateTime,lastModifiedDateTime",
                "$top": "100",
            },
        )

    def list_sections(self, *, notebook_id: str | None = None) -> list[dict[str, Any]]:
        path = (
            f"/me/onenote/notebooks/{notebook_id}/sections"
            if notebook_id
            else "/me/onenote/sections"
        )
        return self._collect_paged_values(
            path,
            params={
                "$select": (
                    "id,displayName,isDefault,parentNotebook/id,parentNotebook/displayName,"
                    "createdDateTime,lastModifiedDateTime"
                ),
                "$top": "100",
            },
        )

    def list_pages(self, *, section_id: str | None = None) -> list[dict[str, Any]]:
        path = (
            f"/me/onenote/sections/{section_id}/pages"
            if section_id
            else "/me/onenote/pages"
        )
        return self._collect_paged_values(
            path,
            params={
                "$select": "id,title,createdDateTime,lastModifiedDateTime,links",
                "$top": "100",
            },
        )

    def create_page(
        self,
        *,
        section_id: str,
        title: str,
        html_or_text: str,
        asset_paths: list[str] | None = None,
        treat_as_plain_text: bool = False,
    ) -> dict[str, Any]:
        asset_paths = asset_paths or []
        path = f"/me/onenote/sections/{section_id}/pages"
        normalized = normalize_onenote_markup(
            html_or_text=html_or_text,
            title=title,
            treat_as_plain_text=treat_as_plain_text,
        )
        if asset_paths:
            assets = prepare_asset_parts(asset_paths)
            document = merge_document_with_assets(
                title=title,
                html_or_fragment=html_or_text,
                assets=assets,
                treat_as_plain_text=treat_as_plain_text,
            )
            return self._request(
                "POST",
                path,
                files=build_create_page_parts(document_html=document, assets=assets),
            )
        if normalized.document_html is None:
            raise ValueError("A title is required to build a OneNote page document.")
        return self._request(
            "POST",
            path,
            content=normalized.document_html.encode("utf-8"),
            headers={"Content-Type": "text/html; charset=utf-8"},
        )

    def append_page(
        self,
        *,
        page_id: str,
        html_or_text: str,
        target: str = "body",
        treat_as_plain_text: bool = False,
    ) -> None:
        fragment = build_append_fragment(
            html_or_fragment=html_or_text,
            treat_as_plain_text=treat_as_plain_text,
        )
        self.update_page(
            page_id=page_id,
            changes=[{"target": target, "action": "append", "content": fragment}],
        )

    def replace_page_content(
        self,
        *,
        page_id: str,
        target: str,
        html_or_text: str,
        treat_as_plain_text: bool = False,
    ) -> None:
        fragment = build_replace_fragment(
            html_or_fragment=html_or_text,
            treat_as_plain_text=treat_as_plain_text,
        )
        self.update_page(
            page_id=page_id,
            changes=[{"target": target, "action": "replace", "content": fragment}],
        )

    def replace_page_with_assets(
        self,
        *,
        page_id: str,
        target: str,
        asset_paths: list[str],
        html_or_text: str | None = None,
        treat_as_plain_text: bool = False,
    ) -> None:
        assets = prepare_asset_parts(asset_paths)
        fragment = build_replace_fragment(
            html_or_fragment=html_or_text,
            assets=assets,
            treat_as_plain_text=treat_as_plain_text,
        )
        self.update_page(
            page_id=page_id,
            changes=[{"target": target, "action": "replace", "content": fragment}],
            asset_paths=asset_paths,
        )

    def attach_to_page(
        self,
        *,
        page_id: str,
        asset_paths: list[str],
        target: str = "body",
    ) -> None:
        assets = prepare_asset_parts(asset_paths)
        fragment = build_append_fragment(assets=assets)
        self.update_page(
            page_id=page_id,
            changes=[{"target": target, "action": "append", "content": fragment}],
            asset_paths=asset_paths,
        )

    def update_page(
        self,
        *,
        page_id: str,
        changes: list[dict[str, Any]],
        asset_paths: list[str] | None = None,
    ) -> None:
        path = f"/me/onenote/pages/{page_id}/content"
        asset_paths = asset_paths or []
        if asset_paths:
            assets = prepare_asset_parts(asset_paths)
            self._request(
                "PATCH",
                path,
                files=build_update_page_parts(commands=changes, assets=assets),
            )
            return

        self._request(
            "PATCH",
            path,
            content=json.dumps(changes).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

    def get_page_content(
        self,
        *,
        page_id: str,
        include_ids: bool = True,
    ) -> str:
        params = {"includeIDs": "true"} if include_ids else None
        response = self._request(
            "GET",
            f"/me/onenote/pages/{page_id}/content",
            params=params,
            expect_json=False,
        )
        assert isinstance(response, str)
        return response

    def _request(
        self,
        method: str,
        path: str,
        *,
        expect_json: bool = True,
        **kwargs: Any,
    ) -> Any:
        headers = {
            **self._default_headers,
            **dict(kwargs.pop("headers", {}) or {}),
        }
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.request(method, path, headers=headers, **kwargs)
            except httpx.HTTPError as exc:
                raise GraphRequestError(
                    status_code=0,
                    code="transport_error",
                    message=f"{method} {path} failed: {exc}",
                ) from exc
            if response.status_code in {429, 503, 504} and attempt < self._max_retries:
                wait_seconds = _retry_delay_seconds(response, attempt)
                time.sleep(wait_seconds)
                continue
            if response.is_error:
                raise _build_graph_error(response)
            if response.status_code == 204:
                return None
            if not expect_json:
                return response.text
            if not response.content:
                return {}
            try:
                return response.json()
            except ValueError as exc:
                raise GraphRequestError(
                    status_code=response.status_code,
                    code="invalid_json",
                    message=f"{method} {path} returned invalid JSON.",
                ) from exc
        raise RuntimeError("Graph request retries were exhausted unexpectedly.")

    def _collect_paged_values(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        next_path: str | None = path
        next_params = params
        while next_path is not None:
            payload = self._request("GET", next_path, params=next_params)
            items.extend(list(payload.get("value", [])))
            next_path = payload.get("@odata.nextLink")
            next_params = None
        return items


def _retry_delay_seconds(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(float(retry_after), 0.0)
        except ValueError:
            pass
    return min(2**attempt, 10)


def _build_graph_error(response: httpx.Response) -> GraphRequestError:
    code: str | None = None
    message = response.text
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message") or message
    return GraphRequestError(
        status_code=response.status_code,
        code=code,
        message=message,
    )
