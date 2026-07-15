#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_DIR="${ROOT_DIR}/.run/dev-backend-8118"
DATA_DIR="${RUNTIME_DIR}/data"
LOG_FILE="${RUNTIME_DIR}/backend.log"
PID_FILE="${RUNTIME_DIR}/backend.pid"
ENV_FILE="${RUNTIME_DIR}/dev.env"
BASE_ENV_FILE="${ROOT_DIR}/.env"
PORT=8118
BASE_URL="http://batata-default-string.tail0302c4.ts.net:${PORT}"
TAILSCALE_SOCKET="${TAILSCALE_SOCKET:-/home/batata/.local/share/tailscale-userspace/tailscaled.sock}"

usage() {
  cat <<'EOF'
Usage: scripts/dev_backend_8118.sh [start|status|restart|stop]

Runs the DEV Codex Mobile backend expected by the DEV APK:
  http://batata-default-string.tail0302c4.ts.net:8118

The process uses isolated runtime/data/log paths under .run/dev-backend-8118
and configures Tailscale Serve for :8118 when available.
EOF
}

listener_pid() {
  ss -ltnp "sport = :${PORT}" 2>/dev/null \
    | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' \
    | head -n 1
}

health_environment() {
  curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/health" \
    | jq -r '.environment_identity.environment // empty'
}

health_json() {
  curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/health"
}

serve_has_port() {
  local status
  command -v tailscale >/dev/null 2>&1 \
    && [[ -S "${TAILSCALE_SOCKET}" ]] \
    && status="$(tailscale --socket="${TAILSCALE_SOCKET}" serve status 2>/dev/null)" \
    && grep -q "tail0302c4.ts.net:${PORT}" <<<"${status}"
}

pid_is_alive() {
  local pid="${1:-}"
  [[ "${pid}" =~ ^[0-9]+$ ]] && kill -0 "${pid}" 2>/dev/null
}

base_env_value() {
  local key="$1"
  [[ -f "${BASE_ENV_FILE}" ]] || return 1
  sed -n "s/^${key}=//p" "${BASE_ENV_FILE}" | tail -n 1
}

codex_env_value() {
  local key="$1"
  local fallback="${2:-}"
  local value="${!key:-}"
  if [[ -z "${value}" ]]; then
    value="$(base_env_value "${key}" || true)"
  fi
  printf '%s' "${value:-${fallback}}"
}

write_runtime_env() {
  mkdir -p "${DATA_DIR}" "${DATA_DIR}/feedback_images" "${DATA_DIR}/feedback_audio" \
    "${DATA_DIR}/asset_depot" "${DATA_DIR}/project_factory_state" \
    "${RUNTIME_DIR}/runtime"
  local codex_command codex_use_exec codex_exec_args codex_resume_args
  codex_command="$(codex_env_value CODEX_COMMAND "codex")"
  codex_use_exec="$(codex_env_value CODEX_USE_EXEC "true")"
  codex_exec_args="$(codex_env_value CODEX_EXEC_ARGS "--skip-git-repo-check --color never --dangerously-bypass-approvals-and-sandbox")"
  codex_resume_args="$(codex_env_value CODEX_RESUME_ARGS "--skip-git-repo-check --dangerously-bypass-approvals-and-sandbox")"
  cat >"${ENV_FILE}" <<EOF
API_PORT=${PORT}
API_BASE_URL=${BASE_URL}
CODEX_COMMAND=${codex_command}
CODEX_USE_EXEC=${codex_use_exec}
CODEX_EXEC_ARGS=${codex_exec_args}
CODEX_RESUME_ARGS=${codex_resume_args}
CODEX_WORKDIR=${ROOT_DIR}
PROJECTS_ROOT=$(dirname "${ROOT_DIR}")
CHAT_STORE_PATH=${DATA_DIR}/chat_store.sqlite3
FEEDBACK_QUEUE_PATH=${DATA_DIR}/feedback_queue.json
FEEDBACK_IMAGE_DIR=${DATA_DIR}/feedback_images
FEEDBACK_AUDIO_DIR=${DATA_DIR}/feedback_audio
ASSET_DEPOT_DIR=${DATA_DIR}/asset_depot
PROJECT_FACTORY_STATE_DIR=${DATA_DIR}/project_factory_state
BRIDGE_ENVIRONMENT=dev
BRIDGE_STAGE_ID=dev-app
BRIDGE_SPEC_ID=018
BRIDGE_STAGE_BRANCH=main
BRIDGE_STAGE_WORKTREE_PATH=${ROOT_DIR}
BRIDGE_APP_CHANNEL=dev
BRIDGE_UPDATER_CHANNEL=dev
BRIDGE_APP_LABEL=Codex Mobile Bridge DEV
BRIDGE_ENVIRONMENT_COLOR=#38BDF8
DEV_PIPELINE_STATE_PATH=${ROOT_DIR}/.data/dev_pipeline_state.json
DEV_PIPELINE_RUNTIME_ROOT=${RUNTIME_DIR}/runtime
DEV_PIPELINE_AUTO_RUNNER_ENABLED=true
DEV_PIPELINE_AUTO_RUNNER_INTERVAL_SECONDS=30
DEV_PIPELINE_AUTO_RUNNER_WORKER_ID=dev-auto-runner
DEV_PIPELINE_AUTO_RUNNER_RECONCILE_EXISTING=false
EOF
}

