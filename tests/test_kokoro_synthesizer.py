from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest

from backend.app.infrastructure.speech import kokoro_synthesizer
from backend.app.infrastructure.speech.base import (
    SpeechSynthesisError,
    SpeechSynthesisUnavailableError,
)
from backend.app.infrastructure.speech.kokoro_synthesizer import (
    KokoroSpeechSynthesizer,
)


def test_status_ready_when_dependencies_are_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kokoro_synthesizer, "_missing_dependencies", lambda: [])
    synthesizer = _build_synthesizer(response_format="mp3")

    status = synthesizer.status()

    assert status.backend == "kokoro"
    assert status.ready is True
    assert status.voice == "ef_dora"
    assert status.response_format == "wav"
    assert status.detail == "Kokoro-82M local TTS: lang=e, speed=1"


def test_status_not_ready_includes_missing_espeak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        kokoro_synthesizer,
        "_missing_dependencies",
        lambda: ["espeak-ng/espeak"],
    )
    synthesizer = _build_synthesizer()

    status = synthesizer.status()

    assert status.ready is False
    assert "espeak-ng/espeak" in (status.detail or "")


def test_missing_dependencies_checks_espeak_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        kokoro_synthesizer.importlib.util,
        "find_spec",
        lambda name: object(),
    )
    monkeypatch.setattr(kokoro_synthesizer.shutil, "which", lambda name: None)

    assert kokoro_synthesizer._missing_dependencies() == ["espeak-ng/espeak"]


def test_synthesize_rejects_empty_sanitized_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kokoro_synthesizer, "_missing_dependencies", lambda: [])
    synthesizer = _build_synthesizer()

    with pytest.raises(SpeechSynthesisError, match="input cannot be empty"):
        synthesizer.synthesize("  ```python\nprint('hidden')\n```  ")


def test_synthesize_sanitizes_text_and_returns_wav_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kokoro_synthesizer, "_missing_dependencies", lambda: [])
    calls: list[dict[str, Any]] = []
    _install_fake_kokoro(
        monkeypatch,
        calls=calls,
        segments=[["tone"]],
    )
    monkeypatch.setattr(
        kokoro_synthesizer,
        "_encode_audio",
        lambda segments, response_format, sample_rate: b"RIFF-fake-wav",
    )
    synthesizer = _build_synthesizer()

    result = synthesizer.synthesize(
        "  Read [this link](https://example.test).\n```dart\nignored();\n``` Now.  "
    )

    assert result.audio_bytes == b"RIFF-fake-wav"
    assert result.content_type == "audio/wav"
    assert result.response_format == "wav"
    assert calls == [
        {
            "lang_code": "e",
            "text": "Read this link. Now.",
            "voice": "ef_dora",
            "speed": 1.0,
            "split_pattern": r"\n+",
        }
    ]


def test_synthesize_concatenates_multiple_segments_without_real_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kokoro_synthesizer, "_missing_dependencies", lambda: [])
    _install_fake_kokoro(
        monkeypatch,
        segments=[["a"], ["b"]],
    )
    concatenated: list[Any] = []
    _install_fake_audio_modules(monkeypatch, concatenated=concatenated)
    synthesizer = _build_synthesizer()

    result = synthesizer.synthesize("Hola.")

    assert concatenated == [[["a"], ["b"]]]
    assert result.audio_bytes == b"WAV|24000|['a', 'b']"
    assert result.content_type == "audio/wav"


def test_synthesize_unsupported_requested_format_falls_back_to_wav(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kokoro_synthesizer, "_missing_dependencies", lambda: [])
    _install_fake_kokoro(monkeypatch, segments=[["a"]])
    _install_fake_audio_modules(monkeypatch)
    synthesizer = _build_synthesizer(response_format="flac")

    result = synthesizer.synthesize("Hola.", response_format="mp3")

    assert result.response_format == "wav"
    assert result.content_type == "audio/wav"
    assert result.audio_bytes == b"WAV|24000|['a']"


def test_synthesize_soundfile_write_failures_map_to_synthesis_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kokoro_synthesizer, "_missing_dependencies", lambda: [])
    _install_fake_kokoro(monkeypatch, segments=[["a"]])
    _install_fake_audio_modules(
        monkeypatch,
        write_error=RuntimeError("libsndfile refused data"),
    )
    synthesizer = _build_synthesizer()

    with pytest.raises(SpeechSynthesisError, match="Kokoro audio encoding failed"):
        synthesizer.synthesize("Hola.")


