# Plan

This file is the legacy index for tools that expect a root `plan.md`. The canonical Workbench hierarchy is in `tree.json`.

## Plan 1: Preview Contract And SDD Alignment

- File: [`plans/01-preview-contract-and-sdd-alignment/plan.md`](plans/01-preview-contract-and-sdd-alignment/plan.md)
- Status: `planned`
- Tasks: `6`

## Plan 2: Cloudflare Configuration And Client Boundary

- File: [`plans/02-cloudflare-configuration-and-client-boundary/plan.md`](plans/02-cloudflare-configuration-and-client-boundary/plan.md)
- Status: `done`
- Tasks: `6`

## Plan 3: Preview Runtime Data Model

- File: [`plans/03-preview-runtime-data-model/plan.md`](plans/03-preview-runtime-data-model/plan.md)
- Status: `planned`
- Tasks: `7`

## Plan 4: Cloudflare Worker Preview Runtime

- File: [`plans/04-cloudflare-worker-preview-runtime/plan.md`](plans/04-cloudflare-worker-preview-runtime/plan.md)
- Status: `in_progress`
- Tasks: `8`

## Plan 5: Flutter Web Preview Adapter

- File: [`plans/05-flutter-web-preview-adapter/plan.md`](plans/05-flutter-web-preview-adapter/plan.md)
- Status: `in_progress`
- Tasks: `6`

## Plan 6: Admin Invite And Email Delivery

- File: [`plans/06-admin-invite-and-email-delivery/plan.md`](plans/06-admin-invite-and-email-delivery/plan.md)
- Status: `planned`
- Tasks: `7`

## Plan 7: Project Factory Backend Integration

- File: [`plans/07-project-factory-backend-integration/plan.md`](plans/07-project-factory-backend-integration/plan.md)
- Status: `in_progress`
- Tasks: `7`

## Plan 8: Mobile And Workbench UX

- File: [`plans/08-mobile-and-workbench-ux/plan.md`](plans/08-mobile-and-workbench-ux/plan.md)
- Status: `planned`
- Tasks: `5`

## Plan 9: Validation And Contract Tests

- File: [`plans/09-validation-and-contract-tests/plan.md`](plans/09-validation-and-contract-tests/plan.md)
- Status: `in_progress`
- Tasks: `7`

## Plan 10: Operations And Documentation

- File: [`plans/10-operations-and-documentation/plan.md`](plans/10-operations-and-documentation/plan.md)
- Status: `planned`
- Tasks: `9`

## Notes

### Implementation Order

1. Contract and docs first.
2. Cloudflare doctor/client second.
3. Worker runtime and D1 third.
4. Flutter preview adapter fourth.
5. Factory job integration fifth.
6. Mobile/Workbench UX sixth.
7. End-to-end validation last.

This keeps infrastructure validation and contract tests ahead of user-facing
claims that previews are ready.
