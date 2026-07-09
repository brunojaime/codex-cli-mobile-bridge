from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from backend.app.application.services.project_factory_generator_service import (
    ProjectFactoryGeneratedFile,
    ProjectFactoryGenerationResult,
    ProjectFactoryGeneratorService,
)
from backend.app.application.services.project_factory_job_runner import (
    ProjectFactoryJobRunner,
    ProjectFactoryJobRunnerBlockedError,
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


def test_project_factory_runner_success_writes_prompts_and_runs_pairs(
    tmp_path: Path,
) -> None:
    process_runner = _FakeProcessRunner()
    runner = _runner(tmp_path, process_runner)
    events: list[dict[str, object]] = []

    result = runner.run(
        _context(tmp_path, generator_runs=2, reviewer_runs=2),
        event_sink=events.append,
    )

    project = Path(result.generation_result.target_path)
    assert project.is_dir()
    assert (project / ".codex/factory/prompts/research-planning.md").is_file()
    assert (project / ".codex/factory/prompts/generator-01.md").is_file()
    assert (project / ".codex/factory/prompts/reviewer-02.md").is_file()
    assert (project / ".codex/factory/prompts/finalize-validation.md").is_file()
    assert (project / ".codex/factory/prompts/publish-finalize.md").is_file()
    assert len(process_runner.calls) == 8
    assert "Generator pass 1:" in process_runner.calls[1][-1]
    assert "Reviewer pass 1:" in process_runner.calls[2][-1]
    assert "Generator pass 2:" in process_runner.calls[3][-1]
    assert "Reviewer pass 2:" in process_runner.calls[4][-1]
    assert [event["phase"] for event in events if event["status"] == "completed"] == [
        "scaffold",
        "research_planning",
        "generator_pass",
        "reviewer_pass",
        "generator_pass",
        "reviewer_pass",
        "finalize_validation",
        "publish_finalize",
        "local_git_commit",
        "publish_verification",
    ]
    assert events[-1]["command"] == ["bash", "scripts/validate_publication_ready.sh"]


def test_project_factory_runner_remote_publication_runs_required_phases(
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
            publication_validation_mode="remote",
        ),
        event_sink=events.append,
    )

    assert ("bash", "scripts/validate_generated_project.sh") in process_runner.calls
    assert process_runner.calls.index(
        ("bash", "scripts/validate_generated_project.sh")
    ) < process_runner.calls.index(("bash", "scripts/publish_project.sh"))
    assert process_runner.calls[-7:] == [
        ("bash", "scripts/publish_project.sh"),
        ("bash", "scripts/apply_cloudflare_preview.sh"),
        ("bash", "scripts/smoke_web_preview.sh"),
        ("bash", "scripts/smoke_preview_api.sh"),
        (
            "bash",
            "scripts/publish_android_preview_release.sh",
            "--push",
            "--watch",
        ),
        ("bash", "scripts/register_installable_app.sh"),
        ("bash", "scripts/validate_initial_preview_release.sh"),
    ]
    completed_phases = [
        event["phase"] for event in events if event["status"] == "completed"
    ]
    assert completed_phases[-7:] == [
        "github_publish",
        "cloudflare_preview_apply",
        "web_preview_smoke",
        "preview_api_smoke",
        "android_preview_release",
        "installable_app_registration",
        "publish_verification",
    ]


def test_project_factory_runner_remote_publication_blocks_on_preflight(
    tmp_path: Path,
) -> None:
    process_runner = _FakeProcessRunner()
    runner = _runner(
        tmp_path,
        process_runner,
        remote_preflight=lambda: {
            "ok": False,
            "status": "blocked",
            "checks": [
                {
                    "code": "workers_routes_edit_access",
                    "ok": False,
                    "detail": "Workers Routes: Edit permission is required.",
                }
            ],
        },
    )
    events: list[dict[str, object]] = []

    with pytest.raises(ProjectFactoryJobRunnerBlockedError):
        runner.run(
            _context(
                tmp_path,
                generator_runs=0,
                reviewer_runs=0,
                publication_validation_mode="remote",
            ),
            event_sink=events.append,
        )

    assert not (tmp_path / "clinica-norte").exists()
    assert process_runner.calls == []
    blocked = [event for event in events if event["status"] == "blocked"]
    assert blocked[-1]["phase"] == "cloudflare_preview_preflight"
    assert "workers_routes_edit_access" in blocked[-1]["stderr"]


