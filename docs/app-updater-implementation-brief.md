# App Updater Implementation Brief

## Goal

Integrate the already-existing Bridge-controlled Android APK updater into the Codex Mobile app so Codex Mobile can show an update prompt/button and update itself without the user manually opening GitHub and downloading APKs.

The reusable updater and the Ambientando Calendar pattern already exist. This work is not about reimplementing the wrapper or proving Ambientando works. It is about making Codex Mobile use the same existing updater flow.

## Existing Work To Reuse

Inspect and build on:

- `docs/bridge-controlled-app-updater-plan.md`
- `backend/app/application/services/app_update_service.py`
- `backend/app/infrastructure/config/app_updates.json`
- `/app-updates` routes in `backend/app/api/routes.py`
- `AppUpdate*` schemas in `backend/app/api/schemas.py`
- `packages/codex_app_updater`
- `packages/codex_app_updater/test/codex_app_updater_test.dart`

The existing design already supports:

- app registry by `sourceApp`
- Bridge-owned release discovery
- Bridge APK proxy endpoints
- protected dynamic installable-app registration through `POST /installable-apps`
- reusable Flutter updater package
- Android installer launcher
- Ambientando Calendar registry entry
- Codex Mobile registry entry

Treat these as existing infrastructure to reuse. Do not rebuild them unless a small fix is required to make Codex Mobile consume them.

## Branching Requirement

Do not work on the current branch or dirty working tree. Another Codex may be using it.

Create a separate branch/worktree before editing:

```bash
git fetch origin
git worktree add ../codex-cli-mobile-bridge-app-updater origin/codex/real-streaming-codex-cli -b codex/bridge-controlled-app-updater
```

If that base is not correct, inspect remote branches and choose the right base. Do not reset or clean the current working tree.

## Core Behavior

The Codex Mobile updater flow should be:

1. Codex Mobile starts or resumes.
2. Reusable updater checks Bridge:
   `GET /app-updates/codex-mobile?currentVersion=...&currentBuild=...`
3. Bridge checks configured GitHub Releases server-side.
4. Bridge returns update metadata and a Bridge APK URL.
5. Codex Mobile shows update banner/dialog only if an update is available.
6. User taps update.
7. Codex Mobile downloads APK from Bridge, not directly from GitHub.
8. Codex Mobile verifies checksum when available.
9. Codex Mobile opens Android installer.
10. Android asks user to confirm install.

Silent install is not in scope.

## Important Constraints

- Apps must not call GitHub directly.
- Apps must not contain GitHub tokens.
- Bridge must not leak GitHub token in responses, URLs, headers, or logs.
- Dynamic installable-app registration must require
  `INSTALLABLE_APPS_REGISTRATION_TOKEN`; without it, `POST /installable-apps`
  stays disabled.
- Registration payloads must not include direct external APK URLs. Codex Mobile
  installs only through Bridge APK proxy URLs returned by `/installable-apps`.
- Private GitHub repos may return 404 without authentication; use authenticated tools or Bridge server-side token before concluding a repo/release is missing.
- Do not restart the real Bridge backend while user runs are active. Use tests, TestClient, or isolated processes.
- Do not publish APK releases or tags until reviewer confirms.

## Backend Check

Do not make broad backend changes. First verify the existing backend path for `sourceApp=codex-mobile`:

- `/app-updates/codex-mobile` returns update metadata.
- The returned `apkUrl` points to the Bridge proxy, not directly to GitHub.
- The proxy can serve the configured Codex Mobile APK asset.
- Errors do not leak secrets.

Only patch backend if one of those checks fails.

## Flutter Package Check

Do not reimplement `packages/codex_app_updater`. First verify it already provides what Codex Mobile needs:

- `CodexAppUpdater`
- `CodexAppUpdaterConfig`
- update banner/dialog
- download/checksum/install flow
- disabled/up-to-date no-op behavior
- Android installer permission handling

Only patch the package if Codex Mobile integration exposes a missing piece.

## Codex Mobile Integration

Integrate the existing updater into Codex Mobile, likely under `frontend/mobile_app`.

Codex Mobile should:

- depend on the reusable updater package
- wrap the mobile app with `CodexAppUpdater`
- pass `sourceApp: codex-mobile`
- pass the active Bridge URL
- pass Codex Mobile current version/build
- keep `enabled` configurable
- show nothing when disabled or up-to-date
- show update UI when a newer Codex Mobile APK exists

Do not touch Ambientando Calendar unless a reviewer explicitly asks. Ambientando already follows the wrapper pattern and is not the target of this task.

## Validation

Backend:

```bash
uv run pytest tests/test_message_flow.py
uv run python -m compileall backend
```

If dedicated tests are added:

```bash
uv run pytest tests/test_app_updates.py
```

Updater package, only if touched:

```bash
cd packages/codex_app_updater
flutter pub get
flutter analyze
flutter test
```

Bridge mobile app:

```bash
cd frontend/mobile_app
flutter pub get
flutter analyze
flutter test
```

Ambientando Calendar should not be touched for this task. If it is touched for an unavoidable reason:

```bash
cd /home/batata/Projects/ambientando-calendar/frontend
flutter pub get
flutter analyze
flutter test
```

Manual validation before release:

1. Install older Codex Mobile APK.
2. Bridge reports newer APK through `/app-updates/codex-mobile`.
3. Codex Mobile shows update prompt.
4. Codex Mobile downloads through Bridge proxy.
5. Checksum passes.
6. Android installer opens.
7. User confirms install.
8. Installed build changes.

## Commit And Release Policy

- Use small scoped commits.
- Keep this branch separate from Developer Feedback v0.3 work.
- Do not publish releases until reviewer confirms.
- Report exact commands and results.