def test_synthesize_concatenate_failures_map_to_synthesis_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kokoro_synthesizer, "_missing_dependencies", lambda: [])
    _install_fake_kokoro(monkeypatch, segments=[["a"], ["b"]])
    _install_fake_audio_modules(
        monkeypatch,
        concatenate_error=RuntimeError("cannot concatenate"),
    )
    synthesizer = _build_synthesizer()

    with pytest.raises(SpeechSynthesisError, match="Kokoro audio encoding failed"):
        synthesizer.synthesize("Hola.")


def test_synthesize_supported_flac_format_returns_flac_content_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kokoro_synthesizer, "_missing_dependencies", lambda: [])
    _install_fake_kokoro(monkeypatch, segments=[["a"]])
    _install_fake_audio_modules(monkeypatch)
    synthesizer = _build_synthesizer(response_format="flac")

    result = synthesizer.synthesize("Hola.")

    assert result.response_format == "flac"
    assert result.content_type == "audio/flac"
    assert result.audio_bytes == b"FLAC|24000|['a']"


def test_synthesize_reports_missing_dependencies_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        kokoro_synthesizer,
        "_missing_dependencies",
        lambda: ["kokoro", "espeak-ng/espeak"],
    )
    synthesizer = _build_synthesizer()

    with pytest.raises(SpeechSynthesisUnavailableError) as exc_info:
        synthesizer.synthesize("Hola.")

    assert "kokoro, espeak-ng/espeak" in str(exc_info.value)


def test_synthesize_pipeline_failures_map_to_synthesis_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kokoro_synthesizer, "_missing_dependencies", lambda: [])
    _install_fake_kokoro(monkeypatch, pipeline_error=RuntimeError("boom"))
    synthesizer = _build_synthesizer()

    with pytest.raises(SpeechSynthesisError, match="Kokoro speech synthesis failed"):
        synthesizer.synthesize("Hola.")


def _build_synthesizer(response_format: str = "wav") -> KokoroSpeechSynthesizer:
    return KokoroSpeechSynthesizer(
        lang_code="e",
        voice="ef_dora",
        speed=1.0,
        split_pattern=r"\n+",
        sample_rate=24_000,
        response_format=response_format,
    )


def _install_fake_kokoro(
    monkeypatch: pytest.MonkeyPatch,
    *,
    calls: list[dict[str, Any]] | None = None,
    segments: list[Any] | None = None,
    pipeline_error: Exception | None = None,
) -> None:
    module = ModuleType("kokoro")

    class FakePipeline:
        def __init__(self, *, lang_code: str) -> None:
            self._lang_code = lang_code

        def __call__(
            self,
            text: str,
            *,
            voice: str,
            speed: float,
            split_pattern: str,
        ) -> list[tuple[str, str, Any]]:
            if pipeline_error is not None:
                raise pipeline_error
            if calls is not None:
                calls.append(
                    {
                        "lang_code": self._lang_code,
                        "text": text,
                        "voice": voice,
                        "speed": speed,
                        "split_pattern": split_pattern,
                    }
                )
            return [
                ("graphemes", "phonemes", segment) for segment in (segments or [["a"]])
            ]

    module.KPipeline = FakePipeline
    monkeypatch.setitem(sys.modules, "kokoro", module)


def _install_fake_audio_modules(
    monkeypatch: pytest.MonkeyPatch,
    *,
    concatenated: list[Any] | None = None,
    concatenate_error: Exception | None = None,
    write_error: Exception | None = None,
) -> None:
    numpy_module = ModuleType("numpy")

    def concatenate(segments: list[Any]) -> list[Any]:
        if concatenate_error is not None:
            raise concatenate_error
        if concatenated is not None:
            concatenated.append(segments)
        joined: list[Any] = []
        for segment in segments:
            joined.extend(segment)
        return joined

    numpy_module.concatenate = concatenate
    monkeypatch.setitem(sys.modules, "numpy", numpy_module)

    soundfile_module = ModuleType("soundfile")

    def write(buffer: Any, audio: Any, sample_rate: int, *, format: str) -> None:
        if write_error is not None:
            raise write_error
        buffer.write(f"{format}|{sample_rate}|{audio}".encode("utf-8"))

    soundfile_module.write = write
    monkeypatch.setitem(sys.modules, "soundfile", soundfile_module)
