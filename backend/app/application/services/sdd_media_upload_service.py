from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend.app.application.services.sdd_spec_target_service import (
    ALLOWED_AUDIO_EXTENSIONS,
    ALLOWED_AUDIO_MIME_TYPES,
    AUDIO_MAX_BYTES,
    AUDIO_MAX_DURATION_MS,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_IMAGE_MIME_TYPES,
    IMAGE_MAX_BYTES,
)


DEFAULT_STAGED_RETENTION_HOURS = 24


@dataclass(frozen=True, slots=True)
class SddMediaUploadResult:
    status: str
    workspace_path: str
    intake_item: dict[str, object] | None
    staged_path: str | None
    metadata_path: str | None
    blocked: tuple[str, ...]
    cleanup: tuple[str, ...]
    next_actions: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": "codex.sddMediaUpload",
            "version": 1,
            "status": self.status,
            "workspace_path": self.workspace_path,
            "intake_item": self.intake_item,
            "staged_path": self.staged_path,
            "metadata_path": self.metadata_path,
            "blocked": list(self.blocked),
            "cleanup": list(self.cleanup),
            "next_actions": list(self.next_actions),
        }


@dataclass(frozen=True, slots=True)
class SddMediaLifecycleResult:
    status: str
    workspace_path: str
    staged_path: str | None
    lifecycle: str
    deleted: tuple[str, ...]
    would_delete: tuple[str, ...]
    blocked: tuple[str, ...]
    cleanup: tuple[str, ...]
    next_actions: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": "codex.sddMediaLifecycle",
            "version": 1,
            "status": self.status,
            "workspace_path": self.workspace_path,
            "staged_path": self.staged_path,
            "lifecycle": self.lifecycle,
            "deleted": list(self.deleted),
            "would_delete": list(self.would_delete),
            "blocked": list(self.blocked),
            "cleanup": list(self.cleanup),
            "next_actions": list(self.next_actions),
        }


