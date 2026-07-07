#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/safe_restart_backend.sh [--url URL] [--timeout SECONDS] [--poll SECONDS]
                                  [--systemd-user|--systemd|--detached|--no-restart]

Activates backend drain mode, waits until no non-terminal jobs remain, then restarts
the backend. Drain mode rejects new jobs while existing accepted runs finish.
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
SERVICE_NAME="codex-mobile-bridge-backend.service"

read_env_value() {
  local key="$1"
  local file="$2"
  if [[ ! -f "${file}" ]]; then
    return 1
  fi

  local line
  line="$(grep -E "^${key}=" "${file}" | tail -n 1 || true)"
  if [[ -z "${line}" ]]; then
    return 1
  fi

  printf '%s\n' "${line#*=}" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

require_value() {
  local option="$1"
  local value="${2:-}"
  if [[ -z "${value}" || "${value}" == --* ]]; then
    echo "${option} requires a value." >&2
    exit 1
  fi
}

require_positive_integer() {
  local option="$1"
  local value="$2"
  if [[ ! "${value}" =~ ^[0-9]+$ ]]; then
    echo "${option} must be a positive integer." >&2
    exit 1
  fi
  if (( value <= 0 )); then
    echo "${option} must be a positive integer." >&2
    exit 1
  fi
}

validate_url() {
  local value="$1"
  if [[ ! "${value}" =~ ^https?://[^[:space:]]+$ ]]; then
    echo "--url must be an http:// or https:// URL." >&2
    exit 1
  fi
}

API_PORT="${API_PORT:-$(read_env_value API_PORT "${ENV_FILE}" || true)}"
API_PORT="${API_PORT:-8000}"
API_BASE_URL="${API_BASE_URL:-$(read_env_value API_BASE_URL "${ENV_FILE}" || true)}"
API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:${API_PORT}}"
TIMEOUT_SECONDS=3600
POLL_SECONDS=5
RESTART_MODE="auto"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url)
      require_value "$1" "${2:-}"
      API_BASE_URL="$2"
      shift 2
      ;;
    --timeout)
      require_value "$1" "${2:-}"
      require_positive_integer "$1" "$2"
      TIMEOUT_SECONDS="$2"
      shift 2
      ;;
    --poll)
      require_value "$1" "${2:-}"
      require_positive_integer "$1" "$2"
      POLL_SECONDS="$2"
      shift 2
      ;;
    --systemd-user)
      RESTART_MODE="systemd-user"
      shift
      ;;
    --systemd)
      RESTART_MODE="systemd"
      shift
      ;;
    --detached)
      RESTART_MODE="detached"
      shift
      ;;
    --no-restart)
      RESTART_MODE="none"
      shift
      ;;
    -h|--help)
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

validate_url "${API_BASE_URL}"
require_positive_integer "--timeout" "${TIMEOUT_SECONDS}"
require_positive_integer "--poll" "${POLL_SECONDS}"

api_request() {
  local method="$1"
  local path="$2"
  local body="${3:-}"

  python3 - "$method" "${API_BASE_URL}${path}" "$body" <<'PY'
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

method, url, body = sys.argv[1], sys.argv[2], sys.argv[3]
data = body.encode("utf-8") if body else None
request = urllib.request.Request(
    url,
    data=data,
    method=method,
    headers={"Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        print(response.read().decode("utf-8"))
except urllib.error.HTTPError as exc:
    sys.stderr.write(exc.read().decode("utf-8") + "\n")
    raise SystemExit(exc.code)
except urllib.error.URLError as exc:
    sys.stderr.write(f"Cannot reach backend at {url}: {exc}\n")
    raise SystemExit(1)
PY
}

json_field() {
  local field="$1"
  local payload="$2"
  python3 - "$field" "$payload" <<'PY'
from __future__ import annotations

import json
import sys

payload = json.loads(sys.argv[2])
value = payload.get(sys.argv[1])
if isinstance(value, bool):
    print("true" if value else "false")
else:
    print(value)
PY
}

detect_restart_mode() {
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

restart_backend() {
  local mode="$1"
  case "${mode}" in
    systemd-user)
      systemctl --user restart "${SERVICE_NAME}"
      ;;
    systemd)
      systemctl restart "${SERVICE_NAME}"
      ;;
    detached)
      "${ROOT_DIR}/scripts/stop_backend.sh"
      "${ROOT_DIR}/scripts/run_backend_detached.sh"
      ;;
    none)
      echo "Drain is complete; restart was skipped because --no-restart was set."
      ;;
    *)
      echo "Unsupported restart mode: ${mode}" >&2
      exit 1
      ;;
  esac
}

disable_drain() {
  api_request POST /maintenance/drain '{"requested":false}' >/dev/null
}

echo "Activating backend drain at ${API_BASE_URL}"
status_json="$(api_request POST /maintenance/drain '{"requested":true}')"
deadline=$((SECONDS + TIMEOUT_SECONDS))

while true; do
  active_count="$(json_field active_job_count "${status_json}")"
  ready="$(json_field ready_to_restart "${status_json}")"
  echo "Drain status: active_job_count=${active_count}, ready_to_restart=${ready}"

  if [[ "${ready}" == "true" ]]; then
    break
  fi
  if (( SECONDS >= deadline )); then
    echo "Timed out waiting for active jobs to finish; drain remains enabled." >&2
    exit 124
  fi
  sleep "${POLL_SECONDS}"
  status_json="$(api_request GET /maintenance/drain)"
done

if [[ "${RESTART_MODE}" == "auto" ]]; then
  RESTART_MODE="$(detect_restart_mode)"
fi

echo "Restarting backend with mode: ${RESTART_MODE}"
if [[ "${RESTART_MODE}" == "none" ]]; then
  disable_drain
  echo "Drain is complete; restart was skipped and drain has been disabled."
  exit 0
fi

if ! restart_backend "${RESTART_MODE}"; then
  echo "Backend restart failed; attempting to disable drain." >&2
  disable_drain || true
  exit 1
fi

if ! "${ROOT_DIR}/scripts/validate_backend_post_release.sh"; then
  echo "Backend post-restart validation failed; attempting to disable drain." >&2
  disable_drain || true
  exit 1
fi

disable_drain
echo "Backend restarted and post-restart validation passed."
