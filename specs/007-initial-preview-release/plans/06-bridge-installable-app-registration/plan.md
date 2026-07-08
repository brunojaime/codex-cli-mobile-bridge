# Bridge Installable-App Registration

Register the preview APK as an installable app entry.

- Add preview channel metadata to the Bridge registration payload.
- Register display name as `<App Name> Preview`.
- Include preview URL, runtime profile, tag, APK asset, update metadata, and
  production readiness state.
- Verify Bridge catalog lookup by `source_app`.
- Block with a manual registration command when Bridge config is missing.
