---
name: mcp-app-builder
description: Create or update repo-local MCP apps for codex-cli-mobile-bridge. Use when the user wants a new MCP server/app scaffold, wants to expose new tools/resources/prompts from this repo, or wants the mobile frontend to discover and install that app automatically.
---

# MCP App Builder

Use this skill only inside the `codex-cli-mobile-bridge` repository when the task is to add or evolve repo-local MCP apps.

## What This Repo Now Supports

This repository auto-discovers MCP apps from `mcp_apps/<module_name>/app.json`.

The backend already knows how to:

- inspect repo MCP apps through the real MCP protocol
- list their tools, resources, prompts, and preview data in `/codex/tooling`
- install them into Codex through `/codex/mcp-apps/{app_id}/install`

The Flutter frontend already knows how to:

- show available repo MCP apps in the Codex tools sheet
- preview app data when the app declares a `preview_tool`
- install an app into Codex and enable it for the current run

Do not add bespoke discovery logic for each new app unless the app genuinely needs a new contract.

## Default Pattern

Prefer the repo standard:

1. Create `mcp_apps/<module_name>/__init__.py`
2. Create `mcp_apps/<module_name>/server.py`
3. Create `mcp_apps/<module_name>/app.json`
4. Keep transport as `stdio` unless the user specifically needs remote HTTP
5. Use Python `FastMCP` from the official `mcp` SDK
6. Return JSON-friendly structured data from tools
7. Add a `preview_tool` in `app.json` when the frontend should show a live preview

Use the scaffolder first:

```bash
uv run python codex-skills/mcp-app-builder/scripts/scaffold_mcp_app.py my-app \
  --title "My App" \
  --description "What this app does"
```

After scaffolding, replace the placeholder tool/resource/prompt with the real domain behavior.

## App Spec Contract

Read [references/repo-contract.md](references/repo-contract.md) when you need the exact `app.json` shape and repo conventions.

Important fields:

- `app_id`: stable identifier and folder name
- use kebab-case for `app_id` and underscore module names for the Python package folder when needed
- `recommended_server_id`: the Codex MCP server name the frontend installs
- `command` and `args`: how Codex launches the server
- `env`: runtime variables such as `PROJECTS_ROOT`
- `preview_tool`: optional tool call the backend executes for frontend preview
- `supports_ui_extension`: set this when the server is designed for MCP Apps UI metadata
- `ui_entry_uri`: optional `ui://...` entry when using the UI extension

## Tooling Rules

For safe apps:

- mark tools read-only with `ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)`
- expose at least one tool
- expose a resource and prompt when it helps discovery or reuse

For preview-friendly apps:

- make `preview_tool` deterministic and cheap
- keep preview output small enough for mobile display
- prefer structured JSON, not prose blobs

## Frontend Expectations

No frontend code changes are required for ordinary new apps if they follow the existing contract.

The frontend will automatically show:

- app name and description
- install state
- tool/resource/prompt counts
- preview data from `preview_tool`

Current limitation:

- this repo does not yet render full inline `io.modelcontextprotocol/ui` iframe apps inside Flutter

So if the user asks for a true interactive MCP Apps UI host, that is a larger frontend feature. You can still scaffold the protocol metadata today, but call out that the current mobile client only supports metadata, install flow, and preview rendering.

## Validation

After changes:

1. Run targeted Python tests for MCP tooling/install flows.
2. Run `dart format` on touched Flutter files if any UI code changed.
3. Validate the app over the real protocol by inspecting `/codex/tooling` or by using the backend helper route.
4. If the user wants the app installed for local Codex use, run:

```bash
codex mcp list
codex mcp get <server-id> --json
```

If adding a brand new app, prefer validating installation through the backend install endpoint or `codex mcp add`.
