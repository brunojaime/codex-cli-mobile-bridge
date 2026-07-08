# Chat Transcript Lazy Loading Tasks

- [x] T001 Define transcript window response schema.
- [x] T002 Define stable cursor format and ordering contract.
- [x] T003 Define latest-user-message anchor selection rules.
- [x] T004 Define backward compatibility and full-transcript escape hatch.
- [x] T005 Add repository/service method for paged messages before cursor.
- [x] T006 Add repository/service method for latest user anchor window.
- [x] T007 Add API request parameters or endpoint for bounded session detail.
- [x] T008 Add paging metadata to session detail responses.
- [x] T009 Make session list summaries avoid serializing full transcripts.
- [x] T010 Keep full transcript available for explicit export/debug use.
- [x] T011 Extend Flutter API client and models for message windows.
- [x] T012 Update chat controller to load initial latest-user exchange.
- [x] T013 Add upward-scroll lazy loading with scroll-position preservation.
- [x] T014 Add loading, empty, retry, and exhausted-history UI states.
- [x] T015 Deduplicate overlapping pages and live appended messages.
- [x] T016 Preserve composer and active run updates while older pages load.
- [x] T017 Preserve current run/reviewer/job metadata with partial messages.
- [x] T018 Preserve attachment, asset, feedback, and recovery affordances for visible messages.
- [x] T019 Ensure New Project readiness markers and build prompts remain detectable.
- [x] T020 Ensure summary/collapse views still work over the loaded window.
- [x] T021 Add backend tests for anchor selection and cursor pagination.
- [x] T022 Add backend tests for session list lightweight behavior.
- [x] T023 Add Flutter model/API tests for paged transcript payloads.
- [x] T024 Add Flutter widget tests for initial load, scroll-up load, retry, and append behavior.
- [x] T025 Add regression tests for active generator/reviewer conversations.
- [x] T026 Run full backend and mobile validation before deployment.

