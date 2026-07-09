# T095 Validate preview runtime profiles across sources of truth

Spec: `007-initial-preview-release`

Plan: `Preview Completeness Hardening`

- [x] Require `mock`, `preview`, `real`, and `staging` in `.codex/project.yaml`,
      `release/release-contracts.yaml`, web preview manifest, backend config,
      Flutter config, and preview workflow.
- [x] Fail generated preview release profile validation if preview metadata is
      present in one source but missing in another.
