from __future__ import annotations

from typing import Any

import httpx

from backend.app.application.services.cloudflare_preview_service import (
    CloudflareLookupResult,
    CloudflarePreviewDoctorService,
    CloudflareProvisioningPlanner,
    HttpCloudflareClient,
)
from backend.app.application.services.project_factory_generator_service import (
    _web_preview_manifest_payload,
)
from backend.app.infrastructure.config.settings import Settings


def test_cloudflare_doctor_reports_missing_configuration_without_client_calls() -> None:
    fake_client = _FakeCloudflareClient()
    service = CloudflarePreviewDoctorService(
        settings=Settings(
            cloudflare_api_token=None,
            cloudflare_dns_api_token=None,
            cloudflare_account_id=None,
            cloudflare_zone_id=None,
        ),
        client=fake_client,
    )

    payload = service.doctor()

    assert payload["kind"] == "codex.webPreviewDoctor"
    assert payload["ok"] is False
    assert payload["status"] == "blocked_configuration"
    checks = {item["code"]: item for item in payload["checks"]}
    assert checks["cloudflare_platform_token_configured"]["ok"] is False
    assert checks["cloudflare_dns_token_configured"]["ok"] is False
    assert fake_client.calls == []
    assert payload["planner"]["dry_run"] is True


def test_cloudflare_doctor_validates_required_cloudflare_surfaces() -> None:
    service = CloudflarePreviewDoctorService(
        settings=_configured_settings(),
        client=_FakeCloudflareClient(
            dns_records=[
                {
                    "id": "dns-1",
                    "name": "preview.nienfos.com",
                    "type": "CNAME",
                },
            ],
            r2_result=CloudflareLookupResult(
                ok=False,
                status_code=403,
                error="R2 disabled",
            ),
        ),
    )

    payload = service.doctor()

    assert payload["ok"] is True
    assert payload["status"] == "ready"
    assert payload["base_domain"] == "preview.nienfos.com"
    checks = {item["code"]: item for item in payload["checks"]}
    assert checks["cloudflare_account"]["ok"] is True
    assert checks["cloudflare_zone"]["ok"] is True
    assert checks["preview_dns_record"]["status"] == "present"
    assert checks["workers_access"]["ok"] is True
    assert checks["preview_worker_script"]["ok"] is True
    assert checks["d1_access"]["ok"] is True
    assert checks["pages_project"]["ok"] is True
    assert checks["r2_optional_access"]["ok"] is True
    assert checks["r2_optional_access"]["status"] == "disabled_or_blocked"
    assert "platform-token" not in str(payload)
    assert "dns-token" not in str(payload)


def test_cloudflare_doctor_blocks_missing_preview_dns_record() -> None:
    service = CloudflarePreviewDoctorService(
        settings=_configured_settings(),
        client=_FakeCloudflareClient(dns_records=[]),
    )

    payload = service.doctor()

    assert payload["ok"] is False
    assert payload["status"] == "blocked"
    checks = {item["code"]: item for item in payload["checks"]}
    assert checks["preview_dns_record"]["ok"] is False
    assert checks["preview_dns_record"]["status"] == "missing"


def test_cloudflare_provisioning_planner_is_dry_run_and_side_effect_free() -> None:
    plan = CloudflareProvisioningPlanner(settings=_configured_settings()).plan()

    assert plan["kind"] == "codex.webPreviewProvisioningPlan"
    assert plan["dry_run"] is True
    assert plan["side_effects"] == []
    assert plan["runtime_type"] == "cloudflare_worker_assets"
    assert plan["health_path"] == "/api/health"
    resources = {(item["kind"], item.get("name")) for item in plan["resources"]}
    assert ("dns_record", "preview.nienfos.com") in resources
    assert ("worker_script", "nienfos-preview-runtime") in resources
    assert ("d1_database", "nienfos-preview") in resources
    assert ("pages_project", "nienfos-preview-web") in resources
    assert ("r2_bucket", None) in resources


def test_cloudflare_planner_can_use_generated_web_preview_manifest() -> None:
    manifest = _web_preview_manifest_payload("clinica-norte", "Clinica Norte")

    plan = CloudflareProvisioningPlanner(
        settings=_configured_settings(),
    ).plan_for_manifest(manifest)

    resources = {(item["kind"], item.get("name")) for item in plan["resources"]}
    assert ("dns_record", "preview.nienfos.com") in resources
    assert ("worker_script", "nienfos-preview-runtime") in resources
    assert ("d1_database", "nienfos-preview") in resources
    assert ("pages_project", "nienfos-preview-web") in resources
    assert plan["dry_run"] is True
    assert plan["runtime_type"] == "cloudflare_worker_assets"
    assert plan["health_path"] == "/api/health"
    assert plan["access_mode"] == "invite_token"
    assert plan["required_worker_secrets"] == ["WEB_PREVIEW_INVITE_SECRET"]
    secret_resources = [
        item for item in plan["resources"] if item["kind"] == "worker_secret"
    ]
    assert secret_resources == [
        {
            "kind": "worker_secret",
            "name": "WEB_PREVIEW_INVITE_SECRET",
            "mode": "required_external",
            "status": "operator_configured",
        }
    ]
    assert "test-web-preview-invite-secret" not in str(plan)


