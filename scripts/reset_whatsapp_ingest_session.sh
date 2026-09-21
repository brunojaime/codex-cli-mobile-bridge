#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
AUTH_DIR="${WHATSAPP_AUTH_DIR:-${ROOT_DIR}/.data/whatsapp_ingest/auth}"
SERVICE="nienfos-whatsapp-ingest.service"

if [[ ! -d "${AUTH_DIR}" ]]; then
  echo "No WhatsApp session directory exists at ${AUTH_DIR}." >&2
  exit 1
fi

BACKUP_DIR="${AUTH_DIR}.backup-$(date -u +%Y%m%dT%H%M%SZ)"
systemctl --user stop "${SERVICE}"
mv -- "${AUTH_DIR}" "${BACKUP_DIR}"
mkdir -m 700 -- "${AUTH_DIR}"
systemctl --user start "${SERVICE}"

echo "Previous session moved to ${BACKUP_DIR}"
echo "A new QR will appear in the private WhatsApp dashboard."
