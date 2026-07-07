from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
from threading import RLock
from uuid import uuid4


ALLOWED_ASSET_ROLES = frozenset(
    {"visual_reference", "exact_asset", "app_icon", "logo", "document_context"}
)

_ALLOWED_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".svg",
        ".pdf",
        ".txt",
        ".md",
        ".json",
        ".csv",
        ".docx",
    }
)
_ALLOWED_MIME_PREFIXES = ("image/", "text/")
_ALLOWED_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "application/json",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/csv",
    }
)


@dataclass(frozen=True, slots=True)
class AssetDepotItem:
    id: str
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    created_at: str
    storage_path: str
    source: str

    def to_payload(self) -> dict[str, object]:
        return {
            "asset_id": self.id,
            "id": self.id,
            "original_filename": self.original_filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "created_at": self.created_at,
            "storage_path": self.storage_path,
            "source": self.source,
        }


class AssetDepotError(ValueError):
    pass


class AssetDepotService:
    def __init__(
        self,
        *,
        storage_root: str | Path,
        max_upload_bytes: int,
    ) -> None:
        self._storage_root = Path(storage_root).expanduser().resolve()
        self._files_root = self._storage_root / "files"
        self._metadata_root = self._storage_root / "metadata"
        self._max_upload_bytes = max_upload_bytes
        self._lock = RLock()
        self._files_root.mkdir(parents=True, exist_ok=True)
        self._metadata_root.mkdir(parents=True, exist_ok=True)

    def create_asset(
        self,
        *,
        filename: str,
        content_type: str | None,
        content: bytes,
        source: str = "manual_upload",
    ) -> AssetDepotItem:
        original_filename = _safe_original_filename(filename)
        normalized_content_type = _normalize_content_type(content_type, original_filename)
        _validate_asset_content(
            filename=original_filename,
            content_type=normalized_content_type,
            content=content,
            max_upload_bytes=self._max_upload_bytes,
        )
        asset_id = "asset-" + uuid4().hex[:12]
        suffix = Path(original_filename).suffix.lower()
        digest = hashlib.sha256(content).hexdigest()
        asset = AssetDepotItem(
            id=asset_id,
            original_filename=original_filename,
            content_type=normalized_content_type,
            size_bytes=len(content),
            sha256=digest,
            created_at=_now_iso(),
            storage_path=f"files/{asset_id}{suffix}",
            source=_safe_source(source),
        )
        with self._lock:
            _atomic_write_bytes(self._path_for_asset(asset), content)
            _atomic_write_json(self._metadata_path(asset.id), asset.to_payload())
        return asset

    def import_file(
        self,
        *,
        path: str | Path,
        filename: str,
        content_type: str | None,
        source: str,
    ) -> AssetDepotItem:
        resolved = Path(path).expanduser().resolve(strict=True)
        if not resolved.is_file():
            raise AssetDepotError("Asset source file not found.")
        content = resolved.read_bytes()
        return self.create_asset(
            filename=filename,
            content_type=content_type,
            content=content,
            source=source,
        )

    def get_asset(self, asset_id: str) -> AssetDepotItem | None:
        _validate_asset_id(asset_id)
        metadata_path = self._metadata_path(asset_id)
        with self._lock:
            if not metadata_path.is_file():
                return None
            return _asset_from_payload(_read_json(metadata_path))

    def list_assets(self, *, limit: int = 100) -> tuple[AssetDepotItem, ...]:
        normalized_limit = max(1, min(limit, 500))
        with self._lock:
            assets: list[AssetDepotItem] = []
            for metadata_path in sorted(
                self._metadata_root.glob("*.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            ):
                assets.append(_asset_from_payload(_read_json(metadata_path)))
                if len(assets) >= normalized_limit:
                    break
            return tuple(assets)

    def delete_asset(self, asset_id: str) -> bool:
        _validate_asset_id(asset_id)
        with self._lock:
            asset = self.get_asset(asset_id)
            if asset is None:
                return False
            self._metadata_path(asset_id).unlink(missing_ok=True)
            self._path_for_asset(asset).unlink(missing_ok=True)
            return True

    def asset_file_path(self, asset: AssetDepotItem) -> Path:
        return self._path_for_asset(asset)

    def copy_asset_to(
        self,
        *,
        asset: AssetDepotItem,
        target_project: Path,
        relative_destination: str,
    ) -> str:
        destination = (target_project / relative_destination).resolve()
        project_root = target_project.resolve()
        try:
            destination.relative_to(project_root)
        except ValueError as exc:
            raise AssetDepotError("Asset destination escapes generated project.") from exc
        source = self._path_for_asset(asset)
        if not source.is_file():
            raise AssetDepotError(f"Asset file is missing: {asset.id}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        return str(destination.relative_to(target_project))

    def _metadata_path(self, asset_id: str) -> Path:
        return self._metadata_root / f"{asset_id}.json"

    def _path_for_asset(self, asset: AssetDepotItem) -> Path:
        path = (self._storage_root / asset.storage_path).resolve()
        try:
            path.relative_to(self._storage_root)
        except ValueError as exc:
            raise AssetDepotError("Unsafe asset storage path.") from exc
        return path


def _safe_original_filename(filename: str) -> str:
    cleaned = filename.strip()
    if not cleaned:
        raise AssetDepotError("Asset filename is required.")
    normalized = cleaned.replace("\\", "/")
    if "/" in normalized or normalized in {".", ".."}:
        raise AssetDepotError("Asset filename must not contain path separators.")
    if not re.fullmatch(r"[A-Za-z0-9._ -]{1,180}", normalized):
        raise AssetDepotError("Asset filename contains unsupported characters.")
    return normalized


def _normalize_content_type(content_type: str | None, filename: str) -> str:
    normalized = (content_type or "").split(";", maxsplit=1)[0].strip().lower()
    if normalized:
        return normalized
    guessed, _encoding = mimetypes.guess_type(filename)
    if guessed:
        return guessed.lower()
    raise AssetDepotError("Asset content type is required.")


def _validate_asset_content(
    *,
    filename: str,
    content_type: str,
    content: bytes,
    max_upload_bytes: int,
) -> None:
    if not content:
        raise AssetDepotError("Asset cannot be empty.")
    if len(content) > max_upload_bytes:
        raise AssetDepotError(f"Asset exceeds the {max_upload_bytes} byte limit.")
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise AssetDepotError("Asset extension is not supported.")
    if not (
        content_type in _ALLOWED_MIME_TYPES
        or any(content_type.startswith(prefix) for prefix in _ALLOWED_MIME_PREFIXES)
    ):
        raise AssetDepotError("Asset content type is not supported.")


def _safe_source(source: str) -> str:
    cleaned = source.strip() or "manual_upload"
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,80}", cleaned):
        raise AssetDepotError("Asset source is invalid.")
    return cleaned


def _validate_asset_id(asset_id: str) -> None:
    if not re.fullmatch(r"asset-[a-f0-9]{12}", asset_id):
        raise AssetDepotError("Invalid asset id.")


def validate_asset_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized not in ALLOWED_ASSET_ROLES:
        raise AssetDepotError("Unsupported project asset role.")
    return normalized


def _asset_from_payload(payload: dict[str, object]) -> AssetDepotItem:
    return AssetDepotItem(
        id=str(payload.get("asset_id") or payload["id"]),
        original_filename=str(payload["original_filename"]),
        content_type=str(payload["content_type"]),
        size_bytes=int(payload["size_bytes"]),
        sha256=str(payload["sha256"]),
        created_at=str(payload["created_at"]),
        storage_path=str(payload["storage_path"]),
        source=str(payload["source"]),
    )


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssetDepotError("Invalid asset metadata payload.")
    return payload


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


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
