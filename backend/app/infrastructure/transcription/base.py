from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


class AudioTranscriptionError(RuntimeError):
    pass


class AudioTranscriptionUnavailableError(AudioTranscriptionError):
    pass


@dataclass(slots=True)
class AudioTranscriberStatus:
    backend: str
    ready: bool
    detail: str | None = None


class AudioTranscriber(ABC):
    @abstractmethod
    def status(self) -> AudioTranscriberStatus:
        raise NotImplementedError

    @abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        language: str | None = None,
    ) -> str:
        raise NotImplementedError
