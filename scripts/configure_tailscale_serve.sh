#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

export PATH="${HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

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

  printf '%s\n' "${line#*=}"
}

API_PORT="$(read_env_value "API_PORT" "${ENV_FILE}" || true)"
TAILSCALE_SOCKET="$(read_env_value "TAILSCALE_SOCKET" "${ENV_FILE}" || true)"

API_PORT="${API_PORT:-8000}"
TAILSCALE_SOCKET="${TAILSCALE_SOCKET:-${HOME}/.local/share/tailscale-userspace/tailscaled.sock}"
TARGET_URL="http://127.0.0.1:${API_PORT}"

if ! command -v tailscale >/dev/null 2>&1; then
  echo "tailscale not found in PATH" >&2
  exit 1
fi

configure_serve() {
  local -a tailscale_args=("$@")
  local status
  status="$(tailscale "${tailscale_args[@]}" serve status --json 2>/dev/null || printf '{}')"

  if ! proxy_matches "${status}" "443"; then
    tailscale "${tailscale_args[@]}" serve --bg --https=443 --yes "${TARGET_URL}"
  fi

  status="$(tailscale "${tailscale_args[@]}" serve status --json 2>/dev/null || printf '{}')"
  if ! proxy_matches "${status}" "80"; then
    tailscale "${tailscale_args[@]}" serve --bg --http=80 --yes "${TARGET_URL}"
  fi
}

proxy_matches() {
  local status_json="$1"
  local port="$2"
  STATUS_JSON="${status_json}" python3 - "${port}" "${TARGET_URL}" <<'PY'
import json
import os
import sys

port = sys.argv[1]
target = sys.argv[2]
try:
    payload = json.loads(os.environ.get("STATUS_JSON", "{}"))
except json.JSONDecodeError:
    raise SystemExit(1)

for key, value in (payload.get("Web") or {}).items():
    if not key.endswith(f":{port}"):
        continue
    handlers = value.get("Handlers") or {}
    root = handlers.get("/") or {}
    if root.get("Proxy") == target:
        raise SystemExit(0)
raise SystemExit(1)
PY
}

if [[ -n "${TAILSCALE_SOCKET}" ]]; then
  configure_serve --socket="${TAILSCALE_SOCKET}"
  exit 0
fi

configure_serve
