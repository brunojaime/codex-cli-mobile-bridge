from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from backend.app.application.services.project_factory_init_service import (
    ProjectFactoryInitCommandResult,
    ProjectFactoryInitService,
)
from backend.app.domain.entities.project_factory_init import (
    ProjectFactoryInitPhaseName,
    ProjectFactoryInitPhaseStatus,
    ProjectFactoryInitRemoteResourceType,
)


@dataclass(frozen=True, slots=True)
class _FakeResponse:
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""


class _FakeRunner:
    def __init__(self, responses: list[tuple[tuple[str, ...], _FakeResponse]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, ...]] = []
        self.envs: list[dict[str, str] | None] = []

    def run(
        self,
        argv: tuple[str, ...],
        *,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: float = 0,
    ) -> ProjectFactoryInitCommandResult:
        del timeout_seconds
        self.calls.append(argv)
        self.envs.append(env)
        assert self.responses, f"Unexpected command: {argv}"
        expected, response = self.responses.pop(0)
        assert argv == expected
        return ProjectFactoryInitCommandResult(
            argv=argv,
            cwd=str(cwd) if cwd is not None else None,
            exit_code=response.exit_code,
            stdout=response.stdout,
            stderr=response.stderr,
            started_at="2026-07-11T00:00:00+00:00",
            completed_at="2026-07-11T00:00:01+00:00",
            env=env,
        )


def test_github_init_creates_repo_sets_origin_pushes_and_persists(
    tmp_path: Path,
) -> None:
    runner = _FakeRunner(_success_create_responses())
    service = ProjectFactoryInitService(
        state_root=tmp_path / "state",
        command_runner=runner,
        github_owner="owner",
    )
    job = service.start_or_resume(
        draft_id="draft-1",
        project_name="Clinica Norte",
        slug="clinica-norte",
        workspace_path=str(tmp_path / "clinica-norte"),
    )

    completed = service.run_github_repository_phase(job.id)

    phase = completed.phase(ProjectFactoryInitPhaseName.GITHUB_REPOSITORY)
    assert phase.status == ProjectFactoryInitPhaseStatus.COMPLETED
    assert ("gh", "repo", "create", "owner/clinica-norte", "--private") in runner.calls
    assert ("git", "remote", "add", "origin", "https://github.com/owner/clinica-norte") in runner.calls
    assert ("git", "push", "-u", "origin", "main") in runner.calls
    repo = _resource(completed, ProjectFactoryInitRemoteResourceType.GITHUB_REPOSITORY)
    branch = _resource(completed, ProjectFactoryInitRemoteResourceType.GITHUB_BRANCH)
    assert repo.url == "https://github.com/owner/clinica-norte"
    assert repo.metadata["defaultBranch"] == "main"
    assert branch.status == "pushed"
    assert branch.metadata["commitSha"] == "abc123"

    reloaded = ProjectFactoryInitService(state_root=tmp_path / "state")
    persisted = reloaded.get_job(job.id)
    assert persisted is not None
    persisted_repo = _resource(
        persisted,
        ProjectFactoryInitRemoteResourceType.GITHUB_REPOSITORY,
    )
    assert persisted_repo.url == "https://github.com/owner/clinica-norte"
    assert persisted.phase(ProjectFactoryInitPhaseName.GITHUB_REPOSITORY).command_evidence


def test_github_init_verifies_existing_repo_without_duplicate_create(
    tmp_path: Path,
) -> None:
    runner = _FakeRunner(_success_existing_responses())
    service = ProjectFactoryInitService(
        state_root=tmp_path / "state",
        command_runner=runner,
        github_owner="owner",
    )
    job = service.start_or_resume(
        draft_id="draft-1",
        project_name="Clinica Norte",
        slug="clinica-norte",
        workspace_path=str(tmp_path / "clinica-norte"),
    )

    completed = service.run_github_repository_phase(job.id)

    assert completed.phase(ProjectFactoryInitPhaseName.GITHUB_REPOSITORY).status == (
        ProjectFactoryInitPhaseStatus.COMPLETED
    )
    assert not [call for call in runner.calls if call[:3] == ("gh", "repo", "create")]
    assert ("git", "remote", "add", "origin", "https://github.com/owner/clinica-norte") not in runner.calls


