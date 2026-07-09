from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from backend.app.application.services.sdd_media_upload_service import (
    SddMediaUploadService,
)
from backend.app.application.services.sdd_spec_target_service import (
    SddSpecTargetValidationService,
    SpecIntakeMediaItemInput,
    SpecIntakeValidationError,
    SpecIntakeValidationInput,
)


DEFAULT_RETENTION_HOURS = 24


@dataclass(frozen=True, slots=True)
class SddIntakePlannedArtifact:
    item_index: int
    kind: str
    target_path: str
    staging_path: str
    byte_size: int | None
    sha256: str | None
    retention: str


@dataclass(frozen=True, slots=True)
class SddIntakeDryRun:
    status: str
    workspace_path: str | None
    spec_id: str | None
    target_root: str | None
    staging_root: str
    retention_hours: int
    would_create: tuple[SddIntakePlannedArtifact, ...]
    existing: tuple[str, ...]
    blocked: tuple[str, ...]
    rejected_media: tuple[SpecIntakeValidationError, ...]
    next_actions: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": "codex.sddIntakeDryRun",
            "version": 1,
            "status": self.status,
            "workspace_path": self.workspace_path,
            "spec_id": self.spec_id,
            "target_root": self.target_root,
            "staging_root": self.staging_root,
            "retention_hours": self.retention_hours,
            "would_create": [
                {
                    "item_index": item.item_index,
                    "kind": item.kind,
                    "target_path": item.target_path,
                    "staging_path": item.staging_path,
                    "byte_size": item.byte_size,
                    "sha256": item.sha256,
                    "retention": item.retention,
                }
                for item in self.would_create
            ],
            "existing": list(self.existing),
            "blocked": list(self.blocked),
            "rejected_media": [
                {
                    "code": error.code,
                    "field": error.field,
                    "message": error.message,
                }
                for error in self.rejected_media
            ],
            "next_actions": list(self.next_actions),
        }


@dataclass(frozen=True, slots=True)
class SddIntakePersistedArtifact:
    item_index: int
    kind: str
    target_path: str
    byte_size: int
    sha256: str | None
    source_ref: str | None
    metadata: dict[str, object]

    def to_payload(self) -> dict[str, object]:
        return {
            "item_index": self.item_index,
            "kind": self.kind,
            "target_path": self.target_path,
            "byte_size": self.byte_size,
            "sha256": self.sha256,
            "source_ref": self.source_ref,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class SddIntakePersistenceResult:
    status: str
    dry_run: SddIntakeDryRun
    persisted: tuple[SddIntakePersistedArtifact, ...]
    blocked: tuple[str, ...]
    cleanup: tuple[str, ...]
    retention_manifest_path: str | None
    next_actions: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": "codex.sddIntakePersistence",
            "version": 1,
            "status": self.status,
            "dry_run": self.dry_run.to_payload(),
            "persisted": [artifact.to_payload() for artifact in self.persisted],
            "blocked": list(self.blocked),
            "cleanup": list(self.cleanup),
            "retention_manifest_path": self.retention_manifest_path,
            "next_actions": list(self.next_actions),
        }


