from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path

import yaml

from backend.app.application.services.project_factory_init_service import (
    ProjectFactoryInitCommandResult,
    ProjectFactoryInitService,
)
from backend.app.application.services import project_factory_init_service as init_module
from backend.app.domain.entities.project_factory_init import (
    ProjectFactoryInitPhaseName,
    ProjectFactoryInitPhaseStatus,
    ProjectFactoryInitRemoteResourceType,
)
from backend.app.infrastructure.config.settings import Settings


@dataclass(frozen=True, slots=True)
class _FakeResponse:
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    on_run: Callable[[Path], None] | None = None


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
        if argv == ("flutter", "create", "--platforms=android", "."):
            _write_android_build_gradle(Path(cwd or ""))
            return ProjectFactoryInitCommandResult(
                argv=argv,
                cwd=str(cwd) if cwd is not None else None,
                exit_code=0,
                stdout="created android\n",
                started_at="2026-07-11T00:00:00+00:00",
                completed_at="2026-07-11T00:00:01+00:00",
                env=env,
            )
        assert self.responses, f"Unexpected command: {argv}"
        expected, response = self.responses.pop(0)
        if not _argv_matches(argv, expected) and _is_auto_github_actions_config_cmd(
            argv
        ):
            self.responses.insert(0, (expected, response))
            stdout = (
                "https://github.com/owner/clinica-norte\n"
                if argv == ("git", "remote", "get-url", "origin")
                else ""
            )
            return ProjectFactoryInitCommandResult(
                argv=argv,
                cwd=str(cwd) if cwd is not None else None,
                exit_code=0,
                stdout=stdout,
                started_at="2026-07-11T00:00:00+00:00",
                completed_at="2026-07-11T00:00:01+00:00",
                env=env,
            )
        assert len(argv) == len(expected)
        assert _argv_matches(argv, expected)
        cwd_path = Path(cwd) if cwd is not None else Path()
        if response.on_run is not None:
            response.on_run(cwd_path)
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


def _argv_matches(actual: tuple[str, ...], expected: tuple[str, ...]) -> bool:
    return len(actual) == len(expected) and all(
        expected_part == "__ANY__" or actual_part == expected_part
        for actual_part, expected_part in zip(actual, expected, strict=True)
    )


def _is_auto_github_actions_config_cmd(argv: tuple[str, ...]) -> bool:
    return (
        argv == ("git", "remote", "get-url", "origin")
        or argv[:3] == ("gh", "variable", "set")
        or argv[:3] == ("gh", "secret", "set")
    )


def test_android_release_creates_prerelease_registers_bridge_and_persists(
    tmp_path: Path,
) -> None:
    release_tag = "android-preview-v0.1.0-build.1"
    runner = _FakeRunner(
        [
            (
                _release_view_cmd(release_tag),
                _FakeResponse(exit_code=1, stderr="not found"),
            ),
            (
                _publish_cmd(),
                _FakeResponse(stdout="secret-token built", on_run=_write_apk),
            ),
            (
                _release_view_cmd(release_tag),
                _FakeResponse(stdout=json.dumps(_release(release_tag))),
            ),
            (_lookup_cmd(), _FakeResponse(exit_code=22, stderr="not found")),
            (_register_cmd(), _FakeResponse(stdout="registered")),
            (
                _lookup_cmd(),
                _FakeResponse(stdout=json.dumps(_installable(release_tag))),
            ),
        ]
    )
    service = _service(tmp_path, runner)
    job = _generated_job(service)

    completed = service.run_android_preview_release_phases(job.id)

    release_phase = completed.phase(ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE)
    install_phase = completed.phase(
        ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION
    )
    assert release_phase.status == ProjectFactoryInitPhaseStatus.COMPLETED
    assert install_phase.status == ProjectFactoryInitPhaseStatus.COMPLETED
    assert _publish_cmd() in runner.calls
    assert _register_cmd() in runner.calls
    publish_env = runner.envs[runner.calls.index(_publish_cmd())] or {}
    assert publish_env["APP_RUNTIME_PROFILE"] == "preview"
    assert publish_env["API_RUNTIME"] == "cloudflare_preview"
    assert publish_env["API_BASE_URL"] == (
        "https://preview.nienfos.com/clinica-norte/api"
    )
    assert publish_env["ANDROID_PREVIEW_RELEASE_MODE"] == "bridge_local"
    assert publish_env["APP_RELEASE_TAG"] == release_tag
    assert publish_env["BRIDGE_REGISTRATION_TOKEN"] == "secret-token"
    assert publish_env["BRIDGE_PUBLIC_URL"] == "https://bridge.test"
    assert publish_env["BRIDGE_REGISTRATION_URL"] == "http://127.0.0.1:8000"
    variable_sets = {
        call[3]: call[5]
        for call in runner.calls
        if call[:3] == ("gh", "variable", "set")
    }
    assert variable_sets["API_BASE_URL"] == (
        "https://preview.nienfos.com/clinica-norte/api"
    )
    assert variable_sets["CODEX_BRIDGE_DEV_MODE"] == "true"
    assert variable_sets["CODEX_BRIDGE_WORKBENCH_URL"] == "https://bridge.test"
    assert variable_sets["CODEX_FEEDBACK_ENABLED"] == "true"
    assert variable_sets["CODEX_FEEDBACK_BRIDGE_URL"] == "https://bridge.test"
    assert variable_sets["CODEX_APP_UPDATER_BRIDGE_URL"] == "https://bridge.test"
    mobile = tmp_path / "projects/clinica-norte/apps/mobile"
    android_manifest = (mobile / "android/app/src/main/AndroidManifest.xml").read_text(
        encoding="utf-8"
    )
    assert 'android:networkSecurityConfig="@xml/network_security_config"' in (
        android_manifest
    )
    network_security = (
        mobile / "android/app/src/main/res/xml/network_security_config.xml"
    ).read_text(encoding="utf-8")
    assert "tail0302c4.ts.net" in network_security
    assert "localhost" not in json.dumps(completed.to_payload())
    apk = next(
        artifact
        for artifact in release_phase.artifacts
        if artifact.kind == "android_preview_apk"
    )
    assert apk.path and apk.path.endswith("clinica-norte.apk")
    assert apk.sha256
    release = _resource(completed, ProjectFactoryInitRemoteResourceType.GITHUB_RELEASE)
    installable = _resource(
        completed,
        ProjectFactoryInitRemoteResourceType.BRIDGE_INSTALLABLE_APP,
    )
    assert release.identifier == release_tag
    assert release.status == "prerelease_verified"
    assert installable.identifier == "clinica-norte"
    assert installable.metadata["releaseChannel"] == "prerelease"
    assert installable.metadata["mockOrDemo"] is False

    reloaded = ProjectFactoryInitService(
        state_root=tmp_path / "state",
        settings=_settings(tmp_path),
    )
    persisted = reloaded.get_job(job.id)
    assert persisted is not None
    assert _resource(persisted, ProjectFactoryInitRemoteResourceType.GITHUB_RELEASE)
    assert persisted.phase(
        ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION
    ).command_evidence
    assert "secret-token" not in json.dumps(persisted.to_payload())


