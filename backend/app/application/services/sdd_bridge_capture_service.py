from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.application.services.feedback_queue_service import FeedbackQueueItem
from backend.app.application.services.sdd_media_upload_service import (
    SddMediaUploadService,
    SddMediaUploadResult,
)
from backend.app.application.services.sdd_spec_creation_service import (
    SddSpecCreationService,
)
from backend.app.application.services.sdd_spec_edit_service import SddSpecEditService
from backend.app.application.services.sdd_spec_target_service import (
    SpecIntakeMediaItemInput,
    SpecIntakeValidationInput,
    SpecTargetInput,
)


@dataclass(frozen=True, slots=True)
class SddBridgeCaptureResult:
    status: str
    workspace_path: str
    target_mode: str
    feedback_item_ids: tuple[str, ...]
    intake_items: tuple[SpecIntakeMediaItemInput, ...]
    staged_media: tuple[dict[str, object], ...]
    dry_run: dict[str, object] | None
    apply_result: dict[str, object] | None
    blocked: tuple[str, ...]
    next_actions: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": "codex.sddBridgeCaptureIntake",
            "version": 1,
            "status": self.status,
            "workspace_path": self.workspace_path,
            "target_mode": self.target_mode,
            "feedback_item_ids": list(self.feedback_item_ids),
            "intake_items": [_intake_item_payload(item) for item in self.intake_items],
            "staged_media": list(self.staged_media),
            "dry_run": self.dry_run,
            "apply_result": self.apply_result,
            "blocked": list(self.blocked),
            "next_actions": list(self.next_actions),
        }