configure_tailscale_serve() {
  if ! command -v tailscale >/dev/null 2>&1; then
    echo "tailscale CLI not found; skipped Serve configuration."
    return
  fi
  if [[ ! -S "${TAILSCALE_SOCKET}" ]]; then
    echo "Tailscale socket not found at ${TAILSCALE_SOCKET}; skipped Serve configuration."
    return
  fi
  if tailscale --socket="${TAILSCALE_SOCKET}" serve status 2>/dev/null \
    | grep -q "tail0302c4.ts.net:${PORT}"; then
    echo "Tailscale Serve already has :${PORT}."
    return
  fi
  tailscale --socket="${TAILSCALE_SOCKET}" serve --bg --http="${PORT}" "http://127.0.0.1:${PORT}"
}

start_backend() {
  mkdir -p "${RUNTIME_DIR}"
  write_runtime_env

  local existing_pid
  existing_pid="$(listener_pid || true)"
  if [[ -n "${existing_pid}" ]]; then
    if [[ "$(health_environment || true)" != "dev" ]]; then
      echo "Port ${PORT} is in use by PID ${existing_pid}, but it is not a DEV backend." >&2
      exit 1
    fi
    echo "${existing_pid}" >"${PID_FILE}"
    echo "DEV backend already listening on ${PORT} with PID ${existing_pid}."
    configure_tailscale_serve
    return
  fi

  local python_bin="${ROOT_DIR}/.venv/bin/python"
  if [[ ! -x "${python_bin}" ]]; then
    python_bin="python3"
  fi

  local codex_command codex_use_exec codex_exec_args codex_resume_args
  codex_command="$(codex_env_value CODEX_COMMAND "codex")"
  codex_use_exec="$(codex_env_value CODEX_USE_EXEC "true")"
  codex_exec_args="$(codex_env_value CODEX_EXEC_ARGS "--skip-git-repo-check --color never --dangerously-bypass-approvals-and-sandbox")"
  codex_resume_args="$(codex_env_value CODEX_RESUME_ARGS "--skip-git-repo-check --dangerously-bypass-approvals-and-sandbox")"

  cd "${ROOT_DIR}"
  setsid -f env \
    API_PORT="${PORT}" \
    API_BASE_URL="${BASE_URL}" \
    CODEX_COMMAND="${codex_command}" \
    CODEX_USE_EXEC="${codex_use_exec}" \
    CODEX_EXEC_ARGS="${codex_exec_args}" \
    CODEX_RESUME_ARGS="${codex_resume_args}" \
    CODEX_WORKDIR="${ROOT_DIR}" \
    PROJECTS_ROOT="$(dirname "${ROOT_DIR}")" \
    CHAT_STORE_PATH="${DATA_DIR}/chat_store.sqlite3" \
    FEEDBACK_QUEUE_PATH="${DATA_DIR}/feedback_queue.json" \
    FEEDBACK_IMAGE_DIR="${DATA_DIR}/feedback_images" \
    FEEDBACK_AUDIO_DIR="${DATA_DIR}/feedback_audio" \
    ASSET_DEPOT_DIR="${DATA_DIR}/asset_depot" \
    PROJECT_FACTORY_STATE_DIR="${DATA_DIR}/project_factory_state" \
    BRIDGE_ENVIRONMENT="dev" \
    BRIDGE_STAGE_ID="dev-app" \
    BRIDGE_SPEC_ID="018" \
    BRIDGE_STAGE_BRANCH="main" \
    BRIDGE_STAGE_WORKTREE_PATH="${ROOT_DIR}" \
    BRIDGE_APP_CHANNEL="dev" \
    BRIDGE_UPDATER_CHANNEL="dev" \
    BRIDGE_APP_LABEL="Codex Mobile Bridge DEV" \
    BRIDGE_ENVIRONMENT_COLOR="#38BDF8" \
    DEV_PIPELINE_STATE_PATH="${ROOT_DIR}/.data/dev_pipeline_state.json" \
    DEV_PIPELINE_RUNTIME_ROOT="${RUNTIME_DIR}/runtime" \
    DEV_PIPELINE_AUTO_RUNNER_ENABLED="true" \
    DEV_PIPELINE_AUTO_RUNNER_INTERVAL_SECONDS="30" \
    DEV_PIPELINE_AUTO_RUNNER_WORKER_ID="dev-auto-runner" \
    DEV_PIPELINE_AUTO_RUNNER_RECONCILE_EXISTING="false" \
    "${python_bin}" -u main.py >>"${LOG_FILE}" 2>&1

  for _ in $(seq 1 20); do
    existing_pid="$(listener_pid || true)"
    if [[ -n "${existing_pid}" ]]; then
      echo "${existing_pid}" >"${PID_FILE}"
      configure_tailscale_serve
      echo "DEV backend started on ${PORT} with PID ${existing_pid}."
      return
    fi
    sleep 1
  done

  echo "DEV backend did not start on ${PORT}. Recent log:" >&2
  tail -n 120 "${LOG_FILE}" >&2 || true
  exit 1
}