def test_http_cloudflare_client_uses_expected_paths_and_tokens(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_request(method: str, url: str, **kwargs: Any) -> httpx.Response:
        calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(kwargs.get("headers") or {}),
                "json": kwargs.get("json"),
            },
        )
        return httpx.Response(
            200,
            request=httpx.Request(method, url),
            json={"success": True, "result": []},
        )

    monkeypatch.setattr(httpx, "request", fake_request)
    client = HttpCloudflareClient(
        api_token="platform-token",
        dns_api_token="dns-token",
        base_url="https://api.cloudflare.test/client/v4",
        timeout_seconds=1,
    )

    client.list_dns_records(zone_id="zone-1", name="preview.nienfos.com")
    client.create_dns_record(
        zone_id="zone-1",
        payload={"type": "CNAME", "name": "preview.nienfos.com"},
    )
    client.update_dns_record(
        zone_id="zone-1",
        record_id="record-1",
        payload={"proxied": True},
    )
    client.get_worker_script(account_id="acct-1", script_name="preview-worker")
    client.deploy_worker_script(
        account_id="acct-1",
        script_name="preview-worker",
        script_content="export default {};",
    )
    client.list_d1_databases("acct-1")
    client.create_d1_database(account_id="acct-1", name="preview-d1")
    client.execute_d1_sql(
        account_id="acct-1",
        database_id="d1-1",
        sql="SELECT 1",
    )
    client.get_pages_project(account_id="acct-1", project_name="preview-pages")
    client.create_pages_project(account_id="acct-1", name="preview-pages")

    assert calls[0]["url"].endswith(
        "/zones/zone-1/dns_records?name=preview.nienfos.com",
    )
    assert calls[0]["headers"]["Authorization"] == "Bearer dns-token"
    assert calls[1]["method"] == "POST"
    assert calls[1]["headers"]["Authorization"] == "Bearer dns-token"
    assert calls[2]["method"] == "PATCH"
    assert calls[2]["url"].endswith("/zones/zone-1/dns_records/record-1")
    assert calls[3]["url"].endswith(
        "/accounts/acct-1/workers/scripts/preview-worker",
    )
    assert calls[3]["headers"]["Authorization"] == "Bearer platform-token"
    assert calls[4]["method"] == "PUT"
    assert calls[4]["url"].endswith(
        "/accounts/acct-1/workers/scripts/preview-worker",
    )
    assert calls[4]["headers"]["Content-Type"] == "application/javascript"
    assert calls[5]["url"].endswith("/accounts/acct-1/d1/database")
    assert calls[6]["method"] == "POST"
    assert calls[6]["url"].endswith("/accounts/acct-1/d1/database")
    assert calls[6]["json"] == {"name": "preview-d1"}
    assert calls[7]["method"] == "POST"
    assert calls[7]["url"].endswith("/accounts/acct-1/d1/database/d1-1/query")
    assert calls[7]["json"] == {"sql": "SELECT 1", "params": []}
    assert calls[8]["url"].endswith("/accounts/acct-1/pages/projects/preview-pages")
    assert calls[9]["method"] == "POST"
    assert calls[9]["url"].endswith("/accounts/acct-1/pages/projects")


def _configured_settings() -> Settings:
    return Settings(
        cloudflare_api_token="platform-token",
        cloudflare_dns_api_token="dns-token",
        cloudflare_account_id="acct-1",
        cloudflare_zone_id="zone-1",
        cloudflare_zone_name="nienfos.com",
        preview_base_domain="preview.nienfos.com",
        preview_worker_name="nienfos-preview-runtime",
        preview_d1_database_name="nienfos-preview",
        preview_pages_project_name="nienfos-preview-web",
        preview_r2_bucket_name=None,
    )


class _FakeCloudflareClient:
    def __init__(
        self,
        *,
        dns_records: list[dict[str, Any]] | None = None,
        r2_result: CloudflareLookupResult | None = None,
    ) -> None:
        self.calls: list[str] = []
        self._dns_records = dns_records or []
        self._r2_result = r2_result or CloudflareLookupResult(
            ok=True,
            payload={"result": []},
        )

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
        return CloudflareLookupResult(ok=True, payload={"result": self._dns_records})

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
        return CloudflareLookupResult(ok=True, payload={"result": {"id": script_name}})

    def deploy_worker_script(
        self,
        *,
        account_id: str,
        script_name: str,
        script_content: str,
    ) -> CloudflareLookupResult:
        self.calls.append(f"deploy_worker_script:{account_id}:{script_name}")
        return CloudflareLookupResult(
            ok=True,
            payload={"result": {"id": script_name, "size": len(script_content)}},
        )

    def list_d1_databases(self, account_id: str) -> CloudflareLookupResult:
        self.calls.append(f"list_d1_databases:{account_id}")
        return CloudflareLookupResult(ok=True, payload={"result": []})

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
            payload={"result": [{"success": True, "sql": sql, "params": params or []}]},
        )

    def get_pages_project(
        self,
        *,
        account_id: str,
        project_name: str,
    ) -> CloudflareLookupResult:
        self.calls.append(f"get_pages_project:{account_id}:{project_name}")
        return CloudflareLookupResult(ok=True, payload={"result": {"name": project_name}})

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
        return self._r2_result
