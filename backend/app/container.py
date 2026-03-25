from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from backend.app.application.services.message_service import MessageService
from backend.app.domain.repositories.chat_repository import (
    ChatRepository,
    PersistenceDiagnosticIssue,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.execution.base import ExecutionProvider
from backend.app.infrastructure.execution.lambda_provider import LambdaExecutionProvider
from backend.app.infrastructure.execution.local_provider import LocalExecutionProvider
from backend.app.infrastructure.persistence.in_memory_chat_repository import InMemoryChatRepository
from backend.app.infrastructure.persistence.sqlite_chat_repository import SqliteChatRepository
from backend.app.infrastructure.persistence.unavailable_chat_repository import (
    UnavailableChatRepository,
)
from backend.app.infrastructure.realtime.job_stream_hub import JobStreamHub
from backend.app.infrastructure.transcription.base import AudioTranscriber
from backend.app.infrastructure.transcription.command_transcriber import CommandAudioTranscriber
from backend.app.infrastructure.transcription.disabled_transcriber import DisabledAudioTranscriber
from backend.app.infrastructure.transcription.faster_whisper_transcriber import (
    FasterWhisperAudioTranscriber,
)
from backend.app.infrastructure.transcription.openai_transcriber import OpenAIAudioTranscriber


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    message_service: MessageService
    job_stream_hub: JobStreamHub
    audio_transcriber: AudioTranscriber
    persistence_startup_issue: PersistenceDiagnosticIssue | None = None


def build_container(settings: Settings | None = None) -> AppContainer:
    resolved_settings = settings or Settings()
    persistence_startup_issue: PersistenceDiagnosticIssue | None = None
    try:
        repository = _build_repository(resolved_settings)
    except Exception as exc:
        persistence_startup_issue = _persistence_startup_issue_from_exception(exc)
        repository = UnavailableChatRepository(persistence_startup_issue)
    provider = _build_execution_provider(resolved_settings)
    audio_transcriber = _build_audio_transcriber(resolved_settings)
    message_service = MessageService(
        repository=repository,
        execution_provider=provider,
        default_workspace_path=resolved_settings.codex_workdir,
        audio_transcriber=audio_transcriber,
        document_text_char_limit=resolved_settings.document_text_char_limit,
    )
    job_stream_hub = JobStreamHub(
        poll_interval_seconds=resolved_settings.poll_interval_seconds,
    )
    return AppContainer(
        settings=resolved_settings,
        message_service=message_service,
        job_stream_hub=job_stream_hub,
        audio_transcriber=audio_transcriber,
        persistence_startup_issue=persistence_startup_issue,
    )


def _build_repository(settings: Settings) -> ChatRepository:
    if settings.chat_store_backend == "memory":
        return InMemoryChatRepository(projects_root=settings.projects_root)

    return SqliteChatRepository(
        database_path=settings.chat_store_path,
        projects_root=settings.projects_root,
    )


def _persistence_startup_issue_from_exception(
    exc: Exception,
) -> PersistenceDiagnosticIssue:
    if isinstance(exc, sqlite3.DatabaseError):
        return PersistenceDiagnosticIssue(
            table="database",
            row_id=None,
            field=None,
            code="sqlite_database_error",
            detail=str(exc),
        )
    return PersistenceDiagnosticIssue(
        table="database",
        row_id=None,
        field=None,
        code="persistence_startup_failure",
        detail=str(exc),
    )


def _build_execution_provider(settings: Settings) -> ExecutionProvider:
    if settings.effective_backend_mode == "lambda":
        return LambdaExecutionProvider(
            endpoint=settings.lambda_endpoint,
            timeout_seconds=settings.execution_timeout_seconds,
        )

    return LocalExecutionProvider(
        command=settings.codex_command,
        use_exec_mode=settings.codex_use_exec,
        exec_args=settings.codex_exec_args,
        resume_args=settings.codex_resume_args,
        workdir=settings.codex_workdir,
        timeout_seconds=settings.execution_timeout_seconds,
    )


def _build_audio_transcriber(settings: Settings) -> AudioTranscriber:
    if settings.audio_transcription_backend == "auto":
        if settings.audio_transcription_command:
            return CommandAudioTranscriber(
                command=settings.audio_transcription_command,
                timeout_seconds=settings.audio_transcription_timeout_seconds,
            )

        if settings.openai_api_key:
            return OpenAIAudioTranscriber(
                api_key=settings.openai_api_key,
                model=settings.audio_transcription_model,
                base_url=settings.openai_base_url,
                timeout_seconds=settings.audio_transcription_timeout_seconds,
                default_language=settings.audio_transcription_language,
            )

        return FasterWhisperAudioTranscriber(
            model=settings.audio_transcription_local_model,
            device=settings.audio_transcription_local_device,
            compute_type=settings.audio_transcription_local_compute_type,
        )

    if settings.audio_transcription_backend == "command":
        return CommandAudioTranscriber(
            command=settings.audio_transcription_command,
            timeout_seconds=settings.audio_transcription_timeout_seconds,
        )

    if settings.audio_transcription_backend == "openai":
        return OpenAIAudioTranscriber(
            api_key=settings.openai_api_key,
            model=settings.audio_transcription_model,
            base_url=settings.openai_base_url,
            timeout_seconds=settings.audio_transcription_timeout_seconds,
            default_language=settings.audio_transcription_language,
        )

    if settings.audio_transcription_backend == "faster_whisper":
        return FasterWhisperAudioTranscriber(
            model=settings.audio_transcription_local_model,
            device=settings.audio_transcription_local_device,
            compute_type=settings.audio_transcription_local_compute_type,
        )

    return DisabledAudioTranscriber()
