from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import base64
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class FeedbackQueueItem:
    id: str
    source_app: str
    source_display_name: str | None
    comment: str
    created_at: str
    status: str = "pending"
    screenshot_mime_type: str = "image/png"
    screenshot_file: str | None = None
    selection_points: list[dict[str, float]] = field(default_factory=list)
    selection_bounds: dict[str, float] = field(default_factory=dict)
    audio_mime_type: str | None = None
    audio_duration_ms: int | None = None
    audio_byte_length: int | None = None
    audio_file: str | None = None
    audio_transcript: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FeedbackQueueItem":
        return cls(
            id=str(payload["id"]),
            source_app=str(payload.get("source_app") or "unknown"),
            source_display_name=(
                str(payload["source_display_name"])
                if payload.get("source_display_name") is not None
                else None
            ),
            comment=str(payload.get("comment") or ""),
            created_at=str(payload.get("created_at") or ""),
            status=str(payload.get("status") or "pending"),
            screenshot_mime_type=str(
                payload.get("screenshot_mime_type") or "image/png"
            ),
            screenshot_file=(
                str(payload["screenshot_file"])
                if payload.get("screenshot_file") is not None
                else None
            ),
            selection_points=list(payload.get("selection_points") or []),
            selection_bounds=dict(payload.get("selection_bounds") or {}),
            audio_mime_type=(
                str(payload["audio_mime_type"])
                if payload.get("audio_mime_type") is not None
                else None
            ),
            audio_duration_ms=(
                int(payload["audio_duration_ms"])
                if payload.get("audio_duration_ms") is not None
                else None
            ),
            audio_byte_length=(
                int(payload["audio_byte_length"])
                if payload.get("audio_byte_length") is not None
                else None
            ),
            audio_file=(
                str(payload["audio_file"])
                if payload.get("audio_file") is not None
                else None
            ),
            audio_transcript=(
                str(payload["audio_transcript"])
                if payload.get("audio_transcript") is not None
                else None
            ),
        )

    def to_dict(self, *, include_image: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "source_app": self.source_app,
            "source_display_name": self.source_display_name,
            "comment": self.comment,
            "created_at": self.created_at,
            "status": self.status,
            "screenshot_mime_type": self.screenshot_mime_type,
            "has_screenshot": self.screenshot_file is not None,
            "selection_points": self.selection_points,
            "selection_bounds": self.selection_bounds,
            "audio_mime_type": self.audio_mime_type,
            "audio_duration_ms": self.audio_duration_ms,
            "audio_byte_length": self.audio_byte_length,
            "has_audio": self.audio_file is not None or bool(self.audio_byte_length),
            "audio_transcript": self.audio_transcript,
        }
        if include_image and self.screenshot_file:
            path = Path(self.screenshot_file)
            if path.exists():
                data["screenshot_png_base64"] = base64.b64encode(
                    path.read_bytes()
                ).decode("ascii")
        if include_image and self.audio_file:
            path = Path(self.audio_file)
            if path.exists():
                data["audio_base64"] = base64.b64encode(path.read_bytes()).decode(
                    "ascii"
                )
        return data


