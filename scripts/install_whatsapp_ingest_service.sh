#!/usr/bin/env bash

set -euo pipefail

ENABLE_NOW=false
if [[ "${1:-}" == "--enable-now" ]]; then
  ENABLE_NOW=true
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--enable-now]" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVICE_DIR="${ROOT_DIR}/services/whatsapp_ingest"
USER_SYSTEMD_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
UNIT="nienfos-whatsapp-ingest.service"

if [[ -f "${HOME}/.nvm/nvm.sh" ]]; then
  # shellcheck disable=SC1091
  source "${HOME}/.nvm/nvm.sh"
  nvm use 22 >/dev/null
fi

cd "${SERVICE_DIR}"
npm ci
npm test

mkdir -p "${USER_SYSTEMD_DIR}"
cat > "${USER_SYSTEMD_DIR}/${UNIT}" <<EOF
[Unit]
Description=Nienfos silent WhatsApp group intake
After=network-online.target codex-mobile-bridge-tailscaled.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${ROOT_DIR}
ExecStart=${ROOT_DIR}/scripts/run_whatsapp_ingest.sh
Restart=always
RestartSec=5
UMask=0077

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
if [[ "${ENABLE_NOW}" == "true" ]]; then
  systemctl --user enable --now "${UNIT}"
fi

echo "Installed ${USER_SYSTEMD_DIR}/${UNIT}"
echo "Status: systemctl --user status ${UNIT}"
echo "Logs:  journalctl --user -u ${UNIT} -f"
