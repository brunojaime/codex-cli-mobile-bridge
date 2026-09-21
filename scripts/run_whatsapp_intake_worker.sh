#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Python virtual environment is missing: ${PYTHON_BIN}" >&2
  exit 1
fi

cd "${ROOT_DIR}"
exec "${PYTHON_BIN}" -m services.whatsapp_ingest.worker
