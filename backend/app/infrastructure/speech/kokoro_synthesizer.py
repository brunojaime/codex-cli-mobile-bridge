from __future__ import annotations

from io import BytesIO
import importlib.util
import re
import shutil
import threading
from typing import Any

from backend.app.infrastructure.speech.base import (
    SpeechSynthesizer,
    SpeechSynthesizerStatus,
    SpeechSynthesisError,
    SpeechSynthesisUnavailableError,
    SynthesizedSpeech,
)


_SUPPORTED_RESPONSE_FORMAT_CONTENT_TYPES = {
    "flac": "audio/flac",
    "ogg": "audio/ogg",
    "wav": "audio/wav",
}


class KokoroSpeechSynthesizer(SpeechSynthesizer):
    def __init__(
        self,
        *,
        lang_code: str,
        voice: str,
        speed: float,
        split_pattern: str,
        sample_rate: int,
        response_format: str,
    ) -> None:
        self._lang_code = lang_code
        self._voice = voice
        self._speed = speed
        self._split_pattern = split_pattern
        self._sample_rate = sample_rate
        self._response_format = _normalize_response_format(response_format)
        self._pipeline: Any | None = None
        self._lock = threading.Lock()

    def status(self) -> SpeechSynthesizerStatus:
        missing_dependencies = _missing_dependencies()
        ready = not missing_dependencies
        detail = (
            f"Kokoro-82M local TTS: lang={self._lang_code}, speed={self._speed:g}"
            if ready
            else (
                "Kokoro speech dependencies are missing: "
                f"{', '.join(missing_dependencies)}. "
                "Install with `uv pip install -e '.[speech]'` and ensure "
                "`espeak-ng` is available on the host."
            )
        )
        return SpeechSynthesizerStatus(
            backend="kokoro",
            ready=ready,
            detail=detail,
            voice=self._voice,
            response_format=self._response_format,
        )

    def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        response_format: str | None = None,
        instructions: str | None = None,
    ) -> SynthesizedSpeech:
        missing_dependencies = _missing_dependencies()
        if missing_dependencies:
            raise SpeechSynthesisUnavailableError(
                "Kokoro speech dependencies are not installed: "
                f"{', '.join(missing_dependencies)}."
            )

        input_text = _prepare_text_for_speech(text)
        if not input_text:
            raise SpeechSynthesisError("Speech synthesis input cannot be empty.")

        resolved_format = _normalize_response_format(
            response_format or self._response_format
        )
        try:
            with self._lock:
                pipeline = self._load_pipeline()
                generator = pipeline(
                    input_text,
                    voice=voice or self._voice,
                    speed=self._speed,
                    split_pattern=self._split_pattern,
                )
                audio_segments = [audio for _, _, audio in generator]
        except SpeechSynthesisUnavailableError:
            raise
        except Exception as exc:
            raise SpeechSynthesisError(
                f"Kokoro speech synthesis failed: {exc}"
            ) from exc

        if not audio_segments:
            raise SpeechSynthesisError("Kokoro returned empty audio output.")

        try:
            audio_bytes = _encode_audio(
                audio_segments, resolved_format, self._sample_rate
            )
        except Exception as exc:
            raise SpeechSynthesisError(
                f"Kokoro audio encoding failed: {exc}"
            ) from exc

        return SynthesizedSpeech(
            audio_bytes=audio_bytes,
            content_type=_content_type_for_format(resolved_format),
            response_format=resolved_format,
        )

    def _load_pipeline(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline

        try:
            from kokoro import KPipeline
        except ImportError as exc:
            raise SpeechSynthesisUnavailableError(
                "Kokoro is not installed. Install with `uv pip install -e '.[speech]'`."
            ) from exc

        self._pipeline = KPipeline(lang_code=self._lang_code)
        return self._pipeline


def _missing_dependencies() -> list[str]:
    missing: list[str] = []
    if importlib.util.find_spec("kokoro") is None:
        missing.append("kokoro")
    if importlib.util.find_spec("soundfile") is None:
        missing.append("soundfile")
    if not _has_espeak_binary():
        missing.append("espeak-ng/espeak")
    return missing


def _has_espeak_binary() -> bool:
    return shutil.which("espeak-ng") is not None or shutil.which("espeak") is not None


def _prepare_text_for_speech(text: str) -> str:
    stripped = text.strip()
    stripped = re.sub(r"```[\s\S]*?```", " ", stripped)
    stripped = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", stripped)
    stripped = re.sub(r"\s+", " ", stripped)
    return stripped.strip()


def _encode_audio(
    audio_segments: list[Any],
    response_format: str,
    sample_rate: int,
) -> bytes:
    import numpy as np
    import soundfile as sf

    audio = _join_audio_segments(audio_segments, np)
    buffer = BytesIO()
    sf.write(buffer, audio, sample_rate, format=response_format.upper())
    return buffer.getvalue()


def _join_audio_segments(audio_segments: list[Any], np_module: Any) -> Any:
    if len(audio_segments) == 1:
        return audio_segments[0]
    return np_module.concatenate(audio_segments)


def _normalize_response_format(response_format: str) -> str:
    normalized = response_format.strip().lower()
    if normalized in _SUPPORTED_RESPONSE_FORMAT_CONTENT_TYPES:
        return normalized
    return "wav"


def _content_type_for_format(response_format: str) -> str:
    return _SUPPORTED_RESPONSE_FORMAT_CONTENT_TYPES.get(response_format, "audio/wav")
