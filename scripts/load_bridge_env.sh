#!/usr/bin/env bash
# Official Bridge env/secrets loader for Project Factory release operations.
# It loads known local env files and reports only missing variable names.

bridge_env_load() {
  local bridge_root="${CODEX_MOBILE_BRIDGE_ROOT:-/home/batata/Projects/codex-cli-mobile-bridge}"
  local loaded=0
  local env_file
  for env_file in "$bridge_root/secrets/cloudflare.env" "$bridge_root/.env"; do
    if [[ -f "$env_file" ]]; then
      bridge_env_load_file "$env_file"
      loaded=1
    fi
  done
  export CODEX_MOBILE_BRIDGE_ENV_LOADED="$loaded"
}

bridge_env_load_file() {
  local env_file="$1"
  local line key value
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    [[ "$line" =~ ^[[:space:]]*export[[:space:]]+ ]] && line="${line#export }"
    [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || continue
    key="${line%%=*}"
    value="${line#*=}"
    if [[ "$value" == \"*\" && "$value" == *\" ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
      value="${value:1:${#value}-2}"
    fi
    export "$key=$value"
  done < "$env_file"
}

bridge_env_require() {
  local missing=()
  local key
  for key in "$@"; do
    if [[ -z "${!key:-}" ]]; then
      missing+=("$key")
    fi
  done
  if (( ${#missing[@]} > 0 )); then
    printf 'Bridge env preflight failed. Missing required variable(s): %s\n' "${missing[*]}" >&2
    printf 'Load them from /home/batata/Projects/codex-cli-mobile-bridge/secrets/cloudflare.env or /home/batata/Projects/codex-cli-mobile-bridge/.env.\n' >&2
    return 2
  fi
}

bridge_env_require_any() {
  local label="$1"
  shift
  local key
  for key in "$@"; do
    if [[ -n "${!key:-}" ]]; then
      return 0
    fi
  done
  printf 'Bridge env preflight failed. Missing one of %s: %s\n' "$label" "$*" >&2
  printf 'Load it from /home/batata/Projects/codex-cli-mobile-bridge/secrets/cloudflare.env or /home/batata/Projects/codex-cli-mobile-bridge/.env.\n' >&2
  return 2
}

bridge_env_load_preview_signing() {
  local source_app="${SOURCE_APP:-${APP_SLUG:-}}"
  if [[ -z "$source_app" ]]; then
    printf 'Bridge env preflight failed. SOURCE_APP or APP_SLUG is required before loading preview signing.\n' >&2
    return 2
  fi
  local bridge_root="${CODEX_MOBILE_BRIDGE_ROOT:-/home/batata/Projects/codex-cli-mobile-bridge}"
  local signing_env="$bridge_root/secrets/$source_app-preview-signing.env"
  local keystore="$bridge_root/secrets/$source_app-preview-upload-keystore.jks"
  [[ -f "$signing_env" ]] || {
    printf 'Android preview signing env missing: %s\n' "$signing_env" >&2
    return 2
  }
  [[ -f "$keystore" ]] || {
    printf 'Android preview keystore missing: %s\n' "$keystore" >&2
    return 2
  }
  set -a
  # shellcheck disable=SC1090
  source "$signing_env"
  set +a
  export ANDROID_KEYSTORE_PATH="$keystore"
  bridge_env_require ANDROID_KEY_ALIAS ANDROID_STORE_PASSWORD ANDROID_KEY_PASSWORD
}

bridge_env_load
