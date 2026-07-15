#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUBSPEC_PATH="$ROOT_DIR/frontend/mobile_app/pubspec.yaml"
CHANNEL="prod"
PUSH_TAG=false
DRY_RUN=false
PYTHON_BIN="${PYTHON:-${ROOT_DIR}/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

usage() {
  cat <<'EOF'
Usage: scripts/publish_android_release.sh [--channel prod|dev] [--push] [--dry-run]

Creates the Android release tag for the selected Codex Mobile channel.

  prod  -> android-vX.Y.Z-build.N
  dev   -> android-dev-vX.Y.Z-build.N

Pushing the tag lets GitHub Actions build and publish the APK.
EOF
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --channel)
      CHANNEL="${2:?missing --channel value}"
      shift 2
      ;;
    --push)
      PUSH_TAG=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Opcion desconocida: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$CHANNEL" in
  prod|dev) ;;
  *)
    echo "Canal invalido: $CHANNEL. Usa prod o dev." >&2
    exit 2
    ;;
esac

if [[ ! -f "$PUBSPEC_PATH" ]]; then
  echo "No se encontro $PUBSPEC_PATH" >&2
  exit 1
fi

VERSION="$(awk '/^version:/ { print $2; exit }' "$PUBSPEC_PATH")"

if [[ -z "$VERSION" ]]; then
  echo "No pude leer la version desde $PUBSPEC_PATH" >&2
  exit 1
fi

GUARD_OUTPUT="$("$PYTHON_BIN" "${ROOT_DIR}/scripts/environment_guard.py" \
  --operation android-release-publish \
  --target-environment "${CHANNEL}" \
  --action release)" || {
  echo "Environment guard blocked Android release publication." >&2
  echo "${GUARD_OUTPUT}" >&2
  exit 1
}
echo "${GUARD_OUTPUT}" | "$PYTHON_BIN" -c 'import json,sys; p=json.load(sys.stdin); print("Environment guard ok: current={} target={} audit={}".format(p["current_environment"], p["target_environment"], p["audit_log"]))'

if [[ "$CHANNEL" == "dev" ]]; then
  TAG="android-dev-v${VERSION//+/-build.}"
  SOURCE_APP="codex-mobile-dev"
  UPDATER_CHANNEL="dev"
  APP_LABEL="Codex Mobile Bridge DEV"
  ENVIRONMENT_COLOR="#38BDF8"
  EXPECTED_PACKAGE_ID="com.example.codex_mobile_frontend.dev"
  BRIDGE_URL="${DEV_API_BASE_URL:-${CODEX_DEV_APP_UPDATER_BRIDGE_URL:-}}"
  if [[ -z "$BRIDGE_URL" ]]; then
    echo "DEV_API_BASE_URL or CODEX_DEV_APP_UPDATER_BRIDGE_URL is required for DEV releases." >&2
    exit 1
  fi
else
  TAG="android-v${VERSION//+/-build.}"
  SOURCE_APP="codex-mobile"
  UPDATER_CHANNEL="prod"
  APP_LABEL="Codex Mobile Bridge"
  ENVIRONMENT_COLOR="#55D6BE"
  EXPECTED_PACKAGE_ID="com.example.codex_mobile_frontend"
  BRIDGE_URL="${CODEX_APP_UPDATER_BRIDGE_URL:-${API_BASE_URL:-http://batata-default-string.tail0302c4.ts.net}}"
fi
BRIDGE_URL="${BRIDGE_URL%/}"

PREFLIGHT_OUTPUT="$(mktemp)"
trap 'rm -f "${PREFLIGHT_OUTPUT}"' EXIT

"${PYTHON_BIN}" "${ROOT_DIR}/scripts/validate_android_release_channel.py" \
  --channel "${CHANNEL}" \
  --source-app "${SOURCE_APP}" \
  --api-base-url "${BRIDGE_URL}" \
  --app-label "${APP_LABEL}" \
  --updater-channel "${UPDATER_CHANNEL}" \
  --environment-color "${ENVIRONMENT_COLOR}" \
  --release-tag "${TAG}" \
  --expected-package-id "${EXPECTED_PACKAGE_ID}" \
  --pubspec "${PUBSPEC_PATH}" \
  --app-updates-registry "${ROOT_DIR}/backend/app/infrastructure/config/app_updates.json" >"${PREFLIGHT_OUTPUT}"

echo "Release preflight ok: ${CHANNEL} ${TAG}"

if [[ "$DRY_RUN" == true ]]; then
  cat "${PREFLIGHT_OUTPUT}"
  echo "Dry run only; no tag created."
  exit 0
fi

if ! git -C "$ROOT_DIR" diff --quiet || ! git -C "$ROOT_DIR" diff --cached --quiet; then
  echo "Hay cambios sin commit. Hace commit antes de publicar el release." >&2
  exit 1
fi

if git -C "$ROOT_DIR" rev-parse "$TAG" >/dev/null 2>&1; then
  echo "El tag $TAG ya existe." >&2
  exit 1
fi

git -C "$ROOT_DIR" tag -a "$TAG" -m "Android release $VERSION"

echo "Tag creado: $TAG"

if [[ "$PUSH_TAG" == true ]]; then
  git -C "$ROOT_DIR" push origin "$TAG"
  echo "Tag enviado. GitHub Actions va a compilar y publicar el APK en Releases."
else
  echo "Para publicar en GitHub ejecuta:"
  echo "  git push origin $TAG"
fi

echo "Updater Bridge:"
echo "  ${BRIDGE_URL}/app-updates/${SOURCE_APP}?platform=android&currentVersion=0.0.0&currentBuild=0&channel=${UPDATER_CHANNEL}"
echo "Instalacion en telefono: abrir o reanudar Codex Mobile; el updater baja el APK desde el Bridge y abre el instalador de Android."
