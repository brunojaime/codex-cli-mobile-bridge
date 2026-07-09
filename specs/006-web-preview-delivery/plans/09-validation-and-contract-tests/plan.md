# Validation And Contract Tests

Add validation layers that fail before a broken preview is reported as ready.

Required checks:

- Cloudflare configuration doctor.
- DNS record lookup for `preview.nienfos.com`.
- D1 migration validation.
- Worker health check.
- Flutter web build.
- Preview URL smoke test.
- Invite accept smoke test using a test invite.
- Contract tests for Preview API v1.
- No-secret scan for generated repos.
- Cost posture report.
- Regression checks that generated release scripts, Android workflow, updater
  endpoint, release metadata, and installable-app registration scripts are still
  generated and validated.
