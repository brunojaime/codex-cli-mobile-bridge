# Android Preview Release Workflow

Add a preview-specific Android release lane.

- Generate `android-preview-v*` tag workflow.
- Generate `scripts/publish_android_preview_release.sh`.
- Build APKs with preview runtime defines.
- Allow explicit debug-preview signing only when metadata says so.
- Keep productive release signing gates unchanged.
- Verify GitHub release assets and app updater metadata.