def test_android_release_uses_public_bridge_url_when_transport_is_local(
    tmp_path: Path,
) -> None:
    release_tag = "android-preview-v0.1.0-build.1"
    public_lookup = (
        "curl",
        "-fsS",
        "-H",
        "Host: bridge.test",
        "-H",
        "X-Forwarded-Proto: https",
        "http://127.0.0.1:8000/installable-apps/clinica-norte",
    )
    runner = _FakeRunner(
        [
            (
                _release_view_cmd(release_tag),
                _FakeResponse(stdout=json.dumps(_release(release_tag))),
            ),
            (public_lookup, _FakeResponse(exit_code=22, stderr="not found")),
            (_register_cmd(), _FakeResponse(stdout="registered")),
            (
                public_lookup,
                _FakeResponse(stdout=json.dumps(_installable(release_tag))),
            ),
        ]
    )
    service = _service(
        tmp_path,
        runner,
        api_base_url="http://localhost:8000",
        app_update_public_base_url="https://bridge.test",
    )
    job = _generated_job(service)

    completed = service.run_android_preview_release_phases(job.id)

    phase = completed.phase(ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION)
    assert phase.status == ProjectFactoryInitPhaseStatus.COMPLETED
    assert public_lookup in runner.calls
    register_env = runner.envs[runner.calls.index(_register_cmd())] or {}
    assert register_env["BRIDGE_REGISTRATION_URL"] == "http://127.0.0.1:8000"
    assert register_env["BRIDGE_PUBLIC_URL"] == "https://bridge.test"
    assert "localhost" not in json.dumps(
        [resource.to_payload() for resource in completed.remote_resources]
    )


def test_bridge_public_url_ignores_app_preview_api_base_url(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        api_base_url="http://localhost:8000",
        app_update_public_base_url="https://preview.nienfos.com/satshowroom/api",
    )

    resolved = init_module._resolve_bridge_public_url(
        "http://localhost:8000",
        settings=settings,
        command_env={"BRIDGE_PUBLIC_URL": "https://bridge.example.test"},
    )

    assert resolved == "https://bridge.example.test"