class SddBridgeCaptureService:
    def __init__(
        self,
        *,
        projects_root: str | Path,
        workspace_aliases: dict[str, str] | None = None,
        codex_job_service: object | None = None,
    ) -> None:
        self._projects_root = Path(projects_root).expanduser().resolve()
        self._workspace_aliases = workspace_aliases or {}
        self._media_service = SddMediaUploadService(
            projects_root=self._projects_root,
            workspace_aliases=self._workspace_aliases,
        )
        self._creation_service = SddSpecCreationService(
            projects_root=self._projects_root,
            workspace_aliases=self._workspace_aliases,
        )
        self._edit_service = SddSpecEditService(
            projects_root=self._projects_root,
            workspace_aliases=self._workspace_aliases,
            codex_job_service=codex_job_service,
        )

    def dry_run_capture(
        self,
        *,
        workspace_path: str,
        spec_target: SpecTargetInput,
        feedback_items: tuple[FeedbackQueueItem, ...],
        artifact: str | None = None,
        job_id: str = "bridge-capture",
    ) -> SddBridgeCaptureResult:
        return self._run(
            workspace_path=workspace_path,
            spec_target=spec_target,
            feedback_items=feedback_items,
            artifact=artifact,
            job_id=job_id,
            apply=False,
        )

    def apply_capture(
        self,
        *,
        workspace_path: str,
        spec_target: SpecTargetInput,
        feedback_items: tuple[FeedbackQueueItem, ...],
        artifact: str | None = None,
        job_id: str = "bridge-capture",
    ) -> SddBridgeCaptureResult:
        return self._run(
            workspace_path=workspace_path,
            spec_target=spec_target,
            feedback_items=feedback_items,
            artifact=artifact,
            job_id=job_id,
            apply=True,
        )

    def _run(
        self,
        *,
        workspace_path: str,
        spec_target: SpecTargetInput,
        feedback_items: tuple[FeedbackQueueItem, ...],
        artifact: str | None,
        job_id: str,
        apply: bool,
    ) -> SddBridgeCaptureResult:
        normalized_target = SpecTargetInput(
            mode=spec_target.mode,
            spec_id=spec_target.spec_id,
            artifact=artifact or spec_target.artifact or "auto",
        )
        if normalized_target.mode == "none":
            return SddBridgeCaptureResult(
                status="feedback-only",
                workspace_path=workspace_path,
                target_mode="none",
                feedback_item_ids=tuple(item.id for item in feedback_items),
                intake_items=(),
                staged_media=(),
                dry_run=None,
                apply_result=None,
                blocked=(),
                next_actions=(
                    "spec_target.mode none preserves ordinary Bridge feedback behavior.",
                ),
            )
        intake_items, staged_media, blockers = self._to_intake_items(
            workspace_path=workspace_path,
            feedback_items=feedback_items,
        )
        if blockers:
            return SddBridgeCaptureResult(
                status="blocked",
                workspace_path=workspace_path,
                target_mode=normalized_target.mode,
                feedback_item_ids=tuple(item.id for item in feedback_items),
                intake_items=intake_items,
                staged_media=tuple(staged_media),
                dry_run=None,
                apply_result=None,
                blocked=tuple(blockers),
                next_actions=("Fix capture media blockers before SDD intake.",),
            )
        request = SpecIntakeValidationInput(
            workspace_path=workspace_path,
            spec_target=normalized_target,
            bridge_spec_target=normalized_target,
            intake_items=intake_items,
        )
        if normalized_target.mode == "new_spec":
            dry_run = self._creation_service.dry_run_new_spec(request, job_id=job_id)
            if not apply:
                return _result(
                    status=dry_run.status,
                    workspace_path=workspace_path,
                    target=normalized_target,
                    feedback_items=feedback_items,
                    intake_items=intake_items,
                    staged_media=tuple(staged_media),
                    dry_run=dry_run.to_payload(),
                    apply_result=None,
                )
            apply_result = self._creation_service.apply_new_spec(
                request,
                job_id=job_id,
            )
            return _result(
                status=apply_result.status,
                workspace_path=workspace_path,
                target=normalized_target,
                feedback_items=feedback_items,
                intake_items=intake_items,
                staged_media=tuple(staged_media),
                dry_run=dry_run.to_payload(),
                apply_result=apply_result.to_payload(),
            )
        if normalized_target.mode == "existing_spec":
            dry_run = self._edit_service.dry_run_existing_spec_edit(request)
            if not apply:
                return _result(
                    status=dry_run.status,
                    workspace_path=workspace_path,
                    target=normalized_target,
                    feedback_items=feedback_items,
                    intake_items=intake_items,
                    staged_media=tuple(staged_media),
                    dry_run=dry_run.to_payload(),
                    apply_result=None,
                )
            apply_result = self._edit_service.apply_existing_spec_edit(
                request,
            )
            return _result(
                status=apply_result.status,
                workspace_path=workspace_path,
                target=normalized_target,
                feedback_items=feedback_items,
                intake_items=intake_items,
                staged_media=tuple(staged_media),
                dry_run=dry_run.to_payload(),
                apply_result=apply_result.to_payload(),
            )
        return SddBridgeCaptureResult(
            status="blocked",
            workspace_path=workspace_path,
            target_mode=normalized_target.mode,
            feedback_item_ids=tuple(item.id for item in feedback_items),
            intake_items=intake_items,
            staged_media=tuple(staged_media),
            dry_run=None,
            apply_result=None,
            blocked=(f"unsupported spec_target mode: {normalized_target.mode}",),
            next_actions=("Choose none, new_spec, or existing_spec.",),
        )

    def _to_intake_items(
        self,
        *,
        workspace_path: str,
        feedback_items: tuple[FeedbackQueueItem, ...],
    ) -> tuple[
        tuple[SpecIntakeMediaItemInput, ...], list[dict[str, object]], list[str]
    ]:
        intake_items: list[SpecIntakeMediaItemInput] = []
        staged_media: list[dict[str, object]] = []
        blockers: list[str] = []
        image_refs: list[str] = []
        audio_ref: str | None = None
        audio_item: SpecIntakeMediaItemInput | None = None
        for index, item in enumerate(feedback_items):
            text = item.comment.strip()
            if text:
                intake_items.append(SpecIntakeMediaItemInput(kind="text", text=text))
            if item.screenshot_file:
                staged = self._stage_file(
                    workspace_path=workspace_path,
                    path=Path(item.screenshot_file),
                    kind="image",
                    mime_type=item.screenshot_mime_type or "image/png",
                    duration_ms=None,
                )
                if staged.status != "staged" or staged.intake_item is None:
                    blockers.extend(staged.blocked)
                else:
                    staged_media.append(staged.to_payload())
                    payload_ref = str(staged.intake_item["payload_ref"])
                    image_refs.append(payload_ref)
                    if len(feedback_items) == 1 and not item.audio_file:
                        intake_items.append(
                            SpecIntakeMediaItemInput(**staged.intake_item)
                        )
                        region = _bounds_region(item.selection_bounds)
                        if region:
                            intake_items.append(
                                SpecIntakeMediaItemInput(
                                    kind="marked_region",
                                    mime_type=str(staged.intake_item["mime_type"]),
                                    byte_size=int(staged.intake_item["byte_size"]),
                                    filename=f"{item.id}-marked.png",
                                    source_ref=payload_ref,
                                    payload_ref=payload_ref,
                                    region=region,
                                )
                            )
            if item.audio_file:
                staged_audio = self._stage_file(
                    workspace_path=workspace_path,
                    path=Path(item.audio_file),
                    kind="audio",
                    mime_type=item.audio_mime_type or "audio/mp4",
                    duration_ms=item.audio_duration_ms,
                )
                if staged_audio.status != "staged" or staged_audio.intake_item is None:
                    blockers.extend(staged_audio.blocked)
                else:
                    staged_media.append(staged_audio.to_payload())
                    audio_ref = str(staged_audio.intake_item["payload_ref"])
                    audio_item = SpecIntakeMediaItemInput(**staged_audio.intake_item)
        if len(feedback_items) > 1 and image_refs and audio_ref is None:
            intake_items.append(
                SpecIntakeMediaItemInput(
                    kind="screenshot_batch",
                    image_count=len(image_refs),
                    references=tuple(image_refs),
                )
            )
        if image_refs and audio_ref is not None:
            intake_items.append(
                SpecIntakeMediaItemInput(
                    kind="image_sequence",
                    frame_count=len(image_refs),
                    audio_track_count=1,
                    timeline_ms=tuple(index * 1000 for index in range(len(image_refs))),
                    references=tuple([*image_refs, audio_ref]),
                )
            )
        elif audio_item is not None and not image_refs:
            intake_items.append(audio_item)
        return (tuple(intake_items), staged_media, blockers)

    def _stage_file(
        self,
        *,
        workspace_path: str,
        path: Path,
        kind: str,
        mime_type: str,
        duration_ms: int | None,
    ):
        if not path.is_file():
            return SddMediaUploadResult(
                status="blocked",
                workspace_path=workspace_path,
                intake_item=None,
                staged_path=None,
                metadata_path=None,
                blocked=(f"capture media file is missing: {path}",),
                cleanup=(),
                next_actions=("Restore capture artifact before SDD intake.",),
            )
        content = path.read_bytes()
        staged = self._media_service.stage_media(
            workspace_path=workspace_path,
            kind=kind,
            filename=path.name,
            mime_type=mime_type,
            content=content,
            duration_ms=duration_ms,
        )
        if (
            staged.status == "blocked"
            and staged.blocked
            and "would overwrite" in staged.blocked[0]
        ):
            existing = _existing_staged_result(
                workspace_path=workspace_path,
                filename=path.name,
                kind=kind,
                mime_type=mime_type,
                content=content,
                duration_ms=duration_ms,
            )
            if existing is not None:
                return existing
        return staged


