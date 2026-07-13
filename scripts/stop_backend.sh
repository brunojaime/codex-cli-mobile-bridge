#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PID_FILE="${ROOT_DIR}/.run/backend.pid"
ENV_FILE="${ROOT_DIR}/.env"

# shellcheck source=scripts/backend_process_lib.sh
source "${ROOT_DIR}/scripts/backend_process_lib.sh"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pid-file)
      backend_require_arg_value "$1" "${2-}"
      PID_FILE="${2:-}"
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

BACKEND_ENV_ALLOWED_KEYS=(API_PORT)
backend_export_env_file_values "${ENV_FILE}" "${BACKEND_ENV_ALLOWED_KEYS[@]}"

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
