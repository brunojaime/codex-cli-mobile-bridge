from contextlib import contextmanager
import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.work_routes import router, get_work, get_container
from backend.app.application.services.project_deployments import (
    DeploymentRecord,
    deployment_overview,
)
from backend.app.application.services.project_deployments import record_deployment


@pytest.fixture
def rig(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE work_tasks(id TEXT, workspace TEXT, receipt TEXT, updated_at TEXT, status TEXT)"
    )

    @contextmanager
    def ledger():
        yield db

    service = SimpleNamespace(
        messages=SimpleNamespace(
            list_workspaces=lambda: [
                SimpleNamespace(name="Project", path=str(workspace))
            ]
        ),
        ledger=ledger,
    )
    yield SimpleNamespace(service=service, path=workspace, db=db)
    db.close()


def receipt(
    rig,
    environment="dev",
    commit="a" * 40,
    date="2026-11-06T12:00:00Z",
    status="published",
    id=None,
    release=None,
):
    record_deployment(
        rig.path,
        DeploymentRecord(
            id=id or f"{environment}:{date}",
            environment=environment,
            commit=commit,
            release=release,
            deployed_at=date,
            status=status,
        ),
    )


def project(rig, previews=None):
    return deployment_overview(rig.service, previews)["projects"][0]


def test_empty_always_has_three_environments(rig):
    result = project(rig)
    assert [e["name"] for e in result["environments"]] == ["dev", "qa", "prod"]
    assert all(
        e["current"] is None and not e["history"] for e in result["environments"]
    )
    assert result["comparison"] == "insufficient"


def test_comparison_and_failed_attempt_preserves_published_release(rig):
    for env in ("dev", "qa", "prod"):
        receipt(rig, env)
    assert project(rig)["comparison"] == "same"
    receipt(rig, "dev", commit="b" * 40, date="2026-11-06T13:00:00Z", status="failed")
    result = project(rig)
    assert result["comparison"] == "same"
    assert result["environments"][0]["latest"]["status"] == "failed"
    assert result["environments"][0]["current"]["commit"] == "a" * 40
    receipt(rig, "dev", commit="b" * 40, date="2026-11-06T14:00:00Z")
    assert project(rig)["comparison"] == "different"


def test_missing_identity_partial_and_deactivation(rig):
    receipt(rig)
    receipt(rig, "qa")
    assert project(rig)["comparison"] == "partial_same"
    receipt(rig, "prod", commit=None)
    assert project(rig)["comparison"] == "unknown"
    receipt(rig, "qa", date="2026-11-06T15:00:00Z", status="disabled")
    assert project(rig)["environments"][1]["current"] is None


def test_corrupt_manifest_is_error_not_no_deploy(rig):
    directory = rig.path / ".codex"
    directory.mkdir()
    (directory / "deployments.json").write_text("{bad secret-value-do-not-echo")
    result = project(rig)
    assert result["errors"]
    assert result["comparison"] == "unknown"
    assert "secret-value" not in json.dumps(result)


def test_real_delivery_and_preview_plans_do_not_become_releases(rig):
    rig.db.execute(
        "INSERT INTO work_tasks VALUES (?,?,?,?,?)",
        (
            "one",
            str(rig.path),
            json.dumps({"environment": "dev", "commit": "b" * 40}),
            "2026-11-06T12:00:00Z",
            "completed",
        ),
    )
    previews = SimpleNamespace(
        list_previews=lambda **kw: [
            {"project_path": str(rig.path), "status": "planned"}
        ]
    )
    result = project(rig, previews)
    assert result["environments"][0]["current"]["source"] == "delivery"
    assert len(result["environments"][0]["history"]) == 1


def test_expired_preview_removes_active_and_does_not_use_plan_hash(rig):
    previews = SimpleNamespace(
        list_previews=lambda **kw: [
            {
                "project_path": str(rig.path),
                "status": "expired",
                "preview_id": "one",
                "updated_at": "2026-11-06T14:00:00Z",
                "completed_at": "2026-11-05T14:00:00Z",
                "plan_hash": "not-a-release",
            }
        ]
    )
    env = project(rig, previews)["environments"][0]
    assert env["current"] is None
    assert env["latest"]["release"] is None
    assert env["latest"]["deployed_at"].startswith("2026-11-06")


def test_writer_idempotent_and_conflict_rejected(rig):
    receipt(rig)
    receipt(rig)
    assert len(project(rig)["environments"][0]["history"]) == 1
    with pytest.raises(ValueError):
        receipt(rig, commit="b" * 40)
    with pytest.raises(ValueError):
        receipt(rig, date="2026-11-06T12:00:00")


def test_scoped_api_and_unknown_project(rig):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_work] = lambda: rig.service
    app.dependency_overrides[get_container] = lambda: SimpleNamespace()

    # sqlite test connection stays on this thread only by using service substitute.
    class NoRows:
        def execute(self, *args):
            return self

        def fetchall(self):
            return []

    @contextmanager
    def ledger():
        yield NoRows()

    rig.service.ledger = ledger
    with TestClient(app) as client:
        result = client.get(
            "/work/deployments", params={"workspace_path": str(rig.path)}
        )
        assert result.status_code == 200
        assert len(result.json()["projects"]) == 1
        assert (
            client.get(
                "/work/deployments", params={"workspace_path": "/not-allowed"}
            ).status_code
            == 404
        )


def test_same_commit_different_releases_are_distinguished(rig):
    receipt(rig, "dev", release="v2")
    receipt(rig, "prod", release="v1")
    assert project(rig)["comparison"] == "different"


def test_source_failure_never_claims_release_equality(rig):
    for env in ("dev", "qa", "prod"):
        receipt(rig, env)

    def unavailable(**kwargs):
        raise OSError("private provider error")

    result = project(rig, SimpleNamespace(list_previews=unavailable))
    assert result["comparison"] == "unknown"
    assert result["errors"]
    assert "private provider" not in json.dumps(result)
