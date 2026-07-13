from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_backend_pid_check_rejects_unrelated_live_process() -> None:
    script = """
      set -euo pipefail
      source scripts/backend_process_lib.sh
      if backend_is_expected_process "$PWD" "$$"; then
        echo "current shell was incorrectly accepted as backend" >&2
        exit 1
      fi
      echo ok
    """

    result = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "ok"


def test_backend_env_loader_does_not_execute_metacharacters_and_preserves_spaces(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "runtime with spaces" / ".env.stage"
    marker = tmp_path / "executed"
    chat_store = tmp_path / "data dir" / "chat store.sqlite3"
    image_dir = tmp_path / "image dir"
    env_file.parent.mkdir()
    env_file.write_text(
        "\n".join(
            [
                f"API_PORT=$(touch {shlex.quote(str(marker))})",
                f"CHAT_STORE_PATH='{chat_store}'",
                f'export FEEDBACK_IMAGE_DIR="{image_dir}"',
                "IGNORED_SECRET=should-not-export",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    script = f"""
      set -euo pipefail
      source scripts/backend_process_lib.sh
      backend_export_env_file_values {shlex.quote(str(env_file))} API_PORT CHAT_STORE_PATH FEEDBACK_IMAGE_DIR
      printf 'api=%s\\nchat=%s\\nimage=%s\\nsecret=%s\\n' "${{API_PORT}}" "${{CHAT_STORE_PATH}}" "${{FEEDBACK_IMAGE_DIR}}" "${{IGNORED_SECRET:-}}"
    """

    result = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not marker.exists()
    assert f"api=$(touch {marker})" in result.stdout
    assert f"chat={chat_store}" in result.stdout
    assert f"image={image_dir}" in result.stdout
    assert "secret=" in result.stdout


@pytest.mark.parametrize(
    ("script", "flag"),
    [
        ("scripts/run_backend_detached.sh", "--env-file"),
        ("scripts/run_backend_detached.sh", "--pid-file"),
        ("scripts/run_backend_detached.sh", "--runtime-dir"),
        ("scripts/run_backend_detached.sh", "--log-file"),
        ("scripts/stop_backend.sh", "--env-file"),
        ("scripts/stop_backend.sh", "--pid-file"),
    ],
)
def test_backend_process_script_arguments_require_non_empty_values(
    script: str,
    flag: str,
) -> None:
    result = subprocess.run(
        ["bash", script, flag, ""],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert f"{flag} requires a non-empty value." in result.stderr


def test_dev_backend_8118_script_contract() -> None:
    script_path = ROOT / "scripts/dev_backend_8118.sh"
    script = script_path.read_text(encoding="utf-8")

    syntax = subprocess.run(
        ["bash", "-n", str(script_path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert syntax.returncode == 0, syntax.stdout + syntax.stderr
    assert os.access(script_path, os.X_OK)
    assert "set -euo pipefail" in script
    assert "start|status|restart|stop" in script
    assert "PORT=8118" in script
    assert "API_PORT=\"${PORT}\"" in script
    assert "BRIDGE_ENVIRONMENT=\"dev\"" in script
    assert "BRIDGE_APP_CHANNEL=\"dev\"" in script
    assert "BRIDGE_UPDATER_CHANNEL=\"dev\"" in script
    assert "BRIDGE_ENVIRONMENT_COLOR=#38BDF8" in script
    assert "BRIDGE_ENVIRONMENT_COLOR=\"#38BDF8\"" in script
    assert ".run/dev-backend-8118" in script
    assert ".run/backend.pid" not in script
    assert ".run/backend.log" not in script
    assert "API_PORT=8000" not in script
    assert "BRIDGE_ENVIRONMENT=prod" not in script
    assert "serve --bg --http=\"${PORT}\"" in script
    assert "restart)" in script
    assert "stop)" in script


def test_dev_backend_8118_script_does_not_embed_secrets() -> None:
    script = (ROOT / "scripts/dev_backend_8118.sh").read_text(encoding="utf-8")
    lowered = script.lower()

    forbidden_fragments = [
        "ghp_",
        "github_token=",
        "api_key=",
        "password=",
        "secret=",
        "bearer ",
        "-----begin",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in lowered
