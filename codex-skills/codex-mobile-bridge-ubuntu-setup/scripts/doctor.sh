#!/usr/bin/env bash

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
FAILURES=0
WARNINGS=0

usage() {
  cat <<'EOF'
Usage:
  codex-skills/codex-mobile-bridge-ubuntu-setup/scripts/doctor.sh [--require-backend] [--skip-flutter]

Checks a local codex-cli-mobile-bridge checkout for Ubuntu/Linux portability:
commands, .env, PROJECTS_ROOT, Python environment, Codex CLI, backend health,
Tailscale status, and Flutter tooling.

Options:
  --require-backend  fail if http://127.0.0.1:${API_PORT}/health is not reachable
  --skip-flutter     skip Flutter command and dependency checks
EOF
}

REQUIRE_BACKEND=false
SKIP_FLUTTER=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --require-backend)
      REQUIRE_BACKEND=true
      shift
      ;;
    --skip-flutter)
      SKIP_FLUTTER=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

ok() {
  printf '[OK] %s\n' "$1"
}

warn() {
  WARNINGS=$((WARNINGS + 1))
  printf '[WARN] %s\n' "$1"
}

fail() {
  FAILURES=$((FAILURES + 1))
  printf '[FAIL] %s\n' "$1"
}

env_value() {
  local key="$1"
  [[ -f "${ENV_FILE}" ]] || return 1
  awk -F= -v key="${key}" '
    $0 !~ /^[[:space:]]*#/ && $1 == key {
      value = substr($0, index($0, "=") + 1)
    }
    END {
      if (value != "") {
        print value
      }
    }
  ' "${ENV_FILE}"
}

require_command() {
  local command_name="$1"
  local install_hint="$2"
  if command -v "${command_name}" >/dev/null 2>&1; then
    ok "${command_name} is installed"
  else
    fail "${command_name} is missing (${install_hint})"
  fi
}

optional_command() {
  local command_name="$1"
  local install_hint="$2"
  if command -v "${command_name}" >/dev/null 2>&1; then
    ok "${command_name} is installed"
  else
    warn "${command_name} is missing (${install_hint})"
  fi
}

printf 'Codex CLI Mobile Bridge doctor\n'
printf 'Root: %s\n\n' "${ROOT_DIR}"

if [[ -f "${ROOT_DIR}/main.py" && -f "${ROOT_DIR}/pyproject.toml" && -d "${ROOT_DIR}/backend" ]]; then
  ok "repository shape looks correct"
else
  fail "run this script from inside a codex-cli-mobile-bridge checkout"
fi

require_command python3 "sudo apt install -y python3 python3-venv"
require_command uv "curl -LsSf https://astral.sh/uv/install.sh | sh"
optional_command ffmpeg "sudo apt install -y ffmpeg; recommended for audio tooling and diagnostics"
require_command curl "sudo apt install -y curl"
require_command git "sudo apt install -y git"
require_command codex "install and authenticate Codex CLI on this machine"

if [[ "${SKIP_FLUTTER}" == "false" ]]; then
  optional_command flutter "install Flutter SDK and add it to PATH"
fi

if [[ -f "${ENV_FILE}" ]]; then
  ok ".env exists"
else
  fail ".env is missing; run cp .env.example .env"
fi

SERVER_NAME="$(env_value SERVER_NAME || true)"
PROJECTS_ROOT="$(env_value PROJECTS_ROOT || true)"
API_PORT="$(env_value API_PORT || true)"
TAILSCALE_SOCKET="$(env_value TAILSCALE_SOCKET || true)"
CHAT_STORE_BACKEND="$(env_value CHAT_STORE_BACKEND || true)"
CHAT_STORE_PATH="$(env_value CHAT_STORE_PATH || true)"

API_PORT="${API_PORT:-8000}"

if [[ -n "${SERVER_NAME}" ]]; then
  ok "SERVER_NAME=${SERVER_NAME}"
