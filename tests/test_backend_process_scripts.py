from __future__ import annotations

import os
import re
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
        ("scripts/recover_codex_backends.sh", "--target"),
        ("scripts/recover_codex_backends.sh", "--health-timeout"),
        ("scripts/recover_codex_backends.sh", "--prod-mode"),
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


def test_run_backend_detached_exports_codex_runtime_settings() -> None:
    script_path = ROOT / "scripts/run_backend_detached.sh"
    script = script_path.read_text(encoding="utf-8")

    syntax = subprocess.run(
        ["bash", "-n", str(script_path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert syntax.returncode == 0, syntax.stdout + syntax.stderr
    assert "CODEX_COMMAND" in script
    assert "CODEX_USE_EXEC" in script
    assert "CODEX_EXEC_ARGS" in script
    assert "CODEX_RESUME_ARGS" in script
    assert "PROJECT_FACTORY_GITHUB_OWNER" in script
    assert "APP_UPDATE_PUBLIC_BASE_URL" in script
    assert "BRIDGE_PUBLIC_URL" in script
    assert "INSTALLABLE_APPS_REGISTRATION_TOKEN" in script
    assert "backend_export_env_file_values" in script
    assert "nohup env \\" in script
    assert "CODEX_EXEC_ARGS=\"${CODEX_EXEC_ARGS:-}\"" in script
    assert (
        'DEV_PIPELINE_AUTO_RUNNER_ENABLED="${DEV_PIPELINE_AUTO_RUNNER_ENABLED:-false}"'
        in script
    )
    assert (
        'DEV_PIPELINE_AUTO_RUNNER_INTERVAL_SECONDS="${DEV_PIPELINE_AUTO_RUNNER_INTERVAL_SECONDS:-30}"'
        in script
    )
    assert (
        'DEV_PIPELINE_AUTO_RUNNER_RECONCILE_EXISTING="${DEV_PIPELINE_AUTO_RUNNER_RECONCILE_EXISTING:-false}"'
        in script
    )
    assert "LISTENER_PID=\"$(backend_find_listener_pid" in script
    assert "echo \"${LISTENER_PID}\" > \"${PID_FILE}\"" in script


def test_run_backend_foreground_contract() -> None:
    script_path = ROOT / "scripts/run_backend_foreground.sh"
    script = script_path.read_text(encoding="utf-8")

    syntax = subprocess.run(
        ["bash", "-n", str(script_path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert syntax.returncode == 0, syntax.stdout + syntax.stderr
    assert "backend_export_env_file_values" in script
    assert "CODEX_EXEC_ARGS" in script
    assert "PROJECT_FACTORY_GITHUB_OWNER" in script
    assert "APP_UPDATE_PUBLIC_BASE_URL" in script
    assert "BRIDGE_PUBLIC_URL" in script
    assert "INSTALLABLE_APPS_REGISTRATION_TOKEN" in script
    assert (
        'DEV_PIPELINE_AUTO_RUNNER_ENABLED="${DEV_PIPELINE_AUTO_RUNNER_ENABLED:-false}"'
        in script
    )
    assert (
        'DEV_PIPELINE_AUTO_RUNNER_INTERVAL_SECONDS="${DEV_PIPELINE_AUTO_RUNNER_INTERVAL_SECONDS:-30}"'
        in script
    )
    assert (
        'DEV_PIPELINE_AUTO_RUNNER_RECONCILE_EXISTING="${DEV_PIPELINE_AUTO_RUNNER_RECONCILE_EXISTING:-false}"'
        in script
    )
    assert "exec env \\" in script
    assert '"${PYTHON_BIN}" main.py' in script


def test_recover_codex_backends_contract() -> None:
    script_path = ROOT / "scripts/recover_codex_backends.sh"
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
    assert "--target prod|dev|all" in script
    assert "--force" in script
    assert "curl -fsS --max-time" in script
    assert "force_stop_port_backend" in script
    assert "backend_is_expected_process" in script
    assert "scripts/dev_backend_8118.sh\" start" in script
    assert "scripts/run_backend_detached.sh" in script


def test_main_loads_allowlisted_runtime_env_only() -> None:
    source = (ROOT / "main.py").read_text(encoding="utf-8")

    assert "_BRIDGE_RUNTIME_ENV_KEYS" in source
    assert "CODEX_EXEC_ARGS" in source
    assert "PROJECT_FACTORY_GITHUB_OWNER" in source
    assert "APP_UPDATE_PUBLIC_BASE_URL" in source
    assert "BRIDGE_PUBLIC_URL" in source
    assert "INSTALLABLE_APPS_REGISTRATION_TOKEN" in source
    assert "dotenv_values" in source
    assert "os.environ.setdefault" in source
    assert "APP_UPDATE_GITHUB_TOKEN" not in source
    assert "SMTP_PASSWORD" not in source
    assert "OPENAI_API_KEY" not in source


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
    assert "CODEX_COMMAND=\"${codex_command}\"" in script
    assert "CODEX_USE_EXEC=\"${codex_use_exec}\"" in script
    assert "CODEX_EXEC_ARGS=\"${codex_exec_args}\"" in script
    assert "CODEX_RESUME_ARGS=\"${codex_resume_args}\"" in script
    assert "PROJECT_FACTORY_GITHUB_OWNER" in script
    assert "PROJECT_FACTORY_GITHUB_VISIBILITY" in script
    assert "PROJECT_FACTORY_GITHUB_DEFAULT_BRANCH" in script
    assert "APP_UPDATE_PUBLIC_BASE_URL=${BASE_URL}" in script
    assert "BRIDGE_PUBLIC_URL=${BASE_URL}" in script
    assert "INSTALLABLE_APPS_REGISTRATION_TOKEN" in script
    assert "--dangerously-bypass-approvals-and-sandbox" in script
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
    assert "FALLBACK_BASE_ENV_FILE" in script
    assert "codex-cli-mobile-bridge/.env" in script
    assert "BASE_SECRET_ENV_FILE" in script
    assert "FALLBACK_SECRET_ENV_FILE" in script
    assert "codex-cli-mobile-bridge/secrets/cloudflare.env" in script
    assert "CLOUDFLARE_API_TOKEN" in script
    assert "CLOUDFLARE_DNS_API_TOKEN" in script
    assert "CLOUDFLARE_ACCOUNT_ID" in script
    assert "CLOUDFLARE_ZONE_ID" in script
    assert "WEB_PREVIEW_APPLY_ENABLED" in script
    assert "WEB_PREVIEW_INVITE_SECRET" in script
    assert "WEB_PREVIEW_EMAIL_PROVIDER" in script
    assert "WEB_PREVIEW_EMAIL_FROM" in script
    assert "WEB_PREVIEW_EMAIL_ENDPOINT" in script
    assert "WEB_PREVIEW_EMAIL_API_TOKEN" in script
    assert "WEB_PREVIEW_SMTP_HOST" in script
    assert "WEB_PREVIEW_SMTP_PORT" in script
    assert "WEB_PREVIEW_SMTP_USERNAME" in script
    assert "WEB_PREVIEW_SMTP_PASSWORD" in script
    assert "WEB_PREVIEW_SMTP_USE_TLS" in script
    assert "WEB_PREVIEW_SMTP_IMPLICIT_TLS" in script
    assert "WEB_PREVIEW_SMTP_TIMEOUT_SECONDS" in script
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
        "bearer ",
        "-----begin",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in lowered

    sensitive_assignments = re.findall(
        r"(?im)^\s*[A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|API_KEY)=(.+)$",
        script,
    )
    assert sensitive_assignments
    for value in sensitive_assignments:
        stripped = value.strip().rstrip(" \\")
        assert (
            stripped.startswith("${")
            or stripped.startswith('"${')
            or stripped.startswith('"$(codex_env_value ')
        )
