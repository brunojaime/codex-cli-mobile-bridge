from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from backend.app.application.services.project_factory_generator_service import (
    ProjectFactoryGeneratorService,
)
from backend.app.application.services.project_factory_manifest_service import (
    ProjectFactoryManifestInput,
    ProjectFactoryManifestService,
)
from backend.app.application.services.web_preview_deploy_service import (
    WebPreviewDeployService,
    WebPreviewPlanInput,
)
from backend.app.application.services.web_preview_invite_service import (
    WEB_PREVIEW_INVITE_AUDIENCE,
    WEB_PREVIEW_INVITE_SCOPE,
    WebPreviewInviteCreateInput,
    WebPreviewInviteError,
    WebPreviewInviteService,
    sign_web_preview_invite,
    verify_web_preview_invite,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.main import create_app


SECRET = "test-web-preview-invite-secret-value-32"


def test_web_preview_invite_token_verifier_accepts_valid_token() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    token = _token("clinica-norte", exp=int((now + timedelta(minutes=5)).timestamp()))

    payload = verify_web_preview_invite(
        secret=SECRET,
        token=token,
        source_app="clinica-norte",
        now=now,
    )

    assert payload["source_app"] == "clinica-norte"
    assert payload["aud"] == WEB_PREVIEW_INVITE_AUDIENCE
    assert payload["scope"] == WEB_PREVIEW_INVITE_SCOPE


def test_web_preview_invite_token_verifier_rejects_expired_and_wrong_app() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    expired = _token(
        "clinica-norte",
        exp=int((now - timedelta(seconds=1)).timestamp()),
    )
    wrong_app = _token(
        "otra-app",
        exp=int((now + timedelta(minutes=5)).timestamp()),
    )

    with pytest.raises(WebPreviewInviteError) as expired_exc:
        verify_web_preview_invite(
            secret=SECRET,
            token=expired,
            source_app="clinica-norte",
            now=now,
        )
    with pytest.raises(WebPreviewInviteError) as app_exc:
        verify_web_preview_invite(
            secret=SECRET,
            token=wrong_app,
            source_app="clinica-norte",
            now=now,
        )

    assert expired_exc.value.code == "expired_invite_token"
    assert app_exc.value.code == "invalid_invite_app"


def test_web_preview_invite_creation_requires_secret(tmp_path: Path) -> None:
    deploy_service = _planned_preview(tmp_path, secret=None)
    service = WebPreviewInviteService(
        settings=_settings(tmp_path, secret=None),
        preview_service=deploy_service,
    )

    with pytest.raises(WebPreviewInviteError) as exc:
        service.create_invite(WebPreviewInviteCreateInput(preview_id="wp-clinica-norte"))

    assert exc.value.code == "web_preview_invite_secret_missing"
    assert exc.value.status_code == 503


def test_web_preview_invite_creation_validates_ttl(tmp_path: Path) -> None:
    deploy_service = _planned_preview(tmp_path)
    service = WebPreviewInviteService(
        settings=_settings(tmp_path),
        preview_service=deploy_service,
    )

    with pytest.raises(WebPreviewInviteError) as invalid:
        service.create_invite(
            WebPreviewInviteCreateInput(
                preview_id="wp-clinica-norte",
                ttl_seconds=0,
            )
        )
    with pytest.raises(WebPreviewInviteError) as exceeds:
        service.create_invite(
            WebPreviewInviteCreateInput(
                preview_id="wp-clinica-norte",
                ttl_seconds=604801,
            )
        )

    assert invalid.value.code == "invalid_invite_ttl"
    assert exceeds.value.code == "invite_ttl_exceeds_max"


def test_web_preview_invite_creation_persists_metadata_without_plain_token(
    tmp_path: Path,
) -> None:
    deploy_service = _planned_preview(tmp_path)
    service = WebPreviewInviteService(
        settings=_settings(tmp_path),
        preview_service=deploy_service,
    )

    invite = service.create_invite(
        WebPreviewInviteCreateInput(
            preview_id="wp-clinica-norte",
            ttl_seconds=300,
        )
    )

    assert invite["invite_url"].startswith(
        "https://preview.nienfos.com/clinica-norte/__preview/access?token=",
    )
    assert invite["token"]
    assert invite["token_sha256"]
    stored_path = tmp_path / "state/invites" / f"{invite['invite_id']}.json"
    stored = stored_path.read_text(encoding="utf-8")
    assert invite["token"] not in stored
    payload = json.loads(stored)
    assert payload["token_sha256"] == invite["token_sha256"]
    assert payload["single_use"] is True
    assert payload["used_at"] is None
    assert payload["revoked_at"] is None
    listed = service.list_invites("wp-clinica-norte")
    assert listed[0]["invite_id"] == invite["invite_id"]
    assert listed[0]["single_use"] is True
    assert "token" not in listed[0]
    assert "invite_url" not in listed[0]


def test_web_preview_invite_revoke_marks_metadata_without_plain_token(
    tmp_path: Path,
) -> None:
    deploy_service = _planned_preview(tmp_path)
    service = WebPreviewInviteService(
        settings=_settings(tmp_path),
        preview_service=deploy_service,
    )
    invite = service.create_invite(
        WebPreviewInviteCreateInput(
            preview_id="wp-clinica-norte",
            ttl_seconds=300,
            single_use=True,
        )
    )

    revoked = service.revoke_invite(
        preview_id="wp-clinica-norte",
        invite_id=invite["invite_id"],
    )
    stored = json.loads(
        (tmp_path / "state/invites" / f"{invite['invite_id']}.json").read_text(
            encoding="utf-8",
        )
    )

    assert revoked["revoked_at"]
    assert stored["revoked_at"] == revoked["revoked_at"]
    assert invite["token"] not in json.dumps(stored)


def test_web_preview_invite_api_create_and_list(tmp_path: Path) -> None:
    project = _generated_project(tmp_path)
    settings = _settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)
    plan = client.post(
        "/web-previews/plan",
        json={"projectPath": str(project), "sourceApp": "clinica-norte"},
    )

    response = client.post(
        f"/web-previews/{plan.json()['preview_id']}/invites",
        json={"ttlSeconds": 300, "singleUse": True},
    )
    listed = client.get(f"/web-previews/{plan.json()['preview_id']}/invites")

    assert response.status_code == 200
    payload = response.json()
    assert payload["token"]
    assert payload["invite_url"].endswith(payload["token"])
    assert payload["single_use"] is True
    assert payload["used_at"] is None
    assert payload["revoked_at"] is None
    assert listed.status_code == 200
    listed_payload = listed.json()["invites"][0]
    assert listed_payload["invite_id"] == payload["invite_id"]
    assert listed_payload["token"] is None
    assert listed_payload["invite_url"] is None
    revoke = client.delete(
        f"/web-previews/{plan.json()['preview_id']}/invites/{payload['invite_id']}",
    )
    assert revoke.status_code == 200
    assert revoke.json()["revoked_at"]


