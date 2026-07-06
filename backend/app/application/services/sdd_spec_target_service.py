from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


TEXT_MAX_BYTES = 64 * 1024
AUDIO_MAX_BYTES = 25 * 1024 * 1024
AUDIO_MAX_DURATION_MS = 10 * 60 * 1000
IMAGE_MAX_BYTES = 10 * 1024 * 1024
SCREENSHOT_BATCH_MAX_IMAGES = 20
IMAGE_SEQUENCE_MAX_FRAMES = 60

ALLOWED_TARGET_MODES = frozenset({"none", "new_spec", "existing_spec"})
ALLOWED_ARTIFACT_TARGETS = frozenset({"auto", "spec", "plan", "tasks", "diagram"})
ALLOWED_MEDIA_KINDS = frozenset(
    {
        "text",
        "audio",
        "image",
        "crop",
        "marked_region",
        "screenshot_batch",
        "image_sequence",
    }
)
ALLOWED_AUDIO_MIME_TYPES = frozenset(
    {"audio/m4a", "audio/mp4", "audio/mpeg", "audio/mp3", "audio/wav", "audio/webm"}
)
ALLOWED_AUDIO_EXTENSIONS = frozenset({".m4a", ".mp3", ".wav", ".webm"})
ALLOWED_IMAGE_MIME_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/jpg", "image/webp"}
)
ALLOWED_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp"})

_SPEC_ID_PATTERN = re.compile(r"^[a-z0-9-]+$")
_URL_LIKE_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_SHA256_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")


@dataclass(frozen=True, slots=True)
class SpecTargetInput:
    mode: str
    spec_id: str | None = None
    artifact: str | None = None


@dataclass(frozen=True, slots=True)
class SpecIntakeMediaItemInput:
    kind: str
    mime_type: str | None = None
    byte_size: int | None = None
    filename: str | None = None
    sha256: str | None = None
    text: str | None = None
    transcript: str | None = None
    duration_ms: int | None = None
    source_ref: str | None = None
    payload_ref: str | None = None
    region: Mapping[str, float] | None = None
    image_count: int | None = None
    frame_count: int | None = None
    audio_track_count: int | None = None
    timeline_ms: tuple[int, ...] = ()
    references: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SpecIntakeValidationInput:
    workspace_path: str
    spec_target: SpecTargetInput
    intake_items: tuple[SpecIntakeMediaItemInput, ...] = ()
    title_seed: str | None = None
    workbench_spec_target: SpecTargetInput | None = None
    bridge_spec_target: SpecTargetInput | None = None


@dataclass(frozen=True, slots=True)
class SpecIntakeValidationError:
    code: str
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class SpecIntakeValidationResult:
    ok: bool
    status: str
    workspace_path: str | None
    mode: str | None
    spec_id: str | None
    artifact: str | None
    spec_root: str | None
    media_count: int
    errors: tuple[SpecIntakeValidationError, ...]
    next_actions: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": "codex.sddSpecIntakeValidation",
            "version": 1,
            "ok": self.ok,
            "status": self.status,
            "workspace_path": self.workspace_path,
            "mode": self.mode,
            "spec_id": self.spec_id,
            "artifact": self.artifact,
            "spec_root": self.spec_root,
            "media_count": self.media_count,
            "errors": [
                {
                    "code": error.code,
                    "field": error.field,
                    "message": error.message,
                }
                for error in self.errors
            ],
            "next_actions": list(self.next_actions),
        }


