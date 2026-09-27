# Nienfos Mobile Pipeline

Reusable local React Native release orchestration for Codex Mobile Bridge. Gestión is the first deployed consumer. Builds and GitHub Releases run on the operator host; GitHub Actions is never invoked.

## Agent workflow

1. `list_mobile_projects` and `mobile_status`: inspect enrolled project manifests.
2. `prepare_android_signing`: create/reuse private host signing state and record only its public certificate fingerprint.
3. `bump_mobile_version`: increment the Android build and choose a nondecreasing SemVer. Validate and commit the consumer before building.
4. `start_mobile_job(project, "build")`: build from clean, versioned source using the shared engine. Poll `mobile_job_status`.
5. `verify_android_install`: install that exact APK on a booted emulator, verify launch and unauthenticated API denial, and save runtime evidence. Real login and biometrics remain explicitly unverified until exercised.
6. `start_mobile_job(project, "publish", approval_reference)`: verify provenance, create an immutable annotated tag and publish APK/checksums/receipts in the private GitHub repository. Requires existing human publication authorization.
7. `register_mobile_catalog(project, display_name, approval_reference)`: verify the published GitHub asset digest, register a preview APK through the existing Bridge API and stream the proxied download to verify its digest. Catalog updates preserve other apps. The Bridge service registration credential must already be in the environment; agents never pass its value as a tool argument.

`mobile_sdk_plan` and `update_mobile_sdk` compare/promote the centrally managed session SDK. Custom consumer changes fail closed. Promotion still requires tests, commit, native rebuild and authorized distribution. Updating Bridge does not silently replace installed native binaries.

## Runtime

The project must live directly under `PROJECTS_ROOT` and contain `infra/mobile/project.json` and `infra/mobile/release.json`. Node 22, Java 17, Android SDK/NDK and authenticated GitHub CLI are required. iOS requires a macOS runner; store credentials and submissions are separate from this preview APK flow.

Build workers serialize operations per project. Private jobs live under `~/.local/state/nienfos-mobile-jobs`; signing credentials live under `~/.local/state/nienfos-mobile-signing`. Raw logs, keys and credentials never appear in tool results. Preserve signing identities in private recoverable storage.

Catalog registration currently targets this Bridge's loopback API on port 8000. Its existing API generates download URLs for the requesting remote host, so authenticated tailnet clients download through their Bridge connection. A loopback probe may instead report the configured public preview domain; this is not proof of remote download availability. Verify the actual tailnet URL when delivering.

## First consumer evidence

- Source: `brunojaime/nienfos-gestion`, tag `android-preview-v0.1.0-build.1`.
- Android identity: `com.nienfos.gestion.preview`; real API: `https://qa.gestion.nienfos.com`.
- Local MCP build, Android emulator install/launch, GitHub publication and catalog download exercised on 2026-09-27.
- Architecture/security specification: Gestión `specs/007-mobile-application-pipeline/`.
- Delivery evidence: Gestión `docs/reports/2026-09-27-mobile-delivery/`.
- iOS, store submission, real-device biometrics and adoption by a second project are separate remaining validations.
