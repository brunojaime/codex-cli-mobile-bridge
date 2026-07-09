from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_sdd_doctor_json_v2_reports_warnings_and_readiness(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_adopted_project(project)

    result = _doctor(project, projects_root)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["kind"] == "codex.sddDoctorReport"
    assert payload["version"] == 2
    assert payload["status"] == "warn"
    assert payload["ok"] is True
    assert payload["summary"]["warn"] >= 1
    assert payload["errors"] == []
    assert payload["warnings"]
    assert payload["index_status"]["state"] == "missing"
    assert (
        "Review warnings before relying on full Workbench automation."
        in (payload["next_actions"])
    )
    checks = {check["name"]: check for check in payload["checks"]}
    assert checks["standard"]["status"] == "pass"
    assert checks["context_rules"]["status"] == "pass"
    assert checks["diagram_metadata"]["status"] == "warn"
    assert checks["index_status"]["status"] == "warn"
    assert checks["context_pack"]["status"] == "warn"
    assert checks["llm_instructions"]["status"] == "warn"
    assert checks["workbench_view"]["status"] == "warn"
    assert checks["traceability:001-demo"]["status"] == "pass"
    assert (
        "fallback_to_all_specs_when_indexes_unavailable"
        in (checks["context_pack"]["data"]["blocked_reads"])
    )


def test_sdd_doctor_strict_treats_warnings_as_failure(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_adopted_project(project)

    result = _doctor(project, projects_root, "--strict")

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "warn"
    assert payload["ok"] is True
    assert payload["strict"] is True


def test_sdd_doctor_reports_hard_failures_without_masking_warnings(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_adopted_project(project, invalid_context_rules=True)

    result = _doctor(project, projects_root)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "fail"
    assert payload["ok"] is False
    errors = {check["name"]: check for check in payload["errors"]}
    assert "context_rules" in errors
    assert "context_pack" in errors
    assert "llm_instructions" in errors
    assert payload["warnings"]
    assert (
        "Fix failing SDD checks before write or Codex action flows."
        in (payload["next_actions"])
    )


def test_sdd_doctor_reports_degraded_context_when_regeneration_fails(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_adopted_project(project)
    index_root = project / ".sdd"
    index_root.mkdir()
    index_root.chmod(0o500)
    try:
        result = _doctor(project, projects_root, "--regenerate-indexes")

        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["status"] == "warn"
        degraded = {check["name"]: check for check in payload["degraded"]}
        assert degraded["context_pack"]["data"]["index_status"] == "failed"
        assert degraded["llm_instructions"]["data"]["status"] == "degraded"
        assert degraded["workbench_view"]["data"]["context_status"] == "degraded"
        assert (
            "Regenerate .sdd indexes before related-candidate routing."
            in (payload["next_actions"])
        )
    finally:
        index_root.chmod(0o700)


def test_sdd_doctor_legacy_project_skips_action_readiness(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "legacy"
    _write_legacy_project(project)

    result = _doctor(project, projects_root)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    skipped = {check["name"]: check for check in payload["skipped"]}
    assert skipped["context_pack"]["status"] == "skipped"
    assert skipped["llm_instructions"]["status"] == "skipped"
    assert skipped["workbench_view"]["status"] == "skipped"


def test_sdd_doctor_warns_for_stale_spec_intake_metadata(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_adopted_project(project)
    (project / "specs/001-demo/metadata.yaml").write_text(
        textwrap.dedent(
            """\
            id: 001-demo
            title: Demo
            description: Demo spec.
            status: draft
            source_digests:
              spec.md: not-current
            """
        ),
        encoding="utf-8",
    )

    result = _doctor(project, projects_root)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    checks = {check["name"]: check for check in payload["checks"]}
    intake = checks["spec_intake_readiness"]
    assert intake["status"] == "warn"
    assert intake["data"]["metadata"]["stale"] == [
        {
            "spec_id": "001-demo",
            "path": "specs/001-demo/metadata.yaml",
            "stale_paths": ["spec.md"],
        }
    ]


def test_sdd_doctor_fails_for_missing_intake_retention_artifact(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_adopted_project(project)
    intake = project / "specs/001-demo/intake/jobs/job-001"
    intake.mkdir(parents=True)
    (intake / "retention.json").write_text(
        json.dumps(
            {
                "retention_hours": 24,
                "artifacts": [
                    {
                        "item_index": 0,
                        "kind": "audio",
                        "target_path": (
                            "specs/001-demo/intake/jobs/job-001/media/audio-001.m4a"
                        ),
                        "byte_size": 5,
                        "sha256": hashlib.sha256(b"audio").hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = _doctor(project, projects_root)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    errors = {check["name"]: check for check in payload["errors"]}
    intake_check = errors["spec_intake_readiness"]
    assert intake_check["data"]["missing_intake_artifacts"] == [
        {
            "path": "specs/001-demo/intake/jobs/job-001/retention.json",
            "target_path": "specs/001-demo/intake/jobs/job-001/media/audio-001.m4a",
            "code": "missing_intake_artifact",
            "detail": (
                "specs/001-demo/intake/jobs/job-001/media/audio-001.m4a: "
                "retention artifact is missing"
            ),
        }
    ]


def test_sdd_doctor_warns_for_cleanup_eligible_media_and_failed_jobs(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "demo"
    _write_adopted_project(project)
    media = project / ".codex-bridge/sdd-media/abc-image.png"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"image")
    (media.with_suffix(".png.json")).write_text(
        json.dumps(
            {
                "kind": "codex.sddMediaUpload",
                "version": 1,
                "lifecycle": "staged",
                "media_kind": "image",
                "filename": "image.png",
                "mime_type": "image/png",
                "byte_size": 5,
                "sha256": hashlib.sha256(b"image").hexdigest(),
                "staged_path": ".codex-bridge/sdd-media/abc-image.png",
                "created_at": "2020-01-01T00:00:00Z",
                "retention": {"policy": "test", "hours": 24},
            }
        ),
        encoding="utf-8",
    )
    job_status = project / ".codex-bridge/sdd-jobs/job-001/job-status.json"
    job_status.parent.mkdir(parents=True)
    job_status.write_text(
        json.dumps(
            {
                "status": "failed",
                "next_actions": ["Review job logs before retry."],
            }
        ),
        encoding="utf-8",
    )

    result = _doctor(project, projects_root)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    checks = {check["name"]: check for check in payload["checks"]}
    intake = checks["spec_intake_readiness"]
    assert intake["status"] == "warn"
    assert intake["data"]["staged_media_warnings"] == [
        {
            "path": ".codex-bridge/sdd-media/abc-image.png.json",
            "staged_path": ".codex-bridge/sdd-media/abc-image.png",
            "code": "cleanup_eligible_staged_media",
            "retention_hours": 24,
        }
    ]
    assert intake["data"]["job_state_warnings"] == [
        {
            "path": ".codex-bridge/sdd-jobs/job-001/job-status.json",
            "job_id": "job-001",
            "status": "failed",
            "next_actions": ["Review job logs before retry."],
        }
    ]


def _doctor(
    project: Path, projects_root: Path, *extra_args: str
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


def _write_adopted_project(
    project: Path,
    *,
    invalid_context_rules: bool = False,
) -> None:
    (project / ".specify/memory").mkdir(parents=True)
    (project / "architecture").mkdir(parents=True)
    (project / "domain").mkdir()
    (project / "data").mkdir()
    (project / "specs/001-demo/diagrams").mkdir(parents=True)
    (project / "codex-bridge.yaml").write_text(
        textwrap.dedent(
            f"""\
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
                      - specs/001-demo/spec.md
                candidate_limits:
                  related_specs: 5
                  related_diagrams: 3
            {"    disable_safety: true" if invalid_context_rules else ""}\
            """
        ),
        encoding="utf-8",
    )
    (project / ".specify/memory/constitution.md").write_text(
        "# Constitution\n",
        encoding="utf-8",
    )
    (project / "architecture/overview.md").write_text(
        "# Architecture Overview\n",
        encoding="utf-8",
    )
    (project / "architecture/components.mmd").write_text(
        "flowchart LR\nA --> B\n",
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
    (project / "specs/001-demo/spec.md").write_text(
        textwrap.dedent(
            """\
            ---
            id: 001-demo
            title: Demo
            status: draft
            type: feature
            ---

            # Demo
            """
        ),
        encoding="utf-8",
    )
    (project / "specs/001-demo/plan.md").write_text("# Plan\n", encoding="utf-8")
    (project / "specs/001-demo/tasks.md").write_text(
        "# Tasks\n\n- [ ] T001\n",
        encoding="utf-8",
    )
    (project / "specs/001-demo/traceability.yaml").write_text(
        textwrap.dedent(
            """\
            spec_id: 001-demo
            requirements:
              FR-001:
                acceptance_criteria:
                  - AC-001
                tasks:
                  - T001
                diagrams:
                  - specs/001-demo/diagrams/sequence.mmd
            """
        ),
        encoding="utf-8",
    )
    (project / "specs/001-demo/diagrams/sequence.mmd").write_text(
        "sequenceDiagram\nA->>B: demo\n",
        encoding="utf-8",
    )


def _write_legacy_project(project: Path) -> None:
    _write_adopted_project(project)
    (project / "codex-bridge.yaml").write_text(
        "kind: codex.bridge.project\nversion: 1\n",
        encoding="utf-8",
    )
