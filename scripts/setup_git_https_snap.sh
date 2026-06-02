#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
CHECK_ONLY=0
JSON_OUTPUT=0

print_help() {
  cat <<'EOF'
Usage: setup_git_https_snap.sh [--dry-run] [--json]
       setup_git_https_snap.sh --check [--json]

Configure the Git HTTPS snap workaround for this environment.

Flags:
  --dry-run   Show planned setup changes without writing them.
  --check     Audit the current environment without changing it.
  --json      Emit machine-readable JSON for setup or check mode.
  -h, --help  Show this help text.

Environment:
  SNAP_GIT_CORE     Override the git exec-path target.
  GH_BIN            Override the gh binary used for credential helper and auth check.
  BASHRC            Override the bashrc file to update or inspect.
  GIT_CONFIG_GLOBAL Override the global git config file used by git config --global.
EOF
}

for arg in "$@"; do
  case "$arg" in
    -h|--help)
      print_help
      exit 0
      ;;
    --dry-run) DRY_RUN=1 ;;
    --check) CHECK_ONLY=1 ;;
    --json) JSON_OUTPUT=1 ;;
    *)
      echo "usage: $0 [--dry-run [--json]|--check [--json]|--json]" >&2
      exit 2
      ;;
  esac
done

if [[ "$DRY_RUN" -eq 1 && "$CHECK_ONLY" -eq 1 ]]; then
  echo "usage: $0 [--dry-run [--json]|--check [--json]|--json]" >&2
  exit 2
fi

SNAP_GIT_CORE="${SNAP_GIT_CORE:-/snap/codex/current/usr/lib/git-core}"
GH_BIN="${GH_BIN:-/home/batata/snap/codex/current/.local/bin/gh}"
BASHRC="${BASHRC:-$HOME/.bashrc}"
GIT_EXEC_EXPORT="export GIT_EXEC_PATH=${SNAP_GIT_CORE}"
GH_HELPER="!${GH_BIN} auth git-credential"

fail() {
  echo "setup failed: $1" >&2
  exit 1
}

check_fail() {
  echo "check failed: $1" >&2
  exit 1
}

json_escape() {
  local text="$1"
  text="${text//\\/\\\\}"
  text="${text//\"/\\\"}"
  text="${text//$'\n'/\\n}"
  printf '%s' "$text"
}

JSON_CHECKS=()
JSON_STATUS="passed"

record_json_check() {
  local name="$1"
  local result="$2"
  local message="$3"
  [[ "$result" == "passed" ]] || JSON_STATUS="failed"
  JSON_CHECKS+=("{\"name\":\"$(json_escape "$name")\",\"result\":\"$(json_escape "$result")\",\"message\":\"$(json_escape "$message")\"}")
}

record_json_skipped() {
  local name="$1"
  local message="$2"
  JSON_CHECKS+=("{\"name\":\"$(json_escape "$name")\",\"result\":\"skipped\",\"message\":\"$(json_escape "$message")\"}")
}

emit_json_report() {
  local joined=""
  local item
  for item in "${JSON_CHECKS[@]}"; do
    if [[ -n "$joined" ]]; then
      joined+=","
    fi
    joined+="$item"
  done
  printf '{"status":"%s","checks":[%s]}\n' "$(json_escape "$JSON_STATUS")" "$joined"
}

emit_operation_json() {
  local operation="$1"
  local status="$2"
  local dry_run="$3"
  shift 3

  local joined=""
  local item
  for item in "$@"; do
    if [[ -n "$joined" ]]; then
      joined+=","
    fi
    joined+="$item"
  done

  local git_config_target="${GIT_CONFIG_GLOBAL:-${HOME}/.gitconfig}"
  printf '{"status":"%s","operation":"%s","dry_run":%s,"targets":{"bashrc":"%s","git_config_global":"%s"},"changes":[%s]}\n' \
    "$(json_escape "$status")" \
    "$(json_escape "$operation")" \
    "$dry_run" \
    "$(json_escape "$BASHRC")" \
    "$(json_escape "$git_config_target")" \
    "$joined"
}

