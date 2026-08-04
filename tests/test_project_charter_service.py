from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import pytest

from backend.app.application.services.project_charter_service import (
    ProjectCharterError,
    ProjectCharterService,
)
from backend.app.application.services.project_factory_generator_service import (
    ProjectFactoryGeneratorService,
)
from backend.app.application.services.project_factory_manifest_service import (
    ProjectFactoryManifestInput,
    ProjectFactoryManifestService,
)
from backend.app.domain.entities.project_management import PROJECT_CHARTER_SOURCE_PATH
from backend.app.infrastructure.config.settings import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        projects_root=str(tmp_path / "projects"),
        web_preview_email_provider="smtp",
        web_preview_email_from="bridge@example.com",
        web_preview_smtp_host="smtp.example.com",
        web_preview_smtp_port=587,
        web_preview_smtp_use_tls=True,
    )


def _generated_project(tmp_path: Path) -> Path:
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    plan = ProjectFactoryManifestService(projects_root=projects_root).plan_manifest(
        ProjectFactoryManifestInput(
            name="Operaciones Puerto",
            business_type="port logistics",
            primary_goal="Replace the operational spreadsheet.",
        )
    )
    ProjectFactoryGeneratorService().generate(plan)
    return projects_root / "operaciones-puerto"


def test_reads_formal_initial_draft(tmp_path: Path) -> None:
    workspace = _generated_project(tmp_path)

    document = ProjectCharterService(settings=_settings(tmp_path)).read(
        str(workspace)
    )

    assert document.path == PROJECT_CHARTER_SOURCE_PATH
    assert document.title == "Acta de Proyecto"
    assert document.status == "draft"
    assert document.version == "v0.1"
    assert "Definiciones pendientes" in document.content
    assert document.render_content is not None


def test_email_contains_complete_acta_and_readable_html_attachment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _generated_project(tmp_path)
    service = ProjectCharterService(settings=_settings(tmp_path))
    document = service.read(str(workspace))
    sent: list[EmailMessage] = []

    class FakeSmtp:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> "FakeSmtp":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def starttls(self) -> None:
            pass

        def send_message(self, message: EmailMessage) -> dict[str, object]:
            sent.append(message)
            return {}

    monkeypatch.setattr("smtplib.SMTP", FakeSmtp)

    result = service.share(
        workspace_path=str(workspace),
        recipients=("Owner@Example.com",),
        include_full_document=True,
        message="Revisar el acta completa.",
    )

    assert result["recipients"] == ["owner@example.com"]
    assert document.content in sent[0].get_body(preferencelist=("plain",)).get_content()
    attachments = list(sent[0].iter_attachments())
    assert [item.get_filename() for item in attachments] == [
        "acta-de-proyecto.md",
        "acta-de-proyecto.html",
    ]


def test_rejects_acta_with_stale_metadata_hash(tmp_path: Path) -> None:
    workspace = _generated_project(tmp_path)
    source = workspace / PROJECT_CHARTER_SOURCE_PATH
    source.write_text(source.read_text(encoding="utf-8") + "\nCambio sin metadata.\n")

    with pytest.raises(ProjectCharterError) as exc:
        ProjectCharterService(settings=_settings(tmp_path)).read(str(workspace))

    assert exc.value.code == "project_charter_integrity_failed"
