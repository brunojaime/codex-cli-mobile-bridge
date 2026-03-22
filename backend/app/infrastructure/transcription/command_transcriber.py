from __future__ import annotations

from pathlib import Path
import shlex
import shutil
import subprocess

from backend.app.infrastructure.transcription.base import (
    AudioTranscriber,
    AudioTranscriberStatus,
    AudioTranscriptionError,
    AudioTranscriptionUnavailableError,
)


class CommandAudioTranscriber(AudioTranscriber):
    def __init__(
        self,
        *,
        command: str | None,
        timeout_seconds: int = 120,
    ) -> None:
        self._command = command.strip() if command else ""
        self._timeout_seconds = timeout_seconds

    def status(self) -> AudioTranscriberStatus:
        if not self._command:
            return AudioTranscriberStatus(
                backend="command",
                ready=False,
                detail="AUDIO_TRANSCRIPTION_COMMAND is not configured.",
            )

        executable = shlex.split(self._command)[0]
        has_executable = executable.startswith(("/", "./", "../")) or shutil.which(executable)
        return AudioTranscriberStatus(
            backend="command",
            ready=bool(has_executable),
            detail=f"Command backend configured: {executable}",
        )

    def transcribe(
        self,
        audio_path: Path,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        language: str | None = None,
    ) -> str:
        if not self._command:
            raise AudioTranscriptionUnavailableError(
                "AUDIO_TRANSCRIPTION_COMMAND is not configured."
            )

        resolved_filename = filename or audio_path.name
        resolved_language = language or ""
        resolved_content_type = content_type or ""
        command_parts = [
            part.replace("{file}", str(audio_path))
            .replace("{filename}", resolved_filename)
            .replace("{language}", resolved_language)
            .replace("{content_type}", resolved_content_type)
            for part in shlex.split(self._command)
        ]
        if not any(str(audio_path) in part for part in command_parts):
            command_parts.append(str(audio_path))

        try:
            result = subprocess.run(
                command_parts,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise AudioTranscriptionUnavailableError(
                f"Transcription command was not found: {command_parts[0]}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise AudioTranscriptionError(
                f"Transcription command timed out after {self._timeout_seconds} seconds."
            ) from exc

        if result.returncode != 0:
            raise AudioTranscriptionError(
                result.stderr.strip()
                or result.stdout.strip()
                or "Transcription command failed."
            )

        transcript = result.stdout.strip()
        if not transcript:
            raise AudioTranscriptionError("Transcription command returned an empty transcript.")
        return transcript
