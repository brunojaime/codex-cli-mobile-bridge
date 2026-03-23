from __future__ import annotations

from pathlib import Path
import socket
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Codex Mobile Bridge"
    server_name: str = socket.gethostname()
    backend_mode: Literal["local", "lambda"] = "local"
    use_lambda: bool = False
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_base_url: str = "http://localhost:8000"
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    codex_command: str = "codex"
    codex_use_exec: bool = True
    codex_exec_args: str = "--skip-git-repo-check --color never"
    codex_resume_args: str = "--skip-git-repo-check"
    codex_workdir: str = str(Path.cwd())
    projects_root: str = str(Path.cwd().parent)
    chat_store_backend: Literal["sqlite", "memory"] = "sqlite"
    chat_store_path: str = str(Path.cwd() / ".data" / "chat_store.sqlite3")
    tailscale_socket: str | None = None
    execution_timeout_seconds: int = 0
    lambda_endpoint: str = "http://localhost:9000"
    poll_interval_seconds: int = 2
    audio_max_upload_bytes: int = 25_000_000
    document_max_upload_bytes: int = 25_000_000
    document_text_char_limit: int = 20_000
    image_max_upload_bytes: int = 25_000_000
    audio_transcription_backend: Literal[
        "auto",
        "disabled",
        "command",
        "openai",
        "faster_whisper",
    ] = "auto"
    audio_transcription_command: str | None = None
    audio_transcription_model: str = "gpt-4o-mini-transcribe"
    audio_transcription_language: str | None = None
    audio_transcription_timeout_seconds: int = 120
    audio_transcription_local_model: str = "small"
    audio_transcription_local_compute_type: str = "int8"
    audio_transcription_local_device: str = "auto"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"

    @computed_field
    @property
    def effective_backend_mode(self) -> Literal["local", "lambda"]:
        return "lambda" if self.use_lambda else self.backend_mode