stop_backend() {
  local pid=""
  if [[ -f "${PID_FILE}" ]]; then
    pid="$(cat "${PID_FILE}")"
  fi
  if ! pid_is_alive "${pid}"; then
    pid="$(listener_pid || true)"
  fi
  if [[ -z "${pid}" ]]; then
    rm -f "${PID_FILE}"
    echo "DEV backend is not running."
    return
  fi
  kill "${pid}"
  for _ in $(seq 1 10); do
    if ! pid_is_alive "${pid}"; then
      rm -f "${PID_FILE}"
      echo "Stopped DEV backend PID ${pid}."
      return
    fi
    sleep 1
  done
  echo "DEV backend PID ${pid} did not stop after SIGTERM." >&2
  exit 1
}

status_backend() {
  local failed=0
  local pid
  pid="$(listener_pid || true)"
  if [[ -n "${pid}" ]]; then
    echo "DEV backend listening on ${PORT} with PID ${pid}."
  else
    echo "DEV backend is not listening on ${PORT}."
    failed=1
  fi
  if health_json >/dev/null; then
    health_json | jq '{status, backend_commit, environment_identity: .environment_identity}'
    if [[ "$(health_environment || true)" != "dev" ]]; then
      echo "DEV backend health responded, but environment is not dev." >&2
      failed=1
    fi
  else
    echo "DEV backend health failed."
    failed=1
  fi
  if command -v tailscale >/dev/null 2>&1 && [[ -S "${TAILSCALE_SOCKET}" ]]; then
    if serve_has_port; then
      tailscale --socket="${TAILSCALE_SOCKET}" serve status | grep -A2 ":${PORT}" || true
    else
      echo "Tailscale Serve mapping for :${PORT} is missing." >&2
      failed=1
    fi
  else
    echo "Tailscale Serve status unavailable." >&2
    failed=1
  fi
  return "${failed}"
}

action="${1:-start}"
case "${action}" in
  start)
    start_backend
    ;;
  status)
    status_backend
    ;;
  restart)
    stop_backend
    start_backend
    ;;
  stop)
    stop_backend
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "Unknown action: ${action}" >&2
    usage >&2
    exit 1
    ;;
esac
