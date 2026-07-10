from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Literal, Protocol
from urllib.parse import urlencode

import httpx

from backend.app.infrastructure.config.settings import Settings


@dataclass(frozen=True, slots=True)
class CloudflareLookupResult:
    ok: bool
    status_code: int | None = None
    payload: dict[str, Any] | list[Any] | None = None
    error: str | None = None


class CloudflareClient(Protocol):
    def get_account(self, account_id: str) -> CloudflareLookupResult:
        ...

    def get_zone(self, zone_id: str) -> CloudflareLookupResult:
        ...

    def list_dns_records(
        self,
        *,
        zone_id: str,
        name: str,
        record_type: str | None = None,
    ) -> CloudflareLookupResult:
        ...

    def create_dns_record(
        self,
        *,
        zone_id: str,
        payload: dict[str, Any],
    ) -> CloudflareLookupResult:
        ...

    def update_dns_record(
        self,
        *,
        zone_id: str,
        record_id: str,
        payload: dict[str, Any],
    ) -> CloudflareLookupResult:
        ...

    def list_worker_scripts(self, account_id: str) -> CloudflareLookupResult:
        ...

    def get_worker_script(
        self,
        *,
        account_id: str,
        script_name: str,
    ) -> CloudflareLookupResult:
        ...

    def deploy_worker_script(
        self,
        *,
        account_id: str,
        script_name: str,
        script_content: str,
        worker_format: Literal["classic", "module"] = "module",
    ) -> CloudflareLookupResult:
        ...

    def list_worker_routes(
        self,
        *,
        zone_id: str,
        pattern: str,
    ) -> CloudflareLookupResult:
        ...

    def create_worker_route(
        self,
        *,
        zone_id: str,
        payload: dict[str, Any],
    ) -> CloudflareLookupResult:
        ...

    def update_worker_route(
        self,
        *,
        zone_id: str,
        route_id: str,
        payload: dict[str, Any],
    ) -> CloudflareLookupResult:
        ...

    def list_d1_databases(self, account_id: str) -> CloudflareLookupResult:
        ...

    def create_d1_database(
        self,
        *,
        account_id: str,
        name: str,
    ) -> CloudflareLookupResult:
        ...

    def execute_d1_sql(
        self,
        *,
        account_id: str,
        database_id: str,
        sql: str,
        params: list[Any] | None = None,
    ) -> CloudflareLookupResult:
        ...

    def get_pages_project(
        self,
        *,
        account_id: str,
        project_name: str,
    ) -> CloudflareLookupResult:
        ...

    def create_pages_project(
        self,
        *,
        account_id: str,
        name: str,
        production_branch: str = "main",
    ) -> CloudflareLookupResult:
        ...

    def list_r2_buckets(self, account_id: str) -> CloudflareLookupResult:
        ...


