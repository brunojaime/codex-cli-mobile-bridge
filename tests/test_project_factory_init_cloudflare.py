from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Callable

from backend.app.application.services.cloudflare_preview_service import (
    CloudflareLookupResult,
)
from backend.app.application.services.project_factory_generator_service import (
    ProjectFactoryGeneratorService,
)
from backend.app.application.services.project_factory_init_service import (
    ProjectFactoryInitCommandResult,
    ProjectFactoryInitService,
)
from backend.app.application.services.project_factory_manifest_service import (
    ProjectFactoryManifestInput,
    ProjectFactoryManifestService,
)
from backend.app.domain.entities.project_factory_init import (
    ProjectFactoryInitPhaseName,
    ProjectFactoryInitPhaseStatus,
    ProjectFactoryInitRemoteResourceType,
)
from backend.app.infrastructure.config.settings import Settings


@dataclass(frozen=True, slots=True)
class _FakeCommand:
    exit_code: int = 0
    stdout: str = "wrangler 3.0.0\n"
    stderr: str = ""


class _FakeRunner:
    def __init__(
        self,
        response: _FakeCommand = _FakeCommand(),
        *,
        on_run: Callable[
            [tuple[str, ...], str | Path | None, dict[str, str] | None],
            ProjectFactoryInitCommandResult | None,
        ]
        | None = None,
    ) -> None:
        self.response = response
        self.on_run = on_run
        self.calls: list[tuple[str, ...]] = []

    def run(
        self,
        argv: tuple[str, ...],
        *,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: float = 0,
    ) -> ProjectFactoryInitCommandResult:
        del timeout_seconds
        self.calls.append(argv)
        if self.on_run is not None:
            result = self.on_run(argv, cwd, env)
            if result is not None:
                return result
        return ProjectFactoryInitCommandResult(
            argv=argv,
            cwd=str(cwd) if cwd is not None else None,
            exit_code=self.response.exit_code,
            stdout=self.response.stdout,
            stderr=self.response.stderr,
            env=env,
        )


class _OkDoctor:
    def doctor(self) -> dict[str, Any]:
        return {
            "kind": "codex.webPreviewDoctor",
            "version": 1,
            "ok": True,
            "status": "ready",
            "checks": [],
            "planner": {},
        }


def test_cloudflare_init_blocks_missing_config_without_wrangler(
    tmp_path: Path,
) -> None:
    runner = _FakeRunner()
    service = ProjectFactoryInitService(
        state_root=tmp_path / "state",
        command_runner=runner,
        settings=_settings(tmp_path, configured=False),
        cloudflare_client=_FakeCloudflareClient(),
    )
    project = _generated_project(tmp_path)
    job = _job(service, project)

    blocked = service.run_cloudflare_preview_phases(job.id)

    phase = blocked.phase(ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_PROVISION)
    assert phase.status == ProjectFactoryInitPhaseStatus.BLOCKED
    assert phase.blockers[0].code == "cloudflare_cloudflare_platform_token_configured"
    assert phase.blockers[0].command == ("export", "CLOUDFLARE_API_TOKEN=<token>")
    assert runner.calls == []
    assert "secret-token" not in json.dumps(blocked.to_payload())


def test_cloudflare_init_blocks_missing_wrangler_after_doctor_success(
    tmp_path: Path,
) -> None:
    service = _service(
        tmp_path,
        runner=_FakeRunner(_FakeCommand(exit_code=127, stderr="not found")),
        cloudflare_client=_FakeCloudflareClient(resources_exist=True),
    )
    project = _generated_project(tmp_path)
    job = _job(service, project)

    blocked = service.run_cloudflare_preview_phases(job.id)

    phase = blocked.phase(ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_PROVISION)
    assert phase.status == ProjectFactoryInitPhaseStatus.BLOCKED
    assert phase.blockers[0].code == "cloudflare_wrangler_missing"
    assert phase.blockers[0].command == ("wrangler", "--version")


