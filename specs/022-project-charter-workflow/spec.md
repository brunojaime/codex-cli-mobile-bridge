# Project Charter Workflow

id: 022-project-charter-workflow
status: completed
owner: codex-mobile-bridge

## Intent

Make the approved Project Charter a required source contract for every future
project created through New Project. The charter must be generated from the
confirmed guided intake and approved domain brief before any UX, Generator,
Reviewer, implementation, or release work can continue.

## Functional Contract

- New Project writes `docs/project-charter.md` and
  `docs/project-charter.json` after the user confirms the build contract.
- The metadata records approval status, version, timestamp, document path, and
  SHA-256 digest.
- Deterministic init blocks when approval data or the approved scope is missing.
- Project Factory and Domain Factory block when the charter is absent or its
  required metadata is absent; Project Factory also verifies the approved
  status and content digest before running agents.
- UX, Generator, Reviewer, implementation, SDD, and release prompts read the
  charter first and preserve traceability to it.
- Generated repositories protect both charter files as managed baseline files.

## SDD And Mobile Contract

- SDD project responses expose the charter as a first-class document.
- SDD marks the charter as required for generated projects identified by
  `.codex/project.yaml`; unrelated legacy repositories are not degraded.
- Flutter renders the charter in a full-screen reader on narrow phones and a
  constrained reader on larger screens.
- Reading content uses selectable text, continuous vertical scrolling, a
  maximum readable line width, 16 px body text, and comfortable line height.
- Users can share the charter by email with multiple recipients and an optional
  message.
- `Include full document` defaults to enabled. SMTP delivery includes the full
  body and a Markdown attachment; Cloudflare delivery includes the complete
  document body for every recipient.

## Acceptance Criteria

- An unapproved or scope-empty draft cannot create a charter.
- Full generation cannot start from a blocked deterministic init.
- A missing, unapproved, or digest-mismatched charter blocks Project Factory
  before the first model-driven phase.
- SDD returns the complete charter content and reports a missing charter on a
  generated project.
- Phone and tablet widget tests open the reader without overflow.
- The email request sends all recipients and preserves the full-document flag.
- Release-facing behavior continues using real backend and data paths.

