from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from uuid import uuid4

from backend.app.application.services.sdd_spec_target_service import (
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_IMAGE_MIME_TYPES,
    IMAGE_MAX_BYTES,
)


@dataclass(frozen=True, slots=True)
class ProjectFactoryReferenceAsset:
    id: str
    draft_id: str
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: str
    storage_path: str

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "draft_id": self.draft_id,
            "original_filename": self.original_filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at,
            "storage_path": self.storage_path,
        }

    def to_manifest_item(self) -> dict[str, object]:
        return {
            "id": self.id,
            "original_filename": self.original_filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at,
            "storage_path": self.storage_path,
        }


class ProjectFactoryReferenceAssetError(ValueError):
    pass


class ProjectFactoryReferenceAssetService:
    def __init__(
        self,
        *,
        storage_root: str | Path,
        max_image_bytes: int = IMAGE_MAX_BYTES,
    ) -> None:
        self._storage_root = Path(storage_root).expanduser().resolve()
        self._max_image_bytes = max_image_bytes
        self._lock = RLock()
        self._storage_root.mkdir(parents=True, exist_ok=True)

    def create_asset(
        self,
        *,
        draft_id: str,
        filename: str,
        content_type: str | None,
        content: bytes,
    ) -> ProjectFactoryReferenceAsset:
        _validate_draft_id(draft_id)
        original_filename = _safe_original_filename(filename)
        normalized_content_type = _normalize_content_type(content_type)
        _validate_image(
            filename=original_filename,
            content_type=normalized_content_type,
            content=content,
            max_image_bytes=self._max_image_bytes,
        )
        asset_id = "pf-asset-" + uuid4().hex[:12]
        suffix = Path(original_filename).suffix.lower()
        asset = ProjectFactoryReferenceAsset(
            id=asset_id,
            draft_id=draft_id,
            original_filename=original_filename,
            content_type=normalized_content_type,
            size_bytes=len(content),
            created_at=_now_iso(),
            storage_path=f"{draft_id}/{asset_id}{suffix}",
        )
        with self._lock:
            draft_dir = self._draft_dir(draft_id)
            draft_dir.mkdir(parents=True, exist_ok=True)
            asset_path = self._asset_path(asset)
            metadata_path = self._metadata_path(draft_id, asset_id)
            _atomic_write_bytes(asset_path, content)
            _atomic_write_json(metadata_path, asset.to_payload())
        return asset

    def list_assets(self, draft_id: str) -> tuple[ProjectFactoryReferenceAsset, ...]:
        _validate_draft_id(draft_id)
        with self._lock:
            draft_dir = self._draft_dir(draft_id)
            if not draft_dir.is_dir():
                return ()
            assets: list[ProjectFactoryReferenceAsset] = []
            for metadata_path in sorted(draft_dir.glob("*.json")):
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
                assets.append(_asset_from_payload(payload))
            return tuple(assets)

    def delete_asset(self, *, draft_id: str, asset_id: str) -> bool:
        _validate_draft_id(draft_id)
        _validate_asset_id(asset_id)
        with self._lock:
            metadata_path = self._metadata_path(draft_id, asset_id)
            if not metadata_path.is_file():
                return False
            asset = _asset_from_payload(
                json.loads(metadata_path.read_text(encoding="utf-8"))
            )
            asset_path = self._asset_path(asset)
            metadata_path.unlink(missing_ok=True)
            asset_path.unlink(missing_ok=True)
            return True

    def copy_assets_to_project(
        self,
        *,
        assets: tuple[ProjectFactoryReferenceAsset, ...],
        target_project: Path,
    ) -> tuple[str, ...]:
        copied: list[str] = []
        if not assets:
            return ()
        images_dir = target_project / "references" / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            for asset in assets:
                source = self._asset_path(asset)
                if not source.is_file():
                    raise ProjectFactoryReferenceAssetError(
                        f"Reference asset file is missing: {asset.id}"
                    )
                destination_name = f"{asset.id}-{_slug_filename(asset.original_filename)}"
                destination = images_dir / destination_name
                shutil.copyfile(source, destination)
                copied.append(str(destination.relative_to(target_project)))
        index_path = target_project / "references" / "reference-assets.md"
        index_path.write_text(_reference_index(assets, copied), encoding="utf-8")
        copied.append(str(index_path.relative_to(target_project)))
        return tuple(copied)

    def _draft_dir(self, draft_id: str) -> Path:
        return self._storage_root / draft_id

    def _metadata_path(self, draft_id: str, asset_id: str) -> Path:
        return self._draft_dir(draft_id) / f"{asset_id}.json"

    def _asset_path(self, asset: ProjectFactoryReferenceAsset) -> Path:
        path = (self._storage_root / asset.storage_path).resolve()
        if not _is_relative_to(path, self._storage_root):
            raise ProjectFactoryReferenceAssetError("Unsafe reference asset path.")
        return path


