#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/install_control_services.sh [--enable-now]

Installs user-level systemd units for:
  - codex-mobile-control.service on port 8010
  - codex-mobile-bridge-dev.service on port 8001

The existing codex-mobile-bridge-backend.service remains Production on port 8000.
No running service is restarted unless --enable-now is supplied. Production is
never restarted by this installer.
EOF
}

ENABLE_NOW=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --enable-now)
      ENABLE_NOW=true
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
USER_SYSTEMD_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
CONTROL_ENV_FILE="${ROOT_DIR}/.control.env"
DEV_ENV_FILE="${ROOT_DIR}/.env.dev"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Missing ${PYTHON_BIN}. Install project dependencies first." >&2
  exit 1
fi

mkdir -p "${USER_SYSTEMD_DIR}"

if [[ ! -f "${CONTROL_ENV_FILE}" ]]; then
  CONTROL_TOKEN="$(${PYTHON_BIN} -c 'import secrets; print(secrets.token_urlsafe(48))')"
  CODEX_BIN="$(command -v codex || true)"
  CODEX_BIN="${CODEX_BIN:-codex}"
  umask 077
  {
    echo "CONTROL_HOST=0.0.0.0"
    echo "CONTROL_PORT=8010"
    echo "CONTROL_TOKEN=${CONTROL_TOKEN}"
    echo "CONTROL_DRAIN_TIMEOUT_SECONDS=3600"
    echo "CONTROL_RESTART_TIMEOUT_SECONDS=90"
    echo "CONTROL_POLL_SECONDS=2"
    echo "CONTROL_CODEX_COMMAND=${CODEX_BIN}"
  } >"${CONTROL_ENV_FILE}"
  echo "Created ${CONTROL_ENV_FILE} with a random control token."
fi

if ! grep -q '^CONTROL_CODEX_COMMAND=' "${CONTROL_ENV_FILE}"; then
  CODEX_BIN="$(command -v codex || true)"
  CODEX_BIN="${CODEX_BIN:-codex}"
  printf 'CONTROL_CODEX_COMMAND=%s\n' "${CODEX_BIN}" >>"${CONTROL_ENV_FILE}"
fi

if [[ ! -f "${DEV_ENV_FILE}" ]]; then
  cp "${ROOT_DIR}/config/dev.env.example" "${DEV_ENV_FILE}"
  echo "Created ${DEV_ENV_FILE}."
fi

cat >"${USER_SYSTEMD_DIR}/codex-mobile-control.service" <<EOF
[Unit]
Description=Codex Mobile deterministic control agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${ROOT_DIR}
Environment=HOME=${HOME}
Environment=PATH=${HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=${CONTROL_ENV_FILE}
ExecStart=${PYTHON_BIN} -m control_agent.main
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
EOF

cat >"${USER_SYSTEMD_DIR}/codex-mobile-bridge-dev.service" <<EOF
[Unit]
Description=Codex CLI Mobile Bridge development backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${ROOT_DIR}
Environment=HOME=${HOME}
Environment=PATH=${HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=-${ROOT_DIR}/.env
EnvironmentFile=${DEV_ENV_FILE}
ExecStart=${PYTHON_BIN} ${ROOT_DIR}/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload

if [[ "${ENABLE_NOW}" == "true" ]]; then
  systemctl --user enable --now codex-mobile-control.service
  systemctl --user enable --now codex-mobile-bridge-dev.service
fi

echo
echo "Control services installed. Production was not restarted."
TAILSCALE_SOCKET="$(sed -n 's/^TAILSCALE_SOCKET=//p' "${ROOT_DIR}/.env" | tail -n 1)"
if [[ -n "${TAILSCALE_SOCKET}" ]]; then
  TAILSCALE_DNS_NAME="$(tailscale --socket="${TAILSCALE_SOCKET}" status --json 2>/dev/null | "${PYTHON_BIN}" -c 'import json,sys; print(json.load(sys.stdin).get("Self", {}).get("DNSName", "").rstrip("."))' || true)"
else
  TAILSCALE_DNS_NAME="$(tailscale status --json 2>/dev/null | "${PYTHON_BIN}" -c 'import json,sys; print(json.load(sys.stdin).get("Self", {}).get("DNSName", "").rstrip("."))' || true)"
fi
echo "Control URL over Tailscale: https://${TAILSCALE_DNS_NAME:-<tailscale-dns-name>}/ops"
echo "Read the mobile token with: scripts/show_control_token.sh"
echo "Enable services with: systemctl --user enable --now codex-mobile-control.service codex-mobile-bridge-dev.service"