class SddSpecTargetValidationService:
    def __init__(
        self,
        *,
        projects_root: str | Path,
        workspace_aliases: dict[str, str] | None = None,
    ) -> None:
        self._projects_root = Path(projects_root).expanduser().resolve()
        self._workspace_aliases = {
            key: Path(value).expanduser().resolve()
            for key, value in (workspace_aliases or {}).items()
            if key.strip() and str(value).strip()
        }

    def validate(
        self,
        request: SpecIntakeValidationInput,
    ) -> SpecIntakeValidationResult:
        errors: list[SpecIntakeValidationError] = []
        workspace = self._resolve_workspace(request.workspace_path, errors)
        target = _normalize_target(request.spec_target)

        self._validate_target_conflicts(request, target, errors)
        self._validate_target_semantics(target, workspace, request, errors)
        self._validate_media(request.intake_items, errors)

        spec_root = (
            _spec_root(workspace, target.spec_id)
            if workspace is not None
            and target.spec_id is not None
            and _valid_spec_id(target.spec_id)
            else None
        )
        ok = not errors
        return SpecIntakeValidationResult(
            ok=ok,
            status="valid" if ok else "blocked",
            workspace_path=str(workspace) if workspace else None,
            mode=target.mode if target.mode in ALLOWED_TARGET_MODES else target.mode,
            spec_id=target.spec_id,
            artifact=target.artifact,
            spec_root=str(spec_root) if spec_root else None,
            media_count=len(request.intake_items),
            errors=tuple(errors),
            next_actions=()
            if ok
            else ("Fix validation errors before creating jobs or writing files.",),
        )

    def _resolve_workspace(
        self,
        workspace_path: str,
        errors: list[SpecIntakeValidationError],
    ) -> Path | None:
        raw_path = workspace_path.strip()
        if not raw_path:
            errors.append(
                SpecIntakeValidationError(
                    "missing_workspace",
                    "workspace_path",
                    "workspace_path is required.",
                )
            )
            return None
        alias_path = self._workspace_aliases.get(raw_path)
        candidate = (
            alias_path if alias_path is not None else Path(raw_path).expanduser()
        )
        if not candidate.is_absolute():
            candidate = self._projects_root / candidate
        resolved = candidate.resolve()
        if not self._is_allowed_workspace(resolved):
            errors.append(
                SpecIntakeValidationError(
                    "unsafe_workspace_path",
                    "workspace_path",
                    "workspace_path must resolve under PROJECTS_ROOT or a known alias.",
                )
            )
            return None
        if not resolved.is_dir():
            errors.append(
                SpecIntakeValidationError(
                    "workspace_not_found",
                    "workspace_path",
                    "workspace_path must point to an existing directory.",
                )
            )
            return None
        return resolved

    def _is_allowed_workspace(self, path: Path) -> bool:
        if _is_relative_to(path, self._projects_root):
            return True
        return any(
            path == alias_path for alias_path in self._workspace_aliases.values()
        )

    def _validate_target_conflicts(
        self,
        request: SpecIntakeValidationInput,
        target: SpecTargetInput,
        errors: list[SpecIntakeValidationError],
    ) -> None:
        workbench = (
            _normalize_target(request.workbench_spec_target)
            if request.workbench_spec_target is not None
            else None
        )
        bridge = (
            _normalize_target(request.bridge_spec_target)
            if request.bridge_spec_target is not None
            else None
        )
        for field, candidate in (
            ("workbench_spec_target", workbench),
            ("bridge_spec_target", bridge),
        ):
            if candidate is not None and _target_signature(
                candidate
            ) != _target_signature(target):
                errors.append(
                    SpecIntakeValidationError(
                        "target_conflict",
                        field,
                        "Explicit payload target must match channel target metadata.",
                    )
                )
        if workbench is not None and bridge is not None:
            if _target_signature(workbench) != _target_signature(bridge):
                errors.append(
                    SpecIntakeValidationError(
                        "target_conflict",
                        "spec_target",
                        "Workbench and Bridge targets disagree.",
                    )
                )

    def _validate_target_semantics(
        self,
        target: SpecTargetInput,
        workspace: Path | None,
        request: SpecIntakeValidationInput,
        errors: list[SpecIntakeValidationError],
    ) -> None:
        if target.mode not in ALLOWED_TARGET_MODES:
            errors.append(
                SpecIntakeValidationError(
                    "unsupported_target_mode",
                    "spec_target.mode",
                    f"Unsupported spec_target.mode: {target.mode}",
                )
            )
            return
        if target.artifact not in ALLOWED_ARTIFACT_TARGETS:
            errors.append(
                SpecIntakeValidationError(
                    "unsupported_artifact_target",
                    "spec_target.artifact",
                    f"Unsupported artifact target: {target.artifact}",
                )
            )
        if target.spec_id is not None and not _valid_spec_id(target.spec_id):
            errors.append(
                SpecIntakeValidationError(
                    "invalid_spec_id",
                    "spec_target.spec_id",
                    "spec_id must use lowercase letters, numbers, and hyphens only.",
                )
            )

        if target.mode == "none":
            if target.spec_id is not None:
                errors.append(
                    SpecIntakeValidationError(
                        "invalid_target_combination",
                        "spec_target.spec_id",
                        "spec_target.mode none must not include spec_id.",
                    )
                )
            if target.artifact != "auto":
                errors.append(
                    SpecIntakeValidationError(
                        "invalid_target_combination",
                        "spec_target.artifact",
                        "spec_target.mode none only supports artifact auto.",
                    )
                )
            _validate_intake_presence(request, errors)
            return

        if target.mode == "new_spec":
            if target.artifact != "auto":
                errors.append(
                    SpecIntakeValidationError(
                        "invalid_target_combination",
                        "spec_target.artifact",
                        "spec_target.mode new_spec only supports artifact auto.",
                    )
                )
            if not _has_title_source(request):
                errors.append(
                    SpecIntakeValidationError(
                        "missing_title_source",
                        "title_seed",
                        "new_spec requires title_seed or text/transcript intake.",
                    )
                )
            if (
                workspace is not None
                and target.spec_id is not None
                and _valid_spec_id(target.spec_id)
                and _spec_root(workspace, target.spec_id).exists()
            ):
                errors.append(
                    SpecIntakeValidationError(
                        "spec_slug_collision",
                        "spec_target.spec_id",
                        "Requested spec_id already exists.",
                    )
                )
            _validate_intake_presence(request, errors)
            return

        if target.mode == "existing_spec":
            if target.spec_id is None:
                errors.append(
                    SpecIntakeValidationError(
                        "missing_spec_id",
                        "spec_target.spec_id",
                        "existing_spec requires spec_id.",
                    )
                )
                _validate_intake_presence(request, errors)
                return
            if workspace is None or not _valid_spec_id(target.spec_id):
                _validate_intake_presence(request, errors)
                return
            spec_root = _spec_root(workspace, target.spec_id)
            if not spec_root.is_dir():
                errors.append(
                    SpecIntakeValidationError(
                        "target_spec_not_found",
                        "spec_target.spec_id",
                        "existing_spec must resolve to an existing specs/<spec_id>/ directory.",
                    )
                )
            _validate_intake_presence(request, errors)

    def _validate_media(
        self,
        items: tuple[SpecIntakeMediaItemInput, ...],
        errors: list[SpecIntakeValidationError],
    ) -> None:
        seen_signatures: set[tuple[object, ...]] = set()
        seen_references: set[str] = set()
        for index, item in enumerate(items):
            field = f"intake_items[{index}]"
            self._validate_sha256(item, field, errors)
            signature = _media_signature(item)
            if signature in seen_signatures:
                errors.append(
                    SpecIntakeValidationError(
                        "duplicate_media_item",
                        field,
                        "Duplicate intake item metadata is not allowed.",
                    )
                )
            seen_signatures.add(signature)
            if item.kind not in ALLOWED_MEDIA_KINDS:
                errors.append(
                    SpecIntakeValidationError(
                        "unsupported_media_kind",
                        f"{field}.kind",
                        f"Unsupported intake media kind: {item.kind}",
                    )
                )
                continue
            if item.kind == "text":
                self._validate_text_item(item, field, errors)
            elif item.kind == "audio":
                self._validate_audio_item(item, field, errors)
            elif item.kind in {"image", "crop", "marked_region"}:
                self._validate_image_item(item, field, errors)
            elif item.kind == "screenshot_batch":
                self._validate_screenshot_batch_item(item, field, errors)
            elif item.kind == "image_sequence":
                self._validate_image_sequence_item(item, field, errors)
            self._validate_supported_item_combination(item, field, errors)
            self._validate_source_reference(item, field, seen_references, errors)
            _record_media_references(item, seen_references)

    def _validate_sha256(
        self,
        item: SpecIntakeMediaItemInput,
        field: str,
        errors: list[SpecIntakeValidationError],
    ) -> None:
        if item.sha256 is None:
            return
        if not _SHA256_PATTERN.fullmatch(item.sha256):
            errors.append(
                SpecIntakeValidationError(
                    "invalid_sha256",
                    f"{field}.sha256",
                    "sha256 must be a 64-character hexadecimal digest.",
                )
            )

    def _validate_text_item(
        self,
        item: SpecIntakeMediaItemInput,
        field: str,
        errors: list[SpecIntakeValidationError],
    ) -> None:
        byte_size = _effective_text_byte_size(item)
        if byte_size is None:
            errors.append(
                SpecIntakeValidationError(
                    "missing_media_size",
                    f"{field}.byte_size",
                    "text intake requires text or byte_size metadata.",
                )
            )
            return
        if byte_size > TEXT_MAX_BYTES:
            errors.append(
                SpecIntakeValidationError(
                    "media_text_too_large",
                    f"{field}.byte_size",
                    f"text intake exceeds {TEXT_MAX_BYTES} bytes.",
                )
            )

    def _validate_audio_item(
        self,
        item: SpecIntakeMediaItemInput,
        field: str,
        errors: list[SpecIntakeValidationError],
    ) -> None:
        if not _supported_media_format(
            item,
            allowed_mime_types=ALLOWED_AUDIO_MIME_TYPES,
            allowed_extensions=ALLOWED_AUDIO_EXTENSIONS,
        ):
            errors.append(
                SpecIntakeValidationError(
                    "unsupported_audio_format",
                    f"{field}.mime_type",
                    "audio intake supports m4a, mp3, wav, or webm.",
                )
            )
        self._validate_required_byte_size(item, field, AUDIO_MAX_BYTES, "audio", errors)
        if item.duration_ms is None:
            errors.append(
                SpecIntakeValidationError(
                    "missing_audio_duration",
                    f"{field}.duration_ms",
                    "audio intake requires duration_ms metadata.",
                )
            )
        elif item.duration_ms > AUDIO_MAX_DURATION_MS:
            errors.append(
                SpecIntakeValidationError(
                    "media_audio_duration_too_large",
                    f"{field}.duration_ms",
                    "audio intake exceeds 10 minutes.",
                )
            )

    def _validate_image_item(
        self,
        item: SpecIntakeMediaItemInput,
        field: str,
        errors: list[SpecIntakeValidationError],
    ) -> None:
        if not _supported_media_format(
            item,
            allowed_mime_types=ALLOWED_IMAGE_MIME_TYPES,
            allowed_extensions=ALLOWED_IMAGE_EXTENSIONS,
        ):
            errors.append(
                SpecIntakeValidationError(
                    "unsupported_image_format",
                    f"{field}.mime_type",
                    "image intake supports png, jpg, jpeg, or webp.",
                )
            )
        self._validate_required_byte_size(item, field, IMAGE_MAX_BYTES, "image", errors)
        if item.kind in {"crop", "marked_region"}:
            if not item.source_ref:
                errors.append(
                    SpecIntakeValidationError(
                        "missing_source_ref",
                        f"{field}.source_ref",
                        f"{item.kind} intake requires source_ref.",
                    )
                )
            self._validate_region(item.region, field, errors)

    def _validate_screenshot_batch_item(
        self,
        item: SpecIntakeMediaItemInput,
        field: str,
        errors: list[SpecIntakeValidationError],
    ) -> None:
        if item.image_count is None or item.image_count < 1:
            errors.append(
                SpecIntakeValidationError(
                    "missing_image_count",
                    f"{field}.image_count",
                    "screenshot_batch requires image_count greater than zero.",
                )
            )
            return
        if item.image_count > SCREENSHOT_BATCH_MAX_IMAGES:
            errors.append(
                SpecIntakeValidationError(
                    "media_image_count_too_large",
                    f"{field}.image_count",
                    f"screenshot_batch exceeds {SCREENSHOT_BATCH_MAX_IMAGES} images.",
                )
            )

    def _validate_image_sequence_item(
        self,
        item: SpecIntakeMediaItemInput,
        field: str,
        errors: list[SpecIntakeValidationError],
    ) -> None:
        if item.frame_count is None or item.frame_count < 1:
            errors.append(
                SpecIntakeValidationError(
                    "missing_frame_count",
                    f"{field}.frame_count",
                    "image_sequence requires frame_count greater than zero.",
                )
            )
        elif item.frame_count > IMAGE_SEQUENCE_MAX_FRAMES:
            errors.append(
                SpecIntakeValidationError(
                    "media_frame_count_too_large",
                    f"{field}.frame_count",
                    f"image_sequence exceeds {IMAGE_SEQUENCE_MAX_FRAMES} frames.",
                )
            )
        audio_track_count = item.audio_track_count or 0
        if audio_track_count > 1:
            errors.append(
                SpecIntakeValidationError(
                    "media_audio_track_count_too_large",
                    f"{field}.audio_track_count",
                    "image_sequence supports at most one audio track.",
                )
            )
        if item.timeline_ms:
            if (
                item.frame_count is not None
                and len(item.timeline_ms) != item.frame_count
            ):
                errors.append(
                    SpecIntakeValidationError(
                        "invalid_timeline",
                        f"{field}.timeline_ms",
                        "timeline_ms length must match frame_count.",
                    )
                )
            if tuple(sorted(item.timeline_ms)) != tuple(item.timeline_ms):
                errors.append(
                    SpecIntakeValidationError(
                        "invalid_timeline_order",
                        f"{field}.timeline_ms",
                        "timeline_ms must be in ascending order.",
                    )
                )
            if any(value < 0 for value in item.timeline_ms):
                errors.append(
                    SpecIntakeValidationError(
                        "invalid_timeline",
                        f"{field}.timeline_ms",
                        "timeline_ms values must be greater than or equal to zero.",
                    )
                )

    def _validate_supported_item_combination(
        self,
        item: SpecIntakeMediaItemInput,
        field: str,
        errors: list[SpecIntakeValidationError],
    ) -> None:
        if item.kind == "text" and (
            item.duration_ms is not None
            or item.image_count is not None
            or item.frame_count is not None
            or item.audio_track_count is not None
            or item.region is not None
        ):
            _unsupported_combination(field, "text", errors)
        if item.kind == "audio" and (
            item.image_count is not None
            or item.frame_count is not None
            or item.audio_track_count is not None
            or item.region is not None
        ):
            _unsupported_combination(field, "audio", errors)
        if item.kind == "screenshot_batch" and (
            item.duration_ms is not None
            or item.frame_count is not None
            or item.audio_track_count is not None
            or item.region is not None
        ):
            _unsupported_combination(field, "screenshot_batch", errors)
        if item.kind == "image_sequence" and (
            item.byte_size is not None
            or item.duration_ms is not None
            or item.image_count is not None
            or item.region is not None
            or item.source_ref is not None
        ):
            _unsupported_combination(field, "image_sequence", errors)

    def _validate_source_reference(
        self,
        item: SpecIntakeMediaItemInput,
        field: str,
        seen_references: set[str],
        errors: list[SpecIntakeValidationError],
    ) -> None:
        if item.kind not in {"crop", "marked_region"} or not item.source_ref:
            return
        if item.source_ref not in seen_references:
            errors.append(
                SpecIntakeValidationError(
                    "missing_media_reference",
                    f"{field}.source_ref",
                    "source_ref must reference an earlier image item.",
                )
            )

    def _validate_required_byte_size(
        self,
        item: SpecIntakeMediaItemInput,
        field: str,
        max_bytes: int,
        media_label: str,
        errors: list[SpecIntakeValidationError],
    ) -> None:
        if item.byte_size is None:
            errors.append(
                SpecIntakeValidationError(
                    "missing_media_size",
                    f"{field}.byte_size",
                    f"{media_label} intake requires byte_size metadata.",
                )
            )
            return
        if item.byte_size > max_bytes:
            errors.append(
                SpecIntakeValidationError(
                    f"media_{media_label}_too_large",
                    f"{field}.byte_size",
                    f"{media_label} intake exceeds {max_bytes} bytes.",
                )
            )

    def _validate_region(
        self,
        region: Mapping[str, float] | None,
        field: str,
        errors: list[SpecIntakeValidationError],
    ) -> None:
        if region is None:
            errors.append(
                SpecIntakeValidationError(
                    "missing_region",
                    f"{field}.region",
                    "crop and marked_region intake require region metadata.",
                )
            )
            return
        required_keys = {"x", "y", "width", "height"}
        missing = sorted(required_keys - set(region))
        if missing:
            errors.append(
                SpecIntakeValidationError(
                    "invalid_region",
                    f"{field}.region",
                    f"region is missing required key(s): {', '.join(missing)}.",
                )
            )
            return
        if region["width"] <= 0 or region["height"] <= 0:
            errors.append(
                SpecIntakeValidationError(
                    "invalid_region",
                    f"{field}.region",
                    "region width and height must be greater than zero.",
                )
            )
        if region["x"] < 0 or region["y"] < 0:
            errors.append(
                SpecIntakeValidationError(
                    "invalid_region",
                    f"{field}.region",
                    "region x and y must be greater than or equal to zero.",
                )
            )