class HttpCloudflareClient:
    def __init__(
        self,
        *,
        api_token: str,
        dns_api_token: str | None,
        base_url: str = "https://api.cloudflare.com/client/v4",
        timeout_seconds: float = 10.0,
    ) -> None:
        self._api_token = api_token
        self._dns_api_token = dns_api_token or api_token
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def get_account(self, account_id: str) -> CloudflareLookupResult:
        return self._request("GET", f"/accounts/{account_id}")

    def get_zone(self, zone_id: str) -> CloudflareLookupResult:
        return self._request("GET", f"/zones/{zone_id}", use_dns_token=True)

    def list_dns_records(
        self,
        *,
        zone_id: str,
        name: str,
        record_type: str | None = None,
    ) -> CloudflareLookupResult:
        query: dict[str, str] = {"name": name}
        if record_type:
            query["type"] = record_type
        return self._request(
            "GET",
            f"/zones/{zone_id}/dns_records?{urlencode(query)}",
            use_dns_token=True,
        )

    def create_dns_record(
        self,
        *,
        zone_id: str,
        payload: dict[str, Any],
    ) -> CloudflareLookupResult:
        return self._request(
            "POST",
            f"/zones/{zone_id}/dns_records",
            json=payload,
            use_dns_token=True,
        )

    def update_dns_record(
        self,
        *,
        zone_id: str,
        record_id: str,
        payload: dict[str, Any],
    ) -> CloudflareLookupResult:
        return self._request(
            "PATCH",
            f"/zones/{zone_id}/dns_records/{record_id}",
            json=payload,
            use_dns_token=True,
        )

    def list_worker_routes(
        self,
        *,
        zone_id: str,
        pattern: str,
    ) -> CloudflareLookupResult:
        return self._request(
            "GET",
            f"/zones/{zone_id}/workers/routes?{urlencode({'pattern': pattern})}",
        )

    def create_worker_route(
        self,
        *,
        zone_id: str,
        payload: dict[str, Any],
    ) -> CloudflareLookupResult:
        return self._request(
            "POST",
            f"/zones/{zone_id}/workers/routes",
            json=payload,
        )

    def update_worker_route(
        self,
        *,
        zone_id: str,
        route_id: str,
        payload: dict[str, Any],
    ) -> CloudflareLookupResult:
        return self._request(
            "PUT",
            f"/zones/{zone_id}/workers/routes/{route_id}",
            json=payload,
        )

    def list_worker_scripts(self, account_id: str) -> CloudflareLookupResult:
        return self._request("GET", f"/accounts/{account_id}/workers/scripts")

    def get_worker_script(
        self,
        *,
        account_id: str,
        script_name: str,
    ) -> CloudflareLookupResult:
        return self._request(
            "GET",
            f"/accounts/{account_id}/workers/scripts/{script_name}",
        )

    def deploy_worker_script(
        self,
        *,
        account_id: str,
        script_name: str,
        script_content: str,
        worker_format: Literal["classic", "module"] = "module",
    ) -> CloudflareLookupResult:
        if worker_format == "module":
            return self._request(
                "PUT",
                f"/accounts/{account_id}/workers/scripts/{script_name}",
                files={
                    "metadata": (
                        None,
                        json.dumps({"main_module": "index.js"}),
                        "application/json",
                    ),
                    "index.js": (
                        "index.js",
                        script_content.encode("utf-8"),
                        "application/javascript+module",
                    ),
                },
            )
        if worker_format != "classic":
            return CloudflareLookupResult(
                ok=False,
                error=f"Unsupported Worker format: {worker_format}",
            )
        return self._request(
            "PUT",
            f"/accounts/{account_id}/workers/scripts/{script_name}",
            content=script_content.encode("utf-8"),
            content_type="application/javascript",
        )

    def list_d1_databases(self, account_id: str) -> CloudflareLookupResult:
        return self._request("GET", f"/accounts/{account_id}/d1/database")

    def create_d1_database(
        self,
        *,
        account_id: str,
        name: str,
    ) -> CloudflareLookupResult:
        return self._request(
            "POST",
            f"/accounts/{account_id}/d1/database",
            json={"name": name},
        )

    def execute_d1_sql(
        self,
        *,
        account_id: str,
        database_id: str,
        sql: str,
        params: list[Any] | None = None,
    ) -> CloudflareLookupResult:
        return self._request(
            "POST",
            f"/accounts/{account_id}/d1/database/{database_id}/query",
            json={"sql": sql, "params": params or []},
        )

    def get_pages_project(
        self,
        *,
        account_id: str,
        project_name: str,
    ) -> CloudflareLookupResult:
        return self._request(
            "GET",
            f"/accounts/{account_id}/pages/projects/{project_name}",
        )

    def create_pages_project(
        self,
        *,
        account_id: str,
        name: str,
        production_branch: str = "main",
    ) -> CloudflareLookupResult:
        return self._request(
            "POST",
            f"/accounts/{account_id}/pages/projects",
            json={
                "name": name,
                "production_branch": production_branch,
            },
        )

    def list_r2_buckets(self, account_id: str) -> CloudflareLookupResult:
        return self._request("GET", f"/accounts/{account_id}/r2/buckets")

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        content: bytes | None = None,
        content_type: str = "application/json",
        files: dict[str, tuple[str | None, bytes | str, str]] | None = None,
        use_dns_token: bool = False,
    ) -> CloudflareLookupResult:
        token = self._dns_api_token if use_dns_token else self._api_token
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        if files is None:
            headers["Content-Type"] = content_type
        try:
            response = httpx.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                json=json,
                content=content,
                files=files,
                timeout=self._timeout_seconds,
            )
        except httpx.HTTPError as exc:
            return CloudflareLookupResult(ok=False, error=str(exc))
        payload: dict[str, Any] | list[Any] | None
        try:
            parsed = response.json()
            payload = parsed if isinstance(parsed, (dict, list)) else None
        except ValueError:
            payload = {
                "raw": response.text,
                "content_type": response.headers.get("content-type"),
            }
        if response.status_code >= 400:
            return CloudflareLookupResult(
                ok=False,
                status_code=response.status_code,
                payload=payload,
                error=_cloudflare_error_message(payload) or response.reason_phrase,
            )
        success = bool(payload.get("success", True)) if isinstance(payload, dict) else True
        return CloudflareLookupResult(
            ok=success,
            status_code=response.status_code,
            payload=payload,
            error=None if success else _cloudflare_error_message(payload),
        )