def test_cloudflare_init_existing_resources_urls_deploy_and_smoke_success(
    tmp_path: Path,
) -> None:
    fake = _FakeCloudflareClient(resources_exist=True)
    service = _service(tmp_path, cloudflare_client=fake)
    project = _generated_project(tmp_path)
    job = _job(service, project)

    completed = service.run_cloudflare_preview_phases(job.id)

    assert completed.phase(
        ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_PROVISION
    ).status == ProjectFactoryInitPhaseStatus.COMPLETED
    assert completed.phase(
        ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_DEPLOY
    ).status == ProjectFactoryInitPhaseStatus.COMPLETED
    smoke = completed.phase(ProjectFactoryInitPhaseName.PREVIEW_SMOKE)
    assert smoke.status == ProjectFactoryInitPhaseStatus.COMPLETED
    preview = _resource(completed, ProjectFactoryInitRemoteResourceType.PREVIEW_URL)
    api = _resource(completed, ProjectFactoryInitRemoteResourceType.API_BASE_URL)
    worker = _resource(
        completed,
        ProjectFactoryInitRemoteResourceType.CLOUDFLARE_WORKER,
    )
    route = _resource(
        completed,
        ProjectFactoryInitRemoteResourceType.CLOUDFLARE_ROUTE,
    )
    d1 = _resource(
        completed,
        ProjectFactoryInitRemoteResourceType.CLOUDFLARE_D1_DATABASE,
    )
    assert preview.url == "https://preview.nienfos.com/clinica-norte"
    assert api.url == "https://preview.nienfos.com/clinica-norte/api"
    assert worker.status == "updated"
    assert route.status == "existing"
    assert d1.status == "existing"
    metadata = fake.worker_metadata["nienfos-preview-runtime"]
    assert {"type": "d1", "name": "PREVIEW_DB", "id": "d1-1"} in metadata["bindings"]
    assert fake.calls.index("list_d1_databases:acct-1") < fake.calls.index(
        "deploy_worker_script:acct-1:nienfos-preview-runtime:module"
    )
    generated_wrangler = project / ".codex/factory/cloudflare/wrangler.toml"
    assert any(
        call == ("wrangler", "deploy", "--config", str(generated_wrangler))
        for call in service._command_runner.calls
    )
    assert 'binding = "ASSETS"' in generated_wrangler.read_text()
    assert any(call.startswith("fetch_url:https://preview.nienfos.com/clinica-norte") for call in fake.calls)
    smoke_artifact = smoke.artifacts[0]
    assert smoke_artifact.metadata["checks"][0]["status_code"] == 200
    assert smoke_artifact.metadata["checks"][0]["d1_bound"] is True
    assert smoke_artifact.metadata["checks"][0]["assets_bound"] is True


def test_cloudflare_init_retries_transient_preview_health_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "backend.app.application.services.web_preview_deploy_service.time.sleep",
        lambda _: None,
    )
    fake = _FakeCloudflareClient(
        resources_exist=True,
        transient_health_failures_per_url=4,
    )
    service = _service(tmp_path, cloudflare_client=fake)
    project = _generated_project(tmp_path)
    job = _job(service, project)

    completed = service.run_cloudflare_preview_phases(job.id)

    smoke = completed.phase(ProjectFactoryInitPhaseName.PREVIEW_SMOKE)
    assert smoke.status == ProjectFactoryInitPhaseStatus.COMPLETED
    assert len(smoke.artifacts[0].metadata["checks"]) == 2
    assert sum(call.startswith("fetch_url:") for call in fake.calls) == 10


def test_cloudflare_init_builds_web_preview_before_deploy(
    tmp_path: Path,
) -> None:
    project_ref: dict[str, Path] = {}

    def on_run(
        argv: tuple[str, ...],
        cwd: str | Path | None,
        env: dict[str, str] | None,
    ) -> ProjectFactoryInitCommandResult | None:
        if argv == ("bash", "scripts/build_web_preview.sh"):
            project = Path(cwd or project_ref["project"])
            _write_web_build_output(project)
            return ProjectFactoryInitCommandResult(
                argv=argv,
                cwd=str(cwd) if cwd is not None else None,
                exit_code=0,
                stdout="web preview build completed\n",
                env=env,
            )
        return None

    runner = _FakeRunner(on_run=on_run)
    service = _service(
        tmp_path,
        runner=runner,
        cloudflare_client=_FakeCloudflareClient(resources_exist=True),
    )
    project = _generated_project(tmp_path, write_build_output=False)
    project_ref["project"] = project
    job = _job(service, project)

    completed = service.run_cloudflare_preview_phases(job.id)

    assert ("wrangler", "--version") in runner.calls
    assert ("bash", "scripts/build_web_preview.sh") in runner.calls
    assert completed.phase(
        ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_PROVISION
    ).status == ProjectFactoryInitPhaseStatus.COMPLETED
    provision = completed.phase(
        ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_PROVISION
    )
    evidence_argv = [item.argv for item in provision.command_evidence]
    assert ("bash", "scripts/build_web_preview.sh") in evidence_argv
    assert (
        project / "build/web-preview/clinica-norte/index.html"
    ).exists()