def test_workbench_phase_aligns_verified_foundation_tasks_and_pushes(
    tmp_path: Path,
) -> None:
    aligned_paths = (
        "specs/001-product-foundation/tree.json",
        "specs/001-product-foundation/tasks.md",
        "specs/001-product-foundation/tasks/plan-1-task-10/task.md",
        "specs/001-product-foundation/tasks/plan-1-task-11/task.md",
        "specs/001-product-foundation/metadata.yaml",
    )
    runner = _FakeRunner(
        [
            (("git", "add", *aligned_paths), _FakeResponse()),
            (
                (
                    "git",
                    "-c",
                    "user.name=Codex Project Factory",
                    "-c",
                    "user.email=codex-project-factory@local",
                    "commit",
                    "-m",
                    "Align verified Project Factory task status",
                ),
                _FakeResponse(stdout="[main abc123] aligned\n"),
            ),
            (
                ("git", "rev-parse", "--abbrev-ref", "HEAD"),
                _FakeResponse(stdout="main\n"),
            ),
            (("git", "push", "origin", "main"), _FakeResponse()),
        ]
    )
    service = _service(tmp_path, runner)
    job = _generated_job(service, create_signing=False)
    for phase_name in (
        ProjectFactoryInitPhaseName.LOCAL_VALIDATION,
        ProjectFactoryInitPhaseName.PREVIEW_SMOKE,
        ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE,
        ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION,
    ):
        job = service.complete_phase(job.id, phase_name.value)

    completed = service._complete_workbench_feedback_phase(job.id)

    project = tmp_path / "projects/clinica-norte"
    tree = json.loads(
        (project / "specs/001-product-foundation/tree.json").read_text(
            encoding="utf-8",
        )
    )
    statuses = {task["id"]: task["status"] for task in tree["plans"][0]["tasks"]}
    assert statuses["plan-1-task-10"] == "done"
    assert statuses["plan-1-task-11"] == "done"
    tasks_md = (project / "specs/001-product-foundation/tasks.md").read_text(
        encoding="utf-8"
    )
    assert "- [x] Wire Feedback Bridge and updater." in tasks_md
    assert "- [x] Validate Workbench integration and release readiness." in tasks_md
    metadata = yaml.safe_load(
        (project / "specs/001-product-foundation/metadata.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert metadata["tasks"] == {"total": 11, "completed": 9, "pending": 2}
    phase = completed.phase(
        ProjectFactoryInitPhaseName.WORKBENCH_AND_FEEDBACK_VERIFICATION
    )
    assert phase.status == ProjectFactoryInitPhaseStatus.COMPLETED
    assert any(
        artifact.kind == "verified_foundation_task_alignment"
        for artifact in phase.artifacts
    )
    assert ("git", "push", "origin", "main") in runner.calls


def test_android_github_variables_use_http_for_tailscale_bridge(
    tmp_path: Path,
) -> None:
    runner = _FakeRunner(
        [
            (
                ("git", "remote", "get-url", "origin"),
                _FakeResponse(stdout="https://github.com/owner/clinica-norte\n"),
            ),
            *[(_any_variable_set_cmd(), _FakeResponse()) for _ in range(6)],
            (_any_secret_set_cmd(), _FakeResponse()),
        ]
    )
    service = _service(tmp_path, runner)
    project = tmp_path / "projects/clinica-norte"
    project.mkdir(parents=True)
    _write_existing_signing(tmp_path)

    evidence, blocker = service._ensure_android_github_actions_config(
        "clinica-norte",
        cwd=project,
        preview_api="https://preview.nienfos.com/clinica-norte/api",
        bridge_public_url="https://batata-default-string.tail0302c4.ts.net",
    )

    variable_sets = {
        call[3]: call[5]
        for call in runner.calls
        if call[:3] == ("gh", "variable", "set")
    }
    assert blocker is None
    assert evidence
    assert variable_sets["API_BASE_URL"] == (
        "https://preview.nienfos.com/clinica-norte/api"
    )
    assert variable_sets["CODEX_BRIDGE_DEV_MODE"] == "true"
    assert variable_sets["CODEX_BRIDGE_WORKBENCH_URL"] == (
        "http://batata-default-string.tail0302c4.ts.net"
    )
    assert variable_sets["CODEX_FEEDBACK_BRIDGE_URL"] == (
        "http://batata-default-string.tail0302c4.ts.net"
    )
    assert variable_sets["CODEX_APP_UPDATER_BRIDGE_URL"] == (
        "http://batata-default-string.tail0302c4.ts.net"
    )


def test_frontend_baseline_repairs_generated_artifact_gitignore_entries(
    tmp_path: Path,
) -> None:
    runner = _FakeRunner([])
    service = _service(tmp_path, runner)
    job = service.start_or_resume(
        draft_id="draft-flutter",
        project_name="Clinica Norte",
        slug="clinica-norte",
        frontend_strategy="flutter",
    )
    service.run_frontend_baseline_phase(job.id)
    project = tmp_path / "projects/clinica-norte"
    gitignore = project / ".gitignore"
    original = gitignore.read_text(encoding="utf-8")
    stale = "\n".join(
        line
        for line in original.splitlines()
        if line
        not in {
            ".generated-validation/",
            "backend/.venv/",
            "backend/*.egg-info/",
        }
    )
    gitignore.write_text(stale + "\n", encoding="utf-8")

    repaired = service.run_frontend_baseline_phase(job.id)

    repaired_gitignore = gitignore.read_text(encoding="utf-8")
    assert ".generated-validation/" in repaired_gitignore
    assert "backend/.venv/" in repaired_gitignore
    assert "backend/*.egg-info/" in repaired_gitignore
    phase = repaired.phase(ProjectFactoryInitPhaseName.FLUTTER_OR_STRATEGY_BASELINE)
    assert any(
        evidence.argv
        == (
            "project-factory-generator",
            "repair-gitignore",
            "flutter",
            "clinica-norte",
        )
        for evidence in phase.command_evidence
    )


def test_android_release_generates_preview_signing_when_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    release_tag = "android-preview-v0.1.0-build.1"
    keytool = tmp_path / "bin/keytool"
    keytool.parent.mkdir(parents=True)
    keytool.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(
        init_module.shutil,
        "which",
        lambda name: str(keytool) if name == "keytool" else None,
    )

    runner = _FakeRunner(
        [
            (
                _keytool_cmd(keytool, tmp_path),
                _FakeResponse(
                    on_run=lambda _project: _write_generated_keystore(tmp_path)
                ),
            ),
            (
                _release_view_cmd(release_tag),
                _FakeResponse(exit_code=1, stderr="not found"),
            ),
            (
                _publish_cmd(),
                _FakeResponse(stdout="built", on_run=_write_apk),
            ),
            (
                _release_view_cmd(release_tag),
                _FakeResponse(stdout=json.dumps(_release(release_tag))),
            ),
            (_lookup_cmd(), _FakeResponse(exit_code=22, stderr="not found")),
            (_register_cmd(), _FakeResponse(stdout="registered")),
            (
                _lookup_cmd(),
                _FakeResponse(stdout=json.dumps(_installable(release_tag))),
            ),
        ]
    )
    service = _service(tmp_path, runner, create_signing=False)
    job = _generated_job(service, create_signing=False)

    completed = service.run_android_preview_release_phases(job.id)

    assert (
        completed.phase(ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE).status
        == ProjectFactoryInitPhaseStatus.COMPLETED
    )
    assert (tmp_path / "secrets/clinica-norte-preview-signing.env").is_file()
    assert (tmp_path / "secrets/clinica-norte-preview-upload-keystore.jks").is_file()
    evidence = completed.phase(
        ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE
    ).command_evidence[0]
    assert evidence.argv[0] == str(keytool)
    assert "ANDROID_STORE_PASSWORD" in evidence.redacted_env_keys
    assert "ANDROID_KEY_PASSWORD" in evidence.redacted_env_keys
    payload = json.dumps(completed.to_payload())
    signing_env = (tmp_path / "secrets/clinica-norte-preview-signing.env").read_text(
        encoding="utf-8"
    )
    for line in signing_env.splitlines():
        if "_PASSWORD=" in line:
            assert line.split("=", 1)[1] not in payload


def test_android_release_commits_safe_generated_gitignore_repair_before_retry(
    tmp_path: Path,
) -> None:
    release_tag = "android-preview-v0.1.0-build.1"
    runner = _FakeRunner(
        [
            (
                _release_view_cmd(release_tag),
                _FakeResponse(exit_code=1, stderr="not found"),
            ),
            (
                _publish_cmd(),
                _FakeResponse(
                    exit_code=2,
                    stderr=(
                        "M .gitignore\n"
                        "android preview release blocked: working tree must be "
                        "clean before tagging the preview release\n"
                    ),
                ),
            ),
            (
                ("git", "diff", "--", ".gitignore"),
                _FakeResponse(
                    stdout=(
                        "diff --git a/.gitignore b/.gitignore\n"
                        "@@\n"
                        "+.generated-validation/\n"
                        "+backend/.venv/\n"
                        "+backend/*.egg-info/\n"
                    ),
                ),
            ),
            (("git", "add", ".gitignore"), _FakeResponse()),
            (
                (
                    "git",
                    "commit",
                    "-m",
                    "Ignore generated Project Factory artifacts",
                ),
                _FakeResponse(
                    stdout="[main abc123] Ignore generated Project Factory artifacts"
                ),
            ),
            (("git", "push"), _FakeResponse(stdout="pushed")),
            (_publish_cmd(), _FakeResponse(stdout="built", on_run=_write_apk)),
            (
                _release_view_cmd(release_tag),
                _FakeResponse(stdout=json.dumps(_release(release_tag))),
            ),
            (_lookup_cmd(), _FakeResponse(exit_code=22, stderr="not found")),
            (_register_cmd(), _FakeResponse(stdout="registered")),
            (
                _lookup_cmd(),
                _FakeResponse(stdout=json.dumps(_installable(release_tag))),
            ),
        ]
    )
    service = _service(tmp_path, runner)
    job = _generated_job(service)

    completed = service.run_android_preview_release_phases(job.id)

    assert (
        completed.phase(ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE).status
        == ProjectFactoryInitPhaseStatus.COMPLETED
    )
    assert runner.calls.count(_publish_cmd()) == 2
    assert ("git", "add", ".gitignore") in runner.calls
    assert (
        "git",
        "commit",
        "-m",
        "Ignore generated Project Factory artifacts",
    ) in runner.calls
    assert ("git", "push") in runner.calls


def test_android_release_commits_generated_android_platform_before_retry(
    tmp_path: Path,
) -> None:
    release_tag = "android-preview-v0.1.0-build.1"
    runner = _FakeRunner(
        [
            (
                _release_view_cmd(release_tag),
                _FakeResponse(exit_code=1, stderr="not found"),
            ),
            (
                _publish_cmd(),
                _FakeResponse(
                    exit_code=2,
                    stdout=(
                        "Recreating project ....\n"
                        "  android/app/build.gradle.kts (created)\n"
                    ),
                    stderr=(
                        "?? apps/mobile/.metadata\n"
                        "?? apps/mobile/android/app/build.gradle.kts\n"
                        "?? apps/mobile/android/app/src/main/kotlin/com/example/clinica_norte/MainActivity.kt\n"
                        "android preview release blocked: working tree must be "
                        "clean before tagging the preview release\n"
                    ),
                ),
            ),
            (
                ("git", "status", "--porcelain"),
                _FakeResponse(
                    stdout=(
                        "?? apps/mobile/.metadata\n"
                        "?? apps/mobile/android/app/build.gradle.kts\n"
                        "?? apps/mobile/android/app/src/main/kotlin/com/example/clinica_norte/MainActivity.kt\n"
                    ),
                ),
            ),
            (
                (
                    "git",
                    "add",
                    "apps/mobile/.metadata",
                    "apps/mobile/android/app/build.gradle.kts",
                    "apps/mobile/android/app/src/main/kotlin/com/example/clinica_norte/MainActivity.kt",
                ),
                _FakeResponse(),
            ),
            (
                ("git", "commit", "-m", "Generate Flutter Android platform"),
                _FakeResponse(stdout="[main def456] Generate Flutter Android platform"),
            ),
            (("git", "push"), _FakeResponse(stdout="pushed")),
            (_publish_cmd(), _FakeResponse(stdout="built", on_run=_write_apk)),
            (
                _release_view_cmd(release_tag),
                _FakeResponse(stdout=json.dumps(_release(release_tag))),
            ),
            (_lookup_cmd(), _FakeResponse(exit_code=22, stderr="not found")),
            (_register_cmd(), _FakeResponse(stdout="registered")),
            (
                _lookup_cmd(),
                _FakeResponse(stdout=json.dumps(_installable(release_tag))),
            ),
        ]
    )
    service = _service(tmp_path, runner)
    job = _generated_job(service)

    completed = service.run_android_preview_release_phases(job.id)

    assert (
        completed.phase(ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE).status
        == ProjectFactoryInitPhaseStatus.COMPLETED
    )
    assert runner.calls.count(_publish_cmd()) == 2
    assert (
        "git",
        "commit",
        "-m",
        "Generate Flutter Android platform",
    ) in runner.calls
    assert ("git", "push") in runner.calls


def test_android_release_verifies_existing_prerelease_and_installable_without_publish(
    tmp_path: Path,
) -> None:
    release_tag = "android-preview-v0.1.0-build.1"
    runner = _FakeRunner(
        [
            (
                _release_view_cmd(release_tag),
                _FakeResponse(stdout=json.dumps(_release(release_tag))),
            ),
            (
                _lookup_cmd(),
                _FakeResponse(stdout=json.dumps(_installable(release_tag))),
            ),
        ]
    )
    service = _service(tmp_path, runner)
    job = _generated_job(service)

    completed = service.run_android_preview_release_phases(job.id)

    assert completed.phase(
        ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE
    ).status == (ProjectFactoryInitPhaseStatus.COMPLETED)
    assert _publish_cmd() not in runner.calls
    assert _register_cmd() not in runner.calls


def test_android_release_rerun_is_idempotent_after_create(
    tmp_path: Path,
) -> None:
    release_tag = "android-preview-v0.1.0-build.1"
    runner = _FakeRunner(
        [
            (
                _release_view_cmd(release_tag),
                _FakeResponse(exit_code=1, stderr="not found"),
            ),
            (_publish_cmd(), _FakeResponse(stdout="built", on_run=_write_apk)),
            (
                _release_view_cmd(release_tag),
                _FakeResponse(stdout=json.dumps(_release(release_tag))),
            ),
            (_lookup_cmd(), _FakeResponse(exit_code=22, stderr="not found")),
            (_register_cmd(), _FakeResponse(stdout="registered")),
            (
                _lookup_cmd(),
                _FakeResponse(stdout=json.dumps(_installable(release_tag))),
            ),
            (
                _release_view_cmd(release_tag),
                _FakeResponse(stdout=json.dumps(_release(release_tag))),
            ),
            (
                _lookup_cmd(),
                _FakeResponse(stdout=json.dumps(_installable(release_tag))),
            ),
        ]
    )
    service = _service(tmp_path, runner)
    job = _generated_job(service)

    service.run_android_preview_release_phases(job.id)
    second = service.run_android_preview_release_phases(job.id)

    assert (
        second.phase(ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION).status
        == ProjectFactoryInitPhaseStatus.COMPLETED
    )
    assert runner.calls.count(_publish_cmd()) == 1
    assert runner.calls.count(_register_cmd()) == 1


def test_android_release_preserves_svelte_web_only_skip(
    tmp_path: Path,
) -> None:
    runner = _FakeRunner([])
    service = _service(tmp_path, runner)
    job = service.start_or_resume(
        draft_id="draft-svelte",
        project_name="Clinica Norte",
        slug="clinica-norte",
        frontend_strategy="svelte",
    )
    baseline = service.run_frontend_baseline_phase(job.id)

    completed = service.run_android_preview_release_phases(baseline.id)

    assert runner.calls == []
    assert completed.phase(
        ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE
    ).status == (ProjectFactoryInitPhaseStatus.SKIPPED)
    assert (
        completed.phase(
            ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION
        ).status
        == ProjectFactoryInitPhaseStatus.SKIPPED
    )


def test_android_release_blocks_missing_tooling_or_signing_with_redaction(
    tmp_path: Path,
) -> None:
    release_tag = "android-preview-v0.1.0-build.1"
    runner = _FakeRunner(
        [
            (
                _release_view_cmd(release_tag),
                _FakeResponse(exit_code=1, stderr="not found"),
            ),
            (
                _publish_cmd(),
                _FakeResponse(
                    exit_code=2,
                    stderr=(
                        "flutter missing; signing token secret-token; "
                        "keystore signing-secret"
                    ),
                ),
            ),
        ]
    )
    service = _service(
        tmp_path,
        runner,
        command_env={"ANDROID_STORE_PASSWORD": "signing-secret"},
    )
    job = _generated_job(service)

    blocked = service.run_android_preview_release_phases(job.id)

    phase = blocked.phase(ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE)
    assert phase.status == ProjectFactoryInitPhaseStatus.BLOCKED
    assert phase.blockers[0].code == "android_preview_tooling_or_signing_missing"
    assert phase.blockers[0].command == _publish_cmd()
    evidence = phase.command_evidence[-1]
    assert "secret-token" not in evidence.stderr_summary
    assert "signing-secret" not in evidence.stderr_summary
    assert "INSTALLABLE_APPS_REGISTRATION_TOKEN" in evidence.redacted_env_keys
    assert "ANDROID_STORE_PASSWORD" in evidence.redacted_env_keys


def test_android_release_publish_uses_same_bridge_root_as_generated_signing(
    tmp_path: Path,
) -> None:
    release_tag = "android-preview-v0.1.0-build.1"
    runner = _FakeRunner(
        [
            (
                _release_view_cmd(release_tag),
                _FakeResponse(exit_code=1, stderr="not found"),
            ),
            (_publish_cmd(), _FakeResponse(exit_code=2, stderr="publish blocked")),
        ]
    )
    bridge_root = tmp_path / "bridge-root"
    service = _service(
        tmp_path,
        runner,
        command_env={"CODEX_MOBILE_BRIDGE_ROOT": str(bridge_root)},
    )
    job = _generated_job(service)

    service.run_android_preview_release_phases(job.id)

    publish_env = runner.envs[runner.calls.index(_publish_cmd())] or {}
    assert publish_env["CODEX_MOBILE_BRIDGE_ROOT"] == str(bridge_root)
    assert (bridge_root / "secrets/clinica-norte-preview-signing.env").is_file()
    assert (bridge_root / "secrets/clinica-norte-preview-upload-keystore.jks").is_file()


def test_android_release_blocks_generic_publish_failure(
    tmp_path: Path,
) -> None:
    release_tag = "android-preview-v0.1.0-build.1"
    runner = _FakeRunner(
        [
            (
                _release_view_cmd(release_tag),
                _FakeResponse(exit_code=1, stderr="not found"),
            ),
            (_publish_cmd(), _FakeResponse(exit_code=1, stderr="upload failed")),
        ]
    )
    service = _service(tmp_path, runner)
    job = _generated_job(service)

    blocked = service.run_android_preview_release_phases(job.id)

    phase = blocked.phase(ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE)
    assert phase.status == ProjectFactoryInitPhaseStatus.BLOCKED
    assert phase.blockers[0].code == "android_preview_release_publish_failed"
    assert phase.blockers[0].command == _publish_cmd()


def test_android_release_blocks_missing_apk_asset_after_publish(
    tmp_path: Path,
) -> None:
    release_tag = "android-preview-v0.1.0-build.1"
    runner = _FakeRunner(
        [
            (
                _release_view_cmd(release_tag),
                _FakeResponse(exit_code=1, stderr="not found"),
            ),
            (_publish_cmd(), _FakeResponse(stdout="built")),
            (
                _release_view_cmd(release_tag),
                _FakeResponse(stdout=json.dumps(_release(release_tag, assets=[]))),
            ),
        ]
    )
    service = _service(tmp_path, runner)
    job = _generated_job(service)

    blocked = service.run_android_preview_release_phases(job.id)

    phase = blocked.phase(ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE)
    assert phase.status == ProjectFactoryInitPhaseStatus.BLOCKED
    assert phase.blockers[0].code == "android_preview_release_asset_missing"
    assert phase.blockers[0].command == _publish_cmd()


def test_android_release_blocks_bridge_registration_without_token(
    tmp_path: Path,
) -> None:
    release_tag = "android-preview-v0.1.0-build.1"
    runner = _FakeRunner(
        [
            (
                _release_view_cmd(release_tag),
                _FakeResponse(stdout=json.dumps(_release(release_tag))),
            ),
            (_lookup_cmd(), _FakeResponse(exit_code=22, stderr="not found")),
        ]
    )
    service = _service(tmp_path, runner, registration_token=None)
    job = _generated_job(service)

    blocked = service.run_android_preview_release_phases(job.id)

    phase = blocked.phase(ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION)
    assert phase.status == ProjectFactoryInitPhaseStatus.BLOCKED
    assert phase.blockers[0].code == "bridge_installable_registration_token_missing"
    assert phase.blockers[0].command == (
        "export",
        "INSTALLABLE_APPS_REGISTRATION_TOKEN=<token>",
    )


def test_android_release_blocks_installable_lookup_failure_after_registration(
    tmp_path: Path,
) -> None:
    release_tag = "android-preview-v0.1.0-build.1"
    runner = _FakeRunner(
        [
            (
                _release_view_cmd(release_tag),
                _FakeResponse(stdout=json.dumps(_release(release_tag))),
            ),
            (_lookup_cmd(), _FakeResponse(exit_code=22, stderr="not found")),
            (_register_cmd(), _FakeResponse(stdout="registered")),
            (_lookup_cmd(), _FakeResponse(exit_code=52, stderr="bridge unavailable")),
        ]
    )
    service = _service(tmp_path, runner)
    job = _generated_job(service)

    blocked = service.run_android_preview_release_phases(job.id)

    phase = blocked.phase(ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION)
    assert phase.status == ProjectFactoryInitPhaseStatus.BLOCKED
    assert phase.blockers[0].code == "bridge_installable_lookup_failed"
    assert phase.blockers[0].command == _register_cmd()


def test_android_release_blocks_mock_or_local_installable_payload(
    tmp_path: Path,
) -> None:
    release_tag = "android-preview-v0.1.0-build.1"
    bad_payload = {
        **_installable(release_tag),
        "mockOrDemo": True,
        "previewUrl": "http://localhost:8000/clinica-norte",
    }
    runner = _FakeRunner(
        [
            (
                _release_view_cmd(release_tag),
                _FakeResponse(stdout=json.dumps(_release(release_tag))),
            ),
            (_lookup_cmd(), _FakeResponse(stdout=json.dumps(bad_payload))),
            (_register_cmd(), _FakeResponse(stdout="registered")),
            (_lookup_cmd(), _FakeResponse(stdout=json.dumps(bad_payload))),
        ]
    )
    service = _service(tmp_path, runner)
    job = _generated_job(service)

    blocked = service.run_android_preview_release_phases(job.id)

    phase = blocked.phase(ProjectFactoryInitPhaseName.BRIDGE_INSTALLABLE_REGISTRATION)
    assert phase.status == ProjectFactoryInitPhaseStatus.BLOCKED
    assert phase.blockers[0].code == "bridge_installable_mock_or_local_blocked"
    assert (
        "localhost" in phase.blockers[0].message.lower()
        or "mock" in phase.blockers[0].message.lower()
    )


def test_android_release_blocks_mock_or_local_runtime_contract(
    tmp_path: Path,
) -> None:
    runner = _FakeRunner([])
    service = _service(tmp_path, runner)
    job = _generated_job(service)
    runtime_path = Path(job.relationships.generated_workspace_path or "") / (
        "release/preview-runtime.json"
    )
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    runtime["apiBaseUrl"] = "http://localhost:8000/api"
    runtime_path.write_text(json.dumps(runtime), encoding="utf-8")

    blocked = service.run_android_preview_release_phases(job.id)

    phase = blocked.phase(ProjectFactoryInitPhaseName.ANDROID_PREVIEW_RELEASE)
    assert _publish_cmd() not in runner.calls
    assert not any(call[:2] == ("gh", "release") for call in runner.calls)
    assert phase.status == ProjectFactoryInitPhaseStatus.BLOCKED
    assert phase.blockers[0].code in {
        "android_preview_runtime_contract_invalid",
        "android_preview_runtime_mock_or_local_blocked",
    }


def _service(
    tmp_path: Path,
    runner: _FakeRunner,
    *,
    registration_token: str | None = "secret-token",
    command_env: dict[str, str] | None = None,
    create_signing: bool = True,
    api_base_url: str = "https://bridge.test",
    app_update_public_base_url: str | None = None,
) -> ProjectFactoryInitService:
    del create_signing
    env = {
        "CODEX_MOBILE_BRIDGE_ROOT": str(tmp_path),
        "BRIDGE_PUBLIC_URL": "https://bridge.test",
        **(command_env or {}),
    }
    return ProjectFactoryInitService(
        state_root=tmp_path / "state",
        command_runner=runner,
        command_env=env,
        settings=_settings(
            tmp_path,
            registration_token=registration_token,
            api_base_url=api_base_url,
            app_update_public_base_url=app_update_public_base_url,
        ),
    )


def _settings(
    tmp_path: Path,
    *,
    registration_token: str | None = "secret-token",
    api_base_url: str = "https://bridge.test",
    app_update_public_base_url: str | None = None,
) -> Settings:
    return Settings(
        projects_root=str(tmp_path / "projects"),
        project_factory_state_dir=str(tmp_path / "state"),
        preview_base_domain="preview.nienfos.com",
        api_port=8000,
        api_base_url=api_base_url,
        app_update_public_base_url=app_update_public_base_url,
        installable_apps_registration_token=registration_token,
    )


def _generated_job(service: ProjectFactoryInitService, *, create_signing: bool = True):
    job = service.start_or_resume(
        draft_id="draft-flutter",
        project_name="Clinica Norte",
        slug="clinica-norte",
        frontend_strategy="flutter",
    )
    completed = service.run_frontend_baseline_phase(job.id)
    if create_signing:
        _write_existing_signing(Path(service._command_env["CODEX_MOBILE_BRIDGE_ROOT"]))
    return completed


def _release_view_cmd(release_tag: str) -> tuple[str, ...]:
    return (
        "gh",
        "release",
        "view",
        release_tag,
        "--json",
        "tagName,url,isPrerelease,assets",
    )


def _publish_cmd() -> tuple[str, ...]:
    return ("bash", "scripts/publish_android_preview_release.sh", "--push", "--watch")


def _keytool_cmd(keytool: Path, tmp_path: Path) -> tuple[str, ...]:
    return (
        str(keytool),
        "-genkeypair",
        "-v",
        "-keystore",
        str(tmp_path / "secrets/clinica-norte-preview-upload-keystore.jks"),
        "-storetype",
        "JKS",
        "-keyalg",
        "RSA",
        "-keysize",
        "2048",
        "-validity",
        "10000",
        "-alias",
        "preview",
        "-storepass:env",
        "ANDROID_STORE_PASSWORD",
        "-keypass:env",
        "ANDROID_KEY_PASSWORD",
        "-dname",
        "CN=clinica-norte Preview,O=Codex Project Factory,C=US",
    )


def _register_cmd() -> tuple[str, ...]:
    return ("bash", "scripts/register_installable_app.sh")


def _any_variable_set_cmd() -> tuple[str, ...]:
    return (
        "gh",
        "variable",
        "set",
        "__ANY__",
        "--body",
        "__ANY__",
        "--repo",
        "owner/clinica-norte",
    )


def _any_secret_set_cmd() -> tuple[str, ...]:
    return (
        "gh",
        "secret",
        "set",
        "--env-file",
        "__ANY__",
        "--repo",
        "owner/clinica-norte",
    )


def _lookup_cmd() -> tuple[str, ...]:
    return (
        "curl",
        "-fsS",
        "-H",
        "Host: bridge.test",
        "-H",
        "X-Forwarded-Proto: https",
        "http://127.0.0.1:8000/installable-apps/clinica-norte",
    )


def _write_apk(project: Path) -> None:
    apk = project / "apps/mobile/build/app/outputs/flutter-apk/clinica-norte.apk"
    apk.parent.mkdir(parents=True, exist_ok=True)
    apk.write_bytes(b"preview-apk")


def _write_existing_signing(bridge_root: Path) -> None:
    secrets = bridge_root / "secrets"
    secrets.mkdir(parents=True, exist_ok=True)
    (secrets / "clinica-norte-preview-upload-keystore.jks").write_bytes(b"keystore")
    (secrets / "clinica-norte-preview-signing.env").write_text(
        "\n".join(
            [
                "ANDROID_KEY_ALIAS=preview",
                "ANDROID_STORE_PASSWORD=store-password",
                "ANDROID_KEY_PASSWORD=key-password",
                "ANDROID_STORE_TYPE=JKS",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_generated_keystore(bridge_root: Path) -> None:
    keystore = bridge_root / "secrets/clinica-norte-preview-upload-keystore.jks"
    keystore.parent.mkdir(parents=True, exist_ok=True)
    keystore.write_bytes(b"generated-keystore")


def _write_android_build_gradle(mobile: Path) -> None:
    build_gradle = mobile / "android/app/build.gradle.kts"
    build_gradle.parent.mkdir(parents=True, exist_ok=True)
    build_gradle.write_text(
        "\n".join(
            [
                "plugins {",
                '    id("com.android.application")',
                '    id("kotlin-android")',
                '    id("dev.flutter.flutter-gradle-plugin")',
                "}",
                "",
                "android {",
                '    namespace = "com.example.clinica_norte"',
                "    buildTypes {",
                "        release {",
                '            signingConfig = signingConfigs.getByName("debug")',
                "        }",
                "    }",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _release(
    release_tag: str,
    *,
    assets: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "tagName": release_tag,
        "url": f"https://github.com/owner/clinica-norte/releases/tag/{release_tag}",
        "isPrerelease": True,
        "assets": assets
        if assets is not None
        else [
            {
                "name": "clinica-norte.apk",
                "url": "https://github.com/owner/clinica-norte/releases/download/apk",
            }
        ],
    }


def _installable(release_tag: str) -> dict[str, object]:
    return {
        "sourceApp": "clinica-norte",
        "displayName": "Clinica Norte Preview",
        "repo": "owner/clinica-norte",
        "releaseChannel": "prerelease",
        "releaseTagPattern": "android-preview-v*",
        "apkAssetPattern": "clinica-norte*.apk",
        "latestAssetName": "clinica-norte.apk",
        "releaseTag": release_tag,
        "available": True,
        "apkUrl": "https://bridge.test/app-updates/clinica-norte/apk/clinica-norte.apk",
        "sha256": "a" * 64,
        "previewUrl": "https://preview.nienfos.com/clinica-norte",
        "runtimeProfile": "preview",
        "productionReady": False,
        "mockOrDemo": False,
        "latestBuild": {"releaseTag": release_tag},
        "releaseMetadata": {
            "initialPreviewRelease": True,
            "runtimeProfile": "preview",
            "apiRuntime": "cloudflare_preview",
        },
    }


def _resource(job, resource_type: ProjectFactoryInitRemoteResourceType):
    for resource in job.remote_resources:
        if resource.type == resource_type:
            return resource
    raise AssertionError(f"Missing remote resource {resource_type}")
