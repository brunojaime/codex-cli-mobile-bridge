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


@dataclass(slots=True)
class FeedbackBatchRecord:
    id: str
    source_app: str
    source_display_name: str | None
    created_at: str
    submitted_at: str
    status: str
    workflow_preset_id: str
    release_when_complete: bool
    item_count: int
    item_ids: list[str] = field(default_factory=list)
    job_id: str | None = None
    session_id: str | None = None
    workspace_path: str | None = None
    message: str | None = None
    summary: str | None = None
    summary_generated_at: str | None = None
    notification_created_at: str | None = None
    notification_read_at: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FeedbackBatchRecord":
        return cls(
            id=str(payload["id"]),
            source_app=str(payload.get("source_app") or "unknown"),
            source_display_name=(
                str(payload["source_display_name"])
                if payload.get("source_display_name") is not None
                else None
            ),
            created_at=str(payload.get("created_at") or ""),
            submitted_at=str(payload.get("submitted_at") or ""),
            status=str(payload.get("status") or "pending"),
            workflow_preset_id=str(payload.get("workflow_preset_id") or ""),
            release_when_complete=bool(payload.get("release_when_complete")),
            item_count=int(payload.get("item_count") or 0),
            item_ids=[str(item_id) for item_id in payload.get("item_ids") or []],
            job_id=(
                str(payload["job_id"])
                if payload.get("job_id") is not None
                else None
            ),
            session_id=(
                str(payload["session_id"])
                if payload.get("session_id") is not None
                else None
            ),
            workspace_path=(
                str(payload["workspace_path"])
                if payload.get("workspace_path") is not None
                else None
            ),
            message=(
                str(payload["message"])
                if payload.get("message") is not None
                else None
            ),
            summary=(
                str(payload["summary"])
                if payload.get("summary") is not None
                else None
            ),
            summary_generated_at=(
                str(payload["summary_generated_at"])
                if payload.get("summary_generated_at") is not None
                else None
            ),
            notification_created_at=(
                str(payload["notification_created_at"])
                if payload.get("notification_created_at") is not None
                else None
            ),
            notification_read_at=(
                str(payload["notification_read_at"])
                if payload.get("notification_read_at") is not None
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_app": self.source_app,
            "source_display_name": self.source_display_name,
            "created_at": self.created_at,
            "submitted_at": self.submitted_at,
            "status": self.status,
            "workflow_preset_id": self.workflow_preset_id,
            "release_when_complete": self.release_when_complete,
            "item_count": self.item_count,
            "item_ids": self.item_ids,
            "job_id": self.job_id,
            "session_id": self.session_id,
            "workspace_path": self.workspace_path,
            "message": self.message,
            "summary": self.summary,
            "summary_generated_at": self.summary_generated_at,
            "notification_created_at": self.notification_created_at,
            "notification_read_at": self.notification_read_at,
        }


@dataclass(slots=True)
class FeedbackQuickAskRecord:
    id: str
    source_app: str
    source_display_name: str | None
    created_at: str
    question: str
    screenshot_mime_type: str = "image/png"
    screenshot_file: str | None = None
    selection_points: list[dict[str, float]] = field(default_factory=list)
    selection_bounds: dict[str, float] = field(default_factory=dict)
    job_id: str | None = None
    session_id: str | None = None
    workspace_path: str | None = None
    message: str | None = None
    answer: str | None = None
    answered_at: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FeedbackQuickAskRecord":
        return cls(
            id=str(payload["id"]),
            source_app=str(payload.get("source_app") or "unknown"),
            source_display_name=(
                str(payload["source_display_name"])
                if payload.get("source_display_name") is not None
                else None
            ),
            created_at=str(payload.get("created_at") or ""),
            question=str(payload.get("question") or ""),
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
            job_id=(
                str(payload["job_id"])
                if payload.get("job_id") is not None
                else None
            ),
            session_id=(
                str(payload["session_id"])
                if payload.get("session_id") is not None
                else None
            ),
            workspace_path=(
                str(payload["workspace_path"])
                if payload.get("workspace_path") is not None
                else None
            ),
            message=(
                str(payload["message"])
                if payload.get("message") is not None
                else None
            ),
            answer=(
                str(payload["answer"])
                if payload.get("answer") is not None
                else None
            ),
            answered_at=(
                str(payload["answered_at"])
                if payload.get("answered_at") is not None
                else None
            ),
        )

    def to_dict(self, *, include_image: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "source_app": self.source_app,
            "source_display_name": self.source_display_name,
            "created_at": self.created_at,
            "question": self.question,
            "screenshot_mime_type": self.screenshot_mime_type,
            "has_screenshot": self.screenshot_file is not None,
            "selection_points": self.selection_points,
            "selection_bounds": self.selection_bounds,
            "job_id": self.job_id,
            "session_id": self.session_id,
            "workspace_path": self.workspace_path,
            "message": self.message,
            "answer": self.answer,
            "answered_at": self.answered_at,
        }
        if include_image and self.screenshot_file:
            path = Path(self.screenshot_file)
            if path.exists():
                data["screenshot_png_base64"] = base64.b64encode(
                    path.read_bytes()
                ).decode("ascii")
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

    def list_batches(
        self,
        *,
        source_app: str | None = None,
    ) -> list[FeedbackBatchRecord]:
        source_app_key = (source_app or "").strip().lower()
        records = self._load_batches()
        if source_app_key:
            records = [
                record
                for record in records
                if record.source_app.strip().lower() == source_app_key
            ]
        return sorted(records, key=lambda record: record.submitted_at, reverse=True)

    def list_quick_asks(
        self,
        *,
        source_app: str | None = None,
    ) -> list[FeedbackQuickAskRecord]:
        source_app_key = (source_app or "").strip().lower()
        records = self._load_quick_asks()
        if source_app_key:
            records = [
                record
                for record in records
                if record.source_app.strip().lower() == source_app_key
            ]
        return sorted(records, key=lambda record: record.created_at, reverse=True)

    def get_batch(self, batch_id: str) -> FeedbackBatchRecord:
        for record in self._load_batches():
            if record.id == batch_id:
                return record
        raise KeyError(batch_id)

    def get_quick_ask(self, quick_ask_id: str) -> FeedbackQuickAskRecord:
        for record in self._load_quick_asks():
            if record.id == quick_ask_id:
                return record
        raise KeyError(quick_ask_id)

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

    def create_batch_record(
        self,
        *,
        batch_id: str | None,
        source_app: str,
        source_display_name: str | None,
        workflow_preset_id: str,
        release_when_complete: bool,
        items: list[FeedbackQueueItem],
        job_id: str,
        session_id: str,
        workspace_path: str | None,
        message: str,
    ) -> FeedbackBatchRecord:
        now = datetime.now(UTC).isoformat()
        record = FeedbackBatchRecord(
            id=batch_id or f"feedback-batch-{uuid4().hex}",
            source_app=source_app or "unknown",
            source_display_name=source_display_name,
            created_at=now,
            submitted_at=now,
            status="running",
            workflow_preset_id=workflow_preset_id,
            release_when_complete=release_when_complete,
            item_count=len(items),
            item_ids=[item.id for item in items],
            job_id=job_id,
            session_id=session_id,
            workspace_path=workspace_path,
            message=message,
            summary=None,
            summary_generated_at=None,
            notification_created_at=None,
            notification_read_at=None,
        )
        records = [
            existing for existing in self._load_batches() if existing.id != record.id
        ]
        records.append(record)
        self._save_batches(records)
        return record

    def create_quick_ask_record(
        self,
        *,
        quick_ask_id: str | None,
        source_app: str,
        source_display_name: str | None,
        question: str,
        screenshot_mime_type: str,
        screenshot_png_base64: str,
        selection_points: list[dict[str, float]],
        selection_bounds: dict[str, float],
        job_id: str,
        session_id: str,
        workspace_path: str | None,
        message: str,
    ) -> FeedbackQuickAskRecord:
        record_id = quick_ask_id or f"feedback-quick-ask-{uuid4().hex}"
        image_path = self._store_screenshot(record_id, screenshot_png_base64)
        now = datetime.now(UTC).isoformat()
        record = FeedbackQuickAskRecord(
            id=record_id,
            source_app=source_app or "unknown",
            source_display_name=source_display_name,
            created_at=now,
            question=question,
            screenshot_mime_type=screenshot_mime_type or "image/png",
            screenshot_file=str(image_path) if image_path else None,
            selection_points=selection_points,
            selection_bounds=selection_bounds,
            job_id=job_id,
            session_id=session_id,
            workspace_path=workspace_path,
            message=message,
        )
        records = [
            existing for existing in self._load_quick_asks() if existing.id != record.id
        ]
        records.append(record)
        self._save_quick_asks(records)
        return record

    def set_quick_ask_answer(
        self,
        quick_ask_id: str,
        answer: str | None,
    ) -> FeedbackQuickAskRecord:
        now = datetime.now(UTC).isoformat()
        records = self._load_quick_asks()
        for index, record in enumerate(records):
            if record.id == quick_ask_id:
                records[index] = FeedbackQuickAskRecord(
                    id=record.id,
                    source_app=record.source_app,
                    source_display_name=record.source_display_name,
                    created_at=record.created_at,
                    question=record.question,
                    screenshot_mime_type=record.screenshot_mime_type,
                    screenshot_file=record.screenshot_file,
                    selection_points=record.selection_points,
                    selection_bounds=record.selection_bounds,
                    job_id=record.job_id,
                    session_id=record.session_id,
                    workspace_path=record.workspace_path,
                    message=record.message,
                    answer=answer,
                    answered_at=now if answer else None,
                )
                self._save_quick_asks(records)
                return records[index]
        raise KeyError(quick_ask_id)

    def set_batch_summary(self, batch_id: str, summary: str) -> FeedbackBatchRecord:
        now = datetime.now(UTC).isoformat()
        records = self._load_batches()
        for index, record in enumerate(records):
            if record.id == batch_id:
                records[index] = FeedbackBatchRecord(
                    id=record.id,
                    source_app=record.source_app,
                    source_display_name=record.source_display_name,
                    created_at=record.created_at,
                    submitted_at=record.submitted_at,
                    status=record.status,
                    workflow_preset_id=record.workflow_preset_id,
                    release_when_complete=record.release_when_complete,
                    item_count=record.item_count,
                    item_ids=record.item_ids,
                    job_id=record.job_id,
                    session_id=record.session_id,
                    workspace_path=record.workspace_path,
                    message=record.message,
                    summary=summary,
                    summary_generated_at=now,
                    notification_created_at=record.notification_created_at,
                    notification_read_at=record.notification_read_at,
                )
                self._save_batches(records)
                return records[index]
        raise KeyError(batch_id)

    def ensure_batch_notification(self, batch_id: str) -> FeedbackBatchRecord:
        now = datetime.now(UTC).isoformat()
        records = self._load_batches()
        for index, record in enumerate(records):
            if record.id == batch_id:
                if record.notification_created_at:
                    return record
                records[index] = FeedbackBatchRecord(
                    id=record.id,
                    source_app=record.source_app,
                    source_display_name=record.source_display_name,
                    created_at=record.created_at,
                    submitted_at=record.submitted_at,
                    status=record.status,
                    workflow_preset_id=record.workflow_preset_id,
                    release_when_complete=record.release_when_complete,
                    item_count=record.item_count,
                    item_ids=record.item_ids,
                    job_id=record.job_id,
                    session_id=record.session_id,
                    workspace_path=record.workspace_path,
                    message=record.message,
                    summary=record.summary,
                    summary_generated_at=record.summary_generated_at,
                    notification_created_at=now,
                    notification_read_at=record.notification_read_at,
                )
                self._save_batches(records)
                return records[index]
        raise KeyError(batch_id)

    def mark_batch_notification_read(
        self,
        batch_id: str,
        *,
        read: bool = True,
    ) -> FeedbackBatchRecord:
        now = datetime.now(UTC).isoformat()
        records = self._load_batches()
        for index, record in enumerate(records):
            if record.id == batch_id:
                records[index] = FeedbackBatchRecord(
                    id=record.id,
                    source_app=record.source_app,
                    source_display_name=record.source_display_name,
                    created_at=record.created_at,
                    submitted_at=record.submitted_at,
                    status=record.status,
                    workflow_preset_id=record.workflow_preset_id,
                    release_when_complete=record.release_when_complete,
                    item_count=record.item_count,
                    item_ids=record.item_ids,
                    job_id=record.job_id,
                    session_id=record.session_id,
                    workspace_path=record.workspace_path,
                    message=record.message,
                    summary=record.summary,
                    summary_generated_at=record.summary_generated_at,
                    notification_created_at=record.notification_created_at or now,
                    notification_read_at=now if read else None,
                )
                self._save_batches(records)
                return records[index]
        raise KeyError(batch_id)

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
        payload = self._load_payload()
        return [
            FeedbackQueueItem.from_dict(item)
            for item in payload.get("items", [])
            if isinstance(item, dict)
        ]

    def _save_items(self, items: list[FeedbackQueueItem]) -> None:
        payload = self._load_payload()
        payload["version"] = max(int(payload.get("version") or 1), 2)
        payload["items"] = [
            item.to_dict(include_image=False)
            | {
                "screenshot_file": item.screenshot_file,
                "audio_file": item.audio_file,
            }
            for item in items
        ]
        self._save_payload(payload)

    def _load_batches(self) -> list[FeedbackBatchRecord]:
        payload = self._load_payload()
        return [
            FeedbackBatchRecord.from_dict(record)
            for record in payload.get("batches", [])
            if isinstance(record, dict)
        ]

    def _save_batches(self, records: list[FeedbackBatchRecord]) -> None:
        payload = self._load_payload()
        payload["version"] = max(int(payload.get("version") or 1), 2)
        payload["batches"] = [record.to_dict() for record in records]
        self._save_payload(payload)

    def _load_quick_asks(self) -> list[FeedbackQuickAskRecord]:
        payload = self._load_payload()
        return [
            FeedbackQuickAskRecord.from_dict(record)
            for record in payload.get("quick_asks", [])
            if isinstance(record, dict)
        ]

    def _save_quick_asks(self, records: list[FeedbackQuickAskRecord]) -> None:
        payload = self._load_payload()
        payload["version"] = max(int(payload.get("version") or 1), 2)
        payload["quick_asks"] = [
            record.to_dict(include_image=False)
            | {"screenshot_file": record.screenshot_file}
            for record in records
        ]
        self._save_payload(payload)

    def _load_payload(self) -> dict[str, Any]:
        if not self._queue_path.exists():
            return {"version": 2, "items": [], "batches": [], "quick_asks": []}
        payload = json.loads(self._queue_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {"version": 2, "items": [], "batches": [], "quick_asks": []}
        payload.setdefault("items", [])
        payload.setdefault("batches", [])
        payload.setdefault("quick_asks", [])
        return payload

    def _save_payload(self, payload: dict[str, Any]) -> None:
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