def _result(
    *,
    status: str,
    workspace_path: str,
    target: SpecTargetInput,
    feedback_items: tuple[FeedbackQueueItem, ...],
    intake_items: tuple[SpecIntakeMediaItemInput, ...],
    staged_media: tuple[dict[str, object], ...],
    dry_run: dict[str, object] | None,
    apply_result: dict[str, object] | None,
) -> SddBridgeCaptureResult:
    return SddBridgeCaptureResult(
        status=status,
        workspace_path=workspace_path,
        target_mode=target.mode,
        feedback_item_ids=tuple(item.id for item in feedback_items),
        intake_items=intake_items,
        staged_media=staged_media,
        dry_run=dry_run,
        apply_result=apply_result,
        blocked=tuple(_blocked_from_payload(apply_result or dry_run or {})),
        next_actions=tuple(_next_actions_from_payload(apply_result or dry_run or {})),
    )


def _blocked_from_payload(payload: dict[str, object]) -> list[str]:
    values = payload.get("blocked") or payload.get("blocked_reasons") or []
    return [str(item) for item in values] if isinstance(values, list) else []


def _next_actions_from_payload(payload: dict[str, object]) -> list[str]:
    values = payload.get("next_actions") or []
    return [str(item) for item in values] if isinstance(values, list) else []


