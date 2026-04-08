from __future__ import annotations

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

from html_builder import (  # noqa: E402
    build_append_fragment,
    build_asset_markup,
    build_create_page_parts,
    build_page_document,
    build_replace_fragment,
    merge_document_with_assets,
    prepare_asset_parts,
    text_to_html_fragment,
)


def test_text_to_html_fragment_preserves_paragraphs() -> None:
    fragment = text_to_html_fragment("Line one\nLine two\n\nSecond block")
    assert fragment == "<p>Line one<br />Line two</p><p>Second block</p>"


def test_prepare_asset_parts_and_markup(tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    file_path = tmp_path / "notes.pdf"
    image_path.write_bytes(b"png-data")
    file_path.write_bytes(b"pdf-data")

    assets = prepare_asset_parts([image_path, file_path])

    assert [asset.part_name for asset in assets] == ["imageBlock1", "fileBlock1"]
    markup = build_asset_markup(assets)
    assert 'src="name:imageBlock1"' in markup
    assert 'data="name:fileBlock1"' in markup
    assert 'data-attachment="notes.pdf"' in markup


def test_build_create_page_parts_wraps_presentation_html(tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"binary-image")
    assets = prepare_asset_parts([image_path])

    document = build_page_document(title="Daily Notes", body_html="<p>Hello</p>")
    parts = build_create_page_parts(document_html=document, assets=assets)

    assert parts[0][0] == "Presentation"
    assert parts[0][1][2] == "text/html; charset=utf-8"
    assert parts[1][0] == "imageBlock1"
    assert parts[1][1][0] == "image.png"


def test_build_append_fragment_extracts_body_from_document() -> None:
    document = "<html><body><p>Inside body</p></body></html>"
    fragment = build_append_fragment(html_or_fragment=document)

    assert fragment == "<div><p>Inside body</p></div>"


def test_build_append_fragment_plain_text_escapes_literal_markup() -> None:
    fragment = build_append_fragment(
        html_or_fragment="<html>literal</html>\n<body>text</body>",
        treat_as_plain_text=True,
    )

    assert "&lt;html&gt;literal&lt;/html&gt;" in fragment
    assert "&lt;body&gt;text&lt;/body&gt;" in fragment
    assert "<html>literal</html>" not in fragment


def test_merge_document_with_assets_plain_text_escapes_literal_markup(tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"binary-image")
    assets = prepare_asset_parts([image_path])

    document = merge_document_with_assets(
        title="Literal Markup",
        html_or_fragment="<html>literal</html>\n<body>literal</body>",
        assets=assets,
        treat_as_plain_text=True,
    )

    assert "&lt;html&gt;literal&lt;/html&gt;" in document
    assert "&lt;body&gt;literal&lt;/body&gt;" in document
    assert document.count("<body>") == 1
    assert 'src="name:imageBlock1"' in document


def test_build_replace_fragment_supports_assets_only(tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"binary-image")
    assets = prepare_asset_parts([image_path])

    fragment = build_replace_fragment(assets=assets)

    assert fragment == '<div><p><img src="name:imageBlock1" alt="image.png" /></p></div>'


def test_build_replace_fragment_supports_mixed_text_and_assets(tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"binary-image")
    assets = prepare_asset_parts([image_path])

    fragment = build_replace_fragment(
        html_or_fragment="Replacement text",
        assets=assets,
        treat_as_plain_text=True,
    )

    assert fragment == (
        '<div><p>Replacement text</p><p><img src="name:imageBlock1" alt="image.png" /></p></div>'
    )
