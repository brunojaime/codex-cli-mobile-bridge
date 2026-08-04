#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MOBILE_DIR="${ROOT_DIR}/frontend/mobile_app"
PUBSPEC_PATH="${MOBILE_DIR}/pubspec.yaml"
REGISTRY_PATH="${ROOT_DIR}/backend/app/infrastructure/config/app_updates.json"
CHANNEL="dev"
PUSH_TAG=false
PUBLISH_RELEASE=false
DRY_RUN=false
SIGNING_ENV_FILE="${CODEX_ANDROID_SIGNING_ENV_FILE:-${ROOT_DIR}/secrets/codex-mobile-android-signing.env}"

usage() {
  cat <<'EOF'
Usage: scripts/publish_android_release_local.sh [options]

Builds and optionally publishes the Codex Mobile Android release on this host.

Options:
  --channel dev|prod       Release channel (default: dev)
  --push-tag               Push the version-derived tag after a successful build
  --publish                Create/update the GitHub release and upload both APKs
  --dry-run                Run preflight without signing or building
  --signing-env FILE       Local signing env file
  -h, --help               Show this help

The signing env must define ANDROID_KEYSTORE_PATH, ANDROID_KEY_ALIAS,
ANDROID_KEY_PASSWORD, and ANDROID_STORE_PASSWORD. ANDROID_STORE_TYPE is optional.
EOF
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --channel)
      CHANNEL="${2:?missing --channel value}"
      shift 2
      ;;
    --push-tag)
      PUSH_TAG=true
      shift
      ;;
    --publish)
      PUBLISH_RELEASE=true
      PUSH_TAG=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --signing-env)
      SIGNING_ENV_FILE="${2:?missing --signing-env value}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$CHANNEL" in
  dev)
    FLAVOR="dev"
    SOURCE_APP="codex-mobile-dev"
    APP_LABEL="Codex Mobile Bridge DEV"
    UPDATER_CHANNEL="dev"
    ENVIRONMENT_COLOR="#38BDF8"
    EXPECTED_PACKAGE_ID="com.example.codex_mobile_frontend.dev"
    ARTIFACT_BASE="codex-mobile-dev"
    CODEX_DEV_MODE="true"
    API_BASE_URL="${DEV_API_BASE_URL:-${CODEX_DEV_APP_UPDATER_BRIDGE_URL:-}}"
    ;;
  prod)
    FLAVOR="prod"
    SOURCE_APP="codex-mobile"
    APP_LABEL="Codex Mobile Bridge"
    UPDATER_CHANNEL="prod"
    ENVIRONMENT_COLOR="#55D6BE"
    EXPECTED_PACKAGE_ID="com.example.codex_mobile_frontend"
    ARTIFACT_BASE="codex-mobile"
    CODEX_DEV_MODE="false"
    API_BASE_URL="${CODEX_APP_UPDATER_BRIDGE_URL:-${API_BASE_URL:-}}"
    ;;
  *)
    echo "Unsupported Android release channel: $CHANNEL" >&2
    exit 2
    ;;
esac

if ! python3 "${ROOT_DIR}/scripts/environment_guard.py" \
  --operation local-android-release \
  --target-environment "$CHANNEL" \
  --action release >/dev/null; then
  echo "Environment guard blocked Android release publication." >&2
  exit 1
fi

API_BASE_URL="${API_BASE_URL%/}"
if [[ -z "$API_BASE_URL" ]]; then
  if [[ "$CHANNEL" == "dev" ]]; then
    echo "DEV_API_BASE_URL or CODEX_DEV_APP_UPDATER_BRIDGE_URL is required for DEV releases." >&2
  else
    echo "CODEX_APP_UPDATER_BRIDGE_URL or API_BASE_URL is required for production releases." >&2
  fi
  exit 1
fi

VERSION="$(awk '/^version:/ { print $2; exit }' "$PUBSPEC_PATH")"
SAFE_VERSION="${VERSION//+/-build.}"
if [[ "$CHANNEL" == "dev" ]]; then
  TAG="android-dev-v${SAFE_VERSION}"
  RELEASE_NAME="Android DEV ${VERSION}"
else
  TAG="android-v${SAFE_VERSION}"
  RELEASE_NAME="Android ${VERSION}"
fi

