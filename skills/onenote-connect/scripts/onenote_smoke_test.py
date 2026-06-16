from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import sys
from typing import Any, Sequence

from auth import (
    AuthenticationDependencyError,
    AuthenticationError,
    OneNoteAuthenticator,
    auth_config_from_inputs,
)
from graph_client import GraphRequestError, OneNoteGraphClient


@dataclass(slots=True, frozen=True)
class SmokeCheck:
    name: str
    detail: str
    resource: dict[str, Any] | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a deterministic OneNote smoke test against a real tenant.",
    )
    _add_auth_arguments(parser)
    parser.add_argument(
        "--auth-flow",
        default="auto",
        choices=("auto", "device-code", "interactive"),
        help="Preferred delegated sign-in flow.",
    )
    parser.add_argument(
        "--login-hint",
        help="Preferred username or email to preselect during sign-in.",
    )
    parser.add_argument(
        "--force-interactive",
        action="store_true",
        help="Skip silent token acquisition and force an interactive login.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Opt in to a minimal write workflow that creates one page and appends to one page.",
    )
    parser.add_argument(
        "--write-section",
        help="Section ID used for the smoke-test page creation step in write mode.",
    )
    parser.add_argument(
        "--write-page",
        help="Existing page ID used for the smoke-test append step in write mode.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON output for automation.",
    )
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
        _validate_args(args)
        config = auth_config_from_inputs(
            client_id=args.client_id,
            tenant_id=args.tenant_id,
            authority_base=args.authority_base,
            scopes=args.scopes,
            cache_path=args.cache_path,
        )
        authenticator = authenticator_cls(config, stdout=stdout)
        session = authenticator.acquire_session(
            auth_flow=args.auth_flow,
            login_hint=args.login_hint,
            force_interactive=args.force_interactive,
        )

        checks = [
            SmokeCheck(
                name="auth",
                detail=(
                    f"flow={session.auth_flow} "
                    f"account={session.account_username or 'unknown'} "
                    f"cache={config.cache_path}"
                ),
                resource={
                    "auth_flow": session.auth_flow,
                    "account_username": session.account_username,
                    "display_name": session.display_name,
                    "tenant_id": session.tenant_id,
                    "cache_path": str(config.cache_path),
                },
            )
        ]

        with graph_client_cls(access_token=session.access_token) as graph:
            me = graph.get_me()
            notebooks = graph.list_notebooks()
            sections = graph.list_sections()
            pages = graph.list_pages(section_id=sections[0]["id"] if sections else None)

            checks.extend(
                [
                    SmokeCheck(
                        name="whoami",
                        detail=_format_identity_detail(me),
                        resource=_identity_resource(me),
                    ),
                    SmokeCheck(
                        name="notebooks",
                        detail=_format_collection_detail(
                            notebooks,
                            label_key="displayName",
                        ),
                        resource=_collection_resource(
                            notebooks,
                            label_key="displayName",
                        ),
                    ),
                    SmokeCheck(
                        name="sections",
                        detail=_format_collection_detail(
                            sections,
                            label_key="displayName",
                        ),
                        resource=_collection_resource(
                            sections,
                            label_key="displayName",
                        ),
                    ),
                    SmokeCheck(
                        name="pages",
                        detail=_format_collection_detail(
                            pages,
                            label_key="title",
                        ),
                        resource=_collection_resource(
                            pages,
                            label_key="title",
                        ),
                    ),
                ]
            )

            if args.write:
                stdout.write(
                    "Write mode enabled: this will create one smoke-test page and append to one existing page.\n"
                )
                created_page = graph.create_page(
                    section_id=args.write_section,
                    title=_build_smoke_test_title(),
                    html_or_text="Codex OneNote smoke test create path.",
                    treat_as_plain_text=True,
                )
                graph.append_page(
                    page_id=args.write_page,
                    html_or_text="Codex OneNote smoke test append path.",
                    treat_as_plain_text=True,
                )
                checks.extend(
                    [
                        SmokeCheck(
                            name="create-page",
                            detail=_format_resource_detail(
                                created_page,
                                label_key="title",
                            ),
                            resource={
                                **_resource_identity(created_page, label_key="title"),
                                "section_id": args.write_section,
                            },
                        ),
                        SmokeCheck(
                            name="append-page",
                            detail=f"updated_page_id={args.write_page}",
                            resource={"updated_page_id": args.write_page},
                        ),
                    ]
                )

        payload = _result_payload(
            success=True,
            mode="write" if args.write else "read-only",
            checks=checks,
        )
        if args.json:
            _write_json(stdout, payload)
            return 0
        _write_summary(
            stdout,
            payload=payload,
        )
        return 0
    except (
        AuthenticationDependencyError,
        AuthenticationError,
        GraphRequestError,
        ValueError,
    ) as exc:
        payload = _result_payload(
            success=False,
            mode="write" if getattr(args, "write", False) else "read-only",
            checks=[],
            error={"type": type(exc).__name__, "message": str(exc)},
        )
        if getattr(args, "json", False):
            _write_json(stdout, payload)
            return 1
        _write_summary(
            stderr,
            payload=payload,
        )
        return 1


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


