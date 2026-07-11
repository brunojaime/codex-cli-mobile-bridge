#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKER="$ROOT_DIR/deploy/cloudflare-email-endpoint/worker/src/index.js"
HARNESS="$ROOT_DIR/deploy/cloudflare-email-endpoint/worker/local_test.mjs"
WRANGLER="$ROOT_DIR/deploy/cloudflare-email-endpoint/wrangler.toml.example"

fail() {
  echo "cloudflare email endpoint validation failed: $*" >&2
  exit 1
}

[[ -f "$WORKER" ]] || fail "missing worker source"
[[ -f "$HARNESS" ]] || fail "missing local harness"
[[ -f "$WRANGLER" ]] || fail "missing wrangler example"

grep -q "export default" "$WORKER" || fail "worker must be an ES module"
grep -q "async fetch(request, env, ctx)" "$WORKER" || fail "worker fetch entrypoint missing"
! grep -q "addEventListener('fetch'" "$WORKER" || fail "classic Worker syntax is not allowed"
grep -q "env.EMAIL.send" "$WORKER" || fail "Cloudflare Email Service binding is not used"
grep -q "api.brevo.com/v3/smtp/email" "$WORKER" || fail "Brevo free-compatible provider is not wired"
grep -q "EMAIL_ENDPOINT_TOKEN" "$WORKER" || fail "endpoint token check missing"
grep -q "BREVO_API_KEY" "$WORKER" || fail "Brevo API key support missing"
grep -q "ALLOWED_RECIPIENTS" "$WORKER" || fail "recipient allowlist support missing"
grep -q "EMAIL_PROVIDER = \"brevo\"" "$WRANGLER" || fail "Brevo provider should be default in wrangler example"
grep -q "# \\[\\[send_email\\]\\]" "$WRANGLER" || fail "paid Cloudflare send_email example missing"

if command -v node >/dev/null 2>&1; then
  node "$HARNESS"
else
  echo "node not found; skipped local harness"
fi

echo "cloudflare email endpoint validation completed"
