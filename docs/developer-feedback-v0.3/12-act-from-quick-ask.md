# 12. Act From Quick Ask

## Objective

Let the user convert a quick ask answer into an implementation task after reading the explanation.

## User Flow

1. User asks a quick question.
2. Codex answers without implementing.
3. User taps `Actuar` or `Crear tarea`.
4. App opens implementation flow using original screenshot, bounds, question, and answer.
5. User chooses preset and release option.
6. App sends a normal implementation batch.

## Scope

- Quick ask remains answer-only.
- Acting from quick ask starts a separate implementation workflow.
- The implementation prompt includes the prior answer as context.
- User still chooses preset and release option.

## Backend Impact

- Support converting quick ask record into batch payload or accepting quick ask reference in batch.
- Preserve link between implementation batch and quick ask id.

## Flutter Package Impact

- Add `Actuar` action on quick ask answer.
- Pre-fill implementation comment from question/answer.
- Reuse existing batch preview/send UI.

## Validation

- Quick ask alone does not implement.
- Act action creates implementation batch.
- Batch includes quick ask provenance.
- Preset selection still works.
- Release option still works.

## Tests

- Backend test for quick ask reference in batch.
- Flutter widget test for act action.
- HTTP mock test proving implementation endpoint is called only after act.

## Operational Constraint

Do not restart Bridge backend while converting an active quick ask into a run.
