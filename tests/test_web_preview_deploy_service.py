from __future__ import annotations

from pathlib import Path
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
    WebPreviewPlanInput,
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
    assert (tmp_path / "state/previews/wp-clinica-norte.json").is_file()


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
    assert ("d1_database", "created") in statuses
    assert ("pages_project", "created") in statuses
    assert ("r2_bucket", "skipped") in statuses
    assert fake.calls.count("create_dns_record:zone-1") == 1
    assert "deploy_worker_script:acct-1:nienfos-preview-runtime" in fake.calls


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
        item["status"] in {"existing", "planned_external", "skipped"}
        for item in payload["applied_resources"]
    )
    assert not any(call.startswith("create_dns_record") for call in fake.calls)
    assert not any(call.startswith("deploy_worker_script") for call in fake.calls)
    assert not any(call.startswith("create_d1_database") for call in fake.calls)
    assert not any(call.startswith("create_pages_project") for call in fake.calls)


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


def _write_web_build_output(project: Path) -> None:
    build_dir = project / "build/web-preview/clinica-norte"
    build_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / "index.html").write_text("<!doctype html><title>Preview</title>\n")


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
    ) -> None:
        self.calls: list[str] = []
        self.resources_exist = resources_exist
        self.fail_worker = fail_worker

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
            [{"id": "dns-1", "name": name, "type": record_type or "CNAME"}]
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
        if self.resources_exist:
            return CloudflareLookupResult(
                ok=True,
                payload={"result": {"id": script_name}},
            )
        return CloudflareLookupResult(ok=False, status_code=404, error="not found")

    def deploy_worker_script(
        self,
        *,
        account_id: str,
        script_name: str,
        script_content: str,
    ) -> CloudflareLookupResult:
        self.calls.append(f"deploy_worker_script:{account_id}:{script_name}")
        if self.fail_worker:
            return CloudflareLookupResult(
                ok=False,
                status_code=500,
                error="Bearer secret-token worker deploy failed",
            )
        return CloudflareLookupResult(
            ok=True,
            payload={"result": {"id": script_name, "size": len(script_content)}},
        )

    def list_d1_databases(self, account_id: str) -> CloudflareLookupResult:
        self.calls.append(f"list_d1_databases:{account_id}")
        databases: list[dict[str, Any]] = (
            [{"name": "nienfos-preview"}] if self.resources_exist else []
        )
        return CloudflareLookupResult(ok=True, payload={"result": databases})

    def create_d1_database(
        self,
        *,
        account_id: str,
        name: str,
    ) -> CloudflareLookupResult:
        self.calls.append(f"create_d1_database:{account_id}:{name}")
        return CloudflareLookupResult(ok=True, payload={"result": {"name": name}})

    def execute_d1_sql(
        self,
        *,
        account_id: str,
        database_id: str,
        sql: str,
        params: list[Any] | None = None,
    ) -> CloudflareLookupResult:
        self.calls.append(f"execute_d1_sql:{account_id}:{database_id}")
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