class SddMediaUploadService:
    def __init__(
        self,
        *,
        projects_root: str | Path,
        workspace_aliases: dict[str, str] | None = None,
        staging_root: str = ".codex-bridge/sdd-media",
    ) -> None:
        self._projects_root = Path(projects_root).expanduser().resolve()
        self._workspace_aliases = {
            key: Path(value).expanduser().resolve()
            for key, value in (workspace_aliases or {}).items()
            if key.strip() and str(value).strip()
        }
        self._staging_root = staging_root

    def stage_media(
        self,
        *,
        workspace_path: str,
        kind: str,
        filename: str,
        mime_type: str | None,
        content: bytes,
        sha256: str | None = None,
        duration_ms: int | None = None,
        source_ref: str | None = None,
        region: dict[str, object] | None = None,
    ) -> SddMediaUploadResult:
        if kind == "image":
            return self.stage_image(
                workspace_path=workspace_path,
                filename=filename,
                mime_type=mime_type,
                content=content,
                sha256=sha256,
            )
        if kind == "audio":
            return self.stage_audio(
                workspace_path=workspace_path,
                filename=filename,
                mime_type=mime_type,
                content=content,
                sha256=sha256,
                duration_ms=duration_ms,
            )
        if kind == "crop":
            return self.stage_crop(
                workspace_path=workspace_path,
                filename=filename,
                mime_type=mime_type,
                content=content,
                sha256=sha256,
                source_ref=source_ref,
                region=region,
            )
        return SddMediaUploadResult(
            status="blocked",
            workspace_path=workspace_path,
            intake_item=None,
            staged_path=None,
            metadata_path=None,
            blocked=(f"unsupported media upload kind: {kind}",),
            cleanup=(),
            next_actions=(
                "Use image, crop, or audio upload for this Workbench slice.",
            ),
        )

    def stage_image(
        self,
        *,
        workspace_path: str,
        filename: str,
        mime_type: str | None,
        content: bytes,
        sha256: str | None = None,
    ) -> SddMediaUploadResult:
        try:
            workspace = self._validate_workspace(workspace_path)
        except ValueError as exc:
            return SddMediaUploadResult(
                status="blocked",
                workspace_path=workspace_path,
                intake_item=None,
                staged_path=None,
                metadata_path=None,
                blocked=(str(exc),),
                cleanup=(),
                next_actions=("Fix media upload blockers and retry.",),
            )
        blockers = _image_blockers(
            filename=filename,
            mime_type=mime_type,
            content=content,
            sha256=sha256,
        )
        if blockers:
            return _blocked_result(workspace, blockers)

        staged = _stage_binary(
            workspace=workspace,
            staging_root=self._staging_root,
            media_kind="image",
            filename=filename,
            mime_type=mime_type,
            content=content,
        )
        if staged.status != "staged":
            return staged
        return SddMediaUploadResult(
            status=staged.status,
            workspace_path=staged.workspace_path,
            intake_item=staged.intake_item,
            staged_path=staged.staged_path,
            metadata_path=staged.metadata_path,
            blocked=staged.blocked,
            cleanup=staged.cleanup,
            next_actions=("Run visual extraction before relying on image content.",),
        )

    def stage_crop(
        self,
        *,
        workspace_path: str,
        filename: str,
        mime_type: str | None,
        content: bytes,
        sha256: str | None = None,
        source_ref: str | None = None,
        region: dict[str, object] | None = None,
    ) -> SddMediaUploadResult:
        try:
            workspace = self._validate_workspace(workspace_path)
            self._validate_crop_parent(workspace, source_ref)
        except ValueError as exc:
            return SddMediaUploadResult(
                status="blocked",
                workspace_path=workspace_path,
                intake_item=None,
                staged_path=None,
                metadata_path=None,
                blocked=(str(exc),),
                cleanup=(),
                next_actions=("Fix crop source metadata and retry.",),
            )
        blockers = (
            *_image_blockers(
                filename=filename,
                mime_type=mime_type,
                content=content,
                sha256=sha256,
            ),
            *_region_blockers(region),
        )
        if blockers:
            return _blocked_result(workspace, tuple(blockers))

        assert source_ref is not None
        assert region is not None
        staged = _stage_binary(
            workspace=workspace,
            staging_root=self._staging_root,
            media_kind="crop",
            filename=filename,
            mime_type=mime_type,
            content=content,
            extra_metadata={
                "source_ref": source_ref,
                "region": _normalized_region(region),
            },
        )
        if staged.status != "staged":
            return staged
        assert staged.intake_item is not None
        staged.intake_item["source_ref"] = source_ref
        staged.intake_item["region"] = _normalized_region(region)
        return SddMediaUploadResult(
            status=staged.status,
            workspace_path=staged.workspace_path,
            intake_item=staged.intake_item,
            staged_path=staged.staged_path,
            metadata_path=staged.metadata_path,
            blocked=staged.blocked,
            cleanup=staged.cleanup,
            next_actions=("Crop image staged with source region metadata.",),
        )

    def stage_audio(
        self,
        *,
        workspace_path: str,
        filename: str,
        mime_type: str | None,
        content: bytes,
        sha256: str | None = None,
        duration_ms: int | None = None,
    ) -> SddMediaUploadResult:
        try:
            workspace = self._validate_workspace(workspace_path)
        except ValueError as exc:
            return SddMediaUploadResult(
                status="blocked",
                workspace_path=workspace_path,
                intake_item=None,
                staged_path=None,
                metadata_path=None,
                blocked=(str(exc),),
                cleanup=(),
                next_actions=("Fix media upload blockers and retry.",),
            )
        blockers = _audio_blockers(
            filename=filename,
            mime_type=mime_type,
            content=content,
            sha256=sha256,
            duration_ms=duration_ms,
        )
        if blockers:
            return _blocked_result(workspace, blockers)
        assert duration_ms is not None

        staged = _stage_binary(
            workspace=workspace,
            staging_root=self._staging_root,
            media_kind="audio",
            filename=filename,
            mime_type=mime_type,
            content=content,
            extra_metadata={"duration_ms": duration_ms},
        )
        if staged.status != "staged":
            return staged
        assert staged.intake_item is not None
        staged.intake_item["duration_ms"] = duration_ms
        return SddMediaUploadResult(
            status=staged.status,
            workspace_path=staged.workspace_path,
            intake_item=staged.intake_item,
            staged_path=staged.staged_path,
            metadata_path=staged.metadata_path,
            blocked=staged.blocked,
            cleanup=staged.cleanup,
            next_actions=("Run transcription before relying on audio content.",),
        )

    def delete_staged_media(
        self,
        *,
        workspace_path: str,
        staged_path: str,
    ) -> SddMediaLifecycleResult:
        try:
            workspace = self._validate_workspace(workspace_path)
            target, metadata_path = self._resolve_staged_pair(workspace, staged_path)
            metadata = _read_metadata(metadata_path)
        except Exception as exc:
            return SddMediaLifecycleResult(
                status="blocked",
                workspace_path=workspace_path,
                staged_path=staged_path,
                lifecycle="unknown",
                deleted=(),
                would_delete=(),
                blocked=(str(exc),),
                cleanup=(),
                next_actions=("Fix staged media reference before deleting.",),
            )
        lifecycle = str(metadata.get("lifecycle", "staged"))
        if lifecycle == "consumed":
            return SddMediaLifecycleResult(
                status="blocked",
                workspace_path=str(workspace),
                staged_path=staged_path,
                lifecycle=lifecycle,
                deleted=(),
                would_delete=(),
                blocked=(
                    "staged media has already been consumed by apply/job handoff.",
                ),
                cleanup=(),
                next_actions=("Remove the persisted spec intake artifact explicitly.",),
            )
        deleted: list[str] = []
        cleanup: list[str] = []
        for path in (target, metadata_path):
            try:
                if path.is_file():
                    path.unlink()
                    deleted.append(path.relative_to(workspace).as_posix())
            except OSError as exc:
                cleanup.extend(_cleanup_created([path]))
                return SddMediaLifecycleResult(
                    status="blocked",
                    workspace_path=str(workspace),
                    staged_path=staged_path,
                    lifecycle=lifecycle,
                    deleted=tuple(deleted),
                    would_delete=(),
                    blocked=(str(exc),),
                    cleanup=tuple(cleanup),
                    next_actions=(
                        "Retry deletion or inspect staged media permissions.",
                    ),
                )
        return SddMediaLifecycleResult(
            status="deleted",
            workspace_path=str(workspace),
            staged_path=staged_path,
            lifecycle="deleted",
            deleted=tuple(deleted),
            would_delete=(),
            blocked=(),
            cleanup=(),
            next_actions=(),
        )

    def cleanup_staged_media(
        self,
        *,
        workspace_path: str,
        dry_run: bool = True,
        older_than_hours: int = DEFAULT_STAGED_RETENTION_HOURS,
    ) -> SddMediaLifecycleResult:
        try:
            workspace = self._validate_workspace(workspace_path)
        except ValueError as exc:
            return SddMediaLifecycleResult(
                status="blocked",
                workspace_path=workspace_path,
                staged_path=None,
                lifecycle="unknown",
                deleted=(),
                would_delete=(),
                blocked=(str(exc),),
                cleanup=(),
                next_actions=("Fix workspace_path before cleanup.",),
            )
        root = (workspace / self._staging_root).resolve()
        if not _is_relative_to(root, workspace):
            return SddMediaLifecycleResult(
                status="blocked",
                workspace_path=str(workspace),
                staged_path=None,
                lifecycle="unknown",
                deleted=(),
                would_delete=(),
                blocked=("staging root escapes workspace.",),
                cleanup=(),
                next_actions=("Fix media staging configuration.",),
            )
        if not root.exists():
            return SddMediaLifecycleResult(
                status="dry-run" if dry_run else "applied",
                workspace_path=str(workspace),
                staged_path=None,
                lifecycle="cleanup-eligible",
                deleted=(),
                would_delete=(),
                blocked=(),
                cleanup=(),
                next_actions=(),
            )
        cutoff = datetime.now(UTC) - timedelta(hours=older_than_hours)
        eligible: list[tuple[Path, Path]] = []
        blocked: list[str] = []
        for metadata_path in sorted(root.glob("*.json")):
            try:
                metadata = _read_metadata(metadata_path)
                if metadata.get("lifecycle", "staged") == "consumed":
                    continue
                if not _metadata_is_expired(metadata, cutoff):
                    continue
                staged = metadata_path.with_suffix("")
                self._resolve_staged_pair(
                    workspace, staged.relative_to(workspace).as_posix()
                )
                eligible.append((staged, metadata_path))
            except Exception as exc:
                blocked.append(str(exc))
        would_delete = tuple(
            path.relative_to(workspace).as_posix()
            for pair in eligible
            for path in pair
            if path.exists()
        )
        if dry_run:
            return SddMediaLifecycleResult(
                status="dry-run" if not blocked else "blocked",
                workspace_path=str(workspace),
                staged_path=None,
                lifecycle="cleanup-eligible",
                deleted=(),
                would_delete=would_delete,
                blocked=tuple(blocked),
                cleanup=(),
                next_actions=()
                if not would_delete
                else ("Run cleanup with apply=true to delete eligible staged media.",),
            )
        deleted: list[str] = []
        for staged, metadata_path in eligible:
            for path in (staged, metadata_path):
                if path.is_file():
                    path.unlink()
                    deleted.append(path.relative_to(workspace).as_posix())
        return SddMediaLifecycleResult(
            status="applied" if not blocked else "blocked",
            workspace_path=str(workspace),
            staged_path=None,
            lifecycle="cleanup-eligible",
            deleted=tuple(deleted),
            would_delete=(),
            blocked=tuple(blocked),
            cleanup=(),
            next_actions=(),
        )

    def mark_consumed(
        self,
        *,
        workspace_path: str,
        staged_path: str,
        consumed_path: str,
    ) -> SddMediaLifecycleResult:
        try:
            workspace = self._validate_workspace(workspace_path)
            _target, metadata_path = self._resolve_staged_pair(workspace, staged_path)
            metadata = _read_metadata(metadata_path)
            metadata["lifecycle"] = "consumed"
            metadata["consumed_path"] = consumed_path
            metadata["consumed_at"] = _now_iso()
            _write_replace_bytes(
                metadata_path,
                json.dumps(metadata, indent=2, sort_keys=True).encode() + b"\n",
            )
        except Exception as exc:
            return SddMediaLifecycleResult(
                status="blocked",
                workspace_path=workspace_path,
                staged_path=staged_path,
                lifecycle="unknown",
                deleted=(),
                would_delete=(),
                blocked=(str(exc),),
                cleanup=(),
                next_actions=("Inspect staged media lifecycle metadata.",),
            )
        return SddMediaLifecycleResult(
            status="consumed",
            workspace_path=str(workspace),
            staged_path=staged_path,
            lifecycle="consumed",
            deleted=(),
            would_delete=(),
            blocked=(),
            cleanup=(),
            next_actions=(),
        )

    def _resolve_staged_pair(
        self, workspace: Path, staged_path: str
    ) -> tuple[Path, Path]:
        relative = Path(staged_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe staged media path.")
        if not relative.as_posix().startswith(self._staging_root.rstrip("/") + "/"):
            raise ValueError("staged media path is outside the staging root.")
        target = (workspace / relative).resolve()
        if not _is_relative_to(target, workspace):
            raise ValueError("staged media path escapes workspace.")
        metadata_path = target.with_suffix(target.suffix + ".json")
        if not target.is_file():
            raise ValueError("staged media file does not exist.")
        if not metadata_path.is_file():
            raise ValueError("staged media metadata sidecar does not exist.")
        return target, metadata_path

    def _validate_crop_parent(self, workspace: Path, source_ref: str | None) -> None:
        if not source_ref or not source_ref.strip():
            raise ValueError("crop source_ref is required.")
        _target, metadata_path = self._resolve_staged_pair(workspace, source_ref)
        metadata = _read_metadata(metadata_path)
        if metadata.get("lifecycle") == "deleted":
            raise ValueError("crop source media has been deleted.")
        if metadata.get("media_kind") != "image":
            raise ValueError("crop source_ref must reference a staged image.")

    def _validate_workspace(self, workspace_path: str) -> Path:
        raw = workspace_path.strip()
        if not raw:
            raise ValueError("workspace_path is required.")
        alias_path = self._workspace_aliases.get(raw)
        candidate = alias_path if alias_path is not None else Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = self._projects_root / candidate
        resolved = candidate.resolve()
        if not _is_relative_to(resolved, self._projects_root) and not any(
            resolved == alias for alias in self._workspace_aliases.values()
        ):
            raise ValueError(
                "workspace_path must resolve under PROJECTS_ROOT or a known alias."
            )
        if not resolved.is_dir():
            raise ValueError("workspace_path must point to a directory.")
        return resolved


def _image_blockers(
    *,
    filename: str,
    mime_type: str | None,
    content: bytes,
    sha256: str | None,
) -> tuple[str, ...]:
    blockers: list[str] = []
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        blockers.append("unsupported_image_extension")
    if (mime_type or "").lower() not in ALLOWED_IMAGE_MIME_TYPES:
        blockers.append("unsupported_image_mime_type")
    if len(content) > IMAGE_MAX_BYTES:
        blockers.append(f"image exceeds {IMAGE_MAX_BYTES} bytes")
    if sha256 is not None:
        if not re.fullmatch(r"[a-fA-F0-9]{64}", sha256):
            blockers.append("invalid_sha256")
        elif hashlib.sha256(content).hexdigest().lower() != sha256.lower():
            blockers.append("sha256 mismatch")
    return tuple(blockers)


def _audio_blockers(
    *,
    filename: str,
    mime_type: str | None,
    content: bytes,
    sha256: str | None,
    duration_ms: int | None,
) -> tuple[str, ...]:
    blockers: list[str] = []
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_AUDIO_EXTENSIONS:
        blockers.append("unsupported_audio_extension")
    if (mime_type or "").lower() not in ALLOWED_AUDIO_MIME_TYPES:
        blockers.append("unsupported_audio_mime_type")
    if len(content) > AUDIO_MAX_BYTES:
        blockers.append(f"audio exceeds {AUDIO_MAX_BYTES} bytes")
    if duration_ms is None:
        blockers.append("missing_audio_duration")
    elif duration_ms > AUDIO_MAX_DURATION_MS:
        blockers.append("audio duration exceeds 10 minutes")
    if sha256 is not None:
        if not re.fullmatch(r"[a-fA-F0-9]{64}", sha256):
            blockers.append("invalid_sha256")
        elif hashlib.sha256(content).hexdigest().lower() != sha256.lower():
            blockers.append("sha256 mismatch")
    return tuple(blockers)


def _region_blockers(region: dict[str, object] | None) -> tuple[str, ...]:
    if region is None:
        return ("missing_crop_region",)
    blockers: list[str] = []
    for key in ("x", "y", "width", "height"):
        value = region.get(key)
        if not isinstance(value, (int, float)):
            blockers.append(f"invalid_crop_region_{key}")
            continue
        if key in {"x", "y"} and value < 0:
            blockers.append(f"invalid_crop_region_{key}")
        if key in {"width", "height"} and value <= 0:
            blockers.append(f"invalid_crop_region_{key}")
    return tuple(blockers)


def _normalized_region(region: dict[str, object]) -> dict[str, int | float]:
    return {
        key: region[key]
        for key in ("x", "y", "width", "height")
        if isinstance(region.get(key), (int, float))
    }


def _safe_filename(filename: str) -> str:
    name = Path(filename or "image.png").name
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip(".-")
    return cleaned or "image.png"


def _validate_target_path(workspace: Path, target: Path) -> None:
    resolved = target.resolve()
    if not _is_relative_to(resolved, workspace):
        raise ValueError("staged media path escapes workspace.")
    if resolved.exists():
        raise FileExistsError(
            f"would overwrite existing staged media: {resolved.relative_to(workspace)}"
        )


def _stage_binary(
    *,
    workspace: Path,
    staging_root: str,
    media_kind: str,
    filename: str,
    mime_type: str | None,
    content: bytes,
    extra_metadata: dict[str, object] | None = None,
) -> SddMediaUploadResult:
    digest = hashlib.sha256(content).hexdigest()
    safe_name = _safe_filename(filename)
    target = workspace / staging_root / f"{digest[:16]}-{safe_name}"
    metadata_path = target.with_suffix(target.suffix + ".json")
    created: list[Path] = []
    try:
        _validate_target_path(workspace, target)
        _validate_target_path(workspace, metadata_path)
        _write_atomic_bytes(target, content)
        created.append(target)
        metadata = {
            "kind": "codex.sddMediaUpload",
            "version": 1,
            "lifecycle": "staged",
            "media_kind": media_kind,
            "filename": filename,
            "mime_type": mime_type,
            "byte_size": len(content),
            "sha256": digest,
            "staged_path": target.relative_to(workspace).as_posix(),
            "created_at": _now_iso(),
            "retention": {
                "policy": "staged media eligible for cleanup after intake apply",
                "hours": DEFAULT_STAGED_RETENTION_HOURS,
            },
            **(extra_metadata or {}),
        }
        _write_atomic_bytes(
            metadata_path,
            json.dumps(metadata, indent=2, sort_keys=True).encode() + b"\n",
        )
        created.append(metadata_path)
    except Exception as exc:
        cleanup = _cleanup_created(created)
        return SddMediaUploadResult(
            status="blocked",
            workspace_path=str(workspace),
            intake_item=None,
            staged_path=None,
            metadata_path=None,
            blocked=(str(exc),),
            cleanup=cleanup,
            next_actions=("Fix media upload blockers and retry.",),
        )

    staged_relative = target.relative_to(workspace).as_posix()
    metadata_relative = metadata_path.relative_to(workspace).as_posix()
    return SddMediaUploadResult(
        status="staged",
        workspace_path=str(workspace),
        intake_item={
            "kind": media_kind,
            "mime_type": mime_type,
            "byte_size": len(content),
            "filename": filename,
            "sha256": digest,
            "payload_ref": staged_relative,
        },
        staged_path=staged_relative,
        metadata_path=metadata_relative,
        blocked=(),
        cleanup=(),
        next_actions=(),
    )


def _write_atomic_bytes(path: Path, content: bytes) -> None:
    if path.exists():
        raise FileExistsError(f"would overwrite existing staged media: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temp_path.open("xb") as handle:
            handle.write(content)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _write_replace_bytes(path: Path, content: bytes) -> None:
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
    return tuple(cleaned)


def _blocked_result(
    workspace: Path,
    blockers: tuple[str, ...],
) -> SddMediaUploadResult:
    return SddMediaUploadResult(
        status="blocked",
        workspace_path=str(workspace),
        intake_item=None,
        staged_path=None,
        metadata_path=None,
        blocked=blockers,
        cleanup=(),
        next_actions=("Fix media upload blockers and retry.",),
    )


def _read_metadata(metadata_path: Path) -> dict[str, object]:
    payload = json.loads(metadata_path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("staged media metadata is malformed.")
    return payload


def _metadata_is_expired(metadata: dict[str, object], cutoff: datetime) -> bool:
    value = metadata.get("created_at")
    if not isinstance(value, str):
        return True
    try:
        created_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return True
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return created_at <= cutoff


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
