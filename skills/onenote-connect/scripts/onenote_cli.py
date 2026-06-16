from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from auth import (
    AuthenticationDependencyError,
    AuthenticationError,
    OneNoteAuthenticator,
    auth_config_from_inputs,
    resolve_cache_path,
)
from graph_client import GraphRequestError, OneNoteGraphClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Authenticate with Microsoft Graph and manage OneNote content.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    connect = subparsers.add_parser("connect", help="Authenticate and cache a token.")
    _add_auth_arguments(connect)
    connect.add_argument(
        "--auth-flow",
        default="auto",
        choices=("auto", "device-code", "interactive"),
        help="Preferred delegated sign-in flow.",
    )
    connect.add_argument(
        "--login-hint",
        help="Preferred username or email to preselect during sign-in.",
    )
    connect.add_argument(
        "--force-interactive",
        action="store_true",
        help="Skip silent token acquisition and force an interactive login.",
    )
    connect.add_argument("--json", action="store_true", help="Emit JSON output.")

    clear_auth = subparsers.add_parser(
        "clear-auth",
        help="Delete the cached token store.",
    )
    _add_auth_arguments(clear_auth)
    clear_auth.add_argument("--json", action="store_true", help="Emit JSON output.")

    whoami = subparsers.add_parser("whoami", help="Show the connected Microsoft account.")
    _add_auth_arguments(whoami)
    whoami.add_argument("--json", action="store_true", help="Emit JSON output.")

    list_cached_accounts = subparsers.add_parser(
        "list-cached-accounts",
        help="List locally cached Microsoft identities without calling Graph.",
    )
    _add_auth_arguments(list_cached_accounts)
    list_cached_accounts.add_argument("--json", action="store_true", help="Emit JSON output.")

    list_notebooks = subparsers.add_parser(
        "list-notebooks",
        help="List notebooks the signed-in user can access.",
    )
    _add_auth_arguments(list_notebooks)
    list_notebooks.add_argument(
        "--name-contains",
        help="Case-insensitive substring filter applied to notebook names locally.",
    )
    list_notebooks.add_argument(
        "--limit",
        type=int,
        help="Maximum number of notebooks to emit after filtering.",
    )
    list_notebooks.add_argument("--json", action="store_true", help="Emit JSON output.")

    list_sections = subparsers.add_parser(
        "list-sections",
        help="List sections, optionally constrained to a notebook.",
    )
    _add_auth_arguments(list_sections)
    list_sections.add_argument("--notebook", help="Notebook ID.")
    list_sections.add_argument(
        "--name-contains",
        help="Case-insensitive substring filter applied to section names locally.",
    )
    list_sections.add_argument(
        "--limit",
        type=int,
        help="Maximum number of sections to emit after filtering.",
    )
    list_sections.add_argument("--json", action="store_true", help="Emit JSON output.")

    list_pages = subparsers.add_parser(
        "list-pages",
        help="List pages, optionally constrained to a section.",
    )
    _add_auth_arguments(list_pages)
    list_pages.add_argument("--section", help="Section ID.")
    list_pages.add_argument(
        "--title-contains",
        help="Case-insensitive substring filter applied to page titles locally.",
    )
    list_pages.add_argument(
        "--sort",
        choices=("title", "created", "modified"),
        help="Deterministic local sort order for matching pages.",
    )
    list_pages.add_argument(
        "--descending",
        action="store_true",
        help="Reverse the selected sort order.",
    )
    list_pages.add_argument(
        "--limit",
        type=int,
        help="Maximum number of pages to emit after filtering and sorting.",
    )
    list_pages.add_argument("--json", action="store_true", help="Emit JSON output.")

    get_page_content = subparsers.add_parser(
        "get-page-content",
        help="Fetch the HTML content for a page.",
    )
    _add_auth_arguments(get_page_content)
    get_page_content.add_argument("--page", required=True, help="Page ID.")
    get_page_content.add_argument(
        "--include-ids",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include OneNote element IDs in the HTML. Defaults to enabled.",
    )
    get_page_content.add_argument(
        "--output",
        type=Path,
        help="Write the HTML to this file instead of streaming it to stdout.",
    )

    create_page = subparsers.add_parser(
        "create-page",
        help="Create a page from HTML or plain text.",
    )
    _add_auth_arguments(create_page)
    _add_content_arguments(create_page)
    create_page.add_argument("--section", required=True, help="Target section ID.")
    create_page.add_argument("--title", required=True, help="Page title.")
    create_page.add_argument("--json", action="store_true", help="Emit JSON output.")

    create_with_assets = subparsers.add_parser(
        "create-page-with-assets",
        help="Create a page with HTML or text plus uploaded images and files.",
    )
    _add_auth_arguments(create_with_assets)
    _add_content_arguments(create_with_assets)
    create_with_assets.add_argument("--section", required=True, help="Target section ID.")
    create_with_assets.add_argument("--title", required=True, help="Page title.")
    create_with_assets.add_argument(
        "--asset",
        dest="assets",
        action="append",
        required=True,
        help="Path to an image or file to embed on the page. Repeat for multiple assets.",
    )
    create_with_assets.add_argument("--json", action="store_true", help="Emit JSON output.")

    append_page = subparsers.add_parser(
        "append-page",
        help="Append HTML or text to an existing page.",
    )
    _add_auth_arguments(append_page)
    _add_content_arguments(append_page)
    append_page.add_argument("--page", required=True, help="Target page ID.")
    append_page.add_argument(
        "--target",
        default="body",
        help="OneNote update target. Defaults to body.",
    )
    append_page.add_argument("--json", action="store_true", help="Emit JSON output.")

    replace_page = subparsers.add_parser(
        "replace-page-content",
        help="Replace a specific page element with HTML or text.",
    )
    _add_auth_arguments(replace_page)
    _add_content_arguments(replace_page)
    replace_page.add_argument("--page", required=True, help="Target page ID.")
    replace_page.add_argument(
        "--target",
        required=True,
        help="Element ID to replace, typically discovered via get-page-content.",
    )
    replace_page.add_argument("--json", action="store_true", help="Emit JSON output.")

    replace_page_with_assets = subparsers.add_parser(
        "replace-page-with-assets",
        help="Replace a specific page element with HTML/text plus uploaded assets.",
    )
    _add_auth_arguments(replace_page_with_assets)
    _add_content_arguments(replace_page_with_assets)
    replace_page_with_assets.add_argument("--page", required=True, help="Target page ID.")
    replace_page_with_assets.add_argument(
        "--target",
        required=True,
        help="Element ID to replace, typically discovered via get-page-content.",
    )
    replace_page_with_assets.add_argument(
        "--asset",
        dest="assets",
        action="append",
        required=True,
        help="Path to an image or file to use in the replacement. Repeat for multiple assets.",
    )
    replace_page_with_assets.add_argument("--json", action="store_true", help="Emit JSON output.")

    attach_to_page = subparsers.add_parser(
        "attach-to-page",
        help="Append uploaded images or files to an existing page.",
    )
    _add_auth_arguments(attach_to_page)
    attach_to_page.add_argument("--page", required=True, help="Target page ID.")
    attach_to_page.add_argument(
        "--file",
        dest="files",
        action="append",
        required=True,
        help="Path to an image or file to append. Repeat for multiple files.",
    )
    attach_to_page.add_argument(
        "--target",
        default="body",
        help="OneNote update target. Defaults to body.",
    )
    attach_to_page.add_argument("--json", action="store_true", help="Emit JSON output.")

    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    authenticator_cls: type[OneNoteAuthenticator] = OneNoteAuthenticator,
    graph_client_cls: type[OneNoteGraphClient] = OneNoteGraphClient,
    stdout: Any | None = None,
    stderr: Any | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        if args.command == "clear-auth":
            cache_path = resolve_cache_path(getattr(args, "cache_path", None))
            removed = False
            if cache_path.exists():
                cache_path.unlink()
                removed = True
            return _write_output(
                {"removed": removed, "cache_path": str(cache_path)},
                human_text=(
                    f"Removed cached token file: {cache_path}"
                    if removed
                    else f"No cached token file was present at {cache_path}"
                ),
                as_json=args.json,
                stdout=stdout,
            )

        config = auth_config_from_inputs(
            client_id=getattr(args, "client_id", None),
            tenant_id=getattr(args, "tenant_id", None),
            authority_base=getattr(args, "authority_base", None),
            scopes=getattr(args, "scopes", None),
            cache_path=getattr(args, "cache_path", None),
        )
        authenticator = authenticator_cls(config, stdout=stdout)

        if args.command == "list-cached-accounts":
            accounts = authenticator.list_cached_accounts()
            return _write_output(
                accounts,
                human_text=_format_cached_accounts(accounts),
                as_json=args.json,
                stdout=stdout,
            )

        session = authenticator.acquire_session(
            auth_flow=getattr(args, "auth_flow", "auto"),
            login_hint=getattr(args, "login_hint", None),
            force_interactive=getattr(args, "force_interactive", False),
        )

        if args.command == "connect":
            payload = {
                "connected": True,
                "auth_flow": session.auth_flow,
                "username": session.account_username,
                "display_name": session.display_name,
                "tenant_id": session.tenant_id,
                "cache_path": str(config.cache_path),
            }
            human = "Connected to Microsoft Graph."
            if session.account_username:
                human += f" Account: {session.account_username}"
            return _write_output(payload, human_text=human, as_json=args.json, stdout=stdout)

        with graph_client_cls(access_token=session.access_token) as graph:
            if args.command == "whoami":
                me = graph.get_me()
                return _write_output(
                    me,
                    human_text=_format_whoami(me),
                    as_json=args.json,
                    stdout=stdout,
                )

            if args.command == "list-notebooks":
                notebooks = graph.list_notebooks()
                notebooks = _filter_items_by_name(
                    notebooks,
                    name_contains=args.name_contains,
                    name_keys=("displayName",),
                )
                notebooks = _limit_items(notebooks, limit=args.limit)
                return _write_output(
                    notebooks,
                    human_text=_format_notebooks(notebooks),
                    as_json=args.json,
                    stdout=stdout,
                )

            if args.command == "list-sections":
                sections = graph.list_sections(notebook_id=args.notebook)
                sections = _filter_items_by_name(
                    sections,
                    name_contains=args.name_contains,
                    name_keys=("displayName",),
                )
                sections = _limit_items(sections, limit=args.limit)
                return _write_output(
                    sections,
                    human_text=_format_sections(sections),
                    as_json=args.json,
                    stdout=stdout,
                )

            if args.command == "list-pages":
                pages = graph.list_pages(section_id=args.section)
                pages = _filter_pages_by_title(pages, title_contains=args.title_contains)
                pages = _sort_pages(
                    pages,
                    sort_by=args.sort,
                    descending=args.descending,
                )
                pages = _limit_items(pages, limit=args.limit)
                return _write_output(
                    pages,
                    human_text=_format_pages(pages, sort_by=args.sort),
                    as_json=args.json,
                    stdout=stdout,
                )

            if args.command == "get-page-content":
                page_html = graph.get_page_content(
                    page_id=args.page,
                    include_ids=args.include_ids,
                )
                return _write_page_content(
                    page_html,
                    output_path=args.output,
                    stdout=stdout,
                )

            if args.command == "create-page":
                content, treat_as_plain_text = _load_content_args(args)
                page = graph.create_page(
                    section_id=args.section,
                    title=args.title,
                    html_or_text=content,
                    treat_as_plain_text=treat_as_plain_text,
                )
                return _write_output(
                    page,
                    human_text=_format_page_result("Created page", page),
                    as_json=args.json,
                    stdout=stdout,
                )

            if args.command == "create-page-with-assets":
                content, treat_as_plain_text = _load_content_args(args)
                page = graph.create_page(
                    section_id=args.section,
                    title=args.title,
                    html_or_text=content,
                    asset_paths=args.assets,
                    treat_as_plain_text=treat_as_plain_text,
                )
                return _write_output(
                    page,
                    human_text=_format_page_result("Created page", page),
                    as_json=args.json,
                    stdout=stdout,
                )

            if args.command == "append-page":
                content, treat_as_plain_text = _load_content_args(args)
                graph.append_page(
                    page_id=args.page,
                    html_or_text=content,
                    target=args.target,
                    treat_as_plain_text=treat_as_plain_text,
                )
                return _write_output(
                    {"updated": True, "page_id": args.page, "target": args.target},
                    human_text=f"Appended content to page {args.page}.",
                    as_json=args.json,
                    stdout=stdout,
                )

            if args.command == "replace-page-content":
                content, treat_as_plain_text = _load_content_args(args)
                graph.replace_page_content(
                    page_id=args.page,
                    target=args.target,
                    html_or_text=content,
                    treat_as_plain_text=treat_as_plain_text,
                )
                return _write_output(
                    {
                        "updated": True,
                        "page_id": args.page,
                        "target": args.target,
                        "action": "replace",
                    },
                    human_text=f"Replaced content at target {args.target} on page {args.page}.",
                    as_json=args.json,
                    stdout=stdout,
                )

            if args.command == "replace-page-with-assets":
                content, treat_as_plain_text = _load_content_args(args, required=False)
                graph.replace_page_with_assets(
                    page_id=args.page,
                    target=args.target,
                    asset_paths=args.assets,
                    html_or_text=content,
                    treat_as_plain_text=treat_as_plain_text,
                )
                return _write_output(
                    {
                        "updated": True,
                        "page_id": args.page,
                        "target": args.target,
                        "action": "replace",
                        "assets": args.assets,
                    },
                    human_text=(
                        f"Replaced content at target {args.target} on page {args.page} "
                        f"with {len(args.assets)} asset(s)."
                    ),
                    as_json=args.json,
                    stdout=stdout,
                )

            if args.command == "attach-to-page":
                graph.attach_to_page(
                    page_id=args.page,
                    asset_paths=args.files,
                    target=args.target,
                )
                return _write_output(
                    {
                        "updated": True,
                        "page_id": args.page,
                        "target": args.target,
                        "files": args.files,
                    },
                    human_text=f"Attached {len(args.files)} file(s) to page {args.page}.",
                    as_json=args.json,
                    stdout=stdout,
                )
    except (
        AuthenticationDependencyError,
        AuthenticationError,
        GraphRequestError,
        FileNotFoundError,
        ValueError,
    ) as exc:
        print(str(exc), file=stderr)
        return 1

    parser.error(f"Unhandled command: {args.command}")
    return 2


