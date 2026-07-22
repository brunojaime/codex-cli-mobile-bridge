from __future__ import annotations

import json
import os
import shlex
import subprocess
from collections.abc import Callable, Mapping, Sequence
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
        "API_RUNTIME",
        "APP_ANDROID_RELEASE_TAG",
        "APP_ANDROID_PREVIEW_RELEASE_TAG",
        "APP_RELEASE_TAG",
        "APP_RUNTIME_PROFILE",
        "APP_SLUG",
        "APK_ASSET_PATTERN",
        "BRIDGE_REGISTRATION_TOKEN",
        "BRIDGE_URL",
        "CONFIRM_APPLY",
        "CODEX_HOME",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_D1_DATABASE",
        "DISPLAY_NAME",
        "DEBUG_PREVIEW_SIGNING",
        "DEBUG_PREVIEW_SIGNING_ACKNOWLEDGED",
        "DEBUG_PREVIEW_SIGNING_REASON",
        "ENABLED",
        "EXPECTED_PLAN_HASH",
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
        "PREVIEW_ADMIN_BOOTSTRAP_TOKEN",
        "PREVIEW_ADMIN_EMAIL",
        "PREVIEW_ADMIN_PASSWORD",
        "PREVIEW_API_BASE_URL",
        "PREVIEW_D1_DATABASE",
        "PROJECT_FACTORY_FINAL_COMMIT_MESSAGE",
        "PROJECT_PATH",
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
ProjectFactoryRemotePreflight = Callable[[], Mapping[str, object]]

_VISUAL_UX_SKILL_NAME = "visual-ux-polish"
_VISUAL_UX_SKILL_ENV = "VISUAL_UX_POLISH_SKILL_PATH"
_MAX_AUTOMATIC_UX_ITERATIONS = 10
_VISUAL_UX_REQUIRED_REFERENCES = (
    "references/visual-quality-checklist.md",
    "references/product-category-playbooks.md",
    "references/visual-validation-protocol.md",
    "references/accessibility-performance-polish.md",
)


@dataclass(frozen=True, slots=True)
class _VisualUxSkillContext:
    skill_path: Path
    prompt_section: str


class ProjectFactoryUxSkillUnavailableError(ProjectFactoryJobRunnerError):
    pass


