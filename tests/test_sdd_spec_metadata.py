from __future__ import annotations

import hashlib
import textwrap
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.application.services.sdd_project_service import (
    SddProjectService,
    SddSpecNotFoundError,
    SddWorkspacePathError,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.main import create_app


def test_spec_metadata_reads_valid_metadata_and_targetable_artifacts(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path, metadata=True)
    service = _service(tmp_path)

    metadata = service.get_spec_metadata(str(project), "001-demo")

    assert metadata.id == "001-demo"
    assert metadata.title == "Checkout Favorites"
    assert metadata.description == "Save favorite products from checkout."
    assert metadata.lifecycle_status == "draft"
    assert metadata.created_at == "2026-07-06T00:00:00Z"
    assert metadata.updated_at == "2026-07-06T01:00:00Z"
    assert metadata.generated.title is True
    assert metadata.generated.user_pinned_description is True
    assert metadata.tasks.total == 5
    assert metadata.tasks.completed == 2
    assert metadata.tasks.pending == 3
    assert metadata.last_run_state == "ready"
    assert metadata.metadata_status == "present"
    assert "specs/001-demo/spec.md" in metadata.available_files
    assert "specs/001-demo/diagrams/sequence.mmd" in metadata.diagrams


def test_spec_metadata_uses_fallbacks_for_missing_metadata(tmp_path: Path) -> None:
    project = _write_project(tmp_path, metadata=False)
    service = _service(tmp_path)

    metadata = service.get_spec_metadata(str(project), "001-demo")

    assert metadata.title == "Checkout Flow"
    assert metadata.description == "Users can review cart totals before payment."
    assert metadata.metadata_status == "missing"
    assert metadata.tasks.total == 3
    assert metadata.tasks.completed == 1
    assert metadata.tasks.pending == 2
    assert "metadata.yaml is missing" in metadata.metadata_warnings[0]


def test_spec_metadata_reports_malformed_and_stale_metadata(tmp_path: Path) -> None:
    malformed_project = _write_project(tmp_path / "malformed", metadata=False)
    (malformed_project / "specs/001-demo/metadata.yaml").write_text("- nope\n")
    stale_project = _write_project(tmp_path / "stale", metadata=True)
    (stale_project / "specs/001-demo/metadata.yaml").write_text(
        _metadata_yaml(spec_digest="not-current"),
        encoding="utf-8",
    )

    malformed = _service(tmp_path / "malformed").get_spec_metadata(
        str(malformed_project),
        "001-demo",
    )
    stale = _service(tmp_path / "stale").get_spec_metadata(
        str(stale_project),
        "001-demo",
    )

    assert malformed.metadata_status == "malformed"
    assert "metadata.yaml must contain a mapping." in malformed.metadata_warnings
    assert stale.metadata_status == "stale"
    assert stale.metadata_stale_paths == ("spec.md",)


def test_spec_metadata_reports_invalid_workspace_and_missing_spec(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    service = _service(tmp_path)

    try:
        service.list_spec_metadata(str(tmp_path / "outside"))
    except SddWorkspacePathError as exc:
        assert "PROJECTS_ROOT" in str(exc)
    else:
        raise AssertionError("Expected SddWorkspacePathError")

    try:
        service.get_spec_metadata(str(project), "999-missing")
    except SddSpecNotFoundError as exc:
        assert "999-missing" in str(exc)
    else:
        raise AssertionError("Expected SddSpecNotFoundError")


def test_workbench_view_includes_metadata_summary(tmp_path: Path) -> None:
    project = _write_project(tmp_path, metadata=True)
    client = _client(tmp_path / "projects", codex_workdir=str(project))

    response = client.get(
        "/sdd/workbench/view", params={"workspace_path": str(project)}
    )

    assert response.status_code == 200
    spec = response.json()["feature_specs"][0]
    assert spec["id"] == "001-demo"
    assert spec["title"] == "Checkout Favorites"
    assert spec["description"] == "Save favorite products from checkout."
    assert spec["task_total"] == 5
    assert spec["task_completed"] == 2
    assert spec["task_pending"] == 3
    assert spec["last_run_state"] == "ready"
    assert spec["metadata_status"] == "present"
    assert "specs/001-demo/tasks.md" in spec["available_files"]


def _service(tmp_path: Path) -> SddProjectService:
    return SddProjectService(projects_root=str(tmp_path / "projects"))


def _client(projects_root: Path, **overrides: object) -> TestClient:
    settings = Settings(
        codex_command="python3 tests/fixtures/fake_codex.py",
        codex_use_exec=False,
        projects_root=str(projects_root),
        chat_store_backend="memory",
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
        audio_transcription_backend="disabled",
        speech_synthesis_backend="disabled",
        feedback_source_workspace_aliases="",
        **overrides,
    )
    return TestClient(create_app(settings))


def _write_project(tmp_path: Path, *, metadata: bool = False) -> Path:
    project = tmp_path / "projects/demo"
    (project / ".specify/memory").mkdir(parents=True)
    (project / "architecture").mkdir()
    (project / "domain").mkdir()
    (project / "data").mkdir()
    spec_dir = project / "specs/001-demo"
    (spec_dir / "diagrams").mkdir(parents=True)
    (project / "codex-bridge.yaml").write_text(
        textwrap.dedent(
            """\
            kind: codex.bridge.project
            version: 1
            sdd:
              required: true
              standard: workbench-sdd/v1
              specs: specs
              architecture: architecture
              domain_root: domain
              data_root: data
              generated_index_root: .sdd
              context_rules:
                candidate_limits:
                  related_specs: 5
                  related_diagrams: 3
            """
        ),
        encoding="utf-8",
    )
    (project / ".specify/memory/constitution.md").write_text("# Constitution\n")
    (project / "architecture/overview.md").write_text("# Architecture\n")
    (project / "architecture/components.mmd").write_text("flowchart LR\nA --> B\n")
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
        )
    )
    (project / "domain/glossary.md").write_text("# Glossary\n")
    (project / "data/persistence-model.md").write_text("# Persistence\n")
    (spec_dir / "spec.md").write_text(
        textwrap.dedent(
            """\
            ---
            id: 001-demo
            ---

            # Checkout Flow

            Users can review cart totals before payment.
            """
        ),
        encoding="utf-8",
    )
    (spec_dir / "plan.md").write_text("# Plan\n")
    (spec_dir / "tasks.md").write_text(
        "- [x] T001 Done\n- [ ] T002 Pending\n- [ ] T003 Pending\n"
    )
    (spec_dir / "traceability.yaml").write_text(
        "requirements:\n  FR-001:\n    tasks: [T001]\n"
    )
    (spec_dir / "diagrams/sequence.mmd").write_text(
        "sequenceDiagram\nA->>B: checkout\n"
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
        )
    )
    if metadata:
        spec_digest = hashlib.sha256((spec_dir / "spec.md").read_bytes()).hexdigest()
        (spec_dir / "metadata.yaml").write_text(_metadata_yaml(spec_digest=spec_digest))
    return project


def _metadata_yaml(*, spec_digest: str) -> str:
    return textwrap.dedent(
        f"""\
        id: CHG-2026-07-06-001
        title: Checkout Favorites
        description: Save favorite products from checkout.
        status: draft
        created_at: 2026-07-06T00:00:00Z
        updated_at: 2026-07-06T01:00:00Z
        last_run_state: ready
        generated:
          title: true
          description: true
          user_pinned_title: false
          user_pinned_description: true
        tasks:
          total: 5
          completed: 2
          pending: 3
        source_digests:
          spec.md: {spec_digest}
        """
    )
