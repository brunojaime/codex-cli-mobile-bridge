from __future__ import annotations

import os
import textwrap
from pathlib import Path
import json

from fastapi.testclient import TestClient

from backend.app.infrastructure.config.settings import Settings
from backend.app.main import create_app


def test_sdd_workbench_view_returns_health_compliance_and_context_preview(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_project(project, related_specs=2, related_diagrams=2)
    client = _client(projects_root, codex_workdir=str(project))

    response = client.get(
        "/sdd/workbench/view",
        params={"workspace_path": str(project), "query": "checkout"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "codex.sddWorkbenchView"
    assert payload["workspace_name"] == "demo"
    assert payload["health"]["spec_count"] == 2
    assert payload["health"]["diagram_count"] == 3
    assert payload["standards_compliance"]["standard_id"] == "workbench-sdd/v1"
    assert payload["feature_specs"][0]["id"] == "001-demo"
    assert payload["feature_specs"][0]["lifecycle_status"] == "draft"
    assert payload["feature_specs"][0]["traceability_status"] == "linked"
    assert payload["feature_specs"][0]["plan_count"] == 1
    assert payload["feature_specs"][0]["task_file_count"] == 1
    baselines = {item["path"]: item for item in payload["baselines"]}
    assert baselines["architecture/components.mmd"]["protected"] is True
    assert baselines["domain/glossary.md"]["artifact_type"] == "domain"
    assert baselines["data/persistence-model.md"]["artifact_type"] == "data"
    traceability = payload["traceability_matrix"][0]
    assert traceability["status"] == "linked"
    assert traceability["requirement_count"] == 1
    assert traceability["task_count"] == 1
    assert traceability["diagram_count"] == 1
    assert payload["impact_queue"][0]["artifact_path"] == "architecture/components.mmd"
    assert payload["impact_queue"][0]["status"] == "review-required"
    preview = payload["context_preview"]
    assert preview["status"] == "ready"
    assert preview["preset"] == "new-feature"
    assert preview["index_status"] == "regenerated"
    assert "codex-bridge.yaml" in preview["required_files"]
    assert ".sdd/context-index.yaml" in preview["required_files"]
    assert preview["related_specs"]
    assert preview["related_diagrams"]
    assert "scan_every_full_spec_body" in preview["blocked_reads"]
    assert "Do not scan every full spec body as fallback." in preview["prompt"]
    assert "architecture/components.mmd" in preview["prompt"]
    assert any(
        "Workbench default -> project profile -> project overrides" in item
        for item in preview["routing_decisions"]
    )


def test_sdd_workbench_view_exposes_preview_readiness_contract(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_project(project)
    (project / "release").mkdir()
    (project / "release/preview-runtime.json").write_text(
        json.dumps(
            {
                "sourceApp": "demo",
                "previewUrl": "https://preview.nienfos.com/demo",
                "apiBaseUrl": "https://preview.nienfos.com/demo/api",
                "runtimeProfile": "preview",
                "apiRuntime": "cloudflare_preview",
                "releaseChannel": "prerelease",
                "releaseTagPattern": "android-preview-v*",
                "apkAssetPattern": "app-release.apk",
                "latestAssetName": "app-release.apk",
                "productionReady": False,
                "mockOrDemo": False,
                "bridge": {"verificationEndpoint": "/installable-apps/demo"},
            }
        ),
        encoding="utf-8",
    )
    client = _client(projects_root, codex_workdir=str(project))

    response = client.get("/sdd/workbench/view", params={"workspace_path": str(project)})

    assert response.status_code == 200
    readiness = response.json()["preview_readiness"]
    assert readiness["available"] is True
    assert readiness["status"] == "ready"
    assert readiness["previewUrl"] == "https://preview.nienfos.com/demo"
    assert readiness["apiBaseUrl"] == "https://preview.nienfos.com/demo/api"
    assert readiness["runtimeProfile"] == "preview"
    assert readiness["releaseChannel"] == "prerelease"
    assert readiness["releaseTagPattern"] == "android-preview-v*"
    assert readiness["androidPreviewApk"] == "app-release.apk"
    assert readiness["bridgeRegistrationRequired"] is True
    assert readiness["productionReady"] is False
    assert readiness["mockOrDemo"] is False
    assert readiness["blockers"] == []
    assert readiness["bridge"]["verificationEndpoint"] == "/installable-apps/demo"


def test_sdd_workbench_view_blocks_stale_preview_release_channel(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_project(project)
    (project / "release").mkdir()
    (project / "release/preview-runtime.json").write_text(
        json.dumps(
            {
                "sourceApp": "demo",
                "previewUrl": "https://preview.nienfos.com/demo",
                "apiBaseUrl": "https://preview.nienfos.com/demo/api",
                "runtimeProfile": "preview",
                "apiRuntime": "cloudflare_preview",
                "releaseChannel": "preview",
                "releaseTagPattern": "android-preview-v*",
                "productionReady": False,
                "mockOrDemo": False,
            }
        ),
        encoding="utf-8",
    )
    client = _client(projects_root, codex_workdir=str(project))

    response = client.get("/sdd/workbench/view", params={"workspace_path": str(project)})

    assert response.status_code == 200
    readiness = response.json()["preview_readiness"]
    assert readiness["available"] is True
    assert readiness["status"] == "blocked"
    assert readiness["releaseChannel"] == "preview"
    assert "Initial Preview Release releaseChannel must be prerelease." in (
        readiness["blockers"]
    )


def test_sdd_workbench_view_blocks_invalid_preview_runtime_contract(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_project(project)
    (project / "release").mkdir()
    (project / "release/preview-runtime.json").write_text(
        json.dumps(
            {
                "sourceApp": "demo",
                "previewUrl": "https://preview.nienfos.com/demo",
                "apiBaseUrl": "https://preview.nienfos.com/demo/api",
                "runtimeProfile": "real",
                "apiRuntime": "fastapi",
                "releaseChannel": "stable",
                "releaseTagPattern": "android-v*",
                "productionReady": True,
                "mockOrDemo": True,
            }
        ),
        encoding="utf-8",
    )
    client = _client(projects_root, codex_workdir=str(project))

    response = client.get("/sdd/workbench/view", params={"workspace_path": str(project)})

    assert response.status_code == 200
    blockers = response.json()["preview_readiness"]["blockers"]
    assert "Initial Preview Release runtimeProfile must be preview." in blockers
    assert "Initial Preview Release apiRuntime must be cloudflare_preview." in blockers
    assert "Initial Preview Release releaseChannel must be prerelease." in blockers
    assert (
        "Initial Preview Release releaseTagPattern must be android-preview-v*."
        in blockers
    )
    assert "Initial Preview Release productionReady must be false." in blockers
    assert "Initial Preview Release mockOrDemo must be false." in blockers


def test_sdd_workbench_view_surfaces_unknown_standard_as_blocked(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_project(project, standard_id="workbench-sdd/v9")
    client = _client(projects_root, codex_workdir=str(project))

    response = client.get(
        "/sdd/workbench/view",
        params={"workspace_path": str(project)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["health"]["status"] == "fail"
    assert payload["context_preview"]["status"] == "blocked"
    assert payload["context_preview"]["index_status"] == "not_checked"
    assert "Unsupported SDD standard version" in payload["context_preview"]["error"]
    assert (
        "broad_reads_blocked_until_context_pack_is_available"
        in (payload["context_preview"]["blocked_reads"])
    )
    assert payload["feature_specs"][0]["traceability_status"] == "linked"
    assert payload["impact_queue"][0]["requires_review"] is True


def test_sdd_workbench_view_reports_incomplete_traceability(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_project(project, complete_traceability=False)
    client = _client(projects_root, codex_workdir=str(project))

    response = client.get(
        "/sdd/workbench/view",
        params={"workspace_path": str(project)},
    )

    assert response.status_code == 200
    payload = response.json()
    row = payload["traceability_matrix"][0]
    assert row["status"] == "incomplete"
    assert "requirements" in row["missing_links"]
    assert payload["feature_specs"][0]["traceability_status"] == "incomplete"


def test_sdd_workbench_view_surfaces_invalid_preset_as_blocked(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_project(project)
    client = _client(projects_root, codex_workdir=str(project))

    response = client.get(
        "/sdd/workbench/view",
        params={"workspace_path": str(project), "preset": "unsupported-workflow"},
    )

    assert response.status_code == 200
    preview = response.json()["context_preview"]
    assert preview["status"] == "blocked"
    assert preview["index_status"] == "not_checked"
    assert preview["error"] == "Unsupported context pack preset: unsupported-workflow"
    assert "fallback_to_all_specs_when_indexes_unavailable" in preview["blocked_reads"]


def test_sdd_workbench_view_surfaces_stale_index_hard_failure(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_project(project)
    client = _client(projects_root, codex_workdir=str(project))
    first = client.get("/sdd/workbench/view", params={"workspace_path": str(project)})
    assert first.status_code == 200
    spec_path = project / "specs/001-demo/spec.md"
    spec_path.write_text(spec_path.read_text() + "\nChanged after index.\n")
    os.utime(spec_path, None)

    response = client.get(
        "/sdd/workbench/view",
        params={
            "workspace_path": str(project),
            "auto_regenerate_indexes": "false",
        },
    )

    assert response.status_code == 200
    preview = response.json()["context_preview"]
    assert preview["status"] == "blocked"
    assert preview["mode"] == "hard_failure"
    assert preview["index_status"] == "stale"
    assert "auto-regeneration is disabled" in preview["error"]
    assert "fallback_to_all_specs_when_indexes_unavailable" in preview["blocked_reads"]


def test_sdd_workbench_view_surfaces_missing_index_hard_failure(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_project(project)
    client = _client(projects_root, codex_workdir=str(project))

    response = client.get(
        "/sdd/workbench/view",
        params={
            "workspace_path": str(project),
            "auto_regenerate_indexes": "false",
        },
    )

    assert response.status_code == 200
    preview = response.json()["context_preview"]
    assert preview["status"] == "blocked"
    assert preview["mode"] == "hard_failure"
    assert preview["index_status"] == "missing"
    assert "auto-regeneration is disabled" in preview["error"]
    assert "fallback_to_all_specs_when_indexes_unavailable" in preview["blocked_reads"]


def test_sdd_workbench_view_surfaces_degraded_context_pack(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_project(project)
    (project / ".sdd").write_text("not a directory\n")
    client = _client(projects_root, codex_workdir=str(project))

    response = client.get(
        "/sdd/workbench/view",
        params={"workspace_path": str(project), "allow_degraded": "true"},
    )

    assert response.status_code == 200
    preview = response.json()["context_preview"]
    assert preview["status"] == "degraded"
    assert preview["mode"] == "degraded"
    assert preview["index_status"] == "failed"
    assert preview["related_specs"] == []
    assert preview["related_diagrams"] == []
    assert "Index regeneration failed" in preview["routing_decisions"][0]
    assert "Do not scan every full spec body as fallback." in preview["prompt"]


def test_sdd_workbench_view_blocks_invalid_context_rules_override(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_project(project, invalid_context_rules=True)
    client = _client(projects_root, codex_workdir=str(project))

    response = client.get(
        "/sdd/workbench/view",
        params={"workspace_path": str(project)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["health"]["status"] == "fail"
    assert payload["context_preview"]["status"] == "blocked"
    assert (
        "Unsupported sdd.context_rules key(s): disable_safety"
        in (payload["context_preview"]["error"])
    )


def test_sdd_workbench_view_does_not_fallback_to_full_spec_body(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_project(project)
    marker = "SECRET_FULL_BODY_MARKER"
    (project / "specs/001-demo/spec.md").write_text(
        "# Demo Spec\n\n" + ("x" * 9000) + marker + "\n",
        encoding="utf-8",
    )
    client = _client(projects_root, codex_workdir=str(project))

    response = client.get(
        "/sdd/workbench/view",
        params={"workspace_path": str(project), "query": marker},
    )

    assert response.status_code == 200
    preview = response.json()["context_preview"]
    spec_index = (project / ".sdd/spec-index.yaml").read_text(encoding="utf-8")
    assert preview["status"] == "ready"
    assert marker not in preview["prompt"]
    assert marker not in spec_index
    assert "scan_every_full_spec_body" in preview["blocked_reads"]


def _client(projects_root: Path, **overrides: object) -> TestClient:
    overrides.setdefault("feedback_source_workspace_aliases", "")
    settings = Settings(
        codex_command="python3 tests/fixtures/fake_codex.py",
        codex_use_exec=False,
        projects_root=str(projects_root),
        chat_store_backend="memory",
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
        audio_transcription_backend="disabled",
        speech_synthesis_backend="disabled",
        **overrides,
    )
    return TestClient(create_app(settings))


def _write_project(
    project: Path,
    *,
    standard_id: str = "workbench-sdd/v1",
    related_specs: int = 1,
    related_diagrams: int = 1,
    invalid_context_rules: bool = False,
    complete_traceability: bool = True,
) -> None:
    (project / ".specify/memory").mkdir(parents=True)
    (project / "architecture").mkdir(parents=True)
    (project / "domain").mkdir()
    (project / "data").mkdir()
    (project / "specs/001-demo/diagrams").mkdir(parents=True)
    (project / "architecture/overview.md").write_text(
        "# Architecture Overview\n",
        encoding="utf-8",
    )
    (project / "architecture/components.mmd").write_text(
        "flowchart LR\nA --> B\n",
        encoding="utf-8",
    )
    (project / "architecture/components.yaml").write_text(
        textwrap.dedent(
            """\
            diagram_id: components
            diagram_type: components
            scope: baseline
            status: draft
            owner: project
            source: components.mmd
            """
        ),
        encoding="utf-8",
    )
    (project / "domain/glossary.md").write_text(
        "# Domain Glossary\n",
        encoding="utf-8",
    )
    (project / "data/persistence-model.md").write_text(
        "# Persistence Model\n",
        encoding="utf-8",
    )
    (project / ".specify/memory/constitution.md").write_text(
        "# Constitution\n",
        encoding="utf-8",
    )
    extra_context_rules = "    disable_safety: true\n" if invalid_context_rules else ""
    (project / "codex-bridge.yaml").write_text(
        textwrap.dedent(
            f"""\
            kind: codex.bridge.project
            version: 1
            sdd:
              required: true
              standard: {standard_id}
              project_type: bridge_backend
              constitution: .specify/memory/constitution.md
              specs: specs
              architecture: architecture
              domain_root: domain
              data_root: data
              generated_index_root: .sdd
              protected_baseline:
                - architecture/components.mmd
              context_rules:
                domains:
                  workbench:
                    modules:
                      - backend/app/application/services
                    preferred_context:
                      - specs/001-demo/spec.md
                candidate_limits:
                  related_specs: 5
                  related_diagrams: 3
            {extra_context_rules}\
            """
        ),
        encoding="utf-8",
    )
    for index in range(related_specs):
        spec_id = "001-demo" if index == 0 else f"{index + 1:03d}-demo"
        spec_dir = project / "specs" / spec_id
        (spec_dir / "diagrams").mkdir(parents=True, exist_ok=True)
        (spec_dir / "spec.md").write_text(
            textwrap.dedent(
                f"""\
                ---
                id: {spec_id}
                title: Checkout Spec {index + 1}
                status: draft
                type: feature
                ---

                # Checkout Spec {index + 1}

                checkout indexed summary {index + 1}
                """
            ),
            encoding="utf-8",
        )
        (spec_dir / "plan.md").write_text(
            f"# Checkout Plan {index + 1}\n",
            encoding="utf-8",
        )
        (spec_dir / "tasks.md").write_text(
            f"# Checkout Tasks {index + 1}\n",
            encoding="utf-8",
        )
        traceability = (
            textwrap.dedent(
                f"""\
                spec_id: {spec_id}
                requirements:
                  FR-001:
                    acceptance_criteria:
                      - AC-001
                    tasks:
                      - T001
                    diagrams:
                      - specs/{spec_id}/diagrams/sequence.mmd
                """
            )
            if complete_traceability
            else f"spec_id: {spec_id}\n"
        )
        (spec_dir / "traceability.yaml").write_text(
            traceability,
            encoding="utf-8",
        )
        if index < related_diagrams:
            (spec_dir / "diagrams/sequence.mmd").write_text(
                "sequenceDiagram\nA->>B: checkout\n",
                encoding="utf-8",
            )
            (spec_dir / "diagrams/sequence.yaml").write_text(
                textwrap.dedent(
                    """\
                    diagram_id: sequence
                    diagram_type: sequence
                    scope: feature
                    status: draft
                    owner: project
                    source: sequence.mmd
                    """
                ),
                encoding="utf-8",
            )
