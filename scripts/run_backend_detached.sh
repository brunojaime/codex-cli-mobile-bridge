#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_DIR="${ROOT_DIR}/.run"
PID_FILE="${RUNTIME_DIR}/backend.pid"
LOG_FILE="${RUNTIME_DIR}/backend.log"
ENV_FILE="${ROOT_DIR}/.env"

# shellcheck source=scripts/backend_process_lib.sh
source "${ROOT_DIR}/scripts/backend_process_lib.sh"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --runtime-dir)
      backend_require_arg_value "$1" "${2-}"
      RUNTIME_DIR="${2:-}"
      shift 2
      ;;
    --pid-file)
      backend_require_arg_value "$1" "${2-}"
      PID_FILE="${2:-}"
      shift 2
      ;;
    --log-file)
      backend_require_arg_value "$1" "${2-}"
      LOG_FILE="${2:-}"
      shift 2
      ;;
    --env-file)
      backend_require_arg_value "$1" "${2-}"
      ENV_FILE="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

mkdir -p "${RUNTIME_DIR}"
mkdir -p "$(dirname "${PID_FILE}")" "$(dirname "${LOG_FILE}")"

BACKEND_ENV_ALLOWED_KEYS=(
  API_PORT
  API_BASE_URL
  APP_UPDATE_PUBLIC_BASE_URL
  BRIDGE_URL
  BRIDGE_PUBLIC_URL
  CODEX_APP_UPDATER_BRIDGE_URL
  CODEX_FEEDBACK_BRIDGE_URL
  CODEX_COMMAND
  CODEX_USE_EXEC
  CODEX_EXEC_ARGS
  CODEX_RESUME_ARGS
  CODEX_WORKDIR
  PROJECTS_ROOT
  CHAT_STORE_PATH
  FEEDBACK_QUEUE_PATH
  FEEDBACK_IMAGE_DIR
  FEEDBACK_AUDIO_DIR
  ASSET_DEPOT_DIR
  PROJECT_FACTORY_STATE_DIR
  PROJECT_FACTORY_GITHUB_OWNER
  PROJECT_FACTORY_GITHUB_VISIBILITY
  PROJECT_FACTORY_GITHUB_DEFAULT_BRANCH
  INSTALLABLE_APPS_REGISTRATION_TOKEN
  BRIDGE_REGISTRATION_TOKEN
  BRIDGE_ENVIRONMENT
  BRIDGE_STAGE_ID
  BRIDGE_SPEC_ID
  BRIDGE_STAGE_BRANCH
  BRIDGE_STAGE_WORKTREE_PATH
  BRIDGE_APP_CHANNEL
  BRIDGE_UPDATER_CHANNEL
  BRIDGE_APP_LABEL
  BRIDGE_ENVIRONMENT_COLOR
  DEV_PIPELINE_STATE_PATH
  DEV_PIPELINE_RUNTIME_ROOT
  DEV_PIPELINE_DEV_NOTIFY_URL
  DEV_PIPELINE_AUTO_RUNNER_ENABLED
  DEV_PIPELINE_AUTO_RUNNER_INTERVAL_SECONDS
  DEV_PIPELINE_AUTO_RUNNER_WORKER_ID
  DEV_PIPELINE_AUTO_RUNNER_RECONCILE_EXISTING
)
backend_export_env_file_values "${ENV_FILE}" "${BACKEND_ENV_ALLOWED_KEYS[@]}"

if [[ -f "${PID_FILE}" ]]; then
  EXISTING_PID="$(cat "${PID_FILE}")"
  if backend_is_expected_process "${ROOT_DIR}" "${EXISTING_PID}"; then
    echo "Backend already running with PID ${EXISTING_PID}"
    echo "Log: ${LOG_FILE}"
    exit 0
  fi
  if kill -0 "${EXISTING_PID}" 2>/dev/null; then
    echo "Ignoring stale backend PID ${EXISTING_PID}: process is not this repo backend."
  else
    echo "Ignoring stale backend PID ${EXISTING_PID}: process is not running."
  fi
  rm -f "${PID_FILE}"
fi

API_PORT="${API_PORT:-$(backend_read_env_value API_PORT "${ENV_FILE}" || true)}"
API_PORT="${API_PORT:-8000}"
LISTENER_PID="$(backend_find_listener_pid "${API_PORT}" || true)"
if [[ -n "${LISTENER_PID}" ]]; then
  if backend_is_expected_process "${ROOT_DIR}" "${LISTENER_PID}"; then
    echo "${LISTENER_PID}" > "${PID_FILE}"
    echo "Backend already running on port ${API_PORT} with PID ${LISTENER_PID}"
    echo "PID file refreshed: ${PID_FILE}"
    echo "Log: ${LOG_FILE}"
    exit 0
  fi
  echo "Port ${API_PORT} is already in use by PID ${LISTENER_PID}, but it is not this repo backend." >&2
  exit 1
fi

PYTHON_BIN="python3"
if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
fi

