from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import html
import mimetypes
from pathlib import Path
import re
from typing import Any


_IMAGE_CONTENT_TYPES = {
    "image/bmp",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
}


@dataclass(slots=True, frozen=True)
class AssetPart:
    part_name: str
    filename: str
    content_type: str
    kind: str
    data: bytes


@dataclass(slots=True, frozen=True)
class NormalizedOneNoteMarkup:
    body_html: str
    document_html: str | None


def looks_like_html_document(raw_html: str) -> bool:
    return looks_like_full_html_document(raw_html) or looks_like_body_document(raw_html)


def looks_like_full_html_document(raw_html: str) -> bool:
    return "<html" in raw_html.lower()


def looks_like_body_document(raw_html: str) -> bool:
    return re.search(r"<body(?:\s|>)", raw_html, flags=re.IGNORECASE) is not None


def text_to_html_fragment(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "<p></p>"

    paragraphs = [segment.strip() for segment in re.split(r"\n\s*\n", stripped)]
    rendered: list[str] = []
    for paragraph in paragraphs:
        if not paragraph:
            continue
        lines = [html.escape(line.rstrip()) for line in paragraph.splitlines()]
        rendered.append(f"<p>{'<br />'.join(lines)}</p>")
    return "".join(rendered) or "<p></p>"


def coerce_html_fragment(raw_text: str, *, treat_as_plain_text: bool = False) -> str:
    if treat_as_plain_text:
        return text_to_html_fragment(raw_text)
    return raw_text if raw_text.strip() else "<p></p>"


def prepare_asset_parts(paths: list[str | Path]) -> list[AssetPart]:
    prepared: list[AssetPart] = []
    image_index = 0
    file_index = 0

    for raw_path in paths:
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Asset was not found: {path}")
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type in _IMAGE_CONTENT_TYPES:
            image_index += 1
            prepared.append(
                AssetPart(
                    part_name=f"imageBlock{image_index}",
                    filename=path.name,
                    content_type=content_type,
                    kind="image",
                    data=path.read_bytes(),
                )
            )
            continue

        file_index += 1
        prepared.append(
            AssetPart(
                part_name=f"fileBlock{file_index}",
                filename=path.name,
                content_type=content_type,
                kind="file",
                data=path.read_bytes(),
            )
        )
    return prepared


def build_asset_markup(assets: list[AssetPart]) -> str:
    blocks: list[str] = []
    for asset in assets:
        safe_name = html.escape(asset.filename, quote=True)
        if asset.kind == "image":
            blocks.append(
                f'<p><img src="name:{asset.part_name}" alt="{safe_name}" /></p>'
            )
            continue
        blocks.append(
            "<p>"
            f'<object data-attachment="{safe_name}" '
            f'data="name:{asset.part_name}" '
            f'type="{html.escape(asset.content_type, quote=True)}"></object>'
            "</p>"
        )
    return "".join(blocks)


def build_page_document(
    *,
    title: str,
    body_html: str,
    created: datetime | None = None,
) -> str:
    created_at = created or datetime.now(timezone.utc)
    created_value = created_at.isoformat()
    safe_title = html.escape(title)
    return (
        "<!DOCTYPE html>"
        "<html>"
        "<head>"
        f"<title>{safe_title}</title>"
        f'<meta name="created" content="{created_value}" />'
        "</head>"
        f"<body>{body_html}</body>"
        "</html>"
    )


def normalize_onenote_markup(
    *,
    html_or_text: str,
    title: str | None = None,
    treat_as_plain_text: bool = False,
) -> NormalizedOneNoteMarkup:
    if treat_as_plain_text:
        body_html = text_to_html_fragment(html_or_text)
    elif looks_like_html_document(html_or_text):
        body_html = extract_body_fragment(html_or_text)
    else:
        body_html = coerce_html_fragment(html_or_text, treat_as_plain_text=False)

    if title is None:
        document_html = None
    elif treat_as_plain_text:
        document_html = build_page_document(title=title, body_html=body_html)
    elif looks_like_full_html_document(html_or_text):
        document_html = html_or_text
    else:
        document_html = build_page_document(title=title, body_html=body_html)

    return NormalizedOneNoteMarkup(body_html=body_html, document_html=document_html)


def merge_document_with_assets(
    *,
    title: str,
    html_or_fragment: str,
    assets: list[AssetPart],
    treat_as_plain_text: bool = False,
) -> str:
    normalized = normalize_onenote_markup(
        html_or_text=html_or_fragment,
        title=title,
        treat_as_plain_text=treat_as_plain_text,
    )
    asset_markup = build_asset_markup(assets)
    if normalized.document_html is None:
        raise ValueError("A title is required to build a OneNote document.")
    return inject_fragment_into_document(normalized.document_html, asset_markup)


def inject_fragment_into_document(document_html: str, fragment: str) -> str:
    body_close = re.compile(r"</body\s*>", flags=re.IGNORECASE)
    html_close = re.compile(r"</html\s*>", flags=re.IGNORECASE)

    if body_close.search(document_html):
        return body_close.sub(fragment + "</body>", document_html, count=1)
    if html_close.search(document_html):
        return html_close.sub(f"<body>{fragment}</body></html>", document_html, count=1)
    return document_html + fragment


def extract_body_fragment(document_html: str) -> str:
    match = re.search(r"<body[^>]*>(.*)</body\s*>", document_html, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return document_html.strip()


def build_append_fragment(
    *,
    html_or_fragment: str | None = None,
    assets: list[AssetPart] | None = None,
    treat_as_plain_text: bool = False,
) -> str:
    segments: list[str] = []
    if html_or_fragment:
        normalized = normalize_onenote_markup(
            html_or_text=html_or_fragment,
            treat_as_plain_text=treat_as_plain_text,
        )
        segments.append(normalized.body_html)
    if assets:
        segments.append(build_asset_markup(assets))
    if not segments:
        raise ValueError("Append operations require HTML content, assets, or both.")
    return "<div>" + "".join(segments) + "</div>"


def build_replace_fragment(
    *,
    html_or_fragment: str | None = None,
    assets: list[AssetPart] | None = None,
    treat_as_plain_text: bool = False,
) -> str:
    segments: list[str] = []
    if html_or_fragment:
        normalized = normalize_onenote_markup(
            html_or_text=html_or_fragment,
            treat_as_plain_text=treat_as_plain_text,
        )
        segments.append(normalized.body_html)
    if assets:
        segments.append(build_asset_markup(assets))
    if not segments:
        raise ValueError("Replace operations require HTML content, assets, or both.")
    if len(segments) == 1 and assets is None:
        return segments[0]
    return "<div>" + "".join(segments) + "</div>"


def build_create_page_parts(
    *,
    document_html: str,
    assets: list[AssetPart],
) -> list[tuple[str, tuple[str | None, bytes, str]]]:
    parts: list[tuple[str, tuple[str | None, bytes, str]]] = [
        (
            "Presentation",
            (None, document_html.encode("utf-8"), "text/html; charset=utf-8"),
        )
    ]
    parts.extend(_asset_parts_to_httpx_files(assets))
    return parts


def build_update_page_parts(
    *,
    commands: list[dict[str, Any]],
    assets: list[AssetPart],
) -> list[tuple[str, tuple[str | None, bytes, str]]]:
    import json

    parts: list[tuple[str, tuple[str | None, bytes, str]]] = [
        (
            "Commands",
            (
                None,
                json.dumps(commands).encode("utf-8"),
                "application/json",
            ),
        )
    ]
    parts.extend(_asset_parts_to_httpx_files(assets))
    return parts


def _asset_parts_to_httpx_files(
    assets: list[AssetPart],
) -> list[tuple[str, tuple[str | None, bytes, str]]]:
    return [
        (
            asset.part_name,
            (asset.filename, asset.data, asset.content_type),
        )
        for asset in assets
    ]
