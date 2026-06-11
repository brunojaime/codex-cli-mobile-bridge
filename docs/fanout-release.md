# Fanout Release

Use this flow when a shared Flutter package in this repo changes and associated
apps need a new APK even if their product code did not change.

## Register An Associated App

Add the app under the component in
`backend/app/infrastructure/config/app_release_associations.json`:

```json
{
  "sourceApp": "ambientando-calendar",
  "displayName": "Ambientando Calendar",
  "repo": "brunojaime/ambientando-calendar",
  "localPath": "../ambientando-calendar",
  "defaultBranch": "main",
  "pubspecPath": "frontend/pubspec.yaml",
  "releaseTagPrefix": "android-local-demo-feedback-v",
  "releaseWorkflow": "Android Release"
}
```

`localPath` is resolved relative to this repository root. The target repo must
contain the configured `pubspecPath` and the component dependency as a git
dependency with a `url` and `ref`.

## App Update Registry Requirements

The same `sourceApp` must exist in
`backend/app/infrastructure/config/app_updates.json`.

The registry entry must:

- have `enabled: true`;
- use the same `repo`;
- have a `releaseTagPattern` compatible with `releaseTagPrefix`;
- select APK assets that the target app release workflow publishes.

## Commands

Dry-run only:

```bash
python3 scripts/release_associated_apps.py \
  --dry-run \
  --component codex_app_updater \
  --dependency-ref codex-app-updater-v0.1.2 \
  --json
```

Execute locally without push:

```bash
python3 scripts/release_associated_apps.py \
  --execute \
  --component codex_app_updater \
  --dependency-ref codex-app-updater-v0.1.2
```

Execute and push the release branch and tag:

```bash
python3 scripts/release_associated_apps.py \
  --execute \
  --push \
  --component codex_app_updater \
  --dependency-ref codex-app-updater-v0.1.2
```

`--push` is what triggers the target app's tag-based release workflow. Use it
only after checking the dry-run plan.

## Expected Output

For Ambientando Calendar, a fanout release creates:

- branch:
  `release/ambientando-calendar/android-local-demo-feedback-v1.0.0-build.<n>`;
- tag:
  `android-local-demo-feedback-v1.0.0-build.<n>`;
- workflow:
  `Android Release` in `brunojaime/ambientando-calendar`.

For Gestion Ludmilo, a fanout release creates:

- branch:
  `release/gestion-ludmilo/android-v1.0.0-build.<n>`;
- tag:
  `android-v1.0.0-build.<n>`;
- workflow:
  `Android Release` in `brunojaime/Gestion_ludmilo`.

The script bumps the target app build number and updates only the configured
dependency ref in `pubspec.yaml`.

## Manual Recovery

The script runs a full preflight before modifying any associated app. It does
not implement cross-repo rollback after mutation starts.

If a local execute fails after modifying a target repo:

```bash
cd /path/to/associated-app
git status
git tag -d <tag-if-created>
git checkout <default-branch>
git branch -D <release-branch-if-created>
```

If files were modified but no commit was created:

```bash
git restore <pubspecPath>
```

If `--push` already pushed the branch or tag:

```bash
git push origin :refs/heads/<release-branch>
git push origin :refs/tags/<tag>
```

Then fix the cause, rerun dry-run, and execute again.

## GitHub Actions

The manual workflow `.github/workflows/fanout-release.yml` runs this tool with
`workflow_dispatch`.

Default mode is `dry-run`; it does not publish. `execute` and
`execute-and-push` require explicit input. Pushing to associated repos depends
on a token with write permission to those repos, preferably
`FANOUT_RELEASE_GITHUB_TOKEN`.
