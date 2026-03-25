from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
from typing import Literal
from uuid import uuid4
import xml.etree.ElementTree as ET
import zipfile

from backend.app.domain.entities.chat_message import (
    can_launch_reserved_follow_up,
    ChatMessageAuthorType,
    ChatMessage,
    ChatMessageReasonCode,
    is_follow_up_terminal_failure,
    is_follow_up_waiting_status,
    orphaned_follow_up_resolution_status,
    MessageRecoveryAction,
    ChatMessageRole,
    ChatMessageStatus,
    validate_manual_recovery_candidate,
)
from backend.app.domain.entities.agent_configuration import (
    AgentConfiguration,
    AgentDisplayMode,
    AgentId,
    AgentPreset,
    AgentTriggerSource,
    AgentType,
    AgentVisibilityMode,
    SUPERVISOR_MEMBER_AGENT_IDS,
    TurnBudgetMode,
    normalize_agent_enum_value,
)
from backend.app.domain.entities.agent_profile import (
    AgentProfile,
    builtin_agent_profiles,
    builtin_agent_profiles_by_id,
)
from backend.app.domain.entities.agent_run import AgentRun
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.job import Job, JobConversationKind, JobStatus
from backend.app.domain.entities.workspace import Workspace
from backend.app.domain.repositories.chat_repository import (
    ChatRepository,
    PersistenceDiagnosticIssue,
)
from backend.app.infrastructure.execution.base import ExecutionProvider
from backend.app.infrastructure.execution.base import ExecutionSnapshot
from backend.app.infrastructure.transcription.base import AudioTranscriber, AudioTranscriptionError


DocumentKind = Literal["audio", "docx", "image", "text"]

