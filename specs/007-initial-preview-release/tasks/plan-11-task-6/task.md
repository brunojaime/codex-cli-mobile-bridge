# T096 Regenerate and validate final release output evidence

Spec: `007-initial-preview-release`

Plan: `Preview Completeness Hardening`

- [x] Update `release/release-output-template.md` from final validation with
      current commit, push state, APK URL, APK SHA256 when available, release
      URL, Bridge installable URL, Cloudflare URLs, validations, and blockers.
- [x] Fail validation when release output is stale or claims readiness without
      APK, Bridge, Cloudflare, Workbench, or D1 evidence.
