# 03. Audio Transcription

## Objective

Transcribe audio attached to feedback items and include the transcript in the Codex prompt.

## User Flow

1. User records audio for a feedback item.
2. User saves item locally.
3. User sends batch.
4. Bridge stores audio and transcribes it.
5. Prompt includes audio transcript beside screenshot/comment/bounds.

## Scope

- Audio capture stays in the reusable Flutter package.
- Transcription happens in the Bridge backend.
- If transcription is unavailable, batch send should still work with audio metadata.
- Transcript should be persisted with the batch/item where possible.

## Backend Impact

- Use existing audio transcriber infrastructure.
- Add transcript field per feedback item.
- Include transcript in generated prompt.
- Surface transcription failures as non-fatal warnings unless policy says otherwise.

## Flutter Package Impact

- No direct transcription logic.
- Display "audio attached" before send.
- Display transcript later if history/detail endpoint returns it.

## Validation

- Audio item with transcriber configured includes transcript in prompt.
- Audio item with disabled transcriber still sends successfully.
- Invalid audio base64 is rejected.
- Transcript is associated with correct feedback item.

## Tests

- Backend test with fake command transcriber.
- Backend test with disabled transcriber fallback.
- Backend test for invalid audio payload.
- Flutter serialization test for audio metadata and bytes.

## Operational Constraint

Do not restart the production Bridge backend to toggle transcription while active feedback runs are in progress. Validate with test settings or an isolated process.
