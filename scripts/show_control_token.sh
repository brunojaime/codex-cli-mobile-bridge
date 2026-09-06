#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONTROL_ENV_FILE="${ROOT_DIR}/.control.env"

if [[ ! -f "${CONTROL_ENV_FILE}" ]]; then
  echo "${CONTROL_ENV_FILE} does not exist. Run scripts/install_control_services.sh first." >&2
  exit 1
fi

TOKEN_LINE="$(grep '^CONTROL_TOKEN=' "${CONTROL_ENV_FILE}" | tail -n 1)"
if [[ -z "${TOKEN_LINE}" ]]; then
  echo "CONTROL_TOKEN is missing from ${CONTROL_ENV_FILE}." >&2
  exit 1
fi

printf '%s\n' "${TOKEN_LINE#CONTROL_TOKEN=}"