def test_cloudflare_init_resets_blocked_phase_for_retry(
    tmp_path: Path,
) -> None:
    build_attempts = 0

    def on_run(
        argv: tuple[str, ...],
        cwd: str | Path | None,
        env: dict[str, str] | None,
    ) -> ProjectFactoryInitCommandResult | None:
        nonlocal build_attempts
        if argv != ("bash", "scripts/build_web_preview.sh"):
            return None
        build_attempts += 1
        if build_attempts == 1:
            return ProjectFactoryInitCommandResult(
                argv=argv,
                cwd=str(cwd) if cwd is not None else None,
                exit_code=1,
                stderr="flutter build failed\n",
                env=env,
            )
        project = Path(cwd or "")
        _write_web_build_output(project)
        return ProjectFactoryInitCommandResult(
            argv=argv,
            cwd=str(cwd) if cwd is not None else None,
            exit_code=0,
            stdout="web preview build completed\n",
            env=env,
        )

    service = _service(
        tmp_path,
        runner=_FakeRunner(on_run=on_run),
        cloudflare_client=_FakeCloudflareClient(resources_exist=True),
    )
    project = _generated_project(tmp_path, write_build_output=False)
    job = _job(service, project)

    blocked = service.run_cloudflare_preview_phases(job.id)

    blocked_phase = blocked.phase(
        ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_PROVISION
    )
    assert blocked_phase.status == ProjectFactoryInitPhaseStatus.BLOCKED
    assert blocked_phase.blockers[0].code == "cloudflare_web_preview_build_failed"

    service._reset_blocked_phase_for_retry(job.id)
    completed = service.run_cloudflare_preview_phases(job.id)

    assert build_attempts == 2
    assert completed.phase(
        ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_PROVISION
    ).status == ProjectFactoryInitPhaseStatus.COMPLETED


def test_cloudflare_init_create_path_and_d1_migrations_are_persisted(
    tmp_path: Path,
) -> None:
    fake = _FakeCloudflareClient(resources_exist=False)
    service = _service(
        tmp_path,
        cloudflare_client=fake,
        doctor_service=_OkDoctor(),
    )
    project = _generated_project(tmp_path)
    job = _job(service, project)

    completed = service.run_cloudflare_preview_phases(job.id)

    assert "create_dns_record:zone-1" in fake.calls
    assert "create_worker_route:zone-1:preview.nienfos.com/clinica-norte/*" in fake.calls
    assert "create_d1_database:acct-1:nienfos-preview" in fake.calls
    assert "create_pages_project:acct-1:nienfos-preview-web" in fake.calls
    assert any(call.startswith("execute_d1_sql:acct-1:d1-1") for call in fake.calls)
    provision = completed.phase(
        ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_PROVISION
    )
    migrations = [
        artifact
        for artifact in provision.artifacts
        if artifact.kind == "cloudflare_d1_migration"
    ]
    assert migrations
    assert _resource(
        completed,
        ProjectFactoryInitRemoteResourceType.CLOUDFLARE_D1_DATABASE,
    ).metadata["database_id"] == "d1-1"


def test_cloudflare_init_blocks_worker_route_d1_and_smoke_failures(
    tmp_path: Path,
) -> None:
    cases = [
        (
            _FakeCloudflareClient(resources_exist=True, fail_worker=True),
            "cloudflare_worker_blocked",
            ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_PROVISION,
        ),
        (
            _FakeCloudflareClient(resources_exist=True, fail_route=True),
            "cloudflare_route_blocked",
            ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_PROVISION,
        ),
        (
            _FakeCloudflareClient(resources_exist=True, fail_d1=True),
            "cloudflare_d1_blocked",
            ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_PROVISION,
        ),
        (
            _FakeCloudflareClient(resources_exist=True, health_assets_bound=False),
            "cloudflare_smoke_blocked",
            ProjectFactoryInitPhaseName.PREVIEW_SMOKE,
        ),
    ]
    for index, (fake, expected_code, expected_phase) in enumerate(cases):
        case_root = tmp_path / f"case-{index}"
        service = _service(
            case_root,
            cloudflare_client=fake,
            doctor_service=_OkDoctor()
            if expected_code in {"cloudflare_route_blocked", "cloudflare_d1_blocked"}
            else None,
        )
        project = _generated_project(case_root)
        job = _job(service, project)

        blocked = service.run_cloudflare_preview_phases(job.id)

        phase = blocked.phase(expected_phase)
        assert phase.status == ProjectFactoryInitPhaseStatus.BLOCKED
        assert phase.blockers[0].code == expected_code
        assert phase.blockers[0].command
        if expected_phase == ProjectFactoryInitPhaseName.PREVIEW_SMOKE:
            assert blocked.phase(
                ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_PROVISION
            ).status == ProjectFactoryInitPhaseStatus.COMPLETED
            assert blocked.phase(
                ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_DEPLOY
            ).status == ProjectFactoryInitPhaseStatus.COMPLETED


