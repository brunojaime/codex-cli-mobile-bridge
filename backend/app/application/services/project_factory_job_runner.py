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
        "CODEX_HOME",
        "HOME",
        "LANG",
        "LC_ALL",
        "LOGNAME",
        "OPENAI_API_KEY",
        "PATH",
        "TERM",
        "USER",
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


@dataclass(frozen=True, slots=True)
class ProjectFactoryRunnerResult:
    generation_result: ProjectFactoryGenerationResult


class ProjectFactoryJobRunnerError(RuntimeError):
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
        total_steps = 3 + context.generator_runs + context.reviewer_runs
        completed_steps = 0

        event_sink(_event("scaffold", "running", "Creating project scaffold.", 0))
        generation_result = self._generator_service.generate(
            context.manifest_plan,
            reference_assets=context.reference_assets,
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
            return ProjectFactoryRunnerResult(generation_result=generation_result)

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

Reference assets:
{chr(10).join(reference_lines)}
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