def _add_auth_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--client-id",
        help="Microsoft Entra app client ID. Defaults to ONENOTE_CLIENT_ID.",
    )
    parser.add_argument(
        "--tenant-id",
        help="Tenant ID or alias such as common or organizations. Defaults to ONENOTE_TENANT_ID or common.",
    )
    parser.add_argument(
        "--authority-base",
        help="Authority base URL. Defaults to https://login.microsoftonline.com.",
    )
    parser.add_argument(
        "--scopes",
        help="Comma-separated Graph scopes. Defaults to Notes.ReadWrite,User.Read,offline_access,openid,profile.",
    )
    parser.add_argument(
        "--cache-path",
        help="Token cache path. Defaults to ONENOTE_TOKEN_CACHE_PATH or ~/.config/codex/onenote-connect/token-cache.json.",
    )


def _add_content_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--html-file", help="Path to an HTML file or fragment.")
    parser.add_argument(
        "--text-file",
        help="Path to a plain-text file that should be converted into paragraphs.",
    )
    parser.add_argument(
        "--content",
        help="Inline content. Treated as HTML unless --plain-text is set.",
    )
    parser.add_argument(
        "--plain-text",
        action="store_true",
        help="Treat inline content or --html-file input as plain text.",
    )


def _load_content_args(
    args: argparse.Namespace,
    *,
    required: bool = True,
) -> tuple[str | None, bool]:
    provided = [value for value in (args.html_file, args.text_file, args.content) if value]
    if len(provided) > 1:
        raise ValueError("Choose only one of --html-file, --text-file, or --content.")
    if not provided:
        if not required:
            return None, False
        raise ValueError("One content source is required.")

    if args.html_file:
        return Path(args.html_file).expanduser().read_text(), bool(args.plain_text)
    if args.text_file:
        return Path(args.text_file).expanduser().read_text(), True
    return args.content, bool(args.plain_text)


