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
        env_file=(".env", "secrets/cloudflare.env"),
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
    project_factory_publication_validation_mode: Literal["remote", "local"] = "remote"
    project_factory_github_owner: str | None = None
    project_factory_github_visibility: Literal["private", "public", "internal"] = (
        "private"
    )
    project_factory_github_default_branch: str = "main"
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
    app_update_public_base_url: str | None = None
    bridge_environment: Literal["prod", "dev", "control"] = "prod"
    bridge_stage_id: str | None = None
    bridge_spec_id: str | None = None
    bridge_stage_branch: str | None = None
    bridge_stage_worktree_path: str | None = None
    bridge_app_channel: str = "prod"
    bridge_app_label: str = "Codex Mobile Bridge"
    bridge_updater_channel: str = "prod"
    bridge_environment_color: str = "#55D6BE"
    bridge_dev_main_branch: str = "dev/main"
    dev_pipeline_enabled: bool = True
    dev_pipeline_prod_handoff_enabled: bool = False
    dev_pipeline_promotion_enabled: bool = False
    dev_pipeline_prod_update_executor_enabled: bool = False
    dev_pipeline_dev_notify_url: str | None = None
    dev_pipeline_auto_runner_enabled: bool = False
    dev_pipeline_auto_runner_interval_seconds: float = Field(default=30.0, gt=0)
    dev_pipeline_auto_runner_worker_id: str = "dev-auto-runner"
    dev_pipeline_auto_runner_reconcile_existing: bool = False
    dev_pipeline_state_path: str = str(Path.cwd() / ".data" / "dev_pipeline_state.json")
    dev_pipeline_runtime_root: str = str(Path.home() / ".codex-bridge")
    installable_apps_registration_token: str | None = None
    cloudflare_api_token: str | None = None
    cloudflare_dns_api_token: str | None = None
    cloudflare_account_id: str | None = None
    cloudflare_zone_id: str | None = None
    cloudflare_zone_name: str = "nienfos.com"
    cloudflare_api_base_url: str = "https://api.cloudflare.com/client/v4"
    cloudflare_timeout_seconds: float = 10.0
    preview_base_domain: str = "preview.nienfos.com"
    preview_worker_name: str = "nienfos-preview-runtime"
    preview_d1_database_name: str = "nienfos-preview"
    preview_pages_project_name: str = "nienfos-preview-web"
    preview_r2_bucket_name: str | None = None
    web_preview_state_dir: str = str(Path.cwd() / ".data" / "web_preview_state")
    web_preview_apply_enabled: bool = False
    web_preview_default_ttl_seconds: int = 30 * 24 * 60 * 60
    web_preview_invite_secret: str | None = None
    web_preview_invite_default_ttl_seconds: int = 7 * 24 * 60 * 60
    web_preview_invite_max_ttl_seconds: int = 7 * 24 * 60 * 60
    web_preview_email_provider: Literal[
        "disabled",
        "manual",
        "smtp",
        "cloudflare_email",
    ] = "manual"
    web_preview_email_from: str | None = None
    web_preview_email_endpoint: str | None = None
    web_preview_email_api_token: str | None = None
    web_preview_smtp_host: str | None = None
    web_preview_smtp_port: int = 587
    web_preview_smtp_username: str | None = None
    web_preview_smtp_password: str | None = None
    web_preview_smtp_use_tls: bool = True
    web_preview_smtp_implicit_tls: bool = False
    web_preview_smtp_timeout_seconds: float = 10.0
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