cd "${ROOT_DIR}"
nohup env \
  API_PORT="${API_PORT:-}" \
  API_BASE_URL="${API_BASE_URL:-}" \
  APP_UPDATE_PUBLIC_BASE_URL="${APP_UPDATE_PUBLIC_BASE_URL:-}" \
  BRIDGE_URL="${BRIDGE_URL:-}" \
  BRIDGE_PUBLIC_URL="${BRIDGE_PUBLIC_URL:-}" \
  CODEX_APP_UPDATER_BRIDGE_URL="${CODEX_APP_UPDATER_BRIDGE_URL:-}" \
  CODEX_FEEDBACK_BRIDGE_URL="${CODEX_FEEDBACK_BRIDGE_URL:-}" \
  CODEX_COMMAND="${CODEX_COMMAND:-}" \
  CODEX_USE_EXEC="${CODEX_USE_EXEC:-}" \
  CODEX_EXEC_ARGS="${CODEX_EXEC_ARGS:-}" \
  CODEX_RESUME_ARGS="${CODEX_RESUME_ARGS:-}" \
  CODEX_WORKDIR="${CODEX_WORKDIR:-}" \
  PROJECTS_ROOT="${PROJECTS_ROOT:-}" \
  CHAT_STORE_PATH="${CHAT_STORE_PATH:-}" \
  FEEDBACK_QUEUE_PATH="${FEEDBACK_QUEUE_PATH:-}" \
  FEEDBACK_IMAGE_DIR="${FEEDBACK_IMAGE_DIR:-}" \
  FEEDBACK_AUDIO_DIR="${FEEDBACK_AUDIO_DIR:-}" \
  ASSET_DEPOT_DIR="${ASSET_DEPOT_DIR:-}" \
  PROJECT_FACTORY_STATE_DIR="${PROJECT_FACTORY_STATE_DIR:-}" \
  PROJECT_FACTORY_GITHUB_OWNER="${PROJECT_FACTORY_GITHUB_OWNER:-}" \
  PROJECT_FACTORY_GITHUB_VISIBILITY="${PROJECT_FACTORY_GITHUB_VISIBILITY:-}" \
  PROJECT_FACTORY_GITHUB_DEFAULT_BRANCH="${PROJECT_FACTORY_GITHUB_DEFAULT_BRANCH:-}" \
  INSTALLABLE_APPS_REGISTRATION_TOKEN="${INSTALLABLE_APPS_REGISTRATION_TOKEN:-}" \
  BRIDGE_REGISTRATION_TOKEN="${BRIDGE_REGISTRATION_TOKEN:-}" \
  BRIDGE_ENVIRONMENT="${BRIDGE_ENVIRONMENT:-}" \
  BRIDGE_STAGE_ID="${BRIDGE_STAGE_ID:-}" \
  BRIDGE_SPEC_ID="${BRIDGE_SPEC_ID:-}" \
  BRIDGE_STAGE_BRANCH="${BRIDGE_STAGE_BRANCH:-}" \
  BRIDGE_STAGE_WORKTREE_PATH="${BRIDGE_STAGE_WORKTREE_PATH:-}" \
  BRIDGE_APP_CHANNEL="${BRIDGE_APP_CHANNEL:-}" \
  BRIDGE_UPDATER_CHANNEL="${BRIDGE_UPDATER_CHANNEL:-}" \
  BRIDGE_APP_LABEL="${BRIDGE_APP_LABEL:-}" \
  BRIDGE_ENVIRONMENT_COLOR="${BRIDGE_ENVIRONMENT_COLOR:-}" \
  DEV_PIPELINE_STATE_PATH="${DEV_PIPELINE_STATE_PATH:-}" \
  DEV_PIPELINE_RUNTIME_ROOT="${DEV_PIPELINE_RUNTIME_ROOT:-}" \
  DEV_PIPELINE_DEV_NOTIFY_URL="${DEV_PIPELINE_DEV_NOTIFY_URL:-}" \
  DEV_PIPELINE_AUTO_RUNNER_ENABLED="${DEV_PIPELINE_AUTO_RUNNER_ENABLED:-}" \
  DEV_PIPELINE_AUTO_RUNNER_INTERVAL_SECONDS="${DEV_PIPELINE_AUTO_RUNNER_INTERVAL_SECONDS:-}" \
  DEV_PIPELINE_AUTO_RUNNER_WORKER_ID="${DEV_PIPELINE_AUTO_RUNNER_WORKER_ID:-}" \
  DEV_PIPELINE_AUTO_RUNNER_RECONCILE_EXISTING="${DEV_PIPELINE_AUTO_RUNNER_RECONCILE_EXISTING:-}" \
  "${PYTHON_BIN}" main.py >>"${LOG_FILE}" 2>&1 &
BACKEND_PID=$!
echo "${BACKEND_PID}" > "${PID_FILE}"

for _ in $(seq 1 20); do
  LISTENER_PID="$(backend_find_listener_pid "${API_PORT}" || true)"
  if [[ -n "${LISTENER_PID}" ]]; then
    echo "${LISTENER_PID}" > "${PID_FILE}"
    echo "Backend started with PID ${LISTENER_PID}"
    echo "Log: ${LOG_FILE}"
    echo "PID file: ${PID_FILE}"
    exit 0
  fi
  sleep 1
done

echo "Backend start command returned PID ${BACKEND_PID}, but no listener appeared on port ${API_PORT}." >&2
echo "Log: ${LOG_FILE}"
echo "PID file: ${PID_FILE}"
exit 1
