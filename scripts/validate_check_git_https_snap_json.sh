#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCHEMA_PATH="${SCRIPT_DIR}/../docs/check_git_https_snap.schema.json"
TMP_JSON="$(mktemp)"
TMP_ROOT_JSON="$(mktemp)"
TMP_FAIL_JSON="$(mktemp)"
TMP_FAIL_DIR="$(mktemp -d)"
trap 'rm -f "${TMP_JSON}" "${TMP_ROOT_JSON}" "${TMP_FAIL_JSON}"; rm -rf "${TMP_FAIL_DIR}"' EXIT

print_help() {
  cat <<'EOF'
Usage: validate_check_git_https_snap_json.sh

Run non-destructive contract validation for check_git_https_snap.sh --json.
It validates both:
1. the normal success payload from scripts/check_git_https_snap.sh
2. the equivalent success payload from ./check_git_https_snap.sh
3. a controlled failure payload built from a temporary wrapper over the shared JSON helper

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

set +e
bash "${SCRIPT_DIR}/check_git_https_snap.sh" --json > "${TMP_JSON}"
STATUS=$?
set -e
[[ "${STATUS}" -eq 0 ]]

set +e
"${REPO_ROOT}/check_git_https_snap.sh" --json > "${TMP_ROOT_JSON}"
STATUS=$?
set -e
[[ "${STATUS}" -eq 0 ]]

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
    if payload.get("schema_version") != schema["properties"]["schema_version"]["const"]:
        raise SystemExit(1)
    if payload.get("status") not in schema["properties"]["status"]["enum"]:
        raise SystemExit(1)
    stages = payload.get("stages")
    if not isinstance(stages, list) or not stages:
        raise SystemExit(1)
    item_schema = schema["properties"]["stages"]["items"]
    required_fields = set(item_schema["required"])
    valid_names = set(item_schema["properties"]["name"]["enum"])
    valid_results = set(item_schema["properties"]["result"]["enum"])
    for item in stages:
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
' "${TMP_JSON}" "${SCHEMA_PATH}"

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
    if payload.get("schema_version") != schema["properties"]["schema_version"]["const"]:
        raise SystemExit(1)
    if payload.get("status") not in schema["properties"]["status"]["enum"]:
        raise SystemExit(1)
    stages = payload.get("stages")
    if not isinstance(stages, list) or not stages:
        raise SystemExit(1)
    item_schema = schema["properties"]["stages"]["items"]
    required_fields = set(item_schema["required"])
    valid_names = set(item_schema["properties"]["name"]["enum"])
    valid_results = set(item_schema["properties"]["result"]["enum"])
    for item in stages:
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
' "${TMP_ROOT_JSON}" "${SCHEMA_PATH}"

cat > "${TMP_FAIL_DIR}/test_git_https_snap_setup.sh" <<'EOF'
#!/usr/bin/env bash
echo "simulated harness failure" >&2
exit 1
EOF
chmod +x "${TMP_FAIL_DIR}/test_git_https_snap_setup.sh"

cat > "${TMP_FAIL_DIR}/run_check_failure_json.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
source "${SCRIPT_DIR}/check_git_https_snap_lib.sh"
JSON_STATUS="passed"
JSON_STAGES=()
run_stage_json lint bash "${SCRIPT_DIR}/lint_git_https_snap_shell.sh" || {
  emit_stage_summary_json "1.0"
  exit 1
}
run_stage_json harness bash "${TMP_FAIL_DIR}/test_git_https_snap_setup.sh" || {
  emit_stage_summary_json "1.0"
  exit 1
}
emit_stage_summary_json "1.0"
EOF
chmod +x "${TMP_FAIL_DIR}/run_check_failure_json.sh"

set +e
bash "${TMP_FAIL_DIR}/run_check_failure_json.sh" > "${TMP_FAIL_JSON}"
STATUS=$?
set -e
[[ "${STATUS}" -ne 0 ]]

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
    if payload.get("schema_version") != schema["properties"]["schema_version"]["const"]:
        raise SystemExit(1)
    if payload.get("status") not in schema["properties"]["status"]["enum"]:
        raise SystemExit(1)
    stages = payload.get("stages")
    if not isinstance(stages, list) or not stages:
        raise SystemExit(1)
    item_schema = schema["properties"]["stages"]["items"]
    required_fields = set(item_schema["required"])
    valid_names = set(item_schema["properties"]["name"]["enum"])
    valid_results = set(item_schema["properties"]["result"]["enum"])
    for item in stages:
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

if payload.get("status") != "failed":
    raise SystemExit(1)
stages = payload["stages"]
if stages[-1]["name"] != "harness":
    raise SystemExit(1)
if stages[-1]["result"] != "failed":
    raise SystemExit(1)
' "${TMP_FAIL_JSON}" "${SCHEMA_PATH}"

echo "check_git_https_snap JSON ok"