class CloudflarePreviewDoctorService:
    def __init__(
        self,
        *,
        settings: Settings,
        client: CloudflareClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = client

    def doctor(self) -> dict[str, Any]:
        config_checks = self._configuration_checks()
        if not all(bool(check["ok"]) for check in config_checks):
            return {
                "kind": "codex.webPreviewDoctor",
                "version": 1,
                "ok": False,
                "status": "blocked_configuration",
                "provider": "cloudflare",
                "base_domain": self._settings.preview_base_domain,
                "zone_name": self._settings.cloudflare_zone_name,
                "checks": config_checks,
                "planner": CloudflareProvisioningPlanner(
                    settings=self._settings,
                ).plan(),
            }

        client = self._client or HttpCloudflareClient(
            api_token=self._settings.cloudflare_api_token or "",
            dns_api_token=self._settings.cloudflare_dns_api_token,
            base_url=self._settings.cloudflare_api_base_url,
            timeout_seconds=self._settings.cloudflare_timeout_seconds,
        )
        checks = [*config_checks]
        checks.append(
            _check_from_lookup(
                "cloudflare_account",
                client.get_account(self._settings.cloudflare_account_id or ""),
                "Cloudflare account must be readable.",
            ),
        )
        checks.append(
            _check_from_lookup(
                "cloudflare_zone",
                client.get_zone(self._settings.cloudflare_zone_id or ""),
                "Cloudflare zone must be readable.",
            ),
        )
        dns_records = client.list_dns_records(
            zone_id=self._settings.cloudflare_zone_id or "",
            name=self._settings.preview_base_domain,
            record_type="CNAME",
        )
        checks.append(
            _check_from_lookup(
                "preview_dns_access",
                dns_records,
                "Preview DNS records must be readable.",
            ),
        )
        checks.append(_dns_record_check(dns_records))
        checks.append(
            _check_from_lookup(
                "workers_access",
                client.list_worker_scripts(self._settings.cloudflare_account_id or ""),
                "Workers API must be readable.",
            ),
        )
        checks.append(
            _check_from_lookup(
                "preview_worker_script",
                client.get_worker_script(
                    account_id=self._settings.cloudflare_account_id or "",
                    script_name=self._settings.preview_worker_name,
                ),
                "Shared preview Worker script lookup.",
                ok_on_not_found=False,
            ),
        )
        checks.append(
            _check_from_lookup(
                "workers_routes_edit_access",
                client.list_worker_routes(
                    zone_id=self._settings.cloudflare_zone_id or "",
                    pattern=f"{self._settings.preview_base_domain}/*",
                ),
                "Workers Routes: Edit permission is required to create or update preview routes.",
            ),
        )
        checks.append(
            _check_from_lookup(
                "d1_access",
                client.list_d1_databases(self._settings.cloudflare_account_id or ""),
                "D1 database list must be readable.",
            ),
        )
        checks.append(
            _check_from_lookup(
                "pages_project",
                client.get_pages_project(
                    account_id=self._settings.cloudflare_account_id or "",
                    project_name=self._settings.preview_pages_project_name,
                ),
                "Cloudflare Pages project lookup.",
                ok_on_not_found=False,
            ),
        )
        checks.append(_r2_check(client.list_r2_buckets(self._settings.cloudflare_account_id or "")))
        required_codes = {
            "cloudflare_platform_token_configured",
            "cloudflare_dns_token_configured",
            "cloudflare_account_id_configured",
            "cloudflare_zone_id_configured",
            "cloudflare_zone_name_configured",
            "preview_base_domain_configured",
            "web_preview_apply_enabled",
            "cloudflare_account",
            "cloudflare_zone",
            "preview_dns_access",
            "preview_dns_record",
            "workers_access",
            "preview_worker_script",
            "workers_routes_edit_access",
            "d1_access",
            "pages_project",
        }
        ok = all(
            bool(check["ok"])
            for check in checks
            if str(check["code"]) in required_codes
        )
        return {
            "kind": "codex.webPreviewDoctor",
            "version": 1,
            "ok": ok,
            "status": "ready" if ok else "blocked",
            "provider": "cloudflare",
            "base_domain": self._settings.preview_base_domain,
            "zone_name": self._settings.cloudflare_zone_name,
            "checks": checks,
            "planner": CloudflareProvisioningPlanner(settings=self._settings).plan(),
        }

    def _configuration_checks(self) -> list[dict[str, Any]]:
        return [
            _check(
                "cloudflare_platform_token_configured",
                bool((self._settings.cloudflare_api_token or "").strip()),
                "CLOUDFLARE_API_TOKEN must be configured on the bridge host.",
            ),
            _check(
                "cloudflare_dns_token_configured",
                bool((self._settings.cloudflare_dns_api_token or "").strip()),
                "CLOUDFLARE_DNS_API_TOKEN must be configured on the bridge host.",
            ),
            _check(
                "cloudflare_account_id_configured",
                bool((self._settings.cloudflare_account_id or "").strip()),
                "CLOUDFLARE_ACCOUNT_ID must be configured.",
            ),
            _check(
                "cloudflare_zone_id_configured",
                bool((self._settings.cloudflare_zone_id or "").strip()),
                "CLOUDFLARE_ZONE_ID must be configured.",
            ),
            _check(
                "cloudflare_zone_name_configured",
                bool((self._settings.cloudflare_zone_name or "").strip()),
                "CLOUDFLARE_ZONE_NAME must be configured.",
            ),
            _check(
                "preview_base_domain_configured",
                bool((self._settings.preview_base_domain or "").strip()),
                "PREVIEW_BASE_DOMAIN must be configured.",
            ),
            _check(
                "web_preview_apply_enabled",
                bool(self._settings.web_preview_apply_enabled),
                "WEB_PREVIEW_APPLY_ENABLED must be true before Project Factory can create public previews.",
            ),
        ]


class CloudflareProvisioningPlanner:
    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings

    def plan(self) -> dict[str, Any]:
        return self._plan(
            base_domain=self._settings.preview_base_domain.strip(),
            worker_name=self._settings.preview_worker_name.strip(),
            d1_name=self._settings.preview_d1_database_name.strip(),
            pages_project=self._settings.preview_pages_project_name.strip(),
            r2_bucket=(self._settings.preview_r2_bucket_name or "").strip(),
            runtime_type="cloudflare_worker_assets",
            health_path="/api/health",
        )

    def plan_for_manifest(self, manifest: dict[str, Any]) -> dict[str, Any]:
        cloudflare = manifest.get("cloudflare")
        if not isinstance(cloudflare, dict):
            raise ValueError("web preview manifest must include cloudflare settings")
        resources = cloudflare.get("resources")
        if not isinstance(resources, dict):
            raise ValueError("web preview manifest must include cloudflare resources")
        runtime = manifest.get("runtime")
        runtime = runtime if isinstance(runtime, dict) else {}
        access = manifest.get("access")
        access = access if isinstance(access, dict) else {}
        d1_binding = str(access.get("d1_binding") or "")
        migrations_dir = str(access.get("migrations_dir") or "")
        return self._plan(
            base_domain=str(cloudflare.get("base_domain") or ""),
            worker_name=str(resources.get("worker_name") or ""),
            d1_name=str(resources.get("d1_database") or ""),
            pages_project=str(resources.get("pages_project") or ""),
            r2_bucket=str(resources.get("r2_bucket") or "")
            if resources.get("r2_bucket") is not None
            else "",
            runtime_type=str(runtime.get("type") or "cloudflare_worker_assets"),
            health_path=str(runtime.get("health_path") or "/api/health"),
            access_mode=str(access.get("mode") or "public"),
            required_worker_secrets=tuple(access.get("required_worker_secrets") or ()),
            d1_binding=d1_binding,
            migrations_dir=migrations_dir,
        )

    def _plan(
        self,
        *,
        base_domain: str,
        worker_name: str,
        d1_name: str,
        pages_project: str,
        r2_bucket: str,
        runtime_type: str,
        health_path: str,
        access_mode: str = "public",
        required_worker_secrets: tuple[str, ...] = (),
        d1_binding: str = "",
        migrations_dir: str = "",
    ) -> dict[str, Any]:
        resources = [
            {
                "kind": "dns_record",
                "name": base_domain,
                "record_type": "CNAME",
                "target": self._settings.cloudflare_zone_name,
                "mode": "read_or_create",
            },
            {
                "kind": "worker_script",
                "name": worker_name,
                "mode": "read_or_deploy",
            },
            {
                "kind": "worker_route",
                "name": f"{base_domain}/*",
                "script": worker_name,
                "mode": "read_or_create",
            },
            {
                "kind": "d1_database",
                "name": d1_name,
                "mode": "read_or_create",
            },
            {
                "kind": "pages_project",
                "name": pages_project,
                "mode": "read_or_create",
            },
        ]
        if r2_bucket:
            resources.append(
                {
                    "kind": "r2_bucket",
                    "name": r2_bucket,
                    "mode": "read_or_create_optional",
                },
            )
        else:
            resources.append(
                {
                    "kind": "r2_bucket",
                    "name": None,
                    "mode": "disabled_optional",
                    "status": "disabled",
                },
            )
        for secret_name in required_worker_secrets:
            resources.append(
                {
                    "kind": "worker_secret",
                    "name": secret_name,
                    "mode": "required_external",
                    "status": "operator_configured",
                },
            )
        if access_mode == "invite_token" and d1_binding and migrations_dir:
            resources.append(
                {
                    "kind": "d1_migration",
                    "name": migrations_dir,
                    "binding": d1_binding,
                    "database": d1_name,
                    "mode": "apply_from_project",
                    "status": "planned",
                },
            )
        return {
            "kind": "codex.webPreviewProvisioningPlan",
            "version": 1,
            "dry_run": True,
            "provider": "cloudflare",
            "base_domain": base_domain,
            "runtime_type": runtime_type,
            "health_path": health_path,
            "access_mode": access_mode,
            "required_worker_secrets": list(required_worker_secrets),
            "resources": resources,
            "side_effects": [],
        }


def _check(code: str, ok: bool, detail: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": code,
        "ok": ok,
        "detail": detail,
    }
    payload.update(extra)
    return payload


def _check_from_lookup(
    code: str,
    result: CloudflareLookupResult,
    detail: str,
    *,
    ok_on_not_found: bool = False,
) -> dict[str, Any]:
    not_found = result.status_code == 404
    ok = result.ok or (ok_on_not_found and not_found)
    return _check(
        code,
        ok,
        detail,
        status_code=result.status_code,
        error=result.error if not ok else None,
    )


def _dns_record_check(result: CloudflareLookupResult) -> dict[str, Any]:
    records = _cloudflare_result_list(result.payload)
    if not result.ok:
        return _check(
            "preview_dns_record",
            False,
            "Preview DNS record could not be verified.",
            status="unknown",
            record_count=0,
        )
    if not records:
        return _check(
            "preview_dns_record",
            False,
            "Preview DNS record is missing and must be planned before publish.",
            status="missing",
            record_count=0,
        )
    return _check(
        "preview_dns_record",
        True,
        "Preview DNS record exists.",
        status="present",
        record_count=len(records),
    )


def _r2_check(result: CloudflareLookupResult) -> dict[str, Any]:
    if result.ok:
        return _check(
            "r2_optional_access",
            True,
            "R2 access is available for optional persistent assets.",
            status="available",
        )
    return _check(
        "r2_optional_access",
        True,
        "R2 is optional for MVP previews; enable it before persistent preview assets.",
        status="disabled_or_blocked",
        status_code=result.status_code,
        error=result.error,
    )


def _cloudflare_result_list(payload: dict[str, Any] | list[Any] | None) -> list[Any]:
    if isinstance(payload, dict):
        result = payload.get("result")
        return result if isinstance(result, list) else []
    return payload if isinstance(payload, list) else []


def _cloudflare_error_message(
    payload: dict[str, Any] | list[Any] | None,
) -> str | None:
    if not isinstance(payload, dict):
        return None
    errors = payload.get("errors")
    if not isinstance(errors, list) or not errors:
        return None
    first = errors[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    return str(message) if message else None
