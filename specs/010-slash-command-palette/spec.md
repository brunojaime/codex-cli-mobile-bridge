---
id: 010-slash-command-palette
title: Slash Command Palette
status: active
type: feature
domains:
  - mobile
  - chat
  - command-palette
  - codex-compatibility
related_specs:
  - 002-sdd-visual-workbench
  - 005-new-project-factory
  - 008-sdd-workbench-lazy-loading
  - 011-new-project-guided-intake
---

# Slash Command Palette

## Intent

Codex Mobile must provide a composer command palette that behaves like Codex
slash commands where applicable. A user should be able to type `/`, filter a
list of available commands, and choose a command without leaving the chat.

## Product Outcome

When a user is in any chat:

- typing `/` opens a command palette;
- typing after `/` filters commands;
- global commands are available from normal chats;
- contextual commands appear only when the current screen, workspace, or mode
  supports them;
- unavailable commands are hidden or clearly disabled with a reason;
- selecting a command either inserts canonical text, opens a native panel, or
  executes a structured action;
- command behavior is deterministic and testable.

## Core Rule

The command palette is a UI/action routing layer. It must not own feature logic.
Features register commands; the palette renders availability and dispatches the
selected command.

## Codex Compatibility

The front should mirror the parts of Codex command behavior that fit Codex
Mobile:

- `/` opens commands from the composer.
- Command names are searchable.
- Commands have concise labels and descriptions.
- Commands may be unavailable while a run is active.
- Some commands are global and some are contextual.
- Commands can be aliases for existing UI actions.
- A command that requires backend capability must be disabled or explain the
  mismatch instead of failing silently.

The implementation does not need to duplicate every terminal-only Codex command
if the mobile app cannot support it safely. Unsupported commands must be
documented as omitted or disabled.

## Command Model

Every command must have:

- `id`: stable identifier.
- `slash`: visible command string, such as `/status`.
- `title`: short display name.
- `description`: one-line explanation.
- `scope`: `global`, `workspace`, `session`, `new_project`, `workbench`, or
  another registered feature scope.
- `availability`: `enabled`, `disabled`, or `hidden`.
- `disabled_reason`: required when disabled.
- `action_kind`: `insert_text`, `send_message`, `open_panel`, `open_route`,
  `call_backend`, or `feature_callback`.
- `payload`: structured action data.
- `requires`: optional backend capabilities, active workspace, active session,
  active draft, or current run state.

## Initial Global Commands

The first implementation should define these commands, using existing app
behavior wherever possible:

- `/new-project`: open or resume New Project mode.
- `/plan`: enter a planning-oriented chat mode if supported.
- `/goal`: view or manage a persistent goal if supported.
- `/review`: request a review of the current workspace or change set.
- `/status`: show session, backend, workspace, and current run status.
- `/feedback`: open feedback submission.
- `/workbench`: open SDD Workbench for the current workspace.
- `/apps`: open installable apps.
- `/compact`: request conversation compaction or summary when supported.
- `/diff`: show current workspace changes when supported.
- `/model`: open model selector when supported.
- `/permissions`: show permissions/sandbox state when supported.

Commands may initially be implemented as disabled placeholders if the underlying
backend/UI capability does not exist yet, but the disabled state must be
explicit and tested.

## Contextual Commands

Features can register contextual commands. Examples:

- New Project can register project-contract, project-preview, and project-build
  commands while a project draft is active.
- Workbench can register commands to open specs, diagrams, governance, or
  feedback actions while the Workbench has a workspace.
- Installable Apps can register commands to open the apps catalog or update the
  current app when an update is available.

The palette must not hardcode feature internals. It should consume a registry
or provider API from feature modules.

## UI Contract

The command palette must:

- open from the composer after `/`;
- keep focus usable on mobile;
- show command label, description, and disabled reason when applicable;
- support keyboard/filter text behavior;
- close on selection, cancel, or composer clear;
- not send a half-written slash command accidentally;
- preserve existing message draft text outside the slash token;
- handle loading and empty states;
- avoid layout overflow on small screens.

## Backend Contract

The backend may provide command metadata for capability-aware commands, but the
first slice can use a frontend registry if backend support is not ready.

If backend metadata is added, it must expose:

- available commands for current session/workspace;
- backend capabilities required by each command;
- disabled reasons;
- command payload schema version.

## Safety Rules

- Commands that can start long-running jobs require explicit user selection.
- Commands that mutate state must not execute merely because `/command` appears
  inside normal text.
- Commands must not bypass existing permissions, review, or publication gates.
- Commands must not auto-run build/release actions while another job is active.
- Unknown commands must fail with a clear UI message and must not be sent as a
  dangerous backend action.

## Non-Goals

- Do not rewrite New Project logic in this spec.
- Do not implement the guided intake contract in this spec.
- Do not change Workbench data models.
- Do not change Android release behavior.
- Do not add terminal-only commands that cannot be represented safely on mobile.

## Acceptance Criteria

- Typing `/` opens the command palette.
- Filtering returns matching global and contextual commands.
- Selecting `/new-project` opens or resumes the existing New Project flow.
- Disabled commands show a reason and do not execute.
- Contextual commands appear only in the relevant mode.
- Command execution is covered by widget/model tests.
- Existing chat send behavior still works for ordinary messages starting with
  text before or after a slash command token.
