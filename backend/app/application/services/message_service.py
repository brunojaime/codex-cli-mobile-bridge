from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import shutil
import tempfile
from typing import Literal
from uuid import uuid4
import xml.etree.ElementTree as ET
import zipfile

from backend.app.domain.entities.chat_message import (
    ChatMessageAuthorType,
    ChatMessage,
    ChatMessageRole,
    ChatMessageStatus,
)
from backend.app.domain.entities.chat_session import ChatSession
from backend.app.domain.entities.job import Job, JobConversationKind, JobStatus
from backend.app.domain.entities.workspace import Workspace
from backend.app.domain.repositories.chat_repository import ChatRepository
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

_DEFAULT_AUTO_REVIEWER_PROMPT = (
    "You are the reviewer Codex for another Codex implementation session. "
    "You receive the generator Codex's latest answer and must produce the next "
    "prompt that should be sent back to that generator so the implementation improves. "
    "Push for concrete work: missing code, edge cases, tests, validation, cleanup, "
    "and stronger implementation details. Reply with only the next prompt to send. "
    "Do not explain your role, do not add framing, and do not answer the task yourself."
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


@dataclass(slots=True)
class AttachmentInput:
    path: str
    filename: str | None = None
    content_type: str | None = None


class MessageService:
    def __init__(
        self,
        *,
        repository: ChatRepository,
        execution_provider: ExecutionProvider,
        default_workspace_path: str,
        audio_transcriber: AudioTranscriber,
        document_text_char_limit: int = 20_000,
    ) -> None:
        self._repository = repository
        self._execution_provider = execution_provider
        self._default_workspace_path = str(Path(default_workspace_path).resolve())
        self._audio_transcriber = audio_transcriber
        self._document_text_char_limit = document_text_char_limit
        self._retry_asset_root = Path(tempfile.gettempdir()) / "codex-remote-retry-assets"
        self._retry_asset_root.mkdir(parents=True, exist_ok=True)

    def create_session(
        self,
        *,
        title: str | None = None,
        workspace_path: str | None = None,
    ) -> ChatSession:
        workspace = self._resolve_workspace(workspace_path)
        session = ChatSession(
            id=str(uuid4()),
            title=title or "New chat",
            workspace_path=workspace.path,
            workspace_name=workspace.name,
        )
        self._repository.save_session(session)
        return session

    def list_sessions(self) -> list[ChatSession]:
        return self._repository.list_sessions()

    def list_workspaces(self) -> list[Workspace]:
        return self._repository.list_workspaces()

    def get_session(self, session_id: str) -> ChatSession | None:
        return self._repository.get_session(session_id)

    def list_messages(self, session_id: str) -> list[ChatMessage]:
        return self._repository.list_messages(session_id)

    def update_auto_mode(
        self,
        *,
        session_id: str,
        enabled: bool,
        max_turns: int,
        reviewer_prompt: str | None,
    ) -> ChatSession:
        session = self._repository.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} was not found.")

        session.auto_mode_enabled = enabled
        session.auto_max_turns = max(0, max_turns)
        session.auto_reviewer_prompt = (reviewer_prompt or "").strip() or None
        session.auto_turn_index = 0
        session.touch()
        self._repository.save_session(session)
        return session

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
        conversation_kind: JobConversationKind = JobConversationKind.PRIMARY,
    ) -> Job:
        session = self._resolve_session(
            message=message,
            session_id=session_id,
            workspace_path=workspace_path,
        )
        if conversation_kind == JobConversationKind.PRIMARY and author_type == ChatMessageAuthorType.HUMAN:
            session.auto_turn_index = 0

        user_message = ChatMessage(
            id=str(uuid4()),
            session_id=session.id,
            role=ChatMessageRole.USER,
            author_type=author_type,
            content=message,
            status=ChatMessageStatus.COMPLETED,
        )
        assistant_message = ChatMessage(
            id=str(uuid4()),
            session_id=session.id,
            role=ChatMessageRole.ASSISTANT,
            author_type=ChatMessageAuthorType.ASSISTANT,
            content="",
            status=ChatMessageStatus.PENDING,
        )

        self._repository.save_message(user_message)
        self._repository.save_message(assistant_message)

        job = self._start_job(
            session=session,
            display_message=message,
            execution_message=execution_message or message,
            image_paths=image_paths,
            cleanup_paths=cleanup_paths,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
            provider_session_id=self._provider_session_id_for_kind(
                session,
                conversation_kind,
            ),
            serial_key=self._serial_key_for_kind(session.id, conversation_kind),
            conversation_kind=conversation_kind,
        )
        assistant_message.sync(job_id=job.id)
        session.touch()

        self._repository.save_message(assistant_message)
        self._repository.save_job(job)
        self._repository.save_session(session)
        return job

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
            provider_session_id=self._provider_session_id_for_kind(
                session,
                original_job.conversation_kind,
            ),
            serial_key=self._serial_key_for_kind(
                session.id,
                original_job.conversation_kind,
            ),
            conversation_kind=original_job.conversation_kind,
        )

        assistant_message.sync(
            content="",
            status=ChatMessageStatus.PENDING,
            job_id=retried_job.id,
        )
        session.touch()

        self._repository.save_message(assistant_message)
        self._repository.save_job(retried_job)
        self._repository.save_session(session)
        return retried_job

    def get_job(self, job_id: str) -> Job | None:
        job = self._repository.get_job(job_id)
        if job is None:
            return None

        if job.status.is_terminal:
            if not job.auto_chain_processed:
                self._sync_job_side_effects(job)
                return self._repository.get_job(job_id) or job
            return job

        if not self._execution_provider.has_job(job_id):
            job.sync(
                status=JobStatus.FAILED,
                error="The backend restarted before this in-flight job could be recovered.",
                phase="Failed",
                latest_activity="The backend process lost the live execution state for this job.",
            )
            self._repository.save_job(job)
            self._sync_job_side_effects(job)
            return job

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
        serial_key: str,
        conversation_kind: JobConversationKind,
    ) -> Job:
        retryable_image_paths = self._persist_retryable_image_paths(image_paths)
        job_id = self._execution_provider.execute(
            execution_message,
            image_paths=retryable_image_paths or None,
            cleanup_paths=cleanup_paths,
            provider_session_id=provider_session_id,
            serial_key=serial_key,
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
            if session.title == "New chat" and not self._repository.list_messages(session.id):
                session.title = self._derive_title(message)
            self._repository.save_session(session)
            return session

        session = self.create_session(
            title=self._derive_title(message),
            workspace_path=workspace_path,
        )
        return session

    def _sync_job_side_effects(self, job: Job) -> None:
        session = self._repository.get_session(job.session_id)
        if session and job.provider_session_id:
            if job.conversation_kind == JobConversationKind.REVIEWER:
                if session.reviewer_provider_session_id != job.provider_session_id:
                    session.reviewer_provider_session_id = job.provider_session_id
                    session.touch()
                    self._repository.save_session(session)
            elif session.provider_session_id != job.provider_session_id:
                session.provider_session_id = job.provider_session_id
                session.touch()
                self._repository.save_session(session)

        if job.assistant_message_id is None:
            return

        assistant_message = self._repository.get_message(job.assistant_message_id)
        if assistant_message is None:
            return

        if job.status == JobStatus.COMPLETED:
            assistant_message.sync(
                content=job.response or "",
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

        if session and job.status.is_terminal and not job.auto_chain_processed:
            self._maybe_continue_auto_mode(session=session, job=job)
            job.auto_chain_processed = True
            self._repository.save_job(job)

    def _maybe_continue_auto_mode(
        self,
        *,
        session: ChatSession,
        job: Job,
    ) -> None:
        if not session.auto_mode_enabled or session.auto_max_turns <= 0:
            return
        if job.status != JobStatus.COMPLETED:
            return

        if job.conversation_kind == JobConversationKind.PRIMARY:
            if session.auto_turn_index >= session.auto_max_turns:
                return
            primary_response = (job.response or "").strip()
            if not primary_response:
                return
            self._start_reviewer_turn(
                session=session,
                primary_response=primary_response,
            )
            return

        if job.conversation_kind == JobConversationKind.REVIEWER:
            if session.auto_turn_index >= session.auto_max_turns:
                return
            reviewer_prompt = (job.response or "").strip()
            if not reviewer_prompt:
                return
            self._continue_primary_from_reviewer(
                session=session,
                reviewer_prompt=reviewer_prompt,
                reviewer_message_id=job.assistant_message_id,
            )

    def _start_reviewer_turn(
        self,
        *,
        session: ChatSession,
        primary_response: str,
    ) -> None:
        reviewer_message = ChatMessage(
            id=str(uuid4()),
            session_id=session.id,
            role=ChatMessageRole.USER,
            author_type=ChatMessageAuthorType.REVIEWER_CODEX,
            content="",
            status=ChatMessageStatus.PENDING,
        )
        self._repository.save_message(reviewer_message)

        reviewer_job = self._start_job(
            session=session,
            display_message="[Reviewer Codex auto turn]",
            execution_message=self._build_auto_reviewer_execution_message(
                session=session,
                primary_response=primary_response,
            ),
            image_paths=None,
            cleanup_paths=None,
            user_message_id=None,
            assistant_message_id=reviewer_message.id,
            provider_session_id=session.reviewer_provider_session_id,
            serial_key=self._serial_key_for_kind(session.id, JobConversationKind.REVIEWER),
            conversation_kind=JobConversationKind.REVIEWER,
        )
        reviewer_message.sync(job_id=reviewer_job.id)
        session.touch()
        self._repository.save_message(reviewer_message)
        self._repository.save_job(reviewer_job)
        self._repository.save_session(session)

    def _continue_primary_from_reviewer(
        self,
        *,
        session: ChatSession,
        reviewer_prompt: str,
        reviewer_message_id: str | None,
    ) -> None:
        assistant_message = ChatMessage(
            id=str(uuid4()),
            session_id=session.id,
            role=ChatMessageRole.ASSISTANT,
            author_type=ChatMessageAuthorType.ASSISTANT,
            content="",
            status=ChatMessageStatus.PENDING,
        )
        self._repository.save_message(assistant_message)

        primary_job = self._start_job(
            session=session,
            display_message=reviewer_prompt,
            execution_message=reviewer_prompt,
            image_paths=None,
            cleanup_paths=None,
            user_message_id=reviewer_message_id,
            assistant_message_id=assistant_message.id,
            provider_session_id=session.provider_session_id,
            serial_key=self._serial_key_for_kind(session.id, JobConversationKind.PRIMARY),
            conversation_kind=JobConversationKind.PRIMARY,
        )
        assistant_message.sync(job_id=primary_job.id)
        session.auto_turn_index += 1
        session.touch()
        self._repository.save_message(assistant_message)
        self._repository.save_job(primary_job)
        self._repository.save_session(session)

    def _provider_session_id_for_kind(
        self,
        session: ChatSession,
        conversation_kind: JobConversationKind,
    ) -> str | None:
        if conversation_kind == JobConversationKind.REVIEWER:
            return session.reviewer_provider_session_id
        return session.provider_session_id

    def _serial_key_for_kind(
        self,
        session_id: str,
        conversation_kind: JobConversationKind,
    ) -> str:
        if conversation_kind == JobConversationKind.REVIEWER:
            return f"{session_id}:reviewer"
        return session_id

    def _build_auto_reviewer_execution_message(
        self,
        *,
        session: ChatSession,
        primary_response: str,
    ) -> str:
        reviewer_prompt = (session.auto_reviewer_prompt or "").strip() or _DEFAULT_AUTO_REVIEWER_PROMPT
        return (
            f"{reviewer_prompt}\n\n"
            "Generator Codex latest answer:\n"
            f"{primary_response}\n\n"
            "Return only the next prompt that should be sent back to the generator Codex."
        )

    def _derive_title(self, message: str) -> str:
        normalized = " ".join(message.split())
        if len(normalized) <= 48:
            return normalized or "New chat"
        return f"{normalized[:45]}..."

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
