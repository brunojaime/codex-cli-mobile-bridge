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
import urllib.error
import urllib.request

import yaml

from backend.app.domain.entities.project_management import (
    PROJECT_CHARTER_METADATA_PATH,
    PROJECT_CHARTER_RENDER_PATH,
    PROJECT_CHARTER_SOURCE_PATH,
)
from backend.app.infrastructure.config.settings import Settings


PROJECT_CHARTER_PATH = PROJECT_CHARTER_SOURCE_PATH
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
    render_content: str | None = None

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
    """Compatibility reader and mail delivery for the formal Acta framework."""

    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings
        self._projects_root = Path(settings.projects_root).expanduser().resolve()

    def read(self, workspace_path: str) -> ProjectCharterDocument:
        workspace = self._resolve_workspace(workspace_path)
        try:
            content = (workspace / PROJECT_CHARTER_SOURCE_PATH).read_text(
                encoding="utf-8"
            )
            metadata = yaml.safe_load(
                (workspace / PROJECT_CHARTER_METADATA_PATH).read_text(
                    encoding="utf-8"
                )
            )
        except FileNotFoundError as exc:
            raise ProjectCharterError(
                "project_charter_missing",
                "This project does not have a Project Charter / Acta de Proyecto.",
            ) from exc
        except (OSError, yaml.YAMLError) as exc:
            raise ProjectCharterError(
                "project_charter_invalid", "The Project Charter could not be read."
            ) from exc
        if not isinstance(metadata, dict):
            raise ProjectCharterError(
                "project_charter_invalid", "The Project Charter metadata is invalid."
            )
        digest = sha256(content.encode("utf-8")).hexdigest()
        hashes = metadata.get("hashes")
        expected_digest = hashes.get("source") if isinstance(hashes, dict) else None
        if not content.strip() or expected_digest != digest:
            raise ProjectCharterError(
                "project_charter_integrity_failed",
                "The Acta source does not match its formal metadata.",
            )
        document = metadata.get("document")
        versions = metadata.get("versions")
        timestamps = metadata.get("timestamps")
        delivered = versions.get("delivered") if isinstance(versions, dict) else None
        draft = versions.get("draft") if isinstance(versions, dict) else None
        render_path = workspace / PROJECT_CHARTER_RENDER_PATH
        render_content = (
            render_path.read_text(encoding="utf-8") if render_path.is_file() else None
        )
        return ProjectCharterDocument(
            path=PROJECT_CHARTER_SOURCE_PATH,
            metadata_path=PROJECT_CHARTER_METADATA_PATH,
            title=str(
                document.get("title")
                if isinstance(document, dict) and document.get("title")
                else "Acta de Proyecto"
            ),
            status=str(metadata.get("status") or "draft"),
            version=str(delivered or draft or "v0.1"),
            approved_at=str(
                timestamps.get("delivered_at")
                if isinstance(timestamps, dict) and timestamps.get("delivered_at")
                else ""
            ),
            digest=digest,
            content=content,
            render_content=render_content,
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

    def _resolve_workspace(self, workspace_path: str) -> Path:
        workspace = Path(workspace_path).expanduser().resolve()
        if workspace == self._projects_root or self._projects_root not in workspace.parents:
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
                "SMTP sender and host are required to share the Acta.",
            )
        email = EmailMessage()
        message_id = make_msgid(domain="codex-mobile-bridge.local")
        email["From"] = sender
        email["To"] = ", ".join(recipients)
        email["Subject"] = f"Acta de Proyecto - {_charter_project_name(document.content)}"
        email["Date"] = formatdate(localtime=False, usegmt=True)
        email["Message-ID"] = message_id
        email.set_content(_email_text(document, note=note, include_full=include_full_document))
        email.add_alternative(
            _email_html(document, note=note, include_full=include_full_document),
            subtype="html",
        )
        if include_full_document:
            email.add_attachment(
                document.content.encode("utf-8"),
                maintype="text",
                subtype="markdown",
                filename="acta-de-proyecto.md",
            )
            if document.render_content:
                email.add_attachment(
                    document.render_content.encode("utf-8"),
                    maintype="text",
                    subtype="html",
                    filename="acta-de-proyecto.html",
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
                if smtp_class is smtplib.SMTP and self._settings.web_preview_smtp_use_tls:
                    smtp.starttls()
                username = self._settings.web_preview_smtp_username
                password = self._settings.web_preview_smtp_password
                if username and password:
                    smtp.login(username, password)
                if smtp.send_message(email):
                    raise ProjectCharterError(
                        "project_charter_email_failed", "SMTP refused a recipient."
                    )
        except ProjectCharterError:
            raise
        except Exception as exc:
            raise ProjectCharterError(
                "project_charter_email_failed", "The Acta email could not be sent."
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
                    "subject": f"Acta de Proyecto - {_charter_project_name(document.content)}",
                    "text": _email_text(document, note=note, include_full=include_full_document),
                    "html": _email_html(document, note=note, include_full=include_full_document),
                    "metadata": {
                        "document_kind": "project_charter",
                        "document_digest": document.digest,
                        "document_status": document.status,
                        "document_version": document.version,
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
                    response_payload = json.loads(response.read().decode("utf-8") or "{}")
                message_id = str(response_payload.get("id") or "")
                if message_id:
                    message_ids.append(message_id)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise ProjectCharterError(
                "project_charter_email_failed", "The Acta email could not be sent."
            ) from exc
        return ",".join(message_ids) or None


def _charter_project_name(content: str) -> str:
    match = re.search(r"^- (?:Proyecto|Project): (.+?)$", content, re.MULTILINE)
    return match.group(1).strip() if match else "Proyecto"


def _email_text(
    document: ProjectCharterDocument, *, note: str | None, include_full: bool
) -> str:
    body = [(note or "").strip()] if (note or "").strip() else []
    body.append(
        f"Acta de Proyecto {document.version} ({document.status}).\n"
        f"Integridad: {document.digest}"
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
        f"<p><strong>Acta de Proyecto {html.escape(document.version)} "
        f"({html.escape(document.status)})</strong><br>"
        f"Integridad: <code>{html.escape(document.digest)}</code></p>"
    )
    if include_full:
        pieces.append(
            document.render_content
            or f'<pre style="white-space:pre-wrap">{html.escape(document.content)}</pre>'
        )
    pieces.append("</body></html>")
    return "".join(pieces)
