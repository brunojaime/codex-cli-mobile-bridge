#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/install_user_services.sh [--enable-now]

What it does:
  - Creates systemd user services for the backend
  - Creates userspace Tailscale services when TAILSCALE_SOCKET is set in .env
  - Reloads the user systemd daemon

Options:
  --enable-now   Enable and start the generated services immediately
EOF
}

ENABLE_NOW=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --enable-now)
      ENABLE_NOW=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
USER_SYSTEMD_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"

BACKEND_SERVICE="codex-mobile-bridge-backend.service"
TAILSCALED_SERVICE="codex-mobile-bridge-tailscaled.service"
TAILSCALE_SERVE_SERVICE="codex-mobile-bridge-tailscale-serve.service"

mkdir -p "${USER_SYSTEMD_DIR}"

read_env_value() {
  local key="$1"
  local file="$2"
  if [[ ! -f "${file}" ]]; then
    return 1
  fi

  local line
  line="$(grep -E "^${key}=" "${file}" | tail -n 1 || true)"
  if [[ -z "${line}" ]]; then
    return 1
  fi

  printf '%s\n' "${line#*=}"
}

TAILSCALE_SOCKET="$(read_env_value "TAILSCALE_SOCKET" "${ENV_FILE}" || true)"

cat > "${USER_SYSTEMD_DIR}/${BACKEND_SERVICE}" <<EOF
[Unit]
Description=Codex CLI Mobile Bridge backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${ROOT_DIR}
ExecStart=${ROOT_DIR}/scripts/run_backend_foreground.sh
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

echo "Wrote ${USER_SYSTEMD_DIR}/${BACKEND_SERVICE}"

INSTALL_USERSPACE_TAILSCALE=false
if [[ -n "${TAILSCALE_SOCKET}" ]]; then
  INSTALL_USERSPACE_TAILSCALE=true
  cat > "${USER_SYSTEMD_DIR}/${TAILSCALED_SERVICE}" <<EOF
[Unit]
Description=Userspace tailscaled for Codex CLI Mobile Bridge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${ROOT_DIR}
ExecStart=${ROOT_DIR}/scripts/run_tailscaled_userspace.sh
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

  cat > "${USER_SYSTEMD_DIR}/${TAILSCALE_SERVE_SERVICE}" <<EOF
[Unit]
Description=Expose Codex CLI Mobile Bridge through Tailscale Serve
After=${BACKEND_SERVICE} ${TAILSCALED_SERVICE}
Wants=${BACKEND_SERVICE} ${TAILSCALED_SERVICE}

[Service]
Type=oneshot
WorkingDirectory=${ROOT_DIR}
ExecStart=${ROOT_DIR}/scripts/configure_tailscale_serve.sh
RemainAfterExit=yes

[Install]
WantedBy=default.target
EOF

  echo "Wrote ${USER_SYSTEMD_DIR}/${TAILSCALED_SERVICE}"
  echo "Wrote ${USER_SYSTEMD_DIR}/${TAILSCALE_SERVE_SERVICE}"
fi

systemctl --user daemon-reload

if [[ "${ENABLE_NOW}" == "true" ]]; then
  systemctl --user enable --now "${BACKEND_SERVICE}"
  if [[ "${INSTALL_USERSPACE_TAILSCALE}" == "true" ]]; then
    systemctl --user enable --now "${TAILSCALED_SERVICE}" "${TAILSCALE_SERVE_SERVICE}"
  fi
fi

echo
echo "User services installed."
echo "To survive reboot before login, enable lingering once:"
echo "  loginctl enable-linger ${USER}"
echo
echo "Useful commands:"
echo "  systemctl --user status ${BACKEND_SERVICE}"
echo "  ${ROOT_DIR}/scripts/safe_restart_backend.sh --systemd-user"

if [[ "${INSTALL_USERSPACE_TAILSCALE}" == "true" ]]; then
  echo "  systemctl --user status ${TAILSCALED_SERVICE}"
  echo "  systemctl --user status ${TAILSCALE_SERVE_SERVICE}"
else
  echo "TAILSCALE_SOCKET is empty in .env, so no userspace Tailscale services were installed."
  echo "If you use standard Tailscale instead, enable the system daemon separately:"
  echo "  sudo systemctl enable --now tailscaled"
fi