def test_web_preview_invite_api_reports_disabled_when_secret_missing(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    app = create_app(_settings(tmp_path, secret=None))
    client = TestClient(app)
    plan = client.post(
        "/web-previews/plan",
        json={"projectPath": str(project), "sourceApp": "clinica-norte"},
    )

    response = client.post(f"/web-previews/{plan.json()['preview_id']}/invites")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "web_preview_invite_secret_missing"


def _token(source_app: str, *, exp: int) -> str:
    return sign_web_preview_invite(
        secret=SECRET,
        payload={
            "aud": WEB_PREVIEW_INVITE_AUDIENCE,
            "scope": WEB_PREVIEW_INVITE_SCOPE,
            "preview_id": f"wp-{source_app}",
            "source_app": source_app,
            "app_slug": source_app,
            "invite_id": "wpi-test",
            "iat": exp - 60,
            "exp": exp,
        },
    )


def _planned_preview(
    tmp_path: Path,
    *,
    secret: str | None = SECRET,
) -> WebPreviewDeployService:
    project = _generated_project(tmp_path)
    service = WebPreviewDeployService(settings=_settings(tmp_path, secret=secret))
    service.plan(WebPreviewPlanInput(project_path=str(project)))
    return service


def _generated_project(tmp_path: Path) -> Path:
    projects_root = tmp_path / "projects"
    projects_root.mkdir(parents=True, exist_ok=True)
    manifest_plan = ProjectFactoryManifestService(
        projects_root=projects_root,
    ).plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
        )
    )
    ProjectFactoryGeneratorService().generate(manifest_plan)
    return projects_root / "clinica-norte"


def _settings(tmp_path: Path, *, secret: str | None = SECRET) -> Settings:
    return Settings(
        projects_root=str(tmp_path / "projects"),
        project_factory_state_dir=str(tmp_path / "state/project_factory"),
        web_preview_state_dir=str(tmp_path / "state"),
        web_preview_invite_secret=secret,
        web_preview_invite_default_ttl_seconds=300,
        web_preview_invite_max_ttl_seconds=604800,
        cloudflare_api_token=None,
        cloudflare_dns_api_token=None,
        cloudflare_account_id=None,
        cloudflare_zone_id=None,
    )
