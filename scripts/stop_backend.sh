#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PID_FILE="${ROOT_DIR}/.run/backend.pid"

if [[ ! -f "${PID_FILE}" ]]; then
  echo "Backend is not running."
  exit 0
fi

PID="$(cat "${PID_FILE}")"
if kill -0 "${PID}" 2>/dev/null; then
  kill "${PID}"
  echo "Stopped backend PID ${PID}"
else
  echo "PID ${PID} is not running."
fi

rm -f "${PID_FILE}"
