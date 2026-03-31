#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/check_git_https_snap_lib.sh"

JSON_OUTPUT=0
QUIET=0
SCHEMA_VERSION="1.0"

print_help() {
  cat <<'EOF'
Usage: check_git_https_snap.sh [--json] [--quiet]

Run the full Git HTTPS snap validation flow in order:
1. shell lint / syntax checks
2. non-destructive setup / rollback harness

Flags:
  --json      Emit a machine-readable summary for the consolidated check.
  --quiet     Keep only the final success line unless a stage fails.
  -h, --help  Show this help text.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      print_help
      exit 0
      ;;
    --json)
      JSON_OUTPUT=1
      ;;
    --quiet)
      QUIET=1
      ;;
    *)
      echo "usage: $0 [--json] [--quiet]" >&2
      exit 2
      ;;
  esac
  shift
done

if [[ "$JSON_OUTPUT" -eq 1 ]]; then
  JSON_STATUS="passed"
  JSON_STAGES=()

  run_stage_json lint bash "${SCRIPT_DIR}/lint_git_https_snap_shell.sh" || {
    emit_stage_summary_json "${SCHEMA_VERSION}"
    exit 1
  }
  run_stage_json harness bash "${SCRIPT_DIR}/test_git_https_snap_setup.sh" || {
    emit_stage_summary_json "${SCHEMA_VERSION}"
    exit 1
  }

  emit_stage_summary_json "${SCHEMA_VERSION}"
  exit 0
fi

run_stage_quiet() {
  local stage_name="$1"
  shift
  local tmp_output
  tmp_output="$(mktemp)"
  if "$@" >"${tmp_output}" 2>&1; then
    rm -f "${tmp_output}"
    return 0
  fi

  local output detail
  output="$(cat "${tmp_output}")"
  detail="$(last_non_empty_line "${output}")"
  rm -f "${tmp_output}"
  if [[ -n "${detail}" ]]; then
    echo "git HTTPS snap stage failed: ${stage_name}: ${detail}" >&2
  else
    echo "git HTTPS snap stage failed: ${stage_name}" >&2
  fi
  return 1
}

if [[ "${QUIET}" -eq 1 ]]; then
  run_stage_quiet lint bash "${SCRIPT_DIR}/lint_git_https_snap_shell.sh"
  run_stage_quiet harness bash "${SCRIPT_DIR}/test_git_https_snap_setup.sh"
else
  bash "${SCRIPT_DIR}/lint_git_https_snap_shell.sh"
  bash "${SCRIPT_DIR}/test_git_https_snap_setup.sh"
fi

echo "git HTTPS snap checks ok"
