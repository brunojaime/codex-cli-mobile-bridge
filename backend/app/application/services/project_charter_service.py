from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from hashlib import sha256
import html
import json
from pathlib import Path
import re
import smtplib
from typing import Any
import urllib.error
import urllib.request

from backend.app.infrastructure.config.settings import Settings


PROJECT_CHARTER_PATH = "docs/project-charter.md"
PROJECT_CHARTER_METADATA_PATH = "docs/project-charter.json"
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class ProjectCharterError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ProjectCharterDocument:
    path: str
    metadata_path: str
    title: str
    status: str
    version: str
    approved_at: str
    digest: str
    content: str

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": "codex.projectCharter",
            "schemaVersion": 1,
            "path": self.path,
            "metadataPath": self.metadata_path,
            "title": self.title,
            "status": self.status,
            "version": self.version,
            "approvedAt": self.approved_at,
            "digest": self.digest,
            "content": self.content,
        }


class ProjectCharterService:
    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings
        self._projects_root = Path(settings.projects_root).expanduser().resolve()

    def materialize_from_draft(
        self,
        *,
        workspace: Path,
        draft_payload: dict[str, Any],
        approved_brief: str,
    ) -> ProjectCharterDocument:
        request = draft_payload.get("request")
        guided = draft_payload.get("guided_intake")
        if not isinstance(request, dict) or not isinstance(guided, dict):
            raise ProjectCharterError(
                "project_charter_draft_invalid",
                "The approved Project Factory draft is missing request or intake data.",
            )
        if str(guided.get("status") or "") not in {"confirmed", "build_started"}:
            raise ProjectCharterError(
                "project_charter_not_approved",
                "The Project Factory contract must be approved before creating its charter.",
            )
        approved_at = str(guided.get("confirmedAt") or guided.get("confirmed_at") or "")
        if not approved_at:
            raise ProjectCharterError(
                "project_charter_approval_missing",
                "The approved Project Factory contract has no approval timestamp.",
            )
        if not approved_brief.strip():
            raise ProjectCharterError(
                "project_charter_scope_missing",
                "The approved Project Factory scope is required to create its charter.",
            )
        content = build_project_charter_markdown(
            request=request,
            guided_intake=guided,
            approved_brief=approved_brief,
            approved_at=approved_at,
        )
        return self._write_document(workspace, content=content, approved_at=approved_at)

    def read(self, workspace_path: str) -> ProjectCharterDocument:
        workspace = self._resolve_workspace(workspace_path)
        charter_path = workspace / PROJECT_CHARTER_PATH
        metadata_path = workspace / PROJECT_CHARTER_METADATA_PATH
        try:
            content = charter_path.read_text(encoding="utf-8")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ProjectCharterError(
                "project_charter_missing",
                "This project does not have an approved charter.",
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectCharterError(
                "project_charter_invalid", "The project charter could not be read."
            ) from exc
        digest = sha256(content.encode("utf-8")).hexdigest()
        if metadata.get("digest") != digest or metadata.get("status") != "approved":
            raise ProjectCharterError(
                "project_charter_integrity_failed",
                "The project charter metadata does not match its approved document.",
            )
        return ProjectCharterDocument(
            path=PROJECT_CHARTER_PATH,
            metadata_path=PROJECT_CHARTER_METADATA_PATH,
            title=str(metadata.get("title") or "Project Charter"),
            status="approved",
            version=str(metadata.get("version") or "1.0"),
            approved_at=str(metadata.get("approvedAt") or ""),
            digest=digest,
            content=content,
        )

    def share(
        self,
        *,
        workspace_path: str,
        recipients: tuple[str, ...],
        include_full_document: bool = True,
        message: str | None = None,
    ) -> dict[str, object]:
        document = self.read(workspace_path)
        normalized = tuple(dict.fromkeys(item.strip().lower() for item in recipients))
        if not normalized or any(
            not _EMAIL_PATTERN.fullmatch(item) for item in normalized
        ):
            raise ProjectCharterError(
                "project_charter_invalid_recipients",
                "Provide at least one valid email recipient.",
            )
        provider = str(self._settings.web_preview_email_provider or "").strip()
        if provider == "smtp":
            provider_message_id = self._send_smtp(
                document,
                recipients=normalized,
                include_full_document=include_full_document,
                note=message,
            )
        elif provider == "cloudflare_email":
            provider_message_id = self._send_cloudflare(
                document,
                recipients=normalized,
                include_full_document=include_full_document,
                note=message,
            )
        else:
            raise ProjectCharterError(
                "project_charter_email_unavailable",
                "Email delivery is not configured on this Bridge.",
            )
        return {
            "kind": "codex.projectCharterShare",
            "status": "sent",
            "provider": provider,
            "recipients": list(normalized),
            "includeFullDocument": include_full_document,
            "documentDigest": document.digest,
            "providerMessageId": provider_message_id,
            "sentAt": datetime.now(UTC).isoformat(),
        }

    def _write_document(
        self, workspace: Path, *, content: str, approved_at: str
    ) -> ProjectCharterDocument:
        docs_dir = workspace / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        digest = sha256(content.encode("utf-8")).hexdigest()
        metadata = {
            "kind": "codex.projectCharterMetadata",
            "schemaVersion": 1,
            "title": "Project Charter",
            "status": "approved",
            "version": "1.0",
            "approvedAt": approved_at,
            "path": PROJECT_CHARTER_PATH,
            "digest": digest,
        }
        (workspace / PROJECT_CHARTER_PATH).write_text(content, encoding="utf-8")
        (workspace / PROJECT_CHARTER_METADATA_PATH).write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return ProjectCharterDocument(
            path=PROJECT_CHARTER_PATH,
            metadata_path=PROJECT_CHARTER_METADATA_PATH,
            title="Project Charter",
            status="approved",
            version="1.0",
            approved_at=approved_at,
            digest=digest,
            content=content,
        )

    def _resolve_workspace(self, workspace_path: str) -> Path:
        workspace = Path(workspace_path).expanduser().resolve()
        if (
            workspace == self._projects_root
            or self._projects_root not in workspace.parents
        ):
            raise ProjectCharterError(
                "project_charter_workspace_invalid",
                "The requested workspace is outside the configured projects root.",
            )
        return workspace

    def _send_smtp(
        self,
        document: ProjectCharterDocument,
        *,
        recipients: tuple[str, ...],
        include_full_document: bool,
        note: str | None,
    ) -> str:
        sender = str(self._settings.web_preview_email_from or "").strip()
        host = str(self._settings.web_preview_smtp_host or "").strip()
        if not sender or not host:
            raise ProjectCharterError(
                "project_charter_email_unavailable",
                "SMTP sender and host are required to share the charter.",
            )
        email = EmailMessage()
        message_id = make_msgid(domain="codex-mobile-bridge.local")
        email["From"] = sender
        email["To"] = ", ".join(recipients)
        email["Subject"] = (
            f"Project Charter - {_charter_project_name(document.content)}"
        )
        email["Date"] = formatdate(localtime=False, usegmt=True)
        email["Message-ID"] = message_id
        email.set_content(
            _email_text(document, note=note, include_full=include_full_document)
        )
        email.add_alternative(
            _email_html(document, note=note, include_full=include_full_document),
            subtype="html",
        )
        if include_full_document:
            email.add_attachment(
                document.content.encode("utf-8"),
                maintype="text",
                subtype="markdown",
                filename="project-charter.md",
            )
        smtp_port = self._settings.web_preview_smtp_port
        smtp_class = (
            smtplib.SMTP_SSL
            if self._settings.web_preview_smtp_implicit_tls or smtp_port == 465
            else smtplib.SMTP
        )
        try:
            with smtp_class(
                host,
                smtp_port,
                timeout=self._settings.web_preview_smtp_timeout_seconds,
            ) as smtp:
                if (
                    smtp_class is smtplib.SMTP
                    and self._settings.web_preview_smtp_use_tls
                ):
                    smtp.starttls()
                username = self._settings.web_preview_smtp_username
                password = self._settings.web_preview_smtp_password
                if username and password:
                    smtp.login(username, password)
                refused = smtp.send_message(email)
                if refused:
                    raise ProjectCharterError(
                        "project_charter_email_failed", "SMTP refused a recipient."
                    )
        except ProjectCharterError:
            raise
        except Exception as exc:
            raise ProjectCharterError(
                "project_charter_email_failed", "The charter email could not be sent."
            ) from exc
        return message_id

    def _send_cloudflare(
        self,
        document: ProjectCharterDocument,
        *,
        recipients: tuple[str, ...],
        include_full_document: bool,
        note: str | None,
    ) -> str | None:
        sender = str(self._settings.web_preview_email_from or "").strip()
        endpoint = str(self._settings.web_preview_email_endpoint or "").strip()
        token = str(self._settings.web_preview_email_api_token or "").strip()
        if not sender or not endpoint or not token:
            raise ProjectCharterError(
                "project_charter_email_unavailable",
                "Cloudflare email sender, endpoint, and token are required.",
            )
        message_ids: list[str] = []
        try:
            for recipient in recipients:
                payload = {
                    "from": sender,
                    "to": recipient,
                    "subject": (
                        f"Project Charter - {_charter_project_name(document.content)}"
                    ),
                    "text": _email_text(
                        document,
                        note=note,
                        include_full=include_full_document,
                    ),
                    "html": _email_html(
                        document,
                        note=note,
                        include_full=include_full_document,
                    ),
                    "metadata": {
                        "document_kind": "project_charter",
                        "document_digest": document.digest,
                    },
                }
                request = urllib.request.Request(
                    endpoint,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "authorization": f"Bearer {token}",
                        "content-type": "application/json",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(
                    request,
                    timeout=self._settings.web_preview_smtp_timeout_seconds,
                ) as response:
                    response_payload = json.loads(
                        response.read().decode("utf-8") or "{}"
                    )
                message_id = str(response_payload.get("id") or "")
                if message_id:
                    message_ids.append(message_id)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise ProjectCharterError(
                "project_charter_email_failed", "The charter email could not be sent."
            ) from exc
        return ",".join(message_ids) or None


def build_project_charter_markdown(
    *,
    request: dict[str, Any],
    guided_intake: dict[str, Any],
    approved_brief: str,
    approved_at: str,
) -> str:
    preview = guided_intake.get("contractPreview") or guided_intake.get(
        "contract_preview"
    )
    preview = preview if isinstance(preview, dict) else {}
    decisions = preview.get("decisions")
    decisions = decisions if isinstance(decisions, dict) else {}
    assumptions = preview.get("assumptions")
    assumptions = assumptions if isinstance(assumptions, list) else []
    name = str(request.get("name") or decisions.get("name") or "Unnamed project")
    slug = str(request.get("slug") or decisions.get("slug") or "")
    goal = str(
        request.get("primary_goal")
        or request.get("primaryGoal")
        or decisions.get("primaryGoal")
        or "Not specified"
    )
    business_type = str(
        request.get("business_type")
        or request.get("businessType")
        or decisions.get("businessType")
        or "Not specified"
    )
    platforms = request.get("platforms") or decisions.get("platforms") or []
    if isinstance(platforms, dict):
        platforms = [key for key, enabled in platforms.items() if enabled]
    platform_text = ", ".join(str(item) for item in platforms) or "Not specified"
    approved_scope = approved_brief.strip()
    assumption_lines = (
        "\n".join(
            f"- {str(item.get('message') or item.get('value') or item)}"
            if isinstance(item, dict)
            else f"- {item}"
            for item in assumptions
        )
        or "- No unresolved assumptions were recorded at approval."
    )
    return f"""# Project Charter

- Status: Approved
- Version: 1.0
- Approved at: {approved_at}
- Project: {name}
- Slug: `{slug}`
- Business type: {business_type}
- Platforms: {platform_text}

## Executive objective

{goal}

## Approved scope and requirements

{approved_scope}

## Assumptions recorded at approval

{assumption_lines}

## Delivery and governance

- This charter is the approved source contract for UX, SDD, Generator, Reviewer, implementation, and release validation.
- Changes to scope, roles, workflows, data, acceptance criteria, or release expectations require an explicit charter revision.
- Mock or demo data is not authorized unless a later approved revision states it explicitly.
- Generated implementation must remain traceable to this document in SDD Workbench.
"""


def _charter_project_name(content: str) -> str:
    match = re.search(r"^- Project: (.+?)$", content, re.MULTILINE)
    return match.group(1).strip() if match else "Project"


def _email_text(
    document: ProjectCharterDocument, *, note: str | None, include_full: bool
) -> str:
    prefix = (note or "").strip()
    body = [prefix] if prefix else []
    body.append(
        f"Approved project charter v{document.version}.\nDigest: {document.digest}"
    )
    if include_full:
        body.extend(["", document.content])
    return "\n\n".join(body).strip() + "\n"


def _email_html(
    document: ProjectCharterDocument, *, note: str | None, include_full: bool
) -> str:
    pieces = ["<html><body>"]
    if note and note.strip():
        pieces.append(f"<p>{html.escape(note.strip())}</p>")
    pieces.append(
        f"<p><strong>Approved project charter v{html.escape(document.version)}</strong><br>"
        f"Digest: <code>{html.escape(document.digest)}</code></p>"
    )
    if include_full:
        pieces.append(
            f'<pre style="white-space:pre-wrap">{html.escape(document.content)}</pre>'
        )
    pieces.append("</body></html>")
    return "".join(pieces)
