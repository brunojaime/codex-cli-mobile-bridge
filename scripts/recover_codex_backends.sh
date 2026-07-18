#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/recover_codex_backends.sh [--target prod|dev|all] [--force]
                                    [--health-timeout SECONDS]
                                    [--prod-mode auto|systemd-user|systemd|detached]

Recovers Codex Mobile Bridge backends that are alive but unhealthy or hung.
By default it checks PROD and DEV, skips healthy backends, and restarts only
the unhealthy ones. Use --force to restart even when /health responds.
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
SERVICE_NAME="codex-mobile-bridge-backend.service"
TARGET="all"
FORCE=false
HEALTH_TIMEOUT=5
PROD_MODE="auto"

# shellcheck source=scripts/backend_process_lib.sh
source "${ROOT_DIR}/scripts/backend_process_lib.sh"

require_value() {
  local option="$1"
  local value="${2:-}"
  if [[ -z "${value}" || "${value}" == --* ]]; then
    echo "${option} requires a non-empty value." >&2
    exit 1
  fi
}

require_positive_integer() {
  local option="$1"
  local value="$2"
  if [[ ! "${value}" =~ ^[0-9]+$ || "${value}" == "0" ]]; then
    echo "${option} must be a positive integer." >&2
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      require_value "$1" "${2:-}"
      TARGET="$2"
      shift 2
      ;;
    --force)
      FORCE=true
      shift
      ;;
    --health-timeout)
      require_value "$1" "${2:-}"
      require_positive_integer "$1" "$2"
      HEALTH_TIMEOUT="$2"
      shift 2
      ;;
    --prod-mode)
      require_value "$1" "${2:-}"
      PROD_MODE="$2"
      shift 2
      ;;
    -h|--help|help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

case "${TARGET}" in
  prod|dev|all) ;;
  *)
    echo "--target must be prod, dev, or all." >&2
    exit 1
    ;;
esac

case "${PROD_MODE}" in
  auto|systemd-user|systemd|detached) ;;
  *)
    echo "--prod-mode must be auto, systemd-user, systemd, or detached." >&2
    exit 1
    ;;
esac

health_ok() {
  local port="$1"
  curl -fsS --max-time "${HEALTH_TIMEOUT}" "http://127.0.0.1:${port}/health" >/dev/null
}

wait_for_health() {
  local port="$1"
  local label="$2"
  local attempts="${3:-30}"
  for _ in $(seq 1 "${attempts}"); do
    if health_ok "${port}"; then
      echo "${label} health is back on port ${port}."
      return 0
    fi
    sleep 1
  done
  echo "${label} did not become healthy on port ${port}." >&2
  return 1
}

pid_is_alive() {
  local pid="${1:-}"
  [[ "${pid}" =~ ^[0-9]+$ ]] && kill -0 "${pid}" 2>/dev/null
}

kill_process_family() {
  local pid="$1"
  local signal_name="$2"
  local child
  while IFS= read -r child; do
    [[ -n "${child}" ]] || continue
    kill_process_family "${child}" "${signal_name}"
  done < <(pgrep -P "${pid}" 2>/dev/null || true)
  kill "-${signal_name}" "${pid}" 2>/dev/null || true
}

force_stop_port_backend() {
  local port="$1"
  local label="$2"
  local pid
  pid="$(backend_find_listener_pid "${port}" || true)"
  if [[ -z "${pid}" ]]; then
    echo "${label} has no listener on port ${port}."
    return 0
  fi
  if ! backend_is_expected_process "${ROOT_DIR}" "${pid}"; then
    echo "Port ${port} is owned by PID ${pid}, but it is not this repo backend." >&2
    return 1
  fi

  echo "Stopping ${label} backend PID ${pid}."
  kill_process_family "${pid}" TERM
  for _ in $(seq 1 10); do
    if ! pid_is_alive "${pid}"; then
      return 0
    fi
    sleep 1
  done
  echo "${label} PID ${pid} ignored SIGTERM; sending SIGKILL."
  kill_process_family "${pid}" KILL
}

detect_prod_mode() {
  if systemctl --user is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
    echo "systemd-user"
    return
  fi
  if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
    echo "systemd"
    return
  fi
  echo "detached"
}

restart_prod() {
  local port mode
  port="${API_PORT:-$(backend_read_env_value API_PORT "${ENV_FILE}" || true)}"
  port="${port:-8000}"

  if [[ "${FORCE}" != "true" ]] && health_ok "${port}"; then
    echo "PROD backend is healthy on port ${port}; skipping."
    return 0
  fi

  mode="${PROD_MODE}"
  if [[ "${mode}" == "auto" ]]; then
    mode="$(detect_prod_mode)"
  fi
  echo "Recovering PROD backend with mode ${mode}."

  case "${mode}" in
    systemd-user)
      systemctl --user restart "${SERVICE_NAME}"
      ;;
    systemd)
      systemctl restart "${SERVICE_NAME}"
      ;;
    detached)
      force_stop_port_backend "${port}" "PROD"
      "${ROOT_DIR}/scripts/run_backend_detached.sh"
      ;;
  esac
  wait_for_health "${port}" "PROD"
}

restart_dev() {
  local port=8118
  if [[ "${FORCE}" != "true" ]] && health_ok "${port}"; then
    echo "DEV backend is healthy on port ${port}; skipping."
    return 0
  fi
  echo "Recovering DEV backend on port ${port}."
  force_stop_port_backend "${port}" "DEV"
  "${ROOT_DIR}/scripts/dev_backend_8118.sh" start
  wait_for_health "${port}" "DEV"
}

if [[ "${TARGET}" == "prod" || "${TARGET}" == "all" ]]; then
  restart_prod
fi
if [[ "${TARGET}" == "dev" || "${TARGET}" == "all" ]]; then
  restart_dev
fi

echo "Recovery completed."
