#!/usr/bin/env bash

set -euo pipefail

USERNAME="${SECONDARY_CODEX_USERNAME:-sebastian-buenafont}"
FULL_NAME="${SECONDARY_CODEX_FULL_NAME:-Sebastian Buenafont}"
API_PORT="${SECONDARY_CODEX_API_PORT:-8001}"
SERVER_NAME="${SECONDARY_CODEX_SERVER_NAME:-codex-sebastian-buenafont}"
SOURCE_REPO="${SECONDARY_CODEX_SOURCE_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
TARGET_HOME="/home/${USERNAME}"
TARGET_REPO="${SECONDARY_CODEX_TARGET_REPO:-${TARGET_HOME}/codex-cli-mobile-bridge}"
PROJECTS_ROOT="${SECONDARY_CODEX_PROJECTS_ROOT:-${TARGET_HOME}/Projects}"
TAILSCALE_STATE_DIR="${TARGET_HOME}/.local/share/tailscale-userspace"
TAILSCALE_SOCKET="${TAILSCALE_STATE_DIR}/tailscaled.sock"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script with sudo:" >&2
  echo "  sudo $0" >&2
  exit 1
fi

if [[ ! -d "${SOURCE_REPO}" || ! -f "${SOURCE_REPO}/main.py" ]]; then
  echo "SOURCE_REPO does not look like codex-cli-mobile-bridge: ${SOURCE_REPO}" >&2
  exit 1
fi

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required. Install it with: sudo apt install -y rsync" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required. Install it with: sudo apt install -y python3 python3-venv" >&2
  exit 1
fi

if ! python3 -m venv --help >/dev/null 2>&1; then
  echo "python3-venv is required. Install it with: sudo apt install -y python3-venv" >&2
  exit 1
fi

PYTHON_VERSION="$(python3 - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
case "${PYTHON_VERSION}" in
  3.12|3.13|3.14) ;;
  *)
    echo "python3 ${PYTHON_VERSION} is too old; this project requires Python >= 3.12." >&2
    exit 1
    ;;
esac

if ! id "${USERNAME}" >/dev/null 2>&1; then
  useradd \
    --create-home \
    --shell /bin/bash \
    --comment "${FULL_NAME}" \
    "${USERNAME}"
  echo "Created Linux user: ${USERNAME}"
else
  echo "Linux user already exists: ${USERNAME}"
fi