def test_project_factory_runner_remote_publication_can_rerun_satisfied_phases(
    tmp_path: Path,
) -> None:
    project = tmp_path / "clinica-norte"
    project.mkdir()
    process_runner = _FakeProcessRunner()
    runner = ProjectFactoryJobRunner(
        generator_service=_ReusableProjectGenerator(project),
        process_runner=process_runner,
    )

    context = _context(
        tmp_path,
        generator_runs=0,
        reviewer_runs=0,
        publication_validation_mode="remote",
    )
    runner.run(context, event_sink=lambda _event: None)
    runner.run(context, event_sink=lambda _event: None)

    remote_sequence = [
        ("bash", "scripts/publish_project.sh"),
        ("bash", "scripts/apply_cloudflare_preview.sh"),
        ("bash", "scripts/smoke_web_preview.sh"),
        ("bash", "scripts/smoke_preview_api.sh"),
        (
            "bash",
            "scripts/publish_android_preview_release.sh",
            "--push",
            "--watch",
        ),
        ("bash", "scripts/register_installable_app.sh"),
        ("bash", "scripts/validate_initial_preview_release.sh"),
    ]
    for command in remote_sequence:
        assert process_runner.calls.count(command) == 2


def test_project_factory_runner_remote_publication_reports_blocked_phase(
    tmp_path: Path,
) -> None:
    process_runner = _FakeProcessRunner(fail_call=5, fail_returncode=2)
    runner = _runner(tmp_path, process_runner)
    events: list[dict[str, object]] = []

    with pytest.raises(ProjectFactoryJobRunnerBlockedError):
        runner.run(
            _context(
                tmp_path,
                generator_runs=0,
                reviewer_runs=0,
                publication_validation_mode="remote",
            ),
            event_sink=events.append,
        )

    blocked = [event for event in events if event["status"] == "blocked"]
    assert blocked[-1]["phase"] == "github_publish"
    assert blocked[-1]["exit_code"] == 2


def test_project_factory_runner_remote_publication_requires_generated_validation(
    tmp_path: Path,
) -> None:
    process_runner = _FakeProcessRunner(fail_call=2, fail_returncode=9)
    runner = _runner(tmp_path, process_runner)
    events: list[dict[str, object]] = []

    with pytest.raises(ProjectFactoryJobRunnerError):
        runner.run(
            _context(
                tmp_path,
                generator_runs=0,
                reviewer_runs=0,
                run_generated_validation=False,
                publication_validation_mode="remote",
            ),
            event_sink=events.append,
        )

    assert ("bash", "scripts/validate_generated_project.sh") in process_runner.calls
    assert ("bash", "scripts/publish_project.sh") not in process_runner.calls
    failed = [event for event in events if event["status"] == "failed"]
    assert failed[-1]["phase"] == "finalize_validation"
    assert failed[-1]["exit_code"] == 9


def test_project_factory_runner_blocks_when_publish_script_is_missing(
    tmp_path: Path,
) -> None:
    process_runner = _MissingScriptProcessRunner("scripts/publish_project.sh")
    runner = _runner(tmp_path, process_runner)
    events: list[dict[str, object]] = []

    with pytest.raises(ProjectFactoryJobRunnerBlockedError):
        runner.run(
            _context(
                tmp_path,
                generator_runs=0,
                reviewer_runs=0,
                publication_validation_mode="remote",
            ),
            event_sink=events.append,
        )

    blocked = [event for event in events if event["status"] == "blocked"]
    assert blocked[-1]["phase"] == "github_publish"
    assert "missing script" in blocked[-1]["stderr"]


