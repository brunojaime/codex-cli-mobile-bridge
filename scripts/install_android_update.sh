#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRIDGE_URL="${BRIDGE_URL:-http://127.0.0.1:8000}"
SOURCE_APP="${SOURCE_APP:-codex-mobile}"
CURRENT_VERSION="${CURRENT_VERSION:-0.0.0}"
CURRENT_BUILD="${CURRENT_BUILD:-0}"
CHANNEL="${CHANNEL:-stable}"
PLATFORM="${PLATFORM:-android}"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT_DIR/.run/apks}"
MODE="download"

usage() {
  cat <<'EOF'
Usage: scripts/install_android_update.sh [options]

Resolves an Android APK through the Bridge app-updater endpoint, so the APK can
be installed without browsing GitHub manually.

Options:
  --bridge-url URL       Bridge backend URL. Default: BRIDGE_URL or http://127.0.0.1:8000
  --source-app APP       App update id. Default: SOURCE_APP or codex-mobile
  --current-version VER  Installed version used for update check. Default: 0.0.0
  --current-build N      Installed build used for update check. Default: 0
  --channel NAME         Update channel. Default: stable
  --output-dir DIR       APK download directory. Default: .run/apks
  --print-url            Only print the Bridge APK URL.
  --download-only        Download APK and print path. This is the default.
  --adb-install          Download APK and run: adb install -r <apk>
  -h, --help             Show this help.

Android still requires user-controlled install approval unless a connected
device is installed through adb.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --bridge-url)
      BRIDGE_URL="${2:?missing --bridge-url value}"
      shift 2
      ;;
    --source-app)
      SOURCE_APP="${2:?missing --source-app value}"
      shift 2
      ;;
    --current-version)
      CURRENT_VERSION="${2:?missing --current-version value}"
      shift 2
      ;;
    --current-build)
      CURRENT_BUILD="${2:?missing --current-build value}"
      shift 2
      ;;
    --channel)
      CHANNEL="${2:?missing --channel value}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:?missing --output-dir value}"
      shift 2
      ;;
    --print-url)
      MODE="print"
      shift
      ;;
    --download-only)
      MODE="download"
      shift
      ;;
    --adb-install)
      MODE="adb"
      shift
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

mkdir -p "$OUTPUT_DIR"

python3 - "$BRIDGE_URL" "$SOURCE_APP" "$CURRENT_VERSION" "$CURRENT_BUILD" \
  "$CHANNEL" "$PLATFORM" "$OUTPUT_DIR" "$MODE" <<'PY'
import json
import os
import pathlib
import subprocess
import sys
import urllib.parse
import urllib.request

bridge_url, source_app, current_version, current_build, channel, platform, output_dir, mode = sys.argv[1:]
base = bridge_url.rstrip("/")
query = urllib.parse.urlencode(
    {
        "currentVersion": current_version,
        "currentBuild": current_build,
        "channel": channel,
        "platform": platform,
    }
)
metadata_url = f"{base}/app-updates/{urllib.parse.quote(source_app)}?{query}"

try:
    with urllib.request.urlopen(metadata_url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
except Exception as exc:
    raise SystemExit(f"Failed to resolve update from {metadata_url}: {exc}") from exc

apk_url = payload.get("apkUrl")
if not apk_url:
    latest = payload.get("latestBuild")
    raise SystemExit(
        f"No installable APK available for {source_app}; "
        f"available={payload.get('available')} latestBuild={latest}"
    )

if mode == "print":
    print(apk_url)
    raise SystemExit(0)

asset_name = payload.get("apkAssetName") or f"{source_app}.apk"
safe_name = pathlib.Path(str(asset_name)).name
target = pathlib.Path(output_dir).expanduser().resolve() / safe_name
tmp = target.with_suffix(target.suffix + ".tmp")

with urllib.request.urlopen(apk_url, timeout=120) as response:
    with tmp.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
os.replace(tmp, target)
print(str(target))

if mode == "adb":
    subprocess.run(["adb", "install", "-r", str(target)], check=True)
PY
