from __future__ import annotations

from pathlib import Path
import subprocess

from fastapi.testclient import TestClient
import pytest

from backend.app.api.routes import get_container
from backend.app.infrastructure.config.settings import Settings
from backend.app.main import create_app


def _client(
    tmp_path: Path,
    *,
    enabled: bool = True,
    execute_commands: bool = False,
) -> TestClient:
    settings = Settings(
        projects_root=str(tmp_path / "projects"),
        chat_store_backend="memory",
        audio_transcription_backend="disabled",
        speech_synthesis_backend="disabled",
        project_factory_reference_asset_dir=str(tmp_path / "assets"),
        project_factory_state_dir=str(tmp_path / "state"),
        project_factory_async_jobs=False,
        project_scaffold_enabled=enabled,
        project_scaffold_execute_commands=execute_commands,
        project_scaffold_remote_writes_enabled=False,
    )
    Path(settings.projects_root).mkdir(parents=True, exist_ok=True)
    return TestClient(create_app(settings))


def test_options_preserve_product_default_and_expose_scaffold_contract(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path, enabled=True)

    payload = client.get("/project-factory/options").json()

    assert payload["defaultCreationMode"] == "product"
    assert payload["scaffoldEnabled"] is True
    assert {item["id"] for item in payload["creationModes"]} == {
        "product",
        "scaffold",
    }
    assert payload["scaffold"]["d1_default"] is False
    assert payload["scaffold"]["terraform_apply"] is False
    assert payload["scaffold"]["publish_android"] is False
    assert isinstance(payload["scaffold"]["github_owner_inferred"], bool)
    assert payload["scaffold"]["github_owner_required"] is not payload["scaffold"][
        "github_owner_inferred"
    ]
    assert {item["id"] for item in payload["targetProviders"]["mobile"]} == {
        "flutter",
        "react_native_expo",
        "none",
    }


