"""Versioned completion contract shared with recording uploaders."""
from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

READY_NAME = "LISTO.json"
POLL_SECONDS = 600
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".m4v", ".avi"}
AUDIO_EXTENSIONS = {".mp3"}
TEXT_EXTENSIONS = {".md", ".txt", ".srt", ".vtt"}


class DeliveryFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str = Field(min_length=1, max_length=500)
    drive_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=200)
    role: Literal["video", "audio", "transcript", "summary", "attachment"]
    size: int = Field(ge=1, le=4 * 1024**3)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_path(self):
        path = PurePosixPath(self.path)
        if (
            path.is_absolute() or "\\" in self.path
            or any(p in {"", ".", ".."} for p in self.path.split("/"))
            or any(ord(c) < 32 for c in self.path)
            or any(p.startswith(".") for p in path.parts)
        ):
            raise ValueError("unsafe_delivery_path")
        if self.role == "attachment":
            if len(path.parts) < 2 or path.parts[0] != "adjuntos":
                raise ValueError("attachment_outside_adjuntos")
        elif len(path.parts) != 1 or self.path == READY_NAME:
            raise ValueError("main_file_must_be_at_meeting_root")
        if self.role == "video" and path.suffix.lower() not in VIDEO_EXTENSIONS:
            raise ValueError("unsupported_video")
        if self.role == "audio" and path.suffix.lower() not in AUDIO_EXTENSIONS:
            raise ValueError("unsupported_audio")
        if self.role in {"transcript", "summary"} and path.suffix.lower() not in TEXT_EXTENSIONS:
            raise ValueError("text_file_required")
        return self


class Delivery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    status: Literal["complete"]
    project: str = Field(min_length=1, max_length=200)
    meeting_id: UUID
    revision: int = Field(ge=1, strict=True)
    folder_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=200)
    completed_at: datetime
    files: list[DeliveryFile] = Field(min_length=3, max_length=103)

    @field_validator("completed_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("completed_at_requires_timezone")
        return value

    @model_validator(mode="after")
    def complete_inventory(self):
        if sum(f.role in {"video", "audio"} for f in self.files) != 1:
            raise ValueError("exactly_one_video_or_audio_required")
        for role in ("transcript", "summary"):
            if sum(f.role == role for f in self.files) != 1:
                raise ValueError("exactly_one_" + role + "_required")
        if len({f.path for f in self.files}) != len(self.files):
            raise ValueError("duplicate_path")
        if len({f.drive_id for f in self.files}) != len(self.files):
            raise ValueError("duplicate_drive_id")
        if sum(f.size for f in self.files) > 5 * 1024**3:
            raise ValueError("delivery_too_large")
        return self
