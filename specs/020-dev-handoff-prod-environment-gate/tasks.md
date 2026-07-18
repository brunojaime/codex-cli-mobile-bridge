# DEV Handoff PROD Environment Gate Tasks

- [x] T001 Define environment-gate behavior for PROD, DEV, control, and unknown identity.
- [x] T002 Confirm `/health` publishes PROD handoff capability when the backend flag is enabled.
- [x] T003 Update Flutter slash command context to carry explicit backend environment identity.
- [x] T004 Ensure unknown identity is not rendered as the DEV-only PROD block.
- [x] T005 Add `/dev_handoff` alias resolution to the global `dev-handoff` command.
- [x] T006 Add Flutter model and widget tests for PROD enabled, PROD disabled, DEV blocked, unknown identity, and alias dispatch.
- [x] T007 Add backend tests for `/health` PROD capability publication.
- [x] T008 Run targeted backend and Flutter validation.
