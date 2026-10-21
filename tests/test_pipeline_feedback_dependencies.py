"""Regression for feedback whose own check passes but a prerequisite becomes stale."""

from pathlib import Path
import subprocess
import sys

from backend.app.application.services.pipeline_quality_service import (
    PipelineQualityService,
)


def repository(root: Path) -> Path:
    root.mkdir()
    (root / "ready.txt").write_text("ready\n")
    for args in (
        ["init", "-q"],
        ["add", "."],
        [
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "baseline",
        ],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


def contract(project_id: str, *, dependencies=None, feedback_item_id=None):
    return {
        "project_id": project_id,
        "dependencies": dependencies or [],
        "criteria": [
            {
                "id": "ready",
                "description": "Required component is ready",
                "check_ids": ["ready"],
                "feedback_item_id": feedback_item_id,
            }
        ],
        "checks": [
            {
                "id": "ready",
                "argv": [
                    sys.executable,
                    "-B",
                    "-c",
                    "from pathlib import Path; assert Path('ready.txt').read_text() == 'ready\\n'",
                ],
            }
        ],
    }


def feedback_dependency_scenario(tmp_path: Path) -> dict:
    """Runs the production service against two isolated, real Git repositories."""
    dependency_root = repository(tmp_path / "dependency")
    app_root = repository(tmp_path / "app")
    service = PipelineQualityService(
        database_path=tmp_path / "evidence.sqlite", allowed_roots=[tmp_path]
    )
    dependency = service.register(
        workspace=str(dependency_root),
        work_item_id="required-service",
        contract=contract("required-service"),
    )
    service.execute(dependency["id"], attempt_key="dependency-ready")
    app = service.register(
        workspace=str(app_root),
        work_item_id="resolve-feedback",
        contract=contract(
            "bridge", dependencies=[dependency["id"]], feedback_item_id="comment-1"
        ),
    )
    service.execute(app["id"], attempt_key="app-ready")

    def observe():
        state = service.status(app["id"])
        feedback = service.feedback_resolution(
            source_app="bridge", item_ids=["comment-1"], workspace=str(app_root)
        )
        return {
            "work_verified": state["verified"],
            "work_blockers": state["blockers"],
            "own_check": state["criteria"][0]["status"],
            "feedback_status": feedback["items"][0]["status"],
            "feedback_verified_count": feedback["verified_count"],
            "feedback_blockers": feedback["items"][0].get("blockers", []),
            "own_receipts": state["criteria"][0]["receipt_ids"],
        }

    before = observe()
    # A source change invalidates the prerequisite's evidence; app source stays intact.
    (dependency_root / "configuration.txt").write_text("configuration revision 2\n")
    lost_dependency_evidence = observe()
    service.execute(dependency["id"], attempt_key="dependency-rechecked")
    after_dependency_recheck = observe()
    return {
        "before": before,
        "dependency_changed": lost_dependency_evidence,
        "dependency_rechecked": after_dependency_recheck,
    }


def test_feedback_loses_verified_status_when_required_dependency_changes(tmp_path):
    observed = feedback_dependency_scenario(tmp_path)
    assert observed["before"]["feedback_status"] == "verified"
    lost = observed["dependency_changed"]
    assert not lost["work_verified"] and lost["own_check"] == "verified"
    assert lost["feedback_status"] == "blocked", (
        "Feedback must not claim verified while its required dependency is unverified"
    )
    assert lost["feedback_verified_count"] == 0
    assert lost["feedback_blockers"] == lost["work_blockers"]
    restored = observed["dependency_rechecked"]
    assert restored["feedback_status"] == "verified"
    assert restored["own_receipts"] == observed["before"]["own_receipts"]


if __name__ == "__main__":
    import json
    import tempfile

    with tempfile.TemporaryDirectory(prefix="feedback-dependency-case-") as directory:
        observed = feedback_dependency_scenario(Path(directory))
    print(json.dumps(observed, indent=2))
    lost = observed["dependency_changed"]
    passed = (
        observed["before"]["feedback_status"] == "verified"
        and not lost["work_verified"]
        and lost["own_check"] == "verified"
        and lost["feedback_status"] == "blocked"
        and lost["feedback_verified_count"] == 0
        and lost["feedback_blockers"] == lost["work_blockers"]
        and observed["dependency_rechecked"]["feedback_status"] == "verified"
    )
    print(
        "PASS: feedback follows prerequisite evidence"
        if passed
        else "FAIL: feedback incorrectly claims verified after required dependency evidence is invalidated"
    )
    raise SystemExit(0 if passed else 1)
