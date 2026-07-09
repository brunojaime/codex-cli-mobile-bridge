from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from backend.app.application.services.project_factory_generator_service import (
    ProjectFactoryGenerationResult,
    ProjectFactoryGeneratorService,
)
from backend.app.application.services.project_factory_manifest_service import (
    ProjectFactoryManifestPlan,
)
from backend.app.application.services.project_factory_reference_asset_service import (
    ProjectFactoryReferenceAsset,
)


ALLOWED_ENV_KEYS = frozenset(
    {
        "ANDROID_RELEASE_POLL_SECONDS",
        "ANDROID_RELEASE_TIMEOUT_SECONDS",
        "API_BASE_URL",
        "APP_ANDROID_RELEASE_TAG",
        "APP_RELEASE_TAG",
        "APP_RUNTIME_PROFILE",
        "APK_ASSET_PATTERN",
        "BRIDGE_REGISTRATION_TOKEN",
        "BRIDGE_URL",
        "CODEX_HOME",
        "DISPLAY_NAME",
        "ENABLED",
        "GH_TOKEN",
        "GITHUB_OWNER",
        "GITHUB_REPO",
        "GITHUB_TOKEN",
        "GITHUB_VISIBILITY",
        "HOME",
        "INITIAL_COMMIT_MESSAGE",
        "INSTALLABLE_APPS_REGISTRATION_TOKEN",
        "LANG",
        "LC_ALL",
        "LATEST_ASSET_NAME",
        "LOGNAME",
        "OPENAI_API_KEY",
        "PATH",
        "PROJECT_FACTORY_FINAL_COMMIT_MESSAGE",
        "PUBLISH_BRANCH",
        "RELEASE_CHANNEL",
        "RELEASE_TAG_PATTERN",
        "REQUIRE_INSTALLABLE_APK",
        "SOURCE_APP",
        "TERM",
        "USER",
        "WAIT_FOR_ANDROID_RELEASE",
    }
)


