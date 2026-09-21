#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVICE_DIR="${ROOT_DIR}/services/whatsapp_ingest"

if [[ -f "${HOME}/.nvm/nvm.sh" ]]; then
  # shellcheck disable=SC1091
  source "${HOME}/.nvm/nvm.sh"
  nvm use 22 >/dev/null
fi

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js is not installed." >&2
  exit 1
fi

NODE_MAJOR="$(node -p 'Number(process.versions.node.split(".")[0])')"
if (( NODE_MAJOR < 20 )); then
  echo "WhatsApp intake requires Node.js 20 or newer; found $(node --version)." >&2
  exit 1
fi

if [[ ! -d "${SERVICE_DIR}/node_modules" ]]; then
  echo "Dependencies are missing. Run: cd ${SERVICE_DIR} && npm ci" >&2
  exit 1
fi

cd "${ROOT_DIR}"
exec node "${SERVICE_DIR}/src/index.mjs"
