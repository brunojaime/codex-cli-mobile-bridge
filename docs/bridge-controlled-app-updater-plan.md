# Bridge-Controlled App Updater Plan

## Goal

Add a reusable Android app update flow where each Flutter app checks Codex Mobile Bridge for update metadata instead of talking directly to GitHub Releases.

The app should notify the user when a new APK is available, download it, verify it, and hand off installation to Android. Android still requires user confirmation for sideloaded APK updates; silent updates are out of scope.

## Design Principles

- Keep apps decoupled from GitHub API details.
- Keep app integration minimal: configure `sourceApp`, `bridgeUrl`, current version/build, and add the reusable updater UI/service.
- Centralize release discovery and policy in the Bridge backend.
- Make update metadata generic for any app, not only Ambientando Calendar.
- Preserve Android safety: same signing key, checksum verification, explicit user confirmation.
- Avoid requiring app code changes for future release source or policy changes.

## User Experience

1. App starts or resumes.
2. App checks the Bridge for update metadata in the background.
3. If no update exists, nothing is shown.
4. If an update exists, the app shows a lightweight notification/banner/dialog:
   - current version
   - latest version
   - release notes if available
   - `Actualizar` action
   - `Más tarde` action for optional updates
5. If the user taps `Actualizar`:
   - APK downloads from the URL returned by the Bridge
   - app verifies SHA-256
   - app opens the Android package installer
6. Android asks the user to confirm installation.
7. App update completes through Android.

For required updates, the UI can keep reminding or block non-critical flows, but Android installation must still be user-confirmed.

## Update Status Model

Use these statuses internally in the reusable Flutter updater package and expose them for UI/testing:

- `idle`: no check has started.
- `checking`: app is querying the Bridge.
- `upToDate`: Bridge returned no newer version.
- `updateAvailable`: a newer optional update is available.
- `updateRequired`: a newer required update is available.
- `downloading`: APK download is in progress.
- `downloaded`: APK downloaded successfully.
- `verifying`: checksum/signature metadata is being verified.
- `readyToInstall`: APK passed verification and can be handed to Android.
- `installing`: Android installer intent was launched.
- `dismissed`: user postponed an optional update.
- `failed`: check/download/verification/install launch failed.

Failure state should include a machine-readable reason:

- `bridgeUnavailable`
- `invalidResponse`
- `noCompatibleAsset`
- `downloadFailed`
- `checksumMismatch`
- `permissionRequired`
- `installerUnavailable`
- `unknown`

## Backend Scope

### Configuration

Add a Bridge-side app update registry. It can start as a JSON/YAML file or settings object and later move to database storage.

Example:

```json
{
  "ambientando-calendar": {
    "displayName": "Ambientando Calendar",
    "repo": "brunojaime/ambientando-calendar",
    "releaseTagPattern": "android-local-demo-feedback-v*",
    "apkAssetPattern": "ambientando-calendar-*.apk",
    "latestAssetName": "ambientando-calendar.apk",
    "requiredMinimumBuild": null,
    "enabled": true
  },
  "codex-mobile": {
    "displayName": "Codex Mobile Bridge",
    "repo": "brunojaime/codex-cli-mobile-bridge",
    "releaseTagPattern": "android-v*",
    "apkAssetPattern": "codex-mobile-*.apk",
    "latestAssetName": "codex-mobile.apk",
    "requiredMinimumBuild": null,
    "enabled": true
  }
}
```

### API

Add these endpoints:

```http
GET /app-updates
GET /app-updates/{sourceApp}
```

`GET /app-updates/{sourceApp}` accepts optional query params:

```text
platform=android
currentVersion=1.0.0
currentBuild=38
channel=stable
```

Example response when update exists:

```json
{
  "kind": "codex.appUpdate",
  "version": 1,
  "sourceApp": "ambientando-calendar",
  "displayName": "Ambientando Calendar",
  "platform": "android",
  "currentVersion": "1.0.0",
  "currentBuild": 38,
  "latestVersion": "1.0.0",
  "latestBuild": 39,
  "releaseTag": "android-local-demo-feedback-v1.0.0-build.39",
  "releaseUrl": "https://github.com/brunojaime/ambientando-calendar/releases/tag/android-local-demo-feedback-v1.0.0-build.39",
  "apkUrl": "https://github.com/brunojaime/ambientando-calendar/releases/download/android-local-demo-feedback-v1.0.0-build.39/ambientando-calendar-1.0.0-build.39.apk",
  "apkAssetName": "ambientando-calendar-1.0.0-build.39.apk",
  "sha256": "expected-sha256",
  "sizeBytes": 54670545,
  "releaseNotes": "Optional short changelog.",
  "required": false,
  "available": true
}
```

Example response when current app is up to date:

```json
{
  "kind": "codex.appUpdate",
  "version": 1,
  "sourceApp": "ambientando-calendar",
  "platform": "android",
  "currentVersion": "1.0.0",
  "currentBuild": 39,
  "latestVersion": "1.0.0",
  "latestBuild": 39,
  "available": false,
  "required": false
}
```

### Backend Behavior

