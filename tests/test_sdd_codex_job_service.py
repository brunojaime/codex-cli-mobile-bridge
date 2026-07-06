from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.application.services.sdd_codex_job_service import (
    SddCodexJobService,
    SddCodexProcessResult,
)
from backend.app.application.services.sdd_media_upload_service import (
    SddMediaUploadService,
)
from backend.app.application.services.sdd_spec_edit_service import SddSpecEditService
from backend.app.application.services.sdd_spec_target_service import (
    SpecIntakeMediaItemInput,
    SpecIntakeValidationInput,
    SpecTargetInput,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.main import create_app


class FakeRunner:
    def __init__(
        self,
        result: SddCodexProcessResult | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.result = result or SddCodexProcessResult(returncode=0, stdout="ok\n")
        self.exc = exc
        self.calls: list[dict[str, object]] = []

    def run(
        self,
        *,
        argv: tuple[str, ...],
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> SddCodexProcessResult:
        self.calls.append(
            {
                "argv": argv,
                "cwd": cwd,
                "env": env,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.exc is not None:
            raise self.exc
        return self.result


class WritingRunner(FakeRunner):
    def __init__(
        self,
        writes: dict[str, str],
        result: SddCodexProcessResult | None = None,
    ) -> None:
        super().__init__(result=result)
        self.writes = writes

    def run(
        self,
        *,
        argv: tuple[str, ...],
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> SddCodexProcessResult:
        result = super().run(
            argv=argv,
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
        )
        for relative_path, content in self.writes.items():
            path = cwd / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        return result


def test_codex_job_happy_path_uses_context_pack_handoff_and_safe_argv(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    runner = FakeRunner()
    job_service = SddCodexJobService(
        projects_root=tmp_path / "projects",
        codex_command="codex --profile trusted",
        timeout_seconds=15,
        runner=runner,
        env={
            "PATH": "/usr/bin",
            "OPENAI_API_KEY": "secret",
            "UNSAFE_VAR": "drop-me",
        },
    )
    edit_service = SddSpecEditService(projects_root=tmp_path / "projects")
    request = _edit_request(project, text="Update tasks; rm -rf /")
    dry_run = edit_service.dry_run_existing_spec_edit(request)

    job = job_service.start_existing_spec_edit_job(request=request, dry_run=dry_run)
    completed = job_service.run_job(job.id)

    assert job.status == "queued"
    assert job.id.startswith("sddjob-")
    assert job.required_files
    assert "read_all_specs_without_context_pack" in job.blocked_reads
    assert job.command_argv[:2] == ("codex", "--profile")
    assert "exec" in job.command_argv
    assert "Update tasks; rm -rf /" not in job.command_argv
    assert "UNSAFE_VAR" not in job.env_keys
    assert set(job.env_keys) == {"OPENAI_API_KEY", "PATH"}
    assert job.intake_references == (
        f"specs/001-existing/intake/jobs/{job.id}/original-request.md",
    )
    assert job.media_persistence["status"] == "applied"
    assert (project / job.job_root / "request.json").is_file()
    assert (project / job.job_root / "context-pack.json").is_file()
    assert (
        project / f"specs/001-existing/intake/jobs/{job.id}/original-request.md"
    ).read_text() == "Update tasks; rm -rf /"
    assert (
        "Update tasks; rm -rf /" in (project / job.job_root / "prompt.md").read_text()
    )
    assert completed.status == "completed"
    assert completed.to_payload()["activity_state"] == "ready"
    assert any(
        event["state"] == "running-codex"
        for event in completed.to_payload()["activity"]["events"]
    )
    assert completed.stdout == "ok\n"
    assert completed.exit_code == 0
    assert runner.calls[0]["cwd"] == project / job.sandbox_root
    assert runner.calls[0]["env"] == {"OPENAI_API_KEY": "secret", "PATH": "/usr/bin"}
    assert (project / "specs/001-existing/tasks.md").read_text() == "- [ ] Existing\n"
    assert (project / job.sandbox_root / "specs/001-existing/tasks.md").is_file()


def test_codex_job_handoff_includes_structured_sequence_media_refs(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    upload_service = SddMediaUploadService(projects_root=tmp_path / "projects")
    frame1 = upload_service.stage_image(
        workspace_path=str(project),
        filename="frame-1.png",
        mime_type="image/png",
        content=b"frame1",
    )
    frame2 = upload_service.stage_image(
        workspace_path=str(project),
        filename="frame-2.png",
        mime_type="image/png",
        content=b"frame2",
    )
    audio = upload_service.stage_audio(
        workspace_path=str(project),
        filename="narration.m4a",
        mime_type="audio/mp4",
        content=b"voice",
        duration_ms=1000,
    )
    request = _edit_request(
        project,
        intake_items=(
            SpecIntakeMediaItemInput(kind="text", text="Update tasks with walkthrough"),
            SpecIntakeMediaItemInput(
                kind="image_sequence",
                frame_count=2,
                audio_track_count=1,
                timeline_ms=(0, 1000),
                references=(
                    frame1.staged_path or "",
                    frame2.staged_path or "",
                    audio.staged_path or "",
                ),
            ),
        ),
    )
    edit_service = SddSpecEditService(projects_root=tmp_path / "projects")
    job_service = SddCodexJobService(projects_root=tmp_path / "projects")

    dry_run = edit_service.dry_run_existing_spec_edit(request)
    job = job_service.start_existing_spec_edit_job(request=request, dry_run=dry_run)

    assert job.status == "queued"
    assert (
        f"specs/001-existing/intake/jobs/{job.id}/media/frame-001.png"
        in job.intake_references
    )
    assert (
        f"specs/001-existing/intake/jobs/{job.id}/media/narration.m4a"
        in job.intake_references
    )
    persisted = job.media_persistence["persisted"]
    assert any(
        item["metadata"].get("timeline_ms") == [0, 1000]
        for item in persisted
        if item["kind"] == "sequence_manifest"
    )
    assert (
        project / f"specs/001-existing/intake/jobs/{job.id}/timeline.yaml"
    ).is_file()


def test_codex_job_blocks_invalid_dry_run_and_invalid_workspace(tmp_path: Path) -> None:
    project = _write_project(tmp_path, include_plan=False)
    job_service = SddCodexJobService(projects_root=tmp_path / "projects")
    edit_service = SddSpecEditService(projects_root=tmp_path / "projects")

    blocked_dry_run = edit_service.dry_run_existing_spec_edit(
        _edit_request(project, artifact="plan")
    )
    job = job_service.start_existing_spec_edit_job(
        request=_edit_request(project, artifact="plan"),
        dry_run=blocked_dry_run,
    )

    assert job.status == "blocked"
    assert job.blocked_reasons == ("Spec edit dry-run is blocked.",)
    assert not (project / ".codex-bridge").exists()

    unsafe_request = SpecIntakeValidationInput(
        workspace_path=str(tmp_path / "outside"),
        spec_target=SpecTargetInput(
            mode="existing_spec",
            spec_id="001-existing",
            artifact="tasks",
        ),
        intake_items=(SpecIntakeMediaItemInput(kind="text", text="Edit"),),
    )
    unsafe_dry_run = edit_service.dry_run_existing_spec_edit(unsafe_request)
    unsafe_job = job_service.start_existing_spec_edit_job(
        request=unsafe_request,
        dry_run=unsafe_dry_run,
    )

    assert unsafe_job.status == "blocked"
    assert unsafe_job.command_argv == ()


def test_codex_job_timeout_cancel_nonzero_and_concurrency_limit(
    tmp_path: Path,
) -> None:
    timeout_project = _write_project(tmp_path / "timeout")
    timeout_edit_service = SddSpecEditService(
        projects_root=tmp_path / "timeout/projects"
    )
    timeout_request = _edit_request(timeout_project)
    timeout_dry_run = timeout_edit_service.dry_run_existing_spec_edit(timeout_request)

    timeout_service = SddCodexJobService(
        projects_root=tmp_path / "timeout/projects",
        runner=FakeRunner(exc=subprocess.TimeoutExpired(cmd=("codex",), timeout=1)),
        timeout_seconds=1,
    )
    timeout_job = timeout_service.start_existing_spec_edit_job(
        request=timeout_request,
        dry_run=timeout_dry_run,
    )
    timed_out = timeout_service.run_job(timeout_job.id)

    assert timed_out.status == "timed_out"
    assert "timed out" in timed_out.blocked_reasons[0]

    failing_project = _write_project(tmp_path / "failing")
    failing_edit_service = SddSpecEditService(
        projects_root=tmp_path / "failing/projects"
    )
    failing_request = _edit_request(failing_project)
    failing_dry_run = failing_edit_service.dry_run_existing_spec_edit(failing_request)
    failing_service = SddCodexJobService(
        projects_root=tmp_path / "failing/projects",
        runner=FakeRunner(
            SddCodexProcessResult(returncode=2, stdout="", stderr="bad request")
        ),
    )
    failing_job = failing_service.start_existing_spec_edit_job(
        request=failing_request,
        dry_run=failing_dry_run,
    )
    failed = failing_service.run_job(failing_job.id)

    assert failed.status == "failed"
    assert failed.exit_code == 2
    assert failed.stderr == "bad request"

    cancel_project = _write_project(tmp_path / "cancel")
    cancel_edit_service = SddSpecEditService(projects_root=tmp_path / "cancel/projects")
    cancel_request = _edit_request(cancel_project)
    cancel_dry_run = cancel_edit_service.dry_run_existing_spec_edit(cancel_request)
    cancel_service = SddCodexJobService(projects_root=tmp_path / "cancel/projects")
    queued = cancel_service.start_existing_spec_edit_job(
        request=cancel_request,
        dry_run=cancel_dry_run,
    )
    cancelled = cancel_service.cancel_job(queued.id)
    assert cancelled.status == "cancelled"
    assert cancelled.to_payload()["activity_state"] == "cancelled"

    concurrency_project = _write_project(tmp_path / "concurrency")
    concurrency_edit_service = SddSpecEditService(
        projects_root=tmp_path / "concurrency/projects"
    )
    concurrency_request = _edit_request(concurrency_project)
    concurrency_dry_run = concurrency_edit_service.dry_run_existing_spec_edit(
        concurrency_request
    )
    concurrency_service = SddCodexJobService(
        projects_root=tmp_path / "concurrency/projects"
    )
    first = concurrency_service.start_existing_spec_edit_job(
        request=concurrency_request,
        dry_run=concurrency_dry_run,
    )
    second = concurrency_service.start_existing_spec_edit_job(
        request=_edit_request(concurrency_project, text="Another edit"),
        dry_run=concurrency_dry_run,
    )

    assert first.status == "queued"
    assert second.status == "blocked"
    assert "already active" in second.blocked_reasons[0]


def test_codex_job_retry_creates_new_clean_queued_job_from_failed(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    edit_service = SddSpecEditService(projects_root=tmp_path / "projects")
    request = _edit_request(project)
    dry_run = edit_service.dry_run_existing_spec_edit(request)
    job_service = SddCodexJobService(
        projects_root=tmp_path / "projects",
        runner=FakeRunner(SddCodexProcessResult(returncode=2, stderr="bad")),
    )
    original = job_service.start_existing_spec_edit_job(
        request=request,
        dry_run=dry_run,
    )
    failed = job_service.run_job(original.id)
    (project / failed.sandbox_root / "specs/001-existing/tasks.md").write_text(
        "- [x] unsafe generated output\n"
    )

    retry = job_service.retry_job(failed.id)

    assert retry.status == "queued"
    assert retry.retry_eligible is True
    assert retry.retry_job_id != failed.id
    assert retry.job is not None
    assert retry.job.retry_source_job_id == failed.id
    assert retry.job.status == "queued"
    assert "request.json" in retry.copied_references
    assert (project / retry.job.job_root / "request.json").is_file()
    assert (project / retry.job.sandbox_root / ".codex-job/prompt.md").is_file()
    assert (
        project / retry.job.sandbox_root / "specs/001-existing/tasks.md"
    ).read_text() == "- [ ] Existing\n"
    assert (project / "specs/001-existing/tasks.md").read_text() == "- [ ] Existing\n"
    payload = retry.to_payload()
    assert payload["original_job_id"] == failed.id
    assert payload["retry_job_id"] == retry.job.id
    assert payload["activity_state"] == "queued"
    assert any(
        event["state"] == "retry-created"
        for event in retry.job.to_payload()["activity"]["events"]
    )


def test_codex_job_retry_blocks_ineligible_concurrency_and_stale_target(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    edit_service = SddSpecEditService(projects_root=tmp_path / "projects")
    request = _edit_request(project)
    dry_run = edit_service.dry_run_existing_spec_edit(request)
    service = SddCodexJobService(projects_root=tmp_path / "projects")
    queued = service.start_existing_spec_edit_job(request=request, dry_run=dry_run)

    running_block = service.retry_job(queued.id)
    assert running_block.status == "blocked"
    assert "current status is queued" in running_block.blocked_reasons[0]

    cancelled = service.cancel_job(queued.id)
    service._jobs["sddjob-active"] = replace(
        cancelled,
        id="sddjob-active",
        status="queued",
        process_state="queued",
        completed_at_epoch=None,
    )
    concurrency_block = service.retry_job(cancelled.id)
    assert concurrency_block.status == "blocked"
    assert "already active" in concurrency_block.blocked_reasons[0]

    service.cancel_job("sddjob-active")
    (project / "specs/001-existing/tasks.md").write_text("- [ ] Changed outside\n")
    stale_block = service.retry_job(cancelled.id)
    assert stale_block.status == "blocked"
    assert "changed since original job" in stale_block.blocked_reasons[0]

    completed_project = _write_project(tmp_path / "completed")
    completed_edit_service = SddSpecEditService(
        projects_root=tmp_path / "completed/projects"
    )
    completed_request = _edit_request(completed_project)
    completed_dry_run = completed_edit_service.dry_run_existing_spec_edit(
        completed_request
    )
    completed_service = SddCodexJobService(
        projects_root=tmp_path / "completed/projects",
        runner=FakeRunner(),
    )
    completed_job = completed_service.start_existing_spec_edit_job(
        request=completed_request,
        dry_run=completed_dry_run,
    )
    completed_service.run_job(completed_job.id)
    completed_block = completed_service.retry_job(completed_job.id)
    assert completed_block.status == "blocked"
    assert "current status is completed" in completed_block.blocked_reasons[0]


def test_codex_job_retry_endpoint_reports_original_and_retry_ids(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    client = TestClient(
        create_app(
            Settings(
                projects_root=str(tmp_path / "projects"),
                chat_store_backend="memory",
                audio_transcription_backend="disabled",
                speech_synthesis_backend="disabled",
            )
        )
    )
    apply_response = client.post(
        "/sdd/specs/edit/apply",
        json={
            "workspacePath": str(project),
            "specTarget": {
                "mode": "existing_spec",
                "specId": "001-existing",
                "artifact": "tasks",
            },
            "intakeItems": [{"kind": "text", "text": "Update tasks"}],
        },
    )
    job_id = apply_response.json()["job"]["job_id"]
    cancel_response = client.post(f"/sdd/codex-jobs/{job_id}/cancel")
    assert cancel_response.json()["status"] == "cancelled"

    retry_response = client.post(f"/sdd/codex-jobs/{job_id}/retry")

    assert retry_response.status_code == 200
    payload = retry_response.json()
    assert payload["kind"] == "codex.sddCodexJobRetry"
    assert payload["status"] == "queued"
    assert payload["retry_eligible"] is True
    assert payload["original_job_id"] == job_id
    assert payload["retry_job_id"] != job_id
    assert payload["job"]["retry_source_job_id"] == job_id
    assert payload["activity"]["events"][0]["state"] == "retry-created"
    assert client.post("/sdd/codex-jobs/missing/retry").status_code == 404


def test_codex_job_review_apply_keeps_repo_unchanged_until_explicit_apply(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    runner = WritingRunner(
        {"specs/001-existing/tasks.md": "- [x] Existing\n- [ ] Added by Codex\n"}
    )
    job_service = SddCodexJobService(
        projects_root=tmp_path / "projects",
        runner=runner,
    )
    edit_service = SddSpecEditService(projects_root=tmp_path / "projects")
    request = _edit_request(project)
    dry_run = edit_service.dry_run_existing_spec_edit(request)

    job = job_service.start_existing_spec_edit_job(request=request, dry_run=dry_run)
    completed = job_service.run_job(job.id)

    assert completed.status == "completed"
    assert (project / "specs/001-existing/tasks.md").read_text() == "- [ ] Existing\n"

    review = job_service.review_job(job.id)

    assert review.status == "ready"
    assert review.to_payload()["activity_state"] == "review-ready"
    assert review.to_payload()["activity"]["events"][0]["state"] == "review-ready"
    assert review.validation_status == "pass"
    assert review.changed_files[0].path == "specs/001-existing/tasks.md"
    assert review.changed_files[0].patch_path is not None
    assert (project / review.changed_files[0].patch_path).is_file()

    apply_result = job_service.apply_reviewed_job(job.id)

    assert apply_result.status == "applied"
    assert apply_result.to_payload()["activity_state"] == "applied"
    assert any(
        event["state"] == "reviewed-apply-completed"
        for event in apply_result.to_payload()["activity"]["events"]
    )
    assert apply_result.applied == ("specs/001-existing/tasks.md",)
    assert "Added by Codex" in (project / "specs/001-existing/tasks.md").read_text()
    assert apply_result.post_apply_refresh["metadata_refresh"]["status"] in {
        "updated",
        "unchanged",
    }
    assert apply_result.post_apply_refresh["index_status"]["state"] in {
        "fresh",
        "regenerated",
    }


def test_codex_job_activity_endpoint_reports_queued_state(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    client = TestClient(
        create_app(
            Settings(
                projects_root=str(tmp_path / "projects"),
                chat_store_backend="memory",
                audio_transcription_backend="disabled",
                speech_synthesis_backend="disabled",
            )
        )
    )

    apply_response = client.post(
        "/sdd/specs/edit/apply",
        json={
            "workspacePath": str(project),
            "specTarget": {
                "mode": "existing_spec",
                "specId": "001-existing",
                "artifact": "tasks",
            },
            "intakeItems": [{"kind": "text", "text": "Update tasks"}],
        },
    )
    job_id = apply_response.json()["job"]["job_id"]

    activity_response = client.get(f"/sdd/codex-jobs/{job_id}/activity")

    assert activity_response.status_code == 200
    payload = activity_response.json()
    assert payload["kind"] == "codex.sddActivity"
    assert payload["state"] == "queued"
    assert [event["state"] for event in payload["events"]] == [
        "received",
        "media-consumed",
        "preparing-context",
        "queued",
    ]
    assert "review" not in " ".join(event["state"] for event in payload["events"])


def test_codex_job_review_blocks_unsafe_and_protected_generated_changes(
    tmp_path: Path,
) -> None:
    project = _write_project(tmp_path)
    job_service = SddCodexJobService(
        projects_root=tmp_path / "projects",
        runner=WritingRunner(
            {
                "specs/001-existing/tasks.md": "- [x] Existing\n",
                "specs/001-existing/plan.md": "# Unexpected\n",
                "architecture/components.mmd": "flowchart TD\n  A-->B\n",
            }
        ),
    )
    edit_service = SddSpecEditService(projects_root=tmp_path / "projects")
    request = _edit_request(project)
    dry_run = edit_service.dry_run_existing_spec_edit(request)

    job = job_service.start_existing_spec_edit_job(request=request, dry_run=dry_run)
    job_service.run_job(job.id)
    review = job_service.review_job(job.id)
    apply_result = job_service.apply_reviewed_job(job.id)

    assert review.status == "blocked"
    assert "specs/001-existing/plan.md" in review.blocked_paths
    assert "architecture/components.mmd" in review.protected_baseline_impacts
    assert apply_result.status == "blocked"
    assert (project / "specs/001-existing/tasks.md").read_text() == "- [ ] Existing\n"


def test_codex_job_review_blocks_conflict_before_apply(tmp_path: Path) -> None:
    project = _write_project(tmp_path)
    job_service = SddCodexJobService(
        projects_root=tmp_path / "projects",
        runner=WritingRunner({"specs/001-existing/tasks.md": "- [x] Existing\n"}),
    )
    edit_service = SddSpecEditService(projects_root=tmp_path / "projects")
    request = _edit_request(project)
    dry_run = edit_service.dry_run_existing_spec_edit(request)

    job = job_service.start_existing_spec_edit_job(request=request, dry_run=dry_run)
    job_service.run_job(job.id)
    (project / "specs/001-existing/tasks.md").write_text("- [ ] Changed outside\n")
    review = job_service.review_job(job.id)

    assert review.status == "blocked"
    assert review.conflicts
    assert "changed since job started" in review.conflicts[0]


def test_codex_job_apply_restores_original_on_write_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = _write_project(tmp_path)
    job_service = SddCodexJobService(
        projects_root=tmp_path / "projects",
        runner=WritingRunner({"specs/001-existing/tasks.md": "- [x] Existing\n"}),
    )
    edit_service = SddSpecEditService(projects_root=tmp_path / "projects")
    request = _edit_request(project)
    dry_run = edit_service.dry_run_existing_spec_edit(request)

    job = job_service.start_existing_spec_edit_job(request=request, dry_run=dry_run)
    job_service.run_job(job.id)

    import backend.app.application.services.sdd_codex_job_service as job_module

    calls = {"count": 0}

    def fail_write(path: Path, content: bytes) -> None:
        calls["count"] += 1
        path.write_bytes(content)
        if calls["count"] == 1:
            raise OSError("forced write failure")

    monkeypatch.setattr(job_module, "_write_atomic_bytes", fail_write)
    apply_result = job_service.apply_reviewed_job(job.id)

    assert apply_result.status == "blocked"
    assert "forced write failure" in apply_result.blocked[0]
    assert (project / "specs/001-existing/tasks.md").read_text() == "- [ ] Existing\n"


def _edit_request(
    project: Path,
    *,
    artifact: str = "tasks",
    text: str = "Update tasks",
    intake_items: tuple[SpecIntakeMediaItemInput, ...] | None = None,
) -> SpecIntakeValidationInput:
    return SpecIntakeValidationInput(
        workspace_path=str(project),
        spec_target=SpecTargetInput(
            mode="existing_spec",
            spec_id="001-existing",
            artifact=artifact,
        ),
        intake_items=intake_items
        if intake_items is not None
        else (SpecIntakeMediaItemInput(kind="text", text=text),),
    )


def _write_project(
    tmp_path: Path,
    *,
    include_plan: bool = True,
) -> Path:
    project = tmp_path / "projects/demo"
    spec_root = project / "specs/001-existing"
    spec_root.mkdir(parents=True)
    (project / "codex-bridge.yaml").write_text("sdd:\n  standard: workbench-sdd/v1\n")
    (spec_root / "spec.md").write_text("# Existing Spec\n\nCurrent behavior.\n")
    if include_plan:
        (spec_root / "plan.md").write_text("# Plan\n")
    (spec_root / "tasks.md").write_text("- [ ] Existing\n")
    (spec_root / "traceability.yaml").write_text("requirements: {}\n")
    return project
