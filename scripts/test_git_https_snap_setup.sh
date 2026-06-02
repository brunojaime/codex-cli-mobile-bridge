#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP_SCRIPT="${SCRIPT_DIR}/setup_git_https_snap.sh"
ROLLBACK_SCRIPT="${SCRIPT_DIR}/rollback_git_https_snap.sh"
SCHEMA_PATH="${SCRIPT_DIR}/../docs/setup_git_https_snap_check.schema.json"
OPERATION_SCHEMA_PATH="${SCRIPT_DIR}/../docs/git_https_snap_operation.schema.json"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

BASHRC_PATH="${TMP_DIR}/bashrc"
GITCONFIG_PATH="${TMP_DIR}/gitconfig"
NOAUTH_HOME="${TMP_DIR}/noauth-home"
NOAUTH_XDG="${TMP_DIR}/noauth-xdg"

assert_json_payload() {
  local json_file="$1"
  local phase="$2"

  python3 -c '
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
schema = json.loads(Path(sys.argv[2]).read_text())

try:
    import jsonschema  # type: ignore
except ImportError:
    jsonschema = None

if jsonschema is not None:
    jsonschema.validate(instance=payload, schema=schema)
else:
    if not isinstance(payload, dict):
        raise SystemExit(1)
    if set(payload.keys()) != set(schema["required"]):
        raise SystemExit(1)
    if payload.get("status") not in schema["properties"]["status"]["enum"]:
        raise SystemExit(1)
    checks = payload.get("checks")
    if not isinstance(checks, list) or not checks:
        raise SystemExit(1)
    item_schema = schema["properties"]["checks"]["items"]
    required_fields = set(item_schema["required"])
    valid_names = set(item_schema["properties"]["name"]["enum"])
    valid_results = set(item_schema["properties"]["result"]["enum"])
    for item in checks:
        if not isinstance(item, dict):
            raise SystemExit(1)
        if set(item.keys()) != required_fields:
            raise SystemExit(1)
        if item.get("name") not in valid_names:
            raise SystemExit(1)
        if item.get("result") not in valid_results:
            raise SystemExit(1)
        if not isinstance(item.get("message"), str) or not item["message"]:
            raise SystemExit(1)

checks = payload.get("checks")
if not isinstance(checks, list) or not checks:
    raise SystemExit(1)
expected_order = [
    "git_exec_path",
    "gh_bin",
    "gh_auth",
    "bashrc_export",
    "credential_helper",
    "git_ls_remote",
    "git_push_dry_run",
]
phase = sys.argv[3]
expected = {
    "before": {
        "status": "failed",
        "results": {
            "git_exec_path": "passed",
            "gh_bin": "passed",
            "gh_auth": "passed",
            "bashrc_export": "failed",
            "credential_helper": "failed",
            "git_ls_remote": "skipped",
            "git_push_dry_run": "skipped",
        },
    },
    "after_setup": {
        "status": "passed",
        "results": {name: "passed" for name in expected_order},
    },
    "after_rollback": {
        "status": "failed",
        "results": {
            "git_exec_path": "passed",
            "gh_bin": "passed",
            "gh_auth": "passed",
            "bashrc_export": "failed",
            "credential_helper": "failed",
            "git_ls_remote": "skipped",
            "git_push_dry_run": "skipped",
        },
    },
}[phase]

if payload.get("status") != expected["status"]:
    raise SystemExit(1)

names = [item.get("name") for item in checks]
if names != expected_order:
    raise SystemExit(1)

for item in checks:
    if "result" not in item:
        raise SystemExit(1)
    if item["result"] != expected["results"][item["name"]]:
        raise SystemExit(1)
' "${json_file}" "${SCHEMA_PATH}" "${phase}"
}

