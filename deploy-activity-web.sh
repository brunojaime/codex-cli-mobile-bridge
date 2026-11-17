#!/bin/bash
# Build the activity preview front and publish it on :5180 keeping its runtime config.
set -euo pipefail
cd /home/brunojaime/.local/share/codex-bridge-runtime/activity-preview/frontend/mobile_app
CFG=$(mktemp -d)
cp build/web/bridge-config.json build/web/version.json "$CFG"/
/home/brunojaime/tools/flutter/bin/flutter build web --release --no-wasm-dry-run --no-web-resources-cdn 2>&1 | tail -1
cp "$CFG"/bridge-config.json build/web/
python3 - "$CFG/version.json" <<'PY'
import json, sys, datetime
old = json.load(open(sys.argv[1])); new = json.load(open("build/web/version.json"))
old.update({k: new[k] for k in ("version", "build_number") if k in new})
old["local_revision"] = "activity-ux-" + datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
json.dump(old, open("build/web/version.json", "w"), indent=2)
PY
rm -rf "$CFG"
curl -s http://127.0.0.1:5180/version.json | grep local_revision