run_or_print() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    if [[ "$JSON_OUTPUT" -ne 1 ]]; then
      echo "dry-run: $*"
    fi
  else
    eval "$@"
  fi
}

[[ -d "$SNAP_GIT_CORE" ]] || fail "missing git exec path: $SNAP_GIT_CORE"
[[ -x "$GH_BIN" ]] || fail "missing gh binary: $GH_BIN"
if ! "$GH_BIN" auth status >/dev/null 2>&1; then
  fail "gh auth status failed for current environment"
fi

if [[ "$DRY_RUN" -eq 1 && "$JSON_OUTPUT" -ne 1 ]]; then
  echo "dry-run: preflight ok"
fi

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  if [[ "$JSON_OUTPUT" -eq 1 ]]; then
    if [[ -d "$SNAP_GIT_CORE" ]]; then
      record_json_check "git_exec_path" "passed" "found ${SNAP_GIT_CORE}"
    else
      record_json_check "git_exec_path" "failed" "missing git exec path: ${SNAP_GIT_CORE}"
      record_json_skipped "gh_bin" "skipped because preflight failed"
      record_json_skipped "gh_auth" "skipped because preflight failed"
      record_json_skipped "bashrc_export" "skipped because preflight failed"
      record_json_skipped "credential_helper" "skipped because preflight failed"
      record_json_skipped "git_ls_remote" "skipped because preflight failed"
      record_json_skipped "git_push_dry_run" "skipped because preflight failed"
      emit_json_report
      exit 1
    fi

    if [[ -x "$GH_BIN" ]]; then
      record_json_check "gh_bin" "passed" "found ${GH_BIN}"
    else
      record_json_check "gh_bin" "failed" "missing gh binary: ${GH_BIN}"
      record_json_skipped "gh_auth" "skipped because preflight failed"
      record_json_skipped "bashrc_export" "skipped because preflight failed"
      record_json_skipped "credential_helper" "skipped because preflight failed"
      record_json_skipped "git_ls_remote" "skipped because preflight failed"
      record_json_skipped "git_push_dry_run" "skipped because preflight failed"
      emit_json_report
      exit 1
    fi

    if "$GH_BIN" auth status >/dev/null 2>&1; then
      record_json_check "gh_auth" "passed" "gh auth status ok"
    else
      record_json_check "gh_auth" "failed" "gh auth status failed for current environment"
      record_json_skipped "bashrc_export" "skipped because preflight failed"
      record_json_skipped "credential_helper" "skipped because preflight failed"
      record_json_skipped "git_ls_remote" "skipped because preflight failed"
      record_json_skipped "git_push_dry_run" "skipped because preflight failed"
      emit_json_report
      exit 1
    fi

    CONFIG_READY=1
    if grep -qxF "$GIT_EXEC_EXPORT" "$BASHRC" 2>/dev/null; then
      record_json_check "bashrc_export" "passed" "found export in ${BASHRC}"
    else
      record_json_check "bashrc_export" "failed" "missing export in ${BASHRC}: ${GIT_EXEC_EXPORT}"
      CONFIG_READY=0
    fi

    CURRENT_HELPER="$(git config --global --get credential.https://github.com.helper || true)"
    if [[ "${CURRENT_HELPER}" == "${GH_HELPER}" ]]; then
      record_json_check "credential_helper" "passed" "credential.https://github.com.helper is configured correctly"
    else
      record_json_check "credential_helper" "failed" "credential.https://github.com.helper is not set to ${GH_HELPER}"
      CONFIG_READY=0
    fi

    if [[ "${CONFIG_READY}" -eq 1 ]]; then
      if GIT_EXEC_PATH="${SNAP_GIT_CORE}" git ls-remote --heads origin >/dev/null; then
        record_json_check "git_ls_remote" "passed" "git ls-remote succeeded"
      else
        record_json_check "git_ls_remote" "failed" "git ls-remote failed with the configured environment"
      fi
      if GIT_EXEC_PATH="${SNAP_GIT_CORE}" git push --dry-run origin HEAD >/dev/null; then
        record_json_check "git_push_dry_run" "passed" "git push --dry-run succeeded"
      else
        record_json_check "git_push_dry_run" "failed" "git push --dry-run failed with the configured environment"
      fi
    else
      record_json_skipped "git_ls_remote" "skipped because setup is incomplete"
      record_json_skipped "git_push_dry_run" "skipped because setup is incomplete"
    fi

    emit_json_report
    [[ "$JSON_STATUS" == "passed" ]] || exit 1
    exit 0
  fi

  grep -qxF "$GIT_EXEC_EXPORT" "$BASHRC" 2>/dev/null \
    || check_fail "missing export in ${BASHRC}: ${GIT_EXEC_EXPORT}"

  CURRENT_HELPER="$(git config --global --get credential.https://github.com.helper || true)"
  [[ "${CURRENT_HELPER}" == "${GH_HELPER}" ]] \
    || check_fail "credential.https://github.com.helper is not set to ${GH_HELPER}"

  GIT_EXEC_PATH="${SNAP_GIT_CORE}" git ls-remote --heads origin >/dev/null \
    || check_fail "git ls-remote failed with the configured environment"
  GIT_EXEC_PATH="${SNAP_GIT_CORE}" git push --dry-run origin HEAD >/dev/null \
    || check_fail "git push --dry-run failed with the configured environment"

  echo "check ok"
  exit 0