def test_cloudflare_init_persists_after_reload_and_redacts_secrets(
    tmp_path: Path,
) -> None:
    fake = _FakeCloudflareClient(resources_exist=True, fail_worker=True)
    service = _service(tmp_path, cloudflare_client=fake)
    project = _generated_project(tmp_path)
    job = _job(service, project)

    blocked = service.run_cloudflare_preview_phases(job.id)

    payload = json.dumps(blocked.to_payload())
    assert "secret-token" not in payload
    phase = blocked.phase(ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_PROVISION)
    assert "secret-token" not in phase.blockers[0].message
    assert all("secret-token" not in item.stdout_summary for item in phase.command_evidence)

    reloaded = ProjectFactoryInitService(
        state_root=tmp_path / "state",
        settings=_settings(tmp_path),
    )
    persisted = reloaded.get_job(job.id)
    assert persisted is not None
    persisted_phase = persisted.phase(
        ProjectFactoryInitPhaseName.CLOUDFLARE_PREVIEW_PROVISION
    )
    assert persisted_phase.blockers[0].code == "cloudflare_worker_blocked"
    assert _resource(persisted, ProjectFactoryInitRemoteResourceType.PREVIEW_URL).url == (
        "https://preview.nienfos.com/clinica-norte"
    )


def _service(
    tmp_path: Path,
    *,
    runner: _FakeRunner | None = None,
    cloudflare_client: "_FakeCloudflareClient | None" = None,
    doctor_service: _OkDoctor | None = None,
) -> ProjectFactoryInitService:
    fake = cloudflare_client or _FakeCloudflareClient(resources_exist=True)
    return ProjectFactoryInitService(
        state_root=tmp_path / "state",
        command_runner=runner or _FakeRunner(),
        settings=_settings(tmp_path),
        cloudflare_client=fake,
        cloudflare_doctor_service=doctor_service,
    )


def _job(service: ProjectFactoryInitService, project: Path):
    return service.start_or_resume(
        draft_id="draft-1",
        project_name="Clinica Norte",
        slug="clinica-norte",
        workspace_path=str(project),
    )


def _generated_project(tmp_path: Path, *, write_build_output: bool = True) -> Path:
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
    project = projects_root / "clinica-norte"
    if write_build_output:
        _write_web_build_output(project)
    return project


def _write_web_build_output(project: Path) -> None:
    build_dir = project / "build/web-preview/clinica-norte"
    assets_dir = build_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / "index.html").write_text("<!doctype html><title>Preview</title>\n")
    (build_dir / "manifest.json").write_text("{}\n")
    (build_dir / "flutter_bootstrap.js").write_text("void 0;\n")
    (assets_dir / "AssetManifest.bin").write_bytes(b"assets")