def _validate_args(args: argparse.Namespace) -> None:
    if args.write:
        if not args.write_section or not args.write_page:
            raise ValueError(
                "Write mode requires both --write-section and --write-page."
            )
        return
    if args.write_section or args.write_page:
        raise ValueError(
            "Refusing write-target arguments without --write. Pass --write to enable tenant mutations."
        )


def _write_summary(
    stream: Any,
    *,
    payload: dict[str, Any],
) -> None:
    stream.write(f"Smoke test: {'PASS' if payload['ok'] else 'FAIL'}\n")
    stream.write(f"Mode: {payload['mode']}\n")
    for check in payload["checks"]:
        stream.write(f"- {check['name']}: PASS ({check['detail']})\n")
    if payload["error"] is not None:
        stream.write(f"Error: {payload['error']['message']}\n")


def _result_payload(
    *,
    success: bool,
    mode: str,
    checks: list[SmokeCheck],
    error: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "ok": success,
        "status": "passed" if success else "failed",
        "mode": mode,
        "checks": [
            {
                "name": check.name,
                "ok": True,
                "detail": check.detail,
                "resource": check.resource,
            }
            for check in checks
        ],
        "error": error,
    }


def _write_json(stream: Any, payload: dict[str, Any]) -> None:
    json.dump(payload, stream, indent=2)
    stream.write("\n")


def _format_identity_detail(me: dict[str, Any]) -> str:
    identity = _identity_resource(me)
    display_name = identity["display_name"]
    user_id = identity["id"]
    user_principal_name = identity["user_principal_name"]
    return (
        f"display_name={display_name} "
        f"user_principal_name={user_principal_name} "
        f"id={user_id}"
    )


def _format_collection_detail(
    items: list[dict[str, Any]],
    *,
    label_key: str,
) -> str:
    collection = _collection_resource(items, label_key=label_key)
    first_id = collection["first_id"]
    first_label = collection[f"first_{label_key}"]
    return f"count={len(items)} first_id={first_id} first_{label_key}={first_label}"


def _format_resource_detail(
    resource: dict[str, Any],
    *,
    label_key: str,
) -> str:
    resource_identity = _resource_identity(resource, label_key=label_key)
    return f"id={resource_identity['id']} {label_key}={resource_identity[label_key]}"


def _identity_resource(me: dict[str, Any]) -> dict[str, str]:
    return {
        "display_name": str(me.get("displayName") or "unknown"),
        "id": str(me.get("id") or "unknown"),
        "user_principal_name": str(
            me.get("userPrincipalName") or me.get("mail") or "unknown"
        ),
    }


def _collection_resource(
    items: list[dict[str, Any]],
    *,
    label_key: str,
) -> dict[str, Any]:
    first = items[0] if items else {}
    return {
        "count": len(items),
        "first_id": str(first.get("id") or "none"),
        f"first_{label_key}": str(first.get(label_key) or "none"),
    }


def _resource_identity(
    resource: dict[str, Any],
    *,
    label_key: str,
) -> dict[str, str]:
    return {
        "id": str(resource.get("id") or "unknown"),
        label_key: str(resource.get(label_key) or "unknown"),
    }


def _build_smoke_test_title() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"Codex OneNote smoke test {timestamp}"


if __name__ == "__main__":
    raise SystemExit(main())
