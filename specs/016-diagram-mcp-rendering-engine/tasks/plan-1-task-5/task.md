# T005 Define validation errors and warnings

Spec: 016-diagram-mcp-rendering-engine

Plan: Diagram Domain And Schema Contract

Status: pending

- [ ] T005 Define validation errors and warnings.

## Acceptance Notes

- Validation errors include code, path, message, and severity.
- Warnings are non-blocking and preserve renderability when possible.
- Validation covers the full MVP checklist in the spec.

## Implementation Notes

- Use stable error codes for tests and clients.
- Do not return raw exceptions as user-facing validation output.
