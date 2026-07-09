# Plan 1: Message Window Contract

Define the public contract for partial transcript loading.

## Scope

- Response schema for bounded transcript windows.
- Cursor format and chronological ordering rules.
- Latest user-authored message anchor semantics.
- Backward-compatible full transcript access for explicit debug/export flows.

## Acceptance

- Backend and frontend can agree on a partial transcript response without guessing.
- Existing behavior remains available only through an explicit compatibility path.

