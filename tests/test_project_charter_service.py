from __future__ import annotations

from email.message import EmailMessage
import json
from pathlib import Path

import pytest

from backend.app.application.services.project_charter_service import (
    PROJECT_CHARTER_METADATA_PATH,
    PROJECT_CHARTER_PATH,
    ProjectCharterError,
    ProjectCharterService,
)
from backend.app.application.services.project_factory_init_service import (
    ProjectFactoryInitService,
)
from backend.app.infrastructure.config.settings import Settings


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "projects_root": str(tmp_path / "projects"),
        "web_preview_email_provider": "smtp",
        "web_preview_email_from": "bridge@example.com",
        "web_preview_smtp_host": "smtp.example.com",
        "web_preview_smtp_port": 587,
        "web_preview_smtp_use_tls": True,
    }
    values.update(overrides)
    return Settings(**values)


def _approved_draft() -> dict[str, object]:
    return {
        "request": {
            "name": "Port Operations",
            "slug": "port-operations",
            "business_type": "port logistics",
            "primary_goal": "Replace the operational spreadsheet.",
            "platforms": ["android", "web"],
        },
        "guided_intake": {
            "status": "confirmed",
            "confirmedAt": "2026-08-03T12:00:00+00:00",
            "contractPreview": {
                "decisions": {"name": "Port Operations"},
                "assumptions": [{"message": "Preview uses real persisted data."}],
            },
        },
    }


def test_project_charter_materializes_approved_complete_document(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "projects/port-operations"
    workspace.mkdir(parents=True)
    service = ProjectCharterService(settings=_settings(tmp_path))

    document = service.materialize_from_draft(
        workspace=workspace,
        draft_payload=_approved_draft(),
        approved_brief=(
            "Admins and employees record vessel movements. "
            "Users can search and read published operations."
        ),
    )

    assert document.status == "approved"
    assert "Replace the operational spreadsheet" in document.content
    assert "Admins and employees record vessel movements" in document.content
    assert (workspace / PROJECT_CHARTER_PATH).read_text(encoding="utf-8") == (
        document.content
    )
    metadata = json.loads(
        (workspace / PROJECT_CHARTER_METADATA_PATH).read_text(encoding="utf-8")
    )
    assert metadata["status"] == "approved"
    assert metadata["digest"] == document.digest
    assert service.read(str(workspace)).digest == document.digest


def test_project_charter_rejects_unapproved_draft(tmp_path: Path) -> None:
    workspace = tmp_path / "projects/port-operations"
    workspace.mkdir(parents=True)
    draft = _approved_draft()
    guided = draft["guided_intake"]
    assert isinstance(guided, dict)
    guided["status"] = "ready_for_review"

    with pytest.raises(ProjectCharterError) as exc:
        ProjectCharterService(settings=_settings(tmp_path)).materialize_from_draft(
            workspace=workspace,
            draft_payload=draft,
            approved_brief="Approved scope",
        )

    assert exc.value.code == "project_charter_not_approved"
    assert not (workspace / PROJECT_CHARTER_PATH).exists()


def test_project_charter_rejects_missing_approved_scope(tmp_path: Path) -> None:
    workspace = tmp_path / "projects/port-operations"
    workspace.mkdir(parents=True)

    with pytest.raises(ProjectCharterError) as exc:
        ProjectCharterService(settings=_settings(tmp_path)).materialize_from_draft(
            workspace=workspace,
            draft_payload=_approved_draft(),
            approved_brief="   ",
        )

    assert exc.value.code == "project_charter_scope_missing"


def test_project_charter_email_contains_full_document_and_attachment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "projects/port-operations"
    workspace.mkdir(parents=True)
    service = ProjectCharterService(settings=_settings(tmp_path))
    document = service.materialize_from_draft(
        workspace=workspace,
        draft_payload=_approved_draft(),
        approved_brief="Complete approved scope.",
    )
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
        message="Please review the approved charter.",
    )

    assert result["status"] == "sent"
    assert result["recipients"] == ["owner@example.com"]
    assert len(sent) == 1
    message = sent[0]
    assert document.content in message.get_body(preferencelist=("plain",)).get_content()
    attachments = list(message.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "project-charter.md"
    assert document.content in attachments[0].get_content()


def test_init_materializes_charter_and_uses_real_draft_manifest_values(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    state_root = tmp_path / "state"
    charter_service = ProjectCharterService(settings=settings)
    init_service = ProjectFactoryInitService(
        state_root=state_root,
        settings=settings,
        project_charter_service=charter_service,
    )
    workspace = tmp_path / "projects/port-operations"
    workspace.mkdir(parents=True)
    domain_brief = workspace / ".codex/ux/domain-brief.md"
    domain_brief.parent.mkdir(parents=True)
    domain_brief.write_text(
        "Admins and employees record vessel movements with real persisted data.",
        encoding="utf-8",
    )
    draft_payload = _approved_draft()
    drafts_dir = state_root / "drafts"
    drafts_dir.mkdir(parents=True)
    (drafts_dir / "draft-1.json").write_text(
        json.dumps(draft_payload),
        encoding="utf-8",
    )
    job = init_service.start_or_resume(
        draft_id="draft-1",
        workspace_path=str(workspace),
        project_name="Fallback name",
        slug="port-operations",
        frontend_strategy="flutter",
    )

    evidence, blocker = init_service._ensure_project_charter(
        job=job,
        target=workspace,
    )
    manifest_input = init_service._manifest_input_from_draft(
        job,
        strategy="flutter",
    )

    assert blocker is None
    assert evidence[0].argv == ("project-factory", "charter", "materialize")
    assert (workspace / PROJECT_CHARTER_PATH).is_file()
    assert manifest_input.name == "Port Operations"
    assert manifest_input.business_type == "port logistics"
    assert manifest_input.primary_goal == "Replace the operational spreadsheet."
    assert manifest_input.platforms == ("android", "web")