assert_operation_json() {
  local json_file="$1"
  local expected_operation="$2"
  local expected_dry_run="$3"
  local expected_bashrc_action="$4"
  local expected_bashrc_applied="$5"
  local expected_helper_action="$6"
  local expected_helper_applied="$7"

  python3 -c '
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
schema = json.loads(Path(sys.argv[2]).read_text())

try:
    import jsonschema  # type: ignore
except ImportError:
    jsonschema = None

if jsonschema is not None:
    jsonschema.validate(instance=payload, schema=schema)
else:
    if not isinstance(payload, dict):
        raise SystemExit(1)
    if set(payload.keys()) != set(schema["required"]):
        raise SystemExit(1)
    if payload.get("status") not in schema["properties"]["status"]["enum"]:
        raise SystemExit(1)
    if payload.get("operation") not in schema["properties"]["operation"]["enum"]:
        raise SystemExit(1)
    if not isinstance(payload.get("dry_run"), bool):
        raise SystemExit(1)
    targets = payload.get("targets")
    if not isinstance(targets, dict) or set(targets.keys()) != set(schema["properties"]["targets"]["required"]):
        raise SystemExit(1)
    for key in ("bashrc", "git_config_global"):
        if not isinstance(targets.get(key), str) or not targets[key]:
            raise SystemExit(1)
    changes = payload.get("changes")
    if not isinstance(changes, list) or not changes:
        raise SystemExit(1)
    item_schema = schema["properties"]["changes"]["items"]
    required_fields = set(item_schema["required"])
    valid_targets = set(item_schema["properties"]["target"]["enum"])
    valid_actions = set(item_schema["properties"]["action"]["enum"])
    for item in changes:
        if not isinstance(item, dict):
            raise SystemExit(1)
        if set(item.keys()) != required_fields:
            raise SystemExit(1)
        if item.get("target") not in valid_targets:
            raise SystemExit(1)
        if item.get("action") not in valid_actions:
            raise SystemExit(1)
        if not isinstance(item.get("applied"), bool):
            raise SystemExit(1)
        if not isinstance(item.get("message"), str) or not item["message"]:
            raise SystemExit(1)

if payload.get("status") != "passed":
    raise SystemExit(1)
if payload.get("operation") != sys.argv[3]:
    raise SystemExit(1)
if payload.get("dry_run") != (sys.argv[4].lower() == "true"):
    raise SystemExit(1)

targets = payload["targets"]
if targets["bashrc"] != sys.argv[5]:
    raise SystemExit(1)
if targets["git_config_global"] != sys.argv[6]:
    raise SystemExit(1)

changes = {item["target"]: item for item in payload["changes"]}
if changes.get("bashrc_export", {}).get("action") != sys.argv[7]:
    raise SystemExit(1)
if changes.get("bashrc_export", {}).get("applied") != (sys.argv[8].lower() == "true"):
    raise SystemExit(1)
if changes.get("credential_helper", {}).get("action") != sys.argv[9]:
    raise SystemExit(1)
if changes.get("credential_helper", {}).get("applied") != (sys.argv[10].lower() == "true"):
    raise SystemExit(1)
' "${json_file}" "${OPERATION_SCHEMA_PATH}" "${expected_operation}" "${expected_dry_run}" "${BASHRC_PATH}" "${GITCONFIG_PATH}" "${expected_bashrc_action}" "${expected_bashrc_applied}" "${expected_helper_action}" "${expected_helper_applied}"
}

touch "${BASHRC_PATH}" "${GITCONFIG_PATH}"

set +e
BASHRC="${BASHRC_PATH}" GIT_CONFIG_GLOBAL="${GITCONFIG_PATH}" "${SETUP_SCRIPT}" --check >/dev/null 2>"${TMP_DIR}/check-before.stderr"
STATUS=$?
set -e
[[ "${STATUS}" -ne 0 ]]
grep -q 'check failed: missing export in' "${TMP_DIR}/check-before.stderr"

set +e
BASHRC="${BASHRC_PATH}" GIT_CONFIG_GLOBAL="${GITCONFIG_PATH}" "${SETUP_SCRIPT}" --check --json >"${TMP_DIR}/check-before.json"
STATUS=$?
set -e
[[ "${STATUS}" -ne 0 ]]
assert_json_payload "${TMP_DIR}/check-before.json" "before"

BASHRC="${BASHRC_PATH}" GIT_CONFIG_GLOBAL="${GITCONFIG_PATH}" "${SETUP_SCRIPT}" --dry-run
BASHRC="${BASHRC_PATH}" GIT_CONFIG_GLOBAL="${GITCONFIG_PATH}" "${SETUP_SCRIPT}" --dry-run --json >"${TMP_DIR}/setup-dry-run.json"
assert_operation_json "${TMP_DIR}/setup-dry-run.json" "setup" "true" "appended" "false" "configured" "false"
[[ ! -s "${BASHRC_PATH}" ]]
[[ -z "$(GIT_CONFIG_GLOBAL="${GITCONFIG_PATH}" git config --global --list --show-origin || true)" ]]
BASHRC="${BASHRC_PATH}" GIT_CONFIG_GLOBAL="${GITCONFIG_PATH}" "${SETUP_SCRIPT}" --json >"${TMP_DIR}/setup.json"
assert_operation_json "${TMP_DIR}/setup.json" "setup" "false" "appended" "true" "configured" "true"

