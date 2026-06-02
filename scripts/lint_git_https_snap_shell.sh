#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TARGETS=(
  "${REPO_ROOT}/check_git_https_snap.sh"
  "${SCRIPT_DIR}/check_git_https_snap_lib.sh"
  "${SCRIPT_DIR}/check_git_https_snap.sh"
  "${SCRIPT_DIR}/setup_git_https_snap.sh"
  "${SCRIPT_DIR}/rollback_git_https_snap.sh"
  "${SCRIPT_DIR}/test_git_https_snap_setup.sh"
  "${SCRIPT_DIR}/validate_check_git_https_snap_json.sh"
  "${SCRIPT_DIR}/validate_check_git_https_snap_quiet.sh"
)
EXECUTABLE_TARGETS=(
  "${REPO_ROOT}/check_git_https_snap.sh"
  "${SCRIPT_DIR}/check_git_https_snap.sh"
  "${SCRIPT_DIR}/setup_git_https_snap.sh"
  "${SCRIPT_DIR}/rollback_git_https_snap.sh"
  "${SCRIPT_DIR}/validate_check_git_https_snap_json.sh"
)

for target in "${EXECUTABLE_TARGETS[@]}"; do
  if [[ ! -x "${target}" ]]; then
    echo "executable bit missing: ${target}" >&2
    exit 1
  fi
done
echo "executable bits ok"

for target in "${TARGETS[@]}"; do
  bash -n "${target}"
done
echo "bash -n ok"

if command -v shellcheck >/dev/null 2>&1; then
  shellcheck "${TARGETS[@]}"
  echo "shellcheck ok"
else
  echo "shellcheck skipped: shellcheck is not installed"
fi