def test_project_factory_runner_blocks_when_cloudflare_preview_apply_is_missing(
    tmp_path: Path,
) -> None:
    process_runner = _MissingScriptProcessRunner("scripts/apply_cloudflare_preview.sh")
    runner = _runner(tmp_path, process_runner)
    events: list[dict[str, object]] = []

    with pytest.raises(ProjectFactoryJobRunnerBlockedError):
        runner.run(
            _context(
                tmp_path,
                generator_runs=0,
                reviewer_runs=0,
                publication_validation_mode="remote",
            ),
            event_sink=events.append,
        )

    blocked = [event for event in events if event["status"] == "blocked"]
    assert blocked[-1]["phase"] == "cloudflare_preview_apply"
    assert "missing script" in blocked[-1]["stderr"]


def test_project_factory_runner_blocks_when_preview_api_smoke_is_missing(
    tmp_path: Path,
) -> None:
    process_runner = _MissingScriptProcessRunner("scripts/smoke_preview_api.sh")
    runner = _runner(tmp_path, process_runner)
    events: list[dict[str, object]] = []

    with pytest.raises(ProjectFactoryJobRunnerBlockedError):
        runner.run(
            _context(
                tmp_path,
                generator_runs=0,
                reviewer_runs=0,
                publication_validation_mode="remote",
            ),
            event_sink=events.append,
        )

    blocked = [event for event in events if event["status"] == "blocked"]
    assert blocked[-1]["phase"] == "preview_api_smoke"
    assert "missing script" in blocked[-1]["stderr"]


def test_project_factory_runner_blocks_when_web_preview_smoke_is_missing(
    tmp_path: Path,
) -> None:
    process_runner = _MissingScriptProcessRunner("scripts/smoke_web_preview.sh")
    runner = _runner(tmp_path, process_runner)
    events: list[dict[str, object]] = []

    with pytest.raises(ProjectFactoryJobRunnerBlockedError):
        runner.run(
            _context(
                tmp_path,
                generator_runs=0,
                reviewer_runs=0,
                publication_validation_mode="remote",
            ),
            event_sink=events.append,
        )

    blocked = [event for event in events if event["status"] == "blocked"]
    assert blocked[-1]["phase"] == "web_preview_smoke"
    assert "missing script" in blocked[-1]["stderr"]


def test_project_factory_runner_blocks_when_android_preview_release_is_missing(
    tmp_path: Path,
) -> None:
    process_runner = _MissingScriptProcessRunner(
        "scripts/publish_android_preview_release.sh"
    )
    runner = _runner(tmp_path, process_runner)
    events: list[dict[str, object]] = []

    with pytest.raises(ProjectFactoryJobRunnerBlockedError):
        runner.run(
            _context(
                tmp_path,
                generator_runs=0,
                reviewer_runs=0,
                publication_validation_mode="remote",
            ),
            event_sink=events.append,
        )

    blocked = [event for event in events if event["status"] == "blocked"]
    assert blocked[-1]["phase"] == "android_preview_release"
    assert "missing script" in blocked[-1]["stderr"]


def test_project_factory_runner_blocks_when_installable_registration_is_missing(
    tmp_path: Path,
) -> None:
    process_runner = _MissingScriptProcessRunner("scripts/register_installable_app.sh")
    runner = _runner(tmp_path, process_runner)
    events: list[dict[str, object]] = []

    with pytest.raises(ProjectFactoryJobRunnerBlockedError):
        runner.run(
            _context(
                tmp_path,
                generator_runs=0,
                reviewer_runs=0,
                publication_validation_mode="remote",
            ),
            event_sink=events.append,
        )

    blocked = [event for event in events if event["status"] == "blocked"]
    assert blocked[-1]["phase"] == "installable_app_registration"
    assert "missing script" in blocked[-1]["stderr"]


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
            _context(tmp_path, generator_runs=1, reviewer_runs=1),
            event_sink=events.append,
        )

    assert (tmp_path / "clinica-norte").is_dir()
    failed = [event for event in events if event["status"] == "failed"]
    assert failed
    assert failed[0]["phase"] == "generator_pass"
    assert failed[0]["exit_code"] == 7


