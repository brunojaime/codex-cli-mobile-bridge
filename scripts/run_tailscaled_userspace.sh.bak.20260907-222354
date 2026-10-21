#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${HOME}/.local/share/tailscale-userspace"
SOCKET_PATH="${STATE_DIR}/tailscaled.sock"
STATE_PATH="${STATE_DIR}/tailscaled.state"
SOCKS5_SERVER="${TAILSCALE_SOCKS5_SERVER:-127.0.0.1:1055}"
HTTP_PROXY_LISTEN="${TAILSCALE_OUTBOUND_HTTP_PROXY_LISTEN:-127.0.0.1:1056}"

mkdir -p "${STATE_DIR}"

TAILSCALED_BIN="${TAILSCALED_BIN:-$(command -v tailscaled)}"

if [[ -z "${TAILSCALED_BIN}" ]]; then
  echo "tailscaled not found in PATH. Set TAILSCALED_BIN explicitly." >&2
  exit 1
fi

exec "${TAILSCALED_BIN}" \
  --tun=userspace-networking \
  --socket="${SOCKET_PATH}" \
  --state="${STATE_PATH}" \
  --socks5-server="${SOCKS5_SERVER}" \
  --outbound-http-proxy-listen="${HTTP_PROXY_LISTEN}"