else
  fail "SERVER_NAME is empty in .env"
fi

if [[ -n "${PROJECTS_ROOT}" && "${PROJECTS_ROOT}" != "/absolute/path/to/your/projects" ]]; then
  if [[ -d "${PROJECTS_ROOT}" ]]; then
    ok "PROJECTS_ROOT exists: ${PROJECTS_ROOT}"
  else
    fail "PROJECTS_ROOT does not exist: ${PROJECTS_ROOT}"
  fi
else
  fail "PROJECTS_ROOT must be set to a real parent folder"
fi

if [[ "${CHAT_STORE_BACKEND:-sqlite}" == "sqlite" ]]; then
  ok "CHAT_STORE_BACKEND=sqlite"
  if [[ -n "${CHAT_STORE_PATH}" ]]; then
    ok "CHAT_STORE_PATH=${CHAT_STORE_PATH}"
  else
    warn "CHAT_STORE_PATH is empty; default persistence may not be explicit"
  fi
else
  warn "CHAT_STORE_BACKEND=${CHAT_STORE_BACKEND:-unset}; sqlite is recommended for persisted history"
fi

if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  ok ".venv exists"
else
  fail ".venv missing; run python3 -m venv .venv && source .venv/bin/activate && uv pip install -e '.[dev]'"
fi

if command -v codex >/dev/null 2>&1; then
  if codex --version >/dev/null 2>&1; then
    ok "codex command responds"
  else
    fail "codex is installed but did not respond to --version"
  fi
fi

HEALTH_URL="http://127.0.0.1:${API_PORT}/health"
WORKSPACES_URL="http://127.0.0.1:${API_PORT}/workspaces"

if curl -fsS "${HEALTH_URL}" >/tmp/codex-mobile-bridge-health.json 2>/dev/null; then
  ok "backend health is reachable: ${HEALTH_URL}"
  if curl -fsS "${WORKSPACES_URL}" >/tmp/codex-mobile-bridge-workspaces.json 2>/dev/null; then
    ok "workspaces endpoint is reachable: ${WORKSPACES_URL}"
  else
    warn "backend is up but workspaces endpoint failed: ${WORKSPACES_URL}"
  fi
else
  if [[ "${REQUIRE_BACKEND}" == "true" ]]; then
    fail "backend is not reachable at ${HEALTH_URL}"
  else
    warn "backend is not running at ${HEALTH_URL}; start it with ./scripts/run_backend_detached.sh"
  fi
fi

if command -v tailscale >/dev/null 2>&1; then
  ok "tailscale is installed"
  if [[ -n "${TAILSCALE_SOCKET}" ]]; then
    if tailscale --socket="${TAILSCALE_SOCKET}" status >/dev/null 2>&1; then
      ok "userspace Tailscale responds on ${TAILSCALE_SOCKET}"
    else
      warn "TAILSCALE_SOCKET is set but userspace Tailscale is not responding"
    fi
  else
    if tailscale status >/dev/null 2>&1; then
      ok "standard Tailscale daemon responds"
    else
      warn "tailscale is installed but not connected; run sudo systemctl enable --now tailscaled && sudo tailscale up"
    fi
  fi
else
  warn "tailscale is not installed; install it if the phone needs Tailnet access"
fi

if [[ "${SKIP_FLUTTER}" == "false" && -d "${ROOT_DIR}/frontend/mobile_app" ]]; then
  if command -v flutter >/dev/null 2>&1; then
    if (cd "${ROOT_DIR}/frontend/mobile_app" && flutter pub get >/dev/null 2>&1); then
      ok "Flutter dependencies resolve"
    else
      warn "flutter pub get failed in frontend/mobile_app"
    fi
  fi
fi

printf '\nSummary: %d failure(s), %d warning(s)\n' "${FAILURES}" "${WARNINGS}"

if [[ "${FAILURES}" -gt 0 ]]; then
  exit 1
fi
