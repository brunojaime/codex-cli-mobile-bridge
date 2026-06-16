# Codex App Updater

Reusable Bridge-controlled Android APK updater for Codex Mobile Bridge apps.

## Android Background Download Validation

The Android implementation downloads APKs through `DownloadManager` into:

```text
<external-files>/Download/codex_app_updates/<safe-apk-name>
```

`FileProvider` exposes `external-files-path`, so the installer receives a
`content://` URI with `FLAG_GRANT_READ_URI_PERMISSION`.

The Flutter downloader waits for the native plugin to report
`DownloadManager.STATUS_SUCCESSFUL`. Enqueueing the Android download is not
treated as completion. `STATUS_FAILED` is returned as a download failure with
the Android reason code in the message.

Manual validation checklist for a real device or emulator:

1. Install a build that contains this package.
2. Configure the Bridge to report a newer APK release.
3. Start the update from the app.
4. Press Home or lock the screen while the download is active.
5. Wait for the Android download notification to finish.
6. Reopen the app and tap the update action again if the installer is not
   already open.
7. Confirm the Android package installer opens for the downloaded APK.

The native plugin persists the `DownloadManager` id, source URL, safe filename,
and APK path. If the Flutter controller is recreated, the next update action
reuses or queries the existing Android download instead of blindly enqueueing a
second stale APK.
