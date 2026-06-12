# 13. Formal v0.3 Contract

## Objective

Define a stable v0.3 API contract for reusable multi-app developer feedback.

## Required Concepts

- `sourceApp`
- `sourceDisplayName`
- `batchId`
- `quickAskId`
- `jobId`
- `sessionId`
- `runId`
- `workflowPresetId`
- `releaseWhenComplete`
- `status`
- `finalSummary`
- `notifications`
- `audioTranscript`
- `selectionBounds`
- `selectionPoints`
- `provenance`

## Batch Payload

`codex.developerFeedbackBatch` should include:

- `kind`
- `version: 3`
- `batchId`
- `sourceApp`
- `sourceDisplayName`
- `workflowPresetId`
- `releaseWhenComplete`
- `items`

Each item should include:

- `kind: codex.developerFeedback`
- `version: 3`
- `id`
- `comment`
- `screenshotMimeType`
- `screenshotPngBase64`
- `selectionPoints`
- `selectionBounds`
- `audioMimeType`
- `audioBase64`
- `hasAudio`

## Response Payloads

Batch start response should include:

- `batchId`
- `jobId`
- `sessionId`
- `status`
- `sourceApp`

History/status response should include:

- `batchId`
- `status`
- `workflowStatus`
- `jobId`
- `sessionId`
- `runId`
- `itemCount`
- `workflowPresetId`
- `releaseWhenComplete`
- `finalSummary`
- `notificationUnread`

Quick ask response should include:

- `quickAskId`
- `jobId`
- `sessionId`
- `status`
- `answer`
- `provenance`

## Compatibility

- Continue accepting v0.1/v0.2 payload fields where practical.
- Do not break existing Ambientando wrapper integration.
- Add new fields as optional unless required for a new endpoint.
- Apps should discover optional features through capabilities or graceful fallback.

## Validation

- v0.2 batch still works.
- v0.3 batch returns new ids.
- Unknown optional fields are ignored safely.
- Missing required v0.3 fields return 422.
- Source app routing remains generic.
- Second non-Ambientando fixture works.

## Tests

- Backend contract tests for v0.2 compatibility.
- Backend contract tests for v0.3.
- Flutter serialization tests for v0.3.
- Mock HTTP tests for batch, quick ask, status, history, notifications.
- Ambientando tests after package bump.

## Operational Constraint

Do not restart the Bridge backend while validating the contract against active user runs. Use test clients or isolated backend instances.