1. Validate `sourceApp`.
2. Load update config for that app.
3. Query GitHub Releases for the configured repo.
4. Filter releases by tag pattern and channel.
5. Select the latest valid Android release.
6. Select the APK asset by configured pattern.
7. Derive `latestVersion` and `latestBuild` from tag or release metadata.
8. Include SHA-256:
   - Prefer a `.sha256` release asset if present.
   - Otherwise use GitHub asset digest when available.
   - If no checksum exists, return `sha256: null` and let the Flutter package decide whether to block or warn.
9. Compare latest build with `currentBuild`.
10. Return update metadata.

### Backend Tests

Add tests for:

- Known app with newer release returns `available: true`.
- Known app with same build returns `available: false`.
- Unknown `sourceApp` returns 404 or disabled response.
- Disabled app returns no update.
- Release without APK asset is ignored.
- Multiple releases choose highest valid build.
- Required update when `currentBuild < requiredMinimumBuild`.
- GitHub failure returns stable error response.
- Checksum is surfaced when available.
- `/app-updates` lists configured apps without leaking secrets.

## Flutter Reusable Package Scope

Create a package, or add a new module if preferred:

```text
packages/codex_app_updater
```

The package should provide:

- `CodexAppUpdaterConfig`
- `CodexAppUpdaterController`
- `CodexAppUpdateStatus`
- `CodexAppUpdateInfo`
- reusable update banner/dialog widget
- Android APK downloader
- checksum verifier
- Android installer launcher

Example app integration:

```dart
CodexAppUpdater(
  config: CodexAppUpdaterConfig(
    sourceApp: 'ambientando-calendar',
    bridgeUrl: bridgeUrl,
    currentVersion: packageInfo.version,
    currentBuild: int.parse(packageInfo.buildNumber),
    enabled: true,
  ),
  child: MyApp(),
)
```

### Android Requirements

The package or host app must support:

- APK download to app cache.
- FileProvider or supported install intent path.
- `REQUEST_INSTALL_PACKAGES` where required.
- Handling Android's "install unknown apps" permission screen.
- Clear error when user must grant install permission.

The package must not attempt silent install.

### Flutter Package Tests

Add tests for:

- Parses update response correctly.
- No UI when `available: false`.
- Shows optional update action when `available: true`.
- Shows required update state when `required: true`.
- Download status transitions.
- Checksum mismatch blocks installation.
- Installer launch is called only after successful verification.
- Bridge unavailable maps to `failed(bridgeUnavailable)`.
- `sourceApp`, version, build, and platform are sent to backend.

## App Integration Scope

For each app, keep changes minimal:

1. Add package dependency.
2. Configure `sourceApp`, `bridgeUrl`, current version/build, and `enabled`.
3. Add updater wrapper/widget near app root.
4. Add or update tests.
5. Release a new APK so the updater exists in the installed app.

Do not duplicate updater internals inside the app.

## Ambientando Calendar Integration

Expected changes:

- Update `frontend/pubspec.yaml` with `codex_app_updater` dependency.
- Add updater wrapper/config in the app root.
- Use `sourceApp: ambientando-calendar`.
- Use existing Bridge URL config.
- Add widget tests for update available and up-to-date cases.
- Bump Flutter build number before release.
- Publish one Android APK release only after validation passes.

## Validation Plan

### Bridge Backend

Run:

```bash
uv run pytest tests/test_message_flow.py
uv run python -m compileall backend
```

If new dedicated tests are created, include:

```bash
uv run pytest tests/test_app_updates.py
```

If ruff is available:

```bash
uv run ruff check backend tests
```

### Flutter Updater Package

Run from the package directory:

```bash
flutter pub get
flutter analyze
flutter test
```

### Bridge Mobile App

Run if mobile app code is touched:

```bash
cd frontend/mobile_app
flutter pub get
flutter analyze
flutter test
```

### Ambientando Calendar

Run from `frontend/`:

```bash
flutter pub get
flutter analyze
flutter test
```

Also validate a CI-compatible dependency layout: no local sibling path dependency unless the workflow provisions that path.

### Manual Android Validation

Validate on a real Android device:

1. Install an older Ambientando APK.
2. Start Bridge backend with app update endpoint enabled.
3. Publish or mock a newer update response.
4. Open Ambientando.
5. Confirm update prompt appears.
6. Tap update.
7. Confirm APK downloads.
8. Confirm checksum verification passes.
9. Confirm Android installer opens.
10. Confirm user can install update.
11. Confirm app version/build changed after update.

## Release Plan

1. Implement backend update endpoints and tests.
2. Implement reusable Flutter updater package and tests.
3. Tag the updater package if it is released as a Git package.
4. Integrate updater into Ambientando Calendar.
5. Run all validations.
6. Push app changes.
7. Publish Ambientando APK release.
8. Verify release assets.
9. Install old APK and validate in-app update to the new APK.

Do not publish APK releases until implementation and validation are complete.

## Non-Goals

- Silent Android updates.
- Play Store integration.
- iOS update flow.
- Replacing Android package installer.
- Hardcoding Ambientando-specific logic into reusable packages.
- Requiring each app to call GitHub directly.

## Open Decisions

- Whether update config starts as JSON/YAML or Python settings.
- Whether release metadata should be cached and for how long.
- Whether required updates should block the app or only keep prompting.
- Whether checksum must be mandatory for install.
- Whether `codex_app_updater` should live in the existing bridge repo package namespace or a separate repo later.
