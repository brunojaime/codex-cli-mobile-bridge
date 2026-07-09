# T092 Generate Workbench visibility gating and Flutter preview tests

Spec: `007-initial-preview-release`

Plan: `Preview Completeness Hardening`

- [x] Generate Workbench visibility rules for `mock`, `preview`, `staging`, and
      `real`.
- [x] Show Workbench in preview only to `owner`/`admin` or explicitly authorized
      developer mode.
- [x] Generate Flutter tests that fail if preview owner/admin users do not see
      Workbench or if real runtime shows Workbench.
