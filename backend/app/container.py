from __future__ import annotations

from dataclasses import dataclass

from backend.app.application.services.message_service import MessageService
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.execution.base import ExecutionProvider
from backend.app.infrastructure.execution.lambda_provider import LambdaExecutionProvider
from backend.app.infrastructure.execution.local_provider import LocalExecutionProvider
from backend.app.infrastructure.persistence.in_memory_chat_repository import InMemoryChatRepository
from backend.app.infrastructure.realtime.job_stream_hub import JobStreamHub


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    message_service: MessageService
    job_stream_hub: JobStreamHub


def build_container(settings: Settings | None = None) -> AppContainer:
    resolved_settings = settings or Settings()
    repository = InMemoryChatRepository(projects_root=resolved_settings.projects_root)
    provider = _build_execution_provider(resolved_settings)
    message_service = MessageService(
        repository=repository,
        execution_provider=provider,
        default_workspace_path=resolved_settings.codex_workdir,
    )
    job_stream_hub = JobStreamHub(
        poll_interval_seconds=resolved_settings.poll_interval_seconds,
    )
    return AppContainer(
        settings=resolved_settings,
        message_service=message_service,
        job_stream_hub=job_stream_hub,
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
