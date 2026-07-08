# Chat Transcript Lazy Loading Tasks

- [ ] T001 Define transcript window response schema.
- [ ] T002 Define stable cursor format and ordering contract.
- [ ] T003 Define latest-user-message anchor selection rules.
- [ ] T004 Define backward compatibility and full-transcript escape hatch.
- [ ] T005 Add repository/service method for paged messages before cursor.
- [ ] T006 Add repository/service method for latest user anchor window.
- [ ] T007 Add API request parameters or endpoint for bounded session detail.
- [ ] T008 Add paging metadata to session detail responses.
- [ ] T009 Make session list summaries avoid serializing full transcripts.
- [ ] T010 Keep full transcript available for explicit export/debug use.
- [ ] T011 Extend Flutter API client and models for message windows.
- [ ] T012 Update chat controller to load initial latest-user exchange.
- [ ] T013 Add upward-scroll lazy loading with scroll-position preservation.
- [ ] T014 Add loading, empty, retry, and exhausted-history UI states.
- [ ] T015 Deduplicate overlapping pages and live appended messages.
- [ ] T016 Preserve composer and active run updates while older pages load.
- [ ] T017 Preserve current run/reviewer/job metadata with partial messages.
- [ ] T018 Preserve attachment, asset, feedback, and recovery affordances for visible messages.
- [ ] T019 Ensure New Project readiness markers and build prompts remain detectable.
- [ ] T020 Ensure summary/collapse views still work over the loaded window.
- [ ] T021 Add backend tests for anchor selection and cursor pagination.
- [ ] T022 Add backend tests for session list lightweight behavior.
- [ ] T023 Add Flutter model/API tests for paged transcript payloads.
- [ ] T024 Add Flutter widget tests for initial load, scroll-up load, retry, and append behavior.
- [ ] T025 Add regression tests for active generator/reviewer conversations.
- [ ] T026 Run full backend and mobile validation before deployment.

