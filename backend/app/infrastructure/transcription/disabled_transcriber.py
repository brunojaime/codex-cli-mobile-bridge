from __future__ import annotations

from pathlib import Path

from backend.app.infrastructure.transcription.base import (
    AudioTranscriber,
    AudioTranscriberStatus,
    AudioTranscriptionUnavailableError,
)


class DisabledAudioTranscriber(AudioTranscriber):
    def status(self) -> AudioTranscriberStatus:
        return AudioTranscriberStatus(
            backend="disabled",
            ready=False,
            detail="Audio transcription is disabled.",
        )

    def transcribe(
        self,
        audio_path: Path,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        language: str | None = None,
    ) -> str:
        raise AudioTranscriptionUnavailableError(
            "Audio transcription is disabled. Configure "
            "AUDIO_TRANSCRIPTION_BACKEND=openai or AUDIO_TRANSCRIPTION_BACKEND=command."
        )