@dataclass(frozen=True, slots=True)
class ProjectFactoryProcessResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class ProjectFactoryProcessRunner(Protocol):
    def run(
        self,
        *,
        argv: tuple[str, ...],
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> ProjectFactoryProcessResult: ...


class SubprocessProjectFactoryProcessRunner:
    def run(
        self,
        *,
        argv: tuple[str, ...],
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> ProjectFactoryProcessResult:
        completed = subprocess.run(
            list(argv),
            cwd=cwd,
            env=env,
            timeout=timeout_seconds if timeout_seconds > 0 else None,
            text=True,
            capture_output=True,
            check=False,
            shell=False,
        )
        return ProjectFactoryProcessResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


@dataclass(frozen=True, slots=True)
class ProjectFactoryRunnerContext:
    draft_id: str
    manifest_plan: ProjectFactoryManifestPlan
    reference_assets: tuple[ProjectFactoryReferenceAsset, ...]
    generator_runs: int
    reviewer_runs: int
    codex_command: str
    timeout_seconds: int
    run_generated_validation: bool = False
    publication_validation_mode: str = "remote"
    project_assets: tuple[object, ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectFactoryRunnerResult:
    generation_result: ProjectFactoryGenerationResult


class ProjectFactoryJobRunnerError(RuntimeError):
    pass


class ProjectFactoryJobRunnerBlockedError(ProjectFactoryJobRunnerError):
    pass


ProjectFactoryEventSink = Callable[[dict[str, object]], None]


class ProjectFactoryJobRunner:
    def __init__(
        self,
        *,
        generator_service: ProjectFactoryGeneratorService,
        process_runner: ProjectFactoryProcessRunner | None = None,
    ) -> None:
        self._generator_service = generator_service
        self._process_runner = process_runner or SubprocessProjectFactoryProcessRunner()

    def run(
        self,
        context: ProjectFactoryRunnerContext,
        *,
        event_sink: ProjectFactoryEventSink,
    ) -> ProjectFactoryRunnerResult:
        remote_publication = context.publication_validation_mode == "remote"
        publication_steps = 3 if remote_publication else 0
        total_steps = (
            6 + publication_steps + context.generator_runs + context.reviewer_runs
        )
        completed_steps = 0

        event_sink(_event("scaffold", "running", "Creating project scaffold.", 0))
        generation_result = self._generator_service.generate(
            context.manifest_plan,
            reference_assets=context.reference_assets,
            project_assets=context.project_assets,
        )
        completed_steps += 1
        project_path = Path(generation_result.target_path)
        event_sink(
            _event(
                "scaffold",
                "completed",
                "Project scaffold created.",
                _progress(completed_steps, total_steps),
            )
        )

        prompt_root = project_path / ".codex" / "factory" / "prompts"
        prompt_root.mkdir(parents=True, exist_ok=True)
        self._write_prompt_materials(
            prompt_root=prompt_root,
            context=context,
            project_path=project_path,
        )

        completed_steps = self._run_cli_step(
            context=context,
            project_path=project_path,
            prompt_path=prompt_root / "research-planning.md",
            phase="research_planning",
            label="Research and planning",
            completed_steps=completed_steps,
            total_steps=total_steps,
            event_sink=event_sink,
        )

        for index in range(context.generator_runs):
            completed_steps = self._run_cli_step(
                context=context,
                project_path=project_path,
                prompt_path=prompt_root / f"generator-{index + 1:02d}.md",
                phase="generator_batch",
                label=f"Generator run {index + 1} of {context.generator_runs}",
                completed_steps=completed_steps,
                total_steps=total_steps,
                event_sink=event_sink,
            )

        for index in range(context.reviewer_runs):
            completed_steps = self._run_cli_step(
                context=context,
                project_path=project_path,
                prompt_path=prompt_root / f"reviewer-{index + 1:02d}.md",
                phase="reviewer_batch",
                label=f"Reviewer run {index + 1} of {context.reviewer_runs}",
                completed_steps=completed_steps,
                total_steps=total_steps,
                event_sink=event_sink,
            )

        event_sink(
            _event(
                "finalize_validation",
                "running",
                "Preparing final Project Factory validation.",
                _progress(completed_steps, total_steps),
            )
        )
        (prompt_root / "finalize-validation.md").write_text(
            _finalize_prompt(),
            encoding="utf-8",
        )
        validation_command = ("bash", "scripts/validate_generated_project.sh")
        if context.run_generated_validation:
            try:
                result = self._process_runner.run(
                    argv=validation_command,
                    cwd=project_path,
                    env=_allowed_env(),
                    timeout_seconds=context.timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                event_sink(
                    _event(
                        "finalize_validation",
                        "failed",
                        "Generated project validation timed out.",
                        _progress(completed_steps, total_steps),
                        command=validation_command,
                        stderr=str(exc),
                    )
                )
                raise ProjectFactoryJobRunnerError(
                    "Generated project validation timed out."
                ) from exc
            if result.returncode != 0:
                event_sink(
                    _event(
                        "finalize_validation",
                        "failed",
                        (
                            "Generated project validation failed with exit code "
                            f"{result.returncode}."
                        ),
                        _progress(completed_steps, total_steps),
                        command=validation_command,
                        stdout=result.stdout,
                        stderr=result.stderr,
                        exit_code=result.returncode,
                    )
                )
                raise ProjectFactoryJobRunnerError(
                    "Generated project validation failed with exit code "
                    f"{result.returncode}."
                )
            completed_steps += 1
            event_sink(
                _event(
                    "finalize_validation",
                    "completed",
                    "Generated project validation completed.",
                    _progress(completed_steps, total_steps),
                    command=validation_command,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.returncode,
                )
            )
        else:
            completed_steps += 1
            event_sink(
                _event(
                    "finalize_validation",
                    "completed",
                    (
                        "Generated project validation skipped. Run "
                        "`scripts/validate_generated_project.sh` from the project root "
                        "to validate backend and mobile together."
                    ),
                    _progress(completed_steps, total_steps),
                    command=validation_command,
                )
            )

        publish_prompt_path = prompt_root / "publish-finalize.md"
        publish_prompt_path.write_text(_publish_finalize_prompt(), encoding="utf-8")
        completed_steps = self._run_cli_step(
            context=context,
            project_path=project_path,
            prompt_path=publish_prompt_path,
            phase="publish_finalize",
            label="Publish finalize",
            completed_steps=completed_steps,
            total_steps=total_steps,
            event_sink=event_sink,
        )
        completed_steps = self._run_command_step(
            project_path=project_path,
            argv=("bash", "scripts/finalize_local_commit.sh"),
            phase="local_git_commit",
            label="Local git commit",
            completed_steps=completed_steps,
            total_steps=total_steps,
            event_sink=event_sink,
            timeout_seconds=context.timeout_seconds,
        )
        if remote_publication:
            completed_steps = self._run_command_step(
                project_path=project_path,
                argv=("bash", "scripts/publish_project.sh"),
                phase="github_publish",
                label="GitHub publish",
                completed_steps=completed_steps,
                total_steps=total_steps,
                event_sink=event_sink,
                timeout_seconds=context.timeout_seconds,
                block_on_failure=True,
            )
            completed_steps = self._run_command_step(
                project_path=project_path,
                argv=("bash", "scripts/publish_android_release.sh", "--push", "--watch"),
                phase="android_release",
                label="Android release",
                completed_steps=completed_steps,
                total_steps=total_steps,
                event_sink=event_sink,
                timeout_seconds=context.timeout_seconds,
                block_on_failure=True,
            )
            completed_steps = self._run_command_step(
                project_path=project_path,
                argv=("bash", "scripts/register_installable_app.sh"),
                phase="installable_app_registration",
                label="Installable app registration",
                completed_steps=completed_steps,
                total_steps=total_steps,
                event_sink=event_sink,
                timeout_seconds=context.timeout_seconds,
                block_on_failure=True,
            )
        completed_steps = self._run_command_step(
            project_path=project_path,
            argv=("bash", "scripts/validate_publication_ready.sh"),
            phase="publish_verification",
            label="Publication verification",
            completed_steps=completed_steps,
            total_steps=total_steps,
            event_sink=event_sink,
            timeout_seconds=context.timeout_seconds,
            env_overrides={
                "PUBLICATION_VALIDATION_MODE": context.publication_validation_mode,
            },
            block_on_failure=remote_publication,
        )
        return ProjectFactoryRunnerResult(generation_result=generation_result)

    def _run_cli_step(
        self,
        *,
        context: ProjectFactoryRunnerContext,
        project_path: Path,
        prompt_path: Path,
        phase: str,
        label: str,
        completed_steps: int,
        total_steps: int,
        event_sink: ProjectFactoryEventSink,
    ) -> int:
        event_sink(
            _event(
                phase,
                "running",
                label,
                _progress(completed_steps, total_steps),
            )
        )
        prompt = prompt_path.read_text(encoding="utf-8")
        argv = _codex_argv(context.codex_command, prompt)
        try:
            result = self._process_runner.run(
                argv=argv,
                cwd=project_path,
                env=_allowed_env(),
                timeout_seconds=context.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            event_sink(
                _event(
                    phase,
                    "failed",
                    f"{label} timed out.",
                    _progress(completed_steps, total_steps),
                    command=argv,
                    stderr=str(exc),
                )
            )
            raise ProjectFactoryJobRunnerError(f"{label} timed out.") from exc
        if result.returncode != 0:
            event_sink(
                _event(
                    phase,
                    "failed",
                    f"{label} failed with exit code {result.returncode}.",
                    _progress(completed_steps, total_steps),
                    command=argv,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.returncode,
                )
            )
            raise ProjectFactoryJobRunnerError(
                f"{label} failed with exit code {result.returncode}."
            )
        completed_steps += 1
        event_sink(
            _event(
                phase,
                "completed",
                f"{label} completed.",
                _progress(completed_steps, total_steps),
                command=argv,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
            )
        )
        return completed_steps

    def _run_command_step(
        self,
        *,
        project_path: Path,
        argv: tuple[str, ...],
        phase: str,
        label: str,
        completed_steps: int,
        total_steps: int,
        event_sink: ProjectFactoryEventSink,
        timeout_seconds: int,
        env_overrides: dict[str, str] | None = None,
        blocked_exit_codes: set[int] | None = None,
        block_on_failure: bool = False,
    ) -> int:
        event_sink(
            _event(
                phase,
                "running",
                label,
                _progress(completed_steps, total_steps),
                command=argv,
            )
        )
        try:
            result = self._process_runner.run(
                argv=argv,
                cwd=project_path,
                env={**_allowed_env(), **(env_overrides or {})},
                timeout_seconds=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            event_sink(
                _event(
                    phase,
                    "failed",
                    f"{label} timed out.",
                    _progress(completed_steps, total_steps),
                    command=argv,
                    stderr=str(exc),
                )
            )
            raise ProjectFactoryJobRunnerError(f"{label} timed out.") from exc
        if result.returncode != 0:
            blocked = block_on_failure or result.returncode in (
                blocked_exit_codes or set()
            )
            status = "blocked" if blocked else "failed"
            event_sink(
                _event(
                    phase,
                    status,
                    f"{label} {status} with exit code {result.returncode}.",
                    _progress(completed_steps, total_steps),
                    command=argv,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.returncode,
                )
            )
            if blocked:
                raise ProjectFactoryJobRunnerBlockedError(
                    f"{label} blocked with exit code {result.returncode}."
                )
            raise ProjectFactoryJobRunnerError(
                f"{label} failed with exit code {result.returncode}."
            )
        completed_steps += 1
        event_sink(
            _event(
                phase,
                "completed",
                f"{label} completed.",
                _progress(completed_steps, total_steps),
                command=argv,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
            )
        )
        return completed_steps

    def _write_prompt_materials(
        self,
        *,
        prompt_root: Path,
        context: ProjectFactoryRunnerContext,
        project_path: Path,
    ) -> None:
        manifest = context.manifest_plan.manifest
        reference_lines = [
            f"- {asset.id}: {asset.original_filename} ({asset.content_type})"
            for asset in context.reference_assets
        ] or ["- No uploaded reference images."]
        project_asset_lines = [
            f"- {getattr(asset, 'asset_id', '')}: {getattr(asset, 'original_filename', '')} "
            f"role={getattr(asset, 'role', '')} sha256={getattr(asset, 'sha256', '')}"
            for asset in context.project_assets
        ] or ["- No promoted project assets."]
        base = f"""# Project Factory Context

Project path: `{project_path}`
Draft id: `{context.draft_id}`
Name: `{manifest.get("name")}`
Business type: `{manifest.get("business_type")}`
Primary goal: {manifest.get("primary_goal")}

Required defaults:
- Flutter iOS/Android/Web.
- FastAPI backend unless manifest says otherwise.
- Auth, registration, Google login placeholders.
- RBAC, admin, domain management, notifications.
- Feedback Bridge, app updater, and Workbench SDD artifacts.
- Real data paths by default; no mock/demo release data.
- Initial git commit, GitHub publish/push status, and release readiness must be
  explicit. Do not report the project complete if files are only untracked local
  changes.

Reference assets:
{chr(10).join(reference_lines)}

Promoted project assets:
{chr(10).join(project_asset_lines)}
"""
        (prompt_root / "research-planning.md").write_text(
            base + "\nResearch typical apps, UX patterns, and product plan.\n",
            encoding="utf-8",
        )
        for index in range(context.generator_runs):
            (prompt_root / f"generator-{index + 1:02d}.md").write_text(
                base
                + f"\nGenerator run {index + 1}: implement the next safe slice with tests.\n",
                encoding="utf-8",
            )
        for index in range(context.reviewer_runs):
            (prompt_root / f"reviewer-{index + 1:02d}.md").write_text(
                base
                + f"\nReviewer run {index + 1}: review generated work and request concrete fixes.\n",
                encoding="utf-8",
            )


def _codex_argv(command: str, prompt: str) -> tuple[str, ...]:
    base = tuple(shlex.split(command.strip() or "codex"))
    return (*base, "exec", "--skip-git-repo-check", "--color", "never", prompt)


def _allowed_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key in ALLOWED_ENV_KEYS}


def _event(
    phase: str,
    status: str,
    message: str,
    progress: int,
    *,
    command: Sequence[str] = (),
    stdout: str = "",
    stderr: str = "",
    exit_code: int | None = None,
) -> dict[str, object]:
    return {
        "phase": phase,
        "status": status,
        "message": message,
        "progress": progress,
        "command": list(command),
        "stdout": _truncate(stdout),
        "stderr": _truncate(stderr),
        "exit_code": exit_code,
    }


def _progress(completed_steps: int, total_steps: int) -> int:
    if total_steps <= 0:
        return 100
    return min(100, round((completed_steps / total_steps) * 100))


def _truncate(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[truncated]"


def _finalize_prompt() -> str:
    return """# Finalize Validation

Validate the generated project foundation, update specs/plans/tasks if needed,
and leave concrete next actions for the Workbench.
"""


def _publish_finalize_prompt() -> str:
    return """# Publish Finalize

Finish delivery. This Project Factory job is not complete until publication is
real and verifiable.

Required outcome:
- Run the generated validation script and fix failures.
- Commit all intended project files.
- Keep `scripts/publish_project.sh`, `scripts/publish_android_release.sh`,
  `scripts/register_installable_app.sh`, `scripts/validate_publication_ready.sh`,
  and `.github/workflows/android-release.yml` present and executable.
- Prepare any source fixes needed before the runner executes those scripts.
- Do not use mock/demo data, placeholder API URLs, or local demo mode unless
  the user explicitly requested a demo/mock release.
- If credentials or release configuration are missing, leave a concrete blocker
  and let the publication phase report `blocked` instead of claiming the app is
  installable.
"""
