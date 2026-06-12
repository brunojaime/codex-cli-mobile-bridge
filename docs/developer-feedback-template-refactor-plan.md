# Developer Feedback Template Refactor Plan

## Objective

Refactor the current Ambientando Calendar developer feedback flow into a reusable Codex Mobile Bridge capability without changing the existing behavior.

The current Ambientando Calendar integration works and must continue to work exactly the same from a user perspective:

- The template can be enabled in the client app.
- The developer can mark a screen area, add a comment, optionally attach audio, and send the item to Codex CLI through the bridge.
- The Mobile Bridge receives the item in the feedback queue.
- The queue item is associated with the correct workspace.
- Screenshots and metadata can be staged into the chat composer or submitted to a Codex run.
- Existing Ambientando Calendar tests and bridge tests continue to pass.

This is a refactor, not a feature rewrite. The only intended behavior change is that the same mechanism becomes reusable by other client apps with minimal setup.

## Non-Goals

Do not redesign the editor UI.

Do not change the current Ambientando Calendar workflow.

Do not change queue semantics, attachment semantics, or how Codex runs are started except where hardcoded Ambientando naming must become generic.

Do not require every future client app to duplicate and maintain its own copy of the feedback editor implementation.

Do not add a broad plugin system, app marketplace, or MCP UI host as part of this work. This plan is only about the developer feedback template and Mobile Bridge queue integration.

Do not release anything until tests and review confirm the refactor is complete.

## Target State

The developer feedback template should become a reusable client-side integration owned by the Codex Mobile Bridge ecosystem.

A future Flutter app should integrate it with a small, explicit setup similar to:

```dart
MaterialApp(
  builder: (context, child) => CodexDeveloperFeedbackTemplate(
    enabled: const bool.fromEnvironment('CODEX_FEEDBACK_TEMPLATE_ENABLED'),
    sourceApp: const String.fromEnvironment('CODEX_FEEDBACK_SOURCE_APP'),
    sourceDisplayName: const String.fromEnvironment('CODEX_FEEDBACK_SOURCE_NAME'),
    bridgeUrl: const String.fromEnvironment('CODEX_FEEDBACK_BRIDGE_URL'),
    child: child ?? const SizedBox.shrink(),
  ),
)
```

The exact class and environment variable names can change during implementation, but the final integration must stay this simple:

1. Add the reusable template dependency or shared source.
2. Wrap the app once near `MaterialApp`.
3. Provide a stable `sourceApp` identifier.
4. Provide the Mobile Bridge URL.
5. Build the client app.

## Current Coupling To Remove

Ambientando Calendar currently owns the template implementation under its app source tree.

The client payload hardcodes Ambientando-specific values:

- `sourceApp: ambientando-calendar`
- payload kinds such as `ambientando.developerFeedback`
- Ambientando-specific README instructions

The Mobile Bridge is mostly generic already, but still has Ambientando-specific defaults and prompt text:

- `FeedbackQueueItemRequest.sourceApp` defaults to `ambientando-calendar`
- the direct start-session prompt says `Ambientando Calendar`
- tests mostly use Ambientando fixtures, even though some already cover other project names

The Mobile Bridge workspace matching currently depends on normalizing `sourceApp` and comparing it to the workspace name or fallback path name. That can work for multiple apps, but it should be made explicit and extensible so app names, repo names, and display names do not have to be identical.

## Required Work

### 1. Extract The Template

Move the reusable template out of `ambientando-calendar` ownership.

Acceptable implementation options:

- A reusable Flutter package checked into `codex-cli-mobile-bridge`, for example `packages/codex_developer_feedback_template`.
- A documented shared source module generated or vendored from this repo into client apps.

Prefer the package-like option if it keeps future app integration simpler and keeps one canonical implementation.

The extracted template must include:

- visual overlay and toolbar
- area selection and drawing
- screenshot capture
- comment capture
- optional audio capture where supported
- queue export JSON
- bridge submission
- tests for the reusable package/module

### 2. Parameterize Client Identity

Replace Ambientando hardcoding with explicit configuration:

- `sourceApp`: stable machine identifier, for example `ambientando-calendar`, `smart-nienfos`, or `maep-platform`
- `sourceDisplayName`: human-readable label, for example `Ambientando Calendar`
- `bridgeUrl`: Mobile Bridge base URL
- `enabled`: compile-time or runtime flag

The template should still support a custom submission callback for tests or special clients.

The default bridge payload should use generic names:

- `kind: codex.developerFeedback`
- `version: 1`
- `queue: codexCli`
- `sourceApp`
- `sourceDisplayName`
- `comment`
- `createdAt`
- `screenshotMimeType`
- `screenshotPngBase64`
- `selectionPoints`
- `selectionBounds`
- optional audio metadata and bytes

Keep backward compatibility with the current Ambientando payload shape for existing queued items.

### 3. Generalize Mobile Bridge Feedback Queue

