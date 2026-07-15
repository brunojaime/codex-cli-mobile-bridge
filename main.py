from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values


_BRIDGE_RUNTIME_ENV_KEYS = {
    "API_PORT",
    "API_BASE_URL",
    "CODEX_COMMAND",
    "CODEX_USE_EXEC",
    "CODEX_EXEC_ARGS",
    "CODEX_RESUME_ARGS",
    "CODEX_WORKDIR",
    "PROJECTS_ROOT",
    "CHAT_STORE_PATH",
    "FEEDBACK_QUEUE_PATH",
    "FEEDBACK_IMAGE_DIR",
    "FEEDBACK_AUDIO_DIR",
    "ASSET_DEPOT_DIR",
    "PROJECT_FACTORY_STATE_DIR",
    "BRIDGE_ENVIRONMENT",
    "BRIDGE_STAGE_ID",
    "BRIDGE_SPEC_ID",
    "BRIDGE_STAGE_BRANCH",
    "BRIDGE_STAGE_WORKTREE_PATH",
    "BRIDGE_APP_CHANNEL",
    "BRIDGE_UPDATER_CHANNEL",
    "BRIDGE_APP_LABEL",
    "BRIDGE_ENVIRONMENT_COLOR",
    "DEV_PIPELINE_STATE_PATH",
    "DEV_PIPELINE_RUNTIME_ROOT",
}


def _load_bridge_runtime_env() -> None:
    env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.is_file():
        return
    for key, value in dotenv_values(env_file).items():
        if key in _BRIDGE_RUNTIME_ENV_KEYS and value is not None:
            os.environ.setdefault(key, value)


_load_bridge_runtime_env()

from backend.app.main import run


if __name__ == "__main__":
    run()
