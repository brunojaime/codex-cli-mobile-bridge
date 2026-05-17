#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/install_boot_services.sh [--enable-now]

What it does:
  - Disables the existing user services to avoid conflicts at login
  - Creates system services that run as the current user at boot
  - Enables those services immediately when requested
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
SYSTEMD_DIR="/etc/systemd/system"
CURRENT_USER="${SUDO_USER:-${USER}}"
CURRENT_GROUP="$(id -gn "${CURRENT_USER}")"
CURRENT_HOME="$(getent passwd "${CURRENT_USER}" | cut -d: -f6)"
CURRENT_UID="$(id -u "${CURRENT_USER}")"

BACKEND_SERVICE="codex-mobile-bridge-backend.service"
TAILSCALED_SERVICE="codex-mobile-bridge-tailscaled.service"
TAILSCALE_SERVE_SERVICE="codex-mobile-bridge-tailscale-serve.service"
PATH_VALUE="${CURRENT_HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin"

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

USER_BUS_PATH="/run/user/${CURRENT_UID}/bus"
USER_RUNTIME_DIR="/run/user/${CURRENT_UID}"
if [[ -S "${USER_BUS_PATH}" ]]; then
  runuser -u "${CURRENT_USER}" -- env \
    XDG_RUNTIME_DIR="${USER_RUNTIME_DIR}" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=${USER_BUS_PATH}" \
    systemctl --user disable --now \
    "${BACKEND_SERVICE}" \
    "${TAILSCALED_SERVICE}" \
    "${TAILSCALE_SERVE_SERVICE}" || true
fi

cat > "${SYSTEMD_DIR}/${BACKEND_SERVICE}" <<EOF
[Unit]
Description=Codex CLI Mobile Bridge backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${CURRENT_USER}
Group=${CURRENT_GROUP}
WorkingDirectory=${ROOT_DIR}
Environment=HOME=${CURRENT_HOME}
Environment=PATH=${PATH_VALUE}
ExecStart=${ROOT_DIR}/.venv/bin/python ${ROOT_DIR}/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "Wrote ${SYSTEMD_DIR}/${BACKEND_SERVICE}"

INSTALL_USERSPACE_TAILSCALE=false
if [[ -n "${TAILSCALE_SOCKET}" ]]; then
  INSTALL_USERSPACE_TAILSCALE=true
  cat > "${SYSTEMD_DIR}/${TAILSCALED_SERVICE}" <<EOF
[Unit]
Description=Userspace tailscaled for Codex CLI Mobile Bridge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${CURRENT_USER}
Group=${CURRENT_GROUP}
WorkingDirectory=${ROOT_DIR}
Environment=HOME=${CURRENT_HOME}
Environment=PATH=${PATH_VALUE}
ExecStart=${ROOT_DIR}/scripts/run_tailscaled_userspace.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

  cat > "${SYSTEMD_DIR}/${TAILSCALE_SERVE_SERVICE}" <<EOF
[Unit]
Description=Expose Codex CLI Mobile Bridge through Tailscale Serve
After=${BACKEND_SERVICE} ${TAILSCALED_SERVICE}
Wants=${BACKEND_SERVICE} ${TAILSCALED_SERVICE}

[Service]
Type=oneshot
User=${CURRENT_USER}
Group=${CURRENT_GROUP}
WorkingDirectory=${ROOT_DIR}
Environment=HOME=${CURRENT_HOME}
Environment=PATH=${PATH_VALUE}
ExecStart=${ROOT_DIR}/scripts/configure_tailscale_serve.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

  echo "Wrote ${SYSTEMD_DIR}/${TAILSCALED_SERVICE}"
  echo "Wrote ${SYSTEMD_DIR}/${TAILSCALE_SERVE_SERVICE}"
fi

systemctl daemon-reload

if [[ "${ENABLE_NOW}" == "true" ]]; then
  systemctl enable --now "${BACKEND_SERVICE}"
  if [[ "${INSTALL_USERSPACE_TAILSCALE}" == "true" ]]; then
    systemctl enable --now "${TAILSCALED_SERVICE}" "${TAILSCALE_SERVE_SERVICE}"
  fi
fi

echo
echo "Boot services installed."
echo "Useful commands:"
echo "  systemctl status ${BACKEND_SERVICE}"
echo "  systemctl restart ${BACKEND_SERVICE}"

if [[ "${INSTALL_USERSPACE_TAILSCALE}" == "true" ]]; then
  echo "  systemctl status ${TAILSCALED_SERVICE}"
  echo "  systemctl status ${TAILSCALE_SERVE_SERVICE}"
else
  echo "TAILSCALE_SOCKET is empty in .env, so no userspace Tailscale system services were installed."
  echo "If you use standard Tailscale instead, enable the system daemon separately:"
  echo "  sudo systemctl enable --now tailscaled"
fi