if [[ -n "$(git -C "$ROOT_DIR" status --porcelain)" ]]; then
  echo "The worktree must be clean before a local Android release." >&2
  exit 2
fi

BRANCH="$(git -C "$ROOT_DIR" symbolic-ref --short HEAD 2>/dev/null || true)"
[[ -n "$BRANCH" ]] || {
  echo "Release must run from a named branch." >&2
  exit 2
}
UPSTREAM="$(git -C "$ROOT_DIR" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
[[ -n "$UPSTREAM" ]] || {
  echo "The current branch must have an upstream before release." >&2
  exit 2
}
LOCAL_HEAD="$(git -C "$ROOT_DIR" rev-parse HEAD)"
REMOTE_HEAD="$(git -C "$ROOT_DIR" rev-parse "$UPSTREAM")"
[[ "$LOCAL_HEAD" == "$REMOTE_HEAD" ]] || {
  echo "Local HEAD must be pushed to $UPSTREAM before release." >&2
  exit 2
}

python3 "${ROOT_DIR}/scripts/validate_android_release_channel.py" \
  --channel "$CHANNEL" \
  --source-app "$SOURCE_APP" \
  --api-base-url "$API_BASE_URL" \
  --app-label "$APP_LABEL" \
  --updater-channel "$UPDATER_CHANNEL" \
  --environment-color "$ENVIRONMENT_COLOR" \
  --release-tag "$TAG" \
  --expected-package-id "$EXPECTED_PACKAGE_ID" \
  --pubspec "$PUBSPEC_PATH" \
  --app-updates-registry "$REGISTRY_PATH" >/dev/null

echo "Local release preflight ok: $CHANNEL $TAG"
echo "Real API: $API_BASE_URL"
if [[ "$DRY_RUN" == true ]]; then
  exit 0
fi

if [[ ! -f "$SIGNING_ENV_FILE" ]]; then
  echo "Missing local Android signing env: $SIGNING_ENV_FILE" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
source "$SIGNING_ENV_FILE"
set +a

missing=()
for key in ANDROID_KEYSTORE_PATH ANDROID_KEY_ALIAS ANDROID_KEY_PASSWORD ANDROID_STORE_PASSWORD; do
  [[ -n "${!key:-}" ]] || missing+=("$key")
