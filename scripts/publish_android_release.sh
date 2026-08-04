#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --channel)
      ARGS+=(--channel "${2:?missing --channel value}")
      shift 2
      ;;
    --push)
      ARGS+=(--publish)
      shift
      ;;
    --dry-run)
      ARGS+=(--dry-run)
      shift
      ;;
    --signing-env)
      ARGS+=(--signing-env "${2:?missing --signing-env value}")
      shift 2
      ;;
    -h|--help)
      exec "$ROOT_DIR/scripts/publish_android_release_local.sh" --help
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      exit 2
      ;;
  esac
done

exec "$ROOT_DIR/scripts/publish_android_release_local.sh" "${ARGS[@]}"
