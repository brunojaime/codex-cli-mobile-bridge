---
name: codex-mobile-android-release
description: Publish or update the Android APK release for the codex-cli-mobile-bridge repository. Use when the user asks to deploy, publish, ship, upload, or refresh the Android app/APK/GitHub release for this repo so it can be installed on a phone.
---

# Codex Mobile Android Release

Use this skill only inside the `codex-cli-mobile-bridge` repository when the user wants a real Android APK release on GitHub.

## What This Repo Already Uses

This repository already has the Android release flow:

- `frontend/mobile_app/pubspec.yaml` holds the Flutter app version
- `scripts/publish_android_release.sh` creates the Android release tag
- `.github/workflows/android-release.yml` builds the APK on GitHub Actions
- the workflow publishes:
  - `codex-mobile.apk`
  - `codex-mobile-<version>.apk`

Default to this tag-driven workflow instead of inventing a new one.

## Required Checks

Before publishing:

1. Confirm these files exist:
   - `frontend/mobile_app/pubspec.yaml`
   - `scripts/publish_android_release.sh`
   - `.github/workflows/android-release.yml`
2. Read the current Flutter version from `frontend/mobile_app/pubspec.yaml`.
3. Inspect existing Android release tags.
4. Check the git worktree.

If the working tree contains unfinished changes, do not tag blindly. Commit the intended changes first or ask the user to confirm scope.

## Version Rule

The helper script turns the Flutter version into a tag like:

- `1.0.0+10` -> `android-v1.0.0-build.10`

If that tag already exists, the release will fail. In that case:

1. Bump the version in `frontend/mobile_app/pubspec.yaml`.
2. Commit the version bump together with any releaseable changes.
3. Push the commit.
4. Run the release tagging flow.

Unless the user specifies a version, prefer the smallest safe increment:

- keep the semantic version the same
- increase the build number by 1

## Preferred Release Flow

Use this flow:

1. Verify the repo is on the intended commit.
2. Run targeted validation if the user changed the app.
   - Prefer `flutter analyze`
   - Use `flutter test` when the touched area has relevant tests
3. Ensure the intended changes are committed and pushed.
4. Run:

```bash
./scripts/publish_android_release.sh --push
```

5. Watch GitHub Actions or the GitHub Release until the APK assets appear.
6. Report:
   - release tag
   - release URL
   - direct APK URL for `codex-mobile.apk`

## Fallback Flow

Use a manual APK upload only when the user explicitly wants a one-off asset on an existing release or the tag workflow is not the right fit.

Manual fallback:

1. Build locally:

```bash
cd frontend/mobile_app
flutter build apk --release
```

2. Upload to the chosen release with `gh release upload`.

Do not default to this when the standard Android tag workflow is available.

## Verification

After publishing, verify one of these:

- the GitHub release contains APK assets
- `releases/latest/download/codex-mobile.apk` resolves for the new Android tag release

If the release exists but has no APK asset yet, say that clearly and keep checking the workflow status.

## Report Format

Keep the final report short and concrete:

- Flutter version
- Android tag
- release URL
- direct APK URL
- whether the APK was produced by GitHub Actions or uploaded manually
- any caveat about signing, workflow still running, or missing assets