done
if (( ${#missing[@]} > 0 )); then
  printf 'Missing Android signing variable(s): %s\n' "${missing[*]}" >&2
  exit 2
fi
if [[ ! -f "$ANDROID_KEYSTORE_PATH" ]]; then
  echo "Android keystore does not exist at the configured path." >&2
  exit 2
fi

KEYSTORE_TARGET="${MOBILE_DIR}/android/upload-keystore.jks"
KEY_PROPERTIES="${MOBILE_DIR}/android/key.properties"
SIGNING_BACKUP_DIR="$(mktemp -d)"
[[ ! -f "$KEYSTORE_TARGET" ]] || cp "$KEYSTORE_TARGET" "$SIGNING_BACKUP_DIR/upload-keystore.jks"
[[ ! -f "$KEY_PROPERTIES" ]] || cp "$KEY_PROPERTIES" "$SIGNING_BACKUP_DIR/key.properties"
cleanup_signing() {
  rm -f "$KEYSTORE_TARGET" "$KEY_PROPERTIES"
  [[ ! -f "$SIGNING_BACKUP_DIR/upload-keystore.jks" ]] || cp "$SIGNING_BACKUP_DIR/upload-keystore.jks" "$KEYSTORE_TARGET"
  [[ ! -f "$SIGNING_BACKUP_DIR/key.properties" ]] || cp "$SIGNING_BACKUP_DIR/key.properties" "$KEY_PROPERTIES"
  rm -rf "$SIGNING_BACKUP_DIR"
}
trap cleanup_signing EXIT

cp "$ANDROID_KEYSTORE_PATH" "$KEYSTORE_TARGET"
chmod 600 "$KEYSTORE_TARGET"
{
  printf 'storeFile=upload-keystore.jks\n'
  printf 'storePassword=%s\n' "$ANDROID_STORE_PASSWORD"
  printf 'keyAlias=%s\n' "$ANDROID_KEY_ALIAS"
  printf 'keyPassword=%s\n' "$ANDROID_KEY_PASSWORD"
  if [[ -n "${ANDROID_STORE_TYPE:-}" ]]; then
    printf 'storeType=%s\n' "$ANDROID_STORE_TYPE"
  fi
} >"$KEY_PROPERTIES"
chmod 600 "$KEY_PROPERTIES"

(
  cd "$MOBILE_DIR"
  flutter pub get
)

API_BASE_URL="$API_BASE_URL" \
CODEX_APP_UPDATER_BRIDGE_URL="$API_BASE_URL" \
  python3 "${ROOT_DIR}/scripts/validate_android_release_network.py"

(
  cd "$MOBILE_DIR"
  flutter build apk --release --flavor "$FLAVOR" \
    --dart-define=API_BASE_URL="$API_BASE_URL" \
    --dart-define=APP_UPDATER_ENABLED=true \
    --dart-define=CODEX_APP_UPDATER_ENABLED=true \
    --dart-define=CODEX_APP_UPDATER_BRIDGE_URL="$API_BASE_URL" \
    --dart-define=CODEX_APP_UPDATER_AUTO_INSTALL=true \
    --dart-define=BRIDGE_APP_SOURCE_APP="$SOURCE_APP" \
    --dart-define=BRIDGE_APP_CHANNEL="$CHANNEL" \
    --dart-define=BRIDGE_UPDATER_CHANNEL="$UPDATER_CHANNEL" \
    --dart-define=BRIDGE_APP_LABEL="$APP_LABEL" \
    --dart-define=BRIDGE_ENVIRONMENT_COLOR="$ENVIRONMENT_COLOR" \
    --dart-define=CODEX_BRIDGE_DEV_MODE="$CODEX_DEV_MODE" \
    --dart-define=CODEX_BRIDGE_WORKSPACE_PATH=codex-cli-mobile-bridge
)

APK_PATH="${MOBILE_DIR}/build/app/outputs/flutter-apk/app-${FLAVOR}-release.apk"
METADATA_PATH="${MOBILE_DIR}/build/app/outputs/apk/${FLAVOR}/release/output-metadata.json"
python3 "${ROOT_DIR}/scripts/verify_android_release_apk.py" \
  --channel "$CHANNEL" \
  --apk "$APK_PATH" \
  --metadata "$METADATA_PATH" \
  --expected-package-id "$EXPECTED_PACKAGE_ID" \
  --expected-output-file "app-${FLAVOR}-release.apk"

ARTIFACT_DIR="${ROOT_DIR}/release-artifacts"
mkdir -p "$ARTIFACT_DIR"
LATEST_APK="${ARTIFACT_DIR}/${ARTIFACT_BASE}.apk"
VERSIONED_APK="${ARTIFACT_DIR}/${ARTIFACT_BASE}-${SAFE_VERSION}.apk"
cp "$APK_PATH" "$LATEST_APK"
cp "$APK_PATH" "$VERSIONED_APK"
sha256sum "$LATEST_APK" "$VERSIONED_APK"

if git -C "$ROOT_DIR" rev-parse "$TAG" >/dev/null 2>&1; then
  TAG_HEAD="$(git -C "$ROOT_DIR" rev-list -n 1 "$TAG")"
  [[ "$TAG_HEAD" == "$LOCAL_HEAD" ]] || {
    echo "Existing tag $TAG does not point to current HEAD." >&2
    exit 2
  }
else
  git -C "$ROOT_DIR" tag -a "$TAG" -m "Android release $VERSION"
fi
if [[ "$PUSH_TAG" == true ]]; then
  git -C "$ROOT_DIR" push origin "$TAG"
fi

if [[ "$PUBLISH_RELEASE" == true ]]; then
  prerelease_args=()
  [[ "$CHANNEL" == "dev" ]] && prerelease_args+=(--prerelease)
  if gh release view "$TAG" --repo brunojaime/codex-cli-mobile-bridge >/dev/null 2>&1; then
    gh release upload "$TAG" "$LATEST_APK" "$VERSIONED_APK" \
      --repo brunojaime/codex-cli-mobile-bridge --clobber
  else
    gh release create "$TAG" "$LATEST_APK" "$VERSIONED_APK" \
      --repo brunojaime/codex-cli-mobile-bridge \
      --title "$RELEASE_NAME" \
      --generate-notes \
      "${prerelease_args[@]}"
  fi
fi

echo "Local Android release ready: $TAG"
