#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

# shellcheck source=scripts/backend_process_lib.sh
source "${ROOT_DIR}/scripts/backend_process_lib.sh"

API_PORT="${API_PORT:-$(backend_read_env_value API_PORT "${ENV_FILE}" || true)}"
API_PORT="${API_PORT:-8000}"
TAILSCALE_SOCKET="${TAILSCALE_SOCKET:-$(backend_read_env_value TAILSCALE_SOCKET "${ENV_FILE}" || true)}"
LOCAL_BASE_URL="http://127.0.0.1:${API_PORT}"

check_json_endpoint() {
  local url="$1"
  local label="$2"
  local body
  body="$(curl -fsS --max-time 15 "${url}")"
  python3 - "$label" "$body" <<'PY'
from __future__ import annotations

import json
import sys

label, body = sys.argv[1], sys.argv[2]
payload = json.loads(body)
if label == "health":
    assert payload.get("status") == "ok", payload
    assert payload.get("features", {}).get("project_factory") is True, payload
elif label == "project-factory/options":
    assert payload.get("kind") == "codex.projectFactoryOptions", payload
    workflow = payload.get("creation_workflow") or {}
    assert workflow.get("mode") == "generator_reviewer_pairs", payload
    assert workflow.get("generator_runs") == 20, payload
    assert workflow.get("reviewer_runs") == 20, payload
print(f"{label} ok")
PY
}

check_json_endpoint "${LOCAL_BASE_URL}/health" "health"
check_json_endpoint "${LOCAL_BASE_URL}/project-factory/options" "project-factory/options"

if [[ -n "${TAILSCALE_SOCKET}" ]]; then
  if ! command -v tailscale >/dev/null 2>&1; then
    echo "tailscale CLI not available; local backend checks passed."
    exit 0
  fi
  serve_status="$(tailscale --socket="${TAILSCALE_SOCKET}" serve status || true)"
  if [[ "${serve_status}" != *"http://127.0.0.1:${API_PORT}"* ]]; then
    echo "Tailscale Serve is not proxying to ${LOCAL_BASE_URL}." >&2
    echo "${serve_status}" >&2
    exit 1
  fi
  echo "tailscale serve ok"
else
  health_json="$(curl -fsS --max-time 15 "${LOCAL_BASE_URL}/health")"
  public_url="$(python3 - "$health_json" <<'PY'
from __future__ import annotations

import json
import sys

payload = json.loads(sys.argv[1])
print(payload.get("tailscale_suggested_url") or "")
PY
)"
  if [[ -n "${public_url}" ]]; then
    check_json_endpoint "${public_url}/project-factory/options" "project-factory/options"
  else
    echo "No Tailscale public URL reported; local backend checks passed."
  fi
fi
