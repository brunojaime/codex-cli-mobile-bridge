#!/usr/bin/env bash
set -euo pipefail
systemctl --user start codex-bridge-activity-backend.service codex-bridge-activity-web.service
exec /usr/bin/google-chrome --app=http://127.0.0.1:5180/ --class=CodexBridgeActivity
