#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TMP_DIR="$(mktemp -d)"
TMP_STDOUT="$(mktemp)"
TMP_STDERR="$(mktemp)"
trap 'rm -rf "${TMP_DIR}"; rm -f "${TMP_STDOUT}" "${TMP_STDERR}"' EXIT

print_help() {
  cat <<'EOF'
Usage: validate_check_git_https_snap_quiet.sh

Run a non-destructive controlled failure check for ./check_git_https_snap.sh --quiet.
It verifies that quiet mode:
1. exits non-zero on failure
2. suppresses noisy stage output
3. keeps a short stage-specific error message

Flags:
  -h, --help  Show this help text.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  print_help
  exit 0
elif [[ $# -gt 0 ]]; then
  echo "usage: $0" >&2
  exit 2
fi

mkdir -p "${TMP_DIR}/scripts"
cp "${REPO_ROOT}/check_git_https_snap.sh" "${TMP_DIR}/check_git_https_snap.sh"
cp "${SCRIPT_DIR}/check_git_https_snap.sh" "${TMP_DIR}/scripts/check_git_https_snap.sh"
cp "${SCRIPT_DIR}/check_git_https_snap_lib.sh" "${TMP_DIR}/scripts/check_git_https_snap_lib.sh"
chmod +x "${TMP_DIR}/check_git_https_snap.sh" "${TMP_DIR}/scripts/check_git_https_snap.sh"

cat > "${TMP_DIR}/scripts/lint_git_https_snap_shell.sh" <<'EOF'
#!/usr/bin/env bash
echo "bash -n ok"
exit 0
EOF
chmod +x "${TMP_DIR}/scripts/lint_git_https_snap_shell.sh"

cat > "${TMP_DIR}/scripts/test_git_https_snap_setup.sh" <<'EOF'
#!/usr/bin/env bash
echo "noisy harness line 1"
echo "noisy harness line 2"
echo "simulated harness failure"
exit 1
EOF
chmod +x "${TMP_DIR}/scripts/test_git_https_snap_setup.sh"

set +e
(cd "${TMP_DIR}" && ./check_git_https_snap.sh --quiet >"${TMP_STDOUT}" 2>"${TMP_STDERR}")
STATUS=$?
set -e

if [[ "${STATUS}" -eq 0 ]]; then
  echo "expected ./check_git_https_snap.sh --quiet to fail" >&2
  exit 1
fi

python3 -c '
import sys
from pathlib import Path

stdout = Path(sys.argv[1]).read_text()
stderr = Path(sys.argv[2]).read_text()

if stdout.strip():
    raise SystemExit("quiet failure should not write success output to stdout")

if "git HTTPS snap stage failed: harness: simulated harness failure" not in stderr:
    raise SystemExit("missing short stage failure message")

if "noisy harness line 1" in stderr or "noisy harness line 2" in stderr:
    raise SystemExit("quiet failure leaked noisy harness output")
' "${TMP_STDOUT}" "${TMP_STDERR}"

echo "check_git_https_snap quiet ok"