_AUDIO_SUFFIXES = {
    ".aac",
    ".flac",
    ".m4a",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".ogg",
    ".opus",
    ".wav",
    ".webm",
}
_IMAGE_SUFFIXES = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
_TEXT_SUFFIXES = {
    ".c",
    ".cc",
    ".cfg",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".env",
    ".go",
    ".graphql",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".log",
    ".lua",
    ".md",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

_RESERVED_MESSAGE_SUPERSEDED_REASON = (
    "Superseded by a newer user turn before the follow-up job was created."
)
_RESERVED_MESSAGE_STALE_REASON = (
    "This reserved follow-up no longer belongs to the active run."
)
_SUBMISSION_UNKNOWN_REASON = (
    "The backend lost the durable job record after provider submission was attempted. "
    "Automatic recovery stopped to avoid duplicate provider execution."
)
_SUBMISSION_UNKNOWN_SUPERSEDED_REASON = (
    "A newer user turn superseded this follow-up after provider submission was attempted, "
    "so automatic recovery stopped to avoid duplicate execution."
)

class DocumentProcessingError(RuntimeError):
    pass


class UnsupportedDocumentError(DocumentProcessingError):
    pass


@dataclass(slots=True)
class AudioSubmission:
    job: Job
    transcript: str


@dataclass(slots=True)
class DocumentSubmission:
    job: Job
    document_kind: DocumentKind
    attached_document_name: str
    transcript: str | None = None
    extracted_text_preview: str | None = None


@dataclass(slots=True, frozen=True)
class FollowUpContext:
    display_message: str
    execution_message: str
    user_message_id: str | None
    conversation_kind: JobConversationKind
    agent_id: AgentId
    agent_type: AgentType
    trigger_source: AgentTriggerSource


@dataclass(slots=True, frozen=True)
class SupervisorDecision:
    status: str
    plan: tuple[str, ...]
    next_agent_id: AgentId | None
    instruction: str
    user_response: str

    @property
    def is_complete(self) -> bool:
        return self.status == "complete"


@dataclass(slots=True)
class AttachmentInput:
    path: str
    filename: str | None = None
    content_type: str | None = None


@dataclass(slots=True)
class _TerminalJobLockEntry:
    lock: threading.Lock
    users: int = 0


class MessageService:
    def __init__(
        self,
        *,
        repository: ChatRepository,
        execution_provider: ExecutionProvider,
        default_workspace_path: str,
        audio_transcriber: AudioTranscriber,
        document_text_char_limit: int = 20_000,
        title_generation_model: str | None = None,
    ) -> None:
        self._repository = repository
        self._execution_provider = execution_provider
        self._default_workspace_path = str(Path(default_workspace_path).resolve())
        self._audio_transcriber = audio_transcriber
        self._document_text_char_limit = document_text_char_limit
        self._title_generation_model = (title_generation_model or "").strip() or None
        self._retry_asset_root = Path(tempfile.gettempdir()) / "codex-remote-retry-assets"
        self._retry_asset_root.mkdir(parents=True, exist_ok=True)
        self._job_monitor_lock = threading.RLock()
        self._job_monitor_unsubscribes: dict[str, Callable[[], None] | None] = {}
        self._terminal_job_lock_guard = threading.RLock()
        self._terminal_job_locks: dict[str, _TerminalJobLockEntry] = {}

    def create_session(
        self,
        *,
        title: str | None = None,
        workspace_path: str | None = None,
        agent_profile_id: str | None = None,
        title_is_placeholder: bool | None = None,
    ) -> ChatSession:
        workspace = self._resolve_workspace(workspace_path)
        profile = self.get_agent_profile(agent_profile_id or "default")
        configuration = self._profile_configuration_for_session(profile)
        resolved_title = title or profile.name
        session = ChatSession(
            id=str(uuid4()),
            title=resolved_title,
            workspace_path=workspace.path,
            workspace_name=workspace.name,
            title_is_placeholder=(
                title_is_placeholder if title_is_placeholder is not None else title is None
            ),
            agent_profile_id=profile.id,
            agent_profile_name=profile.name,
            agent_profile_color=profile.color_hex,
            agent_configuration=configuration.normalized(),
        )
        self._repository.save_session(session)
        return session

    def list_sessions(self) -> list[ChatSession]:
        return self._repository.list_sessions()

    def list_agent_profiles(self) -> list[AgentProfile]:
        builtins = builtin_agent_profiles_by_id()
        profiles = {
            profile.id: profile
            for profile in builtin_agent_profiles()
        }
        for profile in self._repository.list_agent_profiles():
            normalized = profile.normalized()
            if normalized.id in builtins:
                continue
            profiles[normalized.id] = normalized
        return sorted(
            profiles.values(),
            key=lambda profile: (0 if profile.is_builtin else 1, profile.name.lower(), profile.id),
        )

    def get_agent_profile(self, profile_id: str) -> AgentProfile:
        builtins = builtin_agent_profiles_by_id()
        if profile_id in builtins:
            return builtins[profile_id]
        profile = self._repository.get_agent_profile(profile_id)
        if profile is None:
            raise ValueError(f"Agent profile {profile_id} was not found.")
        return profile.normalized()

    def create_agent_profile(
        self,
        *,
        name: str,
        description: str,
        color_hex: str,
        configuration: AgentConfiguration,
    ) -> AgentProfile:
        profile = AgentProfile(
            id=str(uuid4()),
            name=name,
            description=description,
            color_hex=color_hex,
            prompt=configuration.normalized().agents[AgentId.GENERATOR].prompt,
            configuration=self._profile_configuration_for_storage(configuration),
        ).normalized()
        self._repository.save_agent_profile(profile)
        return profile

    def export_agent_profiles(self) -> list[AgentProfile]:
        builtin_ids = set(builtin_agent_profiles_by_id())
        return [
            profile.normalized()
            for profile in self._repository.list_agent_profiles()
            if profile.normalized().id not in builtin_ids
        ]

    def import_agent_profiles(
        self,
        *,
        profiles: list[AgentProfile],
    ) -> list[AgentProfile]:
        imported_profiles: list[AgentProfile] = []
        builtin_ids = builtin_agent_profiles_by_id().keys()
        for profile in profiles:
            normalized = profile.normalized()
            if normalized.is_builtin or normalized.id in builtin_ids:
                raise ValueError("Built-in agent profiles are immutable and cannot be imported.")
            self._repository.save_agent_profile(normalized)
            imported_profiles.append(normalized)
        return imported_profiles

    def apply_agent_profile_to_session(
        self,
        *,
        session_id: str,
        profile_id: str,
    ) -> ChatSession:
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} was not found.")
        self._ensure_session_can_be_reconfigured(session)

        profile = self.get_agent_profile(profile_id)
        session.agent_configuration = self._profile_configuration_for_session(profile)
        session.agent_profile_id = profile.id
        session.agent_profile_name = profile.name
        session.agent_profile_color = profile.color_hex
        session.auto_turn_index = 0
        session.active_agent_turn_index = 0
        session.active_agent_run_id = None
        session.touch()
        self._repository.save_session(session)
        return session

    def list_workspaces(self) -> list[Workspace]:
        return self._repository.list_workspaces()

    def validate_persistence_integrity(self) -> list[PersistenceDiagnosticIssue]:
        return self._repository.validate_integrity()

    def is_persistence_available(self) -> bool:
        return self._repository.is_available()

    def persistence_startup_issue(self) -> PersistenceDiagnosticIssue | None:
        return self._repository.startup_issue()

    def get_session(self, session_id: str) -> ChatSession | None:
        session = self._repository.get_session(session_id)
        if session is None:
            return None
        self._reconcile_reserved_follow_ups(session)
        return self._repository.get_session(session_id) or session

    def set_session_archived(
        self,
        *,
        session_id: str,
        archived: bool,
    ) -> ChatSession:
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} was not found.")
        session.archived_at = session.updated_at if archived else None
        session.touch()
        if archived:
            session.archived_at = session.updated_at
        self._repository.save_session(session)
        return session

    def list_messages(self, session_id: str) -> list[ChatMessage]:
        session = self._repository.get_session(session_id)
        if session is not None:
            self._reconcile_reserved_follow_ups(session)
        return self._repository.list_messages(session_id)

    def update_agent_configuration(
        self,
        *,
        session_id: str,
        configuration: AgentConfiguration,
    ) -> ChatSession:
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} was not found.")
        self._ensure_session_can_be_reconfigured(session)

        session.agent_configuration = configuration.normalized()
        session.auto_turn_index = 0
        session.active_agent_turn_index = 0
        session.active_agent_run_id = None
        session.touch()
        self._repository.save_session(session)
        return session

    def _profile_configuration_for_storage(
        self,
        configuration: AgentConfiguration,
    ) -> AgentConfiguration:
        normalized = configuration.normalized()
        sanitized_agents = {
            agent_id: definition.normalized()
            for agent_id, definition in normalized.agents.items()
        }
        for definition in sanitized_agents.values():
            definition.provider_session_id = None
        return AgentConfiguration(
            preset=normalized.preset,
            display_mode=normalized.display_mode,
            turn_budget_mode=normalized.turn_budget_mode,
            agents=sanitized_agents,
            supervisor_member_ids=normalized.supervisor_member_ids,
        ).normalized()

    def _run_configuration_snapshot(
        self,
        configuration: AgentConfiguration,
    ) -> AgentConfiguration:
        return self._profile_configuration_for_storage(configuration)

    def _profile_configuration_for_session(
        self,
        profile: AgentProfile,
    ) -> AgentConfiguration:
        return self._profile_configuration_for_storage(
            profile.resolved_configuration(),
        )

    def update_auto_mode(
        self,
        *,
        session_id: str,
        enabled: bool,
        max_turns: int,
        reviewer_prompt: str | None,
    ) -> ChatSession:
        session = self.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} was not found.")
        self._ensure_session_can_be_reconfigured(session)

        configuration = session.agent_configuration.normalized()
        configuration.preset = AgentPreset.REVIEW if enabled else AgentPreset.SOLO
        configuration.agents[AgentId.REVIEWER].enabled = enabled
        configuration.agents[AgentId.REVIEWER].max_turns = max(0, max_turns)
        if reviewer_prompt is not None:
            configuration.agents[AgentId.REVIEWER].prompt = reviewer_prompt.strip()
        configuration.agents[AgentId.SUMMARY].enabled = False
        configuration.agents[AgentId.SUMMARY].max_turns = 0
        return self.update_agent_configuration(
            session_id=session_id,
            configuration=configuration,
        )

    def _ensure_session_can_be_reconfigured(
        self,
        session: ChatSession,
    ) -> None:
        if session.active_agent_run_id:
            raise RuntimeError(
                "Cannot change the session agent profile or configuration while work is in flight."
            )

        in_flight_statuses = {
            ChatMessageStatus.RESERVED,
            ChatMessageStatus.SUBMISSION_PENDING,
            ChatMessageStatus.PENDING,
        }
        has_in_flight_messages = any(
            message.status in in_flight_statuses
            for message in self._repository.list_messages(session.id)
        )
        if has_in_flight_messages:
            raise RuntimeError(
                "Cannot change the session agent profile or configuration while work is in flight."
            )

    def submit_message(
        self,
        message: str,
        session_id: str | None = None,
        workspace_path: str | None = None,
        image_paths: list[str] | None = None,
        cleanup_paths: list[str] | None = None,
        execution_message: str | None = None,
        *,
        author_type: ChatMessageAuthorType = ChatMessageAuthorType.HUMAN,
        agent_id: AgentId = AgentId.USER,
        agent_type: AgentType = AgentType.HUMAN,
        agent_label: str | None = None,
        visibility: AgentVisibilityMode = AgentVisibilityMode.VISIBLE,
        trigger_source: AgentTriggerSource = AgentTriggerSource.USER,
        run_id: str | None = None,
        conversation_kind: JobConversationKind = JobConversationKind.PRIMARY,
    ) -> Job:
        session = self._resolve_session(
            message=message,
            session_id=session_id,
            workspace_path=workspace_path,
        )
        current_configuration = session.agent_configuration.normalized()
        agent_run: AgentRun | None = None
        self._cancel_reserved_follow_ups_for_inactive_runs(session)
        if conversation_kind == JobConversationKind.PRIMARY and author_type == ChatMessageAuthorType.HUMAN:
            if session.active_agent_run_id:
                self._cancel_reserved_follow_ups_for_run(
                    session,
                    run_id=session.active_agent_run_id,
                    reason=_RESERVED_MESSAGE_SUPERSEDED_REASON,
                )
            run_id = str(uuid4())
            session.active_agent_run_id = run_id
            session.active_agent_turn_index = 0
            session.auto_turn_index = 0
            agent_run = AgentRun(
                run_id=run_id,
                session_id=session.id,
                configuration=self._run_configuration_snapshot(current_configuration),
            )

        resolved_run_id = run_id or session.active_agent_run_id or str(uuid4())
        entry_agent_id = self._entry_agent_for_configuration(current_configuration)
        entry_agent_definition = current_configuration.agents[entry_agent_id]
        if conversation_kind == JobConversationKind.PRIMARY:
            if entry_agent_id == AgentId.SUPERVISOR:
                execution_message = self._build_supervisor_execution_message(
                    supervisor_prompt=entry_agent_definition.prompt,
                    user_prompt=execution_message or message,
                    supervisor_member_ids=current_configuration.supervisor_member_ids,
                    trigger_source=trigger_source,
                )
            else:
                execution_message = self._build_generator_execution_message(
                    generator_prompt=entry_agent_definition.prompt,
                    user_prompt=execution_message or message,
                    trigger_source=trigger_source,
                )

        user_message = ChatMessage(
            id=str(uuid4()),
            session_id=session.id,
            role=ChatMessageRole.USER,
            author_type=author_type,
            agent_id=agent_id,
            agent_type=agent_type,
            agent_label=agent_label,
            visibility=visibility,
            trigger_source=trigger_source,
            run_id=resolved_run_id,
            content=message,
            status=ChatMessageStatus.COMPLETED,
        )
        assistant_message = ChatMessage(
            id=str(uuid4()),
            session_id=session.id,
            role=ChatMessageRole.ASSISTANT,
            author_type=ChatMessageAuthorType.ASSISTANT,
            agent_id=entry_agent_id,
            agent_type=entry_agent_definition.agent_type,
            agent_label=entry_agent_definition.label,
            visibility=entry_agent_definition.visibility,
            trigger_source=trigger_source,
            run_id=resolved_run_id,
            content="",
            status=ChatMessageStatus.PENDING,
        )

        job = self._start_job(
            session=session,
            display_message=message,
            execution_message=execution_message or message,
            image_paths=image_paths,
            cleanup_paths=cleanup_paths,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
            provider_session_id=self._provider_session_id_for_agent(
                session,
                entry_agent_id,
            ),
            model=self._model_for_agent(session, entry_agent_id),
            serial_key=self._serial_key_for_agent(session.id, entry_agent_id),
            conversation_kind=conversation_kind,
            agent_id=entry_agent_id,
            agent_type=entry_agent_definition.agent_type,
            trigger_source=trigger_source,
            run_id=resolved_run_id,
        )
        assistant_message.sync(job_id=job.id)
        session.touch()

        self._repository.save_turn(
            session,
            messages=[user_message, assistant_message],
            job=job,
            agent_run=agent_run,
        )
        self._register_background_job_watch(job.id)
        self._maybe_finalize_session_title(session.id)
        return job

    def list_agent_runs(self, session_id: str) -> list[AgentRun]:
        return self._repository.list_agent_runs(session_id)

    def submit_audio_message(
        self,
        audio_path: str,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        session_id: str | None = None,
        workspace_path: str | None = None,
        language: str | None = None,
    ) -> AudioSubmission:
        transcript = self._audio_transcriber.transcribe(
            Path(audio_path),
            filename=filename,
            content_type=content_type,
            language=language,
        ).strip()
        if not transcript:
            raise AudioTranscriptionError("Transcription returned an empty prompt.")

        job = self.submit_message(
            transcript,
            session_id=session_id,
            workspace_path=workspace_path,
        )
        return AudioSubmission(job=job, transcript=transcript)

    def submit_document_message(
        self,
        document_path: str,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        message: str | None = None,
        session_id: str | None = None,
        workspace_path: str | None = None,
        language: str | None = None,
    ) -> DocumentSubmission:
        resolved_path = Path(document_path)
        attached_document_name = filename or resolved_path.name
        document_kind = self._classify_document(
            filename=attached_document_name,
            content_type=content_type,
        )
        display_message = self._build_document_display_message(
            message=message,
            document_kind=document_kind,
            document_name=attached_document_name,
        )
        cleanup_paths = [str(resolved_path)]

        if document_kind == "image":
            prompt = (message or "").strip() or "Please analyze the attached document image."
            job = self.submit_message(
                display_message,
                session_id=session_id,
                workspace_path=workspace_path,
                image_paths=[str(resolved_path)],
                cleanup_paths=cleanup_paths,
                execution_message=prompt,
            )
            return DocumentSubmission(
                job=job,
                document_kind=document_kind,
                attached_document_name=attached_document_name,
            )

        if document_kind == "audio":
            transcript = self._audio_transcriber.transcribe(
                resolved_path,
                filename=attached_document_name,
                content_type=content_type,
                language=language,
            ).strip()
            if not transcript:
                raise AudioTranscriptionError("Transcription returned an empty prompt.")

            prompt = self._build_document_execution_message(
                message=message,
                document_kind=document_kind,
                document_name=attached_document_name,
                content_label="Transcript",
                content=transcript,
            )
            job = self.submit_message(
                display_message,
                session_id=session_id,
                workspace_path=workspace_path,
                cleanup_paths=cleanup_paths,
                execution_message=prompt,
            )
            return DocumentSubmission(
                job=job,
                document_kind=document_kind,
                attached_document_name=attached_document_name,
                transcript=transcript,
                extracted_text_preview=self._build_text_preview(transcript),
            )

        extracted_text = self._extract_document_text(
            document_path=resolved_path,
            document_kind=document_kind,
        ).strip()
        if not extracted_text:
            raise DocumentProcessingError("Document extraction returned empty text.")

        prompt = self._build_document_execution_message(
            message=message,
            document_kind=document_kind,
            document_name=attached_document_name,
            content_label="Extracted document text",
            content=extracted_text,
        )
        job = self.submit_message(
            display_message,
            session_id=session_id,
            workspace_path=workspace_path,
            cleanup_paths=cleanup_paths,
            execution_message=prompt,
        )
        return DocumentSubmission(
            job=job,
            document_kind=document_kind,
            attached_document_name=attached_document_name,
            extracted_text_preview=self._build_text_preview(extracted_text),
        )

    def submit_attachment_message(
        self,
        attachments: list[AttachmentInput],
        *,
        message: str | None = None,
        session_id: str | None = None,
        workspace_path: str | None = None,
        language: str | None = None,
    ) -> Job:
        if not attachments:
            raise ValueError("At least one attachment is required.")

        cleanup_paths: list[str] = []
        image_paths: list[str] = []
        attachment_summaries: list[str] = []
        attachment_details: list[str] = []

        for index, attachment in enumerate(attachments, start=1):
            resolved_path = Path(attachment.path)
            attached_name = attachment.filename or resolved_path.name
            document_kind = self._classify_document(
                filename=attached_name,
                content_type=attachment.content_type,
            )
            cleanup_paths.append(str(resolved_path))
            attachment_summaries.append(f"- {document_kind}: {attached_name}")

            if document_kind == "image":
                image_paths.append(str(resolved_path))
                continue

            if document_kind == "audio":
                transcript = self._audio_transcriber.transcribe(
                    resolved_path,
                    filename=attached_name,
                    content_type=attachment.content_type,
                    language=language,
                ).strip()
                if not transcript:
                    raise AudioTranscriptionError("Transcription returned an empty prompt.")
                attachment_details.append(
                    self._build_attachment_detail_section(
                        index=index,
                        document_kind=document_kind,
                        document_name=attached_name,
                        content_label="Transcript",
                        content=transcript,
                    )
                )
                continue

            extracted_text = self._extract_document_text(
                document_path=resolved_path,
                document_kind=document_kind,
            ).strip()
            if not extracted_text:
                raise DocumentProcessingError("Document extraction returned empty text.")
            attachment_details.append(
                self._build_attachment_detail_section(
                    index=index,
                    document_kind=document_kind,
                    document_name=attached_name,
                    content_label="Extracted document text",
                    content=extracted_text,
                )
            )

        display_message = self._build_attachment_batch_display_message(
            message=message,
            attachment_summaries=attachment_summaries,
        )
        execution_message = self._build_attachment_batch_execution_message(
            message=message,
            attachment_summaries=attachment_summaries,
            attachment_details=attachment_details,
            image_count=len(image_paths),
        )
        return self.submit_message(
            display_message,
            session_id=session_id,
            workspace_path=workspace_path,
            image_paths=image_paths or None,
            cleanup_paths=cleanup_paths,
            execution_message=execution_message,
        )

    def cancel_job(self, job_id: str) -> Job:
        job = self.get_job(job_id)
        if job is None:
            raise ValueError(f"Job {job_id} was not found.")

        if job.status.is_terminal:
            return job

        if not self._execution_provider.cancel_job(job_id):
            raise RuntimeError("This backend cannot cancel the requested job.")

        cancelled_job = self.get_job(job_id)
        return cancelled_job or job

    def retry_job(self, job_id: str) -> Job:
        original_job = self.get_job(job_id)
        if original_job is None:
            raise ValueError(f"Job {job_id} was not found.")
        if not original_job.status.is_terminal:
            raise RuntimeError("Only terminal jobs can be retried.")

        session = self._repository.get_session(original_job.session_id)
        if session is None:
            raise ValueError(f"Session {original_job.session_id} was not found.")
        if original_job.assistant_message_id is None:
            raise RuntimeError("This job cannot be retried because its assistant turn is missing.")

        assistant_message = self._repository.get_message(original_job.assistant_message_id)
        if assistant_message is None:
            raise RuntimeError("This job cannot be retried because its assistant turn was not found.")

        retried_job = self._start_job(
            session=session,
            display_message=original_job.message,
            execution_message=original_job.execution_message or original_job.message,
            image_paths=original_job.image_paths,
            cleanup_paths=None,
            user_message_id=original_job.user_message_id,
            assistant_message_id=assistant_message.id,
            provider_session_id=self._provider_session_id_for_agent(
                session,
                original_job.agent_id,
            ),
            model=self._model_for_agent(session, original_job.agent_id),
            serial_key=self._serial_key_for_agent(
                session.id,
                original_job.agent_id,
            ),
            conversation_kind=original_job.conversation_kind,
            agent_id=original_job.agent_id,
            agent_type=original_job.agent_type,
            trigger_source=original_job.trigger_source,
            run_id=original_job.run_id,
        )

        assistant_message.sync(
            content="",
            status=ChatMessageStatus.PENDING,
            job_id=retried_job.id,
            agent_label=assistant_message.agent_label,
        )
        session.touch()

        self._repository.save_turn(
            session,
            messages=[assistant_message],
            job=retried_job,
        )
        self._register_background_job_watch(retried_job.id)
        return retried_job

    def recover_submission_unknown_message(
        self,
        *,
        session_id: str,
        message_id: str,
        action: MessageRecoveryAction,
    ) -> ChatSession:
        session = self._repository.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} was not found.")

        message = self._repository.get_message(message_id)
        if message is None or message.session_id != session_id:
            raise ValueError(f"Message {message_id} was not found.")
        validate_manual_recovery_candidate(message)

        if action == MessageRecoveryAction.CANCEL:
            message.sync(
                status=ChatMessageStatus.CANCELLED,
                reason_code=ChatMessageReasonCode.MANUAL_CANCEL_REQUESTED,
                recovery_action=MessageRecoveryAction.CANCEL,
                content=self._append_recovery_note(
                    message.content,
                    "Operator cancelled this uncertain follow-up.",
                ),
            )
            self._repository.save_message(message)
            self._complete_follow_up_run_after_manual_resolution(
                session=session,
                message=message,
            )
            return self._repository.get_session(session_id) or session

        if session.active_agent_run_id not in {None, message.run_id}:
            raise RuntimeError("Finish the current active run before retrying this uncertain follow-up.")

        context = self._build_follow_up_context(
            session=session,
            message=message,
        )
        if context is None:
            raise RuntimeError("This uncertain follow-up cannot be retried because its source context is no longer available.")

        retry_message = ChatMessage(
            id=str(uuid4()),
            session_id=session.id,
            role=message.role,
            author_type=message.author_type,
            content="",
            status=ChatMessageStatus.RESERVED,
            agent_id=message.agent_id,
            agent_type=message.agent_type,
            agent_label=message.agent_label,
            visibility=message.visibility,
            trigger_source=message.trigger_source,
            run_id=message.run_id,
            dedupe_key=self._next_manual_retry_dedupe_key(message),
            reason_code=ChatMessageReasonCode.MANUAL_RETRY_REQUESTED,
            recovered_from_message_id=message.id,
            recovery_action=MessageRecoveryAction.RETRY,
        )
        retry_message = self._repository.reserve_message(retry_message)
        if retry_message.job_id is not None:
            raise RuntimeError("The manual retry was already created.")

        message.sync(
            status=ChatMessageStatus.CANCELLED,
            reason_code=ChatMessageReasonCode.MANUAL_RETRY_REQUESTED,
            recovery_action=MessageRecoveryAction.RETRY,
            superseded_by_message_id=retry_message.id,
            content=self._append_recovery_note(
                message.content,
                f"Operator retried this uncertain follow-up as message {retry_message.id}.",
            ),
        )
        session.active_agent_run_id = message.run_id
        session.touch()
        self._repository.save_turn(
            session,
            messages=[message, retry_message],
        )
        self._launch_reserved_follow_up(
            session=session,
            message=retry_message,
            display_message=context.display_message,
            execution_message=context.execution_message,
            user_message_id=context.user_message_id,
            conversation_kind=context.conversation_kind,
            agent_id=context.agent_id,
            agent_type=context.agent_type,
            trigger_source=context.trigger_source,
            run_id=message.run_id or "",
        )
        return self._repository.get_session(session_id) or session

    def get_job(self, job_id: str) -> Job | None:
        job = self._repository.get_job(job_id)
        if job is None:
            return None

        if job.status.is_terminal:
            if not job.auto_chain_processed:
                return self._sync_terminal_job_side_effects(job.id) or job
            return job

        if not self._execution_provider.has_job(job_id):
            job.sync(
                status=JobStatus.FAILED,
                error="The backend restarted before this in-flight job could be recovered.",
                phase="Failed",
                latest_activity="The backend process lost the live execution state for this job.",
            )
            self._repository.save_job(job)
            return self._sync_terminal_job_side_effects(job.id) or job

        snapshot = self._execution_provider.get_snapshot(job_id)
        job.sync(
            status=snapshot.status,
            response=snapshot.response,
            error=snapshot.error,
            provider_session_id=snapshot.provider_session_id,
            phase=snapshot.phase,
            latest_activity=snapshot.latest_activity,
        )
        self._repository.save_job(job)
        if job.status.is_terminal:
            return self._sync_terminal_job_side_effects(job.id) or job
        self._sync_job_side_effects(job)
        return job

    def watch_job(
        self,
        job_id: str,
        on_change: Callable[[ExecutionSnapshot], None],
    ) -> Callable[[], None] | None:
        if self._repository.get_job(job_id) is None:
            return None
        return self._execution_provider.watch_job(job_id, on_change)

    def supports_job_cancellation(self) -> bool:
        return self._execution_provider.supports_job_cancellation()

    def supports_job_retry(self) -> bool:
        return True

    def _start_job(
        self,
        *,
        session: ChatSession,
        display_message: str,
        execution_message: str,
        image_paths: list[str] | None,
        cleanup_paths: list[str] | None,
        user_message_id: str | None,
        assistant_message_id: str | None,
        provider_session_id: str | None,
        model: str | None,
        serial_key: str,
        conversation_kind: JobConversationKind,
        agent_id: AgentId,
        agent_type: AgentType,
        trigger_source: AgentTriggerSource,
        run_id: str | None,
        submission_token: str | None = None,
    ) -> Job:
        retryable_image_paths = self._persist_retryable_image_paths(image_paths)
        job_id = self._execution_provider.execute(
            execution_message,
            image_paths=retryable_image_paths or None,
            cleanup_paths=cleanup_paths,
            provider_session_id=provider_session_id,
            model=model,
            serial_key=serial_key,
            submission_token=submission_token,
            workdir=session.workspace_path,
        )
        return Job(
            id=job_id,
            session_id=session.id,
            message=display_message,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            provider_session_id=provider_session_id,
            conversation_kind=conversation_kind,
            agent_id=agent_id,
            agent_type=agent_type,
            trigger_source=trigger_source,
            run_id=run_id,
            submission_token=submission_token,
            execution_message=execution_message,
            image_paths=retryable_image_paths,
        )

    def _persist_retryable_image_paths(
        self,
        image_paths: list[str] | None,
    ) -> list[str]:
        if not image_paths:
            return []

        persisted_paths: list[str] = []
        for image_path in image_paths:
            source = Path(image_path)
            extension = source.suffix or ".bin"
            destination = self._retry_asset_root / f"{uuid4()}{extension}"
            shutil.copy2(source, destination)
            persisted_paths.append(str(destination))
        return persisted_paths

    def _resolve_session(
        self,
        *,
        message: str,
        session_id: str | None,
        workspace_path: str | None,
    ) -> ChatSession:
        if session_id:
            session = self._repository.get_session(session_id)
            if session is None:
                raise ValueError(f"Session {session_id} was not found.")
            return session

        session = self.create_session(
            title=self._derive_title(message),
            workspace_path=workspace_path,
            title_is_placeholder=True,
        )
        return session

    def _sync_job_side_effects(self, job: Job) -> None:
        session = self._repository.get_session(job.session_id)
        if session and job.provider_session_id:
            configuration = session.agent_configuration.normalized()
            definition = configuration.agents.get(job.agent_id)
            if definition is not None and definition.provider_session_id != job.provider_session_id:
                definition.provider_session_id = job.provider_session_id
                session.agent_configuration = configuration
            if job.agent_id == AgentId.GENERATOR:
                session.provider_session_id = job.provider_session_id
            elif job.agent_id == AgentId.REVIEWER:
                session.reviewer_provider_session_id = job.provider_session_id
            if definition is not None or job.agent_id in {AgentId.GENERATOR, AgentId.REVIEWER}:
                session.touch()
                self._repository.save_session(session)

        if job.assistant_message_id is None:
            return

        assistant_message = self._repository.get_message(job.assistant_message_id)
        if assistant_message is None:
            return

        if job.status == JobStatus.COMPLETED:
            completed_content = job.response or ""
            if job.agent_id == AgentId.SUPERVISOR:
                decision = self._parse_supervisor_decision(completed_content)
                if decision is not None:
                    completed_content = self._format_supervisor_message_content(decision)
            assistant_message.sync(
                content=completed_content,
                status=ChatMessageStatus.COMPLETED,
                job_id=job.id,
            )
        elif job.status == JobStatus.CANCELLED:
            assistant_message.sync(
                content=job.error or "Execution cancelled.",
                status=ChatMessageStatus.CANCELLED,
                job_id=job.id,
            )
        elif job.status == JobStatus.FAILED:
            assistant_message.sync(
                content=job.error or "Execution failed.",
                status=ChatMessageStatus.FAILED,
                job_id=job.id,
            )
        else:
            assistant_message.sync(
                status=ChatMessageStatus.PENDING,
                job_id=job.id,
            )

        self._repository.save_message(assistant_message)

        if session and job.status.is_terminal:
            session.touch()
            self._repository.save_session(session)

    def _sync_terminal_job_side_effects(self, job_id: str) -> Job | None:
        entry = self._acquire_terminal_job_lock(job_id)
        try:
            with entry.lock:
                job = self._repository.get_job(job_id)
                if job is None:
                    return None
                self._sync_job_side_effects(job)
                if not job.auto_chain_processed:
                    session = self._repository.get_session(job.session_id)
                    if session is not None:
                        if job.status == JobStatus.COMPLETED:
                            self._maybe_continue_agent_chain(session=session, job=job)
                        elif job.run_id:
                            self._complete_agent_run(
                                session=session,
                                run_id=job.run_id,
                                completed_turn_index=self._completed_turn_index_for_run(
                                    session,
                                    run_id=job.run_id,
                                ),
                            )
                    job.auto_chain_processed = True
                    self._repository.save_job(job)
                return self._repository.get_job(job_id) or job
        finally:
            self._release_terminal_job_lock(job_id, entry)

    def _acquire_terminal_job_lock(self, job_id: str) -> _TerminalJobLockEntry:
        with self._terminal_job_lock_guard:
            entry = self._terminal_job_locks.get(job_id)
            if entry is None:
                entry = _TerminalJobLockEntry(lock=threading.Lock())
                self._terminal_job_locks[job_id] = entry
            entry.users += 1
            return entry

    def _release_terminal_job_lock(
        self,
        job_id: str,
        entry: _TerminalJobLockEntry,
    ) -> None:
        with self._terminal_job_lock_guard:
            current = self._terminal_job_locks.get(job_id)
            if current is not entry:
                return
            entry.users -= 1
            if entry.users == 0:
                self._terminal_job_locks.pop(job_id, None)

    def _maybe_continue_agent_chain(
        self,
        *,
        session: ChatSession,
        job: Job,
    ) -> None:
        if job.status != JobStatus.COMPLETED or not job.run_id:
            return
        if session.active_agent_run_id != job.run_id:
            return
        if self._recover_submission_pending_follow_up_for_run(session, run_id=job.run_id):
            return
        if self._recover_reserved_follow_up_for_run(session, run_id=job.run_id):
            return

        configuration = session.agent_configuration.normalized()
        if configuration.preset == AgentPreset.SUPERVISOR:
            self._maybe_continue_supervisor_chain(
                session=session,
                job=job,
                configuration=configuration,
            )
            return

        generator = configuration.agents[AgentId.GENERATOR]
        reviewer = configuration.agents[AgentId.REVIEWER]
        summary = configuration.agents[AgentId.SUMMARY]

        generator_turns = self._count_agent_messages(
            session.id,
            run_id=job.run_id,
            agent_id=AgentId.GENERATOR,
        )
        reviewer_turns = self._count_agent_messages(
            session.id,
            run_id=job.run_id,
            agent_id=AgentId.REVIEWER,
        )
        summary_turns = self._count_agent_messages(
            session.id,
            run_id=job.run_id,
            agent_id=AgentId.SUMMARY,
        )

        if job.agent_id == AgentId.GENERATOR:
            next_reviewer_turn_number = reviewer_turns + 1
            reviewer_message = self._find_agent_message(
                session.id,
                run_id=job.run_id,
                agent_id=AgentId.REVIEWER,
                trigger_source=AgentTriggerSource.GENERATOR,
                role=ChatMessageRole.USER,
                dedupe_key=f"run:{job.run_id}:reviewer:{next_reviewer_turn_number}",
            )
            if reviewer.enabled and reviewer.max_turns > reviewer_turns:
                if reviewer_message is None:
                    self._start_reviewer_turn(
                        session=session,
                        run_id=job.run_id,
                        primary_response=(job.response or "").strip(),
                        reviewer_turn_number=next_reviewer_turn_number,
                    )
                    return
                if is_follow_up_waiting_status(reviewer_message.status):
                    return
                if is_follow_up_terminal_failure(reviewer_message.status):
                    self._complete_agent_run(
                        session=session,
                        run_id=job.run_id,
                        completed_turn_index=reviewer_turns,
                    )
                    return
            summary_message = self._find_agent_message(
                session.id,
                run_id=job.run_id,
                agent_id=AgentId.SUMMARY,
                role=ChatMessageRole.ASSISTANT,
            )
            if summary.enabled and summary.max_turns > summary_turns:
                if summary_message is None:
                    self._start_summary_turn(
                        session=session,
                        run_id=job.run_id,
                        trigger_source=AgentTriggerSource.GENERATOR,
                        dedupe_key=f"run:{job.run_id}:summary",
                    )
                    return
                if is_follow_up_waiting_status(summary_message.status):
                    return
            self._complete_agent_run(
                session=session,
                run_id=job.run_id,
                completed_turn_index=reviewer_turns,
            )
            return

        if job.agent_id == AgentId.REVIEWER:
            reviewer_prompt = (job.response or "").strip()
            next_generator_turn_number = generator_turns + 1
            generator_follow_up = self._find_agent_message(
                session.id,
                run_id=job.run_id,
                agent_id=AgentId.GENERATOR,
                trigger_source=AgentTriggerSource.REVIEWER,
                role=ChatMessageRole.ASSISTANT,
                dedupe_key=f"run:{job.run_id}:generator:{next_generator_turn_number}",
            )
            if reviewer_prompt and generator_turns < generator.max_turns:
                if generator_follow_up is None:
                    self._continue_generator_from_reviewer(
                        session=session,
                        run_id=job.run_id,
                        reviewer_prompt=reviewer_prompt,
                        reviewer_message_id=job.assistant_message_id,
                        generator_turn_number=next_generator_turn_number,
                    )
                    session.active_agent_turn_index = reviewer_turns
                    session.auto_turn_index = reviewer_turns
                    session.touch()
                    self._repository.save_session(session)
                    return
                if is_follow_up_waiting_status(generator_follow_up.status):
                    return
                if is_follow_up_terminal_failure(generator_follow_up.status):
                    self._complete_agent_run(
                        session=session,
                        run_id=job.run_id,
                        completed_turn_index=reviewer_turns,
                    )
                    return
            summary_message = self._find_agent_message(
                session.id,
                run_id=job.run_id,
                agent_id=AgentId.SUMMARY,
                role=ChatMessageRole.ASSISTANT,
            )
            if summary.enabled and summary.max_turns > summary_turns:
                if summary_message is None:
                    self._start_summary_turn(
                        session=session,
                        run_id=job.run_id,
                        trigger_source=AgentTriggerSource.REVIEWER,
                        dedupe_key=f"run:{job.run_id}:summary",
                    )
                    return
                if is_follow_up_waiting_status(summary_message.status):
                    return
            self._complete_agent_run(
                session=session,
                run_id=job.run_id,
                completed_turn_index=reviewer_turns,
            )
            return

        if job.agent_id == AgentId.SUMMARY:
            self._complete_agent_run(
                session=session,
                run_id=job.run_id,
                completed_turn_index=reviewer_turns,
            )

    def _maybe_continue_supervisor_chain(
        self,
        *,
        session: ChatSession,
        job: Job,
        configuration: AgentConfiguration,
    ) -> None:
        if job.agent_id == AgentId.SUPERVISOR:
            decision = self._parse_supervisor_decision(job.response or "")
            if decision is None:
                self._complete_agent_run(
                    session=session,
                    run_id=job.run_id or "",
                    completed_turn_index=self._count_agent_messages(
                        session.id,
                        run_id=job.run_id or "",
                        agent_id=AgentId.SUPERVISOR,
                    ),
                )
                return

            if decision.is_complete or decision.next_agent_id is None:
                self._complete_agent_run(
                    session=session,
                    run_id=job.run_id or "",
                    completed_turn_index=self._count_agent_messages(
                        session.id,
                        run_id=job.run_id or "",
                        agent_id=AgentId.SUPERVISOR,
                    ),
                )
                return

            specialist_id = decision.next_agent_id
            if specialist_id not in SUPERVISOR_MEMBER_AGENT_IDS:
                self._complete_agent_run(
                    session=session,
                    run_id=job.run_id or "",
                    completed_turn_index=self._count_agent_messages(
                        session.id,
                        run_id=job.run_id or "",
                        agent_id=AgentId.SUPERVISOR,
                    ),
                )
                return

            specialist = configuration.agents[specialist_id]
            specialist_turns = self._count_agent_messages(
                session.id,
                run_id=job.run_id or "",
                agent_id=specialist_id,
            )
            specialist_budget_exhausted = (
                configuration.turn_budget_mode == TurnBudgetMode.EACH_AGENT
                and specialist.max_turns <= specialist_turns
            )
            if not specialist.enabled or specialist_budget_exhausted:
                self._complete_agent_run(
                    session=session,
                    run_id=job.run_id or "",
                    completed_turn_index=self._count_agent_messages(
                        session.id,
                        run_id=job.run_id or "",
                        agent_id=AgentId.SUPERVISOR,
                    ),
                )
                return

            specialist_message = self._find_agent_message(
                session.id,
                run_id=job.run_id or "",
                agent_id=specialist_id,
                trigger_source=AgentTriggerSource.SUPERVISOR,
                role=ChatMessageRole.ASSISTANT,
                dedupe_key=f"run:{job.run_id}:{specialist_id.value}:{specialist_turns + 1}",
            )
            if specialist_message is None:
                self._start_specialist_turn(
                    session=session,
                    run_id=job.run_id or "",
                    specialist_id=specialist_id,
                    supervisor_message_id=job.assistant_message_id,
                    supervisor_instruction=decision.instruction,
                    turn_number=specialist_turns + 1,
                )
                return
            if is_follow_up_waiting_status(specialist_message.status):
                return
            self._complete_agent_run(
                session=session,
                run_id=job.run_id or "",
                completed_turn_index=self._count_agent_messages(
                    session.id,
                    run_id=job.run_id or "",
                    agent_id=AgentId.SUPERVISOR,
                ),
            )
            return

        if job.agent_id in SUPERVISOR_MEMBER_AGENT_IDS:
            supervisor_turns = self._count_agent_messages(
                session.id,
                run_id=job.run_id or "",
                agent_id=AgentId.SUPERVISOR,
            )
            supervisor = configuration.agents[AgentId.SUPERVISOR]
            if supervisor.max_turns <= supervisor_turns:
                self._complete_agent_run(
                    session=session,
                    run_id=job.run_id or "",
                    completed_turn_index=supervisor_turns,
                )
                return

            supervisor_message = self._find_agent_message(
                session.id,
                run_id=job.run_id or "",
                agent_id=AgentId.SUPERVISOR,
                trigger_source=self._trigger_source_for_agent(job.agent_id),
                role=ChatMessageRole.ASSISTANT,
                dedupe_key=f"run:{job.run_id}:supervisor:{supervisor_turns + 1}",
            )
            if supervisor_message is None:
                self._continue_supervisor_from_specialist(
                    session=session,
                    run_id=job.run_id or "",
                    specialist_id=job.agent_id,
                    specialist_report=(job.response or "").strip(),
                    supervisor_turn_number=supervisor_turns + 1,
                )
                return
            if is_follow_up_waiting_status(supervisor_message.status):
                return

            self._complete_agent_run(
                session=session,
                run_id=job.run_id or "",
                completed_turn_index=supervisor_turns,
            )

    def _start_reviewer_turn(
        self,
        *,
        session: ChatSession,
        run_id: str,
        primary_response: str,
        reviewer_turn_number: int,
    ) -> None:
        if not primary_response:
            return
        reviewer = session.agent_configuration.normalized().agents[AgentId.REVIEWER]
        reviewer_message = ChatMessage(
            id=str(uuid4()),
            session_id=session.id,
            role=ChatMessageRole.USER,
            author_type=ChatMessageAuthorType.REVIEWER_CODEX,
            agent_id=AgentId.REVIEWER,
            agent_type=AgentType.REVIEWER,
            agent_label=reviewer.label,
            visibility=reviewer.visibility,
            trigger_source=AgentTriggerSource.GENERATOR,
            run_id=run_id,
            dedupe_key=f"run:{run_id}:reviewer:{reviewer_turn_number}",
            content="",
            status=ChatMessageStatus.RESERVED,
        )
        reviewer_message = self._repository.reserve_message(reviewer_message)
        if not can_launch_reserved_follow_up(reviewer_message):
            return

        self._launch_reserved_follow_up(
            session=session,
            message=reviewer_message,
            display_message=f"[{reviewer.label} agent follow-up]",
            execution_message=self._build_reviewer_execution_message(
                reviewer_prompt=reviewer.prompt,
                primary_response=primary_response,
            ),
            user_message_id=None,
            conversation_kind=JobConversationKind.REVIEWER,
            agent_id=AgentId.REVIEWER,
            agent_type=AgentType.REVIEWER,
            trigger_source=AgentTriggerSource.GENERATOR,
            run_id=run_id,
        )

    def _continue_generator_from_reviewer(
        self,
        *,
        session: ChatSession,
        run_id: str,
        reviewer_prompt: str,
        reviewer_message_id: str | None,
        generator_turn_number: int,
    ) -> None:
        if reviewer_message_id is None:
            return

        configuration = session.agent_configuration.normalized()
        generator_definition = configuration.agents[AgentId.GENERATOR]
        assistant_message = ChatMessage(
            id=str(uuid4()),
            session_id=session.id,
            role=ChatMessageRole.ASSISTANT,
            author_type=ChatMessageAuthorType.ASSISTANT,
            agent_id=AgentId.GENERATOR,
            agent_type=AgentType.GENERATOR,
            agent_label=generator_definition.label,
            visibility=generator_definition.visibility,
            trigger_source=AgentTriggerSource.REVIEWER,
            run_id=run_id,
            dedupe_key=f"run:{run_id}:generator:{generator_turn_number}",
            content="",
            status=ChatMessageStatus.RESERVED,
        )
        assistant_message = self._repository.reserve_message(assistant_message)
        if not can_launch_reserved_follow_up(assistant_message):
            return

        self._launch_reserved_follow_up(
            session=session,
            message=assistant_message,
            display_message=reviewer_prompt,
            execution_message=self._build_generator_execution_message(
                generator_prompt=generator_definition.prompt,
                user_prompt=reviewer_prompt,
                trigger_source=AgentTriggerSource.REVIEWER,
            ),
            user_message_id=reviewer_message_id,
            conversation_kind=JobConversationKind.PRIMARY,
            agent_id=AgentId.GENERATOR,
            agent_type=AgentType.GENERATOR,
            trigger_source=AgentTriggerSource.REVIEWER,
            run_id=run_id,
        )

    def _start_summary_turn(
        self,
        *,
        session: ChatSession,
        run_id: str,
        trigger_source: AgentTriggerSource,
        dedupe_key: str,
    ) -> None:
        summary = session.agent_configuration.normalized().agents[AgentId.SUMMARY]
        summary_message = ChatMessage(
            id=str(uuid4()),
            session_id=session.id,
            role=ChatMessageRole.ASSISTANT,
            author_type=ChatMessageAuthorType.ASSISTANT,
            agent_id=AgentId.SUMMARY,
            agent_type=AgentType.SUMMARY,
            agent_label=summary.label,
            visibility=summary.visibility,
            trigger_source=trigger_source,
            run_id=run_id,
            dedupe_key=dedupe_key,
            content="",
            status=ChatMessageStatus.RESERVED,
        )
        summary_message = self._repository.reserve_message(summary_message)
        if not can_launch_reserved_follow_up(summary_message):
            return

        self._launch_reserved_follow_up(
            session=session,
            message=summary_message,
            display_message=f"[{summary.label} summary turn]",
            execution_message=self._build_summary_execution_message(
                session_id=session.id,
                run_id=run_id,
                summary_prompt=summary.prompt,
            ),
            user_message_id=None,
            conversation_kind=JobConversationKind.SUMMARY,
            agent_id=AgentId.SUMMARY,
            agent_type=AgentType.SUMMARY,
            trigger_source=trigger_source,
            run_id=run_id,
        )

    def _start_specialist_turn(
        self,
        *,
        session: ChatSession,
        run_id: str,
        specialist_id: AgentId,
        supervisor_message_id: str | None,
        supervisor_instruction: str,
        turn_number: int,
    ) -> None:
        if supervisor_message_id is None or specialist_id not in SUPERVISOR_MEMBER_AGENT_IDS:
            return

        configuration = session.agent_configuration.normalized()
        specialist = configuration.agents[specialist_id]
        assistant_message = ChatMessage(
            id=str(uuid4()),
            session_id=session.id,
            role=ChatMessageRole.ASSISTANT,
            author_type=ChatMessageAuthorType.ASSISTANT,
            agent_id=specialist_id,
            agent_type=specialist.agent_type,
            agent_label=specialist.label,
            visibility=specialist.visibility,
            trigger_source=AgentTriggerSource.SUPERVISOR,
            run_id=run_id,
            dedupe_key=f"run:{run_id}:{specialist_id.value}:{turn_number}",
            content="",
            status=ChatMessageStatus.RESERVED,
        )
        assistant_message = self._repository.reserve_message(assistant_message)
        if not can_launch_reserved_follow_up(assistant_message):
            return

        self._launch_reserved_follow_up(
            session=session,
            message=assistant_message,
            display_message=f"[{specialist.label} specialist turn]",
            execution_message=self._build_specialist_execution_message(
                specialist_prompt=specialist.prompt,
                supervisor_instruction=supervisor_instruction,
                specialist_id=specialist_id,
            ),
            user_message_id=supervisor_message_id,
            conversation_kind=JobConversationKind.SPECIALIST,
            agent_id=specialist_id,
            agent_type=specialist.agent_type,
            trigger_source=AgentTriggerSource.SUPERVISOR,
            run_id=run_id,
        )

    def _continue_supervisor_from_specialist(
        self,
        *,
        session: ChatSession,
        run_id: str,
        specialist_id: AgentId,
        specialist_report: str,
        supervisor_turn_number: int,
    ) -> None:
        configuration = session.agent_configuration.normalized()
        supervisor = configuration.agents[AgentId.SUPERVISOR]
        assistant_message = ChatMessage(
            id=str(uuid4()),
            session_id=session.id,
            role=ChatMessageRole.ASSISTANT,
            author_type=ChatMessageAuthorType.ASSISTANT,
            agent_id=AgentId.SUPERVISOR,
            agent_type=AgentType.SUPERVISOR,
            agent_label=supervisor.label,
            visibility=supervisor.visibility,
            trigger_source=self._trigger_source_for_agent(specialist_id),
            run_id=run_id,
            dedupe_key=f"run:{run_id}:supervisor:{supervisor_turn_number}",
            content="",
            status=ChatMessageStatus.RESERVED,
        )
        assistant_message = self._repository.reserve_message(assistant_message)
        if not can_launch_reserved_follow_up(assistant_message):
            return

        self._launch_reserved_follow_up(
            session=session,
            message=assistant_message,
            display_message=f"[{supervisor.label} supervisor turn]",
            execution_message=self._build_supervisor_follow_up_message(
                session_id=session.id,
                run_id=run_id,
                supervisor_prompt=supervisor.prompt,
                supervisor_member_ids=configuration.supervisor_member_ids,
                specialist_id=specialist_id,
                specialist_report=specialist_report,
            ),
            user_message_id=None,
            conversation_kind=JobConversationKind.SUPERVISOR,
            agent_id=AgentId.SUPERVISOR,
            agent_type=AgentType.SUPERVISOR,
            trigger_source=self._trigger_source_for_agent(specialist_id),
            run_id=run_id,
        )

    def _entry_agent_for_configuration(
        self,
        configuration: AgentConfiguration,
    ) -> AgentId:
        normalized = configuration.normalized()
        if normalized.preset == AgentPreset.SUPERVISOR:
            return AgentId.SUPERVISOR
        return AgentId.GENERATOR

    def _provider_session_id_for_agent(
        self,
        session: ChatSession,
        agent_id: AgentId,
    ) -> str | None:
        configuration = session.agent_configuration.normalized()
        definition = configuration.agents.get(agent_id)
        if definition is not None:
            return definition.provider_session_id
        return None

    def _model_for_agent(
        self,
        session: ChatSession,
        agent_id: AgentId,
    ) -> str | None:
        configuration = session.agent_configuration.normalized()
        definition = configuration.agents.get(agent_id)
        if definition is not None:
            return definition.model
        return None

    def _serial_key_for_agent(
        self,
        session_id: str,
        agent_id: AgentId,
    ) -> str:
        if agent_id == AgentId.GENERATOR:
            return session_id
        return f"{session_id}:{agent_id.value}"

    def _count_agent_messages(
        self,
        session_id: str,
        *,
        run_id: str,
        agent_id: AgentId,
    ) -> int:
        return sum(
            1
            for message in self._repository.list_messages(session_id)
            if message.run_id == run_id
            and message.agent_id == agent_id
            and message.status == ChatMessageStatus.COMPLETED
        )

    def _completed_turn_index_for_run(
        self,
        session: ChatSession,
        *,
        run_id: str,
    ) -> int:
        configuration = session.agent_configuration.normalized()
        target_agent_id = (
            AgentId.SUPERVISOR
            if configuration.preset == AgentPreset.SUPERVISOR
            else AgentId.REVIEWER
        )
        return self._count_agent_messages(
            session.id,
            run_id=run_id,
            agent_id=target_agent_id,
        )

    def _find_agent_message(
        self,
        session_id: str,
        *,
        run_id: str,
        agent_id: AgentId,
        trigger_source: AgentTriggerSource | None = None,
        role: ChatMessageRole | None = None,
        dedupe_key: str | None = None,
    ) -> ChatMessage | None:
        matches = [
            message
            for message in self._repository.list_messages(session_id)
            if message.run_id == run_id and message.agent_id == agent_id
        ]
        if trigger_source is not None:
            matches = [
                message for message in matches if message.trigger_source == trigger_source
            ]
        if role is not None:
            matches = [message for message in matches if message.role == role]
        if dedupe_key is not None:
            matches = [message for message in matches if message.dedupe_key == dedupe_key]
        if not matches:
            return None
        matches.sort(key=lambda message: (message.created_at, message.id))
        return matches[-1]

    def _append_recovery_note(
        self,
        content: str,
        note: str,
    ) -> str:
        normalized = content.strip()
        if not normalized:
            return note
        return f"{normalized}\n\n{note}"

    def _next_manual_retry_dedupe_key(self, message: ChatMessage) -> str:
        base = message.dedupe_key or f"message:{message.id}"
        prefix = f"{base}:manual-retry:"
        retry_count = sum(
            1
            for candidate in self._repository.list_messages(message.session_id)
            if candidate.recovered_from_message_id == message.id
            and candidate.dedupe_key is not None
            and candidate.dedupe_key.startswith(prefix)
        )
        return f"{prefix}{retry_count + 1}"

    def _has_agent_message(
        self,
        session_id: str,
        *,
        run_id: str,
        agent_id: AgentId,
        trigger_source: AgentTriggerSource | None = None,
        role: ChatMessageRole | None = None,
    ) -> bool:
        for message in self._repository.list_messages(session_id):
            if message.run_id != run_id or message.agent_id != agent_id:
                continue
            if trigger_source is not None and message.trigger_source != trigger_source:
                continue
            if role is not None and message.role != role:
                continue
            return True
        return False

    def _complete_follow_up_run_after_manual_resolution(
        self,
        *,
        session: ChatSession,
        message: ChatMessage,
    ) -> None:
        if not message.run_id:
            session.touch()
            self._repository.save_session(session)
            return
        self._complete_agent_run(
            session=session,
            run_id=message.run_id,
            completed_turn_index=self._completed_turn_index_for_run(
                session,
                run_id=message.run_id,
            ),
        )

    def _complete_agent_run(
        self,
        *,
        session: ChatSession,
        run_id: str,
        completed_turn_index: int,
    ) -> None:
        if session.active_agent_run_id != run_id:
            return
        session.active_agent_run_id = None
        session.active_agent_turn_index = completed_turn_index
        session.auto_turn_index = completed_turn_index
        session.touch()
        self._repository.save_session(session)

    def _reconcile_reserved_follow_ups(
        self,
        session: ChatSession,
    ) -> None:
        self._cancel_reserved_follow_ups_for_inactive_runs(session)
        active_run_id = session.active_agent_run_id
        if active_run_id:
            if self._recover_submission_pending_follow_up_for_run(
                session,
                run_id=active_run_id,
            ):
                return
            self._recover_reserved_follow_up_for_run(session, run_id=active_run_id)

    def _cancel_reserved_follow_ups_for_inactive_runs(
        self,
        session: ChatSession,
    ) -> None:
        active_run_id = session.active_agent_run_id
        changed = False
        for message in self._repository.list_messages(session.id):
            if message.job_id is not None:
                continue
            if message.run_id == active_run_id:
                continue
            resolved_status = orphaned_follow_up_resolution_status(message.status)
            if resolved_status is None:
                continue
            reason = (
                _RESERVED_MESSAGE_STALE_REASON
                if resolved_status == ChatMessageStatus.CANCELLED
                else _SUBMISSION_UNKNOWN_REASON
            )
            message.sync(
                content=reason,
                reason_code=(
                    ChatMessageReasonCode.ORPHANED_FOLLOW_UP_CANCELLED
                    if resolved_status == ChatMessageStatus.CANCELLED
                    else ChatMessageReasonCode.SUBMISSION_OUTCOME_UNKNOWN
                ),
                status=resolved_status,
            )
            self._repository.save_message(message)
            changed = True
        if changed:
            session.touch()
            self._repository.save_session(session)

    def _cancel_reserved_follow_ups_for_run(
        self,
        session: ChatSession,
        *,
        run_id: str,
        reason: str,
    ) -> None:
        changed = False
        for message in self._repository.list_messages(session.id):
            if (
                message.run_id != run_id
                or message.job_id is not None
            ):
                continue
            resolved_status = orphaned_follow_up_resolution_status(message.status)
            if resolved_status is None:
                continue
            resolved_reason = (
                reason
                if resolved_status == ChatMessageStatus.CANCELLED
                else _SUBMISSION_UNKNOWN_SUPERSEDED_REASON
            )
            message.sync(
                content=resolved_reason,
                reason_code=ChatMessageReasonCode.SUPERSEDED_BY_NEWER_RUN,
                status=resolved_status,
            )
            self._repository.save_message(message)
            changed = True
        if changed:
            session.touch()
            self._repository.save_session(session)

    def _recover_submission_pending_follow_up_for_run(
        self,
        session: ChatSession,
        *,
        run_id: str,
    ) -> bool:
        pending_messages = [
            message
            for message in self._repository.list_messages(session.id)
            if message.run_id == run_id
            and message.status == ChatMessageStatus.SUBMISSION_PENDING
            and message.job_id is None
        ]
        if not pending_messages:
            return False

        pending_messages.sort(key=lambda message: (message.created_at, message.id))
        message = pending_messages[0]
        if not message.submission_token:
            self._finalize_reserved_follow_up(
                session=session,
                message=message,
                status=ChatMessageStatus.SUBMISSION_UNKNOWN,
                reason=_SUBMISSION_UNKNOWN_REASON,
                reason_code=ChatMessageReasonCode.SUBMISSION_OUTCOME_UNKNOWN,
            )
            return True

        provider = self._execution_provider
        if not provider.supports_submission_lookup():
            self._finalize_reserved_follow_up(
                session=session,
                message=message,
                status=ChatMessageStatus.SUBMISSION_UNKNOWN,
                reason=_SUBMISSION_UNKNOWN_REASON,
                reason_code=ChatMessageReasonCode.SUBMISSION_OUTCOME_UNKNOWN,
            )
            return True

        job_id = provider.get_job_id_by_submission_token(message.submission_token)
        if not job_id or not provider.has_job(job_id):
            self._finalize_reserved_follow_up(
                session=session,
                message=message,
                status=ChatMessageStatus.SUBMISSION_UNKNOWN,
                reason=_SUBMISSION_UNKNOWN_REASON,
                reason_code=ChatMessageReasonCode.SUBMISSION_OUTCOME_UNKNOWN,
            )
            return True

        self._attach_submitted_follow_up_job(
            session=session,
            message=message,
            job_id=job_id,
        )
        return True

    def _recover_reserved_follow_up_for_run(
        self,
        session: ChatSession,
        *,
        run_id: str,
    ) -> bool:
        reserved_messages = [
            message
            for message in self._repository.list_messages(session.id)
            if message.run_id == run_id
            and message.status == ChatMessageStatus.RESERVED
            and message.job_id is None
        ]
        if not reserved_messages:
            return False

        reserved_messages.sort(key=lambda message: (message.created_at, message.id))
        message = reserved_messages[0]
        configuration = session.agent_configuration.normalized()
        definition = configuration.agents.get(message.agent_id)
        if definition is None or not definition.enabled:
            self._finalize_reserved_follow_up(
                session=session,
                message=message,
                status=ChatMessageStatus.CANCELLED,
                reason="This reserved follow-up was disabled before it could be recovered.",
            )
            return True

        context = self._build_follow_up_context(
            session=session,
            message=message,
        )
        if context is None:
            self._finalize_reserved_follow_up(
                session=session,
                message=message,
                status=ChatMessageStatus.FAILED,
                reason="The reserved follow-up could not be recovered because its prerequisite context is missing.",
            )
            return True

        self._launch_reserved_follow_up(
            session=session,
            message=message,
            display_message=context.display_message,
            execution_message=context.execution_message,
            user_message_id=context.user_message_id,
            conversation_kind=context.conversation_kind,
            agent_id=context.agent_id,
            agent_type=context.agent_type,
            trigger_source=context.trigger_source,
            run_id=run_id,
        )
        return True

    def _attach_submitted_follow_up_job(
        self,
        *,
        session: ChatSession,
        message: ChatMessage,
        job_id: str,
    ) -> None:
        context = self._build_follow_up_context(
            session=session,
            message=message,
        )
        if context is None:
            self._finalize_reserved_follow_up(
                session=session,
                message=message,
                status=ChatMessageStatus.SUBMISSION_UNKNOWN,
                reason=_SUBMISSION_UNKNOWN_REASON,
                reason_code=ChatMessageReasonCode.SUBMISSION_OUTCOME_UNKNOWN,
            )
            return

        snapshot = self._execution_provider.get_snapshot(job_id)
        job = Job(
            id=job_id,
            session_id=session.id,
            message=context.display_message,
            user_message_id=context.user_message_id,
            assistant_message_id=message.id,
            provider_session_id=snapshot.provider_session_id,
            conversation_kind=context.conversation_kind,
            agent_id=context.agent_id,
            agent_type=context.agent_type,
            trigger_source=context.trigger_source,
            run_id=message.run_id,
            submission_token=message.submission_token,
            execution_message=context.execution_message,
            status=snapshot.status,
            response=snapshot.response,
            error=snapshot.error,
            phase=snapshot.phase,
            latest_activity=snapshot.latest_activity,
        )
        message.sync(
            status=ChatMessageStatus.PENDING,
            job_id=job.id,
        )
        session.touch()
        self._repository.save_turn(
            session,
            messages=[message],
            job=job,
        )
        self._register_background_job_watch(job.id)
        self._sync_job_side_effects(job)

    def _build_follow_up_context(
        self,
        *,
        session: ChatSession,
        message: ChatMessage,
    ) -> FollowUpContext | None:
        configuration = session.agent_configuration.normalized()
        definition = configuration.agents.get(message.agent_id)
        if definition is None:
            return None

        if message.agent_id == AgentId.REVIEWER:
            primary_message = self._latest_completed_agent_message(
                session.id,
                run_id=message.run_id or "",
                agent_id=AgentId.GENERATOR,
            )
            if primary_message is None or not primary_message.content.strip():
                return None
            return FollowUpContext(
                display_message=f"[{definition.label} agent follow-up]",
                execution_message=self._build_reviewer_execution_message(
                    reviewer_prompt=definition.prompt,
                    primary_response=primary_message.content.strip(),
                ),
                user_message_id=None,
                conversation_kind=JobConversationKind.REVIEWER,
                agent_id=AgentId.REVIEWER,
                agent_type=AgentType.REVIEWER,
                trigger_source=AgentTriggerSource.GENERATOR,
            )

        if message.agent_id == AgentId.GENERATOR:
            reviewer_message = self._latest_completed_agent_message(
                session.id,
                run_id=message.run_id or "",
                agent_id=AgentId.REVIEWER,
            )
            if reviewer_message is None or not reviewer_message.content.strip():
                return None
            reviewer_prompt = reviewer_message.content.strip()
            return FollowUpContext(
                display_message=reviewer_prompt,
                execution_message=self._build_generator_execution_message(
                    generator_prompt=definition.prompt,
                    user_prompt=reviewer_prompt,
                    trigger_source=AgentTriggerSource.REVIEWER,
                ),
                user_message_id=reviewer_message.id,
                conversation_kind=JobConversationKind.PRIMARY,
                agent_id=AgentId.GENERATOR,
                agent_type=AgentType.GENERATOR,
                trigger_source=AgentTriggerSource.REVIEWER,
            )

        if message.agent_id == AgentId.SUMMARY:
            return FollowUpContext(
                display_message=f"[{definition.label} summary turn]",
                execution_message=self._build_summary_execution_message(
                    session_id=session.id,
                    run_id=message.run_id or "",
                    summary_prompt=definition.prompt,
                ),
                user_message_id=None,
                conversation_kind=JobConversationKind.SUMMARY,
                agent_id=AgentId.SUMMARY,
                agent_type=AgentType.SUMMARY,
                trigger_source=message.trigger_source,
            )

        if message.agent_id in SUPERVISOR_MEMBER_AGENT_IDS:
            supervisor_message = self._latest_completed_agent_message(
                session.id,
                run_id=message.run_id or "",
                agent_id=AgentId.SUPERVISOR,
            )
            if supervisor_message is None:
                return None
            decision = self._parse_supervisor_decision(
                self._job_response_for_message(supervisor_message) or supervisor_message.content
            )
            if decision is None or not decision.instruction.strip():
                return None
            return FollowUpContext(
                display_message=f"[{definition.label} specialist turn]",
                execution_message=self._build_specialist_execution_message(
                    specialist_prompt=definition.prompt,
                    supervisor_instruction=decision.instruction,
                    specialist_id=message.agent_id,
                ),
                user_message_id=supervisor_message.id,
                conversation_kind=JobConversationKind.SPECIALIST,
                agent_id=message.agent_id,
                agent_type=definition.agent_type,
                trigger_source=AgentTriggerSource.SUPERVISOR,
            )

        if message.agent_id == AgentId.SUPERVISOR:
            if message.trigger_source == AgentTriggerSource.USER:
                user_message = self._latest_user_message_for_run(
                    session.id,
                    run_id=message.run_id or "",
                )
                if user_message is None or not user_message.content.strip():
                    return None
                return FollowUpContext(
                    display_message=f"[{definition.label} supervisor turn]",
                    execution_message=self._build_supervisor_execution_message(
                        supervisor_prompt=definition.prompt,
                        user_prompt=user_message.content.strip(),
                        supervisor_member_ids=configuration.supervisor_member_ids,
                        trigger_source=AgentTriggerSource.USER,
                    ),
                    user_message_id=user_message.id,
                    conversation_kind=JobConversationKind.SUPERVISOR,
                    agent_id=AgentId.SUPERVISOR,
                    agent_type=AgentType.SUPERVISOR,
                    trigger_source=AgentTriggerSource.USER,
                )

            specialist_id = self._agent_id_from_trigger_source(message.trigger_source)
            if specialist_id not in SUPERVISOR_MEMBER_AGENT_IDS:
                return None
            specialist_message = self._latest_completed_agent_message(
                session.id,
                run_id=message.run_id or "",
                agent_id=specialist_id,
            )
            if specialist_message is None or not specialist_message.content.strip():
                return None
            return FollowUpContext(
                display_message=f"[{definition.label} supervisor turn]",
                execution_message=self._build_supervisor_follow_up_message(
                    session_id=session.id,
                    run_id=message.run_id or "",
                    supervisor_prompt=definition.prompt,
                    supervisor_member_ids=configuration.supervisor_member_ids,
                    specialist_id=specialist_id,
                    specialist_report=specialist_message.content.strip(),
                ),
                user_message_id=None,
                conversation_kind=JobConversationKind.SUPERVISOR,
                agent_id=AgentId.SUPERVISOR,
                agent_type=AgentType.SUPERVISOR,
                trigger_source=message.trigger_source,
            )

        return None

    def _launch_reserved_follow_up(
        self,
        *,
        session: ChatSession,
        message: ChatMessage,
        display_message: str,
        execution_message: str,
        user_message_id: str | None,
        conversation_kind: JobConversationKind,
        agent_id: AgentId,
        agent_type: AgentType,
        trigger_source: AgentTriggerSource,
        run_id: str,
    ) -> None:
        if not can_launch_reserved_follow_up(message):
            return
        submission_token = message.submission_token or message.dedupe_key or f"message:{message.id}"
        message.sync(
            status=ChatMessageStatus.SUBMISSION_PENDING,
            submission_token=submission_token,
        )
        self._repository.save_message(message)
        job = self._start_job(
            session=session,
            display_message=display_message,
            execution_message=execution_message,
            image_paths=None,
            cleanup_paths=None,
            user_message_id=user_message_id,
            assistant_message_id=message.id,
            provider_session_id=self._provider_session_id_for_agent(
                session,
                agent_id,
            ),
            model=self._model_for_agent(session, agent_id),
            serial_key=self._serial_key_for_agent(session.id, agent_id),
            conversation_kind=conversation_kind,
            agent_id=agent_id,
            agent_type=agent_type,
            trigger_source=trigger_source,
            run_id=run_id,
            submission_token=submission_token,
        )
        message.sync(
            status=ChatMessageStatus.PENDING,
            job_id=job.id,
        )
        session.touch()
        self._repository.save_turn(
            session,
            messages=[message],
            job=job,
        )
        self._register_background_job_watch(job.id)

    def _finalize_reserved_follow_up(
        self,
        *,
        session: ChatSession,
        message: ChatMessage,
        status: ChatMessageStatus,
        reason: str,
        reason_code: ChatMessageReasonCode = ChatMessageReasonCode.FOLLOW_UP_TERMINAL_COMPLETED_RUN,
    ) -> None:
        message.sync(
            content=reason,
            reason_code=reason_code,
            status=status,
        )
        self._repository.save_message(message)
        if not message.run_id:
            return
        self._complete_agent_run(
            session=session,
            run_id=message.run_id,
            completed_turn_index=self._completed_turn_index_for_run(
                session,
                run_id=message.run_id,
            ),
        )

    def _register_background_job_watch(self, job_id: str) -> None:
        with self._job_monitor_lock:
            if job_id in self._job_monitor_unsubscribes:
                return
            self._job_monitor_unsubscribes[job_id] = None

        def on_change(snapshot: ExecutionSnapshot) -> None:
            if not snapshot.status.is_terminal:
                return
            try:
                self.get_job(job_id)
            finally:
                unsubscribe = self._remove_background_job_watch(job_id)
                if unsubscribe is not None:
                    unsubscribe()

        unsubscribe = self._execution_provider.watch_job(job_id, on_change)
        if unsubscribe is None:
            self._remove_background_job_watch(job_id)
            return

        should_unsubscribe = False
        with self._job_monitor_lock:
            if job_id not in self._job_monitor_unsubscribes:
                should_unsubscribe = True
            else:
                self._job_monitor_unsubscribes[job_id] = unsubscribe

        if should_unsubscribe:
            unsubscribe()

    def _remove_background_job_watch(
        self,
        job_id: str,
    ) -> Callable[[], None] | None:
        with self._job_monitor_lock:
            return self._job_monitor_unsubscribes.pop(job_id, None)

    def _latest_completed_agent_message(
        self,
        session_id: str,
        *,
        run_id: str,
        agent_id: AgentId,
    ) -> ChatMessage | None:
        messages = [
            message
            for message in self._repository.list_messages(session_id)
            if message.run_id == run_id
            and message.agent_id == agent_id
            and message.status == ChatMessageStatus.COMPLETED
        ]
        if not messages:
            return None
        messages.sort(key=lambda message: (message.created_at, message.id))
        return messages[-1]

    def _latest_user_message_for_run(
        self,
        session_id: str,
        *,
        run_id: str,
    ) -> ChatMessage | None:
        messages = [
            message
            for message in self._repository.list_messages(session_id)
            if message.run_id == run_id
            and message.role == ChatMessageRole.USER
            and message.author_type == ChatMessageAuthorType.HUMAN
        ]
        if not messages:
            return None
        messages.sort(key=lambda message: (message.created_at, message.id))
        return messages[-1]

    def _job_response_for_message(
        self,
        message: ChatMessage,
    ) -> str | None:
        if message.job_id is None:
            return None
        job = self._repository.get_job(message.job_id)
        return None if job is None else job.response

    def _agent_id_from_trigger_source(
        self,
        trigger_source: AgentTriggerSource,
    ) -> AgentId | None:
        mapping = {
            AgentTriggerSource.GENERATOR: AgentId.GENERATOR,
            AgentTriggerSource.REVIEWER: AgentId.REVIEWER,
            AgentTriggerSource.SUMMARY: AgentId.SUMMARY,
            AgentTriggerSource.SUPERVISOR: AgentId.SUPERVISOR,
            AgentTriggerSource.QA: AgentId.QA,
            AgentTriggerSource.UX: AgentId.UX,
            AgentTriggerSource.SENIOR_ENGINEER: AgentId.SENIOR_ENGINEER,
            AgentTriggerSource.SCRAPER: AgentId.SCRAPER,
        }
        return mapping.get(trigger_source)

    def _trigger_source_for_agent(
        self,
        agent_id: AgentId,
    ) -> AgentTriggerSource:
        return {
            AgentId.GENERATOR: AgentTriggerSource.GENERATOR,
            AgentId.REVIEWER: AgentTriggerSource.REVIEWER,
            AgentId.SUMMARY: AgentTriggerSource.SUMMARY,
            AgentId.SUPERVISOR: AgentTriggerSource.SUPERVISOR,
            AgentId.QA: AgentTriggerSource.QA,
            AgentId.UX: AgentTriggerSource.UX,
            AgentId.SENIOR_ENGINEER: AgentTriggerSource.SENIOR_ENGINEER,
            AgentId.SCRAPER: AgentTriggerSource.SCRAPER,
        }.get(agent_id, AgentTriggerSource.SYSTEM)

    def _build_generator_execution_message(
        self,
        *,
        generator_prompt: str,
        user_prompt: str,
        trigger_source: AgentTriggerSource,
    ) -> str:
        default_generator_prompt = AgentConfiguration.default().agents[AgentId.GENERATOR].prompt
        if (
            trigger_source == AgentTriggerSource.USER
            and generator_prompt.strip() == default_generator_prompt
        ):
            return user_prompt.strip()

        prefix = (
            "User request"
            if trigger_source == AgentTriggerSource.USER
            else "Follow-up request from another agent"
        )
        return f"{generator_prompt}\n\n{prefix}:\n{user_prompt.strip()}"

    def _build_supervisor_execution_message(
        self,
        *,
        supervisor_prompt: str,
        user_prompt: str,
        supervisor_member_ids: tuple[AgentId, ...],
        trigger_source: AgentTriggerSource,
    ) -> str:
        prefix = (
            "User request"
            if trigger_source == AgentTriggerSource.USER
            else "Supervisor follow-up request"
        )
        available_specialists = ", ".join(agent_id.value for agent_id in supervisor_member_ids)
        return (
            f"{supervisor_prompt}\n\n"
            f"Available specialist ids: {available_specialists}\n"
            f"{prefix}:\n{user_prompt.strip()}"
        )

    def _build_supervisor_follow_up_message(
        self,
        *,
        session_id: str,
        run_id: str,
        supervisor_prompt: str,
        supervisor_member_ids: tuple[AgentId, ...],
        specialist_id: AgentId,
        specialist_report: str,
    ) -> str:
        transcript = self._build_run_transcript(session_id=session_id, run_id=run_id)
        available_specialists = ", ".join(agent_id.value for agent_id in supervisor_member_ids)
        return (
            f"{supervisor_prompt}\n\n"
            f"Available specialist ids: {available_specialists}\n"
            f"Latest specialist report agent_id: {specialist_id.value}\n"
            f"Latest specialist report:\n{specialist_report.strip()}\n\n"
            f"Conversation transcript for this run:\n{transcript}"
        )
    
    def _build_specialist_execution_message(
        self,
        *,
        specialist_prompt: str,
        supervisor_instruction: str,
        specialist_id: AgentId,
    ) -> str:
        return (
            f"{specialist_prompt}\n\n"
            f"Assigned specialist id: {specialist_id.value}\n"
            "Supervisor assignment:\n"
            f"{supervisor_instruction.strip()}"
        )

    def _build_reviewer_execution_message(
        self,
        *,
        reviewer_prompt: str,
        primary_response: str,
    ) -> str:
        return (
            f"{reviewer_prompt}\n\n"
            "Generator Codex latest answer:\n"
            f"{primary_response}\n\n"
            "Return only the next prompt that should be sent back to the generator Codex."
        )

    def _build_summary_execution_message(
        self,
        *,
        session_id: str,
        run_id: str,
        summary_prompt: str,
    ) -> str:
        transcript = self._build_run_transcript(session_id=session_id, run_id=run_id)
        return f"{summary_prompt}\n\nConversation transcript for this run:\n{transcript}"

    def _build_run_transcript(
        self,
        *,
        session_id: str,
        run_id: str,
    ) -> str:
        transcript_parts: list[str] = []
        for message in self._repository.list_messages(session_id):
            if message.run_id != run_id or not message.content.strip():
                continue
            transcript_parts.append(
                f"{message.agent_id.value}/{message.role.value}: {message.content.strip()}"
            )
        return "\n\n".join(transcript_parts)

    def _parse_supervisor_decision(
        self,
        raw: str,
    ) -> SupervisorDecision | None:
        normalized = raw.strip()
        if not normalized:
            return None
        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None

        status = str(payload.get("status") or "").strip().lower()
        if status not in {"continue", "complete"}:
            return None

        raw_plan = payload.get("plan")
        if isinstance(raw_plan, list):
            plan = tuple(
                str(item).strip()
                for item in raw_plan
                if str(item).strip()
            )
        else:
            plan = ()

        raw_next_agent_id = payload.get("next_agent_id")
        next_agent_id: AgentId | None = None
        if raw_next_agent_id not in {None, ""}:
            try:
                candidate = AgentId(
                    normalize_agent_enum_value(str(raw_next_agent_id).strip())
                )
            except ValueError:
                return None
            if candidate not in SUPERVISOR_MEMBER_AGENT_IDS:
                return None
            next_agent_id = candidate

        instruction = str(payload.get("instruction") or "").strip()
        user_response = str(payload.get("user_response") or "").strip()
        return SupervisorDecision(
            status=status,
            plan=plan,
            next_agent_id=next_agent_id,
            instruction=instruction,
            user_response=user_response,
        )

    def _format_supervisor_message_content(
        self,
        decision: SupervisorDecision,
    ) -> str:
        lines: list[str] = []
        if decision.user_response:
            lines.append(decision.user_response)
        if decision.plan:
            if lines:
                lines.append("")
            lines.append("Plan:")
            lines.extend(f"- {step}" for step in decision.plan)
        if not decision.is_complete and decision.next_agent_id is not None:
            lines.append("")
            lines.append(f"Next agent: {decision.next_agent_id.value}")
        return "\n".join(lines).strip() or "Supervisor completed the turn."

    def _derive_title(self, message: str) -> str:
        normalized = " ".join(message.split())
        if len(normalized) <= 48:
            return normalized or "New chat"
        return f"{normalized[:45]}..."

    def _maybe_finalize_session_title(self, session_id: str) -> None:
        session = self._repository.get_session(session_id)
        if session is None or session.archived_at is not None or not session.title_is_placeholder:
            return

        messages = self._repository.list_messages(session_id)
        if self._count_titleable_turns(messages) < 4:
            return

        generated_title = (
            self._generate_title_with_codex(session, messages)
            or self._derive_conversation_title(messages)
        )
        normalized_title = self._normalize_generated_title(generated_title)
        if normalized_title is None:
            return

        latest_session = self._repository.get_session(session_id)
        if latest_session is None or latest_session.archived_at is not None:
            return
        if not latest_session.title_is_placeholder:
            return

        latest_session.title = normalized_title
        latest_session.title_is_placeholder = False
        latest_session.touch()
        self._repository.save_session(latest_session)

    def _count_titleable_turns(self, messages: list[ChatMessage]) -> int:
        return sum(
            1
            for message in messages
            if message.role == ChatMessageRole.USER
            and message.author_type == ChatMessageAuthorType.HUMAN
            and message.content.strip()
        )

    def _generate_title_with_codex(
        self,
        session: ChatSession,
        messages: list[ChatMessage],
    ) -> str | None:
        prompt = self._build_title_generation_prompt(messages)
        if not prompt:
            return None

        try:
            job_id = self._execution_provider.execute(
                prompt,
                serial_key=f"{session.id}:title",
                workdir=session.workspace_path,
                model=self._title_generation_model,
            )
        except Exception:
            return None

        deadline = time.monotonic() + 4.0
        snapshot = self._execution_provider.get_snapshot(job_id)
        while not snapshot.status.is_terminal and time.monotonic() < deadline:
            time.sleep(0.05)
            snapshot = self._execution_provider.get_snapshot(job_id)

        if snapshot.status != JobStatus.COMPLETED:
            return None
        return snapshot.response

    def _build_title_generation_prompt(
        self,
        messages: list[ChatMessage],
    ) -> str:
        conversation_lines: list[str] = []
        for message in messages:
            content = " ".join(message.content.split()).strip()
            if not content:
                continue
            role_label = "User" if message.role == ChatMessageRole.USER else "Assistant"
            conversation_lines.append(f"{role_label}: {content}")
            if len(conversation_lines) >= 8:
                break

        if not conversation_lines:
            return ""

        return (
            "Create a concise chat title from this conversation. "
            "Return only the title, 3 to 6 words, no quotes, maximum 60 characters.\n\n"
            + "\n".join(conversation_lines)
        )

    def _derive_conversation_title(self, messages: list[ChatMessage]) -> str:
        for message in messages:
            if message.role != ChatMessageRole.USER:
                continue
            normalized = " ".join(message.content.split()).strip()
            if not normalized:
                continue
            if len(normalized) <= 60:
                return normalized
            return f"{normalized[:57]}..."
        return "New chat"

    def _normalize_generated_title(self, raw_title: str | None) -> str | None:
        if raw_title is None:
            return None

        first_line = next(
            (line.strip() for line in raw_title.splitlines() if line.strip()),
            "",
        )
        if not first_line:
            return None

        normalized = first_line.strip().strip('"').strip("'").strip()
        if not normalized:
            return None
        if len(normalized) > 60:
            return None
        if ":" in normalized and len(normalized.split()) > 8:
            return None
        return normalized

    def _classify_document(
        self,
        *,
        filename: str,
        content_type: str | None,
    ) -> DocumentKind:
        suffix = Path(filename).suffix.lower()
        normalized_content_type = (content_type or "").split(";", maxsplit=1)[0].strip().lower()

        if normalized_content_type.startswith("image/") or suffix in _IMAGE_SUFFIXES:
            return "image"
        if normalized_content_type.startswith("audio/") or suffix in _AUDIO_SUFFIXES:
            return "audio"
        if suffix == ".docx" or normalized_content_type in {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }:
            return "docx"
        if self._looks_like_text_document(suffix=suffix, content_type=normalized_content_type):
            return "text"

        raise UnsupportedDocumentError(
            "Unsupported document type. Supported uploads are images, audio, text/code files, "
            "and .docx documents."
        )

    def _looks_like_text_document(
        self,
        *,
        suffix: str,
        content_type: str,
    ) -> bool:
        if suffix in _TEXT_SUFFIXES:
            return True
        if content_type.startswith("text/"):
            return True
        return content_type in {
            "application/json",
            "application/ld+json",
            "application/sql",
            "application/toml",
            "application/x-sh",
            "application/xml",
            "application/x-yaml",
        }

    def _build_document_display_message(
        self,
        *,
        message: str | None,
        document_kind: DocumentKind,
        document_name: str,
    ) -> str:
        summary = f"[Attached {document_kind} document: {document_name}]"
        instructions = (message or "").strip()
        if not instructions:
            return summary
        return f"{instructions}\n\n{summary}"

    def _build_document_execution_message(
        self,
        *,
        message: str | None,
        document_kind: DocumentKind,
        document_name: str,
        content_label: str,
        content: str,
    ) -> str:
        instructions = (message or "").strip() or (
            f"Please analyze the attached {document_kind} document."
        )
        truncated_content = self._truncate_document_text(content)
        return (
            f"{instructions}\n\n"
            f"Document name: {document_name}\n"
            f"Document kind: {document_kind}\n\n"
            f"{content_label}:\n{truncated_content}"
        )

    def _build_attachment_detail_section(
        self,
        *,
        index: int,
        document_kind: DocumentKind,
        document_name: str,
        content_label: str,
        content: str,
    ) -> str:
        truncated_content = self._truncate_document_text(content)
        return (
            f"Attachment {index}\n"
            f"Document name: {document_name}\n"
            f"Document kind: {document_kind}\n\n"
            f"{content_label}:\n{truncated_content}"
        )

    def _build_attachment_batch_display_message(
        self,
        *,
        message: str | None,
        attachment_summaries: list[str],
    ) -> str:
        summary_block = "[Attached files]\n" + "\n".join(attachment_summaries)
        instructions = (message or "").strip()
        if not instructions:
            return summary_block
        return f"{instructions}\n\n{summary_block}"

    def _build_attachment_batch_execution_message(
        self,
        *,
        message: str | None,
        attachment_summaries: list[str],
        attachment_details: list[str],
        image_count: int,
    ) -> str:
        instructions = (message or "").strip() or self._default_attachment_batch_instruction(
            attachment_summaries=attachment_summaries,
            image_count=image_count,
        )
        sections = [
            instructions,
            "Attached files:\n" + "\n".join(attachment_summaries),
        ]
        if image_count > 0:
            image_label = "image is" if image_count == 1 else "images are"
            sections.append(f"The attached {image_label} provided separately to this prompt.")
        if attachment_details:
            sections.append("\n\n".join(attachment_details))
        return "\n\n".join(section for section in sections if section.strip())

    def _default_attachment_batch_instruction(
        self,
        *,
        attachment_summaries: list[str],
        image_count: int,
    ) -> str:
        if len(attachment_summaries) == 1:
            if image_count == 1:
                return "Please analyze the attached image."
            summary = attachment_summaries[0].removeprefix("- ").strip()
            if ":" in summary:
                document_kind = summary.split(":", maxsplit=1)[0]
                return f"Please analyze the attached {document_kind} document."
        if image_count == len(attachment_summaries):
            return "Please analyze the attached images."
        return "Please analyze the attached files."

    def _truncate_document_text(self, text: str) -> str:
        normalized = text.strip()
        if len(normalized) <= self._document_text_char_limit:
            return normalized
        return (
            f"{normalized[: self._document_text_char_limit].rstrip()}\n\n"
            "[Document content truncated by the backend.]"
        )

    def _build_text_preview(self, text: str) -> str:
        normalized = " ".join(text.split())
        if len(normalized) <= 240:
            return normalized
        return f"{normalized[:237]}..."

    def _extract_document_text(
        self,
        *,
        document_path: Path,
        document_kind: DocumentKind,
    ) -> str:
        if document_kind == "docx":
            return self._extract_docx_text(document_path)
        if document_kind == "text":
            return document_path.read_text(encoding="utf-8", errors="replace")
        raise DocumentProcessingError(
            f"Document text extraction is not supported for {document_kind} files."
        )

    def _extract_docx_text(self, document_path: Path) -> str:
        try:
            with zipfile.ZipFile(document_path) as archive:
                xml_payload = archive.read("word/document.xml")
        except FileNotFoundError as exc:
            raise DocumentProcessingError("The uploaded .docx file could not be read.") from exc
        except KeyError as exc:
            raise DocumentProcessingError(
                "The uploaded .docx file is missing word/document.xml."
            ) from exc
        except zipfile.BadZipFile as exc:
            raise DocumentProcessingError("The uploaded .docx file is not a valid ZIP archive.") from exc

        try:
            root = ET.fromstring(xml_payload)
        except ET.ParseError as exc:
            raise DocumentProcessingError("The uploaded .docx file could not be parsed.") from exc

        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs: list[str] = []
        for paragraph in root.findall(".//w:p", namespace):
            runs = [
                node.text.strip()
                for node in paragraph.findall(".//w:t", namespace)
                if node.text and node.text.strip()
            ]
            if runs:
                paragraphs.append("".join(runs))

        return "\n\n".join(paragraphs)

    def _resolve_workspace(self, workspace_path: str | None) -> Workspace:
        workspaces = self._repository.list_workspaces()
        if not workspaces:
            raise ValueError("No workspaces were found.")

        if workspace_path is None:
            for workspace in workspaces:
                if workspace.path == self._default_workspace_path:
                    return workspace
            return workspaces[0]

        for workspace in workspaces:
            if workspace.path == workspace_path:
                return workspace

        raise ValueError(f"Workspace {workspace_path} was not found.")
