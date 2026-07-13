# PROD DEV App Release And Environment UI Plan

## Goal

Ship separate DEV and PROD app identities so the same DEV frontend can show
stage-specific chats while PROD remains visibly stable and distinct.

## Scope

- DEV/PROD release channels.
- App labels, badges, colors, API URLs, updater channels.
- Frontend environment header.
- Release validation.
- GitHub Actions or deterministic release wrapper updates.

## Tasks

- T043 Define DEV and PROD release channels, app labels, environment badges, color tokens, API base URLs, updater channels, and workspace/stage visibility rules.
- T044 Add backend configuration for separate DEV and PROD app/update channels without mock/demo defaults.
- T045 Add frontend environment banner/header rendering that is independent from existing `CODEX DEV` developer-mode signal.
- T046 Build release validation for DEV APK and PROD APK to verify labels, colors, API URLs, updater URLs, and environment identity.
- T047 Update Android release workflow or deterministic release wrapper to support DEV and PROD channels safely.
- T048 Add Flutter/widget tests for distinct DEV/PROD UI colors, badges, headers, and stage identity display.

## Acceptance Criteria

- DEV and PROD apps are visually distinct in the first viewport.
- Existing `CODEX DEV` developer-mode signal is not repurposed.
- Release validation fails when API URLs, updater URLs, badges, labels, or color
  identities are wrong.
- DEV release and PROD release cannot be confused by tag/channel metadata.

## Validation

- Flutter tests for labels, colors, badges, and stage header.
- Android release-network validation for each channel.
- Release workflow dry-run or artifact validation.

