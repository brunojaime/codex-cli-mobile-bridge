# Validation And Regression Coverage

Add tests that prevent historical false-readiness regressions and preview/production
mixups.

- Test first release defaults to preview.
- Test a job cannot become `ready` without Cloudflare preview and Bridge
  registration.
- Test missing Cloudflare config becomes `blocked`.
- Test missing Bridge config becomes `blocked`.
- Test preview APK metadata points to preview API, not production or localhost.
- Test productive tags still require production backend health and release
  signing.
- Test mock/demo tags stay visibly separate.
