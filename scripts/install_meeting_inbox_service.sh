#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd "${script_dir}/.." && pwd)"
unit_dir="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
unit="codex-meeting-inbox.service"
cd "${project_dir}"

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--enable-now" ) ]]; then
  echo "Usage: $0 [--enable-now]" >&2
  exit 1
fi

# doctor only prints presence/missing names, never credential values.
"${project_dir}/.venv/bin/python" - <<'PY'
import os
from pathlib import Path
from dotenv import load_dotenv, set_key
load_dotenv('.env', override=False)
target = Path('.data/relevamientos-inbox/service.env')
for name in ('GOOGLE_DRIVE_TOKEN_FILE', 'GOOGLE_DRIVE_OAUTH_CLIENT_FILE', 'RELEVAMIENTOS_GOOGLE_TOKEN_FILE'):
    if os.environ.get(name):
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.touch(mode=0o600, exist_ok=True)
        os.chmod(target, 0o600)
        set_key(str(target), name, os.environ[name])
PY
"${project_dir}/.venv/bin/python" -m services.relevamientos.inbox doctor
if [[ "${1:-}" == "--enable-now" ]]; then
  "${project_dir}/.venv/bin/python" -m services.relevamientos.inbox doctor --check-drive
  "${project_dir}/.venv/bin/python" - <<'PY'
import os
import httpx
from dotenv import load_dotenv
load_dotenv('.env', override=False)
load_dotenv('.data/relevamientos-inbox/service.env', override=False)
response = httpx.get(os.environ.get('RELEVAMIENTOS_BRIDGE_URL', 'http://127.0.0.1:8000').rstrip('/') + '/openapi.json', timeout=15)
response.raise_for_status()
if '/meeting-intakes' not in response.json().get('paths', {}):
    raise SystemExit('Backend pendiente de cargar la ruta /meeting-intakes. No se activó el monitor.')
PY
fi

mkdir -p "${unit_dir}"
cat > "${unit_dir}/${unit}" <<EOF
[Unit]
Description=Codex Bridge verified meeting intake from Google Drive
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${project_dir}
ExecStart=${project_dir}/.venv/bin/python -m services.relevamientos.inbox watch
Restart=on-failure
RestartPreventExitStatus=2
RestartSec=30
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
if [[ "${1:-}" == "--enable-now" ]]; then
  systemctl --user enable --now "${unit}"
fi
echo "Installed ${unit}"
