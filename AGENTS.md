# Codex Mobile Bridge Agent Notes

## Release Data Policy

Production or user-installable releases must use real backend configuration and
real data paths. Do not enable mock data, seeded demo state, local demo mode, or
placeholder API URLs in release builds unless the user explicitly asks for a
demo/mock APK.

For Codex Mobile Android releases, use the standard tag workflow from
`scripts/publish_android_release.sh` after bumping `frontend/mobile_app/pubspec.yaml`.
Before publishing, verify the workflow will build with the intended real
`API_BASE_URL`/bridge URL and app updater defines. If a release is specifically
for feedback/edit mode, keep the real backend URL and real workspace/update
configuration; feedback mode should not imply mock data.

If the user does request a mock/demo release, make that visible in the version
scope, release tag, and final report so it cannot be confused with a real-data
release.