def _write_output(
    payload: Any,
    *,
    human_text: str,
    as_json: bool,
    stdout: Any,
) -> int:
    if as_json:
        json.dump(payload, stdout, indent=2)
        stdout.write("\n")
    else:
        stdout.write(human_text.rstrip() + "\n")
    return 0


def _write_page_content(
    page_html: str,
    *,
    output_path: Path | None,
    stdout: Any,
) -> int:
    if output_path is None:
        stdout.write(page_html)
        if not page_html.endswith("\n"):
            stdout.write("\n")
        return 0

    resolved_path = output_path.expanduser()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(page_html)
    stdout.write(f"Wrote page content to {resolved_path}\n")
    return 0


def _format_whoami(payload: dict[str, Any]) -> str:
    display_name = payload.get("displayName") or "Unknown user"
    user_principal_name = payload.get("userPrincipalName") or payload.get("mail")
    if user_principal_name:
        return f"{display_name} <{user_principal_name}>"
    return display_name


def _format_cached_accounts(accounts: list[dict[str, Any]]) -> str:
    if not accounts:
        return "No cached accounts found."
    lines = []
    for account in accounts:
        username = account.get("username") or account.get("home_account_id") or "Unknown account"
        display_name = account.get("name")
        if display_name and display_name != username:
            lines.append(f"{username}  {display_name}")
            continue
        lines.append(str(username))
    return "\n".join(lines)


