# Codex Mobile Frontend

This Flutter app is the mobile chat client for the local Codex bridge backend in the repository root.

Run it from this directory:

```bash
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

Use `10.0.2.2` for Android emulators and `localhost` for iOS simulator unless your network setup requires something else.

## Release Networking

The real Android release defaults to `http://batata-default-string.tail0302c4.ts.net`.
That host requires Tailnet/MagicDNS access on the phone. Configure a real HTTPS
public bridge URL for `API_BASE_URL`/`CODEX_APP_UPDATER_BRIDGE_URL` if the APK
must work outside the Tailnet.