class SddIntakeService:
    def __init__(
        self,
        *,
        projects_root: str | Path,
        workspace_aliases: dict[str, str] | None = None,
        staging_root: str | Path = ".codex-bridge/sdd-intake",
        validator: SddSpecTargetValidationService | None = None,
    ) -> None:
        self._projects_root = Path(projects_root).expanduser().resolve()
        self._workspace_aliases = workspace_aliases or {}
        self._staging_root = Path(staging_root)
        self._validator = validator or SddSpecTargetValidationService(
            projects_root=self._projects_root,
            workspace_aliases=self._workspace_aliases,
        )

    def dry_run_storage(
        self,
        request: SpecIntakeValidationInput,
        *,
        job_id: str = "dry-run",
    ) -> SddIntakeDryRun:
        validation = self._validator.validate(request)
        safe_job_id = _safe_job_id(job_id)
        staging_root = (self._staging_root / safe_job_id).as_posix()
        rejected_media = tuple(
            error
            for error in validation.errors
            if error.field.startswith("intake_items")
        )
        blockers = tuple(
            f"{error.field}: {error.code}: {error.message}"
            for error in validation.errors
            if not error.field.startswith("intake_items")
        )
        if not validation.ok:
            return SddIntakeDryRun(
                status="blocked",
                workspace_path=validation.workspace_path,
                spec_id=validation.spec_id,
                target_root=validation.spec_root,
                staging_root=staging_root,
                retention_hours=DEFAULT_RETENTION_HOURS,
                would_create=(),
                existing=(),
                blocked=blockers,
                rejected_media=rejected_media,
                next_actions=("Fix validation errors before storing intake media.",),
            )

        target_root = _target_root_for_validation(
            validation,
            safe_job_id=safe_job_id,
        )
        artifacts = tuple(
            artifact
            for index, item in enumerate(request.intake_items)
            for artifact in _planned_artifacts_for_item(
                item,
                item_index=index,
                target_root=target_root,
                staging_root=staging_root,
            )
        )
        duplicate_targets = _duplicate_target_paths(artifacts)
        if duplicate_targets:
            return SddIntakeDryRun(
                status="blocked",
                workspace_path=validation.workspace_path,
                spec_id=validation.spec_id,
                target_root=target_root,
                staging_root=staging_root,
                retention_hours=DEFAULT_RETENTION_HOURS,
                would_create=artifacts,
                existing=(),
                blocked=tuple(
                    f"duplicate planned intake artifact: {path}"
                    for path in duplicate_targets
                ),
                rejected_media=(),
                next_actions=("Adjust intake items so planned paths are unique.",),
            )
        source_ref_errors = _validate_structured_source_refs(
            Path(validation.workspace_path),
            request.intake_items,
            artifacts,
        )
        if source_ref_errors:
            return SddIntakeDryRun(
                status="blocked",
                workspace_path=validation.workspace_path,
                spec_id=validation.spec_id,
                target_root=target_root,
                staging_root=staging_root,
                retention_hours=DEFAULT_RETENTION_HOURS,
                would_create=artifacts,
                existing=(),
                blocked=source_ref_errors,
                rejected_media=(),
                next_actions=(
                    "Fix structured media references before storing intake.",
                ),
            )
        existing = tuple(
            artifact.target_path
            for artifact in artifacts
            if validation.workspace_path is not None
            and (Path(validation.workspace_path) / artifact.target_path).exists()
        )
        if existing:
            return SddIntakeDryRun(
                status="blocked",
                workspace_path=validation.workspace_path,
                spec_id=validation.spec_id,
                target_root=target_root,
                staging_root=staging_root,
                retention_hours=DEFAULT_RETENTION_HOURS,
                would_create=artifacts,
                existing=existing,
                blocked=tuple(
                    f"would overwrite existing intake artifact: {path}"
                    for path in existing
                ),
                rejected_media=(),
                next_actions=(
                    "Choose a new job id or remove existing intake artifacts.",
                ),
            )

        return SddIntakeDryRun(
            status="dry-run",
            workspace_path=validation.workspace_path,
            spec_id=validation.spec_id,
            target_root=target_root,
            staging_root=staging_root,
            retention_hours=DEFAULT_RETENTION_HOURS,
            would_create=artifacts,
            existing=(),
            blocked=(),
            rejected_media=(),
            next_actions=("Dry-run only; no intake files were written.",),
        )

    def persist_storage(
        self,
        request: SpecIntakeValidationInput,
        *,
        job_id: str = "apply",
        dry_run: SddIntakeDryRun | None = None,
    ) -> SddIntakePersistenceResult:
        dry_run = dry_run or self.dry_run_storage(request, job_id=job_id)
        if dry_run.status != "dry-run":
            return SddIntakePersistenceResult(
                status="blocked",
                dry_run=dry_run,
                persisted=(),
                blocked=tuple(dry_run.blocked)
                or tuple(
                    f"{error.field}: {error.code}: {error.message}"
                    for error in dry_run.rejected_media
                ),
                cleanup=(),
                retention_manifest_path=None,
                next_actions=("Fix intake dry-run blockers before persisting media.",),
            )
        if dry_run.workspace_path is None or dry_run.target_root is None:
            return _blocked_persistence(
                dry_run,
                "workspace_path and target_root are required.",
            )
        workspace = Path(dry_run.workspace_path)
        path_errors = _validate_persistence_paths(workspace, dry_run)
        if path_errors:
            return SddIntakePersistenceResult(
                status="blocked",
                dry_run=dry_run,
                persisted=(),
                blocked=path_errors,
                cleanup=(),
                retention_manifest_path=None,
                next_actions=("Fix unsafe intake paths before persisting media.",),
            )

        created: list[Path] = []
        persisted: list[SddIntakePersistedArtifact] = []
        try:
            for artifact in dry_run.would_create:
                item = request.intake_items[artifact.item_index]
                target_path = (workspace / artifact.target_path).resolve()
                if target_path.exists():
                    raise FileExistsError(
                        f"would overwrite existing intake artifact: {artifact.target_path}"
                    )
                content, source_ref = _artifact_content(
                    workspace=workspace,
                    item=item,
                    artifact=artifact,
                    dry_run=dry_run,
                )
                _verify_planned_content(artifact, content)
                _write_atomic_bytes(target_path, content)
                created.append(target_path)
                persisted.append(
                    SddIntakePersistedArtifact(
                        item_index=artifact.item_index,
                        kind=artifact.kind,
                        target_path=artifact.target_path,
                        byte_size=len(content),
                        sha256=hashlib.sha256(content).hexdigest(),
                        source_ref=source_ref,
                        metadata=_structured_metadata_for_item(item),
                    )
                )
            manifest_path = workspace / dry_run.target_root / "retention.json"
            manifest_payload = {
                "retention_hours": dry_run.retention_hours,
                "artifacts": [artifact.to_payload() for artifact in persisted],
                "next_actions": _media_next_actions(request),
            }
            _write_atomic_bytes(
                manifest_path,
                json.dumps(manifest_payload, indent=2, sort_keys=True).encode() + b"\n",
            )
            created.append(manifest_path)
            _mark_staged_sources_consumed(
                projects_root=self._projects_root,
                workspace_aliases=self._workspace_aliases,
                workspace=workspace,
                persisted=tuple(persisted),
            )
            return SddIntakePersistenceResult(
                status="applied",
                dry_run=dry_run,
                persisted=tuple(persisted),
                blocked=(),
                cleanup=(),
                retention_manifest_path=manifest_path.relative_to(workspace).as_posix(),
                next_actions=_media_next_actions(request),
            )
        except Exception as exc:
            cleanup = _cleanup_created(created)
            return SddIntakePersistenceResult(
                status="blocked",
                dry_run=dry_run,
                persisted=(),
                blocked=(str(exc),),
                cleanup=cleanup,
                retention_manifest_path=None,
                next_actions=("Fix media persistence blockers and retry.",),
            )