def _validate_image(
    *,
    filename: str,
    content_type: str,
    content: bytes,
    max_image_bytes: int,
) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        raise ProjectFactoryReferenceAssetError(
            "Reference images must use png, jpg, jpeg, or webp files."
        )
    if content_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise ProjectFactoryReferenceAssetError(
            "Reference image content type is not supported."
        )
    if not content:
        raise ProjectFactoryReferenceAssetError("Reference image cannot be empty.")
    if len(content) > max_image_bytes:
        raise ProjectFactoryReferenceAssetError(
            f"Reference image exceeds the {max_image_bytes} byte limit."
        )


def _safe_original_filename(filename: str) -> str:
    cleaned = filename.strip()
    if not cleaned:
        raise ProjectFactoryReferenceAssetError("Reference image filename is required.")
    normalized = cleaned.replace("\\", "/")
    if "/" in normalized or normalized in {".", ".."}:
        raise ProjectFactoryReferenceAssetError(
            "Reference image filename must not contain path separators."
        )
    if not re.fullmatch(r"[A-Za-z0-9._ -]{1,160}", normalized):
        raise ProjectFactoryReferenceAssetError(
            "Reference image filename contains unsupported characters."
        )
    return normalized


def _normalize_content_type(content_type: str | None) -> str:
    normalized = (content_type or "").split(";", maxsplit=1)[0].strip().lower()
    if not normalized:
        raise ProjectFactoryReferenceAssetError(
            "Reference image content type is required."
        )
    return normalized


def _asset_from_payload(payload: dict[str, object]) -> ProjectFactoryReferenceAsset:
    return ProjectFactoryReferenceAsset(
        id=str(payload["id"]),
        draft_id=str(payload["draft_id"]),
        original_filename=str(payload["original_filename"]),
        content_type=str(payload["content_type"]),
        size_bytes=int(payload["size_bytes"]),
        created_at=str(payload["created_at"]),
        storage_path=str(payload["storage_path"]),
    )


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temp_path, path)


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temp_path.write_bytes(content)
    os.replace(temp_path, path)


def _reference_index(
    assets: tuple[ProjectFactoryReferenceAsset, ...],
    copied_paths: list[str],
) -> str:
    lines = [
        "# Reference Assets",
        "",
        "These images were uploaded during Project Factory draft creation and should be used as visual context, not copied blindly.",
        "",
    ]
    for asset, copied_path in zip(assets, copied_paths, strict=False):
        lines.extend(
            [
                f"## {asset.original_filename}",
                "",
                f"- id: `{asset.id}`",
                f"- content type: `{asset.content_type}`",
                f"- size bytes: {asset.size_bytes}",
                f"- created at: `{asset.created_at}`",
                f"- copied path: `{copied_path}`",
                f"- bridge storage path: `{asset.storage_path}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _slug_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    stem = Path(filename).stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", stem).strip("-") or "reference"
    return f"{slug}{suffix}"


def _validate_draft_id(draft_id: str) -> None:
    if not re.fullmatch(r"pf-draft-[a-f0-9]{12}", draft_id):
        raise ProjectFactoryReferenceAssetError("Invalid project factory draft id.")


def _validate_asset_id(asset_id: str) -> None:
    if not re.fullmatch(r"pf-asset-[a-f0-9]{12}", asset_id):
        raise ProjectFactoryReferenceAssetError("Invalid project factory asset id.")


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
