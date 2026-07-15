from __future__ import annotations

import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api.routes import (
    _stage_run_final_summary,
    _stage_run_reviewer_contract,
)
from backend.app.application.services.dev_pipeline_service import DevPipelineService
from backend.app.application.services.message_service import BackendDrainStatus
from backend.app.infrastructure.config.settings import Settings
from backend.app.main import create_app

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_FAKE_CODEX = f"python3 {_FIXTURES_DIR / 'fake_codex.py'}"
_FAKE_CODEX_HANDOFF = f"python3 {_FIXTURES_DIR / 'fake_codex_handoff.py'}"


def test_health_exposes_prod_environment_identity(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.get("/health")

    assert response.status_code == 200
    identity = response.json()["environment_identity"]
    assert identity["kind"] == "codex.bridgeEnvironmentIdentity"
    assert identity["environment"] == "prod"
    assert identity["app_channel"] == "prod"
    assert "write_bridge_code" in identity["denied_capabilities"]
    assert "enqueue_dev_handoff" in identity["denied_capabilities"]
    assert "enqueue_dev_handoff" not in identity["allowed_capabilities"]


def test_prod_handoff_is_flag_guarded(tmp_path: Path) -> None:
    client = _client(tmp_path, prod_handoff_enabled=False)

    response = client.post("/dev-pipeline/handoffs", json=_handoff_payload())

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "prod_handoff_disabled"
    assert not (tmp_path / "state.json").exists()


def test_mobile_handoff_requires_one_shot_draft_grant(tmp_path: Path) -> None:
    client = _client(
        tmp_path,
        prod_handoff_enabled=True,
        codex_command=_FAKE_CODEX_HANDOFF,
    )
    payload = {**_handoff_payload(), "created_by_action": "mobile_dev_handoff"}

    blocked = client.post(
        "/dev-pipeline/handoffs",
        json=payload,
        headers={"X-Idempotency-Key": "mobile-no-grant"},
    )

    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "dev_handoff_draft_grant_required"

    draft = client.post("/dev-pipeline/handoffs/draft", json={})
    assert draft.status_code == 200, draft.text
    draft_data = draft.json()["data"]
    assert draft_data["draft_token"]
    assert draft_data["draft_status"] == "generating"
    draft_data = _ready_handoff_draft(client, draft_data["draft_id"])
    assert draft_data["draft_status"] == "ready"
    assert draft_data["proposed_spec"].startswith("001-")
    assert draft_data["proposed_tasks"]

    queued = client.post(
        "/dev-pipeline/handoffs",
        json={**payload, "draft_token": draft_data["draft_token"]},
        headers={"X-Idempotency-Key": "mobile-with-grant"},
    )
    assert queued.status_code == 200, queued.text
    assert queued.json()["data"]["status"] == "queued"

    reused = client.post(
        "/dev-pipeline/handoffs",
        json={**payload, "draft_token": draft_data["draft_token"], "title": "Other"},
        headers={"X-Idempotency-Key": "mobile-reused-grant"},
    )
    assert reused.status_code == 409
    assert reused.json()["detail"]["code"] == "dev_handoff_draft_grant_consumed"


def test_handoff_draft_does_not_enqueue_until_reviewed(tmp_path: Path) -> None:
    client = _client(
        tmp_path,
        prod_handoff_enabled=True,
        codex_command=_FAKE_CODEX_HANDOFF,
    )

    response = client.post(
        "/dev-pipeline/handoffs/draft",
        json={"title": "Enable reviewed DEV handoff specs"},
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["title"] == "Enable reviewed DEV handoff specs"
    assert data["draft_status"] == "generating"
    data = _ready_handoff_draft(client, data["draft_id"])
    assert data["title"] == "LLM prepared bridge handoff"
    assert data["created_by_action"] == "mobile_dev_handoff"
    assert data["acceptance_criteria"]
    snapshot = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert snapshot["handoffs"] == {}
    assert snapshot["backlog"] == {}
    assert len(snapshot["handoff_drafts"]) == 1


def test_prod_normal_cannot_read_or_mutate_dev_pipeline_state(tmp_path: Path) -> None:
    client = _client(tmp_path, prod_handoff_enabled=True)

    responses = [
        client.get("/dev-pipeline"),
        client.get("/dev-pipeline/projection"),
        client.post("/dev-pipeline/backfill/stages", json={"dry_run": True}),
        client.post(
            "/dev-pipeline/stages",
            json={"spec_id": "018-dev-prod-stage-promotion-pipeline"},
        ),
        client.post(
            "/dev-pipeline/sessions/bind",
            json={
                "session_id": "session-018",
                "stage_id": "spec-018",
                "workspace_path": str(tmp_path / "codex-cli-mobile-bridge-spec-018"),
                "branch": "dev/spec-018-dev-prod-stage-promotion-pipeline",
            },
        ),
        client.post(
            "/dev-pipeline/stages/spec-018/lifecycle",
            json={"action": "status"},
        ),
        client.post(
            "/dev-pipeline/merge-queue",
            json={"stage_id": "spec-018", "requested_by": "prod", "approved": True},
        ),
        client.post(
            "/dev-pipeline/promotions",
            json={"requested_by": "prod", "target": "prod", "user_approved": True},
        ),
        client.post(
            "/dev-pipeline/prod-update/prepare",
            json={"prepared_update_id": "update-1"},
        ),
        client.post(
            "/dev-pipeline/release-channels/validate",
            json={"configs": []},
        ),
    ]

    assert {response.status_code for response in responses} == {403}
    permissions = client.get("/dev-pipeline/permissions").json()["data"]
    assert sorted(permissions["modes"]) == ["prod_normal", "prod_slash"]
    assert "dev_stage" not in permissions["modes"]


def test_dev_pipeline_projection_filters_workbench_and_blocks_prod(
    tmp_path: Path,
) -> None:
    repo_root = _init_git_repo(tmp_path)
    stage, dev_client = _materialized_stage(
        tmp_path,
        repo_root=repo_root,
        key="projection",
    )
    prod_client = _client(tmp_path, repo_root=repo_root, prod_handoff_enabled=True)

    prod_response = prod_client.get("/dev-pipeline/projection")
    projection = dev_client.get(
        "/dev-pipeline/projection",
        params={"stage_id": stage["stage_id"], "status": "active"},
    )

    assert prod_response.status_code == 403
    assert projection.status_code == 200, projection.text
    data = projection.json()["data"]
    assert data["filters"] == {"stage_id": stage["stage_id"], "status": "active"}
    assert [item["stage_id"] for item in data["stages"]] == [stage["stage_id"]]
    assert [item["stage_id"] for item in data["workbench"]["active_stages"]] == [
        stage["stage_id"]
    ]
    assert data["workbench"]["merge_status"] == []


def test_backfill_stage_candidates_dry_run_detects_existing_specs_and_blockers(
    tmp_path: Path,
) -> None:
    repo_root = _init_git_repo(tmp_path)
    spec_017 = repo_root / "specs/017-existing-stage"
    spec_018 = repo_root / "specs/018-missing-branch"
    spec_017.mkdir()
    spec_018.mkdir()
    spec_017.joinpath("spec.md").write_text("# Existing\n", encoding="utf-8")
    spec_018.joinpath("spec.md").write_text("# Missing Branch\n", encoding="utf-8")
    _git(repo_root, "add", "specs")
    _git(repo_root, "commit", "-m", "add specs")
    _git(repo_root, "branch", "dev/spec-017-existing-stage", "dev/main")
    worktree_017 = repo_root.parent / "codex-cli-mobile-bridge-spec-017"
    _git(
        repo_root,
        "worktree",
        "add",
        str(worktree_017),
        "dev/spec-017-existing-stage",
    )
    worktree_017.joinpath("dirty.txt").write_text("dirty\n", encoding="utf-8")
    client = _client(tmp_path, environment="dev", repo_root=repo_root)

    response = client.post("/dev-pipeline/backfill/stages", json={"dry_run": True})

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    by_spec = {item["spec_id"]: item for item in data["candidates"]}
    assert data["dry_run"] is True
    assert "017-existing-stage" in by_spec
    assert "missing_branch" not in by_spec["017-existing-stage"]["blockers"]
    assert "dirty_worktree" in by_spec["017-existing-stage"]["blockers"]
    assert "missing_branch" in by_spec["018-missing-branch"]["blockers"]
    assert not (tmp_path / "state.json").exists()


def test_dev_pipeline_enabled_flag_blocks_stateful_operations(tmp_path: Path) -> None:
    client = _client(tmp_path, environment="dev", pipeline_enabled=False)

    snapshot = client.get("/dev-pipeline")
    stage = client.post(
        "/dev-pipeline/stages",
        json={"spec_id": "018-dev-prod-stage-promotion-pipeline"},
    )

    assert snapshot.status_code == 409
    assert snapshot.json()["detail"]["code"] == "dev_pipeline_disabled"
    assert stage.status_code == 409
    assert stage.json()["detail"]["code"] == "dev_pipeline_disabled"


def test_prod_handoff_enqueue_is_immutable_and_idempotent(tmp_path: Path) -> None:
    client = _client(tmp_path, prod_handoff_enabled=True)
    payload = _handoff_payload_with_grant(client)

    first = client.post(
        "/dev-pipeline/handoffs",
        json=payload,
        headers={"X-Idempotency-Key": "handoff-key-1"},
    )
    second = client.post(
        "/dev-pipeline/handoffs",
        json=payload,
        headers={"X-Idempotency-Key": "handoff-key-1"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_item = first.json()["data"]
    second_item = second.json()["data"]
    assert first_item == second_item
    assert first_item["immutable"] is True
    assert first_item["operation"] == "enqueue_only"
    snapshot = _client(tmp_path, environment="dev").get("/dev-pipeline").json()["data"]
    assert [item["id"] for item in snapshot["handoffs"]] == [first_item["id"]]
    assert snapshot["backlog"][0]["status"] == "queued"


def test_prod_handoff_idempotency_key_conflicts_on_payload_change(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path, prod_handoff_enabled=True)
    payload = _handoff_payload_with_grant(client)
    changed = {**payload, "problem": "A different PROD problem."}

    first = client.post(
        "/dev-pipeline/handoffs",
        json=payload,
        headers={"X-Idempotency-Key": "handoff-key-conflict"},
    )
    conflict = client.post(
        "/dev-pipeline/handoffs",
        json=changed,
        headers={"X-Idempotency-Key": "handoff-key-conflict"},
    )

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"


def test_prod_handoff_audit_redacts_selected_context_and_evidence(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path, prod_handoff_enabled=True)
    payload = {
        **_handoff_payload_with_grant(client),
        "selected_context": {
            "visible": "keep",
            "auth": {"token": "prod-token-value"},
            "items": [{"password": "prod-password"}],
        },
        "evidence": [
            {
                "kind": "note",
                "text": "safe evidence",
                "secret_key": "prod-secret",
                "nested": {"apiToken": "nested-token"},
            }
        ],
    }

    response = client.post(
        "/dev-pipeline/handoffs",
        json=payload,
        headers={"X-Idempotency-Key": "handoff-audit-redaction"},
    )

    assert response.status_code == 200
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    event = state["events"][-1]
    assert event["source_session_id"] == "session-prod"
    assert event["selected_context"]["visible"] == "keep"
    assert event["selected_context"]["auth"]["token"] == "[redacted]"
    assert event["selected_context"]["items"][0]["password"] == "[redacted]"
    assert event["evidence"][0]["text"] == "safe evidence"
    assert event["evidence"][0]["secret_key"] == "[redacted]"
    assert event["evidence"][0]["nested"]["apiToken"] == "[redacted]"


def test_backlog_claim_requires_dev_environment(tmp_path: Path) -> None:
    prod_client = _client(tmp_path, prod_handoff_enabled=True)
    prod_client.post(
        "/dev-pipeline/handoffs",
        json=_handoff_payload_with_grant(prod_client),
        headers={"X-Idempotency-Key": "claim-key"},
    )

    blocked = prod_client.post(
        "/dev-pipeline/backlog/claim",
        json={"worker_id": "dev-worker"},
    )
    dev_client = _client(tmp_path, environment="dev", prod_handoff_enabled=True)
    claimed = dev_client.post(
        "/dev-pipeline/backlog/claim",
        json={"worker_id": "dev-worker"},
    )

    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "dev_environment_required"
    assert claimed.status_code == 200
    assert claimed.json()["data"]["status"] == "claimed"
    assert claimed.json()["data"]["locked_by"] == "dev-worker"


def test_materialize_creates_new_spec_stage_and_worktree(tmp_path: Path) -> None:
    repo_root = _init_git_repo(tmp_path)
    handoff_id, dev_client = _enqueue_and_claim(
        tmp_path,
        repo_root=repo_root,
        key="materialize-new-spec",
    )

    response = dev_client.post(
        f"/dev-pipeline/backlog/{handoff_id}/materialize",
        json={"worker_id": "dev-worker"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    backlog = data["backlog"]
    spec = data["spec"]
    stage = data["stage"]
    worktree = tmp_path / "codex-cli-mobile-bridge-spec-018"
    assert backlog["status"] == "materialized"
    assert backlog["spec_id"] == "018-dev-prod-stage-promotion-pipeline"
    assert backlog["stage_id"] == "spec-018"
    assert backlog["branch"] == "dev/spec-018-dev-prod-stage-promotion-pipeline"
    assert Path(backlog["worktree_path"]) == worktree.resolve()
    assert spec["status"] == "created"
    assert stage["runtime"]["port"] == 8118
    assert (worktree / "specs/018-dev-prod-stage-promotion-pipeline/spec.md").exists()
    assert "Fix bridge update gate" in (
        worktree / "specs/018-dev-prod-stage-promotion-pipeline/spec.md"
    ).read_text(encoding="utf-8")
    assert _git(worktree, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == (
        "dev/spec-018-dev-prod-stage-promotion-pipeline"
    )
    snapshot = dev_client.get("/dev-pipeline").json()["data"]
    assert snapshot["backlog"][0]["status"] == "materialized"
    assert snapshot["specs"][0]["stage_id"] == "spec-018"
    assert snapshot["stages"][0]["spec_id"] == "018-dev-prod-stage-promotion-pipeline"


def test_backlog_notify_materializes_specific_handoff(tmp_path: Path) -> None:
    repo_root = _init_git_repo(tmp_path)
    prod_client = _client(
        tmp_path,
        repo_root=repo_root,
        prod_handoff_enabled=True,
    )
    old = prod_client.post(
        "/dev-pipeline/handoffs",
        json=_handoff_payload_with_grant(
            prod_client,
            {
                **_handoff_payload(),
                "title": "Older queued handoff",
                "proposed_spec": "020-older-queued-handoff",
            },
        ),
        headers={"X-Idempotency-Key": "notify-old"},
    )
    assert old.status_code == 200, old.text
    newer = prod_client.post(
        "/dev-pipeline/handoffs",
        json=_handoff_payload_with_grant(
            prod_client,
            {
                **_handoff_payload(),
                "title": "Newer exact handoff",
                "proposed_spec": "021-newer-exact-handoff",
            },
        ),
        headers={"X-Idempotency-Key": "notify-new"},
    )
    assert newer.status_code == 200, newer.text
    old_id = old.json()["data"]["id"]
    newer_id = newer.json()["data"]["id"]
    dev_client = _client(tmp_path, environment="dev", repo_root=repo_root)

    response = dev_client.post(
        "/dev-pipeline/backlog/notify",
        json={"worker_id": "dev-auto-runner", "handoff_id": newer_id},
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["backlog"]["handoff_id"] == newer_id
    assert data["backlog"]["status"] == "materialized"
    snapshot = dev_client.get("/dev-pipeline").json()["data"]
    backlog = {item["handoff_id"]: item for item in snapshot["backlog"]}
    assert backlog[old_id]["status"] == "queued"
    assert backlog[newer_id]["status"] == "materialized"
    assert data["stage"]["stage_id"] == "spec-021"


def test_prod_enqueue_schedules_dev_notify_background_task(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_notify(**kwargs: object) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(
        "backend.app.api.routes._notify_dev_pipeline_backend",
        fake_notify,
    )
    client = _client(
        tmp_path,
        prod_handoff_enabled=True,
        dev_notify_url="http://127.0.0.1:8118/dev-pipeline/backlog/notify",
    )

    response = client.post(
        "/dev-pipeline/handoffs",
        json=_handoff_payload_with_grant(client),
        headers={"X-Idempotency-Key": "notify-background"},
    )

    assert response.status_code == 200, response.text
    assert calls == [
        {
            "notify_url": "http://127.0.0.1:8118/dev-pipeline/backlog/notify",
            "handoff_id": response.json()["data"]["id"],
            "worker_id": "dev-auto-runner",
        }
    ]


def test_materialize_attaches_existing_spec(tmp_path: Path) -> None:
    repo_root = _init_git_repo(tmp_path)
    spec_dir = repo_root / "specs/018-dev-prod-stage-promotion-pipeline"
    spec_dir.mkdir(parents=True)
    spec_dir.joinpath("spec.md").write_text("# Existing Spec\n", encoding="utf-8")
    spec_dir.joinpath("plan.md").write_text("# Existing Plan\n", encoding="utf-8")
    spec_dir.joinpath("tasks.md").write_text("# Existing Tasks\n", encoding="utf-8")
    _git(repo_root, "add", "specs/018-dev-prod-stage-promotion-pipeline")
    _git(repo_root, "commit", "-m", "add existing spec")
    handoff_id, dev_client = _enqueue_and_claim(
        tmp_path,
        repo_root=repo_root,
        key="materialize-existing-spec",
    )

    response = dev_client.post(
        f"/dev-pipeline/backlog/{handoff_id}/materialize",
        json={"worker_id": "dev-worker"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["backlog"]["status"] == "materialized"
    assert data["spec"]["status"] == "attached"
    worktree_spec = (
        tmp_path
        / "codex-cli-mobile-bridge-spec-018"
        / "specs/018-dev-prod-stage-promotion-pipeline/spec.md"
    )
    assert worktree_spec.read_text(encoding="utf-8") == "# Existing Spec\n"


def test_materialize_is_idempotent_for_same_worker(tmp_path: Path) -> None:
    repo_root = _init_git_repo(tmp_path)
    handoff_id, dev_client = _enqueue_and_claim(
        tmp_path,
        repo_root=repo_root,
        key="materialize-idempotent",
    )

    first = dev_client.post(
        f"/dev-pipeline/backlog/{handoff_id}/materialize",
        json={"worker_id": "dev-worker"},
    )
    second = dev_client.post(
        f"/dev-pipeline/backlog/{handoff_id}/materialize",
        json={"worker_id": "dev-worker"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["backlog"] == second.json()["data"]["backlog"]


def test_materialize_blocks_dirty_and_incompatible_worktrees(tmp_path: Path) -> None:
    dirty_repo_root = _init_git_repo(tmp_path / "dirty")
    dirty_handoff_id, dirty_dev = _enqueue_and_claim(
        tmp_path / "dirty",
        repo_root=dirty_repo_root,
        key="materialize-dirty-worktree",
    )
    dirty_worktree = dirty_repo_root.parent / "codex-cli-mobile-bridge-spec-018"
    _git(
        dirty_repo_root,
        "worktree",
        "add",
        "-b",
        "dev/spec-018-dev-prod-stage-promotion-pipeline",
        str(dirty_worktree),
        "dev/main",
    )
    dirty_worktree.joinpath("untracked.txt").write_text("dirty", encoding="utf-8")

    dirty = dirty_dev.post(
        f"/dev-pipeline/backlog/{dirty_handoff_id}/materialize",
        json={"worker_id": "dev-worker"},
    )

    incompatible_repo_root = _init_git_repo(tmp_path / "incompatible")
    incompatible_handoff_id, incompatible_dev = _enqueue_and_claim(
        tmp_path / "incompatible",
        repo_root=incompatible_repo_root,
        key="materialize-incompatible-worktree",
    )
    incompatible_worktree = (
        incompatible_repo_root.parent / "codex-cli-mobile-bridge-spec-018"
    )
    _git(
        incompatible_repo_root,
        "worktree",
        "add",
        "-b",
        "dev/spec-018-other",
        str(incompatible_worktree),
        "dev/main",
    )
    incompatible = incompatible_dev.post(
        f"/dev-pipeline/backlog/{incompatible_handoff_id}/materialize",
        json={"worker_id": "dev-worker"},
    )

    assert dirty.status_code == 200
    assert dirty.json()["data"]["backlog"]["status"] == "blocked"
    assert dirty.json()["data"]["backlog"]["blocker_reason"] == "dirty_worktree"
    dirty_worktree.joinpath("untracked.txt").unlink()
    retry = dirty_dev.post(
        f"/dev-pipeline/backlog/{dirty_handoff_id}/materialize",
        json={"worker_id": "dev-worker"},
    )
    assert retry.status_code == 200
    assert retry.json()["data"]["backlog"]["status"] == "materialized"
    assert retry.json()["data"]["backlog"]["partial_artifacts"] == []
    assert incompatible.status_code == 200
    assert incompatible.json()["data"]["backlog"]["status"] == "blocked"
    assert (
        incompatible.json()["data"]["backlog"]["blocker_reason"]
        == "incompatible_worktree_branch"
    )


def test_materialize_records_partial_artifacts_after_worktree_created(
    tmp_path: Path,
) -> None:
    repo_root = _init_git_repo(tmp_path)
    handoff_id, dev_client = _enqueue_and_claim(
        tmp_path,
        repo_root=repo_root,
        key="materialize-partial-artifacts",
    )
    state_path = tmp_path / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["stages"]["spec-018"] = {
        "stage_id": "spec-018",
        "spec_id": "018-conflicting-stage",
        "branch": "dev/spec-018-conflicting-stage",
        "worktree_path": str(tmp_path / "other-worktree"),
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")

    response = dev_client.post(
        f"/dev-pipeline/backlog/{handoff_id}/materialize",
        json={"worker_id": "dev-worker"},
    )

    assert response.status_code == 200
    backlog = response.json()["data"]["backlog"]
    assert backlog["status"] == "blocked"
    assert backlog["blocker_reason"] == "stage_identity_mismatch"
    assert {artifact["kind"] for artifact in backlog["partial_artifacts"]} >= {
        "git_worktree",
        "sdd_skeleton_file",
    }
    assert response.json()["data"]["handoff"]["status"] == "queued"


def test_materialize_blocks_invalid_proposed_spec(tmp_path: Path) -> None:
    repo_root = _init_git_repo(tmp_path)
    payload = {**_handoff_payload(), "proposed_spec": "invalid spec"}
    handoff_id, dev_client = _enqueue_and_claim(
        tmp_path,
        repo_root=repo_root,
        key="materialize-invalid-spec",
        payload=payload,
    )

    response = dev_client.post(
        f"/dev-pipeline/backlog/{handoff_id}/materialize",
        json={"worker_id": "dev-worker"},
    )

    assert response.status_code == 200
    backlog = response.json()["data"]["backlog"]
    assert backlog["status"] == "blocked"
    assert backlog["blocker_reason"] == "invalid_or_missing_proposed_spec"


def test_materialize_parallel_stages_are_isolated(tmp_path: Path) -> None:
    repo_root = _init_git_repo(tmp_path)
    handoff_017, dev_client = _enqueue_and_claim(
        tmp_path,
        repo_root=repo_root,
        key="materialize-017",
        payload={
            **_handoff_payload(),
            "title": "Spec 017 handoff",
            "proposed_spec": "017-new-project-deterministic-init-pipeline",
        },
    )
    handoff_018, _ = _enqueue_and_claim(
        tmp_path,
        repo_root=repo_root,
        key="materialize-018",
        payload=_handoff_payload(),
    )

    stage_017 = dev_client.post(
        f"/dev-pipeline/backlog/{handoff_017}/materialize",
        json={"worker_id": "dev-worker"},
    ).json()["data"]["stage"]
    stage_018 = dev_client.post(
        f"/dev-pipeline/backlog/{handoff_018}/materialize",
        json={"worker_id": "dev-worker"},
    ).json()["data"]["stage"]

    assert stage_017["stage_id"] == "spec-017"
    assert stage_018["stage_id"] == "spec-018"
    assert stage_017["branch"] == "dev/spec-017-new-project-deterministic-init-pipeline"
    assert stage_018["branch"] == "dev/spec-018-dev-prod-stage-promotion-pipeline"
    for key in ["pid_file", "logs_dir", "data_dir", "env_file"]:
        assert stage_017["runtime"][key] != stage_018["runtime"][key]


def test_prod_and_control_cannot_materialize_backlog(tmp_path: Path) -> None:
    repo_root = _init_git_repo(tmp_path)
    handoff_id, _ = _enqueue_and_claim(
        tmp_path,
        repo_root=repo_root,
        key="materialize-env-guard",
    )

    prod = _client(tmp_path, repo_root=repo_root, prod_handoff_enabled=True).post(
        f"/dev-pipeline/backlog/{handoff_id}/materialize",
        json={"worker_id": "dev-worker"},
    )
    control = _client(tmp_path, repo_root=repo_root, environment="control").post(
        f"/dev-pipeline/backlog/{handoff_id}/materialize",
        json={"worker_id": "dev-worker"},
    )

    assert prod.status_code == 403
    assert prod.json()["detail"]["code"] == "dev_environment_required"
    assert control.status_code == 403
    assert control.json()["detail"]["code"] == "dev_environment_required"


def test_stage_session_binding_and_message_enforcement(tmp_path: Path) -> None:
    repo_root = _init_git_repo(tmp_path)
    handoff_id, dev_client = _enqueue_and_claim(
        tmp_path,
        repo_root=repo_root,
        key="stage-session-binding",
    )
    materialized = dev_client.post(
        f"/dev-pipeline/backlog/{handoff_id}/materialize",
        json={"worker_id": "dev-worker"},
    ).json()["data"]
    stage = materialized["stage"]
    stage_client = _client(
        tmp_path,
        environment="dev",
        repo_root=repo_root,
        api_base_url=stage["backend_url"],
        projects_root=tmp_path,
    )

    created = stage_client.post(
        "/dev-pipeline/stages/spec-018/sessions",
        json={"title": "Stage chat"},
    )
    assert created.status_code == 200
    binding = created.json()["data"]
    session_id = binding["session_id"]
    assert binding["status"] == "bound"
    assert binding["worktree_path"] == stage["worktree_path"]
    assert binding["branch"] == stage["branch"]
    persisted = stage_client.get(f"/dev-pipeline/sessions/{session_id}/binding")
    assert persisted.status_code == 200
    assert persisted.json()["data"] == binding

    mismatch = stage_client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "wrong workspace", "workspace_path": str(tmp_path)},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == "stage_workspace_mismatch"

    sent = stage_client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "run in the stage"},
    )
    assert sent.status_code == 202

    _git(Path(stage["worktree_path"]), "checkout", "-b", "dev/spec-018-wrong")
    branch_mismatch = stage_client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "wrong branch"},
    )
    assert branch_mismatch.status_code == 409
    assert branch_mismatch.json()["detail"]["code"] == "stage_branch_mismatch"


def test_stage_session_cannot_move_stage_and_prod_control_cannot_read(
    tmp_path: Path,
) -> None:
    repo_root = _init_git_repo(tmp_path)
    handoff_017, dev_client = _enqueue_and_claim(
        tmp_path,
        repo_root=repo_root,
        key="stage-binding-017",
        payload={
            **_handoff_payload(),
            "proposed_spec": "017-new-project-deterministic-init-pipeline",
        },
    )
    handoff_018, _ = _enqueue_and_claim(
        tmp_path,
        repo_root=repo_root,
        key="stage-binding-018",
    )
    dev_client.post(
        f"/dev-pipeline/backlog/{handoff_017}/materialize",
        json={"worker_id": "dev-worker"},
    )
    stage_018 = dev_client.post(
        f"/dev-pipeline/backlog/{handoff_018}/materialize",
        json={"worker_id": "dev-worker"},
    ).json()["data"]["stage"]
    stage_client = _client(
        tmp_path,
        environment="dev",
        repo_root=repo_root,
        api_base_url=stage_018["backend_url"],
        projects_root=tmp_path,
    )
    session_id = stage_client.post(
        "/dev-pipeline/stages/spec-017/sessions",
        json={},
    ).json()["data"]["session_id"]

    move = stage_client.post(
        "/dev-pipeline/stages/spec-018/sessions",
        json={"session_id": session_id},
    )
    prod_read = _client(tmp_path, repo_root=repo_root).get(
        f"/dev-pipeline/sessions/{session_id}/binding"
    )
    control_read = _client(tmp_path, environment="control", repo_root=repo_root).get(
        f"/dev-pipeline/sessions/{session_id}/binding"
    )

    assert move.status_code == 409
    assert move.json()["detail"]["code"] == "session_stage_mismatch"
    assert prod_read.status_code == 403
    assert control_read.status_code == 403


def test_stage_run_uses_reviewer_auto_chain_preset_and_records_evidence(
    tmp_path: Path,
) -> None:
    repo_root = _init_git_repo(tmp_path)
    handoff_id, dev_client = _enqueue_and_claim(
        tmp_path,
        repo_root=repo_root,
        key="stage-run-reviewer-evidence",
    )
    stage = dev_client.post(
        f"/dev-pipeline/backlog/{handoff_id}/materialize",
        json={"worker_id": "dev-worker"},
    ).json()["data"]["stage"]
    stage_client = _client(
        tmp_path,
        environment="dev",
        repo_root=repo_root,
        api_base_url=stage["backend_url"],
        projects_root=tmp_path,
    )
    session_id = stage_client.post(
        "/dev-pipeline/stages/spec-018/sessions",
        json={"title": "Stage run"},
    ).json()["data"]["session_id"]

    run = stage_client.post(
        "/dev-pipeline/stages/spec-018/runs/start",
        json={"session_id": session_id, "requested_by": "tester"},
    )

    assert run.status_code == 200
    payload = run.json()["data"]
    assert payload["status"] in {"queued", "running", "completed"}
    assert payload["job_id"]
    assert payload["agent_run_id"]
    assert payload["started_at"]
    assert "Implement DEV stage" in payload["prompt"]
    assert payload["preset"] == "DEV Stage Generator/Reviewer"
    assert payload["auto_chain"]["preset"] == "review"
    assert payload["evidence"]["reviewer"]["status"] in {"planned", "observed"}
    assert payload["evidence"]["risks"] == [
        "agent execution is not started by this control yet"
    ]
    status = stage_client.get(f"/dev-pipeline/stage-runs/{payload['id']}")
    assert status.status_code == 200
    duplicate = stage_client.post(
        "/dev-pipeline/stages/spec-018/runs/start",
        json={"session_id": session_id, "requested_by": "tester"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "stage_run_active"
    cancelled = stage_client.post(
        f"/dev-pipeline/stage-runs/{payload['id']}/cancel",
        json={"requested_by": "tester"},
    )
    assert cancelled.json()["data"]["status"] in {"cancelled", "failed", "completed"}
    retried = stage_client.post(
        f"/dev-pipeline/stage-runs/{payload['id']}/retry",
        json={"requested_by": "tester"},
    )
    assert retried.json()["data"]["status"] in {"queued", "running", "completed"}


def test_stage_run_reviewer_json_contract_and_final_summary() -> None:
    complete = _stage_run_reviewer_contract(
        json.dumps({"status": "complete", "summary": "All acceptance criteria pass."})
    )
    follow_up = _stage_run_reviewer_contract(
        json.dumps({"status": "continue", "prompt": "Add regression coverage."})
    )
    invalid = _stage_run_reviewer_contract("Review complete.")
    summary = _stage_run_final_summary(
        run={"stage_id": "spec-018", "branch": "dev/spec-018-test"},
        reviewer=complete,
        changed_files=["M backend/app.py"],
        tests=["pytest tests/test_dev_pipeline.py -q"],
    )

    assert complete["status"] == "complete"
    assert complete["completion"] == "All acceptance criteria pass."
    assert follow_up["status"] == "continue"
    assert follow_up["continue"] == "Add regression coverage."
    assert invalid["status"] == "invalid_contract"
    assert invalid["blocker"] == "reviewer_response_must_be_json"
    assert "Termine." in summary
    assert "All acceptance criteria pass." in summary
    assert "pytest tests/test_dev_pipeline.py -q" in summary


def test_stage_run_pause_resume_controls_are_explicit_and_idempotent(
    tmp_path: Path,
) -> None:
    repo_root = _init_git_repo(tmp_path)
    stage, _dev_client = _materialized_stage(
        tmp_path,
        repo_root=repo_root,
        key="stage-run-pause-resume",
    )
    stage_client = _client(
        tmp_path,
        environment="dev",
        repo_root=repo_root,
        api_base_url=stage["backend_url"],
        projects_root=tmp_path,
    )
    session_id = stage_client.post(
        "/dev-pipeline/stages/spec-018/sessions",
        json={"title": "Pause resume"},
    ).json()["data"]["session_id"]
    run = stage_client.post(
        "/dev-pipeline/stages/spec-018/runs/start",
        json={"session_id": session_id, "requested_by": "tester"},
    ).json()["data"]

    paused = stage_client.post(
        f"/dev-pipeline/stage-runs/{run['id']}/pause",
        json={"requested_by": "tester"},
    ).json()["data"]
    paused_again = stage_client.post(
        f"/dev-pipeline/stage-runs/{run['id']}/pause",
        json={"requested_by": "tester"},
    ).json()["data"]
    resumed = stage_client.post(
        f"/dev-pipeline/stage-runs/{run['id']}/resume",
        json={"requested_by": "tester"},
    ).json()["data"]
    resumed_again = stage_client.post(
        f"/dev-pipeline/stage-runs/{run['id']}/resume",
        json={"requested_by": "tester"},
    ).json()["data"]

    assert paused["status"] == "pause_requested"
    assert paused["blocker_reason"] == "message_service_pause_not_supported"
    assert paused_again["status"] == "pause_requested"
    assert resumed["status"] == "resume_requested"
    assert resumed["blocker_reason"] == "message_service_resume_not_supported"
    assert resumed_again["status"] == "resume_requested"


def test_stage_run_start_guards_binding_branch_and_stage_status(tmp_path: Path) -> None:
    repo_root = _init_git_repo(tmp_path)
    handoff_id, dev_client = _enqueue_and_claim(
        tmp_path,
        repo_root=repo_root,
        key="stage-run-start-guards",
    )
    stage = dev_client.post(
        f"/dev-pipeline/backlog/{handoff_id}/materialize",
        json={"worker_id": "dev-worker"},
    ).json()["data"]["stage"]
    stage_client = _client(
        tmp_path,
        environment="dev",
        repo_root=repo_root,
        api_base_url=stage["backend_url"],
        projects_root=tmp_path,
    )
    unbound_session = stage_client.post(
        "/sessions",
        json={"title": "Unbound", "workspace_path": stage["worktree_path"]},
    ).json()["id"]
    unbound = stage_client.post(
        "/dev-pipeline/stages/spec-018/runs/start",
        json={"session_id": unbound_session},
    )
    assert unbound.status_code == 409
    assert unbound.json()["detail"]["code"] == "stage_session_binding_required"

    bound_session = stage_client.post(
        "/dev-pipeline/stages/spec-018/sessions",
        json={"title": "Bound"},
    ).json()["data"]["session_id"]
    _git(Path(stage["worktree_path"]), "checkout", "-b", "dev/spec-018-mismatch")
    branch_mismatch = stage_client.post(
        "/dev-pipeline/stages/spec-018/runs/start",
        json={"session_id": bound_session},
    )
    assert branch_mismatch.status_code == 409
    assert branch_mismatch.json()["detail"]["code"] == "stage_branch_mismatch"
    _git(Path(stage["worktree_path"]), "checkout", stage["branch"])

    state_path = tmp_path / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["stages"]["spec-018"]["status"] = "blocked"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    blocked = stage_client.post(
        "/dev-pipeline/stages/spec-018/runs/start",
        json={"session_id": bound_session},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "stage_not_active"


def test_stage_registration_session_binding_and_lifecycle_plan(tmp_path: Path) -> None:
    client = _client(tmp_path, environment="dev")
    worktree = tmp_path / "codex-cli-mobile-bridge-spec-018"
    worktree.mkdir()

    stage = client.post(
        "/dev-pipeline/stages",
        json={
            "spec_id": "018-dev-prod-stage-promotion-pipeline",
            "worktree_path": str(worktree),
            "owner": "tester",
        },
    ).json()["data"]
    binding = client.post(
        "/dev-pipeline/sessions/bind",
        json={
            "session_id": "session-018",
            "stage_id": "spec-018",
            "workspace_path": str(worktree),
            "branch": "dev/spec-018-dev-prod-stage-promotion-pipeline",
        },
    )
    mismatch = client.post(
        "/dev-pipeline/sessions/bind",
        json={
            "session_id": "session-019",
            "stage_id": "spec-018",
            "workspace_path": str(tmp_path / "other"),
            "branch": "dev/spec-018-dev-prod-stage-promotion-pipeline",
        },
    )
    lifecycle = client.post(
        "/dev-pipeline/stages/spec-018/lifecycle",
        json={"action": "restart", "apply": False},
    ).json()["data"]

    assert stage["stage_id"] == "spec-018"
    assert stage["branch"] == "dev/spec-018-dev-prod-stage-promotion-pipeline"
    assert stage["runtime"]["port"] == 8118
    assert binding.status_code == 200
    assert binding.json()["data"]["backend_url"] == "http://127.0.0.1:8118"
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == "stage_worktree_mismatch"
    assert lifecycle["status"] == "planned"
    assert lifecycle["apply"] is False
    assert [command[0] for command in lifecycle["commands"]] == [
        "scripts/stop_backend.sh",
        "scripts/run_backend_detached.sh",
    ]


def test_stage_registration_rejects_wrong_branch_and_unsafe_worktree(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path, environment="dev")

    wrong_branch = client.post(
        "/dev-pipeline/stages",
        json={
            "spec_id": "018-dev-prod-stage-promotion-pipeline",
            "branch": "dev/018-dev-prod-stage-promotion-pipeline",
        },
    )
    unsafe_worktree = client.post(
        "/dev-pipeline/stages",
        json={
            "spec_id": "018-dev-prod-stage-promotion-pipeline",
            "worktree_path": str(tmp_path / "unexpected"),
        },
    )

    assert wrong_branch.status_code == 409
    assert wrong_branch.json()["detail"]["code"] == "stage_branch_invalid"
    assert unsafe_worktree.status_code == 409
    assert unsafe_worktree.json()["detail"]["code"] == "unsafe_stage_worktree"


def test_stage_runtime_isolated_for_parallel_stages(tmp_path: Path) -> None:
    client = _client(tmp_path, environment="dev")
    (tmp_path / "codex-cli-mobile-bridge-spec-017").mkdir()
    (tmp_path / "codex-cli-mobile-bridge-spec-018").mkdir()

    stage_017 = client.post(
        "/dev-pipeline/stages",
        json={"spec_id": "017-new-project-deterministic-init-pipeline"},
    ).json()["data"]
    stage_018 = client.post(
        "/dev-pipeline/stages",
        json={"spec_id": "018-dev-prod-stage-promotion-pipeline"},
    ).json()["data"]
    restart_018 = client.post(
        "/dev-pipeline/stages/spec-018/lifecycle",
        json={"action": "restart", "apply": False},
    ).json()["data"]

    runtime_017 = stage_017["runtime"]
    runtime_018 = stage_018["runtime"]
    assert runtime_017["port"] == 8117
    assert runtime_018["port"] == 8118
    for key in ["pid_file", "logs_dir", "data_dir", "env_file"]:
        assert runtime_017[key] != runtime_018[key]
    assert restart_018["commands"] == [
        [
            "scripts/stop_backend.sh",
            "--env-file",
            runtime_018["env_file"],
            "--pid-file",
            runtime_018["pid_file"],
        ],
        [
            "scripts/run_backend_detached.sh",
            "--env-file",
            runtime_018["env_file"],
            "--pid-file",
            runtime_018["pid_file"],
            "--runtime-dir",
            str(Path(runtime_018["logs_dir"]).parent),
            "--log-file",
            str(Path(runtime_018["logs_dir"]) / "backend.log"),
        ],
    ]


def test_stage_lifecycle_healthcheck_updates_runtime_without_restart(
    tmp_path: Path,
) -> None:
    server, url = _start_health_server(status_code=200, body='{"ok": true}')
    try:
        client = _client(tmp_path, environment="dev", projects_root=tmp_path)
        stage = client.post(
            "/dev-pipeline/stages",
            json={
                "spec_id": "018-dev-prod-stage-promotion-pipeline",
                "backend_url": url,
            },
        ).json()["data"]

        response = client.post(
            "/dev-pipeline/stages/spec-018/lifecycle",
            json={"action": "healthcheck"},
        )

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["status"] == "healthy"
        assert data["runtime"]["health"] == "healthy"
        assert data["runtime"]["last_healthcheck_at"]
        assert data["healthcheck"]["url"] == f"{url}/health"
        assert stage["runtime"]["last_restart_at"] is None
    finally:
        server.shutdown()
        server.server_close()


def test_stage_lifecycle_healthcheck_reports_failure(tmp_path: Path) -> None:
    server, url = _start_health_server(status_code=503, body='{"ok": false}')
    try:
        client = _client(tmp_path, environment="dev", projects_root=tmp_path)
        client.post(
            "/dev-pipeline/stages",
            json={
                "spec_id": "018-dev-prod-stage-promotion-pipeline",
                "backend_url": url,
            },
        )

        response = client.post(
            "/dev-pipeline/stages/spec-018/lifecycle",
            json={"action": "healthcheck"},
        )

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["status"] == "unhealthy"
        assert data["runtime"]["health"] == "unhealthy"
        assert data["healthcheck"]["status_code"] == 503
    finally:
        server.shutdown()
        server.server_close()


def test_parallel_stage_backend_healthcheck_isolation_preserves_bindings(
    tmp_path: Path,
) -> None:
    server_017, url_017 = _start_health_server(status_code=200)
    server_018, url_018 = _start_health_server(status_code=200)
    try:
        client = _client(tmp_path, environment="dev", projects_root=tmp_path)
        (tmp_path / "codex-cli-mobile-bridge-spec-017").mkdir()
        (tmp_path / "codex-cli-mobile-bridge-spec-018").mkdir()
        client.post(
            "/dev-pipeline/stages",
            json={
                "spec_id": "017-new-project-deterministic-init-pipeline",
                "backend_url": url_017,
            },
        )
        client.post(
            "/dev-pipeline/stages",
            json={
                "spec_id": "018-dev-prod-stage-promotion-pipeline",
                "backend_url": url_018,
            },
        )
        session_017 = client.post("/dev-pipeline/stages/spec-017/sessions", json={})
        session_018 = client.post("/dev-pipeline/stages/spec-018/sessions", json={})
        assert session_017.status_code == 200, session_017.text
        assert session_018.status_code == 200, session_018.text
        healthy_017 = client.post(
            "/dev-pipeline/stages/spec-017/lifecycle",
            json={"action": "healthcheck"},
        ).json()["data"]
        healthy_018 = client.post(
            "/dev-pipeline/stages/spec-018/lifecycle",
            json={"action": "healthcheck"},
        ).json()["data"]
        assert healthy_017["status"] == "healthy"
        assert healthy_018["status"] == "healthy"

        server_017.shutdown()
        server_017.server_close()
        failed_017 = client.post(
            "/dev-pipeline/stages/spec-017/lifecycle",
            json={"action": "healthcheck"},
        ).json()["data"]
        still_healthy_018 = client.post(
            "/dev-pipeline/stages/spec-018/lifecycle",
            json={"action": "healthcheck"},
        ).json()["data"]

        assert failed_017["status"] == "unhealthy"
        assert still_healthy_018["status"] == "healthy"
        binding_017 = client.get(
            f"/dev-pipeline/sessions/{session_017.json()['data']['session_id']}/binding"
        ).json()["data"]
        binding_018 = client.get(
            f"/dev-pipeline/sessions/{session_018.json()['data']['session_id']}/binding"
        ).json()["data"]
        assert binding_017["stage_id"] == "spec-017"
        assert binding_018["stage_id"] == "spec-018"
    finally:
        server_018.shutdown()
        server_018.server_close()


def test_merge_queue_applies_stage_branch_to_dev_main(tmp_path: Path) -> None:
    repo_root = _init_git_repo(tmp_path)
    stage, dev_client = _materialized_stage(
        tmp_path,
        repo_root=repo_root,
        key="merge-success",
    )
    worktree = Path(stage["worktree_path"])
    worktree.joinpath("feature.txt").write_text("stage feature\n", encoding="utf-8")
    _git(worktree, "add", ".")
    _git(worktree, "commit", "-m", "stage feature")
    _checkout_integration_branch(repo_root)
    target_before = _git(repo_root, "rev-parse", "dev/main").stdout.strip()
    source_sha = _git(repo_root, "rev-parse", stage["branch"]).stdout.strip()

    queued = dev_client.post(
        "/dev-pipeline/merge-queue",
        json=_merge_request(stage["stage_id"]),
    )
    assert queued.status_code == 200, queued.text
    merge = queued.json()["data"]
    assert merge["status"] == "queued"
    applied = dev_client.post(
        f"/dev-pipeline/merge-queue/{merge['id']}/apply",
        json={"requested_by": "dev-worker"},
    )

    assert applied.status_code == 200, applied.text
    result = applied.json()["data"]
    assert result["status"] == "merged"
    assert result["commit_ids"]["target_before"] == target_before
    assert result["commit_ids"]["source"] == source_sha
    assert result["commit_ids"]["merge_commit"]
    assert _git(repo_root, "show", "dev/main:feature.txt").stdout == "stage feature\n"
    snapshot = dev_client.get("/dev-pipeline").json()["data"]
    assert snapshot["merge_queue"][0]["status"] == "merged"
    assert snapshot["stages"][0]["integration_status"] == "merged_to_dev_main"
    assert snapshot["backlog"][0]["integration_status"] == "merged_to_dev_main"


def test_merge_apply_records_inline_sdd_doctor_success(tmp_path: Path) -> None:
    repo_root = _init_git_repo(tmp_path)
    _install_fake_sdd_doctor(repo_root, ok=True)
    stage, dev_client = _materialized_stage(
        tmp_path,
        repo_root=repo_root,
        key="merge-sdd-doctor-ok",
    )
    _commit_stage_changes(Path(stage["worktree_path"]), "stage ready")
    _checkout_integration_branch(repo_root)

    merge = dev_client.post(
        "/dev-pipeline/merge-queue",
        json=_merge_request(stage["stage_id"]),
    ).json()["data"]
    applied = dev_client.post(
        f"/dev-pipeline/merge-queue/{merge['id']}/apply",
        json={"requested_by": "dev-worker"},
    )

    assert applied.status_code == 200, applied.text
    result = applied.json()["data"]
    assert result["status"] == "merged"
    assert result["evidence"]["sdd_doctor"]["status"] == "passed"
    assert result["evidence"]["sdd_doctor"]["allowlisted"] is True


def test_merge_apply_blocks_failed_inline_sdd_doctor_without_partial_integration(
    tmp_path: Path,
) -> None:
    repo_root = _init_git_repo(tmp_path)
    _install_fake_sdd_doctor(repo_root, ok=False)
    stage, dev_client = _materialized_stage(
        tmp_path,
        repo_root=repo_root,
        key="merge-sdd-doctor-failed",
    )
    _commit_stage_changes(Path(stage["worktree_path"]), "stage ready")
    _checkout_integration_branch(repo_root)
    target_before = _git(repo_root, "rev-parse", "dev/main").stdout.strip()

    merge = dev_client.post(
        "/dev-pipeline/merge-queue",
        json=_merge_request(stage["stage_id"]),
    ).json()["data"]
    applied = dev_client.post(
        f"/dev-pipeline/merge-queue/{merge['id']}/apply",
        json={"requested_by": "dev-worker"},
    )

    assert applied.status_code == 200, applied.text
    result = applied.json()["data"]
    assert result["status"] == "blocked"
    assert "sdd_doctor_failed" in result["blockers"]
    assert result["evidence"]["sdd_doctor"]["status"] == "failed"
    assert _git(repo_root, "rev-parse", "dev/main").stdout.strip() == target_before


def test_merge_queue_blocks_without_completed_run_or_validated_evidence(
    tmp_path: Path,
) -> None:
    repo_root = _init_git_repo(tmp_path)
    stage, dev_client = _materialized_stage(
        tmp_path,
        repo_root=repo_root,
        key="merge-missing-evidence",
    )
    _commit_stage_changes(Path(stage["worktree_path"]), "stage ready")
    _checkout_integration_branch(repo_root)

    response = dev_client.post(
        "/dev-pipeline/merge-queue",
        json={
            "stage_id": stage["stage_id"],
            "requested_by": "dev-worker",
            "approved": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status"] == "blocked"
    assert "missing_validation_evidence" in payload["blockers"]


def test_merge_queue_blocks_dirty_stage_worktree(tmp_path: Path) -> None:
    repo_root = _init_git_repo(tmp_path)
    stage, dev_client = _materialized_stage(
        tmp_path,
        repo_root=repo_root,
        key="merge-dirty-worktree",
    )
    Path(stage["worktree_path"]).joinpath("dirty.txt").write_text(
        "not committed\n",
        encoding="utf-8",
    )
    _checkout_integration_branch(repo_root)

    response = dev_client.post(
        "/dev-pipeline/merge-queue",
        json=_merge_request(stage["stage_id"]),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status"] == "blocked"
    assert "dirty_worktree" in payload["blockers"]


def test_merge_queue_blocks_stale_stage_branch(tmp_path: Path) -> None:
    repo_root = _init_git_repo(tmp_path)
    stage, dev_client = _materialized_stage(
        tmp_path,
        repo_root=repo_root,
        key="merge-stale",
    )
    _commit_stage_changes(Path(stage["worktree_path"]), "stage ready")
    _git(repo_root, "checkout", "dev/main")
    repo_root.joinpath("base-only.txt").write_text("base moved\n", encoding="utf-8")
    _git(repo_root, "add", "base-only.txt")
    _git(repo_root, "commit", "-m", "advance dev main")
    _checkout_integration_branch(repo_root)

    response = dev_client.post(
        "/dev-pipeline/merge-queue",
        json=_merge_request(stage["stage_id"]),
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status"] == "blocked"
    assert "stale_branch" in payload["blockers"]
    assert "merge_conflict" not in payload["blockers"]


def test_merge_queue_records_conflict_without_partial_integration(
    tmp_path: Path,
) -> None:
    repo_root = _init_git_repo(tmp_path)
    stage, dev_client = _materialized_stage(
        tmp_path,
        repo_root=repo_root,
        key="merge-conflict",
    )
    worktree = Path(stage["worktree_path"])
    worktree.joinpath("conflict.txt").write_text("stage\n", encoding="utf-8")
    _git(worktree, "add", ".")
    _git(worktree, "commit", "-m", "stage conflict")
    _git(repo_root, "checkout", "dev/main")
    repo_root.joinpath("conflict.txt").write_text("base\n", encoding="utf-8")
    _git(repo_root, "add", "conflict.txt")
    _git(repo_root, "commit", "-m", "base conflict")
    target_before = _git(repo_root, "rev-parse", "dev/main").stdout.strip()
    _checkout_integration_branch(repo_root)

    queued = dev_client.post(
        "/dev-pipeline/merge-queue",
        json=_merge_request(stage["stage_id"]),
    )
    assert queued.status_code == 200
    merge = queued.json()["data"]
    assert merge["status"] == "blocked"
    assert "merge_conflict" in merge["blockers"]
    applied = dev_client.post(
        f"/dev-pipeline/merge-queue/{merge['id']}/apply",
        json={"requested_by": "dev-worker"},
    )

    assert applied.status_code == 200
    result = applied.json()["data"]
    assert result["status"] == "blocked"
    assert "merge_conflict" in result["blockers"]
    assert _git(repo_root, "rev-parse", "dev/main").stdout.strip() == target_before
    assert _git(repo_root, "show", "dev/main:conflict.txt").stdout == "base\n"


def test_merge_queue_blocks_failed_validation_with_logs(tmp_path: Path) -> None:
    repo_root = _init_git_repo(tmp_path)
    stage, dev_client = _materialized_stage(
        tmp_path,
        repo_root=repo_root,
        key="merge-validation-failed",
    )
    _commit_stage_changes(Path(stage["worktree_path"]), "stage ready")
    _checkout_integration_branch(repo_root)

    response = dev_client.post(
        "/dev-pipeline/merge-queue",
        json={
            **_merge_request(stage["stage_id"]),
            "validation_passed": False,
            "validation_log": "pytest failed",
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status"] == "blocked"
    assert "validation_failed" in payload["blockers"]
    assert payload["evidence"]["validation_log"] == "pytest failed"


def test_merge_queue_serializes_running_merges(tmp_path: Path) -> None:
    repo_root = _init_git_repo(tmp_path)
    stage_017, dev_client = _materialized_stage(
        tmp_path,
        repo_root=repo_root,
        key="merge-serialize-017",
        payload={
            **_handoff_payload(),
            "title": "Spec 017 handoff",
            "proposed_spec": "017-new-project-deterministic-init-pipeline",
        },
    )
    stage_018, _ = _materialized_stage(
        tmp_path,
        repo_root=repo_root,
        key="merge-serialize-018",
    )
    _commit_stage_changes(Path(stage_017["worktree_path"]), "stage 017 ready")
    _commit_stage_changes(Path(stage_018["worktree_path"]), "stage 018 ready")
    _checkout_integration_branch(repo_root)
    first = dev_client.post(
        "/dev-pipeline/merge-queue",
        json=_merge_request(stage_017["stage_id"]),
    ).json()["data"]
    state_path = tmp_path / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["merge_queue"][first["id"]]["status"] = "applying"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    second = dev_client.post(
        "/dev-pipeline/merge-queue",
        json=_merge_request(stage_018["stage_id"]),
    )

    assert second.status_code == 200
    payload = second.json()["data"]
    assert payload["status"] == "blocked"
    assert "serialized_queue_busy" in payload["blockers"]


def test_prod_and_control_cannot_read_or_mutate_merge_queue(tmp_path: Path) -> None:
    prod = _client(tmp_path, prod_handoff_enabled=True)
    control = _client(tmp_path, environment="control")

    responses = [
        prod.get("/dev-pipeline/merge-queue/merge-spec-018"),
        prod.post(
            "/dev-pipeline/merge-queue/merge-spec-018/apply",
            json={"requested_by": "prod"},
        ),
        control.get("/dev-pipeline/merge-queue/merge-spec-018"),
        control.post(
            "/dev-pipeline/merge-queue/merge-spec-018/apply",
            json={"requested_by": "control"},
        ),
    ]

    assert {response.status_code for response in responses} == {403}


def test_release_channel_validation_rejects_prod_mock_defaults(tmp_path: Path) -> None:
    client = _client(tmp_path, environment="control")

    response = client.post(
        "/dev-pipeline/release-channels/validate",
        json={
            "configs": [
                {
                    "channel": "dev",
                    "api_base_url": "http://127.0.0.1:8118",
                    "app_label": "Codex Bridge DEV",
                    "updater_channel": "dev",
                    "color": "#38BDF8",
                },
                {
                    "channel": "prod",
                    "api_base_url": "https://demo.example.invalid",
                    "app_label": "Codex Bridge",
                    "updater_channel": "prod",
                    "color": "#55D6BE",
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["ok"] is False
    codes = {error["code"] for error in payload["errors"]}
    assert "prod_api_cannot_be_mock_demo_or_local" in codes
    assert "invalid_release_tag_pattern" not in codes
    assert payload["contract"]["prod"]["release_tag_pattern"] == "android-v*"
    assert payload["contract"]["dev"]["release_tag_pattern"] == "android-dev-v*"


def test_release_channel_validation_accepts_dev_stage_and_prod_real(
    tmp_path: Path,
) -> None:
    client = _client(
        tmp_path,
        environment="control",
        api_base_url="https://bridge.example.invalid",
    )

    response = client.post(
        "/dev-pipeline/release-channels/validate",
        json={
            "configs": [
                {
                    "channel": "dev",
                    "app_channel": "dev",
                    "api_base_url": "http://127.0.0.1:8118",
                    "app_label": "Codex Mobile Bridge DEV",
                    "updater_channel": "dev",
                    "color": "#38BDF8",
                    "release_tag_pattern": "android-dev-v*",
                    "stage_id": "spec-018",
                    "branch": "dev/spec-018-dev-prod-stage-promotion-pipeline",
                },
                {
                    "channel": "prod",
                    "app_channel": "prod",
                    "api_base_url": "https://bridge.example.invalid",
                    "app_label": "Codex Mobile Bridge",
                    "updater_channel": "prod",
                    "color": "#55D6BE",
                    "release_tag_pattern": "android-v*",
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["ok"] is True
    assert payload["errors"] == []
    assert payload["backend_config"]["api_base_url"] == (
        "https://bridge.example.invalid"
    )


def test_release_channel_validation_rejects_mixed_channels_and_bad_tags(
    tmp_path: Path,
) -> None:
    client = _client(
        tmp_path,
        environment="control",
        api_base_url="https://bridge.example.invalid",
    )

    response = client.post(
        "/dev-pipeline/release-channels/validate",
        json={
            "configs": [
                {
                    "channel": "prod",
                    "app_channel": "dev",
                    "api_base_url": "http://127.0.0.1:8000",
                    "app_label": "Codex Mobile Bridge DEV",
                    "updater_channel": "dev",
                    "color": "",
                    "release_tag": "android-dev-v1.2.3",
                    "release_tag_pattern": "android-dev-v*",
                },
                {
                    "channel": "dev",
                    "app_channel": "dev",
                    "api_base_url": "http://127.0.0.1:8118",
                    "app_label": "Codex Mobile Bridge",
                    "updater_channel": "prod",
                    "color": "#38BDF8",
                    "release_tag": "android-v1.2.3",
                    "release_tag_pattern": "android-v*",
                },
            ],
        },
    )

    assert response.status_code == 200
    codes = {error["code"] for error in response.json()["data"]["errors"]}
    assert {
        "mixed_app_channel",
        "prod_api_cannot_be_mock_demo_or_local",
        "invalid_prod_updater_channel",
        "invalid_prod_app_label",
        "missing_release_identity",
        "invalid_environment_color",
        "invalid_release_tag_pattern",
        "invalid_dev_updater_channel",
        "invalid_dev_app_label",
        "invalid_release_tag",
    } <= codes


def test_promotion_and_prod_update_gates_fail_closed(tmp_path: Path) -> None:
    client = _client(tmp_path, environment="control", promotion_enabled=False)

    promotion = client.post(
        "/dev-pipeline/promotions",
        json={
            "requested_by": "tester",
            "target": "prod",
            "release_tag": "android-v1.2.3",
            "user_approved": True,
        },
    )
    update = client.post(
        "/dev-pipeline/prod-update/status",
        json={"prepared_update_id": "update-1"},
    )

    assert promotion.status_code == 409
    assert promotion.json()["detail"]["code"] == "promotion_disabled"
    assert update.status_code == 200
    assert update.json()["data"]["state"] == "waiting_for_idle"
    assert update.json()["data"]["force_restart_requires_strong_confirmation"] is True
    snapshot = _client(tmp_path, environment="dev").get("/dev-pipeline").json()["data"]
    assert snapshot["prod_updates"][0]["prepared_update_id"] == "update-1"
    assert snapshot["prod_updates"][0]["state"] == "waiting_for_idle"


def test_prod_update_idle_becomes_auto_update_eligible_without_restart(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path, environment="control")
    client.post("/maintenance/drain", json={"requested": True})

    response = client.post(
        "/dev-pipeline/prod-update/prepare",
        json={
            "prepared_update_id": "update-eligible",
            "update_version": "2026.07.13",
            "requested_by": "control",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["state"] == "auto_update_eligible"
    assert data["notification"] is True
    assert data["executor"]["status"] == "planned"
    assert data["executor"]["command"]["allowlisted"] is True
    assert data["update_version"] == "2026.07.13"


def test_prod_update_busy_backend_exposes_blockers(tmp_path: Path) -> None:
    service = _prod_update_service(tmp_path, environment="control")

    update = service.prod_update_status(
        prepared_update_id="update-busy",
        update_version="busy",
        requested_by="control",
        drain_status=BackendDrainStatus(
            requested=True,
            active_jobs=[],
            active_session_ids=["session-1"],
            active_agent_run_ids=["run-1"],
            in_flight_message_ids=["message-1"],
            pending_follow_up_message_ids=["reserved-reviewer"],
            sdd_codex_job_ids=["job-sdd"],
            project_factory_job_ids=["job-project"],
            domain_factory_job_ids=["job-domain"],
            unknown_blockers=["background_tasks"],
        ),
    )

    assert update["state"] == "waiting_for_idle"
    assert {
        "active_sessions",
        "in_flight_messages",
        "active_agent_runs",
        "pending_follow_ups",
        "sdd_codex_jobs",
        "project_factory_jobs",
        "domain_factory_jobs",
        "unknown:background_tasks",
    } <= set(update["blockers"])
    assert update["quiescence"]["pending_follow_up_message_ids"] == [
        "reserved-reviewer"
    ]


def test_prod_update_force_requires_strong_confirmation_and_records_evidence(
    tmp_path: Path,
) -> None:
    service = _prod_update_service(tmp_path, environment="control")
    drain = BackendDrainStatus(
        requested=True,
        active_jobs=[],
        active_session_ids=["session-1"],
        in_flight_message_ids=["message-1"],
    )
    service.prod_update_status(
        prepared_update_id="update-force",
        update_version="force",
        requested_by="control",
        drain_status=drain,
    )

    rejected = service.prod_update_status(
        prepared_update_id=None,
        force_requested=True,
        requested_by="control",
        strong_confirmation="wrong",
        drain_status=drain,
    )
    accepted = service.prod_update_status(
        prepared_update_id=None,
        force_requested=True,
        requested_by="control",
        strong_confirmation="FORCE PROD UPDATE update-force",
        drain_status=drain,
    )

    assert rejected["state"] == "blocked"
    assert rejected["blockers"] == ["strong_confirmation_required"]
    assert accepted["state"] == "force_requested"
    assert accepted["interruption_evidence"]["drain"]["active_session_ids"] == [
        "session-1"
    ]
    assert accepted["interruption_evidence"]["post_validation_plan"]


def test_prod_update_failed_executor_and_acknowledgement(tmp_path: Path) -> None:
    service = _prod_update_service(
        tmp_path,
        environment="control",
        executor_enabled=True,
    )
    drain = BackendDrainStatus(
        requested=True,
        active_jobs=[],
        active_session_ids=[],
        in_flight_message_ids=[],
    )
    failed = service.prod_update_status(
        prepared_update_id="update-fail",
        requested_by="control",
        drain_status=drain,
        execute=True,
        executor_result={"status": "failed", "stderr": "boom"},
    )
    completed = service.prod_update_status(
        prepared_update_id="update-ok",
        requested_by="control",
        drain_status=drain,
        execute=True,
        executor_result={"status": "completed", "stdout": "ok"},
    )
    acknowledged = service.prod_update_status(
        prepared_update_id=None,
        acknowledged=True,
        requested_by="prod",
        drain_status=drain,
    )

    assert failed["state"] == "failed"
    assert failed["notification"] is True
    assert failed["executor"]["stderr"] == "boom"
    assert completed["state"] == "updated_pending_ack"
    assert acknowledged["state"] == "acknowledged"
    assert acknowledged["notification"] is False


def test_prod_update_access_allows_prod_control_and_blocks_dev(tmp_path: Path) -> None:
    prod = _client(tmp_path, environment="prod")
    control = _client(tmp_path, environment="control")
    dev = _client(tmp_path, environment="dev")

    prod_status = prod.get("/dev-pipeline/prod-update/status")
    control_prepare = control.post(
        "/dev-pipeline/prod-update/prepare",
        json={"prepared_update_id": "update-access"},
    )
    prod_prepare = prod.post(
        "/dev-pipeline/prod-update/prepare",
        json={"prepared_update_id": "update-prod-forbidden"},
    )
    dev_status = dev.get("/dev-pipeline/prod-update/status")

    assert prod_status.status_code == 200
    assert control_prepare.status_code == 200
    assert prod_prepare.status_code == 403
    assert dev_status.status_code == 403


def test_promotion_orchestrator_blocks_outside_control_environment(
    tmp_path: Path,
) -> None:
    prod = _client(tmp_path, prod_handoff_enabled=True, promotion_enabled=True)
    dev = _client(tmp_path, environment="dev", promotion_enabled=True)

    responses = [
        prod.post(
            "/dev-pipeline/promotions",
            json={
                "requested_by": "tester",
                "target": "prod",
                "release_tag": "android-v1.2.3",
                "user_approved": True,
            },
        ),
        dev.get("/dev-pipeline/promotions/promotion-1"),
        dev.post(
            "/dev-pipeline/promotions/promotion-1/advance",
            json={"requested_by": "tester"},
        ),
    ]

    assert {response.status_code for response in responses} == {403}


def test_promotion_orchestrator_blocks_preflight_failures(tmp_path: Path) -> None:
    repo_root = _init_git_repo(tmp_path)
    client = _promotion_client(tmp_path, repo_root=repo_root)

    missing_merge = client.post(
        "/dev-pipeline/promotions",
        json=_promotion_request(),
    ).json()["data"]
    _seed_validated_dev_main_merge(tmp_path, repo_root)
    invalid_tag = client.post(
        "/dev-pipeline/promotions",
        json={**_promotion_request(), "release_tag": "v1.2.3"},
    ).json()["data"]
    missing_approval = client.post(
        "/dev-pipeline/promotions",
        json={**_promotion_request(), "user_approved": False},
    ).json()["data"]
    repo_root.joinpath("dirty.txt").write_text("dirty\n", encoding="utf-8")
    dirty = client.post(
        "/dev-pipeline/promotions",
        json=_promotion_request(),
    ).json()["data"]

    assert missing_merge["state"] == "blocked"
    assert "missing_validated_dev_main_merge" in missing_merge["blockers"]
    assert invalid_tag["state"] == "blocked"
    assert "invalid_or_missing_prod_release_tag" in invalid_tag["blockers"]
    assert missing_approval["state"] == "approval_required"
    assert "missing_user_approval" in missing_approval["blockers"]
    assert dirty["state"] == "blocked"
    assert "dirty_repository" in dirty["blockers"]


def test_promotion_orchestrator_blocks_bad_prod_config_and_missing_secret(
    tmp_path: Path,
) -> None:
    repo_root = _init_git_repo(tmp_path)
    _seed_validated_dev_main_merge(tmp_path, repo_root)
    mock_config = _client(
        tmp_path,
        environment="control",
        repo_root=repo_root,
        api_base_url="http://localhost:8000",
        promotion_enabled=True,
        app_update_github_token="token",
    )
    missing_secret = _client(
        tmp_path,
        environment="control",
        repo_root=repo_root,
        api_base_url="https://bridge.example.invalid",
        promotion_enabled=True,
    )

    mock_response = mock_config.post(
        "/maintenance/drain",
        json={"requested": True},
    )
    secret_response = missing_secret.post(
        "/maintenance/drain",
        json={"requested": True},
    )
    assert mock_response.status_code == 200
    assert secret_response.status_code == 200
    mock_promotion = mock_config.post(
        "/dev-pipeline/promotions",
        json=_promotion_request(),
    ).json()["data"]
    secret_promotion = missing_secret.post(
        "/dev-pipeline/promotions",
        json=_promotion_request(),
    ).json()["data"]

    assert mock_promotion["state"] == "blocked"
    assert "prod_api_placeholder" in mock_promotion["blockers"]
    assert "release_channel_validation_failed" in mock_promotion["blockers"]
    assert "prod_api_cannot_be_mock_demo_or_local" in mock_promotion["blockers"]
    assert secret_promotion["state"] == "blocked"
    assert "missing_app_update_github_token" in secret_promotion["blockers"]


def test_promotion_orchestrator_blocks_active_drain_directly(tmp_path: Path) -> None:
    repo_root = _init_git_repo(tmp_path)
    _seed_validated_dev_main_merge(tmp_path, repo_root)
    service = _promotion_service(tmp_path, repo_root=repo_root)

    promotion = service.request_promotion(
        requested_by="tester",
        target="prod",
        release_tag="android-v1.2.3",
        user_approved=True,
        dry_run=True,
        drain_status=BackendDrainStatus(
            requested=True,
            active_jobs=[],
            active_session_ids=["session-active"],
            in_flight_message_ids=[],
        ),
    )

    assert promotion["state"] == "drain_waiting"
    assert "prod_not_quiescent" in promotion["blockers"]
    assert promotion["evidence"]["drain"]["active_session_ids"] == ["session-active"]


def test_promotion_orchestrator_dry_run_success_records_allowlisted_evidence(
    tmp_path: Path,
) -> None:
    repo_root = _init_git_repo(tmp_path)
    _seed_validated_dev_main_merge(tmp_path, repo_root)
    client = _promotion_client(tmp_path, repo_root=repo_root)
    client.post("/maintenance/drain", json={"requested": True})

    response = client.post(
        "/dev-pipeline/promotions",
        json=_promotion_request(),
    )

    assert response.status_code == 200, response.text
    promotion = response.json()["data"]
    assert promotion["state"] == "dry_run_passed"
    assert promotion["deployed"] is False
    assert promotion["release_published"] is False
    assert promotion["next_required_action"] == "prepare_rollback_plan"
    assert promotion["evidence"]["merge"]["validated"] is True
    assert promotion["evidence"]["release_config"]["app_update_github_token"] == (
        "[present]"
    )
    assert all(command["allowlisted"] for command in promotion["planned_commands"])
    assert {
        command["name"] for command in promotion["planned_commands"]
    } >= {
        "sdd_doctor",
        "backend_post_release_validation",
        "android_release_workflow",
        "release_channel_validation",
    }
    assert any(
        command["status"] == "blocked_real_release"
        for command in promotion["planned_commands"]
    )


def test_promotion_advance_respects_approval_and_drain_order(
    tmp_path: Path,
) -> None:
    repo_root = _init_git_repo(tmp_path)
    _seed_validated_dev_main_merge(tmp_path, repo_root)
    client = _promotion_client(tmp_path, repo_root=repo_root)
    requested = client.post(
        "/dev-pipeline/promotions",
        json={**_promotion_request(), "user_approved": False},
    ).json()["data"]

    no_approval = client.post(
        f"/dev-pipeline/promotions/{requested['id']}/advance",
        json={"requested_by": "tester", "user_approved": False},
    ).json()["data"]
    approved = client.post(
        f"/dev-pipeline/promotions/{requested['id']}/advance",
        json={"requested_by": "tester", "user_approved": True},
    ).json()["data"]
    client.post("/maintenance/drain", json={"requested": True})
    drained = client.post(
        f"/dev-pipeline/promotions/{requested['id']}/advance",
        json={"requested_by": "tester", "user_approved": True},
    ).json()["data"]
    rollback_ready = client.post(
        f"/dev-pipeline/promotions/{requested['id']}/advance",
        json={"requested_by": "tester", "user_approved": True},
    ).json()["data"]

    assert no_approval["state"] == "approval_required"
    assert approved["state"] == "drain_waiting"
    assert drained["state"] == "dry_run_passed"
    assert rollback_ready["state"] == "rollback_ready"
    assert rollback_ready["release_published"] is False
    assert rollback_ready["next_required_action"] == (
        "await_explicit_real_promotion_instruction"
    )


def test_promotion_payload_rejects_ad_hoc_command_execution(tmp_path: Path) -> None:
    client = _promotion_client(tmp_path, repo_root=_init_git_repo(tmp_path))

    response = client.post(
        "/dev-pipeline/promotions",
        json={**_promotion_request(), "command": "git push origin prod"},
    )

    assert response.status_code == 422


def test_dev_pipeline_end_to_end_handoff_to_update_gate_is_deterministic(
    tmp_path: Path,
) -> None:
    repo_root = _init_git_repo(tmp_path)
    prod_client = _client(
        tmp_path,
        repo_root=repo_root,
        prod_handoff_enabled=True,
    )
    handoff = prod_client.post(
        "/dev-pipeline/handoffs",
        json=_handoff_payload_with_grant(prod_client),
        headers={"X-Idempotency-Key": "e2e-handoff"},
    )
    assert handoff.status_code == 200, handoff.text
    handoff_id = handoff.json()["data"]["id"]
    assert prod_client.get("/dev-pipeline").status_code == 403
    assert prod_client.get("/dev-pipeline/projection").status_code == 403

    dev_client = _client(tmp_path, environment="dev", repo_root=repo_root)
    claim = dev_client.post(
        "/dev-pipeline/backlog/claim",
        json={"worker_id": "e2e-worker"},
    )
    assert claim.status_code == 200, claim.text
    materialized = dev_client.post(
        f"/dev-pipeline/backlog/{handoff_id}/materialize",
        json={"worker_id": "e2e-worker"},
    )
    assert materialized.status_code == 200, materialized.text
    stage = materialized.json()["data"]["stage"]

    stage_client = _client(
        tmp_path,
        environment="dev",
        repo_root=repo_root,
        api_base_url=stage["backend_url"],
        projects_root=tmp_path,
    )
    session = stage_client.post(
        "/dev-pipeline/stages/spec-018/sessions",
        json={"title": "E2E stage"},
    )
    assert session.status_code == 200, session.text
    session_id = session.json()["data"]["session_id"]
    run = stage_client.post(
        "/dev-pipeline/stages/spec-018/runs/start",
        json={
            "session_id": session_id,
            "requested_by": "e2e-worker",
            "initial_prompt": "Implement the deterministic E2E stage change.",
        },
    )
    assert run.status_code == 200, run.text
    assert run.json()["data"]["job_id"]

    state_path = tmp_path / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    for item in state["runs"].values():
        if item["stage_id"] == stage["stage_id"]:
            item["status"] = "completed"
            item["finished_at"] = "2026-07-13T00:00:00Z"
            item["evidence"]["tests_executed"] = ["pytest e2e"]
            item["evidence"]["summary"] = "E2E fake provider completed."
    state_path.write_text(json.dumps(state), encoding="utf-8")

    _commit_stage_changes(Path(stage["worktree_path"]), "e2e stage changes")
    _checkout_integration_branch(repo_root)
    merge = dev_client.post(
        "/dev-pipeline/merge-queue",
        json=_merge_request(stage["stage_id"]),
    )
    assert merge.status_code == 200, merge.text
    applied = dev_client.post(
        f"/dev-pipeline/merge-queue/{merge.json()['data']['id']}/apply",
        json={
            "requested_by": "e2e-worker",
            "evidence_validated": True,
            "validation_passed": True,
            "tests_executed": ["pytest e2e"],
        },
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["data"]["status"] == "merged"

    _git(repo_root, "checkout", "dev/main")
    control_client = _promotion_client(tmp_path, repo_root=repo_root)
    control_client.post("/maintenance/drain", json={"requested": True})
    release_validation = control_client.post(
        "/dev-pipeline/release-channels/validate",
        json={
            "configs": [
                {
                    "channel": "dev",
                    "app_channel": "dev",
                    "api_base_url": stage["backend_url"],
                    "app_label": "Codex Mobile Bridge DEV",
                    "updater_channel": "dev",
                    "color": "#38BDF8",
                    "release_tag_pattern": "android-dev-v*",
                    "stage_id": stage["stage_id"],
                    "branch": stage["branch"],
                },
                {
                    "channel": "prod",
                    "app_channel": "prod",
                    "api_base_url": "https://bridge.example.invalid",
                    "app_label": "Codex Mobile Bridge",
                    "updater_channel": "prod",
                    "color": "#55D6BE",
                    "release_tag_pattern": "android-v*",
                },
            ],
        },
    )
    assert release_validation.status_code == 200, release_validation.text
    assert release_validation.json()["data"]["ok"] is True
    promotion = control_client.post(
        "/dev-pipeline/promotions",
        json=_promotion_request(),
    )
    assert promotion.status_code == 200, promotion.text
    assert promotion.json()["data"]["state"] in {"dry_run_passed", "rollback_ready"}
    update = control_client.post(
        "/dev-pipeline/prod-update/prepare",
        json={
            "prepared_update_id": "e2e-update",
            "update_version": "2026.07.13",
            "requested_by": "control",
        },
    )
    assert update.status_code == 200, update.text
    assert update.json()["data"]["state"] == "auto_update_eligible"

    projection = control_client.get("/dev-pipeline/projection")
    assert projection.status_code == 200, projection.text
    data = projection.json()["data"]
    assert data["workbench"]["backlog_items"][0]["handoff_id"] == handoff_id
    assert data["workbench"]["active_stages"][0]["stage_id"] == stage["stage_id"]
    assert data["workbench"]["stage_runs"][0]["status"] == "completed"
    assert data["workbench"]["merge_status"][0]["status"] == "merged"
    assert data["workbench"]["promotion_status"][0]["state"] in {
        "dry_run_passed",
        "rollback_ready",
    }
    assert data["release_validations"][0]["status"] == "passed"
    assert data["prod_updates"][0]["state"] == "auto_update_eligible"
    assert prod_client.get("/dev-pipeline/projection").status_code == 403
    assert (
        prod_client.post(
            "/dev-pipeline/merge-queue",
            json=_merge_request(stage["stage_id"]),
        ).status_code
        == 403
    )


def _client(
    tmp_path: Path,
    *,
    environment: str = "prod",
    repo_root: Path | None = None,
    api_base_url: str = "http://localhost:8000",
    projects_root: Path | None = None,
    prod_handoff_enabled: bool = False,
    promotion_enabled: bool = False,
    pipeline_enabled: bool = True,
    app_update_github_token: str | None = None,
    codex_command: str = _FAKE_CODEX,
    dev_notify_url: str | None = None,
    auto_runner_enabled: bool = False,
) -> TestClient:
    projects_root = projects_root or tmp_path / "projects"
    projects_root.mkdir(exist_ok=True)
    repo_root = repo_root or tmp_path / "codex-cli-mobile-bridge"
    repo_root.mkdir(exist_ok=True)
    settings = Settings(
        codex_command=codex_command,
        codex_use_exec=False,
        codex_workdir=str(repo_root),
        api_base_url=api_base_url,
        projects_root=str(projects_root),
        chat_store_backend="memory",
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
        audio_transcription_backend="disabled",
        speech_synthesis_backend="disabled",
        feedback_source_workspace_aliases="",
        dev_pipeline_state_path=str(tmp_path / "state.json"),
        dev_pipeline_runtime_root=str(tmp_path / "runtime"),
        dev_pipeline_enabled=pipeline_enabled,
        bridge_environment=environment,
        bridge_app_channel=environment if environment in {"dev", "prod"} else "prod",
        bridge_updater_channel=environment
        if environment in {"dev", "prod"}
        else "prod",
        bridge_app_label=(
            "Codex Mobile Bridge DEV" if environment == "dev" else "Codex Mobile Bridge"
        ),
        dev_pipeline_prod_handoff_enabled=prod_handoff_enabled,
        dev_pipeline_promotion_enabled=promotion_enabled,
        dev_pipeline_dev_notify_url=dev_notify_url,
        dev_pipeline_auto_runner_enabled=auto_runner_enabled,
        app_update_github_token=app_update_github_token,
    )
    return TestClient(create_app(settings))


def _init_git_repo(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    repo_root = tmp_path / "codex-cli-mobile-bridge"
    repo_root.mkdir()
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "tests@example.invalid")
    _git(repo_root, "config", "user.name", "Tests")
    _git(repo_root, "checkout", "-b", "dev/main")
    repo_root.joinpath("README.md").write_text("test repo\n", encoding="utf-8")
    repo_root.joinpath("specs").mkdir()
    repo_root.joinpath("specs/.gitkeep").write_text("", encoding="utf-8")
    _git(repo_root, "add", "README.md", "specs/.gitkeep")
    _git(repo_root, "commit", "-m", "initial")
    return repo_root


def _install_fake_sdd_doctor(repo_root: Path, *, ok: bool) -> None:
    script = repo_root / "scripts/codex_bridge_sdd_doctor.py"
    script.parent.mkdir()
    script.write_text(
        "from __future__ import annotations\n"
        "import json\n"
        "import sys\n"
        f"ok = {ok!r}\n"
        "print(json.dumps({'ok': ok, 'summary': {'fail': 0 if ok else 1}}))\n"
        "raise SystemExit(0 if ok else 1)\n",
        encoding="utf-8",
    )
    _git(repo_root, "add", "scripts/codex_bridge_sdd_doctor.py")
    _git(repo_root, "commit", "-m", "add fake sdd doctor")


def _start_health_server(
    *,
    status_code: int = 200,
    body: str = '{"ok": true}',
) -> tuple[HTTPServer, str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
            if self.path != "/health":
                self.send_response(404)
                self.end_headers()
                return
            encoded = body.encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def _enqueue_and_claim(
    tmp_path: Path,
    *,
    repo_root: Path,
    key: str,
    payload: dict[str, object] | None = None,
) -> tuple[str, TestClient]:
    prod_client = _client(
        tmp_path,
        repo_root=repo_root,
        prod_handoff_enabled=True,
    )
    handoff = prod_client.post(
        "/dev-pipeline/handoffs",
        json=_handoff_payload_with_grant(prod_client, payload),
        headers={"X-Idempotency-Key": key},
    )
    assert handoff.status_code == 200, handoff.text
    handoff_id = handoff.json()["data"]["id"]
    dev_client = _client(tmp_path, environment="dev", repo_root=repo_root)
    claim = dev_client.post(
        "/dev-pipeline/backlog/claim",
        json={"worker_id": "dev-worker"},
    )
    assert claim.status_code == 200, claim.text
    assert claim.json()["data"]["handoff_id"] == handoff_id
    return handoff_id, dev_client


def _materialized_stage(
    tmp_path: Path,
    *,
    repo_root: Path,
    key: str,
    payload: dict[str, object] | None = None,
) -> tuple[dict[str, object], TestClient]:
    handoff_id, dev_client = _enqueue_and_claim(
        tmp_path,
        repo_root=repo_root,
        key=key,
        payload=payload,
    )
    response = dev_client.post(
        f"/dev-pipeline/backlog/{handoff_id}/materialize",
        json={"worker_id": "dev-worker"},
    )
    assert response.status_code == 200, response.text
    stage = response.json()["data"]["stage"]
    assert stage["status"] == "active"
    return stage, dev_client


def _commit_stage_changes(worktree: Path, message: str) -> None:
    worktree.joinpath("stage-ready.txt").write_text(f"{message}\n", encoding="utf-8")
    _git(worktree, "add", ".")
    _git(worktree, "commit", "-m", message)


def _checkout_integration_branch(repo_root: Path) -> None:
    _git(repo_root, "checkout", "-B", "integration-base")


def _merge_request(stage_id: object) -> dict[str, object]:
    return {
        "stage_id": str(stage_id),
        "requested_by": "dev-worker",
        "approved": True,
        "evidence_validated": True,
        "validation_passed": True,
        "tests_executed": ["pytest tests/test_dev_pipeline.py -q"],
    }


def _promotion_client(tmp_path: Path, *, repo_root: Path) -> TestClient:
    return _client(
        tmp_path,
        environment="control",
        repo_root=repo_root,
        api_base_url="https://bridge.example.invalid",
        promotion_enabled=True,
        app_update_github_token="token",
    )


def _promotion_request() -> dict[str, object]:
    return {
        "requested_by": "tester",
        "target": "prod",
        "release_tag": "android-v1.2.3",
        "user_approved": True,
        "dry_run": True,
    }


def _seed_validated_dev_main_merge(tmp_path: Path, repo_root: Path) -> None:
    sha = _git(repo_root, "rev-parse", "dev/main").stdout.strip()
    state_path = tmp_path / "state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    else:
        state = {
            "kind": "codex.devPipelineState",
            "version": 1,
            "handoffs": {},
            "backlog": {},
            "specs": {},
            "stages": {},
            "sessions": {},
            "runs": {},
            "merge_queue": {},
            "promotions": {},
            "prod_updates": {},
            "events": [],
        }
    state["merge_queue"]["merge-seeded"] = {
        "id": "merge-seeded",
        "stage_id": "spec-018",
        "spec_id": "018-dev-prod-stage-promotion-pipeline",
        "source_branch": "dev/spec-018-dev-prod-stage-promotion-pipeline",
        "target_branch": "dev/main",
        "status": "merged",
        "commit_ids": {
            "merge_commit": sha,
            "target_after": sha,
            "source": sha,
        },
        "updated_at": "2026-07-13T00:00:00Z",
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")


def _promotion_service(tmp_path: Path, *, repo_root: Path) -> DevPipelineService:
    return DevPipelineService(
        state_path=str(tmp_path / "state.json"),
        runtime_root=str(tmp_path / "runtime"),
        repository_root=str(repo_root),
        environment="control",
        backend_url="https://bridge.example.invalid",
        app_channel="prod",
        app_label="Codex Mobile Bridge",
        updater_channel="prod",
        color="#55D6BE",
        enabled=True,
        promotion_enabled=True,
        app_update_registry_path=str(
            Path("backend/app/infrastructure/config/app_updates.json").resolve()
        ),
        app_update_github_token_present=True,
    )


def _prod_update_service(
    tmp_path: Path,
    *,
    environment: str,
    executor_enabled: bool = False,
) -> DevPipelineService:
    repo_root = tmp_path / "codex-cli-mobile-bridge"
    repo_root.mkdir(exist_ok=True)
    return DevPipelineService(
        state_path=str(tmp_path / "state.json"),
        runtime_root=str(tmp_path / "runtime"),
        repository_root=str(repo_root),
        environment=environment,  # type: ignore[arg-type]
        backend_url="https://bridge.example.invalid",
        app_channel="prod",
        app_label="Codex Mobile Bridge",
        updater_channel="prod",
        color="#55D6BE",
        enabled=True,
        prod_update_executor_enabled=executor_enabled,
    )


def _handoff_payload_with_grant(
    client: TestClient,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    granted_payload = dict(payload or _handoff_payload())
    draft = client.post(
        "/dev-pipeline/handoffs/draft",
        json={"title": str(granted_payload.get("title") or "DEV handoff")},
    )
    assert draft.status_code == 200, draft.text
    data = draft.json()["data"]
    ready = _ready_handoff_draft(client, str(data["draft_id"]))
    granted_payload["draft_token"] = ready["draft_token"]
    return granted_payload


def _ready_handoff_draft(client: TestClient, draft_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 3
    last_response = None
    while time.monotonic() < deadline:
        response = client.get(f"/dev-pipeline/handoffs/drafts/{draft_id}")
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        if data["draft_status"] == "ready":
            return data
        if data["draft_status"] == "failed":
            raise AssertionError(data.get("draft_error"))
        last_response = data
        time.sleep(0.05)
    raise AssertionError(f"Handoff draft did not become ready: {last_response}")


def _handoff_payload() -> dict[str, object]:
    return {
        "kind": "bridge.devHandoff",
        "version": 1,
        "source_environment": "prod",
        "target_environment": "dev",
        "operation": "enqueue_only",
        "title": "Fix bridge update gate",
        "problem": "The bridge should wait for idle work before updating.",
        "context": "Current PROD session saw an update while a reviewer follow-up was pending.",
        "evidence": [{"kind": "note", "text": "reviewer pending"}],
        "proposed_spec": "018-dev-prod-stage-promotion-pipeline",
        "proposed_plan": "11-prod-backend-update-idle-gate",
        "proposed_tasks": ["T061", "T062", "T063"],
        "acceptance_criteria": "Update waits until drain status is quiescent.",
        "regression_tests": ["busy backend waits"],
        "risks": ["interrupting active work"],
        "created_from_session_id": "session-prod",
        "created_by_action": "prod_dev_handoff",
    }