def _normalize_target(target: SpecTargetInput) -> SpecTargetInput:
    spec_id = target.spec_id.strip() if target.spec_id is not None else None
    return SpecTargetInput(
        mode=target.mode.strip(),
        spec_id=spec_id or None,
        artifact=(target.artifact or "auto").strip(),
    )


def _target_signature(target: SpecTargetInput) -> tuple[str, str | None, str]:
    normalized = _normalize_target(target)
    return (normalized.mode, normalized.spec_id, normalized.artifact)


def _valid_spec_id(spec_id: str) -> bool:
    if not spec_id or spec_id in {".", ".."}:
        return False
    if "/" in spec_id or "\\" in spec_id or "." in spec_id:
        return False
    if _URL_LIKE_PATTERN.search(spec_id):
        return False
    return bool(_SPEC_ID_PATTERN.fullmatch(spec_id))


def _spec_root(workspace: Path, spec_id: str | None) -> Path | None:
    if spec_id is None:
        return None
    return (workspace / "specs" / spec_id).resolve()


def _has_title_source(request: SpecIntakeValidationInput) -> bool:
    if request.title_seed and request.title_seed.strip():
        return True
    return any(
        (item.text and item.text.strip())
        or (item.transcript and item.transcript.strip())
        for item in request.intake_items
    )


