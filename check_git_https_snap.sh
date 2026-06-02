#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage: ./check_git_https_snap.sh [--json] [--quiet]

Run the repo-level Git HTTPS snap validation wrapper.
This delegates to scripts/check_git_https_snap.sh without changing behavior.

Flags:
  --json      Emit the same machine-readable summary as scripts/check_git_https_snap.sh --json.
  --quiet     Keep only the final success line unless a stage fails.
  -h, --help  Show this help text.
EOF
  exit 0
fi

exec "${SCRIPT_DIR}/scripts/check_git_https_snap.sh" "$@"