def test_scaffold_endpoints_create_confirm_run_poll_and_recover(tmp_path: Path) -> None:
    client = _client(tmp_path, execute_commands=True)

    created = client.post(
        "/project-factory/scaffolds",
        json={
            "name": "API Scaffold",
            "stackPreset": None,
            "mobileProvider": "none",
            "webProvider": "none",
            "apiProvider": "none",
            "cloudflareMode": "disabled",
            "awsReadinessMode": "none",
            "githubMode": "disabled",
        },
    )

    assert created.status_code == 200
    draft = created.json()
    assert draft["creationMode"] == "scaffold"
    assert draft["request"]["apiProvider"] == "none"
    assert draft["contractPreview"]["publishAndroid"] is False
    confirmed = client.post(
        f"/project-factory/scaffolds/{draft['draftId']}/confirm",
        json={"expectedContractHash": draft["contractHash"]},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "scaffold_contract_ready"

    started = client.post(
        f"/project-factory/scaffolds/{draft['draftId']}/jobs"
    )
    assert started.status_code == 200
    job = started.json()
    assert job["status"] == "scaffold_ready"
    assert job["canStartProduct"] is True
    assert [item["name"] for item in job["phases"]] == [
        "scaffold_preflight",
        "scaffold_contract",
        "workspace_baseline",
        "target_bootstrap",
        "target_validation",
        "local_git_commit",
        "github_repository",
        "cloudflare_scaffold",
        "aws_readiness",
        "workbench_registration",
        "scaffold_context_pack",
    ]
    polled = client.get(
        f"/project-factory/scaffold-jobs/{job['scaffoldJobId']}"
    )
    assert polled.status_code == 200
    assert polled.json()["providerPlans"] == []
    result = client.get(
        f"/project-factory/scaffold-jobs/{job['scaffoldJobId']}/result"
    )
    assert result.status_code == 200
    assert result.json()["status"] == "scaffold_ready"
    status = subprocess.run(
        ("git", "status", "--porcelain"),
        cwd=job["workspacePath"],
        check=False,
        capture_output=True,
        text=True,
    )
    log = subprocess.run(
        ("git", "log", "--format=%s"),
        cwd=job["workspacePath"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert status.returncode == 0
    assert status.stdout == ""
    assert "Create composable project scaffold" in log.stdout
    assert "Record scaffold result" in log.stdout

    session = client.post(
        "/sessions",
        json={
            "title": "API Scaffold Product",
            "workspace_path": job["workspacePath"],
        },
    )
    assert session.status_code == 201
    product = client.post(
        f"/project-factory/scaffold-jobs/{job['scaffoldJobId']}/start-product",
        json={"sessionId": session.json()["id"]},
    )
    repeated = client.post(
        f"/project-factory/scaffold-jobs/{job['scaffoldJobId']}/start-product",
        json={"sessionId": session.json()["id"]},
    )
    assert product.status_code == 200
    assert product.json()["status"] == "scaffold_ready"
    assert product.json()["domainFactoryRelationship"]["status"] == "domain_intake"
    assert repeated.json()["domainFactoryRelationship"] == product.json()[
        "domainFactoryRelationship"
    ]

    restarted = _client(tmp_path)
    recovered = restarted.get(
        f"/project-factory/scaffold-jobs/{job['scaffoldJobId']}"
    )
    assert recovered.status_code == 200
    assert recovered.json()["status"] == "scaffold_ready"


def test_scaffold_feature_flag_fails_closed_without_affecting_product_api(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path, enabled=False)

    scaffold = client.post(
        "/project-factory/scaffolds",
        json={"name": "Hidden"},
    )
    options = client.get("/project-factory/options")

    assert scaffold.status_code == 403
    assert options.status_code == 200
    assert options.json()["scaffoldEnabled"] is False
    assert options.json()["defaultCreationMode"] == "product"


def test_product_draft_endpoint_cannot_bypass_scaffold_gate_or_dedicated_intake(
    tmp_path: Path,
) -> None:
    payload = {
        "name": "Wrong entry point",
        "businessType": "must not be asked by scaffold",
        "primaryGoal": "must not be inferred by scaffold",
        "creationMode": "scaffold",
    }

    disabled = _client(tmp_path / "disabled", enabled=False).post(
        "/project-factory/drafts", json=payload
    )
    enabled = _client(tmp_path / "enabled", enabled=True).post(
        "/project-factory/drafts", json=payload
    )

    assert disabled.status_code == 403
    assert enabled.status_code == 409
    assert "/project-factory/scaffolds" in enabled.json()["detail"]


def test_scaffold_admin_email_is_conditional(tmp_path: Path) -> None:
    client = _client(tmp_path)

    unprotected = client.post(
        "/project-factory/scaffolds",
        json={
            "name": "Public Neutral",
            "previewProtected": False,
            "githubMode": "disabled",
        },
    )
    protected = client.post(
        "/project-factory/scaffolds",
        json={
            "name": "Protected Neutral",
            "previewProtected": True,
            "githubMode": "disabled",
        },
    )
    invalid_mode = client.post(
        "/project-factory/scaffolds",
        json={
            "name": "Protected Without Provision",
            "previewProtected": True,
            "initialAdminEmail": "owner@example.org",
            "cloudflareMode": "generate_only",
            "githubMode": "disabled",
        },
    )

    assert unprotected.status_code == 200
    assert protected.status_code == 422
    assert invalid_mode.status_code == 422
    assert "initialAdminEmail is required only" in protected.json()["detail"]
    assert "requires cloudflareMode=provision_scaffold" in invalid_mode.json()[
        "detail"
    ]


def test_start_product_api_rejects_blocked_scaffold_before_domain_activation(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path, execute_commands=False)
    created = client.post(
        "/project-factory/scaffolds",
        json={
            "name": "Blocked Foundation",
            "githubMode": "disabled",
            "cloudflareMode": "disabled",
        },
    ).json()
    client.post(
        f"/project-factory/scaffolds/{created['draftId']}/confirm",
        json={"expectedContractHash": created["contractHash"]},
    )
    job = client.post(
        f"/project-factory/scaffolds/{created['draftId']}/jobs"
    ).json()
    session = client.post(
        "/sessions",
        json={
            "title": "Must stay inactive",
            "workspace_path": job["workspacePath"],
        },
    ).json()

    response = client.post(
        f"/project-factory/scaffold-jobs/{job['scaffoldJobId']}/start-product",
        json={"sessionId": session["id"]},
    )
    persisted = client.get(
        f"/project-factory/scaffold-jobs/{job['scaffoldJobId']}"
    ).json()

    assert job["status"] == "scaffold_blocked_with_context"
    assert job["canStartProduct"] is False
    assert response.status_code == 409
    assert persisted["domainFactoryRelationship"] is None


def test_start_product_rolls_back_scaffold_relationship_when_domain_start_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, execute_commands=True)
    created = client.post(
        "/project-factory/scaffolds",
        json={
            "name": "Rollback Foundation",
            "stackPreset": None,
            "mobileProvider": "none",
            "webProvider": "none",
            "apiProvider": "none",
            "githubMode": "disabled",
            "cloudflareMode": "disabled",
            "awsReadinessMode": "none",
        },
    ).json()
    client.post(
        f"/project-factory/scaffolds/{created['draftId']}/confirm",
        json={"expectedContractHash": created["contractHash"]},
    )
    job = client.post(
        f"/project-factory/scaffolds/{created['draftId']}/jobs"
    ).json()
    session = client.post(
        "/sessions",
        json={
            "title": "Rollback product",
            "workspace_path": job["workspacePath"],
        },
    ).json()
    container = client.app.dependency_overrides[get_container]()

    def _fail_start(**_kwargs):
        raise RuntimeError("injected domain activation failure")

    monkeypatch.setattr(container.domain_factory_service, "start", _fail_start)

    response = client.post(
        f"/project-factory/scaffold-jobs/{job['scaffoldJobId']}/start-product",
        json={"sessionId": session["id"]},
    )
    persisted = client.get(
        f"/project-factory/scaffold-jobs/{job['scaffoldJobId']}"
    ).json()
    manifest = Path(job["workspacePath"], ".codex/project.yaml").read_text(
        encoding="utf-8"
    )

    assert response.status_code == 409
    assert persisted["domainFactoryRelationship"] is None
    assert persisted["canStartProduct"] is True
    assert "state: scaffold_ready" in manifest
    assert "next_action: start_product" in manifest