def _validate_intake_presence(
    request: SpecIntakeValidationInput,
    errors: list[SpecIntakeValidationError],
) -> None:
    if request.intake_items:
        return
    errors.append(
        SpecIntakeValidationError(
            "missing_intake",
            "intake_items",
            "At least one intake item is required.",
        )
    )


def _effective_text_byte_size(item: SpecIntakeMediaItemInput) -> int | None:
    if item.text is not None:
        return len(item.text.encode("utf-8"))
    return item.byte_size


def _unsupported_combination(
    field: str,
    kind: str,
    errors: list[SpecIntakeValidationError],
) -> None:
    errors.append(
        SpecIntakeValidationError(
            "unsupported_item_combination",
            field,
            f"{kind} intake includes metadata fields that belong to another media kind.",
        )
    )


def _media_signature(item: SpecIntakeMediaItemInput) -> tuple[object, ...]:
    return (
        item.kind,
        item.mime_type,
        item.byte_size,
        item.filename,
        item.sha256,
        item.text,
        item.transcript,
        item.duration_ms,
        item.source_ref,
        item.payload_ref,
        tuple(sorted((item.region or {}).items())),
        item.image_count,
        item.frame_count,
        item.audio_track_count,
        tuple(item.timeline_ms),
        tuple(item.references),
    )


def _record_media_references(
    item: SpecIntakeMediaItemInput,
    seen_references: set[str],
) -> None:
    for reference in item.references:
        if reference:
            seen_references.add(reference)
    if item.filename:
        seen_references.add(item.filename)
        seen_references.add(f"media/{item.filename}")
    if item.payload_ref:
        seen_references.add(item.payload_ref)
    if item.sha256:
        seen_references.add(item.sha256)


def _supported_media_format(
    item: SpecIntakeMediaItemInput,
    *,
    allowed_mime_types: frozenset[str],
    allowed_extensions: frozenset[str],
) -> bool:
    if item.mime_type and item.mime_type.lower() in allowed_mime_types:
        return True
    if item.filename and Path(item.filename).suffix.lower() in allowed_extensions:
        return True
    return False


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
