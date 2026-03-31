#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
JSON_OUTPUT=0

print_help() {
  cat <<'EOF'
Usage: rollback_git_https_snap.sh [--dry-run] [--json]

Undo the Git HTTPS snap workaround for this environment.

Flags:
  --dry-run   Show planned rollback changes without writing them.
  --json      Emit machine-readable JSON for rollback mode.
  -h, --help  Show this help text.

Environment:
  SNAP_GIT_CORE     Override the git exec-path export line to remove.
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
    --json) JSON_OUTPUT=1 ;;
    *)
      echo "usage: $0 [--dry-run [--json]|--json]" >&2
      exit 2
      ;;
  esac
done

SNAP_GIT_CORE="${SNAP_GIT_CORE:-/snap/codex/current/usr/lib/git-core}"
GH_BIN="${GH_BIN:-/home/batata/snap/codex/current/.local/bin/gh}"
BASHRC="${BASHRC:-$HOME/.bashrc}"
GIT_EXEC_EXPORT="export GIT_EXEC_PATH=${SNAP_GIT_CORE}"

json_escape() {
  local text="$1"
  text="${text//\\/\\\\}"
  text="${text//\"/\\\"}"
  text="${text//$'\n'/\\n}"
  printf '%s' "$text"
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

if [[ -f "$BASHRC" ]]; then
  if grep -qxF "$GIT_EXEC_EXPORT" "$BASHRC" 2>/dev/null; then
    if [[ "$DRY_RUN" -eq 1 ]]; then
      BASHRC_ACTION="removed"
      BASHRC_APPLIED="false"
      BASHRC_MESSAGE="would remove ${GIT_EXEC_EXPORT} from ${BASHRC}"
      if [[ "$JSON_OUTPUT" -ne 1 ]]; then
        echo "dry-run: would remove from $BASHRC -> $GIT_EXEC_EXPORT"
      fi
    else
      BASHRC_ACTION="removed"
      BASHRC_APPLIED="true"
      BASHRC_MESSAGE="removed ${GIT_EXEC_EXPORT} from ${BASHRC}"
      TMP_FILE=$(mktemp)
      grep -vxF "$GIT_EXEC_EXPORT" "$BASHRC" > "$TMP_FILE" || true
      mv "$TMP_FILE" "$BASHRC"
    fi
  elif [[ "$DRY_RUN" -eq 1 ]]; then
    BASHRC_ACTION="not_present"
    BASHRC_APPLIED="false"
    BASHRC_MESSAGE="bashrc does not contain ${GIT_EXEC_EXPORT}"
    if [[ "$JSON_OUTPUT" -ne 1 ]]; then
      echo "dry-run: bashrc does not contain: $GIT_EXEC_EXPORT"
    fi
  else
    BASHRC_ACTION="not_present"
    BASHRC_APPLIED="false"
    BASHRC_MESSAGE="bashrc does not contain ${GIT_EXEC_EXPORT}"
  fi
elif [[ "$DRY_RUN" -eq 1 ]]; then
  BASHRC_ACTION="not_present"
  BASHRC_APPLIED="false"
  BASHRC_MESSAGE="bashrc does not exist: ${BASHRC}"
  if [[ "$JSON_OUTPUT" -ne 1 ]]; then
    echo "dry-run: bashrc does not exist: $BASHRC"
  fi
else
  BASHRC_ACTION="not_present"
  BASHRC_APPLIED="false"
  BASHRC_MESSAGE="bashrc does not exist: ${BASHRC}"
fi

if [[ -z "${BASHRC_ACTION:-}" ]]; then
  BASHRC_ACTION="not_present"
  BASHRC_APPLIED="false"
  BASHRC_MESSAGE="bashrc does not contain ${GIT_EXEC_EXPORT}"
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  HELPER_ACTION="removed"
  HELPER_APPLIED="false"
  HELPER_MESSAGE="would unset credential.https://github.com.helper"
  if [[ "$JSON_OUTPUT" -ne 1 ]]; then
    echo "dry-run: would unset credential.https://github.com.helper"
  fi
elif git config --global --get credential.https://github.com.helper >/dev/null 2>&1; then
  git config --global --unset-all credential.https://github.com.helper || true
  HELPER_ACTION="removed"
  HELPER_APPLIED="true"
  HELPER_MESSAGE="removed credential.https://github.com.helper"
else
  HELPER_ACTION="not_present"
  HELPER_APPLIED="false"
  HELPER_MESSAGE="credential.https://github.com.helper was not set"
fi

if [[ "$JSON_OUTPUT" -eq 1 ]]; then
  emit_operation_json "rollback" "passed" "$([[ "$DRY_RUN" -eq 1 ]] && echo true || echo false)" \
    "{\"target\":\"bashrc_export\",\"action\":\"$(json_escape "$BASHRC_ACTION")\",\"applied\":${BASHRC_APPLIED},\"message\":\"$(json_escape "$BASHRC_MESSAGE")\"}" \
    "{\"target\":\"credential_helper\",\"action\":\"$(json_escape "$HELPER_ACTION")\",\"applied\":${HELPER_APPLIED},\"message\":\"$(json_escape "$HELPER_MESSAGE")\"}"
else
  echo "rollback complete"
fi
