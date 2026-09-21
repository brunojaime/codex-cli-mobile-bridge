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
USER_SYSTEMD_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
UNIT="nienfos-whatsapp-intake-worker.service"

"${ROOT_DIR}/.venv/bin/python" -m pytest -q \
  "${ROOT_DIR}/tests/test_whatsapp_intake_worker.py"

mkdir -p "${USER_SYSTEMD_DIR}"
cat > "${USER_SYSTEMD_DIR}/${UNIT}" <<EOF
[Unit]
Description=Nienfos WhatsApp intake transcription and Codex triage worker
After=network-online.target codex-mobile-bridge-backend.service nienfos-whatsapp-ingest.service
Wants=network-online.target codex-mobile-bridge-backend.service

[Service]
Type=simple
WorkingDirectory=${ROOT_DIR}
ExecStart=${ROOT_DIR}/scripts/run_whatsapp_intake_worker.sh
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
