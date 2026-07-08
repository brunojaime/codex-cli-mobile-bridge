# Slash Command Palette Plan

## Plan 1: Contract And Registry

- Define the command model.
- Define global and contextual command scopes.
- Define action kinds and availability states.
- Keep feature logic outside the palette.

## Plan 2: Composer UI

- Detect slash invocation from the composer.
- Render a mobile-safe command palette.
- Filter commands as the user types.
- Preserve normal draft text around slash commands.

## Plan 3: Command Dispatch

- Dispatch commands to existing UI actions or feature callbacks.
- Support disabled and hidden commands.
- Add backend capability checks where needed.
- Keep mutating commands explicit and gated.

## Plan 4: Feature Integration

- Register global commands.
- Register New Project contextual commands without implementing guided intake.
- Register Workbench and Apps commands where existing UI already supports them.

## Plan 5: Validation And Release

- Add unit and widget tests.
- Run mobile analyze and tests.
- Publish an Android release only when frontend behavior changes are ready.