def _bounds_region(bounds: dict[str, Any]) -> dict[str, float] | None:
    try:
        x = float(bounds["left"] if "left" in bounds else bounds["x"])
        y = float(bounds["top"] if "top" in bounds else bounds["y"])
        width = float(bounds["width"])
        height = float(bounds["height"])
    except (KeyError, TypeError, ValueError):
        return None
    if width <= 0 or height <= 0 or x < 0 or y < 0:
        return None
    return {"x": x, "y": y, "width": width, "height": height}


def _existing_staged_result(
    *,
    workspace_path: str,
    filename: str,
    kind: str,
    mime_type: str,
    content: bytes,
    duration_ms: int | None,
) -> SddMediaUploadResult | None:
    digest = hashlib.sha256(content).hexdigest()
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", Path(filename).name).strip(".-")
    relative = f".codex-bridge/sdd-media/{digest[:16]}-{safe_name or 'media'}"
    workspace = Path(workspace_path).expanduser().resolve()
    media_path = workspace / relative
    metadata_path = media_path.with_suffix(media_path.suffix + ".json")
    if not media_path.is_file() or not metadata_path.is_file():
        return None
    intake_item: dict[str, object] = {
        "kind": kind,
        "mime_type": mime_type,
        "byte_size": len(content),
        "filename": filename,
        "sha256": digest,
        "payload_ref": relative,
    }
    if duration_ms is not None:
        intake_item["duration_ms"] = duration_ms
    return SddMediaUploadResult(
        status="staged",
        workspace_path=str(workspace),
        intake_item=intake_item,
        staged_path=relative,
        metadata_path=f"{relative}.json",
        blocked=(),
        cleanup=(),
        next_actions=(),
    )


def _intake_item_payload(item: SpecIntakeMediaItemInput) -> dict[str, object]:
    return {
        "kind": item.kind,
        **({"mime_type": item.mime_type} if item.mime_type else {}),
        **({"byte_size": item.byte_size} if item.byte_size is not None else {}),
        **({"filename": item.filename} if item.filename else {}),
        **({"sha256": item.sha256} if item.sha256 else {}),
        **({"text": item.text} if item.text else {}),
        **({"transcript": item.transcript} if item.transcript else {}),
        **({"duration_ms": item.duration_ms} if item.duration_ms is not None else {}),
        **({"source_ref": item.source_ref} if item.source_ref else {}),
        **({"payload_ref": item.payload_ref} if item.payload_ref else {}),
        **({"region": dict(item.region)} if item.region else {}),
        **({"image_count": item.image_count} if item.image_count is not None else {}),
        **({"frame_count": item.frame_count} if item.frame_count is not None else {}),
        **(
            {"audio_track_count": item.audio_track_count}
            if item.audio_track_count is not None
            else {}
        ),
        **({"timeline_ms": list(item.timeline_ms)} if item.timeline_ms else {}),
        **({"references": list(item.references)} if item.references else {}),
    }