def test_github_init_repeated_run_does_not_create_duplicate_repo(
    tmp_path: Path,
) -> None:
    runner = _FakeRunner(
        [
            *_success_create_responses(),
            *_success_existing_responses(),
        ]
    )
    service = ProjectFactoryInitService(
        state_root=tmp_path / "state",
        command_runner=runner,
        github_owner="owner",
    )
    job = service.start_or_resume(
        draft_id="draft-1",
        project_name="Clinica Norte",
        slug="clinica-norte",
        workspace_path=str(tmp_path / "clinica-norte"),
    )

    service.run_github_repository_phase(job.id)
    service.run_github_repository_phase(job.id)

    create_calls = [call for call in runner.calls if call[:3] == ("gh", "repo", "create")]
    assert create_calls == [("gh", "repo", "create", "owner/clinica-norte", "--private")]


def test_github_init_blocks_origin_mismatch_without_push(tmp_path: Path) -> None:
    runner = _FakeRunner(
        [
            *_preflight_existing_repo(),
            (("git", "rev-parse", "--is-inside-work-tree"), _FakeResponse(stdout="true\n")),
            (("git", "rev-parse", "--abbrev-ref", "HEAD"), _FakeResponse(stdout="main\n")),
            (("git", "rev-parse", "HEAD"), _FakeResponse(stdout="abc123\n")),
            (
                ("git", "remote", "get-url", "origin"),
                _FakeResponse(stdout="https://github.com/other/repo\n"),
            ),
        ]
    )
    service = _service(tmp_path, runner)
    job = _job(service, tmp_path)

    blocked = service.run_github_repository_phase(job.id)

    phase = blocked.phase(ProjectFactoryInitPhaseName.GITHUB_REPOSITORY)
    assert phase.status == ProjectFactoryInitPhaseStatus.BLOCKED
    assert phase.blockers[0].code == "github_origin_conflict"
    assert phase.blockers[0].command == (
        "git",
        "remote",
        "set-url",
        "origin",
        "https://github.com/owner/clinica-norte",
    )
    assert not [call for call in runner.calls if call[:2] == ("git", "push")]


def test_github_init_blocks_push_failure(tmp_path: Path) -> None:
    runner = _FakeRunner(
        [
            *_preflight_existing_repo(),
            *_local_git_until_missing_origin(),
            (
                ("git", "remote", "add", "origin", "https://github.com/owner/clinica-norte"),
                _FakeResponse(),
            ),
            (
                ("git", "push", "-u", "origin", "main"),
                _FakeResponse(exit_code=1, stderr="network failed"),
            ),
        ]
    )
    service = _service(tmp_path, runner)
    job = _job(service, tmp_path)

    blocked = service.run_github_repository_phase(job.id)

    phase = blocked.phase(ProjectFactoryInitPhaseName.GITHUB_REPOSITORY)
    assert phase.status == ProjectFactoryInitPhaseStatus.BLOCKED
    assert phase.blockers[0].code == "github_push_failed"
    assert phase.blockers[0].command == ("git", "push", "-u", "origin", "main")


def test_github_init_blocks_branch_policy_or_permission_failure(tmp_path: Path) -> None:
    runner = _FakeRunner(
        [
            *_preflight_existing_repo(),
            *_local_git_until_missing_origin(),
            (
                ("git", "remote", "add", "origin", "https://github.com/owner/clinica-norte"),
                _FakeResponse(),
            ),
            (
                ("git", "push", "-u", "origin", "main"),
                _FakeResponse(exit_code=1, stderr="protected branch permission denied"),
            ),
        ]
    )
    service = _service(tmp_path, runner)
    job = _job(service, tmp_path)

    blocked = service.run_github_repository_phase(job.id)

    phase = blocked.phase(ProjectFactoryInitPhaseName.GITHUB_REPOSITORY)
    assert phase.blockers[0].code == "github_branch_policy_or_permission_failure"
    assert "permissions" in phase.blockers[0].next_action.lower()


