from __future__ import annotations

from pathlib import Path
import socket
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


_DEFAULT_FEEDBACK_SOURCE_WORKSPACE_ALIASES = {
    "sat-catalogo-ropa": Path("sat-catalogo-ropa"),
    "smart-nienfos": Path("smart_nienfos"),
    "smart-nienfos-admin": Path("smart_nienfos"),
}


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
    codex_streaming_mode: Literal["auto", "exec", "app_server"] = "auto"
    codex_exec_args: str = "--skip-git-repo-check --color never"
    codex_resume_args: str = "--skip-git-repo-check"
    codex_reasoning_effort: str | None = "high"
    codex_title_generation_model: str | None = None
    codex_workdir: str = str(Path.cwd())
    projects_root: str = str(Path.cwd().parent)
    chat_store_backend: Literal["sqlite", "memory"] = "sqlite"
    chat_store_path: str = str(Path.cwd() / ".data" / "chat_store.sqlite3")
    feedback_queue_path: str = str(Path.cwd() / ".data" / "feedback_queue.json")
    feedback_image_dir: str = str(Path.cwd() / ".data" / "feedback_images")
    feedback_audio_dir: str = str(Path.cwd() / ".data" / "feedback_audio")
    asset_depot_dir: str = str(Path.cwd() / ".data" / "asset_depot")
    asset_depot_max_upload_bytes: int = 25_000_000
    project_factory_reference_asset_dir: str = str(
        Path.cwd() / ".data" / "project_factory_reference_assets"
    )
    project_factory_state_dir: str = str(Path.cwd() / ".data" / "project_factory_state")
    project_factory_async_jobs: bool = True
    project_factory_generator_runs_override: int | None = None
    project_factory_reviewer_runs_override: int | None = None
    project_factory_step_timeout_seconds: int = 0
    project_factory_run_generated_validation: bool = False
    feedback_source_workspace_aliases: str = ""
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
    speech_synthesis_backend: Literal["disabled", "openai", "kokoro"] = "disabled"
    speech_synthesis_model: str = "gpt-4o-mini-tts"
    speech_synthesis_voice: str = "cedar"
    speech_synthesis_response_format: str = "mp3"
    speech_synthesis_instructions: str = (
        "Speak naturally with clear pacing, grounded tone, and concise phrasing."
    )
    speech_synthesis_timeout_seconds: int = 120
    speech_synthesis_kokoro_lang_code: str = "e"
    speech_synthesis_kokoro_voice: str = "ef_dora"
    speech_synthesis_kokoro_speed: float = Field(default=1.0, ge=0.5, le=2.0)
    speech_synthesis_kokoro_split_pattern: str = r"\n+"
    speech_synthesis_kokoro_sample_rate: int = 24_000
    app_update_registry_path: str = str(Path(__file__).with_name("app_updates.json"))
    app_update_github_token: str | None = None
    app_update_github_timeout_seconds: float = 10.0
    sdd_file_max_bytes: int = 256_000
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"

    @property
    def feedback_source_workspace_alias_map(self) -> dict[str, str]:
        projects_root = Path(self.projects_root).expanduser()
        aliases: dict[str, str] = {
            source_app: str(projects_root / relative_path)
            for source_app, relative_path in (
                _DEFAULT_FEEDBACK_SOURCE_WORKSPACE_ALIASES.items()
            )
        }
        for raw_entry in self.feedback_source_workspace_aliases.split(","):
            entry = raw_entry.strip()
            if not entry or ":" not in entry:
                continue
            source_app, workspace_path = entry.split(":", 1)
            source_app = source_app.strip()
            workspace_path = workspace_path.strip()
            if source_app and workspace_path:
                aliases[source_app] = workspace_path
        return aliases

    @computed_field
    @property
    def effective_backend_mode(self) -> Literal["local", "lambda"]:
        return "lambda" if self.use_lambda else self.backend_mode
