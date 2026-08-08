from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

from fastapi.testclient import TestClient
import httpx
import pytest
import yaml

from backend.app.application.services.project_scaffold_service import (
    ProjectScaffoldService,
    ScaffoldDraftInput,
)
from backend.app.domain.entities.project_scaffold import CloudflareMode


def _generate(tmp_path: Path, preset: str) -> Path:
    projects = tmp_path / "projects"
    projects.mkdir(exist_ok=True)
    service = ProjectScaffoldService(
        projects_root=projects,
        state_root=tmp_path / f"state-{preset}",
        execute_commands=False,
        allow_remote_writes=False,
    )
    draft = service.create_draft(
        ScaffoldDraftInput(
            name=f"Contract {preset}",
            stack_preset=preset,
            github_mode="disabled",
            cloudflare_mode=CloudflareMode.DISABLED,
        )
    )
    service.confirm_draft(draft.id, draft.contract_hash)
    job = service.run(service.start_or_resume(draft.id).id)
    return Path(job.workspace_path)


def _assert_contract(response_get) -> None:
    correlation = {"x-correlation-id": "black-box-id"}
    health = response_get("/health", headers=correlation)
    assert health.status_code == 200
    assert health.headers["x-correlation-id"] == "black-box-id"
    assert set(health.json()) == {"status", "source_app", "version"}
    assert health.json()["status"] == "ok"
    version = response_get("/version", headers=correlation)
    assert version.status_code == 200
    assert version.headers["x-correlation-id"] == "black-box-id"
    assert set(version.json()) == {"source_app", "version"}
    missing = response_get("/missing", headers=correlation)
    assert missing.status_code == 404
    assert missing.headers["x-correlation-id"] == "black-box-id"
    assert missing.json() == {
        "error": {
            "code": "not_found",
            "message": "Route not found",
            "correlation_id": "black-box-id",
        }
    }


def test_fastapi_provider_passes_shared_black_box_contract(tmp_path: Path) -> None:
    workspace = _generate(tmp_path, "expo-sveltekit-fastapi")
    api_root = workspace / "services/api"
    spec = importlib.util.spec_from_file_location(
        "generated_scaffold_api", api_root / "app/main.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(api_root))
    try:
        spec.loader.exec_module(module)
        _assert_contract(TestClient(module.app).get)
    finally:
        sys.path.remove(str(api_root))


def test_go_provider_has_real_server_tests_and_openapi_parity(tmp_path: Path) -> None:
    workspace = _generate(tmp_path, "expo-sveltekit-go")
    api_root = workspace / "services/api"
    server = (api_root / "internal/server/server.go").read_text(encoding="utf-8")
    tests = (api_root / "internal/server/server_test.go").read_text(encoding="utf-8")
    contract = yaml.safe_load(
        (workspace / "contracts/openapi.yaml").read_text(encoding="utf-8")
    )

    assert set(contract["paths"]) == {"/health", "/version"}
    assert {"Health", "Version", "Error"}.issubset(contract["components"]["schemas"])
    assert "func New() http.Handler" in server
    assert 'case "/health"' in server and 'case "/version"' in server
    assert '"not_found", "Route not found"' in server
    assert "server.New().ServeHTTP" in tests
    assert "fastapi" not in server.lower()

    go_binary = os.environ.get("GO_BINARY") or shutil.which("go")
    if go_binary is None:
        pytest.skip("Go toolchain is not installed on this validation host.")
    completed = subprocess.run(
        (go_binary, "test", "./..."),
        cwd=api_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    binary = tmp_path / "scaffold-api"
    built = subprocess.run(
        (go_binary, "build", "-trimpath", "-o", str(binary), "./cmd/server"),
        cwd=api_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert built.returncode == 0, built.stdout + built.stderr
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    process = subprocess.Popen(
        (str(binary),),
        cwd=api_root,
        env={**os.environ, "PORT": str(port)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        base_url = f"http://127.0.0.1:{port}"
        for _ in range(50):
            try:
                if httpx.get(f"{base_url}/health", timeout=0.2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.05)
        else:
            raise AssertionError("Generated Go API did not become healthy")
        _assert_contract(
            lambda path, headers: httpx.get(
                f"{base_url}{path}",
                headers=headers,
                timeout=2,
            )
        )
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_generated_types_cover_health_version_and_errors(tmp_path: Path) -> None:
    workspace = _generate(tmp_path, "expo-sveltekit-fastapi")
    client = (workspace / "contracts/generated/api.ts").read_text(encoding="utf-8")
    assert "export type Health" in client
    assert "export type Version" in client
    assert "export type ApiError" in client
    assert "export const getHealth" in client
    assert "export const getVersion" in client
    assert "from 'react'" not in client
    assert "from 'svelte'" not in client