def _format_notebooks(notebooks: list[dict[str, Any]]) -> str:
    if not notebooks:
        return "No notebooks found."
    lines = []
    for notebook in notebooks:
        default_marker = " [default]" if notebook.get("isDefault") else ""
        lines.append(
            f"{notebook.get('id')}  {notebook.get('displayName', 'Unnamed notebook')}{default_marker}"
        )
    return "\n".join(lines)


def _format_sections(sections: list[dict[str, Any]]) -> str:
    if not sections:
        return "No sections found."
    lines = []
    for section in sections:
        parent = section.get("parentNotebook") or {}
        parent_name = parent.get("displayName")
        suffix = f" ({parent_name})" if parent_name else ""
        default_marker = " [default]" if section.get("isDefault") else ""
        lines.append(
            f"{section.get('id')}  {section.get('displayName', 'Unnamed section')}{suffix}{default_marker}"
        )
    return "\n".join(lines)


def _format_pages(
    pages: list[dict[str, Any]],
    *,
    sort_by: str | None = None,
) -> str:
    if not pages:
        return "No pages found."
    lines = []
    for page in pages:
        title = page.get("title") or page.get("displayName") or "Untitled page"
        web_url = _page_web_url(page)
        metadata = _page_sort_metadata(page, sort_by=sort_by)
        suffix_parts = [part for part in (metadata, web_url) if part]
        suffix = "".join(f"  {part}" for part in suffix_parts)
        lines.append(f"{page.get('id')}  {title}{suffix}")
    return "\n".join(lines)


