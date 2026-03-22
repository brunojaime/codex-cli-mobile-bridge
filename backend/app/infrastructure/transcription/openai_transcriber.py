from __future__ import annotations

from pathlib import Path
import json

import httpx

from backend.app.infrastructure.transcription.base import (
    AudioTranscriber,
    AudioTranscriberStatus,
    AudioTranscriptionError,
    AudioTranscriptionUnavailableError,
)


class OpenAIAudioTranscriber(AudioTranscriber):
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        base_url: str,
        timeout_seconds: int = 120,
        default_language: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._default_language = default_language

    def status(self) -> AudioTranscriberStatus:
        return AudioTranscriberStatus(
            backend="openai",
            ready=bool(self._api_key),
            detail=f"OpenAI transcription model: {self._model}",
        )

    def transcribe(
        self,
        audio_path: Path,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        language: str | None = None,
    ) -> str:
        if not self._api_key:
            raise AudioTranscriptionUnavailableError(
                "OPENAI_API_KEY is not configured for audio transcription."
            )

        data = {"model": self._model}
        resolved_language = language or self._default_language
        if resolved_language:
            data["language"] = resolved_language

        try:
            with audio_path.open("rb") as audio_file:
                response = httpx.post(
                    f"{self._base_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    data=data,
                    files={
                        "file": (
                            filename or audio_path.name,
                            audio_file,
                            content_type or "application/octet-stream",
                        )
                    },
                    timeout=self._timeout_seconds,
                )
        except httpx.TimeoutException as exc:
            raise AudioTranscriptionError(
                f"OpenAI transcription timed out after {self._timeout_seconds} seconds."
            ) from exc
        except httpx.HTTPError as exc:
            raise AudioTranscriptionError(f"OpenAI transcription request failed: {exc}") from exc

        if response.status_code >= 400:
            raise AudioTranscriptionError(
                _extract_openai_error(response) or "OpenAI transcription request failed."
            )

        transcript = _extract_transcript(response)
        if not transcript:
            raise AudioTranscriptionError("OpenAI returned an empty transcript.")
        return transcript


def _extract_transcript(response: httpx.Response) -> str:
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = response.json()
        if isinstance(payload, dict):
            return str(payload.get("text", "")).strip()
        return ""
    return response.text.strip()


def _extract_openai_error(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        return response.text.strip() or None

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
    return response.text.strip() or None