def _target_root_for_validation(validation: object, *, safe_job_id: str) -> str:
    mode = getattr(validation, "mode", None)
    spec_id = getattr(validation, "spec_id", None)
    if mode == "none":
        return "feedback/intake"
    if mode == "existing_spec" and spec_id:
        return f"specs/{spec_id}/intake/jobs/{safe_job_id}"
    if spec_id:
        return f"specs/{spec_id}/intake"
    return "specs/<new-spec>/intake"


def _planned_artifacts_for_item(
    item: SpecIntakeMediaItemInput,
    *,
    item_index: int,
    target_root: str,
    staging_root: str,
) -> tuple[SddIntakePlannedArtifact, ...]:
    if item.kind == "text":
        return (
            _artifact(
                item,
                item_index,
                kind="text",
                relative_path=f"{target_root}/original-request.md",
                staging_root=staging_root,
            ),
        )
    if item.kind == "audio":
        extension = _extension_for_item(item, fallback=".m4a")
        return (
            _artifact(
                item,
                item_index,
                kind="audio",
                relative_path=f"{target_root}/media/audio-{item_index + 1:03d}{extension}",
                staging_root=staging_root,
            ),
            _artifact(
                item,
                item_index,
                kind="transcript",
                relative_path=f"{target_root}/transcript.md",
                staging_root=staging_root,
            ),
        )
    if item.kind in {"image", "crop", "marked_region"}:
        extension = _extension_for_item(item, fallback=".png")
        suffix = {"image": "image", "crop": "crop", "marked_region": "marked"}[
            item.kind
        ]
        return (
            _artifact(
                item,
                item_index,
                kind=item.kind,
                relative_path=f"{target_root}/media/{suffix}-{item_index + 1:03d}{extension}",
                staging_root=staging_root,
            ),
        )
    if item.kind == "screenshot_batch":
        count = item.image_count or 0
        return tuple(
            _artifact(
                item,
                item_index,
                kind="screenshot",
                relative_path=f"{target_root}/media/screenshot-{number:03d}.png",
                staging_root=staging_root,
            )
            for number in range(1, count + 1)
        )
    if item.kind == "image_sequence":
        frame_count = item.frame_count or 0
        artifacts = [
            _artifact(
                item,
                item_index,
                kind="sequence_frame",
                relative_path=f"{target_root}/media/frame-{number:03d}.png",
                staging_root=staging_root,
            )
            for number in range(1, frame_count + 1)
        ]
        if item.audio_track_count:
            artifacts.append(
                _artifact(
                    item,
                    item_index,
                    kind="sequence_audio",
                    relative_path=f"{target_root}/media/narration.m4a",
                    staging_root=staging_root,
                )
            )
        artifacts.append(
            _artifact(
                item,
                item_index,
                kind="sequence_manifest",
                relative_path=f"{target_root}/timeline.yaml",
                staging_root=staging_root,
            )
        )
        return tuple(artifacts)
    return ()