def _filter_pages_by_title(
    pages: list[dict[str, Any]],
    *,
    title_contains: str | None,
) -> list[dict[str, Any]]:
    return _filter_items_by_name(
        pages,
        name_contains=title_contains,
        name_keys=("title", "displayName"),
    )


def _filter_items_by_name(
    items: list[dict[str, Any]],
    *,
    name_contains: str | None,
    name_keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    if not name_contains:
        return list(items)
    needle = name_contains.casefold()
    return [
        item
        for item in items
        if _item_name_contains(item, needle=needle, name_keys=name_keys)
    ]


def _item_name_contains(
    item: dict[str, Any],
    *,
    needle: str,
    name_keys: tuple[str, ...],
) -> bool:
    for key in name_keys:
        value = item.get(key)
        if value and needle in str(value).casefold():
            return True
    return False


def _sort_pages(
    pages: list[dict[str, Any]],
    *,
    sort_by: str | None,
    descending: bool,
) -> list[dict[str, Any]]:
    if sort_by is None:
        return list(pages)
    if sort_by == "title":
        return sorted(
            pages,
            key=lambda page: _page_title(page).casefold(),
            reverse=descending,
        )

    field_name = (
        "createdDateTime"
        if sort_by == "created"
        else "lastModifiedDateTime"
    )
    present_pages: list[tuple[datetime, dict[str, Any]]] = []
    missing_pages: list[dict[str, Any]] = []
    for page in pages:
        parsed = _parse_page_timestamp(page.get(field_name))
        if parsed is None:
            missing_pages.append(page)
            continue
        present_pages.append((parsed, page))
    ordered_present = sorted(
        present_pages,
        key=lambda item: item[0],
        reverse=descending,
    )
    return [page for _, page in ordered_present] + missing_pages


def _limit_items(
    items: list[dict[str, Any]],
    *,
    limit: int | None,
) -> list[dict[str, Any]]:
    if limit is None:
        return list(items)
    if limit < 1:
        raise ValueError("--limit must be at least 1.")
    return list(items[:limit])


def _page_title(page: dict[str, Any]) -> str:
    return str(page.get("title") or page.get("displayName") or "")


def _parse_page_timestamp(raw_value: Any) -> datetime | None:
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _page_sort_metadata(
    page: dict[str, Any],
    *,
    sort_by: str | None,
) -> str | None:
    if sort_by == "created":
        return _page_timestamp_label("created", page.get("createdDateTime"))
    if sort_by == "modified":
        return _page_timestamp_label("modified", page.get("lastModifiedDateTime"))
    return None


def _page_timestamp_label(label: str, raw_value: Any) -> str | None:
    parsed = _parse_page_timestamp(raw_value)
    if parsed is None:
        return None
    return f"{label} {parsed.isoformat()}"


def _format_page_result(prefix: str, payload: dict[str, Any]) -> str:
    page_id = payload.get("id") or "unknown"
    title = payload.get("title") or payload.get("displayName")
    web_url = _page_web_url(payload)
    message = f"{prefix}: {page_id}"
    if title:
        message += f" ({title})"
    if web_url:
        message += f"\n{web_url}"
    return message


def _page_web_url(page: dict[str, Any]) -> str | None:
    return page.get("links", {}).get("oneNoteWebUrl", {}).get("href")


if __name__ == "__main__":
    raise SystemExit(main())
