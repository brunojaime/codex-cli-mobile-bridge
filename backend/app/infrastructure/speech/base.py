from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class SpeechSynthesisError(RuntimeError):
    pass


class SpeechSynthesisUnavailableError(SpeechSynthesisError):
    pass


@dataclass(slots=True)
class SpeechSynthesizerStatus:
    backend: str
    ready: bool
    detail: str | None = None
    voice: str | None = None
    response_format: str | None = None


@dataclass(slots=True)
class SynthesizedSpeech:
    audio_bytes: bytes
    content_type: str
    response_format: str


class SpeechSynthesizer(ABC):
    @abstractmethod
    def status(self) -> SpeechSynthesizerStatus:
        raise NotImplementedError

    @abstractmethod
    def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        response_format: str | None = None,
        instructions: str | None = None,
    ) -> SynthesizedSpeech:
        raise NotImplementedError
