from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from fastapi.testclient import TestClient
import pytest

from backend.app.api.routes import get_container
from backend.app.application.services.cloudflare_preview_service import (
    CloudflareLookupResult,
)
from backend.app.application.services.project_factory_manifest_service import (
    ProjectFactoryManifestInput,
    ProjectFactoryManifestService,
)
from backend.app.application.services.project_factory_generator_service import (
    ProjectFactoryGeneratorService,
)
from backend.app.application.services.web_preview_deploy_service import (
    WebPreviewDeployInput,
    WebPreviewDeployService,
    WebPreviewError,
    WebPreviewLifecycleInput,
    WebPreviewPlanInput,
    _worker_script_content,
)
from backend.app.application.services.web_preview_invite_service import (
    WebPreviewInviteCreateInput,
    WebPreviewInviteService,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.main import create_app


def test_web_preview_plan_is_stable_and_persisted(tmp_path: Path) -> None:
    project = _generated_project(tmp_path)
    service = _service(tmp_path)

    first = service.plan(WebPreviewPlanInput(project_path=str(project)))
    second = service.plan(WebPreviewPlanInput(project_path=str(project)))

    assert first["status"] == "planned"
    assert first["preview_id"] == "wp-clinica-norte"
    assert first["plan_hash"] == second["plan_hash"]
    assert first["preview_url"] == "https://preview.nienfos.com/clinica-norte"
    assert first["health_url"] == (
        "https://preview.nienfos.com/clinica-norte/api/health"
    )
    assert {
        "kind": "worker_secret",
        "name": "WEB_PREVIEW_INVITE_SECRET",
        "mode": "required_external",
        "status": "operator_configured",
    } in first["planned_resources"]
    assert {
        "kind": "d1_migration",
        "name": "deploy/web-preview/d1/migrations",
        "binding": "PREVIEW_DB",
        "database": "nienfos-preview",
        "mode": "apply_from_project",
        "status": "planned",
    } in first["planned_resources"]
    assert "secret-token" not in str(first)
    assert (tmp_path / "state/previews/wp-clinica-norte.json").is_file()
    assert first["expires_at"]
    assert first["disabled_at"] is None
    assert first["audit_events"][0]["event_type"] == "preview_plan_created"
    assert first["audit_events"][0]["source_app"] == "clinica-norte"


def test_worker_script_content_extracts_module_from_multipart_payload() -> None:
    boundary = "----preview-worker-boundary"
    script = "export default { async fetch(request, env, ctx) { return new Response('ok'); } };"
    raw = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="metadata"\r\n'
        "Content-Type: application/json\r\n\r\n"
        '{"main_module":"index.js"}\r\n'
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="index.js"; filename="index.js"\r\n'
        "Content-Type: application/javascript+module\r\n\r\n"
        f"{script}\r\n"
        f"--{boundary}--\r\n"
    )

    assert (
        _worker_script_content(
            {
                "raw": raw,
                "content_type": f"multipart/form-data; boundary={boundary}",
            }
        )
        == script
    )


