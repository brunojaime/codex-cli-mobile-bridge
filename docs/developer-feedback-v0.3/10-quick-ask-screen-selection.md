# 10. Quick Ask On Screen Selection

## Objective

Allow a user to ask a quick question about a selected screen area without triggering implementation.

## User Flow

1. Wrapper is enabled.
2. User long-presses or enters quick ask mode.
3. User marks a screen area.
4. User asks a short question.
5. Bridge sends screenshot, bounds, and question to Codex with answer-only instructions.
6. App displays the answer.

## Prompt Policy

Quick ask must instruct Codex:

- Do not edit files.
- Do not implement changes.
- Explain what may be happening.
- Be concise but useful.
- Suggest likely causes.
- Suggest possible next steps without executing them.

## Backend Impact

- Add quick ask endpoint.
- Use a separate answer-only prompt.
- Persist quick ask records.
- Link response to screenshot/bounds/question.

## Flutter Package Impact

- Add quick ask gesture or mode.
- Add question dialog.
- Show answer result.
- Keep it separate from implementation batch send.

## Validation

- Quick ask does not call batch start-session.
- Prompt contains answer-only instruction.
- Screenshot and bounds are attached.
- Answer is displayed and stored.
- Disabled wrapper has no quick ask behavior.

## Tests

- Backend test for quick ask prompt policy.
- Backend test for quick ask persistence.
- Flutter widget test for long-press or quick ask mode.
- Flutter HTTP mock test for quick ask submission.

## Operational Constraint

Do not restart the Bridge backend while validating quick ask against live Codex sessions. Use isolated tests or a safe maintenance window.
