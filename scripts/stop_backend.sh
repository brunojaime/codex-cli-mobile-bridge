#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PID_FILE="${ROOT_DIR}/.run/backend.pid"
ENV_FILE="${ROOT_DIR}/.env"

# shellcheck source=scripts/backend_process_lib.sh
source "${ROOT_DIR}/scripts/backend_process_lib.sh"

API_PORT="${API_PORT:-$(backend_read_env_value API_PORT "${ENV_FILE}" || true)}"
API_PORT="${API_PORT:-8000}"

stop_pid() {
  local pid="$1"
  kill "${pid}"
  echo "Stopped backend PID ${pid}"
}

if [[ -f "${PID_FILE}" ]]; then
  PID="$(cat "${PID_FILE}")"
  if backend_is_expected_process "${ROOT_DIR}" "${PID}"; then
    stop_pid "${PID}"
    rm -f "${PID_FILE}"
    exit 0
  fi
  if kill -0 "${PID}" 2>/dev/null; then
    echo "Ignoring stale backend PID ${PID}: process is not this repo backend."
  else
    echo "Ignoring stale backend PID ${PID}: process is not running."
  fi
  rm -f "${PID_FILE}"
fi

LISTENER_PID="$(backend_find_listener_pid "${API_PORT}" || true)"
if [[ -n "${LISTENER_PID}" ]]; then
  if backend_is_expected_process "${ROOT_DIR}" "${LISTENER_PID}"; then
    stop_pid "${LISTENER_PID}"
    exit 0
  fi
  echo "Port ${API_PORT} is in use by PID ${LISTENER_PID}, but it is not this repo backend." >&2
  exit 1
fi

echo "Backend is not running."
