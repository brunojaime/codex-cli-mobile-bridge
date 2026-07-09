# T091 Enforce prerelease Bridge/GitHub channel and exact installable lookup

Spec: `007-initial-preview-release`

Plan: `Preview Completeness Hardening`

- [x] Use `releaseChannel=prerelease` for preview runtime metadata, generated
      Bridge registration, promotion metadata, signing policy, and mobile model
      defaults.
- [x] Require `/installable-apps/{sourceApp}` to return `available=true`,
      `apkUrl`, `releaseTag=android-preview-v*`, `releaseChannel=prerelease`,
      and valid SHA256 when present.
