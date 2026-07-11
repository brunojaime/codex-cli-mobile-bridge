# Deterministic Android Preview Release And Bridge Installable Registration

Move Android preview release and Bridge installable app registration into init
for frontend strategies that support installable output.

Status: completed

## Deterministic Pipeline Scope

- Android preview APK build.
- `android-preview-v*` GitHub prerelease.
- APK and updater metadata verification.
- Bridge installable app registration.
- Release blockers with exact retry commands.

## Tasks

- [x] T027 Build Android preview APK for Flutter/installable strategies against the real preview API.
- [x] T028 Create or verify GitHub prerelease `android-preview-v*` with APK and updater metadata.
- [x] T029 Register or update Bridge installable app entry for supported strategies.
- [x] T030 Validate APK metadata, release metadata, Bridge installable discovery, and no mock/demo flags.
- [x] T031 Persist Android release and installable-app blockers with exact retry commands.
