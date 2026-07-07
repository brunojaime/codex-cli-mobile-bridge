from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

loaded_scripts = sys.modules.get("scripts")
loaded_scripts_path = getattr(loaded_scripts, "__file__", "") if loaded_scripts else ""
if loaded_scripts_path and not loaded_scripts_path.startswith(str(ROOT / "scripts")):
    del sys.modules["scripts"]

from backend.app.infrastructure.config.settings import Settings  # noqa: E402
from backend.app.main import create_app  # noqa: E402
from scripts.codex_bridge_sdd_backfill import backfill_workspace  # noqa: E402


def test_existing_spec_api_job_review_apply_refreshes_indexes_and_strict_doctor(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_backfillable_project(project)
    backfill = backfill_workspace(project, apply=True)
    assert backfill.status == "applied"
    before_tasks = (project / "specs/001-existing/tasks.md").read_text()
    fake_codex = _write_fake_codex(tmp_path)
    client = _client(projects_root, fake_codex)

    apply_response = client.post(
        "/sdd/specs/edit/apply",
        json={
            "workspacePath": str(project),
            "specTarget": {
                "mode": "existing_spec",
                "specId": "001-existing",
                "artifact": "tasks",
            },
            "intakeItems": [{"kind": "text", "text": "Mark existing task done"}],
        },
    )
    assert apply_response.status_code == 200
    queued = apply_response.json()
    job_id = queued["job"]["job_id"]
    assert queued["status"] == "queued"
    assert "scan_every_full_spec_body" in queued["job"]["blocked_reads"]

    run_response = client.post(f"/sdd/codex-jobs/{job_id}/run")
    assert run_response.status_code == 200
    completed = run_response.json()
    assert completed["status"] == "completed"
    assert completed["activity_state"] == "ready"
    assert (project / "specs/001-existing/tasks.md").read_text() == before_tasks

    review_response = client.get(f"/sdd/codex-jobs/{job_id}/review")
    assert review_response.status_code == 200
    review = review_response.json()
    assert review["status"] == "ready"
    assert review["validation_status"] == "pass"
    assert review["changed_files"][0]["path"] == "specs/001-existing/tasks.md"
    assert review["changed_files"][0]["patch_path"].endswith(".diff")

    reviewed_apply_response = client.post(f"/sdd/codex-jobs/{job_id}/apply")
    assert reviewed_apply_response.status_code == 200
    reviewed_apply = reviewed_apply_response.json()
    assert reviewed_apply["status"] == "applied"
    assert reviewed_apply["activity_state"] == "applied"
    assert reviewed_apply["applied"] == ["specs/001-existing/tasks.md"]
    assert reviewed_apply["post_apply_refresh"]["index_status"]["state"] in {
        "fresh",
        "regenerated",
    }
    assert (
        "Added by fake Codex" in (project / "specs/001-existing/tasks.md").read_text()
    )

    doctor = _doctor(project, projects_root, "--strict")
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    payload = json.loads(doctor.stdout)
    assert payload["status"] == "pass"
    assert payload["summary"]["fail"] == 0
    assert payload["index_status"]["state"] == "fresh"


def _client(projects_root: Path, fake_codex: Path) -> TestClient:
    settings = Settings(
        codex_command=f"{sys.executable} {fake_codex}",
        projects_root=str(projects_root),
        chat_store_backend="memory",
        execution_timeout_seconds=10,
        poll_interval_seconds=0,
        audio_transcription_backend="disabled",
        speech_synthesis_backend="disabled",
        feedback_source_workspace_aliases="",
    )
    return TestClient(create_app(settings))


def _write_fake_codex(tmp_path: Path) -> Path:
    script = tmp_path / "fake_codex_write_tasks.py"
    script.write_text(
        textwrap.dedent(
            """\
            from pathlib import Path

            Path("specs/001-existing/tasks.md").write_text(
                "- [x] Existing\\n- [ ] Added by fake Codex\\n",
                encoding="utf-8",
            )
            print("fake codex wrote reviewed output")
            """
        ),
        encoding="utf-8",
    )
    return script


def _write_backfillable_project(project: Path) -> None:
    (project / ".specify/memory").mkdir(parents=True)
    (project / "architecture").mkdir()
    (project / "domain").mkdir()
    (project / "data").mkdir()
    (project / "specs/001-existing/diagrams").mkdir(parents=True)
    (project / "codex-bridge.yaml").write_text(
        textwrap.dedent(
            """\
            kind: codex.bridge.project
            version: 1
            sdd:
              required: true
              standard: workbench-sdd/v1
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
                      - specs/001-existing/spec.md
                candidate_limits:
                  related_specs: 5
                  related_diagrams: 3
            """
        ),
        encoding="utf-8",
    )
    (project / ".specify/memory/constitution.md").write_text(
        "# Constitution\n", encoding="utf-8"
    )
    (project / "architecture/overview.md").write_text(
        "# Architecture Overview\n", encoding="utf-8"
    )
    (project / "domain/glossary.md").write_text("# Domain Glossary\n", encoding="utf-8")
    (project / "data/persistence-model.md").write_text(
        "# Persistence Model\n", encoding="utf-8"
    )
    (project / "architecture/components.mmd").write_text(
        "flowchart LR\nA --> B\n", encoding="utf-8"
    )
    (project / "specs/001-existing/spec.md").write_text(
        "# Existing Spec\n\nCurrent behavior.\n", encoding="utf-8"
    )
    (project / "specs/001-existing/plan.md").write_text(
        "# Existing Plan\n", encoding="utf-8"
    )
    (project / "specs/001-existing/tasks.md").write_text(
        "- [ ] Existing\n", encoding="utf-8"
    )
    (project / "specs/001-existing/diagrams/sequence.mmd").write_text(
        "sequenceDiagram\nUser->>System: edit spec\n", encoding="utf-8"
    )


def _doctor(
    project: Path,
    projects_root: Path,
    *extra_args: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "scripts/codex_bridge_sdd_doctor.py",
            "--workspace",
            str(project),
            "--projects-root",
            str(projects_root),
            "--json",
            *extra_args,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
