# Deterministic Flutter Workbench Feedback Updater And Runtime Baseline

Move app baseline wiring into init so the LLM starts with Flutter, Workbench,
feedback, updater, and runtime profiles already present.

Status: completed

## Deterministic Pipeline Scope

- Flutter baseline app and Android/web targets.
- Runtime profile wiring against real preview API/D1.
- Workbench and SDD metadata discovery.
- Codex developer feedback template wiring.
- Updater Bridge URL wiring.
- Frontend strategy capability enforcement.

## Tasks

- [x] T022 Generate or verify Flutter baseline app, Android project, web target, and runtime profile wiring before business implementation LLM work.
- [x] T023 Wire Workbench/SDD metadata and Bridge-owned Workbench discovery during init.
- [x] T024 Wire Codex developer feedback template, source app identity, updater Bridge URL, and feedback queue routing during init.
- [x] T025 Validate that preview runtime uses real Cloudflare Preview API/D1 and does not use mock/demo or placeholder URLs.
- [x] T026 Enforce frontend strategy capability limits before Android/installable phases.
