# T093 Require classic Cloudflare Worker format

Spec: `007-initial-preview-release`

Plan: `Preview Completeness Hardening`

- [x] Generate Worker code with `addEventListener('fetch', ...)`.
- [x] Reject `export default` in generated web preview validation when Bridge
      deploys `application/javascript`.
- [x] Keep the local Worker harness working against the classic handler.