class FeedbackQueueService:
    def __init__(self, queue_path: str, image_dir: str, audio_dir: str) -> None:
        self._queue_path = Path(queue_path)
        self._image_dir = Path(image_dir)
        self._audio_dir = Path(audio_dir)
        self._queue_path.parent.mkdir(parents=True, exist_ok=True)
        self._image_dir.mkdir(parents=True, exist_ok=True)
        self._audio_dir.mkdir(parents=True, exist_ok=True)

    def list_items(self, *, include_images: bool = False) -> list[FeedbackQueueItem]:
        return self._load_items(include_images=include_images)

    def get_item(self, item_id: str, *, include_image: bool = False) -> FeedbackQueueItem:
        for item in self._load_items(include_images=include_image):
            if item.id == item_id:
                return item
        raise KeyError(item_id)

    def create_item(self, payload: dict[str, Any]) -> FeedbackQueueItem:
        item_id = str(payload.get("id") or f"feedback-{uuid4().hex}")
        created_at = str(
            payload.get("createdAt")
            or payload.get("created_at")
            or datetime.now(UTC).isoformat()
        )
        image_path = self._store_screenshot(
            item_id,
            payload.get("screenshotPngBase64") or payload.get("screenshot_png_base64"),
        )
        audio_path = self._store_audio(
            item_id,
            payload.get("audioBase64") or payload.get("audio_base64"),
        )
        item = FeedbackQueueItem(
            id=item_id,
            source_app=str(
                payload.get("sourceApp")
                or payload.get("source_app")
                or "unknown"
            ),
            source_display_name=(
                payload.get("sourceDisplayName")
                or payload.get("source_display_name")
            ),
            comment=str(payload.get("comment") or ""),
            created_at=created_at,
            status="pending",
            screenshot_mime_type=str(
                payload.get("screenshotMimeType")
                or payload.get("screenshot_mime_type")
                or "image/png"
            ),
            screenshot_file=str(image_path) if image_path else None,
            selection_points=list(
                payload.get("selectionPoints") or payload.get("selection_points") or []
            ),
            selection_bounds=dict(
                payload.get("selectionBounds") or payload.get("selection_bounds") or {}
            ),
            audio_mime_type=payload.get("audioMimeType")
            or payload.get("audio_mime_type"),
            audio_duration_ms=payload.get("audioDurationMs")
            or payload.get("audio_duration_ms"),
            audio_byte_length=(
                payload.get("audioByteLength")
                or payload.get("audio_byte_length")
                or (audio_path.stat().st_size if audio_path else None)
            ),
            audio_file=str(audio_path) if audio_path else None,
            audio_transcript=payload.get("audioTranscript")
            or payload.get("audio_transcript"),
        )
        items = [existing for existing in self._load_items() if existing.id != item.id]
        items.append(item)
        self._save_items(items)
        return item

    def set_audio_transcript(
        self,
        item_id: str,
        transcript: str | None,
    ) -> FeedbackQueueItem:
        items = self._load_items()
        for index, item in enumerate(items):
            if item.id == item_id:
                items[index] = FeedbackQueueItem(
                    id=item.id,
                    source_app=item.source_app,
                    source_display_name=item.source_display_name,
                    comment=item.comment,
                    created_at=item.created_at,
                    status=item.status,
                    screenshot_mime_type=item.screenshot_mime_type,
                    screenshot_file=item.screenshot_file,
                    selection_points=item.selection_points,
                    selection_bounds=item.selection_bounds,
                    audio_mime_type=item.audio_mime_type,
                    audio_duration_ms=item.audio_duration_ms,
                    audio_byte_length=item.audio_byte_length,
                    audio_file=item.audio_file,
                    audio_transcript=transcript,
                )
                self._save_items(items)
                return items[index]
        raise KeyError(item_id)

    def mark_submitted(self, item_id: str) -> FeedbackQueueItem:
        items = self._load_items()
        for index, item in enumerate(items):
            if item.id == item_id:
                items[index] = FeedbackQueueItem(
                    id=item.id,
                    source_app=item.source_app,
                    source_display_name=item.source_display_name,
                    comment=item.comment,
                    created_at=item.created_at,
                    status="submitted",
                    screenshot_mime_type=item.screenshot_mime_type,
                    screenshot_file=item.screenshot_file,
                    selection_points=item.selection_points,
                    selection_bounds=item.selection_bounds,
                    audio_mime_type=item.audio_mime_type,
                    audio_duration_ms=item.audio_duration_ms,
                    audio_byte_length=item.audio_byte_length,
                    audio_file=item.audio_file,
                    audio_transcript=item.audio_transcript,
                )
                self._save_items(items)
                return items[index]
        raise KeyError(item_id)

    def delete_item(self, item_id: str) -> None:
        items = self._load_items()
        kept: list[FeedbackQueueItem] = []
        deleted: FeedbackQueueItem | None = None
        for item in items:
            if item.id == item_id:
                deleted = item
            else:
                kept.append(item)
        if deleted is None:
            raise KeyError(item_id)
        if deleted.screenshot_file:
            Path(deleted.screenshot_file).unlink(missing_ok=True)
        if deleted.audio_file:
            Path(deleted.audio_file).unlink(missing_ok=True)
        self._save_items(kept)

    def clear(self) -> None:
        for item in self._load_items():
            if item.screenshot_file:
                Path(item.screenshot_file).unlink(missing_ok=True)
            if item.audio_file:
                Path(item.audio_file).unlink(missing_ok=True)
        self._save_items([])

    def _store_screenshot(self, item_id: str, image_base64: Any) -> Path | None:
        if not isinstance(image_base64, str) or not image_base64.strip():
            return None
        try:
            image_bytes = base64.b64decode(image_base64, validate=True)
        except Exception as exc:
            raise ValueError("Invalid screenshot PNG base64.") from exc
        if not image_bytes:
            return None
        path = self._image_dir / f"{item_id}.png"
        path.write_bytes(image_bytes)
        return path

    def _store_audio(self, item_id: str, audio_base64: Any) -> Path | None:
        if not isinstance(audio_base64, str) or not audio_base64.strip():
            return None
        try:
            audio_bytes = base64.b64decode(audio_base64, validate=True)
        except Exception as exc:
            raise ValueError("Invalid audio base64.") from exc
        if not audio_bytes:
            return None
        path = self._audio_dir / f"{item_id}.webm"
        path.write_bytes(audio_bytes)
        return path

    def _load_items(self, *, include_images: bool = False) -> list[FeedbackQueueItem]:
        if not self._queue_path.exists():
            return []
        payload = json.loads(self._queue_path.read_text(encoding="utf-8"))
        return [
            FeedbackQueueItem.from_dict(item)
            for item in payload.get("items", [])
            if isinstance(item, dict)
        ]

    def _save_items(self, items: list[FeedbackQueueItem]) -> None:
        payload = {
            "version": 1,
            "items": [
                item.to_dict(include_image=False)
                | {
                    "screenshot_file": item.screenshot_file,
                    "audio_file": item.audio_file,
                }
                for item in items
            ],
        }
        self._queue_path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self._queue_path.parent,
            delete=False,
        ) as temp_file:
            json.dump(payload, temp_file, indent=2)
            temp_path = Path(temp_file.name)
        temp_path.replace(self._queue_path)
