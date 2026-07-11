# Deterministic Init Observability Recovery Tests And Guardrails

Add the verification layer that keeps init deterministic, recoverable, and
honest about release state.

Status: completed

## Deterministic Pipeline Scope

- Backend state transition and idempotency tests.
- GitHub and Cloudflare command construction tests.
- Secret redaction tests.
- Mobile New Project progress UI tests.
- Release guardrails for real preview data paths.
- Workbench/Kanban continuity tests.

## Tasks

- [x] T036 Add backend tests for init state transitions, idempotency, recovery, and phase ordering.
- [x] T037 Add backend tests for GitHub and Cloudflare command construction, blocked recovery, and secret redaction.
- [x] T039 Add Flutter tests for New Project button behavior, init progress UI, blocked states, retry, and first-chat continuity.
- [x] T040 Add release guardrail tests for preview real-data policy, no mock/demo defaults, Android prerelease tags, and Bridge installable registration.
- [x] T041 Add Workbench/Kanban continuity tests for draft/init/job scope moving into the generated workspace.