class ProjectFactoryJobRunner:
    def __init__(
        self,
        *,
        generator_service: ProjectFactoryGeneratorService,
        process_runner: ProjectFactoryProcessRunner | None = None,
        remote_preflight: ProjectFactoryRemotePreflight | None = None,
        visual_ux_skill_path: Path | None = None,
    ) -> None:
        self._generator_service = generator_service
        self._process_runner = process_runner or SubprocessProjectFactoryProcessRunner()
        self._remote_preflight = remote_preflight
        self._visual_ux_skill_path = visual_ux_skill_path

    def run(
        self,
        context: ProjectFactoryRunnerContext,
        *,
        event_sink: ProjectFactoryEventSink,
    ) -> ProjectFactoryRunnerResult:
        if context.generator_runs != context.reviewer_runs:
            raise ProjectFactoryJobRunnerError(
                "Paired generator/reviewer workflow requires matching run counts."
            )
        remote_publication = context.publication_validation_mode == "remote"
        supports_android_installable = _supports_android_installable(
            context.manifest_plan,
        )
        publication_steps = (
            (6 if supports_android_installable else 4)
            if remote_publication
            else 0
        )
        preflight_steps = 1 if remote_publication and self._remote_preflight else 0
        total_steps = (
            9
            + (2 * _MAX_AUTOMATIC_UX_ITERATIONS)
            + preflight_steps
            + publication_steps
            + context.generator_runs
            + context.reviewer_runs
        )
        completed_steps = 0

        if remote_publication and self._remote_preflight is not None:
            completed_steps = self._run_remote_preflight(
                completed_steps=completed_steps,
                total_steps=total_steps,
                event_sink=event_sink,
            )

        try:
            visual_ux_skill_context = _load_visual_ux_skill_context(
                self._visual_ux_skill_path,
            )
        except ProjectFactoryUxSkillUnavailableError as exc:
            event_sink(
                _event(
                    "ux_skill_unavailable",
                    "blocked",
                    "visual-ux-polish skill is unavailable; UX lane cannot run.",
                    _progress(completed_steps, total_steps),
                    stderr=str(exc),
                )
            )
            raise ProjectFactoryJobRunnerBlockedError(
                "visual-ux-polish skill is unavailable; UX lane cannot run."
            ) from exc

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
            visual_ux_skill_context=visual_ux_skill_context,
        )

        completed_steps = self._run_cli_step(
            context=context,
            project_path=project_path,
            prompt_path=prompt_root / "ux-brief.md",
            phase="ux_baseline_generator",
            label="Early UX generator pass 1 of 2",
            completed_steps=completed_steps,
            total_steps=total_steps,
            event_sink=event_sink,
        )
        completed_steps = self._run_cli_step(
            context=context,
            project_path=project_path,
            prompt_path=prompt_root / "ux-brief-reviewer.md",
            phase="ux_baseline_reviewer",
            label="Early UX reviewer pass 1 of 1",
            completed_steps=completed_steps,
            total_steps=total_steps,
            event_sink=event_sink,
        )
        completed_steps = self._run_cli_step(
            context=context,
            project_path=project_path,
            prompt_path=prompt_root / "ux-brief-generator-02.md",
            phase="ux_baseline_generator",
            label="Early UX generator pass 2 of 2",
            completed_steps=completed_steps,
            total_steps=total_steps,
            event_sink=event_sink,
        )
        try:
            _require_ux_brief(project_path)
        except ProjectFactoryJobRunnerError as exc:
            event_sink(
                _event(
                    "ux_brief",
                    "failed",
                    str(exc),
                    _progress(completed_steps, total_steps),
                )
            )
            raise

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
                phase="generator_pass",
                label=f"Generator pass {index + 1} of {context.generator_runs}",
                completed_steps=completed_steps,
                total_steps=total_steps,
                event_sink=event_sink,
            )
            completed_steps = self._run_cli_step(
                context=context,
                project_path=project_path,
                prompt_path=prompt_root / f"reviewer-{index + 1:02d}.md",
                phase="reviewer_pass",
                label=f"Reviewer pass {index + 1} of {context.reviewer_runs}",
                completed_steps=completed_steps,
                total_steps=total_steps,
                event_sink=event_sink,
            )

        completed_steps = self._run_ux_lane(
            context=context,
            project_path=project_path,
            prompt_root=prompt_root,
            completed_steps=completed_steps,
            total_steps=total_steps,
            event_sink=event_sink,
        )

        _write_ux_evidence_index(project_path)

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
        must_run_generated_validation = (
            context.run_generated_validation or remote_publication
        )
        if must_run_generated_validation:
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
                    (
                        "Generated project validation completed. "
                        "Remote publication gate satisfied."
                        if remote_publication
                        else "Generated project validation completed."
                    ),
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
                argv=("bash", "scripts/apply_cloudflare_preview.sh"),
                phase="cloudflare_preview_apply",
                label="Cloudflare preview apply",
                completed_steps=completed_steps,
                total_steps=total_steps,
                event_sink=event_sink,
                timeout_seconds=context.timeout_seconds,
                block_on_failure=True,
            )
            completed_steps = self._run_command_step(
                project_path=project_path,
                argv=("bash", "scripts/smoke_web_preview.sh"),
                phase="web_preview_smoke",
                label="Web preview smoke",
                completed_steps=completed_steps,
                total_steps=total_steps,
                event_sink=event_sink,
                timeout_seconds=context.timeout_seconds,
                block_on_failure=True,
            )
            completed_steps = self._run_command_step(
                project_path=project_path,
                argv=("bash", "scripts/smoke_preview_api.sh"),
                phase="preview_api_smoke",
                label="Preview API smoke",
                completed_steps=completed_steps,
                total_steps=total_steps,
                event_sink=event_sink,
                timeout_seconds=context.timeout_seconds,
                block_on_failure=True,
            )
            if supports_android_installable:
                completed_steps = self._run_command_step(
                    project_path=project_path,
                    argv=(
                        "bash",
                        "scripts/publish_android_preview_release.sh",
                        "--push",
                        "--watch",
                    ),
                    phase="android_preview_release",
                    label="Android preview release",
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
            argv=(
                "bash",
                "scripts/validate_initial_preview_release.sh"
                if remote_publication
                else "scripts/validate_publication_ready.sh",
            ),
            phase="publish_verification",
            label=(
                "Initial preview release verification"
                if remote_publication
                else "Publication verification"
            ),
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

    def _run_remote_preflight(
        self,
        *,
        completed_steps: int,
        total_steps: int,
        event_sink: ProjectFactoryEventSink,
    ) -> int:
        phase = "cloudflare_preview_preflight"
        event_sink(
            _event(
                phase,
                "running",
                "Checking Cloudflare preview readiness before remote publication.",
                _progress(completed_steps, total_steps),
            )
        )
        try:
            payload = self._remote_preflight() if self._remote_preflight else {}
        except Exception as exc:
            event_sink(
                _event(
                    phase,
                    "failed",
                    "Cloudflare preview preflight failed.",
                    _progress(completed_steps, total_steps),
                    stderr=str(exc),
                )
            )
            raise ProjectFactoryJobRunnerError(
                "Cloudflare preview preflight failed."
            ) from exc
        if not _preflight_ready(payload):
            blockers = _preflight_blockers(payload)
            event_sink(
                _event(
                    phase,
                    "blocked",
                    "Cloudflare preview preflight blocked remote publication.",
                    _progress(completed_steps, total_steps),
                    stderr="\n".join(blockers),
                )
            )
            raise ProjectFactoryJobRunnerBlockedError(
                "Cloudflare preview preflight blocked remote publication."
            )
        completed_steps += 1
        event_sink(
            _event(
                phase,
                "completed",
                "Cloudflare preview preflight completed.",
                _progress(completed_steps, total_steps),
            )
        )
        return completed_steps

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
        completed, _result = self._run_cli_step_result(
            context=context,
            project_path=project_path,
            prompt_path=prompt_path,
            phase=phase,
            label=label,
            completed_steps=completed_steps,
            total_steps=total_steps,
            event_sink=event_sink,
        )
        return completed

    def _run_cli_step_result(
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
    ) -> tuple[int, ProjectFactoryProcessResult]:
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
        return completed_steps, result

    def _run_ux_lane(
        self,
        *,
        context: ProjectFactoryRunnerContext,
        project_path: Path,
        prompt_root: Path,
        completed_steps: int,
        total_steps: int,
        event_sink: ProjectFactoryEventSink,
    ) -> int:
        generator_base = (prompt_root / "ux-generator.md").read_text(encoding="utf-8")
        reviewer_base = (prompt_root / "ux-reviewer.md").read_text(encoding="utf-8")
        reviewer_feedback = ""
        for iteration in range(1, _MAX_AUTOMATIC_UX_ITERATIONS + 1):
            generator_prompt_path = _ux_iteration_prompt_path(
                prompt_root,
                "ux-generator",
                iteration,
            )
            reviewer_prompt_path = _ux_iteration_prompt_path(
                prompt_root,
                "ux-reviewer",
                iteration,
            )
            if iteration > 1:
                generator_prompt_path.write_text(
                    generator_base
                    + "\n\n# UX Reviewer Continuation\n\n"
                    + reviewer_feedback.strip()
                    + "\n",
                    encoding="utf-8",
                )
                reviewer_prompt_path.write_text(
                    reviewer_base
                    + f"\n\nReview UX iteration {iteration}. Return `status=complete` "
                    "only when the UX gate is ready; otherwise include the next "
                    "UX-only continuation prompt.\n",
                    encoding="utf-8",
                )
            completed_steps, _generator_result = self._run_cli_step_result(
                context=context,
                project_path=project_path,
                prompt_path=generator_prompt_path,
                phase="ux_generator",
                label=(
                    "Senior UX generator pass "
                    f"{iteration} of {_MAX_AUTOMATIC_UX_ITERATIONS}"
                ),
                completed_steps=completed_steps,
                total_steps=total_steps,
                event_sink=event_sink,
            )
            completed_steps, reviewer_result = self._run_cli_step_result(
                context=context,
                project_path=project_path,
                prompt_path=reviewer_prompt_path,
                phase="ux_reviewer",
                label=(
                    "Senior UX reviewer pass "
                    f"{iteration} of {_MAX_AUTOMATIC_UX_ITERATIONS}"
                ),
                completed_steps=completed_steps,
                total_steps=total_steps,
                event_sink=event_sink,
            )
            reviewer_feedback = _ux_reviewer_feedback(
                project_path=project_path,
                result=reviewer_result,
            )
            if _ux_reviewer_is_complete(reviewer_feedback):
                skipped_steps = (
                    _MAX_AUTOMATIC_UX_ITERATIONS - iteration
                ) * 2
                completed_steps += skipped_steps
                event_sink(
                    _event(
                        "ux_lane",
                        "completed",
                        (
                            "Automatic UX lane completed after "
                            f"{iteration} of {_MAX_AUTOMATIC_UX_ITERATIONS} pass(es)."
                        ),
                        _progress(completed_steps, total_steps),
                    )
                )
                return completed_steps
        event_sink(
            _event(
                "ux_lane",
                "completed",
                (
                    "Automatic UX lane reached the maximum "
                    f"{_MAX_AUTOMATIC_UX_ITERATIONS} pass(es)."
                ),
                _progress(completed_steps, total_steps),
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
        visual_ux_skill_context: _VisualUxSkillContext,
    ) -> None:
        manifest = context.manifest_plan.manifest
        frontend_strategy = str(manifest.get("frontend_strategy") or "flutter")
        frontend = manifest.get("frontend") if isinstance(manifest, dict) else {}
        source_root = (
            frontend.get("source_root")
            if isinstance(frontend, dict)
            else ("apps/web" if frontend_strategy == "svelte" else "apps/mobile")
        )
        reference_lines = [
            f"- {asset.id}: {asset.original_filename} ({asset.content_type})"
            for asset in context.reference_assets
        ] or ["- No uploaded reference images."]
        project_asset_lines = [
            f"- {getattr(asset, 'asset_id', '')}: {getattr(asset, 'original_filename', '')} "
            f"role={getattr(asset, 'role', '')} sha256={getattr(asset, 'sha256', '')}"
            for asset in context.project_assets
        ] or ["- No promoted project assets."]
        init_context = _project_factory_init_context_section(project_path)
        default_rules = (
            init_context
            or f"""Required defaults:
- Frontend strategy: `{frontend_strategy}`.
- Frontend source root: `{source_root}`.
- Flutter keeps iOS/Android/Web, APK preview, Bridge installability, and
  Workbench APK entry.
- Svelte is web-first under `apps/web`; do not claim APK or Bridge
  installability without an explicit wrapper strategy.
- FastAPI backend unless manifest says otherwise.
- Auth, registration, Google login placeholders.
- RBAC, admin, domain management, notifications.
- Feedback Bridge, app updater, and Workbench SDD artifacts.
- Real data paths by default; no mock/demo release data.
- Initial git commit, GitHub publish/push status, and release readiness must be
  explicit. Do not report the project complete if files are only untracked local
  changes.
"""
        )
        base = f"""# Project Factory Context

Project path: `{project_path}`
Draft id: `{context.draft_id}`
Name: `{manifest.get("name")}`
Business type: `{manifest.get("business_type")}`
Primary goal: {manifest.get("primary_goal")}

{default_rules}

Reference assets:
{chr(10).join(reference_lines)}

Promoted project assets:
{chr(10).join(project_asset_lines)}
"""
        ux_brief_contract = """
Required UX brief input:
- Read `.codex/ux/pre-project-ux-brief.md` before planning, generating, or
  reviewing app UI.
- If the file is missing, stop and report that the UX brief contract was not
  satisfied instead of proceeding with generic UX assumptions.
- Apply the brief as product direction while preserving the manifest, release
  defaults, backend contracts, auth, RBAC, persistence, and business logic.
"""
        (prompt_root / "research-planning.md").write_text(
            base
            + ux_brief_contract
            + "\nResearch typical apps, UX patterns, and product plan.\n",
            encoding="utf-8",
        )
        (prompt_root / "ux-brief.md").write_text(
            base
            + visual_ux_skill_context.prompt_section
            + """
# Lightweight UX Brief

# Early UX Generator Pass 1

The visual-ux-polish skill above is loaded and required.

This is the first early UX intervention. Do not edit product code,
backend code, auth, RBAC, persistence, release wiring, or generated
functionality. Create `.codex/ux/pre-project-ux-brief.md` only.

Research the requested app type and comparable professional products. Produce
clear UX direction for the factory generator: audience, first-use intent,
information architecture, navigation model, primary screens, empty/loading/error
states, visual tone, accessibility constraints, mobile/desktop expectations,
benchmark notes, and UX acceptance criteria.
""",
            encoding="utf-8",
        )
        (prompt_root / "ux-brief-reviewer.md").write_text(
            base
            + visual_ux_skill_context.prompt_section
            + ux_brief_contract
            + """
# Early UX Reviewer Pass 1

The visual-ux-polish skill above is loaded and required.

Review `.codex/ux/pre-project-ux-brief.md` against the user's product/domain
brief. Do not edit product code, backend code, auth, RBAC, persistence, release
wiring, or generated functionality. Write `.codex/ux/pre-project-ux-review.md`
with concrete look-and-feel corrections for the second UX Generator pass.

Focus on whether the brief gives clear enough visual direction for the later
Domain Factory Generator/Domain Reviewer implementation pair.
""",
            encoding="utf-8",
        )
        (prompt_root / "ux-brief-generator-02.md").write_text(
            base
            + visual_ux_skill_context.prompt_section
            + ux_brief_contract
            + """
# Lightweight UX Brief

# Early UX Generator Pass 2

The visual-ux-polish skill above is loaded and required.

Read `.codex/ux/pre-project-ux-brief.md` and
`.codex/ux/pre-project-ux-review.md`, then update
`.codex/ux/pre-project-ux-brief.md` into the final early UX baseline for the
Domain Factory Generator/Domain Reviewer pair.

Do not edit product code, backend code, auth, RBAC, persistence, release wiring,
or generated functionality. This pass only improves the look-and-feel direction
that the domain implementation must consume.
""",
            encoding="utf-8",
        )
        for index in range(context.generator_runs):
            (prompt_root / f"generator-{index + 1:02d}.md").write_text(
                base
                + ux_brief_contract
                + f"\nGenerator pass {index + 1}: implement the next safe slice with tests. "
                "A reviewer pass runs immediately after this pass.\n",
                encoding="utf-8",
            )
        for index in range(context.reviewer_runs):
            (prompt_root / f"reviewer-{index + 1:02d}.md").write_text(
                base
                + ux_brief_contract
                + f"\nReviewer pass {index + 1}: review only the generator pass with the "
                "same number, verify concrete fixes, and leave actionable follow-up.\n",
                encoding="utf-8",
            )
        (prompt_root / "ux-generator.md").write_text(
            base
            + visual_ux_skill_context.prompt_section
            + ux_brief_contract
            + """
# Senior UX Generator

The visual-ux-polish skill above is loaded and required.

This is the post-Project-Factory UX intervention. Improve only visible UX:
layout, hierarchy, typography, spacing, color, interaction polish, responsive
behavior, empty/loading/error states, accessibility, and user-facing copy. Do
not change product functionality, backend behavior, auth, RBAC, persistence,
schemas, release wiring, or business logic.

Benchmark comparable professional products, inspect or capture screenshots when
the app can run, perform focused UAT on the primary journeys, and save concise
evidence under `.codex/ux/`. Validate mobile and desktop fit before completion.
""",
            encoding="utf-8",
        )
        (prompt_root / "ux-reviewer.md").write_text(
            base
            + visual_ux_skill_context.prompt_section
            + ux_brief_contract
            + """
# Senior UX Reviewer

The visual-ux-polish skill above is loaded and required.

Review only the UX Generator changes and evidence. Check visual quality,
interaction clarity, accessibility, responsive fit, screenshots/UAT evidence,
and scope discipline. Do not request functional/backend/business-logic changes.

This automatic UX lane can run up to 10 generator/reviewer passes. You own the
stop decision. Return complete as soon as the UX is good enough for this stage;
do not spend all 10 passes unless material UX issues remain.

If more UX-only work is needed, write `.codex/ux/ux-reviewer-report.md` with the
required follow-up. If the UX is professional and validated, write the same file
with a stop decision and the evidence reviewed.

End your response, and the report when possible, with this machine-readable
decision:

```json
{"status":"complete|continue|blocked","summary":"short UX readiness summary","continuation_prompt":"next UX-only prompt when status is continue","release_gate":"pass|fail"}
```
""",
            encoding="utf-8",
        )


def _codex_argv(command: str, prompt: str) -> tuple[str, ...]:
    base = tuple(shlex.split(command.strip() or "codex"))
    return (*base, "exec", "--skip-git-repo-check", "--color", "never", prompt)


def _ux_iteration_prompt_path(prompt_root: Path, stem: str, iteration: int) -> Path:
    if iteration == 1:
        return prompt_root / f"{stem}.md"
    return prompt_root / f"{stem}-{iteration:02d}.md"


def _ux_reviewer_feedback(
    *,
    project_path: Path,
    result: ProjectFactoryProcessResult,
) -> str:
    report_path = project_path / ".codex" / "ux" / "ux-reviewer-report.md"
    report = ""
    if report_path.exists():
        report = report_path.read_text(encoding="utf-8")
    return "\n\n".join(
        item.strip()
        for item in (result.stdout, result.stderr, report)
        if item and item.strip()
    )


def _ux_reviewer_is_complete(feedback: str) -> bool:
    normalized = feedback.strip()
    if not normalized:
        return False
    for payload in _json_objects_from_text(normalized):
        status = str(payload.get("status") or "").strip().lower()
        release_gate = str(payload.get("release_gate") or "").strip().lower()
        if status in {"complete", "completed", "approved"}:
            return True
        if status == "ready" and release_gate in {"pass", "passed", "ready"}:
            return True
    lowered = normalized.lower()
    continue_markers = (
        "status: continue",
        "status=continue",
        '"status": "continue"',
        '"status":"continue"',
        "'status': 'continue'",
        "'status':'continue'",
    )
    if any(marker in lowered for marker in continue_markers):
        return False
    complete_markers = (
        "status: complete",
        "status=complete",
        '"status": "complete"',
        '"status":"complete"',
        "'status': 'complete'",
        "'status':'complete'",
        "ux gate: pass",
        "release_gate: pass",
        '"release_gate":"pass"',
        "release gate: pass",
    )
    return any(marker in lowered for marker in complete_markers)


def _json_objects_from_text(text: str) -> tuple[dict[str, object], ...]:
    candidates = [text]
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        candidates.append(text[first : last + 1])
    parsed: list[dict[str, object]] = []
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            parsed.append(payload)
    return tuple(parsed)


def _load_visual_ux_skill_context(
    override_path: Path | None,
) -> _VisualUxSkillContext:
    skill_path = override_path or _default_visual_ux_skill_path()
    skill_path = skill_path.expanduser()
    if not skill_path.is_file():
        raise ProjectFactoryUxSkillUnavailableError(
            f"{_VISUAL_UX_SKILL_NAME} skill file not found: {skill_path}"
        )
    skill_root = skill_path.parent
    sections = [("SKILL.md", skill_path)]
    sections.extend(
        (relative_path, skill_root / relative_path)
        for relative_path in _VISUAL_UX_REQUIRED_REFERENCES
    )
    loaded: list[str] = []
    for label, path in sections:
        if not path.is_file():
            raise ProjectFactoryUxSkillUnavailableError(
                f"{_VISUAL_UX_SKILL_NAME} required reference missing: {path}"
            )
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            raise ProjectFactoryUxSkillUnavailableError(
                f"{_VISUAL_UX_SKILL_NAME} required reference is empty: {path}"
            )
        loaded.append(f"## {label}\n\n{content}")
    prompt_section = (
        "\n# Required visual-ux-polish Skill Context\n\n"
        f"Resolved skill path: `{skill_path}`\n\n"
        + "\n\n".join(loaded)
        + "\n"
    )
    return _VisualUxSkillContext(
        skill_path=skill_path,
        prompt_section=prompt_section,
    )


def _default_visual_ux_skill_path() -> Path:
    configured = os.environ.get(_VISUAL_UX_SKILL_ENV)
    if configured:
        return Path(configured)
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home) / "skills" / _VISUAL_UX_SKILL_NAME / "SKILL.md"
    return Path.home() / ".codex" / "skills" / _VISUAL_UX_SKILL_NAME / "SKILL.md"


def _require_ux_brief(project_path: Path) -> None:
    brief_path = project_path / ".codex" / "ux" / "pre-project-ux-brief.md"
    if not brief_path.is_file() or not brief_path.read_text(encoding="utf-8").strip():
        raise ProjectFactoryJobRunnerError(
            "UX brief step completed without writing .codex/ux/pre-project-ux-brief.md."
        )


def _write_ux_evidence_index(project_path: Path) -> None:
    ux_root = project_path / ".codex" / "ux"
    ux_root.mkdir(parents=True, exist_ok=True)
    index_path = ux_root / "evidence-index.json"
    artifacts = [
        str(path.relative_to(project_path))
        for path in sorted(ux_root.rglob("*"))
        if path.is_file() and path != index_path
    ]
    index_path.write_text(
        json.dumps(
            {
                "kind": "codex.projectFactoryUxEvidenceIndex",
                "version": 1,
                "artifacts": artifacts,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _allowed_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key in ALLOWED_ENV_KEYS}


def _preflight_ready(payload: Mapping[str, object]) -> bool:
    if payload.get("ok") is True:
        return True
    return str(payload.get("status") or "").lower() == "ready"


def _supports_android_installable(manifest_plan: ProjectFactoryManifestPlan) -> bool:
    manifest = manifest_plan.manifest
    frontend = manifest.get("frontend") if isinstance(manifest, dict) else None
    capabilities = (
        frontend.get("strategy_capabilities")
        if isinstance(frontend, dict)
        else None
    )
    if isinstance(capabilities, dict):
        return bool(
            capabilities.get("supports_android_preview_apk") is True
            and capabilities.get("supports_bridge_installable_app") is True
        )
    return str(manifest.get("frontend_strategy") or "flutter") == "flutter"


def _project_factory_init_context_section(project_path: Path) -> str:
    factory_dir = project_path / ".codex/factory"
    init_result_path = factory_dir / "init-result.json"
    llm_context_path = factory_dir / "llm-start-context.md"
    if not init_result_path.is_file() or not llm_context_path.is_file():
        return ""
    try:
        init_result = json.loads(init_result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    if not isinstance(init_result, dict):
        return ""
    context_text = llm_context_path.read_text(encoding="utf-8")
    context_excerpt = context_text[:4000]
    return f"""Initialized deterministic baseline:
- Init result: `.codex/factory/init-result.json`
- LLM start context: `.codex/factory/llm-start-context.md`
- Init job id: `{init_result.get("initJobId")}`
- Source app: `{init_result.get("sourceApp")}`
- Preview API: `{_init_context_preview_api(init_result)}`
- Ready for business LLM: `{init_result.get("readyForBusinessLlm")}`
- Blocked with context: `{init_result.get("blockedWithContext")}`

Business generator/reviewer rules:
- Consume the initialized baseline from the context pack before making changes.
- Do not recreate GitHub, Cloudflare Worker/route/D1, Android prerelease,
  Bridge installable, feedback, updater, or Workbench plumbing manually.
- Keep preview runtime real; do not switch to mock/demo/local/placeholder URLs
  unless the user explicitly asks for a demo/mock build.
- Implement product/business work only on top of the initialized baseline.
- Update specs, tasks, tests, and release evidence as product work changes.

Context pack excerpt:
```md
{context_excerpt}
```
"""


def _init_context_preview_api(init_result: dict[str, object]) -> object:
    resources = init_result.get("resources")
    if not isinstance(resources, dict):
        return None
    preview = resources.get("cloudflarePreview")
    if not isinstance(preview, dict):
        return None
    return preview.get("apiBaseUrl")


def _preflight_blockers(payload: Mapping[str, object]) -> list[str]:
    blockers: list[str] = []
    checks = payload.get("checks")
    if isinstance(checks, list):
        for item in checks:
            if not isinstance(item, Mapping) or item.get("ok") is True:
                continue
            code = str(item.get("code") or "cloudflare_preview_check")
            detail = str(item.get("detail") or item.get("message") or "not ready")
            blockers.append(f"{code}: {detail}")
    if blockers:
        return blockers
    status = str(payload.get("status") or "blocked")
    return [f"cloudflare_preview_doctor: status={status}"]


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
- Keep `scripts/publish_project.sh`, `scripts/apply_cloudflare_preview.sh`,
  `scripts/smoke_preview_api.sh`, `scripts/publish_android_preview_release.sh`,
  `scripts/register_installable_app.sh`,
  `scripts/validate_initial_preview_release.sh`, and
  `.github/workflows/android-preview-release.yml` present and executable.
- Prepare any source fixes needed before the runner executes those scripts.
- The initial release must be `android-preview-v*` against
  `https://preview.nienfos.com/<slug>/api`; do not publish `android-v*` yet.
- Do not use mock/demo data, placeholder API URLs, invented backends, or local
  demo mode unless the user explicitly requested a demo/mock release.
- If credentials or release configuration are missing, leave a concrete blocker
  and let the publication phase report `blocked` instead of claiming the app is
  installable.
"""