Update the bridge so the queue contract is app-agnostic.

Required backend changes:

- Remove the Ambientando default from `FeedbackQueueItemRequest.sourceApp`; use an explicit source when provided and a neutral fallback such as `unknown`.
- Accept optional `sourceDisplayName`.
- Persist and return `source_display_name` where available.
- Replace hardcoded `Ambientando Calendar` prompt text with a generic prompt based on `source_display_name`, `source_app`, or selected workspace name.
- Preserve existing API compatibility for current Ambientando clients.

Required frontend changes:

- Display the source display name when available.
- Keep current feedback queue UX unchanged for Ambientando.
- Keep screenshot staging and composer metadata behavior unchanged.
- Make workspace matching explicit and extensible.

### 4. Add Explicit App-To-Workspace Matching

Do not rely only on normalized string equality between `sourceApp` and workspace name.

Add one simple mapping mechanism. Keep it small.

Acceptable options:

- A bridge-side config/env mapping, for example `FEEDBACK_SOURCE_WORKSPACE_ALIASES=ambientando-calendar:/home/.../ambientando-calendar,smart-nienfos:/home/.../smart_nienfos`
- A lightweight aliases file under bridge data/config.
- A workspace metadata field surfaced by the project catalog.

The chosen approach must allow:

- `sourceApp` to stay stable even if the display name changes.
- one source app to map to one workspace path.
- future aliases without code changes.
- fallback to the current normalized-name behavior when no mapping exists.

### 5. Migrate Ambientando Calendar

After the bridge supports the generic contract, migrate Ambientando Calendar to consume the reusable template.

Ambientando must keep the same external behavior:

- same enable behavior for the feedback toolbar
- same bridge URL behavior
- same screenshot/comment/audio behavior
- same feedback queue behavior in Mobile Bridge

Ambientando-specific values should become configuration:

- `CODEX_FEEDBACK_TEMPLATE_ENABLED=true`
- `CODEX_FEEDBACK_SOURCE_APP=ambientando-calendar`
- `CODEX_FEEDBACK_SOURCE_NAME=Ambientando Calendar`
- `CODEX_FEEDBACK_BRIDGE_URL=<bridge-url>`

Existing legacy flags can remain as aliases for one release if that avoids breaking current build scripts.

### 6. Tests And Validation

Add or update tests at each layer.

Reusable template tests:

- disabled template renders only the child
- enabled template shows the toolbar
- selection plus comment creates a queue item
- payload includes configurable `sourceApp` and `sourceDisplayName`
- bridge submission posts to `/feedback-queue`
- export JSON stays stable
- legacy/custom submission path remains covered

Mobile Bridge backend tests:

- accepts generic source app payload
- accepts current Ambientando payload
- persists source display name
- direct start-session prompt is generic and contains the correct source/workspace
- screenshot and audio handling remain unchanged
- invalid target mode behavior remains unchanged

Mobile Bridge Flutter tests:

- Ambientando queue still appears for Ambientando workspace
- a second app source appears for its mapped workspace
- source aliases work when source app and workspace name differ
- unrelated app feedback does not appear in the wrong workspace
- selected screenshots are staged into the composer with the same marked-area instruction
- target mode still supports generator-only and generator-plus-reviewer

End-to-end/manual validation:

- run the bridge backend locally
- build/run Ambientando with the feedback template enabled
- submit screenshot feedback from Ambientando
- confirm the bridge queue receives it
- confirm it appears under the Ambientando workspace
- stage it into chat and verify image attachment plus metadata
- submit/start a run and verify the generated prompt is no longer Ambientando-hardcoded except through configured display name

### 7. Release Rules

This refactor may require two releases:

- a new Codex Mobile Bridge frontend/backend release if the bridge app or API changes
- a new Ambientando Calendar frontend release only if Ambientando client code or build configuration changes

Do not release Ambientando Calendar if the bridge-only phase keeps the current Ambientando client fully compatible and no Ambientando code changes are made.

Do release Ambientando Calendar after migrating it to the reusable template, because the Flutter frontend bundle must include that change.

The reviewer decides when the implementation is complete enough to release. A release is allowed only after:

- tests pass
- the reviewer confirms the behavior is unchanged for Ambientando
- the reviewer confirms the integration path is generic for at least one non-Ambientando app fixture
- any required manual validation has been completed or explicitly waived

## Done Means Done

The implementation is complete only when all of the following are true:

- Ambientando Calendar works exactly as before.
- The reusable template has no Ambientando-specific hardcoding.
- A second app can integrate by setting configuration and wrapping its app, without editing bridge internals.
- The bridge queue stores, displays, filters, stages, and submits feedback from multiple apps.
- Workspace matching is configurable and still has the current fallback behavior.
- All relevant tests pass.
- Release requirements are clear, and releases are cut only if the reviewer determines they are necessary and ready.

Do not expand the scope beyond this list.
