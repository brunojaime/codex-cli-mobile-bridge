# Preview Completeness Hardening Plan

Close false-ready gaps in the Initial Preview Release contract.

This plan makes the first generated release fail closed unless the preview APK,
Cloudflare preview, Preview API, D1 persistence, Workbench visibility, Bridge
installable-app lookup, runtime profile metadata, Worker deploy format, and final
release output all agree.

The implementation keeps production release blocked until explicit promotion and
uses `prerelease` as the Bridge/GitHub release channel for `android-preview-v*`.
