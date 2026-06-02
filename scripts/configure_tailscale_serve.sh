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

if [[ -n "${TAILSCALE_SOCKET}" ]]; then
  if tailscale --socket="${TAILSCALE_SOCKET}" serve status | grep -Fq "|-- / proxy ${TARGET_URL}"; then
    exit 0
  fi
  exec tailscale --socket="${TAILSCALE_SOCKET}" serve --http=80 "${TARGET_URL}"
fi

if tailscale serve status | grep -Fq "|-- / proxy ${TARGET_URL}"; then
  exit 0
fi

exec tailscale serve --http=80 "${TARGET_URL}"
