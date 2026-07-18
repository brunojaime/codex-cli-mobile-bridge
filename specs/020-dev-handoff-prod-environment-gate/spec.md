# DEV Handoff PROD Environment Gate

id: 020-dev-handoff-prod-environment-gate
status: completed
owner: codex-mobile-bridge

## Intent

Fix the production regression where `/dev-handoff` is blocked in the production
chat with the message `DEV handoff is only available from PROD.` even though the
user is already in PROD.

## Problem

The mobile slash command layer must decide whether `/dev-handoff` is enabled
from backend environment identity and capabilities. A missing or still-loading
identity was being treated the same as a non-PROD environment, which can show a
false DEV-only block in production.

The command also has two expected spellings in operator usage:

- `/dev-handoff`
- `/dev_handoff`

Both spellings must resolve to the same global command and handler.

## Requirements

- The backend `/health` payload remains the source of truth for environment
  identity.
- PROD means `environment_identity.environment == "prod"`.
- DEV means `environment_identity.environment == "dev"`.
- The handoff command is enabled only when PROD identity also allows
  `enqueue_dev_handoff` and does not deny it.
- The message `DEV handoff is only available from PROD.` may appear only when
  the backend explicitly identifies the current environment as non-PROD.
- Missing or not-yet-loaded environment identity must not be mislabeled as DEV.
- `/dev_handoff` and `/dev-handoff` must route to the same `dev-handoff`
  handler.
- Mobile and any supported client must rely on the same backend identity and
  capability contract.

## Acceptance Criteria

- From PROD with `enqueue_dev_handoff` allowed, `/dev-handoff` opens the handoff
  flow.
- From PROD without `enqueue_dev_handoff`, `/dev-handoff` is disabled with a
  backend capability message, not a DEV environment message.
- From DEV, `/dev-handoff` stays blocked with
  `DEV handoff is only available from PROD.`
- If environment identity is unavailable, the UI reports unavailable identity
  instead of claiming the user is not in PROD.
- `/dev_handoff` resolves to the same `dev-handoff` handler as `/dev-handoff`.
- Backend and Flutter tests cover the PROD, DEV, unknown identity, and alias
  cases.

## Implementation Notes

- Keep the backend fail-closed: the frontend must not assume PROD when
  environment identity is missing.
- Preserve the existing one-shot draft grant before enqueueing mobile handoffs.
- Do not enable mock data or demo state for this production handoff path.