def _settings(tmp_path: Path, *, configured: bool = True) -> Settings:
    token = "secret-token" if configured else None
    return Settings(
        projects_root=str(tmp_path / "projects"),
        project_factory_state_dir=str(tmp_path / "state/project_factory"),
        web_preview_state_dir=str(tmp_path / "state/web_preview"),
        web_preview_apply_enabled=True,
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


def _resource(job, resource_type: ProjectFactoryInitRemoteResourceType):
    for resource in job.remote_resources:
        if resource.type == resource_type:
            return resource
    raise AssertionError(f"Missing resource: {resource_type.value}")


class _FakeCloudflareClient:
    def __init__(
        self,
        *,
        resources_exist: bool = True,
        fail_worker: bool = False,
        fail_route: bool = False,
        fail_d1: bool = False,
        health_d1_bound: bool = True,
        health_assets_bound: bool = True,
        transient_health_failures_per_url: int = 0,
    ) -> None:
        self.calls: list[str] = []
        self.sql_calls: list[dict[str, Any]] = []
        self.resources_exist = resources_exist
        self.fail_worker = fail_worker
        self.fail_route = fail_route
        self.fail_d1 = fail_d1
        self.health_d1_bound = health_d1_bound
        self.health_assets_bound = health_assets_bound
        self.transient_health_failures_per_url = transient_health_failures_per_url
        self.health_fetch_counts: dict[str, int] = {}
        self.worker_scripts: dict[str, str] = {}
        self.worker_metadata: dict[str, dict[str, Any]] = {}
        self.d1_columns: dict[str, set[str]] = {
            "preview_invites": {
                "invite_id",
                "token_sha256",
                "source_app",
                "app_slug",
                "single_use",
                "created_at",
                "expires_at",
                "used_at",
                "revoked_at",
            },
            "preview_app_updates": {
                "source_app",
                "release_tag",
                "apk_url",
                "created_at",
            },
        }

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
        records = [
            {
                "id": "dns-1",
                "name": name,
                "type": record_type or "CNAME",
                "content": "nienfos.com",
                "proxied": True,
            }
        ] if self.resources_exist else []
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
        if script_name in self.worker_scripts:
            return CloudflareLookupResult(
                ok=True,
                payload={"raw": self.worker_scripts[script_name]},
            )
        if self.resources_exist:
            return CloudflareLookupResult(
                ok=True,
                payload={
                    "raw": "export default { async fetch() { return new Response('ok'); } };"
                },
            )
        return CloudflareLookupResult(ok=False, status_code=404, error="not found")

    def deploy_worker_script(
        self,
        *,
        account_id: str,
        script_name: str,
        script_content: str,
        worker_format: str = "module",
        metadata: dict[str, Any] | None = None,
    ) -> CloudflareLookupResult:
        self.calls.append(
            f"deploy_worker_script:{account_id}:{script_name}:{worker_format}"
        )
        self.worker_metadata[script_name] = metadata or {}
        if self.fail_worker:
            return CloudflareLookupResult(
                ok=False,
                status_code=500,
                error="Bearer secret-token worker deploy failed",
            )
        self.worker_scripts[script_name] = script_content
        return CloudflareLookupResult(ok=True, payload={"result": {"id": script_name}})

    def list_worker_routes(
        self,
        *,
        zone_id: str,
        pattern: str,
    ) -> CloudflareLookupResult:
        self.calls.append(f"list_worker_routes:{zone_id}:{pattern}")
        if self.fail_route:
            return CloudflareLookupResult(
                ok=False,
                status_code=403,
                error="route permission denied",
            )
        routes = [
            {
                "id": "route-1",
                "pattern": pattern,
                "script": "nienfos-preview-runtime",
            }
        ] if self.resources_exist else []
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

    def list_d1_databases(self, account_id: str) -> CloudflareLookupResult:
        self.calls.append(f"list_d1_databases:{account_id}")
        if self.fail_d1:
            return CloudflareLookupResult(
                ok=False,
                status_code=403,
                error="D1 permission denied",
            )
        databases = [{"name": "nienfos-preview", "uuid": "d1-1"}] if self.resources_exist else []
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
        pragma = re.fullmatch(r"\s*PRAGMA\s+table_info\(([^)]+)\)\s*", sql, re.I)
        if pragma:
            table = pragma.group(1)
            return CloudflareLookupResult(
                ok=True,
                payload={
                    "result": [
                        {"name": column}
                        for column in sorted(self.d1_columns.get(table, set()))
                    ]
                },
            )
        alter = re.fullmatch(
            r"\s*ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)\s+.+",
            sql,
            re.I | re.S,
        )
        if alter:
            table, column = alter.groups()
            self.d1_columns.setdefault(table, set()).add(column)
        return CloudflareLookupResult(ok=True, payload={"result": [{"success": True}]})

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

    def fetch_url(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> CloudflareLookupResult:
        self.calls.append(f"fetch_url:{url}")
        assert headers and headers["User-Agent"] == "CodexProjectFactoryPreviewSmoke/1.0"
        self.health_fetch_counts[url] = self.health_fetch_counts.get(url, 0) + 1
        if self.health_fetch_counts[url] <= self.transient_health_failures_per_url:
            return CloudflareLookupResult(
                ok=False,
                status_code=401,
                error="Unauthorized",
            )
        return CloudflareLookupResult(
            ok=True,
            status_code=200,
            payload={
                "ok": True,
                "d1_bound": self.health_d1_bound,
                "assets_bound": self.health_assets_bound,
            },
        )
