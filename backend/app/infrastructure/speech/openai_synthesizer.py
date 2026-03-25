from __future__ import annotations

import json

import httpx

from backend.app.infrastructure.speech.base import (
    SpeechSynthesizer,
    SpeechSynthesizerStatus,
    SpeechSynthesisError,
    SpeechSynthesisUnavailableError,
    SynthesizedSpeech,
)


class OpenAISpeechSynthesizer(SpeechSynthesizer):
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        voice: str,
        response_format: str,
        instructions: str | None,
        base_url: str,
        timeout_seconds: int = 120,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._voice = voice
        self._response_format = response_format
        self._instructions = instructions
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def status(self) -> SpeechSynthesizerStatus:
        return SpeechSynthesizerStatus(
            backend="openai",
            ready=bool(self._api_key),
            detail=f"OpenAI speech model: {self._model}",
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
        if not self._api_key:
            raise SpeechSynthesisUnavailableError(
                "OPENAI_API_KEY is not configured for speech synthesis."
            )

        input_text = text.strip()
        if not input_text:
            raise SpeechSynthesisError("Speech synthesis input cannot be empty.")

        payload: dict[str, str] = {
            "model": self._model,
            "input": input_text,
            "voice": voice or self._voice,
            "response_format": response_format or self._response_format,
        }
        resolved_instructions = instructions or self._instructions
        if resolved_instructions:
            payload["instructions"] = resolved_instructions

        try:
            response = httpx.post(
                f"{self._base_url}/audio/speech",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self._timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise SpeechSynthesisError(
                f"OpenAI speech request timed out after {self._timeout_seconds} seconds."
            ) from exc
        except httpx.HTTPError as exc:
            raise SpeechSynthesisError(f"OpenAI speech request failed: {exc}") from exc

        if response.status_code >= 400:
            raise SpeechSynthesisError(
                _extract_openai_error(response) or "OpenAI speech request failed."
            )

        content = bytes(response.content)
        if not content:
            raise SpeechSynthesisError("OpenAI returned empty audio output.")

        return SynthesizedSpeech(
            audio_bytes=content,
            content_type=(
                response.headers.get("content-type")
                or _content_type_for_format(payload["response_format"])
            ),
            response_format=payload["response_format"],
        )


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


def _content_type_for_format(response_format: str) -> str:
    return {
        "aac": "audio/aac",
        "flac": "audio/flac",
        "mp3": "audio/mpeg",
        "opus": "audio/opus",
        "pcm": "audio/pcm",
        "wav": "audio/wav",
    }.get(response_format, "application/octet-stream")