def test_github_init_blocks_missing_owner_without_running_commands(tmp_path: Path) -> None:
    runner = _FakeRunner([])
    service = ProjectFactoryInitService(
        state_root=tmp_path / "state",
        command_runner=runner,
    )
    job = _job(service, tmp_path)

    blocked = service.run_github_repository_phase(job.id)

    phase = blocked.phase(ProjectFactoryInitPhaseName.GITHUB_REPOSITORY)
    assert phase.blockers[0].code == "github_owner_missing"
    assert phase.blockers[0].command == ("export", "PROJECT_FACTORY_GITHUB_OWNER=<owner>")
    assert runner.calls == []


def test_github_init_blocks_missing_gh_and_auth_failure(tmp_path: Path) -> None:
    missing_gh_runner = _FakeRunner(
        [(("gh", "--version"), _FakeResponse(exit_code=127, stderr="not found"))]
    )
    service = _service(tmp_path / "missing-gh", missing_gh_runner)
    job = _job(service, tmp_path / "missing-gh")

    missing_gh = service.run_github_repository_phase(job.id)

    assert missing_gh.phase(ProjectFactoryInitPhaseName.GITHUB_REPOSITORY).blockers[0].code == (
        "github_cli_missing"
    )

    auth_runner = _FakeRunner(
        [
            (("gh", "--version"), _FakeResponse(stdout="gh version 2\n")),
            (("gh", "auth", "status"), _FakeResponse(exit_code=1, stderr="not logged in")),
        ]
    )
    auth_service = _service(tmp_path / "auth", auth_runner)
    auth_job = _job(auth_service, tmp_path / "auth")

    auth_blocked = auth_service.run_github_repository_phase(auth_job.id)

    auth_phase = auth_blocked.phase(ProjectFactoryInitPhaseName.GITHUB_REPOSITORY)
    assert auth_phase.blockers[0].code == "github_auth_required"
    assert auth_phase.blockers[0].command == ("gh", "auth", "login")


def test_github_init_blocks_repo_conflict_and_view_permission(tmp_path: Path) -> None:
    conflict_runner = _FakeRunner(
        [
            (("gh", "--version"), _FakeResponse(stdout="gh version 2\n")),
            (("gh", "auth", "status"), _FakeResponse(stdout="ok\n")),
            (
                _view_cmd(),
                _FakeResponse(
                    stdout=_repo_json(owner="other", name="clinica-norte"),
                ),
            ),
        ]
    )
    conflict_service = _service(tmp_path / "conflict", conflict_runner)
    conflict_job = _job(conflict_service, tmp_path / "conflict")

    conflicted = conflict_service.run_github_repository_phase(conflict_job.id)

    assert conflicted.phase(ProjectFactoryInitPhaseName.GITHUB_REPOSITORY).blockers[0].code == (
        "github_repo_conflict"
    )

    permission_runner = _FakeRunner(
        [
            (("gh", "--version"), _FakeResponse(stdout="gh version 2\n")),
            (("gh", "auth", "status"), _FakeResponse(stdout="ok\n")),
            (_view_cmd(), _FakeResponse(exit_code=1, stderr="forbidden")),
        ]
    )
    permission_service = _service(tmp_path / "permission", permission_runner)
    permission_job = _job(permission_service, tmp_path / "permission")

    blocked = permission_service.run_github_repository_phase(permission_job.id)

    assert blocked.phase(ProjectFactoryInitPhaseName.GITHUB_REPOSITORY).blockers[0].code == (
        "github_repo_permission_blocked"
    )


def test_github_command_evidence_redacts_secret_values(tmp_path: Path) -> None:
    runner = _FakeRunner(
        [
            (
                ("gh", "--version"),
                _FakeResponse(
                    stdout="token secret-token visible",
                    stderr="secret-token stderr",
                ),
            ),
            (("gh", "auth", "status"), _FakeResponse(exit_code=1, stderr="bad secret-token")),
        ]
    )
    service = ProjectFactoryInitService(
        state_root=tmp_path / "state",
        command_runner=runner,
        github_owner="owner",
        command_env={"GH_TOKEN": "secret-token"},
    )
    job = _job(service, tmp_path)

    blocked = service.run_github_repository_phase(job.id)

    phase = blocked.phase(ProjectFactoryInitPhaseName.GITHUB_REPOSITORY)
    evidence = phase.command_evidence[0]
    assert "secret-token" not in evidence.stdout_summary
    assert "secret-token" not in evidence.stderr_summary
    assert "GH_TOKEN" in evidence.redacted_env_keys
    assert all(env == {"GH_TOKEN": "secret-token"} for env in runner.envs)