def test_web_preview_lifecycle_extend_disable_and_expire_are_persisted(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    service = _service(tmp_path)
    plan = service.plan(WebPreviewPlanInput(project_path=str(project)))

    extended = service.extend_preview(
        WebPreviewLifecycleInput(
            preview_id=plan["preview_id"],
            ttl_seconds=3600,
            reason="operator extend",
        )
    )
    disabled = service.disable_preview(
        WebPreviewLifecycleInput(
            preview_id=plan["preview_id"],
            reason="operator pause",
        )
    )
    expired = service.expire_preview(
        WebPreviewLifecycleInput(preview_id=plan["preview_id"])
    )

    assert extended["expires_at"] != plan["expires_at"]
    assert disabled["status"] == "disabled"
    assert disabled["disabled_reason"] == "operator pause"
    assert expired["status"] == "expired"
    assert {event["event_type"] for event in expired["audit_events"]} >= {
        "preview_plan_created",
        "preview_extended",
        "preview_disabled",
        "preview_expired",
    }
    assert all(
        event["source_app"] == "clinica-norte" for event in expired["audit_events"]
    )


def test_web_preview_get_marks_active_preview_expired_when_expires_at_elapsed(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    service = _service(tmp_path)
    plan = service.plan(WebPreviewPlanInput(project_path=str(project)))
    state_path = tmp_path / "state/previews/wp-clinica-norte.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["status"] = "active"
    state["expires_at"] = "2026-01-01T00:00:00Z"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    refreshed = service.get_preview(plan["preview_id"])

    assert refreshed is not None
    assert refreshed["status"] == "expired"
    assert refreshed["audit_events"][-1]["event_type"] == "preview_expired"


def test_web_preview_deploy_is_blocked_when_apply_is_disabled(tmp_path: Path) -> None:
    project = _generated_project(tmp_path)
    service = _service(tmp_path, apply_enabled=False)
    plan = service.plan(WebPreviewPlanInput(project_path=str(project)))

    with pytest.raises(WebPreviewError) as exc:
        service.deploy(
            WebPreviewDeployInput(
                project_path=str(project),
                confirm_apply=True,
                expected_plan_hash=plan["plan_hash"],
            )
        )

    assert exc.value.code == "apply_disabled"
    assert exc.value.status_code == 403


def test_web_preview_deploy_requires_confirmation_and_plan_hash(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    service = _service(tmp_path, apply_enabled=True)

    with pytest.raises(WebPreviewError) as exc:
        service.deploy(WebPreviewDeployInput(project_path=str(project)))
    assert exc.value.code == "dry_run_required"

    with pytest.raises(WebPreviewError) as exc:
        service.deploy(
            WebPreviewDeployInput(project_path=str(project), confirm_apply=True)
        )
    assert exc.value.code == "plan_hash_required"

    with pytest.raises(WebPreviewError) as exc:
        service.deploy(
            WebPreviewDeployInput(
                project_path=str(project),
                confirm_apply=True,
                expected_plan_hash="0" * 64,
            )
        )
    assert exc.value.code == "plan_hash_mismatch"


def test_web_preview_deploy_is_blocked_when_cloudflare_config_missing(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    service = _service(tmp_path, apply_enabled=True, configured=False)
    plan = service.plan(WebPreviewPlanInput(project_path=str(project)))

    with pytest.raises(WebPreviewError) as exc:
        service.deploy(
            WebPreviewDeployInput(
                project_path=str(project),
                confirm_apply=True,
                expected_plan_hash=plan["plan_hash"],
            )
        )

    assert exc.value.code == "cloudflare_configuration_missing"
    assert exc.value.status_code == 503


def test_web_preview_deploy_applies_resources_with_fake_cloudflare(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    _write_web_build_output(project)
    fake = _FakeCloudflareClient()
    service = _service(tmp_path, apply_enabled=True, fake=fake)
    plan = service.plan(WebPreviewPlanInput(project_path=str(project)))
    invite_service = WebPreviewInviteService(
        settings=_settings(tmp_path, apply_enabled=True),
        preview_service=service,
    )
    invite = invite_service.create_invite(
        WebPreviewInviteCreateInput(preview_id=plan["preview_id"]),
    )
    assert invite["sync_status"] == "not_deployed"

    payload = service.deploy(
        WebPreviewDeployInput(
            project_path=str(project),
            confirm_apply=True,
            expected_plan_hash=plan["plan_hash"],
        )
    )

    assert payload["status"] == "active"
    statuses = {(item["kind"], item["status"]) for item in payload["applied_resources"]}
    assert ("dns_record", "created") in statuses
    assert ("worker_script", "created") in statuses
    assert ("worker_route", "created") in statuses
    assert ("d1_database", "created") in statuses
    assert ("d1_migration", "applied") in statuses
    assert ("pages_project", "created") in statuses
    assert ("r2_bucket", "skipped") in statuses
    assert payload["invite_sync_summary"]["synced"] == 1
    assert fake.calls.count("create_dns_record:zone-1") == 1
    assert "deploy_worker_script:acct-1:nienfos-preview-runtime:module" in fake.calls
    worker_resource = next(
        item for item in payload["applied_resources"] if item["kind"] == "worker_script"
    )
    assert worker_resource["worker_format"] == "module"
    assert worker_resource["verified"] is True
    assert worker_resource["verification_status"] == "verified"
    assert payload["worker_script_verification_status"] == "verified"
    assert (
        "create_worker_route:zone-1:preview.nienfos.com/clinica-norte/*"
        in fake.calls
    )
    assert "execute_d1_sql:acct-1:d1-1" in fake.calls
    stored = _read_invite(tmp_path, invite["invite_id"])
    assert stored["sync_status"] == "synced"
    assert stored["synced_at"]
    assert stored["sync_error"] is None
    insert_calls = [call for call in fake.sql_calls if "preview_invites" in call["sql"]]
    assert insert_calls
    assert invite["token"] not in insert_calls[-1]["sql"]
    assert invite["token_sha256"] in insert_calls[-1]["params"]


def test_web_preview_deploy_is_idempotent_when_resources_exist(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    _write_web_build_output(project)
    fake = _FakeCloudflareClient(resources_exist=True)
    service = _service(tmp_path, apply_enabled=True, fake=fake)
    plan = service.plan(WebPreviewPlanInput(project_path=str(project)))

    payload = service.deploy(
        WebPreviewDeployInput(
            project_path=str(project),
            confirm_apply=True,
            expected_plan_hash=plan["plan_hash"],
        )
    )

    assert payload["status"] == "active"
    assert all(
        item["status"] in {
            "existing",
            "updated",
            "planned_external",
            "skipped",
            "applied",
        }
        for item in payload["applied_resources"]
    )
    assert not any(call.startswith("create_dns_record") for call in fake.calls)
    assert "deploy_worker_script:acct-1:nienfos-preview-runtime:module" in fake.calls
    assert not any(call.startswith("create_worker_route") for call in fake.calls)
    assert not any(call.startswith("create_d1_database") for call in fake.calls)
    assert not any(call.startswith("create_pages_project") for call in fake.calls)
    assert "execute_d1_sql:acct-1:d1-1" in fake.calls


def test_web_preview_deploy_fails_when_worker_remote_verification_mismatches(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    _write_web_build_output(project)
    fake = _FakeCloudflareClient(worker_verify_mismatch=True)
    service = _service(tmp_path, apply_enabled=True, fake=fake)
    plan = service.plan(WebPreviewPlanInput(project_path=str(project)))

    with pytest.raises(WebPreviewError) as exc:
        service.deploy(
            WebPreviewDeployInput(
                project_path=str(project),
                confirm_apply=True,
                expected_plan_hash=plan["plan_hash"],
            )
        )

    assert exc.value.code == "deploy_failed"
    assert "worker_verify_hash_mismatch" in exc.value.message
    state = _read_preview(tmp_path, plan["preview_id"])
    assert state["status"] == "failed"
    assert "worker_verify_hash_mismatch" in state["error"]


def test_web_preview_deploy_recovers_existing_active_without_duplicate_apply(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    _write_web_build_output(project)
    fake = _FakeCloudflareClient()
    service = _service(tmp_path, apply_enabled=True, fake=fake)
    plan = service.plan(WebPreviewPlanInput(project_path=str(project)))
    first = service.deploy(
        WebPreviewDeployInput(
            project_path=str(project),
            confirm_apply=True,
            expected_plan_hash=plan["plan_hash"],
        )
    )
    fake.calls.clear()

    recovered = service.deploy(
        WebPreviewDeployInput(
            project_path=str(project),
            confirm_apply=True,
            expected_plan_hash=plan["plan_hash"],
        )
    )

    assert first["status"] == "active"
    assert recovered["status"] == "active"
    assert recovered["recovery_status"] == "existing_active_verified"
    assert not fake.calls
    assert recovered["audit_events"][-1]["event_type"] == "preview_recovery_verified"


def test_web_preview_deploy_recovers_interrupted_applying_state_with_existing_resources(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    _write_web_build_output(project)
    fake = _FakeCloudflareClient(resources_exist=True)
    service = _service(tmp_path, apply_enabled=True, fake=fake)
    plan = service.plan(WebPreviewPlanInput(project_path=str(project)))
    state_path = tmp_path / "state/previews/wp-clinica-norte.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["status"] = "applying"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    recovered = service.deploy(
        WebPreviewDeployInput(
            project_path=str(project),
            confirm_apply=True,
            expected_plan_hash=plan["plan_hash"],
        )
    )

    assert recovered["status"] == "active"
    assert recovered["recovery_status"] == "recovering_from_applying"
    assert all(
        item["status"] in {
            "existing",
            "updated",
            "planned_external",
            "skipped",
            "applied",
        }
        for item in recovered["applied_resources"]
    )
    assert "preview_recovery_started" in {
        event["event_type"] for event in recovered["audit_events"]
    }


def test_web_preview_deploy_accepts_svelte_strategy_assets(
    tmp_path: Path,
) -> None:
    project = _generated_svelte_project(tmp_path)
    _write_svelte_web_build_output(project)
    fake = _FakeCloudflareClient()
    service = _service(tmp_path, apply_enabled=True, fake=fake)
    plan = service.plan(WebPreviewPlanInput(project_path=str(project)))

    payload = service.deploy(
        WebPreviewDeployInput(
            project_path=str(project),
            confirm_apply=True,
            expected_plan_hash=plan["plan_hash"],
        )
    )

    assert payload["status"] == "active"
    assert payload["source_app"] == "portal-clientes"
    assert (
        "create_worker_route:zone-1:preview.nienfos.com/portal-clientes/*"
        in fake.calls
    )


def test_web_preview_deploy_failure_persists_failed_state_without_secrets(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    _write_web_build_output(project)
    fake = _FakeCloudflareClient(fail_worker=True)
    service = _service(tmp_path, apply_enabled=True, fake=fake)
    plan = service.plan(WebPreviewPlanInput(project_path=str(project)))

    with pytest.raises(WebPreviewError) as exc:
        service.deploy(
            WebPreviewDeployInput(
                project_path=str(project),
                confirm_apply=True,
                expected_plan_hash=plan["plan_hash"],
            )
        )

    assert exc.value.code == "deploy_failed"
    stored = service.get_preview("wp-clinica-norte")
    assert stored is not None
    assert stored["status"] == "failed"
    assert "worker_deploy_failed" in stored["error"]
    assert "secret-token" not in str(stored)
    assert "Bearer secret" not in str(stored)


def test_web_preview_deploy_api_plan_status_list_and_apply_gate(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    app = create_app(_settings(tmp_path, apply_enabled=False))
    client = TestClient(app)

    plan_response = client.post(
        "/web-previews/plan",
        json={"projectPath": str(project), "sourceApp": "clinica-norte"},
    )
    blocked_response = client.post(
        "/web-previews/deploy",
        json={
            "projectPath": str(project),
            "sourceApp": "clinica-norte",
            "confirmApply": True,
            "expectedPlanHash": plan_response.json()["plan_hash"],
        },
    )
    status_response = client.get("/web-previews/wp-clinica-norte")
    list_response = client.get("/web-previews")
    missing_response = client.get("/web-previews/missing")

    assert plan_response.status_code == 200
    assert plan_response.json()["status"] == "planned"
    assert blocked_response.status_code == 403
    assert blocked_response.json()["detail"]["code"] == "apply_disabled"
    assert status_response.status_code == 200
    assert status_response.json()["preview_id"] == "wp-clinica-norte"
    assert status_response.json()["health_url"].endswith("/api/health")
    assert list_response.status_code == 200
    assert list_response.json()["previews"][0]["preview_id"] == "wp-clinica-norte"
    assert missing_response.status_code == 404


def test_web_preview_deploy_api_success_with_fake_cloudflare(tmp_path: Path) -> None:
    project = _generated_project(tmp_path)
    _write_web_build_output(project)
    app = create_app(_settings(tmp_path, apply_enabled=True))
    container = app.dependency_overrides[get_container]()
    container.web_preview_deploy_service = WebPreviewDeployService(
        settings=container.settings,
        client=_FakeCloudflareClient(),
    )
    client = TestClient(app)
    plan = client.post(
        "/web-previews/plan",
        json={"projectPath": str(project), "sourceApp": "clinica-norte"},
    ).json()

    response = client.post(
        "/web-previews/deploy",
        json={
            "projectPath": str(project),
            "sourceApp": "clinica-norte",
            "confirmApply": True,
            "expectedPlanHash": plan["plan_hash"],
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "active"


def test_web_preview_lifecycle_api_mutations(tmp_path: Path) -> None:
    project = _generated_project(tmp_path)
    app = create_app(_settings(tmp_path, apply_enabled=False))
    client = TestClient(app)
    plan = client.post(
        "/web-previews/plan",
        json={"projectPath": str(project), "sourceApp": "clinica-norte"},
    ).json()

    extended = client.post(
        f"/web-previews/{plan['preview_id']}/extend",
        json={"ttlSeconds": 3600, "reason": "more review"},
    )
    disabled = client.post(
        f"/web-previews/{plan['preview_id']}/disable",
        json={"reason": "pause sharing"},
    )
    expired = client.post(f"/web-previews/{plan['preview_id']}/expire", json={})

    assert extended.status_code == 200
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    assert disabled.json()["disabled_reason"] == "pause sharing"
    assert expired.status_code == 200
    assert expired.json()["status"] == "expired"
    assert expired.json()["audit_events"][-1]["event_type"] == "preview_expired"


def test_web_preview_invite_created_after_deploy_syncs_immediately(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    _write_web_build_output(project)
    fake = _FakeCloudflareClient()
    service = _service(tmp_path, apply_enabled=True, fake=fake)
    plan = service.plan(WebPreviewPlanInput(project_path=str(project)))
    service.deploy(
        WebPreviewDeployInput(
            project_path=str(project),
            confirm_apply=True,
            expected_plan_hash=plan["plan_hash"],
        )
    )
    invite_service = WebPreviewInviteService(
        settings=_settings(tmp_path, apply_enabled=True),
        preview_service=service,
    )

    invite = invite_service.create_invite(
        WebPreviewInviteCreateInput(preview_id=plan["preview_id"]),
    )

    assert invite["sync_status"] == "synced"
    assert invite["synced_at"]
    assert invite["sync_error"] is None
    assert fake.sql_calls[-1]["params"][0] == invite["invite_id"]
    assert fake.sql_calls[-1]["params"][1] == invite["token_sha256"]


def test_web_preview_invite_sync_failure_and_retry_are_persisted(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    _write_web_build_output(project)
    fake = _FakeCloudflareClient()
    service = _service(tmp_path, apply_enabled=True, fake=fake)
    plan = service.plan(WebPreviewPlanInput(project_path=str(project)))
    service.deploy(
        WebPreviewDeployInput(
            project_path=str(project),
            confirm_apply=True,
            expected_plan_hash=plan["plan_hash"],
        )
    )
    fake.fail_invite_sync = True
    invite_service = WebPreviewInviteService(
        settings=_settings(tmp_path, apply_enabled=True),
        preview_service=service,
    )

    invite = invite_service.create_invite(
        WebPreviewInviteCreateInput(preview_id=plan["preview_id"]),
    )

    assert invite["sync_status"] == "failed"
    assert "d1_invite_sync_failed" in invite["sync_error"]
    assert "secret-token" not in invite["sync_error"]
    fake.fail_invite_sync = False
    retried = invite_service.sync_invite(
        preview_id=plan["preview_id"],
        invite_id=invite["invite_id"],
    )
    assert retried["sync_status"] == "synced"
    assert retried["sync_error"] is None


def test_web_preview_invite_revoke_after_deploy_updates_d1(
    tmp_path: Path,
) -> None:
    project = _generated_project(tmp_path)
    _write_web_build_output(project)
    fake = _FakeCloudflareClient()
    service = _service(tmp_path, apply_enabled=True, fake=fake)
    plan = service.plan(WebPreviewPlanInput(project_path=str(project)))
    service.deploy(
        WebPreviewDeployInput(
            project_path=str(project),
            confirm_apply=True,
            expected_plan_hash=plan["plan_hash"],
        )
    )
    invite_service = WebPreviewInviteService(
        settings=_settings(tmp_path, apply_enabled=True),
        preview_service=service,
    )
    invite = invite_service.create_invite(
        WebPreviewInviteCreateInput(preview_id=plan["preview_id"]),
    )

    revoked = invite_service.revoke_invite(
        preview_id=plan["preview_id"],
        invite_id=invite["invite_id"],
    )

    assert revoked["sync_status"] == "synced"
    assert revoked["revoked_at"]
    assert fake.sql_calls[-1]["params"][0] == invite["invite_id"]
    assert fake.sql_calls[-1]["params"][7] == revoked["revoked_at"]


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


def _generated_svelte_project(tmp_path: Path) -> Path:
    projects_root = tmp_path / "projects"
    projects_root.mkdir(parents=True, exist_ok=True)
    manifest_plan = ProjectFactoryManifestService(
        projects_root=projects_root,
    ).plan_manifest(
        ProjectFactoryManifestInput(
            name="Portal Clientes",
            business_type="services",
            primary_goal="Clientes consultan estados",
            platforms=("web",),
            frontend_strategy="svelte",
        )
    )
    ProjectFactoryGeneratorService().generate(manifest_plan)
    return projects_root / "portal-clientes"


def _write_web_build_output(project: Path) -> None:
    build_dir = project / "build/web-preview/clinica-norte"
    assets_dir = build_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / "index.html").write_text("<!doctype html><title>Preview</title>\n")
    (build_dir / "manifest.json").write_text("{}\n")
    (build_dir / "flutter_bootstrap.js").write_text("void 0;\n")
    (assets_dir / "AssetManifest.bin").write_bytes(b"assets")


def _write_svelte_web_build_output(project: Path) -> None:
    build_dir = project / "build/web-preview/portal-clientes"
    assets_dir = build_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / "index.html").write_text(
        '<!doctype html><script type="module" src="/assets/index.js"></script>\n',
        encoding="utf-8",
    )
    (assets_dir / "index.js").write_text("console.log('preview');\n")


def _read_invite(tmp_path: Path, invite_id: str) -> dict[str, Any]:
    return json.loads(
        (tmp_path / "state/invites" / f"{invite_id}.json").read_text(
            encoding="utf-8",
        )
    )


def _read_preview(tmp_path: Path, preview_id: str) -> dict[str, Any]:
    return json.loads(
        (tmp_path / "state/previews" / f"{preview_id}.json").read_text(
            encoding="utf-8",
        )
    )


def _settings(
    tmp_path: Path,
    *,
    apply_enabled: bool,
    configured: bool = True,
) -> Settings:
    token = "secret-token" if configured else None
    return Settings(
        projects_root=str(tmp_path / "projects"),
        project_factory_state_dir=str(tmp_path / "state/project_factory"),
        web_preview_state_dir=str(tmp_path / "state"),
        web_preview_apply_enabled=apply_enabled,
        cloudflare_api_token=token,
        cloudflare_dns_api_token=token,
        cloudflare_account_id="acct-1" if configured else None,
        cloudflare_zone_id="zone-1" if configured else None,
        cloudflare_zone_name="nienfos.com",
        preview_base_domain="preview.nienfos.com",
        preview_worker_name="nienfos-preview-runtime",
        preview_d1_database_name="nienfos-preview",
        preview_pages_project_name="nienfos-preview-web",
        preview_r2_bucket_name=None,
        web_preview_invite_secret="test-web-preview-invite-secret-value-32",
    )


def _service(
    tmp_path: Path,
    *,
    apply_enabled: bool = False,
    configured: bool = True,
    fake: "_FakeCloudflareClient | None" = None,
) -> WebPreviewDeployService:
    return WebPreviewDeployService(
        settings=_settings(
            tmp_path,
            apply_enabled=apply_enabled,
            configured=configured,
        ),
        client=fake,
    )


class _FakeCloudflareClient:
    def __init__(
        self,
        *,
        resources_exist: bool = False,
        fail_worker: bool = False,
        worker_verify_mismatch: bool = False,
        fail_invite_sync: bool = False,
    ) -> None:
        self.calls: list[str] = []
        self.sql_calls: list[dict[str, Any]] = []
        self.resources_exist = resources_exist
        self.fail_worker = fail_worker
        self.worker_verify_mismatch = worker_verify_mismatch
        self.fail_invite_sync = fail_invite_sync
        self.worker_scripts: dict[str, str] = {}

    def get_account(self, account_id: str) -> CloudflareLookupResult:
        self.calls.append(f"get_account:{account_id}")
        return CloudflareLookupResult(ok=True, payload={"result": {"id": account_id}})

    def get_zone(self, zone_id: str) -> CloudflareLookupResult:
        self.calls.append(f"get_zone:{zone_id}")
        return CloudflareLookupResult(ok=True, payload={"result": {"id": zone_id}})

    def list_dns_records(
        self,
        *,
        zone_id: str,
        name: str,
        record_type: str | None = None,
    ) -> CloudflareLookupResult:
        self.calls.append(f"list_dns_records:{zone_id}:{name}:{record_type}")
        records: list[dict[str, Any]] = (
            [
                {
                    "id": "dns-1",
                    "name": name,
                    "type": record_type or "CNAME",
                    "content": "nienfos.com",
                    "proxied": True,
                }
            ]
            if self.resources_exist
            else []
        )
        return CloudflareLookupResult(ok=True, payload={"result": records})

    def create_dns_record(
        self,
        *,
        zone_id: str,
        payload: dict[str, Any],
    ) -> CloudflareLookupResult:
        self.calls.append(f"create_dns_record:{zone_id}")
        return CloudflareLookupResult(ok=True, payload={"result": payload})

    def update_dns_record(
        self,
        *,
        zone_id: str,
        record_id: str,
        payload: dict[str, Any],
    ) -> CloudflareLookupResult:
        self.calls.append(f"update_dns_record:{zone_id}:{record_id}")
        return CloudflareLookupResult(ok=True, payload={"result": payload})

    def list_worker_routes(
        self,
        *,
        zone_id: str,
        pattern: str,
    ) -> CloudflareLookupResult:
        self.calls.append(f"list_worker_routes:{zone_id}:{pattern}")
        routes: list[dict[str, Any]] = (
            [{"id": "route-1", "pattern": pattern, "script": "nienfos-preview-runtime"}]
            if self.resources_exist
            else []
        )
        return CloudflareLookupResult(ok=True, payload={"result": routes})

    def create_worker_route(
        self,
        *,
        zone_id: str,
        payload: dict[str, Any],
    ) -> CloudflareLookupResult:
        self.calls.append(f"create_worker_route:{zone_id}:{payload['pattern']}")
        return CloudflareLookupResult(ok=True, payload={"result": payload})

    def update_worker_route(
        self,
        *,
        zone_id: str,
        route_id: str,
        payload: dict[str, Any],
    ) -> CloudflareLookupResult:
        self.calls.append(f"update_worker_route:{zone_id}:{route_id}")
        return CloudflareLookupResult(ok=True, payload={"result": payload})

    def list_worker_scripts(self, account_id: str) -> CloudflareLookupResult:
        self.calls.append(f"list_worker_scripts:{account_id}")
        return CloudflareLookupResult(ok=True, payload={"result": []})

    def get_worker_script(
        self,
        *,
        account_id: str,
        script_name: str,
    ) -> CloudflareLookupResult:
        self.calls.append(f"get_worker_script:{account_id}:{script_name}")
        if script_name in self.worker_scripts:
            content = (
                "mismatched remote worker"
                if self.worker_verify_mismatch
                else self.worker_scripts[script_name]
            )
            return CloudflareLookupResult(ok=True, payload={"raw": content})
        if self.resources_exist:
            return CloudflareLookupResult(
                ok=True,
                payload={"raw": "// existing worker script"},
            )
        return CloudflareLookupResult(ok=False, status_code=404, error="not found")

    def deploy_worker_script(
        self,
        *,
        account_id: str,
        script_name: str,
        script_content: str,
        worker_format: str = "module",
    ) -> CloudflareLookupResult:
        self.calls.append(
            f"deploy_worker_script:{account_id}:{script_name}:{worker_format}"
        )
        if self.fail_worker:
            return CloudflareLookupResult(
                ok=False,
                status_code=500,
                error="Bearer secret-token worker deploy failed",
            )
        self.worker_scripts[script_name] = script_content
        return CloudflareLookupResult(
            ok=True,
            payload={"result": {"id": script_name, "size": len(script_content)}},
        )

    def list_d1_databases(self, account_id: str) -> CloudflareLookupResult:
        self.calls.append(f"list_d1_databases:{account_id}")
        databases: list[dict[str, Any]] = (
            [{"name": "nienfos-preview", "uuid": "d1-1"}]
            if self.resources_exist
            else []
        )
        return CloudflareLookupResult(ok=True, payload={"result": databases})

    def create_d1_database(
        self,
        *,
        account_id: str,
        name: str,
    ) -> CloudflareLookupResult:
        self.calls.append(f"create_d1_database:{account_id}:{name}")
        return CloudflareLookupResult(
            ok=True,
            payload={"result": {"name": name, "uuid": "d1-1"}},
        )

    def execute_d1_sql(
        self,
        *,
        account_id: str,
        database_id: str,
        sql: str,
        params: list[Any] | None = None,
    ) -> CloudflareLookupResult:
        self.calls.append(f"execute_d1_sql:{account_id}:{database_id}")
        self.sql_calls.append({"sql": sql, "params": params or []})
        if self.fail_invite_sync and "INSERT INTO preview_invites" in sql:
            return CloudflareLookupResult(
                ok=False,
                status_code=500,
                error="Bearer secret-token invite sync failed",
            )
        return CloudflareLookupResult(
            ok=True,
            payload={"result": [{"sql": sql, "params": params or []}]},
        )

    def get_pages_project(
        self,
        *,
        account_id: str,
        project_name: str,
    ) -> CloudflareLookupResult:
        self.calls.append(f"get_pages_project:{account_id}:{project_name}")
        if self.resources_exist:
            return CloudflareLookupResult(
                ok=True,
                payload={"result": {"name": project_name}},
            )
        return CloudflareLookupResult(ok=False, status_code=404, error="not found")

    def create_pages_project(
        self,
        *,
        account_id: str,
        name: str,
        production_branch: str = "main",
    ) -> CloudflareLookupResult:
        self.calls.append(f"create_pages_project:{account_id}:{name}")
        return CloudflareLookupResult(
            ok=True,
            payload={"result": {"name": name, "production_branch": production_branch}},
        )

    def list_r2_buckets(self, account_id: str) -> CloudflareLookupResult:
        self.calls.append(f"list_r2_buckets:{account_id}")
        return CloudflareLookupResult(ok=True, payload={"result": []})