fi

run_or_print "touch \"$BASHRC\""

OPERATION_CHANGES=()
if grep -qxF "$GIT_EXEC_EXPORT" "$BASHRC" 2>/dev/null; then
  OPERATION_CHANGES+=("{\"target\":\"bashrc_export\",\"action\":\"unchanged\",\"applied\":false,\"message\":\"$(json_escape "bashrc already contains ${GIT_EXEC_EXPORT}")\"}")
  if [[ "$DRY_RUN" -eq 1 && "$JSON_OUTPUT" -ne 1 ]]; then
    echo "dry-run: bashrc already contains: $GIT_EXEC_EXPORT"
  fi
else
  if [[ "$DRY_RUN" -eq 1 ]]; then
    OPERATION_CHANGES+=("{\"target\":\"bashrc_export\",\"action\":\"appended\",\"applied\":false,\"message\":\"$(json_escape "would append ${GIT_EXEC_EXPORT} to ${BASHRC}")\"}")
  else
    OPERATION_CHANGES+=("{\"target\":\"bashrc_export\",\"action\":\"appended\",\"applied\":true,\"message\":\"$(json_escape "appended ${GIT_EXEC_EXPORT} to ${BASHRC}")\"}")
  fi
  run_or_print "printf '%s\n' \"$GIT_EXEC_EXPORT\" >> \"$BASHRC\""
fi

run_or_print "git config --global --replace-all credential.https://github.com.helper \"$GH_HELPER\""
if [[ "$DRY_RUN" -eq 1 ]]; then
  OPERATION_CHANGES+=("{\"target\":\"credential_helper\",\"action\":\"configured\",\"applied\":false,\"message\":\"$(json_escape "would configure credential.https://github.com.helper to ${GH_HELPER}")\"}")
else
  OPERATION_CHANGES+=("{\"target\":\"credential_helper\",\"action\":\"configured\",\"applied\":true,\"message\":\"$(json_escape "configured credential.https://github.com.helper to ${GH_HELPER}")\"}")
fi

if [[ "$JSON_OUTPUT" -eq 1 ]]; then
  emit_operation_json "setup" "passed" "$([[ "$DRY_RUN" -eq 1 ]] && echo true || echo false)" "${OPERATION_CHANGES[@]}"
elif [[ "$DRY_RUN" -eq 1 ]]; then
  echo "dry-run: would configure credential.https://github.com.helper=$GH_HELPER"
else
  echo "setup complete"
  echo "configured bashrc: $BASHRC"
  if [[ -n "${GIT_CONFIG_GLOBAL:-}" ]]; then
    echo "configured git global: ${GIT_CONFIG_GLOBAL}"
  else
    echo "configured git global: ${HOME}/.gitconfig"
  fi
fi