def _service(tmp_path: Path, runner: _FakeRunner) -> ProjectFactoryInitService:
    return ProjectFactoryInitService(
        state_root=tmp_path / "state",
        command_runner=runner,
        github_owner="owner",
    )


def _job(service: ProjectFactoryInitService, tmp_path: Path):
    return service.start_or_resume(
        draft_id="draft-1",
        project_name="Clinica Norte",
        slug="clinica-norte",
        workspace_path=str(tmp_path / "clinica-norte"),
    )


def _resource(job, resource_type: ProjectFactoryInitRemoteResourceType):
    for resource in job.remote_resources:
        if resource.type == resource_type:
            return resource
    raise AssertionError(f"Missing resource: {resource_type.value}")


def _success_create_responses() -> list[tuple[tuple[str, ...], _FakeResponse]]:
    return [
        (("gh", "--version"), _FakeResponse(stdout="gh version 2\n")),
        (("gh", "auth", "status"), _FakeResponse(stdout="ok\n")),
        (_view_cmd(), _FakeResponse(exit_code=1, stderr="Could not resolve to a Repository")),
        (("gh", "repo", "create", "owner/clinica-norte", "--private"), _FakeResponse()),
        (_view_cmd(), _FakeResponse(stdout=_repo_json())),
        *_local_git_until_missing_origin(),
        (
            ("git", "remote", "add", "origin", "https://github.com/owner/clinica-norte"),
            _FakeResponse(),
        ),
        (("git", "push", "-u", "origin", "main"), _FakeResponse()),
    ]


def _success_existing_responses() -> list[tuple[tuple[str, ...], _FakeResponse]]:
    return [
        *_preflight_existing_repo(),
        (("git", "rev-parse", "--is-inside-work-tree"), _FakeResponse(stdout="true\n")),
        (("git", "rev-parse", "--abbrev-ref", "HEAD"), _FakeResponse(stdout="main\n")),
        (("git", "rev-parse", "HEAD"), _FakeResponse(stdout="abc123\n")),
        (
            ("git", "remote", "get-url", "origin"),
            _FakeResponse(stdout="https://github.com/owner/clinica-norte\n"),
        ),
        (("git", "push", "-u", "origin", "main"), _FakeResponse()),
    ]


def _preflight_existing_repo() -> list[tuple[tuple[str, ...], _FakeResponse]]:
    return [
        (("gh", "--version"), _FakeResponse(stdout="gh version 2\n")),
        (("gh", "auth", "status"), _FakeResponse(stdout="ok\n")),
        (_view_cmd(), _FakeResponse(stdout=_repo_json())),
    ]


def _local_git_until_missing_origin() -> list[tuple[tuple[str, ...], _FakeResponse]]:
    return [
        (("git", "rev-parse", "--is-inside-work-tree"), _FakeResponse(stdout="true\n")),
        (("git", "rev-parse", "--abbrev-ref", "HEAD"), _FakeResponse(stdout="main\n")),
        (("git", "rev-parse", "HEAD"), _FakeResponse(stdout="abc123\n")),
        (("git", "remote", "get-url", "origin"), _FakeResponse(exit_code=2, stderr="No such remote")),
    ]


def _view_cmd() -> tuple[str, ...]:
    return (
        "gh",
        "repo",
        "view",
        "owner/clinica-norte",
        "--json",
        "name,owner,url,defaultBranchRef,visibility",
    )


def _repo_json(*, owner: str = "owner", name: str = "clinica-norte") -> str:
    return json.dumps(
        {
            "name": name,
            "owner": {"login": owner},
            "url": f"https://github.com/{owner}/{name}",
            "defaultBranchRef": {"name": "main"},
            "visibility": "PRIVATE",
        }
    )
