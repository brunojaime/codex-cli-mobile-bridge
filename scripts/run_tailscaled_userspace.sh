#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${HOME}/.local/share/tailscale-userspace"
SOCKET_PATH="${STATE_DIR}/tailscaled.sock"
STATE_PATH="${STATE_DIR}/tailscaled.state"

mkdir -p "${STATE_DIR}"

TAILSCALED_BIN="${TAILSCALED_BIN:-$(command -v tailscaled)}"

if [[ -z "${TAILSCALED_BIN}" ]]; then
  echo "tailscaled not found in PATH. Set TAILSCALED_BIN explicitly." >&2
  exit 1
fi

exec "${TAILSCALED_BIN}" \
  --tun=userspace-networking \
  --socket="${SOCKET_PATH}" \
  --state="${STATE_PATH}"