install_tailscale_binary() {
  local binary_name="$1"
  local current_path
  current_path="$(command -v "${binary_name}" || true)"
  if [[ -n "${current_path}" && "${current_path}" != /home/* ]]; then
    return 0
  fi

  local batata_path="/home/batata/.local/bin/${binary_name}"
  if [[ -x "${batata_path}" ]]; then
    install -m 0755 "${batata_path}" "/usr/local/bin/${binary_name}"
    echo "Installed ${binary_name} to /usr/local/bin from ${batata_path}"
    return 0
  fi

  echo "${binary_name} is not globally available." >&2
  echo "Install Tailscale globally, then rerun:" >&2
  echo "  curl -fsSL https://tailscale.com/install.sh | sh" >&2
  exit 1
}

install_tailscale_binary tailscale
install_tailscale_binary tailscaled

CODEX_COMMAND="$(command -v codex || true)"
if [[ -z "${CODEX_COMMAND}" ]]; then
  for candidate in /snap/bin/codex /usr/local/bin/codex /usr/bin/codex; do
    if [[ -x "${candidate}" ]]; then
      CODEX_COMMAND="${candidate}"
      break
    fi
  done
fi
if [[ -z "${CODEX_COMMAND}" ]]; then
  echo "codex CLI is not globally available. Install it before using the new backend." >&2
  CODEX_COMMAND="codex"
fi

mkdir -p "${PROJECTS_ROOT}" "${TARGET_REPO}" "${TAILSCALE_STATE_DIR}"

rsync -a --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '.data/' \
  --exclude '.run/' \
  --exclude '.pytest_cache/' \
  --exclude '.ruff_cache/' \
  --exclude '**/__pycache__/' \
  "${SOURCE_REPO}/" "${TARGET_REPO}/"

cat > "${TARGET_REPO}/.env" <<EOF
SERVER_NAME=${SERVER_NAME}
CODEX_COMMAND=${CODEX_COMMAND}
CODEX_USE_EXEC=true
CODEX_EXEC_ARGS=--skip-git-repo-check --color never --dangerously-bypass-approvals-and-sandbox
CODEX_RESUME_ARGS=--skip-git-repo-check --dangerously-bypass-approvals-and-sandbox
CODEX_WORKDIR=${PROJECTS_ROOT}
PROJECTS_ROOT=${PROJECTS_ROOT}
CHAT_STORE_BACKEND=sqlite
CHAT_STORE_PATH=.data/chat_store.sqlite3
TAILSCALE_SOCKET=${TAILSCALE_SOCKET}
API_HOST=0.0.0.0
API_PORT=${API_PORT}
API_BASE_URL=http://localhost:${API_PORT}
EOF

chown -R "${USERNAME}:${USERNAME}" "${TARGET_REPO}" "${PROJECTS_ROOT}" "${TARGET_HOME}/.local"

run_as_secondary_user() {
  runuser -u "${USERNAME}" -- env \
    "HOME=${TARGET_HOME}" \
    "USER=${USERNAME}" \
    "LOGNAME=${USERNAME}" \
    "$@"
}

run_as_secondary_user bash -lc "
  set -euo pipefail
  cd '${TARGET_REPO}'
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -e .
  ./scripts/install_user_services.sh
"

loginctl enable-linger "${USERNAME}"

USER_UID="$(id -u "${USERNAME}")"
USER_SYSTEMCTL=(
  runuser -u "${USERNAME}" -- env
  "HOME=${TARGET_HOME}"
  "USER=${USERNAME}"
  "LOGNAME=${USERNAME}"
  "XDG_RUNTIME_DIR=/run/user/${USER_UID}"
  systemctl --user
)

for _ in 1 2 3 4 5; do
  if [[ -S "/run/user/${USER_UID}/bus" ]]; then
    break
  fi
  sleep 1
done

SERVICES_STARTED=false
if "${USER_SYSTEMCTL[@]}" daemon-reload; then
  "${USER_SYSTEMCTL[@]}" enable --now codex-mobile-bridge-backend.service
  "${USER_SYSTEMCTL[@]}" enable --now codex-mobile-bridge-tailscaled.service
  SERVICES_STARTED=true
else
  echo "Could not reach ${USERNAME}'s systemd user manager yet." >&2
  echo "The account and repo were prepared; start services after logging in once or after reboot." >&2
fi

cat <<EOF

Secondary Codex Mobile Bridge user is prepared.

User:
  ${USERNAME} (${FULL_NAME})

Backend:
  ${TARGET_REPO}
  http://127.0.0.1:${API_PORT}

Projects root:
  ${PROJECTS_ROOT}

Services started now:
  ${SERVICES_STARTED}

Next manual steps:
  1. Log Codex CLI in as ${USERNAME}:
       sudo -iu ${USERNAME} codex login

  2. Authenticate this userspace Tailscale daemon with Sebastian's account:
       sudo -iu ${USERNAME}
       tailscale --socket='${TAILSCALE_SOCKET}' up --hostname='${SERVER_NAME}'

  3. After Tailscale auth succeeds, enable Serve:
       systemctl --user enable --now codex-mobile-bridge-tailscale-serve.service
       tailscale --socket='${TAILSCALE_SOCKET}' serve status

  4. Verify locally:
       curl -fsS http://127.0.0.1:${API_PORT}/health
       curl -fsS http://127.0.0.1:${API_PORT}/workspaces

EOF
