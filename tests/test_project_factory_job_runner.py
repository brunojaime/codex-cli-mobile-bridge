from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from backend.app.application.services.project_factory_generator_service import (
    ProjectFactoryGeneratorService,
)
from backend.app.application.services.project_factory_job_runner import (
    ProjectFactoryJobRunner,
    ProjectFactoryJobRunnerError,
    ProjectFactoryProcessResult,
)
from backend.app.application.services.project_factory_manifest_service import (
    ProjectFactoryManifestInput,
    ProjectFactoryManifestService,
)
from backend.app.application.services.project_factory_reference_asset_service import (
    ProjectFactoryReferenceAssetService,
)


def test_project_factory_runner_success_writes_prompts_and_runs_batches(
    tmp_path: Path,
) -> None:
    process_runner = _FakeProcessRunner()
    runner = _runner(tmp_path, process_runner)
    events: list[dict[str, object]] = []

    result = runner.run(
        _context(tmp_path, generator_runs=1, reviewer_runs=2),
        event_sink=events.append,
    )

    project = Path(result.generation_result.target_path)
    assert project.is_dir()
    assert (project / ".codex/factory/prompts/research-planning.md").is_file()
    assert (project / ".codex/factory/prompts/generator-01.md").is_file()
    assert (project / ".codex/factory/prompts/reviewer-02.md").is_file()
    assert (project / ".codex/factory/prompts/finalize-validation.md").is_file()
    assert (project / ".codex/factory/prompts/publish-finalize.md").is_file()
    assert len(process_runner.calls) == 7
    assert [event["phase"] for event in events if event["status"] == "completed"] == [
        "scaffold",
        "research_planning",
        "generator_batch",
        "reviewer_batch",
        "reviewer_batch",
        "finalize_validation",
        "publish_finalize",
        "local_git_commit",
        "publish_verification",
    ]
    assert events[-1]["command"] == ["bash", "scripts/validate_publication_ready.sh"]


def test_project_factory_runner_can_execute_generated_validation(
    tmp_path: Path,
) -> None:
    process_runner = _FakeProcessRunner()
    runner = _runner(tmp_path, process_runner)
    events: list[dict[str, object]] = []

    runner.run(
        _context(
            tmp_path,
            generator_runs=0,
            reviewer_runs=0,
            run_generated_validation=True,
        ),
        event_sink=events.append,
    )

    assert ("bash", "scripts/validate_generated_project.sh") in process_runner.calls
    completed = [event for event in events if event["phase"] == "finalize_validation"]
    assert completed[-1]["status"] == "completed"
    assert completed[-1]["stdout"] == "ok"
    assert events[-1]["phase"] == "publish_verification"


def test_project_factory_runner_reports_generated_validation_failure(
    tmp_path: Path,
) -> None:
    process_runner = _FakeProcessRunner(fail_call=2)
    runner = _runner(tmp_path, process_runner)
    events: list[dict[str, object]] = []

    with pytest.raises(ProjectFactoryJobRunnerError):
        runner.run(
            _context(
                tmp_path,
                generator_runs=0,
                reviewer_runs=0,
                run_generated_validation=True,
            ),
            event_sink=events.append,
        )

    failed = [event for event in events if event["status"] == "failed"]
    assert failed[-1]["phase"] == "finalize_validation"
    assert failed[-1]["command"] == ["bash", "scripts/validate_generated_project.sh"]
    assert failed[-1]["exit_code"] == 7


def test_project_factory_runner_failure_keeps_project_and_reports_error(
    tmp_path: Path,
) -> None:
    process_runner = _FakeProcessRunner(fail_call=2)
    runner = _runner(tmp_path, process_runner)
    events: list[dict[str, object]] = []

    with pytest.raises(ProjectFactoryJobRunnerError):
        runner.run(
            _context(tmp_path, generator_runs=1, reviewer_runs=0),
            event_sink=events.append,
        )

    assert (tmp_path / "clinica-norte").is_dir()
    failed = [event for event in events if event["status"] == "failed"]
    assert failed
    assert failed[0]["phase"] == "generator_batch"
    assert failed[0]["exit_code"] == 7


def test_project_factory_runner_timeout_reports_failed_phase(tmp_path: Path) -> None:
    process_runner = _FakeProcessRunner(timeout_call=1)
    runner = _runner(tmp_path, process_runner)
    events: list[dict[str, object]] = []

    with pytest.raises(ProjectFactoryJobRunnerError):
        runner.run(
            _context(tmp_path, generator_runs=0, reviewer_runs=0),
            event_sink=events.append,
        )

    failed = [event for event in events if event["status"] == "failed"]
    assert failed[0]["phase"] == "research_planning"
    assert "timed out" in failed[0]["message"]


class _FakeProcessRunner:
    def __init__(self, *, fail_call: int | None = None, timeout_call: int | None = None):
        self.calls: list[tuple[str, ...]] = []
        self.fail_call = fail_call
        self.timeout_call = timeout_call

    def run(self, *, argv, cwd, env, timeout_seconds):
        self.calls.append(tuple(argv))
        call_number = len(self.calls)
        if self.timeout_call == call_number:
            raise subprocess.TimeoutExpired(argv, timeout_seconds)
        if self.fail_call == call_number:
            return ProjectFactoryProcessResult(
                returncode=7,
                stdout="partial",
                stderr="failed",
            )
        return ProjectFactoryProcessResult(returncode=0, stdout="ok", stderr="")


def _runner(tmp_path: Path, process_runner: _FakeProcessRunner) -> ProjectFactoryJobRunner:
    reference_service = ProjectFactoryReferenceAssetService(
        storage_root=tmp_path / ".assets",
    )
    generator = ProjectFactoryGeneratorService(
        reference_asset_service=reference_service,
    )
    return ProjectFactoryJobRunner(
        generator_service=generator,
        process_runner=process_runner,
    )


def _context(
    tmp_path: Path,
    *,
    generator_runs: int,
    reviewer_runs: int,
    run_generated_validation: bool = False,
):
    plan = ProjectFactoryManifestService(projects_root=tmp_path).plan_manifest(
        ProjectFactoryManifestInput(
            name="Clinica Norte",
            business_type="medical",
            primary_goal="Reservar turnos",
        )
    )
    from backend.app.application.services.project_factory_job_runner import (
        ProjectFactoryRunnerContext,
    )

    return ProjectFactoryRunnerContext(
        draft_id="pf-draft-000000000000",
        manifest_plan=plan,
        reference_assets=(),
        generator_runs=generator_runs,
        reviewer_runs=reviewer_runs,
        codex_command="fake-codex",
        timeout_seconds=1,
        run_generated_validation=run_generated_validation,
    )
