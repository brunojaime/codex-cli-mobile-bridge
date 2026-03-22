from __future__ import annotations

from pathlib import Path

from backend.app.infrastructure.transcription.base import (
    AudioTranscriber,
    AudioTranscriberStatus,
    AudioTranscriptionError,
    AudioTranscriptionUnavailableError,
)


class FasterWhisperAudioTranscriber(AudioTranscriber):
    def __init__(
        self,
        *,
        model: str = "small",
        device: str = "auto",
        compute_type: str = "int8",
    ) -> None:
        self._model_name = model
        self._device = device
        self._compute_type = compute_type
        self._model = None

    def status(self) -> AudioTranscriberStatus:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return AudioTranscriberStatus(
                backend="faster_whisper",
                ready=False,
                detail="faster-whisper is not installed.",
            )

        return AudioTranscriberStatus(
            backend="faster_whisper",
            ready=True,
            detail=f"Local faster-whisper model: {self._model_name}",
        )

    def transcribe(
        self,
        audio_path: Path,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        language: str | None = None,
    ) -> str:
        model = self._get_model()

        try:
            segments, _info = model.transcribe(
                str(audio_path),
                language=language,
                vad_filter=True,
                beam_size=5,
            )
        except Exception as exc:
            raise AudioTranscriptionError(
                f"Local faster-whisper transcription failed: {exc}"
            ) from exc

        transcript = " ".join(segment.text.strip() for segment in segments).strip()
        if not transcript:
            raise AudioTranscriptionError("Local faster-whisper returned an empty transcript.")
        return transcript

    def _get_model(self):
        if self._model is not None:
            return self._model

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise AudioTranscriptionUnavailableError(
                "faster-whisper is not installed."
            ) from exc

        try:
            self._model = WhisperModel(
                self._model_name,
                device=self._device,
                compute_type=self._compute_type,
            )
        except Exception as exc:
            raise AudioTranscriptionUnavailableError(
                f"Failed to initialize faster-whisper model '{self._model_name}': {exc}"
            ) from exc

        return self._model
