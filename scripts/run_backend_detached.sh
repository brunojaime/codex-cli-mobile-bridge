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

mkdir -p "${RUNTIME_DIR}"

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
nohup "${PYTHON_BIN}" main.py >>"${LOG_FILE}" 2>&1 &
BACKEND_PID=$!
echo "${BACKEND_PID}" > "${PID_FILE}"

echo "Backend started with PID ${BACKEND_PID}"
echo "Log: ${LOG_FILE}"
echo "PID file: ${PID_FILE}"
