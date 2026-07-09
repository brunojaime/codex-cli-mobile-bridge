# GitHub And Release Readiness

- Create an initial local git commit for every generated project.
- In remote publication mode, execute the generated GitHub publish script so the
  repository is actually created/verified and pushed, not merely documented.
- Generate and execute an Android release script that creates the productive tag,
  pushes it, waits for the GitHub Actions release workflow, and verifies APK
  assets.
- Register the published APK in the Bridge installable-app catalog so Codex
  Mobile can show it under Apps.
- Leave an explicit `blocked` publish state when GitHub, release, Bridge URL, or
  registration-token configuration is missing. Do not report `ready` for local
  foundations that have not been remotely published.
- Generate AWS, App Store, and Play Store readiness files.
- Keep Google, AWS, Apple, and Play credentials as explicit pending items.