set +e
BASHRC="${BASHRC_PATH}" GIT_CONFIG_GLOBAL="${GITCONFIG_PATH}" "${SETUP_SCRIPT}" --check >/dev/null
STATUS=$?
set -e
[[ "${STATUS}" -eq 0 ]]

set +e
BASHRC="${BASHRC_PATH}" GIT_CONFIG_GLOBAL="${GITCONFIG_PATH}" "${SETUP_SCRIPT}" --check --json >"${TMP_DIR}/check-after-setup.json"
STATUS=$?
set -e
[[ "${STATUS}" -eq 0 ]]
assert_json_payload "${TMP_DIR}/check-after-setup.json" "after_setup"

grep -qxF 'export GIT_EXEC_PATH=/snap/codex/current/usr/lib/git-core' "${BASHRC_PATH}"
[[ "$(grep -c '^export GIT_EXEC_PATH=' "${BASHRC_PATH}")" -eq 1 ]]
GIT_CONFIG_GLOBAL="${GITCONFIG_PATH}" git config --global --get credential.https://github.com.helper \
  | grep -qxF '!/home/batata/snap/codex/current/.local/bin/gh auth git-credential'

GIT_CONFIG_GLOBAL="${GITCONFIG_PATH}" GIT_EXEC_PATH=/snap/codex/current/usr/lib/git-core git ls-remote --heads origin >/dev/null
GIT_CONFIG_GLOBAL="${GITCONFIG_PATH}" GIT_EXEC_PATH=/snap/codex/current/usr/lib/git-core git push --dry-run origin HEAD >/dev/null

BASHRC_BEFORE_ROLLBACK="$(cat "${BASHRC_PATH}")"
GITCONFIG_BEFORE_ROLLBACK="$(cat "${GITCONFIG_PATH}")"
BASHRC="${BASHRC_PATH}" GIT_CONFIG_GLOBAL="${GITCONFIG_PATH}" "${ROLLBACK_SCRIPT}" --dry-run --json >"${TMP_DIR}/rollback-dry-run.json"
assert_operation_json "${TMP_DIR}/rollback-dry-run.json" "rollback" "true" "removed" "false" "removed" "false"
[[ "$(cat "${BASHRC_PATH}")" == "${BASHRC_BEFORE_ROLLBACK}" ]]
[[ "$(cat "${GITCONFIG_PATH}")" == "${GITCONFIG_BEFORE_ROLLBACK}" ]]
BASHRC="${BASHRC_PATH}" GIT_CONFIG_GLOBAL="${GITCONFIG_PATH}" "${ROLLBACK_SCRIPT}" --json >"${TMP_DIR}/rollback.json"
assert_operation_json "${TMP_DIR}/rollback.json" "rollback" "false" "removed" "true" "removed" "true"
[[ ! -s "${BASHRC_PATH}" ]]
if [[ -n "$(GIT_CONFIG_GLOBAL="${GITCONFIG_PATH}" git config --global --list --show-origin || true)" ]]; then
  echo "test failed: git config should be empty after rollback" >&2
  exit 1
fi

set +e
BASHRC="${BASHRC_PATH}" GIT_CONFIG_GLOBAL="${GITCONFIG_PATH}" "${SETUP_SCRIPT}" --check >/dev/null 2>"${TMP_DIR}/check-after-rollback.stderr"
STATUS=$?
set -e
[[ "${STATUS}" -ne 0 ]]
grep -q 'check failed: missing export in' "${TMP_DIR}/check-after-rollback.stderr"

set +e
BASHRC="${BASHRC_PATH}" GIT_CONFIG_GLOBAL="${GITCONFIG_PATH}" "${SETUP_SCRIPT}" --check --json >"${TMP_DIR}/check-after-rollback.json"
STATUS=$?
set -e
[[ "${STATUS}" -ne 0 ]]
assert_json_payload "${TMP_DIR}/check-after-rollback.json" "after_rollback"

mkdir -p "${NOAUTH_HOME}" "${NOAUTH_XDG}"
set +e
HOME="${NOAUTH_HOME}" XDG_CONFIG_HOME="${NOAUTH_XDG}" \
  BASHRC="${TMP_DIR}/fail-bashrc" GIT_CONFIG_GLOBAL="${TMP_DIR}/fail-gitconfig" \
  "${SETUP_SCRIPT}" >/dev/null 2>"${TMP_DIR}/noauth.stderr"
STATUS=$?
set -e
[[ "${STATUS}" -ne 0 ]]
grep -q 'setup failed: gh auth status failed for current environment' "${TMP_DIR}/noauth.stderr"

echo "git HTTPS snap setup test ok"