def _artifact(
    item: SpecIntakeMediaItemInput,
    item_index: int,
    *,
    kind: str,
    relative_path: str,
    staging_root: str,
) -> SddIntakePlannedArtifact:
    return SddIntakePlannedArtifact(
        item_index=item_index,
        kind=kind,
        target_path=relative_path,
        staging_path=f"{staging_root}/{relative_path}",
        byte_size=item.byte_size
        if kind not in {"text", "transcript", "sequence_manifest", "sequence_frame"}
        else None,
        sha256=item.sha256 if kind not in {"transcript", "sequence_manifest"} else None,
        retention="staged media eligible for cleanup after 24h until associated with a spec",
    )


def _extension_for_item(item: SpecIntakeMediaItemInput, *, fallback: str) -> str:
    if item.filename:
        suffix = Path(item.filename).suffix.lower()
        if suffix:
            return suffix
    mime_to_extension = {
        "audio/m4a": ".m4a",
        "audio/mp4": ".m4a",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/wav": ".wav",
        "audio/webm": ".webm",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
    }
    if item.mime_type:
        return mime_to_extension.get(item.mime_type.lower(), fallback)
    return fallback


def _safe_job_id(job_id: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", job_id.strip())
    normalized = normalized.strip(".-")
    return normalized or "dry-run"


def _duplicate_target_paths(
    artifacts: tuple[SddIntakePlannedArtifact, ...],
) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for artifact in artifacts:
        if artifact.target_path in seen and artifact.target_path not in duplicates:
            duplicates.append(artifact.target_path)
        seen.add(artifact.target_path)
    return tuple(duplicates)


def _blocked_persistence(
    dry_run: SddIntakeDryRun,
    reason: str,
) -> SddIntakePersistenceResult:
    return SddIntakePersistenceResult(
        status="blocked",
        dry_run=dry_run,
        persisted=(),
        blocked=(reason,),
        cleanup=(),
        retention_manifest_path=None,
        next_actions=("Fix intake persistence blockers and retry.",),
    )


def _validate_persistence_paths(
    workspace: Path,
    dry_run: SddIntakeDryRun,
) -> tuple[str, ...]:
    target_root = dry_run.target_root or ""
    errors: list[str] = []
    for artifact in dry_run.would_create:
        path = Path(artifact.target_path)
        if path.is_absolute() or ".." in path.parts:
            errors.append(f"unsafe intake artifact path: {artifact.target_path}")
            continue
        if not artifact.target_path.startswith(target_root.rstrip("/") + "/"):
            errors.append(
                f"intake artifact escapes target root: {artifact.target_path}"
            )
            continue
        resolved = (workspace / artifact.target_path).resolve()
        if not _is_relative_to(resolved, workspace):
            errors.append(f"intake artifact escapes workspace: {artifact.target_path}")
    return tuple(errors)


def _validate_structured_source_refs(
    workspace: Path,
    items: tuple[SpecIntakeMediaItemInput, ...],
    artifacts: tuple[SddIntakePlannedArtifact, ...],
) -> tuple[str, ...]:
    errors: list[str] = []
    seen_source_refs: set[str] = set()
    for item_index, item in enumerate(items):
        field = f"intake_items[{item_index}]"
        if item.kind in {"crop", "marked_region"} and item.source_ref:
            parent_found = any(
                previous.kind == "image"
                and item.source_ref
                in {
                    previous.filename or "",
                    previous.payload_ref or "",
                    f"media/{previous.filename or ''}",
                }
                for previous in items[:item_index]
            )
            if not parent_found:
                errors.append(f"{field}.source_ref: missing_parent_media")
        if item.kind == "screenshot_batch":
            expected = item.image_count or 0
            if len(item.references) != expected:
                errors.append(
                    f"{field}.references: expected {expected} references, got {len(item.references)}"
                )
        if item.kind == "image_sequence":
            expected = (item.frame_count or 0) + (item.audio_track_count or 0)
            if len(item.references) != expected:
                errors.append(
                    f"{field}.references: expected {expected} references, got {len(item.references)}"
                )
        for reference in item.references:
            if reference in seen_source_refs:
                errors.append(
                    f"{field}.references: duplicate media reference {reference}"
                )
            seen_source_refs.add(reference)
    for artifact in artifacts:
        item = items[artifact.item_index]
        source_ref = _source_ref_for_artifact(item, artifact)
        if source_ref is None:
            if artifact.kind not in {"text", "transcript", "sequence_manifest"}:
                errors.append(
                    f"intake_items[{artifact.item_index}].references: requires payload_ref or references for {artifact.kind}"
                )
            continue
        source_error = _source_ref_error(workspace, source_ref)
        if source_error:
            errors.append(
                f"intake_items[{artifact.item_index}].payload_ref: {source_error}"
            )
    return tuple(dict.fromkeys(errors))


def _source_ref_error(workspace: Path, source_ref: str) -> str | None:
    try:
        resolved = _resolve_source_ref(workspace, source_ref)
    except ValueError as exc:
        return str(exc)
    if source_ref.startswith(".codex-bridge/sdd-media/"):
        metadata_path = resolved.with_suffix(resolved.suffix + ".json")
        if not metadata_path.is_file():
            return f"staged media sidecar is missing: {source_ref}"
        try:
            metadata = json.loads(metadata_path.read_text())
        except json.JSONDecodeError:
            return f"staged media sidecar is malformed: {source_ref}"
        if isinstance(metadata, dict) and metadata.get("lifecycle") == "deleted":
            return f"staged media has been deleted: {source_ref}"
    return None


def _artifact_content(
    *,
    workspace: Path,
    item: SpecIntakeMediaItemInput,
    artifact: SddIntakePlannedArtifact,
    dry_run: SddIntakeDryRun,
) -> tuple[bytes, str | None]:
    if artifact.kind == "text":
        return ((item.text or item.transcript or "").encode("utf-8"), None)
    if artifact.kind == "transcript":
        transcript = item.transcript
        if transcript and transcript.strip():
            return (transcript.encode("utf-8"), None)
        return (
            (
                "# Transcript\n\n"
                "Transcription has not been generated yet. Run media extraction before "
                "asking Codex to depend on transcript text.\n"
            ).encode("utf-8"),
            None,
        )
    if artifact.kind == "sequence_manifest":
        return (_sequence_manifest(item, dry_run).encode("utf-8"), None)
    source_ref = _source_ref_for_artifact(item, artifact)
    if source_ref is None:
        raise ValueError(
            f"intake_items[{artifact.item_index}] requires payload_ref or references "
            f"for {artifact.kind} persistence."
        )
    source_path = _resolve_source_ref(workspace, source_ref)
    return (source_path.read_bytes(), source_ref)


def _source_ref_for_artifact(
    item: SpecIntakeMediaItemInput,
    artifact: SddIntakePlannedArtifact,
) -> str | None:
    if artifact.kind in {"audio", "image", "crop", "marked_region"}:
        return item.payload_ref
    if artifact.kind == "screenshot":
        index = _trailing_number(artifact.target_path) - 1
        return item.references[index] if 0 <= index < len(item.references) else None
    if artifact.kind == "sequence_frame":
        index = _trailing_number(artifact.target_path) - 1
        return item.references[index] if 0 <= index < len(item.references) else None
    if artifact.kind == "sequence_audio":
        frame_count = item.frame_count or 0
        return (
            item.references[frame_count] if frame_count < len(item.references) else None
        )
    return None


def _structured_metadata_for_item(
    item: SpecIntakeMediaItemInput,
) -> dict[str, object]:
    metadata: dict[str, object] = {}
    if item.source_ref:
        metadata["source_ref"] = item.source_ref
    if item.region:
        metadata["region"] = dict(item.region)
    if item.references:
        metadata["references"] = list(item.references)
    if item.timeline_ms:
        metadata["timeline_ms"] = list(item.timeline_ms)
    if item.frame_count is not None:
        metadata["frame_count"] = item.frame_count
    if item.audio_track_count is not None:
        metadata["audio_track_count"] = item.audio_track_count
    if item.image_count is not None:
        metadata["image_count"] = item.image_count
    return metadata


def _resolve_source_ref(workspace: Path, source_ref: str) -> Path:
    raw = Path(source_ref).expanduser()
    candidate = raw if raw.is_absolute() else workspace / raw
    resolved = candidate.resolve()
    if not _is_relative_to(resolved, workspace):
        raise ValueError(f"payload_ref escapes workspace: {source_ref}")
    if not resolved.is_file():
        raise ValueError(f"payload_ref does not resolve to a file: {source_ref}")
    return resolved


def _verify_planned_content(
    artifact: SddIntakePlannedArtifact,
    content: bytes,
) -> None:
    if artifact.byte_size is not None and len(content) != artifact.byte_size:
        raise ValueError(
            f"byte_size mismatch for {artifact.target_path}: "
            f"expected {artifact.byte_size}, got {len(content)}"
        )
    if artifact.sha256 is not None:
        digest = hashlib.sha256(content).hexdigest()
        if digest.lower() != artifact.sha256.lower():
            raise ValueError(f"sha256 mismatch for {artifact.target_path}")


def _sequence_manifest(item: SpecIntakeMediaItemInput, dry_run: SddIntakeDryRun) -> str:
    lines = [
        "kind: codex.sddIntakeTimeline",
        "version: 1",
        f"frame_count: {item.frame_count or 0}",
        f"audio_track_count: {item.audio_track_count or 0}",
        "timeline_ms:",
    ]
    for value in item.timeline_ms:
        lines.append(f"  - {value}")
    lines.extend(
        [
            "references:",
            *[f"  - {reference}" for reference in item.references],
            "retention:",
            f"  hours: {dry_run.retention_hours}",
            "next_actions:",
            "  - Generate visual summaries before relying on image sequence content.",
        ]
    )
    return "\n".join(lines) + "\n"


def _media_next_actions(
    request: SpecIntakeValidationInput,
) -> tuple[str, ...]:
    kinds = {item.kind for item in request.intake_items}
    actions: list[str] = []
    has_audio_without_transcript = any(
        item.kind == "audio" and not (item.transcript or "").strip()
        for item in request.intake_items
    )
    if has_audio_without_transcript or any(
        item.audio_track_count for item in request.intake_items
    ):
        actions.append("Run transcription before relying on audio content.")
    if kinds & {"image", "crop", "marked_region", "screenshot_batch", "image_sequence"}:
        actions.append("Run visual extraction before relying on image content.")
    return tuple(actions)


def _mark_staged_sources_consumed(
    *,
    projects_root: Path,
    workspace_aliases: dict[str, str],
    workspace: Path,
    persisted: tuple[SddIntakePersistedArtifact, ...],
) -> None:
    service = SddMediaUploadService(
        projects_root=projects_root,
        workspace_aliases=workspace_aliases,
    )
    for artifact in persisted:
        source_ref = artifact.source_ref or ""
        if not source_ref.startswith(".codex-bridge/sdd-media/"):
            continue
        service.mark_consumed(
            workspace_path=str(workspace),
            staged_path=source_ref,
            consumed_path=artifact.target_path,
        )


def _write_atomic_bytes(path: Path, content: bytes) -> None:
    if path.exists():
        raise FileExistsError(f"would overwrite existing intake artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temp_path.open("xb") as handle:
            handle.write(content)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _cleanup_created(paths: list[Path]) -> tuple[str, ...]:
    cleaned: list[str] = []
    for path in reversed(paths):
        try:
            if path.is_file():
                path.unlink()
                cleaned.append(path.as_posix())
        except OSError:
            continue
    for path in reversed(paths):
        parent = path.parent
        while parent.name in {"media", "intake"}:
            try:
                parent.rmdir()
                cleaned.append(parent.as_posix())
            except OSError:
                break
            parent = parent.parent
    return tuple(cleaned)


def _trailing_number(path: str) -> int:
    match = re.search(r"-(\d+)\.[^.]+$", path)
    return int(match.group(1)) if match else 0


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
