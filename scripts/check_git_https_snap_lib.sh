#!/usr/bin/env bash

json_escape() {
  local text="$1"
  text="${text//\\/\\\\}"
  text="${text//\"/\\\"}"
  text="${text//$'\n'/\\n}"
  printf '%s' "$text"
}

last_non_empty_line() {
  local text="$1"
  local last=""
  while IFS= read -r line; do
    if [[ -n "${line// }" ]]; then
      last="$line"
    fi
  done <<< "$text"
  printf '%s' "$last"
}

run_stage_json() {
  local stage_name="$1"
  shift

  set +e
  local output
  output="$("$@" 2>&1)"
  local exit_code=$?
  set -e

  local result message
  if [[ $exit_code -eq 0 ]]; then
    result="passed"
    message="$(last_non_empty_line "$output")"
    [[ -n "$message" ]] || message="${stage_name} ok"
  else
    result="failed"
    message="$(last_non_empty_line "$output")"
    [[ -n "$message" ]] || message="${stage_name} failed"
    JSON_STATUS="failed"
  fi

  JSON_STAGES+=("{\"name\":\"$(json_escape "$stage_name")\",\"result\":\"$(json_escape "$result")\",\"message\":\"$(json_escape "$message")\"}")
  return "$exit_code"
}

emit_stage_summary_json() {
  local schema_version="$1"
  local joined=""
  local stage
  for stage in "${JSON_STAGES[@]}"; do
    if [[ -n "$joined" ]]; then
      joined+=","
    fi
    joined+="$stage"
  done
  printf '{"schema_version":"%s","status":"%s","stages":[%s]}\n' "$(json_escape "$schema_version")" "$(json_escape "$JSON_STATUS")" "$joined"
}