def test_project_factory_runner_rejects_unpaired_run_counts(tmp_path: Path) -> None:
    process_runner = _FakeProcessRunner()
    runner = _runner(tmp_path, process_runner)

    with pytest.raises(ProjectFactoryJobRunnerError, match="matching run counts"):
        runner.run(
            _context(tmp_path, generator_runs=2, reviewer_runs=1),
            event_sink=lambda _event: None,
        )

    assert process_runner.calls == []


def test_project_factory_runner_blocks_when_remote_publication_fails(
    tmp_path: Path,
) -> None:
    process_runner = _FakeProcessRunner(fail_call=5)
    runner = _runner(tmp_path, process_runner)
    events: list[dict[str, object]] = []

    with pytest.raises(ProjectFactoryJobRunnerBlockedError):
        runner.run(
            _context(
                tmp_path,
                generator_runs=0,
                reviewer_runs=0,
                publication_validation_mode="remote",
            ),
            event_sink=events.append,
        )

    blocked = [event for event in events if event["status"] == "blocked"]
    assert blocked
    assert blocked[-1]["phase"] == "github_publish"
    assert blocked[-1]["command"] == ["bash", "scripts/publish_project.sh"]
    assert blocked[-1]["exit_code"] == 7


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
    def __init__(
        self,
        *,
        fail_call: int | None = None,
        fail_returncode: int = 7,
        timeout_call: int | None = None,
    ):
        self.calls: list[tuple[str, ...]] = []
        self.fail_call = fail_call
        self.fail_returncode = fail_returncode
        self.timeout_call = timeout_call

    def run(self, *, argv, cwd, env, timeout_seconds):
        self.calls.append(tuple(argv))
        call_number = len(self.calls)
        if self.timeout_call == call_number:
            raise subprocess.TimeoutExpired(argv, timeout_seconds)
        if self.fail_call == call_number:
            return ProjectFactoryProcessResult(
                returncode=self.fail_returncode,
                stdout="partial",
                stderr="failed",
            )
        return ProjectFactoryProcessResult(returncode=0, stdout="ok", stderr="")


class _MissingScriptProcessRunner(_FakeProcessRunner):
    def __init__(self, missing_script: str):
        super().__init__()
        self.missing_script = missing_script

    def run(self, *, argv, cwd, env, timeout_seconds):
        self.calls.append(tuple(argv))
        if self.missing_script in argv:
            return ProjectFactoryProcessResult(
                returncode=127,
                stdout="",
                stderr=f"missing script: {self.missing_script}",
            )
        return ProjectFactoryProcessResult(returncode=0, stdout="ok", stderr="")


class _ReusableProjectGenerator:
    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path

    def generate(self, manifest_plan, *, reference_assets=(), project_assets=()):
        return ProjectFactoryGenerationResult(
            ok=True,
            status="ready",
            target_path=str(self.project_path),
            generated_files=(
                ProjectFactoryGeneratedFile(path=".codex/project.yaml", size_bytes=0),
            ),
            git_status="existing",
            message="Existing project foundation verified.",
        )


def _runner(
    tmp_path: Path,
    process_runner: _FakeProcessRunner,
    remote_preflight=None,
) -> ProjectFactoryJobRunner:
    reference_service = ProjectFactoryReferenceAssetService(
        storage_root=tmp_path / ".assets",
    )
    generator = ProjectFactoryGeneratorService(
        reference_asset_service=reference_service,
    )
    return ProjectFactoryJobRunner(
        generator_service=generator,
        process_runner=process_runner,
        remote_preflight=remote_preflight,
    )


def _context(
    tmp_path: Path,
    *,
    generator_runs: int,
    reviewer_runs: int,
    run_generated_validation: bool = False,
    publication_validation_mode: str = "local",
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
        publication_validation_mode=publication_validation_mode,
    )
