from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from backend.app.application.services.app_update_service import (
    AppUpdateRegistry,
    AppUpdateService,
    HttpGitHubReleaseClient,
)
from backend.app.application.services.asset_depot_service import AssetDepotService
from backend.app.application.services.cloudflare_preview_service import (
    CloudflarePreviewDoctorService,
)
from backend.app.application.services.message_service import MessageService
from backend.app.application.services.project_factory_service import (
    ProjectFactoryService,
)
from backend.app.application.services.web_preview_deploy_service import (
    WebPreviewDeployService,
)
from backend.app.application.services.web_preview_invite_service import (
    WebPreviewInviteService,
)
from backend.app.application.services.sdd_codex_job_service import SddCodexJobService
from backend.app.application.services.sdd_project_service import SddProjectService
from backend.app.application.services.sdd_workbench_view_service import (
    SddWorkbenchViewService,
)
from backend.app.application.services.feedback_queue_service import FeedbackQueueService
from backend.app.domain.repositories.chat_repository import (
    ChatRepository,
    PersistenceDiagnosticIssue,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.execution.base import ExecutionProvider
from backend.app.infrastructure.execution.lambda_provider import LambdaExecutionProvider
from backend.app.infrastructure.execution.local_provider import LocalExecutionProvider
from backend.app.infrastructure.persistence.in_memory_chat_repository import (
    InMemoryChatRepository,
)
from backend.app.infrastructure.persistence.sqlite_chat_repository import (
    SqliteChatRepository,
)
from backend.app.infrastructure.persistence.unavailable_chat_repository import (
    UnavailableChatRepository,
)
from backend.app.infrastructure.realtime.job_stream_hub import JobStreamHub
from backend.app.infrastructure.speech.base import SpeechSynthesizer
from backend.app.infrastructure.speech.disabled_synthesizer import (
    DisabledSpeechSynthesizer,
)
from backend.app.infrastructure.speech.kokoro_synthesizer import (
    KokoroSpeechSynthesizer,
)
from backend.app.infrastructure.speech.openai_synthesizer import (
    OpenAISpeechSynthesizer,
)
from backend.app.infrastructure.transcription.base import AudioTranscriber
from backend.app.infrastructure.transcription.command_transcriber import (
    CommandAudioTranscriber,
)
from backend.app.infrastructure.transcription.disabled_transcriber import (
    DisabledAudioTranscriber,
)
from backend.app.infrastructure.transcription.faster_whisper_transcriber import (
    FasterWhisperAudioTranscriber,
)
from backend.app.infrastructure.transcription.openai_transcriber import (
    OpenAIAudioTranscriber,
)


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    message_service: MessageService
    feedback_queue_service: FeedbackQueueService
    asset_depot_service: AssetDepotService
    app_update_service: AppUpdateService
    sdd_project_service: SddProjectService
    sdd_workbench_view_service: SddWorkbenchViewService
    sdd_codex_job_service: SddCodexJobService
    project_factory_service: ProjectFactoryService
    cloudflare_preview_doctor_service: CloudflarePreviewDoctorService
    web_preview_deploy_service: WebPreviewDeployService
    web_preview_invite_service: WebPreviewInviteService
    job_stream_hub: JobStreamHub
    audio_transcriber: AudioTranscriber
    speech_synthesizer: SpeechSynthesizer
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
    speech_synthesizer = _build_speech_synthesizer(resolved_settings)
    message_service = MessageService(
        repository=repository,
        execution_provider=provider,
        default_workspace_path=resolved_settings.codex_workdir,
        audio_transcriber=audio_transcriber,
        document_text_char_limit=resolved_settings.document_text_char_limit,
        title_generation_model=resolved_settings.codex_title_generation_model,
        follow_up_reconcile_interval_seconds=(
            float(resolved_settings.poll_interval_seconds)
            if resolved_settings.poll_interval_seconds > 0
            else None
        ),
    )
    job_stream_hub = JobStreamHub(
        poll_interval_seconds=resolved_settings.poll_interval_seconds,
    )
    feedback_queue_service = FeedbackQueueService(
        queue_path=resolved_settings.feedback_queue_path,
        image_dir=resolved_settings.feedback_image_dir,
        audio_dir=resolved_settings.feedback_audio_dir,
    )
    asset_depot_service = AssetDepotService(
        storage_root=resolved_settings.asset_depot_dir,
        max_upload_bytes=resolved_settings.asset_depot_max_upload_bytes,
    )
    app_update_service = AppUpdateService(
        registry=AppUpdateRegistry.from_json_file(
            resolved_settings.app_update_registry_path,
        ),
        release_client=HttpGitHubReleaseClient(
            token=resolved_settings.app_update_github_token,
            timeout_seconds=resolved_settings.app_update_github_timeout_seconds,
        ),
        registry_path=resolved_settings.app_update_registry_path,
    )
    sdd_project_service = SddProjectService(
        projects_root=resolved_settings.projects_root,
        workspace_aliases=resolved_settings.feedback_source_workspace_alias_map,
        file_max_bytes=resolved_settings.sdd_file_max_bytes,
    )
    sdd_workbench_view_service = SddWorkbenchViewService()
    sdd_codex_job_service = SddCodexJobService(
        projects_root=resolved_settings.projects_root,
        workspace_aliases=resolved_settings.feedback_source_workspace_alias_map,
        codex_command=resolved_settings.codex_command,
        timeout_seconds=resolved_settings.execution_timeout_seconds,
    )
    project_factory_service = ProjectFactoryService(
        projects_root=resolved_settings.projects_root,
        reference_asset_storage_root=(
            resolved_settings.project_factory_reference_asset_dir
        ),
        asset_depot_service=asset_depot_service,
        max_reference_asset_bytes=resolved_settings.image_max_upload_bytes,
        state_root=resolved_settings.project_factory_state_dir,
        codex_command=resolved_settings.codex_command,
        timeout_seconds=resolved_settings.project_factory_step_timeout_seconds,
        generator_runs_override=(
            resolved_settings.project_factory_generator_runs_override
        ),
        reviewer_runs_override=(
            resolved_settings.project_factory_reviewer_runs_override
        ),
        run_generated_validation=(
            resolved_settings.project_factory_run_generated_validation
        ),
        publication_validation_mode=(
            resolved_settings.project_factory_publication_validation_mode
        ),
        async_jobs=resolved_settings.project_factory_async_jobs,
    )
    cloudflare_preview_doctor_service = CloudflarePreviewDoctorService(
        settings=resolved_settings,
    )
    web_preview_deploy_service = WebPreviewDeployService(
        settings=resolved_settings,
    )
    web_preview_invite_service = WebPreviewInviteService(
        settings=resolved_settings,
        preview_service=web_preview_deploy_service,
    )
    return AppContainer(
        settings=resolved_settings,
        message_service=message_service,
        feedback_queue_service=feedback_queue_service,
        asset_depot_service=asset_depot_service,
        app_update_service=app_update_service,
        sdd_project_service=sdd_project_service,
        sdd_workbench_view_service=sdd_workbench_view_service,
        sdd_codex_job_service=sdd_codex_job_service,
        project_factory_service=project_factory_service,
        cloudflare_preview_doctor_service=cloudflare_preview_doctor_service,
        web_preview_deploy_service=web_preview_deploy_service,
        web_preview_invite_service=web_preview_invite_service,
        job_stream_hub=job_stream_hub,
        audio_transcriber=audio_transcriber,
        speech_synthesizer=speech_synthesizer,
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
        streaming_mode=settings.codex_streaming_mode,
        exec_args=settings.codex_exec_args,
        resume_args=settings.codex_resume_args,
        default_reasoning_effort=settings.codex_reasoning_effort,
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


def _build_speech_synthesizer(settings: Settings) -> SpeechSynthesizer:
    if settings.speech_synthesis_backend == "openai":
        return OpenAISpeechSynthesizer(
            api_key=settings.openai_api_key,
            model=settings.speech_synthesis_model,
            voice=settings.speech_synthesis_voice,
            response_format=settings.speech_synthesis_response_format,
            instructions=settings.speech_synthesis_instructions,
            base_url=settings.openai_base_url,
            timeout_seconds=settings.speech_synthesis_timeout_seconds,
        )

    if settings.speech_synthesis_backend == "kokoro":
        return KokoroSpeechSynthesizer(
            lang_code=settings.speech_synthesis_kokoro_lang_code,
            voice=settings.speech_synthesis_kokoro_voice,
            speed=settings.speech_synthesis_kokoro_speed,
            split_pattern=settings.speech_synthesis_kokoro_split_pattern,
            sample_rate=settings.speech_synthesis_kokoro_sample_rate,
            response_format=settings.speech_synthesis_response_format,
        )

    return DisabledSpeechSynthesizer()
